# Deta Generator：七参数FDTD数据生成包

独立于模型训练项目，用于在另一台已安装 **Lumerical FDTD的Windows计算机**上生成As₂Se₃四聚体真实光谱数据。支持Au、Ag及有限基板不镀金对照。无需安装PyTorch、CUDA或Metaformer训练代码；求解采用Lumerical原生CPU引擎，增加线程不会保证等比例加速。

七参数顺序为 `[P,L,H,dX,dY,theta_odd_deg,theta_even_deg]`，前五项nm，后两项deg。代码键为 `p,l,h,alpha_x,alpha_y,theta_odd_deg,theta_even_deg`。I/III共享奇数角，II/IV共享偶数角，各柱绕自身中心旋转，角度独立且以90°为周期。dX/dY是未旋转时的名义边缘间隙；每个采样结构检查旋转后的碰撞与周期边界。

## 在计算机上运行

使用Lumerical版本兼容的Python环境；本机实际连接验证使用Python3.10、Lumerical2024 R1。必须有可用FDTD求解许可，包不包含Lumerical软件、许可或凭据。

```powershell
git clone https://github.com/CypherZzzyer05/Deta_Generator.git
cd Deta_Generator
python -m pip install .

# 先创建任务。12只是流程验证样本量，正式训练需按研究目标扩大。
python -m deta_generator init --job-dir jobs/au4 --preset au-4 --samples 12 --threads 16
# 指向新计算机的安装路径；以下路径是示例，请改成实际版本与目录。
$env:LUMERICAL_LUMAPI_PATH = 'C:\Program Files\Lumerical\v241\api\python\lumapi.py'
python -m deta_generator doctor --config jobs/au4/job.json
python -m deta_generator preflight --config jobs/au4/job.json
python -m deta_generator plan --config jobs/au4/job.json
# 先算一个样本，核对资源、耗时、材料和光谱，然后去掉limit采集完整计划。
python -m deta_generator generate --config jobs/au4/job.json --limit 1
python -m deta_generator generate --config jobs/au4/job.json
python -m deta_generator status --config jobs/au4/job.json
```

只需安装包时，也可下载仓库 `artifacts/deta_generator-0.1.0-py3-none-any.whl`，运行 `python -m pip install <wheel文件路径>`。wheel内已带默认配置和As₂Se₃材料文件。安装依赖只有NumPy与psutil；使用前仍需本机原生Lumerical API和求解许可。

也可使用安装后的 `deta-generator` 命令，或Windows脚本：

```powershell
.\scripts\run-windows.ps1 -Command generate -Config jobs/au4/job.json -Threads 16 -Limit 1
```

`doctor`检查API连接、版本和实际材料拟合；`preflight`另外构造首个计划结构，读取实际网格和原生内存估计，**二者均不运行电磁求解**。它们不证明求解许可、光谱收敛或设备精度。生成时每个结构都重新做网格与内存检查；内存不足则拒绝启动该样本。原生内存建议是近似值，尤其共形网格仍需实际试算。

## 网格、镀层和计算成本

预设有 `au-4`、`au-8`、`ag-4`、`ag-8`、`bare-4`、`bare-8`。4 nm预设为默认；全域每个实际x/y/z网格单元必须严格小于10 nm，金属区域z网格2.5 nm。8 nm用于探索，需要针对目标结构与更细网格复核；当前研究候选第一反射谷8→4 nm变化约4.10个百分点，超过既定3个百分点标准，不能直接认定8 nm足够精确。

结构为As₂Se₃ / 350 nm SiO₂ / 150 nm金属 / 空气，法向x偏振，700–1700 nm。`bare`使用 `remove_metal=true`，仅移除金属物体，保留有限基板、源、监测器、下方空气域及金属区网格，并要求移除前后网格一致。**不能用 `metal_material=null` 替代这个受控不镀金结构。** 当前有限薄基板不代表毫米厚实物基片。

每个训练样本输出1000个均匀波长点的R/T/A。1000是每条光谱的点数，`--samples`才是不同几何结构数量。为控制数据集成本，这个包默认只记录远场光谱；当前本机金层/网格研究的两平面E/H分析与报告仍在独立研究项目中进行。

## 迁移、续算和分片

按相同命令重跑即可跳过校验成功的样本，补算缺失、失败或损坏的数据。Ctrl+C保留已经完成的样本；中断的当前样本下次重新算。更换机器时复制整个任务目录，并通过 `--lumapi`、`--threads`、`--output`指定新机器路径和资源。修改几何范围、采样数、种子、网格、材料内容或物理设置时须使用新任务目录。

线程数、进程数、API路径和输出位置不进入物理指纹；原始材料内容及生成代码进入指纹。续算和合并要求同一求解器版本，实际材料拟合按1e−7容差核对。固定计划中的样本ID和训练/验证/测试归属不会按完成顺序变化。每个样本完成后立即保存NPZ和manifest；默认每25个尝试及正常/可捕获中断退出时刷新汇总数据集，可用 `--pack-every`调整，避免大型批次每次都重读全部数据。

强机器可先提高单个FDTD任务的线程数；要多任务并行时，按下面方式给不同任务独立输出目录。每个任务占用独立许可和内存，线程总数与峰值内存由使用者按机器资源配置。不要让多个任务写入同一输出目录。

```powershell
# 两条命令在不同终端/机器执行，使用同一job.json与同一版本的包。
python -m deta_generator generate --config jobs/au4/job.json --shard-count 2 --shard-index 0 --output jobs/au4/shard0 --threads 16
python -m deta_generator generate --config jobs/au4/job.json --shard-count 2 --shard-index 1 --output jobs/au4/shard1 --threads 16
# 两个任务结束后，把分片目录复制到同一机器并合并。
python -m deta_generator merge --config jobs/au4/job.json --shards jobs/au4/shard0 jobs/au4/shard1 --output jobs/au4/merged
```

合并验证配置、采样计划、划分、校验值、实际网格、求解状态、版本及拟合；冲突的重复ID拒绝合并。合并不会删除分片。一个任务的 `plan`已固定采样几何；多机器首次建立计划时需使用相同NumPy版本以确保采样序列一致，合并时仍逐项核对实际几何。

## 输出与模型接口

- `manifest.json`：固定七参数计划、划分、物理指纹、状态、版本、拟合及运行记录。
- `samples/sample_XXXXXX.npz`与CSV：每个成功样本的原始R/T/A、混合单位标签、实际网格坐标及求解记录。
- `projects/`：本机原生FSP、实际网格和资源检查，默认保存；不提交Git。
- `dataset.npz`：`spectra[N,1000]`、`geometry_values[N,7]`、`geometry_01[N,7]`、`parameter_names`、`parameter_units`、`lower_values`、`upper_values`、固定划分索引，以及T/A等。
- `summary.json`、`generation.log`、`errors.jsonl`：完成数量、日志与失败原因。

光谱保留入射功率归一化R，不做逐条min-max缩放、不裁剪不合理结果。未达到自动关断时最多四次延长时间；不合格样本排除在训练数据之外。可用 `pack`再次校验和打包已有成功数据，全程不调用求解器。

## 材料与验证范围

As₂Se₃采用Joseph实测700 nm薄膜n/k，CSV原始SHA256为 `9e6ee6d3b584f33226d7201e2b2e12490726cb3b8256726754e5aca9cae64ce9`；材料说明与CC0来源随包提供。实测至1688 nm，最后12 nm是显式端点延拓。Au/Ag使用本机Lumerical Palik库，未随包分发其数据。

**当前Au默认FDTD拟合存在明显损耗误差。** 本包保持已有研究配置以便复现，输出记录材料精度未验证及实际拟合误差，质量标记沿用 `pipeline_validation`，现有Metaformer训练入口需要显式允许流程验证数据才能读取。它不会悄悄替换材料或将生成数据宣称为实验预测。大规模采集前请查看 `doctor.json` 的材料误差；本机研究正在独立核对和处理这个问题。网格检查、自动关断与材料准确性是不同验证项。

软件验证使用测试替身检查续算、迁移、分片及完整性，测试数据不作为研究数据。真实研究求解来自Lumerical；目标机器上的许可、运行速度和材料拟合必须在该机器试算确认。继承来源与方法文档见 [SOURCE.md](SOURCE.md)。
