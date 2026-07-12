"""BI5 R1 · B-9 — One-shot historical backfill.

Idempotent sweep over the existing on-disk BI5 archive that REGISTERS
coverage into the ``market_data`` collection so the UI immediately
shows historical BI5 coverage even before a fresh scheduler cycle
runs. The script does NOT re-download anything; it only walks the
local archive that the previous engineering team already populated
on disk (~110 MB across the seeded 7 symbols).

Idempotency is enforced via the existing ``bi5_ingest_log`` per-file
hash check inside ``incremental_update_bi5``. Re-running this script
N times produces zero duplicate rows.

Usage::

    python -m scripts.bi5_one_shot_backfill              # all registry symbols
    python -m scripts.bi5_one_shot_backfill EURUSD       # one symbol
    python -m scripts.bi5_one_shot_backfill EURUSD GBPUSD
"""
from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is on sys.path when invoked via ``python scripts/...``.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("bi5-one-shot-backfill")


async def _resolve_symbols(explicit: list[str] | None) -> list[str]:
    if explicit:
        return [s.upper() for s in explicit]

    # Prefer registry (DSR flag ON) so newly onboarded symbols are
    # included automatically.
    try:
        from engines.market_universe_adapter import is_flag_on
        if is_flag_on():
            from engines import market_universe as MU
            rows = await MU.list_symbols(enabled=True, limit=2000)
            syms = [
                r["symbol"]
                for r in rows
                if r and r.get("eligibility", {}).get("ingestion_enabled")
            ]
            if syms:
                return syms
    except Exception as e:                                       # pragma: no cover
        logger.warning("registry resolution failed, using legacy: %s", e)

    from config.symbols import SYMBOL_CONFIG
    return list(SYMBOL_CONFIG.keys())


async def _backfill_one(symbol: str) -> dict:
    """Returns a summary dict per symbol."""
    from data_engine.incremental_updater import incremental_update_bi5
    from engines.db import get_db
    started = datetime.now(timezone.utc)
    try:
        result = await incremental_update_bi5(symbol, "1m")
    except Exception as e:                                      # pragma: no cover
        return {
            "symbol": symbol,
            "status": "error",
            "error":  str(e)[:240],
            "ticks_added":      0,
            "files_scanned":    0,
            "files_ingested":   0,
        }

    # Write a one-shot summary row to bi5_ingest_log so the BI5 Health
    # surface picks it up immediately. Idempotency unaffected — the
    # per-file dedupe is on the file_key, which this summary row does
    # not carry.
    try:
        db = get_db()
        await db["bi5_ingest_log"].insert_one({
            "symbol":             symbol,
            "timestamp":          datetime.now(timezone.utc).isoformat(),
            "ingested_at":        datetime.now(timezone.utc).isoformat(),
            "source":             "scheduler",
            "ticks_added":        int(result.get("ticks_added", 0) or 0),
            "rows_added":         int(result.get("ticks_added", 0) or 0),
            "gaps_found":         0,
            "gaps_repaired":      0,
            "status":             "ok" if (result.get("files_ingested", 0) or 0) > 0 else "fetched-no-new",
            "latency_ms":         int(
                (datetime.now(timezone.utc) - started).total_seconds() * 1000
            ),
            "coverage_percent":   0.0,
            "health_score_reserved": None,
            "ingest_version":     "r1-v1",
            "live_lookback_days": 0,
            "backfill":           True,
        })
    except Exception as e:                                      # pragma: no cover
        logger.warning("summary row insert failed for %s: %s", symbol, e)

    return {
        "symbol":           symbol,
        "status":           "ok",
        "ticks_added":      int(result.get("ticks_added", 0) or 0),
        "files_scanned":    int(result.get("files_scanned", 0) or 0),
        "files_ingested":   int(result.get("files_ingested", 0) or 0),
        "range_after":      result.get("range_after"),
        "elapsed_seconds":  round(
            (datetime.now(timezone.utc) - started).total_seconds(), 2
        ),
    }


async def main(args: list[str]) -> int:
    explicit = [a for a in args if not a.startswith("-")]
    symbols = await _resolve_symbols(explicit if explicit else None)
    logger.info("backfilling %d symbol(s): %s", len(symbols), symbols)

    summaries: list[dict] = []
    for sym in symbols:
        logger.info("→ %s", sym)
        rep = await _backfill_one(sym)
        summaries.append(rep)
        logger.info(
            "  done · status=%s · ticks_added=%d · files_ingested=%d",
            rep.get("status"),
            rep.get("ticks_added", 0),
            rep.get("files_ingested", 0),
        )

    total_ticks = sum(s.get("ticks_added", 0) for s in summaries)
    total_files = sum(s.get("files_ingested", 0) for s in summaries)
    errors      = [s for s in summaries if s.get("status") == "error"]
    logger.info(
        "summary: symbols=%d · ticks_added=%d · files_ingested=%d · errors=%d",
        len(summaries), total_ticks, total_files, len(errors),
    )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
