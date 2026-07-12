"""Regression tests for the unified data-access + auto-recovery layer.

Covers:
  • TF-aware threshold lookup (canonical + DB-native forms).
  • Bar loader returns docs as-is from `market_data`.
  • `load_with_recovery` happy path → status `"ok"`.
  • Below threshold + auto_recover=False → status `"insufficient"`,
    no download attempted.
  • Below threshold + auto_recover=True with successful mock download
    → status `"recovered"`.
  • Below threshold + auto_recover=True with failed mock download
    → status `"insufficient"` + `recovery.attempted=True`.
  • `auto_factory._load_data` → real prices when data exists; (None,
    "none", 0) when not.
  • `auto_mutation_runner._check_data_available` → recovers / returns 0.

These tests stub the Mongo cursor and the Dukascopy downloader in
memory so they're hermetic and fast.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List

import pytest  # noqa: E402

sys.path.insert(0, "/app/backend")

from engines import data_access  # noqa: E402


# ─────────────────────────────────────────────────────────────────────
# In-memory market_data stub
# ─────────────────────────────────────────────────────────────────────

class _FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = docs

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, n: int):
        self._docs = self._docs[:int(n)]
        return self

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class _FakeMarketData:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None):
        sym = query.get("symbol")
        src = query.get("source")
        tf = query.get("timeframe")
        matched = [
            d for d in self.docs
            if d.get("symbol") == sym
            and d.get("source") == src
            and d.get("timeframe") == tf
        ]
        return _FakeCursor(matched)


class _FakeDB:
    def __init__(self, docs):
        self.market_data = _FakeMarketData(docs)


def _make_bars(symbol: str, tf_db: str, count: int, source: str = "bid_1m"):
    """Generate `count` synthetic OHLCV docs in the same shape that
    the Dukascopy importer writes."""
    out = []
    base_price = 1.10 if "JPY" not in symbol else 150.0
    for i in range(count):
        out.append({
            "symbol": symbol,
            "source": source,
            "timeframe": tf_db,
            "timestamp": f"2026-01-{(i % 28) + 1:02d}T{(i % 24):02d}:00:00+00:00",
            "open": base_price + i * 0.0001,
            "high": base_price + i * 0.0001 + 0.0005,
            "low":  base_price + i * 0.0001 - 0.0005,
            "close": base_price + i * 0.0001 + 0.0002,
            "volume": 100,
        })
    return out


@pytest.fixture
def fake_db(monkeypatch):
    """Patch `engines.db.get_db` to return an in-memory DB. Tests fill
    the docs list before invoking the loader."""
    state = {"docs": []}

    def _get_db():
        return _FakeDB(state["docs"])

    monkeypatch.setattr(data_access, "get_db", _get_db)
    return state


# ─────────────────────────────────────────────────────────────────────
# Threshold policy
# ─────────────────────────────────────────────────────────────────────

class TestMinCandlesFor:
    def test_canonical_forms(self):
        assert data_access.min_candles_for("H1") == 500
        assert data_access.min_candles_for("M30") == 1000
        assert data_access.min_candles_for("M15") == 2000
        assert data_access.min_candles_for("H4") == 200
        assert data_access.min_candles_for("D1") == 100

    def test_db_native_forms(self):
        assert data_access.min_candles_for("1h") == 500
        assert data_access.min_candles_for("30m") == 1000
        assert data_access.min_candles_for("15m") == 2000

    def test_unknown_falls_back_to_absolute_floor(self):
        assert data_access.min_candles_for("WAT") == data_access.ABSOLUTE_MIN_CANDLES
        assert data_access.min_candles_for("") == data_access.ABSOLUTE_MIN_CANDLES


# ─────────────────────────────────────────────────────────────────────
# load_ohlc_bars + load_closes
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLoadBars:
    async def test_returns_empty_when_no_data(self, fake_db):
        bars = await data_access.load_ohlc_bars("EURUSD", "H1")
        assert bars == []

    async def test_returns_docs_in_db_order(self, fake_db):
        fake_db["docs"] = _make_bars("EURUSD", "1h", 100)
        bars = await data_access.load_ohlc_bars("EURUSD", "H1")
        assert len(bars) == 100
        assert all("close" in b for b in bars)

    async def test_canonical_tf_maps_to_db_tf(self, fake_db):
        # Docs stored under tf=`1h`; query with canonical `H1`.
        fake_db["docs"] = _make_bars("EURUSD", "1h", 50)
        bars = await data_access.load_ohlc_bars("EURUSD", "H1")
        assert len(bars) == 50

    async def test_load_closes_returns_three_lists(self, fake_db):
        fake_db["docs"] = _make_bars("EURUSD", "1h", 100)
        prices, highs, lows = await data_access.load_closes("EURUSD", "H1")
        assert len(prices) == len(highs) == len(lows) == 100

    async def test_load_closes_returns_empty_below_floor(self, fake_db):
        fake_db["docs"] = _make_bars("EURUSD", "1h", 30)  # < ABSOLUTE_MIN_CANDLES
        prices, highs, lows = await data_access.load_closes("EURUSD", "H1")
        assert prices == [] and highs == [] and lows == []


# ─────────────────────────────────────────────────────────────────────
# load_with_recovery
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLoadWithRecovery:
    async def test_status_ok_when_above_threshold(self, fake_db):
        fake_db["docs"] = _make_bars("EURUSD", "1h", 600)  # > 500 H1 threshold
        res = await data_access.load_with_recovery("EURUSD", "H1")
        assert res["status"] == "ok"
        assert res["count"] == 600
        assert res["threshold"] == 500
        assert "recovery" not in res

    async def test_insufficient_when_recovery_disabled(self, fake_db):
        fake_db["docs"] = _make_bars("EURUSD", "1h", 200)  # < 500
        res = await data_access.load_with_recovery("EURUSD", "H1", auto_recover=False)
        assert res["status"] == "insufficient"
        assert res["count"] == 200
        assert "auto-downloading" not in res["message"].lower()
        assert "recovery" not in res

    async def test_recovery_succeeds_inserts_top_up_data(self, fake_db, monkeypatch):
        """Below threshold + recovery=True. Mock downloader fills more bars."""
        fake_db["docs"] = _make_bars("EURUSD", "1h", 200)

        async def fake_download(symbol, tf, df, dt):
            # Simulate inserting enough bars to cross the H1 threshold.
            fake_db["docs"] = _make_bars(symbol, tf, 800)
            return {"success": True, "rows_inserted": 600}

        monkeypatch.setattr(
            "data_engine.dukascopy_downloader.download_and_store",
            fake_download,
        )
        res = await data_access.load_with_recovery("EURUSD", "H1", auto_recover=True)
        assert res["status"] == "recovered"
        assert res["count"] == 800
        assert res["recovery"]["attempted"] is True
        assert res["recovery"]["before"] == 200
        assert res["recovery"]["after"] == 800
        assert res["recovery"]["downloaded"] == 600

    async def test_recovery_fails_returns_insufficient(self, fake_db, monkeypatch):
        fake_db["docs"] = _make_bars("EURUSD", "1h", 200)

        async def fake_download(symbol, tf, df, dt):
            return {"success": False, "error": "Dukascopy: instrument not available"}

        monkeypatch.setattr(
            "data_engine.dukascopy_downloader.download_and_store",
            fake_download,
        )
        res = await data_access.load_with_recovery("EURUSD", "H1", auto_recover=True)
        assert res["status"] == "insufficient"
        assert res["recovery"]["attempted"] is True
        assert res["recovery"]["error"] is not None
        assert "Recovery failed" in res["message"]

    async def test_recovery_exception_caught_does_not_propagate(self, fake_db, monkeypatch):
        fake_db["docs"] = _make_bars("EURUSD", "1h", 200)

        async def fake_download(symbol, tf, df, dt):
            raise RuntimeError("network blew up")

        monkeypatch.setattr(
            "data_engine.dukascopy_downloader.download_and_store",
            fake_download,
        )
        res = await data_access.load_with_recovery("EURUSD", "H1", auto_recover=True)
        assert res["status"] == "insufficient"
        assert "network blew up" in (res["recovery"]["error"] or "")


# ─────────────────────────────────────────────────────────────────────
# Auto-loop integration — never break the loop
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAutoLoopRecovery:
    async def test_auto_factory_load_data_skips_when_recovery_fails(
        self, fake_db, monkeypatch,
    ):
        """auto_factory._load_data must return (None, "none", 0) — never
        raise — when data is unavailable."""
        from engines import auto_factory
        # Empty DB + downloader returns failure
        monkeypatch.setattr(
            "data_engine.dukascopy_downloader.download_and_store",
            lambda *a, **k: _async_return({"success": False, "error": "x"}),
        )
        prices, src, n = await auto_factory._load_data("EURUSD", "H1")
        assert prices is None
        assert src == "none"
        assert n == 0

    async def test_auto_factory_load_data_returns_real_when_threshold_met(
        self, fake_db,
    ):
        from engines import auto_factory
        fake_db["docs"] = _make_bars("EURUSD", "1h", 600)
        prices, src, n = await auto_factory._load_data("EURUSD", "H1")
        assert src == "real"
        assert n == 600
        assert len(prices) == 600

    async def test_auto_mutation_check_returns_recovered_count(
        self, fake_db, monkeypatch,
    ):
        from engines import auto_mutation_runner
        fake_db["docs"] = _make_bars("EURUSD", "1h", 200)

        async def fake_download(symbol, tf, df, dt):
            fake_db["docs"] = _make_bars(symbol, tf, 700)
            return {"success": True, "rows_inserted": 500}

        monkeypatch.setattr(
            "data_engine.dukascopy_downloader.download_and_store",
            fake_download,
        )
        n = await auto_mutation_runner._check_data_available("EURUSD", "H1")
        assert n == 700

    async def test_auto_mutation_check_returns_zero_on_unrecoverable(
        self, fake_db, monkeypatch,
    ):
        from engines import auto_mutation_runner
        fake_db["docs"] = []

        async def fake_download(symbol, tf, df, dt):
            return {"success": False, "error": "no data"}

        monkeypatch.setattr(
            "data_engine.dukascopy_downloader.download_and_store",
            fake_download,
        )
        n = await auto_mutation_runner._check_data_available("EURUSD", "H1")
        assert n == 0


def _async_return(value):
    """Wrap a value in an awaitable for monkeypatch fixtures that
    expect an `async def` callable."""
    async def _coro(*_a, **_k):
        return value
    return _coro()
