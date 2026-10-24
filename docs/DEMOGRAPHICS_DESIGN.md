# 人口、代际、退休金与百年仿真设计（V0.5 草案）

> 目标：让任意历史阶段剧本都能跑 100 年（1200 月），人口有年龄结构、出生/死亡、
> 代际更替、退休与养老金；现代剧本有养老金制度和供养比。
> 本文件先记录设计决策；参数待 `docs/DEMOGRAPHICS_RESEARCH.md` 的研究结果校准。

## 1. 范围

**做**：

- 个体年龄（月）、性别、儿童/劳动年龄/退休状态；
- 出生、儿童成长、成年进入劳动力、退休、年龄别死亡；
- 儿童消费/再生产成本（家庭预算）；
- 养老金现收现付（PAYG）+ 缴费率 + 替代率 + 供养比；
- 1200 月仿真；不同剧本的人口/退休金参数；
- 统计与驾驶舱：人口金字塔、出生/死亡、抚养比、养老金收支。

**暂不做**：

- 个体婚姻/配偶匹配、生育意愿的微观博弈；
- 教育/技能代际传递（先只保留熟练度成长）；
- 完整遗产/继承（资本家先按“王朝”处理，或死亡时现金入银行）；
- 移民、城市化、年龄别医疗支出；
- 精确的养老金精算模型（先做 PAYG 现金流）。

## 2. 数据模型

在 `Worker` 上增加：

| 字段 | 含义 |
|---|---|
| `age_months` | 年龄（月） |
| `sex` | `"F"` / `"M"`（生育用） |
| `is_child` | 未满劳动年龄 |
| `retired` | 已退休 |
| `parent_id` | 母亲/监护人 ID（儿童用） |
| `children_ids` | 子女 ID 列表（育龄女性/家庭用） |
| `pension_income` | 上月养老金 |
| `birth_tick` | 出生月份 |

- 儿童/退休者仍放在 `self.workers` 字典里（统一人口账本），但：
  - `_labor_market` 只处理 `not is_child and not retired and not is_owner_operator`；
  - `enterprise.workers` 只包含在业成年人；
  - `Worker.employed` 仍由 `employer_id` 判断；儿童/退休者恒为 None；
  - `_consume_and_demographics` 处理所有存活人口；
  - `_record_stats` 的 `alive` 改为总人口，新增 `labor_force`、`children`、
    `retired`、`dependency_ratio`。
- `Capitalist` 暂不加年龄；如果时间允许，再按“王朝”处理死亡/继承。

## 3. 月度循环插入点

在现有 `step()` 中新增：

1. `_update_skills()` 后、`_update_expectations_and_plans()` 前：
   - `_demography_pre()`：年龄 +1 月、儿童转劳动年龄、退休、死亡（年龄别）、
     清理死亡者的家庭关系；
2. 劳动市场前：育龄女性生育、儿童加入人口；新生儿的家庭关系；
3. `_submit_household_orders()` 前：家庭把儿童消费预算转给儿童（或合并到
   家长篮子）；养老金在 `_government_settlement()` 发放；
4. `_consume_and_demographics()`：所有人口消费、饥饿/死亡、生活标准；
5. `_record_stats()`：人口结构、出生/死亡、抚养比、养老金。

顺序原则：**先 aging/死亡/退休，再生育/劳动市场，再消费**；死亡者不参与
当月劳动和消费。

## 4. 出生与儿童

- 育龄女性：`fertility_age_min..max`（建议 20–40 岁），每月生育概率
  `p_birth = base_fertility * fertility_multiplier(scenario) * income_factor
  * parity_factor * food_security_factor`。
- `base_fertility` 用“每名育龄女性每月概率”；年化总和生育率 TFR 与月概率
  的近似：`TFR ≈ p_birth * 12 * fertile_years`（fertile_years≈20）。
  - 替代水平 TFR≈2.1 ⇒ p_birth≈0.0088/月；
  - 高生育 TFR≈5 ⇒ p_birth≈0.021/月；
  - 低生育 TFR≈1.2 ⇒ p_birth≈0.005/月。
- 收入/生活标准因子：`clamp(0.5, 1.5, 0.7 + 0.3 * living_standard_score)`；
  饥荒/生存状态降低生育。
- 生育后：创建 `Worker(is_child=True, age_months=0, sex=random, parent_id=mother.id,
  cash=0, food=0, cloth=0, housing=0, skill=0)`；加入 `self.workers` 与
  `mother.children_ids`。
- **再生产成本**：儿童每月消费篮子（建议：食品 0.05 吨、衣物 0.5 件、
  住房 0.1 平米；成年人的 50%），由家长支付：
  - 方案 A（推荐）：家长在 `_submit_household_orders` 中把儿童预算以现金
    转移给儿童（`child_allowance`），儿童自己挂买单；货币守恒、儿童有独立
    消费/饥饿记录。
  - 方案 B：家长篮子合并儿童消费，儿童不独立挂单；实现简单但儿童死亡/统计
    不独立。
  - 采用 A；家长现金不足时按比例转移，儿童可能饥饿/死亡。
- 儿童成长：`age_months >= working_age_months` → `is_child=False`，
  `skill=1.0`，`industry=parent.industry`（或 SERVICE），进入劳动市场；
  不再领儿童 allowance，开始自己找工作/自雇。
- 儿童死亡：年龄别死亡率 + 饥饿；死亡后从 `parent.children_ids` 移除，
  现金入银行。

## 5. 死亡与寿命

- 年龄别月度死亡概率：Gompertz 近似
  `q(age) = q0 + exp((age_years - m)/b) / 12`，或分段表。
- 婴幼儿死亡率单独设 `infant_mortality`；老年上限 `max_age`。
- 饥饿死亡保留现有逻辑，叠加年龄死亡；两者都消耗同一 seeded RNG，保持确定性。
- 参数建议（待研究校准）：
  - 古典：预期寿命 40–50，婴儿死亡率高；
  - Keynesian/MMT：预期寿命 75–80；
  - 晚期资本主义：预期寿命 82–85，低婴儿死亡率。
- 死亡者现金入银行；企业所有者死亡按现有 `_settle_estate`/破产逻辑；
  儿童/退休者死亡只清家庭关系。

## 6. 退休与养老金

- `retirement_age_months`：0 表示不退休（古典）；现代 65/67 岁。
- 到龄：从企业 `workers` 移除，`employed=False`，`retired=True`，`wage=0`。
- 养老金（PAYG）：
  - 政府向在业工人/企业征收 `pension_tax_rate`（工资税）；
  - 退休者每月领取 `pension_replacement * average_wage`（或按退休前工资，
    先简化用平均工资）；
  - 养老金基金 `pension_fund`；不足时政府发债/央行融资（复用
    `_government_finance`）；古典无养老金。
- 指标：
  - `dependency_ratio = retirees / employed`（或 (children+retirees)/employed）；
  - `pension_revenue`、`pension_spending`、`pension_balance`、
    `pension_fund`；
  - `retirees`、`children`、`working_age_population`、`labor_force`。
- 现代剧本参数建议：缴费率 8–15%，替代率 40–60%，退休 65–67。
- 古典：无养老金，退休者靠储蓄/子女；如果完全没有收入，会贫困/死亡。

## 7. 剧本参数（草案）

| 参数 | classical | keynesian | mmt | late_capitalism |
|---|---:|---:|---:|---:|
| 月生育概率（育龄女性） | 0.020 | 0.012 | 0.012 | 0.006 |
| 劳动年龄 | 14 | 16 | 16 | 18 |
| 退休年龄 | — | 65 | 65 | 67 |
| 预期寿命（年） | 45 | 75 | 76 | 84 |
| 婴儿死亡率/月 | 高 | 低 | 低 | 极低 |
| 养老金替代率 | 0 | 0.45 | 0.50 | 0.55 |
| 养老金缴费率 | 0 | 0.10 | 0.12 | 0.16 |
| 儿童食品/月 | 0.05 | 0.05 | 0.05 | 0.04 |
| 儿童衣物/月 | 0.5 | 0.5 | 0.5 | 0.4 |
| 儿童住房/月 | 0.1 | 0.1 | 0.1 | 0.08 |

参数只是起点，必须用 1200 月仿真校准到人口不爆炸/不灭绝、养老金可解释。

## 8. 统计与 UI

新增 stats：

- `population`（总人口）、`children`、`working_age`、`retirees`、
  `labor_force`、`employed`、`unemployed`、`births`、`deaths`、
  `death_rate`、`birth_rate`、`dependency_ratio`；
- `age_histogram`（0–4,5–9,...85+ 或单岁）；
- `pension_revenue/spending/balance/fund`；
- `average_age`、`median_age`。

驾驶舱新增 “人口与代际” 面板：人口金字塔、出生/死亡、抚养比、
养老金收支/基金；时间轴支持 1200 月；与现有总览同一份 stats。

## 9. 测试

- 单测：儿童出生、成年转工人、退休、养老金缴费/发放、死亡清家庭关系；
- 240/600 月：人口不为 0、不爆炸；劳动年龄人口/退休人口合理；
- 1200 月：三/四剧本人口存活；货币守恒（金本位）；
- 养老金恒等式：`pension_fund_t = pension_fund_{t-1} + revenue - spending`；
- 确定性：同 seed 人口/出生/死亡序列一致；
- 现有 65 测试全部通过。

## 10. 主要风险

1. **人口爆炸/灭绝**：生育率/死亡率参数必须校准；用 TFR 目标反推月概率。
2. **儿童消费与货币守恒**：allowance 是转移，不能创造货币；儿童死亡现金入银行。
3. **养老金赤字**：PAYG 在老龄化下会赤字；需要显式债务/央行融资，不能静默透支。
4. **劳动参与率定义**：儿童/退休者不能算失业；失业率分母改为劳动年龄劳动人口。
5. **死亡随机流**：新增年龄死亡会改变现有固定 seed 的死亡序列；现有 240 月
   测试/结果会变化，需要重新基线。
6. **性能**：1200 月 × 更多人口；需要避免 O(n²) 家庭遍历；用 ID 列表。

## 11. 待研究确认

- OLG/人口 ABM 的标准年龄别死亡率/生育率函数与参数；
- 养老金 PAYG 的典型缴费率/替代率/退休年龄；
- 儿童再生产成本占家庭收入的比例；
- 历史剧本（前工业化/古典/Keynesian/MMT/晚期资本主义）的史实参数。
