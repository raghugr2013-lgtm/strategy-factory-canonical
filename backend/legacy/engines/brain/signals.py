"""Phase F — Signal Collector."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .execution_quality import estimate_execution_quality
from .regime_transition import detect_transition
from .risk_budget import compute_risk_budget
from .types import BrainSignals


def _session_now() -> str:
    """UTC → trading session bucket (heuristic, no market calendar)."""
    hr = datetime.now(timezone.utc).hour
    if 0 <= hr < 7:
        return "asian"
    if 7 <= hr < 12:
        return "london"
    if 12 <= hr < 15:
        return "overlap"       # London/NY overlap
    if 15 <= hr < 21:
        return "ny"
    return "quiet"


def _liquidity_band(session: str) -> str:
    return {"overlap": "high", "london": "high", "ny": "high",
            "asian": "medium", "quiet": "low"}.get(session, "medium")


def _spread_context(band: str) -> str:
    return {"high": "tight", "medium": "normal",
            "low": "wide", "unknown": "unknown"}.get(band, "unknown")


async def collect_signals(
    prices: Optional[List[float]] = None,
    portfolio_members: Optional[List[Dict[str, Any]]] = None,
    open_positions: int = 0,
    execution_metadata: Optional[Dict[str, Any]] = None,
    pair: str = "EURUSD",
    timeframe: str = "H1",
) -> BrainSignals:
    """Assemble every input signal for the brain scorer.

    Never raises. Missing inputs degrade to neutral defaults so a Phase F
    tick can always complete even without market data / execution feed.
    """
    # Regime + transition (uses regime_classifier via Phase C wrapper)
    from engines.intelligence.market_regime import current_regime
    snap = await current_regime(pair=pair, timeframe=timeframe, prices=prices)
    # Transition detector uses raw prices (falls back to what current_regime used)
    used_prices = prices or []
    if not used_prices:
        # Reproduce the synthetic curve current_regime uses so both signals agree.
        import math
        used_prices = [round(1.08 + 0.001 * math.sin(i / 12.0), 5)
                       for i in range(200)]
    trans = detect_transition(used_prices)

    # Volatility from evidence / probe fallback
    volatility = float(snap.volatility or 0.0)

    # Pairwise correlation from portfolio equity curves (best-effort)
    avg_corr = None
    if portfolio_members and len(portfolio_members) >= 2:
        try:
            from engines.portfolio.health import _avg_pairwise_correlation
            from engines.portfolio.types import PortfolioMember
            objs = [PortfolioMember.from_dict(m) for m in portfolio_members]
            avg_corr = _avg_pairwise_correlation(objs)
        except Exception:                                    # pragma: no cover
            avg_corr = None

    # Diversification score = distinct styles / n_members (0..1)
    diversification = 1.0
    if portfolio_members:
        styles = {str(m.get("style") or "unknown") for m in portfolio_members}
        diversification = round(
            min(1.0, len(styles) / max(1, len(portfolio_members))), 4)

    # Risk budget
    rb = compute_risk_budget(open_positions=open_positions,
                             avg_correlation=avg_corr)

    # Execution quality (estimated from metadata; missing → neutral 0.7)
    ex = estimate_execution_quality(**(execution_metadata or {}))

    session = _session_now()
    band = _liquidity_band(session)
    return BrainSignals(
        regime=snap.regime,
        regime_confidence=snap.confidence,
        predicted_next_regime=trans.predicted_next_regime,
        transition_probability=trans.transition_probability,
        volatility=volatility,
        avg_pairwise_correlation=avg_corr,
        diversification_score=diversification,
        risk_budget_headroom=rb.headroom,
        liquidity_band=band,
        session=session,
        spread_context=_spread_context(band),
        ts=datetime.now(timezone.utc).isoformat(),
    )
