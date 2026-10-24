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
        f"存活={stat['alive']:>4} "
        f"失业={stat['unemployment_rate'] * 100:5.1f}% "
        f"GDP={stat['gdp']:>9.0f} "
        f"利润率={stat['profit_rate'] * 100:6.2f}% "
        f"粮食={stat['food_output']:>7.1f} "
        f"农业人均={stat['ag_productivity']:>5.2f} "
        f"资本农场={stat['capitalist_farms']:>3} "
        f"化肥={stat['fertilizer_used']:>6.1f} "
        f"农机={stat['farm_machinery']:>3} "
        f"地价={stat['land_price']:>6.1f} "
        f"粮价={stat['prices']['food']:>6.1f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ecosim",
        description="运行资本主义经济沙盒的月度仿真。",
    )
    parser.add_argument("--months", type=int, default=240, help="运行的月度轮数")
    parser.add_argument("--seed", type=int, default=1, help="确定性随机种子")
    parser.add_argument("--every", type=int, default=12, help="每 N 个月打印一行")
    parser.add_argument("--json", type=Path, default=None, help="把完整统计写入 JSON")
    args = parser.parse_args(argv)

    engine = run(args.months, args.seed, args.every)
    final = engine.stats[-1]
    print()
    print("最终状态")
    print(f"  存活：{final['alive']}  本月死亡：{final['dead_this_month']}")
    print(
        f"  GDP：{final['gdp']:.0f}  消费：{final['consumption']:.0f}  "
        f"投资：{final['investment']:.0f}"
    )
    print(f"  失业率：{final['unemployment_rate'] * 100:.1f}%")
    print(f"  全社会利润率：{final['profit_rate'] * 100:.2f}%")
    print(
        f"  粮食产出：{final['food_output']:.1f}  "
        f"农业劳动生产率：{final['ag_productivity']:.2f}"
    )
    print(
        f"  资本主义农场：{final['capitalist_farms']}  "
        f"自耕农农场：{final['household_farms']}"
    )
    print(
        f"  化肥使用：{final['fertilizer_used']:.1f}  "
        f"农机数量：{final['farm_machinery']}"
    )
    print(
        f"  地价：{final['land_price']:.2f}  "
        f"自耕农土地：{final['smallholder_land']:.0f} 亩"
    )
    print(f"  货币总量：{final['money_total']:.0f}（初始 {engine.money_initial:.0f}）")
    if final["warnings"]:
        print("  警告：")
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
        print(f"\n已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
