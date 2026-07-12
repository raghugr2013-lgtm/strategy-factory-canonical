"""BI5 Evolution — Maturity Detection Framework.

Strictly READ-ONLY advisory layer for the BI5 Evolution Governance
Roadmap (`/app/memory/BI5_EVOLUTION_ROADMAP.md`).

Architectural posture
─────────────────────
This module OBSERVES current-state signals and REPORTS per-phase
readiness for BI5-1 through BI5-6. It does **NOT**:
  • trigger phase activations,
  • fetch tick data,
  • mutate storage schemas,
  • activate replay infrastructure,
  • bypass operator approval in any form.

Operator decree is the SOLE activation authority. The framework's role
is to protect against premature escalation by surfacing blockers.

Output shape (per phase)
────────────────────────
    {
      "phase":           "BI5-1",
      "name":            "Canonicalise ingestion semantics",
      "current_status":  "not_started" | "in_progress" | "sealed",
      "ready_to_activate": bool,
      "blockers":        [str, ...],
      "signals":         { name: { value, threshold, ok }, ... },
      "operator_actions_required": [str, ...],
      "depends_on":      [phase_id, ...],
      "evaluated_at":    iso8601,
    }

Public entry points
───────────────────
    await evaluate_all() -> dict        # entire roadmap snapshot
    await evaluate_phase(phase_id) -> dict
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)

PHASE_VERSION = "BI5-Roadmap-v1.0"

# Dependency chain (strict ordering — enforced in readiness math).
PHASE_ORDER: Tuple[str, ...] = (
    "BI5-1", "BI5-2", "BI5-3", "BI5-4", "BI5-5", "BI5-6",
)

# Human-readable phase names (mirror the roadmap document).
PHASE_NAMES = {
    "BI5-1": "Canonicalise ingestion semantics",
    "BI5-2": "Raw tick storage substrate",
    "BI5-3": "Tick-derived realism",
    "BI5-4": "Tick replay engine",
    "BI5-5": "Spread / slippage / microstructure modelling",
    "BI5-6": "Execution-realism UI pivot",
}

# Phase dependency lookup.
PHASE_DEPS = {
    "BI5-1": (),
    "BI5-2": ("BI5-1",),
    "BI5-3": ("BI5-1", "BI5-2"),
    "BI5-4": ("BI5-1", "BI5-2", "BI5-3"),
    "BI5-5": ("BI5-1", "BI5-2", "BI5-3", "BI5-4"),
    "BI5-6": ("BI5-1", "BI5-2", "BI5-3", "BI5-4", "BI5-5"),
}

# Current operator-declared sealed phases. Drift-protected: NEVER auto-update
# this. Updates require explicit operator session + manifest change.
SEALED_PHASES: Tuple[str, ...] = ()


# ──────────────────────────────────────────────────────────────────
# Signal helpers (pure data shape · no business logic)
# ──────────────────────────────────────────────────────────────────

def _signal(value: Any, threshold: Any, *, ok: bool) -> Dict[str, Any]:
    return {"value": value, "threshold": threshold, "ok": bool(ok)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────
# Observation primitives (cheap reads only — never block, never mutate)
# ──────────────────────────────────────────────────────────────────

async def _count_non_canonical_bi5_buckets() -> int:
    """How many BI5 docs exist at TFs other than '1m'?
    Healthy state = 0. Anything > 0 means Phase 27.4 canonical lock has
    leaked and BI5-1 has work to do."""
    try:
        db = get_db()
        return await db["market_data"].count_documents({
            "source": "bi5",
            "timeframe": {"$ne": "1m"},
        })
    except Exception:                                       # pragma: no cover
        return -1   # -1 = unknown / observation failed; never breaks the report


async def _count_bi5_1m_pairs() -> int:
    try:
        db = get_db()
        return len(await db["market_data"].distinct(
            "symbol", {"source": "bi5", "timeframe": "1m"},
        ))
    except Exception:                                       # pragma: no cover
        return -1


async def _count_lifecycle_stage(stage: str) -> int:
    try:
        db = get_db()
        return await db["strategy_lifecycle"].count_documents({"current_stage": stage})
    except Exception:                                       # pragma: no cover
        return -1


async def _count_bi5_realism_evaluations_30d() -> int:
    """Approximate: count strategies with a bi5_realism block updated in
    the last 30 days. Cheap proxy — does not load full docs."""
    try:
        db = get_db()
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        return await db["strategy_lifecycle"].count_documents({
            "bi5_realism.last_evaluated_at": {"$gte": cutoff},
        })
    except Exception:                                       # pragma: no cover
        return -1


async def _universe_last_change_age_days() -> Optional[float]:
    """Days since the universe was last mutated. None when the panel has
    never been touched (operator hasn't widened the boundary yet)."""
    try:
        db = get_db()
        doc = await db["governance_universe"].find_one(
            {"_id": "config"}, {"_id": 0, "audit_log": 1, "updated_at": 1},
        )
        if not doc:
            return None
        updated_at = doc.get("updated_at")
        if not updated_at:
            return None
        ts = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - ts).total_seconds() / 86400.0, 2)
    except Exception:                                       # pragma: no cover
        return None


async def _market_data_ticks_exists() -> bool:
    """BI5-2 substrate detector — does the tick collection exist?"""
    try:
        db = get_db()
        return "market_data_ticks" in await db.list_collection_names()
    except Exception:                                       # pragma: no cover
        return False


async def _cbot_exports_count() -> int:
    """Count of cBot export emissions in audit_log (proxy for export activity)."""
    try:
        db = get_db()
        return await db["audit_log"].count_documents({
            "event_type": "DEPLOYMENT_EXPORTED",
        })
    except Exception:                                       # pragma: no cover
        return -1


# ──────────────────────────────────────────────────────────────────
# Per-phase evaluators
# ──────────────────────────────────────────────────────────────────

async def _evaluate_bi5_1() -> Dict[str, Any]:
    non_canon  = await _count_non_canonical_bi5_buckets()
    bi5_pairs  = await _count_bi5_1m_pairs()
    signals = {
        "bi5_non_canonical_buckets": _signal(non_canon, 0, ok=(non_canon == 0)),
        "bi5_1m_pairs_indexed":      _signal(bi5_pairs, "≥ 0", ok=(bi5_pairs >= 0)),
    }
    blockers: List[str] = []
    if non_canon < 0:
        blockers.append("observation failed for bi5_non_canonical_buckets")
    if non_canon > 0:
        # Note: BI5-1's whole purpose is to FIX this. So the existence of
        # non-canonical buckets actually makes the phase MORE ready to
        # activate (it has measurable work to do). No blocker recorded.
        pass
    return {
        "phase": "BI5-1",
        "name":  PHASE_NAMES["BI5-1"],
        "current_status": "sealed" if "BI5-1" in SEALED_PHASES else "not_started",
        "ready_to_activate": (
            "BI5-1" not in SEALED_PHASES
            # BI5-1 is hygiene — it is essentially always ready.
        ),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Approve BI5-1 scope via ask_human in a dedicated session",
        ],
        "depends_on": list(PHASE_DEPS["BI5-1"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_bi5_2() -> Dict[str, Any]:
    deployment_ready = await _count_lifecycle_stage("deployment_ready")
    evals_30d        = await _count_bi5_realism_evaluations_30d()
    universe_age     = await _universe_last_change_age_days()
    non_canon        = await _count_non_canonical_bi5_buckets()

    signals = {
        "deployment_ready_count":              _signal(deployment_ready, "≥ 1", ok=(deployment_ready >= 1)),
        "bi5_realism.evaluations_30d":         _signal(evals_30d, "≥ 100", ok=(evals_30d >= 100)),
        "universe.last_change_age_days":       _signal(universe_age, "≥ 14", ok=(universe_age is not None and universe_age >= 14)),
        "bi5_canonical_lock_violations":       _signal(non_canon, 0, ok=(non_canon == 0)),
    }
    blockers: List[str] = []
    if "BI5-1" not in SEALED_PHASES:
        blockers.append("BI5-1 must be sealed first (dependency)")
    if deployment_ready < 1:
        blockers.append(f"No deployment_ready strategies yet (have {deployment_ready}; need ≥ 1)")
    if evals_30d < 100:
        blockers.append(f"Realism evaluations in last 30d: {evals_30d} (need ≥ 100)")
    if universe_age is None or universe_age < 14:
        blockers.append(f"Universe age: {universe_age} days (need ≥ 14)")
    if non_canon > 0:
        blockers.append(f"BI5 canonical-lock leak: {non_canon} non-1m docs (BI5-1 must seal)")

    return {
        "phase": "BI5-2",
        "name":  PHASE_NAMES["BI5-2"],
        "current_status": "sealed" if "BI5-2" in SEALED_PHASES else "not_started",
        "ready_to_activate": (not blockers and "BI5-2" not in SEALED_PHASES),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Confirm disk budget for tick storage (≥ 50 GB free recommended)",
            "Approve BI5-2 scope via ask_human in a dedicated session",
            "Pre-review dukascopy_bi5_fetcher design",
        ],
        "depends_on": list(PHASE_DEPS["BI5-2"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_bi5_3() -> Dict[str, Any]:
    ticks_exists      = await _market_data_ticks_exists()
    deployment_ready  = await _count_lifecycle_stage("deployment_ready")
    signals = {
        "market_data_ticks_exists":  _signal(ticks_exists, True, ok=ticks_exists),
        "deployment_ready_count":    _signal(deployment_ready, "≥ 10", ok=(deployment_ready >= 10)),
        # Tick parity / coverage signals get added when BI5-2 substrate exists.
        "tick_parity_passing_pct":   _signal("not_measured", "≥ 95", ok=False),
        "tick_coverage_months_min":  _signal("not_measured", "≥ 6",  ok=False),
    }
    blockers: List[str] = []
    if "BI5-2" not in SEALED_PHASES:
        blockers.append("BI5-2 must be sealed first")
    if not ticks_exists:
        blockers.append("market_data_ticks collection does not exist (BI5-2 substrate missing)")
    if deployment_ready < 10:
        blockers.append(f"deployment_ready cohort: {deployment_ready} (need ≥ 10)")

    return {
        "phase": "BI5-3",
        "name":  PHASE_NAMES["BI5-3"],
        "current_status": "sealed" if "BI5-3" in SEALED_PHASES else "not_started",
        "ready_to_activate": (not blockers and "BI5-3" not in SEALED_PHASES),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Approve parity-validation phase (parallel 1m + tick evaluations for ≥ 30 days)",
            "Approve BI5-3 scope via ask_human in a dedicated session",
        ],
        "depends_on": list(PHASE_DEPS["BI5-3"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_bi5_4() -> Dict[str, Any]:
    cbot_exports     = await _cbot_exports_count()
    deployment_ready = await _count_lifecycle_stage("deployment_ready")
    signals = {
        "cbot_exports_lifetime":    _signal(cbot_exports, "≥ 1", ok=(cbot_exports >= 1)),
        "deployment_ready_count":   _signal(deployment_ready, "≥ 5", ok=(deployment_ready >= 5)),
        "tick_replay_determinism_pct": _signal("not_measured", 100, ok=False),
    }
    blockers: List[str] = []
    if "BI5-3" not in SEALED_PHASES:
        blockers.append("BI5-3 must be sealed first")
    if cbot_exports < 1:
        blockers.append(f"No cBot exports performed yet (have {cbot_exports}; need ≥ 1)")
    if deployment_ready < 5:
        blockers.append(f"deployment_ready cohort: {deployment_ready} (need ≥ 5)")

    return {
        "phase": "BI5-4",
        "name":  PHASE_NAMES["BI5-4"],
        "current_status": "sealed" if "BI5-4" in SEALED_PHASES else "not_started",
        "ready_to_activate": (not blockers and "BI5-4" not in SEALED_PHASES),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Operator validates ≥ 1 cBot export against manual cTrader smoke run first",
            "Approve BI5-4 scope via ask_human in a dedicated session",
        ],
        "depends_on": list(PHASE_DEPS["BI5-4"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_bi5_5() -> Dict[str, Any]:
    deployment_ready = await _count_lifecycle_stage("deployment_ready")
    signals = {
        "replay_validated_deployment_ready_count": _signal(deployment_ready, "≥ 5", ok=(deployment_ready >= 5)),
        "spread_distribution_empirical": _signal("not_measured", "exists", ok=False),
        "firm_execution_policies":        _signal("not_documented", "documented", ok=False),
    }
    blockers: List[str] = []
    if "BI5-4" not in SEALED_PHASES:
        blockers.append("BI5-4 must be sealed first")
    return {
        "phase": "BI5-5",
        "name":  PHASE_NAMES["BI5-5"],
        "current_status": "sealed" if "BI5-5" in SEALED_PHASES else "not_started",
        "ready_to_activate": (not blockers and "BI5-5" not in SEALED_PHASES),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Document per-firm execution policy",
            "Characterise empirical spread/slip distributions",
            "Approve BI5-5 scope via ask_human in a dedicated session",
        ],
        "depends_on": list(PHASE_DEPS["BI5-5"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_bi5_6() -> Dict[str, Any]:
    signals = {
        "all_upstream_phases_sealed": _signal(
            list(SEALED_PHASES),
            list(PHASE_DEPS["BI5-6"]),
            ok=all(p in SEALED_PHASES for p in PHASE_DEPS["BI5-6"]),
        ),
    }
    blockers: List[str] = []
    for dep in PHASE_DEPS["BI5-6"]:
        if dep not in SEALED_PHASES:
            blockers.append(f"{dep} must be sealed first")
    return {
        "phase": "BI5-6",
        "name":  PHASE_NAMES["BI5-6"],
        "current_status": "sealed" if "BI5-6" in SEALED_PHASES else "not_started",
        "ready_to_activate": (not blockers and "BI5-6" not in SEALED_PHASES),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Operator declares UI pivot ready",
            "Approve BI5-6 scope via ask_human in a dedicated session",
        ],
        "depends_on": list(PHASE_DEPS["BI5-6"]),
        "evaluated_at": _now_iso(),
    }


_EVALUATORS = {
    "BI5-1": _evaluate_bi5_1,
    "BI5-2": _evaluate_bi5_2,
    "BI5-3": _evaluate_bi5_3,
    "BI5-4": _evaluate_bi5_4,
    "BI5-5": _evaluate_bi5_5,
    "BI5-6": _evaluate_bi5_6,
}


# ──────────────────────────────────────────────────────────────────
# Public surface
# ──────────────────────────────────────────────────────────────────

async def evaluate_phase(phase_id: str) -> Dict[str, Any]:
    """Evaluate readiness for a single phase. Raises on unknown phase_id."""
    fn = _EVALUATORS.get(phase_id)
    if fn is None:
        raise ValueError(f"unknown BI5 phase: {phase_id!r}")
    return await fn()


async def evaluate_all() -> Dict[str, Any]:
    """Snapshot every phase. Advisory-only."""
    phases: List[Dict[str, Any]] = []
    for pid in PHASE_ORDER:
        phases.append(await _EVALUATORS[pid]())
    return {
        "roadmap_version":     PHASE_VERSION,
        "sealed_phases":       list(SEALED_PHASES),
        "advisory_only":       True,
        "operator_authority":  "operator decree > maturity framework > silence",
        "phases":              phases,
        "evaluated_at":        _now_iso(),
    }
