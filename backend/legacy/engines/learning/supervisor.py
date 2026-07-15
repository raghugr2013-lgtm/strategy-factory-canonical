"""v1.2.0-alpha2 Phase B — Continuous Learning Supervisor.

Orchestrates one complete pipeline pass under a shared `learning_run_id`:
    generate → validate → backtest → optimize → mutate → learn (index) → rank

At every stage an outcome_events row is written via `learning.emitter`.
Every strategy touched receives its `lineage` sub-doc via
`learning.lineage.stamp_lineage`. Thresholds come from
`learning.config` (all env-configurable).

Design constraints:
  - ADDITIVE: does NOT modify the existing generate/backtest engines.
  - SAFE: any stage failure ends the cycle cleanly with an outcome
    event; never crashes the caller.
  - OBSERVABLE: keeps in-process counters + last-N runs for the
    `/api/learning/metrics` endpoint.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Deque, Dict, List, Optional

from . import config as lcfg
from .emitter import (
    emit,
    emit_generate,
    hash_context,
    new_run_id,
)
from .lineage import stamp_lineage

logger = logging.getLogger(__name__)


# ── In-process telemetry ─────────────────────────────────────────────
_LOCK = RLock()
_COUNTERS: Dict[str, int] = {
    "cycles_started": 0,
    "cycles_completed": 0,
    "cycles_failed": 0,
    "cycles_early_reject": 0,
    "stage_generate_ok": 0,
    "stage_generate_fail": 0,
    "stage_backtest_ok": 0,
    "stage_backtest_fail": 0,
    "stage_optimize_ok": 0,
    "stage_optimize_skip": 0,
    "stage_mutate_ok": 0,
    "stage_mutate_skip": 0,
    "stage_rerank_ok": 0,
    "stage_rerank_fail": 0,
}
_ACTIVE_RUNS: Dict[str, Dict[str, Any]] = {}
_RECENT_RUNS: Deque[Dict[str, Any]] = deque(maxlen=100)


@dataclass
class LearningSeed:
    pair: str = "EURUSD"
    timeframe: str = "H1"
    style: str = "trend-following"
    count: int = 1
    max_duration_s: float = 120.0


@dataclass
class LearningRun:
    run_id: str
    seed: LearningSeed
    started_at: str
    finished_at: Optional[str] = None
    status: str = "running"          # running|completed|failed|early_reject
    strategy_hash: Optional[str] = None
    stages: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "seed": {
                "pair": self.seed.pair,
                "timeframe": self.seed.timeframe,
                "style": self.seed.style,
                "count": self.seed.count,
            },
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "strategy_hash": self.strategy_hash,
            "stages": list(self.stages),
            "metrics": dict(self.metrics),
            "reason": self.reason,
        }


def _bump(name: str, by: int = 1) -> None:
    with _LOCK:
        _COUNTERS[name] = _COUNTERS.get(name, 0) + by


def _text_hash(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()[:16]


async def _register_run(run: LearningRun) -> None:
    with _LOCK:
        _ACTIVE_RUNS[run.run_id] = run.to_dict()


async def _finalise_run(run: LearningRun) -> None:
    run.finished_at = datetime.now(timezone.utc).isoformat()
    with _LOCK:
        _ACTIVE_RUNS.pop(run.run_id, None)
        _RECENT_RUNS.append(run.to_dict())


async def _record_stage(
    run: LearningRun,
    stage: str,
    *,
    status: str,
    reason: str = "",
    metrics: Optional[Dict[str, Any]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    duration_ms: int = 0,
    strategy_hash: Optional[str] = None,
    parent_hash: Optional[str] = None,
    retrieval_context_hash: Optional[str] = None,
) -> None:
    entry = {
        "stage": stage,
        "status": status,
        "reason": (reason or "")[:512],
        "metrics": metrics or {},
        "provider": provider,
        "model": model,
        "duration_ms": int(duration_ms),
        "strategy_hash": strategy_hash,
        "parent_hash": parent_hash,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    run.stages.append(entry)
    with _LOCK:
        _ACTIVE_RUNS[run.run_id] = run.to_dict()
    try:
        await emit(
            stage,
            learning_run_id=run.run_id,
            status=status,
            strategy_hash=strategy_hash,
            reason=reason,
            metrics=metrics or {},
            provider=provider,
            model=model,
            duration_ms=int(duration_ms),
            parent_hash=parent_hash,
            retrieval_context_hash=retrieval_context_hash,
        )
    except Exception:  # noqa: BLE001
        logger.exception("supervisor: emit failed for stage=%s", stage)


# ── Stage helpers ────────────────────────────────────────────────────
async def _stage_generate(run: LearningRun) -> Optional[Dict[str, Any]]:
    try:
        from engines.strategy_engine import generate_strategy_text
    except Exception as e:  # noqa: BLE001
        await _record_stage(run, "generate", status="fail",
                            reason=f"import_failed: {e}")
        _bump("stage_generate_fail")
        return None
    t0 = time.time()
    try:
        text = await generate_strategy_text(run.seed.pair, run.seed.timeframe, run.seed.style)
    except Exception as e:  # noqa: BLE001
        await _record_stage(run, "generate", status="fail",
                            reason=f"generation_failed: {str(e)[:200]}",
                            duration_ms=int((time.time() - t0) * 1000))
        _bump("stage_generate_fail")
        return None
    dur_ms = int((time.time() - t0) * 1000)
    if not text:
        await _record_stage(run, "generate", status="fail",
                            reason="empty_output", duration_ms=dur_ms)
        _bump("stage_generate_fail")
        return None

    strategy_hash = _text_hash(text)
    run.strategy_hash = strategy_hash
    # Grab LLM stats snapshot for provider/model + retrieval hash if available
    provider = model = None
    try:
        from engines.strategy_engine import get_generation_stats
        stats = get_generation_stats()
        # Provider info isn't per-strategy exposed today — best-effort.
        provider = "vie"
        model = str(stats.get("llm_success", 0))  # placeholder count marker
    except Exception:  # noqa: BLE001
        pass

    ret_hash = hash_context(run.seed.pair, run.seed.timeframe, run.seed.style)
    await _record_stage(
        run, "generate", status="pass",
        reason="strategy_text_generated",
        metrics={"length": len(text)},
        provider=provider, model=model,
        duration_ms=dur_ms,
        strategy_hash=strategy_hash,
        retrieval_context_hash=ret_hash,
    )
    _bump("stage_generate_ok")

    # Stamp lineage on any collection this hash appears in (usually none yet
    # — the pipeline may store it later via save_strategy).
    try:
        await stamp_lineage(
            strategy_hash,
            learning_run_id=run.run_id,
            stage="generate",
            provider=provider, model=model,
            retrieval_context_hash=ret_hash,
        )
    except Exception:  # noqa: BLE001
        logger.exception("supervisor: lineage stamp failed for generate")

    return {"text": text, "strategy_hash": strategy_hash,
            "retrieval_context_hash": ret_hash,
            "provider": provider, "model": model}


async def _load_market_data(pair: str, timeframe: str) -> Dict[str, Any]:
    try:
        from api.pipeline import _load_pipeline_data
        prices, highs, lows, src, n = await _load_pipeline_data(pair, timeframe)
        return {"prices": prices, "highs": highs, "lows": lows,
                "source": src, "n": n}
    except Exception as e:  # noqa: BLE001
        logger.debug("supervisor: market data load failed: %s", e)
        return {"prices": None, "highs": None, "lows": None,
                "source": "unavailable", "n": 0}


def _bt_safe(bt: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(bt, dict):
        return {}
    return bt


async def _stage_backtest(run: LearningRun, gen: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        from engines.backtest_engine import run_backtest_logic
    except Exception as e:  # noqa: BLE001
        await _record_stage(run, "backtest", status="fail",
                            reason=f"import_failed: {e}",
                            strategy_hash=run.strategy_hash)
        _bump("stage_backtest_fail")
        return None

    data = await _load_market_data(run.seed.pair, run.seed.timeframe)
    t0 = time.time()
    try:
        bt = run_backtest_logic(
            gen["text"], run.seed.pair, run.seed.timeframe,
            external_prices=data["prices"],
            external_highs=data["highs"],
            external_lows=data["lows"],
            data_source=data["source"],
            data_points=data["n"],
        )
    except Exception as e:  # noqa: BLE001
        await _record_stage(run, "backtest", status="fail",
                            reason=f"backtest_failed: {str(e)[:200]}",
                            duration_ms=int((time.time() - t0) * 1000),
                            strategy_hash=run.strategy_hash)
        _bump("stage_backtest_fail")
        return None
    dur_ms = int((time.time() - t0) * 1000)
    bt = _bt_safe(bt)

    pf = float(bt.get("profit_factor") or 0.0)
    dd = float(bt.get("max_drawdown_pct") or 0.0)
    wr = float(bt.get("win_rate") or 0.0)
    trades = int(bt.get("total_trades") or 0)

    pf_min = lcfg.pf_min()
    dd_max = lcfg.dd_max_pct()
    tr_min = lcfg.min_trades()
    wr_lo = lcfg.wr_min_pct()
    wr_hi = lcfg.wr_max_pct()

    fails: List[str] = []
    if pf < pf_min:            fails.append(f"pf<{pf_min}")
    if dd > dd_max:            fails.append(f"dd>{dd_max}%")
    if trades < tr_min:        fails.append(f"trades<{tr_min}")
    if wr and wr < wr_lo:      fails.append(f"wr<{wr_lo}%")
    if wr and wr > wr_hi:      fails.append(f"wr>{wr_hi}%")

    status = "pass" if not fails else "fail"
    await _record_stage(
        run, "backtest", status=status,
        reason="ok" if not fails else ",".join(fails),
        metrics={
            "profit_factor": pf, "max_drawdown_pct": dd,
            "win_rate": wr, "total_trades": trades,
            "data_source": data["source"], "data_points": data["n"],
        },
        duration_ms=dur_ms,
        strategy_hash=run.strategy_hash,
    )
    if status == "pass":
        _bump("stage_backtest_ok")
    else:
        _bump("stage_backtest_fail")
    return {"bt": bt, "passed": status == "pass", "fails": fails}


async def _stage_optimize(run: LearningRun, gen: Dict[str, Any], bt: Dict[str, Any]) -> None:
    """Best-effort optimisation stage — currently only records that the
    optimiser was considered. Real optimiser wiring is in the refinement
    engine and lives behind separate endpoints; we do NOT trigger a full
    walk-forward from the supervisor to keep cycle latency bounded.
    """
    uplift_min = lcfg.optimize_uplift_min()
    if uplift_min <= 0:
        await _record_stage(
            run, "optimize", status="skipped",
            reason="uplift_min<=0",
            strategy_hash=run.strategy_hash,
            metrics={"uplift_min": uplift_min},
        )
        _bump("stage_optimize_skip")
        return
    # Placeholder: record as skipped with reason (real wiring in follow-up)
    await _record_stage(
        run, "optimize", status="skipped",
        reason="deferred_to_optimizer_endpoint",
        strategy_hash=run.strategy_hash,
        metrics={"uplift_min": uplift_min},
    )
    _bump("stage_optimize_skip")


async def _stage_mutate(run: LearningRun, gen: Dict[str, Any], bt: Dict[str, Any]) -> None:
    if not lcfg.mutation_enabled():
        await _record_stage(run, "mutate", status="skipped",
                            reason="mutation_disabled",
                            strategy_hash=run.strategy_hash)
        _bump("stage_mutate_skip")
        return
    # Placeholder: emit a mutate "considered" event. Real mutation runs
    # via the dedicated mutation endpoints; the supervisor only registers
    # intent to keep the correlation graph complete.
    await _record_stage(
        run, "mutate", status="pass",
        reason="considered_only",
        strategy_hash=run.strategy_hash,
        metrics={"children": 0},
    )
    _bump("stage_mutate_ok")


async def _stage_rerank(run: LearningRun) -> None:
    """Refresh the knowledge index rows touched by this run's strategy
    so retrieval scores reflect the new outcome events."""
    try:
        from engines.knowledge import rebuild as _kb_rebuild
    except Exception as e:  # noqa: BLE001
        await _record_stage(run, "approve", status="skipped",
                            reason=f"knowledge_import_failed: {e}",
                            strategy_hash=run.strategy_hash)
        _bump("stage_rerank_fail")
        return
    t0 = time.time()
    try:
        summary = await _kb_rebuild(scope="incremental", limit=200)
    except Exception as e:  # noqa: BLE001
        await _record_stage(run, "approve", status="skipped",
                            reason=f"rebuild_failed: {str(e)[:200]}",
                            duration_ms=int((time.time() - t0) * 1000),
                            strategy_hash=run.strategy_hash)
        _bump("stage_rerank_fail")
        return
    await _record_stage(
        run, "approve", status="pass",
        reason="knowledge_index_refreshed",
        metrics=summary,
        duration_ms=int((time.time() - t0) * 1000),
        strategy_hash=run.strategy_hash,
    )
    _bump("stage_rerank_ok")


# ── Public entry points ──────────────────────────────────────────────
async def run_learning_cycle(seed: Optional[LearningSeed] = None) -> LearningRun:
    """Run one full learning cycle. Never raises — always returns a
    LearningRun (possibly with status="failed")."""
    seed = seed or LearningSeed()
    run = LearningRun(
        run_id=new_run_id(),
        seed=seed,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    await _register_run(run)
    _bump("cycles_started")

    started = time.time()
    try:
        # 1) Generate
        gen = await asyncio.wait_for(_stage_generate(run), timeout=seed.max_duration_s)
        if not gen:
            run.status = "failed"
            run.reason = "generation_failed"
            _bump("cycles_failed")
            await _finalise_run(run)
            return run

        # 2) Backtest
        bt_res = await asyncio.wait_for(_stage_backtest(run, gen), timeout=seed.max_duration_s)
        if not bt_res or not bt_res.get("passed"):
            run.status = "early_reject"
            run.reason = ",".join((bt_res or {}).get("fails", []) or ["backtest_failed"])
            _bump("cycles_early_reject")
            # Still refresh the index so the ledger row participates in
            # future retrievals as a "loss".
            try:
                await _stage_rerank(run)
            except Exception:  # noqa: BLE001
                logger.exception("rerank after early_reject failed")
            await _finalise_run(run)
            return run

        # 3) Optimize (env-gated placeholder)
        await _stage_optimize(run, gen, bt_res["bt"])
        # 4) Mutate (env-gated placeholder)
        await _stage_mutate(run, gen, bt_res["bt"])
        # 5) Rebuild knowledge index for outcome-conditioned retrieval
        await _stage_rerank(run)

        run.status = "completed"
        run.metrics = {"backtest": bt_res["bt"], "duration_s": round(time.time() - started, 3)}
        _bump("cycles_completed")
    except asyncio.TimeoutError:
        run.status = "failed"
        run.reason = "timeout"
        _bump("cycles_failed")
    except Exception as e:  # noqa: BLE001
        logger.exception("supervisor: unexpected failure")
        run.status = "failed"
        run.reason = f"unhandled_exception: {str(e)[:200]}"
        _bump("cycles_failed")

    await _finalise_run(run)
    return run


def counters_snapshot() -> Dict[str, Any]:
    with _LOCK:
        return {
            "counters": dict(_COUNTERS),
            "active_runs": list(_ACTIVE_RUNS.values()),
            "recent_runs": list(_RECENT_RUNS),
        }


def get_run(run_id: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        if run_id in _ACTIVE_RUNS:
            return _ACTIVE_RUNS[run_id]
        for r in _RECENT_RUNS:
            if r.get("run_id") == run_id:
                return r
    return None


# ── Scheduler ────────────────────────────────────────────────────────
_SCHEDULER_TASK: Optional[asyncio.Task] = None
_SCHEDULER_STOP = asyncio.Event()
_SCHEDULER_META: Dict[str, Any] = {
    "started_at": None,
    "cycles_launched": 0,
    "last_run_id": None,
    "last_status": None,
    "last_finished_at": None,
}


async def _scheduler_loop() -> None:
    _SCHEDULER_META["started_at"] = datetime.now(timezone.utc).isoformat()
    logger.info("learning scheduler loop started")
    try:
        while not _SCHEDULER_STOP.is_set():
            interval = max(60, lcfg.scheduler_interval_seconds())
            try:
                # Cap concurrent
                with _LOCK:
                    active = len(_ACTIVE_RUNS)
                if active < lcfg.scheduler_max_concurrent():
                    run = await run_learning_cycle(LearningSeed())
                    _SCHEDULER_META["cycles_launched"] += 1
                    _SCHEDULER_META["last_run_id"] = run.run_id
                    _SCHEDULER_META["last_status"] = run.status
                    _SCHEDULER_META["last_finished_at"] = run.finished_at
                else:
                    logger.info("scheduler: skipping tick, active=%d", active)
            except Exception:  # noqa: BLE001
                logger.exception("scheduler tick failed (non-fatal)")
            try:
                await asyncio.wait_for(_SCHEDULER_STOP.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
    finally:
        logger.info("learning scheduler loop stopped")


async def start_scheduler() -> Dict[str, Any]:
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        return {"running": True, "already_started": True, **_SCHEDULER_META}
    _SCHEDULER_STOP.clear()
    _SCHEDULER_TASK = asyncio.create_task(_scheduler_loop())
    return {"running": True, "already_started": False, **_SCHEDULER_META}


async def stop_scheduler() -> Dict[str, Any]:
    global _SCHEDULER_TASK
    if not _SCHEDULER_TASK or _SCHEDULER_TASK.done():
        return {"running": False, **_SCHEDULER_META}
    _SCHEDULER_STOP.set()
    try:
        await asyncio.wait_for(_SCHEDULER_TASK, timeout=5.0)
    except asyncio.TimeoutError:
        _SCHEDULER_TASK.cancel()
    _SCHEDULER_TASK = None
    return {"running": False, **_SCHEDULER_META}


def scheduler_status() -> Dict[str, Any]:
    running = bool(_SCHEDULER_TASK and not _SCHEDULER_TASK.done())
    return {
        "running": running,
        "enabled_by_env": lcfg.scheduler_enabled(),
        "interval_seconds": lcfg.scheduler_interval_seconds(),
        "max_concurrent": lcfg.scheduler_max_concurrent(),
        **_SCHEDULER_META,
    }
