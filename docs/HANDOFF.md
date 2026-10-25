# V0.5 交接（会话入口）

> 这是每次会话开始时自动加载的一页交接。详细档案见
> `docs/WORKSTREAM_V0.5.md`；人口设计与修复见
> `docs/DEMOGRAPHICS_DESIGN.md`；长程结果见 `docs/VALIDATION_V0.5.md`；
> 价格指导价见 `docs/decisions/0005-guidance-prices.md`（feature/price-guidance 分支）。

## 当前基线

- 分支：`v0.4-integration`
- 最新提交：`afeebca`（V0.5 人口/代际/退休金模块 + v0.5.1 修复 + 验证文档）
- Python 版本：0.5.0
- 测试：88 个全绿（人口单测/不变量/测试强化；855.9s，seed=1）
- UI：`python scripts/serve_dashboard.py --port 8765` → `http://127.0.0.1:8765`
  （仍为 V0.4 面板；D2 人口面板待做）
- 已实现：V0.4 全部机制 + V0.5 个体年龄/性别/家庭、Gompertz 死亡、
  ASFR 生育、儿童 allowance/消费、退休、PAYG 养老金（发薪代扣）、
  `LATE_CAPITALISM`、粮食救济缓冲、土地继承/无地承接、人口统计。
- 长程验证：`scripts/validate_v05.py --months 1200 --seed 1 --jobs 4`。

## 当前 240 月结果（seed=1，validation_v05/seed1_240.json）

| 制度 | 人口 | 儿童 | 退休 | 年出生 | 饥饿死亡 | 失业率 | 利润率 | 养老金基金 | 粮价 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| classical | 1670 | 285 | 0 | 17 | 0 | 16.8% | -0.16% | 0 | 81 |
| keynesian | 1639 | 323 | 99 | 14 | 0 | 0.7% | +0.06% | 199,999 | 117 |
| mmt | 1584 | 285 | 137 | 8 | 0 | 0.0% | -0.09% | 301,126 | 117 |
| late_capitalism | 1304 | 171 | 128 | 3 | 0 | 1.7% | -0.04% | 129,263 | 99 |

- 金本位（classical/keynesian/late）货币守恒；MMT 央行货币约 2.10M（显式）。
- `pension_recipients` 含到龄自耕农；`retirees` 只统计退出劳动市场的雇员。
- 利润率是资本主义部门口径；三制度接近零，古典/MMT/晚期略负。

## 1200 月长程验证（seed=1，validation_v05/seed1_1200.json）

| 制度 | 人口 | 儿童 | 退休 | 最后 12 月出生 | 累计饥饿死亡 | 结论 |
|---|---:|---:|---:|---:|---:|---|
| classical | 598 | 95 | 0 | 12 | 974 | 仅饥饿项失败 |
| keynesian | 1216 | 241 | 156 | 15 | 239 | 仅饥饿项失败 |
| mmt | 930 | 159 | 186 | 7 | 0 | 通过 |
| late_capitalism | 354 | 48 | 64 | 1 | 0 | 通过 |

- 养老金基金/预算恒等式在四剧本均通过（补贴已计入 `pension_revenue`）。
- 古典/Keynesian 的 1200 月饥荒是长周期经济内核问题：失业/负利润、
  `estate_land` 闲置（无继承/承接人时不拍卖）、食品产量低于需求。
  人口模块的救济缓冲避免了即时饥荒，但不能替代土地市场/需求/价格机制。
- 晚期资本主义按设计进入老龄化/人口收缩（354 人、末年少儿出生），不是崩溃。

## 下一步优先级

1. **D2 驾驶舱人口面板**：人口金字塔、出生/死亡、抚养比、养老金收支；
   `/api/run` 增加 demography 分组；时间轴支持 1200 月。
2. **D3 剧本**：`IRON_AGE`（无工业/高生育高死亡/儿童劳动）、可选
   `NEOLIBERAL`；`LATE_CAPITALISM` 已实现。
3. **D4 信贷冲击稳定器（最高优先）**：`docs/CREDIT_BACKSTOP_DESIGN.md`
   已设计：wage_arrears、LLR/贴现窗口、食品券、银行冻结规则校准；
   用 240 月信贷冲击对比死亡/零现金/饥饿。
4. **D5 百年仿真/长程修复**：土地 estate 拍卖或无地分配、长期负利润、
   古典/Keynesian 饥荒；20–100 seeds 验证。
5. **价格指导价 v2**：`feature/price-guidance` 已实现 opt-in `guidance`
   （ADR 0005）。v1 用订单簿库存 vs 月需求导致通缩—失业—饥荒；v2 改用
   库存覆盖月数（库存/月度需求），仍在 240 月对比中。默认保持 `band`。
6. **HTML 单文件发行版**：本地驾驶舱可用；单文件发行版仍需同步 V0.5。

## 并行版本树（进行中）

基线：`v0.4-integration`；每个 feature 从当前 HEAD 分支：

| 分支 | worktree | 状态/目标 |
|---|---|---|
| `feature/demography` | `.claude/worktrees/demography` | **已合并** `365aa93`：V0.5 人口/代际/退休金 |
| `fix/demography-safety` | `.claude/worktrees/demography-fix` | **已合并** `7429a3b`：救济/养老金/土地/统计修复 |
| `feature/price-guidance` | `.claude/worktrees/price-guidance` | **进行中**：opt-in 指导价 v1（`33ca831`）+ v2 库存覆盖月数 |
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
