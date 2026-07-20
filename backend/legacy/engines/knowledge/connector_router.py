"""Phase 2 Stage 4 — Connector health router (P4A.0 + P4D.2).

Two admin-visible endpoints. Both gate on
`UKIE_CONNECTOR_FRAMEWORK_ENABLED` (the scaffold's master switch —
default OFF, HTTP 503 when off). Individual connector visibility is
additionally filtered by each connector's own flag.

  GET /api/knowledge/connectors/health           — aggregate snapshot
  GET /api/knowledge/connectors/{name}/health    — per-connector

Read-only. No mutation surface.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_framework_enabled() -> bool:
    return _flag("UKIE_CONNECTOR_FRAMEWORK_ENABLED", False)


def _snapshot_for(connector) -> Dict[str, Any]:
    """Best-effort snapshot: connectors inheriting from AbstractConnector
    expose `health_snapshot()`; legacy connectors get a minimal shape."""
    fn = getattr(connector, "health_snapshot", None)
    if callable(fn):
        try:
            return fn().to_dict()
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[connector_router] snapshot failed for %s: %s", connector.name, e)
    # Legacy fallback
    return {
        "name":               getattr(connector, "name", "unknown"),
        "state":              "unknown",
        "flag_name":          getattr(connector, "flag_name", ""),
        "flag_enabled":       True,   # legacy connectors have no flag
        "auth_configured":    True,
        "auth_mode":          "none",
        "supported_domains":  sorted(d.value for d in getattr(connector, "supported_domains", frozenset())),
        "default_trust_tier": int(getattr(connector, "default_trust_tier", 3)),
        "capabilities":       connector.capabilities.to_dict() if hasattr(connector.capabilities, "to_dict") else {},
        "rate_limit":         connector.rate_limit().to_dict() if callable(getattr(connector, "rate_limit", None)) else {},
        "legacy":             True,
    }


@router.get("/connectors/health")
async def get_connectors_health() -> Dict[str, Any]:
    """Aggregate per-connector health snapshots."""
    if not is_framework_enabled():
        raise HTTPException(status_code=503, detail="UKIE_CONNECTOR_FRAMEWORK_ENABLED is off")
    from .registry import list_connectors
    snaps: List[Dict[str, Any]] = []
    for c in list_connectors():
        snaps.append(_snapshot_for(c))
    return {"count": len(snaps), "connectors": snaps}


@router.get("/connectors/{name}/health")
async def get_connector_health(name: str) -> Dict[str, Any]:
    """Per-connector health snapshot."""
    if not is_framework_enabled():
        raise HTTPException(status_code=503, detail="UKIE_CONNECTOR_FRAMEWORK_ENABLED is off")
    from .registry import get_connector
    c = get_connector(name)
    if c is None:
        raise HTTPException(status_code=404, detail=f"unknown connector: {name}")
    return _snapshot_for(c)
