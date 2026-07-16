"""Task adapter: mutation — perturb winning strategies to explore neighborhood."""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import dependencies_ready


@registry.register
class MutationTask:
    NAME = "mutation"
    WORKLOAD_CLASS = WorkloadClass.MUTATION
    DEPENDS_ON = ("backtest",)
    MIN_INTERVAL_S = 0
    PRIORITY_BASE = 62.0
    CPU_ESTIMATE_CORES = 0.5
    RAM_ESTIMATE_MB = 512
    EXPECTED_DURATION_S = 20.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.75
    PASSIVE = False

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        dep, stale = dependencies_ready(self.DEPENDS_ON, min_recent=1)
        eligible = dep >= 1.0
        return Readiness(
            eligible=eligible,
            reason="deps_ok" if eligible else "waiting_deps",
            pressure=1.0, dependency_readiness=dep, depends_stale=stale,
        )

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            # `engines.auto_mutation_runner` is the canonical mutation driver
            # used by the legacy auto_scheduler. Delegate to its one-cycle
            # helper to preserve semantics.
            from engines.auto_mutation_runner import run_single_cycle
            res = await run_single_cycle(
                batch_size=1,
                pair=ctx.default_seed.get("pair") or None,
                timeframe=ctx.default_seed.get("timeframe", "H1"),
                style=ctx.default_seed.get("style", ""),
                firm="ftmo",
                quality_filter=True,
                quality_threshold=35.0,
                optimizer="random",
                auto_save=True,
                timeout_seconds=120.0,
            )
            ok = str(res.get("status")) in ("completed", "skipped")
            return TaskResult(ok=ok, reason=str(res.get("status")),
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={"strategies_saved": res.get("strategies_saved"),
                                       "pair": res.get("pair")})
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
