"""/api/latent/calibration — diagnostic surface for confidence calibration."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth_utils import get_current_user
from engines import calibration_framework as cf

router = APIRouter()


class PredictionRequest(BaseModel):
    strategy_hash: str = Field(..., min_length=1)
    predicted_pp: float = Field(..., ge=0.0, le=1.0)
    predicted_pp_ci: Optional[List[float]] = Field(
        None, min_length=2, max_length=2,
    )
    source: str = Field("manual", min_length=1)
    metadata: Optional[Dict[str, Any]] = None


class OutcomeRequest(BaseModel):
    strategy_hash: str = Field(..., min_length=1)
    realized_outcome: str = Field(
        ..., pattern="^(pass|fail|in_progress)$",
    )
    source: str = Field("manual_admin", min_length=1)


@router.post("/latent/calibration/predictions")
async def record_prediction(
    body: PredictionRequest,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Persist a (strategy → predicted_pp) row as `in_progress`.
    Subsequent `/outcomes` calls resolve it. Always-on (write-only)."""
    return await cf.record_prediction(
        strategy_hash=body.strategy_hash,
        predicted_pp=body.predicted_pp,
        predicted_pp_ci=body.predicted_pp_ci,
        source=body.source,
        metadata=body.metadata,
    )


@router.post("/latent/calibration/outcomes")
async def record_outcome(
    body: OutcomeRequest,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Resolve the latest in_progress prediction for `strategy_hash`."""
    return await cf.record_outcome(
        strategy_hash=body.strategy_hash,
        realized_outcome=body.realized_outcome,
        source=body.source,
    )


@router.post("/latent/calibration/build-table")
async def build_table(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Rebuild + persist the calibration table from current outcomes.
    The table is identity-safe — sparse bins return raw."""
    return await cf.build_calibration_table(save=True)


@router.get("/latent/calibration/status")
async def status(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Current calibration framework health snapshot."""
    return await cf.diagnostics()
