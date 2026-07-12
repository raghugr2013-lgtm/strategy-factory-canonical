"""/api/latent/risk_of_ruin — diagnostic surface for the RoR engine."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from auth_utils import get_current_user
from engines import risk_of_ruin as ror_engine
from engines.feature_flags import flag

router = APIRouter()


class RoREvaluateRequest(BaseModel):
    strategy_hash: str = Field(..., min_length=1)
    win_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    payoff_ratio: Optional[float] = Field(None, gt=0.0)
    risk_per_trade: float = Field(0.01, gt=0.0, le=0.5)
    capital_units: int = Field(100, ge=1, le=10000)
    trades: Optional[List[Dict[str, Any]]] = None
    dd_limit_pct: float = Field(30.0, gt=0.0, le=100.0)
    n_simulations: Optional[int] = Field(None, ge=100, le=20000)


@router.post("/latent/risk_of_ruin/evaluate")
async def evaluate(
    body: RoREvaluateRequest,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Evaluate + persist RoR for a strategy. Diagnostic only — does NOT
    affect deploy_score (weight is 0.0 by default).

    Provide EITHER (win_rate + payoff_ratio) for closed-form,
    OR `trades` for Monte-Carlo, or both.
    """
    if not flag("ENABLE_RISK_OF_RUIN"):
        return {
            "is_active": False,
            "note":      "ENABLE_RISK_OF_RUIN=false — endpoint stub returning no-op",
        }
    return await ror_engine.evaluate(
        strategy_hash=body.strategy_hash,
        win_rate=body.win_rate,
        payoff_ratio=body.payoff_ratio,
        risk_per_trade=body.risk_per_trade,
        capital_units=body.capital_units,
        trades=body.trades,
        dd_limit_pct=body.dd_limit_pct,
        n_simulations=body.n_simulations,
        source="api",
    )


@router.get("/latent/risk_of_ruin/evaluations")
async def list_evaluations(
    strategy_hash: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List persisted RoR evaluations. Pure read."""
    rows = await ror_engine.list_evaluations(
        strategy_hash=strategy_hash, limit=limit,
    )
    return {
        "is_active":        bool(flag("ENABLE_RISK_OF_RUIN")),
        "weight_in_deploy": ror_engine.deploy_score_weight(),
        "evaluations":      rows,
        "count":            len(rows),
    }
