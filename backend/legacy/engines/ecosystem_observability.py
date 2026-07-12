"""
Phase 1+2 scaffolding — Ecosystem Observability (READ-ONLY aggregators).

Four pure aggregators that surface the institutional state of the
research ecosystem ahead of any widening. Each function:

  * Is async, READ-ONLY, never raises.
  * Reads from collections we already maintain (no new persistence).
  * Returns a JSON-safe dict.
  * Carries no authority — every payload includes `read_only=true,
    governance_authority=false, operator_authority="final"`.

Public surface:
  orchestration_health()    — scheduler + tick + cooldown + error metrics
  replay_allocation()       — replay queue snapshot (current vs prioritized)
  mutation_saturation()     — mutation throughput + variant exhaustion + type-weight evolution
  ecosystem_allocation()    — universe × env_priority × survivor-universe utilisation
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from engines.db import get_db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(extra: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "ts":                  _now_iso(),
        "read_only":           True,
        "governance_authority": False,
        "operator_authority":  "final",
        "phase":               "scaffolding-1",
        **extra,
    }


# ════════════════════════════════════════════════════════════════════
# 1. Orchestration health
# ════════════════════════════════════════════════════════════════════

async def orchestration_health() -> Dict[str, Any]:
    """Aggregate scheduler + tick + cooldown + recent cycle telemetry."""
    out: Dict[str, Any] = {}
    db = get_db()

    # Orchestrator scheduler.
    try:
        from engines import orchestrator_scheduler as orc_sched
        out["orchestrator_scheduler"] = await orc_sched.get_status()
    except Exception as e:                                  # pragma: no cover
        out["orchestrator_scheduler"] = {"error": str(e)[:200]}

    # Auto-discovery scheduler (with subordination flag).
    try:
        from engines import auto_scheduler
        out["auto_scheduler"] = await auto_scheduler.get_status()
    except Exception as e:                                  # pragma: no cover
        out["auto_scheduler"] = {"error": str(e)[:200]}

    # Live multi-cycle snapshot (in-memory).
    try:
        from engines import multi_cycle_runner as mcr
        out["multi_cycle_live"] = mcr.get_status()
    except Exception as e:                                  # pragma: no cover
        out["multi_cycle_live"] = {"error": str(e)[:200]}

    # Cooldown integrity.
    try:
        from api.orchestrator import _cooldown_remaining, COOLDOWN_SECONDS
        out["cooldown"] = {
            "seconds":     COOLDOWN_SECONDS,
            "remaining":   round(_cooldown_remaining(), 1),
            "integrity_ok": _cooldown_remaining() <= COOLDOWN_SECONDS,
        }
    except Exception as e:                                  # pragma: no cover
        out["cooldown"] = {"error": str(e)[:200]}

    # Advisory-lock count.
    try:
        held = await db["advisory_locks"].count_documents({})
        out["advisory_locks"] = {"held": int(held)}
    except Exception as e:                                  # pragma: no cover
        out["advisory_locks"] = {"error": str(e)[:200]}

    # Last 50 auto cycles — status histogram.
    try:
        hist: Dict[str, int] = {}
        async for row in db["auto_run_cycles"].find(
            {}, {"_id": 0, "status": 1},
        ).sort("finished_at", -1).limit(50):
            st = (row.get("status") or "unknown").lower()
            hist[st] = hist.get(st, 0) + 1
        total = sum(hist.values())
        errs = hist.get("error", 0) + hist.get("timeout", 0)
        out["recent_cycles"] = {
            "sampled":     total,
            "status_histogram": hist,
            "error_rate":  round(errs / total, 3) if total > 0 else None,
        }
    except Exception as e:                                  # pragma: no cover
        out["recent_cycles"] = {"error": str(e)[:200]}

    return _envelope(out)


# ════════════════════════════════════════════════════════════════════
# 2. Replay allocation
# ════════════════════════════════════════════════════════════════════

async def replay_allocation(limit: int = 20) -> Dict[str, Any]:
    """Snapshot of the replay candidate pool (elite-plus stages).

    Surfaces (a) the current ORDER (insertion-by-creation), and
    (b) what the order WOULD be under `replay_priority.prioritize` —
    so operators can see the difference before flipping the flag.
    """
    limit = max(1, min(int(limit), 200))
    db = get_db()

    candidates: List[Dict[str, Any]] = []
    try:
        # Pull elite-plus survivors with deploy_score evidence.
        cur = db["strategy_lifecycle"].find(
            {"current_stage": {"$in": [
                "elite", "portfolio_worthy", "deployment_ready",
            ]}},
            {"_id": 0, "strategy_hash": 1, "current_stage": 1,
             "stage_rank": 1, "evidence": 1, "last_realism_at": 1},
        ).limit(limit * 2)  # over-fetch so the prioritized view has headroom
        async for d in cur:
            candidates.append(d)
    except Exception as e:                                  # pragma: no cover
        return _envelope({"error": str(e)[:200], "candidates": [],
                          "prioritized": []})

    # Current order = creation order (Mongo natural). Prioritized order
    # = engines.replay_priority.prioritize (pure function; safe to call
    # regardless of flag state — when off it returns the input order).
    try:
        from engines import replay_priority
        prioritized = replay_priority.prioritize(candidates)[:limit]
    except Exception:                                       # pragma: no cover
        prioritized = candidates[:limit]

    # Lightweight stage breakdown.
    breakdown: Dict[str, int] = {}
    for c in candidates:
        s = c.get("current_stage") or "unknown"
        breakdown[s] = breakdown.get(s, 0) + 1

    # Realism staleness (>14d since last realism eval).
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=14)).isoformat()
    stale = sum(
        1 for c in candidates
        if not c.get("last_realism_at") or c.get("last_realism_at") < cutoff_iso
    )

    return _envelope({
        "candidates_total":      len(candidates),
        "limit":                 limit,
        "stage_breakdown":       breakdown,
        "stale_realism_14d":     stale,
        "current_order":         candidates[:limit],
        "prioritized_order":     prioritized,
        "replay_priority_enabled": _replay_priority_enabled_state(),
    })


def _replay_priority_enabled_state() -> bool:
    try:
        from engines import replay_priority
        return bool(replay_priority.is_enabled())
    except Exception:                                       # pragma: no cover
        return False


# ════════════════════════════════════════════════════════════════════
# 3. Mutation saturation
# ════════════════════════════════════════════════════════════════════

async def mutation_saturation(window_hours: int = 24) -> Dict[str, Any]:
    """Mutation throughput + variant exhaustion + per-type weight delta."""
    db = get_db()
    window_hours = max(1, min(int(window_hours), 168))
    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    cutoff_iso = cutoff_dt.isoformat()

    out: Dict[str, Any] = {
        "window_hours":  window_hours,
        "window_start":  cutoff_iso,
    }

    # Throughput: variants tried + saved in window.
    try:
        n_total = await db["mutation_stability_log"].count_documents(
            {"ts": {"$gte": cutoff_iso}},
        )
        n_saved = await db["mutation_stability_log"].count_documents(
            {"ts": {"$gte": cutoff_iso}, "auto_save_status": "saved"},
        )
        n_rejected = await db["mutation_stability_log"].count_documents(
            {"ts": {"$gte": cutoff_iso},
             "auto_save_status": {"$in": ["rejected", "skipped"]}},
        )
        out["throughput"] = {
            "total":         n_total,
            "saved":         n_saved,
            "rejected":      n_rejected,
            "save_rate":     round(n_saved / n_total, 3) if n_total > 0 else None,
            "rejection_rate": round(n_rejected / n_total, 3) if n_total > 0 else None,
        }
    except Exception as e:                                  # pragma: no cover
        out["throughput"] = {"error": str(e)[:200]}

    # Per-type distribution.
    try:
        per_type: Dict[str, Dict[str, int]] = {}
        async for row in db["mutation_stability_log"].find(
            {"ts": {"$gte": cutoff_iso}},
            {"_id": 0, "mutation_type": 1, "auto_save_status": 1},
        ):
            mt = row.get("mutation_type") or "unknown"
            st = row.get("auto_save_status") or "unknown"
            d = per_type.setdefault(mt, {"total": 0, "saved": 0, "rejected": 0})
            d["total"] += 1
            if st == "saved":
                d["saved"] += 1
            elif st in ("rejected", "skipped"):
                d["rejected"] += 1
        for mt, d in per_type.items():
            d["save_rate"] = round(d["saved"] / d["total"], 3) if d["total"] > 0 else None
        out["per_type"] = per_type
        # Variant exhaustion proxy: a type with > 30 attempts and 0
        # saves is "saturated". Advisory only.
        out["saturated_types"] = sorted(
            mt for mt, d in per_type.items()
            if d["total"] >= 30 and d["saved"] == 0
        )
    except Exception as e:                                  # pragma: no cover
        out["per_type"] = {"error": str(e)[:200]}

    # Process-pool adoption state (visibility before activation).
    try:
        from engines import mutation_pool
        out["pool_adoption"] = mutation_pool.adoption_state()
    except Exception as e:                                  # pragma: no cover
        out["pool_adoption"] = {"error": str(e)[:200]}

    return _envelope(out)


# ════════════════════════════════════════════════════════════════════
# 4. Ecosystem allocation
# ════════════════════════════════════════════════════════════════════

async def ecosystem_allocation() -> Dict[str, Any]:
    """Universe × env_priority × survivor-universe capacity utilisation."""
    out: Dict[str, Any] = {}

    # Operator-decreed universe.
    try:
        from engines import governance_universe as gu
        uni = await gu.get_universe()
        out["universe"] = {
            "pairs":       uni.get("pairs"),
            "timeframes":  uni.get("timeframes"),
            "styles":      uni.get("styles"),
            "exploration_floor_pct": uni.get("exploration_floor_pct"),
            "max_active_cells":      uni.get("max_active_cells"),
            "breadth_vs_depth":      uni.get("breadth_vs_depth"),
        }
    except Exception as e:                                  # pragma: no cover
        out["universe"] = {"error": str(e)[:200]}

    # Adaptive env_priority allocation preview (universe-filtered).
    try:
        from engines import env_priority
        allocation = await env_priority.preview_allocation()
        out["env_priority"] = {
            "cells":          len(allocation),
            "top10":          sorted(
                allocation, key=lambda r: -float(r.get("weight") or 0),
            )[:10],
        }
    except Exception as e:                                  # pragma: no cover
        out["env_priority"] = {"error": str(e)[:200]}

    # Survivor universe (top-N elite cohort).
    try:
        from engines import survivor_registry
        uni = await survivor_registry.fetch_survivor_universe()
        out["survivor_universe"] = {
            "active_count":  uni.get("active_count"),
            "cap":           uni.get("cap"),
            "headroom":      uni.get("headroom"),
            "over_cap":      uni.get("over_cap"),
            "by_stage":      uni.get("by_stage_counts"),
        }
    except Exception as e:                                  # pragma: no cover
        out["survivor_universe"] = {"error": str(e)[:200]}

    # Promotion ledger summary (per-stage counts + p50/p90 deploy_score).
    try:
        from engines import survivor_registry
        ledger = await survivor_registry.fetch_promotion_ledger()
        out["promotion_ledger"] = {
            "stages":            ledger.get("stages"),
            "total_cohort":      ledger.get("total_cohort"),
            "elite_plus_total":  ledger.get("elite_plus_total"),
        }
    except Exception as e:                                  # pragma: no cover
        out["promotion_ledger"] = {"error": str(e)[:200]}

    # Backtest pool adoption.
    try:
        from engines import backtest_pool
        out["backtest_pool_adoption"] = backtest_pool.adoption_state()
    except Exception as e:                                  # pragma: no cover
        out["backtest_pool_adoption"] = {"error": str(e)[:200]}

    return _envelope(out)
