"""历史阶段与政府/央行模块。

三种政策制度：

- CLASSICAL：凯恩斯之前的自由放任；无税收、无失业救济、无公共投资，
  金本位、货币守恒。这是默认剧本。
- KEYNESIAN：二战后福利国家；工资/利润税、失业救济、公共投资，
  以税收和债券融资为主，仍是金本位/货币守恒。
- MMT：主权货币；政府可以发债并由央行购买，央行创造货币，
  政府作为最后雇主提供就业保障（job guarantee）。

模块只负责“政策参数 + 政府账户 + 公共部门行为”，不直接改写市场规则；
Engine 在月度循环中调用它。这样历史阶段可以通过 ScenarioConfig 开关，
而不是把某一种制度硬编码进经济内核。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List

from .enums import Good


class PolicyRegime(str, Enum):
    CLASSICAL = "classical"
    KEYNESIAN = "keynesian"
    MMT = "mmt"


class MoneyRegime(str, Enum):
    GOLD = "gold"
    CREDIT = "credit"


@dataclass
class Government:
    regime: PolicyRegime = PolicyRegime.CLASSICAL
    money_regime: MoneyRegime = MoneyRegime.GOLD

    # 账户
    cash: float = 0.0
    debt: float = 0.0
    central_bank_money: float = 0.0
    bond_holders: Dict[str, float] = field(default_factory=dict)

    # 税收与转移
    tax_rate_wage: float = 0.0
    tax_rate_profit: float = 0.0
    ui_replacement: float = 0.0
    ui_duration: int = 0

    # 公共投资
    public_investment_rate: float = 0.0
    public_investment_countercyclical: float = 0.0

    # 就业保障（MMT / 最后雇主）
    job_guarantee: bool = False
    jg_wage: float = 0.0
    jg_workers: List[str] = field(default_factory=list)
    jg_max_workers: int = 0

    # 公共资本/库存
    public_capital: float = 0.0
    inventory: Dict[Good, float] = field(default_factory=lambda: {g: 0.0 for g in Good})

    # 月度流量（统计用）
    tax_revenue: float = 0.0
    transfers: float = 0.0
    spending: float = 0.0
    interest_paid: float = 0.0
    deficit: float = 0.0
    public_investment_budget: float = 0.0

    @property
    def active(self) -> bool:
        return self.regime != PolicyRegime.CLASSICAL

    @property
    def fiat_money(self) -> bool:
        return self.money_regime == MoneyRegime.CREDIT

    def reset_month(self) -> None:
        self.tax_revenue = 0.0
        self.transfers = 0.0
        self.spending = 0.0
        self.interest_paid = 0.0
        self.deficit = 0.0
        self.public_investment_budget = 0.0
