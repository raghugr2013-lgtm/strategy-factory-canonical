"""GET /api/latent/safe-to-widen — institutional widening advisor.

Strictly observational. Returns a deterministic SAFE / WARNING / BLOCKED
verdict for the next stage in the activation roadmap (S0–S9) plus the
advisory recommendations the operator should consider.

Discipline:
  * No writes anywhere.
  * No flag mutation, no scheduler interaction, no orchestration authority.
  * No automatic activation under any circumstance.
  * The payload always carries `advisory_only=true` and
    `operator_authority="final"` so callers cannot mistake the verdict
    for an authority surface.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import get_current_user
from engines import safe_to_widen

router = APIRouter()


@router.get("/latent/safe-to-widen")
async def get_safe_to_widen(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the institutional widening advisor payload.

    Shape documented on `engines.safe_to_widen.evaluate()`. The
    operator remains the only entity that may flip a flag.
    """
    return await safe_to_widen.evaluate()
