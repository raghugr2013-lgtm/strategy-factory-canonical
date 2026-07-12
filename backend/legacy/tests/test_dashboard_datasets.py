"""
P2 — Dashboard dataset discovery endpoint regression suite.

Covers the response contract + aggregation shape used by the UI to
dynamically populate the pair/timeframe dropdowns.
"""

import pytest
from unittest.mock import patch

from api.dashboard import dashboard_datasets, _DB_TO_CANONICAL_TF


@pytest.mark.asyncio
async def test_datasets_empty_db_returns_success_with_no_pairs():
    async def _empty_agg(_pipe):
        if False:
            yield

    class _FakeCollection:
        def aggregate(self, pipe):
            return _empty_agg(pipe)

    class _FakeDB:
        market_data = _FakeCollection()

    with patch("api.dashboard.get_db", return_value=_FakeDB()) if False else patch(
        "engines.db.get_db", return_value=_FakeDB(),
    ):
        res = await dashboard_datasets()
    assert res["success"] is True
    assert res["min_candles"] == 200
    assert res["pairs"] == []


@pytest.mark.asyncio
async def test_datasets_shapes_pairs_and_timeframes_correctly():
    # Simulate the aggregate: GBPUSD has sufficient H1 + M30, EURUSD has
    # only 120 H1 (below the 200 minimum).
    docs = [
        {"_id": {"symbol": "GBPUSD", "tf": "1h"}, "n": 6200},
        {"_id": {"symbol": "GBPUSD", "tf": "30m"}, "n": 12267},
        {"_id": {"symbol": "EURUSD", "tf": "1h"}, "n": 120},
    ]

    async def _agg_gen(_pipe):
        for d in docs:
            yield d

    class _FakeCollection:
        def aggregate(self, pipe):
            return _agg_gen(pipe)

    class _FakeDB:
        market_data = _FakeCollection()

    with patch("engines.db.get_db", return_value=_FakeDB()):
        res = await dashboard_datasets()

    assert res["success"] is True
    pairs = {p["pair"]: p for p in res["pairs"]}
    assert "GBPUSD" in pairs and "EURUSD" in pairs

    gbp = pairs["GBPUSD"]
    assert gbp["has_sufficient_data"] is True
    assert gbp["total_candles"] == 6200 + 12267
    tfs = {t["tf"]: t for t in gbp["timeframes"]}
    assert tfs["H1"]["candles"] == 6200
    assert tfs["H1"]["sufficient"] is True
    assert tfs["M30"]["candles"] == 12267
    assert tfs["M30"]["sufficient"] is True

    eur = pairs["EURUSD"]
    assert eur["has_sufficient_data"] is False
    assert eur["timeframes"][0]["tf"] == "H1"
    assert eur["timeframes"][0]["sufficient"] is False


@pytest.mark.asyncio
async def test_datasets_sort_puts_sufficient_pairs_first():
    docs = [
        {"_id": {"symbol": "EURUSD", "tf": "1h"}, "n": 120},   # insufficient
        {"_id": {"symbol": "GBPUSD", "tf": "1h"}, "n": 6200},  # sufficient
    ]

    async def _agg_gen(_pipe):
        for d in docs:
            yield d

    class _FakeCollection:
        def aggregate(self, pipe):
            return _agg_gen(pipe)

    class _FakeDB:
        market_data = _FakeCollection()

    with patch("engines.db.get_db", return_value=_FakeDB()):
        res = await dashboard_datasets()

    # GBPUSD has sufficient, so it comes first.
    assert res["pairs"][0]["pair"] == "GBPUSD"
    assert res["pairs"][1]["pair"] == "EURUSD"


@pytest.mark.asyncio
async def test_datasets_handles_aggregate_exception_gracefully():
    class _FakeCollection:
        def aggregate(self, pipe):
            raise RuntimeError("mongo down")

    class _FakeDB:
        market_data = _FakeCollection()

    with patch("engines.db.get_db", return_value=_FakeDB()):
        res = await dashboard_datasets()
    assert res["success"] is False
    assert res["pairs"] == []
    assert "mongo down" in res["error"]


@pytest.mark.asyncio
async def test_datasets_merges_overlapping_sources_by_max():
    # Same (symbol, timeframe) appears twice in aggregation (would only
    # happen if someone forgot to group by source). Our code takes MAX
    # rather than SUM so we don't double-count overlapping slices.
    docs = [
        {"_id": {"symbol": "GBPUSD", "tf": "1h"}, "n": 6200},
        {"_id": {"symbol": "GBPUSD", "tf": "1h"}, "n": 3100},  # smaller slice
    ]

    async def _agg_gen(_pipe):
        for d in docs:
            yield d

    class _FakeCollection:
        def aggregate(self, pipe):
            return _agg_gen(pipe)

    class _FakeDB:
        market_data = _FakeCollection()

    with patch("engines.db.get_db", return_value=_FakeDB()):
        res = await dashboard_datasets()

    gbp = res["pairs"][0]
    assert gbp["timeframes"][0]["candles"] == 6200  # max, not 9300


def test_db_to_canonical_tf_map_complete():
    # Every TF the backtest engine understands should be in the reverse
    # map so the UI always sees canonical forms.
    for db_tf in ("1m", "5m", "15m", "30m", "1h", "4h", "1d"):
        assert db_tf in _DB_TO_CANONICAL_TF
    assert _DB_TO_CANONICAL_TF["1h"] == "H1"
    assert _DB_TO_CANONICAL_TF["15m"] == "M15"
