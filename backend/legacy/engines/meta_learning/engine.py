"""Phase I — Top-level cycle orchestration.

`run_meta_learning_cycle()` is the single entry point invoked by the
orchestrator task and by the `/api/meta-learning/refresh` admin
endpoint. It:

  1. Emits `meta_learning_cycle_start`.
  2. Runs collectors → evaluators → proposers → ranker.
  3. Persists evaluations + recommendations.
  4. In OBSERVE mode, halts here. Emits `meta_learning_cycle_end`.
  5. In RECOMMEND mode, halts here too — application is
     operator-driven via `/api/meta-learning/recommendations/{id}/approve`.
  6. In AUTONOMOUS mode (+ confirm), auto-applies top-N whitelisted
     recommendations.

Deterministic + fully explainable — every step emits outcome events.
Never raises; wraps every stage in try/except so a single bad
evaluator can't take the whole cycle down.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import applier, config as mlcfg, explainability, ledger, proposers
from .collectors import (
    collect_brain_decisions, collect_execution_realised,
    collect_market_intelligence, collect_portfolio_events,
)
from .collectors.execution_realised import join_decision_to_realised
from .evaluators import (
    evaluate_confidence_calibration, evaluate_execution_quality_gate,
    evaluate_market_signal_utility, evaluate_style_regime_matrix,
    evaluate_threshold_calibration, evaluate_weight_sensitivity,
)
from .ranker import rank_and_filter
from .types import MetaMode, MetaRecStatus, MetaSurface

logger = logging.getLogger(__name__)


def _get_current_brain_weights() -> Dict[str, float]:
    """Read current brain scoring weights via the brain config helpers."""
    try:
        from engines.brain import config as bcfg
        return dict(bcfg.scoring_weights())
    except Exception:  # noqa: BLE001
        return {}


def _get_current_brain_thresholds() -> Dict[str, float]:
    try:
        from engines.brain import config as bcfg
        return {
            "BRAIN_TRADE_NOW_THRESHOLD": bcfg.trade_now_threshold(),
            "BRAIN_PAUSE_THRESHOLD":     bcfg.pause_threshold(),
            "BRAIN_RETIRE_THRESHOLD":    bcfg.retire_threshold(),
        }
    except Exception:  # noqa: BLE001
        return {"BRAIN_TRADE_NOW_THRESHOLD": 0.75,
                "BRAIN_PAUSE_THRESHOLD": 0.40,
                "BRAIN_RETIRE_THRESHOLD": 0.25}


def _get_current_market_weights() -> Dict[str, float]:
    try:
        from engines.market_intel_engine import config as micfg
        return {
            "BRAIN_W_MARKET_CONFIDENCE": micfg.w_market_confidence(),
            "BRAIN_W_STYLE_CONFIDENCE":  micfg.w_style_confidence(),
            "BRAIN_W_OPPORTUNITY":       micfg.w_opportunity(),
        }
    except Exception:  # noqa: BLE001
        return {"BRAIN_W_MARKET_CONFIDENCE": 0.0,
                "BRAIN_W_STYLE_CONFIDENCE": 0.0,
                "BRAIN_W_OPPORTUNITY": 0.0}


async def run_meta_learning_cycle(*, force: bool = False) -> Dict[str, Any]:
    """Execute one meta-learning cycle. Returns a summary dict.

    `force=True` runs the cycle even if `META_LEARNING_MODE=disabled`
    (used by the admin `/refresh` endpoint for diagnostic runs; still
    never writes to overrides in disabled/observe modes).
    """
    t0 = time.time()
    cycle_id = "ml_cycle_" + uuid.uuid4().hex[:10]
    cur_mode = mlcfg.mode()

    if cur_mode == MetaMode.DISABLED and not force:
        return {"cycle_id": cycle_id, "mode": cur_mode,
                "skipped": True, "reason": "META_LEARNING_MODE=disabled"}

    window_h = mlcfg.window_hours()
    min_n = mlcfg.min_samples()
    now = datetime.now(timezone.utc)
    win_start = (now - timedelta(hours=window_h)).isoformat()
    win_end = now.isoformat()

    await explainability.emit(
        "meta_learning_cycle_start",
        reason=f"cycle={cycle_id} mode={cur_mode} window={window_h}h",
        metrics={"cycle_id": cycle_id, "mode": cur_mode,
                  "window_hours": window_h, "min_samples": min_n},
        evidence={},
    )

    # ── 1. Collectors ─────────────────────────────────────
    try:
        decisions = await collect_brain_decisions(window_hours=window_h)
        realised = await collect_execution_realised(window_hours=window_h)
        _ = await collect_market_intelligence(window_hours=window_h)
        _ = await collect_portfolio_events(window_hours=window_h)
        pairs = await join_decision_to_realised(decisions, realised)
    except Exception:  # noqa: BLE001
        logger.exception("[meta_learning] collectors failed")
        decisions, realised, pairs = [], [], []

    # ── 2. Evaluators (pure) ──────────────────────────────
    evaluations = []
    try:
        evaluations += evaluate_weight_sensitivity(
            pairs, window_start=win_start, window_end=win_end, min_samples=min_n)
        evaluations += evaluate_threshold_calibration(
            pairs, window_start=win_start, window_end=win_end,
            min_samples=min_n, current_values=_get_current_brain_thresholds())
        evaluations += evaluate_confidence_calibration(
            pairs, window_start=win_start, window_end=win_end, min_samples=min_n)
        evaluations += evaluate_style_regime_matrix(
            pairs, window_start=win_start, window_end=win_end, min_samples=min_n)
        evaluations += evaluate_market_signal_utility(
            pairs, window_start=win_start, window_end=win_end, min_samples=min_n)
        evaluations += evaluate_execution_quality_gate(
            realised, window_start=win_start, window_end=win_end, min_samples=min_n)
    except Exception:  # noqa: BLE001
        logger.exception("[meta_learning] evaluators failed")

    # Persist evaluations + emit outcome_events
    for ev in evaluations:
        await ledger.upsert_evaluation(ev)
        await explainability.emit(
            "meta_learning_evaluation",
            reason=f"{ev.surface}:{ev.target} sig={ev.significance}",
            metrics={"evaluation_id": ev.evaluation_id,
                      "surface": ev.surface, "target": ev.target,
                      "n_samples": ev.n_samples,
                      "significance": ev.significance,
                      "cycle_id": cycle_id},
            evidence={"method": ev.method,
                       "metrics": ev.metrics,
                       **(ev.evidence or {})},
        )

    # ── 3. Proposers ──────────────────────────────────────
    current_weights = _get_current_brain_weights()
    current_thresholds = _get_current_brain_thresholds()
    current_market = _get_current_market_weights()

    recs = []
    try:
        for ev in evaluations:
            if ev.surface == MetaSurface.BRAIN_WEIGHT:
                # Map target env-var back to component weight key
                comp = ev.evidence.get("component_key")
                cur = float(current_weights.get(comp, 0.0)) if comp else 0.0
                recs += proposers.propose_brain_weight(
                    ev, current=cur, mode=cur_mode)
            elif ev.surface == MetaSurface.BRAIN_THRESHOLD:
                cur = float(current_thresholds.get(ev.target, 0.5))
                recs += proposers.propose_brain_threshold(
                    ev, current=cur, mode=cur_mode)
            elif ev.surface == MetaSurface.MARKET_WEIGHT:
                cur = float(current_market.get(ev.target, 0.0))
                recs += proposers.propose_market_weight(
                    ev, current=cur, mode=cur_mode)
            elif ev.surface == MetaSurface.EXECUTION_GATE:
                cur = 0.5  # neutral default
                recs += proposers.propose_execution_gate(
                    ev, current=cur, mode=cur_mode)
            elif ev.surface == MetaSurface.CONFIDENCE_CALIBRATION:
                cur = 1.0  # 1.0 = no shrinkage
                recs += proposers.propose_confidence_calibration(
                    ev, current=cur, mode=cur_mode)
            # STYLE_REGIME_MATRIX evaluations are diagnostic-only in
            # this release (no auto-proposer; surfaces in API as info).
    except Exception:  # noqa: BLE001
        logger.exception("[meta_learning] proposers failed")

    # ── 4. Ranker ─────────────────────────────────────────
    # Build recent_load from applications (last 24h)
    recent_load: Dict[str, int] = {}
    try:
        recent = await ledger.read_applications(limit=500)
        cutoff = datetime.now(timezone.utc).timestamp() - 86400
        for a in recent:
            try:
                ts = datetime.fromisoformat(
                    a.applied_at.replace("Z", "+00:00")).timestamp()
            except (ValueError, TypeError):
                continue
            if ts >= cutoff:
                recent_load[a.target] = recent_load.get(a.target, 0) + 1
    except Exception:  # noqa: BLE001
        pass

    recs = rank_and_filter(recs, recent_load=recent_load)

    # Persist recommendations + emit outcome_events
    for r in recs:
        await ledger.upsert_recommendation(r)
        await explainability.emit(
            "meta_learning_recommendation",
            reason=(f"{r.surface}:{r.target} "
                     f"Δ={r.proposed_delta:+.4f} score="
                     f"{r.evidence.get('ranker_score', 0):.4f} "
                     f"band={r.risk_band}"),
            metrics={"recommendation_id": r.recommendation_id,
                      "evaluation_id": r.evaluation_id,
                      "surface": r.surface, "target": r.target,
                      "proposed_delta": r.proposed_delta,
                      "confidence": r.confidence,
                      "risk_band": r.risk_band,
                      "severity": r.severity,
                      "status": r.status,
                      "cycle_id": cycle_id},
            evidence={**(r.evidence or {})},
        )

    # ── 5. Autonomous auto-apply (dormant unless mode + confirm) ───
    applied_count = 0
    if cur_mode == MetaMode.AUTONOMOUS and mlcfg.autonomous_confirm():
        whitelist = mlcfg.autonomous_whitelist()
        for r in recs:
            if r.status != MetaRecStatus.PENDING:
                continue
            if r.surface not in whitelist:
                continue
            if r.risk_band != "green":  # extra caution: only green auto-applies
                continue
            try:
                app = await applier.apply_recommendation(
                    r, applied_by="autonomous")
                if app is not None:
                    applied_count += 1
            except applier.ApplierGuardBlocked as e:
                logger.warning("[meta_learning] auto-apply blocked: %s", e)

    duration_ms = int((time.time() - t0) * 1000)
    summary = {
        "cycle_id": cycle_id,
        "mode": cur_mode,
        "window_hours": window_h,
        "min_samples": min_n,
        "n_decisions": len(decisions),
        "n_realised":  len(realised),
        "n_pairs":     len(pairs),
        "n_evaluations": len(evaluations),
        "n_recommendations": len([r for r in recs
                                   if r.status == MetaRecStatus.PENDING]),
        "n_expired": len([r for r in recs
                            if r.status == MetaRecStatus.EXPIRED]),
        "n_applied": applied_count,
        "duration_ms": duration_ms,
    }

    await explainability.emit(
        "meta_learning_cycle_end",
        reason=f"cycle={cycle_id} evals={summary['n_evaluations']} "
                f"recs={summary['n_recommendations']} "
                f"applied={applied_count}",
        metrics=summary, evidence={},
    )

    logger.info("[meta_learning] cycle=%s summary=%s", cycle_id, summary)
    return summary
