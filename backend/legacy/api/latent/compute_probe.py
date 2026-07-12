"""GET /api/latent/compute-probe — host compute snapshot (read-only).

Auth-gated. Returns a single `compute_probe.snapshot()` plus the
derived headroom summary. Pure observation — never mutates anything.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import get_current_user
from engines import compute_probe

router = APIRouter()


@router.get("/latent/compute-probe")
async def get_compute_probe(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    snap = compute_probe.snapshot()
    return {
        "available": compute_probe.is_available(),
        "snapshot":  snap,
        "headroom":  compute_probe.headroom_summary(snap),
    }
