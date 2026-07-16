"""Phase F — Strategy Scorer.

Deterministic, transparent, env-tunable. Every input signal contributes
one term; the sum is the strategy's score_now (or score_next when the
transition detector suggests an imminent regime change).

`components` breakdown is preserved in the returned `StrategyScore` so
every decision is fully explainable in outcome_events.
"""
from __future__ import annotations

from typing import Any, Dict

from . import config as bcfg
from .types import BrainSignals, StrategyScore


# Phase C's style→regime preference table (kept in sync with the classifier).
_STYLE_REGIME_FIT = {
    "trending":        {"trend_following": 0.90, "momentum": 0.85,
                        "breakout": 0.75, "volatility_based": 0.55,
                        "session_based": 0.40, "mean_reversion": 0.15},
    "ranging":         {"mean_reversion": 0.90, "session_based": 0.70,
                        "trend_following": 0.20, "momentum": 0.25},
    "high_volatility": {"volatility_based": 0.90, "breakout": 0.85,
                        "momentum": 0.70, "trend_following": 0.50,
                        "mean_reversion": 0.35},
    "low_volatility":  {"trend_following": 0.80, "mean_reversion": 0.75,
                        "session_based": 0.60, "breakout": 0.30},
    "unknown":         {},
}

_STYLE_SESSION_FIT = {
    "asian":    {"session_based": 0.9, "mean_reversion": 0.7},
    "london":   {"trend_following": 0.9, "breakout": 0.9, "momentum": 0.85},
    "ny":       {"volatility_based": 0.9, "breakout": 0.85, "momentum": 0.85},
    "overlap":  {"breakout": 0.95, "volatility_based": 0.9},
    "quiet":    {"mean_reversion": 0.85, "session_based": 0.8},
    "unknown":  {},
}

_STYLE_LIQUIDITY_FIT = {
    "high":     {"trend_following": 0.9, "breakout": 0.9, "momentum": 0.9,
                 "volatility_based": 0.85, "scalping": 0.9},
    "medium":   {"trend_following": 0.7, "mean_reversion": 0.7,
                 "session_based": 0.75, "swing": 0.75},
    "low":      {"mean_reversion": 0.75, "session_based": 0.8, "swing": 0.7},
    "unknown":  {},
}


def _regime_fit(style: str, regime: str) -> float:
    prefs = _STYLE_REGIME_FIT.get(regime, {})
    return float(prefs.get(style, 0.5))


def _session_fit(style: str, session: str) -> float:
    return float(_STYLE_SESSION_FIT.get(session, {}).get(style, 0.5))


def _liquidity_fit(style: str, band: str) -> float:
    return float(_STYLE_LIQUIDITY_FIT.get(band, {}).get(style, 0.5))


def _norm_pf(pf: float) -> float:
    """PF 1.0 → 0.0; 2.0 → 0.5; 3.0 → 0.67; capped 1.0."""
    if pf is None or pf <= 1.0:
        return 0.0
    return round(min(1.0, (float(pf) - 1.0) / 2.0), 4)


def _norm_dd(dd_pct: float) -> float:
    """DD 0% → 1.0; DD 30% → 0.0."""
    if dd_pct is None:
        return 0.5
    return round(max(0.0, min(1.0, 1.0 - float(dd_pct) / 30.0)), 4)


def score_strategy(
    member: Dict[str, Any],
    signals: BrainSignals,
    portfolio_avg_corr: float = 0.0,
) -> StrategyScore:
    """Compute one StrategyScore. Deterministic + explainable."""
    style = str(member.get("style") or "unknown")
    conf = float(member.get("confidence") or 0.5)
    bt = member.get("backtest") or {}
    recent = member.get("recent_metrics") or {}
    pred_acc = float(member.get("prediction_accuracy") or 0.7)

    w = bcfg.scoring_weights()

    # Components
    comp = {
        "regime_fit":     w["regime_fit"]     * _regime_fit(style, signals.regime),
        "confidence":     w["confidence"]     * conf,
        "recent_pf":      w["recent_pf"]      * _norm_pf(float(recent.get("profit_factor") or bt.get("profit_factor") or 0.0)),
        "long_pf":        w["long_pf"]        * _norm_pf(float(bt.get("profit_factor") or 0.0)),
        "dd_penalty":     w["dd_penalty"]     * _norm_dd(float(bt.get("max_drawdown_pct") or 0.0)),
        "prediction_acc": w["prediction_acc"] * pred_acc,
        "corr_penalty":   w["corr_penalty"]   * max(0.0, 1.0 - float(portfolio_avg_corr or 0.0)),
        "session_fit":    w["session_fit"]    * _session_fit(style, signals.session),
        "liquidity_fit":  w["liquidity_fit"]  * _liquidity_fit(style, signals.liquidity_band),
    }
    score_now = round(max(0.0, min(1.0, sum(comp.values()))), 4)

    # score_next: swap regime for predicted_next_regime when transition looms.
    if (signals.predicted_next_regime
            and signals.transition_probability >= bcfg.transition_prob_min()):
        next_fit = _regime_fit(style, signals.predicted_next_regime)
        comp_next = dict(comp)
        comp_next["regime_fit"] = w["regime_fit"] * next_fit
        score_next = round(max(0.0, min(1.0, sum(comp_next.values()))), 4)
    else:
        # No transition expected → next ~ now (slight discount for uncertainty)
        score_next = round(score_now * 0.9, 4)

    reasons = []
    if signals.transition_probability >= bcfg.transition_prob_min():
        reasons.append(f"transition_watch: {signals.regime}"
                       f"→{signals.predicted_next_regime}"
                       f"@p={signals.transition_probability}")
    if signals.risk_budget_headroom < bcfg.risk_headroom_hard_block():
        reasons.append(f"risk_budget_low:{signals.risk_budget_headroom}")

    return StrategyScore(
        strategy_hash=str(member.get("strategy_hash") or ""),
        score_now=score_now,
        score_next=score_next,
        components={k: round(v, 4) for k, v in comp.items()},
        reasons=reasons,
    )
