# 人口/代际/退休金外部研究摘要（V0.5）

> 来源：研究代理的 WebSearch/WebFetch 结果；标注“已核实”的是书目/API/公开摘要，
> 未逐页读全文的地方标注“未核实”。用于校准参数，不是代码契约。

## 1. 结构选择

- **推荐**：个体 agent + Household 容器。Worker/Capitalist 加 `age_months`、
  `sex`、`household_id`、`retired`、`pension`；生育、照护、缴费、遗产需要个体/家庭。
- 聚合年龄队列只用于初始化/统计；1100 人规模下个体成本可接受。
- EcoSim 当前实现采用 `parent_id`/`children_ids` 的个体方案（不建完整 Household），
  是同一方向的简化。

## 2. 生育

- 年龄别生育率 ASFR：峰值 25–29 岁约 **0.09–0.13/年**；月概率 `p_a≈ASFR_a/12`。
- 经济/食品乘数：`m=clip((y/y0)^0.1·(food/food0)^0.3, 0.3, 1.5)`；
  `p=min(0.2, p_a·m)`；月度 Bernoulli。
- TFR = ΣASFR；目标：
  - 古典 5–6（高生育）；
  - Keynesian 2.4–3.0；
  - MMT 1.8–2.1；
  - 晚期资本主义 1.2–1.6（低于替代）。
- 可选 9 个月怀孕；首版可不做。

## 3. 死亡

- Gompertz：`μ(a)=A+B·e^(C·a)`（年），月概率 `q≈1−e^(−μ/12)`。
- 现代：`A=3e−4, B=4.5e−5, C=0.09`（e0≈80）；
- 古典：`A=1.5e−3, B=1e−4, C=0.085`（e0≈40）；
- 婴儿年死亡率：现代 0.004–0.006，古典 0.15–0.25。
- 与饥饿联合：`q=1−(1−q_age)(1−q_hunger)`，不要相加或重复抽。
- 建议独立 `demographic_rng`，避免改变现有饥饿死亡随机流。

## 4. 养老金

- PAYG：月养老金 = `ρ × 社会平均工资`；`d=退休/在职`；
  `τ≈ρ·d + 赤字/工资总额`。
- 典型参数：
  - Keynesian：ρ 40–50%，τ 12–18%，R 65；
  - MMT：ρ 50–60%，τ 15–20%，R 65；
  - 晚期资本主义：ρ 30–50%，τ 15–24%，R 66–67；
  - 古典：无国家养老金（家庭/教会救济，模型中可无）。
- 账本：缴费/发放是现金转移；金本位不足时发债，MMT 才可央行货币；
  不能静默创造货币。

## 5. 儿童/再生产成本

- OECD 修正尺度：儿童约 **0.3 成人消费**（草案 0.5 可下调）。
- 出生一次性成本 1–3 个月成人消费（可选）。
- 照护时间 0–3 岁约 0.2–0.5 FTE（首版可不做）。
- 儿童消费从家庭共享现金扣减并进入市场需求；货币守恒。
- 家庭等值规模：单身 1.0、夫妻 1.5、单亲+1 孩 1.3（可后续）。

## 6. 剧本参数（研究建议）

| 剧本 | TFR | e0 | 退休 R | 替代率 ρ | 缴费率 τ | 儿童系数 | 成年 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 古典 | 5–6 | 35–45 | 无 | 0 | 0 | 0.25–0.35 | 14–16 |
| Keynesian | 2.4–3.0 | 68–72 | 65 | 40–50% | 12–18% | 0.3 | 18 |
| MMT | 1.8–2.1 | 75–78 | 65 | 50–60% | 15–20% | 0.3 | 18 |
| 晚期资本主义 | 1.2–1.6 | 80–84 | 66–67 | 30–50% | 15–24% | 0.3–0.4 | 18–22 |

## 7. 来源

1. Diamond (1965), *National Debt in a Neoclassical Growth Model*, AER 55(5):
   1126–1150. JSTOR 1809231. 书目已核实，全文未读。
   <https://www.jstor.org/stable/1809231>
2. Aparicio Díaz et al. (2011), *Transition to Parenthood: The Role of
   Social Interaction*, Demography 48(2):559–579.
   DOI 10.1007/s13524-011-0023-6（Crossref 已核实）。
   <https://doi.org/10.1007/s13524-011-0023-6>
3. Bacelar & Antunes (2019), *The role of social security in the
   political economy of pensions*, arXiv:1909.08706（元数据已核实）。
   <https://arxiv.org/abs/1909.08706>
4. Deissenberg et al. (2008), EURACE, DOI 10.1016/j.amc.2008.05.116；
   EURACE 固定 1600 户（RAL-TR-2012-006）；
   JAMEL 的“家庭永不消失、无年龄/死亡”见 HAL halshs-00697225。
   <https://epubs.stfc.ac.uk/manifestation/7678/RAL-TR-2012-006.pdf>
   <https://shs.hal.science/halshs-00697225>
5. UN World Population Prospects 2024（TFR 2.25、e0 73.3）；
   World Bank API（HIC TFR 1.42、e0 80.4、OADR 30.3、IMR 4.2）；
   OECD Pensions at a Glance 2023（ρ 50.7%、τ 18.2%、R 64.4→66.3），
   官方摘要已核实，全文未直读。
   <https://population.un.org/wpp/>
   <https://data.worldbank.org/>
   <https://doi.org/10.1787/678055dd-en>

## 8. 实施建议与风险

1. 初始化用稳定人口年龄分布，不要全 0；儿童/退休者参数开关。
2. 生育/死亡/性别用独立 `demographic_rng`；饥饿死亡保留 `self.rng`。
3. 养老金有显式 `pension_fund`/`pension_revenue`/`pension_spending`，
   并进入政府赤字恒等式或独立基金恒等式。
4. 劳动参与率分母排除儿童/退休者；死亡清理雇主/家庭/遗产。
5. 1200 月后检查人口不灭绝/不爆炸；TFR/e0 与剧本匹配。
