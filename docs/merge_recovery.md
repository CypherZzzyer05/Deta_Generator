# 最终合并遇到 WinError 5 的恢复方法

报错位于 `merged/manifest.json.tmp` 替换 `merged/manifest.json`，说明失败发生在汇总清单保存阶段。Windows 文件短暂占用、目标只读属性或写权限均可能引发拒绝访问，单凭错误不能断定是哪一种。旧版采集子进程的 JSON 写入重试没有覆盖最终合并入口。

独立脚本 `scripts/recover-merge.py` 只读取并合并已经保存的分片，不连接或启动 Lumerical，不重跑电磁仿真，也不停止任何进程。可直接配合服务器现有的 0.1.4/0.1.5 包运行，无需重装。

在原项目的 PyCharm PowerShell 终端中，保持原 `fdtd_gen` 环境，关闭目标 JSON 的文件预览或持续读取窗口，然后执行：

```powershell
Invoke-WebRequest 'https://raw.githubusercontent.com/CypherZzzyer05/Deta_Generator/main/scripts/recover-merge.py' -OutFile .\recover-merge.py
python .\recover-merge.py --job-dir .\jobs\au100_metal8_1000_p10
```

脚本从 `parallel_plan.json` 读取原分片数量，要求每个分片清单存在，先检查已保存成功样本数量，再调用原有严格合并实现核对配置、几何、划分、实际材料拟合、求解器版本、网格和文件校验值。未保存成功的编号会明确列出，不会自动补算或忽略。

该进程内对 pipeline 和 merge 各自引用的 JSON 写入函数添加有界重试，同时覆盖最终 NPZ 打包写入。Windows 5/32/33 错误每 0.1 秒重试一次，最多等待约 20 秒；其他错误立即报告，持续权限错误也会停止。所有包装在退出时还原，不修改安装包文件或物理实现指纹。

默认结果写到新目录：

```text
jobs/au100_metal8_1000_p10/merged_recovered/dataset.npz
```

原 `shard0` 至 `shard39` 和失败的 `merged` 目录均保留。新目录只由这次恢复使用。再次运行同一命令可以恢复中断的合并。不要同时启动两个恢复进程，也不要在原分片仍有求解进程时合并；原有目录锁会拒绝并发写入。

完成后应看到 `success=1000`、`planned=1000`、`spectra_shape=[1000,1000]`、`geometry_shape=[1000,7]` 和 `solver_run_performed=false`。若持续报拒绝访问，需要排查目标文件占用、只读属性或目录写权限，不要删除原分片来解决。

本地六项测试覆盖真实 Windows 目标读句柄导致的替换失败及恢复、持续权限错误的有界退出、原分片字节不变、重复合并、拒绝缺失/损坏/活动分片，以及使用未修改的 0.1.4 包执行单文件恢复。测试光谱只作软件测试，未运行真实 FDTD。
