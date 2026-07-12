"""
Pass 14 — Read-only ingestion-health aggregate endpoint.

``GET /api/latent/ingestion-aggregate`` — auth-gated, read-only,
advisory-only. Single consolidated view over:

  * ``data_coverage`` per-row freshness / completeness / lag
  * ``audit_log`` ingestion-runner heartbeat
  * ``market_data`` 24h × prior-24h degradation indicator

Returns a structured payload with verdict in
``{HEALTHY | LAGGING | DEGRADED | STALE | BLOCKED | EMPTY | UNCERTAIN}``
+ operator-readable rationale + per-band counts + a sample of
unhealthy rows.

NEVER writes. NEVER triggers ingestion. Always returns a structured
payload (even on read errors — verdict degrades to ``UNCERTAIN``
with ``read_errors`` populated). Auth-gated; no flag gate — the
aggregator is purely diagnostic and is never consumed by any engine
(statically enforced by
``tests/test_ingestion_health_aggregate.py::test_no_engine_consumer``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from auth_utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/latent/ingestion-aggregate")
async def get_ingestion_aggregate(
    symbol: Optional[str] = Query(None, description="Optional symbol filter."),
    timeframe: Optional[str] = Query(None, description="Optional timeframe filter."),
    source: Optional[str] = Query(None, description="Optional source filter."),
    coverage_limit: int = Query(2000, ge=1, le=5000),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    from engines.ingestion_health_aggregate import aggregate_ingestion_health

    return await aggregate_ingestion_health(
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        coverage_limit=coverage_limit,
    )
