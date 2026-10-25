"""V0.6 需求侧测试：收入依赖需求、肉类质量阶梯、服务吸收劳动。

覆盖：
- Stone-Geary 需求函数的食品占比随收入下降、衣物/住房/服务随收入上升；
- 口粮生存底线与预算恒等式/安全上限；
- 畜牧业把饲料粮转化为肉类，库存非负、货币守恒；
- 家庭在肉类市场出清时按收入目标购买；
- 古典 240 月：无饥荒、货币守恒、服务就业吸收劳动。
"""

from __future__ import annotations

import unittest

from ecosim.config import INITIAL_PRICES, LIVESTOCK_FEED_PER_MEAT
from ecosim.demand import (
    DEFAULT_DEMAND,
    demand_shares,
    demand_targets,
)
from ecosim.engine import Engine
from ecosim.enums import Good, Industry
from ecosim.production import produce
from ecosim.scenarios import CLASSICAL_LAISSEZ_FAIRE, build_scenario_1

try:  # 兼容 `python -m unittest discover -s tests` 和包内导入
    from tests._slow import slow
except ImportError:  # pragma: no cover
    from _slow import slow

PRICES = dict(INITIAL_PRICES)


def targets_for(budget: float) -> dict:
    return demand_targets(budget, PRICES)


def food_total_share(budget: float) -> float:
    return demand_shares(targets_for(budget), PRICES)["food_total"]


class DemandFunctionTests(unittest.TestCase):
    def test_food_share_falls_with_income(self):
        # 初始工资 20 元附近：低/中/高收入预算。
        low = food_total_share(18.0)
        mid = food_total_share(37.5)
        high = food_total_share(75.0)
        self.assertGreaterEqual(low, 0.55)
        self.assertLessEqual(low, 0.65)
        self.assertGreaterEqual(high, 0.20)
        self.assertLessEqual(high, 0.30)
        self.assertLess(high, mid)
        self.assertLess(mid, low)
        # 口粮本身（不含肉类）的份额也必须下降。
        self.assertLess(
            demand_shares(targets_for(75.0), PRICES)["food"],
            demand_shares(targets_for(18.0), PRICES)["food"],
        )

    def test_clothing_housing_service_rise_with_income(self):
        low = targets_for(18.0)
        mid = targets_for(37.5)
        high = targets_for(75.0)
        for good in (Good.CLOTH, Good.BUILDING, Good.SERVICE):
            self.assertLess(low[good], mid[good], msg=good.value)
            self.assertLess(mid[good], high[good], msg=good.value)
        # 服务是收入弹性最高的类别：按预算份额的增幅比较，
        # 服务的份额上升幅度应大于衣物/住房（价格差异使实物量
        # 增幅不可直接比较）。
        low_shares = demand_shares(low, PRICES)
        high_shares = demand_shares(high, PRICES)
        self.assertGreater(
            high_shares["service"] - low_shares["service"],
            high_shares["cloth"] - low_shares["cloth"],
        )
        self.assertGreater(
            high_shares["service"] - low_shares["service"],
            high_shares["housing"] - low_shares["housing"],
        )
        self.assertGreater(high[Good.SERVICE], 3.0 * low[Good.SERVICE])

    def test_meat_demand_appears_only_above_subsistence(self):
        low = targets_for(18.0)
        mid = targets_for(40.0)
        high = targets_for(80.0)
        self.assertAlmostEqual(low[Good.MEAT], 0.0, places=9)
        self.assertGreater(mid[Good.MEAT], 0.0)
        self.assertGreater(high[Good.MEAT], mid[Good.MEAT])

    def test_food_subsistence_floor_survives_any_budget(self):
        for budget in (0.0, 1.0, 5.0, 12.0, 18.0):
            targets = targets_for(budget)
            self.assertGreaterEqual(
                targets[Good.FOOD], DEFAULT_DEMAND.food_subsistence - 1e-12
            )

    def test_budget_identity_and_caps(self):
        budget = 75.0
        targets = targets_for(budget)
        spent = sum(targets[good] * PRICES[good] for good in targets)
        self.assertAlmostEqual(spent, budget, places=6)

        huge = targets_for(10_000.0)
        caps = DEFAULT_DEMAND.quantity_caps()
        # 口粮是饱和的生存品：即使收入极高也停在生存底线，不会撞上限。
        self.assertAlmostEqual(
            huge[Good.FOOD], DEFAULT_DEMAND.food_subsistence, places=9
        )
        for good in (Good.MEAT, Good.CLOTH, Good.BUILDING, Good.SERVICE):
            self.assertAlmostEqual(
                huge[good], caps[good], places=9, msg=good.value
            )
        self.assertLess(sum(huge[g] * PRICES[g] for g in huge), 10_000.0)


class MeatProductionTests(unittest.TestCase):
    def _engine(self) -> Engine:
        engine = Engine(seed=1)
        build_scenario_1(engine, config=CLASSICAL_LAISSEZ_FAIRE)
        return engine

    def test_livestock_transforms_feed_grain_into_meat(self):
        engine = self._engine()
        owner = next(iter(engine.capitalists.values()))
        enterprise = engine.create_enterprise(
            Industry.LIVESTOCK, owner_id=owner.id, cash=10_000.0
        )
        enterprise.add_equipment("livestock_t0", 1)
        enterprise.inventory[Good.FOOD] = 1000.0
        enterprise.plan_ratio = 1.0
        for _ in range(5):
            worker = engine.create_worker(
                Industry.LIVESTOCK, skill=2.0, cash=0.0, food=0.0
            )
            worker.employer_id = enterprise.id
            enterprise.workers.append(worker.id)

        output = produce(engine, enterprise)

        self.assertGreater(output, 0.0)
        self.assertAlmostEqual(
            enterprise.inv(Good.MEAT), output, places=9
        )
        self.assertAlmostEqual(
            enterprise.inv(Good.FOOD),
            1000.0 - output * LIVESTOCK_FEED_PER_MEAT,
            places=9,
        )
        self.assertAlmostEqual(
            enterprise.last_input_used[Good.FOOD],
            output * LIVESTOCK_FEED_PER_MEAT,
            places=9,
        )
        self.assertGreaterEqual(enterprise.inv(Good.FOOD), 0.0)

    def test_high_income_household_buys_meat_and_money_is_conserved(self):
        engine = self._engine()
        owner = next(iter(engine.capitalists.values()))
        seller = engine.create_enterprise(
            Industry.LIVESTOCK, owner_id=owner.id, cash=0.0
        )
        seller.inventory[Good.MEAT] = 10.0

        worker = next(
            w
            for w in engine.workers.values()
            if w.alive and not w.is_child and not w.is_owner_operator
        )
        old_employer = engine.enterprises[worker.employer_id]
        old_employer.workers.remove(worker.id)
        worker.cash = 1000.0
        worker.wage = 100.0
        worker.hours = 16
        worker.employer_id = old_employer.id
        old_employer.workers.append(worker.id)

        before = engine.total_money()
        engine._submit_geary_worker_orders(worker, PRICES)
        engine.market.submit_sell(seller, Good.MEAT, 10.0, PRICES[Good.MEAT])
        engine.market.match()

        self.assertGreater(worker.meat, 0.0)
        self.assertAlmostEqual(engine.total_money(), before, places=6)
        self.assertGreater(seller.cash, 0.0)


class DemandStatsTests(unittest.TestCase):
    """快速统计口径测试：只跑一个月，不进入默认套件的长程 simulation。"""

    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(seed=1)
        build_scenario_1(cls.engine, config=CLASSICAL_LAISSEZ_FAIRE)
        cls.engine.step()
        cls.final = cls.engine.stats[-1]

    def test_stats_expose_demand_and_service_indicators(self):
        for key in (
            "budget_shares",
            "food_share",
            "food_total_share",
            "meat_share",
            "cloth_share",
            "housing_share",
            "service_spending_share",
            "demand_targets",
            "demand_budget",
            "real_wage_proxy",
            "consumer_price_index",
            "service_employment_share",
            "livestock_employment_share",
            "market_budget_shares",
            "market_meat_share",
            "capitalist_meat_consumed",
        ):
            self.assertIn(key, self.final)
        for good in ("food", "meat", "cloth", "housing", "service"):
            self.assertIn(good, self.final["budget_shares"])
        for good in ("food", "meat", "cloth", "building", "service"):
            self.assertIn(good, self.final["demand_targets"])

    def test_budget_shares_sum_to_one_when_spending_positive(self):
        shares = self.final["budget_shares"]
        total = sum(
            shares[key]
            for key in ("food", "meat", "cloth", "housing", "service")
        )
        self.assertAlmostEqual(total, 1.0, places=6)


@slow
class DemandSlowSimulationTests(unittest.TestCase):
    """240 月冒烟：默认跳过，ECOSIM_SLOW_TESTS=1 时运行。"""

    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(seed=1)
        build_scenario_1(cls.engine, config=CLASSICAL_LAISSEZ_FAIRE)
        for _ in range(240):
            cls.engine.step()
        cls.final = cls.engine.stats[-1]

    def test_240_month_no_famine_and_money_conserved(self):
        hunger = sum(stat["hunger_deaths"] for stat in self.engine.stats)
        self.assertEqual(hunger, 0)
        self.assertAlmostEqual(
            self.final["money_total"], self.engine.money_initial, places=2
        )
        self.assertGreater(self.final["alive"], 1000)

    def test_services_absorb_labour_when_industry_sheds_workers(self):
        # 服务自雇吸收工业释放的劳动力；只要求“确实吸收”，
        # 不把旧的零失业基线当作硬目标。
        self.assertGreater(self.final["service_employment_share"], 0.25)
        self.assertGreater(self.final["workers_by_industry"]["service"], 300)
        # free 默认下古典 240 月失业约 20.3%；这里只防“服务业没有吸收、
        # 失业失控”，不把 band 的低失业当硬目标。
        self.assertLess(self.final["unemployment_rate"], 0.25)
        self.assertGreater(self.final["service_spending_share"], 0.15)

    def test_meat_is_produced_and_demanded_over_240_months(self):
        self.assertGreater(
            sum(stat["production"]["meat"] for stat in self.engine.stats), 0.0
        )
        self.assertGreater(
            sum(stat["demand"]["meat"] for stat in self.engine.stats), 0.0
        )
        self.assertGreater(self.final["firms"]["livestock"], 0)
        # 低实际工资下工人肉类消费接近 0，高收入资本家仍有正肉类消费。
        self.assertGreater(self.final["capitalist_meat_consumed"], 0.0)


if __name__ == "__main__":
    unittest.main()
