"""Task adapter: validation — passive-mode wrapper over backtest validation.

Kept as a distinct task type for future explicit validation gates (holdout,
walk-forward, prop-firm rules). Today it piggy-backs on the `backtest`
task's validation stage inside `run_learning_cycle`, so this adapter is
PASSIVE by default — the operator flips it on when explicit validation
scheduling is desired.
"""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass


@registry.register
class ValidationTask:
    NAME = "validation"
    WORKLOAD_CLASS = WorkloadClass.BACKTEST
    DEPENDS_ON = ("backtest",)
    MIN_INTERVAL_S = 0
    PRIORITY_BASE = 68.0
    CPU_ESTIMATE_CORES = 0.4
    RAM_ESTIMATE_MB = 256
    EXPECTED_DURATION_S = 10.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.85
    PASSIVE = True   # activated in a later phase — validation runs inline today
    HARD_TIMEOUT_S = 180.0        # Phase 2 Stage 1
    RETRY_POLICY = "default"      # Phase 2 Stage 1

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        return Readiness(eligible=False, reason="passive", pressure=1.0)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        return TaskResult(ok=True, reason="passive_noop",
                          duration_ms=0,
                          payload={"note": "validation currently runs inline in backtest task"})
