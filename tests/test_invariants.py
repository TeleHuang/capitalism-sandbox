"""V0.4 会计/守恒/统计不变量测试。

覆盖：
- 金本位（classical/keynesian）货币守恒；
- bank.loans 与 Σ enterprise.debt 一致（含资本化利息）；
- 政府预算恒等式 deficit = spending + transfers + interest - tax；
- 库存非负、土地总量恒定；
- 统计字段无 NaN/Inf；
- 三制度 60 月 alive > 0。
"""

from __future__ import annotations

import math
import unittest
from typing import Any, Dict, List

from ecosim.config import TOTAL_LAND_MU
from ecosim.engine import Engine
from ecosim.enums import Good
from ecosim.scenarios import (
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    MMT_SOVEREIGN,
    build_scenario_1,
)

REGIMES = {
    "classical": CLASSICAL_LAISSEZ_FAIRE,
    "keynesian": KEYNESIAN_WELFARE,
    "mmt": MMT_SOVEREIGN,
}
MONTHS = 60


def _iter_numeric_fields(value: Any, path: str = ""):
    """递归产出 (path, value)，只关心数值字段。"""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_numeric_fields(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_numeric_fields(item, f"{path}[{index}]")
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float)):
        yield path, float(value)


def _land_total(engine: Engine) -> float:
    """土地守恒口径。

    自耕农土地已在 land.owners；家庭农场企业上的 land 是同一块地的
    会计镜像，不能重复计入。资本主义农场土地是真正从自耕农手里买来的，
    estate_land 是待售遗产，asset_pool.land 是资产池。
    """
    capitalist_land = sum(
        enterprise.land
        for enterprise in engine.active_enterprises()
        if not enterprise.is_household
    )
    return (
        engine.land.smallholder_land
        + capitalist_land
        + engine.land.estate_land
        + engine.asset_pool.land
    )


class InvariantRun:
    def __init__(self, regime: str, months: int = MONTHS, seed: int = 1):
        self.regime = regime
        self.engine = Engine(seed=seed)
        build_scenario_1(self.engine, config=REGIMES[regime])
        self.violations: Dict[str, List[str]] = {
            "money": [],
            "loans": [],
            "budget": [],
            "inventory": [],
            "land": [],
            "nan": [],
        }
        self.max_loan_debt_gap = 0.0
        self.max_money_drift = 0.0
        self.max_budget_gap = 0.0
        self.saw_positive_debt = False
        self.saw_tax_revenue = False
        for _ in range(months):
            self._step_and_check()
        self.final = self.engine.stats[-1]

    def _step_and_check(self) -> None:
        engine = self.engine
        stat = engine.step()
        tick = stat["tick"]

        # 1) 金本位货币守恒（MMT 是信用货币，不在本条）
        if self.regime != "mmt":
            drift = abs(stat["money_total"] - engine.money_initial)
            self.max_money_drift = max(self.max_money_drift, drift)
            if drift > 0.01:
                self.violations["money"].append(
                    f"T{tick}: money_total={stat['money_total']:.4f}, "
                    f"initial={engine.money_initial:.4f}"
                )

        # 2) bank.loans == Σ enterprise.debt（含资本化未付利息）
        total_debt = sum(e.debt for e in engine.enterprises.values())
        total_loans = sum(engine.bank.loans.values())
        gap = abs(total_debt - total_loans)
        self.max_loan_debt_gap = max(self.max_loan_debt_gap, gap)
        if total_debt > 1e-9:
            self.saw_positive_debt = True
        if gap > 1e-6:
            self.violations["loans"].append(
                f"T{tick}: Σdebt={total_debt:.6f}, loans={total_loans:.6f}"
            )

        # 3) 政府预算恒等式（Keynesian/MMT）
        if engine.government is not None:
            if stat["government_tax_revenue"] > 1e-9:
                self.saw_tax_revenue = True
            # V0.5 养老金显式记账：缴费是收入、发放是支出；补贴属于融资。
            identity = (
                stat["government_spending"]
                + stat["government_transfers"]
                + stat["government_interest_paid"]
                + stat["pension_spending"]
                - stat["government_tax_revenue"]
                - stat["pension_contributions"]
            )
            budget_gap = abs(identity - stat["government_deficit"])
            self.max_budget_gap = max(self.max_budget_gap, budget_gap)
            if budget_gap > 1e-6:
                self.violations["budget"].append(
                    f"T{tick}: deficit={stat['government_deficit']:.6f}, "
                    f"identity={identity:.6f}"
                )

        # 4) 库存非负
        for enterprise in engine.enterprises.values():
            for good, qty in enterprise.inventory.items():
                if qty < -1e-9:
                    self.violations["inventory"].append(
                        f"T{tick}: {enterprise.id} {good.value}={qty:.9f}"
                    )
        for project in engine.projects.values():
            for good, qty in project.inventory.items():
                if qty < -1e-9:
                    self.violations["inventory"].append(
                        f"T{tick}: {project.id} {good.value}={qty:.9f}"
                    )
        for holder_name, holder in (
            ("government", engine.government),
            ("food_reserve", engine.food_reserve),
            ("asset_pool", engine.asset_pool),
        ):
            inventory = getattr(holder, "inventory", None)
            if inventory is not None:
                for good, qty in inventory.items():
                    if qty < -1e-9:
                        self.violations["inventory"].append(
                            f"T{tick}: {holder_name} {good.value}={qty:.9f}"
                        )
        if engine.food_reserve.food < -1e-9:
            self.violations["inventory"].append(
                f"T{tick}: food_reserve.food={engine.food_reserve.food:.9f}"
            )
        for worker in engine.workers.values():
            for attr in ("food", "cloth", "housing"):
                qty = getattr(worker, attr)
                if qty < -1e-9:
                    self.violations["inventory"].append(
                        f"T{tick}: {worker.id}.{attr}={qty:.9f}"
                    )

        # 5) 土地总量恒定
        land_total = _land_total(engine)
        if abs(land_total - TOTAL_LAND_MU) > 1e-6:
            self.violations["land"].append(
                f"T{tick}: land_total={land_total:.6f}, "
                f"expected={TOTAL_LAND_MU:.6f}"
            )

        # 6) 统计字段非 NaN/Inf
        for path, value in _iter_numeric_fields(stat):
            if not math.isfinite(value):
                self.violations["nan"].append(f"T{tick}: {path}={value}")


class InvariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runs = {
            regime: InvariantRun(regime) for regime in REGIMES
        }

    def test_gold_standard_money_is_conserved(self):
        for regime in ("classical", "keynesian"):
            run = self.runs[regime]
            self.assertEqual(
                run.violations["money"],
                [],
                msg=f"{regime} 货币守恒破坏（最大漂移 {run.max_money_drift}）",
            )
            self.assertAlmostEqual(
                run.final["money_total"], run.engine.money_initial, places=2
            )

    def test_bank_loans_equal_enterprise_debt(self):
        # 古典 60 月内可能还没有企业债务（0=0 仍应成立）；Keynesian/MMT
        # 有银行中介，必须出现正债务才能证明测试不是空转。
        for regime in ("keynesian", "mmt"):
            self.assertTrue(
                self.runs[regime].saw_positive_debt,
                msg=f"{regime} 60 月内没有出现企业债务，测试不具区分度",
            )
        for regime, run in self.runs.items():
            self.assertEqual(
                run.violations["loans"],
                [],
                msg=(
                    f"{regime} bank.loans 与 Σdebt 最大差异 "
                    f"{run.max_loan_debt_gap}"
                ),
            )

    def test_government_budget_identity(self):
        for regime in ("keynesian", "mmt"):
            run = self.runs[regime]
            self.assertTrue(run.saw_tax_revenue)
            self.assertEqual(
                run.violations["budget"],
                [],
                msg=(
                    f"{regime} 预算恒等式最大差异 {run.max_budget_gap}"
                ),
            )

    def test_no_negative_inventory(self):
        for regime, run in self.runs.items():
            self.assertEqual(
                run.violations["inventory"],
                [],
                msg=f"{regime} 出现负库存：{run.violations['inventory'][:5]}",
            )

    def test_total_land_is_constant(self):
        for regime, run in self.runs.items():
            self.assertEqual(
                run.violations["land"],
                [],
                msg=f"{regime} 土地总量漂移：{run.violations['land'][:5]}",
            )

    def test_stats_have_no_nan_or_inf(self):
        for regime, run in self.runs.items():
            self.assertEqual(
                run.violations["nan"],
                [],
                msg=f"{regime} 统计字段非有限：{run.violations['nan'][:5]}",
            )

    def test_all_regimes_alive_after_60_months(self):
        for regime, run in self.runs.items():
            self.assertGreater(
                run.final["alive"], 0, msg=f"{regime} 60 月全灭"
            )
            self.assertGreater(
                run.final["alive"],
                1000,
                msg=f"{regime} 60 月存活异常偏低：{run.final['alive']}",
            )


class ShockHookDefaultTests(unittest.TestCase):
    """新增的冲击钩子默认必须中性，不能改变基线行为。"""

    def test_default_hooks_are_neutral(self):
        engine = Engine(seed=1)
        build_scenario_1(engine)
        self.assertEqual(engine.worker_demand_scale, 1.0)
        self.assertEqual(engine.capitalist_demand_scale, 1.0)
        self.assertEqual(engine.lending_scale, 1.0)
        self.assertEqual(engine.productivity_multipliers, {})
        self.assertEqual(engine.bank.frozen_cash, 0.0)

    def test_unpaid_interest_is_capitalized_into_loans(self):
        engine = Engine(seed=1)
        build_scenario_1(engine)
        enterprise = engine.active_enterprises()[0]
        enterprise.debt = 1000.0
        engine.bank.loans[enterprise.id] = 1000.0
        enterprise.cash = 0.0
        engine.bank.charge_interest(enterprise)
        expected = 1000.0 * (1.0 + engine.bank.interest_rate)
        self.assertAlmostEqual(enterprise.debt, expected, places=6)
        self.assertAlmostEqual(
            engine.bank.loans[enterprise.id], expected, places=6
        )

    def test_frozen_reserves_keep_money_conserved(self):
        engine = Engine(seed=1)
        build_scenario_1(engine, config=KEYNESIAN_WELFARE)
        before = engine.total_money()
        amount = engine.bank.cash * 0.5
        engine.bank.cash -= amount
        engine.bank.frozen_cash += amount
        self.assertAlmostEqual(engine.total_money(), before, places=6)
        engine.bank.frozen_cash -= amount
        engine.bank.cash += amount
        self.assertAlmostEqual(engine.total_money(), before, places=6)


if __name__ == "__main__":
    unittest.main()
