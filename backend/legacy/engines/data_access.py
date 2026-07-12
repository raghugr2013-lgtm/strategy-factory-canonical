"""Shared data-access + auto-recovery layer.

Single source of truth for every module that pulls OHLC bars from
`market_data`. Before this module existed, we had three parallel
loaders (`dashboard._load_real_prices`, `auto_factory._load_data`,
`paper_execution_engine._load_bars`) each with its own TF map and its
own insufficient-data behaviour. This module consolidates all of that
into:

    • `load_ohlc_bars(pair, tf, source, limit)`   — canonical OHLCV loader
    • `load_closes(pair, tf)`                     — closes-only tuple, used
                                                     by legacy callers
    • `load_with_recovery(pair, tf, …)`           — loader + auto-download

Threshold policy:
    • Every timeframe has a per-TF minimum (see `MIN_CANDLES_BY_TF`).
    • Below threshold → structured `"insufficient"` status.
    • `auto_recover=True` → one attempt to call Dukascopy download
                            and re-read. Single retry only.

Auto systems (`auto_factory`, `auto_mutation_runner`, paper exec) pass
`auto_recover=True` so the pipeline self-heals. Interactive dashboard
routes keep today's fail-fast behaviour (a2 decision).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.backtest_engine import TIMEFRAME_MAP
from engines.db import get_db

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# Threshold policy
# ─────────────────────────────────────────────────────────────────────

# Per-TF minimum candle counts for a reliable backtest.
# Rule of thumb: indicators (SMA-200, EMA-100, ATR-14) + walk-forward
# windows + OOS holdout need at least ~3× their period.
MIN_CANDLES_BY_TF: Dict[str, int] = {
    "M1":  5000,
    "M5":  3000,
    "M15": 2000,
    "M30": 1000,
    "H1":  500,
    "H4":  200,
    "D1":  100,
}

# Floor used by the legacy `_load_real_prices` wrapper — below this we
# always return empty even if the TF-specific threshold is lower.
ABSOLUTE_MIN_CANDLES = 60


def min_candles_for(timeframe: str) -> int:
    """Return the minimum candle count required for a given timeframe.
    Accepts either canonical (`H1`) or DB-native (`1h`) forms."""
    if not timeframe:
        return ABSOLUTE_MIN_CANDLES
    canon = timeframe.upper()
    if canon in MIN_CANDLES_BY_TF:
        return MIN_CANDLES_BY_TF[canon]
    # Try DB→canonical reverse mapping for `1h`, `15m`, etc.
    db_to_canon = {
        "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
        "1h": "H1", "4h": "H4", "1d": "D1",
    }
    mapped = db_to_canon.get(timeframe.lower())
    if mapped:
        return MIN_CANDLES_BY_TF[mapped]
    return ABSOLUTE_MIN_CANDLES


# ─────────────────────────────────────────────────────────────────────
# Canonical loader
# ─────────────────────────────────────────────────────────────────────

async def load_ohlc_bars(
    pair: str,
    timeframe: str,
    source: str = "bid_1m",
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Load OHLCV bars for (pair, source, timeframe) from `market_data`.

    Returns a list of dicts with keys: `timestamp, open, high, low,
    close, volume` (volume may be absent on legacy docs). Empty list
    when no data is found.

    `timeframe` may be canonical (`H1`) or DB-native (`1h`). Conversion
    is done via the authoritative `TIMEFRAME_MAP` — NO local map.
    """
    db = get_db()
    data_tf = TIMEFRAME_MAP.get(timeframe, timeframe.lower())
    cursor = db.market_data.find(
        {"symbol": pair, "source": source, "timeframe": data_tf},
        {"_id": 0, "timestamp": 1, "open": 1, "high": 1,
         "low": 1, "close": 1, "volume": 1},
    ).sort("timestamp", 1)
    if limit is not None and limit > 0:
        cursor = cursor.limit(int(limit))
    docs = [d async for d in cursor]
    return docs


async def load_closes(pair: str, timeframe: str) -> Tuple[list, list, list]:
    """Closes-only tuple loader for legacy callers.

    Returns `(prices, highs, lows)` where each is a parallel list.
    Emits the same INFO log line the old `_load_real_prices` did so
    log-scraping continues to work.
    Returns `([], [], [])` when the collection holds fewer than
    `ABSOLUTE_MIN_CANDLES` rows — this is the legacy floor and
    does NOT enforce per-TF thresholds. Callers that need per-TF
    guarantees must use `load_with_recovery`.
    """
    docs = await load_ohlc_bars(pair, timeframe)
    first_ts = docs[0].get("timestamp") if docs else None
    last_ts = docs[-1].get("timestamp") if docs else None
    data_tf = TIMEFRAME_MAP.get(timeframe, timeframe.lower())
    logger.info(
        "[data_pipeline] pair=%s tf_raw=%s tf_db=%s candles=%d range=%s → %s",
        pair, timeframe, data_tf, len(docs), first_ts, last_ts,
    )
    if not docs or len(docs) < ABSOLUTE_MIN_CANDLES:
        return [], [], []
    prices = [d["close"] for d in docs]
    highs = [d.get("high", d["close"]) for d in docs]
    lows = [d.get("low", d["close"]) for d in docs]
    return prices, highs, lows


# ─────────────────────────────────────────────────────────────────────
# Auto-recovery loader
# ─────────────────────────────────────────────────────────────────────

# Approximate calendar-days per candle (accounts for 5-day FX week).
_DAYS_PER_CANDLE_BY_TF = {
    "1m": 1 / (60 * 24), "5m": 5 / (60 * 24), "15m": 15 / (60 * 24),
    "30m": 30 / (60 * 24), "1h": 1 / 24, "4h": 4 / 24, "1d": 1.4,
}


def _download_window(tf_db: str, min_candles: int, *, buffer: float = 1.5) -> Tuple[str, str]:
    """Compute a (date_from, date_to) window that should cover at least
    `min_candles × buffer` candles of TF `tf_db`. Returns ISO dates."""
    days_per_candle = _DAYS_PER_CANDLE_BY_TF.get(tf_db, 1 / 24)
    span_days = max(30, int(min_candles * buffer * days_per_candle * 1.5))
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=span_days)
    return start.isoformat(), end.isoformat()


async def load_with_recovery(
    pair: str,
    timeframe: str,
    *,
    min_candles: Optional[int] = None,
    auto_recover: bool = False,
    source: str = "bid_1m",
) -> Dict[str, Any]:
    """Load bars with optional auto-download recovery.

    Args:
        pair: Symbol (EURUSD / XAUUSD / …).
        timeframe: Canonical (`H1`) or DB-native (`1h`).
        min_candles: Per-TF threshold. Defaults to `min_candles_for(tf)`.
        auto_recover: When True, attempts ONE inline Dukascopy download
                      if below threshold, then re-reads. When False,
                      returns `"insufficient"` immediately.
        source: Price source — defaults to `"bid_1m"`.

    Returns a dict:
        {
          "status": "ok" | "recovered" | "insufficient" | "error",
          "bars":   [bar, …]   (may be below threshold on insufficient),
          "count":  int,
          "pair":   str,
          "timeframe":    str,   (canonical form the caller passed)
          "timeframe_db": str,
          "threshold":    int,
          "message":      str,
          "recovery": {              # present when auto_recover triggered
            "attempted": bool,
            "downloaded": int,       # rows inserted by the downloader
            "before": int,           # candle count before recovery
            "after":  int,           # candle count after recovery
            "date_from": str, "date_to": str,
            "error": str | None,
          }
        }
    """
    threshold = int(min_candles if min_candles is not None else min_candles_for(timeframe))
    tf_db = TIMEFRAME_MAP.get(timeframe, timeframe.lower())

    bars = await load_ohlc_bars(pair, timeframe, source=source)
    count = len(bars)

    base = {
        "pair": pair, "timeframe": timeframe, "timeframe_db": tf_db,
        "threshold": threshold, "bars": bars, "count": count,
    }

    if count >= threshold:
        logger.info(
            "[data_access] %s/%s OK — %d candles (threshold %d)",
            pair, timeframe, count, threshold,
        )
        return {**base, "status": "ok", "message": "Data ready — continuing pipeline."}

    if not auto_recover:
        msg = (
            f"Data insufficient for {pair}/{timeframe} — have {count}, "
            f"need {threshold}."
        )
        logger.warning("[data_access] %s", msg)
        return {**base, "status": "insufficient", "message": msg}

    # ── Auto-recovery ─────────────────────────────────────────────
    logger.info(
        "[data_access] %s/%s — data insufficient (%d/%d), auto-downloading…",
        pair, timeframe, count, threshold,
    )
    date_from, date_to = _download_window(tf_db, threshold)
    recovery: Dict[str, Any] = {
        "attempted": True, "downloaded": 0, "before": count, "after": count,
        "date_from": date_from, "date_to": date_to, "error": None,
    }
    try:
        # Lazy import so this module stays import-cheap when the
        # downloader is disabled.
        from data_engine.dukascopy_downloader import download_and_store
        res = await download_and_store(pair, tf_db, date_from, date_to)
        if res.get("success") is False:
            recovery["error"] = str(res.get("error") or "download failed")
        else:
            recovery["downloaded"] = int(res.get("rows_inserted") or 0)
    except Exception as e:
        recovery["error"] = f"download exception: {e}"
        logger.exception("[data_access] recovery failed for %s/%s", pair, timeframe)

    # Re-read regardless of download result — someone else may have
    # populated the collection in the meantime.
    bars2 = await load_ohlc_bars(pair, timeframe, source=source)
    recovery["after"] = len(bars2)

    if len(bars2) >= threshold:
        logger.info(
            "[data_access] %s/%s recovered — %d candles after download "
            "(before=%d, inserted=%d).",
            pair, timeframe, len(bars2), count, recovery["downloaded"],
        )
        return {
            **base, "bars": bars2, "count": len(bars2),
            "status": "recovered",
            "message": "Data ready — continuing pipeline.",
            "recovery": recovery,
        }

    msg = (
        f"Recovery failed for {pair}/{timeframe} — have {len(bars2)}, "
        f"need {threshold}. "
        + (f"Downloader error: {recovery['error']}" if recovery["error"]
           else "Dukascopy may not have data for this range/symbol.")
    )
    logger.error("[data_access] %s", msg)
    return {
        **base, "bars": bars2, "count": len(bars2),
        "status": "insufficient", "message": msg, "recovery": recovery,
    }



# ─────────────────────────────────────────────────────────────────────
# Phase 27.4 — BI5 single-source realism stream
# ─────────────────────────────────────────────────────────────────────

async def load_bi5_1m_bars(
    pair: str, *, limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Canonical realism-stream loader.

    Reads 1-minute BI5 bars for ``pair``. Returns a list of
    ``{timestamp, open, high, low, close, volume}`` dicts ascending by
    timestamp. ``limit`` caps the slice when set; the realism path
    typically passes ``None`` to honour the full retention window.

    This is the SINGLE READ POINT for realism replay. Higher-TF realism
    evaluation MUST resample this output via the bi5_realism resampler —
    never call ``load_ohlc_bars`` with ``source="bi5"`` and
    ``timeframe!="1m"`` directly.

    Architectural invariant (Phase 27.4):
      * Discovery / mutation / OOS / lifecycle progression read
        ``source="bid_1m"`` only.
      * BI5 storage is one bucket per pair: ``(symbol, "bi5", "1m")``.
      * The realism evaluator is the only consumer of BI5 and resamples
        on demand.
    """
    return await load_ohlc_bars(pair, "1m", source="bi5", limit=limit)
