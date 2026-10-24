from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Dict, List, Optional

from .config import (
    BANK_CASH,
    BANK_INTEREST_RATE,
    BANK_LOAN_MONTHS,
    CAPITALIST_CONSUMPTION_RATE,
    CAPITALIST_FOOD,
    CAPITALIST_CLOTH,
    CAPITALIST_HOUSING,
    CAPITALIST_MIN_CONSUMPTION,
    CLOTH_PER_WORKER,
    COMFORT_MULTIPLIER,
    DEPRECIATION_MONTHS,
    DIVIDEND_PAYOUT,
    EQUIPMENT,
    FOOD_PER_WORKER,
    HOUSING_PER_WORKER,
    INITIAL_LAND_PRICE,
    INITIAL_PRICES,
    INVESTMENT_HURDLE,
    MAX_ACTIVE_PROJECTS,
    MAX_NEW_FIRMS_PER_TICK,
    MAX_PROJECTS_PER_TICK,
    PROJECT_TIMEOUT_MONTHS,
    SECTOR_PARAMS,
    SKILL_GROWTH_PER_MONTH,
    SKILL_MAX,
    TOTAL_LAND_MU,
    WAGE_BASE,
)
from .decisions import (
    agricultural_entry_roi,
    best_equipment_choice,
    enterprise_ask_price,
    enterprise_wage_offer,
    input_needs,
    production_plan,
    should_invest,
    wants_fertilizer,
    wage_floor,
)
from .enums import GOOD_LABELS, Good, Industry
from .land import run_land_market
from .market import Market
from .models import (
    Bank,
    Capitalist,
    Enterprise,
    InvestmentProject,
    LandMarket,
    Worker,
)
from .production import (
    capital_value,
    desired_workers,
    equipment_cost,
    inventory_value,
    net_worth,
    produce,
    unit_cost,
)


class Engine:
    def __init__(self, seed: int = 1):
        self.seed = seed
        self.rng = random.Random(seed)
        self.tick = 0
        self.workers: Dict[str, Worker] = {}
        self.enterprises: Dict[str, Enterprise] = {}
        self.capitalists: Dict[str, Capitalist] = {}
        self.projects: Dict[str, InvestmentProject] = {}
        self.market = Market(INITIAL_PRICES)
        self.land = LandMarket(TOTAL_LAND_MU, INITIAL_LAND_PRICE)
        self.bank = Bank(BANK_CASH, BANK_INTEREST_RATE)
        self.stats: List[dict] = []
        self.money_initial = 0.0
        self.dead_this_month = 0
        self.production_month: Dict[Good, float] = {g: 0.0 for g in Good}
        self._next_worker = 0
        self._next_enterprise = 0
        self._next_project = 0
        self._zero_output_streak: Dict[str, int] = defaultdict(int)
        self._warnings: List[str] = []

    # ------------------------------------------------------------------
    # 身份 / 查询辅助
    # ------------------------------------------------------------------
    def new_worker_id(self) -> str:
        self._next_worker += 1
        return f"W_{self._next_worker - 1}"

    def new_enterprise_id(self) -> str:
        self._next_enterprise += 1
        return f"E_{self._next_enterprise - 1}"

    def new_project_id(self) -> str:
        self._next_project += 1
        return f"P_{self._next_project - 1}"

    def enterprise_workers(self, enterprise: Enterprise) -> List[Worker]:
        return [
            self.workers[worker_id]
            for worker_id in enterprise.workers
            if worker_id in self.workers and self.workers[worker_id].alive
        ]

    def sector_params(self, industry: Industry):
        return SECTOR_PARAMS[industry]

    def active_enterprises(self, industry: Optional[Industry] = None) -> List[Enterprise]:
        return [
            e
            for e in self.enterprises.values()
            if e.active and (industry is None or e.industry == industry)
        ]

    def average_wage(self) -> float:
        wages = [
            w.wage
            for w in self.workers.values()
            if w.alive and w.employed and w.wage > 0
        ]
        return sum(wages) / len(wages) if wages else WAGE_BASE

    def total_money(self) -> float:
        return (
            sum(w.cash for w in self.workers.values() if w.alive)
            + sum(c.cash for c in self.capitalists.values())
            + sum(e.cash for e in self.enterprises.values() if e.active)
            + sum(p.cash for p in self.projects.values() if p.active)
            + self.bank.cash
        )

    # ------------------------------------------------------------------
    # 工厂辅助方法
    # ------------------------------------------------------------------
    def create_worker(
        self,
        industry: Industry,
        skill: float = 1.0,
        cash: float = 0.0,
        food: float = FOOD_PER_WORKER,
    ) -> Worker:
        worker = Worker(
            id=self.new_worker_id(),
            industry=industry,
            skill=skill,
            cash=cash,
            food=food,
        )
        self.workers[worker.id] = worker
        return worker

    def create_enterprise(
        self,
        industry: Industry,
        owner_id: str,
        cash: float = 0.0,
        land: float = 0.0,
        is_household: bool = False,
        modernization_capable: bool = True,
    ) -> Enterprise:
        enterprise = Enterprise(
            id=self.new_enterprise_id(),
            industry=industry,
            owner_id=owner_id,
            cash=cash,
            land=land,
            is_household=is_household,
            modernization_capable=modernization_capable,
        )
        self.enterprises[enterprise.id] = enterprise
        return enterprise

    def create_agricultural_enterprise(
        self, capitalist: Capitalist, land_mu: float, price: float
    ) -> Enterprise:
        # 所有者注入的周转资金。资本主义农场需要足够现金
        # 来购买剩余土地和农机；5000 太少，会制造 40 亩的微型农场。

        injection = min(capitalist.cash * 0.5, 20_000.0)
        capitalist.cash -= injection
        enterprise = self.create_enterprise(
            Industry.AGRICULTURE,
            owner_id=capitalist.id,
            cash=injection,
            land=land_mu,
            is_household=False,
            modernization_capable=True,
        )
        return enterprise

    def _start_project(
        self,
        enterprise: Enterprise,
        equipment_key: str,
        is_new: bool = False,
        priority: bool = False,
    ) -> bool:
        active_projects = sum(1 for p in self.projects.values() if p.active)
        if not priority and active_projects >= MAX_ACTIVE_PROJECTS:
            return False
        et = EQUIPMENT[equipment_key]
        needed: Dict[Good, float] = {}
        if et.capital_good is not None and et.capital_cost > 0:
            needed[et.capital_good] = et.capital_cost
        if et.building_cost > 0:
            needed[Good.BUILDING] = et.building_cost
        if not needed:
            return False
        estimate = sum(
            qty * self.market.reference_prices.get(good, 1.0)
            for good, qty in needed.items()
        )
        workers = self.enterprise_workers(enterprise)
        wage_bill = sum(w.wage * w.effective_labor for w in workers)
        reserve = max(wage_bill * 3.0, 100.0)
        if enterprise.cash < estimate * 1.10 + reserve:
            return False
        available = enterprise.cash - reserve
        project_cash = min(available, estimate * 1.25)
        if project_cash < estimate * 0.90:
            return False
        enterprise.cash -= project_cash
        project = InvestmentProject(
            id=self.new_project_id(),
            industry=enterprise.industry,
            enterprise_id=enterprise.id,
            equipment_key=equipment_key,
            quantity=1,
            needed=needed,
            cash=project_cash,
            created_tick=self.tick,
            build_months=et.build_months,
            is_new_enterprise=is_new,
        )
        self.projects[project.id] = project
        enterprise.last_invest_tick = self.tick
        return True

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def step(self) -> dict:
        self.tick += 1
        self.dead_this_month = 0
        self._warnings = []
        self.production_month = {g: 0.0 for g in Good}
        for enterprise in self.enterprises.values():
            enterprise.reset_month_flows()

        self._update_skills()
        self._labor_market()
        self._pay_wages()
        self._produce_all()
        self._update_price_bands()
        run_land_market(self)
        self._investment_decisions()

        self._submit_sell_orders()
        self._submit_household_orders()
        self._submit_input_orders()
        self._submit_project_orders()

        self.market.match()
        for enterprise in self.enterprises.values():
            if enterprise.active:
                out = SECTOR_PARAMS[enterprise.industry].output
                sold = enterprise.last_sales.get(out, 0.0)
                enterprise.smoothed_sales = 0.7 * enterprise.smoothed_sales + 0.3 * sold

        self._progress_projects()
        self._finance()
        self._consume_and_demographics()
        stat = self._record_stats()
        self.market.consumption_spending = 0.0
        self.market.investment_spending = 0.0
        return stat

    # ------------------------------------------------------------------
    # 劳动市场
    # ------------------------------------------------------------------
    def _update_skills(self) -> None:
        for worker in self.workers.values():
            if not worker.alive or not worker.employed:
                continue
            worker.skill = min(SKILL_MAX, worker.skill + SKILL_GROWTH_PER_MONTH)

    def _labor_market(self) -> None:
        prices = self.market.reference_prices
        floor = wage_floor(prices)
        vacancies: Dict[str, int] = {}
        offers: Dict[str, float] = {}

        for enterprise in self.active_enterprises():
            workers = self.enterprise_workers(enterprise)
            required = desired_workers(enterprise)
            effective = sum(w.effective_labor for w in workers)
            if required <= 0:
                target = 0
            elif effective + 1e-9 < required:
                target = len(workers) + math.ceil((required - effective) / 0.75)
            elif effective > required * 1.5:
                target = max(required, math.ceil(required / 0.75))
            else:
                target = len(workers)
            if enterprise.industry == Industry.AGRICULTURE and enterprise.is_household:
                target = max(1, target)

            if len(workers) > target:
                # 保留自耕农所有者和熟练度最高的工人。
                removable = [
                    w
                    for w in sorted(workers, key=lambda w: (w.is_owner_operator, w.skill))
                    if not w.is_owner_operator
                ]
                excess = len(workers) - target
                for worker in removable[:excess]:
                    worker.employer_id = None
                    worker.wage = 0.0
                    enterprise.workers.remove(worker.id)
                workers = self.enterprise_workers(enterprise)

            offer = enterprise_wage_offer(self, enterprise)
            offers[enterprise.id] = offer
            # 现有员工按企业当前工资报价支付。
            for worker in workers:
                worker.wage = offer
                worker.hours = worker.choose_hours(prices)
                worker.industry = enterprise.industry
            vacancies[enterprise.id] = max(0, target - len(workers))

        # 先雇佣失业者，再允许有限度的跳槽。
        unemployed = [
            w
            for w in self.workers.values()
            if w.alive and not w.employed and not w.is_owner_operator
        ]
        unemployed.sort(key=lambda w: (w.cash, w.id))
        hiring = sorted(
            [e for e in vacancies if vacancies[e] > 0],
            key=lambda eid: offers[eid],
            reverse=True,
        )
        for enterprise_id in hiring:
            enterprise = self.enterprises[enterprise_id]
            remaining = vacancies[enterprise_id]
            for worker in list(unemployed):
                if remaining <= 0:
                    break
                reservation = floor * (0.70 if worker.cash < 5.0 else 1.0)
                if offers[enterprise_id] + 1e-9 < reservation:
                    continue
                self._hire(enterprise, worker, offers[enterprise_id], prices)
                unemployed.remove(worker)
                remaining -= 1
            vacancies[enterprise_id] = remaining

        # 有限跳槽：工人把自己的工资与最好的空缺报价比较。
        hiring = sorted(
            [e for e in vacancies if vacancies[e] > 0],
            key=lambda eid: offers[eid],
            reverse=True,
        )
        switches = 0
        if hiring:
            for worker in self.workers.values():
                if switches >= 20 or not hiring:
                    break
                if not worker.alive or not worker.employed or worker.is_owner_operator:
                    continue
                best_id = hiring[0]
                best_offer = offers[best_id]
                if worker.wage + 1e-9 >= best_offer * (1.0 + 0.06):
                    continue
                old_enterprise = self.enterprises.get(worker.employer_id or "")
                if old_enterprise is None:
                    continue
                if old_enterprise.id == best_id:
                    continue
                if worker.id in old_enterprise.workers:
                    old_enterprise.workers.remove(worker.id)
                self._hire(self.enterprises[best_id], worker, best_offer, prices)
                vacancies[best_id] -= 1
                switches += 1
                if vacancies[best_id] <= 0:
                    hiring.pop(0)
                    if not hiring:
                        break

    def _hire(
        self,
        enterprise: Enterprise,
        worker: Worker,
        offer: float,
        prices: Dict[Good, float],
    ) -> None:
        if worker.industry != enterprise.industry:
            worker.skill = max(1.0, worker.skill * 0.75)
        worker.industry = enterprise.industry
        worker.employer_id = enterprise.id
        worker.wage = offer
        worker.hours = worker.choose_hours(prices)
        if worker.id not in enterprise.workers:
            enterprise.workers.append(worker.id)

    # ------------------------------------------------------------------
    # 工资 / 生产
    # ------------------------------------------------------------------
    def _update_price_bands(self) -> None:
        """把薄市场的价格限制在重置成本带内。"""
        prices = self.market.reference_prices
        by_good: Dict[Good, List[float]] = {g: [] for g in Good}
        for enterprise in self.active_enterprises():
            good = SECTOR_PARAMS[enterprise.industry].output
            workers = self.enterprise_workers(enterprise)
            cost = unit_cost(enterprise, prices, workers, self.land.price)
            if cost > 1e-6:
                by_good[good].append(cost)
        for good, costs in by_good.items():
            if not costs:
                continue
            costs.sort()
            median = costs[len(costs) // 2]
            initial = INITIAL_PRICES[good]
            self.market.ceilings[good] = max(median * 2.5, initial * 1.5)
            # 不要让过剩把价格压到重置成本以下；那会形成
            # 通货紧缩陷阱：农场买不起化肥，农机投资也会停止。

            self.market.floors[good] = max(median * 0.90, initial * 0.60)

    def _pay_wages(self) -> None:
        for enterprise in self.active_enterprises():
            workers = self.enterprise_workers(enterprise)
            bill = sum(w.wage * w.effective_labor for w in workers)
            if bill <= 1e-9:
                continue
            # 所有者先于银行垫付工资。否则企业层面的流动性
            # 紧缩会表现为工资拖欠和饥荒，尽管所有者账上
            # 其实有现金。
            if enterprise.cash < bill:
                owner = self.capitalists.get(enterprise.owner_id)
                if owner is None:
                    owner = self.workers.get(enterprise.owner_id)
                if owner is not None and owner.cash > 0:
                    injection = min(bill - enterprise.cash, owner.cash)
                    owner.cash -= injection
                    enterprise.cash += injection
            if enterprise.cash < bill:
                self.bank.lend(enterprise, bill - enterprise.cash)
            factor = 1.0
            if enterprise.cash < bill:
                factor = max(0.0, enterprise.cash / bill)
            for worker in workers:
                paid = worker.wage * worker.effective_labor * factor
                enterprise.cash -= paid
                worker.cash += paid
                enterprise.month_wages += paid

    def _produce_all(self) -> None:
        for enterprise in self.active_enterprises():
            if enterprise.industry == Industry.AGRICULTURE:
                enterprise.use_fertilizer = wants_fertilizer(self, enterprise)
            output = produce(self, enterprise)
            out_good = SECTOR_PARAMS[enterprise.industry].output
            self.production_month[out_good] += output

    # ------------------------------------------------------------------
    # 投资 / 进入
    # ------------------------------------------------------------------
    def _investment_decisions(self) -> None:
        started = 0

        # 1）现有资本主义农场。预留两个名额，避免农业转型
        # 被煤/铁项目挤掉。
        farms = [
            e
            for e in self.active_enterprises(Industry.AGRICULTURE)
            if not e.is_household
        ]
        farms.sort(key=lambda e: e.id)
        farms_started = 0
        for enterprise in farms:
            if started >= MAX_PROJECTS_PER_TICK or farms_started >= 2:
                break
            choice = should_invest(self, enterprise)
            if choice is None:
                continue
            key, _ = choice
            if self._start_project(enterprise, key, priority=True):
                started += 1
                farms_started += 1

        # 2）一个新进入者。化肥行业为空时优先进入化肥：
        # 没有化肥厂，农场就无法采用这种让农业
        # 劳动生产率跃升的投入品。
        entry_candidates = []
        for industry in Industry:
            if industry == Industry.AGRICULTURE:
                continue
            params = SECTOR_PARAMS[industry]
            if len(self.active_enterprises(industry)) >= params.max_firms:
                continue
            choice = best_equipment_choice(self, industry, budget=100_000.0)
            if choice is None:
                continue
            key, roi = choice
            if roi >= INVESTMENT_HURDLE:
                entry_candidates.append((roi, industry, key))
        entry_candidates.sort(reverse=True)

        if entry_candidates and started < MAX_PROJECTS_PER_TICK:
            no_fertilizer = not self.active_enterprises(Industry.FERTILIZER_FACTORY)
            preferred = None
            if no_fertilizer:
                preferred = next(
                    (c for c in entry_candidates if c[1] == Industry.FERTILIZER_FACTORY),
                    None,
                )
            roi, industry, key = preferred or entry_candidates[0]
            cost = equipment_cost(key, self.market.reference_prices)
            candidates = [
                c for c in self.capitalists.values() if c.cash >= cost + 2000.0
            ]
            candidates.sort(key=lambda c: (c.owned_count(self.enterprises), -c.cash, c.id))
            if candidates:
                owner = candidates[0]
                budget = min(owner.cash * 0.5, cost * 2.0 + 3000.0)
                if budget >= cost + 1000.0:
                    owner.cash -= budget
                    enterprise = self.create_enterprise(
                        industry,
                        owner_id=owner.id,
                        cash=budget,
                        modernization_capable=True,
                    )
                    if self._start_project(enterprise, key, is_new=True):
                        started += 1
                    else:
                        enterprise.active = False
                        owner.cash += enterprise.cash
                        enterprise.cash = 0.0

        # 3）现有非农企业，优先处理瓶颈行业。
        priority = {
            Industry.MACHINERY_FACTORY: 0,
            Industry.STEEL_MILL: 1,
            Industry.BRICK_FACTORY: 2,
            Industry.CONSTRUCTION: 3,
            Industry.FERTILIZER_FACTORY: 4,
            Industry.TEXTILE_MILL: 5,
            Industry.COAL_MINE: 6,
            Industry.IRON_MINE: 7,
        }
        existing = sorted(
            self.active_enterprises(),
            key=lambda e: (priority.get(e.industry, 99), e.id),
        )
        for enterprise in existing:
            if started >= MAX_PROJECTS_PER_TICK:
                break
            if enterprise.industry == Industry.AGRICULTURE:
                continue
            choice = should_invest(self, enterprise)
            if choice is None:
                continue
            key, _ = choice
            if self._start_project(enterprise, key):
                started += 1

    # ------------------------------------------------------------------
    # 挂单
    # ------------------------------------------------------------------
    def _submit_sell_orders(self) -> None:
        for enterprise in self.active_enterprises():
            params = SECTOR_PARAMS[enterprise.industry]
            quantity = enterprise.inv(params.output)
            if quantity <= 1e-9:
                continue
            ask = enterprise_ask_price(self, enterprise)
            enterprise.ask_prices[params.output] = ask
            self.market.submit_sell(enterprise, params.output, quantity, ask)

    def _submit_household_orders(self) -> None:
        prices = self.market.reference_prices
        for worker in self.workers.values():
            if not worker.alive:
                continue
            comfort = worker.living_standard in ("comfort", "leisure")
            mult = COMFORT_MULTIPLIER if comfort else 1.0
            cash_left = max(0.0, worker.cash)

            food_gap = max(0.0, FOOD_PER_WORKER * mult - worker.food)
            if food_gap > 1e-9 and cash_left > 0:
                if worker.food < 0.05:
                    food_mult = 1.08
                elif comfort:
                    food_mult = 1.02
                else:
                    food_mult = 1.05
                bid = prices[Good.FOOD] * food_mult
                qty = min(food_gap, cash_left / max(bid, 1e-9))
                if qty > 1e-9:
                    self.market.submit_buy(worker, Good.FOOD, qty, bid)
                    cash_left -= qty * bid

            cloth_gap = max(0.0, CLOTH_PER_WORKER * mult - worker.cloth)
            if cloth_gap > 1e-9 and cash_left > 0:
                bid = prices[Good.CLOTH] * 1.04
                budget = cash_left * 0.60
                qty = min(cloth_gap, budget / max(bid, 1e-9))
                if qty > 1e-9:
                    self.market.submit_buy(worker, Good.CLOTH, qty, bid)
                    cash_left -= qty * bid

            housing_gap = max(0.0, HOUSING_PER_WORKER * mult - worker.housing)
            if housing_gap > 1e-9 and cash_left > 0:
                bid = prices[Good.BUILDING] * 1.04
                qty = min(housing_gap, cash_left * 0.50 / max(bid, 1e-9))
                if qty > 1e-9:
                    self.market.submit_buy(worker, Good.BUILDING, qty, bid)

        for capitalist in self.capitalists.values():
            budget = max(
                CAPITALIST_MIN_CONSUMPTION,
                capitalist.cash * CAPITALIST_CONSUMPTION_RATE,
            )
            budget = min(budget, max(0.0, capitalist.cash))
            cash_left = budget

            food_gap = max(0.0, CAPITALIST_FOOD - capitalist.food)
            if food_gap > 1e-9 and cash_left > 0:
                bid = prices[Good.FOOD] * 1.04
                qty = min(food_gap, cash_left / max(bid, 1e-9))
                if qty > 1e-9:
                    self.market.submit_buy(capitalist, Good.FOOD, qty, bid)
                    cash_left -= qty * bid

            cloth_gap = max(0.0, CAPITALIST_CLOTH - capitalist.cloth)
            if cloth_gap > 1e-9 and cash_left > 0:
                bid = prices[Good.CLOTH] * 1.04
                qty = min(cloth_gap, cash_left * 0.6 / max(bid, 1e-9))
                if qty > 1e-9:
                    self.market.submit_buy(capitalist, Good.CLOTH, qty, bid)
                    cash_left -= qty * bid

            housing_gap = max(0.0, CAPITALIST_HOUSING - capitalist.housing)
            if housing_gap > 1e-9 and cash_left > 0:
                bid = prices[Good.BUILDING] * 1.04
                qty = min(housing_gap, cash_left * 0.6 / max(bid, 1e-9))
                if qty > 1e-9:
                    self.market.submit_buy(capitalist, Good.BUILDING, qty, bid)

    def _submit_input_orders(self) -> None:
        prices = self.market.reference_prices
        for enterprise in self.active_enterprises():
            needs = input_needs(self, enterprise)
            if not needs:
                continue
            workers = self.enterprise_workers(enterprise)
            wage_bill = sum(w.wage * w.effective_labor for w in workers)
            available = max(0.0, enterprise.cash - wage_bill * 2.0)
            if available <= 1e-9:
                continue
            orders = []
            total = 0.0
            for good, qty in needs.items():
                bid = prices[good] * 1.06
                orders.append([good, qty, bid])
                total += qty * bid
            scale = min(1.0, available / total) if total > 0 else 0.0
            for good, qty, bid in orders:
                q = qty * scale
                if q > 1e-9:
                    self.market.submit_buy(enterprise, good, q, bid)

    def _submit_project_orders(self) -> None:
        prices = self.market.reference_prices
        for project in self.projects.values():
            if not project.active:
                continue
            # 给接近完成但现金耗尽的项目的追加资金：
            # 资本品涨价会让项目停在 9.9/10 台设备，
            # 永远占住一个投资名额。
            enterprise = self.enterprises.get(project.enterprise_id)
            if enterprise and enterprise.active:
                workers = self.enterprise_workers(enterprise)
                wage_bill = sum(w.wage * w.effective_labor for w in workers)
                reserve = max(wage_bill * 3.0, 100.0)
                remaining_value = sum(
                    project.remaining(good) * prices.get(good, 0.0)
                    for good in project.needed
                )
                if project.cash + 1e-9 < remaining_value * 1.05:
                    need = remaining_value * 1.15 - project.cash
                    transfer = min(need, max(0.0, enterprise.cash - reserve))
                    if transfer > 0:
                        enterprise.cash -= transfer
                        project.cash += transfer
            if project.cash <= 1e-9:
                continue
            for good, needed in project.needed.items():
                remaining = project.remaining(good)
                if remaining <= 1e-9:
                    continue
                if project.industry == Industry.AGRICULTURE:
                    bid = prices[good] * 1.10
                else:
                    bid = prices[good] * 1.08
                qty = min(remaining, project.cash / max(bid, 1e-9))
                if qty > 1e-9:
                    self.market.submit_buy(project, good, qty, bid)

    # ------------------------------------------------------------------
    # 项目完成
    # ------------------------------------------------------------------
    def _progress_projects(self) -> None:
        for project in list(self.projects.values()):
            if not project.active:
                continue
            project.age += 1
            if not project.started:
                if project.fully_paid():
                    project.started = True
                    project.months_left = project.build_months
                    if project.months_left <= 0:
                        self._complete_project(project)
                elif project.age > PROJECT_TIMEOUT_MONTHS:
                    self._cancel_project(project)
                continue

            project.months_left -= 1
            if project.months_left <= 0:
                self._complete_project(project)

    def _complete_project(self, project: InvestmentProject) -> None:
        enterprise = self.enterprises.get(project.enterprise_id)
        if enterprise and enterprise.active:
            enterprise.add_equipment(project.equipment_key, project.quantity)
            enterprise.active = True
            enterprise.cash += project.cash
            project.cash = 0.0
        else:
            # 孤儿项目：退款给银行，避免货币被销毁。
            self.bank.cash += project.cash
            project.cash = 0.0
        project.active = False

    def _cancel_project(self, project: InvestmentProject) -> None:
        enterprise = self.enterprises.get(project.enterprise_id)
        if enterprise and enterprise.active:
            enterprise.cash += project.cash
            for good, qty in project.inventory.items():
                enterprise.inventory[good] = enterprise.inv(good) + qty
        else:
            self.bank.cash += project.cash
        project.cash = 0.0
        project.active = False

    # ------------------------------------------------------------------
    # 金融 / 分红 / 破产
    # ------------------------------------------------------------------
    def _finance(self) -> None:
        prices = self.market.reference_prices
        for enterprise in list(self.active_enterprises()):
            self.bank.charge_interest(enterprise)
            workers = self.enterprise_workers(enterprise)
            wage_bill = sum(w.wage * w.effective_labor for w in workers)
            if enterprise.cash > wage_bill * 6.0 + 100.0:
                self.bank.repay(enterprise, (enterprise.cash - wage_bill * 3.0) * 0.30)

            enterprise.last_revenue = enterprise.month_revenue
            enterprise.last_costs = enterprise.month_input_cost
            enterprise.last_wages = enterprise.month_wages
            enterprise.last_interest = enterprise.month_interest
            depreciation = (
                capital_value(enterprise, prices, self.land.price) / DEPRECIATION_MONTHS
            )
            enterprise.last_profit = (
                enterprise.last_revenue
                - enterprise.last_costs
                - enterprise.last_wages
                - enterprise.last_interest
                - depreciation
            )

            if (
                enterprise.last_profit > 0
                and enterprise.cash > wage_bill * 3.0 + 100.0
            ):
                dividend = min(
                    enterprise.last_profit * DIVIDEND_PAYOUT,
                    enterprise.cash - wage_bill * 3.0,
                )
                if dividend > 0:
                    enterprise.cash -= dividend
                    owner = self.capitalists.get(enterprise.owner_id)
                    if owner is None:
                        owner_worker = self.workers.get(enterprise.owner_id)
                        if owner_worker and owner_worker.alive:
                            owner_worker.cash += dividend
                        else:
                            # 已死亡的所有者不能收分红；把现金
                            # 放进银行，保证货币审计精确。
                            self.bank.cash += dividend
                    else:
                        owner.cash += dividend

            worth = net_worth(enterprise, prices, self.land.price)
            if enterprise.cash <= 1e-9 and enterprise.last_profit < 0 and worth < 0:
                enterprise.bankruptcy_months += 1
            else:
                enterprise.bankruptcy_months = 0
            if enterprise.bankruptcy_months >= 12:
                self._liquidate(enterprise)

    def _liquidate(self, enterprise: Enterprise) -> None:
        enterprise.active = False
        for worker_id in list(enterprise.workers):
            worker = self.workers.get(worker_id)
            if worker:
                worker.employer_id = None
                worker.wage = 0.0
        enterprise.workers.clear()
        if enterprise.cash > 0:
            self.bank.cash += enterprise.cash
            enterprise.cash = 0.0

    # ------------------------------------------------------------------
    # 消费 / 人口
    # ------------------------------------------------------------------
    def _consume_and_demographics(self) -> None:
        for worker in self.workers.values():
            if not worker.alive:
                continue
            comfort = worker.living_standard in ("comfort", "leisure")
            mult = COMFORT_MULTIPLIER if comfort else 1.0
            food_target = FOOD_PER_WORKER * mult
            cloth_target = CLOTH_PER_WORKER * mult
            housing_target = HOUSING_PER_WORKER * mult

            worker.consumed_food = min(worker.food, food_target)
            worker.food -= worker.consumed_food
            worker.consumed_cloth = min(worker.cloth, cloth_target)
            worker.cloth -= worker.consumed_cloth
            worker.consumed_housing = min(worker.housing, housing_target)
            worker.housing -= worker.consumed_housing

            if worker.consumed_food + 1e-9 < FOOD_PER_WORKER:
                worker.hunger_months += 1
            else:
                worker.hunger_months = 0

            if worker.hunger_months >= 3:
                chance = min(
                    0.50,
                    0.08 + 0.08 * (worker.hunger_months - 3),
                )
                if self.rng.random() < chance:
                    worker.alive = False
                    self.dead_this_month += 1
                    self.bank.cash += max(0.0, worker.cash)
                    worker.cash = 0.0
                    employer = self.enterprises.get(worker.employer_id or "")
                    if employer and worker.id in employer.workers:
                        employer.workers.remove(worker.id)
                    worker.employer_id = None
                    continue

            if worker.consumed_food + 1e-9 < FOOD_PER_WORKER:
                worker.living_standard = "survival"
            elif (
                worker.consumed_cloth + 1e-9 < CLOTH_PER_WORKER
                or worker.consumed_housing + 1e-9 < HOUSING_PER_WORKER
            ):
                worker.living_standard = "subsistence"
            elif worker.hours <= 8 and worker.cash >= 120.0:
                worker.living_standard = "leisure"
            else:
                worker.living_standard = "comfort"

        for capitalist in self.capitalists.values():
            capitalist.consumed_food = min(capitalist.food, CAPITALIST_FOOD)
            capitalist.food -= capitalist.consumed_food
            capitalist.consumed_cloth = min(capitalist.cloth, CAPITALIST_CLOTH)
            capitalist.cloth -= capitalist.consumed_cloth
            capitalist.consumed_housing = min(capitalist.housing, CAPITALIST_HOUSING)
            capitalist.housing -= capitalist.consumed_housing

    # ------------------------------------------------------------------
    # 统计指标
    # ------------------------------------------------------------------
    def _record_stats(self) -> dict:
        prices = self.market.reference_prices
        alive_workers = [w for w in self.workers.values() if w.alive]
        employed = [w for w in alive_workers if w.employed]
        unemployed = len(alive_workers) - len(employed)

        ag_workers = [
            w
            for w in employed
            if w.industry == Industry.AGRICULTURE
        ]
        food_output = self.production_month.get(Good.FOOD, 0.0)
        ag_productivity = food_output / max(len(ag_workers), 1)

        total_capital = 0.0
        total_profit = 0.0
        for enterprise in self.active_enterprises():
            total_capital += capital_value(enterprise, prices, self.land.price) + inventory_value(
                enterprise, prices
            )
            total_profit += enterprise.last_profit
        profit_rate = total_profit / total_capital if total_capital > 0 else 0.0

        firms_by_industry = {
            ind.value: len(self.active_enterprises(ind)) for ind in Industry
        }
        workers_by_industry = {ind.value: 0 for ind in Industry}
        for worker in alive_workers:
            if worker.industry in workers_by_industry:
                workers_by_industry[worker.industry.value] += 1

        living = {"survival": 0, "subsistence": 0, "comfort": 0, "leisure": 0}
        for worker in alive_workers:
            living[worker.living_standard] = living.get(worker.living_standard, 0) + 1

        capitalist_farms = [
            e
            for e in self.active_enterprises(Industry.AGRICULTURE)
            if not e.is_household
        ]
        household_farms = [
            e
            for e in self.active_enterprises(Industry.AGRICULTURE)
            if e.is_household
        ]
        fertilizer_used = sum(
            e.last_input_used.get(Good.FERTILIZER, 0.0)
            for e in self.active_enterprises(Industry.AGRICULTURE)
        )
        farm_machinery = sum(
            sum(v for k, v in e.equipment.items() if k.startswith("farm_"))
            for e in self.active_enterprises(Industry.AGRICULTURE)
        )

        money_total = self.total_money()
        if self.money_initial > 0 and abs(money_total - self.money_initial) > 0.01:
            self._warnings.append(
                f"货币漂移：{money_total:.2f} != {self.money_initial:.2f}"
            )

        for good in Good:
            price = prices[good]
            initial = INITIAL_PRICES[good]
            if price > initial * 10:
                self._warnings.append(f"{GOOD_LABELS[good]} 价格高于初始价的 10 倍")
            if price < initial * 0.1:
                self._warnings.append(f"{GOOD_LABELS[good]} 价格低于初始价的 0.1 倍")
            output = self.production_month.get(good, 0.0)
            if output <= 1e-9:
                self._zero_output_streak[good.value] += 1
            else:
                self._zero_output_streak[good.value] = 0
            if self._zero_output_streak[good.value] == 3:
                self._warnings.append(f"{GOOD_LABELS[good]} 连续 3 个月产量为 0")

        gdp = self.market.consumption_spending + self.market.investment_spending
        stat = {
            "tick": self.tick,
            "alive": len(alive_workers),
            "dead_this_month": self.dead_this_month,
            "money_total": money_total,
            "bank_cash": self.bank.cash,
            "bank_loans": sum(self.bank.loans.values()),
            "gdp": gdp,
            "consumption": self.market.consumption_spending,
            "investment": self.market.investment_spending,
            "unemployment_rate": unemployed / max(len(alive_workers), 1),
            "profit_rate": profit_rate,
            "capital_stock": total_capital,
            "ag_productivity": ag_productivity,
            "food_output": food_output,
            "prices": {g.value: prices[g] for g in Good},
            "production": {g.value: self.production_month.get(g, 0.0) for g in Good},
            "volumes": {g.value: self.market.history[g]["volume"] for g in Good},
            "demand": {g.value: self.market.history[g]["demand"] for g in Good},
            "supply": {g.value: self.market.history[g]["supply"] for g in Good},
            "firms": firms_by_industry,
            "workers_by_industry": workers_by_industry,
            "living_standard": living,
            "capitalist_farms": len(capitalist_farms),
            "household_farms": len(household_farms),
            "fertilizer_used": fertilizer_used,
            "farm_machinery": farm_machinery,
            "smallholder_land": self.land.smallholder_land,
            "land_price": self.land.price,
            "warnings": list(self._warnings),
        }
        self.stats.append(stat)
        return stat
