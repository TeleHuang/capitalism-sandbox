from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from .config import (
    BASE_GRAIN_YIELD,
    DEPRECIATION_MONTHS,
    EQUIPMENT,
    FERTILIZER_COAL_BUFFER_MONTHS,
    FERTILIZER_PER_MU,
    FERTILIZER_YIELD_MULTIPLIER,
    FREE_DEMAND_FACTOR_MAX,
    FREE_DEMAND_FACTOR_MIN,
    FREE_DEMAND_SLOPE,
    FREE_GLUT_COVERAGE,
    FREE_GLUT_SLOPE,
    FREE_MARKUP_INIT_MAX,
    FREE_MARKUP_INIT_MIN,
    FREE_MARKUP_MAX,
    FREE_MARKUP_MIN,
    FREE_MARKUP_SPEED,
    FREE_OBSERVED_WEIGHT,
    FREE_PRICE_CAP_MULT,
    FREE_REF_CORRIDOR,
    INITIAL_PRICES,
    INVESTMENT_HURDLE,
    LAND_PER_WORKER_BASE,
    PRICE_FLOOR,
    SECTOR_PARAMS,
    SKILL_MAX,
    WAGE_BASE,
    WAGE_CAP_MULT,
    WAGE_CASH_DISCOUNT,
    WAGE_CATCHUP_CAP,
    WAGE_CATCHUP_WEIGHT,
    WAGE_COST_OF_LIVING_WEIGHT,
    WAGE_DOWNWARD_SPEED_MULT,
    WAGE_HIRING_PREMIUM,
    WAGE_INFLATION_PASS_THROUGH,
    WAGE_INSTITUTIONAL_CAP,
    WAGE_PROFIT_SLOPE,
    WAGE_SWITCH_THRESHOLD,
    WAGE_TIGHTNESS_SLOPE,
)
from .enums import Good, Industry
from .production import (
    average_skill,
    average_wage,
    capital_value,
    capacity_at_skill_one,
    desired_workers,
    equipment_cost,
    equipment_value,
    farm_requirements,
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
    # 生存工资随食品/住房价格调整，但设 5 倍上限作为防螺旋安全阀。
    # 正式的工资曲线/软价格走廊在 L5/L2 中替换这个临时规则。
    raw = max(WAGE_BASE, subsistence_cost(prices) * 1.1)
    return min(raw, WAGE_BASE * 5.0)


def should_switch(
    current_wage: float,
    best_offer: float,
    threshold: float = WAGE_SWITCH_THRESHOLD,
) -> bool:
    """只有新报价高于现工资 threshold 以上才跳槽。

    旧代码把方向写反，允许工人降薪跳槽；这个函数把语义固定下来。
    """
    return best_offer > current_wage * (1.0 + threshold)


def normal_unit_cost(
    engine: "Engine",
    enterprise: "Enterprise",
    prices: dict[Good, float] | None = None,
    workers: list["Worker"] | None = None,
) -> float:
    """正常产能利用率下的单位成本（full-cost / normal-cost pricing）。

    用户讨论中的成本公式是 ``c_i = w_i l_i + Σ a_ij p_j + F_i / q_i^normal``：
    固定费用按**正常产量**分摊，而不是按当月低利用率分摊。否则需求不足
    → 减产 → 实际单位成本上升 → 成本加成涨价 → 需求更低，会形成虚假的
    成本—价格螺旋（V0.6 自由定价早期版本正是这样把煤/铁推到安全上限）。

    计算口径：
    - 正常产量 = 设备产能 × 平均熟练度（农业 = 土地 × 亩产 × 熟练度，
      施化肥时 ×2）；
    - 正常用工 = 满产所需标准工时工人；工资率取企业在业工人平均工资
      （无工人时取经济平均工资）；
    - 中间投入按正常产量 × 投入系数 × 当前价格；
    - 设备折旧按当前重置价值 / DEPRECIATION_MONTHS；
    - 家庭农场所有者按 WAGE_BASE 计影子工资（不进入任何现金转移）。
    """
    prices = prices if prices is not None else engine.market.reference_prices
    workers = (
        workers
        if workers is not None
        else engine.enterprise_workers(enterprise)
    )
    params = SECTOR_PARAMS[enterprise.industry]
    skill = max(1.0, average_skill(workers)) if workers else 1.0

    if enterprise.industry == Industry.AGRICULTURE:
        if enterprise.land <= 0:
            return 0.0
        output = enterprise.land * BASE_GRAIN_YIELD * skill
        if enterprise.use_fertilizer:
            output *= FERTILIZER_YIELD_MULTIPLIER
        if output <= 1e-9:
            return 0.0
        required, _ = farm_requirements(enterprise)
        required = max(1, required)
        owner_count = (
            sum(
                1
                for worker in workers
                if engine._is_household_farm_owner(enterprise, worker)
            )
            if enterprise.is_household
            else 0
        )
        employee_count = max(0, required - owner_count)
        employee_wages = [
            worker.wage for worker in workers if worker.wage > 0
        ]
        employee_rate = (
            sum(employee_wages) / len(employee_wages)
            if employee_wages
            else engine.average_wage()
        )
        wage_bill = owner_count * WAGE_BASE + employee_count * employee_rate
        input_cost = 0.0
        if enterprise.use_fertilizer:
            input_cost = (
                enterprise.land
                * FERTILIZER_PER_MU
                * prices.get(Good.FERTILIZER, 0.0)
            )
        depreciation = equipment_value(enterprise, prices) / DEPRECIATION_MONTHS
        return (wage_bill + input_cost + depreciation) / output

    capacity = capacity_at_skill_one(enterprise)
    if capacity <= 0:
        return 0.0
    output = capacity * skill
    required = desired_workers(enterprise, plan=1.0)
    if required <= 0 or output <= 1e-9:
        return 0.0
    employee_wages = [worker.wage for worker in workers if worker.wage > 0]
    wage_rate = (
        sum(employee_wages) / len(employee_wages)
        if employee_wages
        else engine.average_wage()
    )
    wage_bill = required * wage_rate
    input_cost = sum(
        ratio * output * prices.get(good, 0.0)
        for good, ratio in params.inputs.items()
    )
    depreciation = equipment_value(enterprise, prices) / DEPRECIATION_MONTHS
    return (wage_bill + input_cost + depreciation) / output


def pricing_unit_cost(
    engine: "Engine",
    enterprise: "Enterprise",
    prices: dict[Good, float] | None = None,
    workers: list["Worker"] | None = None,
) -> float:
    """定价用单位成本；家庭农场加入所有者自有劳动的机会成本。

    自耕农不领现金工资，若直接用现金成本定价，粮食价格会塌到接近 0。
    影子工资只进入定价/价格锚，不进入工资账单、利润或任何现金转移，
    因此不会创造货币。
    """
    prices = prices if prices is not None else engine.market.reference_prices
    workers = (
        workers
        if workers is not None
        else engine.enterprise_workers(enterprise)
    )
    cost = unit_cost(enterprise, prices, workers, engine.land.price)
    if (
        enterprise.is_household
        and enterprise.industry == Industry.AGRICULTURE
        and enterprise.last_output > 1e-9
    ):
        owner_labor = sum(
            worker.effective_labor
            for worker in workers
            if engine._is_household_farm_owner(enterprise, worker)
        )
        if owner_labor > 0:
            cost += owner_labor * WAGE_BASE / enterprise.last_output
    return cost


def wage_target(engine: "Engine", enterprise: "Enterprise") -> float:
    """V0.6 工资目标：生产率分享 + 通胀补偿 + 紧张度 + 制度性追赶。

    ``w_target = WAGE_BASE × A^β × (1+π^e)^α × (1 + tightness + institutional)``

    - ``A``：平滑劳动生产率指数（基期 = 1）；
    - ``β = engine.wage_productivity_share``：生产率分享程度；
    - ``π^e``：月度通胀预期；``α = wage_inflation_pass_through`` 是合同
      指数化程度（古典低、Fordist/MMT 高）；
    - ``tightness``：原工资曲线的失业率项 + 利润分享项；
    - ``institutional``：制度/阶级议价项。真实工资落后于生产率时产生
      “追赶”，生活成本跑赢工资时产生“危机”压力，由
      ``wage_bargain_power`` 放大（古典/维多利亚被压低，Fordist/MMT 较高）。

    该函数只给目标，不直接发钱；实际报价在 ``enterprise_wage_offer``
    中以 ``wage_adjustment_speed`` 向目标部分调整，且工资始终是转移支付，
    不创造货币。
    """
    productivity = max(
        1e-9, float(getattr(engine, "productivity_index", 1.0))
    )
    share = max(
        0.0, float(getattr(engine, "wage_productivity_share", 0.5))
    )
    expected_inflation = float(
        getattr(engine, "inflation_expectations", 0.0)
    )
    pass_through = float(
        getattr(engine, "wage_inflation_pass_through", WAGE_INFLATION_PASS_THROUGH)
    )

    unemployment = getattr(engine, "_wage_unemployment", None)
    if unemployment is None:
        labor_force = engine.labor_force_workers()
        employed = sum(1 for worker in labor_force if worker.employed)
        unemployment = 1.0 - employed / max(1, len(labor_force))
    tightness = WAGE_TIGHTNESS_SLOPE * (0.07 - unemployment)
    if enterprise.last_revenue > 0 and enterprise.last_profit > 0:
        margin = max(
            0.0, min(0.35, enterprise.last_profit / enterprise.last_revenue)
        )
        tightness += WAGE_PROFIT_SLOPE * margin

    # 制度性追赶：用全经济平均工资与 CPI 判断真实工资是否落后。
    cpi = max(1e-6, float(getattr(engine, "cpi", 1.0)))
    wage_index = max(0.0, float(getattr(engine, "wage_index", 1.0)))
    real_wage_index = wage_index / cpi
    catch_up = max(
        0.0,
        min(WAGE_CATCHUP_CAP, productivity - real_wage_index),
    )
    cost_of_living_pressure = max(0.0, min(1.0, cpi / max(wage_index, 1e-9) - 1.0))
    bargain = max(
        0.0, float(getattr(engine, "wage_bargain_power", 0.0))
    )
    institutional = bargain * (
        WAGE_CATCHUP_WEIGHT * catch_up
        + WAGE_COST_OF_LIVING_WEIGHT * cost_of_living_pressure
    )
    institutional = min(WAGE_INSTITUTIONAL_CAP, institutional)

    scale = float(getattr(engine, "wage_floor_scale", 1.0))
    base = (
        WAGE_BASE
        * scale
        * (productivity ** share)
        * max(0.0, 1.0 + expected_inflation) ** pass_through
    )
    return base * max(0.0, 1.0 + tightness + institutional)


def enterprise_wage_offer(engine: "Engine", enterprise: "Enterprise") -> float:
    """企业工资报价：向 ``wage_target`` 部分调整，并保留短期摩擦。"""
    workers = engine.enterprise_workers(enterprise)
    scale = float(getattr(engine, "wage_floor_scale", 1.0))
    floor = wage_floor(engine.market.reference_prices) * scale
    cap = WAGE_BASE * WAGE_CAP_MULT
    target = wage_target(engine, enterprise)

    speed = max(
        0.0,
        min(1.0, float(getattr(engine, "wage_adjustment_speed", 0.15))),
    )
    state = float(getattr(enterprise, "wage_offer", 0.0))
    if state <= 0.0:
        # 新企业/首次报价没有历史状态：直接落到目标，避免从 0 爬升。
        state = target
    else:
        # 向上粘性、向下更快：失业上升时工资能及时回落。
        step_speed = speed
        if target < state:
            step_speed = min(
                1.0, speed * WAGE_DOWNWARD_SPEED_MULT
            )
        state += step_speed * (target - state)
    # 状态也夹在生存下限与绝对上限之间；否则下限会把报价反复拉回，
    # 而状态仍停在低处，形成虚假的长期滞后。
    state = min(max(state, floor), cap)
    enterprise.wage_offer = state

    offer = state
    if len(workers) < desired_workers(enterprise):
        offer *= WAGE_HIRING_PREMIUM
    wage_bill = sum(w.wage * w.effective_labor for w in workers)
    if enterprise.cash < max(wage_bill * 2.0, offer * 2.0):
        offer *= WAGE_CASH_DISCOUNT
    return min(max(floor, round(offer, 2)), cap)


def _inventory_months(enterprise: "Enterprise", good: Good) -> float:
    """库存覆盖月数；服务业/无库存目标部门返回 0。"""
    inventory = enterprise.inv(good)
    sales = enterprise.smoothed_sales
    target = enterprise.target_inventory_months
    if sales > 1e-6:
        return inventory / sales
    if inventory <= 1e-9:
        return 0.0
    return max(target, 0.5) * 2.0


def _ensure_free_markup(
    engine: "Engine", enterprise: "Enterprise", cost: float, ref: float
) -> None:
    """自由成本加成制度：首次定价按当前 ref/cost 校准 markup。

    初始价格结构（煤/铁/钢/布的历史价格）与成本加成的差距很大；
    若从统一 15% 起步，会在头一年制造一次性的价格水平跳变。首次报价
    一次性校准到 ref，之后 markup 围绕该正常加成率波动。
    """
    if enterprise.markup_initialized or cost <= 1e-9:
        return
    normal = min(
        FREE_MARKUP_INIT_MAX,
        max(FREE_MARKUP_INIT_MIN, ref / cost - 1.0),
    )
    enterprise.markup = normal
    enterprise.markup_normal = normal
    enterprise.markup_initialized = True


def free_price_target(
    engine: "Engine", enterprise: "Enterprise", cost: float = 0.0
) -> float:
    """free 制度的目标卖价（未夹在可成交走廊内）。

    ``p* = (1+markup) × cost × demand_factor``，再与上月成交价弱锚定。
    markup 每月按库存缺口和未成交/未售出比例慢速调整。该函数会更新
    enterprise.markup；参数 ``cost`` 缺省时用定价成本（含自耕农影子工资）。
    """
    out = SECTOR_PARAMS[enterprise.industry].output
    if cost <= 0:
        cost = normal_unit_cost(engine, enterprise)
        if cost <= 1e-9:
            cost = pricing_unit_cost(engine, enterprise)
    ref = engine.market.reference_prices.get(out, 1.0)
    _ensure_free_markup(engine, enterprise, cost, ref)

    target_months = enterprise.target_inventory_months
    if target_months > 0:
        months = _inventory_months(enterprise, out)
        gap = (target_months - months) / max(target_months, 1.0)
    else:
        # 服务不可储存：没有库存目标，只由未成交需求/未售出服务驱动。
        gap = 0.0

    history = engine.market.history.get(out, {})
    demand = max(0.0, history.get("demand", 0.0))
    unmet_ratio = (
        min(1.0, max(0.0, history.get("unmet", 0.0)) / demand)
        if demand > 1e-9 else 0.0
    )
    volume = max(0.0, history.get("volume", 0.0))
    unsold = max(0.0, history.get("unsold", 0.0))
    unsold_ratio = (
        min(1.0, unsold / (volume + unsold))
        if volume + unsold > 1e-9 else 0.0
    )

    adjustment = gap + 0.5 * unmet_ratio - 0.25 * unsold_ratio
    # markup 围绕校准后的正常加成率波动，而不是永久棘轮：
    # 持久短缺给出有界溢价（最高 2× 正常加成），短缺消失后回落。
    normal = max(FREE_MARKUP_MIN, enterprise.markup_normal)
    desired_markup = normal * min(2.0, max(0.5, 1.0 + adjustment))
    desired_markup = min(FREE_MARKUP_MAX, max(FREE_MARKUP_MIN, desired_markup))
    enterprise.markup += FREE_MARKUP_SPEED * (
        desired_markup - enterprise.markup
    )
    enterprise.markup = min(
        FREE_MARKUP_MAX, max(FREE_MARKUP_MIN, enterprise.markup)
    )
    demand_factor = 1.0 + (
        FREE_DEMAND_SLOPE * unmet_ratio - FREE_GLUT_SLOPE * unsold_ratio
    )
    demand_factor = min(
        FREE_DEMAND_FACTOR_MAX,
        max(FREE_DEMAND_FACTOR_MIN, demand_factor),
    )
    target = cost * (1.0 + enterprise.markup) * demand_factor

    observed = history.get("observed", 0.0)
    if observed > 0:
        target = (
            (1.0 - FREE_OBSERVED_WEIGHT) * target
            + FREE_OBSERVED_WEIGHT * observed
        )
    return max(PRICE_FLOOR, target)


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

    if getattr(engine, "price_regime", "band") == "free":
        # V0.6：成本加成目标价 + 需求/供给调整 + 成交价锚定。
        # 没有成本下限；只保留绝对安全轨。卖价再夹在参考价 ±3% 内，
        # 保证买卖价能够穿价成交；价格方向由参考价路径逐月体现。
        pricing_cost = normal_unit_cost(
            engine, enterprise, engine.market.reference_prices, workers
        )
        if pricing_cost <= 1e-9:
            pricing_cost = pricing_unit_cost(
                engine, enterprise, engine.market.reference_prices, workers
            )
        if pricing_cost > 1e-9:
            target = free_price_target(engine, enterprise, pricing_cost)
        else:
            # 没有成本信号：退回去年成交价/参考价；不再人为设成本底。
            observed = engine.market.history[out].get("observed", 0.0)
            target = observed if observed > 0 else ref
        price = min(
            max(target, ref * (1.0 - FREE_REF_CORRIDOR)),
            ref * (1.0 + FREE_REF_CORRIDOR),
        )
        price = min(
            price,
            INITIAL_PRICES[out] * FREE_PRICE_CAP_MULT,
        )
        return max(PRICE_FLOOR, price)

    if getattr(engine, "price_regime", "band") == "markup" and cost > 0:
        # L2：成本加成 + 库存调整 + 软走廊。
        target_months = max(enterprise.target_inventory_months, 0.5)
        gap = (target_months - months) / max(target_months, 1.0)
        enterprise.markup = min(
            0.60, max(0.02, enterprise.markup + 0.03 * gap)
        )
        price = cost * (1.0 + enterprise.markup)
        price = max(price, cost * 0.5)
        price = min(price, cost * 2.5)
        # 过渡期限制单次相对参考价的跳幅，避免价格战/一步到位。
        price = min(price, ref * 1.30)
        return max(0.01, price)

    if getattr(engine, "price_regime", "band") == "markup_soft":
        # L2 折中：成本加成给出目标价，但目标价被软走廊锚定在参考价附近。
        # 它保留成本信号（避免自由 markup 在固定篮子需求下崩溃），同时
        # 用 0.85–1.15×ref 的走廊阻止价格战和通胀螺旋。
        if cost <= 0:
            # 没有可用成本信号时退回参考价，不再尝试加成。
            return max(0.01, ref)
        target_months = max(enterprise.target_inventory_months, 0.5)
        gap = (target_months - months) / target_months
        # 慢速调整：按库存缺口每月调整 0.01×gap，避免单月跳价。
        enterprise.markup = min(
            0.40, max(0.02, enterprise.markup + 0.01 * gap)
        )
        desired = cost * (1.0 + enterprise.markup)
        # 先限制在成本带内，再套参考价软走廊。成本带放在走廊内侧，
        # 否则成本极低的行业会把卖价压到走廊下沿以下，使“软走廊”
        # 名存实亡。
        price = min(max(desired, cost * 0.80), cost * 2.0)
        price = min(max(price, ref * 0.85), ref * 1.15)

        # 市场出清护栏（仅 markup_soft）：买方报价通常在参考价的
        # 1.02–1.06 倍，卖价高于该区间会整月无成交；固定篮子下
        # 一次食品市场冻结就足以引发饥荒。因此库存正常时把卖价
        # 锚回 ref±2%，只有库存极高/极低时才向宽走廊的两端让价/抬价。
        if months > 3.0:
            # 高库存：允许让价，但 0.90×ref 已足以清库存；更深的
            # 折价会侵蚀行业现金流（240 月古典测试中 0.85 下沿造成死亡）。
            lo, hi = ref * 0.90, ref * 0.98
        elif months < 0.5 and sales > 1e-6:
            lo, hi = ref * 1.00, ref * (1.05 if out == Good.FOOD else 1.04)
        else:
            lo, hi = ref * 0.98, ref * 1.02
        price = min(max(price, lo), hi)
        # 成本下限在软走廊内不可行（cost×0.8 > 1.15×ref）时，
        # 优先保证卖价处于可成交的走廊内。
        price = max(price, min(cost * 0.80, ref * 1.15))
        return max(0.01, price)

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
            # 目标库存 = 本月用量 + 半个月安全库存。
            target = enterprise.land * FERTILIZER_PER_MU * 1.5
            needed = target - enterprise.inv(Good.FERTILIZER)
            if needed > 1e-9:
                needs[Good.FERTILIZER] = needed
        return needs

    plan = max(0.0, min(1.0, enterprise.plan_ratio))
    workers = engine.enterprise_workers(enterprise)
    skill = sum(w.skill for w in workers) / max(len(workers), 1)
    expected_output = capacity_at_skill_one(enterprise) * plan * skill
    for good, ratio in params.inputs.items():
        target = expected_output * ratio
        # 化肥厂只有煤一种投入，且停炉后恢复成本高；保留更厚的煤库存。
        safety_months = (
            FERTILIZER_COAL_BUFFER_MONTHS
            if enterprise.industry == Industry.FERTILIZER_FACTORY
            else 0.5
        )
        safety = safety_months * target
        needed = target + safety - enterprise.inv(good)
        if needed > 1e-9:
            needs[good] = needed
    return needs


def best_equipment_choice(
    engine: "Engine",
    industry: Industry,
    budget: Optional[float] = None,
    demand_override: Optional[float] = None,
) -> Optional[tuple[str, float]]:
    prices = engine.market.reference_prices
    wage = engine.average_wage()
    land_price = engine.land.price
    params = SECTOR_PARAMS[industry]
    total_demand = engine.market.history[params.output].get("demand", 0.0)
    if industry == Industry.AGRICULTURE:
        # 农业按全社会食品需求评估；不要按单个自耕农的份额，
        # 否则标准 100 亩农场会被 600 个小农的份额压成负 ROI。
        demand = total_demand
    else:
        active = max(1, len(engine.active_enterprises(industry)))
        demand = total_demand / active
    if demand_override is not None:
        demand = demand_override
    candidates = []
    for key in params.equipment:
        et = EQUIPMENT[key]
        if et.capital_good is None or et.build_months <= 0:
            continue
        cost = equipment_cost(key, prices)
        if budget is not None and cost > budget:
            continue
        roi = representative_roi(
            industry, key, prices, wage, land_price, demand=demand
        )
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
    if enterprise.industry == Industry.FERTILIZER_FACTORY:
        pending = sum(
            project.quantity
            for project in engine.projects.values()
            if project.active
            and project.enterprise_id == enterprise.id
            and project.industry == Industry.FERTILIZER_FACTORY
        )
        if enterprise.total_equipment() + pending >= 2:
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
