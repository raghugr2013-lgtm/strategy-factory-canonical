"""Admin CRUD for the P1.6 dynamic market-universe registry.

Endpoints
---------
POST   /api/admin/market-universe                   — upsert symbol
DELETE /api/admin/market-universe                   — delete symbol
POST   /api/admin/market-universe/{symbol}/tier     — quick tier transition
POST   /api/admin/market-universe/{symbol}/enable   — toggle enabled

Discipline
----------
* Admin-authenticated (require_admin).
* Honest refusal via Pydantic + engine-layer ``_validate_payload``.
* Operator email captured in ``updated_by``.
* NO engine is consulted; no backtest re-run is triggered; no
  governance_universe is widened.
* All writes are advisory-only; ``governance_authority=false``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth_utils import require_admin
from engines import market_universe as MU

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Upsert
# ─────────────────────────────────────────────────────────────────────
class _UpsertPayload(BaseModel):
    symbol:                 str = Field(..., min_length=1, max_length=64)
    broker_class:           str = Field("unknown", min_length=1, max_length=64)
    display_name:           Optional[str] = Field(None, max_length=200)
    asset_class:            str = Field("other")
    tier:                   Optional[str] = Field(None)
    enabled:                bool = Field(True)
    priority:               int = Field(100, ge=0, le=1000)
    exploration_budget_pct: Optional[float] = Field(None, ge=0.0, le=100.0)
    compute_cost_hint:      str = Field("medium")
    pip_size:               float = Field(0.0, ge=0.0)
    volume_min:             float = Field(0.0, ge=0.0)
    volume_step:            float = Field(0.0, ge=0.0)
    min_data_bars:          int = Field(0, ge=0)
    aliases:                Optional[List[str]] = None
    tags:                   Optional[List[str]] = None
    notes:                  Optional[str] = Field(None, max_length=2000)
    source:                 Optional[str] = Field("operator", max_length=120)
    regime_gate:            Optional[Dict[str, Any]] = None
    # ─── R0 additions ────────────────────────────────────────────────
    broker_mapping:         Optional[Dict[str, Any]] = None
    precision:              Optional[Dict[str, Any]] = None
    spread_defaults:        Optional[Dict[str, Any]] = None
    cert_defaults:          Optional[Dict[str, Any]] = None
    calendar:               Optional[Dict[str, Any]] = None
    eligibility:            Optional[Dict[str, Any]] = None
    active_state:           Optional[str] = Field(None, max_length=64)
    # ─── DSR-1 additions ────────────────────────────────────────────
    execution_platforms:    Optional[List[str]] = None
    broker_compatibility:   Optional[Dict[str, Any]] = None   # reserved · Phase 14
    strategy_compatibility: Optional[Dict[str, Any]] = None   # reserved · Phase 13
    masterbot_compatibility:Optional[Dict[str, Any]] = None   # reserved · Phase 14
    marketplace_visibility: Optional[Dict[str, Any]] = None   # reserved · Phase 15
    propfirm_eligibility:   Optional[Dict[str, Any]] = None   # reserved · Phase 14


@router.post("/admin/market-universe")
async def upsert_market_universe_symbol(
    payload: _UpsertPayload,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        stored = await MU.upsert_symbol(
            symbol=payload.symbol,
            broker_class=payload.broker_class,
            display_name=payload.display_name,
            asset_class=payload.asset_class,
            tier=payload.tier,
            enabled=payload.enabled,
            priority=payload.priority,
            exploration_budget_pct=payload.exploration_budget_pct,
            compute_cost_hint=payload.compute_cost_hint,
            pip_size=payload.pip_size,
            volume_min=payload.volume_min,
            volume_step=payload.volume_step,
            min_data_bars=payload.min_data_bars,
            aliases=payload.aliases,
            tags=payload.tags,
            notes=payload.notes,
            source=payload.source or "operator",
            regime_gate=payload.regime_gate,
            updated_by=(user.get("email") or user.get("sub") or "<unknown>"),
            broker_mapping=payload.broker_mapping,
            precision=payload.precision,
            spread_defaults=payload.spread_defaults,
            cert_defaults=payload.cert_defaults,
            calendar=payload.calendar,
            eligibility=payload.eligibility,
            active_state=payload.active_state,
            # DSR-1 additions
            execution_platforms=payload.execution_platforms,
            broker_compatibility=payload.broker_compatibility,
            strategy_compatibility=payload.strategy_compatibility,
            masterbot_compatibility=payload.masterbot_compatibility,
            marketplace_visibility=payload.marketplace_visibility,
            propfirm_eligibility=payload.propfirm_eligibility,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail={
            "error":   "invalid_market_universe_payload",
            "message": str(e),
        })
    return {
        "stored":               stored,
        "read_only":            False,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "flag_active":          MU.is_enabled(),
        "engine_consultation":  False,
        "note": (
            "Registry write succeeded. No engine consults the registry "
            "today; future wiring required for activation across "
            "ingestion / mutation / explorer / replay / parity / "
            "execution-realism / orchestration."
        ),
    }


# ─────────────────────────────────────────────────────────────────────
# Delete
# ─────────────────────────────────────────────────────────────────────
@router.delete("/admin/market-universe")
async def delete_market_universe_symbol(
    symbol: str = Query(..., min_length=1, max_length=64),
    broker_class: str = Query("unknown", min_length=1, max_length=64),
    force: bool = Query(False, description="Force delete a seed row."),
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    res = await MU.delete_symbol(
        symbol=symbol, broker_class=broker_class, force=force,
        updated_by=(user.get("email") or user.get("sub") or "<unknown>"),
    )
    if not res.get("deleted") and res.get("reason") == "seed_row_protected_use_force":
        raise HTTPException(status_code=409, detail={
            "error":   "seed_row_protected",
            "message": (
                "This is an R0-seeded canonical row. Re-issue the request "
                "with ?force=true to delete (this is irreversible and will "
                "be audited)."
            ),
            "symbol":       MU.normalize_symbol(symbol),
            "broker_class": MU.normalize_broker_class(broker_class),
        })
    return {
        "deleted":       bool(res.get("deleted")),
        "was_seed":      bool(res.get("was_seed")),
        "reason":        res.get("reason"),
        "symbol":        MU.normalize_symbol(symbol),
        "broker_class":  MU.normalize_broker_class(broker_class),
    }


# ─────────────────────────────────────────────────────────────────────
# Quick lifecycle transitions
# ─────────────────────────────────────────────────────────────────────
class _TierPayload(BaseModel):
    tier:         Literal[
        "active", "candidate", "dormant", "experimental", "regime_activated",
    ]
    broker_class: str = Field("unknown", min_length=1, max_length=64)


@router.post("/admin/market-universe/{symbol}/tier")
async def set_market_universe_tier(
    symbol: str,
    payload: _TierPayload,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        row = await MU.set_tier(
            symbol=symbol, tier=payload.tier,
            broker_class=payload.broker_class,
            updated_by=(user.get("email") or user.get("sub") or "<unknown>"),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_tier", "message": str(e),
        })
    if row is None:
        raise HTTPException(status_code=404, detail={
            "error":   "symbol_not_registered",
            "symbol":  MU.normalize_symbol(symbol),
            "broker_class": MU.normalize_broker_class(payload.broker_class),
            "remediation": (
                "Upsert the symbol first via POST /api/admin/market-universe."
            ),
        })
    return {
        "updated":              row,
        "previous_tier":        None,  # we don't read-before-write to keep it atomic
        "advisory_only":        True,
        "governance_authority": False,
        "engine_consultation":  False,
    }


class _EnablePayload(BaseModel):
    enabled:      bool
    broker_class: str = Field("unknown", min_length=1, max_length=64)


@router.post("/admin/market-universe/{symbol}/enable")
async def set_market_universe_enabled(
    symbol: str,
    payload: _EnablePayload,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    row = await MU.set_enabled(
        symbol=symbol, enabled=payload.enabled,
        broker_class=payload.broker_class,
        updated_by=(user.get("email") or user.get("sub") or "<unknown>"),
    )
    if row is None:
        raise HTTPException(status_code=404, detail={
            "error":   "symbol_not_registered",
            "symbol":  MU.normalize_symbol(symbol),
            "broker_class": MU.normalize_broker_class(payload.broker_class),
        })
    return {
        "updated":              row,
        "advisory_only":        True,
        "governance_authority": False,
        "engine_consultation":  False,
    }


# ═════════════════════════════════════════════════════════════════════
# R0 — Additional endpoints
# ═════════════════════════════════════════════════════════════════════

@router.get("/admin/market-universe/{symbol}")
async def get_market_universe_symbol(
    symbol: str,
    broker_class: str = Query("dukascopy", min_length=1, max_length=64),
    _user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    row = await MU.get_symbol(symbol=symbol, broker_class=broker_class)
    if row is None:
        raise HTTPException(status_code=404, detail={
            "error":        "symbol_not_registered",
            "symbol":       MU.normalize_symbol(symbol),
            "broker_class": MU.normalize_broker_class(broker_class),
        })
    return {"row": row, "engine_consultation": False, "flag_active": MU.is_enabled()}


class _EligibilityPayload(BaseModel):
    eligibility:  Dict[str, bool] = Field(..., description="Subset of MU.ELIGIBILITY_KEYS")
    broker_class: str = Field("dukascopy", min_length=1, max_length=64)


@router.post("/admin/market-universe/{symbol}/eligibility")
async def set_market_universe_eligibility(
    symbol: str,
    payload: _EligibilityPayload,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    row = await MU.set_eligibility(
        symbol=symbol,
        eligibility_patch=payload.eligibility,
        broker_class=payload.broker_class,
        updated_by=(user.get("email") or user.get("sub") or "<unknown>"),
    )
    if row is None:
        raise HTTPException(status_code=404, detail={
            "error":        "symbol_not_registered",
            "symbol":       MU.normalize_symbol(symbol),
            "broker_class": MU.normalize_broker_class(payload.broker_class),
        })
    return {
        "updated":              row,
        "eligibility_keys":     list(MU.ELIGIBILITY_KEYS),
        "advisory_only":        True,
        "governance_authority": False,
        "engine_consultation":  False,
    }


class _CalendarPayload(BaseModel):
    calendar:     Dict[str, Any] = Field(..., description="Patch for calendar.*; keys: market_type, timezone")
    broker_class: str = Field("dukascopy", min_length=1, max_length=64)


@router.post("/admin/market-universe/{symbol}/calendar")
async def set_market_universe_calendar(
    symbol: str,
    payload: _CalendarPayload,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    try:
        row = await MU.set_calendar(
            symbol=symbol,
            calendar_patch=payload.calendar,
            broker_class=payload.broker_class,
            updated_by=(user.get("email") or user.get("sub") or "<unknown>"),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail={
            "error": "invalid_calendar_payload", "message": str(e),
        })
    if row is None:
        raise HTTPException(status_code=404, detail={
            "error":        "symbol_not_registered",
            "symbol":       MU.normalize_symbol(symbol),
            "broker_class": MU.normalize_broker_class(payload.broker_class),
        })
    return {
        "updated":              row,
        "advisory_only":        True,
        "governance_authority": False,
        "engine_consultation":  False,
    }


class _BulkImportPayload(BaseModel):
    rows: List[Dict[str, Any]] = Field(..., min_length=1, max_length=500)


@router.post("/admin/market-universe/bulk-import")
async def bulk_import_market_universe(
    payload: _BulkImportPayload,
    user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    result = await MU.bulk_import(
        rows=payload.rows,
        updated_by=(user.get("email") or user.get("sub") or "<unknown>"),
    )
    result["advisory_only"] = True
    result["governance_authority"] = False
    result["engine_consultation"] = False
    return result


@router.get("/admin/market-universe/audit/{symbol}")
async def list_market_universe_audit(
    symbol: str,
    broker_class: str = Query("dukascopy", min_length=1, max_length=64),
    limit: int = Query(200, ge=1, le=2000),
    _user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    rows = await MU.list_audit_for_symbol(
        symbol=symbol, broker_class=broker_class, limit=limit,
    )
    return {
        "symbol":        MU.normalize_symbol(symbol),
        "broker_class":  MU.normalize_broker_class(broker_class),
        "rows":          rows,
        "total_returned": len(rows),
        "ttl_days":      90,
    }


@router.get("/admin/market-universe/diff/{symbol}/{ts}")
async def diff_market_universe_audit(
    symbol: str,
    ts: str,
    broker_class: str = Query("dukascopy", min_length=1, max_length=64),
    _user: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Return the audit row for a symbol whose ``updated_at == ts``."""
    row = await MU.get_audit_at(symbol=symbol, ts_iso=ts, broker_class=broker_class)
    if row is None:
        raise HTTPException(status_code=404, detail={
            "error":        "audit_entry_not_found",
            "symbol":       MU.normalize_symbol(symbol),
            "broker_class": MU.normalize_broker_class(broker_class),
            "ts":           ts,
        })
    return {"audit": row}

