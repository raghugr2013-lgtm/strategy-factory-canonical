"""CtraderBrokerAdapter — implements BrokerAdapter for cTrader Open API.

Transport abstraction:
  * `CtraderTransport` Protocol — real production impl in H4.1 will
    wrap `ctrader-open-api-py` over a Protobuf websocket
  * `MockCtraderTransport` — deterministic in-process double for
    unit tests; models fills, disconnects, requotes

The adapter itself:
  * Wraps a transport in `ResilientConnection` (backoff, breaker,
    heartbeat)
  * Owns an `OAuthSession` and refreshes via the transport
  * Emits `BrokerHealth` snapshots from live-connection state
  * Satisfies the same `BrokerAdapter` Protocol as the paper broker,
    so `submit_order` / `process_fill` never need to know which
    venue is under them
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Protocol, runtime_checkable

from ... import config as ecfg
from ...types import BrokerHealth, FillEvent, OrderRequest, Position
from ..base import BrokerAdapter, BrokerDisconnected, BrokerError
from .resilience import ResilientConnection
from .session import OAuthSession


@runtime_checkable
class CtraderTransport(Protocol):
    """Every cTrader transport (production Protobuf or mock) MUST
    satisfy this Protocol."""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def heartbeat(self) -> None: ...
    async def send_order(self, req: OrderRequest) -> str: ...
    async def cancel_order(self, request_id: str) -> bool: ...
    async def fetch_positions(self) -> List[Position]: ...
    async def fetch_fills(self) -> List[FillEvent]: ...
    async def refresh_oauth(self, refresh_token: str) -> Dict[str, Any]: ...


class MockCtraderTransport:
    """Deterministic in-process double for tests.

    Behaviour switches:
      * `fail_next_connect`  — raise once on connect
      * `disconnect_after`   — auto-disconnect after N heartbeats
      * `reject_ids`         — request_ids that should be rejected
      * `latency_ms`         — synthetic per-op sleep (scaled 10× for CI)
    """
    NAME = "ctrader"

    def __init__(self,
                 fail_next_connect: bool = False,
                 disconnect_after: int = -1,
                 reject_ids: Optional[List[str]] = None,
                 latency_ms: float = 5.0,
                 clock_fn: Callable[[], float] = time.time,
                 ) -> None:
        self._fail_next_connect = fail_next_connect
        self._disconnect_after = disconnect_after
        self._reject_ids = set(reject_ids or [])
        self._latency_ms = float(latency_ms)
        self._heartbeats = 0
        self._connected = False
        self._pending_fills: List[FillEvent] = []
        self._request_to_broker: Dict[str, str] = {}
        self._clock = clock_fn
        self._submit_seq = 0
        self._refresh_calls = 0

    async def connect(self) -> None:
        if self._fail_next_connect:
            self._fail_next_connect = False
            raise BrokerError("mock ctrader: connect() forced failure")
        await asyncio.sleep(self._latency_ms / 10000.0)
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def heartbeat(self) -> None:
        if not self._connected:
            raise BrokerDisconnected("mock ctrader: heartbeat while disconnected")
        self._heartbeats += 1
        if 0 < self._disconnect_after <= self._heartbeats:
            self._connected = False
            raise BrokerDisconnected(
                "mock ctrader: simulated disconnect after "
                f"{self._disconnect_after} heartbeats")

    async def send_order(self, req: OrderRequest) -> str:
        if not self._connected:
            raise BrokerDisconnected("mock ctrader: not connected")
        # Idempotency
        if req.request_id in self._request_to_broker:
            return self._request_to_broker[req.request_id]
        self._submit_seq += 1
        broker_order_id = f"ctd_{req.request_id[:8]}_{self._submit_seq}"
        self._request_to_broker[req.request_id] = broker_order_id
        if req.request_id in self._reject_ids:
            raise BrokerError(f"mock ctrader: forced reject {req.request_id}")
        # Synthesise a full-fill event.
        price = float(req.price or 1.0)
        self._pending_fills.append(FillEvent(
            fill_id=f"ctd_fill_{self._submit_seq}",
            request_id=req.request_id,
            account_id=req.account_id, pair=req.pair, side=req.side,
            qty_filled=float(req.qty), price=price,
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=self._latency_ms, slippage_pips=0.0,
            is_partial=False, broker_order_id=broker_order_id,
            seq=self._submit_seq,
        ))
        return broker_order_id

    async def cancel_order(self, request_id: str) -> bool:
        return request_id in self._request_to_broker

    async def fetch_positions(self) -> List[Position]:
        return []

    async def fetch_fills(self) -> List[FillEvent]:
        out = list(self._pending_fills)
        self._pending_fills.clear()
        return out

    async def refresh_oauth(self, refresh_token: str) -> Dict[str, Any]:
        self._refresh_calls += 1
        return {
            "access_token":  f"mock_access_{self._refresh_calls}",
            "refresh_token": f"mock_refresh_{self._refresh_calls}",
            "expires_in":    3600,
        }


class CtraderBrokerAdapter:
    """Live-venue adapter. Uses a swappable `CtraderTransport` so tests
    can inject a `MockCtraderTransport` and prod can inject the real
    Protobuf websocket."""

    NAME = "ctrader"

    def __init__(self,
                 transport: CtraderTransport,
                 *,
                 session: Optional[OAuthSession] = None,
                 account_id: Optional[str] = None,
                 ) -> None:
        self.transport = transport
        self.session = session
        self.account_id = account_id or ecfg.default_account_id()
        self.conn = ResilientConnection(transport)
        self._connect_ts = 0.0
        self._reject_count = 0
        self._total_submits = 0
        self._latency_samples: List[float] = []
        self._disconnects_5m: List[float] = []

    # ── Connection ──────────────────────────────────────────
    async def connect(self) -> None:
        # Retry a few times inside the resilience wrapper; caller
        # sees the terminal state via `health()` if it never succeeds.
        for _ in range(5):
            ok = await self.conn.connect()
            if ok:
                self._connect_ts = time.time()
                return
        raise BrokerError("cTrader: unable to connect after 5 attempts")

    async def disconnect(self) -> None:
        await self.conn.disconnect()
        self._disconnects_5m.append(time.time())

    async def _ensure_session(self) -> None:
        if self.session is None:
            return
        if self.session.is_expired() or self.session.is_expiring_soon():
            data = await self.transport.refresh_oauth(self.session.refresh_token)
            self.session.apply_refresh(
                access_token=str(data.get("access_token") or ""),
                refresh_token=str(data.get("refresh_token") or ""),
                expires_in_s=int(data.get("expires_in") or 3600),
            )

    # ── Order flow ──────────────────────────────────────────
    async def submit(self, req: OrderRequest) -> str:
        if ecfg.broker_kill_switch():
            raise BrokerError("BROKER_KILL_SWITCH is ON — submit blocked")
        await self._ensure_session()
        self._total_submits += 1
        t0 = time.time()
        try:
            broker_id = await self.conn.perform(
                lambda: self.transport.send_order(req))
        except BrokerError:
            self._reject_count += 1
            raise
        latency = (time.time() - t0) * 1000.0
        self._latency_samples.append(latency)
        self._latency_samples = self._latency_samples[-100:]
        return broker_id

    async def cancel(self, request_id: str) -> bool:
        return await self.conn.perform(
            lambda: self.transport.cancel_order(request_id))

    async def positions(self) -> List[Position]:
        return await self.transport.fetch_positions()

    async def stream_fills(self) -> AsyncIterator[FillEvent]:
        while True:
            fills = await self.transport.fetch_fills()
            for f in fills:
                yield f
            if not fills:
                await asyncio.sleep(0.05)

    async def drain_fills(self, timeout: float = 0.05) -> List[FillEvent]:
        return await self.transport.fetch_fills()

    # ── Health ──────────────────────────────────────────────
    async def health(self) -> BrokerHealth:
        avg_lat = (sum(self._latency_samples) / len(self._latency_samples)
                   if self._latency_samples else 0.0)
        rej = (self._reject_count / self._total_submits
               if self._total_submits > 0 else 0.0)
        connected = self.conn.connected
        band = "healthy" if connected and rej < 0.05 else \
               "degraded" if connected else "unhealthy"
        return BrokerHealth(
            broker=self.NAME, account_id=self.account_id,
            ts=datetime.now(timezone.utc).isoformat(),
            connected=connected, latency_ms=float(avg_lat),
            reject_rate_5m=float(rej),
            reject_rate_60m=float(rej),
            reject_rate_24h=float(rej),
            disconnect_count_5m=len(self._disconnects_5m),
            disconnect_count_24h=len(self._disconnects_5m),
            score_5m=1.0 if band == "healthy" else 0.5 if band == "degraded" else 0.0,
            score_60m=1.0 if band == "healthy" else 0.5 if band == "degraded" else 0.0,
            score_24h=1.0 if band == "healthy" else 0.5 if band == "degraded" else 0.0,
            band=band,
        )
