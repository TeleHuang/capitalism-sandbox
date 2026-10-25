# V0.5 交接（会话入口）

> 这是每次会话开始时自动加载的一页交接。详细档案见
> `docs/WORKSTREAM_V0.5.md`；人口设计与修复见
> `docs/DEMOGRAPHICS_DESIGN.md`；长程结果见 `docs/VALIDATION_V0.5.md`；
> 价格指导价见 `docs/decisions/0005-guidance-prices.md`（feature/price-guidance 分支）。

## 当前基线

- 分支：`v0.4-integration`
- 最新提交：见 `git log -1`（V0.5 人口/代际/退休金 + v0.5.1 修复 +
  v0.5.2 家庭农场剩余收入修复 + 文档）
- Python 版本：0.5.0
- 测试：95 个全绿（88 + 7 家庭农场回归；分支 1049.3s，
  主线合并后 1403.3s，seed=1）；D2 新增 2 个 dashboard tests 单独通过
  （97 total targeted；D2 为 UI/API-only，未重跑 23 分钟全量）。
- UI：`python scripts/serve_dashboard.py --port 8765` → `http://127.0.0.1:8765`
  （V0.5 人口面板已合并，`3833c23`；截图
  `web/screenshots/v05-demography-keynesian-60.png`）
- 已实现：V0.4 全部机制 + V0.5 个体年龄/性别/家庭、Gompertz 死亡、
  ASFR 生育、儿童 allowance/消费、退休、PAYG 养老金（发薪/经营所得代扣）、
  `LATE_CAPITALISM`、粮食救济缓冲、土地继承/无地承接、家庭农场剩余收入。
- 长程验证：`scripts/validate_v05.py --months 1200 --seed 1 --jobs 4`。

## 当前 240 月结果（seed=1，家庭农场修复后）

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

## 下一步优先级

1. **土地开垦/estate 拍卖（需求缺口，最高优先）**：见上节；
   直接针对 1200 月古典/Keynesian 剩余饥荒和长期土地约束。
2. **D4 信贷冲击稳定器**：`docs/CREDIT_BACKSTOP_DESIGN.md` 已设计：
   wage_arrears、LLR/贴现窗口、食品券、银行冻结规则校准；
   用 240 月信贷冲击对比死亡/零现金/饥饿。
3. **价格指导价 v2 + 人口/救济组合**：`feature/price-guidance` 已实现
   opt-in `guidance`（ADR 0005，v2 `7c1d949`，85 tests）；纯价格变体
   仍崩溃，家庭农场会计修复后需与人口/食品救济一起重测。
4. **D2 驾驶舱人口面板（已完成 `3833c23`）**：4 张人口 KPI、人口金字塔、
   出生/死亡、抚养比、养老金收支、三制度对比人口列；截图
   `web/screenshots/v05-demography-*.png`。后续可加 1200 月时间轴与
   detail 视图。
5. **D3 剧本**：`IRON_AGE`、可选 `NEOLIBERAL`；`LATE_CAPITALISM` 已实现。
6. **D5 百年仿真/长程修复**：20–100 seeds、长期负利润、剩余古典饥荒。
7. **HTML 单文件发行版**：本地驾驶舱可用；单文件发行版仍需同步 V0.5。

## 并行版本树（进行中）

基线：`v0.4-integration`；每个 feature 从当前 HEAD 分支：

| 分支 | worktree | 状态/目标 |
|---|---|---|
| `feature/demography` | `.claude/worktrees/demography` | **已合并** `365aa93`：V0.5 人口/代际/退休金 |
| `fix/demography-safety` | `.claude/worktrees/demography-fix` | **已合并** `7429a3b`：救济/养老金/土地/统计修复 |
| `feature/price-guidance` | `.claude/worktrees/price-guidance` | **待合并/待组合测试**：opt-in 指导价 v1（`33ca831`）+ v2（`7c1d949`）；纯价格仍崩溃，默认 band |
| `fix/household-farm-income` | `.claude/worktrees/household-income` | **已合并** `0e15fad`：自耕农剩余收入/不借债发自己工资 |
| `feature/land-reclamation` | （待建） | **规划中**：可开垦土地池、开垦投资、estate 拍卖/再分配 |
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

**UI 方向（用户确认）**：前后端分离，不为每个版本生成巨大自包含 HTML。
`scripts/serve_dashboard.py` 用 Python 标准库 `http.server` 提供
`/api/run` 和 `/api/compare`；`web/v04/index.html` + `app.js` 通过 fetch 渲染。
启动后浏览器打开 `http://127.0.0.1:8765`。

## 工作方式

- 长任务用子代理 + git worktree 并行开发；每个 feature 一个分支/提交。
- 主代理负责方案选型、审查、跑测试、cherry-pick 到 `v0.4-integration`。
- 不直接改 `main`；不提交 API key/本地设置/临时产物。
- 每完成一个阶段，更新本文件和 `docs/WORKSTREAM_V0.5.md`。
- 用户看的中间产品必须有 UI；纯 CLI 只作为调试/验证。

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
