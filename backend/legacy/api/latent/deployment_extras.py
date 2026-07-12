"""
Pass 15 — Read-only deployment-extras endpoint.

``GET /api/latent/deployment-extras`` — auth-gated, read-only,
advisory-only. Complements ``/api/latent/deployment-readiness``
(Pass 10) by surfacing the four dimensions the original endpoint
does not cover: disk / storage headroom, deployment packaging
artifact presence, recovery-tooling script presence, supervisor
service-template presence.

NEVER writes. NEVER triggers anything. The endpoint is purely a
file-system probe.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/latent/deployment-extras")
async def get_deployment_extras(
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    from engines.deployment_extras import collect_extras

    return {
        "endpoint": "/api/latent/deployment-extras",
        **collect_extras("/app"),
    }
