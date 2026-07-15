"""v1.2.0-alpha2 Phase B — configurable learning thresholds.

Every threshold that controls the continuous-learning supervisor
(early-reject profit factor, minimum trades, drawdown ceiling, etc.)
is defined here and reads from environment variables at *call* time
(not import time) so the operator can retune without restarting.

All values ship with the design-doc defaults so a stock deployment
matches the alpha2 Phase A behaviour. Every getter is idempotent and
cheap (single env read + coerce) — safe to call inside a hot loop.
"""
from __future__ import annotations

import os
from typing import Any, Dict


def _float_env(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name)
        if raw is None or raw == "":
            return float(default)
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _int_env(name: str, default: int) -> int:
    try:
        raw = os.environ.get(name)
        if raw is None or raw == "":
            return int(default)
        return int(raw)
    except (TypeError, ValueError):
        return int(default)


def _flag_env(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


# ── Supervisor early-reject thresholds ────────────────────────────
def pf_min() -> float:
    """Minimum profit factor. Below this → early reject after backtest."""
    return _float_env("LEARNING_PF_MIN", 1.2)


def dd_max_pct() -> float:
    """Maximum drawdown percentage tolerated (post-backtest)."""
    return _float_env("LEARNING_DD_MAX_PCT", 25.0)


def min_trades() -> int:
    """Minimum backtest trade count."""
    return _int_env("LEARNING_MIN_TRADES", 30)


def wr_min_pct() -> float:
    """Minimum win rate percentage."""
    return _float_env("LEARNING_WR_MIN_PCT", 25.0)


def wr_max_pct() -> float:
    """Maximum win rate — > this suggests over-fitting."""
    return _float_env("LEARNING_WR_MAX_PCT", 90.0)


# ── Optimizer + mutator gates ─────────────────────────────────────
def optimize_uplift_min() -> float:
    """Minimum score uplift (delta) required to accept an optimisation."""
    return _float_env("LEARNING_OPTIMIZE_UPLIFT_MIN", 0.0)


def mutation_enabled() -> bool:
    return _flag_env("LEARNING_MUTATION_ENABLED", True)


# ── Cycle scheduling ─────────────────────────────────────────────
def scheduler_enabled() -> bool:
    """Whether the periodic learning scheduler runs."""
    return _flag_env("LEARNING_SCHEDULER_ENABLED", False)


def scheduler_interval_seconds() -> int:
    """Interval between periodic scheduled learning cycles."""
    return _int_env("LEARNING_SCHEDULER_INTERVAL_S", 3600)


def scheduler_max_concurrent() -> int:
    return _int_env("LEARNING_SCHEDULER_MAX_CONCURRENT", 1)


# ── Retrieval / outcome conditioning ──────────────────────────────
def retrieval_outcome_weight() -> float:
    """Scalar boost applied to a candidate's outcome-derived quality
    score during knowledge retrieval. 0.0 → disabled."""
    return _float_env("LEARNING_RETRIEVAL_OUTCOME_WEIGHT", 2.0)


def retrieval_min_events() -> int:
    """Minimum outcome events required before conditioning kicks in."""
    return _int_env("LEARNING_RETRIEVAL_MIN_EVENTS", 3)


# ── AI Workforce router ───────────────────────────────────────────
def ai_workforce_enabled() -> bool:
    """Master switch for the AI Workforce failover router. When False,
    LLM calls take the legacy direct-to-VIE path. When True, calls
    consult the circuit-breaker + provider preferences before dispatch."""
    return _flag_env("AI_WORKFORCE_FAILOVER", False)


def snapshot() -> Dict[str, Any]:
    """Return the current effective configuration. Used by
    `/api/learning/config` for the future dashboard."""
    return {
        "supervisor": {
            "pf_min": pf_min(),
            "dd_max_pct": dd_max_pct(),
            "min_trades": min_trades(),
            "wr_min_pct": wr_min_pct(),
            "wr_max_pct": wr_max_pct(),
            "optimize_uplift_min": optimize_uplift_min(),
            "mutation_enabled": mutation_enabled(),
        },
        "scheduler": {
            "enabled": scheduler_enabled(),
            "interval_seconds": scheduler_interval_seconds(),
            "max_concurrent": scheduler_max_concurrent(),
        },
        "retrieval": {
            "outcome_weight": retrieval_outcome_weight(),
            "min_events": retrieval_min_events(),
        },
        "ai_workforce": {
            "failover_enabled": ai_workforce_enabled(),
        },
    }
