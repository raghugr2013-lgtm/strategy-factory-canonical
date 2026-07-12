"""
System Readiness Check API (Admin-only).

Thin HTTP surface over `engines.readiness_engine.compute_readiness`.
Read-only. Never mutates any collection. Safe to poll.

Endpoint:
  GET /api/admin/readiness   (admin role required)
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import require_admin
from engines.readiness_engine import compute_readiness

router = APIRouter(prefix="/admin", tags=["admin-readiness"])


@router.get("/readiness")
async def readiness_check(admin: Dict[str, Any] = Depends(require_admin)) -> Dict[str, Any]:
    return await compute_readiness()
