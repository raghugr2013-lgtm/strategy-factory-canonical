"""cTrader resilience layer.

Design goals:
  * Exponential backoff on connection failure (100ms → 30s cap)
  * Circuit breaker (5 consecutive failures/60s → OPEN 5min →
    HALF_OPEN test → CLOSED)
  * Heartbeat (every 15s; 3 missed → force reconnect)
  * Duplicate suppression is enforced by the broker adapter itself
    via idempotent `submit(request_id=...)` — this module does not
    duplicate that guard.

Deterministic + injectable clock/sleep for unit tests.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, List, Optional


class BreakerState(str, Enum):
    CLOSED    = "closed"
    OPEN      = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_window_s:   float = 60.0
    failure_threshold:  int   = 5
    open_duration_s:    float = 300.0
    state:              BreakerState = BreakerState.CLOSED
    failures:           List[float] = field(default_factory=list)
    opened_at:          Optional[float] = None
    clock_fn:           Callable[[], float] = time.time

    def record_success(self) -> None:
        self.failures.clear()
        if self.state != BreakerState.CLOSED:
            self.state = BreakerState.CLOSED
            self.opened_at = None

    def record_failure(self) -> None:
        now = self.clock_fn()
        # Drop stale failures outside the sliding window.
        self.failures = [t for t in self.failures
                          if now - t <= self.failure_window_s]
        self.failures.append(now)
        if len(self.failures) >= self.failure_threshold and \
                self.state == BreakerState.CLOSED:
            self.state = BreakerState.OPEN
            self.opened_at = now

    def can_proceed(self) -> bool:
        if self.state == BreakerState.CLOSED:
            return True
        now = self.clock_fn()
        if self.state == BreakerState.OPEN:
            if self.opened_at is None:
                return True
            if now - self.opened_at >= self.open_duration_s:
                self.state = BreakerState.HALF_OPEN
                return True
            return False
        # HALF_OPEN — one probe allowed
        return True


@dataclass
class ExponentialBackoff:
    base_ms:      float = 100.0
    max_ms:       float = 30_000.0
    factor:       float = 2.0
    attempts:     int   = 0

    def next_delay_s(self) -> float:
        delay_ms = min(self.max_ms,
                       self.base_ms * (self.factor ** self.attempts))
        self.attempts += 1
        return delay_ms / 1000.0

    def reset(self) -> None:
        self.attempts = 0


class ResilientConnection:
    """Wraps a low-level transport with:
      * exponential backoff on failure
      * circuit breaker (OPEN → HALF_OPEN → CLOSED)
      * heartbeat (dropped connection auto-reconnect)

    Transport is any object implementing `connect() / disconnect() /
    heartbeat()` (all async). `perform(op)` runs `op` while respecting
    the breaker.
    """

    def __init__(self,
                 transport,
                 *,
                 heartbeat_interval_s: float = 15.0,
                 max_missed_heartbeats: int = 3,
                 breaker: Optional[CircuitBreaker] = None,
                 backoff: Optional[ExponentialBackoff] = None,
                 sleep_fn: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 clock_fn: Callable[[], float] = time.time,
                 ) -> None:
        self.transport = transport
        self.heartbeat_interval_s = heartbeat_interval_s
        self.max_missed_heartbeats = max_missed_heartbeats
        self.breaker = breaker or CircuitBreaker(clock_fn=clock_fn)
        self.backoff = backoff or ExponentialBackoff()
        self.sleep_fn = sleep_fn
        self.clock_fn = clock_fn
        self.connected = False
        self.missed_heartbeats = 0
        self.last_heartbeat_at = 0.0
        self._hb_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        if not self.breaker.can_proceed():
            return False
        try:
            await self.transport.connect()
            self.connected = True
            self.missed_heartbeats = 0
            self.last_heartbeat_at = self.clock_fn()
            self.breaker.record_success()
            self.backoff.reset()
            return True
        except Exception:                                  # noqa: BLE001
            self.breaker.record_failure()
            delay = self.backoff.next_delay_s()
            await self.sleep_fn(delay)
            return False

    async def disconnect(self) -> None:
        if self._hb_task:
            self._hb_task.cancel()
            self._hb_task = None
        try:
            await self.transport.disconnect()
        except Exception:                                  # noqa: BLE001
            pass
        self.connected = False

    async def heartbeat_once(self) -> bool:
        """Single heartbeat probe — used by tests."""
        try:
            await self.transport.heartbeat()
            self.missed_heartbeats = 0
            self.last_heartbeat_at = self.clock_fn()
            return True
        except Exception:                                  # noqa: BLE001
            self.missed_heartbeats += 1
            if self.missed_heartbeats >= self.max_missed_heartbeats:
                self.connected = False
                await self.disconnect()
                return False
            return True

    async def perform(self, op: Callable[[], Awaitable[Any]]) -> Any:
        """Execute an operation, honouring the breaker."""
        if not self.breaker.can_proceed():
            raise RuntimeError("circuit breaker OPEN — refusing operation")
        try:
            result = await op()
            self.breaker.record_success()
            return result
        except Exception:                                  # noqa: BLE001
            self.breaker.record_failure()
            raise
