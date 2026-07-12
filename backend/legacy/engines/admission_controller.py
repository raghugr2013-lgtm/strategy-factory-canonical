"""
VPS Scaling P1.C — Admission controller (PURE FUNCTION + advisory).

The admission gate. Given a WorkloadClass, returns admit / defer /
refuse based on (host capability, compute probe, queue pressure,
concurrency targets). Pure function. No raises. No mutation of caller
state.

Discipline (per CAPACITY_ENGINE_DESIGN.md §6 + operator decisions in
P1.C):
  * Flag-gated: `ENABLE_ADMISSION_CONTROL=false` (default) ⇒ ALWAYS
    returns AdmissionVerdict(decision="admit", reason="flag_off").
    Byte-identical to the pre-P1.C world.
  * Pure function. `gate()` is read-only. The journaling write happens
    in a separate `record()` coroutine — and even that is best-effort
    (Mongo failure does NOT change the verdict).
  * Honest-refusal:
        - band=critical → refuse for every class
        - band=unknown  → refuse BACKTEST / MUTATION / FACTORY_CYCLE;
                          defer API_HOT; refuse AGENT
        - band=warn AND class=FACTORY_CYCLE → refuse (factory cycles
          should not start when host is hot)
  * Cap enforcement: a class is refused if its current depth >= its
    target. Defer is reserved for "you can retry in 30 s" — used when
    `decision == "defer"` for API_HOT and for transient queue overflows.
  * The verdict is *advisory* in P1.C. No engine consults it until P1.D
    wires the `with_admission` wrapper at the cpu_pool / auto_factory /
    mutation_engine / master_bot_deployment entry points.

Public API:
    gate(cls, force=False) → AdmissionVerdict   (pure)
    record(verdict)        → bool               (Mongo write; best-effort)
    is_enabled()           → bool

Verdict shape (caller-stable across P1.D rewiring):

    AdmissionVerdict(
        class_=WorkloadClass,
        decision="admit" | "defer" | "refuse",
        reason=str,
        retry_after_sec=int | None,
        targets=ConcurrencyTargets | None,
        pressure_band=str | None,
        evaluated_at=iso-string,
    )
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from engines import adaptive_concurrency, compute_probe, host_capability, queue_pressure
from engines.feature_flags import flag
from engines.workload_classes import WorkloadClass

logger = logging.getLogger(__name__)

DECISION_ADMIT   = "admit"
DECISION_DEFER   = "defer"
DECISION_REFUSE  = "refuse"

JOURNAL_COLLECTION = "admission_journal"


@dataclass
class AdmissionVerdict:
    class_:          str        # WorkloadClass.value
    decision:        str        # admit / defer / refuse
    reason:          str
    retry_after_sec: Optional[int] = None
    pressure_band:   Optional[str] = None
    band:            Optional[str] = None
    targets:         Optional[Dict[str, Any]] = None
    evaluated_at:    str = ""
    derivation:      Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ─── Public configuration helpers ────────────────────────────────────

def is_enabled() -> bool:
    """True iff the admission gate should consult bands/pressure.

    When False (default), `gate()` short-circuits to admit. This is
    the legacy P1.A/P1.B-byte-identical behaviour.
    """
    try:
        return bool(flag("ENABLE_ADMISSION_CONTROL"))
    except KeyError:
        return False


# ─── The gate ────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _refuse_classes_when(band: str) -> set:
    """Which classes should be refused at a given band?"""
    if band == "critical":
        return {WorkloadClass.API_HOT, WorkloadClass.BACKTEST, WorkloadClass.MUTATION,
                WorkloadClass.FACTORY_CYCLE, WorkloadClass.AGENT}
    if band == "unknown":
        return {WorkloadClass.BACKTEST, WorkloadClass.MUTATION,
                WorkloadClass.FACTORY_CYCLE, WorkloadClass.AGENT}
    if band == "warn":
        return {WorkloadClass.FACTORY_CYCLE}
    return set()


def _defer_classes_when(band: str) -> set:
    """Which classes get a 30 s defer instead of a hard refuse?"""
    if band == "unknown":
        return {WorkloadClass.API_HOT}
    return set()


def gate(
    cls: WorkloadClass,
    *,
    force: bool = False,
    caps: Optional[host_capability.HostCapability] = None,
    probe: Optional[Dict[str, Any]] = None,
    pressure: Optional[Dict[str, Any]] = None,
) -> AdmissionVerdict:
    """Compute an admission verdict. Pure; no I/O; no raises.

    Args
    ----
    cls      : WorkloadClass for the incoming request.
    force    : operator/admin escape hatch — always admits.
    caps     : optional injected HostCapability (test/diag use). When
               None, `host_capability.current()` is consulted.
    probe    : optional injected compute_probe.snapshot(). When None,
               a fresh local snapshot is captured.
    pressure : optional injected queue_pressure.snapshot(). When None,
               a fresh local snapshot is captured.
    """
    if not isinstance(cls, WorkloadClass):
        raise TypeError(f"admission_controller.gate expects WorkloadClass, got {type(cls).__name__}")

    now = _now_iso()

    # ─ Short-circuit when the gate is OFF (P1.C default).
    if not is_enabled():
        return AdmissionVerdict(
            class_=cls.value, decision=DECISION_ADMIT,
            reason="flag_off", evaluated_at=now,
        )

    # ─ Operator override.
    if force:
        return AdmissionVerdict(
            class_=cls.value, decision=DECISION_ADMIT,
            reason="force_override", evaluated_at=now,
        )

    if caps is None:
        caps = host_capability.current()
    if probe is None:
        try:
            probe = compute_probe.snapshot()
        except Exception:                                      # pragma: no cover
            probe = None
    if pressure is None:
        try:
            pressure = queue_pressure.snapshot()
        except Exception:                                      # pragma: no cover
            pressure = None

    targets = adaptive_concurrency.recommend(caps, probe, pressure)
    band = targets.band

    pressure_band = (pressure or {}).get("pressure_band") if isinstance(pressure, dict) else None

    # Step 1 — band-based refuse/defer table.
    if cls in _refuse_classes_when(band):
        return AdmissionVerdict(
            class_=cls.value, decision=DECISION_REFUSE,
            reason=f"band_{band}",
            pressure_band=pressure_band, band=band,
            targets=targets.to_dict(),
            evaluated_at=now,
            derivation=targets.derivation,
        )
    if cls in _defer_classes_when(band):
        return AdmissionVerdict(
            class_=cls.value, decision=DECISION_DEFER,
            reason=f"band_{band}",
            retry_after_sec=30,
            pressure_band=pressure_band, band=band,
            targets=targets.to_dict(),
            evaluated_at=now,
            derivation=targets.derivation,
        )

    # Step 2 — per-class cap enforcement.
    depth_now = queue_pressure.current_depth(cls) if cls in WorkloadClass else 0

    cap: Optional[int] = None
    if cls == WorkloadClass.BACKTEST:
        cap = targets.max_concurrent_backtests
    elif cls == WorkloadClass.MUTATION:
        cap = targets.max_concurrent_mutations
    elif cls == WorkloadClass.FACTORY_CYCLE:
        cap = targets.max_concurrent_factory_cycles
    # API_HOT, AGENT — unlimited (not count-gated; only band-gated).

    if cap is not None and depth_now >= cap:
        # Over the cap. Defer (operator may retry in 30 s) — never refuse
        # for cap overflow, only for band-driven gates.
        return AdmissionVerdict(
            class_=cls.value, decision=DECISION_DEFER,
            reason=f"cap_reached (depth_now={depth_now} cap={cap})",
            retry_after_sec=30,
            pressure_band=pressure_band, band=band,
            targets=targets.to_dict(),
            evaluated_at=now,
            derivation=targets.derivation,
        )

    return AdmissionVerdict(
        class_=cls.value, decision=DECISION_ADMIT,
        reason=f"under_cap (depth_now={depth_now} cap={cap if cap is not None else 'unlimited'})",
        pressure_band=pressure_band, band=band,
        targets=targets.to_dict(),
        evaluated_at=now,
        derivation=targets.derivation,
    )


# ─── Journaling (best-effort) ────────────────────────────────────────

async def record(verdict: AdmissionVerdict) -> bool:
    """Append the verdict to the admission_journal collection.

    Idempotent at-most-once: same verdict written twice → two rows
    (the operator wants the full trail). Never raises. Returns True
    on persistence success.

    The journal is not consulted by any engine in P1.C; it exists for
    operator audit + future ML feedback (auto-learning phase).
    """
    try:
        from engines.db import get_db
        db = get_db()
        doc = verdict.to_dict()
        doc.setdefault("evaluated_at", _now_iso())
        # Stamp host_id for multi-host operation in P1.D.
        caps = host_capability.current()
        doc["host_id"] = caps.host_id if caps else os.environ.get("HOSTNAME", "unknown")
        await db[JOURNAL_COLLECTION].insert_one(doc)
        return True
    except Exception as e:                                     # pragma: no cover
        logger.debug("[admission_controller] journal write failed: %s", e)
        return False


async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent index creation for admission_journal. Never raises."""
    try:
        from engines.db import get_db
        from pymongo import ASCENDING, DESCENDING
        db = get_db()
        existing = await db[JOURNAL_COLLECTION].index_information()
        created, existed = [], []
        if "ix_admission_evaluated_at" not in existing:
            await db[JOURNAL_COLLECTION].create_index(
                [("evaluated_at", DESCENDING)],
                name="ix_admission_evaluated_at",
                background=True,
            )
            created.append("ix_admission_evaluated_at")
        else:
            existed.append("ix_admission_evaluated_at")
        if "ix_admission_class_decision" not in existing:
            await db[JOURNAL_COLLECTION].create_index(
                [("class_", ASCENDING), ("decision", ASCENDING)],
                name="ix_admission_class_decision",
                background=True,
            )
            created.append("ix_admission_class_decision")
        else:
            existed.append("ix_admission_class_decision")
        return {"created": created, "existed": existed, "errors": []}
    except Exception as e:                                     # pragma: no cover
        return {"created": [], "existed": [], "errors": [{"error": str(e)[:200]}]}
