"""Ecosystem Exploration Governance — Maturity Detection Framework.

Strictly READ-ONLY advisory layer for the EG Evolution Governance
Roadmap (`/app/memory/EG_EVOLUTION_ROADMAP.md`).

Architectural posture
─────────────────────
This module OBSERVES current-state ecosystem signals and REPORTS
per-phase readiness for EG-1 through EG-6. It does **NOT**:
  • mutate `governance_universe`
  • trigger orchestrator rules
  • modify `ecosystem_cell_memory`
  • change scheduler intervals
  • escalate autonomy flags
  • activate any phase autonomously

Operator decree is the SOLE activation authority.

Output shape (per phase)
────────────────────────
Same shape as `engines.bi5_maturity` — institutional parity.

Public entry points
───────────────────
    await evaluate_all() -> dict
    await evaluate_phase(phase_id) -> dict
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)

PHASE_VERSION = "EG-Roadmap-v1.0"

PHASE_ORDER: Tuple[str, ...] = (
    "EG-1", "EG-2", "EG-3", "EG-4", "EG-5", "EG-6",
)

PHASE_NAMES = {
    "EG-1": "Universe Boundary Governance",
    "EG-2": "Exploration Memory Layer",
    "EG-3": "Rotational Ecosystem Scheduler",
    "EG-4": "Adaptive Allocation Observation",
    "EG-5": "Exploration vs Exploitation Governance",
    "EG-6": "Full Ecosystem Autonomy",
}

PHASE_DEPS = {
    "EG-1": (),
    "EG-2": ("EG-1",),
    "EG-3": ("EG-1", "EG-2"),
    "EG-4": ("EG-1", "EG-2", "EG-3"),
    "EG-5": ("EG-1", "EG-2", "EG-3", "EG-4"),
    "EG-6": ("EG-1", "EG-2", "EG-3", "EG-4", "EG-5"),
}

# Operator-declared sealed phases. EG-1 is sealed as part of Phase 30.2.
# Drift-protected — NEVER mutated by code. Updates require an explicit
# operator session + manifest change to this constant.
SEALED_PHASES: Tuple[str, ...] = ("EG-1",)


def _signal(value: Any, threshold: Any, *, ok: bool) -> Dict[str, Any]:
    return {"value": value, "threshold": threshold, "ok": bool(ok)}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────
# Observation primitives — cheap reads only, never block, never mutate
# ──────────────────────────────────────────────────────────────────

async def _universe_doc() -> Dict[str, Any]:
    try:
        db = get_db()
        doc = await db["governance_universe"].find_one(
            {"_id": "config"}, {"_id": 0},
        )
        return doc or {}
    except Exception:                                       # pragma: no cover
        return {}


async def _universe_age_days() -> float:
    doc = await _universe_doc()
    updated_at = doc.get("updated_at")
    if not updated_at:
        return 0.0
    try:
        ts = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        return round((datetime.now(timezone.utc) - ts).total_seconds() / 86400.0, 2)
    except Exception:                                       # pragma: no cover
        return 0.0


async def _strategy_performance_total() -> int:
    try:
        db = get_db()
        return await db["strategy_performance_history"].count_documents({})
    except Exception:                                       # pragma: no cover
        return -1


async def _ecosystem_memory_exists() -> bool:
    try:
        db = get_db()
        return "ecosystem_cell_memory" in await db.list_collection_names()
    except Exception:                                       # pragma: no cover
        return False


async def _ecosystem_memory_cells_with_min_exploration(min_count: int = 5) -> int:
    try:
        db = get_db()
        if not await _ecosystem_memory_exists():
            return 0
        return await db["ecosystem_cell_memory"].count_documents({
            "exploration_count": {"$gte": min_count},
        })
    except Exception:                                       # pragma: no cover
        return -1


async def _multi_cycle_executions_total() -> int:
    """Count of completed multi-cycle runs (proxy: rows in mc_runs or similar)."""
    try:
        db = get_db()
        # multi_cycle_runner persists runs in `mc_runs`
        return await db["mc_runs"].count_documents({})
    except Exception:                                       # pragma: no cover
        return -1


async def _count_lifecycle_stage(stage: str) -> int:
    try:
        db = get_db()
        return await db["strategy_lifecycle"].count_documents({"current_stage": stage})
    except Exception:                                       # pragma: no cover
        return -1


async def _rule_13_advisory_count() -> int:
    """How many RULE 13 ROTATIONAL_CELL_ADVISORY recommendations exist?"""
    try:
        db = get_db()
        return await db["orchestrator_recommendations"].count_documents({
            "rule_id": "ROTATIONAL_CELL_ADVISORY",
        })
    except Exception:                                       # pragma: no cover
        return -1


async def _rule_14_allocation_count() -> int:
    try:
        db = get_db()
        return await db["orchestrator_recommendations"].count_documents({
            "rule_id": "ECOSYSTEM_ALLOCATION_ADVISORY",
        })
    except Exception:                                       # pragma: no cover
        return -1


async def _replacement_executed_last_90d() -> int:
    try:
        db = get_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        return await db["audit_log"].count_documents({
            "event_type": "REPLACEMENT_EXECUTED",
            "ts": {"$gte": cutoff},
        })
    except Exception:                                       # pragma: no cover
        return -1


# ──────────────────────────────────────────────────────────────────
# Per-phase evaluators
# ──────────────────────────────────────────────────────────────────

async def _evaluate_eg_1() -> Dict[str, Any]:
    uni = await _universe_doc()
    pairs_n = len(uni.get("pairs") or [])
    tfs_n   = len(uni.get("timeframes") or [])
    styles_n = len(uni.get("styles") or [])
    signals = {
        "universe.pairs_count":      _signal(pairs_n, "≥ 1", ok=(pairs_n >= 1)),
        "universe.timeframes_count": _signal(tfs_n, "≥ 1", ok=(tfs_n >= 1)),
        "universe.styles_count":     _signal(styles_n, "≥ 1", ok=(styles_n >= 1)),
        "universe.config_exists":    _signal(bool(uni), True, ok=bool(uni)),
    }
    return {
        "phase": "EG-1",
        "name":  PHASE_NAMES["EG-1"],
        "current_status": "sealed" if "EG-1" in SEALED_PHASES else "not_started",
        "ready_to_activate": False,   # already sealed
        "blockers": [],
        "signals":  signals,
        "operator_actions_required": [],
        "depends_on": list(PHASE_DEPS["EG-1"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_eg_2() -> Dict[str, Any]:
    universe_age = await _universe_age_days()
    perf_rows    = await _strategy_performance_total()
    memory_exists = await _ecosystem_memory_exists()
    signals = {
        "universe.age_days":                 _signal(universe_age, "≥ 14", ok=(universe_age >= 14)),
        "strategy_performance_history.rows": _signal(perf_rows, "≥ 100", ok=(perf_rows >= 100)),
        "ecosystem_cell_memory.exists":      _signal(memory_exists, False, ok=(not memory_exists or "EG-2" in SEALED_PHASES)),
    }
    blockers: List[str] = []
    if "EG-1" not in SEALED_PHASES:
        blockers.append("EG-1 must be sealed first (dependency)")
    if universe_age < 14:
        blockers.append(f"Universe age {universe_age}d (need ≥ 14d stable)")
    if perf_rows < 100:
        blockers.append(f"strategy_performance_history has {perf_rows} rows (need ≥ 100)")

    return {
        "phase": "EG-2",
        "name":  PHASE_NAMES["EG-2"],
        "current_status": "sealed" if "EG-2" in SEALED_PHASES else "not_started",
        "ready_to_activate": (not blockers and "EG-2" not in SEALED_PHASES),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Confirm universe boundary is stable (no churn intended for ≥ 30 days)",
            "Approve EG-2 scope via ask_human in a dedicated session",
        ],
        "depends_on": list(PHASE_DEPS["EG-2"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_eg_3() -> Dict[str, Any]:
    memory_exists = await _ecosystem_memory_exists()
    cells_min_5   = await _ecosystem_memory_cells_with_min_exploration(5)
    mc_runs       = await _multi_cycle_executions_total()
    signals = {
        "ecosystem_memory.exists":          _signal(memory_exists, True, ok=memory_exists),
        "cells_with_min_5_exploration":     _signal(cells_min_5, "≥ 4", ok=(cells_min_5 >= 4)),
        "multi_cycle_runs.total":           _signal(mc_runs, "≥ 50", ok=(mc_runs >= 50)),
    }
    blockers: List[str] = []
    if "EG-2" not in SEALED_PHASES:
        blockers.append("EG-2 must be sealed first")
    if not memory_exists:
        blockers.append("ecosystem_cell_memory collection does not exist")
    if cells_min_5 < 4:
        blockers.append(f"Only {cells_min_5} cells with ≥ 5 explorations (need ≥ 4)")
    if mc_runs < 50:
        blockers.append(f"Only {mc_runs} multi-cycle runs total (need ≥ 50)")

    return {
        "phase": "EG-3",
        "name":  PHASE_NAMES["EG-3"],
        "current_status": "sealed" if "EG-3" in SEALED_PHASES else "not_started",
        "ready_to_activate": (not blockers and "EG-3" not in SEALED_PHASES),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Approve EG-3 scope via ask_human in a dedicated session",
            "Confirm rotation revisit-cadence parameter (default = 1× universe size)",
        ],
        "depends_on": list(PHASE_DEPS["EG-3"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_eg_4() -> Dict[str, Any]:
    rule_13_count   = await _rule_13_advisory_count()
    deployment_ready = await _count_lifecycle_stage("deployment_ready")
    mc_runs         = await _multi_cycle_executions_total()
    signals = {
        "rule_13_recommendations.count":   _signal(rule_13_count, "≥ 1", ok=(rule_13_count >= 1)),
        "deployment_ready.count":          _signal(deployment_ready, "≥ 5", ok=(deployment_ready >= 5)),
        "multi_cycle_runs.under_eg3":      _signal(mc_runs, "≥ 200", ok=(mc_runs >= 200)),
    }
    blockers: List[str] = []
    if "EG-3" not in SEALED_PHASES:
        blockers.append("EG-3 must be sealed first")
    if rule_13_count < 1:
        blockers.append("No EG-3 RULE 13 recommendations recorded yet")
    if deployment_ready < 5:
        blockers.append(f"deployment_ready cohort: {deployment_ready} (need ≥ 5)")
    if mc_runs < 200:
        blockers.append(f"Multi-cycle runs since EG-3: {mc_runs} (need ≥ 200)")

    return {
        "phase": "EG-4",
        "name":  PHASE_NAMES["EG-4"],
        "current_status": "sealed" if "EG-4" in SEALED_PHASES else "not_started",
        "ready_to_activate": (not blockers and "EG-4" not in SEALED_PHASES),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Operator reviews ≥ 30 days of EG-3 rotation telemetry",
            "Approve EG-4 scope via ask_human in a dedicated session",
        ],
        "depends_on": list(PHASE_DEPS["EG-4"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_eg_5() -> Dict[str, Any]:
    rule_14_count    = await _rule_14_allocation_count()
    deployment_ready = await _count_lifecycle_stage("deployment_ready")
    signals = {
        "rule_14_recommendations.count":   _signal(rule_14_count, "≥ 100", ok=(rule_14_count >= 100)),
        "deployment_ready.count":          _signal(deployment_ready, "≥ 10", ok=(deployment_ready >= 10)),
    }
    blockers: List[str] = []
    if "EG-4" not in SEALED_PHASES:
        blockers.append("EG-4 must be sealed first")
    if rule_14_count < 100:
        blockers.append(f"EG-4 RULE 14 recommendations: {rule_14_count} (need ≥ 100 observed)")
    if deployment_ready < 10:
        blockers.append(f"deployment_ready cohort: {deployment_ready} (need ≥ 10)")
    # Phase 30.4 (auto_replace_enabled=True) is a prerequisite — read from
    # replacement_engine module constant.
    try:
        from engines import replacement_engine as rep
        if rep.SURVIVOR_AUTO_REPLACE_ENABLED is False:
            blockers.append("auto_replace_enabled must be True (Phase 30.4 prereq)")
    except Exception:                                       # pragma: no cover
        blockers.append("replacement_engine state unavailable")

    return {
        "phase": "EG-5",
        "name":  PHASE_NAMES["EG-5"],
        "current_status": "sealed" if "EG-5" in SEALED_PHASES else "not_started",
        "ready_to_activate": (not blockers and "EG-5" not in SEALED_PHASES),
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Phase 30.4 auto_replace_enabled flip operator decree",
            "Approve EG-5 scope via ask_human in a dedicated session",
        ],
        "depends_on": list(PHASE_DEPS["EG-5"]),
        "evaluated_at": _now_iso(),
    }


async def _evaluate_eg_6() -> Dict[str, Any]:
    deployment_ready_total = await _count_lifecycle_stage("deployment_ready")
    replacement_executed   = await _replacement_executed_last_90d()
    signals = {
        "deployment_ready.total":            _signal(deployment_ready_total, "stable ≥ 6 months", ok=False),
        "replacement_executed.last_90d":     _signal(replacement_executed, "≥ 20", ok=(replacement_executed >= 20)),
        "all_upstream_phases_sealed":        _signal(
            list(SEALED_PHASES),
            list(PHASE_DEPS["EG-6"]),
            ok=all(p in SEALED_PHASES for p in PHASE_DEPS["EG-6"]),
        ),
    }
    blockers: List[str] = []
    for dep in PHASE_DEPS["EG-6"]:
        if dep not in SEALED_PHASES:
            blockers.append(f"{dep} must be sealed first")
    if replacement_executed < 20:
        blockers.append(f"Only {replacement_executed} replacements in last 90d (need ≥ 20)")
    blockers.append("EG-6 is deferred indefinitely by operator decree until empirical maturity is proven")

    return {
        "phase": "EG-6",
        "name":  PHASE_NAMES["EG-6"],
        "current_status": "deferred",
        "ready_to_activate": False,
        "blockers": blockers,
        "signals":  signals,
        "operator_actions_required": [
            "Document rollback plan + rehearsal",
            "Operator decree in a dedicated session",
            "Trust-gate certification of every autonomous rule",
        ],
        "depends_on": list(PHASE_DEPS["EG-6"]),
        "evaluated_at": _now_iso(),
    }


_EVALUATORS = {
    "EG-1": _evaluate_eg_1,
    "EG-2": _evaluate_eg_2,
    "EG-3": _evaluate_eg_3,
    "EG-4": _evaluate_eg_4,
    "EG-5": _evaluate_eg_5,
    "EG-6": _evaluate_eg_6,
}


# ──────────────────────────────────────────────────────────────────
# Public surface
# ──────────────────────────────────────────────────────────────────

async def evaluate_phase(phase_id: str) -> Dict[str, Any]:
    fn = _EVALUATORS.get(phase_id)
    if fn is None:
        raise ValueError(f"unknown EG phase: {phase_id!r}")
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
