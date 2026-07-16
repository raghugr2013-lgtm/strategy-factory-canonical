"""Phase F — Adaptive Trading Brain (implementation).

Refinements from operator sign-off (2026-01-16):
  Q1 — Max 5% weight-delta per tick; catastrophic override → immediate 0.
  Q2 — Pre-staged strategies get SHADOW allocation (loaded, warmed, ready
       to switch in seconds — never real capital until fully promoted).
  Q3 — Heuristic regime detector only in this phase. HMM/Bayesian later.
  Q4 — Execution quality ESTIMATED from spread/latency/slippage/rejects/
       broker health/fill quality until live cTrader data exists.
  Q5 — Closed learning improves the SELECTION layer (confidence,
       activation, regime_suitability, style scores, portfolio
       contribution, strategy ranking, risk score) — NEVER rewrites
       strategy logic.
"""
from __future__ import annotations

from .types import (            # noqa: F401
    BrainDecision, BrainReport, BrainSignals, StrategyScore,
)
from .regime_transition import detect_transition, RegimeTransition  # noqa: F401
from .execution_quality import estimate_execution_quality  # noqa: F401
from .risk_budget import compute_risk_budget, RiskBudgetSnapshot  # noqa: F401
from .signals import collect_signals  # noqa: F401
from .scorer import score_strategy  # noqa: F401
from .policy import decide_action  # noqa: F401
from .brain import TradingBrain, brain_tick  # noqa: F401
