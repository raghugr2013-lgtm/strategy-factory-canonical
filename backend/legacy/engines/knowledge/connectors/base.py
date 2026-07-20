"""Phase 2 Stage 4 — AbstractConnector base class (P4A.0).

Composition helper for concrete `KnowledgeConnector` implementations.
Every concrete connector inherits from this base to get:

  * declarative auth (via `ConnectorAuth`)
  * declarative retry (via `RetryPolicy`)
  * built-in health bookkeeping (via `ConnectorObserver`)
  * flag-aware dormancy (`is_flag_enabled()`)
  * a common `content_hash()` helper (SHA-256 over utf-8 bytes)
  * a common `health_snapshot()` composer

Concrete connectors override:

  * `discover(query)` — yield `Reference`s
  * `fetch(ref)`      — return one `RawKnowledgeItem`
  * `rate_limit()`    — declared rate limits

Every concrete connector remains a pure `KnowledgeConnector` Protocol
implementation — the base class is a convenience for shared plumbing,
not a required inheritance chain. `GithubConnector` (which pre-dates
this base) continues to work unmodified.

Design invariants:
  * `discover` / `fetch` DO NOT crash on external failure — they log
    and either yield fewer items or return an item with `content_hash`
    empty. Callers already tolerate this per the Stage-3.β pipeline.
  * When the connector's flag is OFF, `discover` yields nothing and
    `fetch` returns an item with `content_bytes=None`.
  * Every network attempt (once real I/O is wired) flows through
    `_call_with_retry()` — one place to observe, backoff, retry.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any, AsyncIterator, Callable, Dict, FrozenSet, Optional

from ..connector import (
    ConnectorCapabilities,
    DiscoveryQuery,
    RateLimit,
    RawKnowledgeItem,
    Reference,
    now_iso,
)
from ..connector_auth import ConnectorAuth, NoAuth
from ..connector_health import (
    ConnectorHealthSnapshot,
    ConnectorState,
    ConnectorObserver,
    get_observer,
)
from ..connector_retry import CONNECTOR_DEFAULT, RetryPolicy
from ..domains import KnowledgeDomain

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


class AbstractConnector:
    """Base class for Stage-4 connectors.

    Subclasses SHOULD override class attributes:
      * `name`, `source_type`, `supported_domains`, `default_trust_tier`,
        `supported_licenses`, `capabilities`, `flag_name`,
        `connector_version`, `source_contract_version`
      * `_retry_policy` (defaults to `CONNECTOR_DEFAULT`)
      * `_auth` (defaults to `NoAuth()`)
    """

    # ── Protocol-facing attributes (subclasses override) ─────────────
    name:                str                              = "abstract"
    source_type:         str                              = "unknown"
    supported_domains:   FrozenSet[KnowledgeDomain]       = frozenset()
    default_trust_tier:  int                              = 3
    supported_licenses:  FrozenSet[str]                   = frozenset({"*"})
    capabilities:        ConnectorCapabilities            = ConnectorCapabilities()

    # ── Stage-4 additions ────────────────────────────────────────────
    flag_name:                  str    = "UKIE_CONNECTOR_ABSTRACT_ENABLED"
    connector_version:          str    = "0.1.0"
    source_contract_version:    int    = 1
    _retry_policy:              RetryPolicy = CONNECTOR_DEFAULT
    _auth:                      ConnectorAuth = NoAuth()

    def __init__(
        self,
        *,
        observer: Optional[ConnectorObserver] = None,
        auth:     Optional[ConnectorAuth]     = None,
        retry:    Optional[RetryPolicy]       = None,
    ) -> None:
        self._observer = observer or get_observer()
        if auth is not None:
            # class-level default is immutable frozen dataclass — replace at instance
            object.__setattr__(self, "_auth", auth)
        if retry is not None:
            object.__setattr__(self, "_retry_policy", retry)
        # Emit initial state so health snapshots have something to report
        self._observer.note_flag_state(self.name, self.is_flag_enabled())

    # ── Flag helpers ─────────────────────────────────────────────────

    def is_flag_enabled(self) -> bool:
        return _flag(self.flag_name, False)

    def is_available(self) -> bool:
        """True iff the connector's flag is on AND auth is configured."""
        return self.is_flag_enabled() and self._auth.is_configured()

    # ── Protocol methods — subclasses override ────────────────────────

    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[Reference]:  # type: ignore[override]
        """Default implementation — yield nothing. Subclasses override."""
        self._observer.note_flag_state(self.name, self.is_flag_enabled())
        if False:  # pragma: no cover — keeps AsyncIterator return type
            yield  # type: ignore[unreachable]

    async def fetch(self, ref: Reference) -> RawKnowledgeItem:
        """Default implementation — return an empty item. Subclasses
        override. Returns a shape that will not pass the pipeline (no
        content_bytes) — this default is only invoked in the abstract
        base's own test surface.
        """
        self._observer.note_flag_state(self.name, self.is_flag_enabled())
        return RawKnowledgeItem(
            domain=next(iter(self.supported_domains), KnowledgeDomain.STRATEGY),
            connector_name=self.name,
            source_url=ref.source_url,
            source_ref=ref.source_ref,
            content_hash="",
            fetched_at=now_iso(),
            content_bytes=None,
            content_mime=None,
        )

    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=30, burst=5, cooloff_seconds=60.0)

    # ── Shared helpers ───────────────────────────────────────────────

    @staticmethod
    def content_hash(payload: bytes) -> str:
        digest = hashlib.sha256(payload).hexdigest() if payload else ""
        return f"sha256:{digest}" if digest else ""

    async def _call_with_retry(
        self,
        fn: Callable[[], "asyncio.Future[Any]"],
        *,
        on_status: Optional[Callable[[Any], int]] = None,
    ) -> Any:
        """Execute `fn()` with exponential backoff.

        `on_status`, if provided, extracts an HTTP status from the fn
        result to check against the retry policy. Exceptions in
        `_retry_policy.retry_on_exc` also trigger a retry.

        On success: `note_success`. On failure (final): `note_failure`.
        Each intermediate retry: `note_retry`.
        """
        policy = self._retry_policy
        last_exc: Optional[BaseException] = None
        last_status: Optional[int] = None
        result: Any = None
        for attempt in range(max(1, policy.max_attempts)):
            try:
                result = await fn()
            except BaseException as exc:  # noqa: BLE001
                last_exc = exc
                if not policy.should_retry_on_exc(exc):
                    break
            else:
                status = on_status(result) if on_status else 0
                if not status or not policy.should_retry_on_status(status):
                    self._observer.note_success(self.name)
                    return result
                last_status = status
            # Prepare next attempt (or give up)
            if attempt + 1 >= policy.max_attempts:
                break
            self._observer.note_retry(self.name)
            delay = policy.compute_delay(attempt, last_status=last_status)
            if last_status == 429:
                # honour explicit cooling window
                from datetime import datetime, timedelta, timezone
                until = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
                self._observer.note_rate_limit(self.name, until)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:                     # pragma: no cover
                raise

        # Final failure
        err = str(last_exc) if last_exc else f"status={last_status}"
        self._observer.note_failure(self.name, err)
        if last_exc is not None:
            raise last_exc
        return result  # last result with the retryable status (caller decides)

    # ── Health snapshot ──────────────────────────────────────────────

    def health_snapshot(self) -> ConnectorHealthSnapshot:
        # Refresh state marker for flag transitions
        self._observer.note_flag_state(self.name, self.is_flag_enabled())
        obs = self._observer.snapshot(self.name)
        return ConnectorHealthSnapshot(
            name=self.name,
            state=obs.state,
            flag_name=self.flag_name,
            flag_enabled=self.is_flag_enabled(),
            auth_configured=self._auth.is_configured(),
            auth_mode=self._auth.mode,
            supported_domains=sorted(d.value for d in self.supported_domains),
            default_trust_tier=self.default_trust_tier,
            last_success_at=obs.last_success_at,
            last_failure_at=obs.last_failure_at,
            last_error=obs.last_error,
            retry_count_1h=self._observer.retry_count_last_hour(self.name),
            rate_limit_backoff_until=obs.rate_limit_backoff_until,
            connector_version=self.connector_version,
            source_contract_version=self.source_contract_version,
            capabilities=self.capabilities.to_dict(),
            rate_limit=self.rate_limit().to_dict(),
        )
