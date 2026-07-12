"""
Pass 14 — Ingestion-health aggregator (read-only, advisory-only).

Status
------
* **Always callable**, **never engine-consumed**. No flag gate — this is
  a pure diagnostic surface, like ``/api/data/health``. There is no
  activation axis: the aggregator never changes any runtime behavior,
  so dormancy is not the right discipline here. The institutional
  guarantee is the *non-consumption* invariant: no module under
  ``backend/engines/`` imports this module, statically enforced by
  ``tests/test_ingestion_health_aggregate.py::test_no_engine_consumer``.
* Pure function of Mongo reads. NEVER writes. NEVER triggers ingestion.

Why this exists
---------------
The user brief (Pass 14): *"before VPS deployment, ingestion
trustworthiness is one of the highest operational risks remaining.
Silent ingestion degradation, stale market data, lagging pairs, or
failed ingestion cycles can poison mutation/validation quality,
orchestration decisions, execution realism, and parity certification
confidence."*

The existing surfaces are correct but fragmented:

  * ``/api/data/health`` — raw rows from ``market_data``.
  * ``/api/latent/ingestion-health`` — per-row data_coverage probe
    (flag-gated by ``ENABLE_INGEST_HEALTH_PROBE``, default OFF).
  * ``/api/auto-maintenance/status`` — single-runner status.

What is MISSING is a single aggregator that combines:

  1. per-(symbol, timeframe) freshness from ``data_coverage``
  2. ingestion-runner heartbeat (most recent ``DATA_INGESTED`` /
     ``DATA_MAINTENANCE_RUN`` audit event)
  3. multi-window degradation indicator (rows-per-hour for the
     last 24h vs the prior 24h)
  4. operator-readable verdict + rationale

…in one read-only, advisory-only call that the operator can wire
into a dashboard widget.

Verdict vocabulary
------------------
  * ``HEALTHY``   — every covered row healthy AND heartbeat fresh
  * ``LAGGING``   — at least one row stale but ingestion is alive
                    (heartbeat fresh)
  * ``DEGRADED``  — at least one row has gaps / incomplete coverage
                    (ingestion is producing but not at SLA)
  * ``STALE``     — heartbeat is aged (no recent ingestion events)
                    even if rows look OK
  * ``BLOCKED``   — at least one (symbol, tf) is producing zero rows
  * ``EMPTY``     — no coverage rows AND no audit events (fresh
                    install)
  * ``UNCERTAIN`` — Mongo unreachable or read failed

Determinism
-----------
``aggregate_ingestion_health(*, now=...)`` is a pure function of the
Mongo state at call-time + the supplied ``now`` (for reproducible
testing). The only non-determinism is the wall-clock used to compute
lag against bar timestamps — which is the institutional definition
of freshness.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Operator-tunable thresholds (env, optional)
# ─────────────────────────────────────────────────────────────────────
def _f(env: str, default: float) -> float:
    try:
        return float(os.environ.get(env, str(default)))
    except (TypeError, ValueError):
        return default


def _i(env: str, default: int) -> int:
    try:
        return int(os.environ.get(env, str(default)))
    except (TypeError, ValueError):
        return default


def thresholds() -> Dict[str, float]:
    """Operator-tunable thresholds (read each call so .env edits take
    effect after backend restart). Defaults align with the audit's
    ingestion SLA expectations from ``api/latent/ingestion_health.py``.
    """
    return {
        "healthy_max_lag_bars":       _f("INGEST_HEALTHY_MAX_LAG_BARS", 2.0),
        "healthy_min_completeness":   _f("INGEST_HEALTHY_MIN_COMPLETENESS", 0.95),
        "heartbeat_fresh_minutes":    _f("INGEST_HEARTBEAT_FRESH_MINUTES", 90.0),
        "heartbeat_stale_minutes":    _f("INGEST_HEARTBEAT_STALE_MINUTES", 360.0),
        "degradation_min_baseline":   _i("INGEST_DEGRADATION_MIN_BASELINE", 50),
    }


# Per-timeframe seconds — mirrors the table in
# ``api/latent/ingestion_health.py``. Keep in sync if either changes.
_TF_SECONDS: Dict[str, int] = {
    "m1": 60,    "1m":  60,   "M1":  60,
    "m5": 300,   "5m":  300,  "M5":  300,
    "m15": 900,  "15m": 900,  "M15": 900,
    "m30": 1800, "30m": 1800, "M30": 1800,
    "h1": 3600,  "1h":  3600, "H1":  3600,
    "h4": 14400, "4h":  14400, "H4": 14400,
    "d1": 86400, "1d":  86400, "D1": 86400,
}


def _parse_iso(raw: Any) -> Optional[datetime]:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        try:
            t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None
    return None


def _tf_secs(tf: Any) -> int:
    if not isinstance(tf, str):
        return 0
    return _TF_SECONDS.get(tf) or _TF_SECONDS.get(tf.lower()) or 0


# ─────────────────────────────────────────────────────────────────────
# Per-row classifier — pure
# ─────────────────────────────────────────────────────────────────────
def classify_row(
    *,
    rows: int,
    completeness: Optional[float],
    has_gaps: bool,
    lag_bars: Optional[float],
    th: Optional[Dict[str, float]] = None,
) -> str:
    """Pure classifier — returns the per-row band:
    ``healthy | stale | degraded | blocked``.
    """
    th = th or thresholds()
    if rows == 0 or (completeness is not None and completeness <= 0):
        return "blocked"
    if (
        (completeness is not None and completeness < th["healthy_min_completeness"])
        or has_gaps
    ):
        return "degraded"
    if lag_bars is not None and lag_bars > th["healthy_max_lag_bars"]:
        return "stale"
    return "healthy"


def classify_heartbeat(
    *,
    last_event_at: Optional[datetime],
    now: datetime,
    th: Optional[Dict[str, float]] = None,
) -> str:
    """Pure classifier — returns the heartbeat band:
    ``fresh | aged | stale | missing``.
    """
    th = th or thresholds()
    if last_event_at is None:
        return "missing"
    age_minutes = max(0.0, (now - last_event_at).total_seconds() / 60.0)
    if age_minutes <= th["heartbeat_fresh_minutes"]:
        return "fresh"
    if age_minutes <= th["heartbeat_stale_minutes"]:
        return "aged"
    return "stale"


# ─────────────────────────────────────────────────────────────────────
# Verdict synthesiser — pure
# ─────────────────────────────────────────────────────────────────────
def synthesise_verdict(
    *,
    per_band: Dict[str, int],
    heartbeat_band: str,
    coverage_row_count: int,
    audit_event_count: int,
) -> Dict[str, str]:
    """Pure function — combines the per-row band distribution and the
    heartbeat band into a single operator-readable verdict +
    rationale.

    Verdict priority (most severe wins):
       BLOCKED > DEGRADED > LAGGING > STALE > HEALTHY
       (EMPTY / UNCERTAIN are produced by the live wrapper, not here)
    """
    if per_band.get("blocked", 0) > 0:
        return {
            "verdict":   "BLOCKED",
            "rationale": (
                f"{per_band['blocked']} (symbol, timeframe) pair(s) "
                "are producing zero rows. Ingestion runner may be "
                "down or broker connectivity is broken."
            ),
        }
    if per_band.get("degraded", 0) > 0:
        return {
            "verdict":   "DEGRADED",
            "rationale": (
                f"{per_band['degraded']} row(s) have gaps or "
                "incomplete coverage. Ingestion is producing data "
                "but at least one row is below SLA."
            ),
        }
    if per_band.get("stale", 0) > 0:
        return {
            "verdict":   "LAGGING",
            "rationale": (
                f"{per_band['stale']} row(s) are stale (lag > "
                "healthy_max_lag_bars). Heartbeat is "
                f"{heartbeat_band}; data may catch up on next "
                "ingestion cycle."
            ),
        }
    if heartbeat_band == "stale":
        return {
            "verdict":   "STALE",
            "rationale": (
                "All covered rows look healthy BUT no ingestion "
                "events recorded recently. Confirm the ingestion "
                "runner is alive."
            ),
        }
    if coverage_row_count == 0 and audit_event_count == 0:
        return {
            "verdict":   "EMPTY",
            "rationale": (
                "No coverage rows and no ingestion events recorded. "
                "Fresh install or pre-ingestion. Run an ingestion "
                "cycle to populate."
            ),
        }
    return {
        "verdict":   "HEALTHY",
        "rationale": (
            f"All {coverage_row_count} covered row(s) healthy and "
            f"heartbeat {heartbeat_band}."
        ),
    }


# ─────────────────────────────────────────────────────────────────────
# Live aggregator
# ─────────────────────────────────────────────────────────────────────
async def aggregate_ingestion_health(
    *,
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    source: Optional[str] = None,
    coverage_limit: int = 2000,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Live one-shot aggregator.

    Reads (read-only):
      * ``data_coverage`` — for per-row freshness / completeness
      * ``audit_log`` — for ingestion-runner heartbeat events
      * ``market_data`` — for the multi-window degradation indicator
                          (rows per hour over the last 24h vs prior 24h)

    Always returns a structured payload. Never raises in production
    usage — read failures degrade to ``verdict="UNCERTAIN"`` with the
    underlying error captured in ``read_errors``.
    """
    now = now or datetime.now(timezone.utc)
    th = thresholds()
    out: Dict[str, Any] = {
        "endpoint":             "/api/latent/ingestion-aggregate",
        "evaluated_at":         now.isoformat(),
        "read_only":            True,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "thresholds":           th,
        "verdict":              "UNCERTAIN",
        "rationale":            None,
        "per_band":             {"healthy": 0, "stale": 0, "degraded": 0, "blocked": 0},
        "row_count":            0,
        "coverage_row_sample":  [],
        "stale_pairs":          [],
        "blocked_pairs":        [],
        "heartbeat": {
            "band":            "missing",
            "last_event_at":   None,
            "last_event_kind": None,
            "events_24h":      0,
        },
        "degradation": {
            "rows_last_24h":    0,
            "rows_prior_24h":   0,
            "delta_pct":        None,
            "indicator":        "n/a",
        },
        "read_errors":          [],
    }

    try:
        from engines.db import get_db
        db = get_db()
    except Exception as e:                                  # pragma: no cover
        out["read_errors"].append(f"db_unavailable: {str(e)[:200]}")
        out["rationale"] = "Database unreachable."
        return out

    # ── 1) data_coverage rows ───────────────────────────────────────
    q: Dict[str, Any] = {}
    if symbol:
        q["symbol"] = symbol.upper()
    if timeframe:
        q["timeframe"] = timeframe
    if source:
        q["source"] = source
    coverage_limit = max(1, min(int(coverage_limit), 5000))

    coverage_rows: List[Dict[str, Any]] = []
    try:
        cur = db.data_coverage.find(q, {"_id": 0}).sort(
            [("symbol", 1), ("timeframe", 1), ("source", 1)],
        ).limit(coverage_limit)
        coverage_rows = [d async for d in cur]
    except Exception as e:                                  # pragma: no cover
        out["read_errors"].append(f"data_coverage: {str(e)[:200]}")

    per_band = {"healthy": 0, "stale": 0, "degraded": 0, "blocked": 0}
    stale_pairs: List[Dict[str, Any]] = []
    blocked_pairs: List[Dict[str, Any]] = []
    coverage_sample: List[Dict[str, Any]] = []

    for row in coverage_rows:
        tf = row.get("timeframe") or ""
        tf_secs = _tf_secs(tf)
        end_date_dt = _parse_iso(row.get("end_date"))
        last_updated_dt = _parse_iso(row.get("last_updated"))
        if end_date_dt:
            lag_seconds = max(0.0, (now - end_date_dt).total_seconds())
        elif last_updated_dt:
            lag_seconds = max(0.0, (now - last_updated_dt).total_seconds())
        else:
            lag_seconds = None
        lag_bars = (lag_seconds / tf_secs) if (lag_seconds is not None and tf_secs > 0) else None
        comp_raw = row.get("completeness")
        completeness = float(comp_raw) if isinstance(comp_raw, (int, float)) else None
        has_gaps = bool(row.get("has_gaps"))
        rows_n = int(row.get("rows") or 0)

        band = classify_row(
            rows=rows_n, completeness=completeness,
            has_gaps=has_gaps, lag_bars=lag_bars, th=th,
        )
        per_band[band] += 1

        compact = {
            "symbol":       row.get("symbol"),
            "source":       row.get("source"),
            "timeframe":    tf,
            "rows":         rows_n,
            "completeness": completeness,
            "has_gaps":     has_gaps,
            "lag_bars":     round(lag_bars, 2) if lag_bars is not None else None,
            "lag_seconds":  round(lag_seconds, 1) if lag_seconds is not None else None,
            "end_date":     row.get("end_date"),
            "band":         band,
        }
        if band in ("blocked", "stale", "degraded"):
            # Surface the unhealthy rows in full.
            (blocked_pairs if band == "blocked" else stale_pairs).append(compact)
        if len(coverage_sample) < 25:
            # Keep a short sample of all rows for the operator's eyeball.
            coverage_sample.append(compact)

    # ── 2) Heartbeat (audit_log → DATA_INGESTED / DATA_MAINTENANCE_RUN) ──
    last_event_at: Optional[datetime] = None
    last_event_kind: Optional[str] = None
    events_24h = 0
    try:
        cutoff_24h_iso = (now - timedelta(hours=24)).isoformat()
        events_24h = await db.audit_log.count_documents({
            "event": {"$in": [
                "DATA_INGESTED",
                "DATA_MAINTENANCE_RUN",
                "MARKET_DATA_INGESTED",
            ]},
            "ts": {"$gte": cutoff_24h_iso},
        })
        cur = db.audit_log.find(
            {"event": {"$in": [
                "DATA_INGESTED",
                "DATA_MAINTENANCE_RUN",
                "MARKET_DATA_INGESTED",
            ]}},
            {"_id": 0, "event": 1, "ts": 1},
        ).sort("ts", -1).limit(1)
        async for d in cur:
            last_event_at = _parse_iso(d.get("ts"))
            last_event_kind = d.get("event")
    except Exception as e:                                  # pragma: no cover
        out["read_errors"].append(f"audit_log: {str(e)[:200]}")

    # Fallback proxy: most-recent data_coverage.last_updated.
    if last_event_at is None and coverage_rows:
        for row in coverage_rows:
            t = _parse_iso(row.get("last_updated"))
            if t and (last_event_at is None or t > last_event_at):
                last_event_at = t
                last_event_kind = "data_coverage.last_updated"

    heartbeat_band = classify_heartbeat(last_event_at=last_event_at, now=now, th=th)

    # ── 3) Multi-window degradation indicator ───────────────────────
    rows_last_24h = 0
    rows_prior_24h = 0
    delta_pct: Optional[float] = None
    indicator = "n/a"
    try:
        cutoff_now_iso = (now - timedelta(hours=24)).isoformat()
        cutoff_48h_iso = (now - timedelta(hours=48)).isoformat()
        rows_last_24h = await db.market_data.count_documents({
            "timestamp": {"$gte": cutoff_now_iso},
        })
        rows_prior_24h = await db.market_data.count_documents({
            "timestamp": {"$gte": cutoff_48h_iso, "$lt": cutoff_now_iso},
        })
        if rows_prior_24h >= th["degradation_min_baseline"]:
            delta_pct = round(
                (rows_last_24h - rows_prior_24h) / rows_prior_24h * 100.0,
                2,
            )
            if delta_pct >= -10.0:
                indicator = "stable"
            elif delta_pct >= -40.0:
                indicator = "degrading"
            else:
                indicator = "collapsing"
        else:
            indicator = "insufficient_baseline"
    except Exception as e:                                  # pragma: no cover
        out["read_errors"].append(f"market_data: {str(e)[:200]}")

    # ── 4) Verdict synthesis ────────────────────────────────────────
    if out["read_errors"]:
        out["verdict"] = "UNCERTAIN"
        out["rationale"] = "; ".join(out["read_errors"])
    else:
        synth = synthesise_verdict(
            per_band=per_band,
            heartbeat_band=heartbeat_band,
            coverage_row_count=len(coverage_rows),
            audit_event_count=events_24h,
        )
        out["verdict"] = synth["verdict"]
        out["rationale"] = synth["rationale"]

    out["per_band"] = per_band
    out["row_count"] = len(coverage_rows)
    out["coverage_row_sample"] = coverage_sample
    out["stale_pairs"] = stale_pairs[:50]
    out["blocked_pairs"] = blocked_pairs[:50]
    out["heartbeat"] = {
        "band":            heartbeat_band,
        "last_event_at":   last_event_at.isoformat() if last_event_at else None,
        "last_event_kind": last_event_kind,
        "events_24h":      events_24h,
    }
    out["degradation"] = {
        "rows_last_24h":  rows_last_24h,
        "rows_prior_24h": rows_prior_24h,
        "delta_pct":      delta_pct,
        "indicator":      indicator,
    }
    return out


__all__ = [
    "thresholds",
    "classify_row",
    "classify_heartbeat",
    "synthesise_verdict",
    "aggregate_ingestion_health",
]
