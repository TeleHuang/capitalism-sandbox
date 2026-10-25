"""V0.2 模型的静态校准参数。

所有供给侧数量均为月度值。设备类型的 ``capacity`` 是熟练度 1.0 时的产出；
实际产出再乘以在岗工人的平均熟练度。这样既保留了 PRD 的熟练度成长机制
（1.0 -> 2.0），又不需要硬编码两套生产表。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from .enums import Good, Industry

# ---------------------------------------------------------------------------
# 价格与家庭参数
# ---------------------------------------------------------------------------

INITIAL_PRICES: Dict[Good, float] = {
    Good.FOOD: 100.0,
    Good.COAL: 20.0,
    Good.IRON_ORE: 30.0,
    Good.STEEL: 150.0,
    Good.BRICK: 10.0,
    Good.CLOTH: 1.0,
    Good.FERTILIZER: 50.0,
    Good.MACHINERY: 200.0,
    Good.BUILDING: 10.0,
    Good.SERVICE: 10.0,
}

# 月度温饱篮子（PRD 2.2.1）。
FOOD_PER_WORKER = 0.10          # 吨 / 月
CLOTH_PER_WORKER = 1.0          # 件 / 月
HOUSING_PER_WORKER = 0.20       # 平方米 / 月

# 粮食平准库存必须保留的救济缓冲（月）。高价时只释放缓冲以外的库存；
# 否则会把救济库存卖空，粮食救济机制在饥荒时无粮可发。
# 1.5 个月在 60/240 月四剧本测试中消除饥饿死亡，同时比 2 个月更少
# 扭曲粮食市场（古典资本主义利润率更接近零）；救济税目标仍是 3 个月。
FOOD_RELIEF_BUFFER_MONTHS = 1.5

# 服务业/非正规部门：每户每月的服务消费量。服务是温饱之后的
# 可选消费，家庭在食品/衣物/住房之后用剩余现金购买。
SERVICE_PER_HOUSEHOLD = 0.5     # 单位 / 月
CAPITALIST_SERVICE = 0.75       # 资产阶级按 1.5 倍工人标准消费

COMFORT_MULTIPLIER = 1.5
COMFORT_SAVINGS = 60.0
LEISURE_SAVINGS = 120.0

# 劳动供给：工人从这些工时中选择，工资按工时比例发放。
HOURS_OPTIONS = (16, 12, 8)
DEFAULT_HOURS = 16

# 熟练度成长：在业约五年从 1.0 升到 2.0。
SKILL_MIN = 1.0
SKILL_MAX = 2.0
SKILL_GROWTH_PER_MONTH = 1.0 / 60.0

# 生存：饥饿是多月过程，不是单月掷硬币。
HUNGER_DEATH_AFTER_MONTHS = 3
HUNGER_DEATH_BASE = 0.08
HUNGER_DEATH_STEP = 0.08
HUNGER_DEATH_CAP = 0.50

# 工资 / 劳动市场
WAGE_BASE = 20.0
WAGE_SEARCH_PREMIUM = 0.08
WAGE_SWITCH_THRESHOLD = 0.06
MAX_HIRES_PER_ENTERPRISE_PER_MONTH = 20

# 资产阶级
CAPITALIST_CONSUMPTION_RATE = 0.02   # 每月消费现金比例
CAPITALIST_MIN_CONSUMPTION = 100.0
CAPITALIST_FOOD = 0.15
CAPITALIST_CLOTH = 1.5
CAPITALIST_HOUSING = 0.3

# 投资
INVESTMENT_HURDLE = 0.012            # 最低预期月资本回报率
INVESTMENT_RESERVE_MONTHS = 3.0      # 投资后保留的工资月数
MAX_NEW_FIRMS_PER_TICK = 1
MAX_PROJECTS_PER_TICK = 5
MAX_ACTIVE_PROJECTS = 10
PROJECT_TIMEOUT_MONTHS = 18
DEPRECIATION_MONTHS = 120.0
DIVIDEND_PAYOUT = 0.50

# 服务业自雇：需求未满足时，失业者用零资本的手工服务摊进入。
MAX_SERVICE_ENTRIES_PER_MONTH = 25
SERVICE_ENTRY_MIN_REVENUE = 5.0      # 每单位服务收入低于此值则不再进入
SERVICE_FIRM_RESERVE = 2.0           # 自雇家庭保留的周转现金
# 家庭农场保留的周转现金（元）：覆盖无雇工、无现代化投入的小农的
# 工具/交易摩擦，约为初始营运资金的一半。超出部分作为家庭经营所得
# 在 `_finance` 中支付给自耕农，而不是工资或资本利润。
HOUSEHOLD_FARM_RESERVE = 50.0
SERVICE_IDLE_EXIT_MONTHS = 6         # 连续无销售额月数，退回失业/资产池

# 土地市场
TOTAL_LAND_MU = 6000.0
INITIAL_LAND_PRICE = 100.0          # 元 / 亩
LAND_RESERVATION_PRICE = 150.0      # 自耕农只在此价格以上卖地
LAND_PRICE_STEP = 0.05
LAND_SALES_PER_TICK = 0.02          # 每月最多出售自耕农土地的 2%
MIN_CAPITALIST_FARM_MU = 50.0
TARGET_CAPITALIST_FARM_MU = 100.0

# 参考价试探过程
PRICE_STEP = 0.05
PRICE_FLOOR = 0.01

BANK_CASH = 100_000.0
BANK_INTEREST_RATE = 0.01
BANK_LOAN_MONTHS = 3.0


# ---------------------------------------------------------------------------
# 人口 / 代际 / 退休金（V0.5）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DemographicsConfig:
    """人口过程参数（V0.5）。

    生育用年龄别月概率（ASFR/12，按 20–40 岁形状归一化），
    死亡用年化 Gompertz 力 ``mu(a) = A + B * exp(C * a)``，
    月死亡概率 ``q = 1 - exp(-mu/12)``；婴幼儿/儿童单独分段。
    所有随机决策走 ``Engine.demographic_rng``，同 seed 可复现。
    """

    working_age_months: int = 14 * 12
    retirement_age_months: int = 0          # 0 = 不退休（古典）
    fertility_monthly: float = 0.024        # 育龄女性平均月生育概率（ASFR/12）
    fertility_age_min_months: int = 20 * 12
    fertility_age_max_months: int = 40 * 12
    fertility_multiplier: float = 1.0
    # 年化 Gompertz：mu(a) = A + B * exp(C * a)
    mortality_A: float = 0.0015
    mortality_B: float = 0.0001
    mortality_C: float = 0.085
    infant_mortality_annual: float = 0.18
    child_mortality_annual: float = 0.02
    max_age_months: int = 110 * 12
    initial_age_min_months: int = 18 * 12
    initial_age_max_months: int = 60 * 12
    initial_female_share: float = 0.5
    child_food: float = 0.05                # 吨 / 月
    child_cloth: float = 0.5                # 件 / 月
    child_housing: float = 0.1              # 平方米 / 月
    pension_tax_rate: float = 0.0
    pension_replacement: float = 0.0
    pension_fund_initial: float = 0.0


# ---------------------------------------------------------------------------
# 生产目录
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EquipmentType:
    key: str
    label: str
    industry: Industry
    capacity: float                 # 熟练度 1 时的月产出
    workers: int                    # 满产所需工人
    capital_good: Good | None       # 建造一台设备所需商品
    capital_cost: float = 0.0       # 所需资本品数量
    build_months: int = 0
    power: float = 0.0              # 农业：人均土地乘数
    building_cost: float = 0.0      # 每台设备所需建筑面积


@dataclass(frozen=True)
class SectorParams:
    industry: Industry
    output: Good
    inputs: Dict[Good, float]       # 每单位产出的投入量
    equipment: Tuple[str, ...]
    max_firms: int
    is_resource: bool = False


def _make_equipment_tiers(
    prefix: str,
    industry: Industry,
    label: str,
    base_capacity: float,
    base_workers: int,
    capital_good: Good | None,
    t0_cost: float,
    upgrade_cost: float,
    base_build_months: int,
    power_base: float = 0.0,
) -> Dict[str, EquipmentType]:
    """生成 8 个 2 的 N 次方设备等级。

    n=0..7 对应 1×、2×、4×……128×。产能翻倍，工人 +1；t0 可以是
    纯手工设备（造价 0），t1 起使用资本品。农业的 power 逐级翻倍。
    """
    result: Dict[str, EquipmentType] = {}
    for n in range(8):
        key = f"{prefix}_t{n}"
        if n == 0:
            cost = t0_cost
            good = capital_good if t0_cost > 0 else None
        else:
            cost = upgrade_cost * (2 ** (n - 1))
            good = capital_good
        result[key] = EquipmentType(
            key=key,
            label=f"{label} {2 ** n}×",
            industry=industry,
            capacity=base_capacity * (2 ** n),
            workers=0 if power_base > 0 else base_workers + n,
            capital_good=good,
            capital_cost=cost,
            build_months=base_build_months + n // 2,
            power=power_base * (2 ** n) if power_base > 0 else 0.0,
            building_cost=0.0,
        )
    return result


EQUIPMENT: Dict[str, EquipmentType] = {}
EQUIPMENT.update(
    _make_equipment_tiers(
        "farm", Industry.AGRICULTURE, "农机",
        base_capacity=0.0, base_workers=0, capital_good=Good.MACHINERY,
        t0_cost=1.0, upgrade_cost=2.0, base_build_months=2, power_base=1.0,
    )
)
for prefix, industry, label, capacity, workers, good, t0, upgrade, build in [
    ("coal", Industry.COAL_MINE, "手工矿井", 10.0, 10, Good.MACHINERY, 0.0, 2.0, 0),
    ("iron", Industry.IRON_MINE, "手工矿井", 10.0, 10, Good.MACHINERY, 0.0, 2.0, 0),
    ("steel", Industry.STEEL_MILL, "炼钢炉", 50.0, 3, Good.BRICK, 1000.0, 2000.0, 2),
    ("brick", Industry.BRICK_FACTORY, "砖窑", 100.0, 50, Good.BRICK, 300.0, 600.0, 2),
    ("textile", Industry.TEXTILE_MILL, "织机", 50.0, 1, Good.MACHINERY, 0.0, 5.0, 1),
    ("machinery", Industry.MACHINERY_FACTORY, "机械工坊", 5.0, 10, Good.STEEL, 0.0, 20.0, 1),
    ("construction", Industry.CONSTRUCTION, "施工队", 50.0, 20, Good.MACHINERY, 0.0, 3.0, 1),
    # 反应炉建设期 1 个月：2 个月会让化肥厂错过第一批资本主义农场
    # 的采用窗口，造成“农场想买、工厂还在建”的额外停摆。
    ("fertilizer", Industry.FERTILIZER_FACTORY, "反应炉", 20.0, 5, Good.MACHINERY, 1.0, 2.0, 1),
]:
    EQUIPMENT.update(
        _make_equipment_tiers(
            prefix, industry, label,
            base_capacity=capacity, base_workers=workers,
            capital_good=good, t0_cost=t0, upgrade_cost=upgrade,
            base_build_months=build,
        )
    )


# 手工 t0 启动配方：不需要资本品，专门用于死掉的行业重新进入/重建。
# 产能刻意做小，正常扩张仍必须使用 2^N 设备；只在行业没有活跃企业时使用。
_MANUAL_SPECS = [
    ("brick_manual", Industry.BRICK_FACTORY, "手工砖窑", 10.0, 10),
    ("steel_manual", Industry.STEEL_MILL, "手工炼钢炉", 5.0, 5),
    ("machinery_manual", Industry.MACHINERY_FACTORY, "手工机械工坊", 1.0, 5),
    ("construction_manual", Industry.CONSTRUCTION, "手工施工队", 5.0, 10),
    ("textile_manual", Industry.TEXTILE_MILL, "手工织机", 10.0, 5),
]
for key, industry, label, capacity, workers in _MANUAL_SPECS:
    EQUIPMENT[key] = EquipmentType(
        key=key,
        label=label,
        industry=industry,
        capacity=capacity,
        workers=workers,
        capital_good=None,
        capital_cost=0.0,
        build_months=0,
        power=0.0,
        building_cost=0.0,
    )

MANUAL_EQUIPMENT: Dict[Industry, str] = {
    Industry.BRICK_FACTORY: "brick_manual",
    Industry.STEEL_MILL: "steel_manual",
    Industry.MACHINERY_FACTORY: "machinery_manual",
    Industry.CONSTRUCTION: "construction_manual",
    Industry.TEXTILE_MILL: "textile_manual",
}

# 手工服务摊：零资本品、当月可开工。一个摊主即一家服务企业，
# 是失业者自雇/非正规部门的主要载体。刻意不提供 2^N 升级档，
# 避免服务业变成资本密集型部门。
EQUIPMENT["service_t0"] = EquipmentType(
    key="service_t0",
    label="手工服务摊",
    industry=Industry.SERVICE,
    capacity=1.0,
    workers=1,
    capital_good=None,
    capital_cost=0.0,
    build_months=0,
    power=0.0,
    building_cost=0.0,
)


SECTOR_PARAMS: Dict[Industry, SectorParams] = {
    Industry.AGRICULTURE: SectorParams(
        industry=Industry.AGRICULTURE,
        output=Good.FOOD,
        inputs={},
        equipment=tuple(f"farm_t{n}" for n in range(8)),
        max_firms=300,
        is_resource=True,
    ),
    Industry.COAL_MINE: SectorParams(
        industry=Industry.COAL_MINE,
        output=Good.COAL,
        inputs={},
        equipment=tuple(f"coal_t{n}" for n in range(8)),
        max_firms=30,
        is_resource=True,
    ),
    Industry.IRON_MINE: SectorParams(
        industry=Industry.IRON_MINE,
        output=Good.IRON_ORE,
        inputs={},
        equipment=tuple(f"iron_t{n}" for n in range(8)),
        max_firms=15,
        is_resource=True,
    ),
    Industry.STEEL_MILL: SectorParams(
        industry=Industry.STEEL_MILL,
        output=Good.STEEL,
        inputs={Good.IRON_ORE: 1.5, Good.COAL: 1.0},
        equipment=tuple(f"steel_t{n}" for n in range(8)),
        max_firms=8,
    ),
    Industry.BRICK_FACTORY: SectorParams(
        industry=Industry.BRICK_FACTORY,
        output=Good.BRICK,
        inputs={Good.COAL: 0.2},
        equipment=tuple(f"brick_t{n}" for n in range(8)),
        max_firms=5,
    ),
    Industry.TEXTILE_MILL: SectorParams(
        industry=Industry.TEXTILE_MILL,
        output=Good.CLOTH,
        inputs={Good.FOOD: 0.001},
        equipment=tuple(f"textile_t{n}" for n in range(8)),
        max_firms=6,
    ),
    Industry.MACHINERY_FACTORY: SectorParams(
        industry=Industry.MACHINERY_FACTORY,
        output=Good.MACHINERY,
        inputs={Good.STEEL: 1.0},
        equipment=tuple(f"machinery_t{n}" for n in range(8)),
        max_firms=4,
    ),
    Industry.CONSTRUCTION: SectorParams(
        industry=Industry.CONSTRUCTION,
        output=Good.BUILDING,
        inputs={Good.BRICK: 0.5},
        equipment=tuple(f"construction_t{n}" for n in range(8)),
        max_firms=6,
    ),
    Industry.FERTILIZER_FACTORY: SectorParams(
        industry=Industry.FERTILIZER_FACTORY,
        output=Good.FERTILIZER,
        inputs={Good.COAL: 2.0},
        equipment=tuple(f"fertilizer_t{n}" for n in range(8)),
        max_firms=3,
    ),
    Industry.SERVICE: SectorParams(
        industry=Industry.SERVICE,
        output=Good.SERVICE,
        inputs={},
        equipment=("service_t0",),
        max_firms=600,
    ),
}

# 农业：熟练度 1 时每亩每月的基础产量。
BASE_GRAIN_YIELD = 0.01
FERTILIZER_PER_MU = 0.01
FERTILIZER_YIELD_MULTIPLIER = 2.0
LAND_PER_WORKER_BASE = 10.0

# 化肥厂周转资金：煤是唯一投入，且必须用现金现货采购。
# 为其保留 N 个月满产用煤所需现金，避免把最后一笔现金锁进反应炉，
# 导致设备建成却无煤可烧的“有产能、零产出”状态。
FERTILIZER_COAL_BUFFER_MONTHS = 2.0
# 化肥短缺时，化肥厂在招聘队列中获得优先权（只影响失业者/跳槽顺序，
# 不改变工资形成机制）。化肥是农业的互补投入，缺工时优先补位。
FERTILIZER_HIRING_PRIORITY = True
