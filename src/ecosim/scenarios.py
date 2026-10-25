from __future__ import annotations

import math
from dataclasses import dataclass

from .config import (
    FOOD_PER_WORKER,
    INITIAL_PRICES,
    SECTOR_PARAMS,
    TOTAL_LAND_MU,
    WAGE_BASE,
    DemographicsConfig,
)
from .enums import Good, Industry
from .engine import Engine
from .government import Government, MoneyRegime, PolicyRegime
from .models import FoodReserve
from .production import equipment_summary


@dataclass(frozen=True)
class ScenarioConfig:
    """历史阶段/政策制度的可开关配置。

    同一套经济内核可以通过这些开关组合出 pre-Keynesian、Keynesian 和 MMT
    剧本，而不是把某一种制度硬编码进引擎。
    """

    name: str = "第一次工业革命"
    policy_regime: PolicyRegime = PolicyRegime.CLASSICAL
    money_regime: MoneyRegime = MoneyRegime.GOLD
    price_regime: str = "band"
    # V0.6：默认使用收入依赖的 Stone-Geary 需求；"fixed"/"les" 保留为
    # 历史对照实验。
    demand_regime: str = "geary"
    bank_intermediation: bool = False
    tax_rate_wage: float = 0.0
    tax_rate_profit: float = 0.0
    ui_replacement: float = 0.0
    ui_duration: int = 0
    public_investment_rate: float = 0.0
    public_investment_countercyclical: float = 0.0
    job_guarantee: bool = False
    jg_wage: float = 0.0
    jg_max_workers: int = 0
    government_cash: float = 0.0

    # --- V0.6 工资—生产率 / 工时制度 ---
    # 制度性标准工时：16（古典/维多利亚）或 8（Fordist/Keynesian/MMT/晚期）。
    # 有效劳动 = 实际工时 / 标准工时；产能以标准全职工人为口径。
    work_hours: int = 16
    # 工资目标 w* = WAGE_BASE × A^β × (1+π^e)^α × (1+tightness+institutional)
    # β：生产率分享程度。古典/维多利亚压低（Engels 停顿）；Fordist/MMT 接近 1。
    wage_productivity_share: float = 0.50
    # 实际工资报价向目标调整的月度速度（0.10–0.30）；向下的调整会再乘
    # WAGE_DOWNWARD_SPEED_MULT（0.10×3=0.30），避免高失业时工资下降过慢。
    wage_adjustment_speed: float = 0.10
    # 月度通胀预期初始值；之后按 CPI 观察值缓慢适应。金本位可设 0。
    inflation_expectation: float = 0.0
    # 通胀补偿程度 α：古典/维多利亚合同很少指数化，α 低；Fordist/MMT
    # 的工资合同更接近完全补偿，α 高。它决定 π^e 向工资的传导强度。
    wage_inflation_pass_through: float = 0.25
    # 制度/阶级议价力量：放大真实工资追赶与生活成本危机压力。
    # 古典/维多利亚低，Fordist/MMT 高。
    wage_bargain_power: float = 0.10

    # --- V0.5 人口 / 代际 / 退休金 ---
    working_age_years: int = 14
    retirement_age_years: int = 0          # 0 = 不退休
    fertility_monthly: float = 0.012
    fertility_multiplier: float = 1.0
    # 仅用于初始年龄权重/文档；实际死亡由下面的 Gompertz 参数决定。
    life_expectancy_years: float = 50.0
    mortality_A: float = 0.0015
    mortality_B: float = 0.0001
    mortality_C: float = 0.085
    infant_mortality_annual: float = 0.18
    child_mortality_annual: float = 0.02
    initial_age_min_years: int = 18
    initial_age_max_years: int = 60
    initial_female_share: float = 0.5
    # 初始儿童/退休者数量（默认 0，保持旧测试的 1100 初始劳动力口径）。
    initial_children: int = 0
    initial_retirees: int = 0
    child_food: float = 0.05
    child_cloth: float = 0.5
    child_housing: float = 0.1
    pension_tax_rate: float = 0.0
    pension_replacement: float = 0.0
    pension_fund_initial: float = 0.0

    def demographics(self) -> DemographicsConfig:
        return DemographicsConfig(
            working_age_months=self.working_age_years * 12,
            retirement_age_months=self.retirement_age_years * 12,
            fertility_monthly=self.fertility_monthly,
            fertility_multiplier=self.fertility_multiplier,
            mortality_A=self.mortality_A,
            mortality_B=self.mortality_B,
            mortality_C=self.mortality_C,
            infant_mortality_annual=self.infant_mortality_annual,
            child_mortality_annual=self.child_mortality_annual,
            initial_age_min_months=self.initial_age_min_years * 12,
            initial_age_max_months=self.initial_age_max_years * 12,
            initial_female_share=self.initial_female_share,
            child_food=self.child_food,
            child_cloth=self.child_cloth,
            child_housing=self.child_housing,
            pension_tax_rate=self.pension_tax_rate,
            pension_replacement=self.pension_replacement,
            pension_fund_initial=self.pension_fund_initial,
        )


CLASSICAL_LAISSEZ_FAIRE = ScenarioConfig(
    name="古典自由放任（pre-Keynesian）",
    policy_regime=PolicyRegime.CLASSICAL,
    money_regime=MoneyRegime.GOLD,
    work_hours=16,
    # 维多利亚/早期工业：工资只分享一小部分生产率收益，议价力量弱；
    # 金本位下通胀预期为 0。
    wage_productivity_share=0.50,
    wage_adjustment_speed=0.10,
    inflation_expectation=0.0,
    wage_inflation_pass_through=0.25,
    wage_bargain_power=0.10,
    working_age_years=14,
    retirement_age_years=0,
    # 名义 TFR 目标 5–6；食物/收入/parity 乘数会把有效生育率压到
    # 可持续区间（~1200–1600 人），避免超过 6000 亩地的粮食上限。
    fertility_monthly=0.012,
    life_expectancy_years=50.0,
    mortality_A=0.0015,
    mortality_B=0.0001,
    mortality_C=0.085,
    infant_mortality_annual=0.18,
    child_mortality_annual=0.02,
    initial_children=300,
    initial_retirees=0,
)

KEYNESIAN_WELFARE = ScenarioConfig(
    name="凯恩斯福利国家",
    policy_regime=PolicyRegime.KEYNESIAN,
    money_regime=MoneyRegime.GOLD,
    bank_intermediation=True,
    # Fordist 妥协：8 小时标准工时；工资基本跟随生产率，工会议价较高；
    # 金本位下通胀预期仍设为 0。
    work_hours=8,
    wage_productivity_share=1.00,
    wage_adjustment_speed=0.25,
    inflation_expectation=0.0,
    wage_inflation_pass_through=0.75,
    wage_bargain_power=0.55,
    tax_rate_wage=0.08,
    tax_rate_profit=0.08,
    ui_replacement=0.50,
    ui_duration=12,
    public_investment_rate=0.15,
    public_investment_countercyclical=0.08,
    government_cash=10_000.0,
    working_age_years=16,
    retirement_age_years=65,
    fertility_monthly=0.0105,
    life_expectancy_years=80.0,
    mortality_A=0.0003,
    mortality_B=0.000045,
    mortality_C=0.09,
    infant_mortality_annual=0.005,
    child_mortality_annual=0.0005,
    initial_children=200,
    initial_retirees=50,
    pension_tax_rate=0.10,
    pension_replacement=0.45,
)

# L2 可选预设：古典制度 + 成本加成目标价 + 参考价软走廊。
# 其他政策制度可用 dataclasses.replace(config, price_regime="markup_soft")
# 叠加，不需要为每个制度单独复制一份配置。
MARKUP_SOFT = ScenarioConfig(
    name="古典自由放任 + 软成本加成定价（实验）",
    policy_regime=PolicyRegime.CLASSICAL,
    money_regime=MoneyRegime.GOLD,
    price_regime="markup_soft",
)

MMT_SOVEREIGN = ScenarioConfig(
    name="MMT 主权货币 + 就业保障",
    policy_regime=PolicyRegime.MMT,
    money_regime=MoneyRegime.CREDIT,
    bank_intermediation=True,
    # 主权信用货币可以维持温和通胀预期；8 小时工时 + 高议价力量。
    work_hours=8,
    wage_productivity_share=1.00,
    wage_adjustment_speed=0.30,
    inflation_expectation=0.0015,
    wage_inflation_pass_through=1.00,
    wage_bargain_power=0.65,
    tax_rate_wage=0.08,
    tax_rate_profit=0.08,
    ui_replacement=0.45,
    ui_duration=12,
    public_investment_rate=0.08,
    public_investment_countercyclical=0.04,
    job_guarantee=True,
    jg_wage=30.0,
    jg_max_workers=0,
    government_cash=0.0,
    working_age_years=16,
    retirement_age_years=65,
    fertility_monthly=0.0082,
    life_expectancy_years=80.0,
    mortality_A=0.00028,
    mortality_B=0.000042,
    mortality_C=0.09,
    infant_mortality_annual=0.0045,
    child_mortality_annual=0.0004,
    initial_children=200,
    initial_retirees=50,
    pension_tax_rate=0.12,
    pension_replacement=0.50,
)

# 晚期资本主义：低生育、长寿、老龄化、较高养老金缴费/替代率。
# 仍是金本位 + 福利国家财政，因此货币守恒测试同样适用。
LATE_CAPITALISM = ScenarioConfig(
    name="晚期资本主义（低生育/长寿/老龄化）",
    policy_regime=PolicyRegime.KEYNESIAN,
    money_regime=MoneyRegime.GOLD,
    bank_intermediation=True,
    # 晚期 Fordist：8 小时工时，生产率分享较高但低于黄金时代，
    # 老龄化/财政压力下议价力量略低。
    work_hours=8,
    wage_productivity_share=0.90,
    wage_adjustment_speed=0.20,
    inflation_expectation=0.0005,
    wage_inflation_pass_through=0.75,
    wage_bargain_power=0.45,
    tax_rate_wage=0.10,
    tax_rate_profit=0.10,
    ui_replacement=0.40,
    ui_duration=18,
    public_investment_rate=0.12,
    public_investment_countercyclical=0.06,
    government_cash=20_000.0,
    working_age_years=18,
    retirement_age_years=67,
    fertility_monthly=0.0055,
    life_expectancy_years=85.0,
    mortality_A=0.00018,
    mortality_B=0.00003,
    mortality_C=0.095,
    infant_mortality_annual=0.002,
    child_mortality_annual=0.0002,
    initial_age_min_years=20,
    initial_age_max_years=70,
    initial_children=150,
    initial_retirees=100,
    child_food=0.04,
    child_cloth=0.4,
    child_housing=0.08,
    pension_tax_rate=0.16,
    pension_replacement=0.55,
)


def build_scenario_1(
    engine: Engine, config: ScenarioConfig = CLASSICAL_LAISSEZ_FAIRE
) -> Engine:
    """第一次工业革命 / 农业国工业化场景。

    总量目标遵循 PRD 场景 1：600 名自耕农、500 名工业工人、100 名资产阶级、
    粮食紧平衡、农业初始未机械化。设备目录经过校准，使初始工业产出
    接近 PRD 的叙事总量。
    """
    engine.demographics = config.demographics()
    demo = engine.demographics
    # V0.6 制度/工资参数必须在创建工人之前写入：create_worker 会据此
    # 设置 standard_hours 和初始工时。
    engine.work_hours = max(1, int(config.work_hours))
    engine.wage_productivity_share = config.wage_productivity_share
    engine.wage_adjustment_speed = config.wage_adjustment_speed
    engine.wage_bargain_power = config.wage_bargain_power
    engine.wage_inflation_pass_through = config.wage_inflation_pass_through
    engine.inflation_expectations = config.inflation_expectation

    def sample_initial_age() -> int:
        """按近似稳定人口年龄分布抽取初始年龄（不是全 0/全同龄）。

        权重 exp(-age / (0.8 * life_expectancy))：高寿命剧本年龄更老。
        """
        min_year = demo.initial_age_min_months // 12
        max_year = demo.initial_age_max_months // 12
        # 初始劳动人口不应在退休年龄以上：LATE_CAPITALISM 的
        # initial_age_max_years=70、退休 67，若不封顶会创建 66 名
        # “已到退休年龄但仍占企业岗位”的工人，首月才退休。
        if demo.retirement_age_months > 0:
            max_year = min(
                max_year, demo.retirement_age_months // 12 - 1
            )
        years = list(range(min_year, max_year + 1))
        scale = max(5.0, 0.8 * config.life_expectancy_years)
        weights = [math.exp(-year / scale) for year in years]
        year = engine.demographic_rng.choices(years, weights=weights, k=1)[0]
        return year * 12 + engine.demographic_rng.randint(0, 11)

    def seed_worker(
        industry: Industry,
        skill: float,
        cash: float,
        food: float,
    ):
        """初始劳动力：18–60 岁（剧本可调）、性别约 50/50。"""
        age = sample_initial_age()
        sex = (
            "F"
            if engine.demographic_rng.random() < demo.initial_female_share
            else "M"
        )
        return engine.create_worker(
            industry=industry,
            skill=skill,
            cash=cash,
            food=food,
            age_months=age,
            sex=sex,
            is_child=False,
            birth_tick=-age,
        )

    # --- 资产阶级 -------------------------------------------------
    for i in range(50):
        engine.capitalists[f"C_{i}"] = _capitalist(f"C_{i}", 100_000.0, "director")
    for i in range(50, 100):
        engine.capitalists[f"C_{i}"] = _capitalist(f"C_{i}", 10_000.0, "manager")

    owner_ids = [c.id for c in engine.capitalists.values()]
    owner_cursor = 0

    # --- 自耕农农业 ------------------------------------------------
    for _ in range(600):
        worker = seed_worker(
            industry=Industry.AGRICULTURE,
            skill=2.0,
            cash=20.0,
            food=0.0,
        )
        enterprise = engine.create_enterprise(
            industry=Industry.AGRICULTURE,
            owner_id=worker.id,
            cash=100.0,
            land=10.0,
            is_household=True,
            modernization_capable=False,
        )
        worker.employer_id = enterprise.id
        # 自耕农所有者是剩余索取者，不是雇员：工资保持 0，
        # 经营所得由 `_finance` 的 payout 发放。
        worker.wage = 0.0
        worker.is_owner_operator = True
        worker.land_owned = 10.0
        enterprise.workers.append(worker.id)
        # 自耕农：10 亩 × 0.01 吨/亩 × 熟练度 2 = 0.2 吨/月。
        enterprise.demand_forecast = 0.2
        enterprise.target_inventory_months = 6.0
        engine.land.owners[worker.id] = 10.0
        engine.land.enterprise_by_owner[worker.id] = enterprise.id

    # --- 工业企业 --------------------------------------------------
    def add_industry(
        industry: Industry,
        enterprise_count: int,
        workers_per_enterprise: int,
        equipment: dict[str, int],
        extra_workers: int = 0,
    ) -> None:
        nonlocal owner_cursor
        for index in range(enterprise_count):
            owner = engine.capitalists[owner_ids[owner_cursor % len(owner_ids)]]
            owner_cursor += 1
            enterprise = engine.create_enterprise(
                industry=industry,
                owner_id=owner.id,
                cash=5000.0,
                modernization_capable=True,
            )
            # 工资报价从 WAGE_BASE 起步，之后按 V0.6 规则向目标部分调整；
            # 若状态为 0，首月会直接跳到目标，掩盖工资粘性。
            enterprise.wage_offer = WAGE_BASE
            for key, count in equipment.items():
                for _ in range(count):
                    enterprise.add_equipment(key)
            worker_count = workers_per_enterprise + (1 if index < extra_workers else 0)
            for _ in range(worker_count):
                worker = seed_worker(
                    industry=industry,
                    skill=2.0,
                    cash=20.0,
                    food=0.0,
                )
                worker.employer_id = enterprise.id
                worker.wage = WAGE_BASE
                enterprise.workers.append(worker.id)
            _seed_inputs(engine, enterprise)
            capacity, _, _ = equipment_summary(enterprise)
            enterprise.demand_forecast = capacity * 2.0

    add_industry(Industry.COAL_MINE, 20, 10, {"coal_t0": 1})
    add_industry(Industry.IRON_MINE, 8, 10, {"iron_t0": 1})
    add_industry(Industry.STEEL_MILL, 3, 4, {"steel_t0": 1})
    add_industry(Industry.BRICK_FACTORY, 1, 50, {"brick_t0": 1})
    add_industry(Industry.TEXTILE_MILL, 1, 20, {"textile_t0": 20})
    add_industry(Industry.MACHINERY_FACTORY, 1, 10, {"machinery_t0": 1})
    add_industry(Industry.CONSTRUCTION, 5, 25, {"construction_t0": 1}, extra_workers=3)
    # 化肥 starts empty; it is an entry opportunity once food/coal prices
    # 它会成为一个进入机会。

    engine.land.total_land = TOTAL_LAND_MU
    engine.market.reference_prices = dict(INITIAL_PRICES)
    engine.wage_floor_scale = (
        0.90 if config.policy_regime == PolicyRegime.CLASSICAL else 1.0
    )
    engine.price_regime = config.price_regime
    engine.demand_regime = config.demand_regime
    engine.bank_intermediation = config.bank_intermediation
    # 粮食平准库存/私人粮商：600 吨 ≈ 5 个月全民口粮，60k 现金。
    engine.food_reserve = FoodReserve(cash=60_000.0, food=600.0)
    if config.policy_regime == PolicyRegime.CLASSICAL:
        engine.government = None
    else:
        engine.government = Government(
            regime=config.policy_regime,
            money_regime=config.money_regime,
            cash=config.government_cash,
            tax_rate_wage=config.tax_rate_wage,
            tax_rate_profit=config.tax_rate_profit,
            ui_replacement=config.ui_replacement,
            ui_duration=config.ui_duration,
            public_investment_rate=config.public_investment_rate,
            public_investment_countercyclical=(
                config.public_investment_countercyclical
            ),
            job_guarantee=config.job_guarantee,
            jg_wage=config.jg_wage,
            jg_max_workers=config.jg_max_workers,
            pension_tax_rate=config.pension_tax_rate,
            pension_replacement=config.pension_replacement,
        )
        # 初始养老金基金只是政府现金中的专项台账，不能凭空增加货币。
        engine.government.pension_fund = min(
            config.pension_fund_initial, engine.government.cash
        )
    _seed_dependents(engine, config)
    engine.money_initial = engine.total_money()
    return engine


def _seed_dependents(engine: Engine, config: ScenarioConfig) -> None:
    """创建初始儿童/退休者（默认 0，保持旧基线）。

    儿童随机挂到一名成年女性名下，出生现金为 0；退休者不进入劳动市场，
    养老金从第一个月的政府结算开始领取。二者都不改变初始货币总量。
    """
    demo = engine.demographics
    adults = [
        worker
        for worker in engine.workers.values()
        if worker.alive and not worker.is_child and not worker.retired
    ]
    women = [worker for worker in adults if worker.sex == "F"]

    for index in range(max(0, config.initial_children)):
        age = engine.demographic_rng.randint(
            0, max(0, demo.working_age_months - 1)
        )
        sex = "F" if engine.demographic_rng.random() < 0.5 else "M"
        mother = women[index % len(women)] if women else None
        child = engine.create_worker(
            industry=mother.industry if mother else Industry.SERVICE,
            skill=0.0,
            cash=0.0,
            food=0.0,
            age_months=age,
            sex=sex,
            is_child=True,
            parent_id=mother.id if mother else None,
            birth_tick=-age,
        )
        child.cloth = 0.0
        child.housing = 0.0
        child.living_standard = "child"
        if mother is not None:
            mother.children_ids.append(child.id)

    if config.retirement_age_years <= 0:
        return
    retire_min = demo.retirement_age_months
    retire_max = min(
        demo.max_age_months - 12,
        demo.retirement_age_months + 18 * 12,
    )
    retirees = []
    for _ in range(max(0, config.initial_retirees)):
        age = engine.demographic_rng.randint(
            retire_min, max(retire_min, retire_max)
        )
        sex = "F" if engine.demographic_rng.random() < 0.5 else "M"
        retiree = engine.create_worker(
            industry=Industry.SERVICE,
            skill=1.0,
            cash=0.0,
            food=0.0,
            age_months=age,
            sex=sex,
            is_child=False,
            birth_tick=-age,
            retired=True,
        )
        retiree.cloth = 0.0
        retiree.housing = 0.0
        retiree.hours = 0
        retirees.append(retiree)

    # 初始退休者在第一次月度养老金发放前没有任何现金；先由财政垫付
    # 两个月养老金（可发债/央行融资），否则会在第 3 个月集体饿死。
    gov = engine.government
    if gov is not None and gov.pension_replacement > 0 and retirees:
        pension_estimate = max(
            WAGE_BASE * gov.pension_replacement,
            FOOD_PER_WORKER * INITIAL_PRICES[Good.FOOD],
        )
        advance_total = pension_estimate * 2.0 * len(retirees)
        if gov.cash < advance_total:
            engine._government_finance(
                advance_total - gov.cash, "pension_advance"
            )
        paid = min(advance_total, gov.cash)
        if paid > 0:
            per_retiree = paid / len(retirees)
            for retiree in retirees:
                retiree.cash += per_retiree
            gov.cash -= paid


def _capitalist(cid: str, cash: float, role: str):
    from .models import Capitalist

    return Capitalist(id=cid, cash=cash, role=role)


def _seed_inputs(engine: Engine, enterprise) -> None:
    """按当前产能和熟练度 2 给每家企业配置一个月投入。"""
    params = SECTOR_PARAMS[enterprise.industry]
    if not params.inputs:
        return
    capacity, _, _ = equipment_summary(enterprise)
    output = capacity * 2.0
    for good, ratio in params.inputs.items():
        enterprise.inventory[good] = max(
            enterprise.inventory.get(good, 0.0), output * ratio
        )
