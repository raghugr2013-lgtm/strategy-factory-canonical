"""Phase J — Proposers, Ranker, Applier, Engine (consolidated).

Kept in one module to minimise cross-file surface area while
preserving clear function boundaries. Each function is pure or
narrowly-scoped async.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from . import config as fecfg
from . import explainability, ledger
from .types import (
    FactoryApplication, FactoryInsight, FactoryRecommendation, FactoryReport,
    FEMode, FERecStatus, FERiskBand, FESeverity, FESurface,
)

logger = logging.getLogger(__name__)


def _rid() -> str:
    return "fe_rec_" + uuid.uuid4().hex[:12]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_iso() -> str:
    return (datetime.now(timezone.utc)
            + timedelta(days=fecfg.rec_ttl_days())).isoformat()


def _clamp(x, lo, hi): return max(lo, min(hi, x))


def _severity(mag: float, thresholds=(0.02, 0.10, 0.30)) -> str:
    a = abs(mag)
    if a < thresholds[0]: return FESeverity.INFO
    if a < thresholds[1]: return FESeverity.LOW
    if a < thresholds[2]: return FESeverity.MED
    return FESeverity.HIGH


def _risk_band(surface: str, delta: float) -> str:
    a = abs(delta)
    if a <= 0.02:
        return FERiskBand.GREEN
    if a <= 0.10:
        return FERiskBand.AMBER
    return FERiskBand.RED


# ═══════════════════════════════════════════════════════════════════
# Proposers
# ═══════════════════════════════════════════════════════════════════

def propose_compute_reallocation(
    insight: FactoryInsight, *, mode: str,
) -> List[FactoryRecommendation]:
    """Recommend a small priority-base delta if the compute_allocation
    insight suggests hint. Bounded by max_delta_per_tick."""
    if insight.surface != FESurface.COMPUTE_ALLOCATION:
        return []
    # Purely diagnostic in this release — always emits an INFO
    # recommendation the operator may inspect.
    max_d = fecfg.max_delta_per_tick()
    delta = 0.0  # zero default — informational only
    return [FactoryRecommendation(
        recommendation_id=_rid(),
        insight_ids=[insight.insight_id],
        surface=FESurface.COMPUTE_REALLOCATION,
        target="ORCH_TASK_PRIORITY_BASE:diagnostic",
        current_value=0.0, proposed_value=0.0, proposed_delta=delta,
        expected_uplift=0.0, confidence=float(insight.significance),
        severity=FESeverity.INFO,
        risk_band=FERiskBand.GREEN,
        rationale="Diagnostic hint — review orchestrator task priorities",
        evidence={"insight_id": insight.insight_id,
                   "metrics": dict(insight.metrics)},
        guardrails={"max_delta_per_tick": max_d},
        mode=mode, status=FERecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


def propose_execution_path_pref(
    insight: FactoryInsight, *, mode: str,
) -> List[FactoryRecommendation]:
    """For each top-ranked execution path, propose a path preference."""
    if insight.surface != FESurface.EXECUTION_QUALITY:
        return []
    metrics = insight.metrics or {}
    if metrics.get("rank", 99) > 3:  # only propose top-3
        return []
    key = str(insight.evidence.get("path_key") or insight.target)
    score = float(metrics.get("mean_score", 0.5))
    proposed_pref = _clamp(score, 0.0, 1.0)
    return [FactoryRecommendation(
        recommendation_id=_rid(),
        insight_ids=[insight.insight_id],
        surface=FESurface.EXECUTION_PATH_PREF,
        target=f"EXEC_PREFERRED_PATH:{key}",
        current_value=0.5, proposed_value=proposed_pref,
        proposed_delta=proposed_pref - 0.5,
        expected_uplift=abs(score - 0.5),
        confidence=float(insight.significance),
        severity=_severity(score - 0.5),
        risk_band=_risk_band(FESurface.EXECUTION_PATH_PREF, score - 0.5),
        rationale=f"Path {key} ranked #{metrics.get('rank')} score={score}",
        evidence={"insight_id": insight.insight_id,
                   "path_key": key, "rank": metrics.get("rank")},
        guardrails={"max_delta_per_tick": fecfg.max_delta_per_tick()},
        mode=mode, status=FERecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


def propose_strategy_pruning(
    insight: FactoryInsight, *, mode: str,
) -> List[FactoryRecommendation]:
    """Flag bottom-N strategies as pruning candidates.
    RECOMMEND-ONLY: Phase D still owns actual retirement."""
    if insight.surface != FESurface.STRATEGY_CONTRIBUTION:
        return []
    if not insight.target.startswith("bottom:"):
        return []
    pnl = float(insight.metrics.get("realised_pnl", 0.0))
    if pnl >= 0:
        return []
    sh = insight.target.split(":", 1)[1]
    return [FactoryRecommendation(
        recommendation_id=_rid(),
        insight_ids=[insight.insight_id],
        surface=FESurface.STRATEGY_PRUNING,
        target=f"strategy:{sh}",
        current_value=1.0, proposed_value=0.0, proposed_delta=-1.0,
        expected_uplift=abs(pnl) / 100.0,
        confidence=float(insight.significance),
        severity=FESeverity.LOW,  # flag only — never MED/HIGH
        risk_band=FERiskBand.AMBER,  # never green — this is a hint
        rationale=f"Strategy {sh} negative PnL {pnl:.2f} — flag for Phase D review",
        evidence={"insight_id": insight.insight_id,
                   "strategy_hash": sh, "realised_pnl": pnl},
        guardrails={"note": "flag-only; Phase D retirement engine decides"},
        mode=mode, status=FERecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


def propose_portfolio_rebalance_hint(
    insight: FactoryInsight, *, mode: str,
) -> List[FactoryRecommendation]:
    """Hint at deteriorating Master Bots — Phase D owns actual rebuilds."""
    if insight.surface != FESurface.PORTFOLIO_HEALTH:
        return []
    if insight.severity not in (FESeverity.MED, FESeverity.HIGH):
        return []
    bid = str(insight.evidence.get("master_bot_id") or "unknown")
    return [FactoryRecommendation(
        recommendation_id=_rid(),
        insight_ids=[insight.insight_id],
        surface=FESurface.PORTFOLIO_REBALANCE_HINT,
        target=f"master_bot:{bid}",
        current_value=1.0, proposed_value=0.0, proposed_delta=0.0,
        expected_uplift=float(insight.metrics.get("composite", 0.0)),
        confidence=float(insight.significance),
        severity=insight.severity,
        risk_band=FERiskBand.AMBER,
        rationale=f"Master Bot {bid} showing health deterioration",
        evidence={"insight_id": insight.insight_id,
                   "composite": insight.metrics.get("composite")},
        guardrails={"note": "hint-only; Phase D owns rebuilds"},
        mode=mode, status=FERecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


def propose_research_investment(
    insight: FactoryInsight, *, mode: str,
) -> List[FactoryRecommendation]:
    """Coverage gap → research investment hint."""
    if insight.surface != FESurface.COVERAGE_GAP:
        return []
    if insight.severity not in (FESeverity.MED, FESeverity.HIGH):
        return []
    gap = float(insight.metrics.get("gap_ratio", 0.0))
    return [FactoryRecommendation(
        recommendation_id=_rid(),
        insight_ids=[insight.insight_id],
        surface=FESurface.RESEARCH_INVESTMENT,
        target="research:coverage_expansion",
        current_value=float(insight.metrics.get("n_strategies", 0)),
        proposed_value=float(insight.metrics.get("target_coverage", 0)),
        proposed_delta=float(insight.metrics.get("target_coverage", 0)
                             - insight.metrics.get("n_strategies", 0)),
        expected_uplift=gap,
        confidence=float(insight.significance),
        severity=insight.severity,
        risk_band=FERiskBand.AMBER,
        rationale=f"Coverage gap {gap:.2f} — invest in under-explored cells",
        evidence={"insight_id": insight.insight_id},
        guardrails={"note": "hint-only; operator directs next research cycles"},
        mode=mode, status=FERecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


def propose_budget_reallocation(
    insight: FactoryInsight, *, mode: str,
) -> List[FactoryRecommendation]:
    """Very conservative — only recommend proportional shifts for
    providers with extremely high cost/pass."""
    if insight.surface != FESurface.PROVIDER_EFFICIENCY:
        return []
    cost_per_pass = float(insight.metrics.get("cost_per_pass", 0.0))
    n_pass = int(insight.metrics.get("n_pass", 0))
    # Only recommend if inefficient
    if cost_per_pass < 1.0 or n_pass == 0:
        return []
    return [FactoryRecommendation(
        recommendation_id=_rid(),
        insight_ids=[insight.insight_id],
        surface=FESurface.BUDGET_REALLOCATION,
        target=insight.target,
        current_value=1.0, proposed_value=0.9, proposed_delta=-0.10,
        expected_uplift=0.05,
        confidence=float(insight.significance),
        severity=FESeverity.LOW,
        risk_band=FERiskBand.AMBER,
        rationale=f"High cost/pass={cost_per_pass:.4f} — consider proportional shift",
        evidence={"insight_id": insight.insight_id},
        guardrails={"proportional_shift_only": True},
        mode=mode, status=FERecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


# ═══════════════════════════════════════════════════════════════════
# Ranker
# ═══════════════════════════════════════════════════════════════════

_RISK_PENALTY = {
    FERiskBand.GREEN: 0.0, FERiskBand.AMBER: 0.5, FERiskBand.RED: 1.0,
}


def _score(r: FactoryRecommendation) -> float:
    penalty = _RISK_PENALTY.get(r.risk_band, 1.0)
    return float(r.expected_uplift) * float(r.confidence) * (1.0 - penalty)


def rank_and_filter(
    recs: List[FactoryRecommendation],
    *, recent_load: Optional[Dict[str, int]] = None,
) -> List[FactoryRecommendation]:
    recent_load = recent_load or {}
    floor = fecfg.rank_floor()
    for r in recs:
        s = _score(r)
        r.evidence = dict(r.evidence or {})
        r.evidence["ranker_score"] = round(s, 6)
        r.evidence["recent_load"] = int(recent_load.get(r.target, 0))
        if s < floor:
            r.status = FERecStatus.EXPIRED
    recs.sort(key=lambda x: (-_score(x), recent_load.get(x.target, 0)))
    return recs


# ═══════════════════════════════════════════════════════════════════
# Applier (dormant in OBSERVE)
# ═══════════════════════════════════════════════════════════════════

class ApplierGuardBlocked(Exception):
    pass


async def apply_recommendation(
    r: FactoryRecommendation, *, applied_by: str,
) -> Optional[FactoryApplication]:
    cur = fecfg.mode()
    if not FEMode.can_apply(cur):
        raise ApplierGuardBlocked(f"mode={cur} — apply blocked")
    if cur == FEMode.AUTONOMOUS:
        if not fecfg.autonomous_confirm():
            raise ApplierGuardBlocked(
                "FACTORY_EVAL_AUTONOMOUS_CONFIRM=YES not set")
        if r.surface not in fecfg.autonomous_whitelist():
            raise ApplierGuardBlocked(
                f"surface {r.surface} not in autonomous_whitelist")
    if abs(r.proposed_delta) > fecfg.max_delta_per_tick() + 1e-9:
        raise ApplierGuardBlocked(
            f"|delta|={abs(r.proposed_delta)} > max_delta_per_tick")
    cap = fecfg.class_caps().get(r.surface, 0.10)
    recent = await ledger.read_applications(target=r.target, limit=1000)
    cutoff = datetime.now(timezone.utc).timestamp() - 86400
    cum = 0.0
    for a in recent:
        try:
            ts = datetime.fromisoformat(a.applied_at.replace("Z", "+00:00")).timestamp()
        except (ValueError, TypeError):
            continue
        if ts >= cutoff:
            cum += abs(a.new_value - a.previous_value)
    if cum + abs(r.proposed_delta) > cap + 1e-9:
        raise ApplierGuardBlocked(f"class cap {cap} exceeded")

    prev_row = await ledger.read_override(r.target)
    previous = float(prev_row["value"]) if prev_row else float(r.current_value)
    await ledger.upsert_override(r.target, r.proposed_value, source=applied_by)

    app = FactoryApplication(
        application_id="fe_app_" + uuid.uuid4().hex[:12],
        recommendation_id=r.recommendation_id, target=r.target,
        previous_value=previous, new_value=float(r.proposed_value),
        applied_at=_now_iso(), applied_by=applied_by, mode=cur,
        reversible=True,
    )
    await ledger.upsert_application(app)
    await ledger.update_recommendation_status(
        r.recommendation_id, FERecStatus.APPLIED,
        reason=f"applied by {applied_by}")

    await explainability.emit(
        "factory_eval_application",
        reason=f"applied {r.target}: {previous} → {r.proposed_value}",
        metrics={"recommendation_id": r.recommendation_id,
                  "target": r.target,
                  "previous_value": previous,
                  "new_value": float(r.proposed_value),
                  "mode": cur},
        evidence={"application_id": app.application_id,
                   "applied_by": applied_by},
    )
    return app


async def revert_override(target: str, *, reason: str = "") -> bool:
    prev_row = await ledger.read_override(target)
    if not prev_row:
        return False
    if not await ledger.delete_override(target):
        return False
    await explainability.emit(
        "factory_eval_revert",
        reason=f"reverted override on {target}: {reason}",
        metrics={"target": target,
                  "previous_value": prev_row.get("value")},
        evidence={"source": prev_row.get("source"), "reason": reason},
    )
    return True


# ═══════════════════════════════════════════════════════════════════
# Engine — full cycle orchestration
# ═══════════════════════════════════════════════════════════════════

async def run_factory_evaluation_cycle(*, force: bool = False,
                                          daily: bool = False,
                                          ) -> Dict[str, Any]:
    """Execute one factory-evaluation cycle. `daily=True` uses the
    long 90-day window (Q1 daily report). `force=True` runs even in
    disabled mode for diagnostics — but still writes nothing to
    overrides when mode ≠ recommend/autonomous."""
    from . import collectors
    from .evaluators import (
        evaluate_bottleneck, evaluate_compute_allocation, evaluate_coverage_gaps,
        evaluate_execution_quality_ranking, evaluate_factory_improvement,
        evaluate_portfolio_health_trends, evaluate_provider_efficiency,
        evaluate_regime_effectiveness, evaluate_research_roi,
        evaluate_strategy_ranking,
    )

    t0 = time.time()
    cycle_id = "fe_cycle_" + uuid.uuid4().hex[:10]
    cur_mode = fecfg.mode()

    if cur_mode == FEMode.DISABLED and not force:
        return {"cycle_id": cycle_id, "mode": cur_mode,
                "skipped": True, "reason": "FACTORY_EVAL_MODE=disabled"}

    window_h = (fecfg.window_hours_long() if daily
                else fecfg.window_hours_short())
    min_n = fecfg.min_samples()
    now = datetime.now(timezone.utc)
    win_start = (now - timedelta(hours=window_h)).isoformat()
    win_end = now.isoformat()

    await explainability.emit(
        "factory_eval_cycle_start",
        reason=f"cycle={cycle_id} mode={cur_mode} window={window_h}h daily={daily}",
        metrics={"cycle_id": cycle_id, "mode": cur_mode,
                  "window_hours": window_h, "min_samples": min_n,
                  "daily": daily},
        evidence={},
    )

    # ── Collectors ──────────────────────────────────────
    kpis_now = await collectors.collect_factory_kpis(window_h)
    kpis_prev = await collectors.collect_factory_kpis(window_h * 2)
    # Prev = broader window; use as baseline (approximation for delta)
    providers = await collectors.collect_provider_metrics(window_h)
    research = await collectors.collect_research_metrics(window_h)
    strategies = await collectors.collect_strategy_contributions(window_h)
    regimes = await collectors.collect_regime_performance(window_h)
    paths = await collectors.collect_execution_paths(window_h)
    trends = await collectors.collect_portfolio_trends(window_h)
    bottleneck = await collectors.collect_bottleneck_metrics()

    # ── Build report ────────────────────────────────────
    report_id = "fe_report_" + uuid.uuid4().hex[:10]
    report = FactoryReport(
        report_id=report_id,
        window_start=win_start, window_end=win_end,
        cycle_ts=_now_iso(), mode=cur_mode,
        kpis=kpis_now, provider_summary=providers,
        research_summary=research, strategy_summary={
            "n_strategies": len(strategies),
            "top_n_realised_pnl": sum(
                s.get("realised_pnl", 0.0) for _, s in sorted(
                    strategies.items(),
                    key=lambda kv: kv[1].get("realised_pnl", 0.0),
                    reverse=True)[:30]),
        },
        regime_summary=regimes, bottleneck_summary=bottleneck,
        execution_summary={"n_paths": len(paths)},
        portfolio_summary={"n_master_bots": len(trends)},
        evidence_ref={"cycle_id": cycle_id, "daily": daily},
        computed_at=_now_iso(),
    )
    await ledger.upsert_report(report)
    await explainability.emit(
        "factory_report",
        reason=f"report={report_id} window={window_h}h",
        metrics={"report_id": report_id, "cycle_id": cycle_id,
                  "n_kpis": len(kpis_now)},
        evidence={"kpis": kpis_now},
    )

    # ── Evaluators ──────────────────────────────────────
    insights: List[FactoryInsight] = []
    try:
        insights += evaluate_factory_improvement(
            kpis_now, kpis_prev, report_id=report_id,
            window_start=win_start, window_end=win_end)
        insights += evaluate_provider_efficiency(
            providers, report_id=report_id,
            window_start=win_start, window_end=win_end, min_samples=min_n)
        insights += evaluate_research_roi(
            research, report_id=report_id,
            window_start=win_start, window_end=win_end, min_samples=min_n)
        insights += evaluate_strategy_ranking(
            strategies, report_id=report_id,
            window_start=win_start, window_end=win_end)
        insights += evaluate_regime_effectiveness(
            regimes, report_id=report_id,
            window_start=win_start, window_end=win_end)
        insights += evaluate_bottleneck(
            bottleneck, report_id=report_id,
            window_start=win_start, window_end=win_end)
        insights += evaluate_compute_allocation(
            kpis_now, report_id=report_id,
            window_start=win_start, window_end=win_end)
        insights += evaluate_execution_quality_ranking(
            paths, report_id=report_id,
            window_start=win_start, window_end=win_end)
        insights += evaluate_portfolio_health_trends(
            trends, report_id=report_id,
            window_start=win_start, window_end=win_end)
        insights += evaluate_coverage_gaps(
            strategies, report_id=report_id,
            window_start=win_start, window_end=win_end)
    except Exception:  # noqa: BLE001
        logger.exception("[factory_eval] evaluators failed")

    for i in insights:
        await ledger.upsert_insight(i)
        await explainability.emit(
            "factory_eval_insight",
            reason=f"{i.surface}:{i.target} sig={i.significance}",
            metrics={"insight_id": i.insight_id, "surface": i.surface,
                      "target": i.target, "severity": i.severity,
                      "cycle_id": cycle_id},
            evidence={"method": i.method, "metrics": i.metrics},
        )

    # ── Proposers ───────────────────────────────────────
    recs: List[FactoryRecommendation] = []
    try:
        for ins in insights:
            recs += propose_compute_reallocation(ins, mode=cur_mode)
            recs += propose_execution_path_pref(ins, mode=cur_mode)
            recs += propose_strategy_pruning(ins, mode=cur_mode)
            recs += propose_portfolio_rebalance_hint(ins, mode=cur_mode)
            recs += propose_research_investment(ins, mode=cur_mode)
            recs += propose_budget_reallocation(ins, mode=cur_mode)
    except Exception:  # noqa: BLE001
        logger.exception("[factory_eval] proposers failed")

    # ── Ranker ──────────────────────────────────────────
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

    for r in recs:
        await ledger.upsert_recommendation(r)
        await explainability.emit(
            "factory_eval_recommendation",
            reason=(f"{r.surface}:{r.target} conf={r.confidence} "
                     f"band={r.risk_band} status={r.status}"),
            metrics={"recommendation_id": r.recommendation_id,
                      "surface": r.surface, "target": r.target,
                      "confidence": r.confidence,
                      "risk_band": r.risk_band,
                      "severity": r.severity,
                      "status": r.status,
                      "cycle_id": cycle_id},
            evidence={**(r.evidence or {})},
        )

    # ── Autonomous auto-apply (dormant unless mode + confirm + whitelist) ──
    applied = 0
    if cur_mode == FEMode.AUTONOMOUS and fecfg.autonomous_confirm():
        whitelist = fecfg.autonomous_whitelist()
        for r in recs:
            if r.status != FERecStatus.PENDING: continue
            if r.surface not in whitelist: continue
            if r.risk_band != FERiskBand.GREEN: continue  # only green auto-applies
            try:
                app = await apply_recommendation(r, applied_by="autonomous")
                if app is not None:
                    applied += 1
            except ApplierGuardBlocked as e:
                logger.warning("[factory_eval] auto-apply blocked: %s", e)

    duration_ms = int((time.time() - t0) * 1000)
    summary = {
        "cycle_id": cycle_id, "report_id": report_id, "mode": cur_mode,
        "daily": daily, "window_hours": window_h,
        "n_insights": len(insights),
        "n_recommendations": len([r for r in recs
                                   if r.status == FERecStatus.PENDING]),
        "n_expired": len([r for r in recs
                            if r.status == FERecStatus.EXPIRED]),
        "n_applied": applied, "duration_ms": duration_ms,
    }
    await explainability.emit(
        "factory_eval_cycle_end",
        reason=(f"cycle={cycle_id} insights={summary['n_insights']} "
                 f"recs={summary['n_recommendations']} applied={applied}"),
        metrics=summary, evidence={},
    )
    logger.info("[factory_eval] cycle=%s summary=%s", cycle_id, summary)
    return summary
