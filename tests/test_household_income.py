"""家庭农场经营所得会计回归测试。

旧实现把自耕农所有者同时当作所有者和雇员：`_pay_wages` 按
``WAGE_BASE`` 给他发工资，现金不足时由所有者垫资或银行放贷，
导致家庭农场为“给自己发工资”而负债并在价格压力下破产。

修复后自耕农所有者是剩余索取者：

- `_labor_market` / 播种 / 继承都把 owner.wage 保持为 0；
- `_pay_wages` 把所有者排除在工资账单和支付循环之外（雇工照常发薪）；
- `_finance` 把扣除 ``HOUSEHOLD_FARM_RESERVE`` 后的经营现金作为
  家庭经营所得 payout，并从 ``last_profit`` 扣除；
- PAYG 缴费按 payout 代扣，保证自耕农不因 wage=0 而逃避缴费。
"""

from __future__ import annotations

import unittest

from ecosim.config import (
    HOUSEHOLD_FARM_RESERVE,
    SERVICE_FIRM_RESERVE,
    WAGE_BASE,
)
from ecosim.engine import Engine
from ecosim.enums import Good, Industry
from ecosim.scenarios import (
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    ScenarioConfig,
    build_scenario_1,
)


def make_engine(config: ScenarioConfig = CLASSICAL_LAISSEZ_FAIRE) -> Engine:
    engine = Engine(seed=1)
    build_scenario_1(engine, config=config)
    return engine


def household_farms(engine: Engine) -> list:
    return [
        enterprise
        for enterprise in engine.active_enterprises(Industry.AGRICULTURE)
        if enterprise.is_household
    ]


class HouseholdFarmWageTests(unittest.TestCase):
    def test_owner_operator_cannot_create_debt_to_pay_himself(self):
        """所有者即使残留非零 wage，也不能进入工资账单/信贷垫付路径。"""
        engine = make_engine()
        farm = household_farms(engine)[0]
        owner = engine.workers[farm.owner_id]
        # 复现旧状态：所有者 wage 非零，农场和所有者都没有现金。
        farm.cash = 0.0
        owner.cash = 0.0
        owner.wage = WAGE_BASE
        owner.hours = 16
        farm.month_wages = 0.0
        before_loan = engine.bank.loans.get(farm.id, 0.0)

        engine._pay_wages()

        self.assertEqual(owner.wage, WAGE_BASE)  # 直接调用不改写数据
        self.assertEqual(farm.month_wages, 0.0)
        self.assertEqual(farm.cash, 0.0)
        self.assertEqual(farm.debt, 0.0)
        self.assertEqual(engine.bank.loans.get(farm.id, 0.0), before_loan)
        self.assertEqual(owner.cash, 0.0)

    def test_hired_workers_on_household_farm_are_still_paid(self):
        """排除的只是所有者；家庭农场雇工照常领工资。"""
        engine = make_engine()
        farm = household_farms(engine)[0]
        owner = engine.workers[farm.owner_id]
        hired = engine.create_worker(
            Industry.AGRICULTURE,
            cash=0.0,
            food=0.0,
            age_months=30 * 12,
        )
        hired.employer_id = farm.id
        hired.wage = 15.0
        hired.hours = 16
        farm.workers.append(hired.id)
        farm.cash = 100.0
        owner.wage = WAGE_BASE
        owner_before = owner.cash

        engine._pay_wages()

        self.assertEqual(owner.cash, owner_before)
        self.assertAlmostEqual(hired.cash, 15.0, places=6)
        self.assertAlmostEqual(farm.cash, 85.0, places=6)
        self.assertEqual(farm.debt, 0.0)

    def test_labor_market_sets_owner_wage_to_zero(self):
        engine = make_engine()
        farm = household_farms(engine)[0]
        owner = engine.workers[farm.owner_id]
        owner.wage = WAGE_BASE

        engine._labor_market()

        self.assertEqual(owner.wage, 0.0)
        self.assertIs(engine.workers[farm.owner_id], owner)

    def test_residual_payout_is_operating_income_not_profit(self):
        engine = make_engine()
        farm = household_farms(engine)[0]
        owner = engine.workers[farm.owner_id]
        farm.cash = HOUSEHOLD_FARM_RESERVE + 37.5
        farm.debt = 0.0
        farm.month_revenue = 100.0
        farm.month_wages = 0.0
        owner.cash = 10.0
        before_money = engine.total_money()

        engine._finance()

        self.assertAlmostEqual(engine.total_money(), before_money, places=6)
        self.assertAlmostEqual(farm.cash, HOUSEHOLD_FARM_RESERVE, places=6)
        self.assertAlmostEqual(owner.cash, 47.5, places=6)
        self.assertAlmostEqual(farm.last_operating_payout, 37.5, places=6)
        # 利润表已扣除经营所得：100 - 37.5 = 62.5。
        self.assertAlmostEqual(farm.last_profit, 62.5, places=6)


class HouseholdFarmPensionTests(unittest.TestCase):
    def test_payout_withholds_pension_and_preserves_fund_identity(self):
        engine = make_engine(KEYNESIAN_WELFARE)
        gov = engine.government
        self.assertIsNotNone(gov)
        farm = household_farms(engine)[0]
        owner = engine.workers[farm.owner_id]
        # 只让目标农场有可分配现金，隔离出本笔 payout 的缴费。
        for other in household_farms(engine):
            if other is not farm:
                engine.bank.cash += other.cash
                other.cash = 0.0
        farm.cash = HOUSEHOLD_FARM_RESERVE + 100.0
        farm.debt = 0.0
        farm.month_revenue = 0.0
        owner_before = owner.cash
        before_money = engine.total_money()
        before_contrib = gov.pension_contributions
        before_fund = gov.pension_fund
        before_revenue = gov.pension_revenue

        engine._finance()

        contribution = 100.0 * gov.pension_tax_rate
        self.assertAlmostEqual(
            gov.pension_contributions - before_contrib, contribution, places=6
        )
        self.assertAlmostEqual(gov.pension_fund - before_fund, contribution, places=6)
        self.assertAlmostEqual(
            gov.pension_revenue - before_revenue, contribution, places=6
        )
        self.assertAlmostEqual(
            owner.cash - owner_before, 100.0 - contribution, places=6
        )
        self.assertAlmostEqual(farm.cash, HOUSEHOLD_FARM_RESERVE, places=6)
        self.assertAlmostEqual(engine.total_money(), before_money, places=6)


class ServiceSelfEmploymentUnchangedTests(unittest.TestCase):
    def test_service_payout_still_uses_service_reserve(self):
        engine = make_engine()
        worker = next(
            worker
            for worker in engine.workers.values()
            if worker.alive and not worker.is_owner_operator
        )
        old_employer = engine.enterprises[worker.employer_id]
        old_employer.workers.remove(worker.id)
        worker.employer_id = None
        worker.wage = 0.0

        history = engine.market.history[Good.SERVICE]
        history["demand"] = 1.0
        history["supply"] = 0.0
        history["unmet"] = 1.0
        engine._service_self_employment(engine.market.reference_prices)

        service = engine.active_enterprises(Industry.SERVICE)[0]
        owner = engine.workers[service.owner_id]
        self.assertTrue(service.is_household)
        self.assertEqual(owner.wage, 0.0)
        service.cash = SERVICE_FIRM_RESERVE + 40.0
        owner_before = owner.cash
        before_money = engine.total_money()

        engine._finance()

        self.assertAlmostEqual(service.cash, SERVICE_FIRM_RESERVE, places=6)
        self.assertAlmostEqual(
            owner.cash - owner_before, 40.0, places=6
        )
        self.assertAlmostEqual(service.last_operating_payout, 40.0, places=6)
        self.assertAlmostEqual(engine.total_money(), before_money, places=6)


class HouseholdFarmLongRunTests(unittest.TestCase):
    def test_240_month_classical_household_farms_survive_without_famine(self):
        engine = make_engine()
        for _ in range(240):
            engine.step()
        final = engine.stats[-1]
        hunger = sum(stat["hunger_deaths"] for stat in engine.stats)

        # 家庭农场可以减少（土地市场自愿卖地），但不能因“给自己发工资”
        # 的债务而被 `_liquidate` 清算。清算计数是直接回归指标；
        # 农场数量/小农土地只需保证农业没有整体消失。
        self.assertEqual(final["household_farm_liquidations_total"], 0)
        self.assertGreaterEqual(final["household_farms"], 100)
        self.assertGreaterEqual(final["smallholder_land"], 1000.0)
        self.assertGreater(
            final["food_output"], 0.80 * final["demand"]["food"]
        )
        self.assertEqual(hunger, 0)
        self.assertAlmostEqual(
            final["money_total"], engine.money_initial, places=2
        )


if __name__ == "__main__":
    unittest.main()
