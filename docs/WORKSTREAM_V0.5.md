# V0.5 工作流：人口、代际、退休金与百年仿真

> 基线：V0.4.2（`v0.4-integration`，利润率为正/接近零，65 测试）。
> 本文件记录 V0.5 的任务分解、状态和交接；详细设计见
> `docs/DEMOGRAPHICS_DESIGN.md`、`docs/DEMOGRAPHICS_RESEARCH.md`、
> `docs/DEMOGRAPHICS_UI_SPEC.md`、`docs/SCENARIOS_ROADMAP.md`。

## 目标

让任意历史阶段剧本可跑 100 年（1200 月），人口有年龄结构、出生/死亡、
代际更替、退休与养老金；现代剧本有 PAYG 养老金、缴费率、替代率、供养比；
并提供至少铁器时代/古典/Keynesian/MMT/晚期资本主义剧本。

## 阶段

| 阶段 | 内容 | 状态 |
|---|---|---|
| D1 | 人口核心：年龄/性别/儿童/退休/出生/死亡/养老金/统计/测试 | **已完成**：`feature/demography` `263e99f` + `fix/demography-safety` `f797b37` + `fix/household-farm-income` `035c97f`；主线 `365aa93`/`7429a3b`/`0e15fad`；95 tests |
| D2 | 驾驶舱人口面板：人口金字塔、出生/死亡、抚养比、养老金 | **已完成** `3833c23`：KPI/金字塔/出生死亡/抚养比/养老金/对比列；截图 `web/screenshots/v05-demography-*.png` |
| D3 | 剧本：IRON_AGE、LATE_CAPITALISM、可选 NEOLIBERAL | `LATE_CAPITALISM` 已完成；IRON_AGE/NEOLIBERAL 待做 |
| D4 | 信贷冲击稳定器：LLR/贴现窗口、wage_arrears、食品券、冻结规则 | 设计完成（`docs/CREDIT_BACKSTOP_DESIGN.md`）；实现待做 |
| D5 | 1200 月验证：人口不灭绝/不爆炸、养老金可持续、20 seeds 抽样 | 脚本已就绪；seed=1 已跑：MMT/晚期通过，古典/Keynesian 仍有长程饥荒 |
| D6 | 单文件 HTML 发行版同步 V0.5 | 待 D5 |

## D1 验收

- `Worker` 有 `age_months/sex/is_child/retired/parent_id/children_ids/
  pension_income`；
- 初期年龄分布合理；儿童成年进入劳动市场；雇员退休；年龄死亡与饥饿死亡
  联合；生育用独立 `demographic_rng`；
- 儿童 allowance 是现金转移，货币守恒；
- 养老金 PAYG 显式记账，金本位不造币；
- stats：population/children/working_age/retirees/labor_force/employed/
  unemployed/births/deaths/dependency_ratio/age_histogram/pension_*；
- 65 旧测试 + 新测试通过；240/600 月稳定；1200 月每制度至少一次冒烟。

## D1 结果（v0.5.1，seed=1）

240 月（`scripts/validate_v05.py --months 240`，四剧本全部 `ok`，
家庭农场剩余收入修复后）：

| 制度 | 人口 | 饥饿死亡 | 粮食产出/需求（吨/月） | 利润率 | 养老金基金 |
|---|---:|---:|---:|---:|---:|
| classical | 1666 | 0 | 175.3 / 158.4 | -0.096% | 0 |
| keynesian | 1640 | 0 | 158.4 / 161.7 | +0.186% | 126,793 |
| mmt | 1601 | 0 | 146.2 / 156.4 | +0.030% | 207,800 |
| late_capitalism | 1311 | 0 | 134.6 / 134.4 | -0.244% | 23,410 |

1200 月（`--months 1200`，家庭农场修复后）：

| 制度 | 人口 | 累计饥饿死亡 | 家庭农场（清算） | estate_land | 结论 |
|---|---:|---:|---:|---:|---|
| classical | 755 | 813 | 200（0） | 100 | 仅饥饿项失败 |
| keynesian | 1751 | 0 | 240（0） | 0 | 通过 |
| mmt | 1138 | 0 | 180（0） | 0 | 通过 |
| late_capitalism | 336 | 0 | 295（0） | 220 | 通过 |

- v0.5.1 修复：救济缓冲 1.5 个月、政府融资缺口不再重复扣减、
  PAYG 发薪/经营所得代扣、自耕农到龄养老金、土地继承/无地承接、
  抚养比/孤儿/初始年龄/ASFR 归一化；详见 `docs/DEMOGRAPHICS_DESIGN.md` §12。
- v0.5.2 修复：自耕农所有者按剩余索取者记账，不再借债给自己发工资；
  家庭农场清算 0，estate_land 大规模沉没消除；classical 600/1200 饥饿
  921/974 → 813/813，但仍未消除（324–404 月需求/流动性危机）。
- 已知长程问题：古典剩余饥荒；土地开垦未实现（需求文档要求“可由农机/
  人力扩张”，当前 `TOTAL_LAND_MU` 固定）；长期利润率接近零/负。

## D2 结果（`3833c23`）

- `/api/run` 新增 population/children/working_age/retirees/labor_force/
  employed/births/deaths/抚养比/养老金等标量序列，以及
  `demography.age_histogram` 年龄桶序列；
- 驾驶舱新增 4 张人口 KPI、人口金字塔、出生/死亡、抚养比、养老金收支图；
- 三制度对比表增加人口/抚养比/养老金基金列；版本号 V0.5；
- `tests/test_dashboard.py` 2 个 payload/缺字段测试通过；
- 截图：`web/screenshots/v05-demography-60.png`、
  `v05-demography-keynesian-60.png`、`v05-demography-60-tall.png`。

## D3 剧本草案

- `IRON_AGE`：1000 自耕农、无工业、高生育/高死亡、无养老金、成年 14；
- `CLASSICAL_LAISSEZ_FAIRE`：现有场景 1；
- `KEYNESIAN_WELFARE`：退休 65、PAYG ρ0.45/τ0.10；
- `MMT_SOVEREIGN`：退休 65、PAYG ρ0.50/τ0.12 + JG；
- `LATE_CAPITALISM`：低生育、长寿、退休 67、ρ0.55/τ0.16、资本集中；
- `NEOLIBERAL`（可选）：低税/低 UI、高不平等、养老金多支柱。

## D4 信贷冲击稳定器

- 最后贷款人/贴现窗口：Keynesian/MMT 央行对工资账单/准备金冻结提供流动性；
- `wage_arrears` 显性化：未付工资记负债，下期优先；
- 食品券/定向转移：零现金家庭可购买最低口粮；
- 银行冻结规则：用资本/流动性比率替代 50% 硬冻结。
- 验收：信贷冲击死亡数显著下降，金本位货币守恒，MMT 货币创造显式。

## D5 验证

- 1200 月 × 4–5 剧本；人口 0.8×–3× 初始、不灭绝/不爆炸；
- 养老金 `fund_t = fund_{t-1} + revenue - spending`；
- 依赖比/老年依赖比合理；
- 同 seed 确定；金本位货币守恒；
- 冲击—恢复（需求/生产率/信贷）在人口结构下仍成立。

**当前工具与结果**：

```powershell
python scripts/validate_v05.py --months 1200 --seed 1 --jobs 4
python scripts/validate_v05.py --months 240 --seed 1 --jobs 4
```

- seed=1 结果见 `artifacts/validation_v05/seed1_{240,1200}.json`；
- 家庭农场修复后：240 月四剧本全部通过；1200 月仅 classical 饥饿项失败
  （813 例，集中在 324–404 月）；MMT/Keynesian/晚期通过；
- 养老金恒等式/预算恒等式四剧本通过；金本位货币漂移 <1e-2；
- 待做：20–100 seeds、土地开垦/estate 拍卖、长期负利润与需求结构。

## 风险

- 人口参数未闭合导致爆炸/灭绝；
- 养老金赤字/货币守恒；补贴必须同时进入 `pension_revenue`；
- 儿童/退休者失业口径；自耕农到龄领养老金但不退出经营；
- 生育/死亡独立 RNG 改变旧 golden；
- 1200 月性能（~3–5 分钟/制度），避免同时多进程；
- 资本家未老化（V0.5 限制），100 年财富集中需谨慎解读；
- `estate_land` 无继承/承接人时仍会积累（家庭农场修复后大幅下降，
  但晚期 1200 月仍有约 220 亩）；尚不能开垦新土地；
- 土地开垦未实现：`TOTAL_LAND_MU` 固定，违反“可由农机/人力扩张”的需求；
- 价格指导价 `guidance` 仍为实验（v1 库存/流量错误导致通缩螺旋）；
- 家庭农场修复后古典 1200 月失业约 20.9%，收入分配副作用待校准。
