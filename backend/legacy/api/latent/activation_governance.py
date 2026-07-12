"""GET /api/latent/activation-governance — unified dormant-vs-active snapshot.

Read-only, auth-gated, observational. Aggregates every governance-relevant
subsystem so the operator can answer "is the system safe to widen?" from
one read.

Discipline:
  * No writes.
  * No flag mutation.
  * No scheduler interaction.
  * Best-effort per subsystem — one failure cannot mask the others.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import get_current_user
from engines import activation_governance

router = APIRouter()


@router.get("/latent/activation-governance")
async def get_activation_governance(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the unified activation-governance snapshot.

    Always reachable while the backend is healthy; never raises.
    """
    return await activation_governance.collect()
