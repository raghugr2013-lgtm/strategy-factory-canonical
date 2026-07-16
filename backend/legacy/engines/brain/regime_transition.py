"""Phase F — Regime Transition Detector (heuristic, Q3).

Compares regime on a short window vs a longer window. If they disagree,
the market is transitioning; probability = fraction of disagreement.

Roadmap noted in design doc: heuristic → hybrid → ML → HMM → Bayesian.
This module lives in the heuristic bucket by intent.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional


@dataclass
class RegimeTransition:
    current_regime:         str
    medium_regime:          str
    predicted_next_regime:  Optional[str]
    transition_probability: float
    method:                 str = "heuristic_short_vs_medium"
    evidence:               Dict[str, Any] = None  # type: ignore

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _classify(prices: List[float]) -> str:
    try:
        from engines.regime_classifier import classify_regime
        return classify_regime(prices)
    except Exception:                                        # pragma: no cover
        return "unknown"


def detect_transition(
    prices: List[float],
    short_window: int = 30,
    medium_window: int = 120,
) -> RegimeTransition:
    """Deterministic short-vs-medium regime comparison.

    - If short == medium → stable; transition_probability = 0.
    - If short ≠ medium → transitioning; probability reflects how many
      of the last three sub-windows agree with `short` (majority-vote).
    """
    if not prices or len(prices) < short_window:
        return RegimeTransition(
            current_regime="unknown", medium_regime="unknown",
            predicted_next_regime=None, transition_probability=0.0,
            evidence={"reason": "insufficient_prices",
                      "n_prices": len(prices) if prices else 0},
        )
    short = _classify(prices[-short_window:])
    medium = _classify(prices[-min(len(prices), medium_window):])
    prob = 0.0
    predicted_next = None
    if short != medium and short != "unknown":
        # Split the short window into 3 sub-windows and vote.
        step = max(1, short_window // 3)
        sub = [_classify(prices[-(i + 1) * step:-i * step]) if i > 0
               else _classify(prices[-step:])
               for i in range(3)]
        agree = sum(1 for s in sub if s == short)
        prob = round(agree / 3.0, 3)
        predicted_next = short
    return RegimeTransition(
        current_regime=medium if medium != "unknown" else short,
        medium_regime=medium,
        predicted_next_regime=predicted_next,
        transition_probability=prob,
        evidence={"short_window": short_window, "medium_window": medium_window,
                  "short_regime": short, "medium_regime": medium,
                  "n_prices": len(prices)},
    )
