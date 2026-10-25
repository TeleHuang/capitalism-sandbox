"""Export V0.6 golden runs for the single-file HTML engine parity harness.

Runs the Python reference engine for a fixed regime/seed/months matrix and
writes a compact JSON file with the metrics a player actually sees.  The JS
release embeds this file; ``scripts/compare_golden_v06.mjs`` replays the same
matrix through the JS port and prints deviations.

Usage:
    python -I scripts/export_golden_v06.py [--quick]

``--quick`` only exports the 60-month runs (useful while iterating); the
default exports 60 and 240 months for all four historical regimes.
This intentionally never runs the 1200-month slow suite.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecosim.engine import Engine  # noqa: E402
from ecosim.scenarios import (  # noqa: E402
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    LATE_CAPITALISM,
    MMT_SOVEREIGN,
    build_scenario_1,
)

REGIMES = {
    "classical": CLASSICAL_LAISSEZ_FAIRE,
    "keynesian": KEYNESIAN_WELFARE,
    "mmt": MMT_SOVEREIGN,
    "late_capitalism": LATE_CAPITALISM,
}

SAMPLE_TICKS = (1, 6, 12, 24, 36, 48, 60, 120, 180, 240)
GOODS = (
    "food",
    "meat",
    "coal",
    "iron_ore",
    "steel",
    "brick",
    "cloth",
    "fertilizer",
    "machinery",
    "building",
    "service",
)
SCALARS = (
    "population",
    "children",
    "working_age",
    "retirees",
    "employed",
    "unemployed",
    "births",
    "deaths",
    "hunger_deaths",
    "gdp",
    "consumption",
    "investment",
    "unemployment_rate",
    "profit_rate",
    "profit_rate_annual",
    "average_wage",
    "cpi",
    "consumer_price_index",
    "real_wage_index",
    "productivity_index",
    "unit_labor_cost",
    "money_total",
    "bank_cash",
    "bank_loans",
    "bank_deposits",
    "government_cash",
    "government_debt",
    "government_tax_revenue",
    "government_transfers",
    "government_spending",
    "government_deficit",
    "government_jg_workers",
    "central_bank_money",
    "pension_fund",
    "pension_spending",
    "food_output",
    "ag_productivity",
    "food_reserve",
    "food_relief",
    "food_levy",
    "land_price",
    "smallholder_land",
    "capitalist_farms",
    "household_farms",
    "farm_machinery",
    "fertilizer_used",
    "service_employment_share",
    "livestock_employment_share",
    "average_hours",
    "food_share",
    "food_total_share",
    "meat_share",
    "cloth_share",
    "housing_share",
    "service_spending_share",
    "market_food_total_share",
    "market_meat_share",
    "market_service_spending_share",
    "household_consumption_value",
    "capital_stock",
    "capitalist_capital_stock",
    "capitalist_profit",
    "household_operating_income",
    "active_enterprises",
    "average_markup",
    "output_index",
    "real_wage_proxy",
)


def pick(stat: dict) -> dict:
    sample = {key: stat.get(key) for key in SCALARS}
    sample["prices"] = {g: stat["prices"].get(g) for g in GOODS}
    sample["production"] = {g: stat["production"].get(g) for g in GOODS}
    sample["volumes"] = {g: stat["volumes"].get(g) for g in GOODS}
    sample["demand"] = {g: stat["demand"].get(g) for g in GOODS}
    sample["supply"] = {g: stat["supply"].get(g) for g in GOODS}
    sample["firms"] = dict(stat["firms"])
    sample["living_standard"] = dict(stat["living_standard"])
    sample["warnings"] = list(stat.get("warnings") or [])[:4]
    return sample


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="only 60-month runs")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "web" / "release" / "src" / "golden_v06.json",
    )
    args = parser.parse_args()

    month_matrix = (60,) if args.quick else (60, 240)
    runs = []
    started = time.time()
    for regime_id, base in REGIMES.items():
        for months in month_matrix:
            config = replace(base, price_regime="free", demand_regime="geary")
            t0 = time.time()
            engine = Engine(seed=1)
            build_scenario_1(engine, config=config)
            samples = {}
            for month in range(1, months + 1):
                stat = engine.step()
                if month in SAMPLE_TICKS:
                    samples[str(month)] = pick(stat)
            runs.append(
                {
                    "regime": regime_id,
                    "seed": 1,
                    "months": months,
                    "price_regime": "free",
                    "demand_regime": "geary",
                    "money_initial": engine.money_initial,
                    "policy_regime": engine.government.regime.value
                    if engine.government
                    else "classical",
                    "samples": samples,
                }
            )
            final = engine.stats[-1]
            print(
                f"{regime_id:16s} {months:3d}mo {time.time() - t0:6.1f}s "
                f"pop={final['population']:4d} gdp={final['gdp']:9.0f} "
                f"u={final['unemployment_rate'] * 100:5.1f}% "
                f"pi={final['profit_rate'] * 100:6.2f}%",
                flush=True,
            )
    payload = {
        "version": "0.6.0",
        "generated_by": "scripts/export_golden_v06.py",
        "seed_notes": "Python reference; free price regime; geary demand",
        "elapsed_seconds": round(time.time() - started, 1),
        "runs": runs,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.1f} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
