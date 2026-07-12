"""BI5 R1 · Diagnostics — Per-symbol BI5 Health surface.

Read-only aggregate over the extended ``bi5_ingest_log`` collection. The
returned shape feeds the operator-facing **MonitoringSuite → BI5 Health**
panel and is forward-compatible with Phase 13/14/15 consumption
(Evidence Score · Trust Score · Strategy Dossier · Automated Valuation
· Marketplace Quality Ranking).

Per-row schema (mirrors the extended ``bi5_ingest_log``):
    symbol                  str
    coverage_percent        float  (0–100)
    last_bi5_sync           ISO-8601 str
    last_gap_repair         ISO-8601 str | null
    ticks_stored            int
    status                  "ok" | "partial" | "manual_only" | "error" | "fetched-no-new"
    health_score_reserved   null today; computed by Phase 13/14 later
    latency_ms              int    (last cycle wall-clock)
    gaps_found              int    (last cycle)
    gaps_repaired           int    (last cycle)
    ingest_version          str
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from auth_utils import get_current_user
from engines.db import get_db
from engines.persistence_adapters.bi5_data_certification_store import (
    get_latest_data_certification,
)

router = APIRouter(prefix="/diag/bi5", tags=["diag-bi5"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def get_bi5_health(
    user: dict = Depends(get_current_user),
    limit: int = Query(200, ge=1, le=500),
) -> Dict[str, Any]:
    """Aggregate latest BI5 ingest row per symbol.

    Sorts by ``timestamp`` desc and groups by symbol to return the most
    recent cycle per symbol. Cheap query (one find + per-symbol dedupe
    in Python — collection size is bounded at ~7×24×30=~5k rows for
    the default 7-symbol universe at hourly cadence).
    """
    db = get_db()
    rows_by_symbol: Dict[str, Dict[str, Any]] = {}

    try:
        cursor = (
            db["bi5_ingest_log"]
            .find(
                {"source": "scheduler"},  # only scheduler summaries; per-file rows excluded
                {"_id": 0},
            )
            .sort("timestamp", -1)
            .limit(2000)
        )
        async for doc in cursor:
            sym = doc.get("symbol")
            if not sym or sym in rows_by_symbol:
                continue
            rows_by_symbol[sym] = doc
            if len(rows_by_symbol) >= limit:
                break
    except Exception as e:
        logger.exception("[diag/bi5/health] aggregation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"health_aggregate_failed: {e}")

    # Backfill missing symbols from the registry so the operator sees
    # every onboarded symbol even before its first cycle has landed.
    registry_symbols: List[str] = []
    try:
        from engines.market_universe_adapter import is_flag_on
        if is_flag_on():
            from engines import market_universe as MU
            reg_rows = await MU.list_symbols(enabled=True, limit=2000)
            for row in reg_rows:
                if (row or {}).get("eligibility", {}).get("ingestion_enabled"):
                    sym = row.get("symbol")
                    if sym:
                        registry_symbols.append(sym)
        else:
            from config.symbols import SYMBOL_CONFIG
            registry_symbols = list(SYMBOL_CONFIG.keys())
    except Exception:                                                # pragma: no cover
        from config.symbols import SYMBOL_CONFIG
        registry_symbols = list(SYMBOL_CONFIG.keys())

    rows: List[Dict[str, Any]] = []
    for sym in sorted(set(list(rows_by_symbol.keys()) + registry_symbols)):
        doc = rows_by_symbol.get(sym, {}) or {}
        # BI5 R2 / B-8 — per-symbol latest data-cert verdict join.
        # Single point lookup per symbol; the collection has at most one
        # row per (symbol, window) so this is cheap. Failures fall back
        # to None so a transient cert-store hiccup never breaks health.
        data_cert_verdict = None
        data_cert_score = None
        data_cert_window = None
        try:
            cert_doc = await get_latest_data_certification(db, symbol=sym)
            if cert_doc:
                data_cert_verdict = cert_doc.get("verdict")
                data_cert_score = float(cert_doc.get("bi5_score") or 0.0)
                ws = cert_doc.get("window_start_utc")
                we = cert_doc.get("window_end_utc")
                data_cert_window = {
                    "start_utc": ws.isoformat() if hasattr(ws, "isoformat") else ws,
                    "end_utc":   we.isoformat() if hasattr(we, "isoformat") else we,
                }
        except Exception:                                       # pragma: no cover
            pass
        rows.append({
            "symbol":               sym,
            "coverage_percent":     float(doc.get("coverage_percent") or 0.0),
            "last_bi5_sync":        doc.get("timestamp")  or doc.get("ingested_at"),
            "last_gap_repair":      doc.get("timestamp")  if (doc.get("gaps_repaired") or 0) > 0 else None,
            "ticks_stored":         int(doc.get("ticks_added") or doc.get("rows_added") or 0),
            "status":               (doc.get("status") or doc.get("state") or "unknown"),
            "gaps_found":           int(doc.get("gaps_found")    or 0),
            "gaps_repaired":        int(doc.get("gaps_repaired") or 0),
            "latency_ms":           int(doc.get("latency_ms")    or 0),
            "health_score_reserved":doc.get("health_score_reserved"),
            "ingest_version":       doc.get("ingest_version") or "n/a",
            "has_data":             bool(doc),
            # BI5 R2 / B-8 — per-symbol cert verdict surfaced inline.
            "data_cert_verdict":    data_cert_verdict,
            "data_cert_score":      data_cert_score,
            "data_cert_window":     data_cert_window,
        })

    # Roll-up counters for the UI strip.
    summary = {
        "symbols_tracked":    len(rows),
        "symbols_ok":         sum(1 for r in rows if r["status"] == "ok"),
        "symbols_error":      sum(1 for r in rows if r["status"] == "error"),
        "symbols_manual_only":sum(1 for r in rows if r["status"] == "manual_only"),
        "symbols_no_data":    sum(1 for r in rows if not r["has_data"]),
        "avg_coverage_pct":   round(
            (sum(r["coverage_percent"] for r in rows) / len(rows)) if rows else 0.0,
            2,
        ),
        "total_ticks_stored": sum(r["ticks_stored"] for r in rows),
        # BI5 R2 / B-8 — per-verdict roll-up across the symbols whose
        # latest data cert was joined above.
        "cert_pass":          sum(1 for r in rows if r.get("data_cert_verdict") == "PASS"),
        "cert_warn":          sum(1 for r in rows if r.get("data_cert_verdict") == "WARN"),
        "cert_fail":          sum(1 for r in rows if r.get("data_cert_verdict") == "FAIL"),
        "cert_absent":        sum(1 for r in rows if r.get("data_cert_verdict") is None),
    }

    return {
        "ok":                True,
        "summary":           summary,
        "rows":              rows,
        "ingest_version":    "r2-bi5-health-with-cert-v1",
        "schema_note":       (
            "health_score_reserved is null today; computed by Phase 13/14 once "
            "the Evidence Score + Trust Score engines land. R2 / B-8 adds "
            "per-symbol data_cert_verdict + data_cert_score join."
        ),
    }
