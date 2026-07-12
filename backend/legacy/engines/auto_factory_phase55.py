"""
Auto Factory Engine — Phase 5.5 (Pure Orchestrator).

Orchestrates the full end-to-end AI Strategy Factory pipeline:

    Data  →  Generate  →  Mutate  →  Validate  →  Select  →  Store  →  Repeat

This engine is ADDITIVE and PURE ORCHESTRATION — it MUST NOT:
  * re-implement ingestion / mutation / scoring / selection logic
  * modify the data maintainer, portfolio builder, trade runner or
    prop firm engine
  * import internal engine functions directly

It only talks to the existing system through its HTTP API surface
(`http://localhost:8001/api/...`) so that the orchestration reflects
exactly what a user would trigger manually from the UI.

Public surface:
  - run_cycle(...)            → awaitable, returns full cycle summary
  - get_status()              → running flag + current/last run + scheduler state
  - get_history(limit)        → recent runs from `auto_factory_phase55_runs`
  - set_toggle(enabled, h)    → enable/disable interval scheduler
  - get_config()/save_config  → configurable filters & universe

Safety:
  * Single `asyncio.Lock` → only one cycle at a time.
  * HTTP calls have explicit timeouts so a hung step cannot pin the loop.
  * Every step is wrapped — a failure is recorded, the run continues.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from engines.db import get_db
from engines.readiness_engine import compute_readiness, failed_red_checks

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Collections
# ──────────────────────────────────────────────────────────────────────
CONFIG_COLLECTION = "auto_factory_config"
RUNS_COLLECTION = "auto_factory_phase55_runs"
STRATEGIES_COLLECTION = "auto_factory_phase55_strategies"

CONFIG_DOC_ID = "phase55_default"

# ──────────────────────────────────────────────────────────────────────
# Defaults (overridable via config collection)
# ──────────────────────────────────────────────────────────────────────
DEFAULTS: Dict[str, Any] = {
    "pairs": ["EURUSD", "XAUUSD", "BTCUSD"],
    "timeframes": ["M15", "H1"],
    "styles": ["trend-following", "mean-reversion", "breakout"],
    "per_combo": 5,
    "firm": "ftmo",
    # Generation / mutation sizing
    "ingestion_max_strategies": 6,
    "mutation_iterations": 2,
    "mutation_per_cycle": 3,
    # Selection filters (defaults from Phase 5.5 spec)
    "min_pf": 1.2,
    "min_runs": 3,
    "max_drawdown": 0.12,   # 12% (fraction form as per spec)
    "min_stability": 0.0,
    "min_pass_probability": 0.0,
    "min_match_score": 0.0,
    "min_env_confidence": 0.0,
    "top_n_store": 20,
    # Step toggles
    "run_data_maintenance": True,
    "run_ingestion": True,
    "run_mutation": True,
    "run_validation": True,
    "run_selection": True,
    # Scheduler
    "scheduler_enabled": False,
    "scheduler_interval_hours": 6.0,
    # HTTP client settings
    "step_timeout_sec": 600,
    # ── Alerts (Phase 5.5 add-on — fully additive) ────────────────
    "alerts_enabled": False,
    "webhook_url": "",
    "telegram_enabled": False,
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "alert_min_pass_probability": 0.6,
    "alert_min_env_confidence": 0.6,
    # ── Monitoring → Alerts bridge (Phase 6 × 5.5) ─────────────────
    "monitoring_alerts_enabled": True,
    "alert_on_daily_dd": True,
    "alert_on_total_dd": True,
    "alert_on_underperformance": True,
    "alert_on_loss_streak": True,
    # ── Paper Execution → Alerts bridge (deviation detector) ───────
    "alert_on_paper_deviation": True,
    "deviation_threshold": 0.20,        # fractional, 0.20 = 20%
    "deviation_persistence": 5,         # consecutive exceeding samples
    # ── Phase 30.2 · Universe Governance opt-in flag (default ON) ──
    # When True, pairs/timeframes/styles are intersected with the
    # operator-decreed allowed universe before each pipeline tick.
    "respect_universe": True,
}

HISTORY_MAXLEN = 20

# ──────────────────────────────────────────────────────────────────────
# Singleton state — single-process FastAPI
# ──────────────────────────────────────────────────────────────────────
_lock = asyncio.Lock()
_state: Dict[str, Any] = {
    "current_run": None,
    "last_run": None,
    "history": deque(maxlen=HISTORY_MAXLEN),
    "scheduler": {
        "enabled": False,
        "interval_hours": None,
        "next_run_at": None,
    },
}
_scheduler: Optional[AsyncIOScheduler] = None
_SCHED_JOB_ID = "auto_factory_phase55_interval"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_url() -> str:
    # Always hit our own ingress-agnostic localhost — Kubernetes routes
    # external /api → :8001 but this is an internal server-to-server call
    # so we skip the ingress entirely.
    return os.environ.get("INTERNAL_API_BASE", "http://localhost:8001")


# ──────────────────────────────────────────────────────────────────────
# Config persistence
# ──────────────────────────────────────────────────────────────────────
async def get_config() -> Dict[str, Any]:
    """Read config from `auto_factory_config`, merged over defaults.

    Phase 30.2 — when ``respect_universe`` is True (default) the
    config's ``pairs``/``timeframes``/``styles`` are intersected with
    the operator-decreed allowed universe before return. Empty
    intersection falls back to the ungoverned defaults with a warning
    (never silent black-hole).
    """
    db = get_db()
    doc = await db[CONFIG_COLLECTION].find_one({"_id": CONFIG_DOC_ID}, {"_id": 0})
    merged = {**DEFAULTS, **(doc or {})}
    # Default to True so the universe boundary is honoured out of the box.
    respect = bool(merged.get("respect_universe", True))
    merged["respect_universe"] = respect
    if respect:
        try:
            from engines import governance_universe as _gu
            uni = await _gu.get_universe()
            uni_pairs = {_gu.canon_pair(p) for p in (uni.get("pairs") or [])}
            uni_tfs   = {_gu.canon_tf(t) for t in (uni.get("timeframes") or [])}
            uni_styles = {_gu.canon_style(s) for s in (uni.get("styles") or [])}
            new_pairs  = [p for p in merged.get("pairs", []) if _gu.canon_pair(p) in uni_pairs]
            new_tfs    = [t for t in merged.get("timeframes", []) if _gu.canon_tf(t) in uni_tfs]
            new_styles = [s for s in merged.get("styles", []) if _gu.canon_style(s) in uni_styles]
            if new_pairs and new_tfs and new_styles:
                merged["pairs"]      = new_pairs
                merged["timeframes"] = new_tfs
                merged["styles"]     = new_styles
                merged["universe_filtered"] = True
            else:
                logger.warning(
                    "[auto_factory_phase55] universe intersection empty for "
                    "pairs/tfs/styles; falling back to ungoverned defaults"
                )
                merged["universe_filtered"] = False
        except Exception as _e:                             # pragma: no cover
            logger.debug("[auto_factory_phase55] universe filter failed: %s", _e)
            merged["universe_filtered"] = False
    return merged


async def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Merge & persist config updates. Unknown keys are preserved so
    the UI can extend without backend churn."""
    db = get_db()
    current = await db[CONFIG_COLLECTION].find_one({"_id": CONFIG_DOC_ID}, {"_id": 0}) or {}
    current.update({k: v for k, v in updates.items() if v is not None})
    current["updated_at"] = _now_iso()
    await db[CONFIG_COLLECTION].replace_one(
        {"_id": CONFIG_DOC_ID}, {"_id": CONFIG_DOC_ID, **current}, upsert=True
    )
    return {**DEFAULTS, **current}


# ──────────────────────────────────────────────────────────────────────
# HTTP orchestration helpers
# ──────────────────────────────────────────────────────────────────────
async def _post(client: httpx.AsyncClient, path: str, payload: Dict[str, Any],
                timeout: float) -> Dict[str, Any]:
    """Single POST wrapper — captures status + body; never raises."""
    step_log: Dict[str, Any] = {"path": path, "method": "POST", "payload": payload}
    t0 = time.perf_counter()
    try:
        r = await client.post(path, json=payload, timeout=timeout)
        step_log["status_code"] = r.status_code
        try:
            step_log["body"] = r.json()
        except Exception:
            step_log["body"] = {"raw": r.text[:500]}
        step_log["ok"] = 200 <= r.status_code < 300
    except Exception as e:
        step_log["ok"] = False
        step_log["error"] = str(e)[:300]
    step_log["elapsed_sec"] = round(time.perf_counter() - t0, 2)
    return step_log


async def _get(client: httpx.AsyncClient, path: str, timeout: float) -> Dict[str, Any]:
    step_log: Dict[str, Any] = {"path": path, "method": "GET"}
    t0 = time.perf_counter()
    try:
        r = await client.get(path, timeout=timeout)
        step_log["status_code"] = r.status_code
        try:
            step_log["body"] = r.json()
        except Exception:
            step_log["body"] = {"raw": r.text[:500]}
        step_log["ok"] = 200 <= r.status_code < 300
    except Exception as e:
        step_log["ok"] = False
        step_log["error"] = str(e)[:300]
    step_log["elapsed_sec"] = round(time.perf_counter() - t0, 2)
    return step_log


# ──────────────────────────────────────────────────────────────────────
# Pipeline steps — each returns a per-step summary
# ──────────────────────────────────────────────────────────────────────
async def _step_data(client: httpx.AsyncClient, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Step 1 — Data refresh via POST /api/data/maintenance/run."""
    if not cfg.get("run_data_maintenance", True):
        return {"step": "data", "skipped": True}
    res = await _post(
        client,
        "/api/data/maintenance/run",
        {"pairs": cfg["pairs"], "timeframes": cfg["timeframes"], "enforce": True},
        timeout=cfg["step_timeout_sec"],
    )
    return {"step": "data", **res}


async def _step_generate(client: httpx.AsyncClient, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Step 2 — Generation via existing ingestion endpoint (synchronous).

    We hit /api/ingestion/run with background=False so the orchestrator
    can block on completion rather than poll. Ingestion generates and
    injects strategies into the strategy library using the existing
    pipeline (same engines as the Workspace tab would use).
    """
    if not cfg.get("run_ingestion", True):
        return {"step": "generate", "skipped": True}
    res = await _post(
        client,
        "/api/ingestion/run",
        {
            "max_strategies": int(cfg["ingestion_max_strategies"]),
            "use_github": True,
            "use_tradingview": True,
            "use_local_queue": True,
            "inject": True,
            "firm": cfg["firm"],
            "background": False,
        },
        timeout=cfg["step_timeout_sec"],
    )
    return {"step": "generate", **res}


async def _step_mutate(client: httpx.AsyncClient, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Step 3 — Mutation via existing auto-mutation runner.

    Kicks off a short mutation burst per (pair, timeframe) combo using
    the existing /api/auto/mutation-runner endpoint. We start the job
    and poll its status endpoint until done or timed out.
    """
    if not cfg.get("run_mutation", True):
        return {"step": "mutate", "skipped": True}

    start = await _post(
        client,
        "/api/auto/mutation-runner",
        {
            "iterations": int(cfg["mutation_iterations"]),
            "strategies_per_cycle": int(cfg["mutation_per_cycle"]),
            "pair": cfg["pairs"][0],
            "timeframe": cfg["timeframes"][0],
            "style": (cfg["styles"][0] if cfg.get("styles") else ""),
            "firm": cfg["firm"],
            "auto_save": True,
        },
        timeout=60,
    )

    # Poll status until idle or timeout.
    poll_log: List[Dict[str, Any]] = []
    deadline = time.time() + float(cfg["step_timeout_sec"])
    while time.time() < deadline:
        st = await _get(client, "/api/auto/mutation-runner/status", timeout=15)
        poll_log.append({"status_code": st.get("status_code"), "body": st.get("body")})
        body = st.get("body") or {}
        running = bool(body.get("running", False))
        if not running:
            break
        await asyncio.sleep(3)

    return {"step": "mutate", "start": start, "polls": len(poll_log),
            "final_status": poll_log[-1] if poll_log else None}


async def _step_validate(client: httpx.AsyncClient, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Step 4 — Validation: market intelligence + prop analysis + challenge matching."""
    if not cfg.get("run_validation", True):
        return {"step": "validate", "skipped": True}

    mi = await _post(
        client,
        "/api/market-intelligence/scan-eligible",
        {"limit": 40, "pairs": cfg["pairs"], "timeframes": cfg["timeframes"], "force": False},
        timeout=cfg["step_timeout_sec"],
    )
    pa = await _post(
        client,
        "/api/prop-firm-analysis/batch-analyze",
        {"firm_slug": cfg["firm"], "limit": 40, "min_runs": int(cfg["min_runs"]), "force": False},
        timeout=cfg["step_timeout_sec"],
    )
    cm = await _post(
        client,
        "/api/challenge-matching/run-eligible",
        {"limit": 40, "force": False},
        timeout=cfg["step_timeout_sec"],
    )
    return {"step": "validate", "market_intelligence": mi,
            "prop_analysis": pa, "challenge_matching": cm}


async def _step_select(client: httpx.AsyncClient, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Step 5 — Selection via /api/auto-select/run with Phase 5.5 filters."""
    if not cfg.get("run_selection", True):
        return {"step": "select", "skipped": True, "selected": []}

    # auto_select expects drawdown as the **stability** threshold in its
    # own domain; we pass PF / runs / pass / match / env confidence and
    # rely on auto_select's internal filtering. DD is enforced locally
    # on the returned set to guarantee Phase 5.5 contract.
    res = await _post(
        client,
        "/api/auto-select/run",
        {
            "top_n": int(cfg["top_n_store"]),
            "min_pf": float(cfg["min_pf"]),
            "min_runs": int(cfg["min_runs"]),
            "min_stability": float(cfg["min_stability"]),
            "min_pass_probability": float(cfg["min_pass_probability"]),
            "min_match_score": float(cfg["min_match_score"]),
            "min_env_confidence": float(cfg["min_env_confidence"]),
            "firm_slug": cfg["firm"],
            "pass_only": False,
            "run_missing_matches": True,
            "persist": True,
        },
        timeout=cfg["step_timeout_sec"],
    )

    body = res.get("body") or {}
    raw = body.get("selected") or body.get("strategies") or body.get("top") or []
    if isinstance(raw, dict):
        raw = raw.get("items", [])

    max_dd = float(cfg["max_drawdown"])

    def _dd_of(s: Dict[str, Any]) -> float:
        # Accept either fraction (0.12) or percent (12.0) forms; normalise.
        dd = (
            s.get("max_drawdown")
            or s.get("max_drawdown_pct")
            or s.get("drawdown")
            or (s.get("metrics") or {}).get("max_drawdown_pct")
            or 0.0
        )
        try:
            dd = float(dd)
        except Exception:
            return 0.0
        return dd / 100.0 if dd > 1.0 else dd

    filtered = [s for s in raw if _dd_of(s) <= max_dd]
    return {"step": "select", "raw_count": len(raw), "kept_count": len(filtered),
            "selected": filtered, "select_call": {k: v for k, v in res.items() if k != "body"}}


async def _step_store(run_id: str, selected: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Step 6 — Persist selected strategies into the Phase 5.5 store."""
    db = get_db()
    stamped = []
    now = _now_iso()
    for rank, s in enumerate(selected, start=1):
        doc = {k: v for k, v in (s or {}).items() if k != "_id"}
        doc.update({
            "run_id": run_id,
            "rank": rank,
            "phase": "5.5",
            "stored_at": now,
        })
        stamped.append(doc)
    inserted = 0
    if stamped:
        r = await db[STRATEGIES_COLLECTION].insert_many(stamped)
        inserted = len(r.inserted_ids)
    return {"step": "store", "stored": inserted}


# ──────────────────────────────────────────────────────────────────────
# Main cycle
# ──────────────────────────────────────────────────────────────────────
async def run_cycle(triggered_by: str = "manual",
                    overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run one complete Phase 5.5 cycle.

    Raises RuntimeError('already_running') when another cycle is in flight.
    Raises RuntimeError('readiness_blocked') when the system-readiness
    check reports overall=='red' — enforced uniformly for BOTH
    API-triggered and scheduler-triggered runs. Never overridable.
    """
    if _lock.locked():
        raise RuntimeError("already_running")

    # ── Pre-flight readiness gate (system-wide; no override) ─────
    # Same logic as the HTTP gate in api/auto_factory.py. Catching it
    # here means APScheduler-triggered runs cannot bypass the gate by
    # skipping the HTTP layer. Any compute failure is treated as red
    # (fail-safe) — logged and refused.
    try:
        readiness = await compute_readiness()
    except Exception as exc:
        logger.exception(
            "phase55 run aborted — readiness check itself failed "
            "(triggered_by=%s)", triggered_by,
        )
        raise RuntimeError("readiness_check_failed") from exc

    if readiness.get("overall") == "red":
        reds = failed_red_checks(readiness)
        reasons = "; ".join(
            f"{c.get('label') or c.get('id')}: {c.get('summary')}" for c in reds
        ) or "unspecified red checks"
        logger.warning(
            "phase55 run aborted — readiness gate red (triggered_by=%s): %s",
            triggered_by, reasons,
        )
        raise RuntimeError("readiness_blocked")

    cfg = await get_config()
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})

    run_id = uuid.uuid4().hex[:12]
    started_iso = _now_iso()
    t0 = time.perf_counter()

    _state["current_run"] = {
        "run_id": run_id,
        "started_at": started_iso,
        "triggered_by": triggered_by,
        "config": cfg,
        "progress": {"completed": 0, "total": 6, "current_step": "init"},
        "steps": [],
    }

    async with _lock:
        summary: Dict[str, Any] = {
            "run_id": run_id,
            "started_at": started_iso,
            "triggered_by": triggered_by,
            "phase": "5.5",
            "config_snapshot": cfg,
            "steps": [],
            "selected_count": 0,
            "stored_count": 0,
            "status": "running",
        }

        headers = {"Content-Type": "application/json"}
        async with httpx.AsyncClient(base_url=_base_url(), headers=headers) as client:
            plan = [
                ("data",     _step_data),
                ("generate", _step_generate),
                ("mutate",   _step_mutate),
                ("validate", _step_validate),
                ("select",   _step_select),
            ]
            selected: List[Dict[str, Any]] = []
            for name, fn in plan:
                _state["current_run"]["progress"]["current_step"] = name
                try:
                    step = await fn(client, cfg)
                except Exception as e:
                    logger.exception("phase5.5 step failed: %s", name)
                    step = {"step": name, "ok": False, "error": str(e)[:300]}
                summary["steps"].append(step)
                _state["current_run"]["steps"].append(step)
                _state["current_run"]["progress"]["completed"] += 1
                if name == "select":
                    selected = step.get("selected", []) or []

            # Step 6 — Store
            _state["current_run"]["progress"]["current_step"] = "store"
            try:
                store_res = await _step_store(run_id, selected)
            except Exception as e:
                logger.exception("phase5.5 store failed")
                store_res = {"step": "store", "ok": False, "error": str(e)[:300], "stored": 0}
            summary["steps"].append(store_res)
            _state["current_run"]["steps"].append(store_res)

            # ── Alerts (additive, fail-silent) ──────────────────────
            try:
                from engines import alert_engine as alerts
                alert_summary = await alerts.process_stored_strategies(
                    selected, cfg, run_id=run_id,
                )
                store_res["alerts"] = alert_summary
                summary["alerts"] = alert_summary
            except Exception:
                logger.exception("phase5.5 alerts step failed (swallowed)")

            _state["current_run"]["progress"]["completed"] += 1
            _state["current_run"]["progress"]["current_step"] = "done"

        summary["selected_count"] = len(selected)
        summary["stored_count"] = store_res.get("stored", 0)
        summary["finished_at"] = _now_iso()
        summary["runtime_sec"] = round(time.perf_counter() - t0, 2)
        summary["status"] = "complete"

        # Persist run document
        try:
            db = get_db()
            await db[RUNS_COLLECTION].insert_one({**summary})
        except Exception:
            logger.exception("failed to persist phase55 run")

        _state["last_run"] = summary
        _state["history"].appendleft({
            "run_id": run_id,
            "started_at": started_iso,
            "finished_at": summary["finished_at"],
            "runtime_sec": summary["runtime_sec"],
            "triggered_by": triggered_by,
            "selected_count": summary["selected_count"],
            "stored_count": summary["stored_count"],
        })
        _state["current_run"] = None

        logger.info(
            "auto_factory_phase55 run %s done — %s selected, %s stored, %.1fs",
            run_id, summary["selected_count"], summary["stored_count"], summary["runtime_sec"],
        )
        return summary


# ──────────────────────────────────────────────────────────────────────
# Status / history / scheduler
# ──────────────────────────────────────────────────────────────────────
def get_status() -> Dict[str, Any]:
    sched = dict(_state["scheduler"])
    if _scheduler and sched.get("enabled"):
        try:
            job = _scheduler.get_job(_SCHED_JOB_ID)
            if job and job.next_run_time:
                sched["next_run_at"] = job.next_run_time.isoformat()
        except Exception:
            pass
    return {
        "phase": "5.5",
        "running": _lock.locked(),
        "current_run": _state["current_run"],
        "last_run": _state["last_run"],
        "history": list(_state["history"]),
        "scheduler": sched,
    }


async def get_history(limit: int = 25) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[RUNS_COLLECTION].find({}, {"_id": 0}).sort("started_at", -1).limit(max(1, min(limit, 200)))
    return await cur.to_list(length=None)


async def get_run_strategies(run_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[STRATEGIES_COLLECTION].find({"run_id": run_id}, {"_id": 0}).sort("rank", 1).limit(limit)
    return await cur.to_list(length=None)


def _scheduled_job_wrapper():
    """Sync bridge into asyncio from APScheduler."""
    async def _runner():
        try:
            await run_cycle(triggered_by="scheduler")
        except RuntimeError as e:
            msg = str(e)
            if msg == "already_running":
                logger.info("phase55 scheduler skipped — previous run still in progress")
            elif msg == "readiness_blocked":
                # Scheduler triggered while the system is not ready.
                # This is the expected safety behaviour — log at INFO so
                # operators can see the scheduler is alive but gated.
                logger.info(
                    "phase55 scheduler skipped — readiness gate red "
                    "(fix issues in Admin → System Readiness; no override)"
                )
            elif msg == "readiness_check_failed":
                logger.warning(
                    "phase55 scheduler skipped — readiness check failed "
                    "(refusing to run for safety)"
                )
            else:
                raise
        except Exception:
            logger.exception("phase55 scheduled run failed")

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.create_task(_runner())


def set_toggle(enabled: bool, interval_hours: float = 6.0) -> Dict[str, Any]:
    """Enable/disable the interval scheduler. Safe to call repeatedly."""
    global _scheduler

    if enabled:
        if interval_hours <= 0:
            raise ValueError("interval_hours must be positive")
        if _scheduler is None:
            _scheduler = AsyncIOScheduler(timezone="UTC")
        try:
            _scheduler.remove_job(_SCHED_JOB_ID)
        except Exception:
            pass
        _scheduler.add_job(
            _scheduled_job_wrapper,
            trigger=IntervalTrigger(hours=float(interval_hours)),
            id=_SCHED_JOB_ID,
            name="auto_factory_phase55_interval",
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
        if not _scheduler.running:
            _scheduler.start()
        job = _scheduler.get_job(_SCHED_JOB_ID)
        _state["scheduler"]["enabled"] = True
        _state["scheduler"]["interval_hours"] = float(interval_hours)
        _state["scheduler"]["next_run_at"] = (
            job.next_run_time.isoformat() if job and job.next_run_time else None
        )
    else:
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
        _state["scheduler"]["enabled"] = False
        _state["scheduler"]["next_run_at"] = None

    return dict(_state["scheduler"])
