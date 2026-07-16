"""Task adapter: learning_cycle — full self-improving loop invocation.

Aliases the `backtest` task's mechanics but declares a higher priority and
different business value so the orchestrator can distinguish it in the
scoring log. Delegates to the same `run_learning_cycle` helper because that
IS the learning cycle definition.
"""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass


@registry.register
class LearningCycleTask:
    NAME = "learning_cycle"
    WORKLOAD_CLASS = WorkloadClass.BACKTEST
    DEPENDS_ON = ()
    MIN_INTERVAL_S = 0
    PRIORITY_BASE = 75.0
    CPU_ESTIMATE_CORES = 0.6
    RAM_ESTIMATE_MB = 512
    EXPECTED_DURATION_S = 15.0
    AI_PROVIDER_REQUIRED = True
    COST_ESTIMATE_USD = 0.003
    BUSINESS_VALUE = 0.95
    PASSIVE = False

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        return Readiness(eligible=True, reason="always_ready", pressure=1.2)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            from engines.learning.supervisor import LearningSeed, run_learning_cycle
            seed = LearningSeed(
                pair=ctx.default_seed.get("pair", "EURUSD"),
                timeframe=ctx.default_seed.get("timeframe", "H1"),
                style=ctx.default_seed.get("style", "trend-following"),
                count=1, max_duration_s=180.0,
            )
            run = await run_learning_cycle(seed)
            return TaskResult(ok=run.status in ("completed", "early_reject"),
                              reason=run.status,
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={"run_id": run.run_id,
                                       "status": run.status,
                                       "hash": run.strategy_hash})
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
