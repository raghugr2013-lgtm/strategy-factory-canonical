"""Task adapter: master_bot_bundle_refresh — Phase C-integrated version.

Reads the top strategies from `strategy_library`, runs them through the
Phase C intelligence pipeline (classify → portfolio contribution → build
Tier 1 / 2 / 3), and emits an `outcome_events` record. Never persists tier
membership unless `ORCH_TASK_MASTER_BOT_BUNDLE_REFRESH_PERSIST=true` (per
Q3 direction — operator-approved deploy).

PASSIVE-by-default remains True for safety; the operator activates it via
`ORCH_TASK_MASTER_BOT_BUNDLE_REFRESH_PASSIVE=false`.
"""
from __future__ import annotations

import os
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
    HARD_TIMEOUT_S = 300.0        # Phase 2 Stage 1
    RETRY_POLICY = "default"      # Phase 2 Stage 1

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
            from engines.intelligence import build_tiered_bundles, emit_decision
            # Pull top strategies from `strategy_library` if it's available.
            strategies = await _load_top_library_strategies(limit=100)
            if not strategies:
                return TaskResult(ok=True, reason="empty_library",
                                  duration_ms=int((time.time() - t0) * 1000),
                                  payload={"note": "no strategies in library"})
            report = build_tiered_bundles(strategies)
            persist = (os.environ.get(
                "ORCH_TASK_MASTER_BOT_BUNDLE_REFRESH_PERSIST", ""
            ).strip().lower() in ("1", "true", "yes"))
            persisted = None
            if persist:
                persisted = await _persist_bundles(report)
            await emit_decision(
                "master_bot_bundle_refresh_task",
                reason=f"accepted={report.accepted} rejected={report.rejected}",
                metrics={
                    "pool_size":   report.pool_size,
                    "accepted":    report.accepted,
                    "tier_1_size": len(report.tier_1),
                    "tier_2_size": len(report.tier_2),
                    "tier_3_size": len(report.tier_3),
                },
                evidence={"persisted": bool(persisted)},
            )
            return TaskResult(ok=True, reason="bundles_refreshed",
                              duration_ms=int((time.time() - t0) * 1000),
                              payload={
                                  "pool_size":   report.pool_size,
                                  "accepted":    report.accepted,
                                  "tier_1_size": len(report.tier_1),
                                  "tier_2_size": len(report.tier_2),
                                  "tier_3_size": len(report.tier_3),
                                  "persisted":   bool(persisted),
                              })
        except Exception as e:
            return TaskResult(ok=False, reason=f"engine_error: {str(e)[:200]}",
                              duration_ms=int((time.time() - t0) * 1000),
                              error=str(e)[:240])


async def _load_top_library_strategies(limit: int = 100):
    """Best-effort loader from `strategy_library` collection. Returns [] on
    any error so the task degrades gracefully in tests / fresh installs."""
    try:
        from db import get_db  # legacy shim
        db = await get_db()
        cursor = db.strategy_library.find(
            {"backtest_result.profit_factor": {"$gt": 1.0}}
        ).sort([("backtest_result.profit_factor", -1)]).limit(limit)
        docs = await cursor.to_list(length=limit)
        # Drop `_id` (ObjectId) before returning.
        for d in docs:
            d.pop("_id", None)
        return docs
    except Exception:
        return []


async def _persist_bundles(report):
    try:
        from engines.master_bot_engine import list_master_bots, set_tier_metadata
        # Assume operator has selected a default master_bot_id via env,
        # otherwise pick the first available bot.
        bot_id = os.environ.get("ORCH_MASTER_BOT_ID")
        if not bot_id:
            bots = await list_master_bots()
            if not bots:
                return None
            bot_id = bots[0].get("id") or bots[0].get("_id")
        result = {}
        for tier_name, tier_list in (
            ("tier_1", report.tier_1),
            ("tier_2", report.tier_2),
            ("tier_3", report.tier_3),
        ):
            result[tier_name] = await set_tier_metadata(
                bot_id, tier_name,
                {"strategies": [s["strategy_hash"] for s in tier_list]},
            )
        return result
    except Exception:
        return None
