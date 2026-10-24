from __future__ import annotations

import unittest

from ecosim.engine import Engine
from ecosim.enums import Good, Industry
from ecosim.production import desired_workers, produce
from ecosim.scenarios import build_scenario_1


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(seed=1)
        build_scenario_1(self.engine)
        self.farm = next(
            e
            for e in self.engine.enterprises.values()
            if e.industry == Industry.AGRICULTURE and e.is_household
        )

    def test_fertilizer_doubles_farm_output(self):
        self.farm.modernization_capable = True
        self.farm.use_fertilizer = False
        self.farm.inventory[Good.FOOD] = 0.0
        base = produce(self.engine, self.farm)

        self.farm.inventory[Good.FOOD] = 0.0
        self.farm.inventory[Good.FERTILIZER] = 1.0
        self.farm.use_fertilizer = True
        boosted = produce(self.engine, self.farm)

        self.assertAlmostEqual(boosted, base * 2.0, places=6)

    def test_machinery_reduces_required_farm_workers(self):
        self.farm.land = 100.0
        before = desired_workers(self.farm)
        self.farm.add_equipment("farm_machinery", 1)
        after = desired_workers(self.farm)
        self.assertEqual(before, 10)  # 每 10 亩 1 个工人
        self.assertEqual(after, 5)    # 每 20 亩 1 个工人


if __name__ == "__main__":
    unittest.main()
