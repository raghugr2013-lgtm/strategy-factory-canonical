"""Phase H5 orchestrator task: broker_health_check.

Samples the active broker adapter's health every `EXEC_HEALTH_INTERVAL_S`
(default 60s). Populates `broker_health` collection + emits
`broker_health_check` outcome events. Active by default (cheap, local),
respects `EXEC_ENABLED` master switch.
"""
from __future__ import annotations

import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure


@registry.register
class BrokerHealthCheckTask:
    NAME = "broker_health_check"
    WORKLOAD_CLASS = WorkloadClass.API_HOT if hasattr(WorkloadClass, "API_HOT") else "api_hot"
    DEPENDS_ON = ()
    MIN_INTERVAL_S = 60
    PRIORITY_BASE = 72.0
    CPU_ESTIMATE_CORES = 0.05
    RAM_ESTIMATE_MB = 32
    EXPECTED_DURATION_S = 0.5
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.80
    PASSIVE = False

    HARD_TIMEOUT_S = 30.0        # Phase 2 Stage 1
    RETRY_POLICY = "default"      # Phase 2 Stage 1
    async def readiness(self, ctx: OrchestratorContext) -> Readiness:
        try:
            from engines.execution import exec_enabled
            if not exec_enabled():
                return Readiness(eligible=False, reason="EXEC_ENABLED=false")
        except Exception:  # pragma: no cover
            pass
        p = freshness_pressure(self.NAME, self.MIN_INTERVAL_S)
        return Readiness(
            eligible=p >= 1.0,
            reason="due" if p >= 1.0 else "recent",
            pressure=p,
        )

    async def run(self, ctx: OrchestratorContext) -> TaskResult:
        t0 = time.time()
        try:
            from engines.execution.broker_health import sample_broker_health
            snap = await sample_broker_health()
            if snap is None:
                return TaskResult(
                    ok=True,
                    reason="no_adapter_or_disabled",
                    duration_ms=int((time.time() - t0) * 1000),
                    payload={"sampled": False},
                )
            return TaskResult(
                ok=True,
                reason=f"score_5m={snap.score_5m} band={snap.band}",
                duration_ms=int((time.time() - t0) * 1000),
                payload={"sampled": True,
                          "broker": snap.broker,
                          "score_5m": snap.score_5m,
                          "score_60m": snap.score_60m,
                          "score_24h": snap.score_24h,
                          "band": snap.band},
            )
        except Exception as e:  # noqa: BLE001
            return TaskResult(ok=False,
                              reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])
