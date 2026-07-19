"""Task adapter: ranking — recompute strategy rankings after new backtests.

Event-driven via dependency readiness (>= 10 recent backtest_ok) OR a
freshness SLA (15 min upper bound).
"""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure


@registry.register
class RankingTask:
    NAME = "ranking"
    WORKLOAD_CLASS = WorkloadClass.API_HOT if hasattr(WorkloadClass, "API_HOT") else "api_hot"
    DEPENDS_ON = ("backtest",)
    MIN_INTERVAL_S = 900
    PRIORITY_BASE = 50.0
    CPU_ESTIMATE_CORES = 0.3
    RAM_ESTIMATE_MB = 256
    EXPECTED_DURATION_S = 5.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.8
    PASSIVE = False

    HARD_TIMEOUT_S = 60.0        # Phase 2 Stage 1
    RETRY_POLICY = "default"      # Phase 2 Stage 1
    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        from ..core import get_orchestrator
        orc = get_orchestrator()
        # Event trigger: at least 10 backtest successes since last ranking.
        bt_ok = orc._runs_ok.get("backtest", 0) + orc._runs_ok.get("learning_cycle", 0)  # noqa: SLF001
        last_rank_calls = orc._runs_total.get(self.NAME, 0)                             # noqa: SLF001
        delta = bt_ok - (last_rank_calls * 10)   # allow up to 10 backtests per ranking
        event_pressure = min(2.0, max(0.0, delta / 10.0))
        sla_pressure = freshness_pressure(self.NAME, self.MIN_INTERVAL_S)
        pressure = max(event_pressure, sla_pressure)
        eligible = pressure >= 1.0
        return Readiness(eligible=eligible,
                         reason="ranking_due" if eligible else "no_new_backtests",
                         pressure=pressure)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            # Prefer `strategy_ranking_engine.rank_all` when available;
            # fall back to `ranking_engine.rank_all`.
            fn = None
            try:
                from engines.strategy_ranking_engine import rank_all as _rank_all  # type: ignore
                fn = _rank_all
            except Exception:                                    # pragma: no cover
                try:
                    from engines.ranking_engine import rank_all as _rank_all  # type: ignore
                    fn = _rank_all
                except Exception:
                    fn = None
            if fn is None:
                return TaskResult(ok=True, reason="engine_stub_no_op",
                                  duration_ms=int((time.time() - t0) * 1000),
                                  payload={"note": "no rank_all() found"})
            import inspect
            res = await fn() if inspect.iscoroutinefunction(fn) else fn()
            return TaskResult(ok=True, reason="ranked",
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={"result": str(res)[:200]})
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
