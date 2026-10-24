from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import (
    COMFORT_SAVINGS,
    FOOD_PER_WORKER,
    HOURS_OPTIONS,
    LEISURE_SAVINGS,
)
from .enums import Good, Industry


def empty_goods() -> Dict[Good, float]:
    return {g: 0.0 for g in Good}


@dataclass
class Worker:
    id: str
    industry: Industry
    skill: float = 1.0
    cash: float = 0.0
    food: float = FOOD_PER_WORKER
    cloth: float = 1.0
    housing: float = 0.2
    employer_id: Optional[str] = None
    wage: float = 0.0
    hours: int = 16
    alive: bool = True
    hunger_months: int = 0
    ui_months: int = 0
    is_owner_operator: bool = False
    land_owned: float = 0.0

    # 上月实际消费，用于生活标准分类。
    consumed_food: float = 0.0
    consumed_cloth: float = 0.0
    consumed_housing: float = 0.0
    living_standard: str = "survival"

    @property
    def effective_labor(self) -> float:
        return self.hours / 16.0

    @property
    def employed(self) -> bool:
        return self.employer_id is not None

    def choose_hours(self, prices: Dict[Good, float]) -> int:
        """PRD 的劳动力再生产阶梯，这里做刻意简化。

        工人先确保储蓄；有了一定缓冲后，会用收入交换闲暇。
        价格是保留工资的一部分，因此食品昂贵时工人仍会保持 16 小时工作。
        """
        basket = (
            FOOD_PER_WORKER * prices[Good.FOOD]
            + prices[Good.CLOTH]
            + 0.2 * prices[Good.BUILDING]
        )
        if self.hours in HOURS_OPTIONS:
            current = self.hours
        else:
            current = 16
        # 饥饿优先于闲暇：没有食物的工人会全职工作。
        if self.food + 1e-9 < 0.10 or self.living_standard in ("survival", "subsistence"):
            return 16
        if self.cash >= LEISURE_SAVINGS and current > 8:
            return 8
        if self.cash >= COMFORT_SAVINGS and current > 12:
            return 12
        if self.cash < basket * 2.0 and current != 16:
            return 16
        return current


@dataclass
class Enterprise:
    id: str
    industry: Industry
    owner_id: str
    is_household: bool = False
    cash: float = 0.0
    debt: float = 0.0
    land: float = 0.0
    equipment: Dict[str, int] = field(default_factory=dict)
    inventory: Dict[Good, float] = field(default_factory=empty_goods)
    workers: List[str] = field(default_factory=list)

    active: bool = True
    age: int = 0
    last_invest_tick: int = -999
    bankruptcy_months: int = 0
    modernization_capable: bool = True
    smoothed_sales: float = 0.0

    # V0.4 负反馈：需求预测、计划产出与库存目标
    demand_forecast: float = 0.0
    plan_ratio: float = 1.0
    markup: float = 0.15
    planned_output: float = 0.0
    target_inventory_months: float = 2.0
    last_demand: float = 0.0
    last_unmet: float = 0.0
    last_fill_rate: float = 1.0
    dormant_months: int = 0
    replacement_months: int = 0

    # 市场 / 会计状态
    ask_prices: Dict[Good, float] = field(default_factory=dict)
    planned_output: float = 0.0
    use_fertilizer: bool = False
    last_output: float = 0.0
    last_input_used: Dict[Good, float] = field(default_factory=dict)

    last_revenue: float = 0.0
    last_costs: float = 0.0
    last_wages: float = 0.0
    last_interest: float = 0.0
    last_profit: float = 0.0
    last_sales: Dict[Good, float] = field(default_factory=empty_goods)

    month_revenue: float = 0.0
    month_input_cost: float = 0.0
    month_wages: float = 0.0
    month_interest: float = 0.0

    def inv(self, good: Good) -> float:
        return self.inventory.get(good, 0.0)

    def add_equipment(self, key: str, quantity: int = 1) -> None:
        self.equipment[key] = self.equipment.get(key, 0) + quantity

    def equipment_count(self, key: str) -> int:
        return self.equipment.get(key, 0)

    def total_equipment(self) -> int:
        return sum(self.equipment.values())

    def reset_month_flows(self) -> None:
        self.month_revenue = 0.0
        self.month_input_cost = 0.0
        self.month_wages = 0.0
        self.month_interest = 0.0
        self.last_sales = empty_goods()
        self.last_output = 0.0
        self.last_input_used = {}


@dataclass
class Capitalist:
    id: str
    cash: float
    role: str = "director"
    food: float = 0.15
    cloth: float = 1.5
    housing: float = 0.3
    consumed_food: float = 0.0
    consumed_cloth: float = 0.0
    consumed_housing: float = 0.0

    def owned_count(self, enterprises: Dict[str, Enterprise]) -> int:
        return sum(1 for e in enterprises.values() if e.owner_id == self.id and e.active)


@dataclass
class InvestmentProject:
    """跨月采购资本品的建设项目。

    项目创建时，现金从企业转移到项目；项目本身是独立的市场参与者，
    因此货币守恒，且项目不会超支。
    """

    id: str
    industry: Industry
    enterprise_id: str
    equipment_key: str
    quantity: int
    needed: Dict[Good, float]
    cash: float
    created_tick: int
    build_months: int
    is_new_enterprise: bool = False
    received: Dict[Good, float] = field(default_factory=empty_goods)
    inventory: Dict[Good, float] = field(default_factory=empty_goods)
    months_left: int = 0
    age: int = 0
    active: bool = True
    started: bool = False

    def fully_paid(self) -> bool:
        return all(
            self.received.get(g, 0.0) + 1e-9 >= qty
            for g, qty in self.needed.items()
        )

    def remaining(self, good: Good) -> float:
        return max(0.0, self.needed.get(good, 0.0) - self.received.get(good, 0.0))


@dataclass
class FoodReserve:
    """粮食平准库存：高价释放、低价收储。

    古典剧本里可以理解为私人粮商；Keynesian/MMT 里是政府战略储备。
    它只参与食品市场，不参与财政/货币创造。
    """

    cash: float = 0.0
    food: float = 0.0


@dataclass
class AssetPool:
    """破产/遗产回收的资产池，避免资产凭空消失。

    当前版本还没有二手设备市场，先记在池子里；后续新进入者可以折价购买。
    """

    inventory: Dict[Good, float] = field(default_factory=empty_goods)
    equipment: Dict[str, int] = field(default_factory=dict)
    land: float = 0.0


@dataclass
class Bank:
    cash: float
    interest_rate: float = 0.01
    loans: Dict[str, float] = field(default_factory=dict)
    deposits: Dict[str, float] = field(default_factory=dict)
    deposit_rate: float = 0.002
    write_offs: float = 0.0
    # 冲击测试钩子：被冻结/不可放贷的准备金。仍属于银行资产和货币总量，
    # 但不参与 Bank.lend / 国债购买；默认 0，不改变基线行为。
    frozen_cash: float = 0.0

    def deposit(self, agent, amount: float) -> float:
        """吸收存款：现金从储户转到银行，货币总量不变。"""
        amount = max(0.0, min(amount, getattr(agent, "cash", 0.0)))
        if amount <= 1e-9:
            return 0.0
        agent.cash -= amount
        self.cash += amount
        self.deposits[agent.id] = self.deposits.get(agent.id, 0.0) + amount
        return amount

    def pay_deposit_interest(self, agents: Dict[str, object]) -> float:
        """支付存款利息；只给仍存活/存在的储户记账。

        死亡储户的存款留在银行，不再支付利息；否则利息会从货币审计中消失。
        """
        total = sum(self.deposits.values())
        if total <= 1e-9 or self.cash <= 1e-9:
            return 0.0
        due = total * self.deposit_rate
        factor = min(1.0, self.cash / due) if due > 0 else 0.0
        credited = 0.0
        for agent_id, amount in list(self.deposits.items()):
            agent = agents.get(agent_id)
            if agent is None or (
                hasattr(agent, "alive") and not getattr(agent, "alive")
            ):
                continue
            interest = amount * self.deposit_rate * factor
            if interest <= 1e-9:
                continue
            agent.cash += interest
            credited += interest
        self.cash -= credited
        return credited

    def lend(self, enterprise: Enterprise, amount: float) -> float:
        amount = max(0.0, min(amount, self.cash))
        if amount <= 1e-9:
            return 0.0
        self.cash -= amount
        enterprise.cash += amount
        enterprise.debt += amount
        self.loans[enterprise.id] = self.loans.get(enterprise.id, 0.0) + amount
        return amount

    def charge_interest(self, enterprise: Enterprise) -> float:
        if enterprise.debt <= 0:
            return 0.0
        interest = enterprise.debt * self.interest_rate
        payable = min(interest, max(enterprise.cash, 0.0))
        enterprise.cash -= payable
        self.cash += payable
        unpaid = interest - payable
        enterprise.debt += unpaid
        if unpaid > 1e-12:
            # 资本化利息同样构成银行债权；否则 bank.loans 会系统性
            # 小于 Σ enterprise.debt，破产核销也会漏记这部分。
            self.loans[enterprise.id] = (
                self.loans.get(enterprise.id, 0.0) + unpaid
            )
        enterprise.month_interest += payable
        return payable

    def repay(self, enterprise: Enterprise, amount: float) -> float:
        amount = max(0.0, min(amount, enterprise.debt, enterprise.cash))
        if amount <= 1e-9:
            return 0.0
        enterprise.cash -= amount
        enterprise.debt -= amount
        self.cash += amount
        self.loans[enterprise.id] = max(0.0, self.loans.get(enterprise.id, 0.0) - amount)
        return amount


@dataclass
class LandMarket:
    total_land: float
    price: float
    owners: Dict[str, float] = field(default_factory=dict)       # 工人 ID -> 亩数
    enterprise_by_owner: Dict[str, str] = field(default_factory=dict)
    estate_land: float = 0.0                                      # 死亡自耕农的待售土地（亩）

    @property
    def smallholder_land(self) -> float:
        return sum(self.owners.values())

    @property
    def capitalist_land(self) -> float:
        return self.total_land - self.smallholder_land
