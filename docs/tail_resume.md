# 剩余样本的尾部加速

0.1.5 新增 `deta_generator.tail`。原来的 `parallel` 控制器按固定分片逐个计算，进入最后几片时，并发数可能下降。本入口在原控制器及其工作进程停止后，校验已有成功数据，把原计划里尚无合格结果的样本按单个编号动态分发，最多同时运行十个。

## 服务器当前批次的快捷用法

可以只下载一个脚本，继续使用原来已安装的 **0.1.4**，无需在采集中重装环境或软件。在原项目的 PyCharm PowerShell 终端、`fdtd_gen` 环境中执行：

```powershell
Invoke-WebRequest 'https://raw.githubusercontent.com/CypherZzzyer05/Deta_Generator/main/src/deta_generator/tail.py' -OutFile .\accelerate_tail.py
$tailJob = '.\jobs\au100_metal8_1000_p10'
python .\accelerate_tail.py --job-dir $tailJob --action plan
```

把 `tailJob` 改成实际任务目录。`plan` 只读原清单，显示已成功数量、剩余编号和仍存活的原工作进程，不启动 FDTD。

确认目录和数量正确后，执行下面两条。**stop 会结束该任务的原控制器、已核对身份的工作进程及其子进程，未保存的当前仿真进度会丢失。** 成功样本不删除、不改写。停止逻辑核对进程创建时间、名称和控制器中的准确任务路径，不按程序名称批量结束其他 Python/FDTD 项目。

```powershell
python .\accelerate_tail.py --job-dir $tailJob --action stop
python .\accelerate_tail.py --job-dir $tailJob --action run --jobs 10
```

按照此前的 977 成功 / 3 运行 / 20 待算快照，新入口会保留并校验 977 个成功样本，将其余 23 个重新调度，启动时按最新保存状态重新统计。线程默认按可用 CPU 预算除以并发数分配，64 个可用逻辑 CPU 时每个样本六线程。许可与内存仍需支持并发，十路不保证相对于三路有固定加速比。

如果原控制器或工作进程仍然存活，`run` 会拒绝启动。不要再同时点击旧的 `parallel` 配置。新控制器持有原任务的控制锁，在原分片目录持有生成锁以阻止并发写入。

## 状态和最终数据

新运行窗口每约 30 秒显示总成功数、运行数、待算数、实际观测到的原生引擎数量和每个活跃样本的时间步进度。单样本日志位于 `tail_resume/logs/`，原生时间步日志位于 `tail_resume/sample_XXXXXX/projects/`。

另开终端可以读取最新状态快照：

```powershell
python .\accelerate_tail.py --job-dir $tailJob --action status
```

旧 `parallel` 的监控仍只统计旧分片，因此切换后应查看新窗口或 tail 状态。

最终数据路径：

```text
jobs/au100_metal8_1000_p10/tail_resume/merged/dataset.npz
```

原 `shard0` 等目录完整保留。新计算写到 `tail_resume/sample_XXXXXX/`，初次运行在 `tail_resume/merged` 先汇总并验证已有成功数据，结束后再次严格合并。完整成功数未达到原计划数量会明确报错。失败或中断后重复 `--action run` 会跳过已完成且校验通过的数据，只补剩余样本。

## 安装包与 PyCharm

也可安装 0.1.5 wheel，再运行 `python -m deta_generator.tail`，参数相同。PyCharm 的模块名为 `deta_generator.tail`，参数示例：

```text
--job-dir jobs/au100_metal8_1000_p10 --action run --jobs 10
```

使用单文件方式时，把 Python 运行配置改为脚本 `accelerate_tail.py`，参数保持上述内容。解释器仍为原 `fdtd_gen`，API 环境变量沿用已有配置，不需要 CUDA。

## 不改变物理实现

`config.py`、`lumerical.py`、`pipeline.py` 与 0.1.4 逐字节一致。几何、随机种子、样本编号、数据划分、材料、网格、时间上限及自动关断阈值均沿用原任务。每个子生成器通过已有 `--shard-count N --shard-index ID` 入口只处理一个原始样本编号。合并沿用原有配置、采样计划、实际材料拟合、求解器版本、网格和文件校验机制。

本地集成测试使用明确标记的测试专用求解器，验证四路/十路调度、失败续算、重复运行不重算、旧版包的单文件兼容，以及停止目标任务时保留无关 Python 进程。测试没有进行原生十路 FDTD 性能测量。
