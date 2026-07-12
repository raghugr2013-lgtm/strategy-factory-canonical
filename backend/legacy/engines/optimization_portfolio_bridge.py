"""
Optimization → Portfolio Rebuild Bridge (SAFE).

Orchestration layer that decides whether to rebuild Portfolio Intelligence
after an Optimization batch completes. **Strictly additive** — this
module imports but never mutates the optimization or portfolio engines.

Safety contract (MANDATORY — every rule must pass for every item in the
batch, otherwise the rebuild is skipped):

    verdict == "OPTIMIZED"
    optimized_pf          >=  original_pf * 0.95      (no degradation)
    optimized_dd          <=  original_dd              (not worse)
    optimized_stability   >=  0.7                      (0..1 scale)
    pass_probability      >=  0.6                      (0..1 scale)

Process:
    1. Derive a stable `batch_id` from the Optimization run.
    2. Dedup — if the same batch was already processed, return the
       original decision.
    3. Cooldown — if the last *triggered* rebuild was within the
       configured window (default 10 minutes), skip.
    4. Evaluate gates over every item in the batch.
    5. If all gates pass → call
       `portfolio_intelligence_engine.run_build_from_source({source:"auto_factory"})`
       directly (no internal HTTP).
    6. Persist the decision (+ reason) to `optimization_portfolio_actions`.

Always returns a dict — never raises. Logs exceptions silently.
"""

from __future__ import annotations

import logging
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

COLL_ACTIONS = "optimization_portfolio_actions"

DEFAULT_CONFIG: Dict[str, Any] = {
    "cooldown_seconds": 600,                    # 10 minutes between triggered rebuilds
    "rebuild_source": "auto_factory",
    "min_optimized_pf_ratio": 0.95,             # optimized_pf >= original_pf × this
    "min_stability": 0.70,
    "min_pass_probability": 0.60,
    "require_all_optimized": True,              # every item must be OPTIMIZED
    "min_items": 1,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _stability_01(v: Any) -> float:
    """Normalise stability value to the [0, 1] scale. The optimization
    engine stores it as 0..100 — we divide automatically when v > 1."""
    x = _as_float(v)
    if x > 1.0:
        x /= 100.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _prob_01(v: Any) -> float:
    """Normalise pass_probability to [0, 1] (source is usually 0..100)."""
    x = _as_float(v)
    if x > 1.0:
        x /= 100.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _batch_id_of(results: Dict[str, Any]) -> str:
    """Pull or derive a stable batch id from the optimization result.

    Prefers the engine-provided `run_id`. Falls back to a SHA1 over
    (built_at, source, candidates, strategy_ids[:3]) so repeated calls
    with the same payload collapse to the same id.
    """
    rid = results.get("run_id") or results.get("batch_id")
    if rid:
        return str(rid)
    items = results.get("results") or []
    ids = []
    for r in items[:3]:
        sid = (r.get("optimized_strategy") or {}).get("strategy_id")
        if sid:
            ids.append(str(sid))
    payload = f"{results.get('built_at', '')}:{results.get('source', '')}:{len(items)}:{','.join(ids)}"
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


# ── Gate evaluation ──────────────────────────────────────────────────
def _evaluate_gates(
    items: List[Dict[str, Any]],
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """Evaluate each safety gate over the full batch.

    Returns:
        {passed: bool, failures: [{strategy_id, reason, ...}]}
    """
    if not items:
        return {"passed": False, "failures": [{"reason": "no_results"}]}
    if len(items) < int(cfg.get("min_items", 1)):
        return {
            "passed": False,
            "failures": [{"reason": f"items<{cfg['min_items']}"}],
        }

    min_ratio = float(cfg["min_optimized_pf_ratio"])
    min_stab = float(cfg["min_stability"])
    min_pp = float(cfg["min_pass_probability"])

    failures: List[Dict[str, Any]] = []
    for r in items:
        og = r.get("original_metrics") or {}
        op = r.get("optimized_metrics") or {}
        sid = (r.get("optimized_strategy") or {}).get("strategy_id")
        verdict = r.get("verdict")

        if cfg.get("require_all_optimized", True) and verdict != "OPTIMIZED":
            failures.append({"strategy_id": sid, "reason": f"verdict={verdict}"})
            continue

        pf_o = _as_float(og.get("pf"))
        pf_n = _as_float(op.get("pf"))
        dd_o = _as_float(og.get("max_drawdown_pct"))
        dd_n = _as_float(op.get("max_drawdown_pct"))
        stab = _stability_01(op.get("stability"))
        pp = _prob_01(op.get("pass_probability"))

        # 1. No PF degradation (≥ 95% of original)
        if pf_o > 0 and pf_n < pf_o * min_ratio:
            failures.append({
                "strategy_id": sid,
                "reason": "pf_degraded",
                "original_pf": round(pf_o, 3),
                "optimized_pf": round(pf_n, 3),
                "threshold": round(pf_o * min_ratio, 3),
            })
            continue

        # 2. DD not worse than original
        if dd_n > dd_o + 1e-6:
            failures.append({
                "strategy_id": sid,
                "reason": "dd_worse",
                "original_dd": round(dd_o, 3),
                "optimized_dd": round(dd_n, 3),
            })
            continue

        # 3. Stability floor
        if stab < min_stab:
            failures.append({
                "strategy_id": sid,
                "reason": "stability_low",
                "stability_01": round(stab, 3),
                "threshold": min_stab,
            })
            continue

        # 4. Pass-probability floor
        if pp < min_pp:
            failures.append({
                "strategy_id": sid,
                "reason": "pass_prob_low",
                "pass_probability_01": round(pp, 3),
                "threshold": min_pp,
            })
            continue

    return {"passed": not failures, "failures": failures}


# ── Persistence helpers ──────────────────────────────────────────────
async def _last_triggered() -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[COLL_ACTIONS].find_one(
        {"triggered": True}, {"_id": 0}, sort=[("ts", -1)],
    )


async def _find_by_batch(batch_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[COLL_ACTIONS].find_one({"batch_id": batch_id}, {"_id": 0})


async def _record(action: Dict[str, Any]) -> None:
    db = get_db()
    try:
        await db[COLL_ACTIONS].insert_one({**action})
    except Exception:
        logger.exception("bridge: failed to persist action")


# ── Public API ───────────────────────────────────────────────────────
async def handle_post_optimization(
    results: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate safety gates and optionally trigger a Portfolio
    Intelligence rebuild. Returns a decision record; never raises.

    Args:
        results: output of `strategy_refinement_engine.run_optimization_batch`
                 — must contain `results: [...]` with per-item
                 original_metrics / optimized_metrics / verdict.
        config:  optional overrides of `DEFAULT_CONFIG`.

    Returns:
        {
          batch_id, ts, triggered: bool, reason: str,
          failures: [...], rebuild: {...} | None,
          cooldown_remaining_seconds: int
        }
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    batch_id = _batch_id_of(results or {})
    now = _now()
    now_iso = now.isoformat()

    try:
        # 1. Dedup — same batch already processed.
        existing = await _find_by_batch(batch_id)
        if existing:
            return {**existing, "deduped": True}

        items = (results or {}).get("results") or []

        # 2. Cooldown — skip if a triggered rebuild fired recently.
        last = await _last_triggered()
        cooldown = int(cfg["cooldown_seconds"])
        if last:
            last_ts = last.get("ts") or last.get("timestamp")
            try:
                last_dt = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
                delta = now - last_dt
                if delta < timedelta(seconds=cooldown):
                    remaining = max(0, cooldown - int(delta.total_seconds()))
                    action = {
                        "batch_id": batch_id,
                        "ts": now_iso,
                        "triggered": False,
                        "reason": "cooldown",
                        "cooldown_remaining_seconds": remaining,
                        "last_triggered_batch_id": last.get("batch_id"),
                        "last_triggered_at": str(last_ts),
                        "source": (results or {}).get("source"),
                        "items_count": len(items),
                        "config": cfg,
                    }
                    await _record(action)
                    return action
            except (TypeError, ValueError):
                # Unparseable timestamp — treat as no cooldown.
                pass

        # 3. Evaluate gates.
        eval_result = _evaluate_gates(items, cfg)
        if not eval_result["passed"]:
            action = {
                "batch_id": batch_id,
                "ts": now_iso,
                "triggered": False,
                "reason": "conditions_failed",
                "failures": eval_result["failures"][:20],
                "items_count": len(items),
                "source": (results or {}).get("source"),
                "config": cfg,
            }
            await _record(action)
            return action

        # 4. All gates passed — call Portfolio Intelligence rebuild.
        rebuild_summary: Optional[Dict[str, Any]] = None
        rebuild_status = "ok"
        rebuild_error: Optional[str] = None
        try:
            from engines import portfolio_intelligence_engine as pie  # lazy import
            result = await pie.run_build_from_source(
                {"source": cfg["rebuild_source"]}
            )
            rebuild_summary = {
                "status": result.get("status"),
                "source": result.get("source"),
                "pool_raw_count": result.get("pool_raw_count"),
                "selected_count": result.get("selected_count"),
                "expected_pf": result.get("expected_pf"),
                "expected_dd": result.get("expected_dd"),
                "diversification_score": result.get("diversification_score"),
                "built_at": result.get("built_at"),
            }
            rebuild_status = result.get("status") or "ok"
        except Exception as e:
            logger.exception("bridge: portfolio rebuild invocation failed")
            rebuild_error = str(e)
            rebuild_status = "error"

        triggered = rebuild_error is None
        action = {
            "batch_id": batch_id,
            "ts": now_iso,
            "triggered": triggered,
            "reason": "approved" if triggered else "rebuild_failed",
            "items_count": len(items),
            "source": (results or {}).get("source"),
            "rebuild_status": rebuild_status,
            "rebuild": rebuild_summary,
            "rebuild_error": rebuild_error,
            "config": cfg,
        }
        await _record(action)
        return action

    except Exception as e:
        # Final safety net — never break the caller.
        logger.exception("bridge: unexpected error in handle_post_optimization")
        return {
            "batch_id": batch_id,
            "ts": now_iso,
            "triggered": False,
            "reason": "bridge_error",
            "error": str(e),
        }


async def get_recent_actions(limit: int = 20) -> List[Dict[str, Any]]:
    """Read the last N bridge decisions from `optimization_portfolio_actions`."""
    db = get_db()
    limit = max(1, min(int(limit), 100))
    cursor = db[COLL_ACTIONS].find({}, {"_id": 0}).sort("ts", -1).limit(limit)
    return [d async for d in cursor]
