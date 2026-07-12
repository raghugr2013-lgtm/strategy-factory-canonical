"""
Factory Supervisor FS-P1.2 — Transport-neutral remote-submit interface.

Discipline (operator-locked):
  * **Provider-neutral & transport-neutral.** The interface here is a
    pure abstract base; HTTP-stub is one implementation. gRPC,
    WebSocket, async queue, etc. drop in by implementing the same
    `RemoteTransport` ABC — NO call-site change anywhere.
  * **Dormant.** Today only the HTTP-stub `transport.submit(...)`
    returns a deterministic `NotConnectedResult` — no real network
    traffic. The worker_runtime treats `NotConnectedResult` as a
    soft-defer and re-enqueues. Activation of the real HTTP transport
    requires explicit operator sign-off + `FS_REMOTE_TRANSPORT=http`.
  * **No SDK pinning.** This module DOES NOT import httpx, aiohttp,
    requests, grpcio, websockets, redis, kombu, kafka-python, etc.
    The HTTP transport stub talks to `urllib.request` from stdlib so
    no dependency footprint is added in FS-P1.2.

Public surface:
    RemoteTransport          — ABC; .submit(envelope) → RemoteSubmitResult
    RemoteSubmitResult       — frozen dataclass
    NotConnectedResult       — sentinel "transport not yet enabled"
    TRANSPORT_REGISTRY       — name → factory
    resolve_transport()      — read FS_REMOTE_TRANSPORT env (default 'none')
    HttpRemoteTransport      — stub that always returns NotConnectedResult
"""
from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TRANSPORT_NAME = "none"


@dataclass
class RemoteSubmitResult:
    """Outcome of a remote-submit call. Always a clean dict shape."""
    transport:     str
    accepted:      bool          # remote acknowledged the envelope
    soft_defer:    bool          # transport ok but remote asked us to wait
    error:         Optional[str] = None
    remote_id:     Optional[str] = None
    remote_ts:     Optional[str] = None
    detail:        Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transport":  self.transport,
            "accepted":   self.accepted,
            "soft_defer": self.soft_defer,
            "error":      self.error,
            "remote_id":  self.remote_id,
            "remote_ts":  self.remote_ts,
            "detail":     dict(self.detail or {}),
        }


def NotConnectedResult(transport: str = "none",
                       reason: str = "not_connected") -> RemoteSubmitResult:
    """Stable sentinel — transport not yet active."""
    return RemoteSubmitResult(
        transport=transport, accepted=False, soft_defer=True,
        error=reason,
        detail={"phase": "FS-P1.2", "note": "transport stub; no real submit"},
    )


class RemoteTransport(abc.ABC):
    """Transport-neutral remote-submit interface.

    A future gRPC/WebSocket/async-queue implementation MUST subclass
    this and provide an async `submit(envelope)` method. Nothing else
    in factory_supervisor knows about transport specifics.
    """

    name: str = "abstract"

    @abc.abstractmethod
    async def submit(self,
                     envelope: Dict[str, Any],
                     *,
                     target_host: Optional[str] = None,
                     ) -> RemoteSubmitResult: ...

    async def healthcheck(self) -> Dict[str, Any]:
        """Optional. Default: returns transport-name + 'unknown'."""
        return {"transport": self.name, "status": "unknown"}


# ─── HTTP stub transport (no real traffic) ──────────────────────────

class HttpRemoteTransport(RemoteTransport):
    """Stub HTTP transport. Always returns NotConnectedResult.

    Real activation requires:
      1. operator sign-off
      2. `FS_REMOTE_TRANSPORT=http`
      3. a concrete implementation replacing this body with an httpx
         POST to the assigned host's /api/factory-supervisor/submit.
    """
    name = "http"

    async def submit(self,
                     envelope: Dict[str, Any],
                     *,
                     target_host: Optional[str] = None,
                     ) -> RemoteSubmitResult:
        return NotConnectedResult(
            transport="http",
            reason="http_transport_stub_FS_P1_2",
        )

    async def healthcheck(self) -> Dict[str, Any]:
        return {
            "transport": "http",
            "status":    "stub_only",
            "note":      "FS-P1.2 ships the interface; activation in FS-P1.5+",
        }


class NoopTransport(RemoteTransport):
    """The default. Always refuses cleanly so caller treats local."""
    name = "none"

    async def submit(self,
                     envelope: Dict[str, Any],
                     *,
                     target_host: Optional[str] = None,
                     ) -> RemoteSubmitResult:
        return NotConnectedResult(
            transport="none",
            reason="remote_transport_disabled",
        )


# ─── Registry + resolver ────────────────────────────────────────────

TRANSPORT_REGISTRY: Dict[str, Callable[[], RemoteTransport]] = {
    "none": NoopTransport,
    "http": HttpRemoteTransport,
}


def resolve_transport() -> RemoteTransport:
    """Read FS_REMOTE_TRANSPORT from feature_flags; unknown → noop."""
    try:
        from engines.feature_flags import flag
        name = str(flag("FS_REMOTE_TRANSPORT") or DEFAULT_TRANSPORT_NAME)
    except Exception:                                          # pragma: no cover
        name = DEFAULT_TRANSPORT_NAME
    factory = TRANSPORT_REGISTRY.get(name) or NoopTransport
    return factory()


def transport_manifest() -> Dict[str, Any]:
    """Diagnostics snapshot for /status + Copilot."""
    return {
        "default":   DEFAULT_TRANSPORT_NAME,
        "active":    _safe_resolve_name(),
        "available": list(TRANSPORT_REGISTRY.keys()),
        "ts":        datetime.now(timezone.utc).isoformat(),
    }


def _safe_resolve_name() -> str:
    try:
        from engines.feature_flags import flag
        n = str(flag("FS_REMOTE_TRANSPORT") or DEFAULT_TRANSPORT_NAME)
        return n if n in TRANSPORT_REGISTRY else DEFAULT_TRANSPORT_NAME
    except Exception:                                          # pragma: no cover
        return DEFAULT_TRANSPORT_NAME
