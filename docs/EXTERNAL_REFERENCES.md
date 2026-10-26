# EcoSim 外部参考实现与文献

> **来源**：2026-10-24 的会话 `843999fa` 中，用户要求“找一找开源项目和论文，看看能不能找到修复 BUG 的灵感”。当时启动了 9 路并行调研（12 个 agent），产出 64 个去重项目、137 篇论文；结果只出现在对话里，没有落盘。本文于 2026-10-26 从会话日志与调研 workflow 输出（`tasks/wbtle6mv5.output`，539 KB）恢复并整理。
>
> **注意**：当时的诊断对象是 **V0.3.2 Python 引擎**；其中库存/生产计划、投资/替换、进入退出、部分会计问题已在 V0.4–V0.6/A2 中处理。本文保留的是**外部参考**，不是当前 backlog。许可证与链接是 2026-10-24 的调研快照；复用代码前必须重新核对 LICENSE。

## 0. 结论先行

1. **负反馈不是自动的**。Goodwin 的 reserve-army 回路确实会把工资和就业拉回来；但 Keen 模型证明，债务/利息正反馈足够强时经济仍会 terminal collapse。“经济不会一边倒”需要制度闭合，不是模型天然保证。
2. **SFC 会计闭合是地基**。Godley–Lavoie、Caiani/JMAB、Eurace、Minsky 的共同点：每个 flow 对应 stock，部门净 lending 之和为 0，银行贷款同时创造存款。EcoSim 的银行/破产/折旧问题首先要用这套账本约束修。
3. **最接近本项目的最小实现**：JAMEL（月度两部门、贷款创造存款、库存/定价/银行齐全）、BAM engine（Python/MIT、信用市场/破产/验证流水线）、JMAB + Caiani benchmark（完整 AB-SFC 资产负债表）、Mark-0（C++/MIT、企业进出/破产/银行损失吸收）。
4. **库存/生产计划**：Beer Game/IOBPCS 与 Holt–Modigliani 的生产平滑规则可以直接借用；关键是让“计划”同时约束生产、采购和劳动，并计入在途/欠交，而不是只影响采购。
5. **许可证**：JAMEL/Minsky/ABCredit/AgentTorch/acclimate 是 GPL/AGPL，只适合读；Eurace 是自定义 EULA；JMAB、MacroABM 没有正式 LICENSE；MIT/Apache/BSD 的 BAM、Mark-0、sfctools、PySD、BPTK-Py、Mesa 可以安全借鉴代码。

## 1. 核心项目矩阵

| 类别 | 项目 | 语言 / 许可 | 最值得借鉴的机制 | 链接 |
|---|---|---|---|---|
| 宏观 ABM | **JAMEL**（Seppecher） | Java / GPL-3.0 | 月度两部门；生产目标 = 12 期平均销售 +（正常库存−库存）/调整期；markup×单位成本；贷款同时创造存款；债务超过资产 36 个月核销 | <https://github.com/pseppecher/jamel> |
| 宏观 ABM | **BAM engine** | Python / MIT | 劳动/信贷/商品三市场；利率 = 基准×(1+φ×杠杆/净值)，杠杆上限 10，单笔≤2×净值；净值<0 或产出=0 破产；自带 Morris/grid/validation 流水线 | <https://github.com/kganitis/bam-engine> |
| 宏观 ABM | **JMAB + Caiani et al. benchmark** | Java / 无正式 LICENSE（README 为 MIT 风格文字） | 完整 AB-SFC 资产负债表；季度基准；预期销售+库存的生产计划；产能利用率+利润率投资；逐笔信贷配给；银行资本充足率；贷款创造存款 | <https://github.com/S120/jmab> · <https://github.com/S120/benchmark> |
| 宏观 ABM | **Eurace@Unibi** | C/FLAME / 自定义 EULA（非 OSI） | 内生信用货币；银行资本约束；企业特定利率/违约概率；破产/债务重组；二手资本品市场（Unibi 分支）；政府/央行/QE | <https://github.com/ETACE/eurace_unibi> |
| 宏观 ABM | **K+S**（Dosi/Fagiolo/Roventini） | LSD 平台 / 无公开代码 | 需求预期+库存；替换投资（payback/obsolescence）；markup；工资指数化；信用配给；进入/退出；R&D；政府税收/失业补贴 | <https://doi.org/10.1016/j.jedc.2010.06.018> |
| 宏观 ABM | **Mark-0 / markovid** | C++（含 JAX 版）/ MIT | 企业产出/价格/工资自适应；需求价格弹性分配；债务/工资脆弱性破产；银行损失吸收；替换企业进入；Taylor 利率规则；单文件易读 | <https://gitlab.com/sharma.dhruv/markovid> |
| 宏观 ABM | **ABCredit.jl**（Banca d'Italia） | Julia / AGPL-3.0 | 资本—信贷—劳动—库存—破产的紧凑状态机；银行资产负债表与信用配给；适合看“少量状态变量”的可校准实现 | <https://github.com/bancaditalia/ABCredit.jl> |
| 宏观 ABM | **CATS2** | MATLAB / CC0-1.0 | CATS 家族的财政乘数、预期与学习；CC0 可自由复用 | <https://github.com/SReissl/CATS2> |
| 宏观 ABM | **LAGOM**（Mandel et al.） | 论文 / 未找到代码 | 多部门 Leontief/IO；库存；固定资本折旧；保留工资/跳槽；信贷；失业保险；Taylor 规则；进入/退出 | <https://globalclimateforum.org/fileadmin/ecf-documents/publications/ecf-working-papers/mandel-fuerst-lass-meissner-jaeger__ecf-working-paper_2009-01.pdf> |
| SFC/SD | **Minsky**（Steve Keen） | C++/TS / GPL-3.0 | Godley 表、复式记账、存量-流量一致、ODE 求解；可直接跑 Keen/Goodwin 类模型 | <https://github.com/highperformancecoder/minsky> |
| SFC/SD | **sfctools**（DLR） | Python / MIT | Agent 资产负债表 + FlowMatrix；每期行列平衡检查；YAML 参数；批次仿真 | <https://gitlab.com/dlr-ve/esy/sfctools/framework> |
| SFC/SD | **sfcr** | R / MIT | Godley–Lavoie SFC 模型；会计恒等式、基线/冲击、Gauss-Seidel/Broyden | <https://github.com/joaomacalos/sfcr> |
| SFC/SD | **PySD** | Python / MIT | Vensim/XMILE 系统动力学模型转 Python；情景/参数扫描；适合先做 Keen/Goodwin 原型 | <https://github.com/SDXorg/pysd> |
| SFC/SD | **BPTK-Py** | Python/Rust / MIT | SD+ABM 混合；XMILE 编译器；Beer Game 库存/欠交/在途模型库；可在 Pyodide 跑 | <https://github.com/transentis/bptk_py> |
| ABM 框架 | **Mesa / Agents.jl** | Python Apache-2.0 / Julia MIT | Agent 调度、空间网格（六边形地图）、实验管理、Monte Carlo；不提供宏观会计结构 | <https://github.com/mesa/mesa> · <https://github.com/JuliaDynamics/Agents.jl> |
| 库存/供应链 | **deepbullwhip** | Python / MIT | OUT/POUT/Smoothing OUT、AR(1)/Beer Game 需求、BWR/NSAmp/FillRate 指标；可复现 Chen 下界 | <https://github.com/ai-vnv/deepbullwhip> |
| 库存/供应链 | **SupplyNetPy** | Python/SimPy / MIT | (s,S)、(R,Q)、periodic、安全库存、易腐库存、随机提前期、节点中断 | <https://supplychainsimulation.github.io/SupplyNetPy/about/> |
| 库存/供应链 | **supplychainpy** | Python / BSD-3-Clause | EOQ、ROP、安全库存、ABC-XYZ、Monte Carlo、服务水平优化 | <https://github.com/KevinFasusi/supplychainpy> |
| 库存/供应链 | **NetLogo Root Beer Game** | NetLogo / 许可证未核实 | Beer Game 的订单/运输延迟/库存/欠交成本；教学与基线 | <http://ccl.northwestern.edu/netlogo/models/RootBeerGameHubNet> |
| IO 网络 | **acclimate** | C++11 / AGPL-3.0 | 全球供应链网络、库存、损失传播、价格变体；最接近“IO+库存”的完整实现 | <https://github.com/acclimate/acclimate> |
| IO 工具 | **pymrio / MARIO** | Python / GPL-3.0 | MRIO 解析、Leontief 逆、IOT/SUT 转换、冲击情景；可用于校准 9 行业 A 矩阵 | <https://github.com/konstantinstadler/pymrio> · <https://github.com/it-is-me-mario/MARIO> |
| LLM/RL | **AI Economist / Concordia / AgentTorch** | Python / BSD-3、Apache-2.0、AGPL-3.0 | 政策沙盒、LLM 生成式 agent、可微分/GPU 仿真；适合未来 LLM 经理层，不提供定量宏观方程 | <https://github.com/salesforce/ai-economist> · <https://github.com/google-deepmind/concordia> · <https://github.com/agenttorch/agenttorch> |
| 验证 | **LSDsensitivity / LSDirf / statsmodels** | R GPL-3 / R GPL-3 / Python BSD-3 | Morris/Sobol 全局敏感性、状态依赖 IRF、ADF/KPSS/ARIMA/VAR；用于参数筛选与典型事实回归 | <https://cran.r-project.org/web/packages/LSDsensitivity/index.html> · <https://cran.r-project.org/web/packages/LSDirf/index.html> · <https://github.com/statsmodels/statsmodels> |

## 2. 许可证速查

| 类别 | 项目 | 使用建议 |
|---|---|---|
| **MIT / Apache / BSD / CC0** | BAM engine、Mark-0、sfctools、sfcr、PySD、BPTK-Py、Mesa、Agents.jl、deepbullwhip、SupplyNetPy、supplychainpy、CATS2、AI Economist（已归档）、Concordia、statsmodels | 可借鉴代码/结构；仍建议保留出处与许可证声明 |
| **GPL / AGPL** | JAMEL（GPL-3）、Minsky（GPL-3）、ABCredit.jl（AGPL-3）、AgentTorch（AGPL-3）、acclimate（AGPL-3）、pymrio/MARIO（GPL-3） | **只读思想，不复制代码**；AGPL 对网络分发传染性强 |
| **自定义 EULA** | Eurace@Unibi | 只读参考；分发/修改需书面许可 |
| **无正式许可证** | JMAB、S120/benchmark、MacroABM、EconAgent、NetLogo Root Beer Game | 法律状态不明确；只读，不要复制 |
| **无公开代码** | K+S、LAGOM、CATS（原始）、MARK I/II | 只读论文/公式 |

> 调研时 EcoSim 仓库自身还没有 LICENSE。发行单文件 HTML 前需要单独决定许可证；这不影响“先借思想”。

## 3. 机制 → EcoSim 映射

### 3.1 九路调研的主题

| # | 主题 | 核心结论（当时） |
|---|---|---|
| 1 | 宏观 ABM 平台/负反馈 | 不是负反馈太少，而是多条回路被实现层短路；库存、投资、信用、工资、价格、进入退出都要闭合 |
| 2 | 系统动力学/SFC/Goodwin–Keen/Minsky | Goodwin reserve-army + SFC stock-flow norms + 制度稳定器，三层叠加才不一边倒 |
| 3 | 库存/生产计划/供应链 | 计划必须同时约束产出/采购/劳动；计入在途、欠交、安全库存；避免 stop-go |
| 4 | 劳动/工资/价格 | 失业不压工资、工资不恢复就业是核心断点；搜索-匹配 + 工资曲线/议价 |
| 5 | 银行/信用/破产/金融摩擦 | 贷款创造存款；银行受资本/杠杆/风险约束；破产要核销债务、回收资产 |
| 6 | 总需求/投资/预期/政府稳定器 | 投资加速器 + 替换投资 + 政府/失业救济；无政府封闭经济缺自主需求地板 |
| 7 | 开源项目核查 | 最直接可读：Mark-0、JAMEL、CATS/ABCredit、JMAB、K+S（无代码）；通用工具箱：Mesa/PySD/BPTK/Minsky/sfctools |
| 8 | 验证/典型事实 | 单 seed 不能当蒙特卡洛；需要 IRF/敏感性/典型事实带；BAM 的验证流水线可参考 |
| 9 | 投入产出网络/瓶颈/替代 | 固定系数 Leontief + 零库存时，单点断供会让全链锁死；需要瓶颈乘数、替代/配给、库存缓冲 |

### 3.2 八条被短路的回路（V0.3.2 诊断，历史）

| 回路 | 应有机制 | 当时代码 | 参考 |
|---|---|---|---|
| 库存—生产 | 库存高→减产/少采购；低→增产/补货 | `production_plan()` 只影响采购，`produce()` 不读计划 | JAMEL、Beer Game、Holt |
| 销售—预期 | 缺货记 backlog，补货恢复 | 销售量被供给截断，企业把缺货当没需求 | K+S、JMAB、Sterman |
| 投资—产能 | 需求/利用率→投资→产能→价格/利润→投资；折旧→替换 | 只看单期 ROI；设备不报废；无替换投资 | K+S、Eurace、JMAB |
| 信用—投资 | 信贷→工资/投入/投资→收入→还款→银行权益→信贷 | 银行固定现金；贷款不创造存款；破产不核销 | JAMEL、BAM、Eurace、McLeay |
| 工资—失业 | 失业↑→工资↓→成本↓→雇佣↑ | 工资钉在生存下限；工资报价不看失业 | Mortensen–Pissarides、Shimer |
| 价格—需求 | 库存↑→价格↓→需求↑；成本↑→价格↑ | 硬成本上下轨；固定篮子降价不增量 | Caiani、Mark-0、Richters |
| 进入—退出 | 亏损→退出→供给↓→利润↑→进入 | 手工 t0 不可投资；破产不清债务/不回收 | K+S、Mark-0、Eurace |
| 需求—收入 | 衰退→税收↓/救济↑→消费地板 | 无政府/救济/出口 | K+S、Eurace、McKay–Reis |

> 这些是 V0.3.2 的诊断。V0.4–V0.6/A2 已处理其中一部分（投资/替换、进入退出、部分会计、需求/工资）；**C 仍直接对应“信用—投资”和“需求—收入”两条**。

### 3.3 当时建议的最小套件（Top 3）

1. **L4 信贷—银行资本—破产清算 + 会计修正**：贷款创造存款；银行 equity/loans/NPL；破产核销 debt/loans、折价回收库存/设备/土地；折旧只算设备。
2. **L1 生产—库存—订单闭环**：计划约束产出；在途/欠交/安全库存；`sales=0` 时不再按 50% 产能生产。
3. **L3 投资—替换—产能 + 手工 bootstrap**：设备 age/life、替换投资、按缺口/ROI 选型；取消农业 priority 绕过项目上限；给砖/钢/机械/施工提供无资本品的手工启动。

## 4. 核心论文（精选 42 篇）

### 4.1 宏观 ABM / SFC

| 年份 | 论文 | 为什么读 | 链接 |
|---|---|---|---|
| 2016 | Caiani et al., *Agent based-stock flow consistent macroeconomics: Towards a benchmark model* | AB-SFC 基准；完整资产负债表/信贷/破产 | <https://doi.org/10.1016/j.jedc.2016.06.001> |
| 2010 | Dosi, Fagiolo, Roventini, *Schumpeter meeting Keynes* | K+S 的基准故事：需求、创新、信贷、政策 | <https://doi.org/10.1016/j.jedc.2010.06.018> |
| 2013 | Dosi et al., *Income distribution, credit and fiscal policies in an agent-based Keynesian model* | 分配/信贷/财政政策组合 | <https://doi.org/10.1016/j.jedc.2012.11.008> |
| 2005 | Delli Gatti et al., *A new approach to business fluctuations* | CATS：异质企业、金融脆弱性、破产 | <https://doi.org/10.1016/j.jebo.2003.10.012> |
| 2015 | Assenza, Delli Gatti, Grazzini, *Emergent dynamics of a macroeconomic agent based model with capital and credit* | ABCredit：资本+信贷的紧凑 ABM | <https://doi.org/10.1016/j.jedc.2014.07.001> |
| 2009 | Mandel et al., *Lagom generiC* | 多部门 IO + 库存 + 信贷 + 政府 | [PDF](https://globalclimateforum.org/fileadmin/ecf-documents/publications/ecf-working-papers/mandel-fuerst-lass-meissner-jaeger__ecf-working-paper_2009-01.pdf) |
| 2014 | Dawid et al., *Agent-Based Macroeconomic Modeling and Policy Analysis: The Eurace@Unibi Model* | Eurace 的完整机制/政策分析 | <https://doi.org/10.4119/unibi/2915476> |
| 2010 | Cincotti, Raberto, Teglio, *Credit Money and Macroeconomic Instability in Eurace* | 内生信用货币与不稳定 | <https://doi.org/10.5018/economics-ejournal.ja.2010-26> |
| 2012 | Seppecher, *Jamel, a Java Agent-based MacroEconomic Laboratory* | JAMEL 的模型说明 | <https://shs.hal.science/halshs-00697225> |
| 2021 | Sharma et al., *V-, U-, L- or W-shaped economic recovery after Covid-19* | Mark-0 的应用与机制 | <https://doi.org/10.1371/journal.pone.0247823> |
| 2017 | Nikiforos, Zezza, *Stock-flow Consistent Macroeconomic Models: A Survey* | SFC 综述 | <https://doi.org/10.1111/joes.12221> |
| 2012 | Godley, Lavoie, *Monetary Economics* | SFC 会计的教科书 | <https://doi.org/10.1007/978-1-137-08599-3> |
| 1992 | Minsky, *The Financial Instability Hypothesis* | 金融不稳定假说 | [PDF](https://www.levyinstitute.org/pubs/wp74.pdf) |
| 1995 | Keen, *Finance and Economic Breakdown* | Keen 模型：债务正反馈与崩溃 | <https://doi.org/10.1080/01603477.1995.11490053> |
| 2012 | Grasselli, Costa Lima, *An analysis of the Keen model* | Keen 模型的数学分析 | <https://doi.org/10.1007/s11579-012-0071-8> |

### 4.2 库存 / 供应链

| 年份 | 论文 | 为什么读 | 链接 |
|---|---|---|---|
| 1989 | Sterman, *Modeling Managerial Behavior* | Beer Game：局部信息/延迟导致牛鞭 | <https://doi.org/10.1287/mnsc.35.3.321> |
| 1997 | Lee, Padmanabhan, Whang, *Information Distortion in a Supply Chain* | 牛鞭效应的经典分类 | <https://doi.org/10.1287/mnsc.43.4.546> |
| 2000 | Chen et al., *Quantifying the Bullwhip Effect* | 预测/提前期/信息对牛鞭的定量 | <https://doi.org/10.1287/mnsc.46.3.436.12069> |
| 1960 | Holt et al., *Planning Production, Inventories, and Work Force* | 生产平滑/库存/劳动力的线性决策规则 | [PDF](https://archive.org/download/PlanningProductionInventoriesAndWorkForce/PlanningProductionInventoriesAndWorkForce.pdf) |
| 1941 | Metzler, *The Nature and Stability of Inventory Cycles* | 库存周期的稳定性 | <https://doi.org/10.2307/1928739> |
| 1999 | Ramey, West, *Inventories* | 库存宏观事实综述 | <https://doi.org/10.1016/s1574-0048(99)10021-1> |

### 4.3 劳动 / 工资

| 年份 | 论文 | 为什么读 | 链接 |
|---|---|---|---|
| 1994 | Mortensen, Pissarides, *Job Creation and Job Destruction* | 匹配函数 + 空缺 + Nash 工资 | <https://doi.org/10.2307/2297896> |
| 2001 | Petrongolo, Pissarides, *Looking into the Black Box* | 匹配函数综述（弹性范围） | <https://doi.org/10.1257/jel.39.2.390> |
| 2005 | Shimer, *The Cyclical Behavior of Equilibrium Unemployment and Vacancies* | 失业/空缺的周期校准 | <https://doi.org/10.1257/0002828053828572> |
| 1994 | Blanchflower, Oswald, *Estimating a Wage Curve for Britain* | 工资曲线（失业—工资） | <https://doi.org/10.2307/2235062> |
| 1958 | Phillips, *The Relation Between Unemployment and the Rate of Change of Money Wage Rates* | 原始 Phillips 曲线 | <https://doi.org/10.1111/j.1468-0335.1958.tb00003.x> |

### 4.4 银行 / 信用 / 破产

| 年份 | 论文 | 为什么读 | 链接 |
|---|---|---|---|
| 2014 | McLeay, Radia, Thomas, *Money creation in the modern economy* | 银行贷款创造存款（BoE） | <https://www.bankofengland.co.uk/quarterly-bulletin/2014/q1/money-creation-in-the-modern-economy> |
| 2015 | Jakab, Kumhof, *Banks are not intermediaries of loanable funds* | 内生货币的账本含义 | <https://www.bankofengland.co.uk/working-paper/2015/banks-are-not-intermediaries-of-loanable-funds-and-why-this-matters> |
| 1981 | Stiglitz, Weiss, *Credit Rationing in Markets with Imperfect Information* | 信用配给的微观基础 | <https://www.jstor.org/stable/1802787> |
| 1997 | Kiyotaki, Moore, *Credit Cycles* | 抵押约束与资产价格 | <https://doi.org/10.1086/262072> |
| 1999 | Bernanke, Gertler, Gilchrist, *The financial accelerator* | 金融加速器 | <https://www.nber.org/papers/w6455> |
| 2021 | Tedeschi et al., *The macroeconomic effects of default and debt restructuring* | 违约/债务重组的 ABM 对照 | <https://www.sciencedirect.com/science/article/abs/pii/S1059056021001672> |

### 4.5 投入产出 / 网络

| 年份 | 论文 | 为什么读 | 链接 |
|---|---|---|---|
| 1936 | Leontief, *Quantitative Input and Output Relations* | IO 分析开山 | <https://doi.org/10.2307/1927837> |
| 2012 | Acemoglu et al., *The Network Origins of Aggregate Fluctuations* | 网络结构/冲击放大 | <https://doi.org/10.3982/ECTA9623> |
| 2019 | Baqaee, Farhi, *The Macroeconomic Impact of Microeconomic Shocks* | 非线性生产网络/超越 Hulten | <https://doi.org/10.3982/ECTA15202> |
| 2019 | Carvalho, Tahbaz-Salehi, *Production Networks: A Primer* | 生产网络入门 | <https://doi.org/10.1146/annurev-economics-080218-030212> |
| 2008 | Hallegatte, *An Adaptive Regional Input-Output Model* | 库存/异质性下的灾害损失传播 | <https://doi.org/10.1111/j.1539-6924.2008.01046.x> |

### 4.6 验证 / 敏感性

| 年份 | 论文 | 为什么读 | 链接 |
|---|---|---|---|
| 2007 | Windrum, Fagiolo, Moneta, *Empirical Validation of Agent-Based Models* | ABM 验证方法 | <https://www.jasss.org/10/2/8.html> |
| 2005 | Grimm et al., *Pattern-Oriented Modeling* | 用模式/典型事实约束模型 | <https://doi.org/10.1126/science.1116681> |
| 1996 | Axtell et al., *Aligning simulation models* | docking/模型对齐 | <https://doi.org/10.1007/BF01299065> |
| 2025 | Amendola, Pereira, *State-dependent impulse responses in agent-based models* | 状态依赖 IRF 方法 | <https://doi.org/10.1016/j.jebo.2024.106811> |
| 2016 | Borgonovo, Plischke, *Sensitivity analysis: A review* | 全局敏感性综述 | <https://doi.org/10.1016/j.ejor.2015.06.032> |

## 5. 对当前 V0.6 / A2 / C 的意义

- **C（银行/信贷/MMT）直接对应**：JAMEL 的“贷款创造存款”、BAM 的信用市场/杠杆/破产规则、Eurace 的银行资本约束与企业特定利率、Mark-0 的银行损失吸收/企业替换、McLeay/Jakab–Kumhof 的账本口径。建议先读 BAM engine 的文档和 JAMEL 的 `BasicBank`/`BasicFirm`，再决定 EcoSim 的 C 最小实现。
- **D（土地开垦/estate）**：K+S/Eurace 的进入退出与资本品 vintage、Mark-0 的企业替换、CATS 的净值/破产；土地作为抵押资产可参考 Kiyotaki–Moore/Mark I/II。
- **价格/工资**：Caiani/JAMEL 的 markup + 库存调整、Richters 的 Sraffian markup、Mark-0 的需求弹性分配、Mortensen–Pissarides/Shimer 的匹配与工资。
- **库存/生产**：Beer Game/IOBPCS、Holt 的生产平滑、BPTK-Py 的模型库；当前 JS 引擎已有 A2 的替换/废钢，但“计划约束产出/在途/欠交”仍值得在 C/D 之后复核。
- **验证**：BAM engine 的 Morris/grid/validation 流水线、LSDsensitivity/LSDirf、statsmodels；建议把“多 seed + IRF + 典型事实带”作为 C 的验收，而不是单 seed 240 月。

## 6. 原始资料

- 会话：`843999fa-b271-4ac1-b419-d7c313e5daf8`（2026-10-24）
- 调研 workflow 原始输出（539 KB，含 9 个 research 主题、64 个项目、137 篇论文、12 条映射、7 条回路设计）已归档：
  `docs/research/ecosim_external_research_2026-10-24.json`
  （原临时路径：`...\tasks\wbtle6mv5.output`）
- 本文是持久化摘要；需要完整项目/论文清单时直接查归档 JSON。

> 引用说明：本文只恢复当时调研的结论与链接，未重新逐条核验 2026-10-24 之后的项目状态/许可证。复制任何代码前，请以仓库当前 LICENSE 为准；GPL/AGPL/EULA/无许可证项目只读思想。
