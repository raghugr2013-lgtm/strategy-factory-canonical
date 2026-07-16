"""Task adapter: strategy_generate — LLM-driven strategy text generation."""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass


@registry.register
class StrategyGenerateTask:
    NAME = "strategy_generate"
    WORKLOAD_CLASS = WorkloadClass.AGENT if hasattr(WorkloadClass, "AGENT") else "agent"
    DEPENDS_ON = ()
    MIN_INTERVAL_S = 0                     # event-driven, no timer
    PRIORITY_BASE = 65.0
    CPU_ESTIMATE_CORES = 0.4
    RAM_ESTIMATE_MB = 256
    EXPECTED_DURATION_S = 6.0
    AI_PROVIDER_REQUIRED = True
    COST_ESTIMATE_USD = 0.002
    BUSINESS_VALUE = 0.85
    PASSIVE = False

    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        # Always eligible when there's room; freshness handled implicitly
        # via the fact that downstream tasks (backtest/mutation) consume
        # generated strategies.
        return Readiness(eligible=True, reason="on_demand", pressure=1.0)

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        seed = ctx.default_seed
        try:
            from engines.strategy_engine import generate_strategy_text
            text = await generate_strategy_text(
                seed.get("pair", "EURUSD"),
                seed.get("timeframe", "H1"),
                seed.get("style", "trend-following"),
            )
            ok = bool(text)
            return TaskResult(ok=ok, reason="generated" if ok else "empty_output",
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={"length": len(text or "")})
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
