"""
Phase 14.4 — Pipeline Logs.

Lightweight, additive structured event log that captures the key
moments of a pipeline run: strategy generation, backtest outcome,
validation rejection, save success/failure, mutation start/result,
auto-save result.

Design constraints (per spec):
  * Fully additive — no changes to scoring / validation / save.
  * Best-effort writes — `log_event` never raises, never blocks the
    caller on failure.
  * Bounded storage — list endpoint returns at most 500 rows.

Stored in a dedicated collection (`pipeline_logs`) so existing
telemetry (mutation_events, mutation_runs, mutation_stability_log,
strategy_library) stays untouched.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

PIPELINE_LOGS_COLL = "pipeline_logs"

# Canonical stages — checked at write time so callers can't drift.
STAGES = (
    "generation",
    "backtest",
    "validation",
    "mutation",
    "save",
    "auto_save",
)

LEVELS = ("info", "success", "warn", "error")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def log_event(
    stage: str,
    message: str,
    level: str = "info",
    *,
    run_id: Optional[str] = None,
    strategy_id: Optional[str] = None,
    pair: Optional[str] = None,
    timeframe: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a single pipeline-log row. Best-effort; never raises."""
    if stage not in STAGES:
        # Fall back to "info" stage rather than reject — we never want
        # logging to break a caller. Tag it so operators notice.
        meta = {**(meta or {}), "__unknown_stage__": stage}
        stage = "info" if "info" in STAGES else STAGES[0]
    if level not in LEVELS:
        level = "info"

    now_utc = datetime.now(timezone.utc)
    doc = {
        "ts": now_utc.isoformat(),
        # Phase 2 P2.8 — BSON Date companion that activates the TTL
        # index `ttl_pipeline_logs` (declared on `ts_dt`).
        "ts_dt": now_utc,
        "stage": stage,
        "level": level,
        "message": str(message)[:500],
        "run_id": run_id,
        "strategy_id": strategy_id,
        "pair": (pair or None),
        "timeframe": (timeframe or None),
        "meta": meta or {},
    }
    try:
        db = get_db()
        await db[PIPELINE_LOGS_COLL].insert_one(doc)
    except Exception as e:
        logger.debug("pipeline_logs insert failed: %s", e)


async def list_logs(
    *,
    limit: int = 100,
    run_id: Optional[str] = None,
    stage: Optional[str] = None,
    level: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch newest-first. Filters are optional."""
    db = get_db()
    limit = max(1, min(int(limit), 500))
    q: Dict[str, Any] = {}
    if run_id:
        q["run_id"] = run_id
    if stage:
        if stage not in STAGES:
            raise ValueError(f"unknown stage: {stage}")
        q["stage"] = stage
    if level:
        if level not in LEVELS:
            raise ValueError(f"unknown level: {level}")
        q["level"] = level
    cur = db[PIPELINE_LOGS_COLL].find(q, {"_id": 0}).sort("ts", -1).limit(limit)
    return [d async for d in cur]


async def clear_logs() -> int:
    """Utility for tests / admin. Returns count deleted."""
    db = get_db()
    res = await db[PIPELINE_LOGS_COLL].delete_many({})
    return res.deleted_count or 0
