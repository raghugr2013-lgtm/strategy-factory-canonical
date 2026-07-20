"""Phase 2 Stage 4 P4B.8 — Operator controls.

Three admin-only endpoints (mounted by `coe_gamma/router.py`):

  POST /api/coe/circuit-breaker/{provider}/reset
  POST /api/coe/queue/pause?class=<X>
  POST /api/coe/queue/resume?class=<X>

Feature flag: `COE_OPERATOR_CONTROLS_ENABLED` (default OFF). When off,
every endpoint returns HTTP 503. Each action writes one audit row
into `coe_operator_events` for post-hoc review.

Pause / resume are declarative — they set an in-memory (or Mongo-backed
via the injected sink) predicate that the admission gate consults.
Existing in-flight work drains normally.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_operator_controls_enabled() -> bool:
    return _flag("COE_OPERATOR_CONTROLS_ENABLED", False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


COE_OPERATOR_EVENTS_COLLECTION = "coe_operator_events"


@dataclass
class OperatorAction:
    action_id:      str
    kind:           str          # "circuit_reset" | "queue_pause" | "queue_resume"
    target:         str          # provider or workload class
    requested_by:   str
    reason:         str
    at:             str
    pipeline_version_note: str   = "coe_gamma_operator_v1"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OperatorControls:
    """Composable operator-controls surface.

    Args:
        breaker_reset_hook: `(provider) → awaitable[bool]` — force the
            provider's circuit CLOSED. Return True on success.
        audit_sink: `(dict) → awaitable[None]` — persist the action.
    """

    def __init__(
        self,
        *,
        breaker_reset_hook: Optional[Callable[[str], Awaitable[bool]]] = None,
        audit_sink:         Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        self._breaker_reset = breaker_reset_hook
        self._audit_sink = audit_sink
        self._paused: Set[str] = set()

    async def _audit(self, action: OperatorAction) -> None:
        if self._audit_sink is None:
            logger.debug("[coe_gamma.operator] %s", action.to_dict())
            return
        try:
            await self._audit_sink(action.to_dict())
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[coe_gamma.operator] audit sink failed: %s", e)

    # ── Public API ────────────────────────────────────────────────────

    async def circuit_reset(
        self,
        *,
        provider:      str,
        requested_by:  str,
        reason:        str,
    ) -> Dict[str, Any]:
        if not is_operator_controls_enabled():
            return {"status": "flag_off"}
        ok = True
        if self._breaker_reset is not None:
            try:
                ok = bool(await self._breaker_reset(provider))
            except Exception as e:                             # noqa: BLE001
                ok = False
                logger.warning("[coe_gamma.operator] breaker reset failed: %s", e)
        action = OperatorAction(
            action_id=uuid.uuid4().hex,
            kind="circuit_reset",
            target=provider,
            requested_by=requested_by,
            reason=reason,
            at=_now_iso(),
        )
        await self._audit(action)
        return {
            "status":   "reset" if ok else "reset_failed",
            "provider": provider,
            "action_id": action.action_id,
        }

    async def queue_pause(
        self,
        *,
        workload_class: str,
        requested_by:   str,
        reason:         str,
    ) -> Dict[str, Any]:
        if not is_operator_controls_enabled():
            return {"status": "flag_off"}
        cls = (workload_class or "").strip().lower()
        self._paused.add(cls)
        action = OperatorAction(
            action_id=uuid.uuid4().hex, kind="queue_pause",
            target=cls, requested_by=requested_by, reason=reason,
            at=_now_iso(),
        )
        await self._audit(action)
        return {"status": "paused", "workload_class": cls, "action_id": action.action_id}

    async def queue_resume(
        self,
        *,
        workload_class: str,
        requested_by:   str,
        reason:         str,
    ) -> Dict[str, Any]:
        if not is_operator_controls_enabled():
            return {"status": "flag_off"}
        cls = (workload_class or "").strip().lower()
        was_paused = cls in self._paused
        self._paused.discard(cls)
        action = OperatorAction(
            action_id=uuid.uuid4().hex, kind="queue_resume",
            target=cls, requested_by=requested_by, reason=reason,
            at=_now_iso(),
        )
        await self._audit(action)
        return {
            "status":         "resumed" if was_paused else "not_paused",
            "workload_class": cls,
            "action_id":      action.action_id,
        }

    def is_paused(self, workload_class: str) -> bool:
        return (workload_class or "").strip().lower() in self._paused


_CONTROLS: Optional[OperatorControls] = None


def get_operator_controls() -> OperatorControls:
    global _CONTROLS
    if _CONTROLS is None:
        _CONTROLS = OperatorControls()
    return _CONTROLS


def _reset_for_tests() -> None:
    global _CONTROLS
    _CONTROLS = None
