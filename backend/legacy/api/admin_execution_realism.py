"""POST/DELETE /api/admin/execution-realism-defaults — admin CRUD on P1.2 registry.

Admin-authenticated. Writes go to ``execution_realism_defaults`` Mongo
collection only — no engine consults the registry today.

This is the **operator decree** surface for P1.2: it captures realism
opinions ahead of the future P1.1 wiring that will substitute the
lookup result for ``execution_engine.DEFAULT_EXECUTION_CONFIG``.

Endpoints
---------
POST   /api/admin/execution-realism-defaults              — upsert
DELETE /api/admin/execution-realism-defaults              — delete

Discipline
----------
* Honest refusal on bad input (validated by
  ``execution_realism_defaults.upsert_defaults``).
* Operator email captured in ``updated_by``.
* No engine is consulted; no backtest re-run is triggered.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_utils import require_admin
from engines import execution_realism_defaults as erd

logger = logging.getLogger(__name__)
router = APIRouter()


class _UpsertPayload(BaseModel):
    pair:             str = Field(..., min_length=1, max_length=32)
    broker_class:     str = Field(..., min_length=1, max_length=64)
    spread_usd:       float = Field(..., ge=0.0, le=1000.0)
    max_slippage_usd: float = Field(..., ge=0.0, le=1000.0)
    commission_usd:   float = Field(..., ge=0.0, le=1000.0)
    notes:            Optional[str] = Field(None, max_length=1000)
    source:           Optional[str] = Field("operator", max_length=120)


@router.post("/admin/execution-realism-defaults")
async def upsert_execution_realism_defaults(
    payload: _UpsertPayload,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Upsert a per-(pair, broker_class) realism defaults row.

    Validation is delegated to ``engines.execution_realism_defaults``.
    Returns the stored document.
    """
    try:
        doc = await erd.upsert_defaults(
            pair=payload.pair,
            broker_class=payload.broker_class,
            spread_usd=float(payload.spread_usd),
            max_slippage_usd=float(payload.max_slippage_usd),
            commission_usd=float(payload.commission_usd),
            notes=payload.notes,
            source=payload.source or "operator",
            updated_by=(user.get("email") or user.get("sub") or "<unknown>"),
        )
    except ValueError as e:
        # Honest refusal — operator gave a malformed value.
        raise HTTPException(status_code=422, detail={
            "error":   "invalid_realism_payload",
            "message": str(e),
        })
    return {
        "stored":               doc,
        "read_only":            False,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "flag_active":          erd.is_enabled(),
        "engine_consultation":  False,
        "note": (
            "Registry write succeeded. No engine consults the registry "
            "today; future P1.1 wiring required for activation."
        ),
    }


@router.delete("/admin/execution-realism-defaults")
async def delete_execution_realism_defaults(
    pair: str,
    broker_class: str,
    _user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Remove a single realism defaults row.

    Returns ``{"deleted": true|false}``. Idempotent — deleting a
    non-existent row returns ``deleted=false`` (not an error).
    """
    deleted = await erd.delete_defaults(pair=pair, broker_class=broker_class)
    return {
        "deleted":   bool(deleted),
        "pair":      erd.normalize_pair(pair),
        "broker_class": erd.normalize_broker_class(broker_class),
    }
