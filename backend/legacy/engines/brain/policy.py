"""Phase F — Decision Policy.

Converts (StrategyScore, member, signals, risk_budget) into a BrainDecision
with a target_weight ∈ [0..1] gated by:

  Q1 — max ±5% delta per tick (BRAIN_MAX_WEIGHT_DELTA_PER_TICK)
       Emergency ZERO overrides: severe DD, confidence collapse, broker
       failure hint (via execution_metadata['broker_health']='unhealthy'),
       corrupted strategy (recent prediction_accuracy collapse).
  Q2 — PRE_STAGE strategies get shadow_allocation only (no real capital).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from . import config as bcfg
from .types import BrainDecision, BrainSignals, StrategyScore


def _catastrophic_signal(member: Dict[str, Any],
                          signals: BrainSignals) -> Optional[str]:
    """Return reason string if any emergency-ZERO trigger fires; else None."""
    bt = member.get("backtest") or {}
    dd = float(bt.get("max_drawdown_pct") or 0.0)
    if dd >= bcfg.emergency_dd_pct():
        return f"emergency_severe_drawdown_{dd:.1f}%"
    conf = float(member.get("confidence") or 1.0)
    if conf <= bcfg.emergency_confidence():
        return f"emergency_confidence_collapse_{conf:.2f}"
    pred_acc = float(member.get("prediction_accuracy") or 1.0)
    if pred_acc <= bcfg.emergency_prediction_accuracy():
        return f"emergency_prediction_accuracy_{pred_acc:.2f}"
    if member.get("corrupted") is True:
        return "emergency_corrupted_strategy"
    if (member.get("broker_health") or "").lower() == "unhealthy":
        return "emergency_broker_failure"
    return None


def _clamp_delta(current: float, proposed: float,
                  cap: Optional[float] = None) -> float:
    cap = cap if cap is not None else bcfg.max_weight_delta_per_tick()
    delta = proposed - current
    if delta > cap:
        return round(current + cap, 4)
    if delta < -cap:
        return round(current - cap, 4)
    return round(proposed, 4)


def decide_action(
    member: Dict[str, Any],
    score: StrategyScore,
    signals: BrainSignals,
    risk_blocks_increase: bool = False,
) -> BrainDecision:
    """Deterministic policy. Never raises."""
    current = float(member.get("allocation") or 0.0)
    status = str(member.get("status") or "active")
    hash_ = str(member.get("strategy_hash") or "")

    # 1. Catastrophic override (Q1)
    cat = _catastrophic_signal(member, signals)
    if cat:
        return BrainDecision(
            strategy_hash=hash_, action="EMERGENCY_ZERO",
            target_weight=0.0, current_weight=current,
            weight_delta=-current, score_now=score.score_now,
            score_next=score.score_next, reason=cat,
            evidence={"catastrophic": True, "score_components": score.components},
        )

    # 2. Retire — deep below threshold
    if score.score_now < bcfg.retire_threshold():
        target = _clamp_delta(current, 0.0)
        return BrainDecision(
            strategy_hash=hash_, action="RETIRE",
            target_weight=target, current_weight=current,
            weight_delta=round(target - current, 4),
            score_now=score.score_now, score_next=score.score_next,
            reason=f"score_now_{score.score_now:.2f}<retire",
            evidence={"components": score.components, "reasons": score.reasons},
        )

    # 3. Pre-stage — paused strategy that WILL fit the incoming regime
    if (status == "paused"
            and score.score_next >= bcfg.trade_now_threshold()
            and signals.transition_probability >= bcfg.transition_prob_min()):
        return BrainDecision(
            strategy_hash=hash_, action="PRE_STAGE",
            target_weight=0.0, current_weight=current,
            weight_delta=0.0,
            shadow_allocation=bcfg.pre_stage_shadow_weight(),
            score_now=score.score_now, score_next=score.score_next,
            reason=f"pre_stage_for_next_regime_{signals.predicted_next_regime}",
            evidence={"shadow_only": True,
                      "transition_probability": signals.transition_probability,
                      "components": score.components},
        )

    # 4. Pause
    if score.score_now < bcfg.pause_threshold():
        target = _clamp_delta(current, 0.0)
        return BrainDecision(
            strategy_hash=hash_, action="PAUSE",
            target_weight=target, current_weight=current,
            weight_delta=round(target - current, 4),
            score_now=score.score_now, score_next=score.score_next,
            reason=f"score_now_{score.score_now:.2f}<pause",
            evidence={"components": score.components},
        )

    # 5. Increase / Trade Now — but respect risk budget block
    if score.score_now >= bcfg.trade_now_threshold():
        if risk_blocks_increase:
            # Hold at current weight — no increase permitted.
            return BrainDecision(
                strategy_hash=hash_, action="TRADE_NOW",
                target_weight=current, current_weight=current,
                weight_delta=0.0, score_now=score.score_now,
                score_next=score.score_next,
                reason="high_score_but_risk_budget_blocked",
                evidence={"components": score.components,
                          "risk_budget_blocked": True},
            )
        # Proposed weight scales with score above threshold; capped at 0.25.
        proposed = min(0.25, 0.10 + (score.score_now - bcfg.trade_now_threshold()) * 0.60)
        target = _clamp_delta(current, proposed)
        action = "INCREASE" if target > current else "TRADE_NOW"
        return BrainDecision(
            strategy_hash=hash_, action=action,
            target_weight=target, current_weight=current,
            weight_delta=round(target - current, 4),
            score_now=score.score_now, score_next=score.score_next,
            reason=f"score_now_{score.score_now:.2f}≥trade_now",
            evidence={"components": score.components,
                      "proposed_uncapped": proposed},
        )

    # 6. Middle band: TRADE_NOW at a mild allocation proportional to score
    proposed = 0.05 + (score.score_now - bcfg.pause_threshold()) * 0.15
    target = _clamp_delta(current, proposed)
    delta = round(target - current, 4)
    action = "TRADE_NOW" if delta == 0 else ("INCREASE" if delta > 0 else "REDUCE")
    if risk_blocks_increase and delta > 0:
        target = current; delta = 0.0; action = "TRADE_NOW"
    return BrainDecision(
        strategy_hash=hash_, action=action,
        target_weight=target, current_weight=current,
        weight_delta=delta, score_now=score.score_now,
        score_next=score.score_next,
        reason=f"middle_band_score_{score.score_now:.2f}",
        evidence={"components": score.components},
    )
