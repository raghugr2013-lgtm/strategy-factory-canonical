"""P0B Phase 2 — `bi5_data_certification` persistence adapter.

Persists `engines.tick_validator.BI5ScoreReport` documents — i.e. the
per-(symbol, window) BI5 **data-feed** quality certification — into
the `bi5_data_certification` collection with an idempotent upsert
keyed by `(symbol, window_start_utc, window_end_utc)`.

This is **the data-feed prerequisite** for strategy certification.
The strategy-level `bi5_certification` collection is owned by the
Phase 3 orchestrator and is intentionally NOT created here (avoids
architectural leakage between persistence and orchestration).

Read helpers expose the queries the BI5 orchestrator (Phase 3) and the
admin / alerting endpoints will use:

    * get_latest_data_certification(symbol)
    * find_data_certs_by_verdict(verdict, *, limit, since_dt=None)

BID/BI5 firewall: this module imports only `pymongo`,
`engines.tick_validator` (Phase 1 dataclass), and stdlib.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from pymongo import DESCENDING

from engines.tick_validator import BI5ScoreReport, DEFAULT_WEIGHTS


BI5_DATA_CERT_COLL = "bi5_data_certification"
_VERDICTS = ("PASS", "WARN", "FAIL")


def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _report_to_doc(
    report: BI5ScoreReport,
    *,
    weights: Mapping[str, float],
    certified_at_dt: datetime,
) -> Dict[str, Any]:
    return {
        "symbol":               report.symbol,
        "window_start_utc":     _to_utc(report.window_start),
        "window_end_utc":       _to_utc(report.window_end),
        "hours_expected":       int(report.hours_expected),
        "hours_present":        int(report.hours_present),
        "hours_missing":        int(report.hours_missing),
        "hours_expected_empty": int(report.hours_expected_empty),
        "hours_decode_fail":    int(report.hours_decode_fail),
        "ticks_total":          int(report.ticks_total),
        "non_monotonic_ticks":  int(report.non_monotonic_ticks),
        "price_outlier_ticks":  int(report.price_outlier_ticks),
        "zero_vol_ticks":       int(report.zero_vol_ticks),
        "sparse_hours":         int(report.sparse_hours),
        "low_density_hours":    int(report.low_density_hours),
        "max_silent_gap_s":     float(report.max_silent_gap_s),
        "subscores":            {k: float(v) for k, v in report.subscores.items()},
        "bi5_score":            float(report.bi5_score),
        "verdict":              report.verdict,
        "weights_used":         {k: float(v) for k, v in weights.items()},
        "evaluator_version":    report.evaluator_version,
        "certified_at_dt":      certified_at_dt,
    }


async def upsert_data_certification(
    db: Any,
    report: BI5ScoreReport,
    *,
    weights: Mapping[str, float] = DEFAULT_WEIGHTS,
    certified_at_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Idempotent upsert of a BI5 *data-feed* certification report.

    Domain key: `(symbol, window_start_utc, window_end_utc)`. Re-runs
    overwrite scores/verdict/subscores while preserving the original
    `certified_at_dt` (only set on insert).
    """
    if report.verdict not in _VERDICTS:
        raise ValueError(
            f"unexpected verdict {report.verdict!r}; must be one of {_VERDICTS}"
        )
    certified_at_dt = certified_at_dt or datetime.now(timezone.utc)
    doc = _report_to_doc(report, weights=weights, certified_at_dt=certified_at_dt)
    key = {
        "symbol":           doc["symbol"],
        "window_start_utc": doc["window_start_utc"],
        "window_end_utc":   doc["window_end_utc"],
    }
    update = {
        "$set": {k: v for k, v in doc.items() if k != "certified_at_dt"},
        "$setOnInsert": {"certified_at_dt": certified_at_dt},
    }
    res = await db[BI5_DATA_CERT_COLL].update_one(key, update, upsert=True)
    return {
        "matched":  int(getattr(res, "matched_count", 0) or 0),
        "upserted": 1 if getattr(res, "upserted_id", None) is not None else 0,
        "modified": int(getattr(res, "modified_count", 0) or 0),
        "key":      {
            "symbol":           key["symbol"],
            "window_start_utc": key["window_start_utc"].isoformat(),
            "window_end_utc":   key["window_end_utc"].isoformat(),
        },
    }


async def get_latest_data_certification(
    db: Any, *, symbol: str,
) -> Optional[Dict[str, Any]]:
    """Most-recent data-cert doc for `symbol`, or None."""
    return await db[BI5_DATA_CERT_COLL].find_one(
        {"symbol": symbol},
        sort=[("certified_at_dt", DESCENDING)],
    )


async def get_data_certification(
    db: Any,
    *,
    symbol: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
) -> Optional[Dict[str, Any]]:
    """Point lookup on the unique key."""
    return await db[BI5_DATA_CERT_COLL].find_one({
        "symbol":           symbol,
        "window_start_utc": _to_utc(window_start_utc),
        "window_end_utc":   _to_utc(window_end_utc),
    })


async def find_data_certs_by_verdict(
    db: Any,
    *,
    verdict: str,
    limit: int = 50,
    since_dt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """List data-feed certs with the given verdict, newest first."""
    if verdict not in _VERDICTS:
        raise ValueError(f"verdict must be one of {_VERDICTS}")
    q: Dict[str, Any] = {"verdict": verdict}
    if since_dt is not None:
        q["certified_at_dt"] = {"$gte": _to_utc(since_dt)}
    cursor = db[BI5_DATA_CERT_COLL].find(
        q, sort=[("certified_at_dt", DESCENDING)],
    ).limit(int(limit))
    return [doc async for doc in cursor]
