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
}

# 月度温饱篮子（PRD 2.2.1）。
FOOD_PER_WORKER = 0.10          # 吨 / 月
CLOTH_PER_WORKER = 1.0          # 件 / 月
HOUSING_PER_WORKER = 0.20       # 平方米 / 月

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
CAPITALIST_FOOD = 0.1
CAPITALIST_CLOTH = 5.0
CAPITALIST_HOUSING = 1.0

# 投资
INVESTMENT_HURDLE = 0.012            # 最低预期月资本回报率
INVESTMENT_RESERVE_MONTHS = 3.0      # 投资后保留的工资月数
MAX_NEW_FIRMS_PER_TICK = 1
MAX_PROJECTS_PER_TICK = 5
MAX_ACTIVE_PROJECTS = 10
PROJECT_TIMEOUT_MONTHS = 18
DEPRECIATION_MONTHS = 120.0
DIVIDEND_PAYOUT = 0.50

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


EQUIPMENT: Dict[str, EquipmentType] = {
    # 农业：农机提高人均土地，不直接提高亩产。
    "farm_machinery": EquipmentType(
        key="farm_machinery",
        label="农机",
        industry=Industry.AGRICULTURE,
        capacity=0.0,
        workers=0,
        capital_good=Good.MACHINERY,
        capital_cost=1.0,
        build_months=2,
        power=1.0,
        building_cost=0.0,
    ),
    # 煤炭 / 铁矿
    "hand_mine": EquipmentType(
        key="hand_mine",
        label="手工矿井",
        industry=Industry.COAL_MINE,
        capacity=10.0,
        workers=10,
        capital_good=None,
    ),
    "mechanized_mine": EquipmentType(
        key="mechanized_mine",
        label="机械化矿井",
        industry=Industry.COAL_MINE,
        capacity=100.0,
        workers=10,
        capital_good=Good.MACHINERY,
        capital_cost=5.0,
        build_months=2,
        building_cost=0.0,
    ),
    # 炼钢：2 的 N 次方炉型，熟练度 1 时基准为 20 吨。
    "furnace_20": EquipmentType(
        key="furnace_20",
        label="20 吨炼钢炉",
        industry=Industry.STEEL_MILL,
        capacity=20.0,
        workers=12,
        capital_good=Good.BRICK,
        capital_cost=200.0,
        build_months=2,
        building_cost=0.0,
    ),
    "furnace_40": EquipmentType(
        key="furnace_40",
        label="40 吨炼钢炉",
        industry=Industry.STEEL_MILL,
        capacity=40.0,
        workers=13,
        capital_good=Good.BRICK,
        capital_cost=400.0,
        build_months=3,
        building_cost=0.0,
    ),
    "furnace_80": EquipmentType(
        key="furnace_80",
        label="80 吨炼钢炉",
        industry=Industry.STEEL_MILL,
        capacity=80.0,
        workers=14,
        capital_good=Good.BRICK,
        capital_cost=800.0,
        build_months=4,
        building_cost=0.0,
    ),
    # 砖
    "brick_kiln": EquipmentType(
        key="brick_kiln",
        label="砖窑",
        industry=Industry.BRICK_FACTORY,
        capacity=100.0,
        workers=50,
        capital_good=Good.BRICK,
        capital_cost=100.0,
        build_months=2,
        building_cost=0.0,
    ),
    "brick_kiln_large": EquipmentType(
        key="brick_kiln_large",
        label="大型砖窑",
        industry=Industry.BRICK_FACTORY,
        capacity=200.0,
        workers=55,
        capital_good=Good.BRICK,
        capital_cost=300.0,
        build_months=3,
        building_cost=0.0,
    ),
    # 纺织
    "hand_loom": EquipmentType(
        key="hand_loom",
        label="手织机",
        industry=Industry.TEXTILE_MILL,
        capacity=50.0,
        workers=1,
        capital_good=None,
    ),
    "industrial_loom": EquipmentType(
        key="industrial_loom",
        label="工业织机",
        industry=Industry.TEXTILE_MILL,
        capacity=500.0,
        workers=5,
        capital_good=Good.MACHINERY,
        capital_cost=5.0,
        build_months=2,
        building_cost=0.0,
    ),
    # 机械
    "hand_forge": EquipmentType(
        key="hand_forge",
        label="手工锻炉",
        industry=Industry.MACHINERY_FACTORY,
        capacity=5.0,
        workers=10,
        capital_good=None,
    ),
    "machine_tool": EquipmentType(
        key="machine_tool",
        label="机床",
        industry=Industry.MACHINERY_FACTORY,
        capacity=20.0,
        workers=10,
        capital_good=Good.STEEL,
        capital_cost=20.0,
        build_months=2,
        building_cost=0.0,
    ),
    # 施工
    "hand_crew": EquipmentType(
        key="hand_crew",
        label="手工施工队",
        industry=Industry.CONSTRUCTION,
        capacity=50.0,
        workers=20,
        capital_good=None,
    ),
    "construction_machinery": EquipmentType(
        key="construction_machinery",
        label="施工机械",
        industry=Industry.CONSTRUCTION,
        capacity=100.0,
        workers=10,
        capital_good=Good.MACHINERY,
        capital_cost=3.0,
        build_months=2,
        building_cost=0.0,
    ),
    # 化肥
    "reactor": EquipmentType(
        key="reactor",
        label="化肥反应炉",
        industry=Industry.FERTILIZER_FACTORY,
        capacity=20.0,
        workers=5,
        capital_good=Good.MACHINERY,
        capital_cost=1.0,
        build_months=2,
        building_cost=0.0,
    ),
}

SECTOR_PARAMS: Dict[Industry, SectorParams] = {
    Industry.AGRICULTURE: SectorParams(
        industry=Industry.AGRICULTURE,
        output=Good.FOOD,
        inputs={},
        equipment=("farm_machinery",),
        max_firms=300,
        is_resource=True,
    ),
    Industry.COAL_MINE: SectorParams(
        industry=Industry.COAL_MINE,
        output=Good.COAL,
        inputs={},
        equipment=("hand_mine", "mechanized_mine"),
        max_firms=30,
        is_resource=True,
    ),
    Industry.IRON_MINE: SectorParams(
        industry=Industry.IRON_MINE,
        output=Good.IRON_ORE,
        inputs={},
        equipment=("hand_mine", "mechanized_mine"),
        max_firms=15,
        is_resource=True,
    ),
    Industry.STEEL_MILL: SectorParams(
        industry=Industry.STEEL_MILL,
        output=Good.STEEL,
        inputs={Good.IRON_ORE: 1.5, Good.COAL: 1.0},
        equipment=("furnace_20", "furnace_40", "furnace_80"),
        max_firms=8,
    ),
    Industry.BRICK_FACTORY: SectorParams(
        industry=Industry.BRICK_FACTORY,
        output=Good.BRICK,
        inputs={Good.COAL: 0.2},
        equipment=("brick_kiln", "brick_kiln_large"),
        max_firms=5,
    ),
    Industry.TEXTILE_MILL: SectorParams(
        industry=Industry.TEXTILE_MILL,
        output=Good.CLOTH,
        inputs={Good.FOOD: 0.001},
        equipment=("hand_loom", "industrial_loom"),
        max_firms=6,
    ),
    Industry.MACHINERY_FACTORY: SectorParams(
        industry=Industry.MACHINERY_FACTORY,
        output=Good.MACHINERY,
        inputs={Good.STEEL: 1.0},
        equipment=("hand_forge", "machine_tool"),
        max_firms=4,
    ),
    Industry.CONSTRUCTION: SectorParams(
        industry=Industry.CONSTRUCTION,
        output=Good.BUILDING,
        inputs={Good.BRICK: 0.5},
        equipment=("hand_crew", "construction_machinery"),
        max_firms=6,
    ),
    Industry.FERTILIZER_FACTORY: SectorParams(
        industry=Industry.FERTILIZER_FACTORY,
        output=Good.FERTILIZER,
        inputs={Good.COAL: 2.0},
        equipment=("reactor",),
        max_firms=3,
    ),
}

# 农业：熟练度 1 时每亩每月的基础产量。
BASE_GRAIN_YIELD = 0.01
FERTILIZER_PER_MU = 0.01
FERTILIZER_YIELD_MULTIPLIER = 2.0
LAND_PER_WORKER_BASE = 10.0
