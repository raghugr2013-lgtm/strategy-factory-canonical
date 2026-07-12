"""Master Bot V1 — Runner Router (MB-9 Phase 2.A).

Sticky-affinity router that maps a deployment's ``(pair, timeframe)``
tuple to one runner from the live fleet.

Discipline (operator-final, default-OFF posture):

  * **Byte-identical to Phase 1 at fleet size 1.** When only one
    runner is registered (and the operator has not explicitly bound
    the deployment to that runner), the router returns it
    deterministically. There is NO flag for this path — it is the
    correct-by-default behaviour.

  * **Policies (env: ``RUNNER_AFFINITY_POLICY``)**:
      - ``sticky_pair_tf`` (default) — pick the runner whose
        ``pair_filters`` AND ``timeframe_filters`` cover the workload.
        Tie-break on freshest heartbeat, then lowest queue depth.
      - ``least_busy`` — pick the runner with the lowest queue depth.
        Tie-break on freshest heartbeat.
      - ``round_robin`` — pick the next alive runner in sorted-by-id
        order; uses an in-memory cursor (resets on import / restart).
      - ``local_only`` — fallback alias that always returns the
        single registered runner (degenerate single-node case).

  * **Honest refusal** — never routes to a runner whose ``verdict``
    is not ``alive``. When no alive candidate exists, returns a
    refusal record (``runner_id=None``, ``reason`` populated).

  * **Read-only.** This module never writes to Mongo. It consults
    ``runner_registry.list_runners()`` (which is itself read-only).

  * **No new flag declarations.** The 6 Phase-2 flags will be
    registered in ``engines.feature_flags`` during Phase 2.B. Until
    then, this module reads ``os.environ`` directly with documented
    defaults (matches the Phase-1 ``MB9_HEARTBEAT_SEC`` convention).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from engines import runner_registry as runners

logger = logging.getLogger(__name__)


# ─── Defaults (Phase-2 flags formally registered in Phase 2.B) ────────
POLICY_STICKY_PAIR_TF = "sticky_pair_tf"
POLICY_LEAST_BUSY     = "least_busy"
POLICY_ROUND_ROBIN    = "round_robin"
POLICY_LOCAL_ONLY     = "local_only"

VALID_POLICIES = (
    POLICY_STICKY_PAIR_TF,
    POLICY_LEAST_BUSY,
    POLICY_ROUND_ROBIN,
    POLICY_LOCAL_ONLY,
)

DEFAULT_POLICY = POLICY_STICKY_PAIR_TF

# Refusal reasons (string constants — surface in audit logs).
REASON_NO_RUNNERS         = "no_runners_registered"
REASON_NO_ALIVE_RUNNERS   = "no_alive_runner_in_fleet"
REASON_NO_AFFINITY_MATCH  = "no_runner_matches_pair_timeframe"
REASON_POLICY_INVALID     = "unknown_policy"


def _resolved_policy(override: Optional[str] = None) -> str:
    """Return the active policy. ``override`` (if any) takes precedence;
    otherwise reads ``RUNNER_AFFINITY_POLICY`` env (default
    ``sticky_pair_tf``). Unknown values fall back to default and emit a
    warning — the router NEVER silently coerces."""
    raw = (override or os.environ.get("RUNNER_AFFINITY_POLICY") or DEFAULT_POLICY).strip()
    if raw not in VALID_POLICIES:
        logger.warning(
            "[runner_router] unknown RUNNER_AFFINITY_POLICY=%r — falling back to %s",
            raw, DEFAULT_POLICY,
        )
        return DEFAULT_POLICY
    return raw


def _is_alive(row: Dict[str, Any]) -> bool:
    return (row.get("verdict") or "").lower() == runners.VERDICT_ALIVE


def _matches_filter(filters: Optional[List[str]], value: str) -> bool:
    """An empty filter list means 'no preference' → matches everything.
    A non-empty list requires the value to be present (case-insensitive)."""
    if not filters:
        return True
    return value.strip().upper() in {f.strip().upper() for f in filters}


def _queue_depth(row: Dict[str, Any]) -> int:
    snap = row.get("last_snapshot") or {}
    qd = snap.get("queue_depth")
    try:
        return int(qd) if qd is not None else 0
    except (TypeError, ValueError):
        return 0


def _sort_key(row: Dict[str, Any]) -> Tuple[int, int, str]:
    # (age_seconds asc, queue_depth asc, runner_id asc) — fresher
    # heartbeat first, then lower queue, then deterministic on id.
    age = row.get("age_seconds")
    age = age if isinstance(age, int) else 10**9   # never_seen → demoted
    return (age, _queue_depth(row), str(row.get("runner_id") or ""))


# ── Stateless decision builder ────────────────────────────────────────

def _refusal(reason: str, policy: str, considered: int = 0) -> Dict[str, Any]:
    return {
        "runner_id":              None,
        "policy_used":            policy,
        "candidates_considered":  considered,
        "reason":                 reason,
    }


def _accept(row: Dict[str, Any], policy: str, considered: int) -> Dict[str, Any]:
    return {
        "runner_id":              row["runner_id"],
        "policy_used":            policy,
        "candidates_considered":  considered,
        "reason":                 "matched",
        "runner_name":            row.get("name"),
        "verdict":                row.get("verdict"),
    }


# ── Round-robin cursor (process-local) ────────────────────────────────
_RR_CURSOR: Dict[str, int] = {"i": 0}


def _round_robin_pick(alive: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic across calls within a process. Resets at import."""
    if not alive:
        raise ValueError("round_robin_pick called with no candidates")
    sorted_alive = sorted(alive, key=lambda r: str(r.get("runner_id") or ""))
    idx = _RR_CURSOR["i"] % len(sorted_alive)
    _RR_CURSOR["i"] = (idx + 1) % len(sorted_alive)
    return sorted_alive[idx]


# ── Public synchronous decision function (pure) ───────────────────────

def decide(
    pair: str,
    timeframe: str,
    fleet: List[Dict[str, Any]],
    *,
    policy: Optional[str] = None,
) -> Dict[str, Any]:
    """Pure decision: given a workload and a fleet snapshot, return the
    route decision dict. Does NO Mongo I/O.

    ``fleet`` items must look like ``runner_registry.list_runners()``
    output (with ``runner_id``, ``verdict``, ``age_seconds``, optional
    ``pair_filters`` / ``timeframe_filters`` / ``last_snapshot``).
    """
    used = _resolved_policy(policy)
    if not fleet:
        return _refusal(REASON_NO_RUNNERS, used, 0)

    alive = [r for r in fleet if _is_alive(r)]
    if not alive:
        return _refusal(REASON_NO_ALIVE_RUNNERS, used, len(fleet))

    # Single-runner shortcut — byte-identical to Phase 1.
    if len(alive) == 1:
        return _accept(alive[0], used, 1)

    if used == POLICY_LOCAL_ONLY:
        return _accept(alive[0], used, len(alive))

    if used == POLICY_ROUND_ROBIN:
        return _accept(_round_robin_pick(alive), used, len(alive))

    if used == POLICY_LEAST_BUSY:
        winner = sorted(alive, key=_sort_key)[0]  # _sort_key already includes queue depth
        return _accept(winner, used, len(alive))

    # POLICY_STICKY_PAIR_TF (default)
    p = (pair or "").strip().upper()
    t = (timeframe or "").strip().upper()
    matched = [
        r for r in alive
        if _matches_filter(r.get("pair_filters"), p)
        and _matches_filter(r.get("timeframe_filters"), t)
    ]
    if not matched:
        return _refusal(REASON_NO_AFFINITY_MATCH, used, len(alive))
    winner = sorted(matched, key=_sort_key)[0]
    return _accept(winner, used, len(matched))


# ── Async convenience wrapper that pulls fleet from runner_registry ──

async def route(
    pair: str,
    timeframe: str,
    *,
    policy: Optional[str] = None,
) -> Dict[str, Any]:
    """Async wrapper: fetches the current fleet and routes."""
    fleet = await runners.list_runners()
    return decide(pair, timeframe, fleet, policy=policy)


__all__ = [
    "POLICY_STICKY_PAIR_TF", "POLICY_LEAST_BUSY",
    "POLICY_ROUND_ROBIN",   "POLICY_LOCAL_ONLY",
    "VALID_POLICIES",       "DEFAULT_POLICY",
    "REASON_NO_RUNNERS",    "REASON_NO_ALIVE_RUNNERS",
    "REASON_NO_AFFINITY_MATCH", "REASON_POLICY_INVALID",
    "decide", "route",
]
