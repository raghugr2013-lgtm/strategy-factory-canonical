"""Phase D.2 — Capital Allocation Engine.

Converts a list of `PortfolioAction`s into a new weight vector.

Design:
    - Base weight per active member = 1 / N (equal-weight scaffold)
    - Risk-parity tilt: weight_i ∝ 1 / (max_drawdown_pct_i + 1)
    - Confidence tilt : weight_i ×= confidence_i
    - Regime-fit tilt : weight_i ×= regime_fit_i (from allocation action evidence)
    - Style cap enforced (no style > PORTFOLIO_MAX_STYLE_SHARE)
    - Cash reserve enforced (≥ PORTFOLIO_MIN_CASH_RESERVE)
    - Paused members get 0 weight; REDUCE/INCREASE bias applied
    - Weights normalised so sum(weights) + cash_reserve == 1

Deterministic. No LLM. No I/O.
"""
from __future__ import annotations

from typing import Dict, List

from . import config as pcfg
from .types import PortfolioAction, PortfolioMember, PortfolioState


def _base_weight(m: PortfolioMember, action: PortfolioAction) -> float:
    if m.status == "paused" and action.action != "ACTIVATE":
        return 0.0
    if action.action == "PAUSE":
        return 0.0
    if action.action == "REPLACE":
        return 0.0
    bt = m.backtest or {}
    dd = float(bt.get("max_drawdown_pct") or 0.0)
    risk_parity = 1.0 / (dd + 1.0)
    conf = max(0.0, min(1.0, m.confidence))
    regime_fit = float((action.evidence or {}).get("regime_fit") or 0.5)
    return round(risk_parity * conf * regime_fit, 6)


def _enforce_style_cap(weights: Dict[str, float],
                       members_by_hash: Dict[str, PortfolioMember]) -> Dict[str, float]:
    style_sum: Dict[str, float] = {}
    for h, w in weights.items():
        m = members_by_hash.get(h)
        if m is None:
            continue
        style_sum[m.style] = style_sum.get(m.style, 0.0) + w
    cap = pcfg.max_style_share()
    for style, total in style_sum.items():
        if total > cap and total > 0:
            factor = cap / total
            for h, w in list(weights.items()):
                m = members_by_hash.get(h)
                if m and m.style == style:
                    weights[h] = w * factor
    return weights


def capital_reweight(
    state: PortfolioState,
    actions: List[PortfolioAction],
) -> Dict[str, object]:
    """Return a dict {weights: {hash: 0..1}, cash_reserve, evidence}.

    Sum of `weights.values()` + `cash_reserve` == 1.0 (rounded to 4dp).
    """
    action_by_hash = {a.strategy_hash: a for a in actions}
    members_by_hash = {m.strategy_hash: m for m in state.members}

    # 1. base weights
    weights: Dict[str, float] = {}
    for m in state.members:
        act = action_by_hash.get(m.strategy_hash) \
            or PortfolioAction(m.strategy_hash, "HOLD")
        weights[m.strategy_hash] = _base_weight(m, act)

    # 2. INCREASE/REDUCE deltas — additive bumps before normalisation
    for a in actions:
        if a.action == "INCREASE":
            weights[a.strategy_hash] = weights.get(a.strategy_hash, 0.0) * 1.3
        elif a.action == "REDUCE":
            weights[a.strategy_hash] = weights.get(a.strategy_hash, 0.0) * 0.6

    # 3. style cap (applied BEFORE normalisation)
    weights = _enforce_style_cap(weights, members_by_hash)

    # 4. normalise to (1 - cash_reserve) — renormalises after style-cap
    #    reductions so weights + cash still sum to 1.0.
    cash = max(pcfg.min_cash_reserve(), state.cash_reserve or 0.0)
    cash = min(0.9, cash)   # never let cash exceed 90%
    total = sum(weights.values())
    if total > 0:
        scale = (1.0 - cash) / total
        for h in weights:
            weights[h] = round(weights[h] * scale, 4)
        # After scaling, style shares might still exceed the cap because the
        # non-capped styles absorb the reallocated weight. Apply the cap a
        # second time then renormalise once more — the fixed point converges
        # in at most 3 iterations for any realistic mix.
        for _ in range(3):
            capped_before = dict(weights)
            weights = _enforce_style_cap(weights, members_by_hash)
            if weights == capped_before:
                break
            total = sum(weights.values())
            if total > 0:
                scale = (1.0 - cash) / total
                for h in weights:
                    weights[h] = round(weights[h] * scale, 4)
        # Final safeguard: if the cap still isn't satisfiable (e.g. the
        # entire portfolio is a single style), push excess to cash reserve.
        style_sum: Dict[str, float] = {}
        for h, w in weights.items():
            m = members_by_hash.get(h)
            if m:
                style_sum[m.style] = style_sum.get(m.style, 0.0) + w
        cap = pcfg.max_style_share()
        for style, total_style in style_sum.items():
            if total_style > cap + 0.001:
                excess = total_style - cap
                factor = cap / total_style if total_style > 0 else 0.0
                for h in list(weights.keys()):
                    m = members_by_hash.get(h)
                    if m and m.style == style:
                        weights[h] = round(weights[h] * factor, 4)
                cash = round(cash + excess, 4)
    else:
        cash = 1.0
        for h in weights:
            weights[h] = 0.0

    # 5. style breakdown for evidence
    style_breakdown: Dict[str, float] = {}
    for h, w in weights.items():
        m = members_by_hash.get(h)
        if m is None:
            continue
        style_breakdown[m.style] = round(style_breakdown.get(m.style, 0.0) + w, 4)

    return {
        "weights":       weights,
        "cash_reserve":  round(cash, 4),
        "style_breakdown": style_breakdown,
        "n_active":      sum(1 for w in weights.values() if w > 0),
        "n_paused":      sum(1 for w in weights.values() if w == 0),
        "sum_check":     round(sum(weights.values()) + cash, 4),
    }
