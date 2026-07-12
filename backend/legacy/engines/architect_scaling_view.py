"""
VPS Scaling P1.D — Architect integration hook (DORMANT, read-only).

The future Architect (auto-learning loop, capacity planner, operator
co-pilot) needs a single consolidated view of the scaling subsystem.
P1.D ships that view as a read-only module. **No Architect actually
calls these functions yet** — they exist so the wiring is one import
when the auto-learning phase lands.

Discipline:
  * READ-ONLY. Every function is `async def get_*()`. No mutation
    primitives, no admit-overrides, no event emit.
  * No raises. Each `get_*` returns a structured dict; on failure the
    relevant section is `None` + an `error` string.
  * No new state — pure projection of host_capability + queue_pressure +
    adaptive_concurrency + admission_journal + scaling_events.
  * Dormant: no production engine imports this module. The API surface
    (`api/scaling.py`) exposes it for operator audit.

Public API:
    get_host_capability_view()       → dict
    get_queue_pressure_view()        → dict
    get_concurrency_recommendation() → dict
    get_admission_journal_stats(window_sec) → dict
    get_full_architect_snapshot()    → dict   (all four bundled)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

logger = logging.getLogger(__name__)

ADMISSION_JOURNAL_COLLECTION = "admission_journal"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def get_host_capability_view() -> Dict[str, Any]:
    """Boot-time host capability + persisted profile."""
    try:
        from engines.host_capability import current as _current
        caps = _current()
        if caps is None:
            return {"available": False, "error": "host_capability not detected"}
        return {
            "available":             True,
            "host_id":               caps.host_id,
            "hostname":              caps.hostname,
            "detected_at":           caps.detected_at,
            "logical_cpu_count":     caps.logical_cpu_count,
            "effective_cpu_count":   caps.effective_cpu_count,
            "mem_total_gb":          caps.mem_total_gb,
            "mem_available_gb":      caps.mem_available_gb,
            "swap_total_gb":         caps.swap_total_gb,
            "cgroup_cpu_quota":      caps.cgroup_cpu_quota,
            "profile":               caps.profile,
        }
    except Exception as e:                                     # pragma: no cover
        return {"available": False, "error": str(e)[:200]}


async def get_queue_pressure_view() -> Dict[str, Any]:
    """Live queue pressure snapshot (rolling window + worker util)."""
    try:
        from engines import queue_pressure
        return queue_pressure.snapshot()
    except Exception as e:                                     # pragma: no cover
        return {"available": False, "error": str(e)[:200]}


async def get_concurrency_recommendation() -> Dict[str, Any]:
    """Current ConcurrencyTargets + inputs that produced it."""
    try:
        from engines import adaptive_concurrency, compute_probe, host_capability, queue_pressure
        caps    = host_capability.current()
        probe   = compute_probe.snapshot()
        press   = queue_pressure.snapshot()
        targets = adaptive_concurrency.recommend(caps, probe, press)
        return {
            "host_profile":   caps.profile if caps else None,
            "probe_band":     targets.derivation.get("probe_band"),
            "pressure_band":  press.get("pressure_band"),
            "final_band":     targets.band,
            "targets":        targets.to_dict(),
            "evaluated_at":   _now_iso(),
        }
    except Exception as e:                                     # pragma: no cover
        return {"available": False, "error": str(e)[:200]}


async def get_admission_journal_stats(window_sec: int = 3600) -> Dict[str, Any]:
    """Per-class admit/defer/refuse counters across the last window.

    Returns:
        {
          "window_sec": int,
          "total":      int,
          "per_decision": {"admit": int, "defer": int, "refuse": int},
          "per_class":    {<class>: {"admit": int, "defer": int, "refuse": int}, ...},
          "evaluated_at": iso-string,
        }
    """
    window_sec = max(1, min(int(window_sec), 86400 * 30))
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(seconds=window_sec)).isoformat()
    per_decision: Dict[str, int] = {"admit": 0, "defer": 0, "refuse": 0}
    per_class: Dict[str, Dict[str, int]] = {}
    total = 0
    try:
        from engines.db import get_db
        db = get_db()
        pipeline = [
            {"$match": {"evaluated_at": {"$gte": cutoff_iso}}},
            {"$group": {
                "_id":  {"class_": "$class_", "decision": "$decision"},
                "n":    {"$sum": 1},
            }},
        ]
        async for row in db[ADMISSION_JOURNAL_COLLECTION].aggregate(pipeline):
            klass = row["_id"].get("class_") or "unknown"
            dec   = row["_id"].get("decision") or "unknown"
            n     = int(row["n"])
            total += n
            per_decision.setdefault(dec, 0)
            per_decision[dec] += n
            per_class.setdefault(klass, {"admit": 0, "defer": 0, "refuse": 0})
            per_class[klass].setdefault(dec, 0)
            per_class[klass][dec] += n
    except Exception as e:                                     # pragma: no cover
        return {
            "window_sec": window_sec, "total": 0,
            "per_decision": per_decision, "per_class": per_class,
            "evaluated_at": _now_iso(), "error": str(e)[:200],
        }

    return {
        "window_sec":   window_sec,
        "total":        total,
        "per_decision": per_decision,
        "per_class":    per_class,
        "evaluated_at": _now_iso(),
    }


async def get_full_architect_snapshot(window_sec: int = 3600) -> Dict[str, Any]:
    """One-shot read of every Architect-visible surface.

    Bundles the four `get_*` calls into a single dict so the future
    Architect can grab everything it needs in a single round trip.
    """
    host       = await get_host_capability_view()
    pressure   = await get_queue_pressure_view()
    concur     = await get_concurrency_recommendation()
    journal    = await get_admission_journal_stats(window_sec)
    return {
        "evaluated_at":               _now_iso(),
        "host_capability":            host,
        "queue_pressure":             pressure,
        "concurrency_recommendation": concur,
        "admission_journal_stats":    journal,
    }
