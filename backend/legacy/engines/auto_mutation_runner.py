"""
Auto Mutation Runner (semi-automatic).

Controlled loop that orchestrates EXISTING generation + mutation engines
to build up the stability log quickly — the prerequisite for Evolution
(Phase 15) to activate.

What it does per cycle:
  1. Generate `strategies_per_cycle` strategies via
     `engines.strategy_engine.generate_strategy_text` (which already
     enforces structural diversity).
  2. For each generated strategy run
     `engines.mutation_engine.run_mutation_pipeline(
         base, max_variants=10, auto_save=True, prices=<real BID>)`.
     The mutation engine and its auto-save gate are NOT modified —
     every variant still goes through the existing `_is_eligible`
     gate and logs to `mutation_stability_log` as designed.
  3. Record the cycle (best_pf, mutation_type distribution, trades,
     reject counts) to `auto_mutation_cycles`.
  4. Safety kill-switch: three consecutive cycles where every single
     strategy's best mutation has PF < 0.9 → abort.

This module only READS from the existing engines — it does not touch
`mutation_engine.py`, `evolution_engine.py`, scoring, or
`strategy_library.save_strategy`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines.mutation_engine import run_mutation_pipeline
from engines.strategy_engine import generate_strategy_text

logger = logging.getLogger(__name__)

CYCLES_COLL = "auto_mutation_cycles"
RUNS_COLL = "auto_mutation_runs"

# Safety constants
BAD_PF_THRESHOLD = 0.9
CONSECUTIVE_BAD_CYCLES_LIMIT = 3

# Single-run lock — only one auto-mutation run active at a time.
_RUN_LOCK = asyncio.Lock()

# In-memory live state (polled by GET /status). The lock on start()
# ensures only one writer; reads are best-effort snapshots.
JOB_STATE: Dict[str, Any] = {
    "status": "idle",          # idle | running | stopped | completed | error
    "job_id": None,
    "started_at": None,
    "finished_at": None,
    "config": None,
    "progress": {
        "current_cycle": 0,
        "total_cycles": 0,
        "strategies_completed_this_cycle": 0,
        "strategies_per_cycle": 0,
    },
    "stats": {
        "best_pf_overall": None,
        "best_mutation_type_overall": None,
        "cycles_completed": 0,
        "strategies_attempted": 0,
        "mutation_runs_attempted": 0,
        "auto_save_saved": 0,
        "auto_save_rejected": 0,
        "auto_save_skipped_or_error": 0,
        "consecutive_bad_cycles": 0,
    },
    "cycle_history": [],       # last 50 cycle summaries (ring)
    "stop_requested": False,
    "last_error": None,
}
_MAX_CYCLE_HISTORY = 50


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot() -> Dict[str, Any]:
    """Deep-enough copy of JOB_STATE safe for returning over JSON."""
    return {
        "status": JOB_STATE["status"],
        "job_id": JOB_STATE["job_id"],
        "started_at": JOB_STATE["started_at"],
        "finished_at": JOB_STATE["finished_at"],
        "config": dict(JOB_STATE["config"] or {}) or None,
        "progress": dict(JOB_STATE["progress"]),
        "stats": dict(JOB_STATE["stats"]),
        "cycle_history": list(JOB_STATE["cycle_history"]),
        "stop_requested": JOB_STATE["stop_requested"],
        "last_error": JOB_STATE["last_error"],
    }


def _reset_state(job_id: str, config: Dict[str, Any]) -> None:
    JOB_STATE["status"] = "running"
    JOB_STATE["job_id"] = job_id
    JOB_STATE["started_at"] = _now_iso()
    JOB_STATE["finished_at"] = None
    JOB_STATE["config"] = config
    JOB_STATE["progress"] = {
        "current_cycle": 0,
        "total_cycles": config.get("iterations", 0),
        "strategies_completed_this_cycle": 0,
        "strategies_per_cycle": config.get("strategies_per_cycle", 0),
    }
    JOB_STATE["stats"] = {
        "best_pf_overall": None,
        "best_mutation_type_overall": None,
        "cycles_completed": 0,
        "strategies_attempted": 0,
        "mutation_runs_attempted": 0,
        "auto_save_saved": 0,
        "auto_save_rejected": 0,
        "auto_save_skipped_or_error": 0,
        "consecutive_bad_cycles": 0,
    }
    JOB_STATE["cycle_history"] = []
    JOB_STATE["stop_requested"] = False
    JOB_STATE["last_error"] = None


def request_stop() -> bool:
    """Operator-level stop request. Returns True if a run was marked for
    stop, False if nothing was running."""
    if JOB_STATE["status"] != "running":
        return False
    JOB_STATE["stop_requested"] = True
    return True


async def _check_data_available(pair: str, timeframe: str) -> int:
    """Return the BID-candle count for (pair, tf), with auto-recovery.

    Auto mutation must never break due to a missing dataset — this
    helper calls `data_access.load_with_recovery` with
    `auto_recover=True` so an inline Dukascopy download is attempted
    before declaring the combo unavailable.
    Returns the post-recovery candle count (0 when recovery fails).
    """
    from engines.data_access import load_with_recovery
    res = await load_with_recovery(
        pair.upper(), timeframe.upper(), auto_recover=True,
    )
    if res["status"] in ("ok", "recovered"):
        return int(res["count"])
    logger.warning(
        "[auto_mutation] data unavailable for %s/%s — %s",
        pair, timeframe, res.get("message"),
    )
    return 0


async def _run_one_strategy(
    pair: str, timeframe: str, style: str, firm: str, auto_save: bool,
    sim_config: Optional[Dict[str, Any]] = None,
    research_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate ONE strategy and push it through the existing mutation
    pipeline. Returns a compact per-strategy summary."""
    t_gen_start = datetime.now(timezone.utc)
    strategy_text = await generate_strategy_text(pair, timeframe, style)
    base = {
        "strategy_text": strategy_text,
        "pair": pair,
        "timeframe": timeframe,
        "style": style or "",
    }
    mut = await run_mutation_pipeline(
        base,
        max_variants=10,
        prices=None,           # real BID path
        triggered_by="auto_mutation_runner",
        auto_save=auto_save,
        firm=firm,
        sim_config=sim_config,
    )

    # Additive hook: record run into strategy_performance_history so the
    # Explorer layer can aggregate it. Never raises out to the runner.
    try:
        from engines.strategy_memory import record_from_mutation_result
        await record_from_mutation_result(
            strategy_text=strategy_text,
            pair=pair,
            timeframe=timeframe,
            source="mutation_runner",
            mutation_result=mut if isinstance(mut, dict) else {},
            type_=style or None,
            research_run_id=research_run_id,
        )
    except Exception as e:
        logger.debug("strategy_memory record (runner) failed: %s", e)

    best = (mut.get("best_variant") or {}) if isinstance(mut, dict) else {}
    best_bt = best.get("backtest") or {}
    auto_save_result = mut.get("auto_save_result") or {} if isinstance(mut, dict) else {}

    return {
        "generated_at": t_gen_start.isoformat(),
        "strategy_preview": (strategy_text or "").splitlines()[0][:200],
        "mutation_run_id": mut.get("run_id") if isinstance(mut, dict) else None,
        "mutation_status": mut.get("status") if isinstance(mut, dict) else None,
        "variants_generated": (mut.get("totals") or {}).get("variants_generated"),
        "variants_errors": (mut.get("totals") or {}).get("errors"),
        "best_mutation_type": best.get("mutation_type"),
        "best_pf": best_bt.get("profit_factor"),
        "best_dd_pct": best_bt.get("max_drawdown_pct"),
        "best_trades": best_bt.get("total_trades"),
        "auto_save_status": auto_save_result.get("status"),
        "auto_save_reason": auto_save_result.get("reason"),
        # Phase 15/16 — evolution telemetry (which mutation types the
        # weighted selector picked this cycle, and which regime the
        # weights came from). Propagates up to `run_single_cycle` so
        # the scheduler response exposes WHY each variant was tried.
        "evolution": (mut.get("evolution") if isinstance(mut, dict) else None),
    }


def _roll_overall_best(
    stats: Dict[str, Any], pf: Optional[float], mutation_type: Optional[str],
) -> None:
    if pf is None:
        return
    try:
        pf_f = float(pf)
    except (TypeError, ValueError):
        return
    cur = stats.get("best_pf_overall")
    if cur is None or pf_f > cur:
        stats["best_pf_overall"] = pf_f
        stats["best_mutation_type_overall"] = mutation_type


async def run_auto_mutation(
    *,
    iterations: int = 20,
    strategies_per_cycle: int = 5,
    pair: str = "EURUSD",
    timeframe: str = "H1",
    style: str = "",
    delay_between_cycles: float = 0.0,
    firm: str = "ftmo",
    auto_save: bool = True,
    research_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Main entry. Acquires the run-lock; returns a summary when done.

    NOTE: blocks until the loop completes. Callers that want background
    execution must schedule this with `asyncio.create_task`.
    """
    iterations = max(1, min(int(iterations), 200))
    strategies_per_cycle = max(1, min(int(strategies_per_cycle), 20))
    delay_between_cycles = max(0.0, min(float(delay_between_cycles or 0.0), 300.0))

    if _RUN_LOCK.locked():
        raise RuntimeError("already_running")

    # ── Phase 2 P2.7 — Cross-worker advisory lock (additive) ────────
    # The in-process _RUN_LOCK does not coordinate across uvicorn worker
    # processes once --workers >= 2. The advisory_lock collection gives
    # cross-process single-flight. In-process lock is preserved as the
    # fast-path check (kept above for raising the same RuntimeError that
    # existing callers — incl. /api/auto-mutation/start — already
    # handle).
    from engines import advisory_lock as _adv
    try:
        await _adv.try_acquire(
            "auto_mutation_run",
            # Generous TTL — long jobs can take minutes per iter; the
            # TTL is only a crash-recovery safety-net, not the primary
            # release path (which is the explicit release call below).
            ttl_seconds=int(max(iterations, 1) * 600 + 600),
            metadata={
                "worker_pid": os.getpid(),
                "kind": "long_run",
                "iterations": int(iterations),
            },
        )
    except _adv.LockHeldError as _e:
        logger.info(
            "[auto_mutation] advisory lock held by another worker: %s",
            _e.holder,
        )
        raise RuntimeError("already_running") from _e

    async with _RUN_LOCK:
        job_id = uuid.uuid4().hex[:12]
        config = {
            "iterations": iterations,
            "strategies_per_cycle": strategies_per_cycle,
            "pair": pair.upper(),
            "timeframe": timeframe.upper(),
            "style": style or "",
            "delay_between_cycles": delay_between_cycles,
            "firm": firm,
            "auto_save": bool(auto_save),
            "research_run_id": research_run_id,
        }
        _reset_state(job_id, config)
        db = get_db()

        # G1 — long-running job opens its own research_run if the caller
        # didn't supply one (e.g. /api/auto-mutation/start manual hit).
        if not research_run_id:
            try:
                from engines import research_lineage
                research_run_id = await research_lineage.new_research_run(
                    trigger_type="manual_api",
                    trigger_reason="run_auto_mutation",
                    config=dict(config),
                )
                config["research_run_id"] = research_run_id
                JOB_STATE["config"] = dict(config)
            except Exception as e:                          # pragma: no cover
                logger.debug("[lineage] run_auto_mutation new_research_run failed: %s", e)

        # Preflight — refuse to burn LLM budget when there's no price data.
        data_points = await _check_data_available(config["pair"], config["timeframe"])
        if data_points < 60:
            JOB_STATE["status"] = "error"
            JOB_STATE["finished_at"] = _now_iso()
            JOB_STATE["last_error"] = (
                f"No real BID candles for {config['pair']}/{config['timeframe']} "
                f"(found {data_points}; need >= 60). Download via Market Data tab first."
            )
            return _snapshot()

        try:
            for cycle_idx in range(1, iterations + 1):
                if JOB_STATE["stop_requested"]:
                    break

                JOB_STATE["progress"]["current_cycle"] = cycle_idx
                JOB_STATE["progress"]["strategies_completed_this_cycle"] = 0

                cycle_started_at = _now_iso()
                per_strategy: List[Dict[str, Any]] = []
                cycle_mutation_types: Dict[str, int] = {}
                cycle_saved = 0
                cycle_rejected = 0
                cycle_other = 0
                cycle_pfs: List[float] = []

                for s_idx in range(strategies_per_cycle):
                    if JOB_STATE["stop_requested"]:
                        break
                    try:
                        summary = await _run_one_strategy(
                            pair=config["pair"],
                            timeframe=config["timeframe"],
                            style=config["style"],
                            firm=config["firm"],
                            auto_save=config["auto_save"],
                            research_run_id=research_run_id,
                        )
                    except Exception as e:
                        logger.exception("auto_mutation: strategy failure")
                        summary = {
                            "error": str(e)[:240],
                            "mutation_status": "error",
                        }
                    per_strategy.append(summary)
                    JOB_STATE["stats"]["strategies_attempted"] += 1

                    # Roll stats
                    if summary.get("mutation_status") == "ok":
                        JOB_STATE["stats"]["mutation_runs_attempted"] += 1
                    pf = summary.get("best_pf")
                    if isinstance(pf, (int, float)):
                        cycle_pfs.append(float(pf))
                        _roll_overall_best(
                            JOB_STATE["stats"], float(pf),
                            summary.get("best_mutation_type"),
                        )
                    mt = summary.get("best_mutation_type")
                    if mt:
                        cycle_mutation_types[mt] = cycle_mutation_types.get(mt, 0) + 1
                    ass = summary.get("auto_save_status")
                    if ass == "saved":
                        cycle_saved += 1
                        JOB_STATE["stats"]["auto_save_saved"] += 1
                    elif ass == "rejected":
                        cycle_rejected += 1
                        JOB_STATE["stats"]["auto_save_rejected"] += 1
                    elif ass in ("skipped", "error", "duplicate"):
                        cycle_other += 1
                        JOB_STATE["stats"]["auto_save_skipped_or_error"] += 1

                    JOB_STATE["progress"]["strategies_completed_this_cycle"] = s_idx + 1

                # Compose cycle summary
                best_pf_cycle = max(cycle_pfs) if cycle_pfs else None
                all_below = bool(cycle_pfs) and all(
                    pf < BAD_PF_THRESHOLD for pf in cycle_pfs
                )
                if all_below:
                    JOB_STATE["stats"]["consecutive_bad_cycles"] += 1
                else:
                    JOB_STATE["stats"]["consecutive_bad_cycles"] = 0

                total_trades_cycle = sum(
                    int(s.get("best_trades") or 0) for s in per_strategy
                )

                cycle_doc = {
                    "job_id": job_id,
                    "research_run_id": research_run_id,
                    "cycle_index": cycle_idx,
                    "started_at": cycle_started_at,
                    "finished_at": _now_iso(),
                    "pair": config["pair"],
                    "timeframe": config["timeframe"],
                    "strategies": per_strategy,
                    "best_pf_cycle": best_pf_cycle,
                    "total_trades_cycle": total_trades_cycle,
                    "mutation_types_seen": cycle_mutation_types,
                    "counts": {
                        "strategies": len(per_strategy),
                        "auto_save_saved": cycle_saved,
                        "auto_save_rejected": cycle_rejected,
                        "auto_save_other": cycle_other,
                    },
                    "all_below_threshold": all_below,
                    "consecutive_bad_cycles_after": JOB_STATE["stats"]["consecutive_bad_cycles"],
                }
                # Persist (best-effort)
                try:
                    await db[CYCLES_COLL].insert_one({**cycle_doc})
                except Exception as e:
                    logger.warning("auto_mutation: cycle persist failed: %s", e)

                # Strip heavy per-strategy list from live state; keep compact
                compact = {
                    "cycle_index": cycle_idx,
                    "finished_at": cycle_doc["finished_at"],
                    "best_pf_cycle": best_pf_cycle,
                    "total_trades_cycle": total_trades_cycle,
                    "mutation_types_seen": cycle_mutation_types,
                    "counts": cycle_doc["counts"],
                    "all_below_threshold": all_below,
                    "consecutive_bad_cycles_after":
                        JOB_STATE["stats"]["consecutive_bad_cycles"],
                }
                JOB_STATE["cycle_history"].append(compact)
                if len(JOB_STATE["cycle_history"]) > _MAX_CYCLE_HISTORY:
                    JOB_STATE["cycle_history"] = JOB_STATE["cycle_history"][-_MAX_CYCLE_HISTORY:]
                JOB_STATE["stats"]["cycles_completed"] += 1

                # Safety kill-switch
                if JOB_STATE["stats"]["consecutive_bad_cycles"] >= CONSECUTIVE_BAD_CYCLES_LIMIT:
                    logger.info(
                        "auto_mutation: safety stop — %d consecutive cycles "
                        "with all PF < %s", CONSECUTIVE_BAD_CYCLES_LIMIT,
                        BAD_PF_THRESHOLD,
                    )
                    JOB_STATE["last_error"] = (
                        f"Safety stop: {CONSECUTIVE_BAD_CYCLES_LIMIT} consecutive "
                        f"cycles with every strategy's best PF < {BAD_PF_THRESHOLD}."
                    )
                    break

                if delay_between_cycles > 0 and cycle_idx < iterations:
                    try:
                        await asyncio.sleep(delay_between_cycles)
                    except asyncio.CancelledError:
                        break

            # Finalize
            JOB_STATE["finished_at"] = _now_iso()
            if JOB_STATE["stop_requested"]:
                JOB_STATE["status"] = "stopped"
            elif JOB_STATE["last_error"]:
                # Safety-stop left an explanatory message but was a normal
                # termination — tag status as completed-with-safety-stop.
                JOB_STATE["status"] = "stopped"
            else:
                JOB_STATE["status"] = "completed"

            # Persist a run-level summary for auditability
            run_doc = {
                "job_id": job_id,
                "research_run_id": research_run_id,
                "started_at": JOB_STATE["started_at"],
                "finished_at": JOB_STATE["finished_at"],
                "status": JOB_STATE["status"],
                "config": config,
                "stats": dict(JOB_STATE["stats"]),
                "last_error": JOB_STATE["last_error"],
            }
            try:
                await db[RUNS_COLL].insert_one({**run_doc})
            except Exception as e:
                logger.warning("auto_mutation: run persist failed: %s", e)

            # G1 — close lineage when this run owns the rrid (always
            # safe: mark_finished is idempotent enough for our use)
            if research_run_id:
                try:
                    from engines import research_lineage
                    await research_lineage.mark_finished(
                        research_run_id,
                        status=JOB_STATE["status"],
                        summary={
                            "cycles_completed": JOB_STATE["stats"]["cycles_completed"],
                            "best_pf": JOB_STATE["stats"].get("best_pf_overall"),
                        },
                        error=JOB_STATE["last_error"],
                    )
                except Exception as e:                          # pragma: no cover
                    logger.debug("[lineage] run_auto_mutation mark_finished failed: %s", e)

            # ── Phase 2 P2.7 — Release advisory lock (normal exit) ───
            try:
                await _adv.release("auto_mutation_run")
            except Exception as _e:                              # pragma: no cover
                logger.debug("[auto_mutation] advisory lock release failed: %s", _e)

            return _snapshot()
        except Exception as e:
            logger.exception("auto_mutation: fatal error")
            JOB_STATE["status"] = "error"
            JOB_STATE["finished_at"] = _now_iso()
            JOB_STATE["last_error"] = f"{type(e).__name__}: {str(e)[:240]}"
            # ── Phase 2 P2.7 — Release advisory lock (fatal exit) ────
            try:
                await _adv.release("auto_mutation_run")
            except Exception as _e:                              # pragma: no cover
                logger.debug("[auto_mutation] advisory lock release failed: %s", _e)
            return _snapshot()


# ── Read-only helpers for API ────────────────────────────────────────

async def list_cycles(
    *, job_id: Optional[str] = None, limit: int = 50,
) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 200))
    q: Dict[str, Any] = {}
    if job_id:
        q["job_id"] = job_id
    cur = db[CYCLES_COLL].find(q, {"_id": 0}).sort([("job_id", -1), ("cycle_index", -1)]).limit(limit)
    return [d async for d in cur]


def get_live_status() -> Dict[str, Any]:
    return _snapshot()


# ═════════════════════════════════════════════════════════════════════
# Scheduler-friendly single-cycle entry point
# (POST /api/auto/run-cycle — Phase 3 "balanced mode")
# ═════════════════════════════════════════════════════════════════════

RUN_CYCLES_COLL = "auto_run_cycles"
_DEFAULT_CYCLE_TIMEOUT_SEC = 420.0   # 7 min hard cap
_CYCLE_PAIR_ROTATION = ["EURUSD", "XAUUSD"]


async def run_single_cycle(
    *,
    batch_size: int = 5,
    pair: Optional[str] = None,
    timeframe: str = "H1",
    style: str = "",
    firm: str = "ftmo",
    quality_filter: bool = True,
    quality_threshold: float = 35.0,
    optimizer: str = "random",
    auto_save: bool = True,
    timeout_seconds: float = _DEFAULT_CYCLE_TIMEOUT_SEC,
    research_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute ONE discovery cycle and return a structured summary.

    Designed for external schedulers (cron, GitHub Actions, platform
    cron workers). NO infinite loops. The whole cycle is wrapped in
    `asyncio.wait_for(..., timeout_seconds)` so it can never block
    indefinitely.

    Behaviour:
      • If an auto-mutation run is already active (`_RUN_LOCK.locked()`),
        returns `{"status": "skipped", "reason": "run_already_active"}`
        WITHOUT waiting — the scheduler can try again next tick.
      • If `pair` is None, alternates EURUSD ↔ XAUUSD based on the
        count of prior `auto_run_cycles` rows (task 7).
      • `quality_filter` + `quality_threshold` are passed through the
        entire evaluation path via `sim_config` — filtering happens
        INSIDE `run_backtest_logic`, not as a post-API filter.
      • `optimizer` is accepted, persisted in the run log, and
        currently NOT used to change mutation behaviour (Phase 3
        scope — can be upgraded without API change).

    Returns:
        {
          "status": "completed" | "skipped" | "error" | "timeout",
          "run_id": str, "started_at": iso, "finished_at": iso,
          "duration_sec": float,
          "config": {...},
          "pair": str, "timeframe": str,
          "strategies_generated": int,
          "strategies_saved": int,
          "avg_pf": float | None,
          "avg_dd": float | None,
          "per_strategy": [...],
          "quality_filter_applied": bool,
          "reason": str | None,   (when skipped / error / timeout)
        }
    """
    if _RUN_LOCK.locked():
        logger.info("[auto/run-cycle] skipped — long run_auto_mutation is active")
        return {
            "status": "skipped",
            "reason": "run_already_active",
            "run_id": None,
            "research_run_id": research_run_id,
        }

    # ── Phase 2 P2.7 — Cross-worker advisory lock (additive) ────────
    # Mirror multi_cycle_runner pattern for single-cycle scheduler hits.
    # In-process fast-path above stays first (lowest latency). If THIS
    # worker is clear but another worker holds the advisory key, treat
    # the same as the in-process skip — the scheduler retries next tick.
    from engines import advisory_lock as _adv
    try:
        await _adv.try_acquire(
            "auto_mutation_run",
            ttl_seconds=int(float(timeout_seconds) + 120.0),
            metadata={
                "worker_pid": os.getpid(),
                "kind": "single_cycle",
                "pair": (pair or "auto"),
                "timeframe": timeframe,
            },
        )
    except _adv.LockHeldError as _e:
        logger.info(
            "[auto/run-cycle] skipped — advisory lock held by another worker: %s",
            _e.holder,
        )
        return {
            "status": "skipped",
            "reason": "run_already_active_other_worker",
            "run_id": None,
            "research_run_id": research_run_id,
        }

    batch_size = max(1, min(int(batch_size), 20))
    timeout_seconds = max(30.0, min(float(timeout_seconds), 900.0))
    run_id = uuid.uuid4().hex[:12]
    started_at = _now_iso()
    t0 = datetime.now(timezone.utc)

    # G1 — every cycle MUST have a lineage handle. If the caller didn't
    # provide one (manual API hit, etc.), create one tagged manual_api so
    # lineage is uniform across all entry points.
    if not research_run_id:
        try:
            from engines import research_lineage
            research_run_id = await research_lineage.new_research_run(
                trigger_type="manual_api",
                trigger_reason="run_single_cycle",
                config={
                    "batch_size": batch_size, "pair": pair, "timeframe": timeframe,
                    "style": style, "firm": firm,
                    "quality_filter": bool(quality_filter),
                    "quality_threshold": float(quality_threshold),
                },
            )
        except Exception as e:                              # pragma: no cover
            logger.debug("[lineage] new_research_run failed: %s", e)

    # Auto-alternate pair when not specified (task 7).
    if not pair:
        db = get_db()
        n_prior = await db[RUN_CYCLES_COLL].count_documents({})
        pair = _CYCLE_PAIR_ROTATION[n_prior % len(_CYCLE_PAIR_ROTATION)]

    pair = pair.upper()
    timeframe = timeframe.upper()

    # quality_filter + quality_threshold are plumbed through sim_config
    # — `run_backtest_logic` applies them inside the evaluation loop,
    # so saved strategies already reflect the filter.
    #
    # TASK 2 — enable regime gating + session-aware spread by default
    # for the auto-discovery path. Both flags are read by
    # `backtest_engine.run_backtest_logic` (cfg.regime_filter /
    # cfg.session_spread). Session_spread was already default-on; the
    # new addition is regime_filter, which suppresses entries when the
    # current 100-bar regime ≠ the strategy_type's preferred regime
    # set. Strategies that survive this gate are inherently more
    # regime-stable, raising both PF and OOS robustness.
    sim_config: Dict[str, Any] = {
        "quality_filter": bool(quality_filter),
        "quality_threshold": float(quality_threshold),
        "regime_filter": True,
        "session_spread": True,
    }

    # Build the runnable as a coroutine so we can wrap it in wait_for.
    async def _do_cycle() -> Dict[str, Any]:
        async with _RUN_LOCK:
            per_strategy: List[Dict[str, Any]] = []
            strategies_saved = 0
            pfs: List[float] = []
            dds: List[float] = []
            for _ in range(batch_size):
                try:
                    summary = await _run_one_strategy(
                        pair=pair, timeframe=timeframe, style=style,
                        firm=firm, auto_save=bool(auto_save),
                        sim_config=sim_config,
                        research_run_id=research_run_id,
                    )
                except Exception as e:
                    logger.exception("[auto/run-cycle] strategy error")
                    summary = {"error": str(e)[:240], "mutation_status": "error"}
                per_strategy.append(summary)
                if summary.get("auto_save_status") == "saved":
                    strategies_saved += 1
                pf = summary.get("best_pf")
                dd = summary.get("best_dd_pct")
                if isinstance(pf, (int, float)):
                    pfs.append(float(pf))
                if isinstance(dd, (int, float)):
                    dds.append(float(dd))
            return {
                "per_strategy": per_strategy,
                "strategies_saved": strategies_saved,
                "pfs": pfs, "dds": dds,
            }

    try:
        body = await asyncio.wait_for(_do_cycle(), timeout=timeout_seconds)
        status = "completed"
        reason = None
    except asyncio.TimeoutError:
        logger.warning("[auto/run-cycle] hit hard timeout (%ss)", timeout_seconds)
        body = {"per_strategy": [], "strategies_saved": 0, "pfs": [], "dds": []}
        status = "timeout"
        reason = f"exceeded_timeout_{timeout_seconds:.0f}s"
    except Exception as e:
        logger.exception("[auto/run-cycle] fatal")
        body = {"per_strategy": [], "strategies_saved": 0, "pfs": [], "dds": []}
        status = "error"
        reason = str(e)[:240]

    finished_at = _now_iso()
    duration_sec = (datetime.now(timezone.utc) - t0).total_seconds()
    pfs = body["pfs"]
    dds = body["dds"]
    avg_pf = round(sum(pfs) / len(pfs), 3) if pfs else None
    avg_dd = round(sum(dds) / len(dds), 3) if dds else None

    # Phase 15/16 — aggregate evolution telemetry across the cycle so
    # the scheduler response answers "did this cycle LEARN, or did it
    # fall back to uniform random?" at a glance.
    per_strats = body["per_strategy"]
    evo_applied_count = sum(
        1 for s in per_strats if (s.get("evolution") or {}).get("applied")
    )
    regimes_seen: Dict[str, int] = {}
    regime_specific_count = 0
    types_selected_union: List[str] = []
    for s in per_strats:
        evo = s.get("evolution") or {}
        rg = evo.get("regime_type")
        if rg:
            regimes_seen[rg] = regimes_seen.get(rg, 0) + 1
        if evo.get("regime_weights_used"):
            regime_specific_count += 1
        for t in (evo.get("selected_types") or []):
            if t not in types_selected_union:
                types_selected_union.append(t)
    total_strats = len(per_strats)
    evolution_summary: Dict[str, Any] = {
        "applied_count": evo_applied_count,
        "total_strategies": total_strats,
        "applied_ratio": (
            round(evo_applied_count / total_strats, 3) if total_strats else 0.0
        ),
        "regime_specific_count": regime_specific_count,
        "regimes_seen": regimes_seen,
        "types_selected_union": types_selected_union,
        "fallback_to_random": (evo_applied_count == 0 and total_strats > 0),
    }

    record = {
        "run_id": run_id,
        "research_run_id": research_run_id,
        "status": status,
        "reason": reason,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": round(duration_sec, 2),
        "pair": pair,
        "timeframe": timeframe,
        "style": style or None,
        "firm": firm,
        "config": {
            "batch_size": batch_size,
            "quality_filter": bool(quality_filter),
            "quality_threshold": float(quality_threshold),
            "optimizer": optimizer,
            "auto_save": bool(auto_save),
            "timeout_seconds": timeout_seconds,
        },
        "strategies_generated": len(body["per_strategy"]),
        "strategies_saved": body["strategies_saved"],
        "avg_pf": avg_pf,
        "avg_dd": avg_dd,
        "quality_filter_applied": bool(quality_filter),
        "evolution_summary": evolution_summary,
    }
    # Persist the run row — don't let a DB hiccup break the response.
    try:
        db = get_db()
        await db[RUN_CYCLES_COLL].insert_one({
            **record, "per_strategy": body["per_strategy"],
        })
    except Exception as e:
        logger.warning("[auto/run-cycle] failed to persist run log: %s", e)

    # G1 — attach the auto_run_cycle to the lineage doc + roll summary.
    if research_run_id:
        try:
            from engines import research_lineage
            await research_lineage.attach_child(
                research_run_id, "auto_run_cycle", run_id,
                extra={"pair": pair, "timeframe": timeframe, "status": status,
                       "saved": body["strategies_saved"], "avg_pf": avg_pf},
            )
            await research_lineage.append_summary(
                research_run_id,
                strategies_generated=len(body["per_strategy"]),
                strategies_saved=body["strategies_saved"],
                envs_scanned=[(pair, timeframe)],
            )
        except Exception as e:                              # pragma: no cover
            logger.debug("[lineage] attach auto_run_cycle failed: %s", e)

    # ── Phase 2 P2.7 — Release advisory lock (best-effort) ─────────
    # TTL safety-net catches any path that bypasses this (e.g. an
    # uncaught BaseException from one of the wrapped ops above).
    try:
        await _adv.release("auto_mutation_run")
    except Exception as _e:                              # pragma: no cover
        logger.debug("[auto/run-cycle] advisory lock release failed: %s", _e)

    # Return a compact response (trim per_strategy to essentials + evo).
    return {**record, "per_strategy": [
        {
            "mutation_status": s.get("mutation_status"),
            "best_pf": s.get("best_pf"),
            "best_dd_pct": s.get("best_dd_pct"),
            "best_trades": s.get("best_trades"),
            "best_mutation_type": s.get("best_mutation_type"),
            "auto_save_status": s.get("auto_save_status"),
            "auto_save_reason": s.get("auto_save_reason"),
            "evolution": s.get("evolution"),
            "error": s.get("error"),
        }
        for s in body["per_strategy"]
    ]}


async def list_cycle_runs(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent `auto_run_cycles` rows (scheduler log)."""
    db = get_db()
    limit = max(1, min(int(limit), 200))
    cur = db[RUN_CYCLES_COLL].find({}, {"_id": 0, "per_strategy": 0}).sort(
        "started_at", -1,
    ).limit(limit)
    return [d async for d in cur]
