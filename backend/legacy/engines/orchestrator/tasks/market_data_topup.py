"""Task adapter: market_data_topup.

Wraps `data_engine.auto_data_maintainer` — refreshes the historical BID / BI5
buckets so downstream backtests always have fresh data. Fires on a freshness
SLA (default 60 min). Passive default: OFF (active on day one)."""
from __future__ import annotations

import time
from typing import Any

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure


@registry.register
class MarketDataTopUpTask:
    NAME = "market_data_topup"
    WORKLOAD_CLASS = WorkloadClass.IO if hasattr(WorkloadClass, "IO") else "io"
    DEPENDS_ON = ()
    MIN_INTERVAL_S = 3600
    PRIORITY_BASE = 60.0
    CPU_ESTIMATE_CORES = 0.3
    RAM_ESTIMATE_MB = 256
    EXPECTED_DURATION_S = 30.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.9
    PASSIVE = False

    HARD_TIMEOUT_S = 300.0        # Phase 2 Stage 1
    RETRY_POLICY = "default"      # Phase 2 Stage 1
    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        p = freshness_pressure(self.NAME, self.MIN_INTERVAL_S)
        # Only "eligible" once the freshness SLA is due — otherwise this
        # task lives on a timer.
        eligible = p >= 1.0
        return Readiness(
            eligible=eligible,
            reason="freshness_sla_due" if eligible else "recent",
            pressure=p,
        )

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            from data_engine import auto_data_maintainer as _adm
            # `_adm.trigger_topup()` (if present) is preferred; fall back to
            # `_adm.run_one_maintenance_pass()` — implementation-agnostic hook.
            fn = (
                getattr(_adm, "trigger_topup", None)
                or getattr(_adm, "run_one_maintenance_pass", None)
                or getattr(_adm, "run_once", None)
            )
            if fn is None:
                return TaskResult(ok=True, reason="engine_stub_no_op",
                                  duration_ms=int((time.time() - t0) * 1000),
                                  payload={"note": "auto_data_maintainer has no top-up hook"})
            res: Any = await fn() if _is_coro(fn) else fn()
            return TaskResult(ok=True, reason="topup_ok",
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={"result": _safe(res)})
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])


def _is_coro(fn) -> bool:
    import inspect
    return inspect.iscoroutinefunction(fn)


def _safe(obj: Any) -> Any:
    """Best-effort JSON-safe representation."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    try:
        import json
        json.dumps(obj)
        return obj
    except Exception:
        return str(obj)[:200]
