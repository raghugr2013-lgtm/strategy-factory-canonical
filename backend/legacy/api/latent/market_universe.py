"""GET /api/latent/market-universe — read-only registry view.

Auth-gated. Returns the per-symbol registry plus tier summary and
activation flag state. NEVER writes. ``advisory_only=true``.

Use this to inspect what operators have registered before deciding
which symbols to promote to ``active`` tier.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from auth_utils import get_current_user
from engines import market_universe as MU

router = APIRouter()


@router.get("/latent/market-universe")
async def list_market_universe(
    tier: Optional[str] = Query(
        None, description=f"Filter by tier (one of: {', '.join(MU.VALID_TIERS)})",
    ),
    asset_class: Optional[str] = Query(
        None,
        description=f"Filter by asset class ({', '.join(MU.VALID_ASSET_CLASSES)}).",
    ),
    broker_class: Optional[str] = Query(
        None, description="Filter by broker class (e.g. dukascopy, tier1_ecn).",
    ),
    enabled: Optional[bool] = Query(
        None, description="Filter by enabled flag.",
    ),
    limit: int = Query(500, ge=1, le=2000),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    rows = await MU.list_symbols(
        tier=tier, asset_class=asset_class,
        broker_class=broker_class, enabled=enabled, limit=limit,
    )
    summary = await MU.count_by_tier()
    return {
        "endpoint":             "/api/latent/market-universe",
        "read_only":            True,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "flag_active":          MU.is_enabled(),
        "default_tier":         MU.default_tier(),
        "tiers":                list(MU.VALID_TIERS),
        "asset_classes":        list(MU.VALID_ASSET_CLASSES),
        "compute_hints":        list(MU.VALID_COMPUTE_HINTS),
        "execution_platforms":  list(MU.VALID_EXECUTION_PLATFORMS),  # DSR-1
        "eligibility_keys":     list(MU.ELIGIBILITY_KEYS),            # DSR-1
        "tier_summary":         summary,
        "total_returned":       len(rows),
        "rows":                 rows,
    }


@router.get("/latent/market-universe/{symbol}")
async def get_market_universe_symbol(
    symbol: str,
    broker_class: str = Query("unknown"),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Resolve a single symbol (matches by canonical name or alias)."""
    row = await MU.get_symbol(symbol, broker_class)
    return {
        "endpoint":             "/api/latent/market-universe/{symbol}",
        "read_only":            True,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "flag_active":          MU.is_enabled(),
        "query_symbol":         MU.normalize_symbol(symbol),
        "broker_class":         MU.normalize_broker_class(broker_class),
        "found":                row is not None,
        "row":                  row,
    }
