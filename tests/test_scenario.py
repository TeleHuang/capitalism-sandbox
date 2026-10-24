from __future__ import annotations

import unittest

from ecosim.engine import Engine
from ecosim.scenarios import build_scenario_1


def run(months: int, seed: int = 1) -> Engine:
    engine = Engine(seed=seed)
    build_scenario_1(engine)
    for _ in range(months):
        engine.step()
    return engine


class ScenarioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = run(60)
        cls.final = cls.engine.stats[-1]

    def test_survives_the_first_five_years_without_a_famine(self):
        self.assertGreaterEqual(self.final["alive"], 1050)
        self.assertEqual(self.final["dead_this_month"], 0)

    def test_money_is_conserved(self):
        self.assertAlmostEqual(
            self.final["money_total"], self.engine.money_initial, places=2
        )

    def test_a_capitalist_agricultural_sector_appears(self):
        self.assertGreater(self.final["capitalist_farms"], 0)
        self.assertLess(self.final["smallholder_land"], 6000.0)

    def test_farms_adopt_fertilizer_and_machinery(self):
        self.assertGreater(self.final["fertilizer_used"], 0.0)
        self.assertGreater(self.final["farm_machinery"], 0)

    def test_agricultural_labour_productivity_rises(self):
        # 初始粮食产出 120 吨、600 名农业工人（人均 0.20）。
        self.assertGreater(self.final["ag_productivity"], 0.21)

    def test_240_month_run_keeps_fertilizer_alive(self):
        engine = run(240)
        final = engine.stats[-1]
        self.assertGreater(final["fertilizer_used"], 0.0)
        self.assertGreater(final["alive"], 1000)
        self.assertAlmostEqual(final["money_total"], engine.money_initial, places=2)

    def test_same_seed_is_deterministic(self):
        a = run(12, seed=7).stats[-1]
        b = run(12, seed=7).stats[-1]
        self.assertEqual(a["alive"], b["alive"])
        self.assertAlmostEqual(a["gdp"], b["gdp"], places=6)
        self.assertAlmostEqual(a["food_output"], b["food_output"], places=6)


if __name__ == "__main__":
    unittest.main()
