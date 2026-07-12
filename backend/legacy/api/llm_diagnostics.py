"""Phase 30.3 — LLM provider routing diagnostics (READ-ONLY).

Operator constraint:
  • Strictly advisory. Returns routing-state visibility, never mutates.
  • Does NOT expose API key values themselves — only presence booleans.
  • Includes recent call-log tail (last 50) for cost / quality monitoring.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import require_admin
from engines import llm_config as lc
from engines.db import get_db

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/diagnostics")
async def llm_diagnostics() -> Dict[str, Any]:
    """Return the resolved router state + per-task resolution. Read-only.

    Includes:
      • flags         — generator + router + auto-failover state
      • providers     — configured / model / api-key-present (NOT the key)
      • task_routing  — requested vs resolved per known task
      • fallback chain
      • known_tasks list
    """
    env = lc.validate_environment()
    # Strip any accidental key material — env shouldn't return keys, but
    # belt-and-braces against future changes.
    for prov, info in env.get("providers", {}).items():
        info.pop("api_key", None)
    env["auto_failover_enabled"] = lc.is_auto_failover_enabled()
    return env


@router.get("/call-log/recent")
async def recent_call_log(
    limit: int = 50,
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """ADMIN-ONLY. Return the most recent LLM call attempts (for cost +
    provider-quality drift monitoring). Read-only."""
    limit = max(1, min(int(limit), 500))
    try:
        db = get_db()
        cur = (db[lc.LLM_CALL_LOG_COLLECTION]
               .find({}, {"_id": 0})
               .sort("ts", -1)
               .limit(limit))
        rows = await cur.to_list(length=limit)
    except Exception as e:
        return {"rows": [], "error": str(e)[:200], "limit": limit}
    return {"rows": rows, "count": len(rows), "limit": limit}


@router.get("/runner-state")
async def runner_state() -> Dict[str, Any]:
    """Phase A.4–A.6 — diagnostic snapshot of the failover runner.

    Read-only. Exposes retry / failover / per-provider concurrency
    state so operators can verify the new infrastructure is engaged.
    """
    from engines import llm_runner
    return llm_runner.get_runner_state()


@router.get("/index-summary")
async def index_summary(
    admin: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    """Phase A.1 / A.2 — ADMIN-ONLY. Returns the set of indexes that
    currently exist on the hot collections."""
    from engines.db_indexes import get_index_summary
    return await get_index_summary()


@router.get("/cpu-pool")
async def cpu_pool_state() -> Dict[str, Any]:
    """Phase D.2 — read-only snapshot of the ProcessPoolExecutor state."""
    from engines import cpu_pool
    return cpu_pool.get_pool_state()
