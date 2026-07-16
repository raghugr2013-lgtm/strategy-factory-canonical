"""Phase D.6 — Self-Rebuilding Master Bot.

Composes the entire Phase D pipeline into a single idempotent pass:

    portfolio_health()          — snapshot health
        ↓
    retirement_candidates()     — find degrading strategies
        ↓
    promotion_candidates()      — find candidates ready for promotion
        ↓
    allocation_decisions()      — decide activate/pause/reduce/increase per member
        ↓
    capital_reweight()          — convert to % weights + cash reserve
        ↓
    dynamic_selector.select_active_strategy()   — Phase C — pick THE strategy for this regime
        ↓
    emit every decision to outcome_events (explainability)

Returns a `RebuildReport` with the full derivation.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config as pcfg
from .allocation import allocation_decisions
from .capital import capital_reweight
from .health import portfolio_health
from .promotion import promotion_candidates
from .retirement import retirement_candidates
from .types import PortfolioAction, PortfolioMember, PortfolioState


@dataclass
class RebuildReport:
    master_bot_id:      str
    ts:                 str
    regime:             str
    health:             Dict[str, Any] = field(default_factory=dict)
    retirements:        List[Dict[str, Any]] = field(default_factory=list)
    promotions:         List[Dict[str, Any]] = field(default_factory=list)
    actions:            List[Dict[str, Any]] = field(default_factory=list)
    capital:            Dict[str, Any] = field(default_factory=dict)
    active_selection:   Dict[str, Any] = field(default_factory=dict)
    changes_applied:    int = 0
    change_cap_hit:     bool = False
    outcome_events_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


async def _emit(decision_type: str, *, strategy_hash: Optional[str] = None,
                reason: str = "", metrics: Optional[Dict[str, Any]] = None,
                evidence: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Emit one outcome_events row via the Phase C explainability layer."""
    try:
        from engines.intelligence.explainability import emit_decision
        return await emit_decision(
            decision_type, strategy_hash=strategy_hash,
            reason=reason, metrics=metrics or {}, evidence=evidence or {},
        )
    except Exception:                                        # noqa: BLE001
        return None


async def rebuild_master_bot(
    state: PortfolioState,
    *,
    regime: str = "unknown",
) -> RebuildReport:
    """Run one full self-rebuild pass. Deterministic — same inputs
    yield the same report (modulo ISO timestamps + emit IDs).

    Fail-open: any per-engine error degrades to a no-op decision;
    the pass never crashes.
    """
    ts = datetime.now(timezone.utc).isoformat()
    outcome_ids: List[str] = []

    # 1. Health snapshot
    try:
        health = portfolio_health(state).to_dict()
    except Exception:                                        # noqa: BLE001
        health = {"error": "health_engine_failed", "signals": {}, "rebalance_required": False}
    hid = await _emit("health_check",
                      reason=f"score={health.get('health_score')}"
                             f" rebalance={health.get('rebalance_required')}",
                      metrics={"health_score": health.get("health_score"),
                               "rebalance_required": health.get("rebalance_required")},
                      evidence={"signals": health.get("signals", {}),
                                "diagnostics": health.get("diagnostics", {})})
    if hid: outcome_ids.append(hid)

    # 2. Retirement candidates
    try:
        retirements = [r.to_dict() for r in retirement_candidates(state.members)]
    except Exception:                                        # noqa: BLE001
        retirements = []
    for r in retirements:
        if r["action"] != "HOLD":
            rid = await _emit("retirement",
                              strategy_hash=r["strategy_hash"],
                              reason=r["reason"],
                              metrics={"action": r["action"],
                                       "proposed_tier": r["proposed_tier"]},
                              evidence=r["evidence"])
            if rid: outcome_ids.append(rid)

    # 3. Promotion candidates
    try:
        promotions = [p.to_dict() for p in promotion_candidates(state.members)]
    except Exception:                                        # noqa: BLE001
        promotions = []
    for p in promotions:
        if p["promote"]:
            pid = await _emit("promotion",
                              strategy_hash=p["strategy_hash"],
                              reason=p["reason"],
                              metrics={"current_tier": p["current_tier"],
                                       "proposed_tier": p["proposed_tier"]},
                              evidence=p["evidence"])
            if pid: outcome_ids.append(pid)

    # 4. Allocation decisions per member
    # Phase F integration — PORTFOLIO_POLICY env switch:
    #   phase_d (default) → deterministic Phase D allocation engine
    #   brain             → Phase F Adaptive Trading Brain
    # Behaviour under `phase_d` is byte-identical to Phase D. Instant
    # rollback: set `PORTFOLIO_POLICY=phase_d` (or unset).
    try:
        import os
        policy = os.environ.get("PORTFOLIO_POLICY", "phase_d").strip().lower()
        if policy == "brain":
            from engines.brain import brain_tick
            brain_report = await brain_tick(
                [m.to_dict() for m in state.members], pair="EURUSD",
                timeframe="H1",
            )
            actions = []
            # Translate BrainDecision → Phase D PortfolioAction wire format.
            for d in brain_report.decisions:
                actions.append({
                    "strategy_hash": d["strategy_hash"],
                    "action":        d["action"],
                    "weight_delta":  d["weight_delta"],
                    "reason":        d["reason"],
                    "evidence":      d.get("evidence") or {},
                })
        else:
            actions = [a.to_dict() for a in allocation_decisions(state, regime=regime)]
    except Exception:                                        # noqa: BLE001
        actions = []
    change_cap = pcfg.rebuild_max_changes()
    changes_applied = 0
    change_cap_hit = False
    non_hold = [a for a in actions if a["action"] != "HOLD"]
    for a in non_hold:
        if changes_applied >= change_cap:
            change_cap_hit = True
            break
        aid = await _emit("allocation_action",
                          strategy_hash=a["strategy_hash"],
                          reason=a["reason"],
                          metrics={"action": a["action"],
                                   "weight_delta": a["weight_delta"]},
                          evidence=a["evidence"])
        if aid: outcome_ids.append(aid)
        changes_applied += 1

    # 5. Capital reweight
    try:
        act_objs = [PortfolioAction(a["strategy_hash"], a["action"],
                                    a["weight_delta"], a.get("reason", ""),
                                    a.get("evidence", {})) for a in actions]
        capital = capital_reweight(state, act_objs)
    except Exception:                                        # noqa: BLE001
        capital = {"weights": {}, "cash_reserve": 1.0, "error": "capital_engine_failed"}
    cid = await _emit("capital_reweight",
                      reason=f"n_active={capital.get('n_active')}"
                             f" cash={capital.get('cash_reserve')}",
                      metrics={"cash_reserve":  capital.get("cash_reserve"),
                               "n_active":      capital.get("n_active"),
                               "n_paused":      capital.get("n_paused")},
                      evidence={"style_breakdown": capital.get("style_breakdown", {})})
    if cid: outcome_ids.append(cid)

    # 6. Dynamic selection (Phase C — pick THE strategy to trade now)
    try:
        from engines.intelligence.dynamic_selector import select_active_strategy
        # Use Phase C's style→regime preference table to synthesise
        # regime_suitability from `style` when the member doesn't carry
        # it explicitly. This is the same mapping the classifier uses.
        from engines.intelligence.strategy_intelligence import _regime_suitability  # type: ignore
        bundle = [{
            "strategy_hash":       m.strategy_hash,
            "style":               m.style,
            "confidence":          m.confidence,
            "regime_suitability":  (m.backtest.get("regime_suitability")
                                    or _regime_suitability(m.style)),
            "backtest":            m.backtest,
        } for m in state.members if m.status != "paused"]
        active = select_active_strategy(bundle, regime).to_dict()
    except Exception:                                        # noqa: BLE001
        active = {"active_hash": None, "reason": "selector_failed", "candidates": []}
    sid = await _emit("master_bot_rebuild",
                      strategy_hash=active.get("active_hash"),
                      reason=active.get("reason", "rebuild_complete"),
                      metrics={"regime": regime,
                               "changes_applied": changes_applied,
                               "cap_hit": change_cap_hit,
                               "n_members": len(state.members),
                               "active_style": active.get("active_style")},
                      evidence={"activation_candidates": active.get("candidates", [])})
    if sid: outcome_ids.append(sid)

    return RebuildReport(
        master_bot_id=state.master_bot_id,
        ts=ts, regime=regime,
        health=health, retirements=retirements, promotions=promotions,
        actions=actions, capital=capital, active_selection=active,
        changes_applied=changes_applied, change_cap_hit=change_cap_hit,
        outcome_events_ids=outcome_ids,
    )
