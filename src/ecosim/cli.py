from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import Engine
from .scenarios import build_scenario_1


def run(months: int = 240, seed: int = 1, every: int = 12) -> Engine:
    engine = Engine(seed=seed)
    build_scenario_1(engine)
    for month in range(1, months + 1):
        stat = engine.step()
        if every > 0 and (month % every == 0 or month == 1):
            _print_row(stat)
    return engine


def _print_row(stat: dict) -> None:
    print(
        f"T{stat['tick']:>3} "
        f"alive={stat['alive']:>4} "
        f"unemp={stat['unemployment_rate'] * 100:5.1f}% "
        f"gdp={stat['gdp']:>9.0f} "
        f"profit={stat['profit_rate'] * 100:6.2f}% "
        f"food={stat['food_output']:>7.1f} "
        f"agprod={stat['ag_productivity']:>5.2f} "
        f"capfarms={stat['capitalist_farms']:>3} "
        f"fert={stat['fertilizer_used']:>6.1f} "
        f"mach={stat['farm_machinery']:>3} "
        f"land={stat['land_price']:>6.1f} "
        f"p_food={stat['prices']['food']:>6.1f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ecosim",
        description="Run the Capitalism Sandbox monthly simulation.",
    )
    parser.add_argument("--months", type=int, default=240, help="number of monthly ticks")
    parser.add_argument("--seed", type=int, default=1, help="deterministic RNG seed")
    parser.add_argument("--every", type=int, default=12, help="print a row every N months")
    parser.add_argument("--json", type=Path, default=None, help="write full stats JSON")
    args = parser.parse_args(argv)

    engine = run(args.months, args.seed, args.every)
    final = engine.stats[-1]
    print()
    print("Final state")
    print(f"  alive: {final['alive']}  dead this month: {final['dead_this_month']}")
    print(f"  GDP: {final['gdp']:.0f}  consumption: {final['consumption']:.0f}  investment: {final['investment']:.0f}")
    print(f"  unemployment: {final['unemployment_rate'] * 100:.1f}%")
    print(f"  aggregate profit rate: {final['profit_rate'] * 100:.2f}%")
    print(f"  food output: {final['food_output']:.1f}  ag productivity: {final['ag_productivity']:.2f}")
    print(f"  capitalist farms: {final['capitalist_farms']}  household farms: {final['household_farms']}")
    print(f"  fertilizer used: {final['fertilizer_used']:.1f}  farm machinery: {final['farm_machinery']}")
    print(f"  land price: {final['land_price']:.2f}  smallholder land: {final['smallholder_land']:.0f} mu")
    print(f"  money total: {final['money_total']:.0f} (initial {engine.money_initial:.0f})")
    if final["warnings"]:
        print("  warnings:")
        for warning in final["warnings"]:
            print(f"    - {warning}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "seed": args.seed,
            "months": args.months,
            "money_initial": engine.money_initial,
            "stats": engine.stats,
        }
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
