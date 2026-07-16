"""Phase F — env-driven brain configuration.

All weights and thresholds live-reload (read at call time, not import).
"""
from __future__ import annotations

import os
from typing import Dict


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


# ── Q1 · gradual portfolio evolution ──
def max_weight_delta_per_tick() -> float:
    return _float("BRAIN_MAX_WEIGHT_DELTA_PER_TICK", 0.05)


# ── Catastrophic override thresholds (Q1 emergency ZERO) ──
def emergency_dd_pct() -> float:
    return _float("BRAIN_EMERGENCY_DD_PCT", 30.0)


def emergency_confidence() -> float:
    return _float("BRAIN_EMERGENCY_CONFIDENCE", 0.15)


def emergency_prediction_accuracy() -> float:
    return _float("BRAIN_EMERGENCY_PREDICTION_ACCURACY", 0.2)


# ── Scoring weights (must sum to ~1.0, but not strictly enforced) ──
def scoring_weights() -> Dict[str, float]:
    return {
        "regime_fit":      _float("BRAIN_W_REGIME_FIT",     0.20),
        "confidence":      _float("BRAIN_W_CONFIDENCE",     0.20),
        "recent_pf":       _float("BRAIN_W_RECENT_PF",      0.15),
        "long_pf":         _float("BRAIN_W_LONG_PF",        0.10),
        "dd_penalty":      _float("BRAIN_W_DD",             0.10),
        "prediction_acc":  _float("BRAIN_W_PRED_ACC",       0.08),
        "corr_penalty":    _float("BRAIN_W_CORR",           0.07),
        "session_fit":     _float("BRAIN_W_SESSION",        0.05),
        "liquidity_fit":   _float("BRAIN_W_LIQUIDITY",      0.05),
    }


# ── Action thresholds ──
def trade_now_threshold() -> float:
    return _float("BRAIN_TRADE_NOW_THRESHOLD", 0.75)


def pause_threshold() -> float:
    return _float("BRAIN_PAUSE_THRESHOLD", 0.40)


def retire_threshold() -> float:
    return _float("BRAIN_RETIRE_THRESHOLD", 0.25)


def transition_prob_min() -> float:
    return _float("BRAIN_TRANSITION_PROB_MIN", 0.50)


# ── Risk budget ──
def risk_max_concurrent_trades() -> int:
    return _int("RISK_MAX_CONCURRENT_TRADES", 6)


def risk_headroom_hard_block() -> float:
    return _float("RISK_HEADROOM_HARD_BLOCK", 0.20)


# ── Pre-staging (Q2) ──
def pre_stage_shadow_weight() -> float:
    """Shadow allocation size for pre-staged strategies (never real capital
    until PROMOTE lifts them into the active portfolio)."""
    return _float("BRAIN_PRE_STAGE_SHADOW", 0.03)
