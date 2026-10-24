from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .config import FOOD_PER_WORKER, HOURS_OPTIONS
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
    is_owner_operator: bool = False
    land_owned: float = 0.0

    # Last month's realised consumption, used for living-standard classification.
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
        """The PRD's labour-reproduction ladder, in a deliberately simple form.

        Workers first secure savings; once they have a comfort cushion they
        exchange income for leisure.  Prices are part of the reservation wage,
        so expensive food keeps people at 16 hours.
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
        # Hunger overrides leisure: a worker without food works full time.
        if self.food + 1e-9 < 0.10 or self.living_standard in ("survival", "subsistence"):
            return 16
        if self.cash >= 120.0 and current > 8:
            return 8
        if self.cash >= 60.0 and current > 12:
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

    # Market / accounting state
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
    food: float = 0.5
    cloth: float = 10.0
    housing: float = 2.0
    consumed_food: float = 0.0
    consumed_cloth: float = 0.0
    consumed_housing: float = 0.0

    def owned_count(self, enterprises: Dict[str, Enterprise]) -> int:
        return sum(1 for e in enterprises.values() if e.owner_id == self.id and e.active)


@dataclass
class InvestmentProject:
    """A construction project that buys capital goods over several months.

    Cash is moved out of the enterprise into the project when it is created.  The
    project is a market participant in its own right, so money is conserved and a
    project cannot over-spend.
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
class Bank:
    cash: float
    interest_rate: float = 0.01
    loans: Dict[str, float] = field(default_factory=dict)

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
        enterprise.debt += interest - payable
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
    owners: Dict[str, float] = field(default_factory=dict)       # worker_id -> mu
    enterprise_by_owner: Dict[str, str] = field(default_factory=dict)

    @property
    def smallholder_land(self) -> float:
        return sum(self.owners.values())

    @property
    def capitalist_land(self) -> float:
        return self.total_land - self.smallholder_land
