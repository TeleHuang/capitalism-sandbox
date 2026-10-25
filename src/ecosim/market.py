from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .config import (
    FREE_COST_ANCHOR_WEIGHT,
    FREE_GLUT_COVERAGE,
    FREE_GLUT_SLOPE,
    FREE_GLUT_STEP_MAX,
    FREE_GLUT_STEP_MIN,
    FREE_OBSERVED_ANCHOR_WEIGHT,
    FREE_PRICE_CAP_MULT,
    FREE_REF_ANCHOR_WEIGHT,
    FREE_SHORTAGE_COVERAGE,
    FREE_SHORTAGE_SLOPE,
    FREE_SHORTAGE_STEP_MAX,
    FREE_SHORTAGE_STEP_MIN,
    INITIAL_PRICES,
    PRICE_FLOOR,
    PRICE_STEP,
    SECTOR_PARAMS,
)
from .enums import Good
from .government import Government
from .models import (
    Capitalist,
    Enterprise,
    FoodReserve,
    InvestmentProject,
    Worker,
)


@dataclass
class Order:
    agent: Any
    good: Good
    side: str
    quantity: float
    price: float


@dataclass
class Transaction:
    seller: Any
    buyer: Any
    good: Good
    quantity: float
    price: float


class Market:
    """带参考价试探过程的双边拍卖。

    订单按“最高买价 / 最低卖价”撮合，成交价取双方报价平均值。
    如果订单簿有交叉意愿但没有重叠价格，则不成交；下个月参考价按
    超额需求调整。这与 V0.1 的关键区别是：V0.1 在买卖价不重叠时
    会把价格永久冻结。
    """

    def __init__(self, prices: Dict[Good, float]):
        self.reference_prices = dict(prices)
        # 价格制度由 Engine 每月同步；只有 "free" 会改变参考价路径。
        self.price_regime = "band"
        # free 制度的价格锚：由 Engine 在撮合前按行业单位成本/markup
        # 中位数写入。成本锚只用于定价，不构成价格下限。
        self.cost_anchors: Dict[Good, float] = {}
        self.markup_anchors: Dict[Good, float] = {}
        self.orders_buy: Dict[Good, List[Order]] = {g: [] for g in Good}
        self.orders_sell: Dict[Good, List[Order]] = {g: [] for g in Good}
        self.history: Dict[Good, Dict[str, float]] = {
            g: {
                "volume": 0.0,
                "price": self.reference_prices[g],
                "observed": 0.0,
                "demand": 0.0,
                "supply": 0.0,
                "unsold": 0.0,
                "unmet": 0.0,
            }
            for g in Good
        }
        self.consumption_spending = 0.0
        self.investment_spending = 0.0
        self.government_spending = 0.0
        # 基于成本的安全轨，由引擎更新。它们不能替代竞争，但可以
        # 防止薄市场把价格推到重置成本的数倍，或砸到成本的零头。

        self.ceilings: Dict[Good, float] = {}
        self.floors: Dict[Good, float] = {}

    # ------------------------------------------------------------------
    # 挂单
    # ------------------------------------------------------------------
    def submit_buy(self, agent: Any, good: Good, quantity: float, price: float) -> None:
        if quantity > 1e-9 and price > 0:
            self.orders_buy[good].append(Order(agent, good, "buy", quantity, price))

    def submit_sell(self, agent: Any, good: Good, quantity: float, price: float) -> None:
        if quantity > 1e-9 and price > 0:
            self.orders_sell[good].append(Order(agent, good, "sell", quantity, price))

    def clear(self) -> None:
        for g in Good:
            self.orders_buy[g].clear()
            self.orders_sell[g].clear()

    # ------------------------------------------------------------------
    # 撮合
    # ------------------------------------------------------------------
    def match(self) -> List[Transaction]:
        transactions: List[Transaction] = []

        for good in Good:
            buys = sorted(self.orders_buy[good], key=lambda o: o.price, reverse=True)
            sells = sorted(self.orders_sell[good], key=lambda o: o.price)

            demand = sum(o.quantity for o in buys)
            supply = sum(o.quantity for o in sells)
            volume = 0.0
            value = 0.0

            while buys and sells:
                b = buys[0]
                s = sells[0]
                if b.price + 1e-9 < s.price:
                    break

                deal_price = (b.price + s.price) / 2.0
                deal_volume = min(b.quantity, s.quantity)

                # 买方预算约束：绝不允许透支。
                buyer_cash = max(getattr(b.agent, "cash", 0.0), 0.0)
                if buyer_cash < deal_price * deal_volume:
                    deal_volume = buyer_cash / deal_price if deal_price > 0 else 0.0

                # 卖方库存约束（防御性；每个卖方只挂一张单）。
                if isinstance(s.agent, Enterprise):
                    deal_volume = min(deal_volume, s.agent.inv(good))
                elif isinstance(s.agent, FoodReserve):
                    deal_volume = min(deal_volume, s.agent.food)

                if deal_volume <= 1e-9:
                    if buyer_cash <= 1e-9:
                        buys.pop(0)
                    else:
                        sells.pop(0)
                    continue

                amount = deal_price * deal_volume
                b.agent.cash -= amount
                s.agent.cash += amount
                self._receive_good(b.agent, good, deal_volume)
                self._deliver_good(s.agent, good, deal_volume)

                if isinstance(b.agent, (Worker, Capitalist)):
                    self.consumption_spending += amount
                if isinstance(b.agent, InvestmentProject):
                    self.investment_spending += amount
                if isinstance(b.agent, Government):
                    self.government_spending += amount
                if isinstance(b.agent, Enterprise):
                    inputs = SECTOR_PARAMS[b.agent.industry].inputs
                    if good in inputs:
                        b.agent.month_input_cost += amount
                if isinstance(s.agent, Enterprise):
                    s.agent.month_revenue += amount
                    s.agent.last_sales[good] = s.agent.last_sales.get(good, 0.0) + deal_volume
                if isinstance(b.agent, InvestmentProject):
                    b.agent.received[good] = b.agent.received.get(good, 0.0) + deal_volume

                transactions.append(Transaction(s.agent, b.agent, good, deal_volume, deal_price))
                b.quantity -= deal_volume
                s.quantity -= deal_volume
                volume += deal_volume
                value += amount

                if b.quantity <= 1e-9:
                    buys.pop(0)
                if s.quantity <= 1e-9:
                    sells.pop(0)

            observed = value / volume if volume > 1e-9 else 0.0
            self._update_reference_price(good, demand, supply, volume, value, buys, sells)
            self.history[good] = {
                "volume": volume,
                "price": self.reference_prices[good],
                "observed": observed,
                "demand": demand,
                "supply": supply,
                "unsold": sum(o.quantity for o in sells),
                "unmet": sum(o.quantity for o in buys),
            }

        self.clear()
        return transactions

    def _update_reference_price(
        self,
        good: Good,
        demand: float,
        supply: float,
        volume: float,
        value: float,
        buys: List[Order],
        sells: List[Order],
    ) -> None:
        if self.price_regime == "free":
            self._update_free_price(
                good, demand, supply, volume, value, buys, sells
            )
            return

        old = self.reference_prices[good]
        if volume > 1e-9:
            observed = value / volume
            new = 0.7 * old + 0.3 * observed
        else:
            new = old

        imbalance = (demand - supply) / max(demand, supply, 1.0)
        imbalance = max(-1.0, min(1.0, imbalance))
        new *= 1.0 + PRICE_STEP * imbalance

        # 如果一侧完全为空，让价格信号略强一些。
        if demand > 1e-9 and supply <= 1e-9:
            new *= 1.0 + PRICE_STEP
        elif supply > 1e-9 and demand <= 1e-9:
            new *= 1.0 - PRICE_STEP

        floor = self.floors.get(good)
        ceiling = self.ceilings.get(good)
        if floor is not None:
            new = max(new, floor)
        if ceiling is not None:
            new = min(new, ceiling)
        self.reference_prices[good] = max(PRICE_FLOOR, new)

    def _update_free_price(
        self,
        good: Good,
        demand: float,
        supply: float,
        volume: float,
        value: float,
        buys: List[Order],
        sells: List[Order],
    ) -> None:
        """自由成本加成制度的参考价路径。

        ``new = w_cost × (1+markup)×unit_cost + w_obs × 成交价 + w_ref × old``
        再叠加需求/供给方向调整：

        - 短缺（有未成交买单或可售库存 <1 个月）：每月 +4%..+25%；
        - 过剩（无未成交买单且可售库存 >3 个月）：每月 -2%..-12%；
        - 其余：只做成本/成交/惯性混合。

        成本锚是定价信号，不是价格下限：当成本高于参考价时参考价逐步
        上调，成本低于参考价时逐步下调；企业可以在亏损价格下销售、
        减产或退出。最后只夹在绝对安全轨内。
        """
        old = self.reference_prices[good]
        observed = value / volume if volume > 1e-9 else 0.0
        cost = self.cost_anchors.get(good, 0.0)
        markup = self.markup_anchors.get(good, 0.15)
        unmet = sum(order.quantity for order in buys)
        unsold = sum(order.quantity for order in sells)
        coverage = (volume + unsold) / max(demand, 1e-9)

        if demand <= 1e-9 and coverage <= 0.0:
            new = old
        else:
            if cost > 1e-9:
                cost_target = cost * (1.0 + markup)
                observed_anchor = observed if observed > 0 else old
                new = (
                    FREE_COST_ANCHOR_WEIGHT * cost_target
                    + FREE_OBSERVED_ANCHOR_WEIGHT * observed_anchor
                    + FREE_REF_ANCHOR_WEIGHT * old
                )
            elif observed > 0:
                new = (
                    (1.0 - FREE_REF_ANCHOR_WEIGHT) * observed
                    + FREE_REF_ANCHOR_WEIGHT * old
                )
            else:
                new = old

            shortage = unmet / max(demand, 1e-9)
            if unmet > 1e-9 or (
                demand > 1e-9 and coverage < FREE_SHORTAGE_COVERAGE
            ):
                strength = max(
                    min(1.0, shortage),
                    max(0.0, 1.0 - coverage),
                )
                step = min(
                    FREE_SHORTAGE_STEP_MAX,
                    FREE_SHORTAGE_STEP_MIN + FREE_SHORTAGE_SLOPE * strength,
                )
                new *= 1.0 + step
            elif unmet <= 1e-9 and coverage > FREE_GLUT_COVERAGE:
                strength = min(
                    1.0,
                    (coverage - FREE_GLUT_COVERAGE) / FREE_GLUT_COVERAGE,
                )
                step = min(
                    FREE_GLUT_STEP_MAX,
                    FREE_GLUT_STEP_MIN + FREE_GLUT_SLOPE * strength,
                )
                new *= 1.0 - step

        cap = INITIAL_PRICES[good] * FREE_PRICE_CAP_MULT
        new = min(max(PRICE_FLOOR, new), cap)
        floor = self.floors.get(good)
        ceiling = self.ceilings.get(good)
        if floor is not None:
            new = max(new, floor)
        if ceiling is not None:
            new = min(new, ceiling)
        self.reference_prices[good] = max(PRICE_FLOOR, new)

    # ------------------------------------------------------------------
    # 商品交割
    # ------------------------------------------------------------------
    @staticmethod
    def _receive_good(agent: Any, good: Good, quantity: float) -> None:
        if isinstance(agent, (Worker, Capitalist)):
            if good == Good.FOOD:
                agent.food += quantity
            elif good == Good.MEAT:
                agent.meat += quantity
            elif good == Good.CLOTH:
                agent.cloth += quantity
            elif good == Good.BUILDING:
                agent.housing += quantity
            elif good == Good.SERVICE:
                agent.service += quantity
            return
        if isinstance(agent, Government):
            agent.inventory[good] = agent.inventory.get(good, 0.0) + quantity
            return
        if isinstance(agent, FoodReserve):
            if good == Good.FOOD:
                agent.food += quantity
            return
        if isinstance(agent, (Enterprise, InvestmentProject)):
            agent.inventory[good] = agent.inventory.get(good, 0.0) + quantity

    @staticmethod
    def _deliver_good(agent: Any, good: Good, quantity: float) -> None:
        if isinstance(agent, Enterprise):
            agent.inventory[good] = max(0.0, agent.inventory.get(good, 0.0) - quantity)
        elif isinstance(agent, FoodReserve) and good == Good.FOOD:
            agent.food = max(0.0, agent.food - quantity)
