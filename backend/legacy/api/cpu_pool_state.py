"""
CPU pool diagnostic API (additive, Phase 2 P2.5).

Read-only operator-visible state of the ProcessPoolExecutor +
factory_runner ownership flag. Required for Phase 2 verification
that scaling activation has actually taken effect at runtime.

Endpoints:
    GET /api/cpu-pool/state
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import get_current_user
from engines import cpu_pool
from engines.db import get_db

router = APIRouter(prefix="/cpu-pool", tags=["cpu-pool"])


@router.get("/state")
async def cpu_pool_state(_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Snapshot of the CPU process pool + scheduler ownership flags.

    Returns:
        {
          "pool_enabled": bool,           # USE_PROCESS_POOL flag state
          "pool_size_configured": int,    # CPU_POOL_SIZE env
          "pool_initialized": bool,       # has any work been submitted?
          "worker_count": int,            # actual ProcessPoolExecutor max_workers
          "factory_runner_owns_schedulers": bool,
          "uvicorn_worker_pid": int,      # this process's PID
          "evaluated_at": ISO,
          "recent_mutation_runs": int,    # last 1h — proves pool actually exercised
          "recent_pipeline_log_count": int,
        }
    """
    state = cpu_pool.get_pool_state()

    # Touch Mongo for recent-activity proof
    db = get_db()
    now = datetime.now(timezone.utc)
    one_hour_ago_iso = (now - __import__("datetime").timedelta(hours=1)).isoformat()
    try:
        recent_muts = await db.mutation_runs.count_documents({"finished_at": {"$gte": one_hour_ago_iso}})
    except Exception:
        recent_muts = -1
    try:
        recent_pipe = await db.pipeline_logs.count_documents({"ts": {"$gte": one_hour_ago_iso}})
    except Exception:
        recent_pipe = -1

    return {
        "pool_enabled": state["enabled"],
        "pool_size_configured": state["pool_size_configured"],
        "pool_initialized": state["pool_initialized"],
        "worker_count": state["worker_count"],
        "factory_runner_owns_schedulers": (
            os.environ.get("FACTORY_RUNNER_OWNS_SCHEDULERS", "false").lower() == "true"
        ),
        "uvicorn_worker_pid": os.getpid(),
        "evaluated_at": now.isoformat(),
        "recent_mutation_runs_1h": recent_muts,
        "recent_pipeline_log_count_1h": recent_pipe,
    }
