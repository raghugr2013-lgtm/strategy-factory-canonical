"""Phase I orchestrator task: meta_learning_evaluation.

Runs one meta-learning cycle every 15 min (env-configurable).
Depends on `execution_attribution` so realised outcomes are available.
Passive when META_LEARNING_MODE=disabled — orchestrator skips.
"""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure


@registry.register
class MetaLearningEvaluationTask:
    NAME = "meta_learning_evaluation"
    WORKLOAD_CLASS = (
        WorkloadClass.API_HOT if hasattr(WorkloadClass, "API_HOT") else "api_hot")
    DEPENDS_ON = ("execution_attribution",)
    MIN_INTERVAL_S = 900  # 15 min default; env overrides via cadence_sec
    PRIORITY_BASE = 55.0
    CPU_ESTIMATE_CORES = 0.10
    RAM_ESTIMATE_MB = 96
    EXPECTED_DURATION_S = 3.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.80
    PASSIVE = False

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        try:
            from engines.meta_learning import config as mlcfg
            from engines.meta_learning.types import MetaMode
            if mlcfg.mode() == MetaMode.DISABLED:
                return Readiness(eligible=False, reason="mode=disabled")
        except Exception:  # noqa: BLE001
            pass
        try:
            from engines.meta_learning import config as mlcfg
            interval = int(mlcfg.cadence_sec())
        except Exception:  # noqa: BLE001
            interval = self.MIN_INTERVAL_S
        p = freshness_pressure(self.NAME, interval)
        return Readiness(eligible=p >= 1.0,
                         reason="due" if p >= 1.0 else "recent", pressure=p)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            from engines.meta_learning.engine import run_meta_learning_cycle
            summary = await run_meta_learning_cycle()
            return TaskResult(
                ok=True,
                reason=(f"evals={summary.get('n_evaluations', 0)} "
                          f"recs={summary.get('n_recommendations', 0)} "
                          f"applied={summary.get('n_applied', 0)}"),
                duration_ms=int((time.time() - t0) * 1000),
                payload=summary,
            )
        except Exception as e:  # noqa: BLE001
            return TaskResult(ok=False, reason=f"err: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
