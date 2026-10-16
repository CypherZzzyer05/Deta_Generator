# 100样本并行采集与模型验证

`deta-generator 0.1.4`提供明确的`--jobs 4/10`入口和独立原生引擎监控，可像原来的au8nm一样在PyCharm中点击运行。求解、材料、网格与数据指纹实现沿用0.1.2，三份物理源文件SHA256完全相同，数据实现标识仍为`deta-generator/0.1.2`。已有任务保持原计划续算；新版Python入口和仓库内新版PS脚本均需安装0.1.4。

## 本次更新：十个样本同时计算

用户上一批日志已经显示四个独立PID；传回manifest的四路样本处理区间也明确重叠。因此本次没有把一个已证实串行的控制器“修成并行”，而是补齐可选择十路、细分任务和真实进度证据。完整服务器记录见[100样本并行审计](server_100_concurrency_audit.md)。

PyCharm模块保持`deta_generator`，下一批例如计划1000样本，参数直接填写：

```text
parallel --job-dir jobs/au100_metal8_1000_p10 --samples 1000 --jobs 10
```

- `jobs=10`表示最多同时计算十个不同结构；`threads`表示每个结构的线程数，`processes=1`仍为每个结构的MPI进程数。
- 不填threads会自动分配：64个可用逻辑CPU为10×6=60线程；128个为10×12=120线程。操作系统检查包含Windows所有处理器组，并显示旧系统或亲和性限制；不修改系统亲和性。
- 新任务默认建立`min(样本数, jobs×4, 64)`个固定小分片，因此1000样本/10路对应40片、每片25样本，最多10片同时活跃。一个完成就接下一片。`workers`是固定分片数，通常无需填写。
- 控制台显示`workers_alive`（活着的Python生成器）和`native_engines`（实际观测到的FDTD引擎），还有各片当前sample、百分比、Auto Shutoff及日志更新时间。引擎数是进程树观察下界；权限或父进程关系可能使部分引擎不可见。
- `parallel_launch.json`记录安装包路径、版本、CPU检查、十路资源预算；`parallel_status.json`记录当前和曾观测到的峰值引擎数。监控持续观察到多worker但仅0/1引擎时提示核对初始化、许可、资源及权限，不能只凭PID数宣称原生并发。
- Windows监控使用共享读写删除句柄，读取JSON字节后立即关闭，再解析。并行子生成器入口对短暂的JSON原子替换共享冲突做有界重试（最多40次、间隔50毫秒）；永久权限错误仍报错。这仅改变结果持久化策略，三份物理源文件及其指纹保持原样。

仅看状态可复制运行配置，在同一行末尾加`--parallel-action status`；不启动新求解。仍可用`--parallel-action prepare`只准备和固定计划。独立PS入口也支持`-Jobs 10`；需要先prepare并按原步骤preflight：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-parallel.ps1 -Command prepare -JobDir .\jobs\au100_metal8_1000_p10 -Samples 1000 -Jobs 10 -Python python -Lumapi 'E:\Lumerical\ANSYS Inc\v251\Lumerical\api\python\lumapi.py'
python -m deta_generator preflight --config jobs/au100_metal8_1000_p10/job.json
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-parallel.ps1 -Command run -JobDir .\jobs\au100_metal8_1000_p10 -Samples 1000 -Jobs 10 -Python python
```

已有四分片目录不允许直接请求十路或改变workers，拒绝时不会改样本。继续旧任务仍用`--workers 4 --jobs 4`；原样本不会变成新1000样本计划的一部分，跨不同sample_count的任务禁止直接合并。此次没有修改采样、材料、网格、自动关断及数据质量，也没有自动扩采服务器数据。

单条`generate`内部逐个求解。新增脚本同时启动多个独立Python生成器，每一路的单次求解仍采用`processes=1`，默认每路16线程。四路共64线程；`--processes`是单结构求解的MPI进程数，不代表同时生成多少个结构。

## 配置

- 新任务目录：`jobs/au100_metal8_100`，保留已有12样本任务。
- 100 nm Au，仅金属z网格8 nm；其余区域自动网格；七参数范围和固定种子不变。
- 100个不同结构，每个1000个波长点；预先固定80训练、10验证、10测试。
- 历史显式四片计划：每片25个ID，分别为0/4/8…、1/5/9…等；新版未指定workers的新100样本/四路任务采用16小片。所有分片读取同一个job.json，各自写shardN。
- 版本、材料拟合、几何、状态及校验值由生成器在续算/合并时检查。12样本任务和100样本任务指纹不同，不直接混合旧文件。

## PyCharm点击运行（推荐）

1. 安装仓库`artifacts/deta_generator-0.1.4-py3-none-any.whl`，确认版本为0.1.4。
2. 复制原来的au8nm Python运行配置，名称改为`Au8nm_100并行`，模块保持`deta_generator`。
3. 解释器保持`E:\anaconda3\envs\fdtd_gen\python.exe`；工作目录保持`E:\CypherzZ\PythonProject\Deta_Generator-main\Deta_Generator-main`。
4. 环境变量保持`LUMERICAL_LUMAPI_PATH=E:\Lumerical\ANSYS Inc\v251\Lumerical\api\python\lumapi.py`。取消两个添加内容根/源根到PYTHONPATH的勾选，避免旧源码覆盖已安装版本。
5. 参数栏填以下一行，点击运行：

```text
parallel --job-dir jobs/au100_metal8_100 --samples 100 --workers 4 --concurrency 4 --threads 16
```

首次运行自动准备100样本计划、完成首结构原生预检，再启动四片。运行窗口每30秒显示总体成功/运行/失败/待运行数量，并给出分片日志路径；求解器时间步百分比仍写入各片原生日志。预检或准备失败时不会启动分片，需先解决控制台错误。再次运行会校验并跳过已有合格样本。

只查看状态时，复制该配置，在参数末尾添加`--parallel-action status`；只准备计划而暂不求解则添加`--parallel-action prepare`。同一入口可用`--parallel-action run`跳过重复预检，或`--parallel-action merge`单独合并。各动作保持同一个job-dir、samples和workers。

PyCharm停止按钮不保证终止后台求解子进程。控制器保存PID，发现上次子生成器仍运行会拒绝重复启动；需要查看进度时使用status配置。

## Windows / PyCharm终端（保留入口）

在项目根目录的PowerShell终端中，先激活`fdtd_gen`。下载新脚本时可直接从仓库下载该单个文件，不需要Git。

```powershell
conda activate fdtd_gen
# 创建100样本的任务和固定计划；这一步不运行FDTD。
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-parallel.ps1 -Command prepare -Python python -Workers 4 -Concurrency 4 -Threads 16 -Lumapi 'E:\Lumerical\ANSYS Inc\v251\Lumerical\api\python\lumapi.py'
# 读取首结构网格与资源；不运行FDTD。
python -m deta_generator preflight --config jobs/au100_metal8_100/job.json
# 同时跑四路；四片结束后校验并自动合并。
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-parallel.ps1 -Command run -Python python -Workers 4 -Concurrency 4 -Threads 16
```

不用创建四个PyCharm运行配置。监控脚本每30秒汇报实际成功/运行/失败/待运行数量，统计时仅计入各分片所属ID，不把其他75个未分配ID当成本片遗漏。

在另一个终端可查看总体状态：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-parallel.ps1 -Command status -Python python -Workers 4 -Concurrency 4 -Threads 16
Get-Content .\jobs\au100_metal8_100\parallel_logs\shard0.stdout.log -Tail 20 -Wait
```

内部时间步进度仍位于每片`projects/sample_XXXXXX_p0.log`，例如第一片首结构：`jobs/au100_metal8_100/shard0/projects/sample_000000_p0.log`。脚本默认保持FDTD窗口隐藏。

同时运行多个原生会话需要机器上的许可实际允许相应并发；预检不证明并发许可可用。若四路中出现许可不足，其他成功样本保留，脚本拒绝宣布100样本完成。解决问题后重跑同一命令会跳过完整、合格样本。

如果机器许可只支持两路，可保留四分片方案，改为分两轮，每路32线程：

PyCharm参数改为`parallel --job-dir jobs/au100_metal8_100 --samples 100 --workers 4 --concurrency 2 --threads 32`；终端入口如下：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-parallel.ps1 -Command run -Python python -Workers 4 -Concurrency 2 -Threads 32
```

`Workers`是固定分片数；`Concurrency`是同时启动的片数。创建任务后保持Workers=4，后者和线程数可按实际资源改变。每片内存依结构变化，已测首结构原生建议约1.68 GiB；四片启动仅按该例估计约6.7 GiB，不能当作实际峰值。目标机约211 GiB可用内存，当前规模主要需要关注实际CPU吞吐和并发许可。

中断父监控脚本不会自动终止已经启动的子生成器，脚本会提示仍在运行的PID；不要在子任务未结束时再次启动同一任务。每个输出目录仍有生成器独占锁。任务失败后的结果保留，合并不会删除分片。

控制器自身也持有任务锁，并记录已启动的子进程PID；发现前一次的生成器仍在运行时拒绝重复启动。`status`只读状态，不持有生成锁。

## 输出

全部成功后得到`jobs/au100_metal8_100/merged/dataset.npz`，包含`[100,1000]`反射谱、`[100,7]`标签、R/T/A及固定80/10/10划分；若不是100个成功样本，脚本明确报错。将完整任务目录保留用于溯源，给训练机器传送merged/dataset.npz即可加载。

## 时间估算

目前只有首结构单任务32线程实测：919.078秒（15分19秒）。按同样平均耗时，100个串行约25.53小时。

以下是采集100样本前的历史场景估算。现已传回的四路16线程100样本实际总历时26小时35分钟，均值56.41分钟/样本（累计调用耗时除以100），最慢样本7小时27分钟。16%的延时重跑样本贡献约62.1%的累计耗时；这些值包含等待，不能当CPU工时。新十路尚未在服务器原生实测，不能承诺比四路快2.5倍。详细数据见并行审计。

| 四路并发下的假定平均单样本耗时 | 每片25个样本的预计时间 |
|---|---:|
| 20分钟 | 8小时20分钟 |
| 30分钟 | 12小时30分钟 |
| 40分钟 | 16小时40分钟 |
| 60分钟 | 25小时 |

这些是场景估算，不是对这台机器的并发实测。首轮四片各完成一个样本后，用各片实际速度更新预计时间。并行速度不能只由CPU核心数或RAM容量推导。

## 模型验证

用户接受目前仅金属8 nm的谱位误差，先做100样本模型流程验证；继续保留`pipeline_validation`标记。训练使用已有Metaformer七输出、square_periodic角度损失，明确允许流程验证数据，固定80/10/10划分，比较测试集误差与训练集均值基线。训练期间不使用测试集选择模型，报告长度参数MAE、角度周期误差、训练/验证曲线及过拟合程度。

100样本适合检验采集、数据接口和训练流程，并提供初步泛化信号；若只在训练集拟合很好，不能据此宣布逆设计能力成立。当前材料拟合和场增强精度尚未验证，训练结果描述为对当前仿真数据的学习。训练在已有研究项目中进行，数据生成机器无需额外安装PyTorch。

准备好的[训练配置模板](train_metaformer_100.json)沿用现有七参数Metaformer/ResNet结构，最多100轮、batch=8、早停20轮，验证集选模型；模板需复制到研究项目的`configs`中，并将真实merged/dataset.npz放在该项目`data/as2se3_au100_metal8_100/dataset.npz`。然后运行`python train_metaformer.py --config configs/train_metaformer_100.json`。生成器仓库不包含训练代码或PyTorch依赖，尚未用这批真实100样本训练。

## 依据

- [Ansys并行性能调优](https://optics.ansys.com/hc/en-us/articles/4403788796947-Getting-the-Best-FDTD-Performance)：实际最佳线程/进程配置和吞吐需对模型及硬件测量。
- [Ansys求解与并发许可](https://optics.ansys.com/hc/en-us/articles/360058577794-Ansys-optics-solve-accelerator-and-Ansys-HPC-license-consumption)：并发许可随许可类型、启动方式和核心数变化，不能仅由一次求解成功推断。
- [Microsoft全部处理器组计数](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-getactiveprocessorcount)：ALL_PROCESSOR_GROUPS读取全系统逻辑处理器。
- [Microsoft处理器组](https://learn.microsoft.com/en-us/windows/win32/procthread/processor-groups)：Windows11/Server2022起默认可跨处理器组；旧系统采用保守预算并显示硬件总数。
- [psutil CPU说明](https://psutil.readthedocs.io/stable/#psutil.cpu_count)：系统逻辑CPU数与进程可用CPU不一定相同。
- [Python官方Windows原子替换讨论](https://bugs.python.org/issue46003)：已有目标文件被读取时，MoveFileEx可能失败，即使读句柄允许共享删除；不能只依赖读取端的共享标志。
