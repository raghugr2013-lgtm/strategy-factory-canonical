"""
Orchestrator heartbeat API (additive, Phase 1 P1.4).

Read-only operator-visible heartbeat for the orchestrator scheduler.
Surfaces tick cadence, last-tick recency, jobs pending, and (when active)
the factory_runner ownership state so the operator can verify no duplicate
schedulers are running.

Endpoints:
    GET /api/orchestrator/heartbeat
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends

from auth_utils import get_current_user
from engines.db import get_db
from engines import orchestrator_scheduler as orch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orchestrator", tags=["orchestrator-heartbeat"])


@router.get("/heartbeat")
async def heartbeat(_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Orchestrator scheduler heartbeat + ownership view.

    Returns:
        {
          "scheduler_pid": int,                              # current process PID
          "factory_runner_owns_schedulers": bool,            # env flag state
          "scheduler_active": bool,                          # APScheduler running
          "interval_minutes": int | null,
          "last_tick_at": ISO | null,
          "ticks_in_last_hour": int,
          "ticks_in_last_24h": int,
          "duplicate_tick_warning": bool,                    # any ticks within 5s of each other?
          "duplicate_tick_count_last_24h": int,
          "audit_log_size": int,                             # rough scale gauge
          "evaluated_at": ISO,
        }
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    one_hour_ago = (now - __import__("datetime").timedelta(hours=1)).isoformat()
    one_day_ago = (now - __import__("datetime").timedelta(hours=24)).isoformat()

    # Tick events from audit_log
    ticks_in_hour = await db.audit_log.count_documents({
        "event": "ORCHESTRATOR_TICK_EMITTED",
        "ts": {"$gte": one_hour_ago},
    })
    ticks_in_day = await db.audit_log.count_documents({
        "event": "ORCHESTRATOR_TICK_EMITTED",
        "ts": {"$gte": one_day_ago},
    })

    # Last tick at
    last_doc = await db.audit_log.find_one(
        {"event": "ORCHESTRATOR_TICK_EMITTED"},
        sort=[("ts", -1)],
        projection={"_id": 0, "ts": 1},
    )
    last_tick_at = last_doc["ts"] if last_doc else None

    # Duplicate-tick detection: any two ticks within 5s of each other (last 24h)?
    duplicate_count = 0
    cursor = db.audit_log.find(
        {"event": "ORCHESTRATOR_TICK_EMITTED", "ts": {"$gte": one_day_ago}},
        projection={"_id": 0, "ts": 1},
    ).sort("ts", 1)
    prev_ts: str = ""
    async for row in cursor:
        ts = row.get("ts", "")
        if prev_ts:
            try:
                d1 = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
                d2 = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if (d2 - d1).total_seconds() < 5.0:
                    duplicate_count += 1
            except Exception:
                pass
        prev_ts = ts

    # Scheduler state
    try:
        sched_status = await orch.get_status()
    except Exception:
        try:
            sched_status = orch.get_status()  # sync fallback
        except Exception:
            sched_status = {}
    if not isinstance(sched_status, dict):
        sched_status = {}

    audit_size = await db.audit_log.estimated_document_count()

    return {
        "scheduler_pid": os.getpid(),
        "factory_runner_owns_schedulers": (
            os.environ.get("FACTORY_RUNNER_OWNS_SCHEDULERS", "false").lower() == "true"
        ),
        "scheduler_active": bool(sched_status.get("running")),
        "interval_minutes": sched_status.get("interval_minutes"),
        "last_tick_at": last_tick_at,
        "ticks_in_last_hour": int(ticks_in_hour),
        "ticks_in_last_24h": int(ticks_in_day),
        "duplicate_tick_warning": duplicate_count > 0,
        "duplicate_tick_count_last_24h": int(duplicate_count),
        "audit_log_size": int(audit_size),
        "evaluated_at": now.isoformat(),
    }
