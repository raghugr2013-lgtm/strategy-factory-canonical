"""Phase 2 Stage 4 P4B.5 — Age-boost priority delta.

Tasks waiting longer than `ORCH_AGE_BOOST_S` (default 60s) receive a
+N priority delta per further 30s of wait. Prevents starvation under
sustained load.

Feature flag: `COE_AGE_BOOST_ENABLED` (default OFF). When off,
`compute_age_boost()` returns 0.0 — Stage-1..3 scoring is preserved
byte-identically.

Pure math — no I/O, no side effects. Composable with the existing
`orchestrator._score_task` via a single add: `score += compute_age_boost(...)`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def is_age_boost_enabled() -> bool:
    return _flag("COE_AGE_BOOST_ENABLED", False)


DEFAULT_AGE_BOOST_START_S:   float = 60.0
DEFAULT_AGE_BOOST_INTERVAL_S: float = 30.0
DEFAULT_AGE_BOOST_DELTA:     float = 1.0
DEFAULT_AGE_BOOST_MAX:       float = 20.0


@dataclass
class AgeBoost:
    """Result of `compute_age_boost()`."""
    delta:         float
    wait_seconds:  float
    intervals:     int
    reason:        str


def compute_age_boost(
    *,
    queued_at_iso: Optional[str],
    now:           Optional[datetime] = None,
    start_after_s: Optional[float] = None,
    interval_s:    Optional[float] = None,
    delta_per_interval: Optional[float] = None,
    max_delta:     Optional[float] = None,
) -> AgeBoost:
    """Compute the priority delta earned by a queued task.

    Returns `AgeBoost(delta=0.0, ...)` when the flag is off, when
    `queued_at_iso` is missing / unparseable, or when the wait is
    below the start threshold.
    """
    if not is_age_boost_enabled():
        return AgeBoost(delta=0.0, wait_seconds=0.0, intervals=0, reason="flag_off")
    if not queued_at_iso:
        return AgeBoost(delta=0.0, wait_seconds=0.0, intervals=0, reason="no_queued_at")
    try:
        queued_at = datetime.fromisoformat(queued_at_iso)
        if queued_at.tzinfo is None:
            queued_at = queued_at.replace(tzinfo=timezone.utc)
    except ValueError:
        return AgeBoost(delta=0.0, wait_seconds=0.0, intervals=0, reason="malformed_queued_at")

    now = now or datetime.now(timezone.utc)
    wait = max(0.0, (now - queued_at).total_seconds())

    start = float(start_after_s if start_after_s is not None
                  else _float_env("ORCH_AGE_BOOST_S", DEFAULT_AGE_BOOST_START_S))
    if wait < start:
        return AgeBoost(delta=0.0, wait_seconds=wait, intervals=0, reason="below_threshold")

    step = float(interval_s if interval_s is not None
                 else _float_env("ORCH_AGE_BOOST_INTERVAL_S", DEFAULT_AGE_BOOST_INTERVAL_S))
    if step <= 0:
        step = DEFAULT_AGE_BOOST_INTERVAL_S
    d_per = float(delta_per_interval if delta_per_interval is not None
                  else _float_env("ORCH_AGE_BOOST_DELTA", DEFAULT_AGE_BOOST_DELTA))
    cap = float(max_delta if max_delta is not None
                else _float_env("ORCH_AGE_BOOST_MAX", DEFAULT_AGE_BOOST_MAX))

    intervals_over = int((wait - start) // step) + 1  # +1 for crossing threshold
    delta = min(cap, intervals_over * d_per)
    return AgeBoost(
        delta=delta,
        wait_seconds=wait,
        intervals=intervals_over,
        reason="ok",
    )
