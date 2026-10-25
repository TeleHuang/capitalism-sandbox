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

from tests._slow import SLOW_ENABLED, slow

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
        # 初始在业劳动人口不能在退休年龄（67）以上。
        for worker in engine.workers.values():
            if worker.alive and not worker.is_child and not worker.retired:
                self.assertLess(
                    worker.age_months, 67 * 12, msg=worker.id
                )
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

    def test_adult_child_is_not_counted_as_orphan(self):
        engine = self.make_engine()
        parent = engine.create_worker(
            Industry.SERVICE, age_months=60 * 12, sex="F"
        )
        adult = engine.create_worker(
            Industry.SERVICE,
            age_months=20 * 12,
            sex="M",
            is_child=False,
            parent_id=parent.id,
        )
        parent.children_ids.append(adult.id)
        engine._kill_worker(parent)
        self.assertEqual(engine._orphaned_this_month, 0)
        self.assertIsNone(adult.parent_id)

    def test_dead_farmer_land_passes_to_adult_child(self):
        engine = self.make_engine()
        farmer = engine.create_worker(
            Industry.AGRICULTURE, age_months=60 * 12, sex="M"
        )
        child = engine.create_worker(
            Industry.SERVICE,
            age_months=20 * 12,
            sex="M",
            is_child=False,
            parent_id=farmer.id,
        )
        farmer.children_ids.append(child.id)
        farmer.is_owner_operator = True
        farmer.land_owned = 10.0
        engine.land.owners[farmer.id] = 10.0
        enterprise = engine.create_enterprise(
            Industry.AGRICULTURE,
            owner_id=farmer.id,
            cash=100.0,
            land=10.0,
            is_household=True,
        )
        enterprise.workers.append(farmer.id)
        farmer.employer_id = enterprise.id
        engine.land.enterprise_by_owner[farmer.id] = enterprise.id
        estate_before = engine.land.estate_land

        engine._kill_worker(farmer)

        self.assertTrue(enterprise.active)
        self.assertEqual(enterprise.owner_id, child.id)
        self.assertEqual(child.employer_id, enterprise.id)
        self.assertTrue(child.is_owner_operator)
        self.assertAlmostEqual(engine.land.owners[child.id], 10.0)
        self.assertNotIn(farmer.id, engine.land.owners)
        self.assertEqual(engine.land.estate_land, estate_before)
        self.assertEqual(engine._orphaned_this_month, 0)

    def test_dead_farmer_land_goes_to_landless_worker_without_heir(self):
        engine = self.make_engine()
        farmer = engine.create_worker(
            Industry.AGRICULTURE, age_months=60 * 12, sex="M"
        )
        farmer.is_owner_operator = True
        farmer.land_owned = 10.0
        engine.land.owners[farmer.id] = 10.0
        enterprise = engine.create_enterprise(
            Industry.AGRICULTURE,
            owner_id=farmer.id,
            cash=100.0,
            land=10.0,
            is_household=True,
        )
        enterprise.workers.append(farmer.id)
        farmer.employer_id = enterprise.id
        engine.land.enterprise_by_owner[farmer.id] = enterprise.id
        landless = engine.create_worker(
            Industry.SERVICE, age_months=30 * 12, sex="M", cash=0.0
        )
        estate_before = engine.land.estate_land

        engine._kill_worker(farmer)

        self.assertTrue(enterprise.active)
        self.assertEqual(enterprise.owner_id, landless.id)
        self.assertTrue(landless.is_owner_operator)
        self.assertAlmostEqual(engine.land.owners[landless.id], 10.0)
        self.assertEqual(engine.land.estate_land, estate_before)

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
        # PAYG 缴费在发薪时代扣；先发工资，再做政府结算。
        engine._pay_wages()
        engine._pay_government_wages()
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

    def test_owner_operator_receives_pension_without_retiring(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=KEYNESIAN_WELFARE)
        engine._monthly_mortality = lambda worker: 0.0  # type: ignore[method-assign]
        farmer = next(
            worker
            for worker in engine.workers.values()
            if worker.alive and worker.is_owner_operator
        )
        farmer.age_months = engine.demographics.retirement_age_months - 1
        engine.step()
        self.assertFalse(farmer.retired)
        self.assertTrue(farmer.is_owner_operator)
        self.assertGreater(farmer.pension_income, 0.0)
        self.assertGreaterEqual(engine.stats[-1]["pension_recipients"], 1)

    def test_late_capitalism_pension_month_conserves_money(self):
        """LATE_CAPITALISM 90 个月：金本位货币守恒 + 基金恒等式。"""
        engine = Engine(seed=1)
        build_scenario_1(engine, config=LATE_CAPITALISM)
        for _ in range(90):
            stat = engine.step()
            self.assertGreaterEqual(stat["pension_fund"], -1e-9)
            self.assertGreaterEqual(stat["pension_fund_unfunded"], 0.0)
            self.assertAlmostEqual(
                stat["money_total"], engine.money_initial, places=2
            )
            self.assertAlmostEqual(
                stat["pension_revenue"],
                stat["pension_contributions"] + stat["pension_subsidy"],
                places=6,
            )
            self.assertAlmostEqual(
                stat["pension_balance"],
                stat["pension_revenue"] - stat["pension_spending"],
                places=6,
            )
        self.assertGreater(
            sum(stat["pension_contributions"] for stat in engine.stats),
            0.0,
        )

    def test_forced_pension_subsidy_conserves_money(self):
        """强制基金/现金为 0，覆盖 pension_subsidy 融资分支。"""
        engine = Engine(seed=1)
        build_scenario_1(engine, config=LATE_CAPITALISM)
        gov = engine.government
        gov.cash = 0.0
        gov.pension_fund = 0.0
        before_money = engine.total_money()
        engine._government_settlement()
        self.assertGreater(gov.pension_subsidy, 0.0)
        self.assertAlmostEqual(engine.total_money(), before_money, places=2)
        self.assertAlmostEqual(
            gov.pension_revenue,
            gov.pension_contributions + gov.pension_subsidy,
            places=6,
        )
        self.assertAlmostEqual(
            gov.pension_balance,
            gov.pension_revenue - gov.pension_spending,
            places=6,
        )
        self.assertAlmostEqual(
            gov.pension_fund,
            gov.pension_revenue - gov.pension_spending,
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
                stat["pension_revenue"],
                stat["pension_contributions"] + stat["pension_subsidy"],
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
        # 独立从 worker 标志重算，避免只比较同一份实现派生出的字段。
        expected_labor_force = sum(
            1
            for worker in engine.workers.values()
            if worker.alive and not worker.is_child and not worker.retired
        )
        expected_unemployed = sum(
            1
            for worker in engine.workers.values()
            if worker.alive and worker.is_working_age and not worker.employed
        )
        self.assertEqual(stat["labor_force"], expected_labor_force)
        self.assertEqual(stat["unemployed"], expected_unemployed)
        for worker in engine.workers.values():
            if worker.alive and (worker.is_child or worker.retired):
                self.assertFalse(worker.employed)
        self.assertEqual(
            stat["unemployed"], stat["labor_force"] - stat["employed"]
        )
        self.assertAlmostEqual(
            stat["unemployment_rate"],
            stat["unemployed"] / max(1, stat["labor_force"]),
            places=9,
        )
        # 总抚养比含儿童和退休者，分母统一为劳动年龄人口。
        self.assertAlmostEqual(
            stat["dependency_ratio"],
            (stat["children"] + stat["retirees"]) / max(1, stat["labor_force"]),
            places=9,
        )
        self.assertAlmostEqual(
            stat["old_age_dependency"],
            stat["retirees"] / max(1, stat["labor_force"]),
            places=9,
        )
        self.assertAlmostEqual(
            stat["child_dependency"],
            stat["children"] / max(1, stat["labor_force"]),
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


class FoodReliefTests(unittest.TestCase):
    def test_classical_sixty_months_has_no_famine_and_keeps_reserve(self):
        """高价时粮商不能把救济库存卖空；60 月古典不应出现饥饿死亡。

        回归场景：V0.5 初版粮商按高价无限释放库存，粮商库存归零后
        粮食救济无粮可发，60 月古典/Keynesian/MMT 分别累计 112/63/122
        例饥饿死亡。保留救济缓冲后应降到 0。
        """
        engine = run(CLASSICAL_LAISSEZ_FAIRE, 60)
        hunger = sum(stat["hunger_deaths"] for stat in engine.stats)
        self.assertEqual(hunger, 0)
        need = engine.feeding_units() * FOOD_PER_WORKER
        self.assertGreaterEqual(engine.food_reserve.food, need)


@slow
class StabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not SLOW_ENABLED:
            raise unittest.SkipTest("slow integration test")
        cls.runs = {
            name: run(config, 240) for name, config in REGIMES.items()
        }
        cls.classical_600 = run(CLASSICAL_LAISSEZ_FAIRE, 600)

    def test_240_month_population_stays_in_sustainable_range(self):
        for name, engine in self.runs.items():
            final = engine.stats[-1]
            # 初始人口 1350–1400；240 月应保持在 0.7×–1.6× 初始区间，
            # 而不是旧断言的“>200 即可”（那允许人口崩溃 85%）。
            self.assertGreater(final["population"], 900, msg=name)
            self.assertLess(final["population"], 2400, msg=name)
            self.assertGreater(final["labor_force"], 0, msg=name)
            # 儿童/退休者必须仍然存在，不能只用 >=0 的同义反复。
            self.assertGreater(final["children"], 0, msg=name)
            if name != "classical":
                self.assertGreater(final["retirees"], 0, msg=name)
            total_births = sum(stat["births"] for stat in engine.stats)
            total_deaths = sum(stat["deaths"] for stat in engine.stats)
            self.assertGreater(total_births, 0, msg=name)
            self.assertGreater(total_deaths, 0, msg=name)
            last_year_births = sum(
                stat["births"] for stat in engine.stats[-12:]
            )
            self.assertGreater(last_year_births, 0, msg=name)
            # 救济缓冲修复后，240 月四剧本都不应有饥饿死亡。
            self.assertEqual(
                sum(stat["hunger_deaths"] for stat in engine.stats),
                0,
                msg=name,
            )
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
