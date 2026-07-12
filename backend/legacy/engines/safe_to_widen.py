"""
Phase 1+2 scaffolding — Safe-to-widen governance advisor (READ-ONLY).

A deterministic, pure-observation aggregator that answers ONE question:

    "If the operator flipped the next activation flag in the S0–S9
     sequence right now, would the system survive it?"

Discipline:
  * Strictly READ-ONLY. No DB writes, no env mutation, no scheduler
    interaction, no flag mutation, no automatic activation.
  * Advisory only. Operator remains final authority.
  * Deterministic. Same observations → same verdict. No probabilistic
    scoring, no model lookups, no LLM calls.
  * Best-effort. Per-check failure cannot mask other checks; on any
    internal error the check is reported as `fail` with reason.

Output shape (consumed by /api/latent/safe-to-widen):

    {
      "ts":             iso8601,
      "advisory_only":  true,
      "operator_authority": "final",
      "current_stage":  "S0" .. "S9",
      "next_stage":     "S1" .. "S9" | None,
      "verdict":        "SAFE" | "WARNING" | "BLOCKED",
      "blocking_reasons":  [str, ...],
      "warning_reasons":   [str, ...],
      "checks":         [ {id, category, status, value, threshold,
                           detail}, ... ],
      "recommendations": {
          "next_activation":           str | None,
          "soak_duration_days":        int,
          "max_concurrent_cells":      int,
          "scheduler_cadence_minutes": int,
          "orchestration_breadth_depth": float (0..1),
      },
    }

Stages tracked (matches PRD §4 activation sequencing):

    S0  factory_runner sibling registered in supervisor (heartbeat seen)
    S1  USE_PROCESS_POOL=true (pool initialised empty)
    S2  ENABLE_PROCESS_POOL_BACKTEST=true
    S3  ENABLE_PROCESS_POOL_MUTATION=true
    S4  ENABLE_CADENCE_SCHEDULER=true
    S5  ENABLE_ADAPTIVE_COOLDOWN=true
    S6  ENABLE_AUTONOMOUS_DISCOVERY=true
    S7  ENABLE_REPLAY_PRIORITY=true
    S8  ENABLE_EVENT_CONTINUATION=true
    S9  COMPUTE_AWARE_ORCHESTRATION=true
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Stage definition table — single source of truth for the roadmap.
# Each entry describes:
#   * the env flag whose `true` value marks the stage DONE
#   * the human description used in recommendations
#   * the recommended soak duration before the NEXT stage
#   * the recommended breadth/depth slider (0=depth-only … 1=breadth-only)
#   * the recommended max concurrent cells
#   * the recommended scheduler cadence (minutes)
#
# These recommendations are conservative defaults; the operator may
# override at will. They are NOT thresholds — they are HINTS.
# ─────────────────────────────────────────────────────────────────────
_STAGE_PLAN: Tuple[Dict[str, Any], ...] = (
    {
        "id":       "S0",
        "marker":   "factory_runner_heartbeat",  # special-case (audit_log)
        "label":    "factory_runner sibling registered in supervisor",
        "soak_days": 14, "breadth_depth": 0.4,
        "max_cells": 1,  "cadence_min": 15,
    },
    {
        "id":       "S1",
        "marker":   "env:USE_PROCESS_POOL",
        "label":    "USE_PROCESS_POOL=true (pool dormant, no callers yet)",
        "soak_days": 14, "breadth_depth": 0.4,
        "max_cells": 2,  "cadence_min": 15,
    },
    {
        "id":       "S2",
        "marker":   "flag:ENABLE_PROCESS_POOL_BACKTEST",
        "label":    "ENABLE_PROCESS_POOL_BACKTEST=true (one backtest hot path)",
        "soak_days": 14, "breadth_depth": 0.45,
        "max_cells": 3,  "cadence_min": 15,
    },
    {
        "id":       "S3",
        "marker":   "flag:ENABLE_PROCESS_POOL_MUTATION",
        "label":    "ENABLE_PROCESS_POOL_MUTATION=true (mutation hot path)",
        "soak_days": 14, "breadth_depth": 0.5,
        "max_cells": 4,  "cadence_min": 15,
    },
    {
        "id":       "S4",
        "marker":   "flag:ENABLE_CADENCE_SCHEDULER",
        "label":    "ENABLE_CADENCE_SCHEDULER=true + wire call-site",
        "soak_days": 14, "breadth_depth": 0.5,
        "max_cells": 5,  "cadence_min": 15,
    },
    {
        "id":       "S5",
        "marker":   "flag:ENABLE_ADAPTIVE_COOLDOWN",
        "label":    "ENABLE_ADAPTIVE_COOLDOWN=true + hook into orchestrator",
        "soak_days": 14, "breadth_depth": 0.5,
        "max_cells": 6,  "cadence_min": 15,
    },
    {
        "id":       "S6",
        "marker":   "flag:ENABLE_AUTONOMOUS_DISCOVERY",
        "label":    "ENABLE_AUTONOMOUS_DISCOVERY=true + RULE 12 module constant flip",
        "soak_days": 21, "breadth_depth": 0.55,
        "max_cells": 6,  "cadence_min": 20,
    },
    {
        "id":       "S7",
        "marker":   "flag:ENABLE_REPLAY_PRIORITY",
        "label":    "ENABLE_REPLAY_PRIORITY=true + route BI5 sweep through prioritize()",
        "soak_days": 14, "breadth_depth": 0.55,
        "max_cells": 7,  "cadence_min": 20,
    },
    {
        "id":       "S8",
        "marker":   "flag:ENABLE_EVENT_CONTINUATION",
        "label":    "ENABLE_EVENT_CONTINUATION=true + factory_runner poller",
        "soak_days": 14, "breadth_depth": 0.6,
        "max_cells": 8,  "cadence_min": 20,
    },
    {
        "id":       "S9",
        "marker":   "flag:COMPUTE_AWARE_ORCHESTRATION",
        "label":    "COMPUTE_AWARE_ORCHESTRATION=true + compute_probe read in decide()",
        "soak_days": 30, "breadth_depth": 0.6,
        "max_cells": 8,  "cadence_min": 20,
    },
)


# Deterministic pass thresholds. These are governance hints, NOT
# authority — flipping them in this file affects only the advisory
# verdict, never any runtime behaviour.
THRESH = {
    "cpu_headroom_pct_min_warn":   25.0,
    "cpu_headroom_pct_min_block":  15.0,
    "ram_headroom_pct_min_warn":   25.0,
    "ram_headroom_pct_min_block":  15.0,
    "open_fds_warn":               2000,
    "open_fds_block":               4000,
    "tick_error_rate_warn":         0.05,
    "tick_error_rate_block":        0.15,
    "auto_cycle_error_rate_warn":   0.20,
    "auto_cycle_error_rate_block":  0.40,
    "advisory_locks_warn":          1,    # >1 held simultaneously is unusual
    "advisory_locks_block":         3,
    "cooldown_anomaly_block_sec":   600,  # remaining >> COOLDOWN is anomalous
    "soak_days_block":              3,    # less than 3 days since prior widen
    "soak_days_warn":               7,
    "scheduler_overdue_warn_x":     1.5,  # next_run_at is >1.5× interval overdue
    "scheduler_overdue_block_x":    3.0,
    "load_per_core_warn":           1.0,  # >= host saturated
    "load_per_core_block":          1.5,
    "event_queue_warn":             50,
    "event_queue_block":            500,
    "survivor_universe_min_warn":   3,    # cohort-too-small advisory floor
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _check(
    cid: str, category: str, status: str,
    *, value: Any = None, threshold: Any = None,
    detail: str = "",
) -> Dict[str, Any]:
    """Build a single check row. `status` ∈ {pass, warn, fail}."""
    if status not in ("pass", "warn", "fail"):
        status = "fail"
    return {
        "id":        cid,
        "category":  category,
        "status":    status,
        "value":     value,
        "threshold": threshold,
        "detail":    str(detail)[:240],
    }


# ─────────────────────────────────────────────────────────────────────
# Stage detection — purely reads env + audit_log; never writes.
# ─────────────────────────────────────────────────────────────────────

def _env_bool(name: str) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


async def _factory_runner_recent_heartbeat(db, *, within_min: int = 10) -> bool:
    """True iff a `factory_runner:heartbeat` (or `:startup`) audit row
    has landed in the last `within_min` minutes."""
    try:
        cutoff_dt = _now() - timedelta(minutes=int(within_min))
        doc = await db["audit_log"].find_one(
            {
                "event": {"$in": [
                    "factory_runner:heartbeat",
                    "factory_runner:startup",
                ]},
                "ts_dt": {"$gte": cutoff_dt},
            },
            {"_id": 0, "event": 1, "ts": 1},
        )
        return bool(doc)
    except Exception:                                       # pragma: no cover
        return False


async def _detect_current_stage(db) -> Tuple[str, Optional[str]]:
    """Return (current_stage_id, next_stage_id_or_None) by inspecting
    which stage markers are currently satisfied.

    A stage is "achieved" when:
      * S0  — factory_runner heartbeat seen recently
      * S1+ — the env flag is set to a truthy value

    The HIGHEST achieved stage is the current stage. The next stage is
    the one immediately after; None when S9 is achieved.
    """
    achieved: List[str] = []
    s0_ok = await _factory_runner_recent_heartbeat(db)
    if s0_ok:
        achieved.append("S0")
    for stage in _STAGE_PLAN[1:]:
        marker = stage["marker"]
        if marker.startswith("env:") and _env_bool(marker.split(":", 1)[1]):
            achieved.append(stage["id"])
        elif marker.startswith("flag:") and _env_bool(marker.split(":", 1)[1]):
            achieved.append(stage["id"])
    if not achieved:
        return ("PRE-S0", "S0")
    current = achieved[-1]  # ordered already
    # Next is the stage whose id is one higher (if it exists).
    ids = [s["id"] for s in _STAGE_PLAN]
    try:
        idx = ids.index(current)
        nxt = ids[idx + 1] if idx + 1 < len(ids) else None
    except ValueError:                                       # pragma: no cover
        nxt = None
    return (current, nxt)


def _plan_for(stage_id: str) -> Dict[str, Any]:
    for s in _STAGE_PLAN:
        if s["id"] == stage_id:
            return s
    # PRE-S0 fallback — recommend S0 plan.
    return _STAGE_PLAN[0]


# ─────────────────────────────────────────────────────────────────────
# Soak duration check — uses the audit_log activation timeline.
# ─────────────────────────────────────────────────────────────────────

async def _last_widening_age_days(db) -> Optional[float]:
    """Wall-clock days since the most recent `latent_capability:override_diff`
    row. None when no diff row has ever been written (i.e. the system
    has never widened anything yet — soak is effectively the whole
    backend boot history)."""
    try:
        doc = await db["audit_log"].find_one(
            {"event": "latent_capability:override_diff"},
            {"_id": 0, "ts_dt": 1},
            sort=[("ts_dt", -1)],
        )
        if not doc:
            return None
        ts = doc.get("ts_dt")
        if not isinstance(ts, datetime):
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (_now() - ts).total_seconds() / 86400.0)
    except Exception:                                       # pragma: no cover
        return None


def stage_from_active_overrides(
    overrides: Dict[str, Any],
    *,
    factory_runner_seen: bool = False,
) -> Tuple[str, Optional[str]]:
    """Pure helper — given an ``active_overrides`` dict (the form
    persisted in ``audit_log.latent_capability:boot_state``) plus a
    boolean indicating whether a factory_runner heartbeat was observed
    in the relevant window, return ``(current_stage, next_stage)``.

    Reuses the same ``_STAGE_PLAN`` table the live evaluator uses, so
    historical / live stage detection cannot drift. The
    ``USE_PROCESS_POOL`` and ``FACTORY_RUNNER_OWNS_SCHEDULERS`` markers
    are NOT in the feature_flags registry (they're Phase D env flags);
    historical detection can only see them when the caller passes them
    through ``overrides`` explicitly. Best effort otherwise.
    """
    achieved: List[str] = []
    if factory_runner_seen:
        achieved.append("S0")
    for stage in _STAGE_PLAN[1:]:
        marker = stage["marker"]
        if not marker:
            continue
        if marker.startswith("env:"):
            name = marker.split(":", 1)[1]
            val = overrides.get(name) if isinstance(overrides, dict) else None
            if isinstance(val, bool) and val:
                achieved.append(stage["id"])
            elif isinstance(val, str) and val.strip().lower() in ("1", "true", "yes", "on"):
                achieved.append(stage["id"])
        elif marker.startswith("flag:"):
            name = marker.split(":", 1)[1]
            val = overrides.get(name) if isinstance(overrides, dict) else None
            if isinstance(val, bool) and val:
                achieved.append(stage["id"])
    if not achieved:
        return ("PRE-S0", "S0")
    current = achieved[-1]
    ids = [s["id"] for s in _STAGE_PLAN]
    try:
        idx = ids.index(current)
        nxt = ids[idx + 1] if idx + 1 < len(ids) else None
    except ValueError:                                       # pragma: no cover
        nxt = None
    return (current, nxt)


def stage_plan() -> List[Dict[str, Any]]:
    """Return a JSON-safe copy of the stage table for diagnostic surfaces."""
    return [dict(s) for s in _STAGE_PLAN]


# ─────────────────────────────────────────────────────────────────────
# Main evaluator
# ─────────────────────────────────────────────────────────────────────

async def evaluate() -> Dict[str, Any]:
    """Build the full safe-to-widen advisory payload. Never raises."""
    # Lazy imports so a subsystem outage cannot prevent the rest of the
    # evaluator from running.
    from engines import (
        compute_probe, cpu_pool, feature_flags as ff,
    )
    from engines.db import get_db

    out: Dict[str, Any] = {
        "ts":                  _now_iso(),
        "advisory_only":       True,
        "operator_authority":  "final",
        "phase":               "scaffolding-1",
    }
    checks: List[Dict[str, Any]] = []

    db = get_db()

    # ── Stage detection ──────────────────────────────────────────
    try:
        current, nxt = await _detect_current_stage(db)
    except Exception as e:                                  # pragma: no cover
        current, nxt = "PRE-S0", "S0"
        logger.debug("[safe_to_widen] stage detection failed: %s", e)
    out["current_stage"] = current
    out["next_stage"]    = nxt

    # ── 1. CPU headroom ──────────────────────────────────────────
    try:
        snap = compute_probe.snapshot()
        cpu_p = snap.get("cpu_percent")
        cpu_head = (100.0 - float(cpu_p)) if isinstance(cpu_p, (int, float)) else None
        if cpu_head is None:
            checks.append(_check("cpu_headroom", "compute", "warn",
                                 detail="psutil unavailable"))
        elif cpu_head < THRESH["cpu_headroom_pct_min_block"]:
            checks.append(_check("cpu_headroom", "compute", "fail",
                                 value=round(cpu_head, 1),
                                 threshold=THRESH["cpu_headroom_pct_min_block"],
                                 detail="cpu headroom below block floor"))
        elif cpu_head < THRESH["cpu_headroom_pct_min_warn"]:
            checks.append(_check("cpu_headroom", "compute", "warn",
                                 value=round(cpu_head, 1),
                                 threshold=THRESH["cpu_headroom_pct_min_warn"],
                                 detail="cpu headroom thin"))
        else:
            checks.append(_check("cpu_headroom", "compute", "pass",
                                 value=round(cpu_head, 1),
                                 threshold=THRESH["cpu_headroom_pct_min_warn"]))
    except Exception as e:                                  # pragma: no cover
        checks.append(_check("cpu_headroom", "compute", "fail",
                             detail=f"probe failed: {str(e)[:120]}"))

    # ── 2. RAM headroom ──────────────────────────────────────────
    try:
        snap = compute_probe.snapshot()
        mem_p = snap.get("mem_percent")
        mem_head = (100.0 - float(mem_p)) if isinstance(mem_p, (int, float)) else None
        if mem_head is None:
            checks.append(_check("ram_headroom", "compute", "warn",
                                 detail="psutil unavailable"))
        elif mem_head < THRESH["ram_headroom_pct_min_block"]:
            checks.append(_check("ram_headroom", "compute", "fail",
                                 value=round(mem_head, 1),
                                 threshold=THRESH["ram_headroom_pct_min_block"]))
        elif mem_head < THRESH["ram_headroom_pct_min_warn"]:
            checks.append(_check("ram_headroom", "compute", "warn",
                                 value=round(mem_head, 1),
                                 threshold=THRESH["ram_headroom_pct_min_warn"]))
        else:
            checks.append(_check("ram_headroom", "compute", "pass",
                                 value=round(mem_head, 1),
                                 threshold=THRESH["ram_headroom_pct_min_warn"]))
    except Exception as e:                                  # pragma: no cover
        checks.append(_check("ram_headroom", "compute", "fail",
                             detail=f"probe failed: {str(e)[:120]}"))

    # ── 3. Load per core ─────────────────────────────────────────
    try:
        snap = compute_probe.snapshot()
        head = compute_probe.headroom_summary(snap)
        lpc = head.get("load_per_core")
        if lpc is None:
            checks.append(_check("load_per_core", "compute", "warn",
                                 detail="loadavg unavailable"))
        elif lpc >= THRESH["load_per_core_block"]:
            checks.append(_check("load_per_core", "compute", "fail",
                                 value=lpc, threshold=THRESH["load_per_core_block"],
                                 detail="host over-subscribed"))
        elif lpc >= THRESH["load_per_core_warn"]:
            checks.append(_check("load_per_core", "compute", "warn",
                                 value=lpc, threshold=THRESH["load_per_core_warn"]))
        else:
            checks.append(_check("load_per_core", "compute", "pass",
                                 value=lpc, threshold=THRESH["load_per_core_warn"]))
    except Exception:                                       # pragma: no cover
        checks.append(_check("load_per_core", "compute", "warn",
                             detail="check unavailable"))

    # ── 4. Open FDs ──────────────────────────────────────────────
    try:
        snap = compute_probe.snapshot()
        fds = snap.get("open_fds")
        if not isinstance(fds, int):
            checks.append(_check("open_fds", "compute", "warn",
                                 detail="fd count unavailable"))
        elif fds >= THRESH["open_fds_block"]:
            checks.append(_check("open_fds", "compute", "fail",
                                 value=fds, threshold=THRESH["open_fds_block"]))
        elif fds >= THRESH["open_fds_warn"]:
            checks.append(_check("open_fds", "compute", "warn",
                                 value=fds, threshold=THRESH["open_fds_warn"]))
        else:
            checks.append(_check("open_fds", "compute", "pass",
                                 value=fds, threshold=THRESH["open_fds_warn"]))
    except Exception:                                       # pragma: no cover
        checks.append(_check("open_fds", "compute", "warn",
                             detail="check unavailable"))

    # ── 5. Orchestration cadence (overdue?) ──────────────────────
    try:
        from engines import orchestrator_scheduler as orc_sched
        st = await orc_sched.get_status()
        enabled = bool(st.get("enabled"))
        interval = int(st.get("interval_minutes") or 15)
        next_iso = st.get("next_run_at")
        if not enabled:
            checks.append(_check("orchestration_cadence", "scheduling", "pass",
                                 value="scheduler_off",
                                 detail="orchestrator scheduler not running — "
                                        "no cadence concern"))
        elif not next_iso:
            checks.append(_check("orchestration_cadence", "scheduling", "warn",
                                 detail="enabled but no next_run_at"))
        else:
            try:
                nxt_dt = datetime.fromisoformat(next_iso.replace("Z", "+00:00"))
                if nxt_dt.tzinfo is None:
                    nxt_dt = nxt_dt.replace(tzinfo=timezone.utc)
                overdue_min = (_now() - nxt_dt).total_seconds() / 60.0
                overdue_x = overdue_min / max(1, interval)
                if overdue_min <= 0:
                    checks.append(_check("orchestration_cadence", "scheduling", "pass",
                                         value=round(overdue_x, 2),
                                         threshold=THRESH["scheduler_overdue_warn_x"]))
                elif overdue_x >= THRESH["scheduler_overdue_block_x"]:
                    checks.append(_check("orchestration_cadence", "scheduling", "fail",
                                         value=round(overdue_x, 2),
                                         threshold=THRESH["scheduler_overdue_block_x"],
                                         detail=f"scheduler {overdue_min:.0f}m overdue"))
                elif overdue_x >= THRESH["scheduler_overdue_warn_x"]:
                    checks.append(_check("orchestration_cadence", "scheduling", "warn",
                                         value=round(overdue_x, 2),
                                         threshold=THRESH["scheduler_overdue_warn_x"]))
                else:
                    checks.append(_check("orchestration_cadence", "scheduling", "pass",
                                         value=round(overdue_x, 2)))
            except Exception:                              # pragma: no cover
                checks.append(_check("orchestration_cadence", "scheduling", "warn",
                                     detail="could not parse next_run_at"))
    except Exception as e:                                  # pragma: no cover
        checks.append(_check("orchestration_cadence", "scheduling", "warn",
                             detail=f"probe failed: {str(e)[:120]}"))

    # ── 6. Orchestration error rate ──────────────────────────────
    try:
        st = await orc_sched.get_status()
        tick_count = int(st.get("tick_count") or 0)
        last_error = st.get("last_error")
        # Rate from auto_run_cycles last 50 rows (most reliable signal).
        total = 0
        errors = 0
        cur = db["auto_run_cycles"].find(
            {}, {"_id": 0, "status": 1},
        ).sort("finished_at", -1).limit(50)
        async for row in cur:
            total += 1
            st_ = (row.get("status") or "").lower()
            if st_ in ("error", "timeout"):
                errors += 1
        rate = (errors / total) if total > 0 else 0.0
        meta = {"sampled": total, "errors": errors, "last_error": last_error,
                "tick_count": tick_count}
        if total == 0:
            checks.append(_check("orchestration_error_rate", "scheduling", "warn",
                                 value=meta, detail="no cycle samples yet"))
        elif rate >= THRESH["auto_cycle_error_rate_block"]:
            checks.append(_check("orchestration_error_rate", "scheduling", "fail",
                                 value=round(rate, 3), threshold=THRESH["auto_cycle_error_rate_block"]))
        elif rate >= THRESH["auto_cycle_error_rate_warn"]:
            checks.append(_check("orchestration_error_rate", "scheduling", "warn",
                                 value=round(rate, 3), threshold=THRESH["auto_cycle_error_rate_warn"]))
        else:
            checks.append(_check("orchestration_error_rate", "scheduling", "pass",
                                 value=round(rate, 3), threshold=THRESH["auto_cycle_error_rate_warn"]))
    except Exception as e:                                  # pragma: no cover
        checks.append(_check("orchestration_error_rate", "scheduling", "warn",
                             detail=f"probe failed: {str(e)[:120]}"))

    # ── 7. Rejected-cycle ratio ──────────────────────────────────
    try:
        total = 0
        rejected = 0
        cur = db["auto_run_cycles"].find(
            {}, {"_id": 0, "status": 1, "counts": 1},
        ).sort("finished_at", -1).limit(100)
        async for row in cur:
            total += 1
            counts = row.get("counts") or {}
            gen = int(counts.get("strategies_generated") or 0)
            saved = int(counts.get("auto_save_saved") or 0)
            if gen > 0 and saved == 0:
                rejected += 1
        rate = (rejected / total) if total > 0 else 0.0
        if total == 0:
            checks.append(_check("rejected_cycle_ratio", "quality", "warn",
                                 detail="no cycle samples yet"))
        elif rate >= 0.80:
            checks.append(_check("rejected_cycle_ratio", "quality", "fail",
                                 value=round(rate, 3), threshold=0.80,
                                 detail="≥80% of recent cycles save nothing"))
        elif rate >= 0.50:
            checks.append(_check("rejected_cycle_ratio", "quality", "warn",
                                 value=round(rate, 3), threshold=0.50))
        else:
            checks.append(_check("rejected_cycle_ratio", "quality", "pass",
                                 value=round(rate, 3), threshold=0.50))
    except Exception as e:                                  # pragma: no cover
        checks.append(_check("rejected_cycle_ratio", "quality", "warn",
                             detail=f"probe failed: {str(e)[:120]}"))

    # ── 8. Overlap / lock contention ─────────────────────────────
    try:
        held = await db["advisory_locks"].count_documents({})
        if held >= THRESH["advisory_locks_block"]:
            checks.append(_check("advisory_lock_contention", "locking", "fail",
                                 value=held, threshold=THRESH["advisory_locks_block"]))
        elif held > THRESH["advisory_locks_warn"]:
            checks.append(_check("advisory_lock_contention", "locking", "warn",
                                 value=held, threshold=THRESH["advisory_locks_warn"]))
        else:
            checks.append(_check("advisory_lock_contention", "locking", "pass",
                                 value=held, threshold=THRESH["advisory_locks_warn"]))
    except Exception:                                       # pragma: no cover
        checks.append(_check("advisory_lock_contention", "locking", "warn",
                             detail="probe failed"))

    # ── 9. Cooldown integrity ────────────────────────────────────
    try:
        from api.orchestrator import _cooldown_remaining, COOLDOWN_SECONDS
        rem = _cooldown_remaining()
        if rem > THRESH["cooldown_anomaly_block_sec"]:
            checks.append(_check("cooldown_integrity", "locking", "fail",
                                 value=round(rem, 1),
                                 threshold=THRESH["cooldown_anomaly_block_sec"],
                                 detail=f"cooldown remaining ({rem:.0f}s) much "
                                        f"greater than expected ({COOLDOWN_SECONDS}s) — "
                                        f"check clock skew"))
        else:
            checks.append(_check("cooldown_integrity", "locking", "pass",
                                 value=round(rem, 1),
                                 threshold=COOLDOWN_SECONDS))
    except Exception as e:                                  # pragma: no cover
        checks.append(_check("cooldown_integrity", "locking", "warn",
                             detail=f"probe failed: {str(e)[:120]}"))

    # ── 10. Process-pool health ──────────────────────────────────
    try:
        pool_state = cpu_pool.get_pool_state()
        flag_on = bool(pool_state.get("enabled"))
        initialised = bool(pool_state.get("pool_initialized"))
        if flag_on and not initialised:
            # Pool flag is on but no submission yet — that's the expected
            # S1 soak state. PASS with informational detail.
            checks.append(_check("process_pool_health", "compute", "pass",
                                 value=pool_state,
                                 detail="pool flag on, awaiting first submitter (S1 soak state)"))
        elif not flag_on and initialised:
            checks.append(_check("process_pool_health", "compute", "warn",
                                 value=pool_state,
                                 detail="pool flag off but executor still resident"))
        else:
            checks.append(_check("process_pool_health", "compute", "pass",
                                 value=pool_state))
    except Exception as e:                                  # pragma: no cover
        checks.append(_check("process_pool_health", "compute", "warn",
                             detail=f"probe failed: {str(e)[:120]}"))

    # ── 11. Event-continuation queue saturation ──────────────────
    try:
        from engines import event_continuation
        snap = await event_continuation.snapshot(limit=1)
        pending = int((snap.get("counts") or {}).get("pending", 0))
        if pending >= THRESH["event_queue_block"]:
            checks.append(_check("event_queue_saturation", "continuation", "fail",
                                 value=pending, threshold=THRESH["event_queue_block"]))
        elif pending >= THRESH["event_queue_warn"]:
            checks.append(_check("event_queue_saturation", "continuation", "warn",
                                 value=pending, threshold=THRESH["event_queue_warn"]))
        else:
            checks.append(_check("event_queue_saturation", "continuation", "pass",
                                 value=pending, threshold=THRESH["event_queue_warn"]))
    except Exception:                                       # pragma: no cover
        checks.append(_check("event_queue_saturation", "continuation", "warn",
                             detail="probe failed"))

    # ── 12. Replay pressure (advisory queue depth) ───────────────
    try:
        # Lightweight proxy: count of strategies in stages eligible for
        # replay that have NOT been touched by the weekly BI5 realism
        # sweep within the last 14 days.
        cutoff_iso = (_now() - timedelta(days=14)).isoformat()
        n_total = await db["strategy_lifecycle"].count_documents(
            {"current_stage": {"$in": ["elite", "portfolio_worthy", "deployment_ready"]}}
        )
        n_stale = await db["strategy_lifecycle"].count_documents({
            "current_stage": {"$in": ["elite", "portfolio_worthy", "deployment_ready"]},
            "$or": [
                {"last_realism_at": {"$exists": False}},
                {"last_realism_at": {"$lt": cutoff_iso}},
            ],
        })
        ratio = (n_stale / n_total) if n_total > 0 else 0.0
        meta = {"total_eligible": n_total, "stale_14d": n_stale,
                "stale_ratio": round(ratio, 3)}
        if n_total == 0:
            checks.append(_check("replay_pressure", "replay", "warn",
                                 value=meta, detail="no survivors yet"))
        elif ratio >= 0.80:
            checks.append(_check("replay_pressure", "replay", "warn",
                                 value=meta, threshold=0.80,
                                 detail="most survivors not realism-validated lately"))
        else:
            checks.append(_check("replay_pressure", "replay", "pass",
                                 value=meta, threshold=0.80))
    except Exception:                                       # pragma: no cover
        checks.append(_check("replay_pressure", "replay", "warn",
                             detail="probe failed"))

    # ── 13. Mutation throughput stability ────────────────────────
    try:
        # Counts the std-dev of `strategies_saved` across last 20 cycles.
        saves: List[int] = []
        cur = db["auto_run_cycles"].find(
            {"counts.auto_save_saved": {"$exists": True}},
            {"_id": 0, "counts": 1},
        ).sort("finished_at", -1).limit(20)
        async for row in cur:
            saves.append(int((row.get("counts") or {}).get("auto_save_saved") or 0))
        if len(saves) < 5:
            checks.append(_check("mutation_throughput_stability", "quality", "warn",
                                 detail=f"only {len(saves)} cycles sampled"))
        else:
            mean = sum(saves) / len(saves)
            var = sum((x - mean) ** 2 for x in saves) / len(saves)
            std = var ** 0.5
            cov = (std / mean) if mean > 0 else None
            meta = {"n": len(saves), "mean_saved": round(mean, 2),
                    "std": round(std, 2), "cov": (round(cov, 3) if cov is not None else None)}
            if cov is None:
                checks.append(_check("mutation_throughput_stability", "quality", "warn",
                                     value=meta, detail="no saves in window"))
            elif cov >= 1.5:
                checks.append(_check("mutation_throughput_stability", "quality", "warn",
                                     value=meta, threshold=1.5,
                                     detail="high cycle-to-cycle volatility"))
            else:
                checks.append(_check("mutation_throughput_stability", "quality", "pass",
                                     value=meta, threshold=1.5))
    except Exception:                                       # pragma: no cover
        checks.append(_check("mutation_throughput_stability", "quality", "warn",
                             detail="probe failed"))

    # ── 14. System soak duration since last widening ─────────────
    try:
        age = await _last_widening_age_days(db)
        if age is None:
            # No prior widening ever — soak is effectively "since boot".
            # We treat this as PASS (the operator is at S0 with the
            # ecosystem in its baseline posture).
            checks.append(_check("soak_duration", "history", "pass",
                                 value=None, detail="no prior widening recorded"))
        elif age < THRESH["soak_days_block"]:
            checks.append(_check("soak_duration", "history", "fail",
                                 value=round(age, 2),
                                 threshold=THRESH["soak_days_block"],
                                 detail="prior widening too recent"))
        elif age < THRESH["soak_days_warn"]:
            checks.append(_check("soak_duration", "history", "warn",
                                 value=round(age, 2),
                                 threshold=THRESH["soak_days_warn"]))
        else:
            checks.append(_check("soak_duration", "history", "pass",
                                 value=round(age, 2),
                                 threshold=THRESH["soak_days_warn"]))
    except Exception:                                       # pragma: no cover
        checks.append(_check("soak_duration", "history", "warn",
                             detail="probe failed"))

    # ── Aggregate verdict ────────────────────────────────────────
    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]
    if fails:
        verdict = "BLOCKED"
    elif warns:
        verdict = "WARNING"
    else:
        verdict = "SAFE"

    out["verdict"]          = verdict
    out["blocking_reasons"] = [f"{c['id']}: {c['detail'] or 'fail'}" for c in fails]
    out["warning_reasons"]  = [f"{c['id']}: {c['detail'] or 'warn'}" for c in warns]
    out["checks"]           = checks

    # ── Recommendations (advisory only) ───────────────────────────
    plan_current = _plan_for(current)
    plan_next    = _plan_for(nxt) if nxt else plan_current
    out["recommendations"] = {
        "next_activation":  plan_next["label"] if nxt else None,
        "next_activation_stage": nxt,
        "soak_duration_days": int(plan_current["soak_days"]),
        "max_concurrent_cells": int(plan_current["max_cells"]),
        "scheduler_cadence_minutes": int(plan_current["cadence_min"]),
        "orchestration_breadth_depth": float(plan_current["breadth_depth"]),
    }

    # ── Feature-flag manifest summary (NOT a check, just context) ──
    try:
        snapshot = ff.all_flags()
        active = ff.active_flags()
        out["flags_summary"] = {
            "flag_count":      len(snapshot),
            "active_overrides": active,
            "all_dormant":     not active,
        }
    except Exception:                                       # pragma: no cover
        out["flags_summary"] = {"error": "probe failed"}

    return out
