"""
Phase 2 scaffolding — Adaptive cooldown primitive (DORMANT).

A pure-function primitive: given a base cooldown plus signals (recent
error rate, host load, queue depth), compute a *clamped* effective
cooldown. Returns ``base_seconds`` unchanged while the gating flag is
OFF, so existing call-sites are unaffected.

Discipline:
  * Pure function. No DB writes, no env mutation, no I/O of any kind.
  * Dormant: ``ENABLE_ADAPTIVE_COOLDOWN=false`` (default) → identity.
  * Bounded: never returns less than ``base_seconds`` (no shortening),
    never more than ``base_seconds * ADAPTIVE_COOLDOWN_MAX_MULT``.
  * Reversible: deleting this file breaks zero existing imports.
"""
from __future__ import annotations

import os
from typing import Any, Dict


def is_enabled() -> bool:
    raw = (os.environ.get("ENABLE_ADAPTIVE_COOLDOWN") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def max_multiplier() -> float:
    try:
        m = float(os.environ.get("ADAPTIVE_COOLDOWN_MAX_MULT") or 4.0)
    except (TypeError, ValueError):
        m = 4.0
    return max(1.0, min(m, 16.0))


def compute_cooldown(
    base_seconds: float,
    *,
    recent_errors: int = 0,
    error_window_size: int = 10,
    load_per_core: float | None = None,
) -> float:
    """Return the effective cooldown in seconds.

    When flag OFF → returns ``base_seconds`` unchanged.
    When flag ON  → returns ``base_seconds × multiplier``, where the
    multiplier is a clamped function of error-rate and load.

    Pure: identical inputs always yield identical outputs.
    """
    base = max(0.0, float(base_seconds))
    if not is_enabled():
        return base
    err_rate = 0.0
    if error_window_size > 0:
        err_rate = max(0.0, min(1.0, float(recent_errors) / float(error_window_size)))
    # Map err_rate 0..1 → 1..MAX (linear).
    cap = max_multiplier()
    mult = 1.0 + err_rate * (cap - 1.0)
    # Add small load contribution (load_per_core > 1.0 is over-subscribed).
    if isinstance(load_per_core, (int, float)) and float(load_per_core) > 1.0:
        extra = min(cap - mult, 0.5 * (float(load_per_core) - 1.0))
        if extra > 0:
            mult += extra
    mult = max(1.0, min(mult, cap))
    return round(base * mult, 3)


def explain(
    base_seconds: float,
    *,
    recent_errors: int = 0,
    error_window_size: int = 10,
    load_per_core: float | None = None,
) -> Dict[str, Any]:
    """Diagnostic surface — returns the multiplier breakdown.

    Useful in the activation-governance endpoint so operators can see
    what the cooldown WOULD become if the flag were flipped on.
    """
    effective = compute_cooldown(
        base_seconds,
        recent_errors=recent_errors,
        error_window_size=error_window_size,
        load_per_core=load_per_core,
    )
    mult = (effective / float(base_seconds)) if base_seconds > 0 else 1.0
    return {
        "enabled":         is_enabled(),
        "max_multiplier":  max_multiplier(),
        "base_seconds":    float(base_seconds),
        "effective_seconds": effective,
        "multiplier":      round(mult, 4),
        "inputs": {
            "recent_errors":     int(recent_errors),
            "error_window_size": int(error_window_size),
            "load_per_core":     load_per_core,
        },
    }
