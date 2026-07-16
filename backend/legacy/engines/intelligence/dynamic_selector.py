"""Phase C.5 — Dynamic Strategy Selector.

Given a Master Bot bundle (list of classified strategies) and the current
regime, selects the highest-confidence strategy to ACTIVATE right now.

Selection formula (deterministic):

    activation_score(s) =
        classification.confidence
      × regime_suitability[current_regime]
      × (1 + solo_pf_boost(s))            # PF > 1.5 bumps by up to 0.3
      × (1 - risk_penalty(s))             # high DD tapers 0..0.3

The winning strategy is returned as an `ActivationDecision` with full
per-candidate scoring for the operator dashboard.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


@dataclass
class ActivationDecision:
    active_hash:        Optional[str]
    active_style:       Optional[str]
    regime:             str
    activation_score:   float
    reason:             str
    candidates:         List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _pf_boost(bt: Dict[str, Any]) -> float:
    pf = float((bt or {}).get("profit_factor") or 0.0)
    if pf <= 1.0:
        return 0.0
    return round(min(0.3, (pf - 1.0) * 0.15), 4)


def _risk_penalty(bt: Dict[str, Any]) -> float:
    dd = float((bt or {}).get("max_drawdown_pct") or 0.0)
    if dd <= 5:
        return 0.0
    return round(min(0.3, (dd - 5.0) / 100.0), 4)


def select_active_strategy(
    bundle: List[Dict[str, Any]],
    current_regime: str,
) -> ActivationDecision:
    """Pick the best strategy in `bundle` for `current_regime`.

    Every bundle element must expose:
        - strategy_hash
        - style
        - regime_suitability (dict)
        - confidence
        - backtest (dict)
    Missing fields degrade gracefully (score 0). Never raises.

    Returns an `ActivationDecision` with the winner + full per-candidate
    scoring for explainability.
    """
    if not bundle:
        return ActivationDecision(
            active_hash=None, active_style=None,
            regime=current_regime, activation_score=0.0,
            reason="empty_bundle", candidates=[],
        )

    scored: List[Dict[str, Any]] = []
    for s in bundle:
        cls_conf = float(s.get("confidence") or 0.0)
        rs = s.get("regime_suitability") or {}
        regime_fit = float(rs.get(current_regime, 0.0))
        if regime_fit == 0.0 and current_regime == "unknown":
            regime_fit = 0.5
        bt = s.get("backtest") or {}
        score = round(
            cls_conf * regime_fit
            * (1.0 + _pf_boost(bt))
            * (1.0 - _risk_penalty(bt)),
            4,
        )
        scored.append({
            "strategy_hash": s.get("strategy_hash"),
            "style":         s.get("style"),
            "confidence":    cls_conf,
            "regime_fit":    regime_fit,
            "pf_boost":      _pf_boost(bt),
            "risk_penalty":  _risk_penalty(bt),
            "score":         score,
        })

    # Deterministic winner: highest score, ties broken by strategy_hash asc.
    scored.sort(key=lambda x: (-x["score"], str(x.get("strategy_hash") or "")))
    winner = scored[0]
    reason = (
        f"regime={current_regime} winner={winner['style']}"
        f" conf={winner['confidence']} fit={winner['regime_fit']}"
    ) if winner["score"] > 0 else f"no_suitable_strategy_for_{current_regime}"

    return ActivationDecision(
        active_hash=winner["strategy_hash"] if winner["score"] > 0 else None,
        active_style=winner["style"] if winner["score"] > 0 else None,
        regime=current_regime,
        activation_score=winner["score"],
        reason=reason,
        candidates=scored,
    )
