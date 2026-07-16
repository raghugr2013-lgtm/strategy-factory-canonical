"""Phase H7 orchestrator task: execution_attribution.

Sweeps closed round-trips into `execution_attribution` every 5 min.
Idempotent via immutable brain_decision_id join.
"""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure


@registry.register
class ExecutionAttributionTask:
    NAME = "execution_attribution"
    WORKLOAD_CLASS = WorkloadClass.API_HOT if hasattr(WorkloadClass, "API_HOT") else "api_hot"
    DEPENDS_ON = ("broker_health_check",)
    MIN_INTERVAL_S = 300
    PRIORITY_BASE = 60.0
    CPU_ESTIMATE_CORES = 0.10
    RAM_ESTIMATE_MB = 64
    EXPECTED_DURATION_S = 2.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.85
    PASSIVE = False

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        try:
            from engines.execution import exec_enabled
            if not exec_enabled():
                return Readiness(eligible=False, reason="EXEC_ENABLED=false")
        except Exception:
            pass
        p = freshness_pressure(self.NAME, self.MIN_INTERVAL_S)
        return Readiness(eligible=p >= 1.0,
                         reason="due" if p >= 1.0 else "recent", pressure=p)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            from engines.execution.attribution import attribute_closed_positions
            from engines.execution import default_account_id
            rows = await attribute_closed_positions(default_account_id())
            return TaskResult(
                ok=True, reason=f"attributed={len(rows)}",
                duration_ms=int((time.time() - t0) * 1000),
                payload={"attributed": len(rows)},
            )
        except Exception as e:
            return TaskResult(ok=False, reason=f"err: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
