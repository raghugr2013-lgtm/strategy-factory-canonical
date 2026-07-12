"""
Phase 5 — Auto Strategy Factory (Continuous Generation).

Continuously generates strategies across a configurable universe of
(pair × timeframe × style) combinations, runs each one through the
EXISTING smart pipeline (generate → backtest → validation → decision →
rank → refine → prop-firm panel), and persists only the eligible
candidates into the existing `strategy_library` collection.

Design goals:
  • REUSE existing engines — no duplication.
      - Pipeline:   api.dashboard.dashboard_generate     (smart pipeline)
      - Save layer: engines.strategy_library.auto_save_top (TRADE / strong-RISKY only)
  • Additive — does not touch Phase 1–4 code paths.
  • Idempotent — single `asyncio.Lock` prevents overlapping runs.
  • Observable — every run emits a structured `RunSummary`; history is
      kept in-memory + mirrored to the `auto_factory_runs` collection.

Public surface:
  - run_auto_factory(...)     → RunSummary (awaitable)
  - get_status()              → current + last + history snapshot
  - start_scheduler(hours)    → enable APScheduler interval job
  - stop_scheduler()          → disable scheduler
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from engines.db import get_db
from engines.readiness_engine import compute_readiness, failed_red_checks
from engines.strategy_library import auto_save_top

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Universe defaults — configurable per-call.
# ─────────────────────────────────────────────────────────────────────
DEFAULT_PAIRS = ["EURUSD", "GBPUSD", "XAUUSD"]
DEFAULT_TIMEFRAMES = ["M5", "M15", "H1", "H4"]
DEFAULT_STYLES = ["trend", "mean-reversion", "breakout"]

# Accept both "trend" and "trend-following" from callers.
_STYLE_ALIAS = {
    "trend": "trend-following",
    "trend-following": "trend-following",
    "mean-reversion": "mean-reversion",
    "mean_reversion": "mean-reversion",
    "mean reversion": "mean-reversion",
    "breakout": "breakout",
}

HISTORY_MAXLEN = 20
RUNS_COLLECTION = "auto_factory_runs"

# ─────────────────────────────────────────────────────────────────────
# Singleton run-state. Kept intentionally simple — a process-local
# dict + asyncio.Lock is enough for a single-worker FastAPI backend.
# ─────────────────────────────────────────────────────────────────────
_lock = asyncio.Lock()
_state: Dict[str, Any] = {
    "current_run": None,           # live RunSummary while a run is in flight
    "last_run": None,              # most recently completed RunSummary
    "history": deque(maxlen=HISTORY_MAXLEN),
    "scheduler": {
        "enabled": False,
        "interval_hours": None,
        "next_run_at": None,
    },
}
_scheduler: Optional[AsyncIOScheduler] = None
_scheduled_job_id = "auto_factory_interval"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_style(s: str) -> str:
    return _STYLE_ALIAS.get((s or "").strip().lower(), s)


# ─────────────────────────────────────────────────────────────────────
# Core runner
# ─────────────────────────────────────────────────────────────────────

async def _run_one_combo(
    pair: str,
    timeframe: str,
    style: str,
    *,
    per_combo: int,
    firm: str,
    top_n: int,
    refine_top: int,
    prefilter_top: int,
) -> Dict[str, Any]:
    """
    Run the existing smart pipeline for one (pair, tf, style) combo.
    Returns a per-combo summary (always — failures captured, not raised).
    """
    # Lazy import to keep engine decoupled from the API layer at import time.
    from api.dashboard import DashboardGenerateRequest, dashboard_generate
    from fastapi import HTTPException

    style_norm = _normalize_style(style)
    started = time.perf_counter()
    summary: Dict[str, Any] = {
        "pair": pair,
        "timeframe": timeframe,
        "style": style_norm,
        "status": "skipped",
        "reason": None,
        "generated": 0,
        "top_returned": 0,
        "saved": 0,
        "duplicates": 0,
        "rejected": 0,
        "best_score": 0.0,
        "best_verdict": None,
        "runtime_sec": 0.0,
        "saved_ids": [],
    }

    req = DashboardGenerateRequest(
        pair=pair,
        timeframe=timeframe,
        style=style_norm,
        count=max(1, min(int(per_combo), 50)),
        firm=firm,
        top_n=max(1, min(int(top_n), 20)),
        refine_top=max(0, min(int(refine_top), 5)),
        prefilter_top=max(1, min(int(prefilter_top), 20)),
    )

    try:
        result = await dashboard_generate(req)
    except HTTPException as e:
        summary["reason"] = f"pipeline skipped: {e.detail}"
        summary["runtime_sec"] = round(time.perf_counter() - started, 2)
        return summary
    except Exception as e:  # pragma: no cover — defensive
        logger.exception("Auto-factory combo failed: %s/%s/%s", pair, timeframe, style_norm)
        summary["status"] = "error"
        summary["reason"] = str(e)[:200]
        summary["runtime_sec"] = round(time.perf_counter() - started, 2)
        return summary

    top_strategies = result.get("top_strategies") or []
    summary["generated"] = result.get("timings", {}).get("generated", 0)
    summary["top_returned"] = len(top_strategies)

    if top_strategies:
        # Ensure every card carries pair/timeframe/style so the library
        # fingerprint and filtering works correctly.
        for s in top_strategies:
            s.setdefault("pair", pair)
            s.setdefault("timeframe", timeframe)
            s.setdefault("style", style_norm)

        best = max(top_strategies, key=lambda x: x.get("score") or 0)
        summary["best_score"] = round(float(best.get("score") or 0), 1)
        summary["best_verdict"] = best.get("verdict")

        # Delegate eligibility + dedup to the library layer (TRADE or strong RISKY).
        save_res = await auto_save_top(top_strategies, source="auto_factory")
        counts = save_res.get("counts", {})
        summary["saved"] = counts.get("saved", 0)
        summary["duplicates"] = counts.get("duplicates", 0)
        summary["rejected"] = counts.get("rejected", 0)
        summary["saved_ids"] = save_res.get("saved", [])

    summary["status"] = "complete"
    summary["runtime_sec"] = round(time.perf_counter() - started, 2)
    return summary


async def run_auto_factory(
    pairs: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    styles: Optional[List[str]] = None,
    *,
    per_combo: int = 10,
    firm: str = "ftmo",
    top_n: int = 5,
    refine_top: int = 1,
    prefilter_top: int = 5,
    triggered_by: str = "manual",
) -> Dict[str, Any]:
    """
    Run one full Auto Factory cycle across the configured universe.

    Steps (per combo):
      generate → backtest → validation → decision → rank → refine → panel
      → auto_save_top(TRADE / strong-RISKY into strategy_library).

    Guarded by a single asyncio.Lock — overlapping invocations raise
    `RuntimeError("already_running")` so the scheduler and the HTTP
    endpoint cannot stomp on each other.

    Also enforces the system-wide readiness gate: if compute_readiness()
    reports overall=='red', the run is refused and
    `RuntimeError("readiness_blocked")` is raised. The gate cannot be
    overridden and applies uniformly to API-triggered and
    scheduler-triggered runs.
    """
    if _lock.locked():
        raise RuntimeError("already_running")

    # ── Pre-flight readiness gate (system-wide; no override) ─────
    try:
        readiness = await compute_readiness()
    except Exception as exc:
        logger.exception(
            "auto_factory run aborted — readiness check itself failed "
            "(triggered_by=%s)", triggered_by,
        )
        raise RuntimeError("readiness_check_failed") from exc

    if readiness.get("overall") == "red":
        reds = failed_red_checks(readiness)
        reasons = "; ".join(
            f"{c.get('label') or c.get('id')}: {c.get('summary')}" for c in reds
        ) or "unspecified red checks"
        logger.warning(
            "auto_factory run aborted — readiness gate red (triggered_by=%s): %s",
            triggered_by, reasons,
        )
        raise RuntimeError("readiness_blocked")

    # R3 — route through market_universe_adapter for discovery pairs.
    # Byte-identical when flag OFF (the adapter falls back to
    # DEFAULT_PAIRS). Filtered downstream by governance_universe.
    if not pairs:
        try:
            from engines.market_universe_adapter import get_discovery_pairs
            pairs = get_discovery_pairs()
        except Exception:                                   # pragma: no cover
            pairs = DEFAULT_PAIRS
    timeframes = timeframes or DEFAULT_TIMEFRAMES
    styles = [_normalize_style(s) for s in (styles or DEFAULT_STYLES)]

    run_id = uuid.uuid4().hex[:12]
    started_iso = _now_iso()
    t0 = time.perf_counter()

    async with _lock:
        _state["current_run"] = {
            "run_id": run_id,
            "started_at": started_iso,
            "triggered_by": triggered_by,
            "pairs": pairs,
            "timeframes": timeframes,
            "styles": styles,
            "per_combo": per_combo,
            "firm": firm,
            "progress": {"completed": 0, "total": len(pairs) * len(timeframes) * len(styles)},
            "combo_results": [],
        }

        combo_results: List[Dict[str, Any]] = []
        for pair in pairs:
            for tf in timeframes:
                for style in styles:
                    result = await _run_one_combo(
                        pair, tf, style,
                        per_combo=per_combo, firm=firm, top_n=top_n,
                        refine_top=refine_top, prefilter_top=prefilter_top,
                    )
                    combo_results.append(result)
                    _state["current_run"]["combo_results"].append(result)
                    _state["current_run"]["progress"]["completed"] += 1

        runtime = round(time.perf_counter() - t0, 2)

        totals = {
            "combos_total": len(combo_results),
            "combos_complete": sum(1 for r in combo_results if r["status"] == "complete"),
            "combos_skipped": sum(1 for r in combo_results if r["status"] == "skipped"),
            "combos_errored": sum(1 for r in combo_results if r["status"] == "error"),
            "strategies_generated": sum(r["generated"] for r in combo_results),
            "strategies_returned": sum(r["top_returned"] for r in combo_results),
            "strategies_saved": sum(r["saved"] for r in combo_results),
            "strategies_duplicate": sum(r["duplicates"] for r in combo_results),
            "strategies_rejected": sum(r["rejected"] for r in combo_results),
            "best_score": max((r["best_score"] for r in combo_results), default=0.0),
        }

        summary: Dict[str, Any] = {
            "run_id": run_id,
            "triggered_by": triggered_by,
            "started_at": started_iso,
            "finished_at": _now_iso(),
            "runtime_sec": runtime,
            "config": {
                "pairs": pairs, "timeframes": timeframes, "styles": styles,
                "per_combo": per_combo, "firm": firm, "top_n": top_n,
                "refine_top": refine_top, "prefilter_top": prefilter_top,
            },
            "totals": totals,
            "combo_results": combo_results,
        }

        # Persist run history (best-effort)
        try:
            db = get_db()
            await db[RUNS_COLLECTION].insert_one({**summary})
        except Exception as e:
            logger.warning("Failed to persist auto_factory run: %s", e)

        _state["last_run"] = summary
        _state["history"].appendleft({
            "run_id": run_id,
            "started_at": started_iso,
            "finished_at": summary["finished_at"],
            "runtime_sec": runtime,
            "triggered_by": triggered_by,
            "totals": totals,
        })
        _state["current_run"] = None

        logger.info(
            "Auto factory run %s done — %s combos, %s saved, %.1fs",
            run_id, totals["combos_total"], totals["strategies_saved"], runtime,
        )
        return summary


# ─────────────────────────────────────────────────────────────────────
# Status + scheduler API
# ─────────────────────────────────────────────────────────────────────

def get_status() -> Dict[str, Any]:
    """Snapshot of factory state. Used by GET /api/auto-factory/status."""
    sched = dict(_state["scheduler"])
    if _scheduler and sched.get("enabled"):
        try:
            job = _scheduler.get_job(_scheduled_job_id)
            if job and job.next_run_time:
                sched["next_run_at"] = job.next_run_time.isoformat()
        except Exception:
            pass
    return {
        "running": _lock.locked(),
        "current_run": _state["current_run"],
        "last_run": _state["last_run"],
        "history": list(_state["history"]),
        "scheduler": sched,
    }


def _scheduled_job_wrapper():
    """APScheduler entry point — must be sync to be scheduled safely,
    then dispatches the async run onto the running event loop."""
    async def _runner():
        try:
            await run_auto_factory(triggered_by="scheduler")
        except RuntimeError as e:
            msg = str(e)
            if msg == "already_running":
                logger.info("Auto factory skipped — previous run still in progress.")
            elif msg == "readiness_blocked":
                logger.info(
                    "Auto factory scheduler skipped — readiness gate red "
                    "(fix issues in Admin → System Readiness; no override)"
                )
            elif msg == "readiness_check_failed":
                logger.warning(
                    "Auto factory scheduler skipped — readiness check failed "
                    "(refusing to run for safety)"
                )
            else:
                raise
        except Exception:
            logger.exception("Scheduled auto factory run failed")

    loop = asyncio.get_event_loop()
    loop.create_task(_runner())


def start_scheduler(interval_hours: float = 6.0) -> Dict[str, Any]:
    """Start (or restart) the APScheduler interval job. Safe to call
    multiple times — existing job is replaced."""
    global _scheduler
    if interval_hours <= 0:
        raise ValueError("interval_hours must be positive")

    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")

    # Replace any existing job with the new interval.
    try:
        _scheduler.remove_job(_scheduled_job_id)
    except Exception:
        pass

    _scheduler.add_job(
        _scheduled_job_wrapper,
        trigger=IntervalTrigger(hours=interval_hours),
        id=_scheduled_job_id,
        name="auto_factory_interval",
        coalesce=True,       # merge missed runs into a single trigger
        max_instances=1,     # overlap guard in addition to the engine lock
        replace_existing=True,
    )

    if not _scheduler.running:
        _scheduler.start()

    _state["scheduler"]["enabled"] = True
    _state["scheduler"]["interval_hours"] = float(interval_hours)

    job = _scheduler.get_job(_scheduled_job_id)
    _state["scheduler"]["next_run_at"] = (
        job.next_run_time.isoformat() if job and job.next_run_time else None
    )
    return dict(_state["scheduler"])


def stop_scheduler() -> Dict[str, Any]:
    """Disable the scheduler. In-flight runs are NOT cancelled."""
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.remove_job(_scheduled_job_id)
        except Exception:
            pass
        if _scheduler.running:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass
        _scheduler = None
    _state["scheduler"]["enabled"] = False
    _state["scheduler"]["next_run_at"] = None
    return dict(_state["scheduler"])
