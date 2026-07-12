"""GET /api/latent/ingestion-health — read-only ingestion reliability diagnostic.

Auth-gated. Read-only. Pure inspection — never writes, never triggers a
backfill. Dormant-flag-gated by ``ENABLE_INGEST_HEALTH_PROBE``: when the
flag is OFF (the institutional default), the endpoint refuses with a
structured ``status="probe_disabled"`` payload so the operator can
verify the gate before relying on the output.

What it surfaces
----------------
Per-row health for every entry in the ``data_coverage`` collection:

  * ``symbol``, ``source``, ``timeframe``
  * ``last_updated`` (ISO)
  * ``lag_seconds`` — how stale the most-recent ingested bar is
    (computed against UTC ``now``)
  * ``lag_bars`` — lag normalised by timeframe (so an H1 row 3 hours
    stale reads ``lag_bars=3``)
  * ``completeness`` (0..1)
  * ``has_gaps`` (bool)
  * ``rows``, ``expected_rows``, ``backfill_progress_pct``
  * ``health`` — per-row band: ``healthy`` | ``stale`` | ``degraded``
    | ``blocked``

Plus an aggregate ``status`` verdict (``healthy`` | ``degraded`` |
``blocked``) and per-band counters for ops dashboards.

Bands (operator-tunable via the flag scope; defaults aligned with
audit doc §1.3 ingestion SLA expectations):

  * ``healthy``   — lag_bars ≤ 2, completeness ≥ 0.95, no gaps
  * ``stale``     — lag_bars > 2 (rows present but not fresh)
  * ``degraded``  — completeness < 0.95 OR has_gaps
  * ``blocked``   — rows == 0 OR completeness == 0

NEVER writes. NEVER triggers ingestion. The endpoint is purely a
diagnostic surface for the VPS operator to confirm ingestion is
actually keeping up — a precondition for any aggressive autonomous
research widening.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from auth_utils import get_current_user
from engines.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# Activation gate (dormant-default)
# ─────────────────────────────────────────────────────────────────────
def _probe_enabled() -> bool:
    raw = os.environ.get("ENABLE_INGEST_HEALTH_PROBE", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


# ─── Per-timeframe seconds (canonical + DB-native names) ────────────
# Operator-readable lag computation. Keep this table aligned with
# engines.timeframe_canon.TIMEFRAME_MAP.
_TF_SECONDS: Dict[str, int] = {
    "m1": 60,    "1m":  60,   "M1":  60,
    "m5": 300,   "5m":  300,  "M5":  300,
    "m15": 900,  "15m": 900,  "M15": 900,
    "m30": 1800, "30m": 1800, "M30": 1800,
    "h1": 3600,  "1h":  3600, "H1":  3600,
    "h4": 14400, "4h":  14400, "H4": 14400,
    "d1": 86400, "1d":  86400, "D1": 86400,
}

# Health-band thresholds. Operator-tunable via env if needed, but
# defaults match the audit's ingestion SLA expectations.
_HEALTHY_MAX_LAG_BARS = float(os.environ.get("INGEST_HEALTHY_MAX_LAG_BARS", "2.0"))
_HEALTHY_MIN_COMPLETENESS = float(os.environ.get("INGEST_HEALTHY_MIN_COMPLETENESS", "0.95"))


def _parse_iso(raw: Optional[str]) -> Optional[datetime]:
    if not raw or not isinstance(raw, str):
        return None
    try:
        # The collection writes ISO-8601 with timezone; tolerate the
        # Mongo serialised variants we've actually seen.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _classify_row(*, lag_bars: Optional[float], completeness: Optional[float],
                  has_gaps: bool, rows: int) -> str:
    if rows == 0 or (completeness is not None and completeness <= 0):
        return "blocked"
    if (completeness is not None and completeness < _HEALTHY_MIN_COMPLETENESS) or has_gaps:
        return "degraded"
    if lag_bars is not None and lag_bars > _HEALTHY_MAX_LAG_BARS:
        return "stale"
    return "healthy"


def _aggregate_status(per_band: Dict[str, int]) -> str:
    if per_band.get("blocked", 0) > 0:
        return "blocked"
    if per_band.get("degraded", 0) > 0 or per_band.get("stale", 0) > 0:
        return "degraded"
    return "healthy"


@router.get("/latent/ingestion-health")
async def get_ingestion_health(
    symbol: Optional[str] = Query(None, description="Optional symbol filter."),
    timeframe: Optional[str] = Query(None, description="Optional timeframe filter."),
    source: Optional[str] = Query(None, description="Optional source filter."),
    limit: int = Query(500, ge=1, le=2000),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "endpoint":             "/api/latent/ingestion-health",
        "read_only":            True,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "flag_active":          _probe_enabled(),
    }

    # ─── Dormant-default refusal ────────────────────────────────────
    if not _probe_enabled():
        return {
            **base,
            "status":   "probe_disabled",
            "summary": (
                "Ingestion-health probe is dormant by default. Set "
                "ENABLE_INGEST_HEALTH_PROBE=true in backend/.env and "
                "restart the backend to activate."
            ),
            "rows":      [],
            "per_band":  {},
            "thresholds": {
                "healthy_max_lag_bars":     _HEALTHY_MAX_LAG_BARS,
                "healthy_min_completeness": _HEALTHY_MIN_COMPLETENESS,
            },
        }

    # ─── Read data_coverage ─────────────────────────────────────────
    db = get_db()
    q: Dict[str, Any] = {}
    if symbol:    q["symbol"]    = symbol.upper()
    if timeframe: q["timeframe"] = timeframe
    if source:    q["source"]    = source
    limit = max(1, min(int(limit), 2000))

    try:
        cur = db.data_coverage.find(q, {"_id": 0}).sort(
            [("symbol", 1), ("timeframe", 1), ("source", 1)],
        ).limit(limit)
        coverage = [d async for d in cur]
    except Exception as e:                                  # pragma: no cover
        logger.warning("[ingestion_health] data_coverage read failed: %s", e)
        return {**base, "status": "blocked",
                "summary": f"data_coverage read failed: {str(e)[:300]}",
                "rows": [], "per_band": {}}

    now = datetime.now(timezone.utc)
    rows_out: List[Dict[str, Any]] = []
    per_band: Dict[str, int] = {"healthy": 0, "stale": 0, "degraded": 0, "blocked": 0}

    for row in coverage:
        tf = row.get("timeframe") or ""
        tf_secs = _TF_SECONDS.get(tf, _TF_SECONDS.get(tf.lower(), 0))
        last_updated_dt = _parse_iso(row.get("last_updated"))
        end_date_dt = _parse_iso(row.get("end_date"))

        # Lag against ``end_date`` (the most-recent bar timestamp), not
        # against ``last_updated`` (which is when the ingestion runner
        # last wrote — could be stale while bars are still fresh).
        if end_date_dt:
            lag_seconds = max(0.0, (now - end_date_dt).total_seconds())
        elif last_updated_dt:
            lag_seconds = max(0.0, (now - last_updated_dt).total_seconds())
        else:
            lag_seconds = None
        lag_bars = (lag_seconds / tf_secs) if (lag_seconds is not None and tf_secs > 0) else None

        completeness = row.get("completeness")
        if isinstance(completeness, (int, float)):
            completeness = float(completeness)
        else:
            completeness = None

        has_gaps = bool(row.get("has_gaps"))
        rows_n = int(row.get("rows") or 0)

        health = _classify_row(
            lag_bars=lag_bars, completeness=completeness,
            has_gaps=has_gaps, rows=rows_n,
        )
        per_band[health] += 1

        rows_out.append({
            "symbol":                 row.get("symbol"),
            "source":                 row.get("source"),
            "timeframe":              tf,
            "last_updated":           row.get("last_updated"),
            "end_date":               row.get("end_date"),
            "lag_seconds":            round(lag_seconds, 1) if lag_seconds is not None else None,
            "lag_bars":               round(lag_bars, 2) if lag_bars is not None else None,
            "completeness":           completeness,
            "has_gaps":               has_gaps,
            "rows":                   rows_n,
            "expected_rows":          row.get("expected_rows"),
            "backfill_progress_pct":  row.get("backfill_progress_pct"),
            "health":                 health,
        })

    status = _aggregate_status(per_band) if rows_out else "blocked"
    summary = {
        "healthy":  "All ingestion rows healthy.",
        "degraded": (
            f"{per_band['stale']} stale, {per_band['degraded']} degraded — "
            "ingestion is producing data but at least one row is not at SLA."
        ),
        "blocked":  (
            f"{per_band['blocked']} row(s) blocked — "
            "ingestion not producing any data for at least one "
            "(symbol, source, timeframe). Confirm the ingestion runner "
            "is alive and broker connectivity is healthy."
        ),
    }.get(status, "Indeterminate status.")

    return {
        **base,
        "status":     status,
        "summary":    summary,
        "thresholds": {
            "healthy_max_lag_bars":     _HEALTHY_MAX_LAG_BARS,
            "healthy_min_completeness": _HEALTHY_MIN_COMPLETENESS,
        },
        "per_band":   per_band,
        "total_rows": len(rows_out),
        "rows":       rows_out,
    }
