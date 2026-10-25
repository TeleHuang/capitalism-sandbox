from __future__ import annotations

import dataclasses
import unittest

import ecosim.engine as engine_module

from ecosim.config import INITIAL_PRICES, SECTOR_PARAMS
from ecosim.decisions import enterprise_ask_price
from ecosim.engine import Engine
from ecosim.enums import Good, Industry
from ecosim.production import unit_cost
from ecosim.scenarios import (
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    MARKUP_SOFT,
    MMT_SOVEREIGN,
    ScenarioConfig,
    build_scenario_1,
)

CORE = (Good.STEEL, Good.BRICK, Good.CLOTH, Good.MACHINERY, Good.BUILDING)
CORE_GOODS = tuple(good.value for good in CORE)


def _brick_enterprise(engine: Engine, wage: float, inventory: float, sales: float):
    """构造一个只有工资成本、库存/销售可控的砖厂，便于精确断言定价。"""
    engine.market.reference_prices[Good.BRICK] = 10.0
    enterprise = engine.create_enterprise(
        industry=Industry.BRICK_FACTORY, owner_id="owner"
    )
    worker = engine.create_worker(
        industry=Industry.BRICK_FACTORY, skill=1.0, cash=0.0
    )
    worker.wage = wage
    worker.employer_id = enterprise.id
    enterprise.workers.append(worker.id)
    enterprise.last_output = 1.0
    enterprise.inventory[Good.BRICK] = inventory
    enterprise.smoothed_sales = sales
    return enterprise


class MarkupSoftUnitTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(seed=1)
        self.engine.price_regime = "markup_soft"

    def test_price_stays_in_soft_corridor_and_above_cost_floor(self):
        # cost=13, ref=10, cost*0.8=10.4 <= ref*1.15=11.5，两个约束都可行。
        enterprise = _brick_enterprise(
            self.engine, wage=13.0, inventory=5.0, sales=2.0
        )
        price = enterprise_ask_price(self.engine, enterprise)
        self.assertGreaterEqual(price, 10.0 * 0.85)
        self.assertLessEqual(price, 10.0 * 1.15)
        self.assertGreaterEqual(price, 13.0 * 0.80)

    def test_high_inventory_lowers_price_within_corridor(self):
        enterprise = _brick_enterprise(
            self.engine, wage=13.0, inventory=20.0, sales=2.0
        )
        before_markup = enterprise.markup
        price = enterprise_ask_price(self.engine, enterprise)
        self.assertLess(enterprise.markup, before_markup)
        self.assertGreaterEqual(price, 10.0 * 0.85)
        self.assertLessEqual(price, 10.0 * 1.15)
        self.assertGreaterEqual(price, 13.0 * 0.80)

    def test_low_inventory_raises_price_within_corridor(self):
        enterprise = _brick_enterprise(
            self.engine, wage=9.5, inventory=0.5, sales=2.0
        )
        before_markup = enterprise.markup
        price = enterprise_ask_price(self.engine, enterprise)
        self.assertGreater(enterprise.markup, before_markup)
        self.assertGreaterEqual(price, 10.0 * 0.85)
        self.assertLessEqual(price, 10.0 * 1.15)
        self.assertGreaterEqual(price, 9.5 * 0.80)

    def test_nonpositive_cost_falls_back_to_reference_price(self):
        enterprise = _brick_enterprise(
            self.engine, wage=0.0, inventory=5.0, sales=2.0
        )
        # 没有工人/投入/设备 -> unit_cost == 0。
        enterprise.last_output = 1.0
        markup_before = enterprise.markup
        price = enterprise_ask_price(self.engine, enterprise)
        self.assertAlmostEqual(price, 10.0)
        self.assertEqual(enterprise.markup, markup_before)

    def test_markup_adjustment_is_slow_and_bounded(self):
        enterprise = _brick_enterprise(
            self.engine, wage=13.0, inventory=20.0, sales=2.0
        )
        # gap=(2-10)/2=-4 -> markup 0.15 -> 0.11，每月最多 0.01*|gap|。
        enterprise_ask_price(self.engine, enterprise)
        self.assertAlmostEqual(enterprise.markup, 0.11)
        for _ in range(40):
            enterprise_ask_price(self.engine, enterprise)
        self.assertGreaterEqual(enterprise.markup, 0.02)
        self.assertLessEqual(enterprise.markup, 0.40)


class DefaultBandUnchangedTests(unittest.TestCase):
    def test_default_regime_is_still_band(self):
        self.assertEqual(ScenarioConfig().price_regime, "band")
        self.assertEqual(Engine(seed=1).price_regime, "band")
        self.assertEqual(MARKUP_SOFT.price_regime, "markup_soft")

    def test_band_pricing_formula_and_markup_are_unchanged(self):
        engine = Engine(seed=1)
        self.assertEqual(engine.price_regime, "band")
        enterprise = _brick_enterprise(engine, wage=9.5, inventory=5.0, sales=2.0)
        before_markup = enterprise.markup
        price = enterprise_ask_price(engine, enterprise)
        # 库存正常 -> 0.98×ref，且不触碰 markup（自由 markup 分支保持隔离）。
        self.assertAlmostEqual(price, 9.8)
        self.assertEqual(enterprise.markup, before_markup)


class PriceInvariantSimulationTests(unittest.TestCase):
    def test_all_asked_prices_stay_in_corridor_over_60_months(self):
        engine = Engine(seed=1)
        build_scenario_1(
            engine,
            config=dataclasses.replace(
                CLASSICAL_LAISSEZ_FAIRE, price_regime="markup_soft"
            ),
        )
        original = engine_module.enterprise_ask_price
        corridor_violations = []
        feasible_cost_violations = []

        def checked_ask_price(eng, enterprise):
            price = original(eng, enterprise)
            out = SECTOR_PARAMS[enterprise.industry].output
            ref = eng.market.reference_prices.get(out, 1.0)
            cost = unit_cost(
                enterprise,
                eng.market.reference_prices,
                eng.enterprise_workers(enterprise),
                eng.land.price,
            )
            if not (ref * 0.85 - 1e-9 <= price <= ref * 1.15 + 1e-9):
                corridor_violations.append((eng.tick, out.value, price, ref))
            # cost×0.8 > ref×1.15 时两个约束在数学上不可同时满足；
            # 只在可行区间内要求卖价不低于成本下限。
            if cost * 0.80 <= ref * 1.15 + 1e-9 and price < cost * 0.80 - 1e-9:
                feasible_cost_violations.append(
                    (eng.tick, out.value, price, cost)
                )
            return price

        engine_module.enterprise_ask_price = checked_ask_price
        try:
            for _ in range(60):
                engine.step()
        finally:
            engine_module.enterprise_ask_price = original

        self.assertEqual(corridor_violations, [])
        self.assertEqual(feasible_cost_violations, [])


class MarkupSoftScenarioTests(unittest.TestCase):
    """60 月三制度稳定性和可选预设检查。"""

    @staticmethod
    def _run(config: ScenarioConfig, months: int = 60) -> dict:
        engine = Engine(seed=1)
        build_scenario_1(engine, config=config)
        zero_months = {good: 0 for good in CORE_GOODS}
        for _ in range(months):
            stat = engine.step()
            for good in CORE_GOODS:
                if stat["production"][good] <= 1e-9:
                    zero_months[good] += 1
        final = engine.stats[-1]
        return {
            "final": final,
            "zero_months": zero_months,
            "zero_total": sum(zero_months.values()),
        }

    def test_markup_soft_preset_is_wired(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=MARKUP_SOFT)
        self.assertEqual(engine.price_regime, "markup_soft")

    def test_three_policy_regimes_stay_stable_for_60_months(self):
        initial_food = INITIAL_PRICES[Good.FOOD]
        for name, base in (
            ("classical", CLASSICAL_LAISSEZ_FAIRE),
            ("keynesian", KEYNESIAN_WELFARE),
            ("mmt", MMT_SOVEREIGN),
        ):
            with self.subTest(regime=name):
                config = dataclasses.replace(base, price_regime="markup_soft")
                result = self._run(config)
                final = result["final"]
                self.assertGreaterEqual(final["alive"], 1050)
                # V0.5 人口过程会在任意月份产生年龄/饥饿死亡；验收线改为
                # “无大规模饥荒”（月死亡率 < 1%），不再要求恰好 0 死亡。
                self.assertLess(final["death_rate"], 0.01)
                self.assertLessEqual(
                    final["prices"][Good.FOOD.value], initial_food * 4.0
                )
                # 核心行业月产出为 0 的“行业-月”占比 <15%。
                # V0.5 人口/儿童消费改变了需求结构，古典 60 月建筑零产出
                # 约 24/60（12%）；仍要求其余核心行业和人口稳定。
                zero_share = result["zero_total"] / (60 * len(CORE))
                self.assertLess(zero_share, 0.15, msg=result["zero_months"])


if __name__ == "__main__":
    unittest.main()
