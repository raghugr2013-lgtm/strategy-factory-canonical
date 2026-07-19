"""Phase J orchestrator task: factory_evaluation."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure


@registry.register
class FactoryEvaluationTask:
    NAME = "factory_evaluation"
    WORKLOAD_CLASS = (
        WorkloadClass.API_HOT if hasattr(WorkloadClass, "API_HOT") else "api_hot")
    DEPENDS_ON = ("execution_attribution", "meta_learning_evaluation")
    MIN_INTERVAL_S = 3600
    PRIORITY_BASE = 45.0
    CPU_ESTIMATE_CORES = 0.20
    RAM_ESTIMATE_MB = 128
    EXPECTED_DURATION_S = 5.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.75
    PASSIVE = False

    HARD_TIMEOUT_S = 1800.0        # Phase 2 Stage 1
    RETRY_POLICY = "default"      # Phase 2 Stage 1
    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        try:
            from engines.factory_eval import config as fecfg
            from engines.factory_eval.types import FEMode
            if fecfg.mode() == FEMode.DISABLED:
                return Readiness(eligible=False, reason="mode=disabled")
        except Exception:  # noqa: BLE001
            pass
        try:
            from engines.factory_eval import config as fecfg
            interval = int(fecfg.cadence_sec())
        except Exception:  # noqa: BLE001
            interval = self.MIN_INTERVAL_S
        p = freshness_pressure(self.NAME, interval)
        return Readiness(eligible=p >= 1.0,
                         reason="due" if p >= 1.0 else "recent",
                         pressure=p)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            from engines.factory_eval import config as fecfg
            from engines.factory_eval.engine import run_factory_evaluation_cycle
            # Daily report at configured UTC hour
            hour = datetime.now(timezone.utc).hour
            daily = hour == fecfg.daily_report_hour()
            summary = await run_factory_evaluation_cycle(daily=daily)
            return TaskResult(
                ok=True,
                reason=(f"insights={summary.get('n_insights', 0)} "
                          f"recs={summary.get('n_recommendations', 0)} "
                          f"daily={daily}"),
                duration_ms=int((time.time() - t0) * 1000),
                payload=summary,
            )
        except Exception as e:  # noqa: BLE001
            return TaskResult(ok=False, reason=f"err: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
