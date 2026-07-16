"""Phase I — env-driven configuration.

Every setting read at call-time so operators can flip a switch and the
running process picks it up on the next tick. No import-time captures.

Defaults are chosen so that `META_LEARNING_MODE=observe` produces a
functional read-only meta-learner. Downstream engines remain byte-
identical unless `*_USE_META_OVERRIDES=true` is explicitly set.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from .types import MetaMode


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw not in (None, "") else float(default)
    except (TypeError, ValueError):
        return float(default)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    try:
        return int(raw) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        return int(default)


def _bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in ("1", "true", "yes", "on", "y"): return True
    if raw in ("0", "false", "no", "off", "n"): return False
    return bool(default)


def _str(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if (v is not None and v != "") else default


# ── Master switches ────────────────────────────────────────────────
def mode() -> str:
    """`disabled | observe (default) | recommend | autonomous`."""
    m = _str("META_LEARNING_MODE", MetaMode.OBSERVE).strip().lower()
    return m if MetaMode.is_valid(m) else MetaMode.OBSERVE


def cadence_sec() -> int:
    return _int("META_LEARNING_CADENCE_SEC", 900)


def window_hours() -> int:
    return _int("META_LEARNING_WINDOW_HOURS", 24)


def min_samples() -> int:
    """Q4 warmup ramp: if `META_LEARNING_WARMUP_UNTIL` (ISO date) is
    in the future, use 30. Else 50."""
    warmup = warmup_until()
    if warmup:
        try:
            until = datetime.fromisoformat(warmup.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) < until:
                return _int("META_LEARNING_MIN_SAMPLES_WARMUP", 30)
        except (ValueError, TypeError):
            pass
    return _int("META_LEARNING_MIN_SAMPLES", 50)


def warmup_until() -> str:
    return _str("META_LEARNING_WARMUP_UNTIL", "")


def sig_threshold() -> float:
    return _float("META_LEARNING_SIG_THRESHOLD", 0.20)


def weight_step() -> float:
    return _float("META_LEARNING_WEIGHT_STEP", 0.01)


def max_delta_per_tick() -> float:
    return _float("META_LEARNING_MAX_DELTA_PER_TICK", 0.02)


def rec_ttl_days() -> int:
    return _int("META_LEARNING_REC_TTL_DAYS", 7)


def rank_floor() -> float:
    return _float("META_LEARNING_RANK_FLOOR", 0.01)


def calib_gap_min() -> float:
    return _float("META_LEARNING_CALIB_GAP_MIN", 0.10)


def autonomous_confirm() -> bool:
    """Q6: Autonomous mode is only truly effective when
    `META_LEARNING_AUTONOMOUS_CONFIRM=YES` is ALSO set — belt-and-
    suspenders promotion gate."""
    return (_str("META_LEARNING_AUTONOMOUS_CONFIRM", "")).strip().upper() == "YES"


# ── Two-step opt-in for downstream override consumption ────────────
def use_meta_overrides_brain() -> bool:
    """If True, brain config helpers may consult
    `meta_learning_overrides` at call-time. Default False (byte-
    identical to Phase F/G/H)."""
    return _bool("BRAIN_USE_META_OVERRIDES", False)


def use_meta_overrides_portfolio() -> bool:
    return _bool("PORTFOLIO_USE_META_OVERRIDES", False)


def use_meta_overrides_exec() -> bool:
    return _bool("EXEC_USE_META_OVERRIDES", False)


# ── Q2 autonomous whitelist ────────────────────────────────────────
def autonomous_whitelist() -> List[str]:
    """Comma-separated env var. Default recommendation: brain weights
    + Phase G market weights only. Empty list = nothing is auto-appliable."""
    raw = _str("META_LEARNING_AUTONOMOUS_WHITELIST",
               "brain_weight,market_weight").strip()
    return [t.strip() for t in raw.split(",") if t.strip()]


def class_caps() -> Dict[str, float]:
    """Per-surface max CUMULATIVE delta per rolling 24h."""
    return {
        "brain_weight":           _float("META_LEARNING_CAP_BRAIN_WEIGHT", 0.05),
        "brain_threshold":        _float("META_LEARNING_CAP_BRAIN_THRESHOLD", 0.05),
        "market_weight":          _float("META_LEARNING_CAP_MARKET_WEIGHT", 0.05),
        "portfolio_cap":          _float("META_LEARNING_CAP_PORTFOLIO", 0.05),
        "execution_gate":         _float("META_LEARNING_CAP_EXEC_GATE", 0.05),
        "confidence_calibration": _float("META_LEARNING_CAP_CONF_CALIB", 0.05),
        "style_regime_matrix":    _float("META_LEARNING_CAP_STYLE_REGIME", 0.05),
    }


# ── Debug helper ──────────────────────────────────────────────────
def config_snapshot() -> Dict[str, Any]:
    return {
        "META_LEARNING_MODE":         mode(),
        "META_LEARNING_CADENCE_SEC":  cadence_sec(),
        "META_LEARNING_WINDOW_HOURS": window_hours(),
        "META_LEARNING_MIN_SAMPLES":  min_samples(),
        "META_LEARNING_WARMUP_UNTIL": warmup_until(),
        "META_LEARNING_SIG_THRESHOLD":sig_threshold(),
        "META_LEARNING_WEIGHT_STEP":  weight_step(),
        "META_LEARNING_MAX_DELTA_PER_TICK": max_delta_per_tick(),
        "META_LEARNING_REC_TTL_DAYS": rec_ttl_days(),
        "META_LEARNING_RANK_FLOOR":   rank_floor(),
        "META_LEARNING_CALIB_GAP_MIN": calib_gap_min(),
        "META_LEARNING_AUTONOMOUS_CONFIRM": autonomous_confirm(),
        "BRAIN_USE_META_OVERRIDES":   use_meta_overrides_brain(),
        "PORTFOLIO_USE_META_OVERRIDES": use_meta_overrides_portfolio(),
        "EXEC_USE_META_OVERRIDES":    use_meta_overrides_exec(),
        "autonomous_whitelist":       autonomous_whitelist(),
        "class_caps":                 class_caps(),
    }
