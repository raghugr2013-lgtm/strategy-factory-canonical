"""
VPS Scaling P1.D — Admission wrapper (the wrap-site helper).

`admission_gate(WorkloadClass)` is an async context manager that
composes the P1.C primitives into the single API every wrap site
calls:

    async with admission_gate(WorkloadClass.FACTORY_CYCLE):
        ...existing work...

Behaviour (per CAPACITY_ENGINE_DESIGN.md §7 + operator P1.D scope):
  * Flag OFF (`ENABLE_ADMISSION_CONTROL=false`, default):
      - __aenter__ returns immediately. No gate call, no journal write,
        no event emit, no counter increment.
      - **Byte-identical to the pre-P1.C/P1.D world.**
  * Flag ON:
      1. Calls `admission_controller.gate(cls)` (pure, ~µs).
      2. Persists the verdict via `admission_controller.record()` (best-
         effort; Mongo failure does NOT change the verdict).
      3. On `refuse`:  emits ADMISSION_REFUSED, raises `AdmissionRefused`.
      4. On `defer`:   emits ADMISSION_DEFERRAL, raises `AdmissionDeferred`.
      5. On `admit`:   `queue_pressure.incr(cls)`, evaluates
         HIGH_QUEUE_PRESSURE + WORKER_SATURATION + CAPACITY_WARNING
         thresholds, emits any tripped events, then enters the block.
      6. On __aexit__: `queue_pressure.decr(cls)` ALWAYS (even on exc).

Honest-refusal: refuses are raised, not silenced. Callers MAY catch
`AdmissionRefused` / `AdmissionDeferred` and decide policy (skip,
retry, log). The wrap sites in P1.D do NOT swallow them — they
propagate to the API layer which maps to HTTP 503/429.

Operator final authority: a `force=True` kwarg admits regardless of
band (still journaled with `reason=force_override`).

Rollback-in-60s: every wrap site can be neutered by flipping
`ENABLE_ADMISSION_CONTROL=false` (no restart needed once supervisord
reloads env, < 5 s in practice).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from engines import admission_controller, queue_pressure, scaling_events
from engines.workload_classes import WorkloadClass

logger = logging.getLogger(__name__)

# Operator-visible thresholds (mirror queue_pressure.snapshot bands).
# These are evaluated AFTER incr() to detect "we just crossed the line"
# transitions. They're soft thresholds — events are advisory.
WORKER_SATURATION_THRESHOLD = 0.90
HIGH_PRESSURE_BANDS         = ("high", "critical")
CAPACITY_WARNING_BANDS      = ("warn", "critical")


# ─── Exceptions ─────────────────────────────────────────────────────

class AdmissionError(Exception):
    """Base for admission-time rejection. Carries the verdict so the
    caller can audit the reason / band without re-running the gate."""

    def __init__(self, message: str, verdict: Optional[Dict[str, Any]] = None,
                 retry_after_sec: Optional[int] = None):
        super().__init__(message)
        self.verdict          = verdict or {}
        self.retry_after_sec  = retry_after_sec


class AdmissionRefused(AdmissionError):
    """gate() returned `refuse`. The caller MUST NOT retry without
    operator intervention (the host is critical or unknown)."""


class AdmissionDeferred(AdmissionError):
    """gate() returned `defer`. The caller MAY retry after
    `retry_after_sec` seconds (typically 30 s)."""


# ─── The async context manager ──────────────────────────────────────

class admission_gate:                                          # noqa: N801 (deliberate lower-case API)
    """Async context manager — the only public wrap-site primitive.

    Usage:
        async with admission_gate(WorkloadClass.BACKTEST):
            result = await some_cpu_bound_work()
        # counter is decremented in finally

    The class is intentionally lower-cased to read as a verb at call
    sites (mirrors `contextlib.suppress` etc.).
    """

    def __init__(self, cls: WorkloadClass, *, force: bool = False,
                 metadata: Optional[Dict[str, Any]] = None):
        if not isinstance(cls, WorkloadClass):
            raise TypeError(
                f"admission_gate expects WorkloadClass, got {type(cls).__name__}"
            )
        self.cls       = cls
        self.force     = bool(force)
        self.metadata  = dict(metadata or {})
        self._held     = False        # set True after a successful incr()
        self._verdict  = None         # populated on flag-ON entry

    async def __aenter__(self) -> "admission_gate":
        # ─ Flag-OFF short-circuit: byte-identical to pre-P1.D world.
        if not admission_controller.is_enabled():
            return self

        verdict = admission_controller.gate(self.cls, force=self.force)
        self._verdict = verdict

        # ─ Refuse — emit + raise (no incr).
        if verdict.decision == admission_controller.DECISION_REFUSE:
            try:
                await admission_controller.record(verdict)
            except Exception as e:                             # pragma: no cover
                logger.debug("[admission_gate] refuse journal raised: %s", e)
            await self._emit_refuse_events(verdict)
            raise AdmissionRefused(
                f"admission refused for {self.cls.value}: {verdict.reason}",
                verdict=verdict.to_dict(),
            )

        # ─ Defer — emit + raise (no incr).
        if verdict.decision == admission_controller.DECISION_DEFER:
            try:
                await admission_controller.record(verdict)
            except Exception as e:                             # pragma: no cover
                logger.debug("[admission_gate] defer journal raised: %s", e)
            await scaling_events.emit(
                scaling_events.EVENT_ADMISSION_DEFERRAL,
                {
                    "class_":          self.cls.value,
                    "reason":          verdict.reason,
                    "band":            verdict.band,
                    "pressure_band":   verdict.pressure_band,
                    "retry_after_sec": verdict.retry_after_sec,
                    "metadata":        self.metadata or None,
                },
            )
            raise AdmissionDeferred(
                f"admission deferred for {self.cls.value}: {verdict.reason}",
                verdict=verdict.to_dict(),
                retry_after_sec=verdict.retry_after_sec,
            )

        # ─ Admit — increment the counter SYNCHRONOUSLY before any await
        #   so concurrent gate() callers on the same event loop see the
        #   incremented depth and respect the cap.
        queue_pressure.incr(self.cls)
        self._held = True

        # Now the awaits are safe (counter is already reserved).
        try:
            await admission_controller.record(verdict)
        except Exception as e:                                 # pragma: no cover
            logger.debug("[admission_gate] admit journal raised: %s", e)
        await self._maybe_emit_pressure_events(verdict)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._held:
            try:
                queue_pressure.decr(self.cls)
            except Exception:                                  # pragma: no cover
                logger.exception("[admission_gate] decr failed for %s", self.cls.value)
        return False  # never suppress

    # ─── Threshold scan + event emission ────────────────────────────

    async def _emit_refuse_events(self, verdict) -> None:
        await scaling_events.emit(
            scaling_events.EVENT_ADMISSION_REFUSED,
            {
                "class_":         self.cls.value,
                "reason":         verdict.reason,
                "band":           verdict.band,
                "pressure_band":  verdict.pressure_band,
                "metadata":       self.metadata or None,
            },
        )

    async def _maybe_emit_pressure_events(self, verdict) -> None:
        """Post-incr threshold scan. Cheap — at most 3 events / admit."""
        try:
            press = queue_pressure.snapshot()
        except Exception:                                      # pragma: no cover
            return

        band = press.get("pressure_band")
        util = float(press.get("worker_utilization") or 0.0)

        if band in HIGH_PRESSURE_BANDS:
            await scaling_events.emit(
                scaling_events.EVENT_HIGH_QUEUE_PRESSURE,
                {
                    "class_":              self.cls.value,
                    "pressure_band":       band,
                    "worker_utilization":  util,
                    "per_class":           press.get("per_class"),
                },
            )
        if util >= WORKER_SATURATION_THRESHOLD:
            await scaling_events.emit(
                scaling_events.EVENT_WORKER_SATURATION,
                {
                    "class_":              self.cls.value,
                    "worker_utilization":  util,
                    "pressure_band":       band,
                },
            )
        if verdict.band in CAPACITY_WARNING_BANDS:
            await scaling_events.emit(
                scaling_events.EVENT_CAPACITY_WARNING,
                {
                    "class_":         self.cls.value,
                    "band":           verdict.band,
                    "band_reason":    verdict.band_reason,
                    "pressure_band":  band,
                },
            )
