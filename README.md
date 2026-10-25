# 资本主义经济模拟 / Capitalism Sandbox

一个封闭资本主义经济的月度步进、确定性多智能体沙盒：规则驱动的工人、追求利润的资本家、
现货市场、劳动市场、土地市场，以及投资与企业进入过程。

长期目标是用 LLM 扮演经理和董事；当前里程碑是先把规则驱动的经济内核做扎实。

> 状态：**V0.6 — 工资—生产率规则、8h/16h 工时制度与自由成本加成价格实验。**
> 引擎可运行、固定随机种子可复现，并有 100+ 个回归测试（240 月长程 smoke
> 默认跳过，设置 `ECOSIM_SLOW_TESTS=1` 运行）。新增古典/Keynesian/MMT
> 三种政策制度、生产—库存闭环、需求约束投资、劳动市场修正、粮食平准库存、
> 服务业/非正规自雇，以及前后端分离的本地驾驶舱。
> LLM 智能体、合同、期货订单和最终单文件 HTML 仍是刻意推迟的内容。

## 快速开始

```powershell
python -m pip install -e .
python -m ecosim --months 240 --seed 1
```

不安装也可以直接运行：

```powershell
$env:PYTHONPATH = "src"
python -m ecosim --months 240 --seed 1
```

输出机器可读的完整运行记录：

```powershell
python -m ecosim --months 240 --seed 1 --json artifacts/run.json
```

运行测试：

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
```

## 历史阶段与政策制度

同一个经济内核可以通过 `--regime` 切换政策/货币制度，用于比较不同历史阶段：

- `classical`（默认）：pre-Keynesian 自由放任；金本位、货币总量守恒、无政府；
  粮食平准库存以私人粮商形式存在。
- `keynesian`：福利国家；工资/利润税、失业救济、公共投资、国债；金本位、货币守恒。
- `mmt`：主权货币 + 就业保障；央行购买国债/创造货币，政府作为最后雇主，
  失业者可以进入公共工程。

```powershell
$env:PYTHONPATH = "src"
python -m ecosim --months 240 --seed 1 --regime classical
python -m ecosim --months 240 --seed 1 --regime keynesian
python -m ecosim --months 240 --seed 1 --regime mmt

# 可选价格制度：参考价锚定的软成本加成（实验预设）
python -m ecosim --months 240 --seed 1 --regime classical --price-regime markup_soft

# V0.6 实验：成本加成 + 供求定价，无成本带，仅绝对安全轨
python -m ecosim --months 240 --seed 1 --regime classical --price-regime free
```

**V0.6 起默认价格制度是 `free`**：取消成本地板/天花板，只保留
`[0.01, 20×初始价]` 的绝对数值安全轨；不向 UI/统计暴露硬价格边界。
目标价为 `(1+markup)×正常单位成本`，markup 围绕按初始价格结构校准的正常
加成率随库存/未成交需求缓慢调整；参考价再混合成交价与供求信号。低于成本
的价格、亏损、减产和退出都是正常经济信号。

`band`（参考价 + 成本带）与 `markup_soft`（参考价 ±15% 软走廊）保留为
显式旧制度/对照实验。V0.6 A+B 后 free 四剧本 240 月可存活、无饥饿、金本位
货币守恒；classical free 仍有约 20% 失业（band 约 3%），这是需求/工资
结构尚未完全闭合的问题，后续 A2/C 继续处理。

## V0.6 工资—生产率与工时制度

工资不再是固定的 `WAGE_BASE + 失业/利润` 规则，而是有一个显式目标并带粘性：

```
w_target = WAGE_BASE × A^β × (1+π^e)^α × (1 + tightness + institutional)
```

- `A`：平滑劳动生产率指数（按初始价格计的实际增加值 / 就业有效劳动 FTE；
  第 12 个月定基 = 1.0）。前 12 个月是初始补库存阶段，不用于定基。
- `β`（`wage_productivity_share`）：生产率分享。古典/维多利亚 0.50，
  Keynesian/MMT 1.00，晚期 0.90。
- `π^e`：月度通胀预期，由剧本 `inflation_expectation` 初始化，再按 CPI
  观察值缓慢适应；`α`（`wage_inflation_pass_through`）是合同指数化程度：
  古典 0.25，Keynesian/晚期 0.75，MMT 1.00。
- `tightness`：原工资曲线的失业率项（斜率 0.5）和利润分享项。
- `institutional`：阶级/制度议价项。真实工资落后于生产率时产生追赶，
  生活成本跑赢工资时产生危机压力；由 `wage_bargain_power` 放大
  （古典 0.10，Keynesian 0.55，MMT 0.65）。
- 实际报价每月向目标调整 `wage_adjustment_speed`（10%–30%）；向下调整
  速度 ×3（名义工资向上粘性、向下更能响应失业）。

`work_hours` 是制度性标准工时：古典/维多利亚 16h，Keynesian/MMT/晚期 8h。
有效劳动 = 实际工时 / 标准工时，因此 8h 制度下按标准工时工作的工人仍贡献
1.0 FTE；本版本把短工时视为制度/闲暇维度，产能以标准全职工人为口径，
不额外模拟小时产出损失。儿童在本版本仍不参加劳动（只有消费和 allowance）。

政策/货币/税收/救济/公共投资/就业保障参数集中在
`src/ecosim/scenarios.py` 的 `ScenarioConfig`；设计说明见
[[docs/decisions/0004-historical-regimes.md]]。

## V0.6 单文件 HTML 发行版

**这是最终发行形态**：一个自包含 HTML，内含 JS 经济引擎和全部 UI，
双击或手机浏览器打开即可，不需要 Python/网络/外部资源。

```text
web/release/ecosim-v06.html
```

- 源码模块：`web/release/src/*.js`；构建：
  `node scripts/build_release_v06.mjs`（`--check` 检查无外部资源）。
- 已实现：V0.4 核心机制、V0.6 收入依赖需求/肉类/服务吸收/工资—生产率/
  8h/16h/默认 free 价格、V0.5 人口/PAYG 养老金。
- 未实现（后续 JS 分支）：A2 耐用品/废钢/土地兼并、C 完整信贷/央行反应函数。
- 黄金对比：`node scripts/test_engine_v06.mjs`（11/11）与
  `node scripts/compare_golden_v06.mjs --months=60|240`。
- Python 仅作为迁移期黄金 oracle，不再新增功能。

## V0.4 本地驾驶舱（诊断/oracle）

前后端分离的调试/观察界面（Python 标准库 HTTP + 原生 HTML/JS/SVG，无 CDN）：

```powershell
python scripts/serve_dashboard.py --port 8765
```

浏览器打开 <http://127.0.0.1:8765>。支持制度切换、月份时间轴、宏观/政府/商品/
行业图表、利润分解、银行/政府预算/库存/价格带诊断，以及三制度对比。
数据来自真实 `Engine.stats`，不写死示例数字。

## 可选的 LLM 经理探针

默认仿真不访问网络。若要在本地验证“长期规划”经理，可先设置环境变量（不要把 token 写进仓库）：

```powershell
$env:ANTHROPIC_BASE_URL = "https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN = "<本地 token>"
$env:ANTHROPIC_MODEL = "deepseek-v4-flash-vision-exp[1M]"
python scripts/llm_probe.py --months 60 --industry fertilizer_factory
```

也可以使用 `--settings <本地 settings_DS.json>`；该文件和 API key 已加入 `.gitignore`，不要提交。

## V0.3 已实现

- 240 个月度轮次；固定随机种子；货币总量守恒审计。
- 10 个行业：农业、煤炭、铁矿、钢铁、砖、纺织、机械、施工、化肥、服务业
  （服务业是 V0.4 新增的劳动密集/非正规自雇部门）。
- **2 的 N 次方设备表**：每个行业 8 个等级（1×~128×），产能翻倍、工人 +1；
  企业优先选择能负担的最小规模，再按需求升级。
- 企业级生产：显式设备目录、劳动需求、投入系数和熟练度。
- 资产阶级按工人最高生活水平（1.5 倍温饱篮子）消费生活资料；当前是封闭经济，不定义出口。
- 利润率口径：利润 /（土地 + 设备 + 存货）；土地不计折旧。
- 参考价试探型双边拍卖：最高买价 / 最低卖价撮合，成交价取双方报价平均值；
  成本价格带只作为薄市场的安全轨，不是硬价格管制。
- 劳动市场：真实发薪、雇佣/解雇、16/12/8 小时自愿工时、熟练度成长和失业。
- 资本主义企业进入与投资：按预期资本回报率决策，并带建设期。
- 土地市场与资本主义农业：土地稀缺且由自耕农持有；农场可以买地、雇工、购买化肥和农机。
  这是让农业劳动生产率不再冻结在糊口均衡的机制。
- 化肥厂单厂最多 2 台反应炉（临时周转资金规则），避免“零化肥”死锁；240 个月回归仍在使用。
- 银行工资周转贷；企业现金与所有者现金分离；分红；基于净资产的破产判断。
- 指标：GDP、投资、失业率、全社会利润率、资本存量、农业劳动生产率、企业数量、
  生活标准分布。

架构文档与代码保持一致：[[03_架构设计文档.md]]。

## 六边形地块视图

最终 HTML 发行版将使用 7 个六边形地块：中心是城市（纺织厂/施工队），周围是机械、钢铁、农业、矿场、化肥、砖厂。农业地块有河流、森林和金色网格农田；矿场是山地；空地块是草地和稀疏树木。当前已有单文件 UI 原型 web/ui-preview.html，尚未接入仿真；见 [[web/README.md]] 和 [[03_架构设计文档.md]]。

## 尚未实现

- 完整 LLM 经理/董事智能体与管理层级；当前只有本地探针，未接入仿真。
- 合同、期货/订单生产、跨月平滑采购。
- 单文件 HTML 发行版尚未同步 V0.4；当前入口是命令行 + 本地驾驶舱。
- `price_regime="markup_soft"` 已作为可选预设实现；自由 `markup` 与
  `demand_regime="les"` 仍是实验分支，默认仍是成本价格带 + 固定篮子。
- 场景 0（铁器时代）和场景 2（晚期资本主义）的完整配置。
- 多种资本品；V0.3 使用一个通用 `MACHINERY` 商品，钢铁厂用 `BRICK`，机床用 `STEEL`。

## 交付形态

本项目采用**双实现**策略：

- **Python 版**：逻辑验证、回归测试、参数校准的参考实现，也是当前仓库的主实现；
- **HTML 版**：最终发行版只包含一个 HTML 文件，电脑双击或手机指定浏览器打开即可游玩，
  不要求安装 Python；实现采用 TypeScript/JavaScript，Python 负责黄金样例。
  当前尚未实现，技术路线见 [[docs/decisions/0003-html-release.md]]。

详细的需求冲突与待选项见 [[docs/REQUIREMENTS_REVIEW.md]]。

## 仓库结构

```
.
├─ 01_产品介绍文档.md
├─ 02_需求定义文档.md          # 由人维护
├─ 03_架构设计文档.md          # 由 Code Bot 维护，必须与代码一致
├─ 04_开发日志文档.md
├─ src/ecosim/                 # Python 参考实现
├─ scripts/                    # LLM 探针、制度对比、验证、驾驶舱服务
├─ tests/                      # 确定性回归测试
├─ docs/
│  ├─ REQUIREMENTS_REVIEW.md   # 需求冲突 / 待选项
│  ├─ LLM_LOCAL_SETUP.md       # 本地 LLM 调试与安全
│  └─ decisions/               # 架构决策记录
└─ web/
   ├─ v04/                     # V0.4 前后端分离驾驶舱（index/app/styles）
   ├─ ui-preview.html          # 旧版完整 UI 原型（V0.3.2，硬编码）
   ├─ hex-map-preview.html     # 较早的纯地图原型
   ├─ screenshots/             # UI 截图
   └─ README.md                # HTML 发行版规划
```

## 开发流程

仓库遵循“人机分工”的流程：

1. **人负责需求文档**（`02_需求定义文档.md`）。Code Bot 不会静默改写需求。
2. **Code Bot 负责架构文档和代码**。架构必须写明需求没有展开的具体机制，并与
   `src/ecosim/` 保持一致。
3. 当需求在经济/史实上明显不合理，或存在逻辑漏洞时，Code Bot 在
   [[docs/REQUIREMENTS_REVIEW.md]] 记录冲突，并给出 2–4 个选项；由人决定后，才修改需求。
4. 代码、测试、架构文档、开发日志必须一起更新，才算完成。

详细检查清单见 [[CONTRIBUTING.md]]。

## 语言约定

所有产品文档、架构文档、代码注释、运行说明使用中文；代码标识符、协议名和第三方 API 名称
可以保留英文。

## 许可证

尚未选择许可证。在添加许可证之前，保留所有权利。
