# 100样本并行采集与模型验证

使用已安装的`deta-generator 0.1.2`和新增的`scripts/run-parallel.ps1`。脚本调用已有的分片生成与校验合并入口，没有更改电磁求解、材料、网格或数据指纹代码，不需要重新安装Python包。

单条`generate`内部逐个求解。新增脚本同时启动多个独立Python生成器，每一路的单次求解仍采用`processes=1`，默认每路16线程。四路共64线程；`--processes`是单结构求解的MPI进程数，不代表同时生成多少个结构。

## 配置

- 新任务目录：`jobs/au100_metal8_100`，保留已有12样本任务。
- 100 nm Au，仅金属z网格8 nm；其余区域自动网格；七参数范围和固定种子不变。
- 100个不同结构，每个1000个波长点；预先固定80训练、10验证、10测试。
- 四片，每片25个ID：0/4/8…、1/5/9…、2/6/10…、3/7/11…。所有分片读取同一个job.json，输出分别为shard0…shard3。
- 版本、材料拟合、几何、状态及校验值由生成器在续算/合并时检查。12样本任务和100样本任务指纹不同，不直接混合旧文件。

## Windows / PyCharm终端

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

不用创建四个PyCharm运行配置。终端中的监控脚本每30秒汇报实际成功/运行/失败/待运行数量，统计时仅计入各分片所属ID，不把其他75个未分配ID当成本片遗漏。

在另一个终端可查看总体状态：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-parallel.ps1 -Command status -Python python -Workers 4 -Concurrency 4 -Threads 16
Get-Content .\jobs\au100_metal8_100\parallel_logs\shard0.stdout.log -Tail 20 -Wait
```

内部时间步进度仍位于每片`projects/sample_XXXXXX_p0.log`，例如第一片首结构：`jobs/au100_metal8_100/shard0/projects/sample_000000_p0.log`。脚本默认保持FDTD窗口隐藏。

同时运行多个原生会话需要机器上的许可实际允许相应并发；预检不证明并发许可可用。若四路中出现许可不足，其他成功样本保留，脚本拒绝宣布100样本完成。解决问题后重跑同一命令会跳过完整、合格样本。

如果机器许可只支持两路，可保留四分片方案，改为分两轮，每路32线程：

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

四路16线程尚未实测，不能把25.53小时直接除以4。分片完工时间由最慢那一路决定；结构共振寿命、网格数量、重试、线程减少及共享内存带宽都会影响每个样本的时间。

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
