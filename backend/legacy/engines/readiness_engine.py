"""
Readiness engine — pure, read-only, framework-agnostic.

Computes the 5 system-readiness checks used by:
  • GET /api/admin/readiness         (admin panel)
  • POST /api/auto-factory/run       (pre-flight gate)

Design rules:
  * No FastAPI / Starlette imports.
  * No writes to any collection.
  * Never raises — per-check failures are captured and reported as RED.
  * Safe to call repeatedly; each check is a small count / single-doc read.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from engines.db import get_db

logger = logging.getLogger(__name__)

AUTO_FACTORY_CONFIG_COLL = "auto_factory_config"
AUTO_FACTORY_CONFIG_DOC_ID = "phase55_default"
MARKET_DATA_COLL = "market_data"
EXECUTION_RUNS_COLL = "execution_runs"

TIER1_SYMBOLS = ("EURUSD", "GBPUSD")
WATCHLIST = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD")


def _watchlist() -> tuple:
    """R3 — route through market_universe_adapter. Byte-identical when
    flag OFF (the adapter falls back to the WATCHLIST tuple)."""
    try:
        from engines.market_universe_adapter import get_active_watchlist
        return tuple(get_active_watchlist())
    except Exception:                                       # pragma: no cover
        return WATCHLIST


def _tier1_symbols() -> tuple:
    """R3 — adapter-routed tier1. Byte-identical when flag OFF."""
    try:
        from engines.market_universe_adapter import get_tier1_symbols
        return tuple(get_tier1_symbols())
    except Exception:                                       # pragma: no cover
        return TIER1_SYMBOLS

MIN_TIER1_BARS = 5000
WARN_TIER1_BARS = 1500
MIN_TOTAL_BARS = 50_000
STALE_RUN_THRESHOLD_HOURS = 6

GREEN, YELLOW, RED = "green", "yellow", "red"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _worst(*statuses: str) -> str:
    order = {GREEN: 0, YELLOW: 1, RED: 2}
    return max(statuses, key=lambda s: order.get(s, 0)) if statuses else GREEN


# ─────────────────────────────────────────────────────────────────────
# Individual checks
# ─────────────────────────────────────────────────────────────────────
async def _check_market_data(db) -> Dict[str, Any]:
    per_symbol: Dict[str, int] = {}
    total = 0
    watch = _watchlist()
    tier1 = _tier1_symbols()
    for sym in watch:
        try:
            n = await db[MARKET_DATA_COLL].count_documents({"symbol": sym})
        except Exception:
            n = 0
        per_symbol[sym] = n
        total += n

    tier1_counts = [per_symbol.get(s, 0) for s in tier1]
    thin_symbols = [s for s in watch if per_symbol.get(s, 0) < WARN_TIER1_BARS]

    if total == 0:
        status = RED
        summary = "No market data in MongoDB — ingestion required before any pipeline run."
    elif any(c < WARN_TIER1_BARS for c in tier1_counts):
        status = RED
        summary = "Tier-1 symbols (EURUSD / GBPUSD) are missing sufficient history."
    elif any(c < MIN_TIER1_BARS for c in tier1_counts) or total < MIN_TOTAL_BARS:
        status = YELLOW
        summary = "Tier-1 history present but some symbols are thin — back-fill recommended."
    elif thin_symbols:
        status = YELLOW
        summary = f"Core pairs OK. Thin history on: {', '.join(thin_symbols)}."
    else:
        status = GREEN
        summary = "All watch-list symbols have sufficient history."

    return {
        "id": "market_data",
        "label": "Market data coverage",
        "status": status,
        "summary": summary,
        "details": {
            "total_rows": total,
            "per_symbol": per_symbol,
            "tier1_minimum_bars": MIN_TIER1_BARS,
            "tier1_warning_bars": WARN_TIER1_BARS,
            "thin_symbols": thin_symbols,
        },
    }


async def _check_llm_budget() -> Dict[str, Any]:
    """Phase 1B: VIE-native LLM readiness check.

    Replaces the v01 `EMERGENT_LLM_KEY` check. Queries VIE /providers and
    reports availability without ever reading provider API keys directly.
    """
    from engines.llm_config import validate_environment  # local import

    try:
        env = validate_environment()
    except Exception as e:  # noqa: BLE001
        return {
            "id": "llm_budget",
            "label": "LLM providers (VIE)",
            "status": RED,
            "summary": f"VIE is unreachable ({e!s:.120}). Start the VIE service or check VIE_URL.",
            "details": {"vie_reachable": False},
        }

    providers_total = int(env.get("providers_total", 0) or 0)
    providers_available = int(env.get("providers_available", 0) or 0)
    available = env.get("available") or []

    if providers_available == 0:
        return {
            "id": "llm_budget",
            "label": "LLM providers (VIE)",
            "status": RED,
            "summary": (
                "No LLM providers available via VIE. Configure at least one of "
                "OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY / "
                "DEEPSEEK_API_KEY / GROQ_API_KEY / KIMI_API_KEY."
            ),
            "details": {
                "vie_reachable": True,
                "providers_total": providers_total,
                "providers_available": 0,
                "available": [],
            },
        }
    return {
        "id": "llm_budget",
        "label": "LLM providers (VIE)",
        "status": GREEN,
        "summary": (
            f"{providers_available}/{providers_total} providers available via VIE: "
            f"{', '.join(available)}. Vendor-independent — no key stored in factory."
        ),
        "details": {
            "vie_reachable": True,
            "providers_total": providers_total,
            "providers_available": providers_available,
            "available": available,
        },
    }


async def _check_alerts(db) -> Dict[str, Any]:
    doc = await db[AUTO_FACTORY_CONFIG_COLL].find_one(
        {"_id": AUTO_FACTORY_CONFIG_DOC_ID}, {"_id": 0}
    ) or {}
    enabled = bool(doc.get("alerts_enabled", False))
    webhook = bool((doc.get("webhook_url") or "").strip())
    tg_enabled = bool(doc.get("telegram_enabled", False))
    tg_configured = bool((doc.get("telegram_bot_token") or "").strip() and (doc.get("telegram_chat_id") or "").strip())
    any_channel = webhook or (tg_enabled and tg_configured)

    if not enabled:
        status = YELLOW
        summary = "Alerts are disabled (safe default). Enable in Auto Factory → Config before running live cycles."
    elif not any_channel:
        status = RED
        summary = "alerts_enabled=True but no channel is configured — alerts will fire silently."
    else:
        status = GREEN
        summary = "Alerts enabled and at least one channel is configured."

    return {
        "id": "alerts",
        "label": "Alerts configuration",
        "status": status,
        "summary": summary,
        "details": {
            "alerts_enabled": enabled,
            "webhook_url_set": webhook,
            "telegram_enabled": tg_enabled,
            "telegram_configured": tg_configured,
        },
    }


async def _check_active_runs(db) -> Dict[str, Any]:
    try:
        running_runs = await db[EXECUTION_RUNS_COLL].find(
            {"status": "running"}, {"_id": 0, "run_id": 1, "started_at": 1, "updated_at": 1}
        ).to_list(length=None)
    except Exception:
        running_runs = []

    try:
        errored = await db[EXECUTION_RUNS_COLL].count_documents({"status": "errored"})
    except Exception:
        errored = 0

    stale: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for r in running_runs:
        ts = r.get("updated_at") or r.get("started_at")
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(str(ts).replace("Z", "+00:00")) if isinstance(ts, str) else ts
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            age_h = (now - t).total_seconds() / 3600.0
            if age_h > STALE_RUN_THRESHOLD_HOURS:
                stale.append({"run_id": r.get("run_id"), "age_hours": round(age_h, 1)})
        except Exception:
            continue

    if stale:
        status = RED
        summary = f"{len(stale)} paper-execution run(s) are stuck running without a recent heartbeat."
    elif errored > 0:
        status = YELLOW
        summary = f"{errored} past runs finished with errored status — review logs before re-deploying."
    elif len(running_runs) > 1:
        status = YELLOW
        summary = f"{len(running_runs)} paper runs currently running — single-active-run lock should normally prevent this."
    else:
        status = GREEN
        summary = "No stale or errored runs."

    return {
        "id": "active_runs",
        "label": "Active run integrity",
        "status": status,
        "summary": summary,
        "details": {
            "currently_running": len(running_runs),
            "errored_total": errored,
            "stale": stale,
            "stale_threshold_hours": STALE_RUN_THRESHOLD_HOURS,
        },
    }


async def _check_risk_limits(db) -> Dict[str, Any]:
    doc = await db[AUTO_FACTORY_CONFIG_COLL].find_one(
        {"_id": AUTO_FACTORY_CONFIG_DOC_ID}, {"_id": 0}
    ) or {}

    max_dd = doc.get("max_drawdown")
    deviation_threshold = doc.get("deviation_threshold")
    deviation_persistence = doc.get("deviation_persistence")
    min_pf = doc.get("min_pf")

    problems: List[str] = []

    def _f(v) -> float:
        try:
            return float(v)
        except Exception:
            return -1.0

    if max_dd is None:
        problems.append("max_drawdown not set (using default 0.12)")
    else:
        f = _f(max_dd)
        if f <= 0 or f > 0.25:
            problems.append(f"max_drawdown out of safe range (0 < x <= 0.25): {max_dd}")

    if deviation_threshold is None:
        problems.append("deviation_threshold not set (using default 0.20)")
    else:
        f = _f(deviation_threshold)
        if f <= 0 or f > 0.5:
            problems.append(f"deviation_threshold out of sane range: {deviation_threshold}")

    if deviation_persistence is not None:
        try:
            if int(deviation_persistence) < 1:
                problems.append("deviation_persistence must be >= 1")
        except Exception:
            problems.append(f"deviation_persistence not an integer: {deviation_persistence}")

    if min_pf is not None:
        f = _f(min_pf)
        if f < 1.0:
            problems.append(f"min_pf is below 1.0 (unprofitable): {min_pf}")

    if not problems:
        status = GREEN
        summary = "Drawdown, deviation and PF thresholds look sane."
    elif any("out of" in p or "unprofitable" in p for p in problems):
        status = RED
        summary = "One or more risk limits are outside safe ranges."
    else:
        status = YELLOW
        summary = "Using defaults for one or more risk limits — review before live."

    return {
        "id": "risk_limits",
        "label": "Drawdown / risk limits",
        "status": status,
        "summary": summary,
        "details": {
            "max_drawdown": max_dd,
            "deviation_threshold": deviation_threshold,
            "deviation_persistence": deviation_persistence,
            "min_pf": min_pf,
            "issues": problems,
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────
async def compute_readiness() -> Dict[str, Any]:
    """Run all 5 readiness checks and return the combined verdict.

    Shape:
      {
        "overall": "green|yellow|red",
        "generated_at": "<ISO>",
        "checks": [ {id,label,status,summary,details}, ... ]
      }

    Per-check failures never bubble out — each check is wrapped so a
    single collection outage cannot blank the whole report.
    """
    db = get_db()

    async def _safe(coro, fallback_id: str, fallback_label: str) -> Dict[str, Any]:
        try:
            return await coro
        except Exception as e:
            logger.exception("readiness check failed: %s", fallback_id)
            return {
                "id": fallback_id,
                "label": fallback_label,
                "status": RED,
                "summary": f"Check failed: {str(e)[:200]}",
                "details": {"error": str(e)[:500]},
            }

    checks = [
        await _safe(_check_market_data(db),   "market_data", "Market data coverage"),
        await _safe(_check_llm_budget(),      "llm_budget",  "LLM key / budget"),
        await _safe(_check_alerts(db),        "alerts",      "Alerts configuration"),
        await _safe(_check_active_runs(db),   "active_runs", "Active run integrity"),
        await _safe(_check_risk_limits(db),   "risk_limits", "Drawdown / risk limits"),
    ]

    overall = _worst(*(c["status"] for c in checks))

    return {
        "overall": overall,
        "generated_at": _now_iso(),
        "checks": checks,
    }


def failed_red_checks(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convenience: filter the compute_readiness() result down to the
    checks that are in RED state. Used by the Auto Factory pre-flight
    gate to build a clear block message."""
    return [c for c in (result.get("checks") or []) if c.get("status") == RED]
