# Deta Generator：七参数FDTD数据生成包

**0.1.5 尾部加速：** 原任务进入最后几个分片时，可校验保留成功数据，停止原采集进程，再将剩余样本按单个编号动态分发。支持单文件脚本配合原 0.1.4 包运行，无需重装正在使用的环境。操作及当前未保存仿真进度的影响见 [尾部加速说明](docs/tail_resume.md)。物理求解实现与既有 0.1.4 完全相同。

独立于模型训练项目，用于在另一台已安装 **Lumerical FDTD的Windows计算机**上生成As₂Se₃四聚体真实光谱数据。支持Au、Ag及有限基板不镀金对照。无需安装PyTorch、CUDA或Metaformer训练代码；求解采用Lumerical原生CPU引擎，增加线程不会保证等比例加速。

七参数顺序为 `[P,L,H,dX,dY,theta_odd_deg,theta_even_deg]`，前五项nm，后两项deg。代码键为 `p,l,h,alpha_x,alpha_y,theta_odd_deg,theta_even_deg`。I/III共享奇数角，II/IV共享偶数角，各柱绕自身中心旋转，角度独立且以90°为周期。dX/dY是未旋转时的名义边缘间隙；每个采样结构检查旋转后的碰撞与周期边界。

## 在计算机上运行

**2026-10-16更新：0.1.4增加明确的`--jobs 10`并发入口、自动线程分配和原生引擎监控。** 沿用0.1.2的仅金属层加密求解代码，Au厚度仍为100 nm。更新包不会修改已有的`job.json`。0.1.2/0.1.3/0.1.4的三份物理实现文件逐字节相同，可继续对应任务；历史0.1.0/0.1.1任务仍用对应wheel，禁止跨网格策略混用数据。

使用Lumerical版本兼容的Python环境；本机实际连接验证使用Python3.10、Lumerical2024 R1。必须有可用FDTD求解许可，包不包含Lumerical软件、许可或凭据。

```powershell
git clone https://github.com/CypherZzzyer05/Deta_Generator.git
cd Deta_Generator
python -m pip install --upgrade .

# 先创建任务。12只是流程验证样本量，正式训练需按研究目标扩大。
python -m deta_generator init --job-dir jobs/au100_metal --preset au-metal --samples 12 --threads 32
# 指向新计算机的安装路径；以下路径是示例，请改成实际版本与目录。
$env:LUMERICAL_LUMAPI_PATH = 'C:\Program Files\Lumerical\v241\api\python\lumapi.py'
python -m deta_generator doctor --config jobs/au100_metal/job.json
python -m deta_generator preflight --config jobs/au100_metal/job.json
python -m deta_generator plan --config jobs/au100_metal/job.json
# 先算一个样本，核对资源、耗时、材料和光谱，然后去掉limit采集完整计划。
python -m deta_generator generate --config jobs/au100_metal/job.json --limit 1
python -m deta_generator generate --config jobs/au100_metal/job.json
python -m deta_generator status --config jobs/au100_metal/job.json
```

没有Git时可下载仓库ZIP，解压后在包含`pyproject.toml`的目录执行`python -m pip install --upgrade .`。也可下载仓库 `artifacts/deta_generator-0.1.4-py3-none-any.whl`，运行 `python -m pip install --upgrade <wheel文件路径>`。wheel内已带默认配置、As₂Se₃材料文件和Windows并行控制器。安装依赖只有NumPy与psutil；使用前仍需本机原生Lumerical API和求解许可。

也可使用安装后的 `deta-generator` 命令，或Windows脚本：

```powershell
.\scripts\run-windows.ps1 -Command generate -Config jobs/au100_metal/job.json -Threads 32 -Limit 1
```

`doctor`检查API连接、版本和实际材料拟合；`preflight`另外构造首个计划结构，读取实际网格和原生内存估计，**二者均不运行电磁求解**。它们不证明求解许可、光谱收敛或设备精度。生成时每个结构都重新做网格与内存检查；内存不足则拒绝启动该样本。原生内存建议是近似值，尤其共形网格仍需实际试算。

## 网格、镀层和计算成本

默认预设为`au-metal`，另有`ag-metal`、`bare-metal`。`mesh_policy="metal_only"`模式只创建`metal_mesh`，只覆盖金属层及上下各一个金属网格步长的界面邻域，默认z网格2.5 nm；x/y不强制覆盖。其他区域使用Lumerical自动网格，`mesh_accuracy=4`。不创建`global_mesh_limit`或`structure_mesh`，`maximum_mesh_nm=null`。旧配置中的`mesh_nm`不参与该模式的覆盖网格构造。

需要金属层8 nm时在新任务初始化时显式设置：

```powershell
python -m deta_generator init --job-dir jobs/au100_metal8 --preset au-metal --metal-mesh-nm 8 --samples 12 --threads 32
```

金属层请求步长必须严格小于10 nm；其实际z单元（包括跨金属界面的单元）逐个复查。所有实际x/y/z坐标仍保存并在续算/合并时复查，但自动网格区域允许超过10 nm，报告不会把这种数据宣称为全域小于10 nm。网格策略来自用户2026-10-14的实战要求；加速幅度和光谱误差需在目标机器试算确认。

显式历史预设`au-4`、`au-8`、`ag-4`、`ag-8`、`bare-4`、`bare-8`保留原全域和结构覆盖网格，仅供有意选择该策略的新任务使用。它们不是新版默认模式。此前全域8→4 nm的精度结果不能代替仅金属加密模式的收敛验证。

Au预设为As₂Se₃ / 350 nm SiO₂ / **100 nm Au** / 空气，法向x偏振，700–1700 nm；Ag预设仍显式使用150 nm。Au厚度是固定物理设置，七个几何自由度不变。`bare`以100 nm Au布局作为参考，使用 `remove_metal=true`，仅移除金属物体，保留有限基板、源、监测器、下方空气域及参考金属区网格，并要求移除前后网格一致。**不能用 `metal_material=null` 替代这个受控不镀金结构。** 当前有限薄基板不代表毫米厚实物基片。

`bare-metal`是配对对照：先生成Au参考布局的自动网格，再把参考x/y步长写入现有`metal_mesh`物体后删除金属，避免因删除材料造成x/y网格变粗。它仍只保留一个金属区域网格物体，逐轴验证移除前后网格相同；不另加全域或四聚体网格。Au/Ag自身的x/y始终不加覆盖。参考x/y不是均匀网格或删除后坐标仍改变时，该对照会拒绝运行。

每个训练样本输出1000个均匀波长点的R/T/A。1000是每条光谱的点数，`--samples`才是不同几何结构数量。为控制数据集成本，这个包默认只记录远场光谱；当前本机金层/网格研究的两平面E/H分析与报告仍在独立研究项目中进行。

## 迁移、续算和分片

按相同命令重跑即可跳过校验成功的样本，补算缺失、失败或损坏的数据。Ctrl+C保留已经完成的样本；中断的当前样本下次重新算。更换机器时复制整个任务目录，并通过 `--lumapi`、`--threads`、`--output`指定新机器路径和资源。修改几何范围、采样数、种子、网格、材料内容或物理设置时须使用新任务目录。

线程数、进程数、API路径和输出位置不进入物理指纹；原始材料内容及生成代码进入指纹。续算和合并要求同一求解器版本，实际材料拟合按1e−7容差核对。固定计划中的样本ID和训练/验证/测试归属不会按完成顺序变化。每个样本完成后立即保存NPZ和manifest；默认每25个尝试及正常/可捕获中断退出时刷新汇总数据集，可用 `--pack-every`调整，避免大型批次每次都重读全部数据。

强机器可先提高单个FDTD任务的线程数；要多任务并行时，按下面方式给不同任务独立输出目录。每个任务占用独立许可和内存，线程总数与峰值内存由使用者按机器资源配置。不要让多个任务写入同一输出目录。

**自动并行入口：** 在PyCharm的Python运行配置中调用`parallel --jobs 10`，同时启动十个独立样本任务；不指定线程时按实际CPU预算分配。新任务默认使用数倍于并发数的小分片，空闲槽接下一片，全部结束自动校验合并。进度分别显示子生成器数和实际观测到的原生引擎数，支持失败续算。也保留独立Windows脚本`scripts/run-parallel.ps1`。操作见[并行说明](docs/parallel_100.md)。

```powershell
# 两条命令在不同终端/机器执行，使用同一job.json与同一版本的包。
python -m deta_generator generate --config jobs/au100_metal/job.json --shard-count 2 --shard-index 0 --output jobs/au100_metal/shard0 --threads 16
python -m deta_generator generate --config jobs/au100_metal/job.json --shard-count 2 --shard-index 1 --output jobs/au100_metal/shard1 --threads 16
# 两个任务结束后，把分片目录复制到同一机器并合并。
python -m deta_generator merge --config jobs/au100_metal/job.json --shards jobs/au100_metal/shard0 jobs/au100_metal/shard1 --output jobs/au100_metal/merged
```

合并验证配置、采样计划、划分、校验值、实际网格、求解状态、版本及拟合；冲突的重复ID拒绝合并。合并不会删除分片。一个任务的 `plan`已固定采样几何；多机器首次建立计划时需使用相同NumPy版本以确保采样序列一致，合并时仍逐项核对实际几何。

## 输出与模型接口

- `manifest.json`：固定七参数计划、划分、物理指纹、状态、版本、拟合及运行记录。
- `samples/sample_XXXXXX.npz`与CSV：每个成功样本的原始R/T/A、混合单位标签、实际网格坐标及求解记录。
- `projects/`：本机原生FSP、实际网格和资源检查，默认保存；不提交Git。
- `dataset.npz`：`spectra[N,1000]`、`geometry_values[N,7]`、`geometry_01[N,7]`、`parameter_names`、`parameter_units`、`lower_values`、`upper_values`、固定划分索引，以及T/A等。
- `summary.json`、`generation.log`、`errors.jsonl`：完成数量、日志与失败原因。

光谱保留入射功率归一化R，不做逐条min-max缩放、不裁剪不合理结果。未达到自动关断时最多四次延长时间；不合格样本排除在训练数据之外。可用 `pack`再次校验和打包已有成功数据，全程不调用求解器。

## PyCharm与运行进度

**同时计算十个样本：** 复制已有`au8nm`的Python运行配置，模块保持`deta_generator`，例如下一批计划1000个结构，参数栏填：

```text
parallel --job-dir jobs/au100_metal8_1000_p10 --samples 1000 --jobs 10
```

安装0.1.4后点击运行即可。入口自动创建新任务、读取首个原生布局/网格，再启动采集；全部成功后合并到该任务的`merged/dataset.npz`。64个可用逻辑CPU时默认十路各6线程；128个时各12线程，启动时打印实际检测结果。`--jobs`是同时计算几个样本，`--threads`是每个样本用几线程，`--samples`是总样本数，三者不同。无须单独下载PowerShell脚本或创建十个运行配置。解释器选择`fdtd_gen`，工作目录保持项目根目录，沿用v251环境变量。取消勾选两个将内容根/源根添加到PYTHONPATH的选项，避免旧源码遮蔽安装包。

旧四分片任务按原计划续跑；不能在同一目录把四个固定分片改成十个。新十路任务使用新目录。单条`generate`仍是有意保留的串行入口，控制台会明确标记SERIAL，不能用`--threads 10`代替`parallel --jobs 10`。

运行配置选择Python模块`deta_generator`，解释器选择安装本包的Conda环境，工作目录设为项目根目录。环境变量`LUMERICAL_LUMAPI_PATH`指向本机`lumapi.py`；例如用户v251安装路径为`E:\Lumerical\ANSYS Inc\v251\Lumerical\api\python\lumapi.py`。参数栏填`init --job-dir jobs/au100_metal --preset au-metal --samples 12 --threads 32`，之后依次换成`preflight --config jobs/au100_metal/job.json`及`generate --config jobs/au100_metal/job.json --limit 1`。

控制台记录样本开始/完成及重试；当前求解器内部进度通过原生日志查看，在PyCharm PowerShell终端执行：

```powershell
Get-Content ".\jobs\au100_metal\data\projects\sample_000000_p0.log" -Tail 20 -Wait
```

`job.json`中`hide_fdtd=false`可在下次启动时显示FDTD界面。进度百分比对应当前仿真时间上限；达到自动关断可以提前结束。更新安装不改变已经运行中的Python进程，应等当前试算结束或自行停止后再安装新版，不要在旧任务目录中切换网格模式。

## 材料与验证范围

As₂Se₃采用Joseph实测700 nm薄膜n/k，CSV原始SHA256为 `9e6ee6d3b584f33226d7201e2b2e12490726cb3b8256726754e5aca9cae64ce9`；材料说明与CC0来源随包提供。实测至1688 nm，最后12 nm是显式端点延拓。Au/Ag使用本机Lumerical Palik库，未随包分发其数据。

**当前Au默认FDTD拟合存在明显损耗误差。** 本包保持已有研究配置以便复现，输出记录材料精度未验证及实际拟合误差，质量标记沿用 `pipeline_validation`，现有Metaformer训练入口需要显式允许流程验证数据才能读取。它不会悄悄替换材料或将生成数据宣称为实验预测。大规模采集前请查看 `doctor.json` 的材料误差；改为100 nm没有修复材料拟合；该问题的器件级验证仍待后续研究。网格检查、自动关断与材料准确性是不同验证项。

软件验证使用测试替身检查续算、迁移、分片及完整性，测试数据不作为研究数据。真实研究求解来自Lumerical；目标机器上的许可、运行速度和材料拟合必须在该机器试算确认。继承来源与方法文档见 [SOURCE.md](SOURCE.md)。
