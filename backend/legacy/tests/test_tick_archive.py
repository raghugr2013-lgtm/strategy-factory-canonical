"""P0A — BI5TickArchive unit tests.

We exercise the Tier-1 raw-bytes archive on an isolated tmp_path. The
archive's contract is:

* ``path_for`` builds ``<root>/<source>/<SYMBOL>/<YYYY>/<MM>/<DD>/<HH>h_ticks.bi5``
* ``write`` is atomic + idempotent + reports byte size
* ``has`` / ``read`` round-trip the payload faithfully
* ``symbol_size_bytes`` sums only the .bi5 files for one (source, symbol)
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path


from data_engine.adapters.base import BI5HourBlob
from data_engine.tick_archive import BI5TickArchive


def _blob(payload: bytes, hour: datetime = datetime(2024, 1, 2, 7, tzinfo=timezone.utc)) -> BI5HourBlob:
    return BI5HourBlob(symbol="EURUSD", hour_utc=hour, payload=payload, source="dukascopy")


def test_path_layout_is_source_symbol_y_m_d_hh(tmp_path: Path):
    archive = BI5TickArchive(root=tmp_path)
    hour = datetime(2024, 3, 2, 5, tzinfo=timezone.utc)
    p = archive.path_for("EURUSD", hour, source="dukascopy")
    # Approved archive spec (see ``tick_archive`` module docstring):
    #   {root}/{source}/{SYMBOL}/{YYYY}/{MM:02d}/{DD:02d}/{HH:02d}h_ticks.bi5
    # MM is 1-indexed for human readability — Dukascopy's 0-indexed URL
    # convention stays inside the HTTP adapter only.
    assert p.is_absolute()
    assert p.suffix == ".bi5"
    parts = p.relative_to(tmp_path).parts
    assert parts[0] == "dukascopy"
    assert parts[1] == "EURUSD"
    # Year then month (1-indexed) then day then hour file
    assert parts[2] == "2024"
    assert parts[3] == "03"  # 1-indexed (March)
    assert parts[4] == "02"
    assert parts[5] == "05h_ticks.bi5"


def test_write_then_has_then_read_round_trip(tmp_path: Path):
    archive = BI5TickArchive(root=tmp_path)
    payload = b"\x01\x02\x03"
    res = archive.write(_blob(payload))
    assert res.bytes_written == 3
    assert res.was_new is True

    assert archive.has("EURUSD", datetime(2024, 1, 2, 7, tzinfo=timezone.utc), source="dukascopy")
    got = archive.read("EURUSD", datetime(2024, 1, 2, 7, tzinfo=timezone.utc), source="dukascopy")
    assert got == payload


def test_write_is_idempotent_when_payload_unchanged(tmp_path: Path):
    archive = BI5TickArchive(root=tmp_path)
    blob = _blob(b"abc")
    r1 = archive.write(blob)
    r2 = archive.write(blob)
    assert r1.was_new is True
    assert r2.was_new is False
    # Bytes still readable and identical.
    assert archive.read("EURUSD", blob.hour_utc, source="dukascopy") == b"abc"


def test_symbol_size_bytes_sums_only_target_symbol(tmp_path: Path):
    archive = BI5TickArchive(root=tmp_path)
    archive.write(_blob(b"AAA", datetime(2024, 1, 2, 7, tzinfo=timezone.utc)))
    archive.write(_blob(b"BBBB", datetime(2024, 1, 2, 8, tzinfo=timezone.utc)))
    # Different symbol → must NOT be counted.
    other = BI5HourBlob(
        symbol="GBPUSD",
        hour_utc=datetime(2024, 1, 2, 8, tzinfo=timezone.utc),
        payload=b"ZZZZZZZZ",
        source="dukascopy",
    )
    archive.write(other)

    assert archive.symbol_size_bytes("EURUSD", "dukascopy") == 3 + 4
    assert archive.symbol_size_bytes("GBPUSD", "dukascopy") == 8


def test_symbol_size_bytes_returns_zero_for_unknown(tmp_path: Path):
    archive = BI5TickArchive(root=tmp_path)
    assert archive.symbol_size_bytes("EURUSD", "dukascopy") == 0
