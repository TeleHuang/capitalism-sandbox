from __future__ import annotations

import unittest

from ecosim.enums import Good, Industry
from ecosim.market import Market
from ecosim.models import Enterprise


class DummyBuyer:
    def __init__(self, cash):
        self.cash = cash
        self.food = 0.0
        self.cloth = 0.0
        self.housing = 0.0


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.market = Market({g: 100.0 for g in Good})
        self.seller = Enterprise(id="S", industry=Industry.BRICK_FACTORY, owner_id="O")
        self.seller.cash = 0.0
        self.seller.inventory[Good.FOOD] = 10.0

    def test_excess_demand_raises_reference_price(self):
        buyer = DummyBuyer(10_000.0)
        self.market.submit_buy(buyer, Good.FOOD, 10.0, 120.0)
        self.market.submit_sell(self.seller, Good.FOOD, 5.0, 80.0)
        before = self.market.reference_prices[Good.FOOD]
        self.market.match()
        self.assertGreater(self.market.reference_prices[Good.FOOD], before)

    def test_buyer_cannot_overdraft(self):
        buyer = DummyBuyer(50.0)
        self.market.submit_buy(buyer, Good.FOOD, 10.0, 100.0)
        self.market.submit_sell(self.seller, Good.FOOD, 10.0, 80.0)
        self.market.match()
        self.assertGreaterEqual(buyer.cash, -1e-9)

    def test_money_is_conserved(self):
        buyer = DummyBuyer(1000.0)
        before = buyer.cash + self.seller.cash
        self.market.submit_buy(buyer, Good.FOOD, 5.0, 110.0)
        self.market.submit_sell(self.seller, Good.FOOD, 5.0, 90.0)
        self.market.match()
        self.assertAlmostEqual(buyer.cash + self.seller.cash, before, places=6)


if __name__ == "__main__":
    unittest.main()
