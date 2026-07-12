"""
P2 — One-click data-load endpoint regression suite.

Verifies the existing /api/download-data endpoint (wrapped by the
frontend's `loadMarketData()` helper) still works:
  * rejects invalid symbols / timeframes with a structured error
  * accepts valid inputs and delegates to download_and_store()
  * returns {success:false, error} when the downloader can't fetch

We keep this suite focused on the CONTRACT between the frontend
`loadMarketData()` call and the backend response shape — the
underlying Dukascopy library itself is mocked.
"""

from unittest.mock import AsyncMock, patch
import pytest

from api.data import download_data, DownloadRequest, ALLOWED_SYMBOLS, ALLOWED_TIMEFRAMES


@pytest.mark.asyncio
async def test_invalid_symbol_returns_structured_error():
    req = DownloadRequest(
        symbol="NOT_A_PAIR", timeframe="1h",
        date_from="2024-01-01", date_to="2024-03-01",
    )
    res = await download_data(req)
    assert res["success"] is False
    assert "symbol" in res["error"].lower() or "one of" in res["error"].lower()


@pytest.mark.asyncio
async def test_invalid_timeframe_returns_structured_error():
    req = DownloadRequest(
        symbol="EURUSD", timeframe="1y",
        date_from="2024-01-01", date_to="2024-03-01",
    )
    res = await download_data(req)
    assert res["success"] is False
    assert "timeframe" in res["error"].lower() or "one of" in res["error"].lower()


@pytest.mark.asyncio
async def test_successful_download_delegates_to_downloader():
    req = DownloadRequest(
        symbol="EURUSD", timeframe="1h",
        date_from="2024-01-01", date_to="2024-02-01",
    )
    fake_result = {
        "symbol": "EURUSD",
        "timeframe": "1h",
        "rows_downloaded": 720,
        "rows_inserted": 500,
        "rows_skipped": 220,
        "first_timestamp": "2024-01-01T00:00:00+00:00",
        "last_timestamp": "2024-02-01T00:00:00+00:00",
        "message": "Downloaded 720 rows, inserted 500, skipped 220 duplicates",
    }
    with patch("api.data.download_and_store", new=AsyncMock(return_value=fake_result)):
        res = await download_data(req)
    assert res["success"] is True
    assert res["rows_inserted"] == 500
    assert res["rows_downloaded"] == 720
    assert res["symbol"] == "EURUSD"
    assert res["timeframe"] == "1h"


@pytest.mark.asyncio
async def test_downloader_failure_propagates_as_success_false():
    req = DownloadRequest(
        symbol="XAUUSD", timeframe="1h",
        date_from="2024-01-01", date_to="2024-02-01",
    )
    fake_err = {
        "success": False,
        "symbol": "XAUUSD",
        "timeframe": "1h",
        "rows_downloaded": 0,
        "rows_inserted": 0,
        "rows_skipped": 0,
        "error": "Data not available for XAUUSD (1h): upstream timeout",
    }
    with patch("api.data.download_and_store", new=AsyncMock(return_value=fake_err)):
        res = await download_data(req)
    # Contract: route returns the downloader's error payload verbatim.
    assert res["success"] is False
    assert "XAUUSD" in res["error"]


@pytest.mark.asyncio
async def test_unexpected_exception_surfaces_as_error():
    req = DownloadRequest(
        symbol="EURUSD", timeframe="1h",
        date_from="2024-01-01", date_to="2024-02-01",
    )
    with patch(
        "api.data.download_and_store",
        new=AsyncMock(side_effect=RuntimeError("network down")),
    ):
        res = await download_data(req)
    assert res["success"] is False
    # Generic exception → error key carries the message (not detail).
    assert "network down" in res["error"]


def test_contract_allowed_symbols_superset():
    # Frontend sends canonical UI pairs (EURUSD, GBPUSD, etc.).
    # All must be allowed by the endpoint so loadMarketData() works
    # for every pair the dropdown can produce.
    for p in ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100", "BTCUSD", "ETHUSD"):
        assert p in ALLOWED_SYMBOLS


def test_contract_allowed_timeframes_superset():
    # Frontend converts canonical TF (H1, M15, etc.) → lowercase db TF
    # before calling. Those lowercase values MUST all be allowed.
    for tf in ("1m", "5m", "15m", "30m", "1h", "4h", "1d"):
        assert tf in ALLOWED_TIMEFRAMES
