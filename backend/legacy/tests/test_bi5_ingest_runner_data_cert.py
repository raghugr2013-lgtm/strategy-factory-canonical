"""P1 data-cert writer tests for the BI5 ingest runner.

Verifies that the additive wiring of `tick_validator.validate_hour` →
`aggregate_window` → `upsert_data_certification` is correctly invoked
during a full BI5 ingest run, and that the P0A `db=None` contract is
preserved byte-identically when no Mongo handle is injected.

Uses mongomock_motor for the Mongo side and stub adapters for the
Dukascopy side — same pattern as `tests/test_p0b_phase4_e2e.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

import pytest
from mongomock_motor import AsyncMongoMockClient

from data_engine.adapters.base import BI5Adapter, BI5HourBlob, normalize_hour_utc
from data_engine.bi5_ingest_runner import BI5IngestRunner, run_bi5_ingest
from data_engine.tick_archive import BI5TickArchive


class _StubAdapter(BI5Adapter):
    """Returns a deterministic synthetic .bi5 payload per requested hour."""

    source_id = "stub_bi5"

    def __init__(self, failing_hours: Optional[set] = None) -> None:
        self._failing_hours = failing_hours or set()
        self._calls = 0

    async def fetch_hour(self, symbol: str, hour_utc: datetime) -> BI5HourBlob:
        self._calls += 1
        hu = normalize_hour_utc(hour_utc)
        if hu in self._failing_hours:
            raise RuntimeError(f"stubbed transient failure at {hu.isoformat()}")
        # A minimal synthetic non-empty payload — the decoder will return [] for
        # an unrecognised blob, which the runner accepts as a zero-tick hour.
        # That's the desired path for this test: validate_hour records the
        # hour, but no bars get persisted.
        payload = b"\x00" * 16
        return BI5HourBlob(
            symbol=symbol, source=self.source_id, hour_utc=hu, payload=payload,
        )

    async def close(self) -> None:
        return None


def _archive(tmp_path) -> BI5TickArchive:
    return BI5TickArchive(root=tmp_path / "bi5")


def _hours(start: str, end: str) -> List[datetime]:
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    out = []
    cur = s
    while cur < e:
        out.append(cur)
        from datetime import timedelta
        cur = cur + timedelta(hours=1)
    return out


# -----------------------------------------------------------------------------
# Test 1 — db=None preserves the P0A contract
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_db_none_keeps_p0a_contract(tmp_path):
    runner = BI5IngestRunner(
        adapter=_StubAdapter(), archive=_archive(tmp_path), db=None,
    )
    report = await runner.run_for_symbol(
        "EURUSD",
        start_utc=datetime(2026, 5, 1, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 1, 3, tzinfo=timezone.utc),
        use_cache=False,
    )
    await runner.close()
    # Regression guard: no Mongo handle => no cert upsert
    assert report.data_cert_upserted == 0
    assert report.spread_bars_upserted_total == 0


# -----------------------------------------------------------------------------
# Test 2 — db handle writes exactly one cert per symbol per window
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_db_handle_writes_one_cert_per_symbol(tmp_path):
    client = AsyncMongoMockClient()
    db = client["test_p1_data_cert"]
    runner = BI5IngestRunner(
        adapter=_StubAdapter(), archive=_archive(tmp_path), db=db,
    )
    report = await runner.run_for_symbol(
        "EURUSD",
        start_utc=datetime(2026, 5, 1, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 1, 5, tzinfo=timezone.utc),
        use_cache=False,
    )
    await runner.close()
    assert report.data_cert_upserted == 1
    cnt = await db["bi5_data_certification"].count_documents({})
    assert cnt == 1
    doc = await db["bi5_data_certification"].find_one({})
    assert doc["symbol"] == "EURUSD"
    assert "verdict" in doc
    assert "bi5_score" in doc
    assert "subscores" in doc


# -----------------------------------------------------------------------------
# Test 3 — re-running the same window is idempotent
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idempotent_rerun_upserts_same_key(tmp_path):
    client = AsyncMongoMockClient()
    db = client["test_p1_idempotent"]
    archive = _archive(tmp_path)
    args = dict(
        start_utc=datetime(2026, 5, 1, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 1, 3, tzinfo=timezone.utc),
        use_cache=False,
    )

    r1 = BI5IngestRunner(adapter=_StubAdapter(), archive=archive, db=db)
    await r1.run_for_symbol("EURUSD", **args)
    await r1.close()

    r2 = BI5IngestRunner(adapter=_StubAdapter(), archive=archive, db=db)
    await r2.run_for_symbol("EURUSD", **args)
    await r2.close()

    cnt = await db["bi5_data_certification"].count_documents({})
    assert cnt == 1  # idempotent — upsert key (symbol, window_start, window_end)


# -----------------------------------------------------------------------------
# Test 4 — partial fetch failures propagate honestly into the cert
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partial_failure_propagates_to_cert(tmp_path):
    # Fail half the hours
    hrs = _hours("2026-05-01T00:00:00+00:00", "2026-05-01T06:00:00+00:00")
    failing = set(hrs[::2])  # every other hour
    client = AsyncMongoMockClient()
    db = client["test_p1_partial"]
    runner = BI5IngestRunner(
        adapter=_StubAdapter(failing_hours=failing),
        archive=_archive(tmp_path),
        db=db,
    )
    report = await runner.run_for_symbol(
        "EURUSD",
        start_utc=hrs[0],
        end_utc=datetime(2026, 5, 1, 6, tzinfo=timezone.utc),
        use_cache=False,
    )
    await runner.close()
    assert report.hours_failed > 0
    assert report.data_cert_upserted == 1
    doc = await db["bi5_data_certification"].find_one({})
    # With half the hours missing, coverage must be < 1.0 → cert verdict
    # should NOT be the strongest pass tier.
    assert doc["subscores"]["cov"] < 1.0


# -----------------------------------------------------------------------------
# Test 5 — module helper passes db through correctly
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_run_bi5_ingest_helper_with_db(tmp_path):
    client = AsyncMongoMockClient()
    db = client["test_p1_helper"]
    rep = await run_bi5_ingest(
        "EURUSD",
        start_utc=datetime(2026, 5, 1, tzinfo=timezone.utc),
        end_utc=datetime(2026, 5, 1, 3, tzinfo=timezone.utc),
        use_cache=False,
        adapter=_StubAdapter(),
        archive=_archive(tmp_path),
        db=db,
    )
    assert rep["data_cert_upserted"] == 1
    cnt = await db["bi5_data_certification"].count_documents({})
    assert cnt == 1
