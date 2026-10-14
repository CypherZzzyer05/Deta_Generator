# 来源与方法

数据生成核心由用户独立Metaformer As₂Se₃研究项目提取，来源提交 `d81e16cdc6c3dca81948b1b86447290fa90b0c11`；此包单独开发于 `codex/portable-fdtd-generator` Git工作树。原 `LumOpt_test` 项目未改动。

继承几何、旋转、有限金属基板、功率方向、光谱质量和实际网格检查；新增可安装包、Windows CLI、跨机器物理指纹、拟合/版本核对、内存预检、独立分片及校验合并。模型训练、历史权重、大型FSP、凭据和求解许可均未打包。

原生求解接口在源项目的本机Lumerical2024 R1中已有真实仿真证据。本包新接口的验证记录在 `docs/validation.md`；不能将软件测试替身等同于重新完成的原生电磁仿真。

方法依据：

- [Ansys Python API](https://optics.ansys.com/hc/en-us/articles/360041579954-Script-Commands-as-Methods-Python-API)
- [实际材料拟合](https://optics.ansys.com/hc/en-us/articles/360034409694-getfdtdindex-Script-command)
- [原生资源检查](https://optics.ansys.com/hc/en-us/articles/4403937981715-runsystemcheck-Script-command)：本机2024 R1使用无参数CPU调用。
- [材料拟合参数](https://optics.ansys.com/hc/en-us/articles/360034915053-Tips-for-improving-the-quality-of-optical-material-fits)
- [As₂Se₃数据](https://refractiveindex.info/?shelf=main&book=As2Se3&page=Joseph-700nm)

本包以CPU资源配置为主，未实现分布式单次FDTD或GPU求解器。分片是把不同几何任务独立分配，而不是拆分一个结构的电磁计算域。

2026-10-14，按用户明确提供的手工仿真实战经验，版本0.1.2将默认网格策略改为仅金属层覆盖网格。原始全域4/8 nm研究结果保留为历史记录；新的默认模式单独标记、验证并生成数据，不沿用历史全域网格的精度结论。
