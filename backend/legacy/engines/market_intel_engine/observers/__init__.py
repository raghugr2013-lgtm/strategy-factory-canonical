"""Phase G — Market observers.

Each observer is a pure deterministic function of a list of
`MarketSnapshot` and returns an `ObserverResult(score∈[0..1], evidence)`.
Zero Mongo access; unit-testable in isolation.
"""
from __future__ import annotations

from .trend_duration import observe as observe_trend_duration
from .volatility_dynamics import observe as observe_volatility_dynamics
from .breakout_quality import observe as observe_breakout_quality
from .reversal_strength import observe as observe_reversal_strength
from .session_stats import observe as observe_session_stats
from .liquidity_estimator import observe as observe_liquidity
from .correlation_matrix import observe as observe_correlation
from .style_performance import observe as observe_style_performance

__all__ = [
    "observe_trend_duration", "observe_volatility_dynamics",
    "observe_breakout_quality", "observe_reversal_strength",
    "observe_session_stats", "observe_liquidity",
    "observe_correlation", "observe_style_performance",
]
