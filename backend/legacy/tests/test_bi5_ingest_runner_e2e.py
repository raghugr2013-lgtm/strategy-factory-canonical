"""P0A — End-to-end BI5 ingest pipeline tests.

Verifies the full Tier-1 (raw archive) + Tier-2 (1m bar derivation) flow:

    fake adapter → real BI5TickArchive(tmp) → real decoder/aggregator →
    monkeypatched _merge_rows (NO MongoDB)

And the public surface:

    POST /api/admin/bi5/run  (mounted on a minimal FastAPI app, auth
                              dependency overridden, ingest fn patched)

Network and MongoDB are NEVER touched. The aggregator/decoder are run
for real so the BI5 binary format contract stays verified end-to-end.
"""
from __future__ import annotations

import lzma
import struct
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.bi5_ingest import router as bi5_ingest_router
from auth_utils import require_admin
from data_engine import bi5_ingest_runner as runner_module
from data_engine.adapters.base import BI5Adapter, BI5HourBlob, normalize_hour_utc
from data_engine.bi5_ingest_runner import (
    BI5IngestRunner,
    IngestReport,
    run_bi5_ingest,
)
from data_engine.tick_archive import BI5TickArchive

# ---------------------------------------------------------------------------
# Synthetic BI5 payload helpers
# ---------------------------------------------------------------------------

# Tick layout matches data_engine.tick_aggregator._TICK_STRUCT: ">IIIff"
_TICK_STRUCT = struct.Struct(">IIIff")


def _build_bi5_payload(
    ticks: List[tuple],
    *,
    price_multiplier: float = 1e5,
) -> bytes:
    """Pack ``(ms_offset, bid, ask, bid_vol, ask_vol)`` tuples into a real
    LZMA-Alone-compressed BI5 hour blob.

    The aggregator decodes with ``lzma.FORMAT_ALONE`` so we MUST compress
    with the same format or the round-trip will fail with LZMAError.
    """
    raw_parts = []
    for ms_offset, bid, ask, bid_vol, ask_vol in ticks:
        bid_fp = int(round(bid * price_multiplier))
        ask_fp = int(round(ask * price_multiplier))
        raw_parts.append(_TICK_STRUCT.pack(
            int(ms_offset), int(ask_fp), int(bid_fp), float(ask_vol), float(bid_vol),
        ))
    raw = b"".join(raw_parts)
    return lzma.compress(raw, format=lzma.FORMAT_ALONE)


class _FakeAdapter(BI5Adapter):
    """In-memory adapter that returns pre-baked payloads keyed by (symbol, hour).

    Records the hours it was asked for so tests can assert cache vs network
    behaviour.
    """

    source_id = "dukascopy"

    def __init__(self, payloads: Dict[datetime, bytes]) -> None:
        self._payloads = {normalize_hour_utc(k): v for k, v in payloads.items()}
        self.fetch_calls: List[datetime] = []
        self.closed = False

    async def fetch_hour(self, symbol: str, hour_utc: datetime) -> BI5HourBlob:
        hour_utc = normalize_hour_utc(hour_utc)
        self.fetch_calls.append(hour_utc)
        payload = self._payloads.get(hour_utc, b"")
        return BI5HourBlob(
            symbol=symbol, hour_utc=hour_utc, payload=payload, source=self.source_id,
        )

    async def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Mongo write-path interception
# ---------------------------------------------------------------------------

class _MergeRowsSpy:
    """Drop-in for ``data_engine.data_manager._merge_rows``.

    Captures every batch of rows handed to it so the test can assert what
    the runner intends to write to ``market_data`` — without actually
    needing a MongoDB connection.
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def __call__(
        self,
        rows: list,
        symbol: str,
        source: str,
        timeframe: str,
        *,
        append_only: bool = False,
    ) -> dict:
        self.calls.append({
            "rows": list(rows),
            "symbol": symbol,
            "source": source,
            "timeframe": timeframe,
            "append_only": append_only,
        })
        return {
            "upserted": len(rows),
            "matched": 0,
            "intra_batch_duplicates": 0,
            "append_only": append_only,
        }


# ---------------------------------------------------------------------------
# Runner E2E — happy path + cache hit + report shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runner_e2e_two_hours_one_with_ticks_one_empty(
    tmp_path, monkeypatch
):
    """Full pipeline over a 2-hour window: hour 0 has ticks, hour 1 is empty."""
    archive = BI5TickArchive(root=str(tmp_path))
    hour0 = datetime(2024, 1, 2, 7, tzinfo=timezone.utc)
    hour1 = hour0 + timedelta(hours=1)

    # Hour 0: 3 ticks across two minutes; price moves 1.10000 → 1.10005.
    payload0 = _build_bi5_payload(
        [
            # (ms_offset_from_hour, bid, ask, bid_vol, ask_vol)
            (    0, 1.10000, 1.10001, 1.0, 1.0),
            (30_000, 1.10003, 1.10004, 1.0, 1.0),  # same minute (00)
            (75_000, 1.10005, 1.10006, 2.0, 2.0),  # next minute (01)
        ],
        price_multiplier=1e5,
    )
    # Hour 1: empty payload → "market closed / no ticks" path.
    adapter = _FakeAdapter({hour0: payload0, hour1: b""})

    spy = _MergeRowsSpy()
    monkeypatch.setattr(runner_module, "_merge_rows", spy)

    runner = BI5IngestRunner(adapter=adapter, archive=archive)
    try:
        report = await runner.run_for_symbol(
            "EURUSD", start_utc=hour0, end_utc=hour1 + timedelta(hours=1),
        )
    finally:
        await runner.close()

    # ----- report shape -------------------------------------------------
    assert isinstance(report, IngestReport)
    assert report.symbol == "EURUSD"
    assert report.source == "dukascopy"
    assert report.hours_total == 2
    assert report.hours_succeeded == 2
    assert report.hours_failed == 0
    assert report.hours_downloaded == 2
    assert report.hours_cached == 0
    # Hour 0 produced ticks; hour 1 was empty.
    assert report.ticks_processed_total == 3
    assert report.bars_generated_total == 2  # minute 00 + minute 01
    assert report.bars_inserted_total == 2
    assert report.bytes_archived_total == len(payload0)  # hour 1 was 0 bytes
    assert report.archive_size_bytes == len(payload0)

    # ----- spy: rows handed to Mongo write path -------------------------
    assert len(spy.calls) == 1, "only hour 0 had bars to write"
    call = spy.calls[0]
    assert call["symbol"] == "EURUSD"
    assert call["source"] == "bi5"
    assert call["timeframe"] == "1m"
    assert call["append_only"] is True
    rows = call["rows"]
    assert len(rows) == 2
    # Row schema parity with data_manager._merge_rows expectation.
    for row in rows:
        assert set(row) >= {
            "symbol", "source", "timeframe", "timestamp",
            "open", "high", "low", "close", "volume",
        }
        assert row["source"] == "bi5"
        assert row["timeframe"] == "1m"
        # OHLC sanity: low ≤ open,close ≤ high.
        assert row["low"] <= row["open"] <= row["high"]
        assert row["low"] <= row["close"] <= row["high"]

    # ----- archive: files actually landed on disk -----------------------
    assert archive.has("EURUSD", hour0, source="dukascopy")
    assert archive.read("EURUSD", hour0, source="dukascopy") == payload0
    # Empty-hour file is still cached (so we don't re-fetch closed hours).
    assert archive.has("EURUSD", hour1, source="dukascopy")
    assert archive.read("EURUSD", hour1, source="dukascopy") == b""


@pytest.mark.asyncio
async def test_runner_e2e_second_run_is_cache_hit_no_network(tmp_path, monkeypatch):
    """Re-running the same window must serve from disk; adapter not called."""
    archive = BI5TickArchive(root=str(tmp_path))
    hour0 = datetime(2024, 1, 2, 7, tzinfo=timezone.utc)
    payload0 = _build_bi5_payload(
        [(0, 1.10000, 1.10001, 1.0, 1.0)], price_multiplier=1e5,
    )

    # First run — populates archive.
    adapter1 = _FakeAdapter({hour0: payload0})
    spy = _MergeRowsSpy()
    monkeypatch.setattr(runner_module, "_merge_rows", spy)

    runner1 = BI5IngestRunner(adapter=adapter1, archive=archive)
    try:
        r1 = await runner1.run_for_symbol(
            "EURUSD", start_utc=hour0, end_utc=hour0 + timedelta(hours=1),
        )
    finally:
        await runner1.close()
    assert r1.hours_downloaded == 1
    assert r1.hours_cached == 0
    assert len(adapter1.fetch_calls) == 1

    # Second run — must hit the cache; new adapter records ZERO calls.
    adapter2 = _FakeAdapter({})  # would raise if called
    runner2 = BI5IngestRunner(adapter=adapter2, archive=archive)
    try:
        r2 = await runner2.run_for_symbol(
            "EURUSD", start_utc=hour0, end_utc=hour0 + timedelta(hours=1),
        )
    finally:
        await runner2.close()

    assert adapter2.fetch_calls == [], "cache hit must NOT call the adapter"
    assert r2.hours_cached == 1
    assert r2.hours_downloaded == 0
    assert r2.bytes_archived_total == 0  # nothing newly archived
    assert r2.archive_size_bytes == len(payload0)


@pytest.mark.asyncio
async def test_runner_to_dict_exposes_archive_size_alias(tmp_path, monkeypatch):
    """Strict requirement: report dict must carry the ``archive_size`` alias."""
    archive = BI5TickArchive(root=str(tmp_path))
    hour0 = datetime(2024, 1, 2, 7, tzinfo=timezone.utc)
    payload0 = _build_bi5_payload(
        [(0, 1.10000, 1.10001, 1.0, 1.0)], price_multiplier=1e5,
    )
    adapter = _FakeAdapter({hour0: payload0})
    spy = _MergeRowsSpy()
    monkeypatch.setattr(runner_module, "_merge_rows", spy)

    d = await run_bi5_ingest(
        "EURUSD", start_utc=hour0, end_utc=hour0 + timedelta(hours=1),
        adapter=adapter, archive=archive,
    )
    assert "archive_size" in d, f"missing alias; keys={sorted(d)}"
    assert "archive_size_bytes" in d
    assert d["archive_size"] == d["archive_size_bytes"]
    assert d["archive_size"] == len(payload0)
    # Sanity: the report-dict has the documented top-level fields.
    expected_keys = {
        "symbol", "source", "from_date", "to_date", "start_utc", "end_utc",
        "hours_total", "hours_succeeded", "hours_failed",
        "hours_downloaded", "hours_cached",
        "ticks_processed", "bars_generated", "bars_inserted", "bars_matched",
        "bytes_archived_total", "archive_root",
        "archive_size", "archive_size_bytes",
        "duration_seconds", "errors",
    }
    assert expected_keys.issubset(d), f"missing: {expected_keys - set(d)}"


@pytest.mark.asyncio
async def test_runner_rejects_unsupported_symbol(tmp_path):
    """Symbol-validation gate is still enforced inside the runner."""
    runner = BI5IngestRunner(
        adapter=_FakeAdapter({}),
        archive=BI5TickArchive(root=str(tmp_path)),
    )
    try:
        with pytest.raises(ValueError, match="not BI5-supported"):
            await runner.run_for_symbol(
                "ZZZZZZ",
                start_utc=datetime(2024, 1, 2, 7, tzinfo=timezone.utc),
                end_utc=datetime(2024, 1, 2, 8, tzinfo=timezone.utc),
            )
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_runner_continues_on_per_hour_failure(tmp_path, monkeypatch):
    """A transient failure on one hour must NOT abort the whole run."""
    archive = BI5TickArchive(root=str(tmp_path))
    hour0 = datetime(2024, 1, 2, 7, tzinfo=timezone.utc)
    hour1 = hour0 + timedelta(hours=1)
    payload1 = _build_bi5_payload(
        [(0, 1.10000, 1.10001, 1.0, 1.0)], price_multiplier=1e5,
    )

    class _FlakyAdapter(_FakeAdapter):
        async def fetch_hour(self, symbol, hour_utc):
            hour_utc = normalize_hour_utc(hour_utc)
            self.fetch_calls.append(hour_utc)
            if hour_utc == hour0:
                raise RuntimeError("simulated transport failure")
            return BI5HourBlob(
                symbol=symbol, hour_utc=hour_utc,
                payload=self._payloads.get(hour_utc, b""),
                source=self.source_id,
            )

    adapter = _FlakyAdapter({hour1: payload1})
    spy = _MergeRowsSpy()
    monkeypatch.setattr(runner_module, "_merge_rows", spy)

    runner = BI5IngestRunner(adapter=adapter, archive=archive)
    try:
        report = await runner.run_for_symbol(
            "EURUSD", start_utc=hour0, end_utc=hour1 + timedelta(hours=1),
        )
    finally:
        await runner.close()

    assert report.hours_total == 2
    assert report.hours_succeeded == 1
    assert report.hours_failed == 1
    assert len(report.errors) == 1
    assert report.errors[0]["hour_utc"] == hour0.isoformat()
    assert "RuntimeError" in report.errors[0]["error"]
    # Surviving hour still produced its bar.
    assert report.bars_inserted_total == 1


# ---------------------------------------------------------------------------
# FastAPI endpoint — POST /api/admin/bi5/run
# ---------------------------------------------------------------------------

def _build_test_app() -> FastAPI:
    """Minimal FastAPI app exposing ONLY the bi5_ingest router under /api.

    Importing ``server`` triggers the full app boot (Mongo client, all
    routers, lifespan hooks) — too heavy and DB-dependent for unit tests.
    Mounting the single router under the production prefix gives us a
    faithful path (``/api/admin/bi5/run``) without the baggage.
    """
    app = FastAPI()
    app.include_router(bi5_ingest_router, prefix="/api")
    # Bypass JWT — these tests are about the endpoint contract, not auth.
    app.dependency_overrides[require_admin] = lambda: {
        "id": "test-admin", "role": "admin", "email": "admin@test.local",
    }
    return app


def test_endpoint_happy_path_returns_report(monkeypatch):
    """POST /api/admin/bi5/run → 200 with structured report (ingest patched)."""
    fake_report = {
        "symbol": "EURUSD",
        "source": "dukascopy",
        "from_date": "2024-01-02T07:00:00+00:00",
        "to_date": "2024-01-02T08:00:00+00:00",
        "start_utc": "2024-01-02T07:00:00+00:00",
        "end_utc": "2024-01-02T08:00:00+00:00",
        "hours_total": 1, "hours_succeeded": 1, "hours_failed": 0,
        "hours_downloaded": 1, "hours_cached": 0,
        "ticks_processed": 3, "bars_generated": 2,
        "bars_inserted": 2, "bars_matched": 0,
        "bytes_archived_total": 123,
        "archive_root": "/tmp/bi5",
        "archive_size_bytes": 123,
        "archive_size": 123,
        "duration_seconds": 0.05,
        "errors": [],
    }

    captured: Dict[str, Any] = {}

    async def _fake_run_bi5_ingest(symbol, *, start_utc, end_utc, use_cache, db=None):
        captured["symbol"] = symbol
        captured["start_utc"] = start_utc
        captured["end_utc"] = end_utc
        captured["use_cache"] = use_cache
        captured["db_passed"] = db is not None
        return fake_report

    # Patch the symbol the endpoint module imported, not the source module.
    monkeypatch.setattr("api.bi5_ingest.run_bi5_ingest", _fake_run_bi5_ingest)

    app = _build_test_app()
    client = TestClient(app)

    resp = client.post("/api/admin/bi5/run", json={
        "symbol": "eurusd",  # lowercase → normalized by validator
        "start_utc": "2024-01-02T07:00:00Z",
        "end_utc": "2024-01-02T08:00:00Z",
        "use_cache": True,
    })

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["report"] == fake_report
    assert "archive_size" in body["report"]
    assert body["report"]["archive_size"] == body["report"]["archive_size_bytes"]

    # Ensure the endpoint forwarded normalized inputs to the runner.
    assert captured["symbol"] == "EURUSD"
    assert captured["start_utc"].tzinfo is not None
    assert captured["end_utc"] > captured["start_utc"]
    assert captured["use_cache"] is True


def test_endpoint_rejects_unsupported_symbol(monkeypatch):
    """Symbol not in BI5 registry → 400 BadRequest."""
    # run_bi5_ingest must NOT be reached.
    async def _boom(*a, **kw):  # pragma: no cover
        raise AssertionError("run_bi5_ingest must not be called for invalid symbol")

    monkeypatch.setattr("api.bi5_ingest.run_bi5_ingest", _boom)

    client = TestClient(_build_test_app())
    resp = client.post("/api/admin/bi5/run", json={
        "symbol": "ZZZZZZ",
        "start_utc": "2024-01-02T07:00:00Z",
        "end_utc": "2024-01-02T08:00:00Z",
    })
    assert resp.status_code == 400
    assert "not BI5-supported" in resp.json()["detail"]


def test_endpoint_rejects_inverted_window():
    """end_utc <= start_utc → 400."""
    client = TestClient(_build_test_app())
    resp = client.post("/api/admin/bi5/run", json={
        "symbol": "EURUSD",
        "start_utc": "2024-01-02T08:00:00Z",
        "end_utc": "2024-01-02T07:00:00Z",
    })
    assert resp.status_code == 400
    assert "strictly greater" in resp.json()["detail"]


def test_endpoint_rejects_window_over_cap():
    """Window > MAX_HOURS_PER_RUN → 400 with explicit message."""
    client = TestClient(_build_test_app())
    resp = client.post("/api/admin/bi5/run", json={
        "symbol": "EURUSD",
        "start_utc": "2024-01-02T00:00:00Z",
        "end_utc": "2024-04-02T00:00:00Z",  # ~3 months
    })
    assert resp.status_code == 400
    assert "exceeds per-run cap" in resp.json()["detail"]


def test_endpoint_rejects_bad_iso():
    """Malformed ISO timestamp → 400 with field-specific error."""
    client = TestClient(_build_test_app())
    resp = client.post("/api/admin/bi5/run", json={
        "symbol": "EURUSD",
        "start_utc": "not-a-timestamp",
        "end_utc": "2024-01-02T08:00:00Z",
    })
    assert resp.status_code == 400
    assert "start_utc" in resp.json()["detail"]


def test_endpoint_translates_runner_value_error_to_400(monkeypatch):
    """A ``ValueError`` from the runner must surface as HTTP 400, not 500."""
    async def _raises(*a, **kw):
        raise ValueError("synthetic registry rejection")
    monkeypatch.setattr("api.bi5_ingest.run_bi5_ingest", _raises)

    client = TestClient(_build_test_app())
    resp = client.post("/api/admin/bi5/run", json={
        "symbol": "EURUSD",
        "start_utc": "2024-01-02T07:00:00Z",
        "end_utc": "2024-01-02T08:00:00Z",
    })
    assert resp.status_code == 400
    assert "synthetic registry rejection" in resp.json()["detail"]


def test_endpoint_lists_supported_symbols():
    """GET /api/admin/bi5/symbols → registry snapshot (P1 will swap source)."""
    client = TestClient(_build_test_app())
    resp = client.get("/api/admin/bi5/symbols")
    assert resp.status_code == 200
    syms = resp.json()["symbols"]
    assert "EURUSD" in syms
    # Sorted, deduped, all uppercase.
    assert syms == sorted(set(syms))
    assert all(s == s.upper() for s in syms)
