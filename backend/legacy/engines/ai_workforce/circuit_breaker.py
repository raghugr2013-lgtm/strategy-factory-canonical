"""AI Workforce circuit-breaker (per-provider, in-process).

Rolling window state machine driven by outcomes recorded via
`ai_workforce.telemetry.record_call`.

State transitions:
    closed → open        when error_rate over last N calls ≥ ERROR_THRESHOLD
    open   → half_open   after OPEN_COOLDOWN_S
    half_open → closed   on next success
    half_open → open     on next failure
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, Optional, Tuple

WINDOW_SIZE = 30
ERROR_THRESHOLD = 0.40
OPEN_COOLDOWN_S = 60.0


@dataclass
class _CBState:
    window: deque = field(default_factory=lambda: deque(maxlen=WINDOW_SIZE))
    state: str = "closed"        # closed | half_open | open
    opened_at: float = 0.0
    last_success_ts: float = 0.0
    last_error: str = ""
    last_error_ts: float = 0.0


class CircuitBreaker:
    def __init__(self) -> None:
        self._lock = RLock()
        self._by_provider: Dict[str, _CBState] = {}

    def _get(self, provider: str) -> _CBState:
        with self._lock:
            if provider not in self._by_provider:
                self._by_provider[provider] = _CBState()
            return self._by_provider[provider]

    def allow(self, provider: str) -> bool:
        cb = self._get(provider)
        with self._lock:
            if cb.state == "closed":
                return True
            if cb.state == "open":
                if time.time() - cb.opened_at >= OPEN_COOLDOWN_S:
                    cb.state = "half_open"
                    return True
                return False
            return True  # half_open lets one call through

    def record(self, provider: str, ok: bool, error: str = "") -> None:
        cb = self._get(provider)
        now = time.time()
        with self._lock:
            cb.window.append(1 if ok else 0)
            if ok:
                cb.last_success_ts = now
                if cb.state == "half_open":
                    cb.state = "closed"
                    cb.window.clear()
            else:
                cb.last_error = error[:200]
                cb.last_error_ts = now
                if cb.state == "half_open":
                    cb.state = "open"
                    cb.opened_at = now
                elif cb.state == "closed" and len(cb.window) >= 10:
                    errs = cb.window.count(0)
                    if errs / len(cb.window) >= ERROR_THRESHOLD:
                        cb.state = "open"
                        cb.opened_at = now

    def snapshot(self) -> Dict[str, Dict[str, object]]:
        with self._lock:
            out = {}
            for provider, cb in self._by_provider.items():
                window_len = len(cb.window)
                errs = cb.window.count(0)
                out[provider] = {
                    "state": cb.state,
                    "window_size": window_len,
                    "error_rate": (errs / window_len) if window_len else 0.0,
                    "opened_at": cb.opened_at or None,
                    "last_success_ts": cb.last_success_ts or None,
                    "last_error": cb.last_error or None,
                    "last_error_ts": cb.last_error_ts or None,
                }
            return out

    def reset(self, provider: str) -> None:
        with self._lock:
            self._by_provider[provider] = _CBState()


_BREAKER = CircuitBreaker()


def get_breaker() -> CircuitBreaker:
    return _BREAKER
