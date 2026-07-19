"""Phase 2 Stage 3.α — Knowledge Domain + Connector router.

Read-only foundation endpoints. Every route refuses with HTTP 503 when
`UKIE_DOMAIN_REGISTRY_ENABLED` is off — zero-cost dormant surface.

Endpoints:
  GET /api/knowledge/domains                — list all six domain specs
  GET /api/knowledge/domains/{domain}       — one domain spec
  GET /api/knowledge/connectors             — list registered connectors
  GET /api/knowledge/connectors/{name}      — one connector's metadata

No writes. No side effects. Pure read-through of the module-level
registries defined in `engines.knowledge.registry`.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from .connector import KnowledgeConnector
from .registry import (
    connectors_for_domain,
    get_connector,
    get_domain,
    get_domain_spec,
    list_connectors,
    list_domains,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _enabled() -> bool:
    return _flag("UKIE_DOMAIN_REGISTRY_ENABLED", False)


def _connector_to_dict(c: KnowledgeConnector) -> Dict[str, Any]:
    return {
        "name":                c.name,
        "source_type":         c.source_type,
        "supported_domains":   sorted(d.value for d in c.supported_domains),
        "default_trust_tier":  c.default_trust_tier,
        "supported_licenses":  sorted(c.supported_licenses),
        "capabilities":        c.capabilities.to_dict(),
        "rate_limit":          c.rate_limit().to_dict(),
    }


# ── Domain endpoints ─────────────────────────────────────────────────

@router.get("/domains")
async def get_domains() -> Dict[str, Any]:
    """Return all six canonical Knowledge Domain specs."""
    if not _enabled():
        raise HTTPException(status_code=503, detail="UKIE_DOMAIN_REGISTRY_ENABLED is off")
    specs = list_domains()
    return {
        "count":   len(specs),
        "domains": [s.to_dict() for s in specs],
    }


@router.get("/domains/{domain}")
async def get_domain_endpoint(domain: str) -> Dict[str, Any]:
    """Return one Knowledge Domain spec by name."""
    if not _enabled():
        raise HTTPException(status_code=503, detail="UKIE_DOMAIN_REGISTRY_ENABLED is off")
    try:
        d = get_domain(domain)
        spec = get_domain_spec(d)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown domain: {domain}")
    return spec.to_dict()


# ── Connector endpoints ──────────────────────────────────────────────

@router.get("/connectors")
async def get_connectors() -> Dict[str, Any]:
    """Return metadata for every registered connector."""
    if not _enabled():
        raise HTTPException(status_code=503, detail="UKIE_DOMAIN_REGISTRY_ENABLED is off")
    connectors = list_connectors()
    return {
        "count":      len(connectors),
        "connectors": [_connector_to_dict(c) for c in connectors],
    }


@router.get("/connectors/{name}")
async def get_connector_endpoint(name: str) -> Dict[str, Any]:
    """Return metadata for one connector by name."""
    if not _enabled():
        raise HTTPException(status_code=503, detail="UKIE_DOMAIN_REGISTRY_ENABLED is off")
    c = get_connector(name)
    if c is None:
        raise HTTPException(status_code=404, detail=f"unknown connector: {name}")
    return _connector_to_dict(c)


@router.get("/domains/{domain}/connectors")
async def get_connectors_for_domain(domain: str) -> Dict[str, Any]:
    """Return connectors that support a given domain."""
    if not _enabled():
        raise HTTPException(status_code=503, detail="UKIE_DOMAIN_REGISTRY_ENABLED is off")
    try:
        d = get_domain(domain)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown domain: {domain}")
    matches = connectors_for_domain(d)
    return {
        "domain":     d.value,
        "count":      len(matches),
        "connectors": [_connector_to_dict(c) for c in matches],
    }
