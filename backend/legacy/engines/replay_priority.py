"""
Phase 2 scaffolding — Replay-priority queue primitive (DORMANT).

Pure function ``prioritize(candidates) → sorted_candidates``. Sort order:
  1. Lifecycle stage rank (elite > portfolio_worthy > stable > rest).
  2. ``deploy_score`` (desc).
  3. ``strategy_hash`` (alphabetical, deterministic tiebreaker).

Discipline:
  * Dormant: ``ENABLE_REPLAY_PRIORITY=false`` (default) → returns the
    input list unchanged. No behavior change.
  * Pure: no I/O, deterministic.
  * Reversible: deleting this file breaks zero imports.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List

# Higher integer = higher priority.
_STAGE_RANK_PRIORITY: Dict[str, int] = {
    "deployment_ready": 7,
    "portfolio_worthy": 6,
    "elite":            5,
    "prop_safe":        4,
    "stable":           3,
    "validated":        2,
    "candidate":        1,
    "explorer":         0,
}


def is_enabled() -> bool:
    raw = (os.environ.get("ENABLE_REPLAY_PRIORITY") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _rank(candidate: Dict[str, Any]) -> int:
    stage = candidate.get("current_stage") or candidate.get("stage")
    return _STAGE_RANK_PRIORITY.get(str(stage), 0)


def _score(candidate: Dict[str, Any]) -> float:
    ev = candidate.get("evidence") or {}
    ds = ev.get("deploy_score") if isinstance(ev, dict) else None
    if not isinstance(ds, (int, float)):
        ds = candidate.get("deploy_score")
    if isinstance(ds, (int, float)):
        return float(ds)
    return float("-inf")


def _hash(candidate: Dict[str, Any]) -> str:
    return str(
        candidate.get("strategy_hash")
        or candidate.get("hash")
        or candidate.get("strategy_id")
        or ""
    )


def prioritize(candidates: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort replay candidates by (stage_rank desc, deploy_score desc,
    strategy_hash asc).

    Pure. When the flag is OFF, returns the candidate list unchanged
    (only materialised to a fresh list).
    """
    items = list(candidates or [])
    if not is_enabled():
        return items
    items.sort(key=lambda c: (-_rank(c), -_score(c), _hash(c)))
    return items


def explain(candidate: Dict[str, Any]) -> Dict[str, Any]:
    """Diagnostic: return the sort key for ONE candidate."""
    return {
        "stage_rank":    _rank(candidate),
        "deploy_score":  _score(candidate) if _score(candidate) > float("-inf") else None,
        "strategy_hash": _hash(candidate),
        "would_prioritize": is_enabled(),
    }
