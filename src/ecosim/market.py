from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .config import PRICE_FLOOR, PRICE_STEP, SECTOR_PARAMS
from .enums import Good
from .models import Capitalist, Enterprise, InvestmentProject, Worker


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
    """A double auction with a reference-price tatonnement.

    Orders are matched highest-bid / lowest-ask at the average price.  If the
    book is crossed but not overlapping there is no trade, and the reference
    price moves next month according to excess demand.  This is the key
    difference from V0.1, where a non-crossing book froze the price forever.
    """

    def __init__(self, prices: Dict[Good, float]):
        self.reference_prices = dict(prices)
        self.orders_buy: Dict[Good, List[Order]] = {g: [] for g in Good}
        self.orders_sell: Dict[Good, List[Order]] = {g: [] for g in Good}
        self.history: Dict[Good, Dict[str, float]] = {
            g: {
                "volume": 0.0,
                "price": self.reference_prices[g],
                "demand": 0.0,
                "supply": 0.0,
                "unsold": 0.0,
                "unmet": 0.0,
            }
            for g in Good
        }
        self.consumption_spending = 0.0
        self.investment_spending = 0.0
        # Cost-based guard rails, updated by the engine.  They are not a
        # substitute for competition; they stop a thin market from ratcheting
        # to 10x replacement cost (or collapsing to 5% of it).
        self.ceilings: Dict[Good, float] = {}
        self.floors: Dict[Good, float] = {}

    # ------------------------------------------------------------------
    # Order submission
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
    # Matching
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

                # Buyer budget constraint: never overdraft.
                buyer_cash = max(getattr(b.agent, "cash", 0.0), 0.0)
                if buyer_cash < deal_price * deal_volume:
                    deal_volume = buyer_cash / deal_price if deal_price > 0 else 0.0

                # Seller inventory constraint (defensive; one order per seller).
                if isinstance(s.agent, Enterprise):
                    deal_volume = min(deal_volume, s.agent.inv(good))

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

            self._update_reference_price(good, demand, supply, volume, value, buys, sells)
            self.history[good] = {
                "volume": volume,
                "price": self.reference_prices[good],
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
        old = self.reference_prices[good]
        if volume > 1e-9:
            observed = value / volume
            new = 0.7 * old + 0.3 * observed
        else:
            new = old

        imbalance = (demand - supply) / max(demand, supply, 1.0)
        imbalance = max(-1.0, min(1.0, imbalance))
        new *= 1.0 + PRICE_STEP * imbalance

        # If one side is completely empty, make the signal a little stronger.
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

    # ------------------------------------------------------------------
    # Goods delivery
    # ------------------------------------------------------------------
    @staticmethod
    def _receive_good(agent: Any, good: Good, quantity: float) -> None:
        if isinstance(agent, (Worker, Capitalist)):
            if good == Good.FOOD:
                agent.food += quantity
            elif good == Good.CLOTH:
                agent.cloth += quantity
            elif good == Good.BUILDING:
                agent.housing += quantity
            return
        if isinstance(agent, (Enterprise, InvestmentProject)):
            agent.inventory[good] = agent.inventory.get(good, 0.0) + quantity

    @staticmethod
    def _deliver_good(agent: Any, good: Good, quantity: float) -> None:
        if isinstance(agent, Enterprise):
            agent.inventory[good] = max(0.0, agent.inventory.get(good, 0.0) - quantity)
