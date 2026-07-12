"""
Pass 16 — Read-only factory-runner heartbeat endpoint.

``GET /api/latent/factory-runner-heartbeat`` — auth-gated, read-only,
advisory-only. Returns a structured freshness verdict for the most
recent ``factory_runner:heartbeat`` row in ``audit_log``.

This endpoint exists to surface the silent-failure mode identified
by the 2026-01 audit: ``deployment-readiness`` could previously
return ``ready`` even when no scheduler was running because the
sibling runner had never been started. The dedicated endpoint here
+ the additive heartbeat check inside
``deployment_readiness.py`` together close that loop.

NEVER writes. NEVER triggers anything. Pure aggregator over an
existing audit_log row.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/latent/factory-runner-heartbeat")
async def get_factory_runner_heartbeat(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    from engines.factory_runner_heartbeat import get_heartbeat_status

    payload = await get_heartbeat_status()
    return {
        "endpoint": "/api/latent/factory-runner-heartbeat",
        **payload,
    }
