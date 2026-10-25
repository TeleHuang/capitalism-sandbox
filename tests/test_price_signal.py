"""V0.6 需求信号传导：下游投资冲击必须传到 0 级产品价格。"""

from __future__ import annotations

import dataclasses
import unittest

from ecosim.engine import Engine
from ecosim.enums import Good
from ecosim.scenarios import KEYNESIAN_WELFARE, build_scenario_1


def run(investment_shock: bool, months: int = 40) -> Engine:
    config = dataclasses.replace(
        KEYNESIAN_WELFARE, price_regime="free"
    )
    engine = Engine(seed=1)
    build_scenario_1(engine, config=config)
    for month in range(1, months + 1):
        if investment_shock and month == 20:
            # 公共投资占 GDP 15% -> 60%，持续 12 个月。
            engine.government.public_investment_rate = 0.60
        if investment_shock and month == 32:
            engine.government.public_investment_rate = 0.15
        engine.step()
    return engine


class PriceSignalTransmissionTests(unittest.TestCase):
    def test_public_investment_shock_reaches_zero_level_prices(self):
        base = run(False)
        shock = run(True)
        # 取冲击期末 T32，而不是冲击结束后价格已回落的 T40。
        base_prices = base.stats[31]["prices"]
        shock_prices = shock.stats[31]["prices"]
        # 下游建筑/机械投资冲击应沿着投入链传导到钢、铁、煤。
        self.assertGreater(
            shock_prices[Good.COAL.value],
            base_prices[Good.COAL.value] * 1.5,
        )
        self.assertGreater(
            shock_prices[Good.IRON_ORE.value],
            base_prices[Good.IRON_ORE.value] * 1.2,
        )
        self.assertGreater(
            shock_prices[Good.STEEL.value],
            base_prices[Good.STEEL.value] * 1.5,
        )
        self.assertGreater(
            shock_prices[Good.BUILDING.value],
            base_prices[Good.BUILDING.value] * 1.5,
        )
        # 价格仍有限且为正，没有被硬边界截断。
        for price in shock_prices.values():
            self.assertGreater(price, 0.0)
            self.assertLess(price, float("inf"))


if __name__ == "__main__":
    unittest.main()
