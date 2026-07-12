"""P0B Phase 2 — `market_spread` persistence adapter.

Persists per-minute spread bars (output of
`engines.spread_analyzer.rollup_spread_minutes`) into Mongo with
idempotent upserts keyed by `(symbol, minute_utc)`.

The unique index is declared in `engines.db_indexes.INDEX_SPECS`; a
TTL is declared in `engines.db_indexes.TTL_SPECS`. This module does
not declare indexes itself — that responsibility stays centralised
with `db_indexes.ensure_indexes()`.

BID/BI5 firewall: this module imports only `pymongo`,
`engines.spread_analyzer` (Phase 1 dataclass), and stdlib.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from pymongo import ASCENDING, UpdateOne

from engines.spread_analyzer import SpreadBar


MARKET_SPREAD_COLL = "market_spread"
SRC = "bi5"


def _to_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _floor_minute_utc(dt: datetime) -> datetime:
    dt = _to_utc(dt)
    return dt.replace(second=0, microsecond=0)


def _bar_to_doc(bar: SpreadBar, *, now_dt: datetime) -> Dict[str, Any]:
    minute_utc = _floor_minute_utc(bar.ts)
    return {
        "symbol":       bar.symbol,
        "minute_utc":   minute_utc,                 # BSON Date (queryable)
        "minute_iso":   minute_utc.isoformat(),     # mirror for human logs
        "spread_open":  float(bar.spread_open),
        "spread_high":  float(bar.spread_high),
        "spread_low":   float(bar.spread_low),
        "spread_close": float(bar.spread_close),
        "spread_mean":  float(bar.spread_mean),
        "tick_count":   int(bar.tick_count),
        "src":          SRC,
        "evaluator_version": "spread_analyzer@P0B-v1",
        "created_at_dt": now_dt,                    # BSON Date — TTL field
    }


async def upsert_spread_bars(
    db: Any,
    bars: Sequence[SpreadBar],
    *,
    now_dt: Optional[datetime] = None,
) -> Dict[str, int]:
    """Idempotent bulk upsert keyed by `(symbol, minute_utc)`.

    Returns a small structured summary `{matched, upserted, modified}`.
    A no-op for an empty input is explicit (returns zeros) so callers
    can wire this in unconditionally.
    """
    if not bars:
        return {"matched": 0, "upserted": 0, "modified": 0}

    now_dt = now_dt or datetime.now(timezone.utc)
    ops: List[UpdateOne] = []
    for b in bars:
        doc = _bar_to_doc(b, now_dt=now_dt)
        key = {"symbol": doc["symbol"], "minute_utc": doc["minute_utc"]}
        # $set on every field but `created_at_dt`, which only fires on
        # insert. This keeps the original ingestion time stable for TTL
        # while still letting later re-derivations correct the OHLC.
        update = {
            "$set": {k: v for k, v in doc.items() if k != "created_at_dt"},
            "$setOnInsert": {"created_at_dt": doc["created_at_dt"]},
        }
        ops.append(UpdateOne(key, update, upsert=True))

    res = await db[MARKET_SPREAD_COLL].bulk_write(ops, ordered=False)
    return {
        "matched":  int(getattr(res, "matched_count", 0) or 0),
        "upserted": int(len(getattr(res, "upserted_ids", {}) or {})),
        "modified": int(getattr(res, "modified_count", 0) or 0),
    }


async def find_spread_bars(
    db: Any,
    *,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
) -> List[Dict[str, Any]]:
    """Return spread bars for `[start_utc, end_utc)` sorted by minute_utc."""
    cursor = db[MARKET_SPREAD_COLL].find(
        {
            "symbol": symbol,
            "minute_utc": {"$gte": _to_utc(start_utc), "$lt": _to_utc(end_utc)},
        },
        sort=[("minute_utc", ASCENDING)],
    )
    return [doc async for doc in cursor]
