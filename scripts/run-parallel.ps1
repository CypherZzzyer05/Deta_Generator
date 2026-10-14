param(
    [ValidateSet('prepare','run','status','merge')]
    [string]$Command = 'prepare',
    [string]$Python = 'python',
    [string]$JobDir = '.\jobs\au100_metal8_100',
    [ValidateRange(1,1000000)][int]$Samples = 100,
    [ValidateRange(1,64)][int]$Workers = 4,
    [ValidateRange(1,64)][int]$Concurrency = 4,
    [ValidateRange(1,1024)][int]$Threads = 16,
    [string]$Lumapi = '',
    [ValidateRange(1,10000)][int]$PackEvery = 10
)
$ErrorActionPreference = 'Stop'
$jobRoot = [System.IO.Path]::GetFullPath($JobDir)
$configPath = Join-Path $jobRoot 'job.json'
$layoutPath = Join-Path $jobRoot 'parallel_plan.json'
$mergedPath = Join-Path $jobRoot 'merged'
$pythonInfo = & $Python -c 'import sys,json,deta_generator,psutil; print(json.dumps(dict(python=sys.executable,version=deta_generator.__version__,cpus=psutil.cpu_count())))'
if ($LASTEXITCODE -ne 0) { throw 'Cannot load deta_generator in the selected Python environment.' }
$pythonInfo = $pythonInfo | ConvertFrom-Json
if ([version]$pythonInfo.version -lt [version]'0.1.2') { throw 'Install deta-generator 0.1.2 or newer first.' }
$pythonExe = $pythonInfo.python
if ($Concurrency -gt $Workers) { $Concurrency = $Workers }
if ($Command -eq 'run' -and $Concurrency * $Threads -gt $pythonInfo.cpus) {
    throw "Concurrency * Threads exceeds the $($pythonInfo.cpus) logical CPUs available."
}

function Invoke-Generator([string[]]$GeneratorArgs) {
    & $pythonExe -m deta_generator @GeneratorArgs
    if ($LASTEXITCODE -ne 0) { throw "Generator failed: $($GeneratorArgs -join ' ')" }
}

function Assert-Task {
    if (-not (Test-Path -LiteralPath $configPath) -or -not (Test-Path -LiteralPath $layoutPath)) {
        throw 'Run -Command prepare once in a new job directory first.'
    }
    $taskConfig = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $layout = Get-Content -LiteralPath $layoutPath -Raw | ConvertFrom-Json
    if ($taskConfig.sample_count -ne $Samples -or $layout.samples -ne $Samples -or $layout.workers -ne $Workers) {
        throw 'Sample count and shard count are fixed. Use a new JobDir to change them.'
    }
    if ($taskConfig.simulation.mesh_policy -ne 'metal_only' -or $taskConfig.simulation.metal_mesh_nm -ne 8 -or
        $taskConfig.simulation.metal_thickness_nm -ne 100 -or $taskConfig.simulation.remove_metal) {
        throw 'This launcher requires the 100 nm Au / metal-only 8 nm task.'
    }
}

function Show-Progress {
    $counts = @{ pending=0; running=0; success=0; failed=0 }
    for ($index=0; $index -lt $Workers; $index++) {
        $manifestPath = Join-Path $jobRoot "shard$index\manifest.json"
        $manifest = $null
        if (Test-Path -LiteralPath $manifestPath) {
            $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        }
        for ($sampleId=$index; $sampleId -lt $Samples; $sampleId+=$Workers) {
            $state = 'pending'
            if ($null -ne $manifest) { $state = $manifest.samples[$sampleId].state }
            $counts[$state]++
        }
    }
    Write-Host ("{0}  success={1}/{2}, running={3}, failed={4}, pending={5}" -f
        (Get-Date -Format 'HH:mm:ss'),$counts.success,$Samples,$counts.running,$counts.failed,$counts.pending)
    return $counts
}

function Merge-Results {
    $mergeArgs = @('merge','--config',$configPath,'--output',$mergedPath,'--shards')
    for ($index=0; $index -lt $Workers; $index++) { $mergeArgs += (Join-Path $jobRoot "shard$index") }
    Invoke-Generator $mergeArgs
    $summary = Get-Content -LiteralPath (Join-Path $mergedPath 'summary.json') -Raw | ConvertFrom-Json
    if ($summary.success -ne $Samples) { throw "Only $($summary.success)/$Samples samples were merged. Rerun missing/failed shards before training." }
    Write-Host "Dataset ready: $(Join-Path $mergedPath 'dataset.npz')"
}

# Start-Process joins ArgumentList into one Windows command line. Quote each
# argument using the Windows CRT rules so directories with spaces work too.
function Quote-WindowsArgument([string]$Value) {
    return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}

if ($Command -eq 'prepare') {
    if (Test-Path -LiteralPath $configPath) {
        Assert-Task
    } else {
        $initArgs = @('init','--job-dir',$jobRoot,'--preset','au-metal','--metal-mesh-nm','8',
                      '--samples',"$Samples",'--threads',"$Threads")
        if ($Lumapi) { $initArgs += @('--lumapi',$Lumapi) }
        Invoke-Generator $initArgs
        @{ samples=$Samples; workers=$Workers; created_at=(Get-Date).ToString('o') } |
            ConvertTo-Json | Set-Content -LiteralPath $layoutPath -Encoding UTF8
    }
    Invoke-Generator @('plan','--config',$configPath)
    Write-Host "Prepared $Samples samples, $Workers shards. Each shard has an independent output directory. No FDTD run started."
    exit 0
}

Assert-Task
if ($Command -eq 'status') { $null = Show-Progress; exit 0 }
if ($Command -eq 'merge') { Merge-Results; exit 0 }

New-Item -ItemType Directory -Force -Path (Join-Path $jobRoot 'parallel_logs') | Out-Null
$active = @()
$nextIndex = 0
$failedWorkers = @()
$lastDisplay = [datetime]::MinValue
$controllerLock = $null
$pidPath = Join-Path $jobRoot 'parallel_workers.json'
$runtimeWorkers = @()
Write-Host "Running up to $Concurrency concurrent samples, $Threads threads per sample."
try {
    try {
        $controllerLock = [System.IO.File]::Open((Join-Path $jobRoot '.parallel-controller.lock'),
            [System.IO.FileMode]::OpenOrCreate,[System.IO.FileAccess]::ReadWrite,[System.IO.FileShare]::None)
    } catch { throw 'Another parallel controller is using this task.' }
    if (Test-Path -LiteralPath $pidPath) {
        $previousWorkers = (Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json).workers
        foreach ($previousWorker in $previousWorkers) {
            $previousProcess = Get-Process -Id $previousWorker.pid -ErrorAction SilentlyContinue
            if ($null -ne $previousProcess -and $previousProcess.ProcessName -eq $previousWorker.process_name) {
                throw "A previous worker is still running (PID $($previousWorker.pid)); wait for it before restarting."
            }
        }
    }
    while ($nextIndex -lt $Workers -or $active.Count -gt 0) {
        while ($nextIndex -lt $Workers -and $active.Count -lt $Concurrency) {
            $workerArgs = @('-m','deta_generator','generate','--config',$configPath,'--processes','1','--threads',"$Threads",
                '--shard-count',"$Workers",'--shard-index',"$nextIndex",'--output',(Join-Path $jobRoot "shard$nextIndex"),
                '--pack-every',"$PackEvery",'--fail-fast')
            $argumentLine = ($workerArgs | ForEach-Object { Quote-WindowsArgument $_ }) -join ' '
            $stdout = Join-Path $jobRoot "parallel_logs\shard$nextIndex.stdout.log"
            $stderr = Join-Path $jobRoot "parallel_logs\shard$nextIndex.stderr.log"
            $process = Start-Process -FilePath $pythonExe -ArgumentList $argumentLine -WorkingDirectory $jobRoot -WindowStyle Hidden -PassThru `
                -RedirectStandardOutput $stdout -RedirectStandardError $stderr
            # Windows PowerShell 5.1 needs a retained native handle to expose
            # ExitCode reliably after a redirected child process has exited.
            $null = $process.Handle
            $runtimeWorkers += @{ index=$nextIndex; pid=$process.Id; process_name=$process.ProcessName }
            @{ workers=@($runtimeWorkers) } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $pidPath -Encoding UTF8
            $active += [pscustomobject]@{ Index=$nextIndex; Process=$process }
            Write-Host "Started shard $nextIndex, PID $($process.Id). Log: $stdout"
            $nextIndex++
        }
        $remaining = @()
        foreach ($worker in $active) {
            $worker.Process.Refresh()
            if ($worker.Process.HasExited) {
                $worker.Process.WaitForExit()
                $workerExitCode = $worker.Process.ExitCode
                if ($null -eq $workerExitCode -or $workerExitCode -ne 0) { $failedWorkers += $worker.Index }
                Write-Host "Shard $($worker.Index) exited with code $workerExitCode."
            } else { $remaining += $worker }
        }
        $active = $remaining
        if (((Get-Date)-$lastDisplay).TotalSeconds -ge 30 -or $active.Count -eq 0) {
            $null = Show-Progress
            $lastDisplay = Get-Date
        }
        if ($active.Count -gt 0) { Start-Sleep -Seconds 5 }
    }
} finally {
    # Interrupting this monitor must not silently terminate native simulations.
    foreach ($worker in $active) {
        if (-not $worker.Process.HasExited) {
            Write-Warning "Shard $($worker.Index) is still running (PID $($worker.Process.Id)). This script did not stop it."
        }
    }
    if ($null -ne $controllerLock) { $controllerLock.Dispose() }
}
if ($failedWorkers.Count -gt 0) {
    throw "Failed shards: $($failedWorkers -join ', '). Results are preserved. Inspect their logs; rerun after resolving the error."
}
Merge-Results
