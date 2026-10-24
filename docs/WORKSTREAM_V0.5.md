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
| D1 | 人口核心：年龄/性别/儿童/退休/出生/死亡/养老金/统计/测试 | 进行中（`feature/demography`） |
| D2 | 驾驶舱人口面板：人口金字塔、出生/死亡、抚养比、养老金 | 待 D1 |
| D3 | 剧本：IRON_AGE、LATE_CAPITALISM、可选 NEOLIBERAL | 待 D1 |
| D4 | 信贷冲击稳定器：LLR/贴现窗口、wage_arrears、食品券、冻结规则 | 待 D1 |
| D5 | 1200 月验证：人口不灭绝/不爆炸、养老金可持续、20 seeds 抽样 | 待 D1–D4 |
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

## 风险

- 人口参数未闭合导致爆炸/灭绝；
- 养老金赤字/货币守恒；
- 儿童/退休者失业口径；
- 生育/死亡独立 RNG 改变旧 golden；
- 1200 月性能（~3 分钟/制度），避免同时多进程；
- 资本家未老化（V0.5 限制），100 年财富集中需谨慎解读。
