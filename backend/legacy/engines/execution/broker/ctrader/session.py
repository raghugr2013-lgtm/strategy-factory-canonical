"""cTrader Open API — OAuth session management.

Real cTrader OAuth tokens expire after ~60 min. This module:
  * caches the token pair (access, refresh) in-process
  * exposes `is_expired()` with a configurable safety margin
  * refreshes via a `refresh_fn` callback (transport-agnostic — the
    real HTTP call lives in `client.py` / a subordinate task)

Test-friendliness: `OAuthSession` accepts an injected `clock_fn` so
tests can drive time forward deterministically.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional


class OAuthTokenExpiredError(RuntimeError):
    """Raised when a request is made with an expired token AND no
    refresh callback is available."""


@dataclass
class OAuthSession:
    access_token:      str
    refresh_token:     str
    expires_at_epoch:  float          # UNIX seconds
    account_id:        str
    safety_margin_s:   int = 600      # refresh 10 min before hard expiry
    clock_fn:          Callable[[], float] = time.time

    def seconds_to_expiry(self) -> float:
        return self.expires_at_epoch - self.clock_fn()

    def is_expired(self) -> bool:
        return self.seconds_to_expiry() <= 0

    def is_expiring_soon(self) -> bool:
        return self.seconds_to_expiry() <= self.safety_margin_s

    def apply_refresh(self, access_token: str, refresh_token: str,
                        expires_in_s: int) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at_epoch = self.clock_fn() + int(expires_in_s)
