"""
P0A — BI5 ingest orchestrator.

Wires the three building blocks into a single hour-by-hour pipeline:

    DukascopyBI5Adapter.fetch_hour
        ↓ (raw .bi5 bytes)
    BI5TickArchive.write                             [Tier 1: filesystem cache]
        ↓
    tick_aggregator.decode_and_aggregate              [decode + 1m OHLCV]
        ↓
    data_engine.data_manager._merge_rows(append_only) [Tier 2: market_data]

The runner walks ``[start_utc, end_utc)`` in hourly steps. For each hour it
checks the archive first (Tier-1 hit) before calling the adapter — this is
what gives idempotent re-runs essentially zero network cost.

Public surface:
    * ``BI5IngestRunner`` — class for tests / dependency injection.
    * ``run_bi5_ingest`` — module-level convenience used by the admin API.

TODO(P1 — Symbol Registry Promotion):
    The symbol-validation step at the top of ``run_for_symbol`` currently
    checks ``config.bi5_symbols.is_bi5_supported``. After P1 it should
    consult ``engines.market_universe`` for both *existence* AND *enabled*
    status (disabled = advisory-only, so we still allow ingest, just log
    a warning).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from config.bi5_symbols import get_bi5_symbol_spec, is_bi5_supported
from data_engine.adapters.base import BI5Adapter, normalize_hour_utc
from data_engine.adapters.dukascopy_bi5 import DukascopyBI5Adapter
from data_engine.data_manager import _merge_rows
from data_engine.market_calendar import is_bi5_session_active
from data_engine.tick_aggregator import (
    Bar1m,
    aggregate_ticks_to_1m,
    decode_bi5_hour,
)
from data_engine.tick_archive import BI5TickArchive
from engines.persistence_adapters.bi5_data_certification_store import (
    upsert_data_certification,
)
from engines.persistence_adapters.market_spread_store import (
    upsert_spread_bars,
)
from engines.spread_analyzer import rollup_spread_minutes
from engines.tick_validator import (
    DEFAULT_WEIGHTS,
    HourValidation,
    aggregate_window,
    validate_hour,
)

logger = logging.getLogger(__name__)

# Hard ceiling so a misconfigured request can't accidentally fan out for years.
MAX_HOURS_PER_RUN = 24 * 31  # ~1 month


@dataclass
class HourResult:
    hour_utc: datetime
    source: str
    bytes_archived: int
    cache_hit: bool
    ticks_decoded: int
    bars_emitted: int
    bars_inserted: int
    bars_matched: int
    spread_bars_emitted: int = 0
    spread_bars_upserted: int = 0
    # P1 data-cert writer wiring: per-hour validation record produced by
    # tick_validator.validate_hour. Always present once the hour was
    # successfully processed; aggregated post-loop into a BI5ScoreReport.
    validation: Optional[HourValidation] = None


@dataclass
class IngestReport:
    symbol: str
    source: str
    start_utc: datetime
    end_utc: datetime
    hours_total: int
    hours_succeeded: int
    hours_failed: int
    hours_downloaded: int
    hours_cached: int
    ticks_processed_total: int
    bars_generated_total: int
    bars_inserted_total: int
    bars_matched_total: int
    bytes_archived_total: int
    archive_root: str = ""
    archive_size_bytes: int = 0
    duration_seconds: float = 0.0
    spread_bars_emitted_total: int = 0
    spread_bars_upserted_total: int = 0
    # P1 data-cert writer: count of bi5_data_certification rows
    # upserted at end of run (0 when db handle is None or when
    # there were no validations to aggregate).
    data_cert_upserted: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "source": self.source,
            "from_date": self.start_utc.isoformat(),
            "to_date": self.end_utc.isoformat(),
            "start_utc": self.start_utc.isoformat(),
            "end_utc": self.end_utc.isoformat(),
            "hours_total": self.hours_total,
            "hours_succeeded": self.hours_succeeded,
            "hours_failed": self.hours_failed,
            "hours_downloaded": self.hours_downloaded,
            "hours_cached": self.hours_cached,
            "ticks_processed": self.ticks_processed_total,
            "bars_generated": self.bars_generated_total,
            "bars_inserted": self.bars_inserted_total,
            "bars_matched": self.bars_matched_total,
            "bytes_archived_total": self.bytes_archived_total,
            "archive_root": self.archive_root,
            "archive_size_bytes": self.archive_size_bytes,
            # Alias retained for downstream consumers / dashboards that expect
            # the shorter ``archive_size`` field. Mirrors archive_size_bytes 1:1.
            "archive_size": self.archive_size_bytes,
            "duration_seconds": round(self.duration_seconds, 3),
            "spread_bars_emitted_total": self.spread_bars_emitted_total,
            "spread_bars_upserted_total": self.spread_bars_upserted_total,
            "data_cert_upserted": self.data_cert_upserted,
            "errors": self.errors[:50],
        }


def _hours_between(start_utc: datetime, end_utc: datetime) -> List[datetime]:
    """Inclusive-of-start, exclusive-of-end list of normalized UTC hours."""
    start = normalize_hour_utc(start_utc)
    end = normalize_hour_utc(end_utc)
    if end <= start:
        return []
    hours = []
    cur = start
    while cur < end:
        hours.append(cur)
        cur = cur + timedelta(hours=1)
    return hours


def _bars_to_market_data_rows(bars: List[Bar1m]) -> List[Dict[str, Any]]:
    """Translate ``Bar1m`` → the dict schema used by ``data_manager._merge_rows``."""
    return [
        {
            "symbol":   b.symbol,
            "source":   b.source,            # "bi5"
            "timeframe": "1m",
            "timestamp": b.minute_utc.isoformat(),
            "open":     b.open,
            "high":     b.high,
            "low":      b.low,
            "close":    b.close,
            "volume":   b.volume,
        }
        for b in bars
    ]


class BI5IngestRunner:
    """Hour-by-hour BI5 ingest orchestrator."""

    def __init__(
        self,
        *,
        adapter: Optional[BI5Adapter] = None,
        archive: Optional[BI5TickArchive] = None,
        own_adapter: bool = True,
        db: Any = None,
    ) -> None:
        self._adapter = adapter or DukascopyBI5Adapter()
        self._archive = archive or BI5TickArchive()
        self._own_adapter = own_adapter and adapter is None
        # `db` is Phase-2 wiring for market_spread persistence. When
        # None, the runner skips spread upserts entirely — preserves
        # the P0A test contract and keeps the firewall clean for code
        # paths that don't want a Mongo dependency yet.
        self._db = db

    async def close(self) -> None:
        if self._own_adapter:
            await self._adapter.close()

    async def run_for_symbol(
        self,
        symbol: str,
        *,
        start_utc: datetime,
        end_utc: datetime,
        use_cache: bool = True,
    ) -> IngestReport:
        """Run the full Tier-1 → Tier-2 pipeline over ``[start_utc, end_utc)``.

        Hours that fail to download (transport error) are logged but do NOT
        abort the run — they show up in ``report.errors``. This is critical
        for long backfills where one bad hour shouldn't burn the rest.
        """
        # TODO(P1): swap this for engines.market_universe check.
        if not is_bi5_supported(symbol):
            raise ValueError(f"Symbol {symbol!r} is not BI5-supported")

        started_at = time.monotonic()
        spec = get_bi5_symbol_spec(symbol)
        hours = _hours_between(start_utc, end_utc)
        if not hours:
            return IngestReport(
                symbol=spec.symbol, source=self._adapter.source_id,
                start_utc=normalize_hour_utc(start_utc),
                end_utc=normalize_hour_utc(end_utc),
                hours_total=0, hours_succeeded=0, hours_failed=0,
                hours_downloaded=0, hours_cached=0,
                ticks_processed_total=0, bars_generated_total=0,
                bars_inserted_total=0, bars_matched_total=0,
                bytes_archived_total=0,
                archive_root=str(self._archive.root),
                archive_size_bytes=self._archive.symbol_size_bytes(
                    spec.symbol, self._adapter.source_id
                ),
                duration_seconds=time.monotonic() - started_at,
            )

        if len(hours) > MAX_HOURS_PER_RUN:
            raise ValueError(
                f"Refusing to ingest {len(hours)} hours in one call "
                f"(cap={MAX_HOURS_PER_RUN}). Break the window into chunks."
            )

        report = IngestReport(
            symbol=spec.symbol, source=self._adapter.source_id,
            start_utc=hours[0], end_utc=hours[-1] + timedelta(hours=1),
            hours_total=len(hours), hours_succeeded=0, hours_failed=0,
            hours_downloaded=0, hours_cached=0,
            ticks_processed_total=0, bars_generated_total=0,
            bars_inserted_total=0, bars_matched_total=0,
            bytes_archived_total=0,
            archive_root=str(self._archive.root),
        )

        # P1 data-cert writer: accumulate per-hour validations for
        # the post-loop aggregate_window → upsert_data_certification call.
        hour_validations: List[HourValidation] = []

        for hour in hours:
            try:
                hr = await self._process_one_hour(spec.symbol, hour, use_cache=use_cache)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "bi5.ingest.hour_failed symbol=%s hour=%s err=%s",
                    spec.symbol, hour.isoformat(), exc,
                )
                report.hours_failed += 1
                report.errors.append({
                    "hour_utc": hour.isoformat(),
                    "error": f"{type(exc).__name__}: {exc}",
                })
                # P1 data-cert writer + Option-A + G-1 calendar wiring:
                # calendar-classify fetch failures. Market-closed hours
                # (weekly forex window + G-1 hourly refinements: Fri
                # 21:00 UTC for FX retail wind-down, weekday 21:00 UTC
                # for metal daily settlement) where the upstream feed
                # returns no payload are an EXPECTED absence, not a
                # "missing" data signal. Classifying them as
                # ``expected_empty`` here keeps cert verdicts robust
                # on re-runs without an archive cache, and honest
                # about genuine in-session fetch failures.
                spec_mt = get_bi5_symbol_spec(spec.symbol).market_type
                if is_bi5_session_active(hour, spec_mt):
                    fail_status = "missing"
                else:
                    fail_status = "expected_empty"
                hour_validations.append(
                    validate_hour(None, hour_utc=hour, symbol=spec.symbol, status=fail_status)
                )
                continue

            report.hours_succeeded += 1
            if hr.cache_hit:
                report.hours_cached += 1
            else:
                report.hours_downloaded += 1
            report.bytes_archived_total += hr.bytes_archived
            report.ticks_processed_total += hr.ticks_decoded
            report.bars_generated_total += hr.bars_emitted
            report.bars_inserted_total += hr.bars_inserted
            report.bars_matched_total += hr.bars_matched
            report.spread_bars_emitted_total += hr.spread_bars_emitted
            report.spread_bars_upserted_total += hr.spread_bars_upserted
            if hr.validation is not None:
                hour_validations.append(hr.validation)

        # P1 data-cert writer: aggregate per-hour validations into a
        # BI5ScoreReport and (when a Mongo handle was injected) persist
        # it via the already-shipped upsert_data_certification adapter.
        # Gated on `self._db is not None` — preserves the P0A test
        # contract for `db=None` runners byte-identically.
        data_cert_upserted = 0
        if hour_validations:
            try:
                score_report = aggregate_window(
                    hour_validations, weights=DEFAULT_WEIGHTS,
                )
                if self._db is not None:
                    cert_res = await upsert_data_certification(
                        self._db, score_report,
                    )
                    data_cert_upserted = int(
                        cert_res.get("upserted", 0) + cert_res.get("modified", 0)
                    )
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "bi5.ingest.data_cert_failed symbol=%s err=%s",
                    spec.symbol, exc,
                )
                report.errors.append({
                    "stage": "data_cert",
                    "error": f"{type(exc).__name__}: {exc}",
                })
        report.data_cert_upserted = data_cert_upserted

        report.archive_size_bytes = self._archive.symbol_size_bytes(
            spec.symbol, self._adapter.source_id
        )
        report.duration_seconds = time.monotonic() - started_at

        logger.info(
            "bi5.ingest.done symbol=%s hours=%d ok=%d fail=%d "
            "downloaded=%d cached=%d ticks=%d bars_gen=%d "
            "bars_ins=%d bars_match=%d dur=%.2fs",
            spec.symbol, report.hours_total, report.hours_succeeded,
            report.hours_failed, report.hours_downloaded, report.hours_cached,
            report.ticks_processed_total, report.bars_generated_total,
            report.bars_inserted_total, report.bars_matched_total,
            report.duration_seconds,
        )
        return report

    async def _process_one_hour(
        self, symbol: str, hour_utc: datetime, *, use_cache: bool
    ) -> HourResult:
        source = self._adapter.source_id
        cache_hit = False
        payload: bytes

        if use_cache and self._archive.has(symbol, hour_utc, source):
            payload = self._archive.read(symbol, hour_utc, source)
            cache_hit = True
            bytes_archived = 0
        else:
            blob = await self._adapter.fetch_hour(symbol, hour_utc)
            write_res = self._archive.write(blob)
            payload = blob.payload
            bytes_archived = write_res.bytes_written

        bars = []
        spread_bars = []
        ticks = decode_bi5_hour(payload, hour_utc=hour_utc, spec=get_bi5_symbol_spec(symbol))
        # P1 data-cert writer + Option-A + G-1 calendar wiring: per-hour
        # validation record. Calendar-aware status classification —
        # market-closed hours (weekly forex window via is_trading_time,
        # plus G-1 hourly exclusions: Fri 21:00 UTC for FX retail
        # wind-down, weekday 21:00 UTC for metal daily settlement) are
        # tagged ``expected_empty`` so they do NOT collapse the
        # window's continuity sub-score in ``aggregate_window``.
        # Trading hours arrive as ``status="ok"``, which is the
        # pre-existing P1 contract. decode_bi5_hour raises on corrupt
        # payloads, which the outer try/except in the run loop catches
        # and records as a "missing" validation instead.
        #
        # NOTE: bars + spread persistence remain calendar-agnostic.
        # Any ticks present in a calendar-closed hour still flow into
        # market_data / market_spread; only the certification status
        # changes. This preserves Tier-2 byte-identity for any
        # downstream consumer that doesn't look at validation. The
        # market_type comes from BI5SymbolSpec (XAU → "metal"),
        # NOT from config.symbols.get_market_type (XAU → "forex"),
        # so XAU correctly picks up the daily-settlement rule.
        spec_mt = get_bi5_symbol_spec(symbol).market_type
        hour_is_open = is_bi5_session_active(hour_utc, spec_mt)
        if hour_is_open:
            hour_validation = validate_hour(
                ticks, hour_utc=hour_utc, symbol=symbol, status="ok",
            )
        else:
            hour_validation = validate_hour(
                None, hour_utc=hour_utc, symbol=symbol, status="expected_empty",
            )

        if ticks:
            bars = aggregate_ticks_to_1m(ticks, symbol=symbol)
            # P0B Phase 2 — derive per-minute spread OHLC from the same
            # tick stream. Pure function; only the upsert below touches
            # Mongo (and only when a db handle was injected).
            spread_bars = rollup_spread_minutes(ticks, symbol=symbol)
        if not bars:
            return HourResult(
                hour_utc=hour_utc, source=source,
                bytes_archived=bytes_archived, cache_hit=cache_hit,
                ticks_decoded=len(ticks),
                bars_emitted=0, bars_inserted=0, bars_matched=0,
                spread_bars_emitted=len(spread_bars),
                spread_bars_upserted=0,
                validation=hour_validation,
            )

        rows = _bars_to_market_data_rows(bars)
        merge = await _merge_rows(
            rows, symbol=symbol, source="bi5", timeframe="1m",
            append_only=True,
        )

        spread_upserted = 0
        if self._db is not None and spread_bars:
            res = await upsert_spread_bars(self._db, spread_bars)
            spread_upserted = int(res.get("upserted", 0) + res.get("modified", 0))

        return HourResult(
            hour_utc=hour_utc, source=source,
            bytes_archived=bytes_archived, cache_hit=cache_hit,
            ticks_decoded=len(ticks),
            bars_emitted=len(bars),
            bars_inserted=int(merge.get("upserted", 0)),
            bars_matched=int(merge.get("matched", 0)),
            spread_bars_emitted=len(spread_bars),
            spread_bars_upserted=spread_upserted,
            validation=hour_validation,
        )


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

async def run_bi5_ingest(
    symbol: str,
    *,
    start_utc: datetime,
    end_utc: datetime,
    use_cache: bool = True,
    adapter: Optional[BI5Adapter] = None,
    archive: Optional[BI5TickArchive] = None,
    db: Any = None,
) -> Dict[str, Any]:
    """One-shot helper used by ``POST /api/admin/bi5/run``."""
    runner = BI5IngestRunner(adapter=adapter, archive=archive, db=db)
    try:
        report = await runner.run_for_symbol(
            symbol, start_utc=start_utc, end_utc=end_utc, use_cache=use_cache,
        )
        return report.to_dict()
    finally:
        await runner.close()
