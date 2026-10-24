from __future__ import annotations

from dataclasses import dataclass

from .config import (
    FOOD_PER_WORKER,
    INITIAL_PRICES,
    SECTOR_PARAMS,
    TOTAL_LAND_MU,
    WAGE_BASE,
)
from .enums import Industry
from .engine import Engine
from .government import Government, MoneyRegime, PolicyRegime
from .models import FoodReserve
from .production import equipment_summary


@dataclass(frozen=True)
class ScenarioConfig:
    """历史阶段/政策制度的可开关配置。

    同一套经济内核可以通过这些开关组合出 pre-Keynesian、Keynesian 和 MMT
    剧本，而不是把某一种制度硬编码进引擎。
    """

    name: str = "第一次工业革命"
    policy_regime: PolicyRegime = PolicyRegime.CLASSICAL
    money_regime: MoneyRegime = MoneyRegime.GOLD
    price_regime: str = "band"
    demand_regime: str = "fixed"
    bank_intermediation: bool = False
    tax_rate_wage: float = 0.0
    tax_rate_profit: float = 0.0
    ui_replacement: float = 0.0
    ui_duration: int = 0
    public_investment_rate: float = 0.0
    public_investment_countercyclical: float = 0.0
    job_guarantee: bool = False
    jg_wage: float = 0.0
    jg_max_workers: int = 0
    government_cash: float = 0.0


CLASSICAL_LAISSEZ_FAIRE = ScenarioConfig(
    name="古典自由放任（pre-Keynesian）",
    policy_regime=PolicyRegime.CLASSICAL,
    money_regime=MoneyRegime.GOLD,
)

KEYNESIAN_WELFARE = ScenarioConfig(
    name="凯恩斯福利国家",
    policy_regime=PolicyRegime.KEYNESIAN,
    money_regime=MoneyRegime.GOLD,
    bank_intermediation=True,
    tax_rate_wage=0.08,
    tax_rate_profit=0.08,
    ui_replacement=0.50,
    ui_duration=12,
    public_investment_rate=0.15,
    public_investment_countercyclical=0.08,
    government_cash=10_000.0,
)

MMT_SOVEREIGN = ScenarioConfig(
    name="MMT 主权货币 + 就业保障",
    policy_regime=PolicyRegime.MMT,
    money_regime=MoneyRegime.CREDIT,
    bank_intermediation=True,
    tax_rate_wage=0.08,
    tax_rate_profit=0.08,
    ui_replacement=0.45,
    ui_duration=12,
    public_investment_rate=0.08,
    public_investment_countercyclical=0.04,
    job_guarantee=True,
    jg_wage=30.0,
    jg_max_workers=0,
    government_cash=0.0,
)


def build_scenario_1(
    engine: Engine, config: ScenarioConfig = CLASSICAL_LAISSEZ_FAIRE
) -> Engine:
    """第一次工业革命 / 农业国工业化场景。

    总量目标遵循 PRD 场景 1：600 名自耕农、500 名工业工人、100 名资产阶级、
    粮食紧平衡、农业初始未机械化。设备目录经过校准，使初始工业产出
    接近 PRD 的叙事总量。
    """
    # --- 资产阶级 -------------------------------------------------
    for i in range(50):
        engine.capitalists[f"C_{i}"] = _capitalist(f"C_{i}", 100_000.0, "director")
    for i in range(50, 100):
        engine.capitalists[f"C_{i}"] = _capitalist(f"C_{i}", 10_000.0, "manager")

    owner_ids = [c.id for c in engine.capitalists.values()]
    owner_cursor = 0

    # --- 自耕农农业 ------------------------------------------------
    for _ in range(600):
        worker = engine.create_worker(
            industry=Industry.AGRICULTURE,
            skill=2.0,
            cash=20.0,
            food=0.0,
        )
        enterprise = engine.create_enterprise(
            industry=Industry.AGRICULTURE,
            owner_id=worker.id,
            cash=100.0,
            land=10.0,
            is_household=True,
            modernization_capable=False,
        )
        worker.employer_id = enterprise.id
        worker.wage = WAGE_BASE
        worker.is_owner_operator = True
        worker.land_owned = 10.0
        enterprise.workers.append(worker.id)
        # 自耕农：10 亩 × 0.01 吨/亩 × 熟练度 2 = 0.2 吨/月。
        enterprise.demand_forecast = 0.2
        enterprise.target_inventory_months = 6.0
        engine.land.owners[worker.id] = 10.0
        engine.land.enterprise_by_owner[worker.id] = enterprise.id

    # --- 工业企业 --------------------------------------------------
    def add_industry(
        industry: Industry,
        enterprise_count: int,
        workers_per_enterprise: int,
        equipment: dict[str, int],
        extra_workers: int = 0,
    ) -> None:
        nonlocal owner_cursor
        for index in range(enterprise_count):
            owner = engine.capitalists[owner_ids[owner_cursor % len(owner_ids)]]
            owner_cursor += 1
            enterprise = engine.create_enterprise(
                industry=industry,
                owner_id=owner.id,
                cash=5000.0,
                modernization_capable=True,
            )
            for key, count in equipment.items():
                for _ in range(count):
                    enterprise.add_equipment(key)
            worker_count = workers_per_enterprise + (1 if index < extra_workers else 0)
            for _ in range(worker_count):
                worker = engine.create_worker(
                    industry=industry,
                    skill=2.0,
                    cash=20.0,
                    food=0.0,
                )
                worker.employer_id = enterprise.id
                worker.wage = WAGE_BASE
                enterprise.workers.append(worker.id)
            _seed_inputs(engine, enterprise)
            capacity, _, _ = equipment_summary(enterprise)
            enterprise.demand_forecast = capacity * 2.0

    add_industry(Industry.COAL_MINE, 20, 10, {"coal_t0": 1})
    add_industry(Industry.IRON_MINE, 8, 10, {"iron_t0": 1})
    add_industry(Industry.STEEL_MILL, 3, 4, {"steel_t0": 1})
    add_industry(Industry.BRICK_FACTORY, 1, 50, {"brick_t0": 1})
    add_industry(Industry.TEXTILE_MILL, 1, 20, {"textile_t0": 20})
    add_industry(Industry.MACHINERY_FACTORY, 1, 10, {"machinery_t0": 1})
    add_industry(Industry.CONSTRUCTION, 5, 25, {"construction_t0": 1}, extra_workers=3)
    # 化肥 starts empty; it is an entry opportunity once food/coal prices
    # 它会成为一个进入机会。

    engine.land.total_land = TOTAL_LAND_MU
    engine.market.reference_prices = dict(INITIAL_PRICES)
    engine.wage_floor_scale = (
        0.90 if config.policy_regime == PolicyRegime.CLASSICAL else 1.0
    )
    engine.price_regime = config.price_regime
    engine.demand_regime = config.demand_regime
    engine.bank_intermediation = config.bank_intermediation
    # 粮食平准库存/私人粮商：600 吨 ≈ 5 个月全民口粮，60k 现金。
    engine.food_reserve = FoodReserve(cash=60_000.0, food=600.0)
    if config.policy_regime == PolicyRegime.CLASSICAL:
        engine.government = None
    else:
        engine.government = Government(
            regime=config.policy_regime,
            money_regime=config.money_regime,
            cash=config.government_cash,
            tax_rate_wage=config.tax_rate_wage,
            tax_rate_profit=config.tax_rate_profit,
            ui_replacement=config.ui_replacement,
            ui_duration=config.ui_duration,
            public_investment_rate=config.public_investment_rate,
            public_investment_countercyclical=(
                config.public_investment_countercyclical
            ),
            job_guarantee=config.job_guarantee,
            jg_wage=config.jg_wage,
            jg_max_workers=config.jg_max_workers,
        )
    engine.money_initial = engine.total_money()
    return engine


def _capitalist(cid: str, cash: float, role: str):
    from .models import Capitalist

    return Capitalist(id=cid, cash=cash, role=role)


def _seed_inputs(engine: Engine, enterprise) -> None:
    """按当前产能和熟练度 2 给每家企业配置一个月投入。"""
    params = SECTOR_PARAMS[enterprise.industry]
    if not params.inputs:
        return
    capacity, _, _ = equipment_summary(enterprise)
    output = capacity * 2.0
    for good, ratio in params.inputs.items():
        enterprise.inventory[good] = max(
            enterprise.inventory.get(good, 0.0), output * ratio
        )
