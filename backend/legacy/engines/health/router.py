"""Phase 2, Stage 1 — Universal Health Contract HTTP endpoints.

Mounted at `/api/health/*` conditional on `COE_HEALTH_CONTRACT_ENABLED`.
Zero-cost when disabled (endpoints simply not registered).

Endpoints:
  GET /api/health/system     — aggregated cross-subsystem snapshot
  GET /api/health/subsystems — list registered subsystem names
  GET /api/health/{subsystem} — one subsystem's HealthSnapshot
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from .providers import (
    all_provider_names,
    collect_all,
    get_provider,
    platform_health_score,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


def _flag_on(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def coe_health_contract_enabled() -> bool:
    return _flag_on("COE_HEALTH_CONTRACT_ENABLED", False)


@router.get("/system")
async def system_health() -> dict:
    """Aggregated snapshot: every registered subsystem + platform score."""
    if not coe_health_contract_enabled():
        raise HTTPException(status_code=503, detail="COE_HEALTH_CONTRACT_ENABLED is off")
    snaps = collect_all()
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "platform_health_score": platform_health_score(snaps),
        "subsystem_count": len(snaps),
        "subsystems": snaps,
    }

    # ── Phase 4 / Coherent UKIE Activation W2 — UKIE async block ──
    # The UKIE snapshot is async + Mongo-touching, so it cannot ride
    # the sync `collect_all()` path. We compose it separately here.
    # When `UKIE_HEALTH_PROVIDER_ENABLED=false` the provider returns
    # None and we OMIT the `ukie` key entirely — preserving response
    # shape for pre-Stage-4 consumers (see
    # engines/knowledge/health_provider.py docstring lines 11-13).
    try:
        from engines.knowledge.health_provider import (
            get_ukie_health_provider,
            is_ukie_health_provider_enabled,
        )
        if is_ukie_health_provider_enabled():
            ukie_block = await get_ukie_health_provider().snapshot()
            if ukie_block is not None:
                payload["ukie"] = ukie_block
    except Exception as e:                                     # noqa: BLE001
        logger.warning("[api/health/system] UKIE composition skipped: %s", e)

    return payload


@router.get("/subsystems")
async def subsystems_list() -> dict:
    """List of currently-registered subsystem provider names."""
    if not coe_health_contract_enabled():
        raise HTTPException(status_code=503, detail="COE_HEALTH_CONTRACT_ENABLED is off")
    return {"subsystems": all_provider_names()}


@router.get("/{subsystem}")
async def subsystem_health(subsystem: str) -> dict:
    """One subsystem's HealthSnapshot as dict."""
    if not coe_health_contract_enabled():
        raise HTTPException(status_code=503, detail="COE_HEALTH_CONTRACT_ENABLED is off")
    fn = get_provider(subsystem)
    if fn is None:
        raise HTTPException(status_code=404, detail=f"unknown subsystem: {subsystem}")
    try:
        snap = fn()
        return snap.to_dict()
    except Exception as e:  # noqa: BLE001
        logger.exception("[api/health] provider %s crashed", subsystem)
        raise HTTPException(status_code=500, detail=f"provider crashed: {str(e)[:200]}") from e
