"""GET /api/latent/feature-flags — flag introspection (read-only)."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import get_current_user
from engines import feature_flags as ff

router = APIRouter()


@router.get("/latent/feature-flags")
async def list_feature_flags(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return the full flag manifest with live values + dormancy state.

    Use this to verify which latent capabilities are activated for the
    current process. Pure read; safe to poll.
    """
    snapshot = ff.all_flags()
    active = ff.active_flags()
    return {
        "flag_count":         len(snapshot),
        "overridden_count":   len(active),
        "all_dormant":        not active,
        "active_overrides":   active,
        "flags":              snapshot,
        "scopes":             ff.scope_index(),
    }
