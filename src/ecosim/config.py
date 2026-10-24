"""Static calibration for the V0.2 model.

All supply-side quantities are monthly.  ``capacity`` on an equipment type is the
output at skill = 1.0; actual output is multiplied by the average skill of the
operating workers.  This keeps the PRD's skill-growth mechanism (1.0 -> 2.0)
meaningful without hard-coding two different production tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from .enums import Good, Industry

# ---------------------------------------------------------------------------
# Prices and household parameters
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

# Monthly subsistence basket (PRD 2.2.1).
FOOD_PER_WORKER = 0.10          # tonnes / month
CLOTH_PER_WORKER = 1.0          # pieces / month
HOUSING_PER_WORKER = 0.20       # square metres / month

COMFORT_MULTIPLIER = 1.5
COMFORT_SAVINGS = 60.0
LEISURE_SAVINGS = 120.0

# Labour supply.  Workers choose hours from this set; wages are pro-rata.
HOURS_OPTIONS = (16, 12, 8)
DEFAULT_HOURS = 16

# Skill growth: 1.0 -> 2.0 over roughly five years of employment.
SKILL_MIN = 1.0
SKILL_MAX = 2.0
SKILL_GROWTH_PER_MONTH = 1.0 / 60.0

# Survival: hunger is a multi-month process, not a one-month coin flip.
HUNGER_DEATH_AFTER_MONTHS = 3
HUNGER_DEATH_BASE = 0.08
HUNGER_DEATH_STEP = 0.08
HUNGER_DEATH_CAP = 0.50

# Wages / labour market
WAGE_BASE = 20.0
WAGE_SEARCH_PREMIUM = 0.08
WAGE_SWITCH_THRESHOLD = 0.06
MAX_HIRES_PER_ENTERPRISE_PER_MONTH = 20

# Capitalists
CAPITALIST_CONSUMPTION_RATE = 0.02   # share of cash spent per month
CAPITALIST_MIN_CONSUMPTION = 100.0
CAPITALIST_FOOD = 0.1
CAPITALIST_CLOTH = 5.0
CAPITALIST_HOUSING = 1.0

# Investment
INVESTMENT_HURDLE = 0.012            # minimum expected monthly return on capital
INVESTMENT_RESERVE_MONTHS = 3.0      # keep this many months of wages after investing
MAX_NEW_FIRMS_PER_TICK = 1
MAX_PROJECTS_PER_TICK = 5
MAX_ACTIVE_PROJECTS = 10
PROJECT_TIMEOUT_MONTHS = 18
DEPRECIATION_MONTHS = 120.0
DIVIDEND_PAYOUT = 0.50

# Land market
TOTAL_LAND_MU = 6000.0
INITIAL_LAND_PRICE = 100.0          # yuan / mu
LAND_RESERVATION_PRICE = 150.0      # smallholders sell only above this
LAND_PRICE_STEP = 0.05
LAND_SALES_PER_TICK = 0.02          # at most 2% of smallholder land per month
MIN_CAPITALIST_FARM_MU = 50.0
TARGET_CAPITALIST_FARM_MU = 100.0

# Reference-price tatonnement
PRICE_STEP = 0.05
PRICE_FLOOR = 0.01

BANK_CASH = 100_000.0
BANK_INTEREST_RATE = 0.01
BANK_LOAN_MONTHS = 3.0


# ---------------------------------------------------------------------------
# Production catalogue
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EquipmentType:
    key: str
    label: str
    industry: Industry
    capacity: float                 # output / month at skill 1
    workers: int                    # workers needed for full capacity
    capital_good: Good | None       # good required to build one unit
    capital_cost: float = 0.0       # units of capital_good
    build_months: int = 0
    power: float = 0.0              # agriculture: land-per-worker multiplier
    building_cost: float = 0.0      # square metres required per unit


@dataclass(frozen=True)
class SectorParams:
    industry: Industry
    output: Good
    inputs: Dict[Good, float]       # input units per output unit
    equipment: Tuple[str, ...]
    max_firms: int
    is_resource: bool = False


EQUIPMENT: Dict[str, EquipmentType] = {
    # Agriculture: machinery raises land per worker, not yield directly.
    "farm_machinery": EquipmentType(
        key="farm_machinery",
        label="farm machinery",
        industry=Industry.AGRICULTURE,
        capacity=0.0,
        workers=0,
        capital_good=Good.MACHINERY,
        capital_cost=1.0,
        build_months=2,
        power=1.0,
        building_cost=0.0,
    ),
    # Coal / iron
    "hand_mine": EquipmentType(
        key="hand_mine",
        label="hand mine",
        industry=Industry.COAL_MINE,
        capacity=10.0,
        workers=10,
        capital_good=None,
    ),
    "mechanized_mine": EquipmentType(
        key="mechanized_mine",
        label="mechanized mine",
        industry=Industry.COAL_MINE,
        capacity=100.0,
        workers=10,
        capital_good=Good.MACHINERY,
        capital_cost=5.0,
        build_months=2,
        building_cost=0.0,
    ),
    # Steel: 2^N furnace family, base 20 t at skill 1.
    "furnace_20": EquipmentType(
        key="furnace_20",
        label="20 t furnace",
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
        label="40 t furnace",
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
        label="80 t furnace",
        industry=Industry.STEEL_MILL,
        capacity=80.0,
        workers=14,
        capital_good=Good.BRICK,
        capital_cost=800.0,
        build_months=4,
        building_cost=0.0,
    ),
    # Brick
    "brick_kiln": EquipmentType(
        key="brick_kiln",
        label="brick kiln",
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
        label="large brick kiln",
        industry=Industry.BRICK_FACTORY,
        capacity=200.0,
        workers=55,
        capital_good=Good.BRICK,
        capital_cost=300.0,
        build_months=3,
        building_cost=0.0,
    ),
    # Textile
    "hand_loom": EquipmentType(
        key="hand_loom",
        label="hand loom",
        industry=Industry.TEXTILE_MILL,
        capacity=50.0,
        workers=1,
        capital_good=None,
    ),
    "industrial_loom": EquipmentType(
        key="industrial_loom",
        label="industrial loom",
        industry=Industry.TEXTILE_MILL,
        capacity=500.0,
        workers=5,
        capital_good=Good.MACHINERY,
        capital_cost=5.0,
        build_months=2,
        building_cost=0.0,
    ),
    # Machinery
    "hand_forge": EquipmentType(
        key="hand_forge",
        label="hand forge",
        industry=Industry.MACHINERY_FACTORY,
        capacity=5.0,
        workers=10,
        capital_good=None,
    ),
    "machine_tool": EquipmentType(
        key="machine_tool",
        label="machine tool",
        industry=Industry.MACHINERY_FACTORY,
        capacity=20.0,
        workers=10,
        capital_good=Good.STEEL,
        capital_cost=20.0,
        build_months=2,
        building_cost=0.0,
    ),
    # Construction
    "hand_crew": EquipmentType(
        key="hand_crew",
        label="hand construction crew",
        industry=Industry.CONSTRUCTION,
        capacity=50.0,
        workers=20,
        capital_good=None,
    ),
    "construction_machinery": EquipmentType(
        key="construction_machinery",
        label="construction machinery",
        industry=Industry.CONSTRUCTION,
        capacity=100.0,
        workers=10,
        capital_good=Good.MACHINERY,
        capital_cost=3.0,
        build_months=2,
        building_cost=0.0,
    ),
    # Fertilizer
    "reactor": EquipmentType(
        key="reactor",
        label="fertilizer reactor",
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

# Agriculture: base yield per mu per month at skill 1.
BASE_GRAIN_YIELD = 0.01
FERTILIZER_PER_MU = 0.01
FERTILIZER_YIELD_MULTIPLIER = 2.0
LAND_PER_WORKER_BASE = 10.0
