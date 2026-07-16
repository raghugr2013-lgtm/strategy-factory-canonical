"""Phase H — PaperBrokerAdapter.

Deterministic paper broker. Fills orders immediately (MARKET) or on
schedule (LIMIT/STOP). Configurable slippage / rejection / partial-fill
rates via env (see `execution.config.paper_config()`).

Design notes:
  * Zero external I/O; safe in CI, local dev, and VPS boot.
  * Deterministic: same input + same env ⇒ same fills. Random draws
    are seeded via `PAPER_SEED` (default 0 → deterministic sequence).
  * Idempotent on `request_id` — resubmitting the same order_id
    returns the same broker_order_id.
  * NEVER writes to the ledger — that is the caller's responsibility
    (single source of truth invariant).
"""
from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Optional

from .. import config as ecfg
from ..types import BrokerHealth, FillEvent, OrderRequest, Position
from .base import BrokerAdapter, BrokerError


class PaperBrokerAdapter:
    """Default deterministic broker."""

    NAME = "paper"

    def __init__(self, seed: int = 0) -> None:
        self._connected = False
        self._rng = random.Random(seed)
        self._orders: Dict[str, OrderRequest] = {}
        self._broker_ids: Dict[str, str] = {}       # request_id → broker_order_id
        self._positions: Dict[str, Position] = {}
        self._fill_seq = 0
        self._connect_ts = 0.0
        self._latency_samples: List[float] = []
        self._reject_count = 0
        self._total_submits = 0
        # Queue of fills produced by submit() — stream_fills consumes.
        self._fill_queue: asyncio.Queue = asyncio.Queue()

    # ── Connection ──────────────────────────────────────────────
    async def connect(self) -> None:
        self._connected = True
        self._connect_ts = time.time()

    async def disconnect(self) -> None:
        self._connected = False

    # ── Order flow ──────────────────────────────────────────────
    async def submit(self, req: OrderRequest) -> str:
        """Deterministic paper submit. Immediately fills MARKET orders
        (respecting configured slippage/reject/partial rates)."""
        if not self._connected:
            raise BrokerError("paper broker not connected")
        if ecfg.broker_kill_switch():
            raise BrokerError("BROKER_KILL_SWITCH is ON — submit blocked")

        # Idempotency
        if req.request_id in self._broker_ids:
            return self._broker_ids[req.request_id]

        self._total_submits += 1
        cfg = ecfg.paper_config()

        # Simulate submission latency
        lat_ms = float(cfg["latency_ms"])
        self._latency_samples.append(lat_ms)
        self._latency_samples = self._latency_samples[-100:]
        await asyncio.sleep(max(0.0, lat_ms / 10000.0))  # scaled 10x for CI speed

        broker_order_id = f"paper_{req.request_id[:10]}_{self._total_submits}"
        self._broker_ids[req.request_id] = broker_order_id
        self._orders[req.request_id] = req

        # Rejection injection
        if self._rng.random() < float(cfg["reject_rate"]):
            self._reject_count += 1
            # Emit a synthetic REJECTED "fill" (qty_filled=0, is_partial=False)
            self._fill_seq += 1
            await self._fill_queue.put(FillEvent(
                fill_id=f"paperfill_{self._fill_seq}",
                request_id=req.request_id,
                account_id=req.account_id,
                pair=req.pair, side=req.side,
                qty_filled=0.0,
                price=float(req.price or 0.0),
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=lat_ms,
                slippage_pips=None,
                is_partial=False,
                broker_order_id=broker_order_id,
                seq=self._fill_seq,
            ))
            raise BrokerError(f"paper reject: rate={cfg['reject_rate']}")

        # Partial fill injection (single split for now)
        partial = self._rng.random() < float(cfg["partial_rate"])
        remaining = float(req.qty)
        # Deterministic paper "market price" = req.price if given else 1.0.
        market_price = float(req.price) if req.price else 1.0
        slippage_pips = float(cfg["slippage_pips"])
        # Sign the slippage per side (BUY pays higher, SELL receives lower)
        fill_price = market_price + (1e-4 * slippage_pips *
                                      (1 if req.side == "BUY" else -1))
        if partial and remaining > 1.0:
            first_qty = round(remaining * 0.5, 4)
            self._fill_seq += 1
            await self._fill_queue.put(FillEvent(
                fill_id=f"paperfill_{self._fill_seq}",
                request_id=req.request_id,
                account_id=req.account_id,
                pair=req.pair, side=req.side,
                qty_filled=first_qty, price=fill_price,
                timestamp=datetime.now(timezone.utc).isoformat(),
                latency_ms=lat_ms, slippage_pips=slippage_pips,
                is_partial=True, broker_order_id=broker_order_id,
                seq=self._fill_seq,
            ))
            remaining -= first_qty

        self._fill_seq += 1
        await self._fill_queue.put(FillEvent(
            fill_id=f"paperfill_{self._fill_seq}",
            request_id=req.request_id,
            account_id=req.account_id,
            pair=req.pair, side=req.side,
            qty_filled=remaining, price=fill_price,
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=lat_ms, slippage_pips=slippage_pips,
            is_partial=False, broker_order_id=broker_order_id,
            seq=self._fill_seq,
        ))
        return broker_order_id

    async def cancel(self, request_id: str) -> bool:
        # In paper mode most orders fill instantly, so cancel is a no-op
        # for terminal orders and a synthetic success for pending ones.
        return request_id in self._broker_ids

    async def positions(self) -> List[Position]:
        return list(self._positions.values())

    async def stream_fills(self) -> AsyncIterator[FillEvent]:
        while True:
            fill = await self._fill_queue.get()
            yield fill

    # ── Non-blocking drain used by tests + order_lifecycle ─────
    async def drain_fills(self, timeout: float = 0.05) -> List[FillEvent]:
        """Return every fill currently queued. Used by callers that
        don't want to run a long-lived consumer task."""
        out: List[FillEvent] = []
        loop_end = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < loop_end:
            try:
                fill = await asyncio.wait_for(self._fill_queue.get(),
                                              timeout=0.005)
                out.append(fill)
            except asyncio.TimeoutError:
                if out:
                    break
                continue
        return out

    # ── Health ──────────────────────────────────────────────────
    async def health(self) -> BrokerHealth:
        avg_lat = (sum(self._latency_samples) / len(self._latency_samples)
                   if self._latency_samples else 0.0)
        reject_rate = (self._reject_count / self._total_submits
                       if self._total_submits > 0 else 0.0)
        connected = self._connected
        band = "healthy" if connected else "unhealthy"
        return BrokerHealth(
            broker=self.NAME,
            account_id=ecfg.default_account_id(),
            ts=datetime.now(timezone.utc).isoformat(),
            connected=connected,
            latency_ms=float(avg_lat),
            reject_rate_5m=float(reject_rate),
            reject_rate_60m=float(reject_rate),
            reject_rate_24h=float(reject_rate),
            score_5m=1.0 if connected and reject_rate < 0.05 else 0.5,
            score_60m=1.0 if connected and reject_rate < 0.05 else 0.5,
            score_24h=1.0 if connected and reject_rate < 0.05 else 0.5,
            band=band,
        )


# ── Process-wide singleton ─────────────────────────────────────
_PAPER_SINGLETON: Optional[PaperBrokerAdapter] = None


def get_paper_adapter() -> PaperBrokerAdapter:
    global _PAPER_SINGLETON
    if _PAPER_SINGLETON is None:
        import os
        seed = int(os.environ.get("PAPER_SEED", "0") or 0)
        _PAPER_SINGLETON = PaperBrokerAdapter(seed=seed)
    return _PAPER_SINGLETON


def reset_paper_adapter() -> None:
    """Test-only helper — resets the singleton between tests."""
    global _PAPER_SINGLETON
    _PAPER_SINGLETON = None
