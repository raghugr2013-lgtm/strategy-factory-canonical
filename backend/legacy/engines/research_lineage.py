"""Phase 26 / G1 — Research Run Lineage.

Single source of truth for "which research-cycle produced this artifact?".
Threads a stable ``research_run_id`` through:

    ai_orchestrator.run_tick
        → multi_cycle_runner.start_multi_cycle
            → auto_mutation_runner.run_single_cycle
                → _run_one_strategy
                    → strategy_memory.record_from_mutation_result
                    → strategy_library.save_strategy

…and through the standalone ``auto_scheduler`` path (which generates its own
research_run for each tick) so EVERY discovery artifact in the system has a
lineage handle.

Design tenets (matches Phase 26.5 lifecycle plan):
    * Additive — every existing signature accepts ``research_run_id`` as
      an optional keyword arg. Old callers that pass nothing still work.
    * Pure persistence — this module never mutates engines. It only
      creates the lineage doc, exposes child-attach helpers, and answers
      lineage queries.
    * Deterministic IDs — ``rr_<UTCYYYYMMDDTHHMMSS>_<8hex>`` so they sort
      naturally and remain human-readable in logs.
    * Cheap reads — the doc carries summaries; we never recompute on read.

Public surface:
    * new_research_run(trigger_type, trigger_reason=, rule_id=, config=) -> rrid
    * attach_child(rrid, kind, child_id, **fields)
    * append_summary(rrid, **delta)
    * mark_finished(rrid, status="completed", summary=None, error=None)
    * get_run(rrid)
    * list_runs(limit=50)
    * get_runs_for_strategy(strategy_hash, limit=20)
    * get_runs_for_library_id(library_id, limit=20)
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "research_runs"

# Trigger taxonomy — keep stable; UI groups by these strings.
TRIGGER_TYPES = {
    "orchestrator_tick",     # ai_orchestrator.run_tick fired a rule that executed
    "auto_scheduler_tick",   # auto_scheduler.py 15-min cron
    "manual_api",            # POST /api/multi-cycle/start, /auto-mutation/run, etc.
    "manual_rerun",          # explorer "↻" button
    "ingestion",             # strategy_ingestion runner
    "workspace_generate",    # workspace tab
}

# Child-kind taxonomy — also UI-stable.
CHILD_KINDS = {
    "multi_cycle_run",
    "auto_run_cycle",
    "mutation_run",
    "library_save",
    "history_row",
    "ingestion_batch",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_id() -> str:
    """``rr_<UTCYYYYMMDDTHHMMSS>_<8hex>`` — human-readable + unique."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"rr_{ts}_{secrets.token_hex(4)}"


# ── Creation ────────────────────────────────────────────────────────

async def new_research_run(
    *,
    trigger_type: str,
    trigger_reason: Optional[str] = None,
    rule_id: Optional[str] = None,
    source: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    parent_research_run_id: Optional[str] = None,
) -> str:
    """Create a new lineage root doc. Returns the new research_run_id.

    Best-effort persistence — never raises out to the caller. Even if the
    DB hiccups, the in-memory id is returned so the caller's pipeline
    never breaks because lineage failed.
    """
    if trigger_type not in TRIGGER_TYPES:
        logger.warning(
            "[lineage] unknown trigger_type=%s — accepting anyway", trigger_type,
        )
    rrid = generate_id()
    doc = {
        "research_run_id": rrid,
        "started_at": _now_iso(),
        "finished_at": None,
        "status": "running",
        "trigger": {
            "type": trigger_type,
            "reason": trigger_reason,
            "rule_id": rule_id,
            "source": source,
        },
        "config": dict(config or {}),
        "children": {
            "multi_cycle_run": [],
            "auto_run_cycle": [],
            "mutation_run": [],
            "library_save": [],
            "history_row": 0,           # row count, not list (can be huge)
            "ingestion_batch": [],
        },
        "summary": {
            "strategies_generated": 0,
            "strategies_saved": 0,
            "library_ids": [],
            "envs_scanned": [],
            "best_pf": None,
            "avg_pf": None,
            "errors": 0,
        },
        "parent_research_run_id": parent_research_run_id,
    }
    try:
        db = get_db()
        await db[COLLECTION].insert_one({**doc})
    except Exception as e:                                  # pragma: no cover
        logger.warning("[lineage] new_research_run persist failed: %s", e)
    return rrid


# ── Mutation helpers (used by engines as they emit children) ───────

async def attach_child(
    rrid: Optional[str],
    kind: str,
    child_id: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Append a child reference to the lineage doc.

    No-op if ``rrid`` is None (engines that aren't orchestrator-triggered).
    """
    if not rrid or not child_id:
        return
    if kind not in CHILD_KINDS:
        logger.debug("[lineage] unknown child kind=%s", kind)
        return
    try:
        db = get_db()
        # history_row is a counter, not a list — saves storage when
        # millions of rows fan out from one research run.
        if kind == "history_row":
            await db[COLLECTION].update_one(
                {"research_run_id": rrid},
                {"$inc": {"children.history_row": 1}},
            )
            return
        entry: Dict[str, Any] = {"id": child_id, "at": _now_iso()}
        if extra:
            entry.update({k: v for k, v in extra.items() if v is not None})
        await db[COLLECTION].update_one(
            {"research_run_id": rrid},
            {"$push": {f"children.{kind}": entry}},
        )
    except Exception as e:                                  # pragma: no cover
        logger.warning("[lineage] attach_child failed: %s", e)


async def append_summary(rrid: Optional[str], **delta: Any) -> None:
    """Increment counters / update best/avg PF on the summary block.

    Recognised keys: strategies_generated, strategies_saved, errors,
    best_pf (max), avg_pf (running mean — sets directly), library_ids
    (push), envs_scanned (push unique).
    """
    if not rrid or not delta:
        return
    inc: Dict[str, Any] = {}
    sets: Dict[str, Any] = {}
    add_to_set: Dict[str, Any] = {}
    for k, v in delta.items():
        if v is None:
            continue
        full = f"summary.{k}"
        if k in ("strategies_generated", "strategies_saved", "errors"):
            inc[full] = int(v)
        elif k == "best_pf":
            sets[full] = float(v)            # caller already takes max
        elif k == "avg_pf":
            sets[full] = float(v)
        elif k == "library_ids":
            add_to_set[full] = (
                {"$each": list(v)} if isinstance(v, (list, tuple, set))
                else v
            )
        elif k == "envs_scanned":
            add_to_set[full] = (
                {"$each": [list(x) for x in v]} if isinstance(v, (list, tuple))
                else v
            )
    update: Dict[str, Any] = {}
    if inc:
        update["$inc"] = inc
    if sets:
        update["$set"] = sets
    if add_to_set:
        update["$addToSet"] = add_to_set
    if not update:
        return
    try:
        db = get_db()
        await db[COLLECTION].update_one({"research_run_id": rrid}, update)
    except Exception as e:                                  # pragma: no cover
        logger.warning("[lineage] append_summary failed: %s", e)


async def mark_finished(
    rrid: Optional[str],
    *,
    status: str = "completed",
    summary: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    if not rrid:
        return
    set_payload: Dict[str, Any] = {
        "finished_at": _now_iso(),
        "status": status,
    }
    if error:
        set_payload["error"] = str(error)[:500]
    if summary:
        # Merge top-level summary keys (counts already maintained via append_summary)
        for k, v in summary.items():
            set_payload[f"summary.{k}"] = v
    try:
        db = get_db()
        await db[COLLECTION].update_one(
            {"research_run_id": rrid},
            {"$set": set_payload},
        )
    except Exception as e:                                  # pragma: no cover
        logger.warning("[lineage] mark_finished failed: %s", e)


# ── Read API ───────────────────────────────────────────────────────

async def get_run(rrid: str) -> Optional[Dict[str, Any]]:
    if not rrid:
        return None
    db = get_db()
    return await db[COLLECTION].find_one({"research_run_id": rrid}, {"_id": 0})


async def list_runs(
    *, limit: int = 50, trigger_type: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    db = get_db()
    q: Dict[str, Any] = {}
    if trigger_type:
        q["trigger.type"] = trigger_type
    if status:
        q["status"] = status
    cur = (
        db[COLLECTION]
        .find(q, {"_id": 0})
        .sort("started_at", -1)
        .limit(max(1, min(int(limit), 200)))
    )
    return [d async for d in cur]


async def get_runs_for_strategy(
    strategy_hash: str, *, limit: int = 20,
) -> List[Dict[str, Any]]:
    """Lineage lookup — every research_run that touched a strategy_hash.

    Joins via ``strategy_performance_history`` which is the per-row
    fan-out collection.
    """
    if not strategy_hash:
        return []
    db = get_db()
    rrids: List[str] = []
    seen: set = set()
    cur = (
        db["strategy_performance_history"]
        .find(
            {"strategy_hash": strategy_hash, "research_run_id": {"$ne": None}},
            {"_id": 0, "research_run_id": 1, "ts": 1},
        )
        .sort("ts", -1)
        .limit(500)
    )
    async for row in cur:
        rrid = row.get("research_run_id")
        if rrid and rrid not in seen:
            seen.add(rrid)
            rrids.append(rrid)
            if len(rrids) >= limit:
                break
    if not rrids:
        return []
    runs = []
    async for d in db[COLLECTION].find(
        {"research_run_id": {"$in": rrids}}, {"_id": 0},
    ):
        runs.append(d)
    # Preserve the recency order from history.
    runs.sort(key=lambda r: rrids.index(r["research_run_id"]))
    return runs


async def get_runs_for_library_id(
    library_id: str, *, limit: int = 20,
) -> List[Dict[str, Any]]:
    """Lineage lookup keyed by saved library_id (alternative to strategy_hash)."""
    if not library_id:
        return []
    db = get_db()
    cur = (
        db[COLLECTION]
        .find(
            {"summary.library_ids": library_id},
            {"_id": 0},
        )
        .sort("started_at", -1)
        .limit(max(1, min(int(limit), 200)))
    )
    return [d async for d in cur]
