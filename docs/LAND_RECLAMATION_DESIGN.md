# 土地开垦与 estate 再分配设计（V0.6 候选）

> 需求依据：`02_需求定义文档.md` 2.3.2：
> “土地为初始自然资源；可由农机/人力扩张”。
> 现状：**未实现**。`TOTAL_LAND_MU = 6000` 固定，600 自耕农 ×10 亩一次
> 分完；`LandMarket` 只做存量转手；农机只提高人均可管理亩数；不变量测试
> 断言土地总量恒等于 6000。长程古典/Keynesian 的剩余饥荒、`estate_land`
> 闲置和价格信号无法带来新供给，都与此有关。

## 1. 目标

- 土地是**可扩张的生产资源**：劳动/农机/投资可以把荒地开垦为耕地；
- 开垦由预期粮价/利润驱动，形成“短缺 → 高价 → 开垦 → 供给增加”的负反馈；
- `estate_land` 可以通过拍卖/再分配重新进入生产，而不是永久闲置；
- 保持会计守恒：总土地资源 = 已耕地 + 可开垦荒地 + estate + 资产池；
- 不同剧本有不同的可开垦上限（铁器时代/古典有边疆，晚期资本主义受土地/环境约束）。

## 2. 数据模型

`LandMarket` 增加：

| 字段 | 含义 |
|---|---|
| `wild_land` | 可开垦荒地（亩） |
| `cultivated_land` | 已耕地（= smallholder + capitalist + household enterprise land） |
| `estate_land` | 死亡/退出农场的待处置土地（已有，需拍卖/再分配） |
| `asset_pool.land` | 资产池土地（已有） |
| `total_land_resource` | `wild_land + cultivated_land + estate_land + asset_pool.land` |

- `TOTAL_LAND_MU` 改名/扩展为 `TOTAL_LAND_RESOURCE`（例如 12000 亩，
  其中 6000 已耕地 + 6000 可开垦），或按剧本配置
  `initial_wild_land` / `max_cultivable_land`。
- 土地质量/边际成本：可开垦地按质量分档（好地先开、边际地成本更高）；
  简化实现可用 `reclamation_cost = base_cost * (1 + k * (cultivated/total))`
  或分段成本曲线。
- 已耕地仍按 `owners`/`enterprise.land` 记账；`smallholder_land` 属性不变。

## 3. 开垦机制

### 3.1 自耕农开垦（P1）

- 无地/少地成年劳动者可用劳动开垦小块荒地（例如 5–10 亩/次），
  消耗时间（1–3 个月）、工具/现金；期间不能从事其他工作或减少工时。
- 新开垦地成为家庭农场（`is_household=True`），所有者 `wage=0`、
  经营所得走 `_finance` payout（与现有家庭农场一致）。
- 触发：无地 + 预期粮价/亩产收益 > 开垦成本；或者有政策补贴时。
- 限制：每月开垦人数/面积上限，避免一次性土地冲击。

### 3.2 资本主义农场开垦（P2）

- 新增农业投资项目 `reclamation`：投入现金/劳动/设备/时间，把
  `wild_land` 转为 `enterprise.land`；项目完成前土地仍在 wild_land。
- ROI 与 `agricultural_entry_roi`/预期粮价挂钩；高价/短缺时进入。
- 开垦成本随已耕地比例上升（边际地更贵）；可设置最大可开垦比例。
- 与现有 `ProjectQueue`/`best_equipment_choice` 复用；农业项目配额仍适用。

### 3.3 estate 拍卖/再分配（P3）

- `estate_land` 进入土地市场供给（拍卖给资本主义农场/新进入者），
  或按政策分配给无地劳动者（古典/土改简化）。
- 拍卖收入进入银行/政府/资产池（无主遗产），货币守恒。
- 与现有继承/无地承接互补：有继承人时先继承；无继承人时拍卖/分配，
  而不是直接沉入 estate。

## 4. 价格与需求信号

- 粮价高 → 农业 ROI 高 → 资本主义农场开垦/进入；自耕农开垦机会成本下降。
- 粮价低 → 开垦停止，边际地退出（可选项：撂荒/土地退化，先不做）。
- 与 `price_regime="guidance"` 配合：指导价上涨应能触发真实开垦，
  而不是只压缩需求；这是验证 guidance 供给响应的关键。
- 土地价格 `land.price` 反映已耕地稀缺性；wild_land 价格/开垦成本分开。

## 5. 会计与守恒

- 开垦是**资源转换**：`wild_land -= mu`，`enterprise.land += mu`
  （或 `land.owners[worker] += mu`），总资源不变。
- 开垦支出：现金从投资者/农场/政府流向劳动/设备/材料；不创造货币。
- 土地是资产、不计折旧（沿用 V0.4 规则）。
- 不变量测试改为 `wild + cultivated + estate + asset_pool = TOTAL_LAND_RESOURCE`。
- `capitalist_land` 属性需修正：当前是 `total_land - smallholder_land`，
  把 estate/资产池也算进“资本主义土地”，应改为实际企业土地之和。

## 6. 统计与 UI

新增 stats：

- `wild_land`、`cultivated_land`、`reclaimed_land_this_month`、
  `reclamation_projects`、`estate_land`、`asset_pool_land`；
- `land_price`、`reclamation_cost`、`agricultural_land`；
- 驾驶舱人口/农业面板增加“已耕地/可开垦/开垦中/地价”。

## 7. 测试

- 总资源守恒：每月 `wild + cultivated + estate + asset_pool = total`；
- 高价/短缺时出现开垦；低价/无利可图时不开垦；
- 开垦项目完成前不增加耕地；完成后耕地增加、wild 减少；
- estate 拍卖/分配后 estate 下降、耕地/农场增加；拍卖收入守恒；
- 240/600/1200 月古典：开垦是否降低饥荒、提高粮食产量；
- 不破坏现有 95 tests；`validate_v05` 增加 wild/cultivated/estate 指标。

## 8. 剧本参数

| 参数 | IRON_AGE/CLASSICAL | KEYNESIAN/MMT | LATE_CAPITALISM |
|---|---:|---:|---:|
| 初始已耕地 | 6000 亩 | 6000 亩 | 6000 亩 |
| 初始可开垦荒地 | 6000–12000 亩 | 3000–6000 亩 | 500–1500 亩 |
| 开垦成本 | 低（人力为主） | 中（机械/化肥） | 高（土地/环境约束） |
| 开垦上限 | 高 | 中 | 低 |

## 9. 风险与限制

- 荒地无限/开垦成本过低会导致无限扩张和生态外溢；需要上限/成本曲线。
- 土地质量、灌溉、 deforestation、城市化暂不建模；先用边际成本近似。
- 开垦与农机 2^N 的关系：农机提高人均管理面积，开垦增加总面积，两者独立。
- estate 拍卖可能把土地集中到资本主义农场，需观察小农/就业/粮食结构。
- 开垦项目会增加投资需求，需与信贷/利率/价格制度一起校准。

## 10. 实施顺序

1. P1：`wild_land` 池 + 自耕农开垦 + 总资源守恒测试；
2. P2：资本主义农场开垦项目 + ROI/价格信号；
3. P3：estate 拍卖/无地分配 + 收入归属；
4. P4：UI/统计 + 240/600/1200 月校准 + 与 guidance 组合测试。

完成后再评估 1200 月古典/Keynesian 的剩余饥荒是否消失，以及
`guidance` 是否能通过开垦形成真正的供给响应。
