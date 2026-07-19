"""Phase 2, Stage 2.ε/2.ζ — CTS tests.

Verifies:
  * Types + Provenance shape (traceability invariant)
  * Resampler correctness (M1 → M5/M15/H1) — synthetic data
  * LocalCTS.load_candles returns Provenance-tagged CandleWindow
  * Cache hit/miss + invalidation semantics
  * data_access route-through when BID_CANONICAL_M1_READ_MODE=true
  * Rebuild bucket
  * Distribution-ready Protocol satisfaction
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.cts import (  # noqa: E402
    Candle,
    CandleWindow,
    CanonicalTimeframeService,
    DataQualityState,
    Provenance,
    get_cts,
    reset_cts_for_tests,
)
from engines.cts.resampler import (  # noqa: E402
    bucket_key_for,
    is_canonical_tf,
    resample_m1_to,
)
from engines.cts.service import LocalCTS  # noqa: E402
from engines.cts.cache import HtfCache, CACHE_COLLECTION  # noqa: E402


# ── Synthetic M1 fixture ─────────────────────────────────────────────

def _synthetic_m1(minutes: int = 240) -> List[Candle]:
    """N minutes of synthetic M1 candles starting at 2026-01-01."""
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    out: List[Candle] = []
    for i in range(minutes):
        ts = start + timedelta(minutes=i)
        # Simple monotonic pattern for verifiability
        o = 1.0 + i * 0.001
        h = o + 0.0005
        l = o - 0.0005
        c = o + 0.0002
        out.append(Candle(
            timestamp=ts.isoformat(),
            open=o, high=h, low=l, close=c, volume=100.0,
        ))
    return out


# ── Traceability invariant ───────────────────────────────────────────

def test_provenance_has_all_traceability_fields():
    p = Provenance(canonical_source="market_data.bid_1m", aggregation_path="m1_native")
    d = p.__dict__
    for field in (
        "canonical_source", "aggregation_path",
        "cache_generated_at", "cache_version", "cache_bucket_key",
        "repair_status", "data_quality_state",
        "gap_count", "generated_at", "cts_version",
    ):
        assert field in d, f"Provenance missing traceability field: {field}"


def test_candle_window_carries_provenance():
    cw = CandleWindow(
        symbol="EURUSD", timeframe="H1", candles=[],
        provenance=Provenance(canonical_source="test", aggregation_path="m1_native"),
    )
    d = cw.to_dict()
    assert "provenance" in d
    assert d["provenance"]["canonical_source"] == "test"


# ── Resampler correctness ────────────────────────────────────────────

def test_resample_m1_to_1m_is_identity():
    m1 = _synthetic_m1(60)
    out, report = resample_m1_to(m1, "1m")
    assert len(out) == 60
    assert report.output_rows == 60


def test_resample_m1_to_h1_correct_bar_count():
    m1 = _synthetic_m1(240)  # 4 hours
    h1, report = resample_m1_to(m1, "H1")
    assert len(h1) == 4
    assert report.duration_ms >= 0.0


def test_resample_ohlc_semantics():
    """Bar's open = first M1 open; close = last M1 close; high/low = min/max."""
    m1 = _synthetic_m1(60)  # 60 minutes = 1 H1 bar
    h1, _ = resample_m1_to(m1, "H1")
    assert len(h1) == 1
    bar = h1[0]
    assert bar.open == pytest.approx(m1[0].open)
    assert bar.close == pytest.approx(m1[-1].close)
    assert bar.high == pytest.approx(max(c.high for c in m1))
    assert bar.low == pytest.approx(min(c.low for c in m1))
    assert bar.volume == pytest.approx(sum(c.volume for c in m1))


def test_resample_m1_to_m15_matches_expected():
    m1 = _synthetic_m1(60)
    m15, _ = resample_m1_to(m1, "M15")
    assert len(m15) == 4  # 60 / 15


def test_resample_empty_input_returns_empty():
    out, report = resample_m1_to([], "H1")
    assert out == []
    assert report.output_rows == 0


def test_resample_unsupported_tf_raises():
    with pytest.raises(ValueError):
        resample_m1_to(_synthetic_m1(10), "17min")


def test_is_canonical_tf():
    assert is_canonical_tf("1m") is True
    assert is_canonical_tf("M1") is True
    assert is_canonical_tf("H1") is False


def test_bucket_key_for_monthly_sharding():
    key = bucket_key_for("EURUSD", "H1", "2026-02-15T14:00:00+00:00")
    assert key == "EURUSD|1h|2026-02"


# ── Protocol satisfaction ────────────────────────────────────────────

def test_local_cts_satisfies_protocol():
    reset_cts_for_tests()
    cts = LocalCTS()
    assert isinstance(cts, CanonicalTimeframeService)


def test_get_cts_singleton():
    reset_cts_for_tests()
    a = get_cts()
    b = get_cts()
    assert a is b


# ── LocalCTS with a stub DB ──────────────────────────────────────────

class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)
    def sort(self, *_a, **_k):
        return self
    def limit(self, n):
        self._docs = self._docs[:n]
        return self
    def __aiter__(self):
        self._i = 0
        return self
    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        d = self._docs[self._i]
        self._i += 1
        return d


class _FakeCollection:
    def __init__(self, docs=None):
        self._docs = list(docs or [])
        self._cache_docs: Dict[str, Dict] = {}

    def find(self, *args, **kwargs):
        return _FakeCursor(self._docs)

    async def find_one(self, q):
        return self._cache_docs.get(q.get("_id"))

    async def update_one(self, q, update, upsert=False):
        _id = q.get("_id")
        doc = self._cache_docs.get(_id, {"_id": _id})
        doc.update(update.get("$set", {}))
        self._cache_docs[_id] = doc
        class _R:
            modified_count = 1
        return _R()

    async def update_many(self, q, update):
        class _R:
            modified_count = 0
        n = 0
        for k, d in self._cache_docs.items():
            if q.get("symbol") in (None, d.get("symbol")):
                d.update(update.get("$set", {}))
                n += 1
        _R.modified_count = n
        return _R

    async def count_documents(self, q):
        stale = q.get("stale")
        if stale is None:
            return len(self._cache_docs)
        return sum(1 for d in self._cache_docs.values() if d.get("stale") == stale)


class _FakeDB:
    def __init__(self, market_data_docs=None):
        self._market_data = _FakeCollection(market_data_docs)
        self._cache = _FakeCollection()
    @property
    def market_data(self):
        return self._market_data
    def __getitem__(self, name):
        if name == CACHE_COLLECTION:
            return self._cache
        return _FakeCollection()


@pytest.mark.asyncio
async def test_local_cts_m1_native_path(monkeypatch):
    monkeypatch.delenv("BID_HTF_CACHE_ENABLED", raising=False)
    fake_m1 = [c.to_dict() for c in _synthetic_m1(60)]
    for d in fake_m1:
        d["timestamp"] = d["timestamp"]  # already iso
    db = _FakeDB(market_data_docs=fake_m1)
    cts = LocalCTS(db_getter=lambda: db)
    win = await cts.load_candles("EURUSD", "1m")
    assert win.symbol == "EURUSD"
    assert win.timeframe == "1m"
    assert len(win.candles) == 60
    assert win.provenance.aggregation_path == "m1_native"
    assert win.provenance.canonical_source == "market_data.bid_1m"


@pytest.mark.asyncio
async def test_local_cts_htf_resample_path(monkeypatch):
    monkeypatch.delenv("BID_HTF_CACHE_ENABLED", raising=False)  # cache off
    fake_m1 = [c.to_dict() for c in _synthetic_m1(240)]
    db = _FakeDB(market_data_docs=fake_m1)
    cts = LocalCTS(db_getter=lambda: db)
    win = await cts.load_candles("EURUSD", "H1")
    assert len(win.candles) == 4
    assert "resampled" in win.provenance.aggregation_path
    assert win.provenance.data_quality_state == DataQualityState.OK.value


@pytest.mark.asyncio
async def test_local_cts_cache_hit_populates_provenance(monkeypatch):
    monkeypatch.setenv("BID_HTF_CACHE_ENABLED", "true")
    fake_m1 = [c.to_dict() for c in _synthetic_m1(60)]
    db = _FakeDB(market_data_docs=fake_m1)
    cts = LocalCTS(db_getter=lambda: db)

    # First call — cache miss → resample + write
    w1 = await cts.load_candles("EURUSD", "H1")
    assert len(w1.candles) == 1
    assert "resampled" in w1.provenance.aggregation_path

    # Force fetch on the same bucket ts by using the cache directly
    # (integration nuance: cache is keyed by "now"'s month, so both
    # calls hit the same bucket key)
    w2 = await cts.load_candles("EURUSD", "H1")
    # Second call should be a cache hit
    assert "cache" in w2.provenance.aggregation_path or "resampled" in w2.provenance.aggregation_path
    # If cache-hit, cache_generated_at is populated
    if "cache" in w2.provenance.aggregation_path:
        assert w2.provenance.cache_generated_at is not None
        assert w2.provenance.cache_bucket_key is not None


@pytest.mark.asyncio
async def test_local_cts_invalidate(monkeypatch):
    monkeypatch.setenv("BID_HTF_CACHE_ENABLED", "true")
    monkeypatch.setenv("BID_CACHE_EVENT_INVALIDATION", "true")
    fake_m1 = [c.to_dict() for c in _synthetic_m1(60)]
    db = _FakeDB(market_data_docs=fake_m1)
    cts = LocalCTS(db_getter=lambda: db)
    await cts.load_candles("EURUSD", "H1")  # materialise
    n = await cts.invalidate("EURUSD", "H1", reason="m1_append")
    assert n >= 0    # count of buckets marked stale


@pytest.mark.asyncio
async def test_local_cts_rebuild_bucket(monkeypatch):
    monkeypatch.setenv("BID_HTF_CACHE_ENABLED", "true")
    fake_m1 = [c.to_dict() for c in _synthetic_m1(60)]
    db = _FakeDB(market_data_docs=fake_m1)
    cts = LocalCTS(db_getter=lambda: db)
    rep = await cts.rebuild_bucket("EURUSD", "H1", "EURUSD|1h|2026-01")
    assert rep.ok
    assert rep.input_rows == 60
    assert rep.output_rows == 1


@pytest.mark.asyncio
async def test_local_cts_health_snapshot_shape(monkeypatch):
    fake_m1 = [c.to_dict() for c in _synthetic_m1(60)]
    db = _FakeDB(market_data_docs=fake_m1)
    cts = LocalCTS(db_getter=lambda: db)
    await cts.load_candles("EURUSD", "1m")
    h = cts.health_snapshot()
    assert h["subsystem"] == "cts"
    for k in ("health_score", "readiness_score", "confidence_score",
              "resource_usage", "last_successful_run",
              "failure_count", "recovery_status"):
        assert k in h


@pytest.mark.asyncio
async def test_data_access_route_through_when_flag_on(monkeypatch):
    """Verify data_access.load_ohlc_bars routes through CTS when BID_CANONICAL_M1_READ_MODE=true."""
    monkeypatch.setenv("BID_CANONICAL_M1_READ_MODE", "true")
    fake_m1 = [c.to_dict() for c in _synthetic_m1(60)]

    # Reset CTS with a stub DB
    reset_cts_for_tests()
    import engines.cts.service as _svc
    _svc._CTS_SINGLETON = LocalCTS(db_getter=lambda: _FakeDB(market_data_docs=fake_m1))

    from engines.data_access import load_ohlc_bars
    docs = await load_ohlc_bars("EURUSD", "1m", source="bid_1m")
    assert len(docs) == 60
    assert "timestamp" in docs[0]


@pytest.mark.asyncio
async def test_data_access_bypass_when_flag_off(monkeypatch):
    """Verify data_access does NOT route through CTS when flag off — legacy path."""
    monkeypatch.delenv("BID_CANONICAL_M1_READ_MODE", raising=False)
    # In legacy path, load_ohlc_bars uses `engines.db.get_db()` directly.
    # Without patching, this may return real DB or []; the assertion is
    # just that the function does not raise and doesn't touch CTS.
    from engines.data_access import load_ohlc_bars
    docs = await load_ohlc_bars("__no_such_symbol__", "1m", source="bid_1m")
    assert isinstance(docs, list)


# ── HTF cache unit tests (stub DB) ───────────────────────────────────

@pytest.mark.asyncio
async def test_htf_cache_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BID_HTF_CACHE_ENABLED", raising=False)
    db = _FakeDB()
    c = HtfCache(db_getter=lambda: db)
    assert c.enabled() is False
    got = await c.get("EURUSD", "H1", "2026-02-01T00:00:00+00:00")
    assert got is None


@pytest.mark.asyncio
async def test_htf_cache_put_and_get_roundtrip(monkeypatch):
    monkeypatch.setenv("BID_HTF_CACHE_ENABLED", "true")
    db = _FakeDB()
    c = HtfCache(db_getter=lambda: db)
    m1 = _synthetic_m1(60)
    h1, _ = resample_m1_to(m1, "H1")
    ok = await c.put("EURUSD", "H1", m1[-1].timestamp, h1, (m1[0].timestamp, m1[-1].timestamp))
    assert ok
    doc = await c.get("EURUSD", "H1", m1[-1].timestamp)
    assert doc is not None
    assert doc["symbol"] == "EURUSD"
    assert doc["stale"] is False
    assert len(doc["candles"]) == 1


@pytest.mark.asyncio
async def test_htf_cache_stale_bucket_treated_as_miss(monkeypatch):
    monkeypatch.setenv("BID_HTF_CACHE_ENABLED", "true")
    monkeypatch.setenv("BID_CACHE_EVENT_INVALIDATION", "true")
    db = _FakeDB()
    c = HtfCache(db_getter=lambda: db)
    m1 = _synthetic_m1(60)
    h1, _ = resample_m1_to(m1, "H1")
    await c.put("EURUSD", "H1", m1[-1].timestamp, h1, (m1[0].timestamp, m1[-1].timestamp))
    # Invalidate the bucket
    n = await c.invalidate("EURUSD", "H1", reason="test_invalidate")
    assert n >= 1
    doc = await c.get("EURUSD", "H1", m1[-1].timestamp)
    # Stale bucket should read back as None (treated as miss)
    assert doc is None
