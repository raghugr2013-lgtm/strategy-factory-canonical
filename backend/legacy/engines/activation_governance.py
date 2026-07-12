"""
Phase 2 scaffolding — Activation governance aggregator (READ-ONLY).

A single function that gathers every dormant-vs-active piece of state
in the platform so operators can answer "is the system safe to widen?"
from one read.

Reads from (no writes anywhere):
  * engines.feature_flags          — all flags, defaults, overrides
  * engines.cpu_pool               — pool state
  * engines.orchestrator_scheduler — scheduler enable + cooldown
  * engines.auto_scheduler         — scheduler enable + subordination
  * engines.advisory_lock          — held lock count (via Mongo)
  * engines.compute_probe          — host CPU/mem/load snapshot
  * engines.env_priority           — adaptive config + master enable
  * engines.governance_universe    — operator-decreed boundary
  * engines.cadence_scheduler      — dormant
  * engines.adaptive_cooldown      — dormant
  * engines.event_continuation     — dormant
  * engines.replay_priority        — dormant

Every individual read is wrapped so one subsystem failure cannot
prevent the others from reporting. Returns a JSON-safe dict.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _safe_call(label: str, awaitable):
    try:
        return await awaitable
    except Exception as e:
        logger.debug("[activation_governance] %s failed: %s", label, e)
        return {"error": str(e)[:200]}


def _safe(label: str, fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        logger.debug("[activation_governance] %s failed: %s", label, e)
        return {"error": str(e)[:200]}


async def collect() -> Dict[str, Any]:
    """Build the unified activation-governance snapshot. Never raises."""
    from engines import feature_flags as ff
    from engines import cpu_pool, compute_probe
    from engines import adaptive_cooldown, replay_priority

    out: Dict[str, Any] = {
        "ts":     _now_iso(),
        "phase":  "scaffolding-1",
    }

    # ── Feature flag manifest ──────────────────────────────────────
    flags_snapshot = _safe("feature_flags.all_flags", ff.all_flags)
    active_overrides = _safe("feature_flags.active_flags", ff.active_flags)
    out["feature_flags"] = {
        "flag_count":      len(flags_snapshot) if isinstance(flags_snapshot, dict) else 0,
        "active_overrides": active_overrides if isinstance(active_overrides, dict) else {},
        "all_dormant":     not (isinstance(active_overrides, dict) and active_overrides),
    }

    # ── CPU pool ──────────────────────────────────────────────────
    out["cpu_pool"] = _safe("cpu_pool.get_pool_state", cpu_pool.get_pool_state)

    # ── Compute probe ─────────────────────────────────────────────
    snap = _safe("compute_probe.snapshot", compute_probe.snapshot)
    out["compute"] = {
        "snapshot":         snap,
        "headroom":         _safe(
            "compute_probe.headroom_summary",
            compute_probe.headroom_summary, snap if isinstance(snap, dict) else None,
        ),
    }

    # ── Orchestrator + auto scheduler ──────────────────────────────
    try:
        from engines import orchestrator_scheduler as orc_sched
        out["orchestrator_scheduler"] = await _safe_call(
            "orchestrator_scheduler.get_status", orc_sched.get_status(),
        )
    except Exception as e:                                   # pragma: no cover
        out["orchestrator_scheduler"] = {"error": str(e)[:200]}
    try:
        from engines import auto_scheduler
        out["auto_scheduler"] = await _safe_call(
            "auto_scheduler.get_status", auto_scheduler.get_status(),
        )
    except Exception as e:                                   # pragma: no cover
        out["auto_scheduler"] = {"error": str(e)[:200]}

    # ── Advisory lock count ───────────────────────────────────────
    try:
        from engines.db import get_db
        n = await get_db()["advisory_locks"].count_documents({})
        out["advisory_locks"] = {"held_count": int(n)}
    except Exception as e:                                   # pragma: no cover
        out["advisory_locks"] = {"error": str(e)[:200]}

    # ── env_priority ──────────────────────────────────────────────
    try:
        from engines import env_priority
        cfg = await env_priority.get_config()
        out["env_priority"] = {
            "adaptation_enabled": bool((cfg.get("knobs") or {}).get("adaptation_enabled", True)),
            "tiers":              list((cfg.get("tiers") or {}).keys()),
            "exploratory_floor":  float((cfg.get("knobs") or {}).get("exploratory_floor", 0)),
        }
    except Exception as e:                                   # pragma: no cover
        out["env_priority"] = {"error": str(e)[:200]}

    # ── governance_universe ────────────────────────────────────────
    try:
        from engines import governance_universe as gu
        uni = await gu.get_universe()
        out["governance_universe"] = {
            "pairs":        uni.get("pairs"),
            "timeframes":   uni.get("timeframes"),
            "styles":       uni.get("styles"),
            "updated_at":   uni.get("updated_at"),
            "updated_by":   uni.get("updated_by"),
        }
    except Exception as e:                                   # pragma: no cover
        out["governance_universe"] = {"error": str(e)[:200]}

    # ── Dormant primitives ────────────────────────────────────────
    try:
        from engines import cadence_scheduler
        out["cadence_scheduler"] = {
            "enabled":         cadence_scheduler.is_enabled(),
            "min_gap_minutes": cadence_scheduler.min_gap_minutes(),
        }
    except Exception as e:                                   # pragma: no cover
        out["cadence_scheduler"] = {"error": str(e)[:200]}

    out["adaptive_cooldown"] = _safe(
        "adaptive_cooldown.explain",
        adaptive_cooldown.explain, 120.0, recent_errors=0,
    )

    try:
        from engines import event_continuation
        out["event_continuation"] = await _safe_call(
            "event_continuation.snapshot", event_continuation.snapshot(limit=10),
        )
    except Exception as e:                                   # pragma: no cover
        out["event_continuation"] = {"error": str(e)[:200]}

    out["replay_priority"] = {
        "enabled": replay_priority.is_enabled(),
    }

    # ── Safe-to-widen summary (purely arithmetic, no thresholds with
    #     operator authority — UI decides) ─────────────────────────
    headroom_ok = bool(
        isinstance(out.get("compute"), dict)
        and isinstance(out["compute"].get("headroom"), dict)
        and out["compute"]["headroom"].get("ok") is True
    )
    no_errors = not any(
        isinstance(v, dict) and "error" in v
        for v in (
            out.get("orchestrator_scheduler"),
            out.get("auto_scheduler"),
            out.get("env_priority"),
            out.get("governance_universe"),
        )
    )
    out["summary"] = {
        "all_dormant":     out["feature_flags"]["all_dormant"],
        "host_headroom_ok": headroom_ok,
        "subsystems_reporting": no_errors,
    }

    return out
