"""V0.4 验证 / 冲击测试套件。

对 classical / keynesian / mmt 三种制度跑 240 月基线，并在 T120 施加
6–12 个月的临时冲击，比较冲击路径与同 seed 基线路径：

- demand：家庭非食品消费、资本家消费、政府公共投资同时下降；
- productivity：农业与非农行业产出乘数下降；
- credit：利率上升 + 银行放贷比例下降 + 银行存款提取（银行中介制度下）。

冲击通过 Engine 上的中性钩子实现（默认 1.0 / 空字典），不改变默认三制度
的宏观行为。输出 JSON / CSV / Markdown 到 artifacts/validation/。

用法：
  PYTHONPATH=src python scripts/validate_v04.py --seeds 1 2 3 --jobs 6
  PYTHONPATH=src python scripts/validate_v04.py --months 60 --seeds 1 --fast
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ecosim.config import INITIAL_PRICES, TOTAL_LAND_MU  # noqa: E402
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
REGIME_LABELS = {
    "classical": "古典自由放任",
    "keynesian": "凯恩斯福利国家",
    "mmt": "MMT 主权货币 + 就业保障",
}
SHOCK_KEYS = ("demand", "productivity", "credit")
SHOCK_LABELS = {
    "demand": "需求冲击",
    "productivity": "生产率冲击",
    "credit": "信贷冲击",
}
CORE_GOODS = (
    Good.STEEL,
    Good.BRICK,
    Good.CLOTH,
    Good.MACHINERY,
    Good.BUILDING,
)

# 冲击参数（可在文档中引用；刻意保持温和，避免把“冲击测试”变成饥荒测试）。
DEMAND_WORKER_SCALE = 0.80       # 衣着/住房购买数量乘数
DEMAND_CAPITALIST_SCALE = 0.70   # 资本家消费预算乘数
AGRI_PRODUCTIVITY_SCALE = 0.90   # 农业产出乘数
INDUSTRY_PRODUCTIVITY_SCALE = 0.85
CREDIT_RATE_ADD = 0.03           # +300bp
CREDIT_LENDING_SCALE = 0.25      # 只发放 25% 的工资缺口贷款
CREDIT_RESERVE_DRAIN = 0.50      # 冻结 50% 银行现金作为不可放贷准备金

SHOCK_DEFINITIONS = {
    "demand": {
        "label": "需求冲击",
        "duration": 12,
        "description": (
            "家庭非食品消费 ×0.80、资本家消费预算 ×0.70；"
            "Keynesian/MMT 的公共投资率与逆周期项临时归零。"
            "食品购买不削减（生存品），因此不是饥荒冲击。"
        ),
        "engine_hooks": [
            "Engine.worker_demand_scale",
            "Engine.capitalist_demand_scale",
            "Government.public_investment_rate / countercyclical",
        ],
    },
    "productivity": {
        "label": "生产率冲击",
        "duration": 12,
        "description": (
            f"农业产出乘数 ×{AGRI_PRODUCTIVITY_SCALE:.2f}，"
            f"非农行业产出乘数 ×{INDUSTRY_PRODUCTIVITY_SCALE:.2f}。"
            "投入品消耗随产出同比例下降。"
        ),
        "engine_hooks": ["Engine.productivity_multipliers"],
    },
    "credit": {
        "label": "信贷冲击",
        "duration": 12,
        "description": (
            f"银行利率 +{CREDIT_RATE_ADD * 10000:.0f}bp；工资缺口贷款只发放 "
            f"{CREDIT_LENDING_SCALE * 100:.0f}%；同时把 "
            f"{CREDIT_RESERVE_DRAIN * 100:.0f}% 银行现金冻结为不可放贷准备金"
            "（仍计入货币总量，冲击结束后解冻）。"
        ),
        "engine_hooks": [
            "Bank.interest_rate",
            "Engine.lending_scale",
            "Bank.frozen_cash",
        ],
    },
}

PLACEBO_KEYS = ("placebo_demand", "placebo_credit")
PLACEBO_DEFINITIONS = {
    "placebo_demand": {
        "label": "安慰剂：1% 需求扰动",
        "description": (
            "家庭非食品消费 ×0.99、资本家消费预算 ×0.99，持续 12 个月；"
            "不削减政府支出。用于估计混沌/路径依赖造成的“伪冲击”量级。"
        ),
    },
    "placebo_credit": {
        "label": "安慰剂：1bp 信贷扰动",
        "description": (
            "利率 +1bp、工资缺口贷款比例 ×0.99、冻结 1% 银行现金，"
            "持续 12 个月。用于估计信贷渠道的可识别下限。"
        ),
    },
}

SERIES_FIELDS = (
    "gdp",
    "output_index",
    "consumption",
    "investment",
    "government_spending",
    "unemployment_rate",
    "alive",
    "deaths_cumulative",
    "food_output",
    "food_price",
    "government_debt",
    "central_bank_money",
    "money_total",
    "bank_loans",
    "bank_cash",
    "bank_frozen_cash",
    "profit_rate",
    "zero_core",
    "zero_food",
)


# ---------------------------------------------------------------------------
# 冲击实施 / 仿真
# ---------------------------------------------------------------------------
@dataclass
class ShockState:
    """保存冲击前的参数，便于在冲击结束时恢复。"""

    values: Dict[str, Any] = field(default_factory=dict)


def apply_shock(engine: Engine, shock_key: str) -> ShockState:
    state = ShockState()
    if shock_key == "placebo_demand":
        state.values["worker_demand_scale"] = engine.worker_demand_scale
        state.values["capitalist_demand_scale"] = engine.capitalist_demand_scale
        engine.worker_demand_scale = 0.99
        engine.capitalist_demand_scale = 0.99
    elif shock_key == "placebo_credit":
        state.values["interest_rate"] = engine.bank.interest_rate
        state.values["lending_scale"] = engine.lending_scale
        state.values["frozen_amount"] = _freeze_bank_reserves(engine, 0.01)
        engine.bank.interest_rate += 0.0001
        engine.lending_scale = 0.99
    elif shock_key == "demand":
        state.values["worker_demand_scale"] = engine.worker_demand_scale
        state.values["capitalist_demand_scale"] = engine.capitalist_demand_scale
        engine.worker_demand_scale = DEMAND_WORKER_SCALE
        engine.capitalist_demand_scale = DEMAND_CAPITALIST_SCALE
        gov = engine.government
        if gov is not None:
            state.values["public_investment_rate"] = gov.public_investment_rate
            state.values[
                "public_investment_countercyclical"
            ] = gov.public_investment_countercyclical
            gov.public_investment_rate = 0.0
            gov.public_investment_countercyclical = 0.0
    elif shock_key == "productivity":
        state.values["productivity_multipliers"] = dict(
            engine.productivity_multipliers
        )
        engine.productivity_multipliers = {
            industry: (
                AGRI_PRODUCTIVITY_SCALE
                if industry == Industry.AGRICULTURE
                else INDUSTRY_PRODUCTIVITY_SCALE
            )
            for industry in Industry
        }
    elif shock_key == "credit":
        state.values["interest_rate"] = engine.bank.interest_rate
        state.values["lending_scale"] = engine.lending_scale
        state.values["frozen_amount"] = _freeze_bank_reserves(
            engine, CREDIT_RESERVE_DRAIN
        )
        engine.bank.interest_rate += CREDIT_RATE_ADD
        engine.lending_scale = CREDIT_LENDING_SCALE
    else:
        raise ValueError(f"unknown shock: {shock_key}")
    return state


def restore_shock(engine: Engine, shock_key: str, state: ShockState) -> None:
    if shock_key == "placebo_demand":
        engine.worker_demand_scale = state.values["worker_demand_scale"]
        engine.capitalist_demand_scale = state.values["capitalist_demand_scale"]
    elif shock_key == "placebo_credit":
        engine.bank.interest_rate = state.values["interest_rate"]
        engine.lending_scale = state.values["lending_scale"]
        _unfreeze_bank_reserves(engine, state.values.get("frozen_amount", 0.0))
    elif shock_key == "demand":
        engine.worker_demand_scale = state.values["worker_demand_scale"]
        engine.capitalist_demand_scale = state.values["capitalist_demand_scale"]
        gov = engine.government
        if gov is not None and "public_investment_rate" in state.values:
            gov.public_investment_rate = state.values["public_investment_rate"]
            gov.public_investment_countercyclical = state.values[
                "public_investment_countercyclical"
            ]
    elif shock_key == "productivity":
        engine.productivity_multipliers = state.values["productivity_multipliers"]
    elif shock_key == "credit":
        engine.bank.interest_rate = state.values["interest_rate"]
        engine.lending_scale = state.values["lending_scale"]
        _unfreeze_bank_reserves(engine, state.values.get("frozen_amount", 0.0))


def _freeze_bank_reserves(engine: Engine, ratio: float) -> float:
    """把一部分银行现金冻结为不可放贷准备金（仍计入货币总量）。

    这是资产负债表内的科目重分类，不是货币创造/销毁；冲击结束后解冻。
    """
    amount = max(0.0, min(engine.bank.cash * ratio, engine.bank.cash))
    if amount <= 1e-9:
        return 0.0
    engine.bank.cash -= amount
    engine.bank.frozen_cash += amount
    return amount


def _unfreeze_bank_reserves(engine: Engine, amount: float) -> None:
    amount = max(0.0, min(amount, engine.bank.frozen_cash))
    if amount <= 1e-9:
        return
    engine.bank.frozen_cash -= amount
    engine.bank.cash += amount


def _series_row(stat: dict, cumulative_deaths: int) -> dict:
    production = stat["production"]
    zero_core = sum(
        1 for good in CORE_GOODS if production.get(good.value, 0.0) <= 1e-9
    )
    zero_food = 1 if production.get(Good.FOOD.value, 0.0) <= 1e-9 else 0
    row = {
        "tick": stat["tick"],
        "gdp": stat["gdp"],
        "output_index": stat["output_index"],
        "consumption": stat["consumption"],
        "investment": stat["investment"],
        "government_spending": stat["government_market_spending"],
        "unemployment_rate": stat["unemployment_rate"],
        "alive": stat["alive"],
        "deaths_cumulative": cumulative_deaths,
        "food_output": stat["food_output"],
        "food_price": stat["prices"][Good.FOOD.value],
        "government_debt": stat["government_debt"],
        "central_bank_money": stat["central_bank_money"],
        "money_total": stat["money_total"],
        "bank_loans": stat["bank_loans"],
        "bank_cash": stat["bank_cash"],
        "bank_frozen_cash": stat["bank_frozen_cash"],
        "profit_rate": stat["profit_rate"],
        "zero_core": zero_core,
        "zero_food": zero_food,
    }
    return row


def simulate(
    regime: str,
    seed: int,
    months: int,
    shock_key: Optional[str] = None,
    shock_start: int = 120,
    shock_duration: int = 12,
) -> dict:
    """跑一条基线或冲击路径，返回逐月序列与零产出摘要。"""
    engine = Engine(seed=seed)
    build_scenario_1(engine, config=CONFIGS[regime])
    shock_state: Optional[ShockState] = None
    applied = False
    series: List[dict] = []
    cumulative_deaths = 0
    zero_months_by_good = {good.value: 0 for good in Good}
    max_zero_streak_by_good = {good.value: 0 for good in Good}
    current_zero_streak = {good.value: 0 for good in Good}

    for tick in range(1, months + 1):
        if shock_key is not None:
            if tick == shock_start and not applied:
                shock_state = apply_shock(engine, shock_key)
                applied = True
            elif (
                applied
                and shock_state is not None
                and tick == shock_start + shock_duration
            ):
                restore_shock(engine, shock_key, shock_state)
                shock_state = None
                applied = False

        stat = engine.step()
        cumulative_deaths += stat["dead_this_month"]
        series.append(_series_row(stat, cumulative_deaths))
        for good in Good:
            if stat["production"].get(good.value, 0.0) <= 1e-9:
                zero_months_by_good[good.value] += 1
                current_zero_streak[good.value] += 1
                max_zero_streak_by_good[good.value] = max(
                    max_zero_streak_by_good[good.value],
                    current_zero_streak[good.value],
                )
            else:
                current_zero_streak[good.value] = 0

    # 若 horizon 在冲击结束前截断，恢复参数，避免误导调用方。
    if applied and shock_state is not None:
        restore_shock(engine, shock_key, shock_state)

    final = engine.stats[-1]
    return {
        "regime": regime,
        "seed": seed,
        "shock": shock_key,
        "months": months,
        "shock_start": shock_start if shock_key else None,
        "shock_duration": shock_duration if shock_key else None,
        "money_initial": engine.money_initial,
        "final_money_total": final["money_total"],
        "money_conserved": abs(final["money_total"] - engine.money_initial) < 0.01
        if not (engine.government is not None and engine.government.fiat_money)
        else None,
        "zero_months_by_good": zero_months_by_good,
        "max_zero_streak_by_good": max_zero_streak_by_good,
        "series": series,
    }


def _task(payload: dict) -> dict:
    return simulate(**payload)


def run_task(task: dict) -> dict:
    """ProcessPool 顶层入口（Windows spawn 需要可 pickle 的顶层函数）。"""
    payload = {key: value for key, value in task.items() if not key.startswith("_")}
    return _task(payload)


# ---------------------------------------------------------------------------
# 指标分析
# ---------------------------------------------------------------------------
def _by_tick(series: Sequence[dict]) -> Dict[int, dict]:
    return {int(row["tick"]): row for row in series}


def _smooth_series(
    series: Sequence[dict], key: str, window: int = 3
) -> Dict[int, dict]:
    """返回 {tick: {key: 最近 window 个月均值}} 的浅层序列。

    月度路径有很强的库存—投资周期；单月峰值会把周期相位差误读成冲击
    幅度。报告的主指标用 3 月移动平均，原始月度峰值的噪声在模型中
    仍然很大（见安慰剂带）。
    """
    values: List[float] = []
    smoothed: Dict[int, dict] = {}
    for row in series:
        values.append(float(row[key]))
        start = max(0, len(values) - window)
        smoothed[int(row["tick"])] = {
            "tick": int(row["tick"]),
            key: statistics.fmean(values[start:]),
        }
    return smoothed


def _net_window(
    base_rows: Dict[int, dict],
    shock_rows: Dict[int, dict],
    key: str,
    start_tick: int,
    end_tick: int,
) -> float:
    base_total = sum(base_rows[tick][key] for tick in range(start_tick, end_tick + 1))
    shock_total = sum(
        shock_rows[tick][key] for tick in range(start_tick, end_tick + 1)
    )
    return (
        (shock_total - base_total) / base_total * 100.0
        if abs(base_total) > 1e-9
        else 0.0
    )


def _adverse_gap(base: float, shock: float, mode: str) -> float:
    if mode == "relative_down":
        return (base - shock) / max(abs(base), 1.0)
    if mode == "relative_up":
        return (shock - base) / max(abs(base), 1.0)
    if mode == "absolute_up":
        return shock - base
    if mode == "absolute_down":
        return base - shock
    raise ValueError(mode)


def _metric_analysis(
    base_rows: Dict[int, dict],
    shock_rows: Dict[int, dict],
    key: str,
    mode: str,
    start_tick: int,
    end_tick: int,
    horizon_tick: int,
    threshold: float,
    recovery_hold: int = 3,
) -> dict:
    ticks = list(range(start_tick, horizon_tick + 1))
    gaps = [
        _adverse_gap(
            base_rows[tick][key],
            shock_rows[tick][key],
            mode,
        )
        for tick in ticks
    ]
    if not gaps:
        return {}
    peak = max(gaps)
    peak_index = gaps.index(peak)
    peak_tick = ticks[peak_index]
    tolerance = 1e-12

    half_life = None
    if peak > tolerance:
        for index in range(peak_index + 1, len(gaps)):
            if gaps[index] <= peak * 0.5:
                half_life = ticks[index] - peak_tick
                break
    else:
        half_life = 0

    # 首次恢复：冲击结束后首次连续 recovery_hold 个月落在阈值内。
    # 这可能是暂时穿回基线，之后仍可能再次偏离。
    first_recovery_tick = None
    first_recovery_months = None
    if peak <= threshold:
        first_recovery_tick = start_tick
        first_recovery_months = 0
    else:
        for index, tick in enumerate(ticks):
            if tick < end_tick:
                continue
            if index + recovery_hold > len(gaps):
                break
            if all(g <= threshold for g in gaps[index : index + recovery_hold]):
                first_recovery_tick = tick
                first_recovery_months = tick - start_tick
                break

    # 持续恢复：从某个月起，直到 horizon 结束都不再超过阈值。
    # 对混沌系统这是更严格、也更诚实的“回到基线”定义。
    recovery_tick = None
    recovery_months = None
    if peak <= threshold:
        recovery_tick = start_tick
        recovery_months = 0
    else:
        for index, tick in enumerate(ticks):
            if tick < end_tick:
                continue
            if all(g <= threshold for g in gaps[index:]):
                recovery_tick = tick
                recovery_months = tick - start_tick
                break

    return {
        "peak_adverse": peak,
        "peak_tick": peak_tick,
        "half_life_months": half_life,
        "recovery_tick": recovery_tick,
        "recovery_months_from_shock_start": recovery_months,
        "recovery_months_from_shock_end": (
            recovery_tick - end_tick if recovery_tick is not None else None
        ),
        "first_recovery_tick": first_recovery_tick,
        "first_recovery_months_from_shock_start": first_recovery_months,
        "window_max_shock": max(shock_rows[tick][key] for tick in ticks),
        "window_max_baseline": max(base_rows[tick][key] for tick in ticks),
        "window_min_shock": min(shock_rows[tick][key] for tick in ticks),
        "window_min_baseline": min(base_rows[tick][key] for tick in ticks),
        "values": {
            "baseline_start": base_rows[start_tick][key],
            "shock_start": shock_rows[start_tick][key],
            "baseline_end": base_rows[horizon_tick][key],
            "shock_end": shock_rows[horizon_tick][key],
        },
    }


def _cumulative_loss(
    base_rows: Dict[int, dict],
    shock_rows: Dict[int, dict],
    key: str,
    start_tick: int,
    horizon_tick: int,
) -> dict:
    loss = 0.0
    base_total = 0.0
    for tick in range(start_tick, horizon_tick + 1):
        base = base_rows[tick][key]
        shock = shock_rows[tick][key]
        loss += max(0.0, base - shock)
        base_total += max(0.0, base)
    return {
        "absolute": loss,
        "pct_of_baseline": loss / base_total * 100.0 if base_total > 0 else 0.0,
    }


def _zero_window_metrics(
    rows: Dict[int, dict], start_tick: int, end_tick: int
) -> dict:
    window = [rows[t] for t in range(start_tick, end_tick + 1)]
    return {
        "core_any_zero_months": sum(1 for row in window if row["zero_core"] > 0),
        "food_zero_months": sum(row["zero_food"] for row in window),
    }


def analyze_run(
    baseline: dict,
    run: dict,
    shock_start: int,
    shock_duration: int,
    months: int,
) -> dict:
    base_rows = _by_tick(baseline["series"])
    shock_rows = _by_tick(run["series"])
    base_gdp = _smooth_series(baseline["series"], "gdp")
    shock_gdp = _smooth_series(run["series"], "gdp")
    base_output = _smooth_series(baseline["series"], "output_index")
    shock_output = _smooth_series(run["series"], "output_index")
    end_tick = shock_start + shock_duration - 1
    result: Dict[str, Any] = {
        "regime": run["regime"],
        "seed": run["seed"],
        "shock": run["shock"],
        "money_conserved": run["money_conserved"],
        "window": {
            "shock_start": shock_start,
            "shock_end": end_tick,
            "horizon": months,
        },
        "zero_months_by_good": run["zero_months_by_good"],
        "max_zero_streak_by_good": run["max_zero_streak_by_good"],
    }

    gdp = _metric_analysis(
        base_gdp,
        shock_gdp,
        "gdp",
        "relative_down",
        shock_start,
        end_tick,
        months,
        threshold=0.10,
    )
    gdp["cumulative_loss"] = _cumulative_loss(
        base_rows, shock_rows, "gdp", shock_start, months
    )
    gdp["net_window_pct"] = _net_window(
        base_rows, shock_rows, "gdp", shock_start, end_tick
    )
    gdp["net_24m_pct"] = _net_window(
        base_rows, shock_rows, "gdp", shock_start, min(months, end_tick + 12)
    )
    gdp["net_full_pct"] = _net_window(
        base_rows, shock_rows, "gdp", shock_start, months
    )
    result["gdp"] = gdp
    result["gdp_raw"] = _metric_analysis(
        base_rows,
        shock_rows,
        "gdp",
        "relative_down",
        shock_start,
        end_tick,
        months,
        threshold=0.10,
    )

    output = _metric_analysis(
        base_output,
        shock_output,
        "output_index",
        "relative_down",
        shock_start,
        end_tick,
        months,
        threshold=0.10,
    )
    output["cumulative_loss"] = _cumulative_loss(
        base_rows, shock_rows, "output_index", shock_start, months
    )
    output["net_window_pct"] = _net_window(
        base_rows, shock_rows, "output_index", shock_start, end_tick
    )
    output["net_24m_pct"] = _net_window(
        base_rows,
        shock_rows,
        "output_index",
        shock_start,
        min(months, end_tick + 12),
    )
    output["net_full_pct"] = _net_window(
        base_rows, shock_rows, "output_index", shock_start, months
    )
    result["output_index"] = output
    result["output_index_raw"] = _metric_analysis(
        base_rows,
        shock_rows,
        "output_index",
        "relative_down",
        shock_start,
        end_tick,
        months,
        threshold=0.10,
    )

    result["unemployment"] = _metric_analysis(
        base_rows,
        shock_rows,
        "unemployment_rate",
        "absolute_up",
        shock_start,
        end_tick,
        months,
        threshold=0.01,
    )
    result["food_output"] = _metric_analysis(
        base_rows,
        shock_rows,
        "food_output",
        "relative_down",
        shock_start,
        end_tick,
        months,
        threshold=0.10,
    )
    result["food_price"] = _metric_analysis(
        base_rows,
        shock_rows,
        "food_price",
        "relative_up",
        shock_start,
        end_tick,
        months,
        threshold=0.10,
    )
    result["government_debt"] = _metric_analysis(
        base_rows,
        shock_rows,
        "government_debt",
        "relative_up",
        shock_start,
        end_tick,
        months,
        threshold=0.10,
    )
    result["central_bank_money"] = _metric_analysis(
        base_rows,
        shock_rows,
        "central_bank_money",
        "relative_up",
        shock_start,
        end_tick,
        months,
        threshold=0.10,
    )
    result["zero_during_shock"] = _zero_window_metrics(
        shock_rows, shock_start, end_tick
    )
    result["zero_post_shock"] = _zero_window_metrics(
        shock_rows, end_tick + 1, months
    )
    # 期末与基线相比的债务/货币差异（不是“恢复”问题，而是水平效应）。
    result["end_levels"] = {
        "baseline_gdp": base_rows[months]["gdp"],
        "shock_gdp": shock_rows[months]["gdp"],
        "baseline_unemployment": base_rows[months]["unemployment_rate"],
        "shock_unemployment": shock_rows[months]["unemployment_rate"],
        "baseline_alive": base_rows[months]["alive"],
        "shock_alive": shock_rows[months]["alive"],
        "baseline_deaths": base_rows[months]["deaths_cumulative"],
        "shock_deaths": shock_rows[months]["deaths_cumulative"],
        "baseline_government_debt": base_rows[months]["government_debt"],
        "shock_government_debt": shock_rows[months]["government_debt"],
        "baseline_central_bank_money": base_rows[months][
            "central_bank_money"
        ],
        "shock_central_bank_money": shock_rows[months]["central_bank_money"],
        "baseline_money_total": base_rows[months]["money_total"],
        "shock_money_total": shock_rows[months]["money_total"],
    }
    return result


# ---------------------------------------------------------------------------
# 聚合 / 输出
# ---------------------------------------------------------------------------
def _mean(values: Iterable[float]) -> Optional[float]:
    values = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.fmean(values) if values else None


def _min(values: Iterable[float]) -> Optional[float]:
    values = [v for v in values if v is not None and math.isfinite(v)]
    return min(values) if values else None


def _max(values: Iterable[float]) -> Optional[float]:
    values = [v for v in values if v is not None and math.isfinite(v)]
    return max(values) if values else None


def baseline_summary(baseline: dict) -> dict:
    final = baseline["series"][-1]
    start = baseline["series"][0]
    return {
        "regime": baseline["regime"],
        "seed": baseline["seed"],
        "alive": final["alive"],
        "deaths": final["deaths_cumulative"],
        "unemployment_rate": final["unemployment_rate"],
        "gdp": final["gdp"],
        "output_index": final["output_index"],
        "investment": final["investment"],
        "consumption": final["consumption"],
        "profit_rate": final["profit_rate"],
        "government_debt": final["government_debt"],
        "central_bank_money": final["central_bank_money"],
        "money_total": final["money_total"],
        "money_initial": baseline["money_initial"],
        "money_conserved": baseline["money_conserved"],
        "zero_months_by_good": baseline["zero_months_by_good"],
        "max_zero_streak_by_good": baseline["max_zero_streak_by_good"],
        "start_gdp": start["gdp"],
    }


def _scalar_summary(run_analysis: dict) -> dict:
    gdp = run_analysis["gdp"]
    output = run_analysis["output_index"]
    unemployment = run_analysis["unemployment"]
    debt = run_analysis["government_debt"]
    cb = run_analysis["central_bank_money"]
    end = run_analysis["end_levels"]
    return {
        "regime": run_analysis["regime"],
        "shock": run_analysis["shock"],
        "seed": run_analysis["seed"],
        "gdp_peak_drop_pct": gdp["peak_adverse"] * 100.0,
        "gdp_raw_peak_drop_pct": run_analysis["gdp_raw"]["peak_adverse"]
        * 100.0,
        "gdp_peak_tick": gdp["peak_tick"],
        "gdp_half_life_months": gdp["half_life_months"],
        "gdp_first_recovery_months": gdp[
            "first_recovery_months_from_shock_start"
        ],
        "gdp_recovery_months": gdp["recovery_months_from_shock_start"],
        "gdp_recovery_tick": gdp["recovery_tick"],
        "gdp_cumulative_loss": gdp["cumulative_loss"]["absolute"],
        "gdp_cumulative_loss_pct": gdp["cumulative_loss"]["pct_of_baseline"],
        "gdp_shock_window_net_pct": gdp["net_window_pct"],
        "gdp_24m_net_pct": gdp["net_24m_pct"],
        "gdp_full_net_pct": gdp["net_full_pct"],
        "output_peak_drop_pct": output["peak_adverse"] * 100.0,
        "output_raw_peak_drop_pct": run_analysis["output_index_raw"][
            "peak_adverse"
        ]
        * 100.0,
        "output_peak_tick": output["peak_tick"],
        "output_half_life_months": output["half_life_months"],
        "output_first_recovery_months": output[
            "first_recovery_months_from_shock_start"
        ],
        "output_recovery_months": output[
            "recovery_months_from_shock_start"
        ],
        "output_cumulative_loss_pct": output["cumulative_loss"][
            "pct_of_baseline"
        ],
        "output_shock_window_net_pct": output["net_window_pct"],
        "output_24m_net_pct": output["net_24m_pct"],
        "output_full_net_pct": output["net_full_pct"],
        "unemployment_baseline_start": unemployment["values"][
            "baseline_start"
        ],
        "unemployment_baseline_peak": unemployment["window_max_baseline"],
        "unemployment_shock_peak": unemployment["window_max_shock"],
        "unemployment_peak_delta_pp": (
            unemployment["window_max_shock"]
            - unemployment["window_max_baseline"]
        )
        * 100.0,
        "unemployment_baseline_end": unemployment["values"]["baseline_end"],
        "unemployment_shock_end": unemployment["values"]["shock_end"],
        "food_peak_drop_pct": run_analysis["food_output"]["peak_adverse"]
        * 100.0,
        "food_price_peak_rise_pct": run_analysis["food_price"][
            "peak_adverse"
        ]
        * 100.0,
        "core_zero_months_during_shock": run_analysis["zero_during_shock"][
            "core_any_zero_months"
        ],
        "core_zero_months_post_shock": run_analysis["zero_post_shock"][
            "core_any_zero_months"
        ],
        "food_zero_months_during_shock": run_analysis["zero_during_shock"][
            "food_zero_months"
        ],
        "government_debt_start": debt["values"]["baseline_start"],
        "government_debt_shock_end": debt["values"]["shock_end"],
        "government_debt_baseline_end": debt["values"]["baseline_end"],
        "government_debt_delta_end": (
            debt["values"]["shock_end"] - debt["values"]["baseline_end"]
        ),
        "government_debt_peak_delta_pct": debt["peak_adverse"] * 100.0,
        "central_bank_money_shock_end": cb["values"]["shock_end"],
        "central_bank_money_baseline_end": cb["values"]["baseline_end"],
        "central_bank_money_delta_end": (
            cb["values"]["shock_end"] - cb["values"]["baseline_end"]
        ),
        "alive_baseline_end": end["baseline_alive"],
        "alive_shock_end": end["shock_alive"],
        "deaths_baseline_end": end["baseline_deaths"],
        "deaths_shock_end": end["shock_deaths"],
        "baseline_end_gdp": end["baseline_gdp"],
        "shock_end_gdp": end["shock_gdp"],
        "money_conserved": run_analysis["money_conserved"],
    }


def aggregate_runs(scalars: Sequence[dict]) -> List[dict]:
    if not scalars:
        return []
    grouped: Dict[tuple, List[dict]] = {}
    for row in scalars:
        grouped.setdefault((row["regime"], row["shock"]), []).append(row)
    aggregate = []
    numeric_keys = [
        key
        for key in scalars[0]
        if key not in ("regime", "shock", "seed", "money_conserved")
    ]
    for (regime, shock), rows in sorted(grouped.items()):
        entry = {
            "regime": regime,
            "shock": shock,
            "seeds": sorted(row["seed"] for row in rows),
            "n": len(rows),
        }
        for key in numeric_keys:
            values = [row.get(key) for row in rows]
            entry[key] = _mean(values)
            entry[f"{key}_min"] = _min(values)
            entry[f"{key}_max"] = _max(values)
        entry["recovered_runs"] = sum(
            1
            for row in rows
            if row.get("gdp_recovery_months") is not None
        )
        entry["first_recovered_runs"] = sum(
            1
            for row in rows
            if row.get("gdp_first_recovery_months") is not None
        )
        entry["money_conserved_all"] = all(
            row.get("money_conserved") is not False for row in rows
        )
        aggregate.append(entry)
    return aggregate


def seed_determinism(
    baselines: Sequence[dict], analyses: Sequence[dict]
) -> dict:
    by_regime: Dict[str, List[dict]] = {}
    for baseline in baselines:
        by_regime.setdefault(baseline["regime"], []).append(
            baseline_summary(baseline)
        )
    result: Dict[str, Any] = {"baselines": {}, "runs": {}}
    for regime, rows in sorted(by_regime.items()):
        result["baselines"][regime] = {
            "seeds": sorted(row["seed"] for row in rows),
            "alive_range": max(row["alive"] for row in rows)
            - min(row["alive"] for row in rows),
            "gdp_range": max(row["gdp"] for row in rows)
            - min(row["gdp"] for row in rows),
            "unemployment_range_pp": (
                max(row["unemployment_rate"] for row in rows)
                - min(row["unemployment_rate"] for row in rows)
            )
            * 100.0,
            "deaths_range": max(row["deaths"] for row in rows)
            - min(row["deaths"] for row in rows),
        }
    grouped: Dict[tuple, List[dict]] = {}
    for analysis in analyses:
        row = _scalar_summary(analysis)
        grouped.setdefault((row["regime"], row["shock"]), []).append(row)
    for (regime, shock), rows in sorted(grouped.items()):
        result["runs"][f"{regime}/{shock}"] = {
            "seed_gdp_peak_range_pp": (
                max(row["gdp_peak_drop_pct"] for row in rows)
                - min(row["gdp_peak_drop_pct"] for row in rows)
            ),
            "seed_recovery_months_range": (
                max((row["gdp_recovery_months"] or 0) for row in rows)
                - min((row["gdp_recovery_months"] or 0) for row in rows)
            ),
            "seed_end_gdp_range": (
                max(row["shock_end_gdp"] for row in rows)
                - min(row["shock_end_gdp"] for row in rows)
            ),
            "seed_alive_range": (
                max(row["alive_shock_end"] for row in rows)
                - min(row["alive_shock_end"] for row in rows)
            ),
        }
    return result


def write_csv(path: Path, rows: Sequence[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "—"
        return f"{value:,.{digits}f}"
    return str(value)


def _fmt_pct(value: Any, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:+.{digits}f}%" if value else f"{value:.{digits}f}%"


def generate_markdown(
    metadata: dict,
    baseline_rows: Sequence[dict],
    aggregates: Sequence[dict],
    determinism: dict,
    placebo_aggregates: Sequence[dict],
    output_path: Path,
) -> None:
    lines: List[str] = []
    lines.append("# V0.4 冲击测试报告（自动生成）")
    lines.append("")
    lines.append(
        f"生成时间：{metadata['generated_at']}　"
        f"月数：{metadata['months']}　种子：{metadata['seeds']}　"
        f"冲击起点：T{metadata['shock_start']}　"
        f"冲击长度：{metadata['shock_duration']} 月"
    )
    lines.append("")
    lines.append(
        "> 本文件由 `scripts/validate_v04.py` 自动生成；方法论与局限见 "
        "`docs/VALIDATION_V0.4.md`。数值是模型输出，不是历史估计。"
    )
    lines.append("")

    lines.append("## 1. 基线（逐 seed，期末 T%s）" % metadata["months"])
    lines.append("")
    lines.append(
        "| 制度 | 存活 | 死亡 | 失业率 | GDP | 投资 | 利润率 | 政府债务 | 央行货币 | 货币守恒 |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|:---:|")
    for row in baseline_rows:
        lines.append(
            f"| {REGIME_LABELS.get(row['regime'], row['regime'])} "
            f"| {_fmt(row['alive'], 0)} | {_fmt(row['deaths'], 0)} "
            f"| {_fmt(row['unemployment_rate'] * 100, 1)}% "
            f"| {_fmt(row['gdp'], 0)} | {_fmt(row['investment'], 0)} "
            f"| {_fmt(row['profit_rate'] * 100, 2)}% "
            f"| {_fmt(row['government_debt'], 0)} "
            f"| {_fmt(row['central_bank_money'], 0)} "
            f"| {_fmt(row['money_conserved'])} |"
        )
    lines.append("")

    lines.append("## 2. 冲击—恢复汇总（种子均值）")
    lines.append("")
    lines.append(
        "| 制度 | 冲击 | GDP 冲击窗净变化 | GDP 24月净变化 | GDP 全期净变化 | "
        "GDP峰值(MA3) | 半衰期(月) | 首次恢复(月) | 持续恢复(月) | 累计低于基线 | "
        "失业率基线→冲击峰值 | 核心零产出(冲击期) | 政府债务期末差 | 央行货币期末差 |"
    )
    lines.append(
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for row in aggregates:
        lines.append(
            f"| {REGIME_LABELS.get(row['regime'], row['regime'])} "
            f"| {SHOCK_LABELS.get(row['shock'], row['shock'])} "
            f"| {_fmt_pct(row['gdp_shock_window_net_pct'], 1)} "
            f"| {_fmt_pct(row['gdp_24m_net_pct'], 1)} "
            f"| {_fmt_pct(row['gdp_full_net_pct'], 1)} "
            f"| {_fmt(row['gdp_peak_drop_pct'], 1)}% "
            f"| {_fmt(row['gdp_half_life_months'], 1)} "
            f"| {_fmt(row['gdp_first_recovery_months'], 1)} "
            f"| {_fmt(row['gdp_recovery_months'], 1)} "
            f"| {_fmt(row['gdp_cumulative_loss_pct'], 2)}% "
            f"| {_fmt(row['unemployment_baseline_peak'] * 100, 1)}% → "
            f"{_fmt(row['unemployment_shock_peak'] * 100, 1)}% "
            f"| {_fmt(row['core_zero_months_during_shock'], 1)} "
            f"| {_fmt(row['government_debt_delta_end'], 0)} "
            f"| {_fmt(row['central_bank_money_delta_end'], 0)} |"
        )
    lines.append("")
    lines.append(
        "指标口径：净变化 =（冲击路径 − 同 seed 基线路径）/ 基线路径，"
        "冲击窗 = T120–T131（12 个月），24 月 = T120–T143，全期 = T120–T240；"
        "负值表示累计低于基线。GDP 峰值/半衰期/恢复基于 3 月移动平均。"
        "首次恢复 = 冲击结束后首次连续 3 个月回到 ±10%（可能再次偏离）；"
        "持续恢复 = 从某月起直到 T240 都不再偏离 ±10%，“—”表示窗口内未持续恢复。"
        "累计低于基线只把低于基线的月份加总，因此恒为非负，受路径相位影响很大。"
        "失业率峰值为冲击窗内的月度最大值；MMT 的就业保障有“当月失业、下月吸收”"
        "的一期滞后，因此单月峰值可能包含会计时点噪声。"
    )
    lines.append("")

    lines.append("## 3. 分冲击明细（种子均值）")
    lines.append("")
    for shock in SHOCK_KEYS:
        rows = [row for row in aggregates if row["shock"] == shock]
        if not rows:
            continue
        lines.append(f"### {SHOCK_LABELS[shock]}")
        lines.append("")
        lines.append(
            "| 制度 | 产出冲击窗净变化 | 产出全期净变化 | 产出峰值(MA3) | "
            "产出半衰期 | 产出首次恢复(月) | 食品产出峰值跌幅 | "
            "食品价格峰值涨幅 | 失业率基线→冲击峰值 | 期末死亡 | 货币守恒 |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|")
        for row in rows:
            unemp_start = row["unemployment_baseline_peak"]
            unemp_peak = row["unemployment_shock_peak"]
            deaths = row["deaths_shock_end"]
            lines.append(
                f"| {REGIME_LABELS.get(row['regime'], row['regime'])} "
                f"| {_fmt_pct(row['output_shock_window_net_pct'], 1)} "
                f"| {_fmt_pct(row['output_full_net_pct'], 1)} "
                f"| {_fmt(row['output_peak_drop_pct'], 1)}% "
                f"| {_fmt(row['output_half_life_months'], 1)} "
                f"| {_fmt(row['output_first_recovery_months'], 1)} "
                f"| {_fmt(row['food_peak_drop_pct'], 1)}% "
                f"| {_fmt(row['food_price_peak_rise_pct'], 1)}% "
                f"| {_fmt(unemp_start * 100, 1)}% → {_fmt(unemp_peak * 100, 1)}% "
                f"| {_fmt(deaths, 0)} "
                f"| {_fmt(row['money_conserved_all'])} |"
            )
        lines.append("")

    lines.append("## 4. 种子稳健性")
    lines.append("")
    lines.append(
        "模型除饥饿死亡外是确定性的；同一制度/冲击下，不同 seed 的差异只来自"
        "死亡抽签。下表给出基线期末与冲击峰值的跨 seed 极差。"
    )
    lines.append("")
    lines.append("| 制度 | 存活极差 | GDP 极差 | 失业率极差(pp) | 死亡极差 |")
    lines.append("|---|---:|---:|---:|---:|")
    for regime, info in determinism.get("baselines", {}).items():
        lines.append(
            f"| {REGIME_LABELS.get(regime, regime)} "
            f"| {_fmt(info['alive_range'], 0)} "
            f"| {_fmt(info['gdp_range'], 2)} "
            f"| {_fmt(info['unemployment_range_pp'], 3)} "
            f"| {_fmt(info['deaths_range'], 0)} |"
        )
    lines.append("")

    lines.append("## 5. 混沌 / 安慰剂带")
    lines.append("")
    lines.append(
        "模型存在很强的内生库存—投资周期；即使只施加 1% 需求扰动或 1bp 信贷扰动，"
        "同一路径也会在数月后与基线明显分叉。下表给出这些安慰剂扰动的量级，"
        "用于判断主冲击的峰值/净变化是否超出“混沌噪声带”。"
    )
    lines.append("")
    if placebo_aggregates:
        lines.append(
            "| 制度 | 安慰剂 | GDP峰值(MA3) | GDP冲击窗净变化 | GDP 24月净变化 | 产出冲击窗净变化 |"
        )
        lines.append("|---|---|---:|---:|---:|---:|")
        for row in placebo_aggregates:
            lines.append(
                f"| {REGIME_LABELS.get(row['regime'], row['regime'])} "
                f"| {PLACEBO_DEFINITIONS.get(row['shock'], {}).get('label', row['shock'])} "
                f"| {_fmt(row['gdp_peak_drop_pct'], 1)}% "
                f"| {_fmt_pct(row['gdp_shock_window_net_pct'], 1)} "
                f"| {_fmt_pct(row['gdp_24m_net_pct'], 1)} "
                f"| {_fmt_pct(row['output_shock_window_net_pct'], 1)} |"
            )
        lines.append("")
        lines.append(
            "解读：安慰剂带的峰值可以达到主冲击峰值的同一量级；因此本报告不把"
            "单路径峰值当作精确冲击乘数。冲击窗净变化和方向性（失业、零产出、"
            "债务/货币）比峰值更可信。"
        )
    else:
        lines.append("本次运行使用 `--no-placebo`，未估计混沌噪声带。")
    lines.append("")

    lines.append("## 6. 自动读数")
    lines.append("")
    finding_lines = _auto_findings(aggregates, placebo_aggregates)
    lines.extend(finding_lines)
    lines.append("")

    lines.append("## 7. 冲击定义")
    lines.append("")
    for shock in SHOCK_KEYS:
        definition = SHOCK_DEFINITIONS[shock]
        lines.append(
            f"- **{definition['label']}**（{definition['duration']} 个月）："
            f"{definition['description']}"
        )
    lines.append("")
    lines.append("## 8. 局限")
    lines.append("")
    lines.append(
        "- 模型除饥饿死亡抽签外是确定性的，但存在强内生周期：参数/冲击的微小"
        "扰动即可让路径在数月后大幅分叉（见第 5 节）。3 个 seed 不能刻画"
        "这种路径不确定性；需要 20–100 个 seed 或冲击起点集成。"
    )
    lines.append(
        "- 只有 9 个行业，没有服务业/非正规部门；因此失业率和劳动吸收能力"
        "被结构性高估/低估，冲击传导也缺少服务业的缓冲。"
    )
    lines.append(
        "- L2 的 markup/LES 仍是实验分支，默认是固定温饱篮子 + 价格带；"
        "价格和工资仍有临时安全阀。"
    )
    lines.append(
        "- 银行/政府资产负债表是简化版：MMT 的央行与财政部合并记账，"
        "没有完整国债期限结构和银行资本。"
    )
    lines.append(
        "- 信贷冲击主要通过利率、放贷比例和冻结准备金传导；模型中企业"
        "工资缺口贷款规模很小，且没有抵押品/风险溢价/企业债券，"
        "信贷渠道本身较弱。"
    )
    lines.append(
        "- MMT 的就业保障在每月劳动市场末尾吸收失业者；被解雇者会有"
        "一个月计入失业，因此单月失业率会冒出 1–5% 的时点峰值。"
    )
    lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _auto_findings(
    aggregates: Sequence[dict],
    placebo_aggregates: Sequence[dict] = (),
) -> List[str]:
    lines: List[str] = []
    for shock in SHOCK_KEYS:
        rows = [row for row in aggregates if row["shock"] == shock]
        if not rows:
            continue
        ranked = sorted(rows, key=lambda row: row["gdp_shock_window_net_pct"])
        parts = ", ".join(
            f"{REGIME_LABELS.get(row['regime'], row['regime'])} "
            f"{row['gdp_shock_window_net_pct']:+.1f}%"
            for row in ranked
        )
        lines.append(
            f"- {SHOCK_LABELS[shock]}的 GDP 冲击窗净变化（相对基线）：{parts}。"
        )
        if shock == "productivity":
            output_parts = ", ".join(
                f"{REGIME_LABELS.get(row['regime'], row['regime'])} "
                f"{row['output_shock_window_net_pct']:+.1f}%"
                for row in sorted(
                    rows, key=lambda row: row["output_shock_window_net_pct"]
                )
            )
            lines.append(
                f"  - 物量产出冲击窗净变化：{output_parts}；名义 GDP 可能因"
                "价格上升而掩盖物量下降，因此生产率冲击应看产出指数。"
            )
        recovered = sum(
            1 for row in rows if row["gdp_recovery_months"] is not None
        )
        lines.append(
            f"  - {recovered}/{len(rows)} 个制度×seed 组合在 T240 前实现"
            "持续恢复（3 月移动平均不再偏离 ±10%）。"
        )
        if max(row["gdp_peak_drop_pct"] for row in rows) < 1.0:
            lines.append(
                "  - 该冲击的峰值影响小于 1%，说明当前模型对这条渠道不敏感；"
                "这是模型局限，不应解读为现实经济中该渠道无效。"
            )
    if placebo_aggregates:
        worst = max(
            row["gdp_peak_drop_pct"] for row in placebo_aggregates
        )
        lines.append(
            f"- 安慰剂带：1% 需求/1bp 信贷扰动的 GDP 峰值(MA3)最高可达 "
            f"{worst:.1f}%，与主冲击峰值同量级；因此单路径峰值不能当作"
            "精确的冲击乘数。"
        )
    lines.append(
        "- 若 MMT 的失业率在冲击期仍接近 0%，说明就业保障确实在吸收冲击，"
        "但应同时看政府债务/央行货币的期末差，而不是只看失业率。"
    )
    return lines


def _default_output_dir() -> Path:
    return ROOT / "artifacts" / "validation"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="V0.4 三制度基线 + 需求/生产率/信贷冲击验证"
    )
    parser.add_argument("--months", type=int, default=240)
    parser.add_argument("--shock-start", type=int, default=120)
    parser.add_argument("--shock-duration", type=int, default=12)
    parser.add_argument(
        "--seeds", type=int, nargs="+", default=[1, 2, 3], help="3–5 个 seed"
    )
    parser.add_argument(
        "--regimes",
        nargs="+",
        choices=sorted(CONFIGS),
        default=sorted(CONFIGS),
    )
    parser.add_argument(
        "--shocks",
        nargs="+",
        choices=list(SHOCK_KEYS),
        default=list(SHOCK_KEYS),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_default_output_dir()
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="并行进程数；1 = 串行（便于调试）",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="仅用于冒烟测试：每个制度/冲击只跑一个 seed，且不再并行",
    )
    parser.add_argument(
        "--no-series-in-json",
        action="store_true",
        help="JSON 中不保存逐月序列（只保留摘要）",
    )
    parser.add_argument(
        "--no-placebo",
        action="store_true",
        help="跳过 1%% 需求/1bp 信贷安慰剂扰动（默认运行，用于估计混沌噪声带）",
    )
    args = parser.parse_args(argv)

    if args.months <= args.shock_start + args.shock_duration:
        parser.error("--months 必须大于 shock_start + shock_duration")
    if not (3 <= len(args.seeds) <= 5) and not args.fast:
        parser.error("按交付要求请使用 3–5 个 seed（或加 --fast 做冒烟测试）")
    if args.fast:
        args.seeds = args.seeds[:1]
        args.jobs = 1

    started = time.perf_counter()
    tasks: List[dict] = []
    for regime in args.regimes:
        for seed in args.seeds:
            tasks.append(
                {
                    "regime": regime,
                    "seed": seed,
                    "months": args.months,
                    "shock_key": None,
                    "shock_start": args.shock_start,
                    "shock_duration": args.shock_duration,
                    "_kind": "baseline",
                }
            )
            for shock in args.shocks:
                tasks.append(
                    {
                        "regime": regime,
                        "seed": seed,
                        "months": args.months,
                        "shock_key": shock,
                        "shock_start": args.shock_start,
                        "shock_duration": args.shock_duration,
                        "_kind": "shock",
                    }
                )
    if not args.no_placebo:
        # 安慰剂只用第一个 seed：Keynesian/MMT 无死亡时逐路径完全相同；
        # classical 的 seed 差异来自死亡，不用于估计参数扰动的混沌带。
        for regime in args.regimes:
            for shock in PLACEBO_KEYS:
                tasks.append(
                    {
                        "regime": regime,
                        "seed": args.seeds[0],
                        "months": args.months,
                        "shock_key": shock,
                        "shock_start": args.shock_start,
                        "shock_duration": args.shock_duration,
                        "_kind": "placebo",
                    }
                )

    results: List[dict] = []
    total = len(tasks)
    print(
        f"[validate_v04] {total} 条路径 × {args.months} 月，"
        f"regimes={args.regimes}, seeds={args.seeds}, shocks={args.shocks}, "
        f"jobs={args.jobs}",
        flush=True,
    )

    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as executor:
            futures = {executor.submit(run_task, task): task for task in tasks}
            for index, future in enumerate(as_completed(futures), start=1):
                task = futures[future]
                result = future.result()
                results.append(result)
                label = task["_kind"]
                print(
                    f"[{index}/{total}] {task['regime']} seed={task['seed']} "
                    f"{label}{'' if task['shock_key'] is None else '/' + task['shock_key']} "
                    f"({time.perf_counter() - started:.1f}s)",
                    flush=True,
                )
    else:
        for index, task in enumerate(tasks, start=1):
            result = run_task(task)
            results.append(result)
            label = task["_kind"]
            print(
                f"[{index}/{total}] {task['regime']} seed={task['seed']} "
                f"{label}{'' if task['shock_key'] is None else '/' + task['shock_key']} "
                f"({time.perf_counter() - started:.1f}s)",
                flush=True,
            )

    baselines = [result for result in results if result["shock"] is None]
    shock_runs = [result for result in results if result["shock"] in SHOCK_KEYS]
    placebo_runs = [
        result for result in results if result["shock"] in PLACEBO_KEYS
    ]
    baseline_by_key = {
        (result["regime"], result["seed"]): result for result in baselines
    }
    analyses = [
        analyze_run(
            baseline_by_key[(result["regime"], result["seed"])],
            result,
            args.shock_start,
            args.shock_duration,
            args.months,
        )
        for result in shock_runs
    ]
    scalars = [_scalar_summary(analysis) for analysis in analyses]
    aggregates = aggregate_runs(scalars)
    regime_order = {name: index for index, name in enumerate(sorted(CONFIGS))}
    shock_order = {name: index for index, name in enumerate(SHOCK_KEYS)}
    aggregates.sort(
        key=lambda row: (
            regime_order.get(row["regime"], 99),
            shock_order.get(row["shock"], 99),
        )
    )
    placebo_analyses = [
        analyze_run(
            baseline_by_key[(result["regime"], result["seed"])],
            result,
            args.shock_start,
            args.shock_duration,
            args.months,
        )
        for result in placebo_runs
    ]
    placebo_scalars = [
        _scalar_summary(analysis) for analysis in placebo_analyses
    ]
    placebo_aggregates = aggregate_runs(placebo_scalars)
    placebo_aggregates.sort(
        key=lambda row: (
            regime_order.get(row["regime"], 99),
            PLACEBO_KEYS.index(row["shock"]),
        )
    )
    baseline_rows = [baseline_summary(result) for result in baselines]
    determinism = seed_determinism(baselines, analyses)

    # 基线 CSV / JSON
    args.output_dir.mkdir(parents=True, exist_ok=True)
    baseline_fields = [
        "regime",
        "seed",
        "alive",
        "deaths",
        "unemployment_rate",
        "gdp",
        "output_index",
        "investment",
        "consumption",
        "profit_rate",
        "government_debt",
        "central_bank_money",
        "money_total",
        "money_initial",
        "money_conserved",
    ]
    write_csv(
        args.output_dir / "baselines_240m.csv",
        baseline_rows,
        baseline_fields,
    )
    (args.output_dir / "baselines_240m.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "months": args.months,
                    "seeds": args.seeds,
                    "regimes": args.regimes,
                },
                "baselines": baseline_rows,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    scalar_fields = [
        "regime",
        "shock",
        "seed",
        "gdp_peak_drop_pct",
        "gdp_raw_peak_drop_pct",
        "gdp_peak_tick",
        "gdp_half_life_months",
        "gdp_first_recovery_months",
        "gdp_recovery_months",
        "gdp_recovery_tick",
        "gdp_cumulative_loss",
        "gdp_cumulative_loss_pct",
        "gdp_shock_window_net_pct",
        "gdp_24m_net_pct",
        "gdp_full_net_pct",
        "output_peak_drop_pct",
        "output_raw_peak_drop_pct",
        "output_peak_tick",
        "output_half_life_months",
        "output_first_recovery_months",
        "output_recovery_months",
        "output_cumulative_loss_pct",
        "output_shock_window_net_pct",
        "output_24m_net_pct",
        "output_full_net_pct",
        "unemployment_baseline_start",
        "unemployment_baseline_peak",
        "unemployment_shock_peak",
        "unemployment_peak_delta_pp",
        "unemployment_baseline_end",
        "unemployment_shock_end",
        "food_peak_drop_pct",
        "food_price_peak_rise_pct",
        "core_zero_months_during_shock",
        "core_zero_months_post_shock",
        "food_zero_months_during_shock",
        "government_debt_start",
        "government_debt_shock_end",
        "government_debt_baseline_end",
        "government_debt_delta_end",
        "government_debt_peak_delta_pct",
        "central_bank_money_shock_end",
        "central_bank_money_baseline_end",
        "central_bank_money_delta_end",
        "alive_baseline_end",
        "alive_shock_end",
        "baseline_end_gdp",
        "shock_end_gdp",
        "deaths_baseline_end",
        "deaths_shock_end",
        "money_conserved",
    ]
    write_csv(
        args.output_dir / "shock_summary.csv",
        sorted(
            scalars,
            key=lambda row: (row["regime"], row["shock"], row["seed"]),
        ),
        scalar_fields,
    )
    write_csv(
        args.output_dir / "shock_aggregates.csv",
        aggregates,
        ["regime", "shock", "n"]
        + [
            field
            for field in aggregates[0]
            if field
            not in (
                "regime",
                "shock",
                "n",
                "seeds",
            )
        ]
        if aggregates
        else ["regime", "shock"],
    )
    if placebo_scalars:
        write_csv(
            args.output_dir / "placebo_summary.csv",
            sorted(
                placebo_scalars,
                key=lambda row: (row["regime"], row["shock"]),
            ),
            scalar_fields,
        )

    # JSON：所有 seed 的摘要；默认只保存 seed=1 的逐月序列以控制体积。
    pruned_baselines = []
    for result in baselines:
        item = {k: v for k, v in result.items() if k != "series"}
        if not args.no_series_in_json and result["seed"] == args.seeds[0]:
            item["series"] = result["series"]
        pruned_baselines.append(item)
    pruned_shock_runs = []
    for result in shock_runs:
        item = {k: v for k, v in result.items() if k != "series"}
        if not args.no_series_in_json and result["seed"] == args.seeds[0]:
            item["series"] = result["series"]
        pruned_shock_runs.append(item)

    payload = {
        "metadata": {
            "script": "scripts/validate_v04.py",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "months": args.months,
            "shock_start": args.shock_start,
            "shock_duration": args.shock_duration,
            "seeds": args.seeds,
            "regimes": args.regimes,
            "shocks": args.shocks,
            "series_included_for_seed": (
                None if args.no_series_in_json else args.seeds[0]
            ),
            "runtime_seconds": round(time.perf_counter() - started, 2),
            "determinism_note": (
                "模型除饥饿死亡外是确定性的；seed 差异只来自死亡抽签。"
            ),
        },
        "shock_definitions": SHOCK_DEFINITIONS,
        "placebo_definitions": PLACEBO_DEFINITIONS,
        "metric_definitions": {
            "gdp": "月度市场交易 GDP = 消费 + 投资 + 政府市场支出",
            "output_index": "按初始价格加权的物量产出指数（固定价格）",
            "peak_drop_pct": "冲击窗口内相对基线的最大不利偏离",
            "half_life_months": "从谷底恢复到峰值缺口一半所需月数",
            "recovery_months": "从冲击开始月恢复到基线 ±10% 并保持 3 个月所需月数",
            "cumulative_loss_pct": "冲击开始至 240 月累计低于基线的 GDP 占基线累计 GDP 的比例",
            "zero_core": "钢/砖/纺织/机械/建筑中任一行业月产量为 0",
        },
        "baselines": pruned_baselines,
        "shock_runs": pruned_shock_runs,
        "analyses": analyses,
        "aggregates": aggregates,
        "placebo_analyses": placebo_analyses,
        "placebo_aggregates": placebo_aggregates,
        "seed_determinism": determinism,
    }
    (args.output_dir / "shock_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    generate_markdown(
        {
            "generated_at": payload["metadata"]["generated_at"],
            "months": args.months,
            "seeds": args.seeds,
            "shock_start": args.shock_start,
            "shock_duration": args.shock_duration,
        },
        baseline_rows,
        aggregates,
        determinism,
        placebo_aggregates,
        args.output_dir / "shock_report.md",
    )

    print()
    print("最终摘要（种子均值）")
    header = (
        "制度      冲击         冲击窗净  24月净   全期净   峰值MA3  半衰期  "
        "持续恢复  累计损失%  失业峰值  核心零产出"
    )
    print(header)
    for row in aggregates:
        print(
            f"{row['regime']:<10} {row['shock']:<12} "
            f"{row['gdp_shock_window_net_pct']:>+8.1f}% "
            f"{row['gdp_24m_net_pct']:>+8.1f}% "
            f"{row['gdp_full_net_pct']:>+8.1f}% "
            f"{row['gdp_peak_drop_pct']:>7.1f}% "
            f"{_fmt(row['gdp_half_life_months'], 1):>6} "
            f"{_fmt(row['gdp_recovery_months'], 1):>8} "
            f"{row['gdp_cumulative_loss_pct']:>8.2f}% "
            f"{row['unemployment_shock_peak'] * 100:>7.1f}% "
            f"{row['core_zero_months_during_shock']:>7.1f}"
        )
    print()
    print(f"已写入 {args.output_dir}")
    print(f"总耗时 {time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
