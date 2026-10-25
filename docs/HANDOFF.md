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
- Python 版本：0.6.0
- 测试：127 fast tests，默认快速套件 **~97s**（12 个 `@slow` skipped，全部 OK）；
  240/600/1200 月长程用 `ECOSIM_SLOW_TESTS=1` 或
  `scripts/validate_v05.py`，不再每次开发都跑。性能：240 月约 15–16s，
  60 月约 4s（优化前 131s / 21.5s）。
- UI：`python scripts/serve_dashboard.py --port 8765` → `http://127.0.0.1:8765`
  （V0.5 人口面板 + V0.6 产品图标/工厂点按面板/机制说明已合并 `ca5ebeb`；
  截图 `web/screenshots/v06-*.png`）
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
- `free` 已删成本上下轨（仅绝对安全轨）；240 月四剧本无饥饿、金本位货币守恒。
  classical free 失业 20.3% vs band 3.1%，**默认保持 band**；free 仍 opt-in。
- 价格方向不再统一：classical free CPI 90（通缩）、keynesian free CPI 166（通胀）。
- 复利年化/过去 12 月利润率已在驾驶舱显示（`profit_rate_annualized`/
  `profit_rate_annual`）。
- 分支：`feature/v06-demand` `1d3bde4`、`feature/v06-wage-price` `9fbcb4d`；
  主线合并 `8a9fdd7` / `727c388`。

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

## 下一步优先级（V0.6）

1. **A2 耐用品/生命周期（最高优先）**：衣服 60 月、住房 600 月（维修/摊销）、
   农机/车 120 月；汽车/住房存量；报废设备/车 → 废钢（价格锚定铁矿，
   钢厂用废钢+半量煤炭）；土地兼并/超大型农机，小农机闲置/出售。
2. **C 银行/信贷/MMT**：贷款创造存款、准备金/资本约束、信用审查/风险溢价、
   央行通胀/利率反应函数；金本位准备金率扩张信用。
3. **D 土地开垦/estate**：开局缓慢开垦（不用粮价 180 阈值）；合并
   `feature/land-reclamation`，estate 拍卖/再分配。
4. **E 单文件 HTML 发行版**：玩家机制 UI（产品图标、工厂面板、2^N、
   矿类/土地/消费/人口说明），全部逻辑/资源内联；当前 `web/v04` 只是诊断版。
5. **重新评估 `price_regime="free"` 默认**：A2/C 完成后看 classical 失业/
   价格方向；当前默认仍 band。
6. **D3 剧本/长程**：`IRON_AGE`、`NEOLIBERAL`；20–100 seeds、
   1200 月、长期负利润与剩余古典饥荒。
7. **D4 信贷冲击稳定器**：`docs/CREDIT_BACKSTOP_DESIGN.md` 的
   wage_arrears/LLR/食品券/冻结规则校准，与 C 一起做。

## 并行版本树（进行中）

基线：`v0.4-integration`；每个 feature 从当前 HEAD 分支：

| 分支 | worktree | 状态/目标 |
|---|---|---|
| `feature/demography` | `.claude/worktrees/demography` | **已合并** `365aa93`：V0.5 人口/代际/退休金 |
| `fix/demography-safety` | `.claude/worktrees/demography-fix` | **已合并** `7429a3b`：救济/养老金/土地/统计修复 |
| `feature/price-guidance` | `.claude/worktrees/price-guidance` | **待合并/待组合测试**：opt-in 指导价 v1（`33ca831`）+ v2（`7c1d949`）；纯价格仍崩溃，默认 band |
| `fix/household-farm-income` | `.claude/worktrees/household-income` | **已合并** `0e15fad`：自耕农剩余收入/不借债发自己工资 |
| `feature/land-reclamation` | `.claude/worktrees/land-reclamation` | **未合并** `2f79f0e`：P1–P3 开垦/estate；缺最终全量+600/1200，且触发阈值 180 太高 |
| `feature/ui-icons` | `.claude/worktrees/ui-icons` | **已合并** `ca5ebeb`：产品图标、工厂面板、机制说明（V0.6 UI） |
| `feature/v06-demand` | `.claude/worktrees/v06-demand` | **已合并** `8a9fdd7`：收入依赖需求、肉类/服务吸收 |
| `feature/v06-wage-price` | `.claude/worktrees/v06-wage-price` | **已合并** `727c388`：生产率工资、8h/16h、free 价格制度 |
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

**标准工作流（用户确认，必须遵守）**：

1. **迭代阶段**：Python + 本地 Web UI。`src/ecosim/` 模块低耦合高内聚，
   方便快速改逻辑；`scripts/serve_dashboard.py` + `web/v04/` 提供诊断界面。
   JavaScript 也能做类似结构，当前选 Python 是为了迭代速度和可测试性。
2. **发行阶段**：最终产品是**一个 HTML 文件**，包含全部经济仿真逻辑和
   UI，电脑双击/手机浏览器直接打开，方便传播；不依赖外部文件/CDN/图片/
   字体/Python。不要在每次小改动时生成巨大自包含 HTML，发行里程碑统一构建。
3. Python 是逻辑权威参考；JS 发行版用固定 seed 黄金运行复现关键指标。
   本地驾驶舱是诊断界面，不是最终发行版。

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
