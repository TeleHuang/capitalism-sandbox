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
- **再生产成本**：研究建议用 OECD 修正尺度约 **0.3 成人消费**（草案按
  0.25–0.4 校准；食品/衣物/住房分别约 0.03–0.05/0.3–0.5/0.06–0.1），由家长支付：
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
- 饥饿死亡保留现有逻辑，叠加年龄死亡；建议**独立 demographic RNG**
  （`random.Random(seed + 常数)`）处理生育/年龄死亡/性别，`self.rng` 只做饥饿死亡，
  避免新增抽样改变旧固定 seed 的死亡序列。
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

## 11. 研究结论

已由研究代理完成，见 [[DEMOGRAPHICS_RESEARCH.md]]。关键结论：

- 个体 agent + Household 容器；EcoSim 用 `parent_id`/`children_ids` 简化；
- Gompertz 死亡 + ASFR 生育 + 月度 Bernoulli；
- PAYG 养老金 `月养老金=ρ×平均工资`，`τ≈ρd+赤字/工资总额`；
- 儿童 OECD 尺度约 0.3 成人；
- 参数表：古典 TFR 5–6/e0 35–45；Keynesian 2.4–3.0/68–72；
  MMT 1.8–2.1/75–78；晚期资本主义 1.2–1.6/80–84；
- 独立 demographic RNG；养老金显式记账；儿童/退休者退出失业分母。

## 12. 实现状态（v0.5.0）

已实现个体年龄/性别/家庭关系、月度 aging/出生/死亡/退休、儿童 allowance、
PAYG 养老金、人口统计与 `LATE_CAPITALISM` 预设。与草案的偏差：

- **独立人口 RNG**：`Engine.demographic_rng = Random(seed + 1_000_003)`；
  生育/年龄死亡/性别不扰动既有经济 RNG，饥饿死亡仍用 `Engine.rng`。
- **生育**：20–40 岁 ASFR 形状（峰值 25–29）× 收入/食物乘数 × parity；
  名义 `fertility_monthly` 按 TFR 目标设定，但食物/收入乘数会把有效生育率
  压到粮食可持续区间。1200 月人口端点以 `scripts/validate_v05.py` 的输出
  为准（`artifacts/validation_v05/`）；V0.5.1 的救济/养老金/土地修复会
  改变旧端点，不再引用初版一次性数字。
- **死亡**：年化 Gompertz `mu(a)=A+B*exp(C*a)`，月概率
  `1-exp(-mu/12)`；婴幼儿/儿童分段。古典 A=1.5e-3/B=1e-4/C=0.085、
  婴儿年死亡 0.18；现代 A≈3e-4、婴儿年死亡 0.005。
- **养老金会计**：`pension_revenue = pension_contributions + pension_subsidy`，
  `pension_balance = revenue - spending`，基金恒等式成立；补贴来自
  `_government_finance`（金本位发债/MMT 央行），不计入当期 deficit 收入侧。
  养老金不低于当前食品温饱线（`0.1 × 食品价`），避免工资/粮价错位导致
  退休者集体饿死；该下限由基金/财政显式融资。
- **儿童成本**：家长先保留自身全额口粮现金，再按儿童人数等比转移；
  不足时儿童可能饥饿。孤儿 allowance 归零并记录 warning。
- **粮食救济**：粮食平准库存对饥饿家庭直接转移实物（每月最多释放库存的
  25%，最低 10 吨）；库存低于 3 个月需求时从农业产出征收最高 25% 的
  实物救济税。两者都不改变货币总量，是防止纯现金约束造成人口灭绝的
  兜底机制，不是生育硬上限。
- **救济缓冲（v0.5.1 修复）**：粮商高价出售时至少保留
  `FOOD_RELIEF_BUFFER_MONTHS = 1.5` 个月口粮库存。旧实现会把库存卖到 0，
  救济无粮可发：60 月古典/Keynesian/MMT 分别累计 112/63/122 例饥饿死亡；
  保留 1.5 个月缓冲后三个制度均为 0，240 月同样为 0。
- **抚养比口径（v0.5.1 修复）**：`dependency_ratio = (儿童 + 退休者) /
  劳动年龄人口`；`old_age_dependency`、`child_dependency` 使用同一分母。
  旧实现把总抚养比写成 `retirees / employed`，不含儿童且分母不一致。
- **政府融资（v0.5.1 修复）**：`_government_finance(amount)` 的 `amount`
  是调用方已扣除 `gov.cash` 后的缺口；旧实现再减一次 `gov.cash`，在
  `0 < gov.cash < bill` 时会系统性少付 UI/养老金/公共投资。
- **长程验证（v0.5.1）**：新增 `scripts/validate_v05.py`，对四剧本跑
  1200 月，检查人口不灭绝、最后 12 个月仍有出生、累计饥饿死亡为 0、
  金本位货币守恒、养老金基金/预算恒等式。单元测试不再声称替代 1200 月
  验证；1200 月结果由该脚本产出到 `artifacts/validation_v05/`。
- **PAYG 代扣（v0.5.1 修复）**：缴费改为在 `_pay_wages` /
  `_pay_government_wages` 发薪时从毛工资代扣，而不是月末从工人消费后的
  剩余现金征收。旧实现下 Keynesian 的实际缴费约为法定费率的 18%，
  养老金基金长期依赖补贴/新债。
- **自耕农养老金（v0.5.1 修复）**：自耕农/自雇摊主不强制退出经营，但
  到退休年龄后同样领取养老金（他们同样缴费）；`pension_recipients`
  统计所有领取者，`retirees` 仍只统计退出劳动市场的雇员。
- **土地继承/承接（v0.5.1 修复）**：死亡自耕农的家庭农场优先由成年子女
  继承；无子女时分配给无地成年劳动者，避免土地直接沉入 `estate_land`。
  无继承/承接人时仍回 `estate_land`；该部分尚未拍卖，长程古典仍会积累
  闲置土地（600 月约 2,000/6,000 亩），需要下一轮土地市场/拍卖机制。
- **生育归一化（v0.5.1 修复）**：`_fertility_age_shape` 的离散平均权重
  改为 0.9469（旧 0.9143 假设了错误的年龄带宽，使有效生育率偏高约 3.6%）。
- **LATE_CAPITALISM 初始年龄（v0.5.1 修复）**：初始在业劳动人口年龄上限
  封顶在退休年龄以下（67 岁剧本 → 最多 66 岁），避免创建首月才退休的
  老年雇员。
- **已知长程问题（不属于 D1）**：600 月古典仍有经济内核衰退：失业率约
  15–23%、资本主义利润率为负、粮食产量低于需求、`estate_land` 闲置。
  人口模块通过救济缓冲避免了即时饥荒，但价格/需求/土地市场需要后续
  L2/信贷/百年验证轮次处理。
- **限制**：资本家仍按“王朝/不朽”处理，不老化、不死亡；因此 100 年尺度
  的财富集中不能解释为人口/退休金机制的结果。自耕农/自雇摊主不强制退休
  （尚无土地/经营权代际继承），只有雇员/失业劳动年龄人口到龄退休。
