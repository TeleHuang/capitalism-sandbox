#!/usr/bin/env python3
"""本地 V0.4 经济驾驶舱服务（Python 标准库，无 FastAPI 依赖）。

启动：
  PYTHONPATH=src python scripts/serve_dashboard.py --port 8765
  （脚本自己会把 src/ 加入 sys.path，因此可以直接 python scripts/serve_dashboard.py）

接口：
  GET /api/run?regime=classical|keynesian|mmt&months=240&seed=1
  GET /api/compare?months=240&seed=1
  GET /api/health

前端：web/v04/index.html + app.js + styles.css，通过 fetch 调用上述接口。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web" / "v04"
sys.path.insert(0, str(ROOT / "src"))

from ecosim.config import SECTOR_PARAMS  # noqa: E402
from ecosim.engine import Engine  # noqa: E402
from ecosim.enums import GOOD_LABELS, Good, Industry  # noqa: E402
from ecosim.scenarios import (  # noqa: E402
    CLASSICAL_LAISSEZ_FAIRE,
    KEYNESIAN_WELFARE,
    MMT_SOVEREIGN,
    ScenarioConfig,
    build_scenario_1,
)

DASHBOARD_VERSION = "0.4.2"
DEFAULT_MONTHS = 240
DEFAULT_SEED = 1
MAX_MONTHS = 1200
MAX_CACHE_ENTRIES = 12

REGIME_SPECS: tuple[tuple[str, str, ScenarioConfig], ...] = (
    ("classical", "古典", CLASSICAL_LAISSEZ_FAIRE),
    ("keynesian", "凯恩斯", KEYNESIAN_WELFARE),
    ("mmt", "MMT", MMT_SOVEREIGN),
)
REGIME_IDS = {regime_id for regime_id, _, _ in REGIME_SPECS}
REGIME_BY_ID = {
    regime_id: (label, config)
    for regime_id, label, config in REGIME_SPECS
}

INDUSTRY_LABELS = {
    "agriculture": "农业",
    "coal_mine": "煤矿",
    "iron_mine": "铁矿",
    "steel_mill": "钢铁",
    "brick_factory": "砖窑",
    "textile_mill": "纺织",
    "machinery_factory": "机械",
    "construction": "建筑",
    "fertilizer_factory": "化肥",
    "service": "服务",
}

SCALAR_FIELDS = (
    "alive",
    "dead_this_month",
    "unemployed",
    "unemployment_rate",
    "active_enterprises",
    "money_total",
    "bank_cash",
    "bank_loans",
    "bank_write_offs",
    "bank_deposits",
    "bank_equity",
    "government_cash",
    "government_debt",
    "government_tax_revenue",
    "government_transfers",
    "government_spending",
    "government_market_spending",
    "government_deficit",
    "government_interest_paid",
    "government_public_investment_budget",
    "government_public_capital",
    "government_jg_workers",
    "central_bank_money",
    "revenue",
    "input_costs",
    "wages",
    "interest",
    "depreciation",
    "profit",
    "gdp",
    "consumption",
    "investment",
    "profit_rate",
    "all_profit_rate",
    "capitalist_profit",
    "household_profit",
    "capitalist_capital_stock",
    "household_capital",
    "capital_stock",
    "food_reserve",
    "food_reserve_cash",
    "average_markup",
)

GOOD_FIELDS = (
    "prices",
    "production",
    "volumes",
    "demand",
    "supply",
    "inventory",
    "price_floors",
    "price_ceilings",
    "zero_output_streak",
)

INDUSTRY_FIELDS = (
    "firms",
    "workers_by_industry",
    "active_projects",
)

COMPARE_METRICS = (
    "alive",
    "unemployment_rate",
    "gdp",
    "investment",
    "profit_rate",
    "government_debt",
    "central_bank_money",
    "government_jg_workers",
    "food_reserve",
)

SCALAR_RATE_FIELDS = {
    "unemployment_rate",
    "profit_rate",
    "average_markup",
}

INTEGER_FIELDS = {
    "alive",
    "dead_this_month",
    "unemployed",
    "active_enterprises",
    "government_jg_workers",
}


class ApiError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _rounded(value: Any, field: str) -> float | int:
    if field in INTEGER_FIELDS:
        return int(round(_finite_float(value)))
    if field in SCALAR_RATE_FIELDS:
        digits = 6
    elif field == "zero_output_streak":
        return int(round(_finite_float(value)))
    else:
        digits = 4
    number = round(_finite_float(value), digits)
    if abs(number) < 10 ** (-(digits + 2)):
        return 0.0
    return number


def _collect_keys(stats: list[dict], fields: tuple[str, ...]) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for stat in stats:
        for field in fields:
            mapping = stat.get(field) or {}
            if not isinstance(mapping, dict):
                continue
            for key in mapping:
                if key not in seen:
                    seen.add(key)
                    keys.append(str(key))
    return keys


def _good_label(key: str) -> str:
    try:
        return GOOD_LABELS[Good(key)]
    except (ValueError, KeyError):
        return key.replace("_", " ")


def _industry_output(key: str) -> str | None:
    try:
        industry = Industry(key)
    except ValueError:
        return None
    params = SECTOR_PARAMS.get(industry)
    if params is None:
        return None
    output = getattr(params, "output", None)
    return output.value if hasattr(output, "value") else None


def _industry_label(key: str) -> str:
    return INDUSTRY_LABELS.get(key, key.replace("_", " "))


def _supplement(engine: Engine) -> dict[str, float]:
    """stats 之外、但诊断表需要的银行/政府账户字段。"""
    loans = sum(engine.bank.loans.values())
    deposits = sum(engine.bank.deposits.values())
    government = engine.government
    return {
        "bank_equity": engine.bank.cash + loans - deposits,
        "government_interest_paid": (
            government.interest_paid if government is not None else 0.0
        ),
        "government_public_investment_budget": (
            government.public_investment_budget if government is not None else 0.0
        ),
        "government_public_capital": (
            government.public_capital if government is not None else 0.0
        ),
    }


def _regime_metadata(
    regime_id: str,
    label: str,
    config: ScenarioConfig,
    money_initial: float | None = None,
) -> dict[str, Any]:
    return {
        "id": regime_id,
        "label": label,
        "name": config.name,
        "policy_regime": config.policy_regime.value,
        "money_regime": config.money_regime.value,
        "price_regime": config.price_regime,
        "demand_regime": config.demand_regime,
        "bank_intermediation": bool(config.bank_intermediation),
        "tax_rate_wage": config.tax_rate_wage,
        "tax_rate_profit": config.tax_rate_profit,
        "ui_replacement": config.ui_replacement,
        "ui_duration": config.ui_duration,
        "public_investment_rate": config.public_investment_rate,
        "public_investment_countercyclical": config.public_investment_countercyclical,
        "job_guarantee": bool(config.job_guarantee),
        "jg_wage": config.jg_wage,
        "jg_max_workers": config.jg_max_workers,
        "government_cash": config.government_cash,
        "money_initial": round(money_initial, 4) if money_initial is not None else None,
    }


def _all_regime_metadata(current_id: str, money_initial: float) -> list[dict[str, Any]]:
    return [
        _regime_metadata(
            regime_id,
            label,
            config,
            money_initial if regime_id == current_id else None,
        )
        for regime_id, label, config in REGIME_SPECS
    ]


def _extract_payload(
    regime_id: str,
    months: int,
    seed: int,
    stats: list[dict],
    supplements: list[dict[str, float]],
    money_initial: float,
    elapsed_seconds: float,
) -> dict[str, Any]:
    goods = _collect_keys(stats, GOOD_FIELDS)
    industries = _collect_keys(stats, INDUSTRY_FIELDS)
    goods_set = set(goods)

    scalar_series: dict[str, list[float | int]] = {
        field: [] for field in SCALAR_FIELDS
    }
    good_series: dict[str, dict[str, list[float | int]]] = {
        field: {good: [] for good in goods} for field in GOOD_FIELDS
    }
    industry_series: dict[str, dict[str, list[int]]] = {
        field: {industry: [] for industry in industries}
        for field in INDUSTRY_FIELDS
    }
    warnings_by_month: list[list[str]] = []

    for index, stat in enumerate(stats):
        supplement = supplements[index] if index < len(supplements) else {}
        for field in SCALAR_FIELDS:
            raw = stat.get(field)
            if raw is None:
                raw = supplement.get(field, 0.0)
            scalar_series[field].append(_rounded(raw, field))
        for field in GOOD_FIELDS:
            mapping = stat.get(field) or {}
            for good in goods:
                raw = mapping.get(good, 0.0) if isinstance(mapping, dict) else 0.0
                good_series[field][good].append(_rounded(raw, field))
        for field in INDUSTRY_FIELDS:
            mapping = stat.get(field) or {}
            for industry in industries:
                raw = mapping.get(industry, 0.0) if isinstance(mapping, dict) else 0.0
                industry_series[field][industry].append(_rounded(raw, field))
        raw_warnings = stat.get("warnings") or []
        deduped: list[str] = []
        if isinstance(raw_warnings, (list, tuple)):
            for warning in raw_warnings:
                text = str(warning)
                if text not in deduped:
                    deduped.append(text)
        warnings_by_month.append(deduped)

    label, config = REGIME_BY_ID[regime_id]
    good_meta = [{"id": good, "label": _good_label(good)} for good in goods]
    industry_meta = []
    for industry in industries:
        output = _industry_output(industry)
        if output is not None and output not in goods_set:
            output = industry if industry in goods_set else None
        industry_meta.append(
            {
                "id": industry,
                "label": _industry_label(industry),
                "output": output,
            }
        )

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "meta": {
            "title": "EcoSim V0.4 经济驾驶舱",
            "version": DASHBOARD_VERSION,
            "months": months,
            "seed": seed,
            "generated_at": generated_at,
            "engine": "Engine + build_scenario_1",
            "goods": good_meta,
            "industries": industry_meta,
            "regimes": _all_regime_metadata(regime_id, money_initial),
            "active_regime": regime_id,
            "config": _regime_metadata(regime_id, label, config, money_initial),
            "command": (
                f"GET /api/run?regime={regime_id}&months={months}&seed={seed}"
            ),
        },
        "regime": regime_id,
        "money_initial": round(money_initial, 4),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "scalars": scalar_series,
        "goods": good_series,
        "industries": industry_series,
        "warnings": warnings_by_month,
    }


def _execute_run(regime_id: str, months: int, seed: int) -> dict[str, Any]:
    label, config = REGIME_BY_ID[regime_id]
    started = time.monotonic()
    print(
        f"[run] regime={regime_id} months={months} seed={seed} ...",
        flush=True,
    )
    engine = Engine(seed=seed)
    build_scenario_1(engine, config=config)
    money_initial = float(engine.money_initial)
    supplements: list[dict[str, float]] = []
    for _ in range(months):
        engine.step()
        supplements.append(_supplement(engine))
    elapsed = time.monotonic() - started
    payload = _extract_payload(
        regime_id,
        months,
        seed,
        engine.stats,
        supplements,
        money_initial,
        elapsed,
    )
    final = engine.stats[-1]
    print(
        f"[run] regime={regime_id} done in {elapsed:.1f}s: "
        f"alive={final['alive']} gdp={final['gdp']:.0f}",
        flush=True,
    )
    return payload


def _build_compare_payload(
    service: "RunService", months: int, seed: int
) -> dict[str, Any]:
    started = time.monotonic()
    runs: dict[str, dict[str, Any]] = {}
    for regime_id, label, _ in REGIME_SPECS:
        print(f"[compare] collecting {regime_id} ...", flush=True)
        runs[regime_id] = service.get_run(regime_id, months, seed)

    first = runs[REGIME_SPECS[0][0]]
    meta = dict(first["meta"])
    meta["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    meta["regimes"] = [
        _regime_metadata(
            regime_id,
            label,
            config,
            _finite_float(runs[regime_id].get("money_initial")),
        )
        for regime_id, label, config in REGIME_SPECS
    ]
    meta["command"] = f"GET /api/compare?months={months}&seed={seed}"
    meta["active_regime"] = None

    monthly: dict[str, dict[str, list[float | int]]] = {}
    summary: dict[str, dict[str, Any]] = {}
    for regime_id, label, config in REGIME_SPECS:
        run = runs[regime_id]
        scalars = run.get("scalars") or {}
        monthly[regime_id] = {
            metric: list(scalars.get(metric) or []) for metric in COMPARE_METRICS
        }
        final_index = max(0, months - 1)
        final = {
            metric: (scalars.get(metric) or [0])[final_index]
            if scalars.get(metric)
            else 0
            for metric in COMPARE_METRICS
        }
        deaths = sum(_finite_float(value) for value in scalars.get("dead_this_month", []))
        zero_output_months: dict[str, int] = {}
        for good in first["meta"]["goods"]:
            series = (run.get("goods", {}).get("production", {}) or {}).get(
                good["id"], []
            )
            zero_output_months[good["id"]] = sum(
                1 for value in series if _finite_float(value) <= 1e-9
            )
        money_initial = _finite_float(run.get("money_initial"))
        money_total_series = scalars.get("money_total") or []
        money_total = _finite_float(money_total_series[-1]) if money_total_series else 0.0
        summary[regime_id] = {
            "label": label,
            "final": final,
            "deaths": int(round(deaths)),
            "zero_output_months": zero_output_months,
            "money_initial": round(money_initial, 4),
            "money_total": round(money_total, 4),
            "money_conserved": (
                abs(money_total - money_initial) <= 0.01
                if config.money_regime.value == "gold"
                else None
            ),
        }

    return {
        "meta": meta,
        "monthly": monthly,
        "summary": summary,
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }


class RunService:
    """负责实际仿真与缓存。

    一个前端页面通常会先请求一个制度，再在后台预取另外两个；
    缓存让 /api/compare 和切换制度不再重复跑 240 个月。
    """

    def __init__(self) -> None:
        self._cache: OrderedDict[tuple[str, int, int], dict[str, Any]] = OrderedDict()
        self._compare_cache: OrderedDict[tuple[int, int], dict[str, Any]] = OrderedDict()
        self._locks: dict[tuple[str, int, int], threading.Lock] = {}
        self._compare_locks: dict[tuple[int, int], threading.Lock] = {}
        self._guard = threading.Lock()

    def _run_lock(self, key: tuple[str, int, int]) -> threading.Lock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def _compare_lock(self, key: tuple[int, int]) -> threading.Lock:
        with self._guard:
            lock = self._compare_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._compare_locks[key] = lock
            return lock

    def get_run(self, regime_id: str, months: int, seed: int) -> dict[str, Any]:
        key = (regime_id, months, seed)
        lock = self._run_lock(key)
        with lock:
            with self._guard:
                cached = self._cache.get(key)
                if cached is not None:
                    self._cache.move_to_end(key)
                    cached = dict(cached)
                    cached["cached"] = True
                    return cached
            payload = _execute_run(regime_id, months, seed)
            payload["cached"] = False
            with self._guard:
                self._cache[key] = payload
                self._cache.move_to_end(key)
                while len(self._cache) > MAX_CACHE_ENTRIES:
                    self._cache.popitem(last=False)
            result = dict(payload)
            return result

    def get_compare(self, months: int, seed: int) -> dict[str, Any]:
        key = (months, seed)
        lock = self._compare_lock(key)
        with lock:
            with self._guard:
                cached = self._compare_cache.get(key)
                if cached is not None:
                    self._compare_cache.move_to_end(key)
                    cached = dict(cached)
                    cached["cached"] = True
                    return cached
            payload = _build_compare_payload(self, months, seed)
            payload["cached"] = False
            with self._guard:
                self._compare_cache[key] = payload
                self._compare_cache.move_to_end(key)
                while len(self._compare_cache) > 3:
                    self._compare_cache.popitem(last=False)
            return dict(payload)


SERVICE: RunService


def _query_int(
    query: dict[str, list[str]],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = query.get(name, [str(default)])[-1]
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ApiError(HTTPStatus.BAD_REQUEST, f"{name} 必须是整数")
    if not minimum <= value <= maximum:
        raise ApiError(
            HTTPStatus.BAD_REQUEST,
            f"{name} 必须在 {minimum} 到 {maximum} 之间",
        )
    return value


def _common_params(query: dict[str, list[str]]) -> tuple[int, int]:
    months = _query_int(query, "months", DEFAULT_MONTHS, 1, MAX_MONTHS)
    seed = _query_int(query, "seed", DEFAULT_SEED, -(2**31), 2**31 - 1)
    return months, seed


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "EcoSimDashboard/0.4"
    sys_version = ""

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(
        self,
        text: str,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        static = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
        }
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            return
        item = static.get(path)
        if item is None:
            self._send_text(
                "404 · 只提供 /、/index.html、/app.js、/styles.css 和 /api/*",
                HTTPStatus.NOT_FOUND,
            )
            return
        file_name, content_type = item
        target = (WEB_DIR / file_name).resolve()
        if not target.is_file() or WEB_DIR.resolve() not in target.parents:
            self._send_text("静态文件不可用", HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        parsed = urlparse(self.path)
        if parsed.path in ("/api/run", "/api/compare", "/api/health"):
            self._handle_api(parsed)
            return
        self._serve_static(parsed.path)

    def _handle_api(self, parsed) -> None:
        query = parse_qs(parsed.query, keep_blank_values=False)
        try:
            if parsed.path == "/api/health":
                self._send_json(
                    {
                        "ok": True,
                        "version": DASHBOARD_VERSION,
                        "cache_entries": len(SERVICE._cache),
                        "compare_entries": len(SERVICE._compare_cache),
                    }
                )
                return
            if parsed.path == "/api/run":
                regime = (query.get("regime") or ["classical"])[-1]
                if regime not in REGIME_IDS:
                    raise ApiError(
                        HTTPStatus.BAD_REQUEST,
                        "regime 必须是 classical、keynesian 或 mmt",
                    )
                months, seed = _common_params(query)
                self._send_json(SERVICE.get_run(regime, months, seed))
                return
            if parsed.path == "/api/compare":
                months, seed = _common_params(query)
                self._send_json(SERVICE.get_compare(months, seed))
                return
            raise ApiError(HTTPStatus.NOT_FOUND, "未知接口")
        except ApiError as exc:
            self._send_json(
                {"error": exc.message, "status": int(exc.status)}, status=exc.status
            )
        except BrokenPipeError:
            pass
        except Exception as exc:  # noqa: BLE001 - 返回 JSON 错误而不是断开连接
            import traceback

            traceback.print_exc()
            self._send_json(
                {"error": f"服务端运行失败：{exc}", "status": 500},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format: str, *args: Any) -> None:
        # 保留简短访问日志，方便用户观察后台是否在跑仿真。
        sys.stderr.write(
            "%s [%s] %s\n"
            % (self.log_date_time_string(), self.address_string(), format % args)
        )


def main(argv: list[str] | None = None) -> int:
    global SERVICE
    parser = argparse.ArgumentParser(
        description="V0.4 本地经济驾驶舱服务（标准库 http.server）"
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1）")
    parser.add_argument("--port", type=int, default=8765, help="端口（默认 8765）")
    parser.add_argument(
        "--prewarm",
        action="store_true",
        help="启动后后台预跑 240 月三制度（首次打开页面会更快，但启动后仍占用 CPU）",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port 必须在 1–65535 之间")

    if not (WEB_DIR / "index.html").is_file():
        print(f"错误：找不到前端文件 {WEB_DIR / 'index.html'}", file=sys.stderr)
        return 2

    SERVICE = RunService()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    server.daemon_threads = True
    print("=" * 66)
    print("EcoSim V0.4 经济驾驶舱")
    print(f"前端：http://{args.host}:{args.port}/")
    print(f"接口：http://{args.host}:{args.port}/api/run?regime=classical&months=240&seed=1")
    print(f"对比：http://{args.host}:{args.port}/api/compare?months=240&seed=1")
    print("首次运行一个 240 月制度约需 20–40 秒；结果缓存在内存中。")
    print("按 Ctrl+C 停止。")
    print("=" * 66)

    if args.prewarm:
        def warm() -> None:
            try:
                SERVICE.get_compare(DEFAULT_MONTHS, DEFAULT_SEED)
                print("[prewarm] 三制度缓存完成", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[prewarm] 失败：{exc}", file=sys.stderr, flush=True)

        threading.Thread(target=warm, name="prewarm", daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n正在停止 ...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
