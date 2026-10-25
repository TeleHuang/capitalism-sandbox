"""V0.5 人口/养老金/百年仿真验证。

对 classical / keynesian / mmt / late_capitalism 跑长程基线（默认 1200 月），
检查：

- 人口不灭绝：期末人口 > 0，劳动年龄人口 > 0，儿童/退休者结构合理；
- 最后 12 个月仍有出生（不是“生育停止后慢慢死光”）；
- 饥饿死亡累计（救济缓冲回归）；
- 金本位货币守恒（classical/keynesian/late_capitalism）；
- 养老金基金恒等式与补贴路径；
- 统计字段有限（无 NaN/Inf）。

这不是单元测试的替代品：1200 月运行较慢，放在 scripts 里按需/夜间跑。
输出 JSON 到 artifacts/validation_v05/。

用法：
  PYTHONPATH=src python scripts/validate_v05.py --months 1200 --seed 1
  PYTHONPATH=src python scripts/validate_v05.py --months 1200 --seed 1 --strict
  PYTHONPATH=src python scripts/validate_v05.py --months 240 --jobs 4
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecosim.engine import Engine  # noqa: E402
from ecosim.scenarios import (  # noqa: E402
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    LATE_CAPITALISM,
    MMT_SOVEREIGN,
    ScenarioConfig,
    build_scenario_1,
)

CONFIGS: Dict[str, ScenarioConfig] = {
    "classical": CLASSICAL_LAISSEZ_FAIRE,
    "keynesian": KEYNESIAN_WELFARE,
    "mmt": MMT_SOVEREIGN,
    "late_capitalism": LATE_CAPITALISM,
}
GOLD_REGIMES = {"classical", "keynesian", "late_capitalism"}


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def run_one(
    name: str, months: int, seed: int
) -> Dict[str, Any]:
    engine = Engine(seed=seed)
    build_scenario_1(engine, config=CONFIGS[name])
    started = time.time()
    for _ in range(months):
        engine.step()

    stats = engine.stats
    final = stats[-1]
    hunger = sum(stat["hunger_deaths"] for stat in stats)
    last12_births = sum(stat["births"] for stat in stats[-12:])
    money_drift = final["money_total"] - engine.money_initial
    pension_identity_gap = max(
        abs(
            stat["pension_fund"]
            - (
                stats[index - 1]["pension_fund"]
                + stat["pension_revenue"]
                - stat["pension_spending"]
            )
        )
        for index, stat in enumerate(stats)
        if index > 0
    )
    budget_gap = max(
        abs(
            stat["government_deficit"]
            - (
                stat["government_spending"]
                + stat["government_transfers"]
                + stat["government_interest_paid"]
                + stat["pension_spending"]
                - stat["government_tax_revenue"]
                - stat["pension_contributions"]
            )
        )
        for stat in stats
        if stat["government_deficit"] is not None
    )
    result: Dict[str, Any] = {
        "regime": name,
        "months": months,
        "seed": seed,
        "population": final["population"],
        "children": final["children"],
        "working_age": final["working_age"],
        "retirees": final["retirees"],
        "last12_births": last12_births,
        "hunger_deaths_total": hunger,
        "max_monthly_death_rate": max(stat["death_rate"] for stat in stats),
        "pension_fund": final["pension_fund"],
        "pension_fund_unfunded": final["pension_fund_unfunded"],
        "pension_subsidy_total": sum(
            stat["pension_subsidy"] for stat in stats
        ),
        "pension_identity_gap": pension_identity_gap,
        "budget_identity_gap": budget_gap,
        "money_initial": engine.money_initial,
        "money_final": final["money_total"],
        "money_drift": money_drift,
        "gold_regime": name in GOLD_REGIMES,
        "profit_rate": final["profit_rate"],
        "all_profit_rate": final["all_profit_rate"],
        "household_profit": final["household_profit"],
        # 家庭经营所得（自耕农/自雇摊主的劳动收入）与资本利润分开报告。
        "household_operating_income": final.get(
            "household_operating_income", 0.0
        ),
        "unemployment_rate": final["unemployment_rate"],
        "food_price": final["prices"]["food"],
        "food_output_final": final["food_output"],
        "food_output_avg_last12": sum(
            stat["food_output"] for stat in stats[-12:]
        ) / max(1, len(stats[-12:])),
        "food_supply_final": final["supply"]["food"],
        "food_demand_final": final["demand"]["food"],
        "food_reserve": final["food_reserve"],
        "household_farms": final["household_farms"],
        "household_farm_liquidations_total": final.get(
            "household_farm_liquidations_total"
        ),
        "capitalist_farms": final["capitalist_farms"],
        "estate_land": final["estate_land"],
        "smallholder_land": final["smallholder_land"],
        "finite_stats": all(
            _finite(value)
            for key, value in final.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ),
        "runtime_seconds": round(time.time() - started, 2),
    }
    result["ok_population"] = result["population"] > 0
    result["ok_births"] = last12_births > 0
    result["ok_hunger"] = hunger == 0
    result["ok_money"] = (
        abs(money_drift) <= 1e-2 if result["gold_regime"] else True
    )
    result["ok_pension"] = pension_identity_gap <= 1e-4
    result["ok_budget"] = budget_gap <= 1e-3
    result["ok"] = all(
        result[key]
        for key in (
            "ok_population",
            "ok_births",
            "ok_hunger",
            "ok_money",
            "ok_pension",
            "ok_budget",
            "finite_stats",
        )
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V0.5 长程人口/养老金验证")
    parser.add_argument("--months", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument(
        "--json",
        type=str,
        default="",
        help="输出 JSON 路径；默认 artifacts/validation_v05/seed{seed}_{months}.json",
    )
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    started = time.time()
    results: Dict[str, Dict[str, Any]] = {}
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            futures = {
                pool.submit(run_one, name, args.months, args.seed): name
                for name in CONFIGS
            }
            for future in as_completed(futures):
                results[futures[future]] = future.result()
    else:
        for name in CONFIGS:
            results[name] = run_one(name, args.months, args.seed)

    output = {
        "months": args.months,
        "seed": args.seed,
        "elapsed_seconds": round(time.time() - started, 2),
        "regimes": {name: results[name] for name in CONFIGS},
        "all_ok": all(item["ok"] for item in results.values()),
    }
    out_path = Path(args.json) if args.json else (
        ROOT / "artifacts" / "validation_v05"
        / f"seed{args.seed}_{args.months}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"{'regime':16} {'pop':>6} {'child':>6} {'ret':>5} "
        f"{'birth12':>7} {'hunger':>6} {'money':>10} {'ok':>5}"
    )
    for name in CONFIGS:
        item = results[name]
        print(
            f"{name:16} {item['population']:6d} {item['children']:6d} "
            f"{item['retirees']:5d} {item['last12_births']:7d} "
            f"{item['hunger_deaths_total']:6d} {item['money_drift']:10.4f} "
            f"{str(item['ok']):>5}"
        )
    print(f"JSON: {out_path}")
    if args.strict and not output["all_ok"]:
        print("FAILED: one or more validation checks failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
