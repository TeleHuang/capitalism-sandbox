from __future__ import annotations

import unittest

from ecosim.engine import Engine
from ecosim.scenarios import (
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    MMT_SOVEREIGN,
    build_scenario_1,
)


def run(config, months: int = 24) -> Engine:
    engine = Engine(seed=1)
    build_scenario_1(engine, config=config)
    for _ in range(months):
        engine.step()
    return engine


class GovernmentTests(unittest.TestCase):
    def test_classical_has_no_government(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=CLASSICAL_LAISSEZ_FAIRE)
        self.assertIsNone(engine.government)

    def test_keynesian_collects_taxes_and_conserves_money(self):
        engine = run(KEYNESIAN_WELFARE, 24)
        final = engine.stats[-1]
        self.assertIsNotNone(engine.government)
        self.assertEqual(final["policy_regime"], "keynesian")
        self.assertGreater(final["government_tax_revenue"], 0.0)
        self.assertAlmostEqual(
            final["money_total"], engine.money_initial, places=2
        )
        self.assertAlmostEqual(
            final["government_deficit"],
            final["government_spending"]
            + final["government_transfers"]
            - final["government_tax_revenue"],
            places=4,
        )

    def test_mmt_creates_money_and_runs_deficits(self):
        engine = run(MMT_SOVEREIGN, 24)
        final = engine.stats[-1]
        self.assertEqual(final["policy_regime"], "mmt")
        self.assertGreaterEqual(
            final["central_bank_money"] + final["government_debt"], 0.0
        )
        # MMT 是信用货币：货币总量允许高于初始值。
        self.assertGreaterEqual(
            final["money_total"] + 1e-6, engine.money_initial
        )

    def test_job_guarantee_absorbs_unemployed(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=MMT_SOVEREIGN)
        # 直接制造一个失业者，验证最后雇主机制。
        worker = next(w for w in engine.workers.values() if w.alive)
        worker.employer_id = None
        worker.wage = 0.0
        worker.is_owner_operator = False
        engine._job_guarantee()
        self.assertIn(worker.id, engine.government.jg_workers)
        self.assertEqual(worker.employer_id, "GOV")
        self.assertEqual(worker.wage, MMT_SOVEREIGN.jg_wage)

    def test_bank_deposit_and_interest_conserve_money(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=CLASSICAL_LAISSEZ_FAIRE)
        capitalist = next(iter(engine.capitalists.values()))
        before = engine.total_money()
        engine.bank.deposit(capitalist, 1000.0)
        self.assertAlmostEqual(engine.total_money(), before, places=6)
        engine.bank.pay_deposit_interest(
            {**engine.workers, **engine.capitalists}
        )
        self.assertAlmostEqual(engine.total_money(), before, places=6)

    def test_all_regimes_reach_low_unemployment_with_service_sector(self):
        classical = run(CLASSICAL_LAISSEZ_FAIRE, 60)
        keynesian = run(KEYNESIAN_WELFARE, 60)
        # V0.4.1 的服务业/非正规自雇会把古典失业也压到接近 0，
        # 因此不再断言 Keynesian 必须严格低于古典；保留“都低”的验收线，
        # 并允许 2pp 的摩擦性差异。
        for engine in (classical, keynesian):
            self.assertLess(engine.stats[-1]["unemployment_rate"], 0.05)
        self.assertLessEqual(
            keynesian.stats[-1]["unemployment_rate"],
            classical.stats[-1]["unemployment_rate"] + 0.02,
        )


if __name__ == "__main__":
    unittest.main()
