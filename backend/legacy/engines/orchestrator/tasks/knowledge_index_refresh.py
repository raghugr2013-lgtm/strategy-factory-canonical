"""Task adapter: knowledge_index_refresh — rebuild the retriever index."""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure


@registry.register
class KnowledgeIndexRefreshTask:
    NAME = "knowledge_index_refresh"
    WORKLOAD_CLASS = WorkloadClass.API_HOT if hasattr(WorkloadClass, "API_HOT") else "api_hot"
    DEPENDS_ON = ()   # incremental refresh works even before learning cycles run
    MIN_INTERVAL_S = 1800
    PRIORITY_BASE = 55.0
    CPU_ESTIMATE_CORES = 0.2
    RAM_ESTIMATE_MB = 128
    EXPECTED_DURATION_S = 5.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.7
    PASSIVE = False

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        p = freshness_pressure(self.NAME, self.MIN_INTERVAL_S)
        eligible = p >= 1.0
        return Readiness(eligible=eligible,
                         reason="due" if eligible else "recent",
                         pressure=p)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            from engines.knowledge import rebuild as _kb_rebuild
            summary = await _kb_rebuild(scope="incremental", limit=200)
            return TaskResult(ok=True, reason="rebuild_ok",
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={
                                  "total_written": summary.get("total_written"),
                                  "total_read":    summary.get("total_read"),
                                  "took_ms":       summary.get("took_ms"),
                              })
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
