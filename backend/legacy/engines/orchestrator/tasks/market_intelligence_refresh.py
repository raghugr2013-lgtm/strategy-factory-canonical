"""Phase G task adapter: market_intelligence_refresh.

Refreshes MarketIntelligence for every (pair, timeframe) in the
configured universe. Piggybacks on `market_data_topup` — the topup
task keeps historical BID / BI5 buckets fresh; this task consumes
those snapshots (via `data_engine.get_recent_closes` when available)
plus in-memory snapshot appends. When no snapshots exist yet the
aggregator returns a neutral MarketIntelligence and the task remains
a cheap no-op.

Active by default (no LLM calls, no external I/O beyond Mongo reads),
but can be paused with `ORCH_TASK_MARKET_INTELLIGENCE_REFRESH_PASSIVE=true`.
"""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure, dependencies_ready


@registry.register
class MarketIntelligenceRefreshTask:
    NAME = "market_intelligence_refresh"
    WORKLOAD_CLASS = WorkloadClass.API_HOT if hasattr(WorkloadClass, "API_HOT") else "api_hot"
    DEPENDS_ON = ("market_data_topup",)
    MIN_INTERVAL_S = 300     # 5-min freshness SLA
    PRIORITY_BASE = 65.0
    CPU_ESTIMATE_CORES = 0.2
    RAM_ESTIMATE_MB = 128
    EXPECTED_DURATION_S = 4.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.85
    PASSIVE = False           # active by default (cheap + local)

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        # Master switch first — respects the MI_ENABLED env.
        try:
            from engines.market_intel_engine import config as micfg
            if not micfg.mi_enabled():
                return Readiness(eligible=False, reason="MI_ENABLED=false")
        except Exception:                                 # pragma: no cover
            pass
        p = freshness_pressure(self.NAME, self.MIN_INTERVAL_S)
        dep, stale = dependencies_ready(self.DEPENDS_ON, min_recent=1)
        eligible = p >= 1.0     # Dependency is soft: we still refresh even if
                                # market_data_topup hasn't fired yet (piggyback
                                # semantics — the ledger may already have snaps
                                # from a prior boot).
        return Readiness(
            eligible=eligible,
            reason="due" if eligible else "recent",
            pressure=p,
            dependency_readiness=dep,
            depends_stale=stale,
        )

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        refreshed = 0
        errors = 0
        try:
            from engines.market_intel_engine import (
                config as micfg,
                refresh_market_intelligence,
            )
            for pair in micfg.mi_universe():
                for tf in micfg.mi_timeframes():
                    try:
                        await refresh_market_intelligence(pair, tf)
                        refreshed += 1
                    except Exception:                     # noqa: BLE001
                        errors += 1
            return TaskResult(
                ok=True,
                reason=f"refreshed={refreshed} errors={errors}",
                duration_ms=int((time.time() - t0) * 1000),
                payload={"refreshed": refreshed, "errors": errors,
                          "universe": micfg.mi_universe(),
                          "timeframes": micfg.mi_timeframes()},
            )
        except Exception as e:                             # noqa: BLE001
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
