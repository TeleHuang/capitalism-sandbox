# V0.6 交接（会话入口）

> 这是每次会话开始时自动加载的一页交接。V0.6 工作流见
> `docs/WORKSTREAM_V0.6.md`；V0.5 人口设计见
> `docs/DEMOGRAPHICS_DESIGN.md`；长程结果见 `docs/VALIDATION_V0.5.md`；
> 价格指导价见 `docs/decisions/0005-guidance-prices.md`。
> 标准工作流：Python + 本地 Web UI 迭代，最终发行单文件 HTML
> （`CLAUDE.md` / `CONTRIBUTING.md`）。

## 当前基线

- 分支：`v0.4-integration`
- 最新提交：见 `git log -1`（V0.5 人口/退休金 + V0.6 A 需求阶梯 +
  B 工资—生产率/自由价格 + UI 图标/工厂面板）
- Python 版本：0.6.0（迁移期 oracle；**唯一逻辑源已改为 TS/JS**）
- **单文件发行版已可用**：`web/release/ecosim-v06.html`（约 584 KiB，双击
  打开；JS 引擎 + UI + 图标全部内联，无外部资源）。模块源码在
  `web/release/src/`，构建脚本 `scripts/build_release_v06.mjs`。
- 本地 Python 驾驶舱只是诊断/oracle，不是最终发行版。
- 测试：128 fast tests，默认快速套件 **~127s**（12 个 `@slow` skipped，全部 OK）；
  240/600/1200 月长程用 `ECOSIM_SLOW_TESTS=1` 或
  `scripts/validate_v05.py`，不再每次开发都跑。性能：240 月约 15–16s，
  60 月约 4s（优化前 131s / 21.5s）。
- UI：**优先打开 `web/release/ecosim-v06.html`**（单文件发行版，含播放、
  人口/养老金、需求/价格、工厂面板、机制说明、黄金对比）。
  本地 Python 诊断：`python scripts/serve_dashboard.py --port 8765`。
  截图 `web/screenshots/v06-release-*.png`。
- 已实现：V0.4 全部机制 + V0.5 个体年龄/性别/家庭、Gompertz 死亡、
  ASFR 生育、儿童 allowance/消费、退休、PAYG 养老金（发薪/经营所得代扣）、
  `LATE_CAPITALISM`、粮食救济缓冲、土地继承/无地承接、家庭农场剩余收入。
- 长程验证：`scripts/validate_v05.py --months 1200 --seed 1 --jobs 4`。
- 性能（seed=1，classical）：240 月约 15–16 秒、60 月约 4 秒；
  优化前约 131 秒 / 21.5 秒（工资报价的 O(n²) 劳动力扫描已缓存）。
  引擎本身没有墙钟/每秒 TIK 节流；UI 是先跑完再显示，不是逐月播放。

## V0.6 A+B 结果（seed=1，240 月）

| 剧本 | 价格制度 | 人口 | 食物占比 | 服务占比 | 失业率 | GDP | 利润率 | CPI |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| classical | band | 1708 | 45.0% | 38.6% | 3.1% | 32,719 | -0.13% | 126.1 |
| classical | free | 1722 | 49.5% | 36.5% | 20.3% | 23,727 | +0.22% | 90.1 |
| keynesian | band | 1660 | 40.8% | 44.7% | 0.6% | 59,774 | +0.02% | 172.0 |
| keynesian | free | 1669 | 40.2% | 40.7% | 1.3% | 50,971 | -0.34% | 166.5 |

- 食物占比从 62.9% 降到 40–49%；服务占比 36–45%；肉类市场存在但工人实际工资
  仍接近 1 个温饱篮子，工人买肉≈0（高收入 Engel 行为由单测覆盖）。
- `free` 已删成本上下轨（仅内部数值夹紧），UI/统计不再暴露价格带；
  **V0.6 起默认 `free`**，band/markup_soft 为显式旧制度。
  classical free 失业 20.3% vs band 3.1%，这是需求/工资结构未完全闭合，
  后续 A2/C 继续处理；不再用 band 掩盖。
- 价格方向不再统一：classical free CPI 90（通缩）、keynesian free CPI 166（通胀）。
- 复利年化/过去 12 月利润率已在驾驶舱显示（`profit_rate_annualized`/
  `profit_rate_annual`）。
- 分支：`feature/v06-demand` `1d3bde4`、`feature/v06-wage-price` `9fbcb4d`；
  主线合并 `8a9fdd7` / `727c388`。

## V0.6 单文件 HTML 发行版（`4f15f01`）

- 文件：`web/release/ecosim-v06.html`（约 584 KiB，双击 / `file://` 打开）。
- 模块源码：`web/release/src/00-core.js` … `60-ui.js`；构建：
  `node scripts/build_release_v06.mjs`（`--check` 验证无外部资源）。
- 已移植：V0.4 核心（13 商品/12 行业含服务与汽车、市场/生产/劳动/投资/
  会计/银行/政府/MMT/JG/化肥/土地/粮食储备）、V0.6 A+B（Stone-Geary 需求、
  肉类、服务吸收、工资—生产率/8h/16h、free 价格）、V0.5 人口/PAYG 养老金、
  A2 耐用品/废钢/土地兼并。
- A2：衣物 60 月、住房 600 月、农机/汽车/设备 120 月；家庭存量、磨损/维修、
  vintage 报废、废钢（锚定铁矿）与钢厂“废钢+半煤”配方；土地兼并到 200 亩、
  超大型 2^N 农机、闲置小农机出售。
- 玩家 UI：开始页/A2 开关、进度、播放控制、KPI（含住房存量）/宏观/劳动/
  人口/货币图、**六边形城市地图**（中心 + 六行业地块，点击工厂）、
  商品/工厂面板/产品图标/2^N 机制说明、A2 机制页、耐用品/废钢/兼并数据页、
  黄金对比页、移动布局。
- 未实现：C 完整信贷/央行反应函数（已标注）。
- 验证：Node 引擎测试 16/16（`--slow`，含四剧本 240 月）；A2 off 时
  Python 黄金 oracle 60/240 月四剧本对照仍在合理区间；Chrome `file://`
  截图验证总览/地图/机制/数据页（A2 开启）。
- 备注：JS 是唯一逻辑源；Python 只作 oracle，不再新增功能。

## V0.5 历史 240 月结果（家庭农场修复后）

| 制度 | 人口 | 饥饿死亡 | 粮食产出/需求（吨/月） | 利润率 | 养老金基金 |
|---|---:|---:|---:|---:|---:|
| classical | 1666 | 0 | 175.3 / 158.4 | -0.096% | 0 |
| keynesian | 1640 | 0 | 158.4 / 161.7 | +0.186% | 126,793 |
| mmt | 1601 | 0 | 146.2 / 156.4 | +0.030% | 207,800 |
| late_capitalism | 1311 | 0 | 134.6 / 134.4 | -0.244% | 23,410 |

- 金本位（classical/keynesian/late）货币守恒；MMT 央行货币约 3.05M（显式）。
- `pension_recipients` 含到龄自耕农；`retirees` 只统计退出劳动市场的雇员。
- 家庭农场不再为“给自己发工资”借债；240 月家庭农场清算 0 次。
- 利润率是资本主义部门口径；`household_operating_income` 单列家庭经营所得。

## 1200 月长程验证（seed=1，家庭农场修复后）

| 制度 | 人口 | 累计饥饿死亡 | 家庭农场（清算） | estate_land | 结论 |
|---|---:|---:|---:|---:|---|
| classical | 755 | 813 | 200（0） | 100 | 仅饥饿项失败 |
| keynesian | 1751 | 0 | 240（0） | 0 | 通过 |
| mmt | 1138 | 0 | 180（0） | 0 | 通过 |
| late_capitalism | 336 | 0 | 295（0） | 220 | 通过 |

- 养老金基金/预算恒等式在四剧本均通过；金本位货币守恒。
- 家庭农场修复消除了 estate_land 大规模沉没和“借债发自己工资”清算；
  classical 600/1200 饥饿从 921/974 降到 813/813，但**未消除**；
  剩余饥荒集中在 324–404 月的需求/流动性/粮食储备危机，不是农场清算。
- classical 1200 失业率约 20.9%（修复前 10.3%），是收入分配变化的副作用，
  需要与工资/需求/土地机制一起校准。
- 晚期资本主义按设计老龄化收缩（336 人、末年少儿出生），不是崩溃。

## 需求缺口：土地开垦尚未实现

`02_需求定义文档.md` 写了“土地为初始自然资源；可由农机/人力扩张”，但代码：
- `TOTAL_LAND_MU = 6000` 固定，600 自耕农 ×10 亩一次分完；
- `LandMarket` 只做存量转手，没有 `wild_land`/可开垦池；
- 农机只提高“人均可管理亩数”，不增加总耕地；
- `tests/test_invariants.py` 断言土地总量恒等于 6000。

后果：粮食供给有固定上限；价格信号无法通过“涨价 → 开垦 → 新供给”完成
负反馈；`estate_land` 只能继承/承接，不能开垦。下一轮 `feature/land-reclamation`
应补：可开垦土地池、开垦投资（劳动/设备/时间、边际成本递增）、
estate 拍卖/再分配、统计与 UI。详见 `docs/LAND_RECLAMATION_DESIGN.md`（待建）。

## 下一步优先级（JS/TS 单一源）

1. **E/F JS/TS 模块化引擎 + 单文件 HTML 发行版（最高优先）**：
   `feature/html-engine`，模块化 ES modules/TS + Node 测试 + 单文件构建；
   先交付核心 V0.6 可玩版（V0.4 机制 + 需求/工资/free + 服务/肉类 +
   人口/养老金尽量），Python 只做黄金 oracle。
2. **A2 耐用品/生命周期（已实现，`feature/js-durables`）**：衣服 60 月、
   住房 600 月、农机/车 120 月、废钢/钢厂回购、汽车/住房存量、土地兼并/
   超大型农机。已知简化：独立汽车装配行业（机械厂不切换产出）、砖砌炉窑
   不进入 vintage 寿命（结构资产）、古典 240 月失业约 20.7%/无饥饿死亡，
   中间年份仍有投资—就业周期，后续可与 C/D 一起平滑。
3. **C 银行/信贷/MMT（JS）**：贷款创造存款、准备金/资本约束、信用审查、
   央行通胀/利率反应函数。
4. **D 土地开垦/estate（JS）**：开局缓慢开垦、estate 拍卖/再分配。
5. **`price_regime="free"` 已是默认**：无成本价格带；A2/C 后继续压
   classical 失业/价格方向；band 只作旧制度对照。
6. **D3 剧本/长程**：`IRON_AGE`、`NEOLIBERAL`；20–100 seeds、
   1200 月、长期负利润与剩余古典饥荒。
7. **D4 信贷冲击稳定器**：`docs/CREDIT_BACKSTOP_DESIGN.md` 的
   wage_arrears/LLR/食品券/冻结规则，与 C 一起做。

## 并行版本树（进行中）

基线：`v0.4-integration`；每个 feature 从当前 HEAD 分支：

| 分支 | worktree | 状态/目标 |
|---|---|---|
| `feature/demography` | `.claude/worktrees/demography` | **已合并** `365aa93`：V0.5 人口/代际/退休金 |
| `fix/demography-safety` | `.claude/worktrees/demography-fix` | **已合并** `7429a3b`：救济/养老金/土地/统计修复 |
| `feature/price-guidance` | `.claude/worktrees/price-guidance` | **待合并/待组合测试**：opt-in 指导价 v1（`33ca831`）+ v2（`7c1d949`）；默认已改为 free，guidance 仍 opt-in |
| `fix/household-farm-income` | `.claude/worktrees/household-income` | **已合并** `0e15fad`：自耕农剩余收入/不借债发自己工资 |
| `feature/land-reclamation` | `.claude/worktrees/land-reclamation` | **未合并** `2f79f0e`：P1–P3 开垦/estate；缺最终全量+600/1200，且触发阈值 180 太高 |
| `feature/ui-icons` | `.claude/worktrees/ui-icons` | **已合并** `ca5ebeb`：产品图标、工厂面板、机制说明（V0.6 UI） |
| `feature/v06-demand` | `.claude/worktrees/v06-demand` | **已合并** `8a9fdd7`：收入依赖需求、肉类/服务吸收 |
| `feature/v06-wage-price` | `.claude/worktrees/v06-wage-price` | **已合并** `727c388`：生产率工资、8h/16h、free 价格制度 |
| `feature/html-engine` | `.claude/worktrees/html-engine` | **进行中**：TS/JS 单一逻辑源 + 单文件 HTML 发行版 |
| `feature/js-durables` | `.claude/worktrees/js-durables` | **待合并**：A2 耐用品/废钢/土地兼并（JS 发行版）；A2 可关闭以重放 oracle |
| `feature/v06-durables` | `.claude/worktrees/v06-durables` | **已取消**：A2 推迟到 JS 发行版之后 |
| `feature/ui-cockpit` | `.claude/worktrees/ui-cockpit` | 已合并 `d8cdae7` |
| `feature/ui-comparison` | `.claude/worktrees/ui-comparison` | 暂停 |
| `feature/services` | `.claude/worktrees/services` | 已合并 `79d27de` |
| `feature/l2` | `.claude/worktrees/l2` | 暂停（自由 markup/LES WIP） |
| `feature/l2-soft` | `.claude/worktrees/l2-soft` | 已合并 `7c97df0` |
| `feature/fertilizer` | `.claude/worktrees/fertilizer` | 已合并 `61fae0e` |
| `feature/validation` | `.claude/worktrees/validation` | 已合并 `1891485` |
| `feature/plan-skill` | `.claude/worktrees/plan-skill` | 已合并 `ed231e1` |

集成规则：子代理在各自 worktree 提交；主代理审查 diff、跑测试、
cherry-pick 到 `v0.4-integration`；冲突时以测试和用户可见指标为准。

**标准工作流（2026-10-25 用户确认，必须遵守）**：

1. **唯一逻辑源：TypeScript/JavaScript**。经济逻辑、UI、测试都在 JS/TS
   模块中维护，ES modules/TypeScript 低耦合高内聚；Node 测试 + 浏览器
   迭代。不再新增 Python 功能。
2. **发行：单文件 HTML**。构建脚本把 JS/CSS/图标/数据内联成一个 HTML；
   双击/手机浏览器直接打开，不依赖外部文件/CDN/图片/字体/Python。
   发行里程碑统一构建，不在每次小改动时生成巨大 HTML。
3. **Python = 迁移期 oracle**。`src/ecosim/` 只作黄金运行/参数校准参考；
   JS parity 后冻结，不双维护。新机制（A2/人口/银行）直接以 JS/TS 实现。

## 工作方式

- 长任务用子代理 + git worktree 并行开发；每个 feature 一个分支/提交。
- 主代理负责方案选型、审查、跑测试、cherry-pick 到 `v0.4-integration`。
- 不直接改 `main`；不提交 API key/本地设置/临时产物。
- 每完成一个阶段，更新本文件和 `docs/WORKSTREAM_V0.5.md`。
- 用户看的中间产品必须有 UI；纯 CLI 只作为调试/验证。
- **测试策略（避免“面向测试编程”）**：
  - 默认 `python -m unittest discover -s tests -v` 只跑快速单元/60 月以内；
    240/600/1200 月测试用 `@slow`（`tests/_slow.py`）门控，设置
    `ECOSIM_SLOW_TESTS=1` 才跑。
  - 长程验证优先用 `scripts/validate_v05.py`，不要让每个新功能复制一套
    240/600 月测试。
  - 新功能只加 1–3 个真正防回归的测试；开发中用定向测试，合并前跑一次
    slow suite，不要每改一行就跑 5–20 分钟全量。

## 常用命令

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m ecosim --months 240 --seed 1 --regime classical
python -m ecosim --months 240 --seed 1 --regime keynesian
python -m ecosim --months 240 --seed 1 --regime mmt
python -m ecosim --months 240 --seed 1 --regime late_capitalism
python scripts/compare_regimes.py --months 240 --seed 1 --json artifacts/regimes_240.json
python scripts/validate_v05.py --months 1200 --seed 1 --jobs 4
```

## 关键文件

- `src/ecosim/engine.py`：月度主循环、人口过程、养老金、粮食救济、土地遗产
- `src/ecosim/government.py`：制度/政府/央行/养老金台账
- `src/ecosim/scenarios.py`：`ScenarioConfig` 与 classical/keynesian/mmt/late_capitalism
- `src/ecosim/models.py`：Worker 年龄/家庭/养老金字段、AssetPool/FoodReserve/Bank
- `tests/test_demography.py`：人口/养老金/救济/土地回归
- `scripts/validate_v05.py`：1200 月长程验证
- `docs/DEMOGRAPHICS_DESIGN.md`：设计 + v0.5.1 修复状态
- `docs/CREDIT_BACKSTOP_DESIGN.md`：D4 设计
