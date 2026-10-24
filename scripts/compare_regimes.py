"""对比 classical / keynesian / mmt 三种历史阶段的 240 月结果。

用法：
  PYTHONPATH=src python scripts/compare_regimes.py --months 240 --seed 1
  PYTHONPATH=src python scripts/compare_regimes.py --json artifacts/regimes.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecosim.engine import Engine  # noqa: E402
from ecosim.enums import Good, Industry  # noqa: E402
from ecosim.scenarios import (  # noqa: E402
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    MMT_SOVEREIGN,
    build_scenario_1,
)

CONFIGS = {
    "classical": CLASSICAL_LAISSEZ_FAIRE,
    "keynesian": KEYNESIAN_WELFARE,
    "mmt": MMT_SOVEREIGN,
}
CORE = (Good.STEEL, Good.BRICK, Good.CLOTH, Good.MACHINERY, Good.BUILDING)


def run(config, months: int, seed: int) -> dict:
    engine = Engine(seed=seed)
    build_scenario_1(engine, config=config)
    deaths = 0
    zero = {good.value: 0 for good in CORE}
    for _ in range(months):
        stat = engine.step()
        deaths += stat["dead_this_month"]
        for good in CORE:
            if stat["production"][good.value] <= 1e-9:
                zero[good.value] += 1
    final = engine.stats[-1]
    return {
        "name": config.name,
        "regime": config.policy_regime.value,
        "money_regime": config.money_regime.value,
        "months": months,
        "seed": seed,
        "alive": final["alive"],
        "deaths": deaths,
        "unemployment_rate": final["unemployment_rate"],
        "gdp": final["gdp"],
        "investment": final["investment"],
        "profit_rate": final["profit_rate"],
        "food_output": final["food_output"],
        "food_price": final["prices"][Good.FOOD.value],
        "government_cash": final["government_cash"],
        "government_debt": final["government_debt"],
        "government_tax_revenue": final["government_tax_revenue"],
        "government_transfers": final["government_transfers"],
        "government_spending": final["government_spending"],
        "government_deficit": final["government_deficit"],
        "government_jg_workers": final["government_jg_workers"],
        "central_bank_money": final["central_bank_money"],
        "money_total": final["money_total"],
        "money_initial": engine.money_initial,
        "money_conserved": abs(final["money_total"] - engine.money_initial) < 0.01,
        "zero_output_months": zero,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="对比历史阶段/政策制度的仿真结果")
    parser.add_argument("--months", type=int, default=240)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    results = {
        name: run(config, args.months, args.seed)
        for name, config in CONFIGS.items()
    }

    header = (
        "| 制度 | 存活 | 死亡 | 失业率 | GDP | 投资 | 利润率 | "
        "政府债务 | 央行货币 | 就业保障 | 货币守恒 |"
    )
    print(f"# {args.months} 月，seed={args.seed}\n")
    print(header)
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|")
    for name, result in results.items():
        print(
            f"| {name} | {result['alive']} | {result['deaths']} | "
            f"{result['unemployment_rate'] * 100:.1f}% | "
            f"{result['gdp']:.0f} | {result['investment']:.0f} | "
            f"{result['profit_rate'] * 100:.2f}% | "
            f"{result['government_debt']:.0f} | "
            f"{result['central_bank_money']:.0f} | "
            f"{result['government_jg_workers']} | "
            f"{'是' if result['money_conserved'] else '否'} |"
        )
    print("\n核心行业零产出月数：")
    for name, result in results.items():
        zero = ", ".join(
            f"{good}={months}" for good, months in result["zero_output_months"].items()
        )
        print(f"- {name}: {zero}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
