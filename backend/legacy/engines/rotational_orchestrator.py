"""
Phase 2 scaffolding — Rotational orchestrator (DORMANT, pure preview).

A deterministic pure function that, given the live universe + the
adaptive env_priority snapshot + the survivor universe, returns the
proposed multi-cell rotation slice the orchestrator WOULD scan if
``ENABLE_ROTATIONAL_ORCHESTRATION=true`` and a future call-site invoked
``propose_rotation()``.

Discipline:
  * Dormant: when the flag is OFF, ``propose_rotation()`` still
    returns a JSON-safe payload — but the response carries
    ``advisory_only=true, would_execute=false``, so the operator can
    inspect what the rotation WOULD propose without changing anything.
  * Pure: no DB writes, no scheduler interaction, no flag mutation.
  * Preserves discipline: no existing engine imports this module.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    raw = (os.environ.get("ENABLE_ROTATIONAL_ORCHESTRATION") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _max_cells() -> int:
    try:
        n = int(os.environ.get("ROTATIONAL_MAX_CELLS_PER_TICK") or 3)
    except (TypeError, ValueError):
        n = 3
    return max(1, min(n, 12))


def _exploration_floor() -> float:
    """Fraction of the proposed slice that MUST be exploratory rather
    than elite-priority (anti-monoculture)."""
    try:
        f = float(os.environ.get("ROTATIONAL_EXPLORATION_FLOOR_PCT") or 0.20)
    except (TypeError, ValueError):
        f = 0.20
    return max(0.0, min(f, 1.0))


async def propose_rotation(
    *,
    universe: Optional[Dict[str, Any]] = None,
    env_priority_snapshot: Optional[List[Dict[str, Any]]] = None,
    survivor_universe: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the proposed next rotation slice.

    All inputs are optional — when omitted, the function fetches the
    live snapshots itself via the existing engine APIs (read-only).

    Output:
        {
          "ts":               iso,
          "advisory_only":    true,
          "would_execute":    bool,
          "enabled":          bool,
          "max_cells":        int,
          "exploration_floor_pct": float,
          "universe":         {pairs, timeframes, styles},
          "candidate_cells":  [(pair, tf, style), ...],
          "elite_slice":      [(pair, tf, style), ...],
          "exploratory_slice":[(pair, tf, style), ...],
          "proposed_slice":   [(pair, tf, style), ...],
          "rationale":        "...",
        }
    """
    # ── Lazy snapshot loads (read-only). ──────────────────────────
    if universe is None:
        try:
            from engines import governance_universe as gu
            universe = await gu.get_universe()
        except Exception as e:                              # pragma: no cover
            logger.debug("[rotational] universe fetch failed: %s", e)
            universe = {"pairs": [], "timeframes": [], "styles": []}

    if env_priority_snapshot is None:
        try:
            from engines import env_priority
            env_priority_snapshot = await env_priority.preview_allocation()
        except Exception:                                   # pragma: no cover
            env_priority_snapshot = []

    if survivor_universe is None:
        try:
            from engines import survivor_registry
            survivor_universe = await survivor_registry.fetch_survivor_universe()
        except Exception:                                   # pragma: no cover
            survivor_universe = {}

    pairs = list(universe.get("pairs") or [])
    timeframes = list(universe.get("timeframes") or [])
    styles = list(universe.get("styles") or [])

    # ── Build candidate set: universe × timeframes × styles. ─────
    candidates: List[Tuple[str, str, str]] = []
    for p in pairs:
        for tf in timeframes:
            for s in (styles or [""]):
                candidates.append((p, tf, s))

    # Rank by env_priority weight (cells absent from the snapshot get
    # neutral weight 1.0 so they remain eligible).
    weight_map: Dict[Tuple[str, str], float] = {}
    for row in (env_priority_snapshot or []):
        key = (str(row.get("pair") or "").upper(),
               str(row.get("timeframe") or "").upper())
        try:
            weight_map[key] = float(row.get("weight") or 1.0)
        except (TypeError, ValueError):
            weight_map[key] = 1.0

    # Survivor cohort presence — pairs/timeframes that already host
    # elite-or-better strategies are "elite-priority" cells.
    elite_keys: set = set()
    by_stage = (survivor_universe or {}).get("by_stage_counts") or {}
    if any((by_stage.get(k) or 0) > 0 for k in ("elite", "portfolio_worthy", "deployment_ready")):
        try:
            # Best-effort: survivor_registry doesn't return per-cell
            # locality cheaply; fall back to "every universe pair has
            # elite priority" as a conservative default. This is pure
            # preview, never authoritative.
            for p in pairs:
                for tf in timeframes:
                    elite_keys.add((p, tf))
        except Exception:                                   # pragma: no cover
            pass

    def _rank(c: Tuple[str, str, str]) -> Tuple[int, float, str]:
        key = (c[0], c[1])
        elite = 1 if key in elite_keys else 0
        return (-elite, -weight_map.get(key, 1.0), f"{c[0]}|{c[1]}|{c[2]}")

    candidates.sort(key=_rank)

    cap = _max_cells()
    floor = _exploration_floor()
    n_total = min(cap, len(candidates))
    n_explore = max(0, min(int(round(n_total * floor)), n_total))
    n_elite = n_total - n_explore

    elite_slice = candidates[:n_elite]
    # Exploratory slice = LAST n_explore (lowest-priority cells), to
    # preserve breadth (anti-monoculture).
    exploratory_slice = candidates[-n_explore:] if n_explore > 0 else []
    proposed = list(elite_slice)
    # Dedupe across the two slices while preserving order.
    seen = set(proposed)
    for c in exploratory_slice:
        if c not in seen:
            proposed.append(c)
            seen.add(c)

    enabled = is_enabled()
    return {
        "ts":                    _now_iso(),
        "advisory_only":         True,
        "would_execute":         False,    # never executes from here
        "enabled":               enabled,
        "max_cells":             cap,
        "exploration_floor_pct": floor,
        "universe": {
            "pairs":      pairs,
            "timeframes": timeframes,
            "styles":     styles,
        },
        "candidates_total": len(candidates),
        "elite_slice":     [list(c) for c in elite_slice],
        "exploratory_slice": [list(c) for c in exploratory_slice],
        "proposed_slice":  [list(c) for c in proposed],
        "rationale": (
            f"rank=elite({n_elite}) + exploratory({n_explore}); "
            f"floor={floor*100:.0f}%; cap={cap}; "
            f"enabled={enabled} (dormant by default — preview only)"
        ),
    }
