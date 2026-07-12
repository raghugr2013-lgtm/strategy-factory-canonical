"""
One-off + reusable aggregator — builds higher-timeframe candles from an
existing lower-timeframe base already in `market_data`.

Use case discovered during P0: EURUSD had 74k 15-minute candles (3 years)
but only 120 1-hour candles (5 days). The Dukascopy ingestor pulls each
timeframe independently, so gaps across timeframes are common.

This script up-samples the low-TF candles into the target high-TF by
bucketing on UTC boundaries:
    * 1h  ← 4 × 15m   (or 60 × 1m / 12 × 5m)
    * 4h  ← 4 × 1h
    * 1d  ← 24 × 1h

Run as a module:

    cd /app/backend && python -m scripts.rebuild_higher_tf \
        --symbol EURUSD --source_tf 15m --target_tf 1h

Or from code:
    from scripts.rebuild_higher_tf import rebuild
    await rebuild("EURUSD", "15m", "1h")
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Iterable

# Path bootstrap when run as `python scripts/rebuild_higher_tf.py`
sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from engines.db import get_db  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


# Map TF → minute count. Keep in sync with other engines.
_TF_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "h1": 60, "4h": 240, "h4": 240,
    "1d": 1440,
}


def _minutes(tf: str) -> int:
    m = _TF_MINUTES.get(tf.lower())
    if not m:
        raise ValueError(f"unsupported timeframe: {tf}")
    return m


def _bucket_floor(ts: datetime, bucket_minutes: int) -> datetime:
    """Floor a UTC datetime to the start of its bucket. E.g. for
    bucket=60 → the hour boundary; for bucket=240 → the 00/04/08/12/16/20
    UTC boundaries (standard H4 convention)."""
    epoch = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)
    minutes_from_midnight = epoch.hour * 60 + epoch.minute
    floored = (minutes_from_midnight // bucket_minutes) * bucket_minutes
    return epoch.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


def _parse_ts(raw) -> datetime:
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    # ISO string in DB
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))


def _aggregate(rows: Iterable[dict], target_minutes: int) -> list[dict]:
    """Bucket low-TF OHLCV rows into target-TF candles."""
    buckets: dict[datetime, dict] = {}
    for r in rows:
        ts = _parse_ts(r["timestamp"])
        key = _bucket_floor(ts, target_minutes)
        b = buckets.get(key)
        o, h, l, c = r.get("open"), r.get("high"), r.get("low"), r.get("close")
        v = r.get("volume", 0) or 0
        if b is None:
            buckets[key] = {"open": o, "high": h, "low": l, "close": c, "volume": v}
        else:
            if h is not None:
                b["high"] = max(b["high"], h) if b["high"] is not None else h
            if l is not None:
                b["low"] = min(b["low"], l) if b["low"] is not None else l
            b["close"] = c
            b["volume"] = (b["volume"] or 0) + v
    out = []
    for ts in sorted(buckets.keys()):
        b = buckets[ts]
        out.append({
            "timestamp": ts.isoformat(),
            "open": b["open"], "high": b["high"],
            "low": b["low"],  "close": b["close"],
            "volume": b["volume"],
        })
    return out


async def rebuild(
    symbol: str,
    source_tf: str,
    target_tf: str,
    *,
    source_key: str = "bid_1m",
    overwrite: bool = True,
) -> dict:
    db = get_db()
    src_min = _minutes(source_tf)
    tgt_min = _minutes(target_tf)
    if tgt_min <= src_min or tgt_min % src_min != 0:
        return {"ok": False, "error": f"target_tf must be a multiple of source_tf ({src_min} → {tgt_min})"}

    rows = await db.market_data.find(
        {"symbol": symbol, "source": source_key, "timeframe": source_tf.lower()},
        {"_id": 0, "timestamp": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
    ).sort("timestamp", 1).to_list(length=None)

    logger.info(f"loaded {len(rows)} {source_tf} rows for {symbol}")
    if not rows:
        return {"ok": False, "error": f"no {source_tf} rows for {symbol}"}

    aggregated = _aggregate(rows, tgt_min)
    logger.info(f"aggregated into {len(aggregated)} {target_tf} candles")

    tgt_tf_lower = target_tf.lower()
    if overwrite:
        r = await db.market_data.delete_many(
            {"symbol": symbol, "source": source_key, "timeframe": tgt_tf_lower}
        )
        logger.info(f"deleted {r.deleted_count} existing {target_tf} rows for {symbol}")

    docs = [
        {"symbol": symbol, "source": source_key, "timeframe": tgt_tf_lower, **row}
        for row in aggregated
    ]
    if docs:
        await db.market_data.insert_many(docs)

    return {
        "ok": True,
        "symbol": symbol,
        "source_tf": source_tf,
        "target_tf": target_tf,
        "source_rows": len(rows),
        "aggregated_rows": len(aggregated),
        "first_ts": aggregated[0]["timestamp"] if aggregated else None,
        "last_ts": aggregated[-1]["timestamp"] if aggregated else None,
    }


def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--source_tf", required=True)
    ap.add_argument("--target_tf", required=True)
    ap.add_argument("--source_key", default="bid_1m")
    ap.add_argument("--no-overwrite", action="store_true")
    args = ap.parse_args()
    res = asyncio.run(rebuild(
        args.symbol, args.source_tf, args.target_tf,
        source_key=args.source_key, overwrite=not args.no_overwrite,
    ))
    print(res)


if __name__ == "__main__":
    _cli()
