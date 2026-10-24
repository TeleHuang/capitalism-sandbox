from __future__ import annotations

from .config import (
    FOOD_PER_WORKER,
    INITIAL_PRICES,
    SECTOR_PARAMS,
    TOTAL_LAND_MU,
    WAGE_BASE,
)
from .enums import Industry
from .engine import Engine
from .production import equipment_summary


def build_scenario_1(engine: Engine) -> Engine:
    """First Industrial Revolution / agricultural-industrialisation scenario.

    The aggregate targets follow the PRD's scenario 1: 600 smallholders, 500
    industrial workers, 100 capitalists, a tight food balance, and an initially
    unmechanised agricultural sector.  The equipment catalogue is calibrated so
    the initial industrial output is close to the PRD's narrative totals.
    """
    # --- Capitalists -------------------------------------------------
    for i in range(50):
        engine.capitalists[f"C_{i}"] = _capitalist(f"C_{i}", 100_000.0, "director")
    for i in range(50, 100):
        engine.capitalists[f"C_{i}"] = _capitalist(f"C_{i}", 10_000.0, "manager")

    owner_ids = [c.id for c in engine.capitalists.values()]
    owner_cursor = 0

    # --- Smallholder agriculture ------------------------------------
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
        engine.land.owners[worker.id] = 10.0
        engine.land.enterprise_by_owner[worker.id] = enterprise.id

    # --- Industrial enterprises -------------------------------------
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

    add_industry(Industry.COAL_MINE, 20, 10, {"hand_mine": 1})
    add_industry(Industry.IRON_MINE, 8, 10, {"hand_mine": 1})
    add_industry(Industry.STEEL_MILL, 3, 13, {"furnace_20": 1}, extra_workers=1)
    add_industry(Industry.BRICK_FACTORY, 1, 50, {"brick_kiln": 1})
    add_industry(Industry.TEXTILE_MILL, 1, 20, {"hand_loom": 20})
    add_industry(Industry.MACHINERY_FACTORY, 1, 10, {"hand_forge": 1})
    add_industry(Industry.CONSTRUCTION, 5, 20, {"hand_crew": 1})
    # Fertilizer starts empty; it is an entry opportunity once food/coal prices
    # make a reactor profitable.

    engine.land.total_land = TOTAL_LAND_MU
    engine.market.reference_prices = dict(INITIAL_PRICES)
    engine.money_initial = engine.total_money()
    return engine


def _capitalist(cid: str, cash: float, role: str):
    from .models import Capitalist

    return Capitalist(id=cid, cash=cash, role=role)


def _seed_inputs(engine: Engine, enterprise) -> None:
    """Give each enterprise one month of inputs at current capacity and skill 2."""
    params = SECTOR_PARAMS[enterprise.industry]
    if not params.inputs:
        return
    capacity, _, _ = equipment_summary(enterprise)
    output = capacity * 2.0
    for good, ratio in params.inputs.items():
        enterprise.inventory[good] = max(
            enterprise.inventory.get(good, 0.0), output * ratio
        )
