"""
LLM health-by-provider API (additive, Phase 1 P1.3).

Reads rolling LLM call telemetry from `llm_call_log` and exposes
per-provider success / failover / latency aggregates. Read-only.

Endpoints:
    GET /api/llm/health-by-provider?window_minutes=60
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from auth_utils import get_current_user
from engines.db import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["llm-health"])


@router.get("/health-by-provider")
async def health_by_provider(
    window_minutes: int = Query(60, ge=1, le=10080),  # max 1 week
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Per-provider rolling health stats from llm_call_log.

    Output:
        {
          "window_minutes": 60,
          "window_start": ISO,
          "window_end": ISO,
          "providers": [
            {
              "provider": "openai",
              "total_calls": int,
              "successes": int,
              "retries": int,
              "exceptions": int,
              "failover_used": int,
              "offline_fallback": int,
              "success_rate": float,
              "error_rate": float,
              "p50_latency_ms": int | null,
              "p95_latency_ms": int | null,
              "last_outcome_at": ISO | null,
            }, ...
          ],
          "tasks": [
            {"task": "strategy", "provider": "openai", "calls": N, "success_rate": ...},
            ...
          ],
          "evaluated_at": ISO,
        }
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)
    win_iso = window_start.isoformat()

    # Pull rows in window
    cursor = db.llm_call_log.find({"ts": {"$gte": win_iso}}).sort("ts", 1)
    rows = [r async for r in cursor]

    # Aggregate per-provider
    by_prov: Dict[str, Dict[str, Any]] = {}
    by_task: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        prov = r.get("provider") or "unknown"
        task = r.get("task") or "unknown"
        outcome = r.get("outcome") or "unknown"
        lat = r.get("latency_ms")
        ts = r.get("ts")

        p = by_prov.setdefault(prov, {
            "provider": prov, "total_calls": 0, "successes": 0, "retries": 0,
            "exceptions": 0, "failover_used": 0, "offline_fallback": 0,
            "_latencies": [], "last_outcome_at": None,
        })
        p["total_calls"] += 1
        if outcome == "success":
            p["successes"] += 1
        elif outcome == "retry":
            p["retries"] += 1
        elif outcome == "exception":
            p["exceptions"] += 1
        elif outcome == "failover_used":
            p["failover_used"] += 1
        elif outcome == "offline_fallback":
            p["offline_fallback"] += 1
        if isinstance(lat, (int, float)) and lat >= 0:
            p["_latencies"].append(int(lat))
        if ts and (p["last_outcome_at"] is None or ts > p["last_outcome_at"]):
            p["last_outcome_at"] = ts

        # Per-task rollup keyed on (task, provider)
        key = f"{task}|{prov}"
        t = by_task.setdefault(key, {
            "task": task, "provider": prov, "calls": 0, "successes": 0,
        })
        t["calls"] += 1
        if outcome == "success":
            t["successes"] += 1

    # Finalise
    providers: List[Dict[str, Any]] = []
    for prov, p in by_prov.items():
        lats = sorted(p.pop("_latencies"))
        if lats:
            p["p50_latency_ms"] = lats[len(lats) // 2]
            p["p95_latency_ms"] = lats[int(len(lats) * 0.95)] if len(lats) > 1 else lats[0]
        else:
            p["p50_latency_ms"] = None
            p["p95_latency_ms"] = None
        total = p["total_calls"]
        p["success_rate"] = round(p["successes"] / total, 4) if total else 0.0
        p["error_rate"] = round((p["exceptions"] + p["retries"]) / total, 4) if total else 0.0
        providers.append(p)
    providers.sort(key=lambda x: -x["total_calls"])

    task_rows: List[Dict[str, Any]] = []
    for t in by_task.values():
        c = t["calls"]
        t["success_rate"] = round(t["successes"] / c, 4) if c else 0.0
        task_rows.append(t)
    task_rows.sort(key=lambda x: (x["task"], -x["calls"]))

    return {
        "window_minutes": window_minutes,
        "window_start": win_iso,
        "window_end": now.isoformat(),
        "providers": providers,
        "tasks": task_rows,
        "evaluated_at": now.isoformat(),
    }
