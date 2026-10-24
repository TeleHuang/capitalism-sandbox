# V0.4 工作流：负反馈修复与历史阶段剧本

> 本文件是长任务的交接文档。每次大阶段结束后更新“进度日志”和“下一步”。
> 约束：用户已确认四个产品选择；修复按修正版最小方案执行；先 Python，JS 冻结到 Python 稳定。

## 0. 用户已确认的产品选择

1. **货币制度**：先做金本位 + 银行中介资本家储蓄（保持货币守恒）；信用货币（贷款创造存款）作为后续剧本开关，不进入 V0.3.2 修复包。
2. **政府/出口**：先跑纯封闭私人经济基线；最小政府（税收 + 失业救济 + 公共投资）做成**可开关模块**；出口更后。
3. **价格制度**：成本加成 + 软价格走廊，删除 `ref×1.02` 硬帽；必须与收入/需求函数配套。
4. **农业优先**：保留 priority，但设活跃农业项目上限（2–3 个或 ≤30% 槽位），配 6–12 个月食品储备；不直接删除 priority。
5. **历史阶段**：仿真器要覆盖凯恩斯主义之前的历史阶段，因此政策/货币/价格制度必须是**剧本配置开关**，而不是把 Keynesian/MMT 硬编码成唯一路径。
6. **政府作为最终借贷人（Keynesian/MMT）**：作为可验证模块，必须能开关、能对比；默认历史阶段（pre-Keynesian）不启用。

## 1. 修正版诊断（对抗性审查后）

**当前不是“需求不足”，而是“供给链 + 劳动配置 + 周转资金”的协调失败。**

- 当前基线：1,059 名工人约 359 万现金，100 名资本家约 173 万；T240 布需求 1,185、建筑 237、机械 20，但供给为 0；食品/煤/铁严重过剩。
- 投资最后一次为正 T105；T105 银行现金 85,077、贷款 14,923；银行现金首次归零 T178。**信贷不是第一约束。**
- `representative_roi` 用满产×SKILL_MAX×当前价，T105 给出煤 81.5%/月、铁 136.3%、化肥 884.8%、建筑 521.1%；先把信贷打开会把钱导向过剩行业。
- 1,059 人几乎全在煤/铁/农业；新企业 0 工人；213 个 owner-operator 不进失业/招聘池。**劳动再配置是点火条件。**
- 初始设备 `age=0`、`life=120`，前 120 个月没有替换投资；手工 t0 按当前 `_start_project`/`best_equipment_choice` 启动不了。
- 只去土地折旧：利润率 -0.373% → 约 -0.198%；按 COGS 约 -0.236%；真正缺口是工资 17.8k vs 收入 10.7k。

**仍然成立：** 资本品循环 `brick→steel→machinery→coal/iron→steel` 自锁；土地折旧、农业 priority、银行现金 cap、破产不核销、替换投资缺失、基线不统一。

## 2. 最小方案（V0.3.2 范围内）

### Phase 0：冻结基线 + 会计修正（不改行为）

- 冻结当前 commit + seed=1 + config，生成 `artifacts/baseline.json`。
- 折旧只算 `equipment_value/120`；土地不计折旧。
- 利润中的中间投入改用 `last_input_used × 参考价`（COGS 的简化版），采购额只进现金流。
- 农场化肥计入成本。
- 项目完成/取消退回 `project.inventory`。
- 破产：注销 `enterprise.debt`、清 `bank.loans[id]`、记录 `bank.write_offs`、回收库存/设备/土地到 `asset_pool`。
- 死亡自耕农：清 `land.owners`/`enterprise_by_owner`/`land_owned`，停用家庭农场，土地进 `land.estate_land`，现金进银行。
- 告警改为 `>=3` 连续零产出；stats 增加利润分解、银行资产负债表、项目队列、企业库存/工资分布。

### Phase 1：最小负反馈套件

1. **L1 生产—库存—订单**
   - `step()` 开头生成 `ProductionPlan` 快照（I/O/B、Dhat、Qplan、planned_inputs）。
   - `produce()` 用 plan 上限；`input_needs()` 复用同一 Qplan；`desired_workers()` 用 plan。
   - POUT/平滑：`β≤0.3`、6 个月调整、12 期平均销售；不要用 τ=2–3。
   - 记录 order-level fill/lost sales；不用被供给截断的 sales 做预测。
   - 旧测试兼容：`produce(..., plan=1.0)`、`desired_workers(..., plan=1.0)` 默认满产。
2. **一次性手工 t0 bootstrap**
   - 独立于 ProjectQueue，直接安装；每厂 cap 1–2；包含 textile；砖/钢/机械/施工/纺织各一套；只给新进入者；正常扩张禁止 manual。
3. **业主权益/存款银行周转资金**
   - 金本位、货币守恒版本：先业主注资，再银行小额周转贷；不做 L4b 内生货币。
   - 银行权益 = 现金 + 贷款 − 存款；先核销 27,519 的 loans/debt 差额。
4. **Shell/资产回收 + 需求约束投资信号 + 农业项目配额**
   - 清理无设备/无工人/无库存的 shell；释放 max_firms 槽位。
   - ROI 改为 `min(Dhat, capacity) × price − 可变成本 − 固定成本`；entry/扩张/选型共用。
   - 农业保留 priority，活跃农业项目 cap 2–3 或 ≤30% 槽位；食品储备 6–12 个月。
5. **替换投资流 δK + 初始 vintage**
   - 用 δK 聚合替换流（或初始 vintage 0–119）；先给机械/钢铁/砖底仓需求。

### 后置（V0.4 研究包，需要 ADR）

- L4b 内生货币/完整银行资产负债表/FlowMatrix。
- L6 政府/税收/UI/公共投资/国债（Keynesian/MMT 模块，可开关）。
- L7 进口/外汇/战略储备/Leontief 配给。
- L2 完整 markup/LES；L5 完整 matching/UI。
- 设备 building_cost、完整 age/life/vintage、Calvo、Sobol/BK/power-law。
- Python/JS 同 seed 1e-6 golden（Python 稳定前冻结 JS）。

## 3. 验收指标

- 核心行业（钢、砖、纺织、机械、建筑）零产出月份占比 <10%，最长连续 <6 个月。
- 库存/销售中位数 1–3 个月；fill rate ≥95%；煤/铁库存 <6 个月销量。
- 投资/GDP 15–25%；不得连续 6 个月投资=0；替换占比 40–60%；项目完成率 >70%；活跃项目 ≤10；农业项目 ≤30%。
- 利润率 ≥50% 月份为正；价格在 `[0.5,2.5]×单位成本`；库存—价格回归 <0。
- 失业率 5–10%；工资曲线斜率约 −0.1；Okun/Phillips/Beveridge 符号正确。
- 冲击—恢复：需求 −20%、生产率 −20%、信用 +200bp；half-life 6–24 月；<36 月回到基线；无永久零产出。
- SFC/会计：`bank.equity=loans+reserves−deposits`；`loans=Σdebt`；无负库存；土地总量恒定。

## 4. 进度日志

- 2026-10-24 21:xx：用户确认四个产品选择；工作流文档创建。
- 2026-10-24 22:xx：Phase 0 完成：
  - `_finance` 折旧改为 `equipment_value/120`（土地不计折旧）；中间成本改为 `last_input_used × 参考价`。
  - 破产清算核销 `enterprise.debt`/`bank.loans`，回收库存/设备/土地到 `AssetPool`/`land.estate_land`。
  - 死亡自耕农遗产清算 `_settle_estate`；项目完成/取消退回 `project.inventory`。
  - 零产出告警改为持续提醒；stats 增加 `bank_write_offs`、`estate_land`、`asset_pool_*`、`zero_output_streak`、`active_projects`。
- 2026-10-24 22:xx：Phase 1 第一版完成：
  - L1：`_update_expectations_and_plans` 在 step 开头生成计划；`produce()`/`desired_workers()`/`input_needs()` 共用计划；POUT 6 个月调整；行业需求 × 产能份额；食品低于 3 个月保底满产。
  - 修正“基础温饱误判为小康”的 1.5 倍需求冲击：小康要求 1.5× 三项 + 积蓄；只有 `cash >= COMFORT_SAVINGS` 且已有基础口粮才尝试升级。
  - 临时安全阀：价格带限制在初始价 2×（floor）/4×（ceiling）；工资下限和工资报价上限为 `WAGE_BASE×5`。L2/L5 会替换。
  - 手工 t0 启动：`brick_manual/steel_manual/machinery_manual/construction_manual/textile_manual`，独立于 ProjectQueue，每行业 12 个月最多一次。
  - 替换投资：每 12 个月给有设备的企业补一台主力设备（聚合 δK 流）。
  - 农业项目 cap：活跃农业项目 ≤3；`priority` 不再无限占满。
  - 需求约束 ROI：`representative_roi` 接受 `demand`，`best_equipment_choice` 用行业需求/产能份额；需求为 0 时不投资。
  - Shell 清理：无设备/工人/土地/库存的壳企业 6 个月后停用。
- 2026-10-24 22:xx：26 个测试全绿（新增 `tests/test_feedback.py` 9 个）。
  - 当前 240 月 seed=1：存活 1100、无死亡；钢/砖/机械零产出 0 个月，建筑 3、纺织 1；化肥 19 个零产出月；投资>0 153/240；利润>0 13/240；活跃项目 ≤8，农业项目 ≤3；化肥超限仍有 26 个企业-月（待查）。
  - 当前剩余问题：投资/利润频率不足、化肥项目上限的 26 个观测、价格/工资仍是临时安全阀、政府/MMT 模块未实现。
- 2026-10-25 03:xx：V0.4.2 利润率修正。
  - 根因：生产计划用 skill=1 产能做分母，`produce()` 又乘熟练度 2.0，实际产出约 2×
    目标；煤/铁/钢库存累积到 100–7,000 个月需求，工资/折旧照付、收入卖不出去。
  - 修复：计划分母改为 `capacity_at_skill_one × 平均熟练度`；必需品固定 0.1 下限
    改为需求感知（库存 >12 月需求时 2% 涓流，否则 0.9×当前需求）。
  - 服务自雇不再领工资（避免与 payout 重复）；利润率改为非 household 资本主义
    企业口径，新增 `all_profit_rate`/`household_profit`/`capitalist_capital_stock`。
  - 240 月 seed=1：古典 1092 存活/8 死亡/失业 10.9%/GDP 30,074/投资 7,148/
    利润率 +0.30%；Keynesian 1100/0/0%/33,058/2,143/-0.01%；
    MMT 1100/0/0%/35,014/1,126/+0.01%。65 测试通过。
  - 剩余：铁/机械/砖 30–500 个月需求库存、建筑 8–19 个零产出月、古典 8 例死亡。

- 2026-10-24 23:xx：L5 与政府/MMT 首版完成。
  - 跳槽阈值修正为 `best_offer > current_wage × (1+6%)`；工资曲线加入失业率项；
    精确用工替换 1.33× 冗余；古典工资下限 0.9×，Keynesian/MMT 1.0×。
  - `Government`/`PolicyRegime`/`MoneyRegime` + `ScenarioConfig` + CLI `--regime`。
  - 三种制度：classical 无政府/金本位；keynesian 税收/UI/公共投资/债券；mmt 央行/就业保障。
  - 粮食平准库存 600 吨、就业保障工资 30；240 月三种制度都无饥荒。
  - 新增 `tests/test_government.py` 5 个；总计 31 个测试全绿。
  - 240 月对比：古典失业 39.3%、Keynesian 41.9%（UI 支持收入但不创造就业）、
    MMT 0.0%（就业保障 476 人，央行货币 3.7M）。这是首版校准，不是历史定论。

## 4.1 下一步（按顺序）

1. 写 ADR：历史阶段 + 政策/货币/价格制度开关（classical / keynesian / mmt）。**已完成：`docs/decisions/0004-historical-regimes.md`**
2. 实现 `src/ecosim/government.py`：税收、失业救济、公共投资、债券；MMT 模式加央行/最后雇主。**已完成首版**
3. 场景配置：把 regime 作为 `ScenarioConfig` 字段，不复制整套场景。**已完成**
4. 测试：classical 无 UI、keynesian 有 UI/公共投资、MMT 有就业保障；需求冲击下对比失业/产出。**已完成 `tests/test_government.py`**
5. 再做 L2 价格 markup/软走廊、L5 工资曲线；替换临时安全阀。
6. 最后同步 `web/engine-preview.html`，重新生成 golden。

### 4.2 政府/MMT 首版实测（seed=1，240 月，L5 后）

| 指标 | 古典 | Keynesian | MMT |
|---|---:|---:|---:|
| 存活 | 1098 | 1100 | 1100 |
| 累计死亡 | 2 | 0 | 0 |
| 期末失业率 | 43.2% | 16.9% | 0.0% |
| 就业保障人数 | 0 | 0 | 452 |
| 政府债务 | 0 | 746,244 | 4,188,688 |
| 央行货币 | 0 | 0 | 4,188,688 |
| 货币总量 | 5,937,000 | 5,947,000 | 10,125,688 |
| GDP | 12,563 | 17,467 | 15,257 |
| 期末投资 | 0 | 0 | 706 |
| 利润率 | -0.08% | -0.20% | -0.01% |
| 钢/砖/机械零产出月 | 0/0/0 | 0/0/0 | 0/0/0 |

说明：
- `classical` 的工资下限为 0.9×制度生存线（更接近 pre-Keynesian 的弹性工资）；
  Keynesian/MMT 保持 1.0× 最低工资。
- Keynesian 启用银行中介 + UI + 公共投资，失业率从 41.9% 降到 16.9%；
  MMT 再用就业保障把失业率压到 0，代价是央行货币/政府债务上升（4.19M）。
  这是首版校准结果，不是历史定论。
- 三种制度都保留了粮食平准库存（初始 600 吨）和食品价格安全阀，240 月无饥荒。
- 核心行业零产出已消失；剩余问题是投资/利润频率、化肥间歇性停摆、Keynesian
  结构性失业，以及 L2 价格 markup/软走廊尚未替换当前价格带。

CLI：
```powershell
$env:PYTHONPATH = "src"
python -m ecosim --months 240 --seed 1 --regime classical
python -m ecosim --months 240 --seed 1 --regime keynesian
python -m ecosim --months 240 --seed 1 --regime mmt
```

### 4.3 当前剩余问题

- 投资/利润频率仍偏低；L5 已完成首版，L2 只完成了 `price_regime="markup"`
  的实验分支。实测 markup 在固定篮子需求下会崩溃（240 月只剩 3–9 人），
  因为降价不能带来足够的需求增量；因此默认仍是 `band`。必须先上 LES/需求弹性，
  再切换 markup。这是 L2 的下一步。
- 价格/工资仍是临时安全阀（2×/4× 价格带、工资 5× 上限、粮食储备）。
- LES 需求分支（`demand_regime="les"`）已实现，但首版校准仍会造成饥荒：
  240 月古典存活 1015、MMT 904；固定篮子（`fixed`）仍是默认。markup + LES
  也仍会崩溃。L2 要做的是重新校准 LES 的 gamma/beta/预算规则，并与 markup
  一起做冲击测试，而不是直接切默认。
- 化肥零产出 19–49 个月（不同制度），需要 L4/化肥周转资金或更低化肥价格。
- Keynesian 240 月期末失业仍高（结构性农业/劳动配置），需要更强的公共投资/UI 校准。
- MMT 首版央行与财政部合并记账，没有完整国债/准备金/银行资本。
- 粮食储备是临时稳定器；没有进口/出口/完整农业贸易。
- `web/engine-preview.html` 仍是旧引擎的忠实移植，Python 稳定后再同步。

## 5. 交接说明

- 关键文件：`src/ecosim/engine.py`、`models.py`、`production.py`、`decisions.py`、`market.py`、`land.py`、`config.py`、`scenarios.py`、`tests/`。
- 先跑：`PYTHONPATH=src python -m unittest discover -s tests -v`。
- 基线：`PYTHONPATH=src python -m ecosim --months 240 --seed 1 --json artifacts/baseline.json`。
- 不要修改 `web/engine-preview.html`，直到 Python 稳定。
- 不提交 git commit（用户未要求）；所有改动留在工作区，文档记录 diff 摘要。

## 6. 本次会话交付摘要（供用户醒来查看）

### 已完成

- Phase 0 会计修正：设备折旧、COGS、项目库存、破产核销、死亡自耕农遗产、
  资产池、零产出告警、stats 扩展。
- Phase 1 负反馈：L1 生产—库存—订单闭环、手工 t0 重启、替换投资、
  农业项目配额、化肥在建造上限、需求约束 ROI、壳企业清理。
- 生活标准修正：小康 = 1.5× 三项 + 积蓄，避免温饱误判导致食品需求瞬间 +50%。
- 价格/工资安全阀：价格带 2×/4× 初始价、工资 5× 上限、粮食平准库存 600 吨。
- L5：工资曲线、精确雇佣/解雇、跳槽阈值方向修正。
- 历史阶段/政府模块：classical / keynesian / mmt；税收、UI、公共投资、债券、
  央行货币创造、就业保障；CLI `--regime`；`scripts/compare_regimes.py`。
- 文档：`03_架构设计文档.md` 第 18 节、`04_开发日志文档.md` V0.4.0、
  `docs/decisions/0004-historical-regimes.md`、本文件。
- 测试：32 个全绿（含 `tests/test_feedback.py` 10 个、`tests/test_government.py` 5 个）。

### 当前 240 月结果（seed=1）

| 制度 | 存活 | 死亡 | 失业率 | GDP | 投资 | 利润率 | 债务 | 央行货币 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| classical | 1098 | 2 | 43.2% | 12,563 | 0 | -0.08% | 0 | 0 |
| keynesian | 1100 | 0 | 41.9% | 25,348 | 9,487 | +0.13% | 362,724 | 0 |
| mmt | 1100 | 0 | 0.0% | 18,479 | 694 | +0.06% | 3,709,211 | 3,709,211 |

核心行业零产出：钢/砖/机械 0 个月；纺织 0–4；建筑 3–7。

### 怎么运行

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m ecosim --months 240 --seed 1 --regime classical
python -m ecosim --months 240 --seed 1 --regime keynesian
python -m ecosim --months 240 --seed 1 --regime mmt
python scripts/compare_regimes.py --months 240 --seed 1 --json artifacts/regimes_240.json
```

### 已知限制（下一轮优先级）

1. 失业率偏高：9 行业模型缺少服务业/非正规部门；Keynesian 的 UI 支持收入但不创造就业。
2. L2 markup/LES 仍是实验分支；固定篮子 + 价格带是默认，否则会崩溃/饥荒。
3. 化肥已改为按潜在需求启动，首次使用提前到古典 T20 / MMT T36；
   仍偏晚，需要周转资金/价格校准。
4. 投资/利润频率偏低，长期接近零利润稳态。
5. MMT 首版央行与财政部合并记账，没有完整国债/准备金/银行资本。
6. `web/engine-preview.html` 仍是 V0.3.2 引擎的忠实移植，尚未同步 V0.4。
7. 未提交 git commit；工作区有 13 个修改文件 + 7 个新文件。
