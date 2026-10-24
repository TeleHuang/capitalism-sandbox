"""只读诊断：信贷冲击为什么造成死亡。

复现 `scripts/validate_v04.py` 的信贷冲击（利率 +300bp、工资缺口贷款 25%、
冻结 50% 银行现金 12 个月），逐月记录食品价格/产量、粮食储备、失业、工资、
现金和生活标准，并与同 seed 基线对比。不修改引擎、不写运行时数据。

用法：
  PYTHONPATH=src python scripts/diagnose_credit_shock.py
  PYTHONPATH=src python scripts/diagnose_credit_shock.py --months 240 --seed 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecosim.engine import Engine  # noqa: E402
from ecosim.scenarios import (  # noqa: E402
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    MMT_SOVEREIGN,
    ScenarioConfig,
    build_scenario_1,
)

REGIMES: Tuple[Tuple[str, ScenarioConfig], ...] = (
    ("classical", CLASSICAL_LAISSEZ_FAIRE),
    ("keynesian", KEYNESIAN_WELFARE),
    ("mmt", MMT_SOVEREIGN),
)
RATE_ADD = 0.03
LENDING_SCALE = 0.25
RESERVE_DRAIN = 0.50


def _freeze(engine: Engine, fraction: float) -> float:
    amount = engine.bank.cash * fraction
    engine.bank.cash -= amount
    engine.bank.frozen_cash += amount
    return amount


def _unfreeze(engine: Engine, amount: float) -> None:
    amount = max(0.0, min(amount, engine.bank.frozen_cash))
    engine.bank.frozen_cash -= amount
    engine.bank.cash += amount


def _worker_summary(engine: Engine) -> Dict[str, float]:
    alive = [w for w in engine.workers.values() if w.alive]
    return {
        "avg_cash": sum(w.cash for w in alive) / max(1, len(alive)),
        "min_cash": min((w.cash for w in alive), default=0.0),
        "zero_cash": sum(1 for w in alive if w.cash < 1.0),
        "avg_food": sum(w.food for w in alive) / max(1, len(alive)),
        "survival": sum(1 for w in alive if w.living_standard == "survival"),
        "subsistence": sum(1 for w in alive if w.living_standard == "subsistence"),
        "comfort": sum(1 for w in alive if w.living_standard == "comfort"),
        "leisure": sum(1 for w in alive if w.living_standard == "leisure"),
        "hungry": sum(1 for w in alive if w.hunger_months > 0),
        "employed": sum(1 for w in alive if w.employed),
    }


def run(config: ScenarioConfig, months: int, seed: int, shocked: bool) -> Dict[str, Any]:
    engine = Engine(seed=seed)
    build_scenario_1(engine, config=config)
    state: Dict[str, float] = {}
    rows: List[Dict[str, Any]] = []
    death_events: List[Dict[str, Any]] = []
    for tick in range(1, months + 1):
        if shocked and tick == 120:
            state["interest_rate"] = engine.bank.interest_rate
            state["lending_scale"] = engine.lending_scale
            state["frozen"] = _freeze(engine, RESERVE_DRAIN)
            engine.bank.interest_rate += RATE_ADD
            engine.lending_scale = LENDING_SCALE
        stat = engine.step()
        if shocked and tick == 132:
            engine.bank.interest_rate = state["interest_rate"]
            engine.lending_scale = state["lending_scale"]
            _unfreeze(engine, state.get("frozen", 0.0))
        workers = _worker_summary(engine)
        row = {
            "tick": tick,
            "alive": stat["alive"],
            "deaths": stat["dead_this_month"],
            "food_output": stat["food_output"],
            "food_price": stat["prices"]["food"],
            "food_reserve": stat["food_reserve"],
            "food_inventory": stat["inventory"]["food"],
            "food_demand": stat["demand"]["food"],
            "food_supply": stat["supply"]["food"],
            "food_volume": stat["volumes"]["food"],
            "food_unmet": stat["demand"]["food"] - stat["volumes"]["food"],
            "food_unsold": stat["supply"]["food"] - stat["volumes"]["food"],
            "unemployment": stat["unemployment_rate"],
            "gdp": stat["gdp"],
            "profit_rate": stat["profit_rate"],
            "bank_cash": stat["bank_cash"],
            "bank_frozen": stat["bank_frozen_cash"],
            "bank_loans": stat["bank_loans"],
            "gov_debt": stat["government_debt"],
            "gov_cash": stat["government_cash"],
            "avg_wage": engine.average_wage(),
            "avg_cash": workers["avg_cash"],
            "min_cash": workers["min_cash"],
            "zero_cash": workers["zero_cash"],
            "avg_food": workers["avg_food"],
            "hungry": workers["hungry"],
            "survival": workers["survival"],
            "subsistence": workers["subsistence"],
            "comfort": workers["comfort"],
            "leisure": workers["leisure"],
        }
        rows.append(row)
        if stat["dead_this_month"]:
            death_events.append(
                {
                    "tick": tick,
                    "deaths": stat["dead_this_month"],
                    "food_price": stat["prices"]["food"],
                    "food_output": stat["food_output"],
                    "food_reserve": stat["food_reserve"],
                    "food_inventory": stat["inventory"]["food"],
                    "food_demand": stat["demand"]["food"],
                    "food_supply": stat["supply"]["food"],
                    "food_volume": stat["volumes"]["food"],
                    "food_unmet": stat["demand"]["food"] - stat["volumes"]["food"],
                    "food_unsold": stat["supply"]["food"] - stat["volumes"]["food"],
                    "unemployment": stat["unemployment_rate"],
                    "avg_wage": row["avg_wage"],
                    "avg_cash": row["avg_cash"],
                    "min_cash": row["min_cash"],
                    "zero_cash": row["zero_cash"],
                    "hungry": workers["hungry"],
                    "survival": workers["survival"],
                }
            )
    final = engine.stats[-1]
    summary = {
        "alive": final["alive"],
        "deaths_total": sum(r["deaths"] for r in rows),
        "unemployment": final["unemployment_rate"],
        "gdp": final["gdp"],
        "investment": final["investment"],
        "profit_rate": final["profit_rate"],
        "food_output": final["food_output"],
        "food_price": final["prices"]["food"],
        "food_reserve": final["food_reserve"],
        "bank_cash": final["bank_cash"],
        "bank_frozen": final["bank_frozen_cash"],
        "bank_loans": final["bank_loans"],
        "gov_debt": final["government_debt"],
        "gov_cash": final["government_cash"],
        "money_total": final["money_total"],
        "money_initial": engine.money_initial,
    }
    return {"summary": summary, "rows": rows, "death_events": death_events}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=240)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument(
        "--regime",
        choices=("classical", "keynesian", "mmt", "all"),
        default="all",
    )
    parser.add_argument(
        "--json", type=Path, default=ROOT / "artifacts" / "credit_shock_diagnosis.json"
    )
    args = parser.parse_args()

    result: Dict[str, Any] = {}
    selected = [
        (name, config)
        for name, config in REGIMES
        if args.regime == "all" or args.regime == name
    ]
    for name, config in selected:
        baseline = run(config, args.months, args.seed, shocked=False)
        shock = run(config, args.months, args.seed, shocked=True)
        result[name] = {"baseline": baseline, "shock": shock}
        print(f"\n=== {name} ===")
        print("baseline:", baseline["summary"])
        print("shock:   ", shock["summary"])
        print("death events:")
        for event in shock["death_events"]:
            print(" ", event)

    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
