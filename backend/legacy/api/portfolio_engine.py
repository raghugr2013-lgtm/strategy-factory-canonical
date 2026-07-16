"""Phase D — /api/portfolio/* endpoints.

Read-heavy advisory endpoints (except `rebuild/{id}` and `capital` which
mutate outcome_events for explainability). Additive over Phase C.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_utils import require_admin

from engines.portfolio import (
    PortfolioMember,
    PortfolioState,
    PortfolioAction,
    allocation_decisions,
    capital_reweight,
    portfolio_health,
    promotion_candidates,
    retirement_candidates,
    rebuild_master_bot,
    record_realised_outcome,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


# ── Pydantic wrappers ─────────────────────────────────────────────

class StateIn(BaseModel):
    master_bot_id:  str = ""
    tier:           str = "tier_1"
    members:        List[Dict[str, Any]] = Field(default_factory=list)
    cash_reserve:   float = 0.1


class AllocateIn(BaseModel):
    state:  StateIn
    regime: str = "unknown"


class CapitalIn(BaseModel):
    state:   StateIn
    actions: List[Dict[str, Any]] = Field(default_factory=list)


class RebuildIn(BaseModel):
    state:  StateIn
    regime: str = "unknown"


class ClosedLearningIn(BaseModel):
    strategy_hash:   str
    predicted_score: Optional[float] = None
    realised_pnl:    Optional[float] = None
    realised_pass:   Optional[bool] = None
    metadata:        Optional[Dict[str, Any]] = None


def _to_state(payload: StateIn) -> PortfolioState:
    return PortfolioState.from_dict(payload.model_dump())


# ── Endpoints ─────────────────────────────────────────────────────

@router.post("/health")
async def portfolio_health_endpoint(state: StateIn):
    """Health snapshot for a supplied portfolio state."""
    r = portfolio_health(_to_state(state))
    return r.to_dict()


@router.get("/health/{master_bot_id}")
async def portfolio_health_by_id(master_bot_id: str):
    """Health snapshot for the persisted master bot (Mongo lookup best-effort)."""
    st = await _load_portfolio_state(master_bot_id)
    r = portfolio_health(st)
    return r.to_dict()


@router.post("/allocate")
async def portfolio_allocate(payload: AllocateIn):
    """Run the Allocation Engine (the brain) on a supplied portfolio state."""
    actions = allocation_decisions(_to_state(payload.state), regime=payload.regime)
    return {"regime": payload.regime,
            "actions": [a.to_dict() for a in actions],
            "action_counts": _count_actions([a.to_dict() for a in actions])}


@router.post("/capital")
async def portfolio_capital(payload: CapitalIn):
    """Convert a list of PortfolioActions into new % weights + cash reserve."""
    actions_objs = [PortfolioAction(
        a.get("strategy_hash", ""),
        a.get("action", "HOLD"),
        float(a.get("weight_delta") or 0.0),
        str(a.get("reason") or ""),
        a.get("evidence") or {},
    ) for a in payload.actions]
    return capital_reweight(_to_state(payload.state), actions_objs)


@router.post("/promotion-candidates")
async def portfolio_promotion_candidates(state: StateIn):
    return {"decisions": [d.to_dict() for d in
                          promotion_candidates(_to_state(state).members)]}


@router.post("/retirement-candidates")
async def portfolio_retirement_candidates(state: StateIn):
    return {"decisions": [d.to_dict() for d in
                          retirement_candidates(_to_state(state).members)]}


@router.post("/rebuild/{master_bot_id}")
async def portfolio_rebuild(
    master_bot_id: str,
    payload: RebuildIn,
    _u=Depends(require_admin),
):
    """Full self-rebuild pass. Idempotent. Emits outcome_events for
    every autonomous action (allocation / retirement / promotion /
    capital reweight / dynamic selection). Requires admin because the
    resulting decisions can materially move production capital when the
    downstream persist layer is enabled."""
    payload.state.master_bot_id = master_bot_id
    state = _to_state(payload.state)
    report = await rebuild_master_bot(state, regime=payload.regime)
    return report.to_dict()


@router.get("/state/{master_bot_id}")
async def portfolio_state(master_bot_id: str):
    st = await _load_portfolio_state(master_bot_id)
    return st.to_dict()


@router.post("/closed-learning/record")
async def portfolio_closed_learning(payload: ClosedLearningIn):
    event_id = await record_realised_outcome(
        payload.strategy_hash,
        predicted_score=payload.predicted_score,
        realised_pnl=payload.realised_pnl,
        realised_pass=payload.realised_pass,
        metadata=payload.metadata,
    )
    return {"ok": event_id is not None, "outcome_event_id": event_id}


# ── Helpers ───────────────────────────────────────────────────────

def _count_actions(actions: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for a in actions:
        counts[a["action"]] = counts.get(a["action"], 0) + 1
    return counts


async def _load_portfolio_state(master_bot_id: str) -> PortfolioState:
    """Best-effort loader from `master_bots` + `strategy_library`. Returns
    an empty state on any error so the endpoint always responds."""
    try:
        from engines.master_bot_engine import list_tiers as _list_tiers  # type: ignore
        tiers = await _list_tiers(master_bot_id)
        members: List[PortfolioMember] = []
        for t in tiers or []:
            for h in (t.get("strategies") or []):
                members.append(PortfolioMember(
                    strategy_hash=str(h),
                    tier=str(t.get("tier") or "tier_3"),
                ))
        return PortfolioState(master_bot_id=master_bot_id, members=members)
    except Exception:                                        # noqa: BLE001
        return PortfolioState(master_bot_id=master_bot_id, members=[])
