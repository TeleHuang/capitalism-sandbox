"""本地 LLM 经理探针：跑一段仿真，让模型对一家企业做长期投资决策。

用法：
  python scripts/llm_probe.py --settings "%USERPROFILE%\\.claude\\settings_DS.json" --months 60

不会把 API key 写入仓库或输出。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecosim.config import EQUIPMENT, SECTOR_PARAMS  # noqa: E402
from ecosim.decisions import representative_roi  # noqa: E402
from ecosim.engine import Engine  # noqa: E402
from ecosim.enums import GOOD_LABELS, Good, Industry  # noqa: E402
from ecosim.llm import (  # noqa: E402
    LLMClient,
    LLMConfig,
    MANAGER_SYSTEM_PROMPT,
    build_manager_prompt,
)
from ecosim.production import equipment_cost, equipment_summary  # noqa: E402
from ecosim.scenarios import build_scenario_1  # noqa: E402


def build_snapshot(engine: Engine, enterprise) -> dict:
    prices = engine.market.reference_prices
    params = SECTOR_PARAMS[enterprise.industry]
    capacity, required_workers, units = equipment_summary(enterprise)
    options = []
    for key in params.equipment:
        et = EQUIPMENT[key]
        if et.capital_good is None:
            continue
        options.append(
            {
                "key": key,
                "capacity": et.capacity,
                "workers": et.workers,
                "cost": round(equipment_cost(key, prices), 2),
                "roi": round(
                    representative_roi(
                        enterprise.industry, key, prices, engine.average_wage(), engine.land.price
                    ),
                    4,
                ),
            }
        )
    return {
        "tick": engine.tick,
        "industry": enterprise.industry.value,
        "cash": round(enterprise.cash, 2),
        "debt": round(enterprise.debt, 2),
        "workers": len(engine.enterprise_workers(enterprise)),
        "equipment": dict(enterprise.equipment),
        "capacity": capacity,
        "required_workers": required_workers,
        "inventory": {GOOD_LABELS[g]: round(q, 2) for g, q in enterprise.inventory.items() if q > 1e-9},
        "last_output": round(enterprise.last_output, 2),
        "last_profit": round(enterprise.last_profit, 2),
        "prices": {
            good.value: round(prices[good], 2)
            for good in (params.output, *params.inputs.keys())
        },
        "market": {
            "output_demand": round(engine.market.history[params.output]["demand"], 2),
            "output_supply": round(engine.market.history[params.output]["supply"], 2),
            "output_unsold": round(engine.market.history[params.output]["unsold"], 2),
        },
        "land_price": round(engine.land.price, 2),
        "unit_cap": 2 if enterprise.industry == Industry.FERTILIZER_FACTORY else None,
        "equipment_options": options,
        "farm_fertilizer_used": round(
            sum(
                e.last_input_used.get(Good.FERTILIZER, 0.0)
                for e in engine.active_enterprises(Industry.AGRICULTURE)
            ),
            2,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 经理长期规划探针")
    parser.add_argument("--settings", type=Path, default=None, help="本地 settings_DS.json 路径")
    parser.add_argument("--months", type=int, default=60, help="先跑多少个月仿真")
    parser.add_argument("--industry", default="fertilizer_factory", help="行业值，如 fertilizer_factory")
    parser.add_argument("--model", default=None, help="覆盖模型名")
    args = parser.parse_args()

    if args.settings:
        config = LLMConfig.from_settings(args.settings, model=args.model)
    else:
        config = LLMConfig.from_env(model=args.model)

    engine = Engine(seed=1)
    build_scenario_1(engine)
    for _ in range(args.months):
        engine.step()

    try:
        industry = Industry(args.industry)
    except ValueError:
        print(f"未知行业：{args.industry}；可选：{[i.value for i in Industry]}")
        return 2

    enterprises = engine.active_enterprises(industry)
    if not enterprises:
        print(f"{args.months} 个月后没有活跃的 {industry.value} 企业")
        return 1
    operating = [e for e in enterprises if e.total_equipment() > 0]
    enterprise = max(operating or enterprises, key=lambda e: (e.total_equipment(), e.cash))
    snapshot = build_snapshot(engine, enterprise)
    print("企业快照：")
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))

    client = LLMClient(config)
    print("\n向模型请求长期投资决策……")
    decision = client.complete_json(
        MANAGER_SYSTEM_PROMPT,
        build_manager_prompt(snapshot),
        max_tokens=2000,
    )
    print("模型决策：")
    print(json.dumps(decision, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
