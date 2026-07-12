"""Phase 30 — Survivor Registry (pure aggregator over strategy_lifecycle).

Operator-decided constants:
    SURVIVOR_TOP_N             = 100
    SURVIVOR_ELIGIBLE_STAGES   = (elite, portfolio_worthy, deployment_ready)
    RANKING_FN                 = deploy_score (descending)

Discipline (Phase 30, anti-drift):
    • READ-ONLY. NEVER mutates strategy_lifecycle / strategy_library / any collection.
    • Observational. No autonomous demotion in v1 (operator decision deferred to 30.1).
    • Bit-stable output: alphabetical fallback ordering on equal deploy_scores.

Public surface:
    SURVIVOR_TOP_N
    SURVIVOR_ELIGIBLE_STAGES
    PHASE_VERSION
    compute_survivor_universe(lifecycle_docs)        — pure, sync
    fetch_survivor_universe()                        — async DB read
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from engines.db import get_db

# Operator decisions (Phase 30.0)
SURVIVOR_TOP_N = 100
SURVIVOR_ELIGIBLE_STAGES = ("elite", "portfolio_worthy", "deployment_ready")
PHASE_VERSION = "30.0"

LIFECYCLE_COLL = "strategy_lifecycle"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _deploy_score_of(doc: Dict[str, Any]) -> float:
    """Extract the canonical ranking signal. Honest refusal → -inf when
    deploy_score is absent (always sorts to the bottom)."""
    ev = doc.get("evidence") or {}
    ds = ev.get("deploy_score")
    if isinstance(ds, (int, float)):
        return float(ds)
    # Fallback: try the library-doc deploy_score if Cohort write didn't
    # capture it under evidence. Never inflate — refusal is the default.
    return float("-inf")


def compute_survivor_universe(
    lifecycle_docs: Iterable[Dict[str, Any]],
    *,
    top_n: int = SURVIVOR_TOP_N,
    eligible_stages: tuple = SURVIVOR_ELIGIBLE_STAGES,
) -> Dict[str, Any]:
    """Pure function. Bucket lifecycle docs into the survivor universe.

    Returns:
        {
          "universe":             [...top-N docs with deploy_score, sorted desc...],
          "active_count":         int,       # how many in eligible stages
          "cap":                  int,       # SURVIVOR_TOP_N
          "headroom":             int,       # cap - active_count  (clamped ≥ 0)
          "over_cap":             bool,      # active_count > cap
          "weakest_decile":       [...bottom 10% of universe by deploy_score...],
          "by_stage_counts":      {stage: int, ...},
          "phase":                "30.0",
          "advisory_only":        true,
          "computed_at":          iso
        }
    """
    eligible = [
        d for d in (lifecycle_docs or [])
        if isinstance(d, dict) and d.get("current_stage") in eligible_stages
    ]
    eligible.sort(
        key=lambda d: (-_deploy_score_of(d), d.get("strategy_hash") or ""),
    )
    universe = eligible[:top_n]
    active_count = len(eligible)
    cap = int(top_n)

    by_stage_counts: Dict[str, int] = {s: 0 for s in eligible_stages}
    for d in eligible:
        s = d.get("current_stage")
        if s in by_stage_counts:
            by_stage_counts[s] += 1

    # Weakest decile of the active universe — purely advisory replacement
    # signal. Empty when active_count < 10.
    decile_size = max(1, len(universe) // 10) if len(universe) >= 10 else 0
    weakest_decile = universe[-decile_size:] if decile_size > 0 else []

    return {
        "universe": [
            {
                "strategy_hash":  d.get("strategy_hash"),
                "current_stage":  d.get("current_stage"),
                "stage_rank":     d.get("stage_rank"),
                "deploy_score":   _deploy_score_of(d) if _deploy_score_of(d) > float("-inf") else None,
                "current_stage_since": d.get("current_stage_since"),
                "last_run_at":    d.get("last_run_at"),
                "flags":          d.get("flags") or [],
            }
            for d in universe
        ],
        "active_count":     active_count,
        "cap":              cap,
        "headroom":         max(0, cap - active_count),
        "over_cap":         active_count > cap,
        "weakest_decile":   [
            {"strategy_hash": d.get("strategy_hash"),
             "deploy_score": _deploy_score_of(d) if _deploy_score_of(d) > float("-inf") else None,
             "current_stage": d.get("current_stage")}
            for d in weakest_decile
        ],
        "by_stage_counts":  by_stage_counts,
        "phase":            PHASE_VERSION,
        "advisory_only":    True,
        "computed_at":      _now_iso(),
    }


async def fetch_survivor_universe(
    *,
    top_n: int = SURVIVOR_TOP_N,
) -> Dict[str, Any]:
    """Read all lifecycle docs in eligible stages and compute the universe.
    Read-only. Projection excludes _id."""
    db = get_db()
    cur = db[LIFECYCLE_COLL].find(
        {"current_stage": {"$in": list(SURVIVOR_ELIGIBLE_STAGES)}},
        {"_id": 0},
    )
    docs = [d async for d in cur]
    return compute_survivor_universe(docs, top_n=top_n)


async def fetch_promotion_ledger() -> Dict[str, Any]:
    """Stage-by-stage breakdown of the cohort. Read-only."""
    from engines.strategy_lifecycle import LIFECYCLE_STAGES
    db = get_db()
    stages_out: Dict[str, Any] = {}
    for stage in LIFECYCLE_STAGES:
        scores: List[float] = []
        count = 0
        async for d in db[LIFECYCLE_COLL].find(
            {"current_stage": stage},
            {"_id": 0, "evidence.deploy_score": 1},
        ):
            count += 1
            ds = ((d.get("evidence") or {}).get("deploy_score"))
            if isinstance(ds, (int, float)):
                scores.append(float(ds))
        stages_out[stage] = {
            "count": count,
            "deploy_score_p50": _percentile(scores, 0.50),
            "deploy_score_p90": _percentile(scores, 0.90),
        }
    total = sum(s["count"] for s in stages_out.values())
    survivors_total = sum(
        stages_out[s]["count"] for s in (
            "candidate", "validated", "stable",
            "prop_safe", "elite", "portfolio_worthy", "deployment_ready",
        )
    )
    elite_plus = sum(stages_out[s]["count"] for s in SURVIVOR_ELIGIBLE_STAGES)
    return {
        "stages":                  stages_out,
        "total_cohort":            total,
        "survivors_total":         survivors_total,
        "elite_plus_total":        elite_plus,
        "deployment_ready_total":  stages_out["deployment_ready"]["count"],
        "phase":                   PHASE_VERSION,
        "computed_at":             _now_iso(),
    }


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 4)
    idx = p * (len(s) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return round(s[lo] * (1 - frac) + s[hi] * frac, 4)
