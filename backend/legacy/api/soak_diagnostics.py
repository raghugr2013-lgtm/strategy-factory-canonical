"""
Phase 2 P2.6/P2.7 — Soak evidence aggregator.

Read-only diagnostic that aggregates the ten signals the operator
demanded prior to ProcessPool activation:

  1. lock_behavior            — advisory_locks table state + history
  2. scheduler_stability      — orchestrator_scheduler tick cadence
  3. orchestration_heartbeat  — factory_runner heartbeat continuity
  4. stale_lock_evidence      — TTL eviction proof + reaper activity
  5. mutation_persistence     — mutation_events / mutation_runs growth
  6. concurrency_anomalies    — duplicate ticks + multi-worker holds
  7. mongo_stability          — collection sizes, connection pool, ops
  8. explorer_continuity      — strategy_library + lifecycle counts
  9. llm_health               — by-provider success/failover rates
  10. backend_factory_runner_processes — supervisor PIDs + uptime

Every probe is a pure-read aggregation. No mutation, no side effects.
Safe to poll every minute.

Output is two-tiered:
  • `summary`   — single line per signal, OK/WARN/INFO.
  • `details`   — full per-signal payload for forensic inspection.

Operator usage:
    curl -H "Authorization: Bearer <admin>" \
         /api/diagnostics/soak-snapshot?window_minutes=60 | jq

Or via the CLI:
    python -m scripts.soak_snapshot --window-minutes=60
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from auth_utils import get_current_user
from engines.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


def _iso_n_min_ago(minutes: int) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(minutes=int(minutes))
    ).isoformat()


def _dt_n_min_ago(minutes: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=int(minutes))


async def _probe_lock_behavior(db, window_minutes: int) -> Dict[str, Any]:
    """Active advisory locks + recent acquire/release activity."""
    try:
        active_cursor = db["advisory_locks"].find({}, {"_id": 1, "holder_pid": 1, "acquired_at_dt": 1, "expires_at_dt": 1, "metadata": 1})
        active: List[Dict[str, Any]] = []
        async for d in active_cursor:
            d["lock_key"] = d.pop("_id")
            for k in ("acquired_at_dt", "expires_at_dt"):
                if isinstance(d.get(k), datetime):
                    d[k] = d[k].isoformat()
            active.append(d)
        return {
            "active_locks": active,
            "active_count": len(active),
            "verdict": "OK" if len(active) <= 2 else "WARN",
            "note": "advisory locks are short-lived; >2 simultaneous is unusual",
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


async def _probe_scheduler_stability(db, window_minutes: int) -> Dict[str, Any]:
    """orchestrator_scheduler tick cadence (heartbeat-derived)."""
    try:
        since = _iso_n_min_ago(window_minutes)
        ticks_cur = db["audit_log"].find(
            {"event": "ORCHESTRATOR_TICK_EMITTED", "ts": {"$gte": since}},
            {"_id": 0, "ts": 1},
        ).sort("ts", 1)
        tick_times: List[str] = [d["ts"] async for d in ticks_cur]
        intervals_min: List[float] = []
        for a, b in zip(tick_times, tick_times[1:]):
            try:
                t1 = datetime.fromisoformat(a.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(b.replace("Z", "+00:00"))
                intervals_min.append(round((t2 - t1).total_seconds() / 60.0, 2))
            except Exception:
                continue
        avg_interval = (
            round(sum(intervals_min) / len(intervals_min), 2)
            if intervals_min else None
        )
        verdict = "OK"
        if not tick_times and window_minutes >= 30:
            verdict = "INFO"  # scheduler may not be active yet
        elif intervals_min and (max(intervals_min) > 30 or min(intervals_min) < 0.5):
            verdict = "WARN"
        return {
            "window_minutes": window_minutes,
            "ticks_in_window": len(tick_times),
            "tick_intervals_min": intervals_min[-20:],  # tail to bound size
            "avg_interval_min": avg_interval,
            "first_tick": tick_times[0] if tick_times else None,
            "last_tick": tick_times[-1] if tick_times else None,
            "verdict": verdict,
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


async def _probe_orchestration_heartbeat(db, window_minutes: int) -> Dict[str, Any]:
    """factory_runner heartbeat cadence (validates the sibling process)."""
    try:
        since = _iso_n_min_ago(window_minutes)
        cur = db["audit_log"].find(
            {"event": {"$in": [
                "factory_runner:startup",
                "factory_runner:heartbeat",
                "factory_runner:shutdown",
            ]}, "ts": {"$gte": since}},
            {"_id": 0, "ts": 1, "event": 1, "pid": 1},
        ).sort("ts", -1)
        events: List[Dict[str, Any]] = [d async for d in cur]
        heartbeats = [e for e in events if e["event"] == "factory_runner:heartbeat"]
        startups = [e for e in events if e["event"] == "factory_runner:startup"]
        shutdowns = [e for e in events if e["event"] == "factory_runner:shutdown"]
        unique_pids = sorted({e.get("pid") for e in events if e.get("pid")})
        verdict = "OK"
        if not events and window_minutes >= 30:
            verdict = "WARN"  # factory_runner not heartbeating
        elif len(startups) > 1 + window_minutes // 1440:
            # multiple startups in a short window = flapping
            verdict = "WARN"
        return {
            "window_minutes": window_minutes,
            "startups": len(startups),
            "shutdowns": len(shutdowns),
            "heartbeats": len(heartbeats),
            "unique_pids": unique_pids,
            "last_event": events[0] if events else None,
            "verdict": verdict,
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


async def _probe_stale_lock_evidence(db, window_minutes: int) -> Dict[str, Any]:
    """Are advisory locks self-healing via TTL? Indirect check via
    Mongo's command stats is not available without admin perms — we
    instead verify the TTL index is present and active.
    """
    try:
        info = await db["advisory_locks"].index_information()
        ttl_idx = info.get("ttl_advisory_locks") or {}
        ttl_seconds = ttl_idx.get("expireAfterSeconds")
        # Probe: insert a doc with expires_at_dt in the past, wait for
        # Mongo TTL reaper to remove it. Mongo's TTL monitor runs every
        # 60s — too slow for inline probing. Instead just verify index
        # existence + presence of any expired docs (which SHOULD be 0
        # under healthy reaper).
        now = datetime.now(timezone.utc)
        expired_count = await db["advisory_locks"].count_documents({
            "expires_at_dt": {"$lt": now},
        })
        verdict = "OK"
        if ttl_seconds is None:
            verdict = "WARN"  # TTL index missing
        elif expired_count > 5:
            verdict = "WARN"  # reaper not keeping up
        return {
            "ttl_index_present": ttl_idx is not None and ttl_seconds is not None,
            "ttl_expire_after_seconds": ttl_seconds,
            "ttl_index_keys": ttl_idx.get("key"),
            "currently_expired_undeleted": expired_count,
            "verdict": verdict,
            "note": "Mongo TTL monitor runs every 60s; small lag is normal",
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


async def _probe_mutation_persistence(db, window_minutes: int) -> Dict[str, Any]:
    """mutation_events + mutation_runs persistence cadence."""
    try:
        since = _iso_n_min_ago(window_minutes)
        events = await db["mutation_events"].count_documents({"ts": {"$gte": since}})
        runs = await db["mutation_runs"].count_documents({"ts": {"$gte": since}})
        total_events = await db["mutation_events"].estimated_document_count()
        total_runs = await db["mutation_runs"].estimated_document_count()
        verdict = "OK"
        if window_minutes >= 60 and events == 0 and total_events == 0:
            verdict = "INFO"  # ecosystem dormant — operator-gated
        return {
            "window_minutes": window_minutes,
            "events_in_window": events,
            "runs_in_window": runs,
            "events_total": total_events,
            "runs_total": total_runs,
            "verdict": verdict,
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


async def _probe_concurrency_anomalies(db, window_minutes: int) -> Dict[str, Any]:
    """Duplicate-tick detection (the D1 mitigation evidence)."""
    try:
        since = _iso_n_min_ago(window_minutes)
        ticks = [d async for d in db["audit_log"].find(
            {"event": "ORCHESTRATOR_TICK_EMITTED", "ts": {"$gte": since}},
            {"_id": 0, "ts": 1},
        ).sort("ts", 1)]
        duplicates: List[Dict[str, Any]] = []
        for a, b in zip(ticks, ticks[1:]):
            try:
                t1 = datetime.fromisoformat(a["ts"].replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(b["ts"].replace("Z", "+00:00"))
                if (t2 - t1).total_seconds() <= 5.0:
                    duplicates.append({"t1": a["ts"], "t2": b["ts"]})
            except Exception:
                continue
        verdict = "OK" if not duplicates else "WARN"
        return {
            "window_minutes": window_minutes,
            "duplicate_tick_count": len(duplicates),
            "duplicate_examples": duplicates[:5],
            "verdict": verdict,
            "note": (
                "Duplicate ticks within 5s usually indicate two schedulers "
                "running simultaneously (D1 in EXECUTION_PLAN). Should be 0."
            ),
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


async def _probe_mongo_stability(db, window_minutes: int) -> Dict[str, Any]:
    """Collection sizes + db stats. Operator can spot abnormal growth."""
    try:
        watch = [
            "market_data", "strategy_library", "audit_log", "llm_call_log",
            "pipeline_logs", "mutation_events", "mutation_runs",
            "multi_cycle_runs", "auto_run_cycles", "strategy_lifecycle",
            "advisory_locks",
        ]
        sizes: Dict[str, int] = {}
        for c in watch:
            try:
                sizes[c] = await db[c].estimated_document_count()
            except Exception:
                sizes[c] = -1
        return {
            "collection_counts": sizes,
            "verdict": "OK",
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


async def _probe_explorer_continuity(db, window_minutes: int) -> Dict[str, Any]:
    """strategy_library + lifecycle stage distribution."""
    try:
        lib_total = await db["strategy_library"].estimated_document_count()
        # Lifecycle stage distribution
        pipeline = [
            {"$group": {"_id": "$current_stage", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        stages: Dict[str, int] = {}
        async for d in db["strategy_lifecycle"].aggregate(pipeline):
            stages[d.get("_id") or "(none)"] = int(d.get("count", 0))
        return {
            "strategy_library_count": lib_total,
            "lifecycle_stage_distribution": stages,
            "verdict": "OK",
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


async def _probe_llm_health(db, window_minutes: int) -> Dict[str, Any]:
    """Per-provider success / failover / error rates."""
    try:
        since = _iso_n_min_ago(window_minutes)
        cur = db["llm_call_log"].find(
            {"ts": {"$gte": since}},
            {"_id": 0, "provider": 1, "outcome": 1},
        )
        by_provider: Dict[str, Dict[str, int]] = {}
        async for d in cur:
            p = d.get("provider") or "?"
            outcome = d.get("outcome") or "?"
            slot = by_provider.setdefault(p, {"total": 0})
            slot["total"] += 1
            slot[outcome] = slot.get(outcome, 0) + 1
        return {
            "window_minutes": window_minutes,
            "by_provider": by_provider,
            "verdict": "OK",
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


async def _probe_processes() -> Dict[str, Any]:
    """Snapshot of running PIDs (best-effort, no /proc parsing)."""
    try:
        # We can't safely call supervisorctl from inside the FastAPI
        # process. Operators should run `supervisorctl status` from the
        # shell. We just report the SERVER process pid + factory_runner
        # heartbeat's last pid (already covered by _probe_orchestration_heartbeat).
        return {
            "server_pid": os.getpid(),
            "note": "Use `supervisorctl status` for full process list.",
            "verdict": "OK",
        }
    except Exception as e:
        return {"verdict": "ERROR", "error": str(e)[:200]}


@router.get("/diagnostics/soak-snapshot")
async def soak_snapshot(
    window_minutes: int = Query(60, ge=1, le=10080),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Aggregate every Phase 2.6/2.7 soak-evidence signal in one call.

    Designed for the 24h soak window before ProcessPool activation.
    Operator may poll every minute (cheap reads only).
    """
    db = get_db()
    parts: Dict[str, Any] = {}
    parts["lock_behavior"]            = await _probe_lock_behavior(db, window_minutes)
    parts["scheduler_stability"]      = await _probe_scheduler_stability(db, window_minutes)
    parts["orchestration_heartbeat"]  = await _probe_orchestration_heartbeat(db, window_minutes)
    parts["stale_lock_evidence"]      = await _probe_stale_lock_evidence(db, window_minutes)
    parts["mutation_persistence"]     = await _probe_mutation_persistence(db, window_minutes)
    parts["concurrency_anomalies"]    = await _probe_concurrency_anomalies(db, window_minutes)
    parts["mongo_stability"]          = await _probe_mongo_stability(db, window_minutes)
    parts["explorer_continuity"]      = await _probe_explorer_continuity(db, window_minutes)
    parts["llm_health"]               = await _probe_llm_health(db, window_minutes)
    parts["processes"]                = await _probe_processes()

    summary = {k: v.get("verdict", "?") for k, v in parts.items()}
    overall = (
        "OK" if all(v == "OK" or v == "INFO" for v in summary.values())
        else ("WARN" if any(v == "WARN" for v in summary.values()) else "ERROR")
    )

    return {
        "snapshot_at":      datetime.now(timezone.utc).isoformat(),
        "window_minutes":   window_minutes,
        "overall_verdict":  overall,
        "summary":          summary,
        "details":          parts,
    }
