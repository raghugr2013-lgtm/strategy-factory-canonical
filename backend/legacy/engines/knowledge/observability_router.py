"""Phase 2 Stage 4 P4D — Observability router.

Endpoints (all self-guard 503 when their flag is off):

  # UKIE health provider — P4D.1
  # (composed into `/api/health/system` by the aggregator; also
  # exposed here for direct inspection). Uses a distinct
  # `/ukie/health` subpath to avoid a route collision with the
  # pre-existing Phase-1 KB probe at `/api/knowledge/health`
  # (see Phase 0 finding P0-F1). Both endpoints coexist; consumers
  # pick the one that matches their intent.
  GET  /api/knowledge/ukie/health

  # Knowledge metrics — P4D.3
  GET  /api/knowledge/metrics

  # Audit visibility — P4D.6
  GET  /api/knowledge/promote-events[?resolved=&refuse_reason=&limit=&offset=]
  GET  /api/knowledge/retro-score-runs[?dry_run=&limit=&offset=]
  GET  /api/knowledge/connector-events[?connector=&limit=&offset=]

Every endpoint is read-only. No writes.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from .constants import KNOWLEDGE_DB_NAME
from .health_provider import (
    get_ukie_health_provider,
    is_ukie_health_provider_enabled,
)
from .metrics import get_knowledge_metrics, is_metrics_enabled

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_audit_visibility_enabled() -> bool:
    return _flag("UKIE_AUDIT_VISIBILITY_ENABLED", False)


def _kb_db():
    try:                                                        # pragma: no cover
        from engines.db import get_db
        return get_db().client[KNOWLEDGE_DB_NAME]
    except Exception:                                           # pragma: no cover
        return None


# Injectable KB DB for tests
_KB_DB_OVERRIDE = None


def _set_kb_db_for_tests(getter):                              # pragma: no cover
    global _KB_DB_OVERRIDE
    _KB_DB_OVERRIDE = getter


def _get_kb_db():
    if _KB_DB_OVERRIDE is not None:
        return _KB_DB_OVERRIDE()
    return _kb_db()


# ── UKIE health ──────────────────────────────────────────────────────

@router.get("/ukie/health")
async def get_ukie_health() -> Dict[str, Any]:
    if not is_ukie_health_provider_enabled():
        raise HTTPException(status_code=503, detail="UKIE_HEALTH_PROVIDER_ENABLED is off")
    snap = await get_ukie_health_provider().snapshot()
    if snap is None:
        raise HTTPException(status_code=503, detail="ukie_health_provider_unavailable")
    return snap


# ── Metrics ──────────────────────────────────────────────────────────

@router.get("/metrics")
async def get_knowledge_metrics_endpoint() -> Dict[str, Any]:
    if not is_metrics_enabled():
        raise HTTPException(status_code=503, detail="UKIE_METRICS_ENABLED is off")
    return await get_knowledge_metrics().snapshot()


# ── Audit visibility ────────────────────────────────────────────────

async def _paged_list(
    collection: str,
    *,
    query: Dict[str, Any],
    limit: int,
    offset: int,
    sort_field: str = "at",
) -> Dict[str, Any]:
    db = _get_kb_db()
    if db is None:
        raise HTTPException(status_code=503, detail="kb_db_unavailable")
    try:
        cur = db[collection].find(query)
        # Attempt sort if the backend supports it
        try:
            cur = cur.sort(sort_field, -1)
        except Exception:                                       # noqa: BLE001
            pass
        try:
            cur = cur.skip(int(offset)).limit(int(limit))
        except Exception:                                       # noqa: BLE001
            pass
        rows = []
        async for r in cur:
            r.pop("_id", None)
            rows.append(r)
        return {"count": len(rows), "rows": rows}
    except Exception as e:                                     # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(e)[:120])


@router.get("/promote-events")
async def get_promote_events(
    resolved:       Optional[str] = Query(None),
    refuse_reason:  Optional[str] = Query(None),
    limit:          int = Query(100, ge=1, le=1000),
    offset:         int = Query(0, ge=0),
) -> Dict[str, Any]:
    if not is_audit_visibility_enabled():
        raise HTTPException(status_code=503, detail="UKIE_AUDIT_VISIBILITY_ENABLED is off")
    q: Dict[str, Any] = {}
    if resolved:      q["resolved"] = resolved
    if refuse_reason: q["refuse_reason"] = refuse_reason
    return await _paged_list("promote_events", query=q, limit=limit,
                              offset=offset, sort_field="attempted_at")


@router.get("/retro-score-runs")
async def get_retro_score_runs(
    dry_run: Optional[bool] = Query(None),
    limit:   int = Query(100, ge=1, le=1000),
    offset:  int = Query(0, ge=0),
) -> Dict[str, Any]:
    if not is_audit_visibility_enabled():
        raise HTTPException(status_code=503, detail="UKIE_AUDIT_VISIBILITY_ENABLED is off")
    q: Dict[str, Any] = {}
    if dry_run is not None:
        q["dry_run"] = bool(dry_run)
    return await _paged_list("retro_score_runs", query=q, limit=limit,
                              offset=offset, sort_field="started_at")


@router.get("/connector-events")
async def get_connector_events(
    connector: Optional[str] = Query(None),
    limit:     int = Query(100, ge=1, le=1000),
    offset:    int = Query(0, ge=0),
) -> Dict[str, Any]:
    if not is_audit_visibility_enabled():
        raise HTTPException(status_code=503, detail="UKIE_AUDIT_VISIBILITY_ENABLED is off")
    q: Dict[str, Any] = {}
    if connector:
        q["connector"] = connector
    return await _paged_list("connector_events", query=q, limit=limit,
                              offset=offset, sort_field="at")
