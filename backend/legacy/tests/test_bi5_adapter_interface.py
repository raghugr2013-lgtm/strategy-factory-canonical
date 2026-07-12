"""P0A — DukascopyBI5Adapter unit tests.

These tests exercise the HTTP adapter WITHOUT touching the network. We
inject a fake ``httpx.AsyncClient`` that returns scripted responses so
we can deterministically cover:

* URL construction (0-indexed month rule)
* 200 OK → BI5HourBlob(payload=bytes)
* 404 → BI5HourBlob(payload=b"") + cached as "no ticks"
* 429/503 transient → retry then success
* Hour normalisation (truncates minute/second/microsecond)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

import httpx
import pytest

from data_engine.adapters.dukascopy_bi5 import DukascopyBI5Adapter


# ---------------------------------------------------------------------------
# Test scaffolding
# ---------------------------------------------------------------------------

class _ScriptedResponse:
    """Mimics httpx.Response well enough for the adapter's needs."""

    def __init__(self, status_code: int, content: bytes = b"") -> None:
        self.status_code = status_code
        self.content = content
        # The adapter uses ``resp.request`` only when raising HTTPStatusError.
        self.request = httpx.Request("GET", "http://test.local/")


class _ScriptedClient:
    """Drop-in for httpx.AsyncClient.get; captures URLs and replays steps."""

    def __init__(self, steps: List[_ScriptedResponse]) -> None:
        self._steps = list(steps)
        self.urls: list[str] = []
        self.is_closed = False

    async def get(self, url: str) -> _ScriptedResponse:  # noqa: D401
        self.urls.append(url)
        if not self._steps:
            raise AssertionError("scripted client out of responses")
        return self._steps.pop(0)

    async def aclose(self) -> None:
        self.is_closed = True


def _make_adapter(steps: List[_ScriptedResponse]) -> tuple[DukascopyBI5Adapter, _ScriptedClient]:
    client = _ScriptedClient(steps)
    adapter = DukascopyBI5Adapter(
        client=client,                # type: ignore[arg-type]
        retry_backoff_s=0.0,          # no real sleeps in tests
        max_retries=4,
    )
    return adapter, client


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------

def test_build_url_uses_zero_indexed_month_and_hour():
    """Dukascopy's path uses month-1; the adapter must honour that."""
    adapter, _ = _make_adapter([_ScriptedResponse(404)])
    # 2024-03-02T05:00 → month 03 → URL ``02`` (zero-indexed)
    hour = datetime(2024, 3, 2, 5, tzinfo=timezone.utc)
    url = adapter.build_url("EURUSD", hour)
    assert url.endswith("/EURUSD/2024/02/02/05h_ticks.bi5"), url


# ---------------------------------------------------------------------------
# fetch_hour: 200 / 404 / transient retry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_hour_200_returns_payload_bytes():
    payload = b"\x00\x01\x02\x03"
    adapter, client = _make_adapter([_ScriptedResponse(200, content=payload)])
    hour = datetime(2024, 1, 2, 7, 30, tzinfo=timezone.utc)  # minute>0 → must normalise

    blob = await adapter.fetch_hour("EURUSD", hour)

    assert blob.symbol == "EURUSD"
    assert blob.source == "dukascopy"
    assert blob.payload == payload
    # Hour normalisation
    assert blob.hour_utc.minute == 0 and blob.hour_utc.second == 0
    # Only one request needed for 200
    assert len(client.urls) == 1


@pytest.mark.asyncio
async def test_fetch_hour_404_returns_empty_payload_no_raise():
    """A 404 means 'no ticks published for this hour' — must NOT raise."""
    adapter, client = _make_adapter([_ScriptedResponse(404)])
    blob = await adapter.fetch_hour("EURUSD", datetime(2024, 1, 6, 22, tzinfo=timezone.utc))
    assert blob.payload == b""
    assert len(client.urls) == 1  # 404 is terminal — no retry


@pytest.mark.asyncio
async def test_fetch_hour_transient_then_success_retries():
    """503 once, 429 once, then 200 OK — adapter must surface the final bytes."""
    payload = b"\xff\xff"
    adapter, client = _make_adapter([
        _ScriptedResponse(503),
        _ScriptedResponse(429),
        _ScriptedResponse(200, content=payload),
    ])
    blob = await adapter.fetch_hour("EURUSD", datetime(2024, 2, 5, 9, tzinfo=timezone.utc))
    assert blob.payload == payload
    assert len(client.urls) == 3  # two retries then success
