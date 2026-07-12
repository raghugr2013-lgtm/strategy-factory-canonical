"""Ingestion orchestrator + scheduler.

Ties collector → parser → validator → normaliser → injector together,
persists per-run + per-strategy logs, and exposes a minimal scheduler
the API can toggle.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from engines.db import get_db

from .collector import (
    collect_from_github,
    collect_from_local_queue,
    collect_from_tradingview,
)
from .injector import inject_strategy
from .normalizer import normalise
from .parser import parse_strategy_with_ai
from .schema import IngestedStrategy
from .validator import validate

logger = logging.getLogger(__name__)

INGESTION_RUNS_COLL = "ingestion_runs"
INGESTED_STRATEGIES_COLL = "ingested_strategies"

DEFAULT_MAX_PER_RUN = 10
DEFAULT_SCHEDULE_HOURS = 3

_RUN_LOCK = asyncio.Lock()
_SCHEDULER: Optional[AsyncIOScheduler] = None

# In-memory state surfaced via GET /status.
STATE: Dict[str, Any] = {
    "last_run_id": None,
    "last_run_at": None,
    "last_run_status": None,
    "last_run_stats": None,
    "scheduler_enabled": False,
    "scheduler_interval_hours": DEFAULT_SCHEDULE_HOURS,
    "scheduler_next_run_at": None,
    "currently_running": False,
    "local_queue_size": 0,
}

_LOCAL_QUEUE: List[Dict[str, str]] = []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_local_strategy(entry: Dict[str, str]) -> int:
    """Append a manually-pasted strategy to the queue. Returns new queue size."""
    _LOCAL_QUEUE.append(entry)
    STATE["local_queue_size"] = len(_LOCAL_QUEUE)
    return len(_LOCAL_QUEUE)


def get_ingestion_state() -> Dict[str, Any]:
    return dict(STATE)


async def list_ingested_strategies(
    *, source: Optional[str] = None, status: Optional[str] = None, limit: int = 100,
) -> List[Dict[str, Any]]:
    db = get_db()
    q: Dict[str, Any] = {}
    if source:
        q["source"] = source
    if status:
        q["status"] = status
    limit = max(1, min(int(limit), 500))
    cur = db[INGESTED_STRATEGIES_COLL].find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
    return [d async for d in cur]


async def list_ingestion_runs(*, limit: int = 20) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 200))
    cur = db[INGESTION_RUNS_COLL].find({}, {"_id": 0}).sort("started_at", -1).limit(limit)
    return [d async for d in cur]


# ── Scheduler ────────────────────────────────────────────────────────

def _schedule_next_refresh() -> None:
    global _SCHEDULER
    if _SCHEDULER and _SCHEDULER.running:
        jobs = _SCHEDULER.get_jobs()
        if jobs:
            STATE["scheduler_next_run_at"] = jobs[0].next_run_time.isoformat() if jobs[0].next_run_time else None
        else:
            STATE["scheduler_next_run_at"] = None
    else:
        STATE["scheduler_next_run_at"] = None


def set_scheduler_enabled(
    enabled: bool, *, interval_hours: Optional[int] = None,
) -> Dict[str, Any]:
    """Turn the background scheduler on/off. Interval is clamped to [1, 12] h."""
    global _SCHEDULER
    if interval_hours is None:
        interval_hours = STATE["scheduler_interval_hours"]
    interval_hours = max(1, min(int(interval_hours), 12))
    STATE["scheduler_interval_hours"] = interval_hours

    if enabled:
        if _SCHEDULER is None:
            _SCHEDULER = AsyncIOScheduler()
        if not _SCHEDULER.running:
            try:
                _SCHEDULER.start()
            except Exception as e:
                logger.warning("scheduler start failed: %s", e)
        # Replace existing job (if any)
        for j in _SCHEDULER.get_jobs():
            j.remove()

        async def _tick():
            try:
                await run_ingestion_once(max_strategies=DEFAULT_MAX_PER_RUN)
            except Exception as e:
                logger.exception("scheduled ingestion failed: %s", e)

        _SCHEDULER.add_job(
            _tick,
            "interval", hours=interval_hours,
            id="ingestion_tick", coalesce=True, max_instances=1,
        )
        STATE["scheduler_enabled"] = True
    else:
        STATE["scheduler_enabled"] = False
        if _SCHEDULER and _SCHEDULER.running:
            try:
                _SCHEDULER.remove_all_jobs()
            except Exception:
                pass
    _schedule_next_refresh()
    return get_ingestion_state()


# ── Single-run orchestrator ──────────────────────────────────────────

async def run_ingestion_once(
    *,
    max_strategies: int = DEFAULT_MAX_PER_RUN,
    github_queries: Optional[List[str]] = None,
    use_github: bool = True,
    use_tradingview: bool = True,
    use_local_queue: bool = True,
    inject: bool = True,
    firm: str = "ftmo",
) -> Dict[str, Any]:
    """Execute one full ingest pass. Serialised by `_RUN_LOCK`."""
    if _RUN_LOCK.locked():
        raise RuntimeError("ingestion already running")

    async with _RUN_LOCK:
        STATE["currently_running"] = True
        run_id = uuid.uuid4().hex[:12]
        started_at = _now_iso()
        db = get_db()

        stats = {
            "total_fetched": 0,
            "total_parsed": 0,
            "total_valid": 0,
            "total_injected": 0,
            "total_rejected": 0,
            # Phase 30 — truthful filtration counters (additive, operator decision)
            "total_evidential": 0,    # injections that produced non-null PF + trades >= 30
            "total_abandoned":  0,    # injections that aborted (data_missing/no_trades/etc)
            "abandon_reasons":  {},   # {reason: count}
            "by_source": {},
            "reject_reasons": {},
            "best_pf_from_ingested": None,
            "best_pf_source": None,
            "best_pf_name": None,
        }
        per_strategy_docs: List[Dict[str, Any]] = []

        try:
            # ── Step 1: collect ──
            collected: List[Dict[str, Any]] = []
            if use_github:
                gh = await collect_from_github(
                    queries=github_queries,
                    max_total=max(2, max_strategies),
                )
                collected.extend(gh)
            if use_tradingview and len(collected) < max_strategies:
                tv = await collect_from_tradingview(
                    max_total=max(1, max_strategies - len(collected)),
                )
                collected.extend(tv)
            if use_local_queue and _LOCAL_QUEUE:
                loc = collect_from_local_queue(_LOCAL_QUEUE)
                collected.extend(loc)
                _LOCAL_QUEUE.clear()
                STATE["local_queue_size"] = 0

            collected = collected[:max_strategies]
            stats["total_fetched"] = len(collected)

            # ── Step 2–6: parse → validate → normalise → inject ──
            for raw in collected:
                src = raw.get("source") or "unknown"
                stats["by_source"].setdefault(src, {"fetched": 0, "valid": 0, "injected": 0})
                stats["by_source"][src]["fetched"] += 1

                try:
                    parsed: IngestedStrategy = await parse_strategy_with_ai(
                        raw["raw_code"],
                        source=src,
                        source_url=raw.get("url"),
                        name_hint=raw.get("name"),
                    )
                except Exception as e:
                    logger.exception("parse failed")
                    per_strategy_docs.append({
                        "run_id": run_id, "source": src, "status": "rejected",
                        "reason": f"parse_error: {str(e)[:160]}",
                        "confidence": 0.0,
                        "url": raw.get("url"),
                        "created_at": _now_iso(),
                    })
                    stats["total_rejected"] += 1
                    stats["reject_reasons"]["parse_error"] = stats["reject_reasons"].get("parse_error", 0) + 1
                    continue
                stats["total_parsed"] += 1

                normalised = normalise(parsed)
                ok, reason, quality = validate(normalised)
                normalised = normalised.model_copy(update={"quality_score": quality})
                if not ok:
                    normalised = normalised.model_copy(update={"rejection_reason": reason})

                doc = {
                    "run_id": run_id,
                    "created_at": _now_iso(),
                    "source": normalised.source,
                    "url": normalised.raw_source_url,
                    "name": normalised.name,
                    "type": normalised.type,
                    "indicators": normalised.indicators,
                    "entry_logic": normalised.entry_logic,
                    "exit_logic": normalised.exit_logic,
                    "risk_model": normalised.risk_model,
                    "timeframe": normalised.timeframe,
                    "pair": normalised.pair,
                    "confidence": normalised.confidence,
                    "quality_score": quality,
                    "status": "accepted" if ok else "rejected",
                    "reason": reason,
                    "raw_code_preview": (normalised.raw_code or "")[:400],
                }

                if not ok:
                    stats["total_rejected"] += 1
                    stats["reject_reasons"][reason] = stats["reject_reasons"].get(reason, 0) + 1
                    per_strategy_docs.append(doc)
                    continue

                stats["total_valid"] += 1
                stats["by_source"][src]["valid"] += 1

                # ── Step 7: inject (if allowed) ──
                if inject:
                    try:
                        mut = await inject_strategy(
                            normalised, max_variants=10, auto_save=True, firm=firm,
                        )
                    except Exception as e:
                        logger.exception("injection failed")
                        doc["status"] = "rejected"
                        doc["reason"] = f"inject_error: {str(e)[:160]}"
                        stats["total_rejected"] += 1
                        stats["reject_reasons"]["inject_error"] = stats["reject_reasons"].get("inject_error", 0) + 1
                        per_strategy_docs.append(doc)
                        continue

                    # Additive hook: record ingestion injection result
                    # into strategy_performance_history. Never raises.
                    #
                    # Phase 30 — Filtration Honesty:
                    # Only write history rows when the injection produced
                    # ACTUAL evidence. Null-metric rows (status=data_missing,
                    # no backtest, no trades) are NOT written to the evidence
                    # collection — they live in `ingestion_runs.per_strategy_docs`
                    # only. This is the inventory-vs-survivor separation
                    # operator decision (Phase 30, anti-drift).
                    _phase30_best = (mut.get("best_variant") or {}) if isinstance(mut, dict) else {}
                    _phase30_bt = _phase30_best.get("backtest") or {}
                    _phase30_pf = _phase30_bt.get("profit_factor")
                    _phase30_trades = _phase30_bt.get("total_trades")
                    _phase30_status = mut.get("status") if isinstance(mut, dict) else None
                    _phase30_has_evidence = (
                        isinstance(_phase30_pf, (int, float))
                        and isinstance(_phase30_trades, (int, float))
                        and int(_phase30_trades) > 0
                    )
                    if _phase30_has_evidence:
                        try:
                            from engines.strategy_memory import record_from_mutation_result
                            await record_from_mutation_result(
                                strategy_text=normalised.to_strategy_text(),
                                pair=normalised.pair,
                                timeframe=normalised.timeframe,
                                source=f"ingestion:{normalised.source}",
                                mutation_result=mut if isinstance(mut, dict) else {},
                                name=normalised.name,
                                type_=normalised.type,
                                indicators=list(normalised.indicators or []),
                            )
                        except Exception as e:
                            logger.debug("strategy_memory record (ingestion) failed: %s", e)
                        stats["total_evidential"] += 1
                    else:
                        stats["total_abandoned"] += 1
                        _reason = _phase30_status or "no_trades_or_pf"
                        stats["abandon_reasons"][_reason] = stats["abandon_reasons"].get(_reason, 0) + 1

                    stats["total_injected"] += 1
                    stats["by_source"][src]["injected"] += 1

                    # Feedback loop — attach best-variant metrics
                    best = (mut.get("best_variant") or {}) if isinstance(mut, dict) else {}
                    bt = best.get("backtest") or {}
                    pf = bt.get("profit_factor")
                    auto_save = mut.get("auto_save_result") or {} if isinstance(mut, dict) else {}
                    doc["injection"] = {
                        "mutation_run_id": mut.get("run_id") if isinstance(mut, dict) else None,
                        "mutation_status": mut.get("status") if isinstance(mut, dict) else None,
                        "best_mutation_type": best.get("mutation_type"),
                        "best_pf": pf,
                        "best_dd_pct": bt.get("max_drawdown_pct"),
                        "best_trades": bt.get("total_trades"),
                        "auto_save_status": auto_save.get("status"),
                        "auto_save_reason": auto_save.get("reason"),
                    }
                    if isinstance(pf, (int, float)):
                        if stats["best_pf_from_ingested"] is None or pf > stats["best_pf_from_ingested"]:
                            stats["best_pf_from_ingested"] = float(pf)
                            stats["best_pf_source"] = src
                            stats["best_pf_name"] = normalised.name

                per_strategy_docs.append(doc)

            # Persist strategies in a single batch (best-effort).
            if per_strategy_docs:
                try:
                    await db[INGESTED_STRATEGIES_COLL].insert_many(per_strategy_docs)
                except Exception as e:
                    logger.warning("ingested_strategies insert_many failed: %s", e)

            run_doc = {
                "run_id": run_id,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "status": "ok",
                "stats": stats,
                "config": {
                    "max_strategies": max_strategies,
                    "use_github": use_github,
                    "use_tradingview": use_tradingview,
                    "use_local_queue": use_local_queue,
                    "inject": inject,
                    "firm": firm,
                    "github_queries": github_queries,
                },
            }
            try:
                await db[INGESTION_RUNS_COLL].insert_one({**run_doc})
            except Exception as e:
                logger.warning("ingestion_runs insert failed: %s", e)

            STATE["last_run_id"] = run_id
            STATE["last_run_at"] = run_doc["finished_at"]
            STATE["last_run_status"] = "ok"
            STATE["last_run_stats"] = dict(stats)
            _schedule_next_refresh()
            return run_doc

        except Exception as e:
            logger.exception("ingestion run fatal: %s", e)
            run_doc = {
                "run_id": run_id,
                "started_at": started_at,
                "finished_at": _now_iso(),
                "status": "error",
                "error": str(e)[:240],
                "stats": stats,
            }
            STATE["last_run_id"] = run_id
            STATE["last_run_at"] = run_doc["finished_at"]
            STATE["last_run_status"] = "error"
            STATE["last_run_stats"] = dict(stats)
            try:
                await db[INGESTION_RUNS_COLL].insert_one({**run_doc})
            except Exception:
                pass
            return run_doc
        finally:
            STATE["currently_running"] = False
