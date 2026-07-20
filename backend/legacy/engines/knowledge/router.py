"""Phase 2 Stage 3.α / 3.β — Knowledge Domain + Connector + Pipeline router.

Read-only foundation endpoints (Stage 3.α) + dry-run / pipeline
diagnostic endpoints (Stage 3.β). Every route refuses with HTTP 503
when `UKIE_DOMAIN_REGISTRY_ENABLED` is off — zero-cost dormant surface.

Stage 3.α endpoints:
  GET  /api/knowledge/domains                — list all six domain specs
  GET  /api/knowledge/domains/{domain}       — one domain spec
  GET  /api/knowledge/connectors             — list registered connectors
  GET  /api/knowledge/connectors/{name}      — one connector's metadata
  GET  /api/knowledge/domains/{domain}/connectors

Stage 3.β endpoints:
  GET  /api/knowledge/pipeline/status        — enabled stages + versions
  GET  /api/knowledge/pipeline/last-run      — most recent pipeline summary
  POST /api/knowledge/dry-run                — run harness in shadow mode

No writes to production `strategies`. No side effects on Mongo except
the dry-run harness reading from `ingestion_runs` when explicitly
requested (`last_n_from_ingestion_runs > 0`).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException

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


# ── Stage 3.β — Pipeline diagnostics + dry-run ────────────────────────

@router.get("/pipeline/status")
async def get_pipeline_status() -> Dict[str, Any]:
    """Snapshot of enabled stages + pipeline version stamps."""
    if not _enabled():
        raise HTTPException(status_code=503, detail="UKIE_DOMAIN_REGISTRY_ENABLED is off")
    from .pipeline import pipeline_status
    return pipeline_status()


@router.get("/pipeline/last-run")
async def get_pipeline_last_run() -> Dict[str, Any]:
    """Return the most recent pipeline summary — dry-run or live.

    Returns `{"status": "none"}` when no run has completed in this
    process lifetime.
    """
    if not _enabled():
        raise HTTPException(status_code=503, detail="UKIE_DOMAIN_REGISTRY_ENABLED is off")
    from .pipeline import get_last_summary
    s = get_last_summary()
    if s is None:
        return {"status": "none"}
    return s.to_dict()


@router.post("/dry-run")
async def post_dry_run(payload: Optional[Dict[str, Any]] = Body(default=None)) -> Dict[str, Any]:
    """Run the UKIE pipeline in shadow mode.

    Request body (all optional):
        {
          "items":                       [ RawKnowledgeItem dict, ... ],
          "last_n_from_ingestion_runs":  10,
          "synthetic_fixture":           "stage_3_beta_default"
        }

    Response is the `PipelineSummary` shape defined in
    `engines.knowledge.pipeline`.
    """
    if not _enabled():
        raise HTTPException(status_code=503, detail="UKIE_DOMAIN_REGISTRY_ENABLED is off")
    body = payload or {}
    items          = body.get("items") if isinstance(body.get("items"), list) else None
    last_n         = int(body.get("last_n_from_ingestion_runs") or 0)
    fixture_name   = body.get("synthetic_fixture")
    # Default: run the built-in fixture if no explicit corpus provided
    if not items and last_n <= 0 and not fixture_name:
        fixture_name = "stage_3_beta_default"

    from .dry_run import run_dry
    summary = await run_dry(
        items=items,
        last_n_from_ingestion_runs=last_n,
        synthetic_fixture_name=fixture_name,
    )
    return summary.to_dict()


# ── Stage 3.γ — Promote Bridge (P2C.9) + Retro-scoring (P2C.11) ──────
#
# The sub-routers implement their own flag gates
# (`UKIE_PROMOTE_BRIDGE_ENABLED`, `UKIE_RETRO_SCORE_ENABLED`) and
# refuse with HTTP 503 when off. We mount them on the same prefix so
# every `/api/knowledge/*` route lives on one FastAPI router.

from .promote_router import router as _promote_router            # noqa: E402
from .retro_score_router import router as _retro_score_router    # noqa: E402
from .connector_router import router as _connector_router        # noqa: E402
from .ukie_gamma_router import router as _ukie_gamma_router      # noqa: E402
from .observability_router import router as _observability_router  # noqa: E402

# Connector-health routes must be registered BEFORE the Stage-3.α
# `/connectors/{name}` catch-all — otherwise `{name}="health"` wins
# and the request routes to the Stage-3.α gate (which returns 503
# unless `UKIE_DOMAIN_REGISTRY_ENABLED` is on). Insert at front.
for _r in reversed(_connector_router.routes):
    router.routes.insert(0, _r)
for _r in _promote_router.routes:
    router.routes.append(_r)
for _r in _retro_score_router.routes:
    router.routes.append(_r)
for _r in _ukie_gamma_router.routes:
    router.routes.append(_r)
for _r in _observability_router.routes:
    router.routes.append(_r)
