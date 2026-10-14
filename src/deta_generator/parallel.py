"""PyCharm-friendly entry to the packaged Windows shard controller."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


def run_parallel(job_dir, samples=100, workers=4, concurrency=None, threads=16,
                 lumapi=None, action='start', pack_every=25):
    if sys.platform != 'win32':
        raise ValueError('The automatic parallel controller is currently for Windows')
    if samples < 1 or not 1 <= workers <= min(samples, 64):
        raise ValueError('Require samples>=1 and 1<=workers<=min(samples,64)')
    concurrency = workers if concurrency is None else concurrency
    if not 1 <= concurrency <= 64 or threads < 1 or pack_every < 1:
        raise ValueError('Concurrency, threads and pack interval must be positive')
    shell = shutil.which('powershell') or shutil.which('pwsh')
    if shell is None:
        raise FileNotFoundError('Windows PowerShell is required for the parallel controller')
    script = Path(__file__).parent/'assets/scripts/run-parallel.ps1'
    if not script.is_file():
        raise FileNotFoundError('Packaged controller missing; reinstall deta-generator 0.1.3 or newer')
    job_dir = Path(job_dir).resolve()
    api = lumapi or os.environ.get('LUMERICAL_LUMAPI_PATH')
    env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
    base = [shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
            '-Python', sys.executable, '-JobDir', str(job_dir), '-Samples', str(samples),
            '-Workers', str(workers), '-Concurrency', str(concurrency), '-Threads', str(threads),
            '-PackEvery', str(pack_every)]
    if api:
        base += ['-Lumapi', api]

    def invoke(command):
        # Inherit stdout/stderr so progress appears in PyCharm's Run window.
        return subprocess.run(base+['-Command', command], env=env).returncode

    if action != 'start':
        return invoke(action)
    print(f'Preparing {samples} samples; {workers} shards; up to {min(workers,concurrency)} concurrent FDTD jobs.', flush=True)
    code = invoke('prepare')
    if code:
        return code
    print('Checking the first native layout and mesh; no FDTD engine run in preflight.', flush=True)
    preflight = [sys.executable, '-m', 'deta_generator', 'preflight', '--config', str(job_dir/'job.json'),
                 '--threads', str(threads)]
    if api:
        preflight += ['--lumapi', api]
    code = subprocess.run(preflight, env=env).returncode
    if code:
        return code
    print('Starting CPU dataset generation; successful shards are merged automatically.', flush=True)
    return invoke('run')
