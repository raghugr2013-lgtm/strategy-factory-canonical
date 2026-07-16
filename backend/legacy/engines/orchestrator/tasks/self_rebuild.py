"""Phase D task adapter: self_rebuild.

Orchestrator-driven full portfolio rebuild pass. Reads a master bot's
persisted portfolio state, runs the Phase D pipeline, and emits
outcome_events for every autonomous decision. PASSIVE-by-default until
operator explicitly activates via
`ORCH_TASK_SELF_REBUILD_PASSIVE=false`.
"""
from __future__ import annotations

import os
import time

from ..registry import registry
from ..types import OrchestratorContext, Readiness, TaskResult, WorkloadClass
from ._helpers import freshness_pressure, dependencies_ready


@registry.register
class SelfRebuildTask:
    NAME = "self_rebuild"
    WORKLOAD_CLASS = WorkloadClass.API_HOT if hasattr(WorkloadClass, "API_HOT") else "api_hot"
    DEPENDS_ON = ("ranking",)
    MIN_INTERVAL_S = 900   # 15 min freshness SLA
    PRIORITY_BASE = 55.0
    CPU_ESTIMATE_CORES = 0.2
    RAM_ESTIMATE_MB = 128
    EXPECTED_DURATION_S = 5.0
    AI_PROVIDER_REQUIRED = False
    COST_ESTIMATE_USD = 0.0
    BUSINESS_VALUE = 0.9
    PASSIVE = True

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
            from engines.portfolio import rebuild_master_bot, PortfolioState
            from engines.intelligence.market_regime import current_regime

            master_bot_id = os.environ.get("ORCH_MASTER_BOT_ID", "")
            # Best-effort portfolio state load — falls back to empty state.
            state = await _load_state(master_bot_id) or PortfolioState(
                master_bot_id=master_bot_id or "default",
                members=[],
            )
            regime_snap = await current_regime(
                pair=ctx.default_seed.get("pair", "EURUSD"),
                timeframe=ctx.default_seed.get("timeframe", "H1"),
            )
            report = await rebuild_master_bot(state, regime=regime_snap.regime)
            return TaskResult(
                ok=True,
                reason=f"rebuilt regime={regime_snap.regime} "
                       f"changes={report.changes_applied}",
                duration_ms=int((time.time() - t0) * 1000),
                payload={
                    "master_bot_id":   report.master_bot_id,
                    "regime":          report.regime,
                    "changes":         report.changes_applied,
                    "cap_hit":         report.change_cap_hit,
                    "active_hash":     report.active_selection.get("active_hash"),
                    "outcome_events":  len(report.outcome_events_ids),
                },
            )
        except Exception as e:                                # noqa: BLE001
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])


async def _load_state(master_bot_id: str):
    """Best-effort — pull tier members from `master_bots` + strategy_library.
    Returns None on any error; caller falls back to empty state."""
    if not master_bot_id:
        return None
    try:
        from engines.master_bot_engine import list_tiers
        from engines.portfolio import PortfolioMember, PortfolioState
        tiers = await list_tiers(master_bot_id)
        members = []
        for t in tiers or []:
            for h in (t.get("strategies") or []):
                members.append(PortfolioMember(
                    strategy_hash=str(h),
                    tier=str(t.get("tier") or "tier_3"),
                ))
        return PortfolioState(master_bot_id=master_bot_id, members=members)
    except Exception:                                        # noqa: BLE001
        return None
