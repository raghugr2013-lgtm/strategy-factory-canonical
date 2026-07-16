"""Phase B.2 — /api/orchestrator/* endpoints.

Additive. Depends on the legacy full-recovery mount block so the router
picks up the standard admin-auth dependency.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from auth_utils import require_admin
from engines.orchestrator import (
    get_orchestrator,
    get_budget_tracker,
    registry,
)
# Import the tasks package for side-effect: all 11 task adapters register.
import engines.orchestrator.tasks  # noqa: F401

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.post("/start")
async def orchestrator_start(_u=Depends(require_admin)):
    """Start the unified orchestration engine. Idempotent. When running,
    legacy schedulers (auto/orchestrator/bi5-realism/auto-maintenance) that
    have `subordinate_to_orchestrator=true` become dormant."""
    orc = get_orchestrator()
    return await orc.start()


@router.post("/stop")
async def orchestrator_stop(_u=Depends(require_admin)):
    orc = get_orchestrator()
    return await orc.stop()


@router.get("/status")
async def orchestrator_status():
    orc = get_orchestrator()
    return orc.snapshot()


@router.get("/tasks")
async def orchestrator_tasks():
    """List every registered task with metadata + runtime counters."""
    orc = get_orchestrator()
    out = []
    for t in registry.all():
        name = t.NAME
        passive_effective = registry.is_passive_via_env(name, bool(getattr(t, "PASSIVE", False)))
        prio = registry.priority_base_via_env(name, float(t.PRIORITY_BASE))
        wc = t.WORKLOAD_CLASS
        wc_str = getattr(wc, "value", str(wc))
        out.append({
            "name": name,
            "workload_class":       wc_str,
            "depends_on":           list(t.DEPENDS_ON),
            "min_interval_s":       int(t.MIN_INTERVAL_S),
            "priority_base":        prio,
            "cpu_estimate_cores":   float(t.CPU_ESTIMATE_CORES),
            "ram_estimate_mb":      int(t.RAM_ESTIMATE_MB),
            "expected_duration_s":  float(t.EXPECTED_DURATION_S),
            "ai_provider_required": bool(t.AI_PROVIDER_REQUIRED),
            "cost_estimate_usd":    float(t.COST_ESTIMATE_USD),
            "business_value":       float(t.BUSINESS_VALUE),
            "passive":              passive_effective,
            "runs_total":           orc._runs_total.get(name, 0),       # noqa: SLF001
            "runs_ok":              orc._runs_ok.get(name, 0),          # noqa: SLF001
            "runs_fail":            orc._runs_fail.get(name, 0),        # noqa: SLF001
            "last_completed_ts":    orc._last_completed_ts.get(name),   # noqa: SLF001
        })
    return {"count": len(out), "tasks": out}


@router.post("/tasks/{name}/dispatch")
async def orchestrator_dispatch_task(name: str, _u=Depends(require_admin)):
    """Manual one-shot dispatch of the named task — bypasses readiness /
    budget gating (operator intent is explicit). Useful for E2E tests +
    ad-hoc operator triggers."""
    if registry.get(name) is None:
        raise HTTPException(status_code=404, detail={"code": "unknown_task",
                                                     "name": name})
    orc = get_orchestrator()
    return await orc.dispatch_task(name)


@router.get("/budget")
async def orchestrator_budget():
    return get_budget_tracker().snapshot()


@router.get("/decisions")
async def orchestrator_decisions(limit: int = 100):
    orc = get_orchestrator()
    return {"count": len(orc.decisions(limit)),
            "decisions": orc.decisions(limit)}
