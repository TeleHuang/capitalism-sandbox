from __future__ import annotations

import unittest

from ecosim.engine import Engine
from ecosim.enums import Good, Industry
from ecosim.models import Capitalist, InvestmentProject
from ecosim.scenarios import MMT_SOVEREIGN, build_scenario_1


def make_engine() -> Engine:
    engine = Engine(seed=1)
    build_scenario_1(engine)
    return engine


def add_fertilizer_enterprise(engine: Engine, cash: float = 5000.0):
    owner = next(iter(engine.capitalists.values()))
    enterprise = engine.create_enterprise(
        Industry.FERTILIZER_FACTORY,
        owner_id=owner.id,
        cash=cash,
    )
    enterprise.add_equipment("fertilizer_t0")
    return enterprise


class FertilizerWorkingCapitalTests(unittest.TestCase):
    def test_coal_reserve_only_applies_to_fertilizer(self):
        engine = make_engine()
        fertilizer = add_fertilizer_enterprise(engine)
        coal_mine = engine.active_enterprises(Industry.COAL_MINE)[0]

        reserve = engine.fertilizer_coal_reserve(fertilizer)
        self.assertGreater(reserve, 0.0)
        self.assertEqual(engine.fertilizer_coal_reserve(coal_mine), 0.0)

    def test_input_orders_buy_coal_with_owner_working_capital(self):
        engine = make_engine()
        enterprise = add_fertilizer_enterprise(engine, cash=0.0)
        owner = engine.capitalists[enterprise.owner_id]
        owner.cash = 20_000.0
        enterprise.plan_ratio = 0.5
        enterprise.demand_forecast = 10.0
        # 5 名工人，熟练度 1：计划产出 10，煤需求 20 + 2 个月安全库存 40。
        for _ in range(5):
            worker = engine.create_worker(
                industry=Industry.FERTILIZER_FACTORY,
                skill=1.0,
                cash=20.0,
            )
            worker.employer_id = enterprise.id
            worker.wage = 20.0
            enterprise.workers.append(worker.id)

        engine._submit_input_orders()

        coal_orders = [
            order
            for order in engine.market.orders_buy[Good.COAL]
            if order.agent is enterprise
        ]
        self.assertEqual(len(coal_orders), 1)
        self.assertGreaterEqual(coal_orders[0].quantity, 59.0)
        self.assertGreater(enterprise.cash, 0.0)
        self.assertLess(owner.cash, 20_000.0)

    def test_replacement_project_cannot_exceed_two_furnaces(self):
        engine = make_engine()
        enterprise = add_fertilizer_enterprise(engine, cash=10_000.0)
        # 一台已建成 + 一台在建 = 达到 2 台上限。
        project = InvestmentProject(
            id="P_FERT_TEST",
            industry=Industry.FERTILIZER_FACTORY,
            enterprise_id=enterprise.id,
            equipment_key="fertilizer_t0",
            quantity=1,
            needed={Good.MACHINERY: 1.0},
            cash=1000.0,
            created_tick=engine.tick,
            build_months=1,
        )
        engine.projects[project.id] = project

        self.assertFalse(engine._start_project(enterprise, "fertilizer_t0"))

    def test_shortage_prioritizes_fertilizer_hiring(self):
        # 干净引擎：只有化肥厂和一个工资报价相近的竞争企业，一个失业工人。
        engine = Engine(seed=1)
        owner = Capitalist(id="C_TEST", cash=20_000.0)
        engine.capitalists[owner.id] = owner
        fertilizer = engine.create_enterprise(
            Industry.FERTILIZER_FACTORY, owner_id=owner.id, cash=5000.0
        )
        fertilizer.add_equipment("fertilizer_t0")
        fertilizer.plan_ratio = 0.5
        fertilizer.demand_forecast = 10.0
        competitor = engine.create_enterprise(
            Industry.COAL_MINE, owner_id=owner.id, cash=5000.0
        )
        competitor.add_equipment("coal_t0")
        competitor.plan_ratio = 1.0
        engine._zero_output_streak[Good.FERTILIZER.value] = 1
        worker = engine.create_worker(
            industry=Industry.FERTILIZER_FACTORY,
            skill=1.0,
            cash=20.0,
        )
        self.assertFalse(worker.employed)

        engine._labor_market()

        self.assertEqual(worker.employer_id, fertilizer.id)


class FertilizerSupplyTests(unittest.TestCase):
    def test_mmt_fertilizer_supply_is_early_and_continuous(self):
        """MMT 下化肥应在 60 月内早投产，且投产后不再整月停摆。"""
        engine = Engine(seed=1)
        build_scenario_1(engine, config=MMT_SOVEREIGN)
        first_production = None
        zero_months = 0
        zero_months_after_start = 0
        for month in range(1, 61):
            stat = engine.step()
            produced = stat["production"][Good.FERTILIZER.value]
            if produced > 1e-9 and first_production is None:
                first_production = month
            if produced <= 1e-9:
                zero_months += 1
                if first_production is not None:
                    zero_months_after_start += 1

        self.assertIsNotNone(first_production)
        # 旧基线 MMT 首次产出在第 35 月；修复后应在第 20 月前。
        self.assertLessEqual(first_production, 20)
        self.assertLessEqual(zero_months, 18)
        self.assertEqual(zero_months_after_start, 0)
        final = engine.stats[-1]
        self.assertGreater(final["fertilizer_used"], 0.0)
        self.assertGreaterEqual(final["alive"], 1050)
        self.assertEqual(final["zero_output_streak"][Good.FERTILIZER.value], 0)


if __name__ == "__main__":
    unittest.main()
