"""
Phase 20 — Multi-cycle optimisation runner.

Drives N sequential discovery cycles. Each cycle:
    1. Picks the next (pair, timeframe) from a rotating scan list.
    2. Calls the EXISTING `auto_mutation_runner.run_single_cycle(...)`
       — which already does generate → mutate → match → save and logs
       to `mutation_stability_log`.
    3. Snapshots avg_pf / strategies_saved / evolution telemetry.

Between cycles, the evolution engine automatically picks up the new
stability-log rows and re-computes mutation-type weights — so cycle N+1
inherits everything cycle N learned. There is NO new learning logic
here; this module is a pure orchestrator.

Public API (consumed by `api/multi_cycle.py`):
    * start_multi_cycle(...)   — kicks off a background task; idempotent guard
    * get_status()             — live in-memory snapshot
    * request_stop()           — graceful stop at next cycle boundary
    * list_runs(limit)         — persisted run history
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.auto_mutation_runner import run_single_cycle
from engines.db import get_db

logger = logging.getLogger(__name__)

RUNS_COLL = "multi_cycle_runs"

# Default scan list — pair × timeframe combinations rotated across
# cycles. The dashboard "Run 5 Cycles" button hits these defaults; the
# API accepts custom lists for power users.
DEFAULT_SCAN: Tuple[Tuple[str, str], ...] = (
    ("EURUSD", "H1"),
    ("XAUUSD", "H1"),
    ("EURUSD", "H4"),
    ("XAUUSD", "H4"),
)
DEFAULT_CYCLES = 5
DEFAULT_BATCH_SIZE = 3
DEFAULT_TIMEOUT_PER_CYCLE = 420.0  # 7 min — same hard cap as run_single_cycle

_RUN_LOCK = asyncio.Lock()
_BG_TASK: Optional[asyncio.Task] = None

# Live in-memory snapshot polled by the dashboard. Single-writer (the
# background task), many-reader (status endpoint) — best-effort copies
# returned to callers so no concurrent-mutation issues.
STATE: Dict[str, Any] = {
    "status": "idle",        # idle | running | stopped | completed | error
    "run_id": None,
    "started_at": None,
    "finished_at": None,
    "config": None,
    "current_cycle": 0,
    "total_cycles": 0,
    "stop_requested": False,
    "last_error": None,
    "cycles": [],            # one summary dict per completed cycle
    "pf_trend": [],          # list[float|None] — best avg_pf per cycle
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot() -> Dict[str, Any]:
    return {
        "status": STATE["status"],
        "run_id": STATE["run_id"],
        "started_at": STATE["started_at"],
        "finished_at": STATE["finished_at"],
        "config": dict(STATE["config"] or {}) or None,
        "current_cycle": STATE["current_cycle"],
        "total_cycles": STATE["total_cycles"],
        "stop_requested": STATE["stop_requested"],
        "last_error": STATE["last_error"],
        "cycles": list(STATE["cycles"]),
        "pf_trend": list(STATE["pf_trend"]),
    }


def _reset_state(run_id: str, config: Dict[str, Any]) -> None:
    STATE["status"] = "running"
    STATE["run_id"] = run_id
    STATE["started_at"] = _now_iso()
    STATE["finished_at"] = None
    STATE["config"] = config
    STATE["current_cycle"] = 0
    STATE["total_cycles"] = config.get("cycles", DEFAULT_CYCLES)
    STATE["stop_requested"] = False
    STATE["last_error"] = None
    STATE["cycles"] = []
    STATE["pf_trend"] = []


def request_stop() -> bool:
    if STATE["status"] != "running":
        return False
    STATE["stop_requested"] = True
    return True


def get_status() -> Dict[str, Any]:
    return _snapshot()


# ─────────────────────────────────────────────────────────────────────
# Cycle execution — pure orchestration, no new logic.
# ─────────────────────────────────────────────────────────────────────

async def _run_one_cycle(
    cycle_index: int,
    scan_list: List[Tuple[str, str]],
    *,
    batch_size: int,
    quality_threshold: float,
    auto_save: bool,
    timeout_per_cycle: float,
    style: str,
    firm: str,
    research_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute ONE multi-cycle iteration: scans every (pair, tf) in
    `scan_list`, calling `run_single_cycle` for each. Aggregates
    cycle-level metrics so the UI can plot a trend."""
    pair_results: List[Dict[str, Any]] = []
    pfs: List[float] = []
    total_generated = 0
    total_saved = 0

    for (pair, tf) in scan_list:
        if STATE["stop_requested"]:
            break
        try:
            res = await run_single_cycle(
                batch_size=batch_size,
                pair=pair,
                timeframe=tf,
                style=style,
                firm=firm,
                quality_filter=True,
                quality_threshold=quality_threshold,
                optimizer="random",
                auto_save=auto_save,
                timeout_seconds=timeout_per_cycle,
                research_run_id=research_run_id,
            )
        except Exception as e:                  # noqa: BLE001 — defensive
            logger.exception("[multi_cycle] run_single_cycle failed")
            res = {
                "status": "error", "reason": str(e)[:240],
                "pair": pair, "timeframe": tf,
                "strategies_generated": 0, "strategies_saved": 0,
                "avg_pf": None, "avg_dd": None,
            }
        pair_results.append({
            "pair": res.get("pair", pair),
            "timeframe": res.get("timeframe", tf),
            "status": res.get("status"),
            "reason": res.get("reason"),
            "strategies_generated": int(res.get("strategies_generated") or 0),
            "strategies_saved": int(res.get("strategies_saved") or 0),
            "avg_pf": res.get("avg_pf"),
            "avg_dd": res.get("avg_dd"),
            "duration_sec": res.get("duration_sec"),
            "evolution_summary": res.get("evolution_summary"),
        })
        total_generated += int(res.get("strategies_generated") or 0)
        total_saved += int(res.get("strategies_saved") or 0)
        pf = res.get("avg_pf")
        if isinstance(pf, (int, float)):
            pfs.append(float(pf))

    best_pf = max(pfs) if pfs else None
    avg_pf = (sum(pfs) / len(pfs)) if pfs else None
    return {
        "cycle_index": cycle_index,
        "started_at_cycle": pair_results[0].get("started_at") if pair_results else None,
        "finished_at_cycle": _now_iso(),
        "scan": pair_results,
        "best_pf": best_pf,
        "avg_pf": round(avg_pf, 3) if avg_pf is not None else None,
        "strategies_generated": total_generated,
        "strategies_saved": total_saved,
    }


async def _drive(
    cycles: int,
    scan_list: List[Tuple[str, str]],
    *,
    batch_size: int,
    quality_threshold: float,
    auto_save: bool,
    timeout_per_cycle: float,
    style: str,
    firm: str,
    research_run_id: Optional[str] = None,
) -> None:
    """The actual multi-cycle loop, run as an asyncio Task. Persists a
    summary to `multi_cycle_runs` on completion / stop / error."""
    db = get_db()
    try:
        for c in range(1, cycles + 1):
            if STATE["stop_requested"]:
                break
            STATE["current_cycle"] = c
            cycle_doc = await _run_one_cycle(
                c, scan_list,
                batch_size=batch_size,
                quality_threshold=quality_threshold,
                auto_save=auto_save,
                timeout_per_cycle=timeout_per_cycle,
                style=style,
                firm=firm,
                research_run_id=research_run_id,
            )
            STATE["cycles"].append(cycle_doc)
            STATE["pf_trend"].append(cycle_doc.get("best_pf"))
            # Phase 2 scaffolding — cadence stamp (best-effort, dormant-
            # default). Marks every scanned cell as "ran" so the
            # cadence gate can hold the operator-decreed minimum gap
            # before re-scanning. No-op when ENABLE_CADENCE_SCHEDULER
            # is off (which is the default).
            try:
                from engines import cadence_scheduler as _cad
                if _cad.is_enabled():
                    for entry in (cycle_doc.get("scan") or []):
                        await _cad.mark_ran(
                            entry.get("pair") or "",
                            entry.get("timeframe") or "",
                            style or "",
                        )
            except Exception:                                # pragma: no cover
                pass
            logger.info(
                "[multi_cycle] cycle %d/%d done — best_pf=%s avg_pf=%s saved=%d",
                c, cycles, cycle_doc.get("best_pf"),
                cycle_doc.get("avg_pf"), cycle_doc.get("strategies_saved"),
            )

        STATE["finished_at"] = _now_iso()
        if STATE["stop_requested"]:
            STATE["status"] = "stopped"
        else:
            STATE["status"] = "completed"
    except Exception as e:                      # pragma: no cover — defensive
        logger.exception("[multi_cycle] driver crashed")
        STATE["status"] = "error"
        STATE["last_error"] = f"{type(e).__name__}: {str(e)[:240]}"
        STATE["finished_at"] = _now_iso()
    finally:
        # ── Phase 2 P2.7 — Release advisory lock (best-effort) ───────
        try:
            from engines import advisory_lock as _adv
            await _adv.release("multi_cycle_run")
        except Exception as _e:                              # pragma: no cover
            logger.debug("[multi_cycle] advisory lock release failed: %s", _e)

    # Persist the run summary (best-effort).
    try:
        await db[RUNS_COLL].insert_one({
            "run_id":           STATE["run_id"],
            "research_run_id":  research_run_id,
            "status":           STATE["status"],
            "started_at":       STATE["started_at"],
            "finished_at":      STATE["finished_at"],
            "config":           STATE["config"],
            "cycles":           STATE["cycles"],
            "pf_trend":         STATE["pf_trend"],
            "last_error":       STATE["last_error"],
        })
    except Exception as e:                      # pragma: no cover
        logger.warning("[multi_cycle] persist failed: %s", e)

    # G1 — close out lineage (only if WE created it; orchestrator-owned
    # rrids are closed by the orchestrator tick instead).
    if research_run_id:
        try:
            from engines import research_lineage
            await research_lineage.attach_child(
                research_run_id, "multi_cycle_run", STATE["run_id"],
                extra={
                    "status": STATE["status"],
                    "pf_trend": STATE["pf_trend"],
                    "config": STATE["config"],
                },
            )
        except Exception as e:                              # pragma: no cover
            logger.debug("[lineage] attach multi_cycle_run failed: %s", e)


async def start_multi_cycle(
    *,
    cycles: int = DEFAULT_CYCLES,
    scan: Optional[List[Tuple[str, str]]] = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    quality_threshold: float = 35.0,
    auto_save: bool = True,
    timeout_per_cycle: float = DEFAULT_TIMEOUT_PER_CYCLE,
    style: str = "",
    firm: str = "ftmo",
    research_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Kick off a multi-cycle run as a background task. Returns the
    initial snapshot. Returns the snapshot of the ALREADY-running run
    if one is active (no error — UI reuses the same status endpoint).
    """
    global _BG_TASK
    if _RUN_LOCK.locked() or STATE["status"] == "running":
        return _snapshot()

    # ── Phase 2 P2.7 — Cross-worker advisory lock (additive) ────────
    # When uvicorn runs with --workers >= 2, the in-process _RUN_LOCK
    # above does not coordinate across worker processes. The
    # advisory_lock collection provides cross-process single-flight.
    # In-process lock is preserved as the fast-path check.
    from engines import advisory_lock as _adv
    try:
        await _adv.try_acquire(
            "multi_cycle_run",
            ttl_seconds=int(timeout_per_cycle * cycles + 600),
            metadata={"worker_pid": os.getpid(), "cycles": int(cycles)},
        )
    except _adv.LockHeldError as _e:
        logger.info("[multi_cycle] advisory lock held by another worker: %s", _e.holder)
        # Mirror in-process-lock-held behaviour: return current snapshot
        return _snapshot()

    cycles = max(1, min(int(cycles), 50))
    batch_size = max(1, min(int(batch_size), 20))
    timeout_per_cycle = max(30.0, min(float(timeout_per_cycle), 900.0))
    # ── Phase 30.2 — Universe Governance filter (additive · reversible)
    # When the caller omits `scan`, intersect DEFAULT_SCAN with the
    # operator-decreed allowed universe. Operator-explicit `scan=[...]`
    # is honoured verbatim (bypass) — manual flexibility preserved.
    universe_filtered = False
    universe_skipped: list = []
    if not scan:
        try:
            from engines import governance_universe as _gu
            universe = await _gu.get_universe()
            filtered = _gu.intersect_scan(universe, DEFAULT_SCAN)
            if filtered:
                scan_list = filtered
                universe_filtered = True
                universe_skipped = [
                    list(c) for c in DEFAULT_SCAN
                    if (c[0], c[1]) not in {(p, tf) for p, tf in filtered}
                ]
            else:
                # Empty intersection — fall back to DEFAULT_SCAN with
                # an audit warning. Never silent black-hole.
                logger.warning(
                    "[multi_cycle] universe intersection empty for DEFAULT_SCAN; "
                    "falling back to ungoverned defaults"
                )
                scan_list = list(DEFAULT_SCAN)
        except Exception as _e:                             # pragma: no cover
            logger.debug("[multi_cycle] universe filter failed: %s", _e)
            scan_list = list(DEFAULT_SCAN)
    else:
        scan_list = [(p.upper(), tf.upper()) for (p, tf) in scan if p and tf]
        if not scan_list:
            scan_list = list(DEFAULT_SCAN)

    # ── Phase 2 scaffolding — cadence gate (additive, dormant-default,
    # fail-open). When ENABLE_CADENCE_SCHEDULER=true the gate consults
    # the cadence_state collection per cell; otherwise should_run_cell
    # is hard-coded True (no behaviour change). Cells that fail the
    # gate are dropped from the scan list with a structured advisory in
    # the run config so operators can see WHY a cell was skipped.
    cadence_dropped: list = []
    try:
        from engines import cadence_scheduler as _cad
        if _cad.is_enabled():
            kept: list = []
            for (p, tf) in scan_list:
                if await _cad.should_run_cell(p, tf, style or ""):
                    kept.append((p, tf))
                else:
                    cadence_dropped.append([p, tf])
            if kept:
                scan_list = kept
            # If the cadence gate filters EVERY cell we keep the
            # original list and surface the fact — anti-blackhole
            # discipline (mirrors universe-intersection behaviour).
    except Exception as _e:                                  # pragma: no cover
        logger.debug("[multi_cycle] cadence gate failed: %s", _e)

    run_id = uuid.uuid4().hex[:12]
    config = {
        "cycles": cycles,
        "scan": [list(c) for c in scan_list],
        "batch_size": batch_size,
        "quality_threshold": quality_threshold,
        "auto_save": auto_save,
        "timeout_per_cycle": timeout_per_cycle,
        "style": style,
        "firm": firm,
        "research_run_id": research_run_id,
        "universe_filtered":  universe_filtered,
        "universe_skipped":   universe_skipped,
        "cadence_dropped":    cadence_dropped,
    }
    _reset_state(run_id, config)

    # G1 — if no upstream lineage handle was supplied (e.g. manual
    # /api/multi-cycle/start), open one now so this run is auditable.
    if not research_run_id:
        try:
            from engines import research_lineage
            research_run_id = await research_lineage.new_research_run(
                trigger_type="manual_api",
                trigger_reason="start_multi_cycle",
                config=dict(config),
            )
            STATE["config"]["research_run_id"] = research_run_id
        except Exception as e:                              # pragma: no cover
            logger.debug("[lineage] start_multi_cycle: new_research_run failed: %s", e)

    async def _runner():
        async with _RUN_LOCK:
            await _drive(
                cycles, scan_list,
                batch_size=batch_size,
                quality_threshold=quality_threshold,
                auto_save=auto_save,
                timeout_per_cycle=timeout_per_cycle,
                style=style,
                firm=firm,
                research_run_id=research_run_id,
            )
            # Mark the lineage finished AFTER the loop — every child
            # cycle has already attached itself.
            if research_run_id:
                try:
                    from engines import research_lineage
                    await research_lineage.mark_finished(
                        research_run_id,
                        status=STATE["status"],
                        summary={
                            "cycles_completed": len(STATE["cycles"]),
                            "pf_trend": STATE["pf_trend"],
                        },
                        error=STATE["last_error"],
                    )
                except Exception as e:                          # pragma: no cover
                    logger.debug("[lineage] mark_finished failed: %s", e)

    _BG_TASK = asyncio.create_task(_runner())
    # Give the task a tick so the snapshot reflects "running" before
    # we hand it to the caller.
    await asyncio.sleep(0.05)
    return _snapshot()


# ─────────────────────────────────────────────────────────────────────
# History (read-only)
# ─────────────────────────────────────────────────────────────────────

async def list_runs(limit: int = 20) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 200))
    cur = db[RUNS_COLL].find({}, {"_id": 0}).sort("started_at", -1).limit(limit)
    return [d async for d in cur]


# ─────────────────────────────────────────────────────────────────────
# Best-of-run lookup — read-only, queries the existing strategy_library.
# ─────────────────────────────────────────────────────────────────────

async def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single persisted run document by run_id."""
    if not run_id:
        return None
    db = get_db()
    return await db[RUNS_COLL].find_one({"run_id": run_id}, {"_id": 0})


async def best_strategy_for_run(run_id: str) -> Dict[str, Any]:
    """Find the highest-scoring strategy_library entry saved during the
    window of `run_id` (started_at .. finished_at | now). Pure read.

    Returns a dict shaped for the dashboard:
      {
        "run_id": str,
        "window": {"from": iso, "to": iso | None},
        "best": {strategy fields...} | None,
        "candidates_considered": int,
      }
    """
    run = await get_run(run_id)
    if not run:
        return {
            "run_id": run_id, "window": None, "best": None,
            "candidates_considered": 0,
            "error": "run_id not found",
        }

    started = run.get("started_at")
    finished = run.get("finished_at")
    if not started:
        return {
            "run_id": run_id, "window": None, "best": None,
            "candidates_considered": 0,
            "error": "run has no started_at timestamp",
        }

    db = get_db()
    q: Dict[str, Any] = {"created_at": {"$gte": started}}
    if finished:
        q["created_at"]["$lte"] = finished

    # Project only what the UI needs — avoid pulling huge nested objects.
    projection = {
        "_id": 0,
        "fingerprint": 1, "pair": 1, "timeframe": 1, "style": 1,
        "score": 1, "verdict": 1, "prop_status": 1,
        "strategy_text": 1, "parameters": 1,
        "pass_probability": 1, "stability_score": 1,
        "indicators": 1, "strategy_type": 1,
        "created_at": 1, "source": 1,
    }
    cursor = db["strategy_library"].find(q, projection)\
        .sort("score", -1).limit(20)
    candidates: List[Dict[str, Any]] = [d async for d in cursor]

    return {
        "run_id": run_id,
        "window": {"from": started, "to": finished},
        "best": candidates[0] if candidates else None,
        "candidates_considered": len(candidates),
    }
