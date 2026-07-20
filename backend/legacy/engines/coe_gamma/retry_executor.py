"""Phase 2 Stage 4 P4B.1 — Retry executor.

Wraps any async callable (a WorkloadQueue task submit, an HTTP fetch,
an LLM call) with an exponential-backoff retry loop. Per-class
policies match PHASE_4_MASTER_PLAN §4.1:

  MARKET_DATA:      5 attempts, 2s → 60s
  AGENT:            3 attempts, 4s → 30s
  BACKTEST:         2 attempts, 10s → 60s
  EXECUTION:        0 retries (fail fast — no idempotency guarantee)
  MONITORING:       3 attempts, 2s → 30s
  META_LEARNING:    3 attempts, 5s → 60s
  KNOWLEDGE:        3 attempts, 2s → 30s

Feature-gated by `COE_RETRY_ENABLED` (default OFF). When off, the
executor is a pass-through — `execute()` runs the callable exactly
once with no retry, no backoff. This preserves Stage-1..3 behaviour.

Every retry event writes a `workload_events` row (deferred write —
the executor calls the injected `event_sink` callable, which the
operator wires to the existing events collection during activation).
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_retry_enabled() -> bool:
    return _flag("COE_RETRY_ENABLED", False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Per-class retry policy ───────────────────────────────────────────

@dataclass(frozen=True)
class ClassRetryPolicy:
    """Per-WorkloadClass retry schedule."""
    max_attempts: int
    base_delay_s: float
    max_delay_s:  float
    jitter:       str = "full"     # "full" | "equal" | "none"

    def compute_delay(self, attempt_index: int) -> float:
        if attempt_index < 0:
            attempt_index = 0
        exp = self.base_delay_s * (2 ** attempt_index)
        raw = min(exp, self.max_delay_s)
        if self.jitter == "none":
            return raw
        if self.jitter == "equal":
            half = raw / 2.0
            return half + random.uniform(0, half)
        return random.uniform(0, raw)


# Class → policy mapping (plan §4.1)
CLASS_RETRY_POLICIES: Dict[str, ClassRetryPolicy] = {
    "market_data":   ClassRetryPolicy(max_attempts=5, base_delay_s=2.0,  max_delay_s=60.0),
    "agent":         ClassRetryPolicy(max_attempts=3, base_delay_s=4.0,  max_delay_s=30.0),
    "backtest":      ClassRetryPolicy(max_attempts=2, base_delay_s=10.0, max_delay_s=60.0),
    "execution":     ClassRetryPolicy(max_attempts=1, base_delay_s=0.0,  max_delay_s=0.0),
    "monitoring":    ClassRetryPolicy(max_attempts=3, base_delay_s=2.0,  max_delay_s=30.0),
    "meta_learning": ClassRetryPolicy(max_attempts=3, base_delay_s=5.0,  max_delay_s=60.0),
    "knowledge":     ClassRetryPolicy(max_attempts=3, base_delay_s=2.0,  max_delay_s=30.0),
}

# Fallback for unknown class names — conservative
_DEFAULT_POLICY = ClassRetryPolicy(max_attempts=2, base_delay_s=4.0, max_delay_s=30.0)


def retry_policy_for_class(workload_class: str) -> ClassRetryPolicy:
    if not workload_class:
        return _DEFAULT_POLICY
    return CLASS_RETRY_POLICIES.get(workload_class.strip().lower(), _DEFAULT_POLICY)


# ── Outcome ──────────────────────────────────────────────────────────

@dataclass
class RetryOutcome:
    """Result of `RetryExecutor.execute()`.

    Attributes:
        ok: True iff the callable returned a value on any attempt.
        attempts: Total attempts made (≥ 1).
        result: The final callable return value on success. None on failure.
        error: Truncated error message on failure.
        history: Per-attempt outcome dicts for audit.
        workload_class: The class the policy was resolved from.
        task_id: Correlation id (uuid or caller-supplied).
        pipeline_version_note: Stamp for future replay.
    """
    ok:              bool
    attempts:        int
    result:          Any                     = None
    error:           Optional[str]           = None
    history:         list                    = field(default_factory=list)
    workload_class:  str                     = ""
    task_id:         str                     = ""
    pipeline_version_note: str               = "coe_gamma_retry_v1"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Drop the raw `result` from serialised dicts — callers may want
        # to log outcomes without accidentally including big payloads.
        d["result"] = "<omitted>" if self.result is not None else None
        return d


# ── Executor ─────────────────────────────────────────────────────────

class RetryExecutor:
    """Runs a callable with per-class exponential backoff.

    Args:
        event_sink: Optional callable `(dict) → awaitable` that
            receives one `workload_events` row per attempt. When None,
            events are only logged at DEBUG.
        sleep: Injectable sleep helper for tests (defaults to
            asyncio.sleep).
    """

    def __init__(
        self,
        *,
        event_sink: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
        sleep:      Optional[Callable[[float], Awaitable[None]]]          = None,
    ) -> None:
        self._event_sink = event_sink
        self._sleep = sleep or asyncio.sleep

    async def execute(
        self,
        callable_: Callable[[], Awaitable[Any]],
        *,
        workload_class:  str,
        task_id:         Optional[str]                = None,
        is_retryable:    Optional[Callable[[BaseException], bool]] = None,
    ) -> RetryOutcome:
        """Execute `callable_` with retries.

        When `COE_RETRY_ENABLED` is off, this is a pass-through: one
        attempt, no backoff. On success returns `RetryOutcome(ok=True)`;
        on failure returns `RetryOutcome(ok=False, error=...)`.

        `is_retryable`, if supplied, decides whether an exception
        triggers a retry. Default: retry on ALL exceptions (subject to
        `max_attempts`). Non-retryable exceptions terminate immediately.
        """
        tid = task_id or uuid.uuid4().hex
        history: list = []

        if not is_retry_enabled():
            # Pass-through — behave EXACTLY like Stage-1..3
            try:
                result = await callable_()
                return RetryOutcome(ok=True, attempts=1, result=result,
                                    workload_class=workload_class, task_id=tid)
            except BaseException as exc:                       # noqa: BLE001
                return RetryOutcome(ok=False, attempts=1, error=str(exc)[:200],
                                    workload_class=workload_class, task_id=tid)

        policy = retry_policy_for_class(workload_class)
        last_exc: Optional[BaseException] = None

        for attempt in range(max(1, policy.max_attempts)):
            attempt_no = attempt + 1
            started_at = _now_iso()
            try:
                result = await callable_()
                history.append({
                    "attempt":       attempt_no,
                    "at":            started_at,
                    "outcome":       "ok",
                })
                await self._emit({
                    "task_id":        tid,
                    "workload_class": workload_class,
                    "attempt":        attempt_no,
                    "outcome":        "ok",
                    "at":             started_at,
                })
                return RetryOutcome(ok=True, attempts=attempt_no, result=result,
                                    history=history,
                                    workload_class=workload_class, task_id=tid)
            except BaseException as exc:                       # noqa: BLE001
                last_exc = exc
                err = str(exc)[:200]
                retryable = True if is_retryable is None else bool(is_retryable(exc))
                history.append({
                    "attempt":       attempt_no,
                    "at":            started_at,
                    "outcome":       "error",
                    "error":         err,
                    "retryable":     retryable,
                })
                await self._emit({
                    "task_id":        tid,
                    "workload_class": workload_class,
                    "attempt":        attempt_no,
                    "outcome":        "error",
                    "error":          err,
                    "retryable":      retryable,
                    "at":             started_at,
                })
                if not retryable:
                    break
            if attempt_no >= policy.max_attempts:
                break
            delay = policy.compute_delay(attempt)
            await self._sleep(delay)

        return RetryOutcome(
            ok=False,
            attempts=len(history),
            error=str(last_exc)[:200] if last_exc else "unknown",
            history=history,
            workload_class=workload_class,
            task_id=tid,
        )

    async def _emit(self, row: Dict[str, Any]) -> None:
        if self._event_sink is None:
            logger.debug("[coe_gamma.retry] event: %s", row)
            return
        try:
            await self._event_sink(row)
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[coe_gamma.retry] event sink failed: %s", e)
