from __future__ import annotations

import unittest

from ecosim.config import EQUIPMENT
from ecosim.engine import Engine
from ecosim.enums import Good, Industry
from ecosim.scenarios import CLASSICAL_LAISSEZ_FAIRE, build_scenario_1


def make_engine() -> Engine:
    engine = Engine(seed=1)
    build_scenario_1(engine, config=CLASSICAL_LAISSEZ_FAIRE)
    return engine


def run(months: int = 60) -> Engine:
    engine = make_engine()
    for _ in range(months):
        engine.step()
    return engine


class ServiceSectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = run(60)
        cls.final = cls.engine.stats[-1]

    def test_dynamic_stat_keys_include_the_tenth_industry(self):
        self.assertEqual(len(Industry), 10)
        self.assertEqual(len(Good), 10)
        for section in (
            "firms",
            "workers_by_industry",
            "production",
            "prices",
            "volumes",
            "demand",
            "supply",
            "zero_output_streak",
        ):
            self.assertIn("service", self.final[section])

    def test_service_self_employment_absorbs_unemployed_workers(self):
        # 无服务业时 60 月古典失业率约 34%（见本次改动前的基线）。
        self.assertGreater(self.final["firms"]["service"], 0)
        self.assertGreater(self.final["workers_by_industry"]["service"], 0)
        self.assertLess(self.final["unemployment_rate"], 0.20)

    def test_service_has_positive_output_volume_and_sane_price(self):
        self.assertGreater(self.final["production"]["service"], 0.0)
        self.assertGreater(self.final["volumes"]["service"], 0.0)
        self.assertGreater(self.final["demand"]["service"], 0.0)
        self.assertGreater(self.final["prices"]["service"], 1.0)
        self.assertLess(self.final["prices"]["service"], 100.0)

    def test_service_inventory_is_not_carried_over(self):
        # 服务是流量：当月未售出的部分不能留到下月再卖。
        for enterprise in self.engine.active_enterprises(Industry.SERVICE):
            self.assertEqual(enterprise.inv(Good.SERVICE), 0.0)

    def test_money_is_conserved_with_service_self_employment(self):
        self.assertAlmostEqual(
            self.final["money_total"], self.engine.money_initial, places=2
        )


class ServiceSelfEmploymentUnitTests(unittest.TestCase):
    def test_unemployed_worker_opens_a_zero_capital_service_stall(self):
        engine = make_engine()
        worker = next(
            w
            for w in engine.workers.values()
            if w.alive and not w.is_owner_operator
        )
        old_employer = engine.enterprises[worker.employer_id]
        old_employer.workers.remove(worker.id)
        worker.employer_id = None
        worker.wage = 0.0

        history = engine.market.history[Good.SERVICE]
        history["demand"] = 10.0
        history["supply"] = 0.0
        history["unmet"] = 10.0

        engine._service_self_employment(engine.market.reference_prices)

        self.assertIsNotNone(worker.employer_id)
        self.assertEqual(worker.industry, Industry.SERVICE)
        self.assertTrue(worker.is_owner_operator)
        enterprise = engine.enterprises[worker.employer_id]
        self.assertTrue(enterprise.is_household)
        self.assertIn("service_t0", enterprise.equipment)

        equipment = EQUIPMENT["service_t0"]
        self.assertIsNone(equipment.capital_good)
        self.assertEqual(equipment.capacity, 1.0)
        self.assertEqual(equipment.workers, 1)
        self.assertEqual(equipment.build_months, 0)

    def test_no_entry_without_unmet_service_demand(self):
        engine = make_engine()
        worker = next(
            w
            for w in engine.workers.values()
            if w.alive and not w.is_owner_operator
        )
        old_employer = engine.enterprises[worker.employer_id]
        old_employer.workers.remove(worker.id)
        worker.employer_id = None
        worker.wage = 0.0

        # 需求已被满足（供给 >= 需求）时不应制造没有销路的自雇就业。
        history = engine.market.history[Good.SERVICE]
        history["demand"] = 10.0
        history["supply"] = 10.0
        history["unmet"] = 0.0

        engine._service_self_employment(engine.market.reference_prices)

        self.assertIsNone(worker.employer_id)
        self.assertEqual(engine.active_enterprises(Industry.SERVICE), [])


if __name__ == "__main__":
    unittest.main()
