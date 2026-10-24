from __future__ import annotations

import math
from typing import Dict, Optional, TYPE_CHECKING

from .config import (
    BASE_GRAIN_YIELD,
    DEPRECIATION_MONTHS,
    EQUIPMENT,
    FERTILIZER_PER_MU,
    FERTILIZER_YIELD_MULTIPLIER,
    LAND_PER_WORKER_BASE,
    SECTOR_PARAMS,
    SKILL_MAX,
    TARGET_CAPITALIST_FARM_MU,
)
from .enums import Good, Industry
from .models import Enterprise, Worker

if TYPE_CHECKING:
    from .engine import Engine


def equipment_summary(enterprise: Enterprise) -> tuple[float, int, int]:
    """返回（熟练度 1 时的产能、所需工人、设备数量）。"""
    capacity = 0.0
    workers = 0
    units = 0
    for key, count in enterprise.equipment.items():
        if count <= 0:
            continue
        et = EQUIPMENT[key]
        capacity += et.capacity * count
        workers += et.workers * count
        units += count
    return capacity, workers, units


def farm_requirements(enterprise: Enterprise) -> tuple[int, float]:
    """返回农场所需工人和农机动力。"""
    power = 0.0
    for key, count in enterprise.equipment.items():
        if count <= 0:
            continue
        power += EQUIPMENT[key].power * count
    if enterprise.land <= 0:
        return 0, power
    land_per_worker = LAND_PER_WORKER_BASE * (1.0 + power)
    return max(1, math.ceil(enterprise.land / land_per_worker)), power


def desired_workers(enterprise: Enterprise, plan: float = 1.0) -> int:
    """按生产计划缩放用工需求。

    plan=1.0 时保持原有的满产用工，旧测试/旧调用不受影响；plan<1 时
    释放冗余工人，让他们能被其它行业雇佣。农业至少保留 1 个所有者。
    """
    if enterprise.industry == Industry.AGRICULTURE:
        required, _ = farm_requirements(enterprise)
    else:
        _, required, _ = equipment_summary(enterprise)
    if required <= 0:
        return 0
    plan = max(0.0, min(1.0, plan))
    if plan <= 1e-9:
        return 1 if enterprise.industry == Industry.AGRICULTURE else 0
    return max(1, int(math.ceil(required * plan)))


def capacity_at_skill_one(enterprise: Enterprise) -> float:
    if enterprise.industry == Industry.AGRICULTURE:
        return enterprise.land * BASE_GRAIN_YIELD
    capacity, _, _ = equipment_summary(enterprise)
    return capacity


def average_skill(workers: list[Worker]) -> float:
    if not workers:
        return 0.0
    return sum(w.skill for w in workers) / len(workers)


def average_wage(workers: list[Worker]) -> float:
    if not workers:
        return 0.0
    return sum(w.wage * w.effective_labor for w in workers) / max(
        sum(w.effective_labor for w in workers), 1e-9
    )


def productivity_multiplier(engine: "Engine", enterprise: Enterprise) -> float:
    """冲击测试钩子：按行业缩放产出。默认 1.0（无冲击）。"""
    multipliers = getattr(engine, "productivity_multipliers", {})
    return max(0.0, multipliers.get(enterprise.industry, 1.0))


def produce(engine: "Engine", enterprise: Enterprise) -> float:
    """执行企业一个月的生产。

    产出 = 产能 × 劳动利用率 × 平均熟练度。投入是硬约束：缺少投入时，
    产出会缩减到现有投入能支撑的水平。化肥是农场的亩产乘数。
    """
    workers = [engine.workers[w] for w in enterprise.workers if engine.workers[w].alive]
    if not workers:
        enterprise.last_output = 0.0
        enterprise.last_input_used = {}
        return 0.0

    effective_labor = sum(w.effective_labor for w in workers)
    skill = average_skill(workers)
    plan = max(0.0, min(1.0, enterprise.plan_ratio))
    if plan <= 1e-9:
        enterprise.last_output = 0.0
        enterprise.last_input_used = {}
        return 0.0

    if enterprise.industry == Industry.AGRICULTURE:
        required, _ = farm_requirements(enterprise)
        if enterprise.land <= 0 or required <= 0:
            enterprise.last_output = 0.0
            return 0.0
        utilisation = min(plan, effective_labor / required)
        base_capacity = (
            enterprise.land
            * BASE_GRAIN_YIELD
            * skill
            * productivity_multiplier(engine, enterprise)
        )
        multiplier = 1.0
        fertilizer_used = 0.0
        if enterprise.use_fertilizer:
            needed = enterprise.land * FERTILIZER_PER_MU
            if enterprise.inv(Good.FERTILIZER) + 1e-9 >= needed:
                multiplier = FERTILIZER_YIELD_MULTIPLIER
                fertilizer_used = needed
                enterprise.inventory[Good.FERTILIZER] -= needed
            else:
                enterprise.use_fertilizer = False
        output = base_capacity * utilisation * multiplier
        enterprise.inventory[Good.FOOD] = enterprise.inv(Good.FOOD) + output
        enterprise.last_output = output
        enterprise.last_input_used = (
            {Good.FERTILIZER: fertilizer_used} if fertilizer_used > 0 else {}
        )
        return output

    capacity, required, _ = equipment_summary(enterprise)
    if capacity <= 0 or required <= 0:
        enterprise.last_output = 0.0
        return 0.0

    utilisation = min(plan, effective_labor / required)
    theoretical = (
        capacity
        * utilisation
        * skill
        * productivity_multiplier(engine, enterprise)
    )

    params = SECTOR_PARAMS[enterprise.industry]
    max_output = theoretical
    for good, ratio in params.inputs.items():
        if ratio <= 0:
            continue
        max_output = min(max_output, enterprise.inv(good) / ratio)

    max_output = max(0.0, max_output)
    used: Dict[Good, float] = {}
    for good, ratio in params.inputs.items():
        consumed = max_output * ratio
        enterprise.inventory[good] = max(0.0, enterprise.inv(good) - consumed)
        used[good] = consumed

    enterprise.inventory[params.output] = enterprise.inv(params.output) + max_output
    enterprise.last_output = max_output
    enterprise.last_input_used = used
    return max_output


def equipment_value(enterprise: Enterprise, prices: Dict[Good, float]) -> float:
    value = 0.0
    for key, count in enterprise.equipment.items():
        if count <= 0:
            continue
        et = EQUIPMENT[key]
        if et.capital_good is not None:
            value += count * et.capital_cost * prices.get(et.capital_good, 0.0)
        value += count * et.building_cost * prices.get(Good.BUILDING, 0.0)
    return value


def full_capacity_unit_cost(
    enterprise: Enterprise,
    prices: Dict[Good, float],
    workers: list[Worker],
) -> float:
    capacity = capacity_at_skill_one(enterprise)
    required = desired_workers(enterprise)
    if capacity <= 0 or required <= 0:
        return 0.0
    effective = sum(w.effective_labor for w in workers)
    skill = average_skill(workers) or 1.0
    plan = max(0.0, min(1.0, enterprise.plan_ratio))
    output = capacity * min(plan, effective / required) * skill
    if output <= 1e-9:
        return 0.0

    wage_bill = sum(w.wage * w.effective_labor for w in workers)
    depreciation = equipment_value(enterprise, prices) / DEPRECIATION_MONTHS

    if enterprise.industry == Industry.AGRICULTURE:
        fertilizer_cost = 0.0
        if enterprise.use_fertilizer:
            fertilizer_cost = (
                enterprise.land * FERTILIZER_PER_MU * prices.get(Good.FERTILIZER, 0.0)
            )
        return (wage_bill + fertilizer_cost + depreciation) / output

    params = SECTOR_PARAMS[enterprise.industry]
    input_cost = sum(
        ratio * output * prices.get(good, 0.0) for good, ratio in params.inputs.items()
    )
    return (wage_bill + input_cost + depreciation) / output


def unit_cost(
    enterprise: Enterprise,
    prices: Dict[Good, float],
    workers: list[Worker],
    land_price: float = 0.0,
) -> float:
    """用于定价的平均成本。

    土地刻意不计折旧：它是资产，不是会折旧的机器。把土地计入折旧曾让
    粮食成本被算成约 142 元/吨，而市场价只有 100 元/吨，导致食品市场
    冻结并引发饥荒。
    """
    output = enterprise.last_output
    if output <= 1e-9:
        return full_capacity_unit_cost(enterprise, prices, workers)
    wage_bill = sum(w.wage * w.effective_labor for w in workers)
    input_cost = sum(
        qty * prices.get(good, 0.0) for good, qty in enterprise.last_input_used.items()
    )
    depreciation = equipment_value(enterprise, prices) / DEPRECIATION_MONTHS
    return (wage_bill + input_cost + depreciation) / output


def capital_value(
    enterprise: Enterprise,
    prices: Dict[Good, float],
    land_price: float,
) -> float:
    value = enterprise.land * land_price
    for key, count in enterprise.equipment.items():
        if count <= 0:
            continue
        et = EQUIPMENT[key]
        if et.capital_good is not None:
            value += count * et.capital_cost * prices.get(et.capital_good, 0.0)
        value += count * et.building_cost * prices.get(Good.BUILDING, 0.0)
    return value


def inventory_value(enterprise: Enterprise, prices: Dict[Good, float]) -> float:
    return sum(qty * prices.get(good, 0.0) for good, qty in enterprise.inventory.items())


def net_worth(
    enterprise: Enterprise,
    prices: Dict[Good, float],
    land_price: float,
) -> float:
    return (
        enterprise.cash
        + inventory_value(enterprise, prices)
        + capital_value(enterprise, prices, land_price)
        - enterprise.debt
    )


def equipment_cost(equipment_key: str, prices: Dict[Good, float]) -> float:
    et = EQUIPMENT[equipment_key]
    good_cost = 0.0
    if et.capital_good is not None:
        good_cost = et.capital_cost * prices.get(et.capital_good, 0.0)
    building_cost = et.building_cost * prices.get(Good.BUILDING, 0.0)
    return good_cost + building_cost


def representative_roi(
    industry: Industry,
    equipment_key: str,
    prices: Dict[Good, float],
    wage: float,
    land_price: float,
    demand: Optional[float] = None,
) -> float:
    """一台新设备（或一个标准农场）的预期月资本回报率。

    使用成熟熟练度（2.0）和当前价格。这是一个刻意简化的短视 ROI；
    正是这个信号让资本流入农业。
    """
    et = EQUIPMENT[equipment_key]
    params = SECTOR_PARAMS[industry]

    if industry == Industry.AGRICULTURE:
        land = TARGET_CAPITALIST_FARM_MU
        power = et.power
        required = max(1, math.ceil(land / (LAND_PER_WORKER_BASE * (1.0 + power))))
        output = land * BASE_GRAIN_YIELD * FERTILIZER_YIELD_MULTIPLIER * SKILL_MAX
        if demand is not None:
            output = min(output, max(0.0, demand))
        if output <= 1e-9:
            return -1.0
        revenue = output * prices.get(params.output, 0.0)
        fertilizer = land * FERTILIZER_PER_MU * prices.get(Good.FERTILIZER, 0.0)
        wages = required * wage
        capital = land * land_price + equipment_cost(equipment_key, prices)
        profit = revenue - fertilizer - wages
        return profit / capital if capital > 0 else -1.0

    output = et.capacity * SKILL_MAX
    if demand is not None:
        output = min(output, max(0.0, demand))
    if output <= 1e-9:
        return -1.0
    revenue = output * prices.get(params.output, 0.0)
    input_cost = sum(
        ratio * output * prices.get(good, 0.0) for good, ratio in params.inputs.items()
    )
    wages = et.workers * wage
    capital = equipment_cost(equipment_key, prices)
    profit = revenue - input_cost - wages
    return profit / capital if capital > 0 else -1.0
