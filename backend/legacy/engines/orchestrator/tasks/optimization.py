"""Task adapter: optimization — walk-forward / GA parameter search.

PASSIVE by default: the optimization engine has significant CPU footprint
and is best invoked explicitly by the operator via `/api/optimization/*`
endpoints until the process pool is enabled (later phase). Kept in the
registry so orchestrator metadata + dashboards show it exists.
"""
from __future__ import annotations

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass


@registry.register
class OptimizationTask:
    NAME = "optimization"
    WORKLOAD_CLASS = WorkloadClass.MUTATION
    DEPENDS_ON = ("backtest",)
    MIN_INTERVAL_S = 0
    PRIORITY_BASE = 58.0
    CPU_ESTIMATE_CORES = 2.0
    RAM_ESTIMATE_MB = 1024
    EXPECTED_DURATION_S = 120.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.7
    PASSIVE = True

    HARD_TIMEOUT_S = 600.0        # Phase 2 Stage 1
    RETRY_POLICY = "default"      # Phase 2 Stage 1
    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        return Readiness(eligible=False, reason="passive", pressure=1.0)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        return TaskResult(ok=True, reason="passive_noop",
                          payload={"note": "activate via ORCH_TASK_OPTIMIZATION_PASSIVE=false"})
