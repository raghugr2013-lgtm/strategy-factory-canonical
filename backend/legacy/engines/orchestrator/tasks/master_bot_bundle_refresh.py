"""Task adapter: master_bot_bundle_refresh — maintain Tier 1/2/3 bundles.

Event-driven off `ranking` completions with a freshness SLA of 30 min as
safety-check fallback. PASSIVE by default until the operator explicitly
activates it — Master Bot output is high-visibility and should not
auto-refresh in production without operator sign-off (per user Q3).
"""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure, dependencies_ready


@registry.register
class MasterBotBundleRefreshTask:
    NAME = "master_bot_bundle_refresh"
    WORKLOAD_CLASS = WorkloadClass.API_HOT if hasattr(WorkloadClass, "API_HOT") else "api_hot"
    DEPENDS_ON = ("ranking",)
    MIN_INTERVAL_S = 1800
    PRIORITY_BASE = 45.0
    CPU_ESTIMATE_CORES = 0.3
    RAM_ESTIMATE_MB = 256
    EXPECTED_DURATION_S = 10.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.85
    PASSIVE = True   # operator-approved auto-refresh; deploy remains manual

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        p = freshness_pressure(self.NAME, self.MIN_INTERVAL_S)
        dep, stale = dependencies_ready(self.DEPENDS_ON, min_recent=1)
        eligible = p >= 1.0 and dep >= 1.0
        return Readiness(
            eligible=eligible,
            reason="due" if eligible else ("waiting_deps" if dep < 1.0 else "recent"),
            pressure=p, dependency_readiness=dep, depends_stale=stale,
        )

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            # Prefer `master_bot_engine.rebuild_tiers` if present.
            fn = None
            try:
                from engines.master_bot_engine import rebuild_tiers as _rt  # type: ignore
                fn = _rt
            except Exception:                                    # pragma: no cover
                try:
                    from engines.master_bot_engine import build_all_tiers as _rt  # type: ignore
                    fn = _rt
                except Exception:
                    fn = None
            if fn is None:
                return TaskResult(ok=True, reason="engine_stub_no_op",
                                  duration_ms=int((time.time() - t0) * 1000),
                                  payload={"tiers": {"1": 10, "2": 10, "3": 10},
                                           "note": "no rebuild_tiers() — placeholder"})
            import inspect
            res = await fn() if inspect.iscoroutinefunction(fn) else fn()
            return TaskResult(ok=True, reason="bundles_refreshed",
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={"result": str(res)[:200]})
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
