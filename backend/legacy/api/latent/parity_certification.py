"""
P1.5 — Dormant parity-certification diagnostic endpoint.

``GET /api/latent/parity-certification`` — auth-gated, read-only,
advisory-only. Aggregates ``cbot_parity_signoff`` rows over a recent
window, computes the would-be hard-gate pass-rate, and returns a
structured promotion-readiness verdict in
``{PROMOTABLE | NEEDS_MORE_EVIDENCE | NOT_READY | UNCERTIFIED}``.

NEVER writes. NEVER triggers a re-signoff. The endpoint is purely
the forensic surface the operator uses to make the P1.5 hard-gate
promotion decision evidence-based rather than judgement-based.

Discipline:
    * ``read_only=true``, ``advisory_only=true``,
      ``governance_authority=false``, ``operator_authority="final"``.
    * The endpoint reports the flag state at read-time but never
      flips any flag.
    * Honest-refusal verdicts (``UNCERTIFIED`` /
      ``NEEDS_MORE_EVIDENCE``) so the operator cannot be misled by
      an empty / under-soaked collection.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from auth_utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/latent/parity-certification")
async def get_parity_certification(
    window_days: int = Query(30, ge=1, le=365),
    require_trade_parity: Optional[bool] = Query(
        None,
        description=(
            "Override the hard-gate flag for the trade-parity dimension. "
            "When omitted, uses the current ENABLE_TRADE_PARITY_HARD_GATE "
            "flag state."
        ),
    ),
    require_htf_parity: Optional[bool] = Query(
        None,
        description=(
            "Override the hard-gate flag for the HTF-parity dimension. "
            "When omitted, uses the current ENABLE_HTF_PARITY_HARD_GATE "
            "flag state."
        ),
    ),
    min_samples: Optional[int] = Query(None, ge=1, le=10000),
    min_pass_rate: Optional[float] = Query(None, ge=0.0, le=1.0),
    limit: int = Query(5000, ge=1, le=50000),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    from engines.parity_certification import certify_window

    out = await certify_window(
        window_days=window_days,
        require_trade_parity=require_trade_parity,
        require_htf_parity=require_htf_parity,
        min_samples=min_samples,
        min_pass_rate=min_pass_rate,
        limit=limit,
    )
    return {
        "endpoint": "/api/latent/parity-certification",
        **out,
    }
