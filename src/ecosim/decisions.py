from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .config import (
    BASE_GRAIN_YIELD,
    EQUIPMENT,
    FERTILIZER_PER_MU,
    FERTILIZER_YIELD_MULTIPLIER,
    INVESTMENT_HURDLE,
    LAND_PER_WORKER_BASE,
    SECTOR_PARAMS,
    SKILL_MAX,
    WAGE_BASE,
)
from .enums import Good, Industry
from .production import (
    capital_value,
    capacity_at_skill_one,
    desired_workers,
    equipment_cost,
    representative_roi,
    unit_cost,
)

if TYPE_CHECKING:
    from .engine import Engine
    from .models import Enterprise, Worker


def subsistence_cost(prices: dict[Good, float]) -> float:
    return (
        0.1 * prices.get(Good.FOOD, 100.0)
        + prices.get(Good.CLOTH, 1.0)
        + 0.2 * prices.get(Good.BUILDING, 10.0)
    )


def wage_floor(prices: dict[Good, float]) -> float:
    return max(WAGE_BASE, subsistence_cost(prices) * 1.1)


def enterprise_wage_offer(engine: "Engine", enterprise: "Enterprise") -> float:
    workers = engine.enterprise_workers(enterprise)
    floor = wage_floor(engine.market.reference_prices)
    offer = max(WAGE_BASE, floor)
    if enterprise.last_revenue > 0 and enterprise.last_profit > 0:
        margin = max(0.0, min(0.35, enterprise.last_profit / enterprise.last_revenue))
        offer *= 1.0 + margin * 0.5
    if len(workers) < desired_workers(enterprise):
        offer *= 1.10
    wage_bill = sum(w.wage * w.effective_labor for w in workers)
    if enterprise.cash < max(wage_bill * 2.0, offer * 2.0):
        offer *= 0.95
    return max(floor, round(offer, 2))


def enterprise_ask_price(engine: "Engine", enterprise: "Enterprise") -> float:
    params = SECTOR_PARAMS[enterprise.industry]
    out = params.output
    ref = engine.market.reference_prices.get(out, 1.0)
    workers = engine.enterprise_workers(enterprise)
    cost = unit_cost(enterprise, engine.market.reference_prices, workers, engine.land.price)
    inventory = enterprise.inv(out)
    capacity = capacity_at_skill_one(enterprise) * max(
        sum(w.skill for w in workers) / max(len(workers), 1), 1.0
    )
    sales = enterprise.smoothed_sales
    if sales <= 1e-6:
        months = 3.0 if inventory > 0 else 0.0
    else:
        months = inventory / sales

    if months > 3.0:
        price = min(ref * 0.90, cost * 1.05 if cost > 0 else ref * 0.90)
    elif months < 0.5:
        price = ref * 1.02
    else:
        price = ref * 0.98

    # 卖方可以亏本清理易腐库存；拒绝低于成本出售
    # 曾在 V0.1 冻结食品市场并引发饥荒。卖价也
    # 被限制在参考价附近，保证买价能够穿价成交。
    if cost > 0:
        price = max(price, cost * 0.85)
    price = min(price, ref * 1.02)
    return max(0.01, price)


def production_plan(engine: "Engine", enterprise: "Enterprise") -> float:
    if enterprise.industry == Industry.AGRICULTURE:
        # 土地是约束；即使库存偏高，农场也会继续生产，
        # 因为食品是生存品。0.4 的产量下限可以避免
        # 市场出清缓慢时自己制造饥荒。
        return 1.0 if enterprise.land > 0 and enterprise.workers else 0.0

    params = SECTOR_PARAMS[enterprise.industry]
    out = params.output
    capacity = capacity_at_skill_one(enterprise)
    if capacity <= 0:
        return 0.0

    inventory = enterprise.inv(out)
    sales = max(enterprise.smoothed_sales, 0.0)
    if sales <= 1e-6:
        target = max(capacity * 0.5, 1.0)
    else:
        target = max(sales * 1.2, capacity * 0.1)
    desired = max(0.0, target - inventory)
    plan = desired / capacity
    if plan < 0.1 and inventory < target:
        plan = 0.1
    return max(0.0, min(1.0, plan))


def wants_fertilizer(engine: "Engine", enterprise: "Enterprise") -> bool:
    if enterprise.industry != Industry.AGRICULTURE or enterprise.land <= 0:
        return False
    if not enterprise.modernization_capable:
        return False
    food_price = engine.market.reference_prices.get(Good.FOOD, 0.0)
    fertilizer_price = engine.market.reference_prices.get(Good.FERTILIZER, 0.0)
    extra_yield = enterprise.land * BASE_GRAIN_YIELD * (FERTILIZER_YIELD_MULTIPLIER - 1.0)
    benefit = extra_yield * food_price * SKILL_MAX
    cost = enterprise.land * FERTILIZER_PER_MU * fertilizer_price
    return benefit > cost * 1.15


def input_needs(engine: "Engine", enterprise: "Enterprise") -> dict[Good, float]:
    params = SECTOR_PARAMS[enterprise.industry]
    needs: dict[Good, float] = {}
    if enterprise.industry == Industry.AGRICULTURE:
        if wants_fertilizer(engine, enterprise):
            needed = enterprise.land * FERTILIZER_PER_MU - enterprise.inv(Good.FERTILIZER)
            if needed > 1e-9:
                needs[Good.FERTILIZER] = needed
        return needs

    plan = production_plan(engine, enterprise)
    workers = engine.enterprise_workers(enterprise)
    skill = sum(w.skill for w in workers) / max(len(workers), 1)
    expected_output = capacity_at_skill_one(enterprise) * plan * skill
    for good, ratio in params.inputs.items():
        needed = expected_output * ratio - enterprise.inv(good)
        if needed > 1e-9:
            needs[good] = needed
    return needs


def best_equipment_choice(
    engine: "Engine", industry: Industry, budget: Optional[float] = None
) -> Optional[tuple[str, float]]:
    prices = engine.market.reference_prices
    wage = engine.average_wage()
    land_price = engine.land.price
    candidates = []
    for key in SECTOR_PARAMS[industry].equipment:
        et = EQUIPMENT[key]
        if et.capital_good is None or et.build_months <= 0:
            continue
        cost = equipment_cost(key, prices)
        if budget is not None and cost > budget:
            continue
        roi = representative_roi(industry, key, prices, wage, land_price)
        candidates.append((cost, key, roi))
    if not candidates:
        return None
    # 企业优先选择“能负担的最小规模”，避免一上来就追求 128× 设备、
    # 把资本品需求和项目现金推到不可完成的程度；后续再按需求升级。
    candidates.sort(key=lambda item: (item[0], -item[2]))
    _, best_key, best_roi = candidates[0]
    return best_key, best_roi


def should_invest(engine: "Engine", enterprise: "Enterprise") -> Optional[tuple[str, float]]:
    if not enterprise.active:
        return None
    if enterprise.industry == Industry.AGRICULTURE and not enterprise.modernization_capable:
        return None
    # 化肥厂是典型的高固定成本、低毛利行业。没有长期规划时，企业会把
    # 现金不断砸进反应炉，最后没钱买煤。先限制单厂最多 2 台反应炉，
    # 作为“保留周转资金”的临时规则；后续由 LLM 经理做长期规划。
    if enterprise.industry == Industry.FERTILIZER_FACTORY and enterprise.total_equipment() >= 2:
        return None
    workers = engine.enterprise_workers(enterprise)
    wage_bill = sum(w.wage * w.effective_labor for w in workers)
    reserve = max(wage_bill * 3.0, 100.0)
    available = enterprise.cash - reserve
    if available <= 0:
        return None
    choice = best_equipment_choice(engine, enterprise.industry, budget=available / 1.10)
    if choice is None:
        return None
    key, roi = choice
    if roi < INVESTMENT_HURDLE:
        return None
    cost = equipment_cost(key, engine.market.reference_prices)
    if enterprise.cash < cost * 1.10 + reserve:
        return None
    if engine.tick - enterprise.last_invest_tick < 6:
        return None
    return key, roi


def agricultural_entry_roi(engine: "Engine") -> tuple[str, float]:
    """一台农机的新资本主义农场的 ROI。"""
    return best_equipment_choice(engine, Industry.AGRICULTURE) or ("farm_t0", -1.0)


def farm_capital_per_mu(engine: "Engine") -> float:
    return engine.land.price + equipment_cost(
        "farm_t0", engine.market.reference_prices
    ) / max(1.0, LAND_PER_WORKER_BASE * 2.0)


def enterprise_capital(engine: "Engine", enterprise: "Enterprise") -> float:
    return capital_value(enterprise, engine.market.reference_prices, engine.land.price)
