"""V0.5 人口/代际/退休金测试。

覆盖：
- 初始年龄/性别结构；
- 出生、成年转工人、退休；
- 儿童 allowance 的货币守恒；
- 死亡清家庭/雇主关系；
- 养老金缴费/发放与基金恒等式；
- 统计口径（儿童/退休者不进入失业分母）；
- 240/600 月人口稳定、金本位货币守恒、同 seed 确定性。
"""

from __future__ import annotations

import math
import unittest
from typing import Any, Dict

from ecosim.config import FOOD_PER_WORKER
from ecosim.engine import Engine
from ecosim.enums import Good, Industry
from ecosim.scenarios import (
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    LATE_CAPITALISM,
    MMT_SOVEREIGN,
    ScenarioConfig,
    build_scenario_1,
)

REGIMES = {
    "classical": CLASSICAL_LAISSEZ_FAIRE,
    "keynesian": KEYNESIAN_WELFARE,
    "mmt": MMT_SOVEREIGN,
    "late_capitalism": LATE_CAPITALISM,
}


def run(config: ScenarioConfig, months: int, seed: int = 1) -> Engine:
    engine = Engine(seed=seed)
    build_scenario_1(engine, config=config)
    for _ in range(months):
        engine.step()
    return engine


def _iter_numeric_fields(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_numeric_fields(
                item, f"{path}.{key}" if path else str(key)
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_numeric_fields(item, f"{path}[{index}]")
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float)):
        yield path, float(value)


class InitialPopulationTests(unittest.TestCase):
    def test_initial_workers_have_age_and_sex_structure(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=CLASSICAL_LAISSEZ_FAIRE)
        adults = [
            worker
            for worker in engine.workers.values()
            if worker.alive and not worker.is_child
        ]
        children = [
            worker for worker in engine.workers.values() if worker.is_child
        ]
        # 初始仍保持 1100 名劳动年龄人口；另有可配置的初始儿童。
        self.assertEqual(len(adults), 1100)
        self.assertGreater(len(children), 0)
        for worker in adults:
            self.assertGreaterEqual(worker.age_months, 18 * 12)
            self.assertLessEqual(worker.age_months, 61 * 12)
        female_share = sum(1 for w in adults if w.sex == "F") / len(adults)
        self.assertGreater(female_share, 0.40)
        self.assertLess(female_share, 0.60)
        self.assertTrue(any(w.age_months > 0 for w in adults))

    def test_fertility_age_range_and_late_preset(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=LATE_CAPITALISM)
        self.assertEqual(LATE_CAPITALISM.retirement_age_years, 67)
        self.assertAlmostEqual(LATE_CAPITALISM.pension_replacement, 0.55)
        self.assertAlmostEqual(LATE_CAPITALISM.pension_tax_rate, 0.16)
        self.assertLess(
            LATE_CAPITALISM.fertility_monthly,
            CLASSICAL_LAISSEZ_FAIRE.fertility_monthly,
        )
        self.assertGreaterEqual(sum(1 for w in engine.workers.values() if w.retired), 1)
        self.assertIsNotNone(engine.government)
        self.assertAlmostEqual(
            engine.government.pension_replacement, 0.55
        )


class IndividualDemographyTests(unittest.TestCase):
    def make_engine(self) -> Engine:
        engine = Engine(seed=1)
        engine._monthly_mortality = lambda worker: 0.0  # type: ignore[method-assign]
        engine._birth_probability = lambda worker: 0.0  # type: ignore[method-assign]
        return engine

    def test_birth_creates_child_with_family_link(self):
        engine = self.make_engine()
        mother = engine.create_worker(
            Industry.SERVICE,
            cash=100.0,
            age_months=25 * 12,
            sex="F",
        )
        mother.living_standard = "comfort"
        mother.consumed_food = FOOD_PER_WORKER
        child = engine._give_birth(mother)
        self.assertTrue(child.is_child)
        self.assertEqual(child.age_months, 0)
        self.assertIn(child.sex, ("F", "M"))
        self.assertEqual(child.cash, 0.0)
        self.assertEqual(child.parent_id, mother.id)
        self.assertIn(child.id, mother.children_ids)
        self.assertEqual(engine.births_this_month, 1)
        self.assertIn(child.id, engine.workers)

    def test_child_becomes_worker_at_working_age(self):
        engine = self.make_engine()
        mother = engine.create_worker(
            Industry.SERVICE, age_months=30 * 12, sex="F"
        )
        child = engine.create_worker(
            Industry.SERVICE,
            skill=0.0,
            age_months=engine.demographics.working_age_months - 1,
            sex="M",
            is_child=True,
            parent_id=mother.id,
        )
        mother.children_ids.append(child.id)
        engine._demography_pre()
        self.assertFalse(child.is_child)
        self.assertFalse(child.retired)
        self.assertEqual(
            child.age_months, engine.demographics.working_age_months
        )
        self.assertGreaterEqual(child.skill, 1.0)
        self.assertTrue(child.is_working_age)

    def test_employee_retires_and_leaves_enterprise(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=KEYNESIAN_WELFARE)
        engine._monthly_mortality = lambda worker: 0.0  # type: ignore[method-assign]
        engine._birth_probability = lambda worker: 0.0  # type: ignore[method-assign]
        worker = next(
            w
            for w in engine.workers.values()
            if w.alive and w.employed and not w.is_owner_operator
        )
        enterprise = engine.enterprises[worker.employer_id]
        worker.age_months = engine.demographics.retirement_age_months - 1
        engine._demography_pre()
        self.assertTrue(worker.retired)
        self.assertIsNone(worker.employer_id)
        self.assertEqual(worker.wage, 0.0)
        self.assertNotIn(worker.id, enterprise.workers)

    def test_child_allowance_conserves_money_and_scales(self):
        engine = Engine(seed=1)
        prices = engine.market.reference_prices
        mother = engine.create_worker(
            Industry.SERVICE, cash=100.0, age_months=30 * 12, sex="F"
        )
        children = []
        for _ in range(2):
            child = engine.create_worker(
                Industry.SERVICE,
                cash=0.0,
                food=0.0,
                age_months=2 * 12,
                sex="F",
                is_child=True,
                parent_id=mother.id,
            )
            mother.children_ids.append(child.id)
            children.append(child)
        before = mother.cash + sum(child.cash for child in children)
        engine._pay_child_allowances(prices)
        after = mother.cash + sum(child.cash for child in children)
        self.assertAlmostEqual(before, after, places=9)
        self.assertGreater(children[0].cash, 0.0)
        self.assertAlmostEqual(children[0].cash, children[1].cash, places=9)

        # 家长现金低于全额口粮线时不转移，优先保障家长生存。
        for child in children:
            child.cash = 0.0
        mother.cash = 0.5 * FOOD_PER_WORKER * prices[Good.FOOD]
        engine._pay_child_allowances(prices)
        self.assertEqual(children[0].cash, 0.0)
        self.assertEqual(children[1].cash, 0.0)
        self.assertAlmostEqual(
            mother.cash,
            0.5 * FOOD_PER_WORKER * prices[Good.FOOD],
            places=9,
        )

        # 超过口粮线后的余额按儿童人数等比分配。
        mother.cash = FOOD_PER_WORKER * prices[Good.FOOD] + 5.0
        engine._pay_child_allowances(prices)
        self.assertAlmostEqual(children[0].cash, 2.5, places=9)
        self.assertAlmostEqual(children[1].cash, 2.5, places=9)

    def test_death_clears_family_and_employer(self):
        engine = Engine(seed=1)
        mother = engine.create_worker(
            Industry.SERVICE, cash=50.0, age_months=30 * 12, sex="F"
        )
        child = engine.create_worker(
            Industry.SERVICE,
            age_months=2 * 12,
            sex="F",
            is_child=True,
            parent_id=mother.id,
        )
        mother.children_ids.append(child.id)
        enterprise = engine.create_enterprise(
            Industry.SERVICE, owner_id="OWNER", cash=1000.0
        )
        enterprise.workers.append(mother.id)
        mother.employer_id = enterprise.id
        bank_before = engine.bank.cash
        engine._kill_worker(mother)
        self.assertFalse(mother.alive)
        self.assertEqual(mother.cash, 0.0)
        self.assertIsNone(child.parent_id)
        self.assertNotIn(child.id, mother.children_ids)
        self.assertNotIn(mother.id, enterprise.workers)
        self.assertIsNone(mother.employer_id)
        self.assertAlmostEqual(engine.bank.cash, bank_before + 50.0, places=9)
        self.assertEqual(engine.dead_this_month, 1)
        self.assertEqual(engine._orphaned_this_month, 1)
        stat = engine._record_stats()
        self.assertTrue(any("孤儿" in warning for warning in stat["warnings"]))


class PensionAccountingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(seed=1)
        build_scenario_1(cls.engine, config=KEYNESIAN_WELFARE)

    def test_contributions_and_benefits_are_explicit(self):
        engine = self.engine
        gov = engine.government
        retiree = engine.create_worker(
            Industry.SERVICE,
            cash=0.0,
            food=0.0,
            age_months=72 * 12,
            sex="F",
            retired=True,
        )
        retiree.cloth = 0.0
        retiree.housing = 0.0
        before_money = engine.total_money()
        engine._government_settlement()
        self.assertGreater(gov.pension_contributions, 0.0)
        self.assertGreater(gov.pension_spending, 0.0)
        self.assertGreater(retiree.pension_income, 0.0)
        self.assertGreater(retiree.cash, 0.0)
        self.assertGreaterEqual(gov.pension_fund, 0.0)
        self.assertAlmostEqual(
            gov.pension_revenue,
            gov.pension_contributions + gov.pension_subsidy,
            places=9,
        )
        self.assertAlmostEqual(
            gov.pension_balance,
            gov.pension_revenue - gov.pension_spending,
            places=9,
        )
        self.assertAlmostEqual(engine.total_money(), before_money, places=2)
        self.assertAlmostEqual(
            gov.deficit,
            gov.spending
            + gov.transfers
            + gov.interest_paid
            + gov.pension_spending
            - gov.tax_revenue
            - gov.pension_contributions,
            places=6,
        )

    def test_fund_identity_and_nonnegative_fund_over_months(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=KEYNESIAN_WELFARE)
        gov = engine.government
        for _ in range(24):
            previous_fund = gov.pension_fund
            stat = engine.step()
            self.assertGreaterEqual(stat["pension_fund"], -1e-9)
            self.assertAlmostEqual(
                stat["pension_fund"],
                previous_fund
                + stat["pension_revenue"]
                - stat["pension_spending"],
                places=6,
            )
            self.assertAlmostEqual(
                stat["pension_balance"],
                stat["pension_revenue"] - stat["pension_spending"],
                places=9,
            )


class PopulationStatisticsTests(unittest.TestCase):
    def test_unemployment_denominator_excludes_children_and_retirees(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=KEYNESIAN_WELFARE)
        stat = engine._record_stats()
        self.assertEqual(stat["alive"], stat["population"])
        self.assertEqual(stat["labor_force"], stat["working_age"])
        self.assertEqual(
            stat["unemployed"], stat["labor_force"] - stat["employed"]
        )
        self.assertAlmostEqual(
            stat["unemployment_rate"],
            stat["unemployed"] / max(1, stat["labor_force"]),
            places=9,
        )
        self.assertAlmostEqual(
            stat["dependency_ratio"],
            stat["retirees"] / max(1, stat["employed"]),
            places=9,
        )
        self.assertEqual(
            sum(stat["age_histogram"].values()), stat["population"]
        )
        self.assertGreater(stat["average_age"], 0.0)
        self.assertGreater(stat["median_age"], 0.0)
        self.assertGreater(stat["children"], 0)
        self.assertGreater(stat["retirees"], 0)
        self.assertEqual(stat["births"], 0)
        self.assertGreaterEqual(stat["pension_fund"], 0.0)


class StabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {
            name: run(config, 240) for name, config in REGIMES.items()
        }
        cls.classical_600 = run(CLASSICAL_LAISSEZ_FAIRE, 600)

    def test_240_month_population_stays_in_sustainable_range(self):
        for name, engine in self.runs.items():
            final = engine.stats[-1]
            self.assertGreater(final["population"], 200, msg=name)
            self.assertLess(final["population"], 4000, msg=name)
            self.assertGreater(final["labor_force"], 0, msg=name)
            self.assertGreaterEqual(final["children"], 0, msg=name)
            self.assertGreaterEqual(final["retirees"], 0, msg=name)
            total_births = sum(stat["births"] for stat in engine.stats)
            total_deaths = sum(stat["deaths"] for stat in engine.stats)
            self.assertGreater(total_births, 0, msg=name)
            self.assertGreater(total_deaths, 0, msg=name)
            self.assertGreaterEqual(final["pension_fund"], 0.0, msg=name)
            self.assertGreaterEqual(final["money_total"] + 1e-6, 0.0, msg=name)

    def test_240_month_gold_regimes_conserve_money(self):
        for name in ("classical", "keynesian", "late_capitalism"):
            engine = self.runs[name]
            final = engine.stats[-1]
            self.assertAlmostEqual(
                final["money_total"], engine.money_initial, places=2, msg=name
            )

    def test_600_month_classical_population_is_not_extinct(self):
        final = self.classical_600.stats[-1]
        self.assertGreater(final["population"], 200)
        self.assertLess(final["population"], 4000)
        self.assertGreater(final["working_age"], 0)
        self.assertGreater(
            sum(stat["births"] for stat in self.classical_600.stats), 0
        )
        self.assertAlmostEqual(
            final["money_total"], self.classical_600.money_initial, places=2
        )

    def test_240_month_stats_are_finite(self):
        for name, engine in self.runs.items():
            for path, value in _iter_numeric_fields(engine.stats[-1]):
                self.assertTrue(
                    math.isfinite(value),
                    msg=f"{name}: {path}={value}",
                )

    def test_same_seed_is_deterministic(self):
        a = run(KEYNESIAN_WELFARE, 24, seed=7)
        b = run(KEYNESIAN_WELFARE, 24, seed=7)
        fields = (
            "population",
            "children",
            "working_age",
            "retirees",
            "births",
            "deaths",
            "pension_revenue",
            "pension_spending",
            "pension_fund",
            "food_relief",
            "money_total",
        )
        for field in fields:
            self.assertAlmostEqual(
                a.stats[-1][field], b.stats[-1][field], places=9, msg=field
            )
        self.assertEqual(
            a.stats[-1]["age_histogram"], b.stats[-1]["age_histogram"]
        )
        for worker_a, worker_b in zip(
            a.workers.values(), b.workers.values()
        ):
            self.assertEqual(worker_a.id, worker_b.id)
            self.assertEqual(worker_a.age_months, worker_b.age_months)
            self.assertEqual(worker_a.sex, worker_b.sex)
            self.assertEqual(worker_a.alive, worker_b.alive)


if __name__ == "__main__":
    unittest.main()
