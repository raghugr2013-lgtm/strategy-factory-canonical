"""GET /api/latent/execution-realism-defaults — read-only registry view.

Auth-gated. Read-only. Lists the operator-decreed per-(pair,
broker_class) realism defaults plus the activation flag state.

This endpoint is the **safe operator inspection surface** for the P1.2
registry. It NEVER triggers a re-execution of any backtest or sign-off
— it merely echoes what's stored.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from auth_utils import get_current_user
from engines import execution_realism_defaults as erd

router = APIRouter()


@router.get("/latent/execution-realism-defaults")
async def list_execution_realism_defaults(
    pair: Optional[str] = Query(
        None,
        description="Optional pair filter (e.g. EURUSD). Case-insensitive.",
    ),
    broker_class: Optional[str] = Query(
        None,
        description=(
            "Optional broker-class filter (e.g. tier1_ecn, retail_stp). "
            "Case-insensitive."
        ),
    ),
    limit: int = Query(
        200, ge=1, le=500,
        description="Max rows returned (1-500).",
    ),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    rows = await erd.list_defaults(
        pair=pair, broker_class=broker_class, limit=limit,
    )
    total = await erd.count_defaults()
    return {
        "endpoint":             "/api/latent/execution-realism-defaults",
        "read_only":            True,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "flag_active":          erd.is_enabled(),
        "total_rows":           total,
        "returned":             len(rows),
        "rows":                 rows,
    }
