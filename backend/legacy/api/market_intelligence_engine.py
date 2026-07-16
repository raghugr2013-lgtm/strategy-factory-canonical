"""v1.2.0-alpha2 Phase G — /api/market-intelligence/* endpoints.

Read-only introspection + operator-triggered refresh. Every response
is JSON-safe. Admin gate on POST /refresh; user gate on GETs.

Endpoints:
  GET  /state?pair=…&timeframe=…&window=24h            latest MarketState
  GET  /state/history?pair=…&timeframe=…&window=…      historical states
  GET  /changes?pair=…&limit=50                        recent structural changes
  GET  /intelligence?pair=…&timeframe=…                latest MarketIntelligence
  POST /refresh?pair=…&timeframe=…                     manual refresh (admin)
  GET  /observers/config                               env-resolved knobs
  GET  /explain/{intelligence_id}                      full explainability chain
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Depends

from auth_utils import require_admin
from engines.market_intel_engine import (
    config as micfg,
    ledger,
    refresh_market_intelligence,
)

router = APIRouter(prefix="/market-intelligence", tags=["market-intelligence-engine"])


@router.get("/state")
async def get_state(
    pair: str = Query(..., min_length=1),
    timeframe: str = Query("H1"),
    window: str = Query("24h"),
) -> Dict[str, Any]:
    s = await ledger.read_latest_state(pair, timeframe, window)
    if s is None:
        return {"pair": pair, "timeframe": timeframe, "window": window,
                "state": None, "reason": "no_state_yet"}
    return {"pair": pair, "timeframe": timeframe, "window": window,
            "state": s.to_dict()}


@router.get("/state/history")
async def get_state_history(
    pair: str = Query(..., min_length=1),
    timeframe: str = Query("H1"),
    window: str = Query("24h"),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    hist = await ledger.read_state_history(pair, timeframe, window, limit=limit)
    return {"pair": pair, "timeframe": timeframe, "window": window,
            "count": len(hist),
            "states": [h.to_dict() for h in hist]}


@router.get("/changes")
async def get_changes(
    pair: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    ch = await ledger.read_recent_changes(pair, limit=limit)
    return {"count": len(ch), "changes": ch, "pair": pair}


@router.get("/intelligence")
async def get_intelligence(
    pair: str = Query(..., min_length=1),
    timeframe: str = Query("H1"),
) -> Dict[str, Any]:
    mi = await ledger.read_latest_intelligence(pair, timeframe)
    if mi is None:
        return {"pair": pair, "timeframe": timeframe,
                "intelligence": None, "reason": "no_intelligence_yet"}
    return {"pair": pair, "timeframe": timeframe,
            "intelligence": mi.to_dict()}


@router.post("/refresh", dependencies=[Depends(require_admin)])
async def post_refresh(
    pair: str = Query(..., min_length=1),
    timeframe: str = Query("H1"),
) -> Dict[str, Any]:
    """Manual idempotent refresh. Runs the aggregator, persists, and
    returns the freshly-computed MarketIntelligence."""
    mi = await refresh_market_intelligence(pair, timeframe)
    return {"pair": pair, "timeframe": timeframe,
            "intelligence": mi.to_dict(),
            "refreshed": True}


@router.get("/observers/config")
async def get_observers_config() -> Dict[str, Any]:
    """Introspection — every env-resolved knob currently active."""
    return {"config": micfg.config_snapshot()}


@router.get("/explain/{intelligence_id}")
async def get_explain(intelligence_id: str) -> Dict[str, Any]:
    """Full per-observer breakdown + linked structural_changes for a
    specific intelligence snapshot. Answers the "why did the brain
    increase this strategy?" question end-to-end."""
    doc = await ledger.read_intelligence_by_id(intelligence_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="intelligence_id not found")
    # Materialised active_structural_changes are already embedded, but
    # also fetch the latest 20 changes for the same pair for context.
    changes = await ledger.read_recent_changes(doc.get("pair"), limit=20)
    return {"intelligence": doc, "recent_changes": changes}
