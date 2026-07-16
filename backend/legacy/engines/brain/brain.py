"""Phase F — TradingBrain orchestrator."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config as bcfg
from .policy import decide_action
from .risk_budget import compute_risk_budget
from .scorer import score_strategy
from .signals import collect_signals
from .types import BrainReport


async def brain_tick(
    portfolio_members: List[Dict[str, Any]],
    *,
    prices: Optional[List[float]] = None,
    open_positions: int = 0,
    execution_metadata: Optional[Dict[str, Any]] = None,
    pair: str = "EURUSD",
    timeframe: str = "H1",
) -> BrainReport:
    """One full brain tick. Never raises — degrades to a neutral report on
    any downstream engine failure."""
    signals = await collect_signals(
        prices=prices, portfolio_members=portfolio_members,
        open_positions=open_positions, execution_metadata=execution_metadata,
        pair=pair, timeframe=timeframe,
    )
    risk = compute_risk_budget(
        open_positions=open_positions,
        avg_correlation=signals.avg_pairwise_correlation,
    )
    decisions: List[Dict[str, Any]] = []
    pre_staged: List[str] = []
    emergencies: List[str] = []
    outcome_ids: List[str] = []

    avg_corr = signals.avg_pairwise_correlation or 0.0
    for m in portfolio_members:
        sc = score_strategy(m, signals, portfolio_avg_corr=avg_corr)
        d = decide_action(m, sc, signals,
                          risk_blocks_increase=risk.is_blocking_increase)
        decisions.append(d.to_dict())
        if d.action == "PRE_STAGE":
            pre_staged.append(d.strategy_hash)
        if d.action == "EMERGENCY_ZERO":
            emergencies.append(d.strategy_hash)

    # Emit outcome events (best-effort — never raises).
    try:
        from engines.intelligence.explainability import emit_decision
        # Per-strategy decisions
        for d in decisions:
            eid = await emit_decision(
                "brain_decision", strategy_hash=d["strategy_hash"],
                reason=d["reason"],
                metrics={"action": d["action"],
                         "target_weight": d["target_weight"],
                         "weight_delta": d["weight_delta"],
                         "score_now": d["score_now"],
                         "score_next": d["score_next"]},
                evidence={"components": (d.get("evidence") or {}).get("components", {}),
                          "regime": signals.regime,
                          "predicted_next_regime": signals.predicted_next_regime,
                          "transition_probability": signals.transition_probability})
            if eid:
                outcome_ids.append(eid)
        # One summary "brain_tick"
        tid = await emit_decision(
            "brain_tick", reason=f"regime={signals.regime}",
            metrics={
                "regime":                 signals.regime,
                "predicted_next_regime":  signals.predicted_next_regime,
                "transition_probability": signals.transition_probability,
                "n_decisions":            len(decisions),
                "n_pre_staged":           len(pre_staged),
                "n_emergencies":          len(emergencies),
                "risk_headroom":          risk.headroom,
                "diversification_score":  signals.diversification_score,
            },
            evidence={"signals": signals.to_dict(),
                      "policy_weights": bcfg.scoring_weights()})
        if tid:
            outcome_ids.append(tid)
    except Exception:                                        # pragma: no cover
        pass

    return BrainReport(
        ts=datetime.now(timezone.utc).isoformat(),
        signals=signals.to_dict(),
        decisions=decisions,
        pre_staged=pre_staged,
        emergency_zeroes=emergencies,
        risk_budget=risk.to_dict(),
        outcome_events_ids=outcome_ids,
        policy_weights=bcfg.scoring_weights(),
    )


class TradingBrain:
    """Convenience wrapper — the callable factory doesn't need a class,
    but future stateful extensions (weight-learning in Phase G) will."""
    async def tick(self, portfolio_members, **kw) -> BrainReport:
        return await brain_tick(portfolio_members, **kw)
