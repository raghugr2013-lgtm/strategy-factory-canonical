"""
Monitoring Engine — Phase 6 (additive only).

Observational risk-control layer. It READS from existing Trade Runner
collections (`trade_runner_runs`, `trade_runner_trades`), computes
aggregate metrics, persists a single `monitoring_state` document plus
per-strategy rows in `strategy_status`, and — when breach thresholds
are crossed — takes protective action via EXISTING HTTP endpoints
(never by monkey-patching engines):

  * hard breach (total DD ≥ 10%)   → POST /api/trade-runner/stop/{id}
                                     for every active run
  * daily breach (daily DD ≥ 5%)   → set state=PAUSED_DAILY and stop
                                     all active runs until next UTC day
  * strategy underperformance       → strategy marked UNDER_REVIEW
    (last 20 trades PF < 1.0)
  * loss streak ≥ 5                → strategy marked PAUSED_STREAK

Fail-safe: all exceptions are swallowed inside the public entrypoints.
If monitoring itself is broken, the rest of the system is unaffected.

Public surface:
  - monitor_portfolio_state()  → awaitable, recomputes + applies rules
  - get_state()                → current {state, metrics, strategies, breaches, actions}
  - reset_state()              → reset breaches and mark RUNNING
  - pause(strategy_id=None)    → force pause (global or single strategy)
  - resume(strategy_id=None)   → force resume
  - start_scheduler(seconds)   → background interval runner
  - stop_scheduler()
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from engines.db import get_db

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Collections
# ──────────────────────────────────────────────────────────────────────
STATE_COLLECTION = "monitoring_state"
STRATEGY_STATUS_COLLECTION = "strategy_status"
BREACH_LOG_COLLECTION = "monitoring_breach_log"

STATE_DOC_ID = "current"

# Read-only dependencies (Trade Runner)
TR_RUNS_COLL = "trade_runner_runs"
TR_TRADES_COLL = "trade_runner_trades"

# ──────────────────────────────────────────────────────────────────────
# System states
# ──────────────────────────────────────────────────────────────────────
STATE_RUNNING = "RUNNING"
STATE_PAUSED_DAILY = "PAUSED_DAILY"
STATE_STOPPED = "STOPPED"
STATE_RECOVERY = "RECOVERY_MODE"

# Strategy-level states
STRAT_ACTIVE = "ACTIVE"
STRAT_UNDER_REVIEW = "UNDER_REVIEW"
STRAT_PAUSED_STREAK = "PAUSED_STREAK"
STRAT_PAUSED_MANUAL = "PAUSED_MANUAL"

# ──────────────────────────────────────────────────────────────────────
# Thresholds (config-driven)
# ──────────────────────────────────────────────────────────────────────
DEFAULTS: Dict[str, Any] = {
    "daily_dd_threshold_pct": 5.0,
    "total_dd_threshold_pct": 10.0,
    "underperform_pf_threshold": 1.0,
    "underperform_window": 20,
    "loss_streak_threshold": 5,
    "scheduler_enabled": False,
    "scheduler_interval_seconds": 60,
}

HISTORY_MAXLEN = 50

# ──────────────────────────────────────────────────────────────────────
# Singleton runtime state (metrics + scheduler)
# ──────────────────────────────────────────────────────────────────────
_lock = asyncio.Lock()
_last_snapshot: Dict[str, Any] = {
    "state": STATE_RUNNING,
    "updated_at": None,
    "metrics": {},
    "strategies": [],
    "breaches": [],
    "actions": [],
    "history": deque(maxlen=HISTORY_MAXLEN),
}
_scheduler: Optional[AsyncIOScheduler] = None
_SCHED_JOB_ID = "monitoring_interval"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_date(ts_iso: Optional[str] = None) -> str:
    try:
        if ts_iso:
            return datetime.fromisoformat(ts_iso.replace("Z", "+00:00")).date().isoformat()
    except Exception:
        pass
    return datetime.now(timezone.utc).date().isoformat()


def _base_url() -> str:
    return os.environ.get("INTERNAL_API_BASE", "http://localhost:8001")


# ──────────────────────────────────────────────────────────────────────
# State persistence
# ──────────────────────────────────────────────────────────────────────
async def _load_state_doc() -> Dict[str, Any]:
    db = get_db()
    doc = await db[STATE_COLLECTION].find_one({"_id": STATE_DOC_ID}, {"_id": 0}) or {}
    return {**DEFAULTS, "state": STATE_RUNNING, **doc}


async def _save_state_doc(patch: Dict[str, Any]) -> Dict[str, Any]:
    db = get_db()
    doc = await db[STATE_COLLECTION].find_one({"_id": STATE_DOC_ID}, {"_id": 0}) or {}
    doc.update(patch)
    doc["updated_at"] = _now_iso()
    await db[STATE_COLLECTION].replace_one(
        {"_id": STATE_DOC_ID}, {"_id": STATE_DOC_ID, **doc}, upsert=True
    )
    return doc


async def _upsert_strategy_status(strategy_id: str, patch: Dict[str, Any]) -> None:
    if not strategy_id:
        return
    db = get_db()
    doc = await db[STRATEGY_STATUS_COLLECTION].find_one(
        {"strategy_id": strategy_id}, {"_id": 0}
    ) or {"strategy_id": strategy_id, "state": STRAT_ACTIVE}
    doc.update(patch)
    doc["updated_at"] = _now_iso()
    await db[STRATEGY_STATUS_COLLECTION].replace_one(
        {"strategy_id": strategy_id}, doc, upsert=True
    )


async def _log_breach(kind: str, details: Dict[str, Any]) -> None:
    try:
        db = get_db()
        await db[BREACH_LOG_COLLECTION].insert_one({
            "kind": kind,
            "details": details,
            "at": _now_iso(),
        })
    except Exception:
        logger.exception("breach log insert failed")


# ──────────────────────────────────────────────────────────────────────
# Data sources — read from Trade Runner collections (OBSERVE ONLY)
# ──────────────────────────────────────────────────────────────────────
async def _load_active_runs() -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[TR_RUNS_COLL].find({"status": {"$in": ["running", "halted"]}}, {"_id": 0}).sort("started_at", -1)
    return await cur.to_list(length=None)


async def _load_recent_runs(limit: int = 25) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[TR_RUNS_COLL].find({}, {"_id": 0}).sort("started_at", -1).limit(limit)
    return await cur.to_list(length=None)


async def _load_recent_trades(run_id: str, n: int = 20) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[TR_TRADES_COLL].find({"run_id": run_id}, {"_id": 0}).sort("closed_at", -1).limit(n)
    rows = await cur.to_list(length=None)
    return list(reversed(rows))  # chronological


def _compute_pf(trades: List[Dict[str, Any]]) -> float:
    gains = sum(max(0.0, float(t.get("pnl") or 0)) for t in trades)
    losses = sum(-min(0.0, float(t.get("pnl") or 0)) for t in trades)
    if losses <= 0:
        return 0.0 if gains <= 0 else 9.99
    return round(gains / losses, 3)


def _loss_streak(trades: List[Dict[str, Any]]) -> int:
    """Trailing consecutive losses (most-recent-backwards)."""
    streak = 0
    for t in reversed(trades):
        pnl = float(t.get("pnl") or 0)
        if pnl < 0:
            streak += 1
        else:
            break
    return streak


def _trades_today(trades: List[Dict[str, Any]]) -> int:
    today = _utc_date()
    return sum(1 for t in trades if (t.get("closed_at") or "").startswith(today))


# ──────────────────────────────────────────────────────────────────────
# Protective actions (via EXISTING HTTP endpoints — never modify engines)
# ──────────────────────────────────────────────────────────────────────
async def _stop_run_via_api(client: httpx.AsyncClient, run_id: str) -> Dict[str, Any]:
    out = {"run_id": run_id, "ok": False}
    try:
        r = await client.post(f"/api/trade-runner/stop/{run_id}", timeout=15)
        out["status_code"] = r.status_code
        out["ok"] = 200 <= r.status_code < 300
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


# ──────────────────────────────────────────────────────────────────────
# Main monitor
# ──────────────────────────────────────────────────────────────────────
async def monitor_portfolio_state() -> Dict[str, Any]:
    """Observe → compute metrics → apply control rules. Fail-safe."""
    async with _lock:
        try:
            return await _monitor_impl()
        except Exception as e:
            logger.exception("monitor_portfolio_state outer failure")
            return {
                "state": _last_snapshot.get("state", STATE_RUNNING),
                "error": str(e)[:300],
                "updated_at": _now_iso(),
            }


async def _monitor_impl() -> Dict[str, Any]:
    cfg = await _load_state_doc()
    prev_state = cfg.get("state", STATE_RUNNING)

    runs = await _load_active_runs()
    snapshot_id = uuid.uuid4().hex[:10]

    per_strategy: List[Dict[str, Any]] = []
    breaches: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []

    # Portfolio aggregates from active runs
    starting_equity = 0.0
    current_equity = 0.0
    peak_equity = 0.0
    daily_start = 0.0

    # Per-run analysis
    for r in runs:
        run_id = r.get("run_id")
        strategy_id = r.get("strategy_id") or run_id
        starting = float(r.get("account_balance_start") or 0.0)
        eq = float(r.get("equity") or starting)
        peak = float(r.get("peak_equity") or eq)
        daily_eq = float(r.get("daily_start_equity") or eq)

        starting_equity += starting
        current_equity += eq
        peak_equity += peak
        daily_start += daily_eq

        trades = await _load_recent_trades(run_id, n=int(cfg["underperform_window"]))
        pf20 = _compute_pf(trades)
        streak = _loss_streak(trades)

        total_dd_pct = 0.0
        if peak > 0:
            total_dd_pct = round(max(0.0, (peak - eq) / peak) * 100.0, 3)
        daily_dd_pct = float(r.get("daily_loss_pct") or 0.0)

        # Determine strategy-level state
        strat_state = STRAT_ACTIVE
        reason: Optional[str] = None
        if len(trades) >= int(cfg["underperform_window"]) and pf20 < float(cfg["underperform_pf_threshold"]):
            strat_state = STRAT_UNDER_REVIEW
            reason = f"PF({pf20}) < {cfg['underperform_pf_threshold']} over last {cfg['underperform_window']} trades"
        if streak >= int(cfg["loss_streak_threshold"]):
            strat_state = STRAT_PAUSED_STREAK
            reason = f"loss streak {streak} ≥ {cfg['loss_streak_threshold']}"

        strat_row = {
            "run_id": run_id,
            "strategy_id": strategy_id,
            "pair": r.get("pair"),
            "timeframe": r.get("timeframe"),
            "state": strat_state,
            "reason": reason,
            "metrics": {
                "equity": round(eq, 2),
                "peak_equity": round(peak, 2),
                "starting_equity": round(starting, 2),
                "total_dd_pct": total_dd_pct,
                "daily_dd_pct": daily_dd_pct,
                "pf_last_n": pf20,
                "loss_streak": streak,
                "trades_today": _trades_today(trades),
                "recent_trades": len(trades),
            },
            "run_status": r.get("status"),
        }
        per_strategy.append(strat_row)

        # Persist strategy_status (no overrides of manual pauses unless explicit resume)
        existing = None
        try:
            db = get_db()
            existing = await db[STRATEGY_STATUS_COLLECTION].find_one(
                {"strategy_id": strategy_id}, {"_id": 0}
            )
        except Exception:
            pass
        if existing and existing.get("state") == STRAT_PAUSED_MANUAL:
            # respect manual pause
            strat_row["state"] = STRAT_PAUSED_MANUAL
            await _upsert_strategy_status(strategy_id, {"metrics": strat_row["metrics"]})
        else:
            await _upsert_strategy_status(strategy_id, {
                "state": strat_state,
                "reason": reason,
                "metrics": strat_row["metrics"],
                "run_id": run_id,
            })

        if strat_state != STRAT_ACTIVE:
            breaches.append({
                "kind": "strategy_" + strat_state.lower(),
                "strategy_id": strategy_id,
                "run_id": run_id,
                "reason": reason,
                "pf_last_n": pf20,
                "loss_streak": streak,
            })

    # Portfolio-level drawdowns
    portfolio_total_dd = 0.0
    if peak_equity > 0:
        portfolio_total_dd = round(max(0.0, (peak_equity - current_equity) / peak_equity) * 100.0, 3)
    portfolio_daily_dd = 0.0
    if daily_start > 0:
        portfolio_daily_dd = round(max(0.0, (daily_start - current_equity) / daily_start) * 100.0, 3)

    # Determine system state based on breaches (respect manual STOPPED / PAUSED_DAILY)
    new_state = STATE_RUNNING

    total_limit = float(cfg["total_dd_threshold_pct"])
    daily_limit = float(cfg["daily_dd_threshold_pct"])

    if portfolio_total_dd >= total_limit:
        new_state = STATE_STOPPED
        breach = {
            "kind": "total_dd",
            "value_pct": portfolio_total_dd,
            "threshold_pct": total_limit,
        }
        breaches.append(breach)
        await _log_breach("total_dd", breach)
    elif portfolio_daily_dd >= daily_limit:
        new_state = STATE_PAUSED_DAILY
        breach = {
            "kind": "daily_dd",
            "value_pct": portfolio_daily_dd,
            "threshold_pct": daily_limit,
        }
        breaches.append(breach)
        await _log_breach("daily_dd", breach)

    # Respect previous hard states
    if prev_state == STATE_STOPPED:
        new_state = STATE_STOPPED
    elif prev_state == STATE_PAUSED_DAILY and new_state != STATE_STOPPED:
        new_state = STATE_PAUSED_DAILY
    elif prev_state == STATE_RECOVERY and new_state == STATE_RUNNING:
        new_state = STATE_RECOVERY

    # Apply protective actions via HTTP endpoints
    if new_state in (STATE_STOPPED, STATE_PAUSED_DAILY) and prev_state != new_state:
        async with httpx.AsyncClient(base_url=_base_url()) as client:
            for r in runs:
                if r.get("status") == "running":
                    res = await _stop_run_via_api(client, r["run_id"])
                    actions.append({"action": "stop_run", **res, "trigger": new_state})

    # Persist state + snapshot
    await _save_state_doc({"state": new_state})
    snapshot = {
        "snapshot_id": snapshot_id,
        "updated_at": _now_iso(),
        "state": new_state,
        "previous_state": prev_state,
        "metrics": {
            "portfolio_current_equity": round(current_equity, 2),
            "portfolio_peak_equity": round(peak_equity, 2),
            "portfolio_starting_equity": round(starting_equity, 2),
            "portfolio_total_dd_pct": portfolio_total_dd,
            "portfolio_daily_dd_pct": portfolio_daily_dd,
            "active_runs": len(runs),
            "active_strategies": sum(1 for s in per_strategy if s["state"] == STRAT_ACTIVE),
            "paused_strategies": sum(1 for s in per_strategy
                                     if s["state"] in (STRAT_PAUSED_STREAK, STRAT_PAUSED_MANUAL)),
            "under_review": sum(1 for s in per_strategy if s["state"] == STRAT_UNDER_REVIEW),
        },
        "thresholds": {
            "daily_dd_threshold_pct": daily_limit,
            "total_dd_threshold_pct": total_limit,
            "underperform_pf_threshold": float(cfg["underperform_pf_threshold"]),
            "underperform_window": int(cfg["underperform_window"]),
            "loss_streak_threshold": int(cfg["loss_streak_threshold"]),
        },
        "strategies": per_strategy,
        "breaches": breaches,
        "actions": actions,
    }

    _last_snapshot.update({
        "state": new_state,
        "updated_at": snapshot["updated_at"],
        "metrics": snapshot["metrics"],
        "strategies": per_strategy,
        "breaches": breaches,
        "actions": actions,
    })
    _last_snapshot["history"].appendleft({
        "snapshot_id": snapshot_id,
        "at": snapshot["updated_at"],
        "state": new_state,
        "metrics": snapshot["metrics"],
        "breaches": breaches,
        "actions": actions,
    })

    # ── Monitoring → Alerts bridge (additive, fail-silent) ──────────
    try:
        from engines import auto_factory_phase55 as af55
        from engines import monitoring_alert_bridge as bridge
        af_cfg = await af55.get_config()
        bridge_summary = await bridge.emit_from_snapshot(snapshot, af_cfg)
        snapshot["alerts"] = bridge_summary
    except Exception:
        logger.exception("monitoring alert bridge failed (swallowed)")

    return snapshot


# ──────────────────────────────────────────────────────────────────────
# Public facade
# ──────────────────────────────────────────────────────────────────────
async def get_state() -> Dict[str, Any]:
    cfg = await _load_state_doc()
    db = get_db()
    strategies = await db[STRATEGY_STATUS_COLLECTION].find({}, {"_id": 0}).to_list(length=None)
    breaches = await db[BREACH_LOG_COLLECTION].find({}, {"_id": 0}).sort("at", -1).limit(25).to_list(length=None)
    return {
        "state": cfg.get("state", STATE_RUNNING),
        "config": {k: cfg.get(k, v) for k, v in DEFAULTS.items()},
        "updated_at": cfg.get("updated_at"),
        "metrics": _last_snapshot.get("metrics", {}),
        "strategies": strategies or _last_snapshot.get("strategies", []),
        "breaches": breaches,
        "recent_actions": _last_snapshot.get("actions", []),
        "history": list(_last_snapshot.get("history", [])),
        "scheduler": {
            "enabled": cfg.get("scheduler_enabled", False),
            "interval_seconds": cfg.get("scheduler_interval_seconds", DEFAULTS["scheduler_interval_seconds"]),
        },
    }


async def reset_state() -> Dict[str, Any]:
    db = get_db()
    await _save_state_doc({"state": STATE_RUNNING})
    # Clear strategy-level automatic pauses (keep manual pauses intact)
    await db[STRATEGY_STATUS_COLLECTION].update_many(
        {"state": {"$in": [STRAT_UNDER_REVIEW, STRAT_PAUSED_STREAK]}},
        {"$set": {"state": STRAT_ACTIVE, "reason": None, "updated_at": _now_iso()}},
    )
    _last_snapshot["state"] = STATE_RUNNING
    _last_snapshot["breaches"] = []
    _last_snapshot["actions"] = []
    return await get_state()


async def pause(strategy_id: Optional[str] = None, *, global_stop: bool = False) -> Dict[str, Any]:
    """Global pause/stop OR per-strategy pause. Also stops any running trade-runner
    run associated with paused strategies."""
    if strategy_id:
        await _upsert_strategy_status(strategy_id, {
            "state": STRAT_PAUSED_MANUAL,
            "reason": "manual_pause",
        })
        # Best-effort: stop trade runner for this strategy
        async with httpx.AsyncClient(base_url=_base_url()) as client:
            db = get_db()
            runs = await db[TR_RUNS_COLL].find(
                {"strategy_id": strategy_id, "status": "running"}, {"_id": 0, "run_id": 1}
            ).to_list(length=None)
            for r in runs:
                await _stop_run_via_api(client, r["run_id"])
        return await get_state()

    # Global stop
    target_state = STATE_STOPPED if global_stop else STATE_PAUSED_DAILY
    await _save_state_doc({"state": target_state})
    async with httpx.AsyncClient(base_url=_base_url()) as client:
        runs = await _load_active_runs()
        for r in runs:
            if r.get("status") == "running":
                await _stop_run_via_api(client, r["run_id"])
    _last_snapshot["state"] = target_state
    return await get_state()


async def resume(strategy_id: Optional[str] = None) -> Dict[str, Any]:
    if strategy_id:
        await _upsert_strategy_status(strategy_id, {
            "state": STRAT_ACTIVE,
            "reason": None,
        })
        return await get_state()
    await _save_state_doc({"state": STATE_RUNNING})
    _last_snapshot["state"] = STATE_RUNNING
    return await get_state()


# ──────────────────────────────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────────────────────────────
def _scheduled_job_wrapper():
    async def _runner():
        try:
            await monitor_portfolio_state()
        except Exception:
            logger.exception("monitoring scheduled run failed")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.create_task(_runner())


async def start_scheduler(interval_seconds: int = 60) -> Dict[str, Any]:
    global _scheduler
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    try:
        _scheduler.remove_job(_SCHED_JOB_ID)
    except Exception:
        pass
    _scheduler.add_job(
        _scheduled_job_wrapper,
        trigger=IntervalTrigger(seconds=int(interval_seconds)),
        id=_SCHED_JOB_ID,
        name="monitoring_interval",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    if not _scheduler.running:
        _scheduler.start()
    await _save_state_doc({
        "scheduler_enabled": True,
        "scheduler_interval_seconds": int(interval_seconds),
    })
    return {"enabled": True, "interval_seconds": int(interval_seconds)}


async def stop_scheduler() -> Dict[str, Any]:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.remove_job(_SCHED_JOB_ID)
        except Exception:
            pass
        if _scheduler.running:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:
                pass
        _scheduler = None
    await _save_state_doc({"scheduler_enabled": False})
    return {"enabled": False}


# ──────────────────────────────────────────────────────────────────────
# Config update (thresholds)
# ──────────────────────────────────────────────────────────────────────
async def update_thresholds(patch: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {
        "daily_dd_threshold_pct", "total_dd_threshold_pct",
        "underperform_pf_threshold", "underperform_window",
        "loss_streak_threshold", "scheduler_interval_seconds",
    }
    clean = {k: v for k, v in (patch or {}).items() if k in allowed and v is not None}
    if not clean:
        return await _load_state_doc()
    return await _save_state_doc(clean)


async def equity_curve(limit: int = 200) -> List[Dict[str, Any]]:
    """Build a coarse portfolio equity curve from the recent history snapshots
    (fail-safe fallback if no trades available)."""
    history = list(_last_snapshot.get("history", []))[:limit]
    return [
        {
            "at": h.get("at"),
            "equity": (h.get("metrics") or {}).get("portfolio_current_equity", 0),
            "peak":   (h.get("metrics") or {}).get("portfolio_peak_equity", 0),
            "dd_pct": (h.get("metrics") or {}).get("portfolio_total_dd_pct", 0),
            "state":  h.get("state"),
        }
        for h in reversed(history)
    ]
