"""Phase D.5 — Strategy Retirement Engine.

Detects degradation using rolling windows over recent outcomes + backtest
trend and emits demotion/archive decisions. Reasons include:

    - PF trend negative over `PORTFOLIO_PF_TREND_WINDOW` outcomes
    - Confidence drift below `PORTFOLIO_CONFIDENCE_MIN_ACTIVE`
    - Prediction accuracy drop (closed-learning feedback)
    - Drawdown exceeds `PORTFOLIO_DRAWDOWN_RETIRE_PCT`
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List

from . import config as pcfg
from .types import PortfolioMember


@dataclass
class RetirementDecision:
    strategy_hash:  str
    current_tier:   str
    action:         str        # HOLD | DEMOTE | ARCHIVE | REPLACE
    proposed_tier:  str
    reason:         str = ""
    evidence:       Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


TIER_ORDER = ["production", "tier_1", "tier_2", "tier_3", "research"]


def _demote_tier(current: str) -> str:
    try:
        i = TIER_ORDER.index(current)
        return TIER_ORDER[i + 1] if i + 1 < len(TIER_ORDER) else current
    except ValueError:
        return "research"


def _pf_trend(outcomes: List[Dict[str, Any]], window: int) -> float:
    """Simple linear-trend slope of PF over the last `window` outcomes.
    Returns 0.0 on insufficient data."""
    ws = outcomes[-window:] if outcomes else []
    pfs = [float(o.get("metrics", {}).get("profit_factor") or 0.0) for o in ws]
    pfs = [p for p in pfs if p > 0]
    if len(pfs) < 3:
        return 0.0
    n = len(pfs)
    xs = list(range(n))
    mx = sum(xs) / n; my = sum(pfs) / n
    num = sum((xs[i] - mx) * (pfs[i] - my) for i in range(n))
    den = sum((v - mx) ** 2 for v in xs)
    if den == 0:
        return 0.0
    return round(num / den, 4)


def _prediction_accuracy(outcomes: List[Dict[str, Any]]) -> float:
    """Fraction of outcomes whose `predicted_pass` matched `status == 'pass'`.
    Returns 1.0 on empty (no signal)."""
    if not outcomes:
        return 1.0
    correct = 0
    total = 0
    for o in outcomes:
        m = o.get("metrics") or {}
        if "predicted_pass" not in m:
            continue
        total += 1
        if bool(m["predicted_pass"]) == (str(o.get("status")) == "pass"):
            correct += 1
    if total == 0:
        return 1.0
    return round(correct / total, 4)


def retirement_candidates(members: List[PortfolioMember]) -> List[RetirementDecision]:
    """Evaluate every member; return one decision per member."""
    out: List[RetirementDecision] = []
    for m in members:
        bt = m.backtest or {}
        dd = float(bt.get("max_drawdown_pct") or 0.0)
        trend = _pf_trend(m.recent_outcomes, pcfg.pf_trend_window())
        pred_acc = _prediction_accuracy(m.recent_outcomes)
        ev = {
            "max_drawdown_pct":     dd,
            "pf_trend":             trend,
            "prediction_accuracy":  pred_acc,
            "confidence":           m.confidence,
            "current_status":       m.status,
        }

        # Severe drawdown → REPLACE
        if dd >= pcfg.drawdown_retire_pct():
            out.append(RetirementDecision(
                m.strategy_hash, m.tier, "REPLACE",
                proposed_tier="research",
                reason=f"drawdown_{dd:.1f}%_exceeds_retire",
                evidence=ev,
            ))
            continue

        # Sustained negative PF trend → DEMOTE
        if trend < -0.05:
            demoted = _demote_tier(m.tier)
            out.append(RetirementDecision(
                m.strategy_hash, m.tier, "DEMOTE",
                proposed_tier=demoted,
                reason=f"pf_trend_{trend:.3f}_negative",
                evidence=ev,
            ))
            continue

        # Poor prediction accuracy AND low confidence → ARCHIVE
        if pred_acc < 0.4 and m.confidence < pcfg.confidence_min_active():
            out.append(RetirementDecision(
                m.strategy_hash, m.tier, "ARCHIVE",
                proposed_tier="research",
                reason=f"pred_acc_{pred_acc:.2f}_low_and_confidence_low",
                evidence=ev,
            ))
            continue

        out.append(RetirementDecision(
            m.strategy_hash, m.tier, "HOLD",
            proposed_tier=m.tier,
            reason="no_degradation_signals",
            evidence=ev,
        ))
    return out
