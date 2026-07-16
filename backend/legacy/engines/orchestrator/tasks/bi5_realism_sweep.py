"""Task adapter: bi5_realism_sweep — weekly BI5 slippage/spread realism check."""
from __future__ import annotations

import time
from typing import Any

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure, dependencies_ready


@registry.register
class BI5RealismSweepTask:
    NAME = "bi5_realism_sweep"
    WORKLOAD_CLASS = WorkloadClass.IO if hasattr(WorkloadClass, "IO") else "io"
    DEPENDS_ON = ("market_data_topup",)
    MIN_INTERVAL_S = 7 * 24 * 3600
    PRIORITY_BASE = 40.0
    CPU_ESTIMATE_CORES = 0.5
    RAM_ESTIMATE_MB = 512
    EXPECTED_DURATION_S = 120.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.6
    PASSIVE = False

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        p = freshness_pressure(self.NAME, self.MIN_INTERVAL_S)
        dep, stale = dependencies_ready(self.DEPENDS_ON, min_recent=1)
        eligible = p >= 1.0 and dep >= 1.0
        return Readiness(
            eligible=eligible,
            reason="due" if eligible else ("waiting_deps" if dep < 1.0 else "recent"),
            pressure=p,
            dependency_readiness=dep,
            depends_stale=stale,
        )

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            from engines import bi5_realism
            summary = await bi5_realism.sweep_realism(force_refresh=False)
            return TaskResult(ok=True, reason="sweep_done",
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={"summary": {
                                  "scanned": summary.get("scanned"),
                                  "evaluated": summary.get("evaluated"),
                                  "ok": summary.get("ok"),
                                  "fail": summary.get("fail"),
                              }})
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
