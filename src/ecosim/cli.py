from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from .engine import Engine
from .scenarios import (
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    LATE_CAPITALISM,
    MMT_SOVEREIGN,
    ScenarioConfig,
    build_scenario_1,
)

REGIMES = {
    "classical": CLASSICAL_LAISSEZ_FAIRE,
    "keynesian": KEYNESIAN_WELFARE,
    "mmt": MMT_SOVEREIGN,
    "late_capitalism": LATE_CAPITALISM,
}


def run(
    months: int = 240,
    seed: int = 1,
    every: int = 12,
    scenario: ScenarioConfig = CLASSICAL_LAISSEZ_FAIRE,
) -> Engine:
    engine = Engine(seed=seed)
    build_scenario_1(engine, config=scenario)
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
    parser.add_argument(
        "--regime",
        choices=sorted(REGIMES),
        default="classical",
        help=(
            "政策制度：classical（自由放任）/ keynesian（福利国家）/ "
            "mmt（主权货币+就业保障）/ late_capitalism（低生育+老龄化）"
        ),
    )
    parser.add_argument(
        "--price-regime",
        choices=("band", "markup_soft", "free"),
        default="band",
        help=(
            "价格制度：band（默认参考价+成本带）/ markup_soft（参考价锚定的"
            "软成本加成）/ free（成本加成+供求，无成本带，仅绝对安全轨）"
        ),
    )
    args = parser.parse_args(argv)

    scenario = REGIMES[args.regime]
    if args.price_regime != "band":
        scenario = replace(scenario, price_regime=args.price_regime)
    engine = run(args.months, args.seed, args.every, scenario)
    final = engine.stats[-1]
    print()
    print("最终状态")
    print(
        f"  人口：{final['population']}（儿童 {final['children']} / "
        f"劳动年龄 {final['working_age']} / 退休 {final['retirees']}）  "
        f"本月出生/死亡：{final['births']}/{final['deaths']}"
    )
    print(
        f"  抚养比：{final['dependency_ratio']:.2f}  "
        f"平均年龄：{final['average_age']:.1f}"
    )
    print(
        f"  GDP：{final['gdp']:.0f}  消费：{final['consumption']:.0f}  "
        f"投资：{final['investment']:.0f}"
    )
    print(f"  失业率：{final['unemployment_rate'] * 100:.1f}%")
    print(f"  全社会利润率：{final['profit_rate'] * 100:.2f}%")
    print(
        f"  标准工时：{final['standard_work_hours']}h  "
        f"实际平均工时：{final['average_hours']:.1f}h  "
        f"平均工资：{final['average_wage']:.2f}"
    )
    print(
        f"  劳动生产率指数：{final['productivity_index']:.3f}  "
        f"单位劳动成本：{final['unit_labor_cost']:.3f}  "
        f"CPI：{final['cpi']:.3f}  "
        f"通胀预期：{final['inflation_expectation'] * 100:.3f}%/月"
    )
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
    print(f"  政策制度：{args.regime}  价格制度：{args.price_regime}")
    if final.get("policy_regime") != "classical":
        print(
            f"  政府现金/债务：{final['government_cash']:.0f} / "
            f"{final['government_debt']:.0f}"
        )
        print(
            f"  税收/转移/支出/赤字：{final['government_tax_revenue']:.0f} / "
            f"{final['government_transfers']:.0f} / "
            f"{final['government_spending']:.0f} / "
            f"{final['government_deficit']:.0f}"
        )
        print(
            f"  就业保障人数：{final['government_jg_workers']}  "
            f"央行货币：{final['central_bank_money']:.0f}"
        )
        print(
            f"  养老金：缴费 {final['pension_contributions']:.0f} / "
            f"发放 {final['pension_spending']:.0f} / "
            f"基金 {final['pension_fund']:.0f} / "
            f"补贴 {final['pension_subsidy']:.0f}"
        )
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
