"""Phase D.4 — Strategy Promotion Engine.

Autonomous pipeline:
    Research → Validated → Tier 3 → Tier 2 → Tier 1 → Production

Rules (stateless — pure function of member state):
    Research → Validated:    total_trades ≥ 30 AND PF > 1.0
    Validated → Tier 3:      confidence ≥ 0.4 AND PF > 1.1 AND DD < 15%
    Tier 3    → Tier 2:      confidence ≥ 0.55 AND PF > 1.3 AND DD < 12% AND ≥N recent outcomes
    Tier 2    → Tier 1:      confidence ≥ 0.7 AND PF > 1.5 AND DD < 10% AND consistent outcomes
    Tier 1    → Production:  confidence ≥ 0.8 AND recent live PnL positive (or explicit approval)
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List

from . import config as pcfg
from .types import PortfolioMember


PIPELINE = ["research", "validated", "tier_3", "tier_2", "tier_1", "production"]


@dataclass
class PromotionDecision:
    strategy_hash:  str
    current_tier:   str
    proposed_tier:  str
    promote:        bool
    reason:         str = ""
    evidence:       Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _next_tier(current: str) -> str:
    try:
        i = PIPELINE.index(current)
        return PIPELINE[i + 1] if i + 1 < len(PIPELINE) else current
    except ValueError:
        return current


def _passes_gate(m: PortfolioMember, gate: str) -> (bool, str, Dict[str, Any]):  # type: ignore[valid-type]
    bt = m.backtest or {}
    pf = float(bt.get("profit_factor") or 0.0)
    dd = float(bt.get("max_drawdown_pct") or 100.0)
    tr = int(bt.get("total_trades") or 0)
    outcomes = len(m.recent_outcomes or [])
    ev = {"profit_factor": pf, "max_drawdown_pct": dd, "total_trades": tr,
          "confidence": m.confidence, "recent_outcomes": outcomes}

    if gate == "validated":
        ok = tr >= 30 and pf > 1.0
        return ok, ("gate_validated_passed" if ok else "insufficient_trades_or_pf"), ev
    if gate == "tier_3":
        ok = m.confidence >= 0.4 and pf > 1.1 and dd < 15.0
        return ok, ("gate_tier_3_passed" if ok else "conf_pf_or_dd_below_threshold"), ev
    if gate == "tier_2":
        ok = (m.confidence >= 0.55 and pf > 1.3 and dd < 12.0
              and outcomes >= pcfg.promotion_min_outcomes())
        return ok, ("gate_tier_2_passed" if ok else "insufficient_evidence_for_tier_2"), ev
    if gate == "tier_1":
        # Consistency check on recent outcomes (fraction "pass" ≥ 0.6).
        pass_rate = 0.0
        if outcomes > 0:
            pass_rate = sum(1 for o in m.recent_outcomes
                            if str(o.get("status")) == "pass") / outcomes
        ev["recent_pass_rate"] = round(pass_rate, 3)
        ok = (m.confidence >= 0.7 and pf > 1.5 and dd < 10.0 and pass_rate >= 0.6)
        return ok, ("gate_tier_1_passed" if ok else "not_ready_for_tier_1"), ev
    if gate == "production":
        # Production requires operator approval; the engine can only
        # RECOMMEND promotion to production.
        ok = m.confidence >= 0.8 and pf > 1.6 and dd < 8.0
        return ok, ("recommend_production" if ok else "not_ready_for_production"), ev
    return False, "unknown_gate", ev


def promotion_candidates(members: List[PortfolioMember]) -> List[PromotionDecision]:
    """Return one PromotionDecision per member — `promote=True` only when
    the next-tier gate passes."""
    out: List[PromotionDecision] = []
    for m in members:
        nxt = _next_tier(m.tier)
        if nxt == m.tier:
            out.append(PromotionDecision(m.strategy_hash, m.tier, m.tier, False,
                                         reason="already_at_top", evidence={}))
            continue
        ok, reason, ev = _passes_gate(m, nxt)
        out.append(PromotionDecision(m.strategy_hash, m.tier,
                                     nxt if ok else m.tier,
                                     bool(ok), reason=reason, evidence=ev))
    return out
