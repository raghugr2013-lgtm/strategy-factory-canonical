"""Task adapter: backtest — one full learning-cycle-embedded backtest run.

We delegate to `engines.learning.supervisor.run_learning_cycle` which
already wires generate → backtest → validate → knowledge index refresh
under a shared `learning_run_id` and emits outcome_events. This is the
canonical "one unit of work" of the factory.
"""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass


@registry.register
class BacktestTask:
    NAME = "backtest"
    WORKLOAD_CLASS = WorkloadClass.BACKTEST
    DEPENDS_ON = ()
    MIN_INTERVAL_S = 0
    PRIORITY_BASE = 70.0
    CPU_ESTIMATE_CORES = 0.6
    RAM_ESTIMATE_MB = 512
    EXPECTED_DURATION_S = 15.0
    AI_PROVIDER_REQUIRED = True
    COST_ESTIMATE_USD = 0.003
    BUSINESS_VALUE = 0.9
    PASSIVE = False
    HARD_TIMEOUT_S = 180.0        # Phase 2 Stage 1
    RETRY_POLICY = "default"      # Phase 2 Stage 1

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        return Readiness(eligible=True, reason="always_ready", pressure=1.0)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            from engines.learning.supervisor import LearningSeed, run_learning_cycle
            seed = LearningSeed(
                pair=ctx.default_seed.get("pair", "EURUSD"),
                timeframe=ctx.default_seed.get("timeframe", "H1"),
                style=ctx.default_seed.get("style", "trend-following"),
                count=1,
                max_duration_s=120.0,
            )
            run = await run_learning_cycle(seed)
            ok = run.status in ("completed", "early_reject")   # both are non-crash outcomes
            return TaskResult(ok=ok, reason=run.status,
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={"run_id": run.run_id,
                                       "status": run.status,
                                       "hash": run.strategy_hash})
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
