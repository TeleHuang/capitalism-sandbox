"""V0.6 收入依赖的家庭需求（Stone-Geary / 线性支出体系）。

旧版家庭需求是固定实物配额（粮食 0.1 吨、布 1 件、住房 0.2 平方米、
服务 0.5 单位），所有目标都会饱和，食品占比长期锁死在高位。V0.6 把
消费拆成两层：

1. **生存层**：``gamma`` 是每个成年人每月的最低实物量（粮食 0.1 吨），
   无论预算多少都会保留这个目标；市场成交仍受现金约束，因此饥荒机制
   不受影响。
2. **温饱以上层**：可支配预算超过生存篮子成本的部分 ``E``，按
   **收入依赖的边际预算份额** ``beta(x)`` 分配到口粮、肉类、衣物、住房
   和服务。``x = 消费预算 / 生存篮子成本`` 是实际收入代理；份额在
   低/中/高三个收入锚点之间按对数收入插值。

需求函数（每个成年人）：

.. math::

    q_i = \\gamma_i + \\beta_i(x) \\cdot E / p_i,
    \\quad E = \\max(0, M - \\sum_j p_j \\gamma_j)

其中 ``M`` 是本月可支配消费预算，``beta_i`` 在每个锚点归一化为 1。
食品的边际份额随收入下降（Engel 定律），服务的边际份额最高且随收入
上升；肉类只在温饱以上出现，是食品质量阶梯。衣物/住房/服务没有硬性
饱和点，只设很高的安全上限（见 ``DemandConfig``），防止极端财富把
单一商品需求推到不合理的数量级。

预算本身仍来自家庭现金：``M = min(cash, max(floor, propensity * cash))``。
不创造货币；未花完的部分留在家庭现金里。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

from .enums import Good

# 消费篮子的商品顺序：口粮、肉类、衣物、住房（建筑）、服务。
BUNDLE: Tuple[Good, ...] = (
    Good.FOOD,
    Good.MEAT,
    Good.CLOTH,
    Good.BUILDING,
    Good.SERVICE,
)

# 统计/份额展示顺序。
BUNDLE_LABELS = {
    Good.FOOD: "food",
    Good.MEAT: "meat",
    Good.CLOTH: "cloth",
    Good.BUILDING: "housing",
    Good.SERVICE: "service",
}


@dataclass(frozen=True)
class DemandConfig:
    """家庭需求参数（V0.6）。

    ``income_anchors`` 以“消费预算 / 生存篮子成本”为单位：
    1.5 ≈ 刚过温饱、3.0 ≈ 中等收入、6.0 ≈ 高收入。
    边际预算份额在三个锚点之间按对数收入线性插值，并在每个锚点
    归一化，保证预算恒等式。
    """

    # --- 生存层（每人每月） ----------------------------------------
    food_subsistence: float = 0.10          # 吨；与 FOOD_PER_WORKER 一致
    meat_subsistence: float = 0.0           # 肉类不是生存品
    cloth_subsistence: float = 0.50         # 件
    housing_subsistence: float = 0.10       # 平方米
    # 服务的最低消费量（非正规照料、家务、集市服务等）。保留一个
    # 正的服务底线，才能在工业裁员时维持服务自雇的吸收能力；高收入
    # 家庭再按收入弹性追加服务消费。
    service_subsistence: float = 0.35       # 单位

    # --- 预算 ------------------------------------------------------
    # 家庭本月消费预算 ≈ 当月收入 × income_spending_share，并至少尝试
    # 维持 consumption_floor_ratio 倍生存篮子；两者都不超过家庭现金。
    # 用“收入流”而不是“现金存量”作为预算基准，避免家庭把历史储蓄
    # 不断转化为需求、造成需求拉动型通胀；未花完的收入留在现金里。
    income_spending_share: float = 0.90
    # 即使当期收入很低，也至少尝试维持 1.45 倍生存篮子（市场成交仍受
    # 现金硬约束）。这使初始工资 20 元、粮价 100 元时食品占比约 60%。
    consumption_floor_ratio: float = 1.45
    # 资本家消费预算上限（× 生存篮子成本）：高收入但非无限，
    # 避免 10 万现金的董事把需求推到离谱数量。
    capitalist_budget_multiple: float = 4.0

    # --- 收入锚点与边际预算份额（低/中/高） ------------------------
    # 口粮完全饱和：温饱以上新增支出不流向口粮，而是流向衣物、住房、
    # 服务和肉类。这样既符合 Engel 定律，也避免与饲料粮争夺口粮、
    # 推高粮价。肉类在低收入锚点为 0，只有收入超过温饱线后才出现。
    income_anchors: Tuple[float, float, float] = (1.5, 3.0, 6.0)
    food_marginal_shares: Tuple[float, float, float] = (0.00, 0.00, 0.00)
    meat_marginal_shares: Tuple[float, float, float] = (0.00, 0.10, 0.14)
    cloth_marginal_shares: Tuple[float, float, float] = (0.13, 0.13, 0.13)
    housing_marginal_shares: Tuple[float, float, float] = (0.22, 0.22, 0.22)
    service_marginal_shares: Tuple[float, float, float] = (0.65, 0.55, 0.51)

    # --- 安全上限（不是“饱和点”，只防极端财富） --------------------
    food_cap: float = 0.25                  # 吨 / 月
    meat_cap: float = 0.05                  # 吨 / 月
    cloth_cap: float = 10.0                 # 件 / 月
    housing_cap: float = 2.0                # 平方米 / 月
    service_cap: float = 8.0                # 单位 / 月

    def marginal_share_table(self) -> Dict[Good, Tuple[float, float, float]]:
        return {
            Good.FOOD: self.food_marginal_shares,
            Good.MEAT: self.meat_marginal_shares,
            Good.CLOTH: self.cloth_marginal_shares,
            Good.BUILDING: self.housing_marginal_shares,
            Good.SERVICE: self.service_marginal_shares,
        }

    def subsistence_quantities(self) -> Dict[Good, float]:
        return {
            Good.FOOD: self.food_subsistence,
            Good.MEAT: self.meat_subsistence,
            Good.CLOTH: self.cloth_subsistence,
            Good.BUILDING: self.housing_subsistence,
            Good.SERVICE: self.service_subsistence,
        }

    def quantity_caps(self) -> Dict[Good, float]:
        return {
            Good.FOOD: self.food_cap,
            Good.MEAT: self.meat_cap,
            Good.CLOTH: self.cloth_cap,
            Good.BUILDING: self.housing_cap,
            Good.SERVICE: self.service_cap,
        }


DEFAULT_DEMAND = DemandConfig()


def _price(prices: Dict[Good, float], good: Good) -> float:
    return max(prices.get(good, 0.0), 1e-9)


def subsistence_cost(
    prices: Dict[Good, float], config: DemandConfig = DEFAULT_DEMAND
) -> float:
    """一个成年人每月生存篮子的现金成本。"""
    quantities = config.subsistence_quantities()
    return sum(_price(prices, good) * quantities[good] for good in BUNDLE)


def consumption_budget(
    cash: float,
    prices: Dict[Good, float],
    income: float = 0.0,
    config: DemandConfig = DEFAULT_DEMAND,
) -> float:
    """家庭本月可支配消费预算（元）。

    以当期收入流为基准（``income * income_spending_share``），而不是
    现金存量；随后用 1.45 倍生存篮子保底，并受实际现金约束。这样
    历史储蓄不会每月自动转化为新的需求，也不会创造货币。
    """
    cash = max(0.0, cash)
    if cash <= 0.0:
        return 0.0
    floor = subsistence_cost(prices, config) * config.consumption_floor_ratio
    desired = max(floor, max(0.0, income) * config.income_spending_share)
    return min(cash, desired)


def capitalist_consumption_budget(
    cash: float,
    prices: Dict[Good, float],
    min_consumption: float,
    consumption_rate: float,
    config: DemandConfig = DEFAULT_DEMAND,
) -> float:
    """资本家消费预算：按现金比例，但受生存篮子倍数上限约束。"""
    cash = max(0.0, cash)
    if cash <= 0.0:
        return 0.0
    cap = subsistence_cost(prices, config) * config.capitalist_budget_multiple
    desired = max(min_consumption, cash * consumption_rate)
    return max(0.0, min(cash, desired, cap))


def _lerp(a: float, b: float, weight: float) -> float:
    return a + (b - a) * weight


def _interpolate(
    values: Tuple[float, float, float],
    anchors: Tuple[float, float, float],
    real_income: float,
) -> float:
    """在三个收入锚点之间按 log(x) 线性插值。"""
    x = max(1e-9, real_income)
    if x <= anchors[0]:
        return values[0]
    if x >= anchors[2]:
        return values[2]
    if x <= anchors[1]:
        weight = math.log(x / anchors[0]) / math.log(anchors[1] / anchors[0])
        return _lerp(values[0], values[1], weight)
    weight = math.log(x / anchors[1]) / math.log(anchors[2] / anchors[1])
    return _lerp(values[1], values[2], weight)


def marginal_budget_shares(
    real_income: float, config: DemandConfig = DEFAULT_DEMAND
) -> Dict[Good, float]:
    """收入依赖的边际预算份额，归一化后之和为 1。"""
    raw = {
        good: _interpolate(values, config.income_anchors, real_income)
        for good, values in config.marginal_share_table().items()
    }
    total = sum(raw.values())
    if total <= 1e-12:
        return {good: 0.0 for good in BUNDLE}
    return {good: value / total for good, value in raw.items()}


def demand_targets(
    budget: float,
    prices: Dict[Good, float],
    config: DemandConfig = DEFAULT_DEMAND,
) -> Dict[Good, float]:
    """给定消费预算，返回成年人每月目标消费量（实物单位）。

    目标量是“想消费多少”，不是“能买到多少”；实际购买仍由
    ``Market`` 的家庭现金约束截断。因此现金为 0 时目标仍保留生存
    篮子，库存中的口粮仍可被消费。
    """
    subsistence = config.subsistence_quantities()
    caps = config.quantity_caps()
    base_cost = subsistence_cost(prices, config)
    budget = max(0.0, budget)
    extra = max(0.0, budget - base_cost)
    real_income = budget / max(base_cost, 1e-9)
    shares = marginal_budget_shares(real_income, config)
    targets: Dict[Good, float] = {}
    for good in BUNDLE:
        price = _price(prices, good)
        quantity = subsistence[good] + shares[good] * extra / price
        targets[good] = max(0.0, min(caps[good], quantity))
    # 口粮的生存底线不能被预算或上限逻辑抹掉；上限高于 0.1，
    # 这里只是显式保护饥饿判定所依赖的 0.1 吨/月。
    targets[Good.FOOD] = max(targets[Good.FOOD], config.food_subsistence)
    return targets


def demand_shares(
    targets: Dict[Good, float],
    prices: Dict[Good, float],
) -> Dict[str, float]:
    """把目标/实际消费量按参考价格折算成预算份额（用于统计）。"""
    values = {
        good: targets.get(good, 0.0) * _price(prices, good) for good in BUNDLE
    }
    total = sum(values.values())
    if total <= 1e-12:
        shares = {label: 0.0 for label in BUNDLE_LABELS.values()}
        shares["food_total"] = 0.0
        return shares
    shares = {
        BUNDLE_LABELS[good]: values[good] / total for good in BUNDLE
    }
    food_total = values[Good.FOOD] + values[Good.MEAT]
    shares["food_total"] = food_total / total
    return shares


def real_wage_proxy(
    average_wage: float,
    prices: Dict[Good, float],
    config: DemandConfig = DEFAULT_DEMAND,
) -> float:
    """实际工资代理：月名义工资可购买多少个生存篮子。"""
    return max(0.0, average_wage) / max(subsistence_cost(prices, config), 1e-9)


def consumer_price_index(
    prices: Dict[Good, float],
    initial_prices: Dict[Good, float],
    config: DemandConfig = DEFAULT_DEMAND,
) -> float:
    """以生存篮子为权重的消费者价格指数（初始=100）。"""
    initial = subsistence_cost(initial_prices, config)
    if initial <= 1e-12:
        return 100.0
    return 100.0 * subsistence_cost(prices, config) / initial
