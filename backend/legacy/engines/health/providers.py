"""Phase 2, Stage 1 — Subsystem health providers.

Each subsystem-facing function returns a `HealthSnapshot`. Providers
are pure functions over in-memory state; never raise. If a subsystem
has no telemetry yet (fresh boot), `empty_snapshot(name)` is
returned.

Stage 1 ships providers for:
  * coe   — Compute Orchestration Engine (based on existing orchestrator + queue_pressure counters)
  * vie   — Vendor-Independent Intelligence Engine (probes vie/providers via cached state)

Stage 4 will retrofit meta_learning, market_intelligence, execution,
portfolio, factory_eval.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .contract import (
    ActionRequired,
    FailureCount,
    HealthSnapshot,
    LastSuccessfulRun,
    RecoveryState,
    RecoveryStatus,
    ResourceUsage,
    empty_snapshot,
)

logger = logging.getLogger(__name__)


# ── COE health ────────────────────────────────────────────────────────

def coe_snapshot() -> HealthSnapshot:
    """Compute Orchestration Engine health.

    Reads from in-memory state of:
      * orchestrator.core (in-flight, tick_count, last_error)
      * queue_pressure (per-class depth + rolling band)
      * cpu_pool (worker count, pool_initialized, crash budget)
      * budget_tracker (daily/monthly headroom)

    Never raises — degrades to empty_snapshot on any failure.
    """
    try:
        return _build_coe_snapshot()
    except Exception:  # noqa: BLE001
        logger.exception("[health/providers] coe_snapshot crashed — returning empty")
        return empty_snapshot("coe")


def _build_coe_snapshot() -> HealthSnapshot:
    subsystem = "coe"

    # ── Signals (all best-effort) ──
    orch_meta: Dict[str, Any] = {}
    in_flight = 0
    tick_count = 0
    dispatched_total = 0
    last_error: Optional[str] = None
    try:
        from engines.orchestrator import get_orchestrator
        snap = get_orchestrator().snapshot()
        orch_meta = snap.get("meta") or {}
        in_flight = len(snap.get("in_flight") or [])
        tick_count = int(orch_meta.get("tick_count") or 0)
        dispatched_total = int(orch_meta.get("dispatched_total") or 0)
        last_error = orch_meta.get("last_error")
    except Exception:  # noqa: BLE001
        pass

    pressure: Dict[str, Any] = {}
    total_depth = 0
    band = "idle"
    worker_util = 0.0
    try:
        from engines import queue_pressure as _qp
        pressure = _qp.snapshot() or {}
        band = str(pressure.get("pressure_band") or "idle")
        worker_util = float(pressure.get("worker_utilization") or 0.0)
        per_class = pressure.get("per_class") or {}
        total_depth = sum(int((v or {}).get("depth_now", 0)) for v in per_class.values())
    except Exception:  # noqa: BLE001
        pass

    pool_state: Dict[str, Any] = {}
    crash_count = 0
    try:
        from engines import cpu_pool as _cp
        pool_state = _cp.get_pool_state() or {}
        crash_count = int(pool_state.get("crash_count", 0) or 0)
    except Exception:  # noqa: BLE001
        pass

    budget_headroom: Optional[float] = None
    try:
        from engines.orchestrator import get_budget_tracker
        btsnap = get_budget_tracker().snapshot() or {}
        gcap = float(((btsnap.get("global") or {}).get("daily_cap_usd") or 0.0))
        gspent = float(((btsnap.get("global") or {}).get("daily_spent_usd") or 0.0))
        if gcap > 0:
            budget_headroom = max(0.0, min(1.0, 1.0 - (gspent / gcap)))
    except Exception:  # noqa: BLE001
        pass

    # ── Score computation (pure fn over the above) ──
    band_penalty = {"idle": 0, "normal": 0, "high": 15, "critical": 40, "unknown": 25}.get(band, 25)
    crash_penalty = min(40, crash_count * 5)
    budget_penalty = 0
    if budget_headroom is not None and budget_headroom < 0.1:
        budget_penalty = 20
    elif budget_headroom is not None and budget_headroom < 0.25:
        budget_penalty = 10
    health_score = max(0, 100 - band_penalty - crash_penalty - budget_penalty)

    # readiness — how much headroom is available RIGHT NOW
    readiness_score = 100
    readiness_score -= int(worker_util * 40)              # up to -40 for saturated pool
    if budget_headroom is not None:
        readiness_score -= int((1.0 - budget_headroom) * 20)
    if band == "critical":
        readiness_score -= 30
    elif band == "high":
        readiness_score -= 15
    readiness_score = max(0, min(100, readiness_score))

    # confidence — do we trust recent output?
    #   proxy = 100 - min(50, error_rate*100). tick_count 0 → "no data yet" → 100.
    ok_total = int(orch_meta.get("dispatched_total") or 0)
    fail_marker = 1 if last_error else 0
    if ok_total > 0:
        confidence_score = max(50, 100 - (fail_marker * 20))
    else:
        confidence_score = 100

    # ── Recovery state ──
    state = RecoveryState.OK
    reason = ""
    action = ActionRequired.NONE
    if crash_count >= 3:
        state = RecoveryState.CRITICAL
        reason = f"cpu_pool crash_count={crash_count}"
        action = ActionRequired.RESTART_COMPONENT
    elif band == "critical":
        state = RecoveryState.DEGRADED
        reason = f"pressure_band={band} worker_utilization={worker_util:.2f}"
        action = ActionRequired.WAIT_FOR_BACKOFF
    elif budget_headroom is not None and budget_headroom < 0.05:
        state = RecoveryState.DEGRADED
        reason = f"budget_headroom={budget_headroom:.3f}"
        action = ActionRequired.RESET_BUDGET
    elif last_error and health_score < 70:
        state = RecoveryState.DEGRADED
        reason = f"last_error: {str(last_error)[:120]}"
        action = ActionRequired.OPERATOR_REVIEW
    elif band == "high":
        state = RecoveryState.DEGRADED
        reason = f"pressure_band={band}"
        action = ActionRequired.NONE

    # ── Assemble ──
    return HealthSnapshot(
        subsystem=subsystem,
        health_score=health_score,
        readiness_score=readiness_score,
        confidence_score=confidence_score,
        resource_usage=ResourceUsage(
            cpu_percent=None,
            mem_mb=None,
            in_flight=in_flight,
            queue_depth=total_depth,
            budget_headroom=budget_headroom,
        ),
        last_successful_run=LastSuccessfulRun(
            at=orch_meta.get("started_at"),
            duration_ms=None,
            ref=str(dispatched_total) if dispatched_total else None,
        ),
        failure_count=FailureCount(
            last_hour=0,   # populated in Stage 4 (needs windowed counters)
            last_day=0,
            since_boot=crash_count,
        ),
        recovery_status=RecoveryStatus(
            state=state, reason=reason, action_required=action,
        ),
    )


# ── VIE health ────────────────────────────────────────────────────────

def vie_snapshot() -> HealthSnapshot:
    """VIE health — aggregates provider availability + budget headroom.

    VIE runs in a separate container; this endpoint reads the cached
    provider-status from `ai_workforce.telemetry` and the budget
    tracker. Live provider probing lives at `/api/vie/probe` — NOT
    called here (would defeat health-check idempotency).
    """
    try:
        return _build_vie_snapshot()
    except Exception:  # noqa: BLE001
        logger.exception("[health/providers] vie_snapshot crashed — returning empty")
        return empty_snapshot("vie")


def _build_vie_snapshot() -> HealthSnapshot:
    subsystem = "vie"

    providers_total = 0
    providers_healthy = 0
    circuits_open = 0
    try:
        from engines.ai_workforce import telemetry as _tel  # type: ignore
        state = _tel.snapshot() if hasattr(_tel, "snapshot") else {}
        providers = state.get("providers") or {}
        providers_total = len(providers)
        for _name, p in providers.items():
            if (p or {}).get("breaker_state") == "closed":
                providers_healthy += 1
            elif (p or {}).get("breaker_state") == "open":
                circuits_open += 1
    except Exception:  # noqa: BLE001
        pass

    budget_headroom: Optional[float] = None
    per_provider_calls_total = 0
    try:
        from engines.orchestrator import get_budget_tracker
        btsnap = get_budget_tracker().snapshot() or {}
        gcap = float(((btsnap.get("global") or {}).get("daily_cap_usd") or 0.0))
        gspent = float(((btsnap.get("global") or {}).get("daily_spent_usd") or 0.0))
        if gcap > 0:
            budget_headroom = max(0.0, min(1.0, 1.0 - (gspent / gcap)))
        per_provider = btsnap.get("per_provider") or {}
        per_provider_calls_total = sum(
            int((v or {}).get("calls_total", 0)) for v in per_provider.values()
        )
    except Exception:  # noqa: BLE001
        pass

    # ── Scores ──
    if providers_total == 0:
        # No provider registered — nothing observed. Not "unhealthy".
        health_score = 100
        readiness_score = 100
        confidence_score = 100
    else:
        health_share = providers_healthy / providers_total
        health_score = int(round(health_share * 100))
        if budget_headroom is not None and budget_headroom < 0.1:
            health_score = max(0, health_score - 20)
        readiness_score = int(round(health_share * 100))
        if budget_headroom is not None:
            readiness_score = int(round(readiness_score * budget_headroom))
        confidence_score = health_score

    state = RecoveryState.OK
    reason = ""
    action = ActionRequired.NONE
    if providers_total > 0 and providers_healthy == 0:
        state = RecoveryState.CRITICAL
        reason = "all_provider_circuits_open"
        action = ActionRequired.OPERATOR_REVIEW
    elif circuits_open > 0:
        state = RecoveryState.DEGRADED
        reason = f"circuits_open={circuits_open}/{providers_total}"
        action = ActionRequired.WAIT_FOR_BACKOFF
    elif budget_headroom is not None and budget_headroom < 0.05:
        state = RecoveryState.DEGRADED
        reason = f"budget_headroom={budget_headroom:.3f}"
        action = ActionRequired.RESET_BUDGET

    return HealthSnapshot(
        subsystem=subsystem,
        health_score=health_score,
        readiness_score=readiness_score,
        confidence_score=confidence_score,
        resource_usage=ResourceUsage(
            cpu_percent=None,
            mem_mb=None,
            in_flight=0,
            queue_depth=0,
            budget_headroom=budget_headroom,
        ),
        last_successful_run=LastSuccessfulRun(
            at=None,
            duration_ms=None,
            ref=str(per_provider_calls_total) if per_provider_calls_total else None,
        ),
        failure_count=FailureCount(
            last_hour=0,
            last_day=0,
            since_boot=circuits_open,
        ),
        recovery_status=RecoveryStatus(
            state=state, reason=reason, action_required=action,
        ),
    )


# ── Registry ──────────────────────────────────────────────────────────
# Central table of subsystem-name → provider-callable. Stage 4 retrofits
# will register their providers here.

_PROVIDERS: Dict[str, Any] = {
    "coe": coe_snapshot,
    "vie": vie_snapshot,
}


def register_provider(name: str, fn) -> None:
    """Register a subsystem's health-snapshot provider.

    Called by subsystem __init__.py or by app boot to make a subsystem
    visible to the `/api/health/system` aggregator.
    """
    _PROVIDERS[name] = fn


def get_provider(name: str):
    return _PROVIDERS.get(name)


def all_provider_names() -> list:
    return sorted(_PROVIDERS.keys())


def collect_all() -> list:
    """Call every registered provider; return their snapshots as dicts.

    Never raises — a failing provider is replaced with an empty snapshot
    tagged `recovery_status.reason="provider_crashed"`.
    """
    out = []
    for name, fn in _PROVIDERS.items():
        try:
            snap = fn()
            out.append(snap.to_dict())
        except Exception as e:  # noqa: BLE001
            logger.exception("[health/providers] %s crashed: %s", name, e)
            snap = empty_snapshot(name)
            snap.recovery_status.reason = f"provider_crashed: {str(e)[:120]}"
            snap.recovery_status.state = RecoveryState.DEGRADED
            snap.recovery_status.action_required = ActionRequired.OPERATOR_REVIEW
            snap.health_score = 0
            snap.readiness_score = 0
            snap.confidence_score = 0
            out.append(snap.to_dict())
    return out


def platform_health_score(snapshots: list) -> int:
    """Weighted mean of subsystem health_score. Uniform weights (1.0) in
    Stage 1 per operator directive; env `PLATFORM_HEALTH_WEIGHT_<SUB>`
    can override later. Never raises.
    """
    import os as _os
    if not snapshots:
        return 100
    total_weight = 0.0
    total = 0.0
    for s in snapshots:
        sub = str(s.get("subsystem") or "").upper()
        raw = _os.environ.get(f"PLATFORM_HEALTH_WEIGHT_{sub}", "1.0")
        try:
            w = float(raw)
        except ValueError:
            w = 1.0
        if w <= 0:
            continue
        total_weight += w
        total += w * float(s.get("health_score") or 0)
    if total_weight <= 0:
        return 100
    return max(0, min(100, int(round(total / total_weight))))
