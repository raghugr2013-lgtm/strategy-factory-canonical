"""Phase D.1 — Portfolio Allocation Engine (the brain).

For every strategy in the portfolio produces one action:
    ACTIVATE / PAUSE / REDUCE / INCREASE / REPLACE / HOLD

Deterministic. Reads:
    - regime (from Phase C market_regime)
    - member.confidence (Phase C classifier)
    - member.backtest (drawdown, PF, WR)
    - correlation vs rest of portfolio
    - style diversity
No LLM calls. No I/O. Pure decision function.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import config as pcfg
from .types import PortfolioAction, PortfolioMember, PortfolioState


def _regime_fit(m: PortfolioMember, regime: str) -> float:
    # Fallback: prefer trend styles in trending regimes, mean_reversion in ranging.
    style_prefs = {
        "trending":        {"trend_following": 0.9, "momentum": 0.85, "breakout": 0.75,
                             "volatility_based": 0.55, "session_based": 0.4,
                             "mean_reversion": 0.15},
        "ranging":         {"mean_reversion": 0.9, "session_based": 0.7,
                             "trend_following": 0.2, "momentum": 0.25},
        "high_volatility": {"volatility_based": 0.9, "breakout": 0.85,
                             "momentum": 0.7, "trend_following": 0.5,
                             "mean_reversion": 0.35},
        "low_volatility":  {"trend_following": 0.8, "mean_reversion": 0.75,
                             "session_based": 0.6, "breakout": 0.3},
        "unknown":         {},
    }
    prefs = style_prefs.get(regime, {})
    return float(prefs.get(m.style, 0.5))


def _pairwise_max_correlation(m: PortfolioMember,
                              others: List[PortfolioMember]) -> Optional[float]:
    import math
    ec = m.equity_curve or []
    max_abs = 0.0
    found = False
    for o in others:
        if o.strategy_hash == m.strategy_hash:
            continue
        eo = o.equity_curve or []
        n = min(len(ec), len(eo))
        if n < 20:
            continue
        xa = ec[:n]; xb = eo[:n]
        ma = sum(xa) / n; mb = sum(xb) / n
        num = sum((xa[i] - ma) * (xb[i] - mb) for i in range(n))
        va = sum((v - ma) ** 2 for v in xa)
        vb = sum((v - mb) ** 2 for v in xb)
        den = math.sqrt(va * vb)
        if den <= 0:
            continue
        c = abs(num / den)
        found = True
        if c > max_abs:
            max_abs = c
    return max_abs if found else None


def _style_share(state: PortfolioState, style: str) -> float:
    if not state.members:
        return 0.0
    same = sum(1 for m in state.members if m.style == style)
    return same / len(state.members)


def _decide_one(m: PortfolioMember,
                state: PortfolioState,
                regime: str) -> PortfolioAction:
    bt = m.backtest or {}
    dd = float(bt.get("max_drawdown_pct") or 0.0)
    pf = float(bt.get("profit_factor") or 0.0)
    fit = _regime_fit(m, regime)
    corr = _pairwise_max_correlation(m, state.members)
    style_share = _style_share(state, m.style)

    ev = {
        "regime":        regime,
        "regime_fit":    fit,
        "confidence":    m.confidence,
        "profit_factor": pf,
        "max_drawdown_pct": dd,
        "max_correlation": corr,
        "style_share":   style_share,
        "current_status": m.status,
        "current_allocation": m.allocation,
    }

    # 1. Hard retirement conditions (severe drawdown or terrible fit + weak).
    if dd >= pcfg.drawdown_retire_pct():
        return PortfolioAction(m.strategy_hash, "REPLACE",
                               -m.allocation,
                               reason=f"drawdown_{dd:.1f}%_exceeds_retire_{pcfg.drawdown_retire_pct():.1f}%",
                               evidence=ev)

    # 2. Pause conditions (moderate drawdown OR low confidence OR bad fit).
    if dd >= pcfg.drawdown_pause_pct():
        return PortfolioAction(m.strategy_hash, "PAUSE",
                               -m.allocation,
                               reason=f"drawdown_{dd:.1f}%_exceeds_pause_{pcfg.drawdown_pause_pct():.1f}%",
                               evidence=ev)
    if m.confidence < pcfg.confidence_min_active():
        return PortfolioAction(m.strategy_hash, "PAUSE",
                               -m.allocation,
                               reason=f"confidence_{m.confidence:.2f}_below_min",
                               evidence=ev)

    # 3. Reduce conditions (heavy correlation with rest of portfolio).
    if corr is not None and corr >= pcfg.correlation_max():
        return PortfolioAction(m.strategy_hash, "REDUCE",
                               -min(m.allocation * 0.3, 0.05),
                               reason=f"correlation_{corr:.2f}_exceeds_max",
                               evidence=ev)

    # 4. Reduce if style already over-represented AND there are ≥2 members
    # (single-member portfolios trivially have style_share=1.0 which
    # shouldn't trigger REDUCE).
    if style_share > pcfg.max_style_share() and len(state.members) >= 2:
        return PortfolioAction(m.strategy_hash, "REDUCE",
                               -0.02,
                               reason=f"style_share_{style_share:.2f}_over_cap",
                               evidence=ev)

    # 5. Activate paused members that no longer trip pause conditions.
    if m.status == "paused":
        return PortfolioAction(m.strategy_hash, "ACTIVATE",
                               0.0,
                               reason="conditions_restored",
                               evidence=ev)

    # 6. Increase when regime fit is high + confidence is high + not over-allocated.
    if fit >= 0.75 and m.confidence >= 0.7 and m.allocation < 0.15:
        return PortfolioAction(m.strategy_hash, "INCREASE",
                               0.03,
                               reason=f"regime_fit_{fit:.2f}_conf_{m.confidence:.2f}_high",
                               evidence=ev)

    return PortfolioAction(m.strategy_hash, "HOLD", 0.0,
                           reason="within_bands", evidence=ev)


def allocation_decisions(
    state: PortfolioState,
    regime: str = "unknown",
) -> List[PortfolioAction]:
    """Compute one PortfolioAction per member. Deterministic — same
    inputs yield same output."""
    return [_decide_one(m, state, regime) for m in state.members]
