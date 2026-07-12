"""
Phase B.1 / B.2 — cBot parity sign-off API.

Read-only diagnostics + admin trigger. Mounted on /api/cbot-parity/*.
NEVER blocks export at this phase (B.2 is the SOFT advisory wiring);
that promotion to a hard gate is Phase B.5 with separate approval.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException

from auth_utils import require_admin
from engines import cbot_parity as cp

router = APIRouter(prefix="/cbot-parity", tags=["cbot-parity"])


@router.get("/{strategy_hash}")
async def get_parity(strategy_hash: str) -> Dict[str, Any]:
    """Return the latest parity sign-off doc for a strategy.

    Shape:
      { "exists": bool, "passed": bool, "signoff": {...} | null }
    """
    so = await cp.get_signoff(strategy_hash)
    return {
        "strategy_hash": strategy_hash,
        "exists": so is not None,
        "passed": cp.is_passed(so),
        "signoff": so,
        "phase": "B.1",
    }


@router.post("/{strategy_hash}/sign-off")
async def trigger_sign_off(
    strategy_hash: str,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    n_bars: int = 240,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """ADMIN-ONLY. Runs the parity simulator + transpiler against a
    recent market_data fixture and persists the outcome.

    Idempotent — re-running overwrites the prior sign-off doc and
    appends a new audit_log row.
    """
    if n_bars < 80 or n_bars > 2000:
        raise HTTPException(status_code=400, detail="n_bars must be in [80, 2000]")
    result = await cp.sign_off_parity(
        strategy_hash,
        pair_override=pair, timeframe_override=timeframe,
        n_bars=n_bars,
        triggered_by=f"admin:{admin.get('email', 'unknown')}",
    )
    return result


@router.get("")
async def list_signoffs(limit: int = 100) -> Dict[str, Any]:
    """Read-only — most recent N sign-off documents."""
    rows = await cp.list_signoffs(limit=limit)
    return {
        "count": len(rows),
        "signoffs": rows,
        "phase": "B.1",
    }
