from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Dict, List, Optional

from .config import (
    BANK_CASH,
    BANK_INTEREST_RATE,
    BANK_LOAN_MONTHS,
    BASE_GRAIN_YIELD,
    CAPITALIST_CONSUMPTION_RATE,
    CAPITALIST_FOOD,
    CAPITALIST_CLOTH,
    CAPITALIST_HOUSING,
    CAPITALIST_MIN_CONSUMPTION,
    CAPITALIST_SERVICE,
    CLOTH_PER_WORKER,
    COMFORT_MULTIPLIER,
    COMFORT_SAVINGS,
    DemographicsConfig,
    LEISURE_SAVINGS,
    DEPRECIATION_MONTHS,
    DIVIDEND_PAYOUT,
    EQUIPMENT,
    FERTILIZER_COAL_BUFFER_MONTHS,
    FERTILIZER_HIRING_PRIORITY,
    FERTILIZER_PER_MU,
    FOOD_PER_WORKER,
    FOOD_RELIEF_BUFFER_MONTHS,
    HOUSEHOLD_FARM_RESERVE,
    HOUSING_PER_WORKER,
    INITIAL_LAND_PRICE,
    INITIAL_PRICES,
    INVESTMENT_HURDLE,
    MANUAL_EQUIPMENT,
    MAX_ACTIVE_PROJECTS,
    MAX_NEW_FIRMS_PER_TICK,
    MAX_PROJECTS_PER_TICK,
    MAX_SERVICE_ENTRIES_PER_MONTH,
    PROJECT_TIMEOUT_MONTHS,
    SECTOR_PARAMS,
    SERVICE_ENTRY_MIN_REVENUE,
    SERVICE_FIRM_RESERVE,
    SERVICE_IDLE_EXIT_MONTHS,
    SERVICE_PER_HOUSEHOLD,
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
    should_switch,
    wants_fertilizer,
    wage_floor,
)
from .enums import GOOD_LABELS, Good, Industry
from .government import Government, MoneyRegime, PolicyRegime
from .land import run_land_market
from .market import Market
from .models import (
    AssetPool,
    Bank,
    Capitalist,
    Enterprise,
    FoodReserve,
    InvestmentProject,
    LandMarket,
    Worker,
)
from .production import (
    average_skill,
    capital_value,
    capacity_at_skill_one,
    desired_workers,
    equipment_cost,
    equipment_value,
    inventory_value,
    net_worth,
    produce,
    unit_cost,
)


class Engine:
    def __init__(self, seed: int = 1):
        self.seed = seed
        self.rng = random.Random(seed)
        # 独立人口随机流：生育/年龄死亡/性别不扰动既有经济 RNG；
        # 饥饿死亡仍使用 self.rng（保留既有死亡随机流语义）。
        # 同 seed 下两条流都完全可复现。
        self.demographic_rng = random.Random(seed + 1_000_003)
        self.tick = 0
        self.workers: Dict[str, Worker] = {}
        self.enterprises: Dict[str, Enterprise] = {}
        self.capitalists: Dict[str, Capitalist] = {}
        self.projects: Dict[str, InvestmentProject] = {}
        self.market = Market(INITIAL_PRICES)
        self.land = LandMarket(TOTAL_LAND_MU, INITIAL_LAND_PRICE)
        self.bank = Bank(BANK_CASH, BANK_INTEREST_RATE)
        self.asset_pool = AssetPool()
        self.food_reserve = FoodReserve()
        self.government: Optional[Government] = None
        # 古典剧本允许工资低于制度性生存线；Keynesian/MMT 保持最低工资。
        self.wage_floor_scale: float = 1.0
        # "band" = 参考价 + 成本价格带（默认）；
        # "markup" = 自由成本加成（实验，固定篮子下易崩溃）；
        # "markup_soft" = 成本加成目标价 + 参考价软走廊（0.85–1.15×ref）。
        self.price_regime: str = "band"
        # "fixed" = 固定温饱篮子；"les" = Stone-Geary 需求（价格弹性）。
        self.demand_regime: str = "fixed"
        # 是否启用银行存款中介（Keynesian/MMT 启用；古典默认关闭）。
        self.bank_intermediation: bool = False
        # --- 冲击测试钩子（默认全部中性，不改变基线行为）---------------
        # 行业产出乘数：{Industry: multiplier}；默认为空 = 1.0。
        self.productivity_multipliers: Dict[Industry, float] = {}
        # 家庭非食品（衣着/住房）消费乘数；食品是生存品，不在此列。
        self.worker_demand_scale: float = 1.0
        # 资本家消费乘数（按可支配消费预算缩放）。
        self.capitalist_demand_scale: float = 1.0
        # 银行对工资缺口放贷的比例；1.0 = 正常，0.0 = 完全信贷冻结。
        self.lending_scale: float = 1.0
        self.stats: List[dict] = []
        self.money_initial = 0.0
        self.dead_this_month = 0
        # V0.5 人口过程（默认参数等价于古典剧本；build_scenario_1 会覆盖）。
        self.demographics: DemographicsConfig = DemographicsConfig()
        self.births_this_month = 0
        self._orphaned_this_month = 0
        self._age_deaths_this_month = 0
        self._hunger_deaths_this_month = 0
        self._pension_shortfall = 0.0
        self._food_relief_this_month = 0.0
        self._food_relief_shortfall = 0.0
        self._food_levy_this_month = 0.0
        # 家庭农场破产清算计数（验证用）：月流量 + 累计。
        self._household_farm_liquidations_this_month = 0
        self.household_farm_liquidations_total = 0
        self.production_month: Dict[Good, float] = {g: 0.0 for g in Good}
        self._next_worker = 0
        self._next_enterprise = 0
        self._next_project = 0
        self._zero_output_streak: Dict[str, int] = defaultdict(int)
        self._last_manual_entry: Dict[Industry, int] = {}
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
            if worker_id in self.workers
            and self.workers[worker_id].alive
            and not self.workers[worker_id].is_child
            and not self.workers[worker_id].retired
        ]

    @staticmethod
    def _is_household_farm(enterprise: Enterprise) -> bool:
        return (
            enterprise.is_household
            and enterprise.industry == Industry.AGRICULTURE
        )

    @classmethod
    def _is_household_farm_owner(
        cls, enterprise: Enterprise, worker: Worker
    ) -> bool:
        """自耕农所有者是剩余索取者，不是雇员。"""
        return cls._is_household_farm(enterprise) and (
            worker.is_owner_operator or worker.id == enterprise.owner_id
        )

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
            if w.alive
            and w.employed
            and not w.is_child
            and not w.retired
            and w.wage > 0
        ]
        return sum(wages) / len(wages) if wages else WAGE_BASE

    def feeding_units(self) -> float:
        """食品需求当量：儿童按 0.5 个成人计算。"""
        units = 0.0
        for worker in self.workers.values():
            if worker.alive:
                units += 0.5 if worker.is_child else 1.0
        return max(1.0, units)

    def labor_force_workers(self) -> List[Worker]:
        """劳动年龄、非退休、非儿童的在劳动市场人口。"""
        return [
            worker
            for worker in self.workers.values()
            if worker.alive and worker.is_working_age
        ]

    def total_money(self) -> float:
        return (
            sum(w.cash for w in self.workers.values() if w.alive)
            + sum(c.cash for c in self.capitalists.values())
            + sum(e.cash for e in self.enterprises.values() if e.active)
            + sum(p.cash for p in self.projects.values() if p.active)
            + self.bank.cash
            + self.bank.frozen_cash
            + self.food_reserve.cash
            + (self.government.cash if self.government is not None else 0.0)
        )

    # ------------------------------------------------------------------
    # 化肥供应 / 周转资金
    # ------------------------------------------------------------------
    def fertilizer_supply_short(self) -> bool:
        """化肥是否处于短缺状态。

        用“上月行业零产出”或“库存低于可机械化农场的月需求”判断。
        短缺时化肥厂在招聘队列中优先补位；供应恢复后自动退出优先。
        """
        if self._zero_output_streak.get(Good.FERTILIZER.value, 0) > 0:
            return True
        stock = sum(
            enterprise.inv(Good.FERTILIZER)
            for enterprise in self.active_enterprises(Industry.FERTILIZER_FACTORY)
        )
        potential = sum(
            farm.land * FERTILIZER_PER_MU
            for farm in self.active_enterprises(Industry.AGRICULTURE)
            if farm.modernization_capable
        )
        return potential > 1e-9 and stock < potential

    def fertilizer_coal_reserve(
        self, enterprise: Enterprise, capacity: Optional[float] = None
    ) -> float:
        """化肥厂为购买煤而保留的周转资金（元）。

        只对化肥厂生效：煤是唯一投入且必须现金采购。投资决策和
        采购下单都从这里取同一个下限，避免现金被设备锁死。
        """
        if enterprise.industry != Industry.FERTILIZER_FACTORY:
            return 0.0
        params = SECTOR_PARAMS[Industry.FERTILIZER_FACTORY]
        coal_ratio = params.inputs.get(Good.COAL, 0.0)
        if coal_ratio <= 0:
            return 0.0
        if capacity is None:
            capacity = capacity_at_skill_one(enterprise)
        coal_price = self.market.reference_prices.get(Good.COAL, 0.0)
        return (
            capacity
            * coal_ratio
            * FERTILIZER_COAL_BUFFER_MONTHS
            * coal_price
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
        age_months: Optional[int] = None,
        sex: Optional[str] = None,
        is_child: Optional[bool] = None,
        parent_id: Optional[str] = None,
        birth_tick: Optional[int] = None,
        retired: bool = False,
    ) -> Worker:
        if age_months is None:
            # 直接创建（测试/新增工人）默认是成年人；初始剧本显式传入年龄。
            age_months = self.demographics.working_age_months + 10 * 12
        if sex is None:
            sex = "F"
        if is_child is None:
            is_child = age_months < self.demographics.working_age_months
        if birth_tick is None:
            birth_tick = self.tick - age_months
        worker = Worker(
            id=self.new_worker_id(),
            industry=industry,
            skill=skill,
            cash=cash,
            food=food,
            age_months=age_months,
            sex=sex,
            is_child=is_child,
            retired=retired,
            parent_id=parent_id,
            birth_tick=birth_tick,
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
        enterprise.demand_forecast = land_mu * BASE_GRAIN_YIELD * 2.0
        enterprise.target_inventory_months = 6.0
        return enterprise

    def _bootstrap_manual_entry(self, industry: Industry, key: str) -> bool:
        """行业死掉后，用无资本品的手工设备重启一次。

        只允许在没有活跃企业的行业使用，且每 12 个月最多一次；
        正常扩张仍必须使用 2^N 设备，避免免费 t0 削弱资本品需求。
        """
        if self.tick - self._last_manual_entry.get(industry, -999) < 12:
            return False
        candidates = [
            capitalist
            for capitalist in self.capitalists.values()
            if capitalist.cash >= 500.0
        ]
        if not candidates:
            return False
        candidates.sort(
            key=lambda c: (c.owned_count(self.enterprises), -c.cash, c.id)
        )
        owner = candidates[0]
        setup_cost = 300.0
        owner.cash -= setup_cost
        enterprise = self.create_enterprise(
            industry,
            owner_id=owner.id,
            cash=setup_cost,
            modernization_capable=True,
        )
        enterprise.add_equipment(key, 1)
        enterprise.demand_forecast = 1.0
        enterprise.target_inventory_months = 1.0
        self._last_manual_entry[industry] = self.tick
        return True

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
        # 化肥厂 2 台反应炉的硬上限必须包含在建项目。替换投资走的是
        # 这条路径，如果这里不拦，企业会每 12 个月把一台机械品和
        # 项目现金锁进注定只能进资产池的第三台反应炉。
        if et.industry == Industry.FERTILIZER_FACTORY:
            pending = sum(
                project.quantity
                for project in self.projects.values()
                if project.active
                and project.enterprise_id == enterprise.id
                and project.industry == Industry.FERTILIZER_FACTORY
            )
            if enterprise.total_equipment() + pending >= 2:
                return False
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
        if et.industry == Industry.FERTILIZER_FACTORY:
            # 新反应炉投产后还要买煤；把这笔周转资金一起留出来。
            reserve += self.fertilizer_coal_reserve(
                enterprise,
                capacity_at_skill_one(enterprise) + et.capacity,
            )
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
        self.births_this_month = 0
        self._orphaned_this_month = 0
        self._age_deaths_this_month = 0
        self._hunger_deaths_this_month = 0
        self._pension_shortfall = 0.0
        self._food_relief_this_month = 0.0
        self._food_relief_shortfall = 0.0
        self._food_levy_this_month = 0.0
        self._household_farm_liquidations_this_month = 0
        self._warnings = []
        self.production_month = {g: 0.0 for g in Good}
        for enterprise in self.enterprises.values():
            enterprise.reset_month_flows()

        if self.government is not None:
            self.government.reset_month()
        self._update_skills()
        # 先 aging/退休/死亡，再出生/劳动市场，最后消费（设计文档 §3）。
        self._demography_pre()
        self._update_expectations_and_plans()
        if self.bank_intermediation:
            self._bank_intermediation()
        self._labor_market()
        self._pay_wages()
        self._pay_government_wages()
        self._produce_all()
        self._produce_government()
        self._collect_food_relief_levy()
        self._update_price_bands()
        run_land_market(self)
        self._investment_decisions()

        self._submit_sell_orders()
        self._submit_household_orders()
        self._submit_food_reserve_orders()
        self._submit_government_orders()
        self._submit_input_orders()
        self._submit_project_orders()

        self.market.match()
        for enterprise in self.enterprises.values():
            if enterprise.active:
                out = SECTOR_PARAMS[enterprise.industry].output
                sold = enterprise.last_sales.get(out, 0.0)
                enterprise.smoothed_sales = 0.7 * enterprise.smoothed_sales + 0.3 * sold

        # 服务是流量而非库存：未售出的服务不能留到下月再卖。
        for enterprise in self.enterprises.values():
            if enterprise.active and enterprise.industry == Industry.SERVICE:
                enterprise.inventory[Good.SERVICE] = 0.0

        self._progress_projects()
        self._finance()
        self._government_settlement()
        self._cleanup_dormant()
        # 粮食平准库存的紧急救济：市场没成交但库存仍在时，避免纯现金
        # 约束造成的饥荒。只转移实物，不改变任何现金，因此不创造货币。
        self._distribute_food_relief()
        self._consume_and_demographics()
        stat = self._record_stats()
        self.market.consumption_spending = 0.0
        self.market.investment_spending = 0.0
        self.market.government_spending = 0.0
        return stat

    # ------------------------------------------------------------------
    # 劳动市场
    # ------------------------------------------------------------------
    def _update_skills(self) -> None:
        for worker in self.workers.values():
            if not worker.alive or not worker.employed:
                continue
            worker.skill = min(SKILL_MAX, worker.skill + SKILL_GROWTH_PER_MONTH)

    # ------------------------------------------------------------------
    # 人口过程：aging / 出生 / 退休 / 死亡
    # ------------------------------------------------------------------
    def _monthly_mortality(self, worker: Worker) -> float:
        """年龄别月度死亡概率（Gompertz + 婴幼儿/儿童分段）。"""
        demo = self.demographics
        age = max(0, worker.age_months)
        if age >= demo.max_age_months:
            return 1.0
        if age < 12:
            annual = demo.infant_mortality_annual
        elif age < 60:
            annual = demo.child_mortality_annual
        else:
            mu = demo.mortality_A + demo.mortality_B * math.exp(
                demo.mortality_C * age / 12.0
            )
            annual = 1.0 - math.exp(-max(0.0, mu))
        monthly = 1.0 - (1.0 - max(0.0, min(1.0, annual))) ** (1.0 / 12.0)
        return max(0.0, min(1.0, monthly))

    @staticmethod
    def _fertility_age_shape(age_months: int) -> float:
        """20–40 岁年龄别生育率形状（均值归一化为 1）。

        峰值在 25–29 岁；这样 ``fertility_monthly`` 仍可直接近似
        ``TFR / (12 * 育龄年数)``，便于按 TFR 目标校准。
        """
        years = age_months / 12.0
        if years < 20 or years > 40:
            return 0.0
        if years < 25:
            weight = 0.7
        elif years < 30:
            weight = 1.2
        elif years < 35:
            weight = 1.1
        elif years < 40:
            weight = 0.8
        else:
            weight = 0.2
        # 20..40 岁（含端点，241 个月）的离散平均权重为
        # (60*3.8 + 0.2) / 241 = 0.9469；按此归一化，避免有效生育率
        # 比名义 TFR 高约 3.6%（旧值 0.9143 假设了错误的年龄带宽）。
        return weight / 0.9469

    def _birth_probability(self, mother: Worker) -> float:
        """育龄女性月度生育概率。

        ``p = min(0.2, ASFR(a)/12 * m * parity)``；
        ``m = clip((y/y0)^0.1 * (food/food0)^0.3, 0.3, 1.5)``，
        食物短缺和极端贫困显著压低生育。
        """
        demo = self.demographics
        if mother.sex != "F" or mother.is_child or mother.retired:
            return 0.0
        if not (
            demo.fertility_age_min_months
            <= mother.age_months
            <= demo.fertility_age_max_months
        ):
            return 0.0
        shape = self._fertility_age_shape(mother.age_months)
        if shape <= 0:
            return 0.0
        score = {
            "survival": 0.0,
            "subsistence": 0.5,
            "comfort": 1.0,
            "leisure": 1.2,
            "child": 0.0,
        }.get(mother.living_standard, 0.5)
        # y/y0 的生活标准代理：0.5（生存）到 1.7（悠闲）。
        y_ratio = max(0.1, 0.5 + score)
        # 用上月实际消费而不是当前库存：月内食品库存通常会被吃空，
        # 用库存会把所有家庭都误判为饥荒。
        if mother.hunger_months > 0:
            food_ratio = 0.3
        else:
            food_ratio = max(
                0.05,
                min(
                    1.5,
                    mother.consumed_food / max(FOOD_PER_WORKER, 1e-9),
                ),
            )
        multiplier = (
            (y_ratio ** 0.1) * (food_ratio ** 0.3)
        )
        multiplier = max(0.3, min(1.5, multiplier))
        living_children = sum(
            1
            for child_id in mother.children_ids
            if child_id in self.workers
            and self.workers[child_id].alive
            and self.workers[child_id].is_child
        )
        parity_factor = 1.0 / (1.0 + 0.10 * living_children)
        probability = (
            demo.fertility_monthly
            * demo.fertility_multiplier
            * shape
            * multiplier
            * parity_factor
        )
        return max(0.0, min(0.2, probability))

    def _give_birth(self, mother: Worker) -> Worker:
        sex = "F" if self.demographic_rng.random() < 0.5 else "M"
        child = self.create_worker(
            industry=mother.industry,
            skill=0.0,
            cash=0.0,
            food=0.0,
            age_months=0,
            sex=sex,
            is_child=True,
            parent_id=mother.id,
            birth_tick=self.tick,
        )
        child.cloth = 0.0
        child.housing = 0.0
        child.service = 0.0
        child.hours = 0
        child.living_standard = "child"
        mother.children_ids.append(child.id)
        self.births_this_month += 1
        return child

    def _retire_worker(self, worker: Worker) -> None:
        """到龄退休：退出企业/就业保障与劳动市场。"""
        employer = self.enterprises.get(worker.employer_id or "")
        if employer is not None and worker.id in employer.workers:
            employer.workers.remove(worker.id)
        if self.government is not None and worker.id in self.government.jg_workers:
            self.government.jg_workers.remove(worker.id)
        worker.employer_id = None
        worker.wage = 0.0
        worker.hours = 0
        worker.ui_months = 0
        worker.retired = True

    def _demography_pre(self) -> None:
        demo = self.demographics
        # 1) 年龄 +1 月；儿童成年；雇员/劳动年龄人口退休。
        for worker in list(self.workers.values()):
            if not worker.alive:
                continue
            worker.age_months += 1
            if worker.is_child and worker.age_months >= demo.working_age_months:
                worker.is_child = False
                worker.skill = max(1.0, worker.skill)
                parent = self.workers.get(worker.parent_id or "")
                worker.industry = (
                    parent.industry
                    if parent is not None and parent.alive
                    else Industry.SERVICE
                )
                worker.hours = 16
            if (
                not worker.is_child
                and not worker.retired
                and demo.retirement_age_months > 0
                and worker.age_months >= demo.retirement_age_months
                # 自耕农/自雇摊主不强制退休：V0.5 还没有土地/经营权的
                # 代际继承机制，强制退休会让家庭农场直接消失。
                and not worker.is_owner_operator
            ):
                self._retire_worker(worker)

        # 2) 年龄别死亡（在出生/劳动市场之前；死亡者当月不参与）。
        for worker in list(self.workers.values()):
            if not worker.alive:
                continue
            if self.demographic_rng.random() < self._monthly_mortality(worker):
                self._kill_worker(worker, cause="age")

        # 3) 育龄女性生育；新生儿当月加入人口并领取 allowance。
        for mother in list(self.workers.values()):
            if not mother.alive:
                continue
            probability = self._birth_probability(mother)
            if (
                probability > 0
                and self.demographic_rng.random() < probability
            ):
                self._give_birth(mother)

    def _kill_worker(self, worker: Worker, cause: str = "age") -> None:
        """死亡清算：现金入银行、清雇主/就业保障/家庭关系。"""
        if not worker.alive:
            return
        worker.alive = False
        self.dead_this_month += 1
        if cause == "hunger":
            self._hunger_deaths_this_month += 1
        else:
            self._age_deaths_this_month += 1

        self.bank.cash += max(0.0, worker.cash)
        worker.cash = 0.0
        self.bank.deposits.pop(worker.id, 0.0)

        employer = self.enterprises.get(worker.employer_id or "")
        if employer is not None and worker.id in employer.workers:
            employer.workers.remove(worker.id)
        worker.employer_id = None
        worker.wage = 0.0
        worker.hours = 0
        if self.government is not None and worker.id in self.government.jg_workers:
            self.government.jg_workers.remove(worker.id)

        # 从父母/监护人的子女列表中移除。
        parent = self.workers.get(worker.parent_id or "")
        if parent is not None and worker.id in parent.children_ids:
            parent.children_ids.remove(worker.id)
        # 死亡者若有未成年子女，孩子仍存活但 allowance 归零；
        # 不凭空创造政府/慈善资金，只记录 warning。
        # 在清空 children_ids 之前选出家庭农场继承人（成年、未退休、
        # 尚未拥有农场），让土地留在农业生产中而不是沉入 estate_land。
        heir = self._choose_heir(worker)
        if worker.children_ids:
            for child_id in list(worker.children_ids):
                child = self.workers.get(child_id)
                if child is not None and child.alive:
                    child.parent_id = None
                    # 只统计未成年孤儿；成年子女失去家长不构成孤儿。
                    if child.is_child:
                        self._orphaned_this_month += 1
            worker.children_ids.clear()
        worker.parent_id = None

        self._settle_estate(worker, heir=heir)

    def _pay_child_allowances(self, prices: Dict[Good, float]) -> None:
        """家长向儿童转移现金（allowance），儿童自己挂买单。

        先给家长保留半个成人温饱篮子；不足时按儿童人数等比缩减。
        这是纯现金转移，货币守恒。
        """
        demo = self.demographics
        child_basket = (
            demo.child_food * prices.get(Good.FOOD, 0.0)
            + demo.child_cloth * prices.get(Good.CLOTH, 0.0)
            + demo.child_housing * prices.get(Good.BUILDING, 0.0)
        )
        if child_basket <= 0:
            return
        # 家长先保留自己的全额口粮现金，再转移剩余部分；否则多子女家庭
        # 会把家长的食品预算挤掉，造成“父母饿死、儿童成孤儿”的连锁死亡。
        adult_reserve = FOOD_PER_WORKER * prices.get(Good.FOOD, 0.0)
        for parent in list(self.workers.values()):
            if not parent.alive or parent.is_child:
                continue
            children = [
                self.workers[child_id]
                for child_id in parent.children_ids
                if child_id in self.workers
                and self.workers[child_id].alive
                and self.workers[child_id].is_child
            ]
            if not children:
                continue
            available = max(0.0, parent.cash - adult_reserve)
            if available <= 1e-9:
                continue
            required = child_basket * len(children)
            pool = min(required, available)
            if pool <= 1e-9:
                continue
            share = pool / len(children)
            for child in children:
                parent.cash -= share
                child.cash += share

    def _submit_child_orders(self, child: Worker, prices: Dict[Good, float]) -> None:
        """儿童用 allowance 购买食品/衣物/住房（不含服务）。"""
        demo = self.demographics
        targets = (
            (Good.FOOD, demo.child_food, 1.05),
            (Good.CLOTH, demo.child_cloth, 1.04),
            (Good.BUILDING, demo.child_housing, 1.04),
        )
        stock = {
            Good.FOOD: child.food,
            Good.CLOTH: child.cloth,
            Good.BUILDING: child.housing,
        }
        cash_left = max(0.0, child.cash)
        for good, target, bid_multiplier in targets:
            gap = max(0.0, target - stock[good])
            if gap <= 1e-9 or cash_left <= 1e-9:
                continue
            bid = prices.get(good, 1.0) * bid_multiplier
            if good != Good.FOOD:
                gap *= max(0.0, getattr(self, "worker_demand_scale", 1.0))
            quantity = min(gap, cash_left / max(bid, 1e-9))
            if quantity <= 1e-9:
                continue
            self.market.submit_buy(child, good, quantity, bid)
            cash_left -= quantity * bid

    def _update_expectations_and_plans(self) -> None:
        """L1：按库存/欠交/需求预测生成生产计划。

        计划必须在生产之前生成；不能再用“生产后、销售前”的库存采样。
        计划同时约束产出、用工和采购，避免“计划只影响采购、产出仍满产”。
        """
        active_by_industry = {
            industry: len(self.active_enterprises(industry)) for industry in Industry
        }
        capacity_by_industry: Dict[Industry, float] = defaultdict(float)
        for enterprise in self.active_enterprises():
            workers = self.enterprise_workers(enterprise)
            skill = max(1.0, average_skill(workers)) if workers else 1.0
            capacity_by_industry[enterprise.industry] += (
                capacity_at_skill_one(enterprise) * skill
            )
        food_stock = sum(
            enterprise.inv(Good.FOOD)
            for enterprise in self.active_enterprises(Industry.AGRICULTURE)
        )
        monthly_food_need = max(1.0, self.feeding_units() * FOOD_PER_WORKER)
        essential = {
            Good.COAL,
            Good.IRON_ORE,
            Good.STEEL,
            Good.BRICK,
            Good.MACHINERY,
            Good.BUILDING,
            Good.FERTILIZER,
        }

        for enterprise in self.active_enterprises():
            params = SECTOR_PARAMS[enterprise.industry]
            out = params.output
            history = self.market.history[out]
            last_sales = enterprise.last_sales.get(out, 0.0)
            workers = self.enterprise_workers(enterprise)
            skill = max(1.0, average_skill(workers)) if workers else 1.0
            capacity = capacity_at_skill_one(enterprise) * skill
            total_capacity = capacity_by_industry[enterprise.industry]
            if total_capacity > 1e-9:
                share = capacity / total_capacity
            else:
                share = 1.0 / max(1, active_by_industry[enterprise.industry])
            # 用行业总需求 × 产能份额，而不是单个企业的成交量。
            # 否则在供不应求时，未成交的企业会把自己的预测越调越低。
            observed = (
                history.get("demand", 0.0) + history.get("unmet", 0.0)
            ) * share
            if enterprise.demand_forecast <= 1e-9:
                enterprise.demand_forecast = max(observed, capacity * 0.1)
            else:
                enterprise.demand_forecast = (
                    0.7 * enterprise.demand_forecast + 0.3 * observed
                )
            enterprise.last_demand = observed
            enterprise.last_unmet = max(0.0, observed - last_sales)
            enterprise.last_fill_rate = (
                last_sales / observed if observed > 1e-9 else 1.0
            )

            if capacity <= 1e-9:
                enterprise.plan_ratio = 0.0
                enterprise.planned_output = 0.0
                continue

            inventory = enterprise.inv(out)
            target = enterprise.target_inventory_months * enterprise.demand_forecast
            # POUT 式部分调整：6 个月重建目标库存，避免一阶振荡。
            desired = (
                enterprise.demand_forecast
                + max(0.0, target - inventory) / 6.0
            )
            plan = desired / capacity

            # 中间投入/资本品是产业链的底仓；但“最低运行率”必须
            # 跟当前需求走，否则低需求行业会按固定 10% 产能无限累库。
            demand_ratio = enterprise.demand_forecast / max(capacity, 1e-9)
            if inventory > 12.0 * max(
                enterprise.demand_forecast, capacity * 0.02
            ):
                # 库存超过约 12 个月需求：只保留 2% 产能的涓流，
                # 既停止大规模累库，又避免核心行业整月零产出。
                plan = min(plan, 0.02) if out in essential else 0.0
            elif out in essential:
                plan = max(
                    plan,
                    min(0.1, max(0.0, 0.9 * demand_ratio)),
                )

            if out == Good.FOOD and food_stock < 3.0 * monthly_food_need:
                # 食品是生存品：库存低于 3 个月时保持满产。
                plan = max(plan, 1.0)

            enterprise.plan_ratio = max(0.0, min(1.0, plan))
            enterprise.planned_output = capacity * enterprise.plan_ratio

    def _labor_market(self) -> None:
        prices = self.market.reference_prices
        floor = wage_floor(prices) * getattr(self, "wage_floor_scale", 1.0)
        vacancies: Dict[str, int] = {}
        offers: Dict[str, float] = {}
        food_stock = sum(
            enterprise.inv(Good.FOOD)
            for enterprise in self.active_enterprises(Industry.AGRICULTURE)
        )
        food_need = max(1.0, self.feeding_units() * FOOD_PER_WORKER)
        food_security = food_stock < 3.0 * food_need
        fertilizer_short = (
            FERTILIZER_HIRING_PRIORITY and self.fertilizer_supply_short()
        )

        def hiring_order(enterprise_id: str) -> tuple[int, float]:
            """短缺时化肥厂排在招聘队列最前，但仍按工资报价竞争。"""
            enterprise = self.enterprises[enterprise_id]
            critical = (
                0
                if fertilizer_short
                and enterprise.industry == Industry.FERTILIZER_FACTORY
                else 1
            )
            return critical, -offers[enterprise_id]

        for enterprise in self.active_enterprises():
            workers = self.enterprise_workers(enterprise)
            if (
                enterprise.is_household
                and enterprise.industry == Industry.SERVICE
            ):
                # 自雇摊主不是雇员：不能再领一份工资，否则会和
                # _finance 的经营所得 payout 重复计入，制造负利润。
                for worker in workers:
                    worker.wage = 0.0
                    worker.hours = worker.choose_hours(prices)
                offers[enterprise.id] = 0.0
                vacancies[enterprise.id] = 0
                continue
            required = desired_workers(enterprise, plan=enterprise.plan_ratio)
            effective = sum(w.effective_labor for w in workers)
            if required <= 0:
                target = 0
            else:
                # 精确用工：按当前平均工时折算需要的工人数，不再保留 1.33× 冗余。
                avg_eff = effective / len(workers) if workers else 1.0
                target = max(1, int(math.ceil(required / max(avg_eff, 0.5))))
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
            if food_security and enterprise.industry == Industry.AGRICULTURE:
                # 粮食安全溢价：食品库存低于 3 个月时，农场优先留住工人。
                offer = min(offer * 1.30, WAGE_BASE * 5.0)
            offers[enterprise.id] = offer
            # 现有员工按企业当前工资报价支付。自耕农所有者例外：
            # 他是剩余索取者，wage 必须保持 0，收入只走经营所得 payout。
            for worker in workers:
                if self._is_household_farm_owner(enterprise, worker):
                    worker.wage = 0.0
                else:
                    worker.wage = offer
                worker.hours = worker.choose_hours(prices)
                worker.industry = enterprise.industry
            vacancies[enterprise.id] = max(0, target - len(workers))

        # 先雇佣失业者，再允许有限度的跳槽。
        unemployed = [
            w
            for w in self.workers.values()
            if w.alive
            and w.is_working_age
            and not w.employed
            and not w.is_owner_operator
        ]
        unemployed.sort(key=lambda w: (w.cash, w.id))
        hiring = sorted(
            [e for e in vacancies if vacancies[e] > 0],
            key=hiring_order,
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
            key=hiring_order,
        )
        switches = 0
        if hiring:
            for worker in self.workers.values():
                if switches >= 20 or not hiring:
                    break
                if (
                    not worker.alive
                    or not worker.is_working_age
                    or not worker.employed
                    or worker.is_owner_operator
                ):
                    continue
                best_id = hiring[0]
                best_offer = offers[best_id]
                if not should_switch(worker.wage, best_offer):
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

        # 正规部门招聘结束后，失业者可用手工服务摊自雇。
        # MMT 的就业保障仍是最后雇主，吸收服务业容纳不下的剩余失业。
        self._service_self_employment(prices)
        if self.government is not None and self.government.job_guarantee:
            self._job_guarantee()

    def _hire(
        self,
        enterprise: Enterprise,
        worker: Worker,
        offer: float,
        prices: Dict[Good, float],
    ) -> None:
        if worker.industry != enterprise.industry:
            worker.skill = max(1.0, worker.skill * 0.75)
        if (
            self.government is not None
            and worker.id in self.government.jg_workers
        ):
            self.government.jg_workers.remove(worker.id)
        worker.industry = enterprise.industry
        worker.employer_id = enterprise.id
        worker.wage = offer
        worker.hours = worker.choose_hours(prices)
        if worker.id not in enterprise.workers:
            enterprise.workers.append(worker.id)

    def _service_self_employment(self, prices: Dict[Good, float]) -> None:
        """失业者以零资本的手工服务摊进入非正规部门。

        只在服务市场存在超额需求时进入：上月有买盘、供给不足且仍有
        未成交订单。这样既不会制造“没有销路的就业”，也能让服务业在
        食品/衣物/住房都买不起的贫困家庭之外，按实际需求逐步吸收劳动力。
        自雇者不受工资下限约束，经营所得由 ``_finance`` 直接转给摊主。
        """
        service_firms = self.active_enterprises(Industry.SERVICE)
        params = SECTOR_PARAMS[Industry.SERVICE]
        if len(service_firms) >= params.max_firms:
            return
        history = self.market.history[Good.SERVICE]
        demand = history.get("demand", 0.0)
        supply = history.get("supply", 0.0)
        unmet = history.get("unmet", 0.0)
        if demand <= 1e-9 or supply + 1e-9 >= demand or unmet <= 0.25:
            return
        price = prices.get(Good.SERVICE, 0.0)
        capacity = EQUIPMENT["service_t0"].capacity
        if price * capacity < SERVICE_ENTRY_MIN_REVENUE:
            return

        candidates = [
            worker
            for worker in self.workers.values()
            if worker.alive
            and worker.is_working_age
            and not worker.employed
            and not worker.is_owner_operator
        ]
        # 优先让最贫困的失业者自雇；他们边际上最需要现金收入。
        candidates.sort(key=lambda worker: (worker.cash, worker.id))
        target = min(
            MAX_SERVICE_ENTRIES_PER_MONTH,
            max(1, int(math.ceil(unmet / max(capacity, 1e-9)))),
        )
        created = 0
        for worker in candidates:
            if created >= target or len(service_firms) >= params.max_firms:
                break
            enterprise = self.create_enterprise(
                Industry.SERVICE,
                owner_id=worker.id,
                cash=0.0,
                is_household=True,
                modernization_capable=False,
            )
            enterprise.add_equipment("service_t0", 1)
            enterprise.demand_forecast = capacity
            # 服务不可储存：不设库存目标，当月未售出部分月末作废。
            enterprise.target_inventory_months = 0.0
            # 跨行业进入的熟练度折减，与原 _hire 的规则一致。
            worker.skill = max(1.0, worker.skill * 0.75)
            worker.industry = Industry.SERVICE
            worker.employer_id = enterprise.id
            worker.wage = 0.0
            worker.hours = worker.choose_hours(prices)
            worker.is_owner_operator = True
            enterprise.workers.append(worker.id)
            service_firms.append(enterprise)
            created += 1

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
            if self._is_household_farm(enterprise):
                # 自耕农不领工资，但其自有劳动仍有机会成本。价格带用
                # WAGE_BASE 作为影子工资，避免零现金成本把粮食价格带
                # 压塌、进而让农机/化肥投资信号失真；该影子成本
                # 不进入工资账单、利润表或任何现金转移。
                owner_labor = sum(
                    worker.effective_labor
                    for worker in workers
                    if self._is_household_farm_owner(enterprise, worker)
                )
                if owner_labor > 0 and enterprise.last_output > 1e-9:
                    cost += (
                        owner_labor
                        * WAGE_BASE
                        / enterprise.last_output
                    )
            if cost > 1e-6:
                by_good[good].append(cost)
        for good, costs in by_good.items():
            if not costs:
                continue
            costs.sort()
            median = costs[len(costs) // 2]
            initial = INITIAL_PRICES[good]
            # 安全轨必须有绝对上下限；否则单位成本（含工资）上涨会
            # 把价格带越推越高，再通过工资下限形成工资—价格螺旋。
            self.market.ceilings[good] = min(
                max(median * 2.5, initial * 1.5), initial * 4.0
            )
            # 不要让过剩把价格压到重置成本以下；那会形成
            # 通货紧缩陷阱：农场买不起化肥，农机投资也会停止。

            self.market.floors[good] = min(
                max(median * 0.90, initial * 0.60), initial * 2.0
            )

    def _bank_intermediation(self) -> None:
        """金本位下的银行存款中介：把闲置现金吸到银行，再贷给企业。

        存款/取款/利息都是现金转移，货币总量守恒。
        """
        for capitalist in self.capitalists.values():
            if capitalist.cash > 10_000.0:
                self.bank.deposit(
                    capitalist, (capitalist.cash - 10_000.0) * 0.10
                )
        for worker in self.workers.values():
            if worker.alive and worker.is_working_age and worker.cash > 1000.0:
                self.bank.deposit(worker, (worker.cash - 1000.0) * 0.02)
        self.bank.pay_deposit_interest(
            {**self.workers, **self.capitalists}
        )

    def _pay_wages(self) -> None:
        gov = self.government
        pension_rate = (
            gov.pension_tax_rate if gov is not None else 0.0
        )
        for enterprise in self.active_enterprises():
            # 自耕农所有者不是雇员：其收入在 `_finance` 按经营所得
            # payout 发放。这里必须把他排除在工资账单和支付循环之外，
            # 否则农场会为“给自己发工资”而垫资/借债并最终破产。
            workers = [
                worker
                for worker in self.enterprise_workers(enterprise)
                if not self._is_household_farm_owner(enterprise, worker)
            ]
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
                shortfall = bill - enterprise.cash
                # 信贷冲击测试钩子：默认 1.0，完全等同原行为。
                self.bank.lend(
                    enterprise,
                    shortfall * max(0.0, getattr(self, "lending_scale", 1.0)),
                )
            factor = 1.0
            if enterprise.cash < bill:
                factor = max(0.0, enterprise.cash / bill)
            for worker in workers:
                gross = worker.wage * worker.effective_labor * factor
                # PAYG 缴费在发薪时从毛工资中代扣，而不是等到月末从
                # 工人已消费后的剩余现金里再收（那会让实际缴费率远低于
                # 法定费率）。企业支付毛工资，政府收到缴费，工人拿净工资。
                contribution = 0.0
                if pension_rate > 0 and gov is not None:
                    contribution = gross * pension_rate
                    gov.cash += contribution
                    gov.pension_fund += contribution
                    gov.pension_contributions += contribution
                    gov.pension_revenue += contribution
                enterprise.cash -= gross
                worker.cash += gross - contribution
                enterprise.month_wages += gross

    # ------------------------------------------------------------------
    # 政府 / 央行（历史阶段模块）
    # ------------------------------------------------------------------
    def _job_guarantee(self) -> None:
        """MMT 的最后雇主：把剩余失业者吸收到公共工程。"""
        gov = self.government
        if gov is None or not gov.job_guarantee:
            return
        if gov.jg_max_workers > 0 and len(gov.jg_workers) >= gov.jg_max_workers:
            return
        unemployed = [
            worker
            for worker in self.workers.values()
            if worker.alive
            and worker.is_working_age
            and not worker.employed
            and not worker.is_owner_operator
        ]
        unemployed.sort(key=lambda worker: (worker.cash, worker.id))
        for worker in unemployed:
            if gov.jg_max_workers > 0 and len(gov.jg_workers) >= gov.jg_max_workers:
                break
            worker.employer_id = "GOV"
            worker.wage = gov.jg_wage
            worker.hours = 16
            worker.industry = Industry.CONSTRUCTION
            worker.ui_months = 0
            gov.jg_workers.append(worker.id)

    def _pay_government_wages(self) -> None:
        gov = self.government
        if gov is None or not gov.jg_workers:
            return
        alive = []
        bill = 0.0
        for worker_id in gov.jg_workers:
            worker = self.workers.get(worker_id)
            if worker is None or not worker.alive:
                continue
            alive.append(worker_id)
            bill += worker.wage * worker.effective_labor
        gov.jg_workers = alive
        if bill <= 1e-9:
            return
        self._government_finance(max(0.0, bill - gov.cash), "wages")
        factor = min(1.0, gov.cash / bill) if bill > 0 else 0.0
        pension_rate = gov.pension_tax_rate
        for worker_id in gov.jg_workers:
            worker = self.workers[worker_id]
            gross = worker.wage * worker.effective_labor * factor
            contribution = gross * pension_rate if pension_rate > 0 else 0.0
            # 就业保障工人同样参加 PAYG：毛工资中代扣，净额发放。
            gov.cash -= gross - contribution
            worker.cash += gross - contribution
            gov.pension_fund += contribution
            gov.pension_contributions += contribution
            gov.pension_revenue += contribution
        gov.spending += bill * factor

    def _produce_government(self) -> None:
        """公共工程产出：就业保障工人建造公共住房。"""
        gov = self.government
        if gov is None or not gov.jg_workers:
            return
        labor = sum(
            self.workers[worker_id].effective_labor
            for worker_id in gov.jg_workers
            if worker_id in self.workers and self.workers[worker_id].alive
        )
        output = 0.4 * labor
        gov.inventory[Good.BUILDING] += output
        gov.public_capital += output

    def _government_finance(self, amount: float, purpose: str) -> float:
        """为政府支出缺口融资。

        MMT：央行购买国债/创造货币；金本位与 Keynesian：向资本家和银行
        发行债券，货币守恒。若融不到足够资金，则让支出按比例缩减。

        ``amount`` 是调用方已经扣除现有 ``gov.cash`` 后的**缺口**；
        本函数只负责为这个缺口融资，不能再减一次政府现金，否则在
        ``0 < gov.cash < bill`` 时会系统性少付（UI/养老金/公共投资）。
        """
        gov = self.government
        if gov is None or amount <= 1e-9:
            return 0.0
        need = max(0.0, amount)
        if need <= 1e-9:
            return 0.0
        if gov.fiat_money:
            gov.cash += need
            gov.central_bank_money += need
            gov.debt += need
            gov.bond_holders["CENTRAL_BANK"] = (
                gov.bond_holders.get("CENTRAL_BANK", 0.0) + need
            )
            return need
        buyers = [
            (capitalist.id, capitalist.cash)
            for capitalist in self.capitalists.values()
            if capitalist.cash > 0
        ]
        buyers.append(("BANK", self.bank.cash))
        buyers.sort(key=lambda item: item[1], reverse=True)
        raised = 0.0
        for buyer_id, cash in buyers:
            if raised >= need:
                break
            take = min(need - raised, cash * 0.5)
            if take <= 1e-9:
                continue
            if buyer_id == "BANK":
                self.bank.cash -= take
            else:
                self.capitalists[buyer_id].cash -= take
            gov.cash += take
            gov.debt += take
            gov.bond_holders[buyer_id] = (
                gov.bond_holders.get(buyer_id, 0.0) + take
            )
            raised += take
        return raised

    def _submit_food_reserve_orders(self) -> None:
        """粮食平准库存：高价释放，低价收储。

        高价时只释放“救济缓冲”以外的库存。缓冲用于 `_distribute_food_relief`：
        如果全部卖空，价格机制会在饥荒时把粮食救济变成空账（V0.5 回归）。
        """
        reserve = self.food_reserve
        price = self.market.reference_prices[Good.FOOD]
        initial = INITIAL_PRICES[Good.FOOD]
        monthly_need = max(1.0, self.feeding_units() * FOOD_PER_WORKER)
        relief_buffer = FOOD_RELIEF_BUFFER_MONTHS * monthly_need
        if price > 1.15 * initial and reserve.food > relief_buffer + 1e-9:
            quantity = min(
                reserve.food - relief_buffer, 0.50 * monthly_need
            )
            if quantity > 1e-9:
                self.market.submit_sell(
                    reserve, Good.FOOD, quantity, price * 0.95
                )
        elif price < 0.85 * initial and reserve.cash > 1e-9:
            quantity = min(
                0.10 * monthly_need, reserve.cash / max(price, 1e-9)
            )
            if quantity > 1e-9:
                self.market.submit_buy(
                    reserve, Good.FOOD, quantity, price * 1.05
                )

    def _submit_government_orders(self) -> None:
        gov = self.government
        if gov is None or not gov.active:
            return
        gdp = self.stats[-1]["gdp"] if self.stats else 0.0
        budget = gov.public_investment_rate * gdp
        if gov.public_investment_countercyclical > 0 and self.stats:
            unemployment = self.stats[-1]["unemployment_rate"]
            budget += (
                gov.public_investment_countercyclical
                * max(0.0, 0.07 - unemployment)
                * gdp
            )
        # 财政现金不能无限闲置：超过 5000 的部分优先用于公共投资。
        if gov.cash > 5000.0 and gdp > 0:
            budget += min(gov.cash - 5000.0, 0.05 * gdp)
        gov.public_investment_budget = max(0.0, budget)
        if budget <= 1e-9:
            return
        self._government_finance(max(0.0, budget - gov.cash), "public_investment")
        spend = min(budget, gov.cash)
        if spend <= 1e-9:
            return
        prices = self.market.reference_prices
        for good, weight in ((Good.BUILDING, 0.6), (Good.MACHINERY, 0.4)):
            target = spend * weight
            price = prices.get(good, 1.0)
            quantity = target / max(price, 1e-9)
            if quantity > 1e-9:
                self.market.submit_buy(gov, good, quantity, price * 1.05)

    def _government_settlement(self) -> None:
        gov = self.government
        if gov is None or not gov.active:
            return
        # 工资税
        for worker in self.workers.values():
            if not worker.alive or not worker.employed:
                continue
            income = worker.wage * worker.effective_labor
            if income <= 0:
                continue
            tax = min(worker.cash, income * gov.tax_rate_wage)
            worker.cash -= tax
            gov.cash += tax
            gov.tax_revenue += tax
        # 利润税
        for enterprise in self.active_enterprises():
            if enterprise.last_profit <= 0:
                continue
            tax = min(
                enterprise.cash, enterprise.last_profit * gov.tax_rate_profit
            )
            enterprise.cash -= tax
            gov.cash += tax
            gov.tax_revenue += tax
        # 养老金缴费已在 `_pay_wages` / `_pay_government_wages` 发薪时
        # 从毛工资中代扣并记入基金；这里不再从消费后的剩余现金征收。
        # 失业救济（儿童/退休者不进入失业救济）
        avg_wage = self.average_wage()
        for worker in self.workers.values():
            if not worker.alive:
                continue
            if worker.is_child or worker.retired:
                continue
            if worker.employed:
                worker.ui_months = 0
                continue
            if worker.is_owner_operator:
                continue
            if gov.ui_duration > 0 and worker.ui_months >= gov.ui_duration:
                continue
            benefit = avg_wage * gov.ui_replacement
            if benefit <= 0:
                continue
            self._government_finance(max(0.0, benefit - gov.cash), "ui")
            paid = min(benefit, gov.cash)
            if paid > 0:
                gov.cash -= paid
                worker.cash += paid
                gov.transfers += paid
            worker.ui_months += 1
        # 养老金发放：替代率 × 社会平均工资；基金不足时显式融资/按比例发放。
        if gov.pension_replacement > 0:
            # 雇员到龄退休后领取；自耕农/自雇摊主不强制退出经营，但到龄
            # 后也领取养老金——他们同样缴纳了 PAYG 缴费，不能只缴不领。
            retirement_age = self.demographics.retirement_age_months
            retirees = [
                worker
                for worker in self.workers.values()
                if worker.alive
                and (
                    worker.retired
                    or (
                        retirement_age > 0
                        and worker.is_owner_operator
                        and not worker.is_child
                        and worker.age_months >= retirement_age
                    )
                )
            ]
            for worker in retirees:
                worker.pension_income = 0.0
            # 替代率 × 平均工资；若低于食品温饱线，按食品线兜底。
            # 这是显式的社会养老金下限，仍由基金/财政融资，不创造货币。
            food_line = FOOD_PER_WORKER * self.market.reference_prices.get(
                Good.FOOD, 0.0
            )
            benefit = max(
                gov.pension_replacement * avg_wage,
                food_line,
            )
            due = benefit * len(retirees)
            if due > 1e-9:
                if gov.cash < due:
                    self._government_finance(due - gov.cash, "pension")
                if gov.pension_fund < due:
                    topup = min(
                        due - gov.pension_fund,
                        max(0.0, gov.cash),
                    )
                    if topup > 0:
                        gov.pension_fund += topup
                        gov.pension_subsidy += topup
                        # 补贴进入基金台账，也必须进入当期收入；
                        # 否则 fund_t = fund_{t-1} + revenue - spending
                        # 会漏掉补贴，长程基金恒等式出现缺口。
                        gov.pension_revenue += topup
                factor = min(
                    1.0,
                    gov.pension_fund / due,
                    gov.cash / due,
                )
                if factor < 1.0 - 1e-9:
                    self._pension_shortfall += due * (1.0 - factor)
                paid_total = 0.0
                for worker in retirees:
                    paid = benefit * factor
                    if paid <= 1e-9:
                        continue
                    gov.cash -= paid
                    gov.pension_fund -= paid
                    worker.cash += paid
                    worker.pension_income = paid
                    paid_total += paid
                gov.pension_spending += paid_total
                # 浮点误差可能留下 -1e-12 量级的“负基金”；显式归零，
                # 真正的赤字已通过 pension_subsidy/按比例发放记录。
                if -1e-6 < gov.pension_fund < 0.0:
                    gov.pension_fund = 0.0
        if gov.pension_revenue > 0 or gov.pension_spending > 0:
            gov.pension_balance = gov.pension_revenue - gov.pension_spending
        # 国债利息
        if gov.debt > 0 and gov.bond_holders:
            interest = gov.debt * self.bank.interest_rate
            self._government_finance(
                max(0.0, interest - gov.cash), "interest"
            )
            paid = min(interest, gov.cash)
            if paid > 0:
                gov.cash -= paid
                gov.interest_paid += paid
                total = sum(gov.bond_holders.values()) or 1.0
                for holder_id, amount in list(gov.bond_holders.items()):
                    share = amount / total
                    if holder_id == "BANK" or holder_id == "CENTRAL_BANK":
                        self.bank.cash += paid * share
                    else:
                        holder = self.capitalists.get(holder_id)
                        if holder is not None:
                            holder.cash += paid * share
                        else:
                            self.bank.cash += paid * share
        gov.spending += self.market.government_spending
        # 养老金会计进入显式预算恒等式：缴费是政府收入侧，发放是支出侧。
        # pension_subsidy 是基金缺口的融资（发债/央行），属于融资而非收入，
        # 因此不计入 deficit 公式；它只进入基金台账。
        gov.deficit = (
            gov.spending
            + gov.transfers
            + gov.pension_spending
            + gov.interest_paid
            - gov.tax_revenue
            - gov.pension_contributions
        )

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

        # 0）死掉的行业：用一次手工 t0 重启（无资本品、小规模）。
        for industry, manual_key in MANUAL_EQUIPMENT.items():
            if not self.active_enterprises(industry):
                self._bootstrap_manual_entry(industry, manual_key)

        # 0.5）替换投资：按 δK 的聚合流量，每 12 个月补充一台主力设备。
        # 不能等设备 age=120 才替换，否则资本品部门在前期没有底仓需求。
        for enterprise in self.active_enterprises():
            if started >= MAX_PROJECTS_PER_TICK:
                break
            if not enterprise.equipment:
                continue
            if enterprise.industry == Industry.AGRICULTURE and enterprise.is_household:
                continue
            out_good = SECTOR_PARAMS[enterprise.industry].output
            if (
                enterprise.plan_ratio < 0.2
                and enterprise.inv(out_good)
                > 6.0 * max(enterprise.demand_forecast, 1e-9)
            ):
                continue
            if self.tick - enterprise.last_invest_tick < 12:
                continue
            key = max(
                enterprise.equipment,
                key=lambda k: (
                    enterprise.equipment[k],
                    EQUIPMENT[k].capacity,
                ),
            )
            if self._start_project(enterprise, key):
                started += 1

        # 1）现有资本主义农场。预留两个名额，避免农业转型
        # 被煤/铁项目挤掉。
        farms = [
            e
            for e in self.active_enterprises(Industry.AGRICULTURE)
            if not e.is_household
        ]
        farms.sort(key=lambda e: e.id)
        # 农业保留 priority，但给活跃农业项目设硬上限；
        # 否则 18 个农场项目会占满全部投资名额，把非农投资锁死。
        active_agri_projects = sum(
            1
            for project in self.projects.values()
            if project.active and project.industry == Industry.AGRICULTURE
        )
        agri_cap = max(1, min(3, MAX_ACTIVE_PROJECTS // 3))
        farms_started = 0
        for enterprise in farms:
            if (
                started >= MAX_PROJECTS_PER_TICK
                or farms_started >= 2
                or active_agri_projects >= agri_cap
            ):
                break
            choice = should_invest(self, enterprise)
            if choice is None:
                continue
            key, _ = choice
            if self._start_project(enterprise, key, priority=True):
                started += 1
                farms_started += 1
                active_agri_projects += 1

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
            if (
                industry == Industry.FERTILIZER_FACTORY
                and not self.active_enterprises(industry)
            ):
                # 化肥是农业的互补投入：没有化肥厂时，用农场的潜在需求
                # 而不是“上月化肥销量=0”来评估进入，避免鸡生蛋死锁。
                potential_demand = sum(
                    farm.land * FERTILIZER_PER_MU
                    for farm in self.active_enterprises(Industry.AGRICULTURE)
                    if farm.modernization_capable
                )
                choice = best_equipment_choice(
                    self,
                    industry,
                    budget=100_000.0,
                    demand_override=max(potential_demand, 1.0),
                )
            else:
                choice = best_equipment_choice(
                    self, industry, budget=100_000.0
                )
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

    def _submit_les_worker_orders(
        self, worker: Worker, prices: Dict[Good, float]
    ) -> None:
        """Stone-Geary LES：生存底线 + 收入/价格弹性。

        budget 低于 3 倍生存成本时全部花掉；高于时保留 2 个月生存储蓄。
        """
        goods = (Good.FOOD, Good.CLOTH, Good.BUILDING)
        gamma = {Good.FOOD: 0.10, Good.CLOTH: 0.50, Good.BUILDING: 0.10}
        beta = {Good.FOOD: 0.30, Good.CLOTH: 0.20, Good.BUILDING: 0.20}
        price = {good: max(prices.get(good, 1.0), 1e-9) for good in goods}
        subsistence = sum(price[good] * gamma[good] for good in goods)
        if worker.cash <= 3.0 * subsistence:
            budget = worker.cash
        else:
            budget = worker.cash - 2.0 * subsistence
        if budget <= subsistence:
            # 预算不足时食品优先：先保证 0.1 吨口粮，再分配衣物/住房。
            food_quantity = min(
                FOOD_PER_WORKER, budget / max(price[Good.FOOD], 1e-9)
            )
            remaining = max(
                0.0, budget - food_quantity * price[Good.FOOD]
            )
            weight = gamma[Good.CLOTH] + gamma[Good.BUILDING]
            quantities = {
                Good.FOOD: food_quantity,
                Good.CLOTH: (
                    remaining * gamma[Good.CLOTH] / weight
                    / max(price[Good.CLOTH], 1e-9)
                    if weight > 0 else 0.0
                ),
                Good.BUILDING: (
                    remaining * gamma[Good.BUILDING] / weight
                    / max(price[Good.BUILDING], 1e-9)
                    if weight > 0 else 0.0
                ),
            }
        else:
            extra = budget - subsistence
            quantities = {
                good: gamma[good] + beta[good] * extra / price[good]
                for good in goods
            }
        stock = {
            Good.FOOD: worker.food,
            Good.CLOTH: worker.cloth,
            Good.BUILDING: worker.housing,
        }
        # 需求冲击钩子：只削减非食品消费；食品是生存品。
        scale = max(0.0, getattr(self, "worker_demand_scale", 1.0))
        cash_left = worker.cash
        for good in goods:
            need = max(0.0, quantities[good] - stock[good])
            if good != Good.FOOD:
                need *= scale
            if need <= 1e-9:
                continue
            bid_multiplier = (
                1.08 if good == Good.FOOD and worker.food < 0.05 else 1.04
            )
            bid = price[good] * bid_multiplier
            quantity = min(need, cash_left / max(bid, 1e-9))
            if quantity <= 1e-9:
                continue
            self.market.submit_buy(worker, good, quantity, bid)
            cash_left -= quantity * bid

        # 服务是温饱之后的可选消费，放在最后用剩余预算。
        service_gap = max(0.0, SERVICE_PER_HOUSEHOLD - worker.service)
        if service_gap > 1e-9 and cash_left > 0:
            bid = prices.get(Good.SERVICE, 10.0) * 1.02
            quantity = min(service_gap, cash_left / max(bid, 1e-9))
            if quantity > 1e-9:
                self.market.submit_buy(worker, Good.SERVICE, quantity, bid)

    def _submit_household_orders(self) -> None:
        prices = self.market.reference_prices
        # 家长先把儿童预算以现金转给儿童；儿童随后独立挂买单。
        self._pay_child_allowances(prices)
        for worker in self.workers.values():
            if not worker.alive:
                continue
            if worker.is_child:
                self._submit_child_orders(worker, prices)
                continue
            if self.demand_regime == "les":
                self._submit_les_worker_orders(worker, prices)
                continue
            comfort = worker.living_standard in ("comfort", "leisure")
            # 有积蓄且已有基础口粮时才尝试升级到 1.5 倍篮子；
            # 否则基础温饱工人会被误判为小康，瞬间把食品需求推高 50%。
            aspire_comfort = (
                worker.cash >= COMFORT_SAVINGS
                and worker.food >= FOOD_PER_WORKER
            )
            mult = COMFORT_MULTIPLIER if (comfort or aspire_comfort) else 1.0
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
                qty = min(
                    cloth_gap * getattr(self, "worker_demand_scale", 1.0),
                    budget / max(bid, 1e-9),
                )
                if qty > 1e-9:
                    self.market.submit_buy(worker, Good.CLOTH, qty, bid)
                    cash_left -= qty * bid

            housing_gap = max(0.0, HOUSING_PER_WORKER * mult - worker.housing)
            if housing_gap > 1e-9 and cash_left > 0:
                bid = prices[Good.BUILDING] * 1.04
                qty = min(
                    housing_gap * getattr(self, "worker_demand_scale", 1.0),
                    cash_left * 0.50 / max(bid, 1e-9),
                )
                if qty > 1e-9:
                    self.market.submit_buy(worker, Good.BUILDING, qty, bid)

            # 服务排在最后；先为住房预留预算，避免服务挤占温饱。
            service_gap = max(0.0, SERVICE_PER_HOUSEHOLD * mult - worker.service)
            if service_gap > 1e-9 and cash_left > 0:
                bid = prices.get(Good.SERVICE, 10.0) * 1.02
                housing_reserve = (
                    HOUSING_PER_WORKER * mult * prices.get(Good.BUILDING, 0.0)
                )
                budget = max(0.0, cash_left - housing_reserve)
                qty = min(service_gap, budget / max(bid, 1e-9))
                if qty > 1e-9:
                    self.market.submit_buy(worker, Good.SERVICE, qty, bid)

        for capitalist in self.capitalists.values():
            budget = max(
                CAPITALIST_MIN_CONSUMPTION,
                capitalist.cash * CAPITALIST_CONSUMPTION_RATE,
            ) * getattr(self, "capitalist_demand_scale", 1.0)
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

            service_gap = max(0.0, CAPITALIST_SERVICE - capitalist.service)
            if service_gap > 1e-9 and cash_left > 0:
                bid = prices.get(Good.SERVICE, 10.0) * 1.02
                housing_reserve = CAPITALIST_HOUSING * prices.get(
                    Good.BUILDING, 0.0
                )
                budget = max(0.0, cash_left - housing_reserve)
                qty = min(service_gap, budget / max(bid, 1e-9))
                if qty > 1e-9:
                    self.market.submit_buy(capitalist, Good.SERVICE, qty, bid)

    def _submit_input_orders(self) -> None:
        prices = self.market.reference_prices
        for enterprise in self.active_enterprises():
            needs = input_needs(self, enterprise)
            if not needs:
                continue
            workers = self.enterprise_workers(enterprise)
            wage_bill = sum(w.wage * w.effective_labor for w in workers)
            # 营运资本：企业现金不足时，所有者先注入一部分。
            # 金本位下这是权益注资，不创造货币。
            input_cash = sum(
                qty * prices.get(good, 0.0) * 1.06 for good, qty in needs.items()
            )
            required_cash = wage_bill * 2.0 + input_cash * 0.5
            if enterprise.industry == Industry.FERTILIZER_FACTORY:
                # 化肥厂只有煤一种投入：先保证采购现金和煤库存缓冲，
                # 其余现金才可以拿去投资/分红。
                required_cash = (
                    wage_bill * 2.0
                    + input_cash
                    + self.fertilizer_coal_reserve(enterprise)
                )
            if enterprise.cash < required_cash:
                owner = self.capitalists.get(enterprise.owner_id)
                if owner is not None and owner.cash > 0:
                    injection = min(
                        required_cash - enterprise.cash,
                        owner.cash * 0.5,
                    )
                    owner.cash -= injection
                    enterprise.cash += injection
            input_total = sum(
                qty * prices.get(good, 0.0) * 1.06
                for good, qty in needs.items()
            )
            input_reserve = input_total * 0.5
            # 营运资本贷款：只有工资能借、投入品不能借，会在
            # “建筑没钱买砖、砖厂没销路”之间形成流动性死锁。
            shortfall = max(
                0.0, wage_bill * 2.0 + input_reserve - enterprise.cash
            )
            if shortfall > 1e-9:
                self.bank.lend(enterprise, shortfall)
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
            if (
                project.industry == Industry.FERTILIZER_FACTORY
                and enterprise.total_equipment() >= 2
            ):
                # 兜底：任何路径都不能把化肥厂推过 2 台反应炉。
                self.asset_pool.equipment[project.equipment_key] = (
                    self.asset_pool.equipment.get(project.equipment_key, 0)
                    + project.quantity
                )
            else:
                enterprise.add_equipment(project.equipment_key, project.quantity)
            enterprise.active = True
            enterprise.cash += project.cash
            # 项目剩余库存必须退回企业；否则资本品会凭空消失。
            for good, qty in project.inventory.items():
                if qty > 0:
                    enterprise.inventory[good] = enterprise.inv(good) + qty
        else:
            # 孤儿项目：退款给银行，货物进资产池，避免资产被销毁。
            self.bank.cash += project.cash
            for good, qty in project.inventory.items():
                if qty > 0:
                    self.asset_pool.inventory[good] += qty
        project.inventory = {g: 0.0 for g in Good}
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
            for good, qty in project.inventory.items():
                if qty > 0:
                    self.asset_pool.inventory[good] += qty
        project.inventory = {g: 0.0 for g in Good}
        project.cash = 0.0
        project.active = False

    # ------------------------------------------------------------------
    # 金融 / 分红 / 破产
    # ------------------------------------------------------------------
    def _finance(self) -> None:
        prices = self.market.reference_prices
        gov = self.government
        pension_rate = gov.pension_tax_rate if gov is not None else 0.0
        for enterprise in list(self.active_enterprises()):
            self.bank.charge_interest(enterprise)
            workers = self.enterprise_workers(enterprise)
            wage_bill = sum(w.wage * w.effective_labor for w in workers)
            if enterprise.cash > wage_bill * 6.0 + 100.0:
                self.bank.repay(enterprise, (enterprise.cash - wage_bill * 3.0) * 0.30)

            enterprise.last_revenue = enterprise.month_revenue
            # 利润表按“实际消耗投入 × 当前参考价”计中间成本。
            # month_input_cost 是采购现金流，采购多不等于亏得多。
            enterprise.last_costs = sum(
                qty * prices.get(good, 0.0)
                for good, qty in enterprise.last_input_used.items()
            )
            enterprise.last_wages = enterprise.month_wages
            enterprise.last_interest = enterprise.month_interest
            # 土地是资产，不计折旧；只对设备计提。
            depreciation = equipment_value(enterprise, prices) / DEPRECIATION_MONTHS
            enterprise.last_profit = (
                enterprise.last_revenue
                - enterprise.last_costs
                - enterprise.last_wages
                - enterprise.last_interest
                - depreciation
            )

            if enterprise.is_household and enterprise.industry == Industry.SERVICE:
                # 自雇摊主不是雇员：当月经营现金在扣除少量周转金后
                # 直接成为家庭收入，不经过工资下限，也不形成资本回报。
                payout = 0.0
                owner = self.workers.get(enterprise.owner_id)
                if owner is not None and owner.alive:
                    payout = max(0.0, enterprise.cash - SERVICE_FIRM_RESERVE)
                    if payout > 0:
                        enterprise.cash -= payout
                        owner.cash += payout
                        enterprise.last_profit -= payout
                enterprise.last_operating_payout = payout
                if enterprise.month_revenue <= 1e-9:
                    enterprise.service_idle_months += 1
                else:
                    enterprise.service_idle_months = 0

            if self._is_household_farm(enterprise):
                # 自耕农所有者同样是剩余索取者：扣除周转金后的经营现金
                # 作为家庭经营所得，不是工资，也不是资本利润。
                # PAYG 缴费按经营所得代扣，保持与工资劳动者相同的费率；
                # 这样 owner.wage=0 不会让自耕农逃避养老金缴费。
                payout = 0.0
                owner = self.workers.get(enterprise.owner_id)
                if owner is not None and owner.alive:
                    payout = max(
                        0.0, enterprise.cash - HOUSEHOLD_FARM_RESERVE
                    )
                    if payout > 0:
                        contribution = 0.0
                        if pension_rate > 0 and gov is not None:
                            contribution = payout * pension_rate
                            gov.cash += contribution
                            gov.pension_fund += contribution
                            gov.pension_contributions += contribution
                            gov.pension_revenue += contribution
                        enterprise.cash -= payout
                        owner.cash += payout - contribution
                        enterprise.last_profit -= payout
                enterprise.last_operating_payout = payout

            if (
                not self._is_household_farm(enterprise)
                and enterprise.last_profit > 0
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
        # 仅用于验证：家庭农场不应因“给自己发工资”而破产清算。
        # 土地市场上的自愿卖地走 `_remove_smallholder`，不计入这里。
        if self._is_household_farm(enterprise):
            self._household_farm_liquidations_this_month += 1
            self.household_farm_liquidations_total += 1
        for worker_id in list(enterprise.workers):
            worker = self.workers.get(worker_id)
            if worker:
                worker.employer_id = None
                worker.wage = 0.0
        enterprise.workers.clear()
        # 家庭农场/服务摊破产时，所有者必须回到劳动市场；否则
        # is_owner_operator 会把他永久排除在雇佣、自雇和就业保障之外。
        owner_worker = self.workers.get(enterprise.owner_id)
        if owner_worker is not None:
            owner_worker.is_owner_operator = False
            owned_mu = self.land.owners.pop(owner_worker.id, 0.0)
            owner_worker.land_owned = 0.0
            self.land.enterprise_by_owner.pop(owner_worker.id, None)
            # 家庭农场土地通常已记录在 enterprise.land 中；只有
            # land.owners 多出来的部分才补进待售土地，避免重复计算。
            if owned_mu > enterprise.land:
                self.land.estate_land += owned_mu - enterprise.land
        # 现金归银行；库存/设备/土地进资产池，不能凭空消失。
        if enterprise.cash > 0:
            self.bank.cash += enterprise.cash
            enterprise.cash = 0.0
        for good, qty in enterprise.inventory.items():
            if qty > 0:
                self.asset_pool.inventory[good] += qty
        for key, count in enterprise.equipment.items():
            if count > 0:
                self.asset_pool.equipment[key] = (
                    self.asset_pool.equipment.get(key, 0) + count
                )
        if enterprise.land > 0:
            self.land.estate_land += enterprise.land
        enterprise.inventory = {g: 0.0 for g in Good}
        enterprise.equipment = {}
        enterprise.land = 0.0
        # 债务注销：银行确认坏账，企业不再挂债。
        loan = self.bank.loans.pop(enterprise.id, 0.0)
        self.bank.write_offs += loan
        enterprise.debt = 0.0

    def _exit_service_firm(self, enterprise: Enterprise) -> None:
        """自雇服务摊退出：摊主回到失业池，资产回收到资产池。

        服务摊没有资本品，但设备/库存仍按“不能凭空消失”的规则处理。
        """
        enterprise.active = False
        for worker_id in list(enterprise.workers):
            worker = self.workers.get(worker_id)
            if worker is not None:
                worker.employer_id = None
                worker.wage = 0.0
                worker.is_owner_operator = False
        enterprise.workers.clear()
        owner = self.workers.get(enterprise.owner_id)
        if enterprise.cash > 0:
            if owner is not None and owner.alive:
                owner.cash += enterprise.cash
            else:
                self.bank.cash += enterprise.cash
            enterprise.cash = 0.0
        for good, qty in enterprise.inventory.items():
            if qty > 0:
                self.asset_pool.inventory[good] += qty
        for key, count in enterprise.equipment.items():
            if count > 0:
                self.asset_pool.equipment[key] = (
                    self.asset_pool.equipment.get(key, 0) + count
                )
        enterprise.inventory = {g: 0.0 for g in Good}
        enterprise.equipment = {}
        enterprise.service_idle_months = 0

    def _cleanup_dormant(self) -> None:
        """清理无设备、无工人、无库存的壳企业，释放 max_firms 槽位。"""
        for enterprise in self.enterprises.values():
            if not enterprise.active:
                continue
            # 长期卖不出去的自雇服务摊主动退出，避免把失业者
            # 伪装成“就业”。设备与库存进入资产池。
            if (
                enterprise.industry == Industry.SERVICE
                and enterprise.is_household
                and enterprise.service_idle_months >= SERVICE_IDLE_EXIT_MONTHS
            ):
                self._exit_service_firm(enterprise)
                continue
            has_assets = (
                bool(enterprise.equipment)
                or bool(enterprise.workers)
                or enterprise.land > 0
                or any(qty > 1e-9 for qty in enterprise.inventory.values())
            )
            if has_assets:
                enterprise.dormant_months = 0
                continue
            enterprise.dormant_months += 1
            if enterprise.dormant_months < 6:
                continue
            if enterprise.cash > 0:
                owner = self.capitalists.get(enterprise.owner_id)
                if owner is not None:
                    owner.cash += enterprise.cash
                else:
                    self.bank.cash += enterprise.cash
                enterprise.cash = 0.0
            enterprise.active = False

    def _choose_heir(self, worker: Worker) -> Optional[Worker]:
        """为死亡自耕农选家庭农场继承人/承接人。

        优先成年子女（未退休、尚未拥有农场/自营摊位，年长者优先）；
        没有子女时，把土地分配给无地成年劳动者（边疆/土改简化），
        避免土地沉入 estate_land 后永久退出生产。两者都没有才回市场。
        """
        candidates = []
        for child_id in worker.children_ids:
            child = self.workers.get(child_id)
            if child is None or not child.alive:
                continue
            if child.is_child or child.retired or child.is_owner_operator:
                continue
            if child.id in self.land.enterprise_by_owner:
                continue
            candidates.append(child)
        if candidates:
            candidates.sort(key=lambda child: (-child.age_months, child.id))
            return candidates[0]

        landless = [
            other
            for other in self.workers.values()
            if other.alive
            and not other.is_child
            and not other.retired
            and not other.is_owner_operator
            and other.land_owned <= 1e-9
            and other.id not in self.land.enterprise_by_owner
        ]
        if not landless:
            return None
        # 优先现金最少（最需要生计）的劳动者，其次年长者。
        landless.sort(key=lambda other: (other.cash, -other.age_months, other.id))
        return landless[0]

    def _transfer_household_farm(
        self,
        enterprise: Enterprise,
        deceased: Worker,
        heir: Worker,
        land_mu: float,
        enterprise_id: str,
    ) -> None:
        """把死亡自耕农的家庭农场转给成年子女，避免土地沉入 estate_land。"""
        # 继承人可能原本受雇于其他企业或就业保障；先退出原岗位。
        previous = self.enterprises.get(heir.employer_id or "")
        if previous is not None and heir.id in previous.workers:
            previous.workers.remove(heir.id)
        if self.government is not None and heir.id in self.government.jg_workers:
            self.government.jg_workers.remove(heir.id)

        if deceased.id in enterprise.workers:
            enterprise.workers.remove(deceased.id)
        if heir.id not in enterprise.workers:
            enterprise.workers.append(heir.id)
        enterprise.owner_id = heir.id
        self.land.enterprise_by_owner[heir.id] = enterprise_id
        own_mu = max(land_mu, enterprise.land)
        if own_mu > 0:
            self.land.owners[heir.id] = own_mu
        heir.employer_id = enterprise_id
        heir.is_owner_operator = True
        heir.industry = enterprise.industry
        heir.land_owned = own_mu
        # 继承人同样只是剩余索取者，不领工资。
        heir.wage = 0.0
        heir.hours = 16

    def _settle_estate(
        self, worker: Worker, heir: Optional[Worker] = None
    ) -> None:
        """死亡自耕农的遗产清算。

        优先把家庭农场转给成年子女（继承）；没有继承人时土地回市场，
        家庭农场停业。死亡只把现金转银行是不够的；如果不清理
        land.owners 和家庭农场，死者会继续“持有”土地并占据雇工/信贷资源。
        """
        ent_id = self.land.enterprise_by_owner.pop(worker.id, None)
        mu = self.land.owners.pop(worker.id, 0.0)
        farm_land = 0.0
        if ent_id:
            enterprise = self.enterprises.get(ent_id)
            if enterprise and enterprise.active:
                farm_land = enterprise.land
                if heir is not None and farm_land > 0:
                    self._transfer_household_farm(
                        enterprise, worker, heir, mu, ent_id
                    )
                    self.bank.deposits.pop(worker.id, 0.0)
                    worker.land_owned = 0.0
                    worker.is_owner_operator = False
                    return
                for worker_id in list(enterprise.workers):
                    other = self.workers.get(worker_id)
                    if other and other.alive:
                        other.employer_id = None
                        other.wage = 0.0
                enterprise.workers.clear()
                if enterprise.cash > 0:
                    self.bank.cash += enterprise.cash
                    enterprise.cash = 0.0
                for good, qty in enterprise.inventory.items():
                    if qty > 0:
                        self.asset_pool.inventory[good] += qty
                for key, count in enterprise.equipment.items():
                    if count > 0:
                        self.asset_pool.equipment[key] = (
                            self.asset_pool.equipment.get(key, 0) + count
                        )
                if enterprise.land > 0:
                    self.land.estate_land += enterprise.land
                enterprise.inventory = {g: 0.0 for g in Good}
                enterprise.equipment = {}
                enterprise.land = 0.0
                enterprise.active = False
        # 家庭农场的 enterprise.land 是 land.owners 的会计镜像：上面已把
        # enterprise.land 计入 estate_land，这里只补多出来的部分，避免土地
        # 在死亡清算时被重复计算。
        if mu > farm_land + 1e-9:
            self.land.estate_land += mu - farm_land
        # 死亡储户的存款留在银行；从存款台账移除，避免利息记到死者。
        self.bank.deposits.pop(worker.id, 0.0)
        worker.land_owned = 0.0
        worker.is_owner_operator = False

    # ------------------------------------------------------------------
    # 消费 / 人口
    # ------------------------------------------------------------------
    def _collect_food_relief_levy(self) -> None:
        """粮食救济实物税：库存低于 3 个月需求时，从当月农业产出征收。

        这是实物转移（不是货币创造）：用于维持粮食平准库存的救济能力。
        库存充足（>= 3 个月需求）时不征收；税率最高 25%，缺口越大越高。
        """
        monthly_need = max(1.0, self.feeding_units() * FOOD_PER_WORKER)
        target = 3.0 * monthly_need
        reserve = self.food_reserve
        if reserve.food >= target:
            return
        # 缺口越大，税率越高（0–25%）。这是实物税，用于维持救济库存。
        rate = min(0.25, 0.25 * (target - reserve.food) / target)
        if rate <= 1e-9:
            return
        levied = 0.0
        for enterprise in self.active_enterprises(Industry.AGRICULTURE):
            available = enterprise.inv(Good.FOOD)
            if available <= 1e-9:
                continue
            take = min(available, enterprise.last_output * rate)
            if take <= 1e-9:
                continue
            enterprise.inventory[Good.FOOD] = available - take
            reserve.food += take
            levied += take
        self._food_levy_this_month = levied

    def _distribute_food_relief(self) -> None:
        """粮食库存紧急救济。

        市场上食物有库存、但部分家庭买不到（现金约束、供给/撮合）时，
        从粮食平准库存直接转移实物。纯实物转移，不改变现金总量；库存
        耗尽后饥饿死亡机制仍会生效。每月最多释放库存的 25%（至少 10
        吨），优先救助饥饿月份最多、现金最少的存活人口。粮商在高价
        出售时必须保留 `FOOD_RELIEF_BUFFER_MONTHS` 个月口粮，否则这里
        会无粮可发（V0.5 修复的饥荒回归）。
        """
        reserve = self.food_reserve
        if reserve.food <= 1e-9:
            return
        demo = self.demographics
        cap = min(reserve.food, max(10.0, 0.25 * reserve.food))
        candidates = []
        for worker in self.workers.values():
            if not worker.alive:
                continue
            target = demo.child_food if worker.is_child else FOOD_PER_WORKER
            if worker.hunger_months >= 1 and worker.food + 1e-9 < target:
                candidates.append((worker.hunger_months, worker.cash, worker.id))
        if not candidates:
            return
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        relieved = 0.0
        unmet = 0.0
        for _, _, worker_id in candidates:
            worker = self.workers[worker_id]
            target = demo.child_food if worker.is_child else FOOD_PER_WORKER
            need = max(0.0, target - worker.food)
            if need <= 1e-9:
                continue
            if cap <= 1e-9:
                unmet += need
                continue
            take = min(need, cap)
            worker.food += take
            reserve.food -= take
            cap -= take
            relieved += take
        self._food_relief_this_month = relieved
        self._food_relief_shortfall = unmet

    def _consume_and_demographics(self) -> None:
        demo = self.demographics
        for worker in self.workers.values():
            if not worker.alive:
                continue
            if worker.is_child:
                food_target = demo.child_food
                cloth_target = demo.child_cloth
                housing_target = demo.child_housing
                service_target = 0.0
                hunger_target = demo.child_food
            else:
                comfort = worker.living_standard in ("comfort", "leisure")
                mult = COMFORT_MULTIPLIER if comfort else 1.0
                food_target = FOOD_PER_WORKER * mult
                cloth_target = CLOTH_PER_WORKER * mult
                housing_target = HOUSING_PER_WORKER * mult
                service_target = SERVICE_PER_HOUSEHOLD * mult
                hunger_target = FOOD_PER_WORKER

            worker.consumed_food = min(worker.food, food_target)
            worker.food -= worker.consumed_food
            worker.consumed_cloth = min(worker.cloth, cloth_target)
            worker.cloth -= worker.consumed_cloth
            worker.consumed_housing = min(worker.housing, housing_target)
            worker.housing -= worker.consumed_housing
            worker.consumed_service = min(worker.service, service_target)
            worker.service -= worker.consumed_service

            # 90% 容差：轻微不足（价格/撮合造成的 1–3% 缺口）不应被当作
            # 连续饥荒累计；真正低于九成口粮才进入饥饿死亡路径。
            if worker.consumed_food + 1e-9 < 0.90 * hunger_target:
                worker.hunger_months += 1
            else:
                worker.hunger_months = 0

            if worker.hunger_months >= 3:
                chance = min(
                    0.50,
                    0.08 + 0.08 * (worker.hunger_months - 3),
                )
                if self.rng.random() < chance:
                    self._kill_worker(worker, cause="hunger")
                    continue

            if worker.is_child:
                # 儿童保留独立类别，避免把成人温饱线套到半个篮子上。
                worker.living_standard = "child"
                continue

            comfort_food = FOOD_PER_WORKER * COMFORT_MULTIPLIER
            comfort_cloth = CLOTH_PER_WORKER * COMFORT_MULTIPLIER
            comfort_housing = HOUSING_PER_WORKER * COMFORT_MULTIPLIER
            if worker.consumed_food + 1e-9 < FOOD_PER_WORKER:
                worker.living_standard = "survival"
            elif (
                worker.consumed_cloth + 1e-9 < CLOTH_PER_WORKER
                or worker.consumed_housing + 1e-9 < HOUSING_PER_WORKER
            ):
                worker.living_standard = "subsistence"
            elif (
                worker.consumed_food + 1e-9 >= comfort_food
                and worker.consumed_cloth + 1e-9 >= comfort_cloth
                and worker.consumed_housing + 1e-9 >= comfort_housing
                and worker.cash >= COMFORT_SAVINGS
            ):
                # 小康/悠闲按 PRD：三项达到温饱线 1.5 倍且有积蓄。
                if worker.hours <= 8 and worker.cash >= LEISURE_SAVINGS:
                    worker.living_standard = "leisure"
                else:
                    worker.living_standard = "comfort"
            else:
                worker.living_standard = "subsistence"

        for capitalist in self.capitalists.values():
            capitalist.consumed_food = min(capitalist.food, CAPITALIST_FOOD)
            capitalist.food -= capitalist.consumed_food
            capitalist.consumed_cloth = min(capitalist.cloth, CAPITALIST_CLOTH)
            capitalist.cloth -= capitalist.consumed_cloth
            capitalist.consumed_housing = min(capitalist.housing, CAPITALIST_HOUSING)
            capitalist.housing -= capitalist.consumed_housing
            capitalist.consumed_service = min(
                capitalist.service, CAPITALIST_SERVICE
            )
            capitalist.service -= capitalist.consumed_service

    # ------------------------------------------------------------------
    # 统计指标
    # ------------------------------------------------------------------
    def _record_stats(self) -> dict:
        prices = self.market.reference_prices
        alive_workers = [w for w in self.workers.values() if w.alive]
        # 劳动年龄人口 = 非儿童、非退休；失业率分母只包含这部分。
        labor_force = [w for w in alive_workers if w.is_working_age]
        employed = [w for w in labor_force if w.employed]
        unemployed = len(labor_force) - len(employed)
        children_count = sum(1 for w in alive_workers if w.is_child)
        retiree_count = sum(1 for w in alive_workers if w.retired)

        ag_workers = [
            w
            for w in employed
            if w.industry == Industry.AGRICULTURE
        ]
        food_output = self.production_month.get(Good.FOOD, 0.0)
        ag_productivity = food_output / max(len(ag_workers), 1)

        active_enterprises = list(self.active_enterprises())
        total_capital = 0.0
        total_profit = 0.0
        total_revenue = 0.0
        total_input_costs = 0.0
        total_wages = 0.0
        total_interest = 0.0
        total_depreciation = 0.0
        capitalist_capital = 0.0
        capitalist_profit = 0.0
        household_capital = 0.0
        household_profit = 0.0
        household_operating_income = 0.0
        for enterprise in active_enterprises:
            enterprise_capital = (
                capital_value(enterprise, prices, self.land.price)
                + inventory_value(enterprise, prices)
            )
            total_capital += enterprise_capital
            total_profit += enterprise.last_profit
            total_revenue += enterprise.last_revenue
            total_input_costs += enterprise.last_costs
            total_wages += enterprise.last_wages
            total_interest += enterprise.last_interest
            total_depreciation += (
                equipment_value(enterprise, prices) / DEPRECIATION_MONTHS
            )
            if enterprise.is_household:
                household_capital += enterprise_capital
                household_profit += enterprise.last_profit
                household_operating_income += enterprise.last_operating_payout
            else:
                capitalist_capital += enterprise_capital
                capitalist_profit += enterprise.last_profit
        # “全社会利润率”只统计资本主义企业（非 household）：
        # 家庭农场/服务自雇的所有者劳动收入不是资本回报，混入会系统性压低利润率。
        # 家庭企业的 last_profit 已扣除经营所得 payout，因此 household_profit
        # 是剩余会计利润；所有者劳动收入在 household_operating_income 单列。
        profit_rate = (
            capitalist_profit / capitalist_capital
            if capitalist_capital > 0
            else 0.0
        )
        all_profit_rate = total_profit / total_capital if total_capital > 0 else 0.0
        aggregate_inventory = {
            good.value: sum(
                enterprise.inv(good) for enterprise in active_enterprises
            )
            for good in Good
        }

        firms_by_industry = {
            ind.value: len(self.active_enterprises(ind)) for ind in Industry
        }
        workers_by_industry = {ind.value: 0 for ind in Industry}
        for worker in labor_force:
            if worker.industry in workers_by_industry:
                workers_by_industry[worker.industry.value] += 1

        living = {
            "survival": 0,
            "subsistence": 0,
            "comfort": 0,
            "leisure": 0,
            "child": 0,
        }
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
        fiat = self.government is not None and self.government.fiat_money
        if (
            not fiat
            and self.money_initial > 0
            and abs(money_total - self.money_initial) > 0.01
        ):
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
            streak = self._zero_output_streak[good.value]
            # 连续第 3 个月提醒一次，之后每 12 个月再提醒；
            # 不能只在恰好第 3 个月提醒，否则长期停摆会被静默忽略。
            if streak == 3 or (streak > 3 and streak % 12 == 0):
                self._warnings.append(
                    f"{GOOD_LABELS[good]} 连续 {streak} 个月产量为 0"
                )

        # --- 人口结构统计 ---
        ages_months = sorted(worker.age_months for worker in alive_workers)
        population = len(ages_months)
        if population:
            average_age = sum(ages_months) / population / 12.0
            middle = population // 2
            if population % 2:
                median_age = ages_months[middle] / 12.0
            else:
                median_age = (
                    ages_months[middle - 1] + ages_months[middle]
                ) / 2.0 / 12.0
        else:
            average_age = 0.0
            median_age = 0.0
        age_histogram = {
            f"{start}-{start + 4}" if start < 85 else "85+": 0
            for start in range(0, 90, 5)
        }
        for age_months in ages_months:
            bucket = age_months // 60
            if bucket >= 17:
                age_histogram["85+"] += 1
            else:
                age_histogram[f"{bucket * 5}-{bucket * 5 + 4}"] += 1
        orphans = sum(
            1
            for worker in alive_workers
            if worker.is_child and worker.parent_id is None
        )
        if self._orphaned_this_month > 0:
            self._warnings.append(
                f"本月 {self._orphaned_this_month} 名儿童因家长死亡成为孤儿；"
                "allowance 归零（不凭空创造兜底资金）"
            )
        if self._pension_shortfall > 1e-6:
            self._warnings.append(
                f"养老金基金缺口 {self._pension_shortfall:.2f}，已按比例发放"
            )
        if self._food_relief_shortfall > 1e-6:
            self._warnings.append(
                f"粮食救济库存不足，缺口 {self._food_relief_shortfall:.2f} 吨"
            )

        projects_by_industry = {ind.value: 0 for ind in Industry}
        for project in self.projects.values():
            if project.active:
                projects_by_industry[project.industry.value] += 1
        gdp = (
            self.market.consumption_spending
            + self.market.investment_spending
            + self.market.government_spending
        )
        government = self.government
        stat = {
            "tick": self.tick,
            # alive 保持历史语义 = 总人口；population 是同一口径的显式别名。
            "alive": population,
            "population": population,
            "children": children_count,
            "working_age": len(labor_force),
            "retirees": retiree_count,
            "labor_force": len(labor_force),
            "employed": len(employed),
            "unemployed": unemployed,
            "births": self.births_this_month,
            "deaths": self.dead_this_month,
            "age_deaths": self._age_deaths_this_month,
            "hunger_deaths": self._hunger_deaths_this_month,
            "birth_rate": self.births_this_month / max(population, 1),
            "death_rate": self.dead_this_month / max(population, 1),
            "birth_rate_annual": (
                12.0 * self.births_this_month / max(population, 1)
            ),
            "death_rate_annual": (
                12.0 * self.dead_this_month / max(population, 1)
            ),
            # 总抚养比 = (儿童 + 退休者) / 劳动年龄人口；老年/儿童抚养比
            # 使用同一分母，避免“总抚养比”只含退休者、且分母与老年比不一致。
            "dependency_ratio": (
                children_count + retiree_count
            ) / max(len(labor_force), 1),
            "old_age_dependency": retiree_count / max(len(labor_force), 1),
            "child_dependency": children_count / max(len(labor_force), 1),
            "age_histogram": age_histogram,
            "average_age": average_age,
            "median_age": median_age,
            "orphans": orphans,
            "dead_this_month": self.dead_this_month,
            "active_enterprises": len(self.active_enterprises()),
            "money_total": money_total,
            "bank_cash": self.bank.cash,
            "bank_frozen_cash": self.bank.frozen_cash,
            "bank_loans": sum(self.bank.loans.values()),
            "bank_write_offs": self.bank.write_offs,
            "bank_deposits": sum(self.bank.deposits.values()),
            "government_cash": government.cash if government else 0.0,
            "government_debt": government.debt if government else 0.0,
            "government_tax_revenue": (
                government.tax_revenue if government else 0.0
            ),
            "government_transfers": government.transfers if government else 0.0,
            "government_spending": government.spending if government else 0.0,
            "government_interest_paid": (
                government.interest_paid if government else 0.0
            ),
            "government_market_spending": self.market.government_spending,
            "government_deficit": government.deficit if government else 0.0,
            "government_jg_workers": (
                len(government.jg_workers) if government else 0
            ),
            "pension_contributions": (
                government.pension_contributions if government else 0.0
            ),
            "pension_subsidy": (
                government.pension_subsidy if government else 0.0
            ),
            "pension_revenue": (
                government.pension_revenue if government else 0.0
            ),
            "pension_spending": (
                government.pension_spending if government else 0.0
            ),
            "pension_balance": (
                government.pension_balance if government else 0.0
            ),
            "pension_fund": (
                government.pension_fund if government else 0.0
            ),
            "pension_recipients": sum(
                1 for worker in alive_workers if worker.pension_income > 0
            ),
            # 养老金基金是政府现金中的专项台账；若其他支出动用了这笔
            # 现金，台账超过现金的部分视为对政府的隐性债权/未备付，
            # 不重复计入货币总量。发放时仍按可用现金比例折算。
            "pension_fund_unfunded": (
                max(0.0, government.pension_fund - government.cash)
                if government
                else 0.0
            ),
            "central_bank_money": (
                government.central_bank_money if government else 0.0
            ),
            "policy_regime": government.regime.value if government else "classical",
            "money_regime": government.money_regime.value if government else "gold",
            "price_regime": self.price_regime,
            "average_markup": (
                sum(e.markup for e in active_enterprises)
                / max(1, len(active_enterprises))
            ),
            "revenue": total_revenue,
            "input_costs": total_input_costs,
            "wages": total_wages,
            "interest": total_interest,
            "depreciation": total_depreciation,
            "profit": total_profit,
            "inventory": aggregate_inventory,
            "price_floors": {
                good.value: self.market.floors.get(good, 0.0) for good in Good
            },
            "price_ceilings": {
                good.value: self.market.ceilings.get(good, 0.0) for good in Good
            },
            "estate_land": self.land.estate_land,
            "food_reserve": self.food_reserve.food,
            "food_reserve_cash": self.food_reserve.cash,
            "food_relief": self._food_relief_this_month,
            "food_relief_unmet": self._food_relief_shortfall,
            "food_levy": self._food_levy_this_month,
            "asset_pool_inventory_value": sum(
                qty * prices.get(good, 0.0)
                for good, qty in self.asset_pool.inventory.items()
            ),
            "asset_pool_equipment_units": sum(self.asset_pool.equipment.values()),
            "zero_output_streak": {
                good.value: self._zero_output_streak[good.value] for good in Good
            },
            "active_projects": projects_by_industry,
            "gdp": gdp,
            "consumption": self.market.consumption_spending,
            "investment": self.market.investment_spending,
            "unemployment_rate": unemployed / max(len(labor_force), 1),
            "profit_rate": profit_rate,
            "all_profit_rate": all_profit_rate,
            "capital_stock": total_capital,
            "capitalist_capital_stock": capitalist_capital,
            "capitalist_profit": capitalist_profit,
            "household_capital": household_capital,
            "household_profit": household_profit,
            "household_operating_income": household_operating_income,
            "household_farm_liquidations": (
                self._household_farm_liquidations_this_month
            ),
            "household_farm_liquidations_total": (
                self.household_farm_liquidations_total
            ),
            "ag_productivity": ag_productivity,
            "food_output": food_output,
            "prices": {g.value: prices[g] for g in Good},
            "production": {g.value: self.production_month.get(g, 0.0) for g in Good},
            "output_index": sum(
                self.production_month.get(good, 0.0) * INITIAL_PRICES[good]
                for good in Good
            ),
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
