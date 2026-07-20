"""Phase 2 Stage 4 — Connector retry policy (P4A.0).

Declarative exponential-backoff retry with jitter, per PHASE_4_MASTER_PLAN
§3.5. Pure data + `should_retry()` decision helpers — the actual sleep
lives in the connector's async HTTP wrapper. This keeps the policy
testable without any real I/O.

Rate-limit awareness:
  * `retry_on_status` — HTTP status codes that qualify as transient.
    Default `{429, 502, 503, 504}`.
  * `cool_off_on_429_s` — mandatory floor on the 429 backoff (server
    is telling us to slow down; we respect it regardless of the
    exponential schedule).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Tuple


DEFAULT_RETRY_STATUSES: FrozenSet[int] = frozenset({429, 502, 503, 504})


@dataclass(frozen=True)
class RetryPolicy:
    """Declarative retry policy.

    Attributes:
        max_attempts: Total attempts, including the initial. `1` = no
            retries. Must be ≥ 1.
        base_delay_s: First backoff interval.
        max_delay_s: Cap on any single backoff.
        jitter: `"full"` = uniform(0, delay); `"equal"` = delay/2 +
            uniform(0, delay/2); `"none"` = deterministic (test-friendly).
        retry_on_status: HTTP status codes that trigger a retry.
        retry_on_exc: Exception types that trigger a retry.
        cool_off_on_429_s: Minimum backoff floor on 429.
    """
    max_attempts:     int   = 3
    base_delay_s:     float = 2.0
    max_delay_s:      float = 60.0
    jitter:           str   = "full"
    retry_on_status:  FrozenSet[int] = field(default_factory=lambda: DEFAULT_RETRY_STATUSES)
    retry_on_exc:     Tuple[type, ...] = field(default_factory=tuple)
    cool_off_on_429_s: float = 60.0

    def should_retry_on_status(self, status: int) -> bool:
        return status in self.retry_on_status

    def should_retry_on_exc(self, exc: BaseException) -> bool:
        return isinstance(exc, self.retry_on_exc) if self.retry_on_exc else False

    def compute_delay(self, attempt_index: int, *, last_status: Optional[int] = None) -> float:
        """Return the sleep-before-next-attempt in seconds.

        `attempt_index` is 0-based (0 = after the first failed attempt).
        """
        if attempt_index < 0:
            attempt_index = 0
        exp = self.base_delay_s * (2 ** attempt_index)
        raw = min(exp, self.max_delay_s)

        if last_status == 429:
            raw = max(raw, self.cool_off_on_429_s)

        if self.jitter == "none":
            return raw
        if self.jitter == "equal":
            half = raw / 2.0
            return half + random.uniform(0, half)
        # "full" (default): uniform(0, raw)
        return random.uniform(0, raw)


# ── Named policies (per WorkloadClass — plan §3.5) ───────────────────

CONNECTOR_DEFAULT = RetryPolicy(
    max_attempts=3,
    base_delay_s=2.0,
    max_delay_s=60.0,
    jitter="full",
    cool_off_on_429_s=60.0,
)

CONNECTOR_CONSERVATIVE = RetryPolicy(
    max_attempts=2,
    base_delay_s=4.0,
    max_delay_s=30.0,
    jitter="equal",
    cool_off_on_429_s=90.0,
)

CONNECTOR_AGGRESSIVE = RetryPolicy(
    max_attempts=5,
    base_delay_s=1.0,
    max_delay_s=30.0,
    jitter="full",
    cool_off_on_429_s=30.0,
)
