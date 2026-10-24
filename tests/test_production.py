from __future__ import annotations

import unittest

from ecosim.config import (
    CAPITALIST_CLOTH,
    CAPITALIST_FOOD,
    CAPITALIST_HOUSING,
    CLOTH_PER_WORKER,
    EQUIPMENT,
    FOOD_PER_WORKER,
    HOUSING_PER_WORKER,
)
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

    def test_two_n_equipment_table(self):
        self.assertEqual(EQUIPMENT["steel_t0"].capacity, 50.0)
        self.assertEqual(EQUIPMENT["steel_t0"].workers, 3)
        self.assertEqual(EQUIPMENT["steel_t1"].capacity, 100.0)
        self.assertEqual(EQUIPMENT["steel_t1"].workers, 4)
        self.assertEqual(EQUIPMENT["steel_t7"].capacity, 6400.0)
        self.assertEqual(EQUIPMENT["steel_t7"].workers, 10)
        self.assertEqual(EQUIPMENT["farm_t1"].power, 2.0)

    def test_capitalists_consume_at_highest_worker_standard(self):
        self.assertAlmostEqual(CAPITALIST_FOOD, FOOD_PER_WORKER * 1.5)
        self.assertAlmostEqual(CAPITALIST_CLOTH, CLOTH_PER_WORKER * 1.5)
        self.assertAlmostEqual(CAPITALIST_HOUSING, HOUSING_PER_WORKER * 1.5)

    def test_machinery_reduces_required_farm_workers(self):
        self.farm.land = 100.0
        before = desired_workers(self.farm)
        self.farm.add_equipment("farm_t0", 1)
        after = desired_workers(self.farm)
        self.assertEqual(before, 10)  # 每 10 亩 1 个工人
        self.assertEqual(after, 5)    # 每 20 亩 1 个工人


if __name__ == "__main__":
    unittest.main()
