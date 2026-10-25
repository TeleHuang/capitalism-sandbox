"""V0.6 工资—生产率与自由成本加成定价的快速回归测试。

覆盖：
- 有效劳动按制度性标准工时折算（16h/8h）；
- 工资目标跟踪生产率，实际报价有粘性（向下调整更快）；
- 工资与生产率同比例增长时单位劳动成本稳定；
- ``price_regime="free"`` 只有绝对安全轨，没有成本地板/天花板；
- 成本加成目标价能把单位成本变化传导到价格，且价格有限、为正。

长程 240 月 smoke 使用 ``tests._slow.slow``，默认跳过。
"""

from __future__ import annotations

import dataclasses
import math
import unittest

from ecosim.config import (
    FREE_PRICE_CAP_MULT,
    INITIAL_PRICES,
    PRICE_FLOOR,
    WAGE_BASE,
)
from ecosim.decisions import (
    enterprise_ask_price,
    enterprise_wage_offer,
    free_price_target,
    wage_target,
)
from ecosim.engine import Engine
from ecosim.enums import Good, Industry
from ecosim.models import Worker
from ecosim.production import unit_cost
from ecosim.scenarios import (
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    build_scenario_1,
)
from tests._slow import slow


def make_engine(config=None) -> Engine:
    engine = Engine(seed=1)
    build_scenario_1(engine, config or CLASSICAL_LAISSEZ_FAIRE)
    return engine


def no_friction_wage_env(engine: Engine) -> None:
    """隔离工资目标的纯生产率/滞后项。"""
    engine.wage_floor_scale = 1.0
    engine.wage_productivity_share = 1.0
    engine.inflation_expectations = 0.0
    engine.wage_inflation_pass_through = 1.0
    engine.wage_bargain_power = 0.0
    engine.wage_adjustment_speed = 0.10
    engine.cpi = 1.0
    engine.wage_index = 1.0
    engine._wage_unemployment = 0.07


def make_brick_enterprise(
    engine: Engine, wage: float, inventory: float, sales: float = 2.0
):
    engine.market.reference_prices[Good.BRICK] = 10.0
    enterprise = engine.create_enterprise(
        industry=Industry.BRICK_FACTORY, owner_id="owner"
    )
    enterprise.add_equipment("brick_t0")
    worker = engine.create_worker(
        industry=Industry.BRICK_FACTORY, skill=1.0, cash=0.0
    )
    worker.wage = wage
    worker.employer_id = enterprise.id
    enterprise.workers.append(worker.id)
    enterprise.last_output = 1.0
    enterprise.last_input_used = {}
    enterprise.inventory[Good.BRICK] = inventory
    enterprise.smoothed_sales = sales
    enterprise.target_inventory_months = 2.0
    return enterprise, worker


class WorkHoursTests(unittest.TestCase):
    def test_effective_labor_is_relative_to_standard_hours(self):
        worker = Worker(
            id="W_TEST",
            industry=Industry.BRICK_FACTORY,
            standard_hours=8,
            hours=8,
        )
        self.assertAlmostEqual(worker.effective_labor, 1.0)
        worker.hours = 4
        self.assertAlmostEqual(worker.effective_labor, 0.5)
        worker.standard_hours = 16
        worker.hours = 8
        self.assertAlmostEqual(worker.effective_labor, 0.5)

    def test_choose_hours_uses_eight_hour_ladder(self):
        worker = Worker(
            id="W_TEST",
            industry=Industry.BRICK_FACTORY,
            standard_hours=8,
            hours=8,
            cash=0.0,
            food=0.0,
            living_standard="survival",
        )
        prices = {good: INITIAL_PRICES[good] for good in Good}
        self.assertEqual(worker.choose_hours(prices), 8)
        worker.food = 1.0
        worker.living_standard = "comfort"
        worker.cash = 1000.0
        self.assertEqual(worker.choose_hours(prices), 4)

    def test_scenario_work_hours_are_wired(self):
        keynesian = make_engine(KEYNESIAN_WELFARE)
        self.assertEqual(keynesian.work_hours, 8)
        adults = [
            worker
            for worker in keynesian.workers.values()
            if worker.is_working_age
        ]
        self.assertTrue(adults)
        for worker in adults:
            self.assertEqual(worker.standard_hours, 8)
            self.assertIn(worker.hours, (8, 6, 4))
            self.assertLessEqual(worker.effective_labor, 1.0 + 1e-9)

        classical = make_engine(CLASSICAL_LAISSEZ_FAIRE)
        self.assertEqual(classical.work_hours, 16)
        self.assertTrue(
            all(
                worker.standard_hours == 16
                for worker in classical.workers.values()
                if worker.is_working_age
            )
        )


class WageRuleTests(unittest.TestCase):
    def test_wage_target_tracks_productivity(self):
        engine = make_engine(KEYNESIAN_WELFARE)
        no_friction_wage_env(engine)
        enterprise = engine.active_enterprises(Industry.STEEL_MILL)[0]
        enterprise.last_revenue = 0.0
        enterprise.last_profit = 0.0

        engine.productivity_index = 1.0
        base = wage_target(engine, enterprise)
        self.assertAlmostEqual(base, WAGE_BASE, places=6)

        engine.productivity_index = 2.0
        doubled = wage_target(engine, enterprise)
        self.assertAlmostEqual(doubled, 2.0 * WAGE_BASE, places=6)
        # 单位劳动成本 = 工资 / 生产率；两者同比例上升时应不变。
        self.assertAlmostEqual(base / 1.0, doubled / 2.0, places=6)

    def test_wage_offer_moves_toward_target_with_asymmetric_lag(self):
        engine = make_engine(KEYNESIAN_WELFARE)
        no_friction_wage_env(engine)
        enterprise = engine.active_enterprises(Industry.STEEL_MILL)[0]
        enterprise.last_revenue = 0.0
        enterprise.last_profit = 0.0

        engine.productivity_index = 2.0
        enterprise.wage_offer = WAGE_BASE
        offer_up = enterprise_wage_offer(engine, enterprise)
        # 向上速度 0.10：20 -> 22（目标 40）。
        self.assertAlmostEqual(offer_up, 22.0, delta=0.6)

        engine.productivity_index = 1.0
        enterprise.wage_offer = 2.0 * WAGE_BASE
        previous = enterprise.wage_offer
        offer_down = enterprise_wage_offer(engine, enterprise)
        # 向下速度 0.10×3：40 -> 34（目标 20）。
        self.assertAlmostEqual(offer_down, 34.0, delta=0.6)
        self.assertLess(offer_down, previous)

    def test_unit_labor_cost_is_stable_when_wages_track_productivity(self):
        engine = Engine(seed=1)
        enterprise = engine.create_enterprise(
            industry=Industry.BRICK_FACTORY, owner_id="owner"
        )
        worker = engine.create_worker(
            industry=Industry.BRICK_FACTORY, skill=1.0, cash=0.0
        )
        worker.employer_id = enterprise.id
        enterprise.workers.append(worker.id)
        enterprise.last_output = 1.0
        enterprise.last_input_used = {}

        worker.wage = WAGE_BASE
        cost_before = unit_cost(
            enterprise,
            engine.market.reference_prices,
            [worker],
            engine.land.price,
        )
        worker.wage = 2.0 * WAGE_BASE
        enterprise.last_output = 2.0
        cost_after = unit_cost(
            enterprise,
            engine.market.reference_prices,
            [worker],
            engine.land.price,
        )
        self.assertAlmostEqual(cost_before, cost_after, places=6)


class FreePriceRegimeTests(unittest.TestCase):
    def test_free_regime_has_only_absolute_rails(self):
        config = dataclasses.replace(
            CLASSICAL_LAISSEZ_FAIRE, price_regime="free"
        )
        engine = make_engine(config)
        engine._update_price_bands()
        for good in Good:
            self.assertAlmostEqual(engine.market.floors[good], PRICE_FLOOR)
            self.assertAlmostEqual(
                engine.market.ceilings[good],
                INITIAL_PRICES[good] * FREE_PRICE_CAP_MULT,
            )
        # 成本锚存在，但不是价格下限。
        self.assertTrue(engine.market.cost_anchors)
        for good, cost in engine.market.cost_anchors.items():
            self.assertLess(engine.market.floors[good], cost)

    def test_free_ask_can_be_below_actual_cost(self):
        engine = Engine(seed=1)
        engine.price_regime = "free"
        engine.market.price_regime = "free"
        enterprise, worker = make_brick_enterprise(
            engine, wage=13.0, inventory=20.0, sales=2.0
        )
        engine._update_price_bands()
        price = enterprise_ask_price(engine, enterprise)
        actual_cost = unit_cost(
            enterprise,
            engine.market.reference_prices,
            [worker],
            engine.land.price,
        )
        self.assertGreater(price, 0.0)
        self.assertTrue(math.isfinite(price))
        self.assertLess(price, actual_cost)
        self.assertGreaterEqual(engine.market.floors[Good.BRICK], PRICE_FLOOR)

    def test_free_price_target_passes_through_normal_cost(self):
        engine = Engine(seed=1)
        engine.price_regime = "free"
        engine.market.price_regime = "free"
        enterprise, worker = make_brick_enterprise(
            engine, wage=13.0, inventory=20.0, sales=2.0
        )
        engine._update_price_bands()
        before = free_price_target(engine, enterprise)
        worker.wage = 26.0
        after = free_price_target(engine, enterprise)
        # 正常单位成本翻倍，目标价应显著上调；只受绝对安全上限约束。
        self.assertGreater(after, before * 1.5)
        self.assertLess(
            after, INITIAL_PRICES[Good.BRICK] * FREE_PRICE_CAP_MULT
        )

    def test_free_prices_stay_finite_and_positive(self):
        config = dataclasses.replace(
            CLASSICAL_LAISSEZ_FAIRE, price_regime="free"
        )
        engine = make_engine(config)
        for _ in range(6):
            stat = engine.step()
            for price in stat["prices"].values():
                self.assertGreater(price, 0.0)
                self.assertTrue(math.isfinite(price))
        for good in Good:
            self.assertAlmostEqual(engine.market.floors[good], PRICE_FLOOR)


class SlowSmokeTests(unittest.TestCase):
    @slow
    def test_free_regime_240_month_smoke(self):
        """慢速 smoke：free 制度 240 月存活、无饥饿、货币守恒。"""
        config = dataclasses.replace(
            CLASSICAL_LAISSEZ_FAIRE, price_regime="free"
        )
        engine = make_engine(config)
        hunger_deaths = 0
        for _ in range(240):
            stat = engine.step()
            hunger_deaths += stat["hunger_deaths"]
            for price in stat["prices"].values():
                self.assertGreater(price, 0.0)
                self.assertTrue(math.isfinite(price))
        final = engine.stats[-1]
        self.assertGreater(final["alive"], 1000)
        self.assertEqual(hunger_deaths, 0)
        self.assertAlmostEqual(
            final["money_total"], engine.money_initial, places=2
        )
        for good in Good:
            self.assertAlmostEqual(engine.market.floors[good], PRICE_FLOOR)


if __name__ == "__main__":
    unittest.main()
