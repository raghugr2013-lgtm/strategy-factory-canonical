"""P0B Phase 3 — Strategy-level `bi5_certification` persistence adapter.

Audit store for the BI5 *strategy* certification record. Distinct
from the data-feed cert (`bi5_data_certification`):

    * bi5_data_certification : (symbol, window)  → feed quality cert
    * bi5_certification      : (strategy_id, ts) → strategy cert

Idempotency model: audit-trail. The unique compound key
``(strategy_id, certification_timestamp)`` means every call inserts a
fresh row — re-certifications create new rows rather than mutating
the previous one.

BID/BI5 firewall: this module imports only `pymongo`, stdlib, and the
Phase-1 ``tick_validator`` threshold constants. It does NOT import
any BID-stage module, any Phase-1 evaluator, or the Phase-3
orchestrator.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from pymongo import DESCENDING

from engines.tick_validator import PASS_THRESHOLD, WARN_THRESHOLD


logger = logging.getLogger(__name__)


BI5_CERT_COLL = "bi5_certification"
EVALUATOR_VERSION = "bi5_cert@P0B-v1"

# Frozen composite weights (Integrity / Spread / Slippage / Execution
# / Stability). The store rejects any deviation from this split so that
# "no second weighting model" is enforced at the storage boundary.
FROZEN_WEIGHTS: Dict[str, float] = {
    "integrity": 0.30,
    "spread":    0.20,
    "slippage":  0.20,
    "execution": 0.15,
    "stability": 0.15,
}
_VERDICTS: Tuple[str, ...] = ("PASS", "WARN", "FAIL")
_VALID_REASONS: Tuple[str, ...] = (
    "DATA_CERT_MISSING",
    "DATA_CERT_NOT_PASS",
    "LOW_COMPOSITE",
    "MISSING_FILLS",
    "MISSING_SIGNALS",
    "STALE_CERTIFICATION",
)

# Operator-tunable freshness window for the derived BI5-Certified flag.
DEFAULT_FRESHNESS_DAYS = int(os.environ.get("BI5_CERT_FRESHNESS_DAYS", "30"))


# ── helpers ──────────────────────────────────────────────────────────

def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _check_weights(weights: Mapping[str, float]) -> None:
    if set(weights) != set(FROZEN_WEIGHTS):
        raise ValueError(
            f"weights_used keys must equal {sorted(FROZEN_WEIGHTS)}, "
            f"got {sorted(weights)}"
        )
    for k, v in FROZEN_WEIGHTS.items():
        if abs(float(weights[k]) - v) > 1e-9:
            raise ValueError(
                f"weights_used[{k!r}]={weights[k]!r} differs from frozen "
                f"split {v}; no second weighting model is allowed"
            )


# ── public dataclass: persisted shape mirror ─────────────────────────

@dataclass(frozen=True)
class StrategyCertRecord:
    strategy_id: str
    pair: str
    timeframe: str
    style: str
    certification_timestamp: datetime
    certification_verdict: str
    certification_version: str
    integrity_score: float
    spread_score: float
    slippage_score: float
    execution_score: float
    stability_score: float
    composite_score: float
    data_cert_ref: Optional[Dict[str, Any]] = None
    mutation_family: Optional[str] = None
    parent_strategy_id: Optional[str] = None
    reason: Optional[str] = None
    venue_profile: Optional[str] = None
    weights_used: Dict[str, float] = field(
        default_factory=lambda: dict(FROZEN_WEIGHTS)
    )
    thresholds_used: Dict[str, float] = field(
        default_factory=lambda: {"pass": PASS_THRESHOLD, "warn": WARN_THRESHOLD}
    )

    def to_doc(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "strategy_id":             self.strategy_id,
            "pair":                    self.pair,
            "timeframe":               self.timeframe,
            "style":                   self.style,
            "certification_timestamp": _to_utc(self.certification_timestamp),
            "certification_verdict":   self.certification_verdict,
            "certification_version":   self.certification_version,
            "integrity_score":         float(self.integrity_score),
            "spread_score":            float(self.spread_score),
            "slippage_score":          float(self.slippage_score),
            "execution_score":         float(self.execution_score),
            "stability_score":         float(self.stability_score),
            "composite_score":         float(self.composite_score),
            "weights_used":            dict(self.weights_used),
            "thresholds_used":         dict(self.thresholds_used),
        }
        # Optional fields — only persist when populated, so research
        # queries can use `$exists` cleanly.
        if self.data_cert_ref is not None:
            d["data_cert_ref"] = dict(self.data_cert_ref)
        if self.mutation_family is not None:
            d["mutation_family"] = self.mutation_family
        if self.parent_strategy_id is not None:
            d["parent_strategy_id"] = self.parent_strategy_id
        if self.reason is not None:
            d["reason"] = self.reason
        if self.venue_profile is not None:
            d["venue_profile"] = self.venue_profile
        return d


# ── writes ───────────────────────────────────────────────────────────

async def upsert_certification(
    db: Any,
    record: StrategyCertRecord,
) -> Dict[str, Any]:
    """Insert a strategy certification row (audit-trail semantics).

    Domain key: ``(strategy_id, certification_timestamp)`` is unique →
    every call creates a new row. Re-running this with the same
    `certification_timestamp` (deliberate idempotent retry) will be a
    no-op (matched=1).
    """
    if not record.strategy_id:
        raise ValueError("strategy_id is required")
    if not record.pair:
        raise ValueError("pair is required")
    if not record.timeframe:
        raise ValueError("timeframe is required")
    if record.certification_verdict not in _VERDICTS:
        raise ValueError(
            f"certification_verdict must be one of {_VERDICTS}, "
            f"got {record.certification_verdict!r}"
        )
    if record.reason is not None and record.reason not in _VALID_REASONS:
        raise ValueError(
            f"reason must be one of {_VALID_REASONS} (or None); "
            f"got {record.reason!r}"
        )
    _check_weights(record.weights_used)

    # Clamp all five scores AND the composite into [0,1] defensively.
    clamped = StrategyCertRecord(
        strategy_id=record.strategy_id,
        pair=record.pair,
        timeframe=record.timeframe,
        style=record.style,
        certification_timestamp=record.certification_timestamp,
        certification_verdict=record.certification_verdict,
        certification_version=record.certification_version,
        integrity_score=_clamp01(record.integrity_score),
        spread_score=_clamp01(record.spread_score),
        slippage_score=_clamp01(record.slippage_score),
        execution_score=_clamp01(record.execution_score),
        stability_score=_clamp01(record.stability_score),
        composite_score=_clamp01(record.composite_score),
        data_cert_ref=record.data_cert_ref,
        mutation_family=record.mutation_family,
        parent_strategy_id=record.parent_strategy_id,
        reason=record.reason,
        venue_profile=record.venue_profile,
        weights_used=dict(record.weights_used),
        thresholds_used=dict(record.thresholds_used),
    )
    doc = clamped.to_doc()
    key = {
        "strategy_id":             doc["strategy_id"],
        "certification_timestamp": doc["certification_timestamp"],
    }
    res = await db[BI5_CERT_COLL].update_one(
        key, {"$set": doc}, upsert=True,
    )
    return {
        "matched":  int(getattr(res, "matched_count", 0) or 0),
        "upserted": 1 if getattr(res, "upserted_id", None) is not None else 0,
        "modified": int(getattr(res, "modified_count", 0) or 0),
        "strategy_id": doc["strategy_id"],
        "certification_timestamp": doc["certification_timestamp"].isoformat(),
        "verdict": doc["certification_verdict"],
    }


# ── reads ────────────────────────────────────────────────────────────

async def get_latest_certification(
    db: Any, *, strategy_id: str,
) -> Optional[Dict[str, Any]]:
    """Newest cert for `strategy_id`, or None."""
    return await db[BI5_CERT_COLL].find_one(
        {"strategy_id": strategy_id},
        sort=[("certification_timestamp", DESCENDING)],
    )


async def list_certifications_for_strategy(
    db: Any, *, strategy_id: str, limit: int = 50,
) -> List[Dict[str, Any]]:
    cursor = db[BI5_CERT_COLL].find(
        {"strategy_id": strategy_id},
        sort=[("certification_timestamp", DESCENDING)],
    ).limit(int(limit))
    return [d async for d in cursor]


async def list_certifications(
    db: Any,
    *,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    style: Optional[str] = None,
    mutation_family: Optional[str] = None,
    verdict: Optional[str] = None,
    since_dt: Optional[datetime] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if pair:
        q["pair"] = pair
    if timeframe:
        q["timeframe"] = timeframe
    if style:
        q["style"] = style
    if mutation_family:
        q["mutation_family"] = mutation_family
    if verdict:
        if verdict not in _VERDICTS:
            raise ValueError(f"verdict must be one of {_VERDICTS}")
        q["certification_verdict"] = verdict
    if since_dt is not None:
        q["certification_timestamp"] = {"$gte": _to_utc(since_dt)}
    cursor = db[BI5_CERT_COLL].find(
        q, sort=[("certification_timestamp", DESCENDING)],
    ).limit(int(limit))
    return [d async for d in cursor]


async def is_bi5_certified(
    db: Any,
    *,
    strategy_id: str,
    freshness_days: Optional[int] = None,
    now_dt: Optional[datetime] = None,
) -> Dict[str, Any]:
    """The derived BI5-Certified flag.

    A strategy is BI5-Certified iff there exists a cert row with
    verdict='PASS' whose `certification_timestamp` is within the
    freshness window. No new lifecycle row is written; the flag is
    purely derived.
    """
    fresh = DEFAULT_FRESHNESS_DAYS if freshness_days is None else int(freshness_days)
    now = now_dt or datetime.now(timezone.utc)
    cutoff = _to_utc(now) - timedelta(days=fresh)
    doc = await db[BI5_CERT_COLL].find_one(
        {
            "strategy_id": strategy_id,
            "certification_verdict": "PASS",
            "certification_timestamp": {"$gte": cutoff},
        },
        sort=[("certification_timestamp", DESCENDING)],
    )
    out: Dict[str, Any] = {
        "strategy_id":     strategy_id,
        "certified":       doc is not None,
        "freshness_days":  fresh,
    }
    if doc is not None:
        out["certified_at"] = doc["certification_timestamp"].isoformat() \
            if isinstance(doc["certification_timestamp"], datetime) \
            else doc["certification_timestamp"]
        out["latest_cert_id"] = str(doc["_id"])
        expires = _to_utc(
            doc["certification_timestamp"]
            if isinstance(doc["certification_timestamp"], datetime)
            else datetime.fromisoformat(doc["certification_timestamp"])
        ) + timedelta(days=fresh)
        out["expires_at"] = expires.isoformat()
    return out


# ── stats aggregation (learning systems read path) ───────────────────

# Group-by keys understood by `aggregate_stats`. ``day`` buckets by
# UTC calendar day.
_VALID_GROUP_BY = ("pair", "style", "timeframe", "mutation_family", "verdict", "day")
DEFAULT_STATS_TOP_N = 100


async def aggregate_stats(
    db: Any,
    *,
    group_by: str,
    since_dt: Optional[datetime] = None,
    top_n: int = DEFAULT_STATS_TOP_N,
) -> List[Dict[str, Any]]:
    """Aggregate cert counts grouped by `group_by`.

    Returns:
        [{key, total, pass, warn, fail, pass_rate}], sorted by ``total``
        DESC, capped at ``top_n``.

    The cap exists to keep payloads bounded under
    ``group_by=mutation_family`` over multi-year slices.
    """
    if group_by not in _VALID_GROUP_BY:
        raise ValueError(
            f"group_by must be one of {_VALID_GROUP_BY}, got {group_by!r}"
        )
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    match: Dict[str, Any] = {}
    if since_dt is not None:
        match["certification_timestamp"] = {"$gte": _to_utc(since_dt)}

    # Build the $group _id for the chosen dimension.
    if group_by == "verdict":
        group_id: Any = "$certification_verdict"
    elif group_by == "day":
        group_id = {
            "$dateToString": {
                "format": "%Y-%m-%d",
                "date":   "$certification_timestamp",
            }
        }
    else:
        # Direct field projections: pair / style / timeframe / mutation_family
        group_id = "$" + group_by

    # Drop docs that are missing the requested field rather than
    # bucketing them under None — research-grade hygiene.
    if group_by not in ("verdict", "day"):
        match[group_by] = {"$ne": None, "$exists": True}

    pipeline: List[Dict[str, Any]] = []
    if match:
        pipeline.append({"$match": match})
    pipeline.extend([
        {"$group": {
            "_id": group_id,
            "total": {"$sum": 1},
            "pass": {"$sum": {
                "$cond": [{"$eq": ["$certification_verdict", "PASS"]}, 1, 0]
            }},
            "warn": {"$sum": {
                "$cond": [{"$eq": ["$certification_verdict", "WARN"]}, 1, 0]
            }},
            "fail": {"$sum": {
                "$cond": [{"$eq": ["$certification_verdict", "FAIL"]}, 1, 0]
            }},
        }},
        {"$sort": {"total": -1}},
        {"$limit": int(top_n)},
    ])

    rows: List[Dict[str, Any]] = []
    async for r in db[BI5_CERT_COLL].aggregate(pipeline):
        total = int(r.get("total", 0) or 0)
        passed = int(r.get("pass", 0) or 0)
        rows.append({
            "key":       r.get("_id"),
            "total":     total,
            "pass":      passed,
            "warn":      int(r.get("warn", 0) or 0),
            "fail":      int(r.get("fail", 0) or 0),
            "pass_rate": (passed / total) if total > 0 else 0.0,
        })
    return rows
