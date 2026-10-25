from __future__ import annotations

import unittest

from ecosim.config import DEPRECIATION_MONTHS, EQUIPMENT
from ecosim.decisions import should_invest, should_switch
from ecosim.engine import Engine
from ecosim.enums import Good, Industry
from ecosim.models import InvestmentProject
from ecosim.production import desired_workers, equipment_value, produce
from ecosim.scenarios import build_scenario_1


def make_engine() -> Engine:
    engine = Engine(seed=1)
    build_scenario_1(engine)
    return engine


class FeedbackTests(unittest.TestCase):
    def test_production_plan_limits_output(self):
        engine = make_engine()
        steel = engine.active_enterprises(Industry.STEEL_MILL)[0]
        steel.plan_ratio = 0.2
        output = produce(engine, steel)
        # steel_t0 产能 50，熟练度 2，计划 0.2 → 上限 20 吨。
        self.assertLessEqual(output, 50.0 * 0.2 * 2.0 + 1e-6)
        self.assertGreater(output, 0.0)

    def test_desired_workers_follow_plan(self):
        engine = make_engine()
        steel = engine.active_enterprises(Industry.STEEL_MILL)[0]
        full = desired_workers(steel, plan=1.0)
        half = desired_workers(steel, plan=0.5)
        self.assertLessEqual(half, full)
        self.assertGreaterEqual(half, 1)

    def test_switch_threshold_rejects_pay_cut(self):
        self.assertFalse(should_switch(100.0, 95.0))
        self.assertFalse(should_switch(100.0, 100.0))
        self.assertFalse(should_switch(100.0, 105.0))
        self.assertTrue(should_switch(100.0, 107.0))

    def test_manual_bootstrap_restarts_empty_industry(self):
        engine = make_engine()
        for enterprise in engine.active_enterprises(Industry.BRICK_FACTORY):
            enterprise.active = False
        engine._investment_decisions()
        brick_firms = engine.active_enterprises(Industry.BRICK_FACTORY)
        self.assertTrue(brick_firms)
        self.assertIn("brick_manual", brick_firms[0].equipment)

    def test_fertilizer_cap_counts_pending_projects(self):
        engine = make_engine()
        owner = next(iter(engine.capitalists.values()))
        enterprise = engine.create_enterprise(
            Industry.FERTILIZER_FACTORY, owner_id=owner.id, cash=10_000.0
        )
        enterprise.add_equipment("fertilizer_t0")
        project = InvestmentProject(
            id="P_TEST",
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
        self.assertIsNone(should_invest(engine, enterprise))

    def test_bankruptcy_writes_off_debt_and_recycles_assets(self):
        engine = make_engine()
        enterprise = engine.active_enterprises(Industry.COAL_MINE)[0]
        enterprise.debt = 1000.0
        engine.bank.loans[enterprise.id] = 1000.0
        enterprise.inventory[Good.COAL] = 10.0
        enterprise.land = 5.0
        worker_ids = list(enterprise.workers)
        engine._liquidate(enterprise)
        self.assertFalse(enterprise.active)
        self.assertEqual(enterprise.debt, 0.0)
        self.assertNotIn(enterprise.id, engine.bank.loans)
        self.assertGreaterEqual(engine.bank.write_offs, 1000.0)
        self.assertGreaterEqual(engine.asset_pool.inventory[Good.COAL], 10.0)
        self.assertGreaterEqual(engine.asset_pool.equipment.get("coal_t0", 0), 1)
        self.assertGreaterEqual(engine.land.estate_land, 5.0)
        for worker_id in worker_ids:
            self.assertIsNone(engine.workers[worker_id].employer_id)

    def test_depreciation_excludes_land(self):
        engine = make_engine()
        farm = next(
            enterprise
            for enterprise in engine.active_enterprises(Industry.AGRICULTURE)
            if enterprise.is_household
        )
        # 本测试只验证“土地不计折旧”，与家庭经营所得 payout 无关。
        # 关闭 household 分支，避免 payout 按设计改变 last_profit。
        farm.is_household = False
        farm.month_revenue = 100.0
        farm.month_wages = 10.0
        farm.month_interest = 0.0
        farm.last_input_used = {}
        farm.debt = 0.0
        engine._finance()
        # 土地不计折旧；没有设备时折旧为 0。
        self.assertAlmostEqual(farm.last_profit, 90.0, places=6)

    def test_dead_smallholder_estate_is_settled(self):
        engine = make_engine()
        farm = next(
            enterprise
            for enterprise in engine.active_enterprises(Industry.AGRICULTURE)
            if enterprise.is_household
        )
        owner = engine.workers[farm.owner_id]
        engine._settle_estate(owner)
        self.assertFalse(farm.active)
        self.assertFalse(owner.is_owner_operator)
        self.assertEqual(owner.land_owned, 0.0)
        self.assertNotIn(owner.id, engine.land.owners)
        self.assertGreaterEqual(engine.land.estate_land, 10.0)

    def test_project_inventory_returns_to_enterprise(self):
        engine = make_engine()
        enterprise = engine.active_enterprises(Industry.COAL_MINE)[0]
        before = enterprise.inv(Good.COAL)
        project = InvestmentProject(
            id="P_TEST",
            industry=Industry.COAL_MINE,
            enterprise_id=enterprise.id,
            equipment_key="coal_t0",
            quantity=1,
            needed={},
            cash=0.0,
            created_tick=engine.tick,
            build_months=0,
        )
        project.inventory[Good.COAL] = 5.0
        engine.projects[project.id] = project
        engine._complete_project(project)
        self.assertAlmostEqual(enterprise.inv(Good.COAL), before + 5.0, places=6)

    def test_money_is_conserved_with_new_mechanisms(self):
        engine = make_engine()
        for _ in range(24):
            engine.step()
        self.assertAlmostEqual(
            engine.total_money(), engine.money_initial, places=2
        )


if __name__ == "__main__":
    unittest.main()
