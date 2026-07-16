"""Phase J — Consolidated evaluators (pure functions).

Each evaluator consumes collector outputs (dicts) + returns a list of
FactoryInsight rows. Deterministic. No side effects.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from .types import FactoryInsight, FESeverity, FESurface


def _eid() -> str:
    return "fe_insight_" + uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _severity(magnitude: float, thresholds=(0.01, 0.05, 0.15)) -> str:
    a = abs(magnitude)
    if a < thresholds[0]: return FESeverity.INFO
    if a < thresholds[1]: return FESeverity.LOW
    if a < thresholds[2]: return FESeverity.MED
    return FESeverity.HIGH


# ── 1. factory_improvement ─────────────────────────────────────────
def evaluate_factory_improvement(
    kpis_now: Dict[str, float], kpis_prev: Dict[str, float],
    *, report_id: str, window_start: str, window_end: str,
) -> List[FactoryInsight]:
    """Simple period-over-period comparison of load-bearing KPIs.
    Slope proxied by (now - prev) / max(|prev|, ε)."""
    out: List[FactoryInsight] = []
    track = ("pnl_24h", "prediction_accuracy_30d", "win_rate_24h",
             "broker_health_score_p50", "attribution_coverage_pct",
             "ai_spend_window_usd")
    computed_at = _now()
    for k in track:
        now_v = float(kpis_now.get(k) or 0.0)
        prev_v = float(kpis_prev.get(k) or 0.0)
        delta = now_v - prev_v
        ratio = delta / max(abs(prev_v), 1e-6)
        out.append(FactoryInsight(
            insight_id=_eid(), report_id=report_id,
            surface=FESurface.FACTORY_IMPROVEMENT, target=k,
            window_start=window_start, window_end=window_end,
            n_samples=2, method="period_over_period_v1",
            metrics={"now": round(now_v, 4), "prev": round(prev_v, 4),
                      "delta": round(delta, 4), "ratio": round(ratio, 4)},
            significance=round(min(1.0, abs(ratio)), 4),
            severity=_severity(ratio),
            evidence={"kpi": k, "period_hours": 24},
            computed_at=computed_at,
        ))
    return out


# ── 2. provider_efficiency ─────────────────────────────────────────
def evaluate_provider_efficiency(
    providers: Dict[str, Any], *, report_id: str,
    window_start: str, window_end: str, min_samples: int,
) -> List[FactoryInsight]:
    out = []
    computed_at = _now()
    for prov, st in providers.items():
        n_ev = int(st.get("n_events", 0))
        if n_ev < 3:  # very small floor for warmup
            continue
        method = ("cost_per_pass_v1" if n_ev >= min_samples
                    else "cost_per_pass_v1_n_low")
        # Severity from cost efficiency vs pass count
        cpp = float(st.get("cost_per_pass", 0.0))
        n_pass = int(st.get("n_pass", 0))
        sig = min(1.0, n_ev / max(1, min_samples))
        out.append(FactoryInsight(
            insight_id=_eid(), report_id=report_id,
            surface=FESurface.PROVIDER_EFFICIENCY, target=f"provider:{prov}",
            window_start=window_start, window_end=window_end,
            n_samples=n_ev, method=method,
            metrics={"spend_usd": round(float(st.get("spend_usd", 0.0)), 4),
                      "n_pass": n_pass, "cost_per_pass": round(cpp, 6)},
            significance=round(sig, 4),
            severity=FESeverity.INFO if n_pass else FESeverity.LOW,
            evidence={"provider": prov,
                       "n_models": len(st.get("models", {}))},
            computed_at=computed_at,
        ))
    return out


# ── 3. research_roi ────────────────────────────────────────────────
def evaluate_research_roi(
    research: Dict[str, Any], *, report_id: str,
    window_start: str, window_end: str, min_samples: int,
) -> List[FactoryInsight]:
    """Per-run pass rate + total cost."""
    if not research:
        return []
    out = []
    computed_at = _now()
    # Aggregate by (prompt_version, model)
    grouped: Dict[str, Dict[str, Any]] = {}
    for rid, st in research.items():
        key = f"{st.get('prompt_version') or 'none'}:{st.get('model') or 'unknown'}"
        g = grouped.setdefault(key, {
            "n_runs": 0, "total_cost": 0.0, "total_pass": 0, "total_events": 0,
        })
        g["n_runs"] += 1
        g["total_cost"] += float(st.get("cost_usd", 0.0))
        g["total_pass"] += int(st.get("n_pass", 0))
        g["total_events"] += int(st.get("n_events", 0))
    for key, g in grouped.items():
        if g["n_runs"] < 1:
            continue
        pass_rate = g["total_pass"] / max(1, g["total_events"])
        cost_per_pass = g["total_cost"] / max(1, g["total_pass"])
        out.append(FactoryInsight(
            insight_id=_eid(), report_id=report_id,
            surface=FESurface.RESEARCH_ROI, target=f"group:{key}",
            window_start=window_start, window_end=window_end,
            n_samples=g["n_runs"],
            method=("group_pass_rate_v1" if g["n_runs"] >= 3
                    else "group_pass_rate_v1_n_low"),
            metrics={"n_runs": g["n_runs"],
                      "total_cost_usd": round(g["total_cost"], 4),
                      "pass_rate": round(pass_rate, 4),
                      "cost_per_pass": round(cost_per_pass, 6)},
            significance=round(min(1.0, g["n_runs"] / max(3, min_samples // 10)), 4),
            severity=_severity(pass_rate),
            evidence={"group_key": key},
            computed_at=computed_at,
        ))
    return out


# ── 4. strategy_ranking ────────────────────────────────────────────
def evaluate_strategy_ranking(
    strategies: Dict[str, Any], *, report_id: str,
    window_start: str, window_end: str, top_n: int = 30, bottom_n: int = 30,
) -> List[FactoryInsight]:
    """Rank by realised PnL. Emit top-N + bottom-N insights."""
    if not strategies:
        return []
    ranked = sorted(strategies.items(),
                    key=lambda kv: kv[1].get("realised_pnl", 0.0), reverse=True)
    top = ranked[:top_n]
    bottom = ranked[-bottom_n:] if len(ranked) > top_n else []
    computed_at = _now()
    out: List[FactoryInsight] = []
    for i, (sh, st) in enumerate(top):
        out.append(FactoryInsight(
            insight_id=_eid(), report_id=report_id,
            surface=FESurface.STRATEGY_CONTRIBUTION,
            target=f"top:{sh}",
            window_start=window_start, window_end=window_end,
            n_samples=int(st.get("n_trades", 0)),
            method="realised_pnl_ranked_v1",
            metrics={"rank": i + 1,
                      "realised_pnl": round(float(st.get("realised_pnl", 0.0)), 2),
                      "n_trades": int(st.get("n_trades", 0)),
                      "mean_delta": float(st.get("mean_delta", 0.0))},
            significance=1.0 if float(st.get("realised_pnl", 0.0)) > 0 else 0.3,
            severity=FESeverity.INFO,
            evidence={"strategy_hash": sh, "direction": "top"},
            computed_at=computed_at,
        ))
    for i, (sh, st) in enumerate(bottom):
        pnl = float(st.get("realised_pnl", 0.0))
        out.append(FactoryInsight(
            insight_id=_eid(), report_id=report_id,
            surface=FESurface.STRATEGY_CONTRIBUTION,
            target=f"bottom:{sh}",
            window_start=window_start, window_end=window_end,
            n_samples=int(st.get("n_trades", 0)),
            method="realised_pnl_ranked_v1",
            metrics={"rank": len(ranked) - bottom_n + i + 1,
                      "realised_pnl": round(pnl, 2),
                      "n_trades": int(st.get("n_trades", 0))},
            significance=round(min(1.0, abs(pnl) / 100.0), 4),
            severity=(FESeverity.MED if pnl < 0 else FESeverity.INFO),
            evidence={"strategy_hash": sh, "direction": "bottom"},
            computed_at=computed_at,
        ))
    return out


# ── 5. regime_effectiveness ────────────────────────────────────────
def evaluate_regime_effectiveness(
    regimes: Dict[str, Any], *, report_id: str,
    window_start: str, window_end: str,
) -> List[FactoryInsight]:
    if not regimes:
        return []
    out = []
    computed_at = _now()
    for reg, st in regimes.items():
        n = int(st.get("n", 0))
        if n < 3:
            continue
        out.append(FactoryInsight(
            insight_id=_eid(), report_id=report_id,
            surface=FESurface.REGIME_EFFECTIVENESS, target=f"regime:{reg}",
            window_start=window_start, window_end=window_end,
            n_samples=n, method="per_regime_v1",
            metrics={"mean_pnl": float(st.get("mean_pnl", 0.0)),
                      "hit_rate": float(st.get("hit_rate", 0.0)),
                      "mean_delta": float(st.get("mean_delta", 0.0)),
                      "n_trades": n},
            significance=round(min(1.0, n / 30.0), 4),
            severity=_severity(float(st.get("mean_delta", 0.0)),
                                 thresholds=(0.05, 0.15, 0.30)),
            evidence={"regime": reg},
            computed_at=computed_at,
        ))
    return out


# ── 6. bottleneck_detector ─────────────────────────────────────────
def evaluate_bottleneck(
    bottleneck: Dict[str, Any], *, report_id: str,
    window_start: str, window_end: str,
) -> List[FactoryInsight]:
    """Q6: single summary insight per cycle (not one per signal)."""
    findings: List[Dict[str, Any]] = []
    cp = bottleneck.get("compute_probe") or {}
    if cp:
        band = str(cp.get("band") or "unknown")
        if band in ("warn", "critical"):
            findings.append({"signal": "compute_band", "band": band,
                              "severity": (FESeverity.MED if band == "warn"
                                            else FESeverity.HIGH)})
    qp = bottleneck.get("queue_pressure") or {}
    if qp:
        depth = float(qp.get("depth") or 0.0)
        if depth > 0.75:
            findings.append({"signal": "queue_pressure", "depth": depth,
                              "severity": FESeverity.MED})
    top3 = findings[:3]
    computed_at = _now()
    sev = FESeverity.INFO
    if top3:
        # Escalate to highest finding severity
        levels = {FESeverity.INFO: 0, FESeverity.LOW: 1,
                    FESeverity.MED: 2, FESeverity.HIGH: 3}
        sev = max(top3, key=lambda f: levels.get(f["severity"], 0))["severity"]
    return [FactoryInsight(
        insight_id=_eid(), report_id=report_id,
        surface=FESurface.BOTTLENECK, target="factory:top3",
        window_start=window_start, window_end=window_end,
        n_samples=len(findings), method="top3_summary_v1",
        metrics={"n_findings": len(findings)},
        significance=round(min(1.0, len(top3) / 3.0), 4),
        severity=sev,
        evidence={"findings": top3, "raw": bottleneck},
        computed_at=computed_at,
    )]


# ── 7. compute_allocation ──────────────────────────────────────────
def evaluate_compute_allocation(
    kpis: Dict[str, float], *, report_id: str,
    window_start: str, window_end: str,
) -> List[FactoryInsight]:
    """Heuristic hint: if orchestrator dispatches are low and win_rate
    is low, suggest priority nudge investigation."""
    computed_at = _now()
    n_tasks = float(kpis.get("orchestrator_task_count") or 0.0)
    if n_tasks < 5:
        return []
    return [FactoryInsight(
        insight_id=_eid(), report_id=report_id,
        surface=FESurface.COMPUTE_ALLOCATION,
        target="orchestrator:task_priorities",
        window_start=window_start, window_end=window_end,
        n_samples=int(n_tasks), method="task_priority_review_v1",
        metrics={"n_tasks": n_tasks,
                  "win_rate_24h": float(kpis.get("win_rate_24h") or 0.0)},
        significance=0.4,
        severity=FESeverity.INFO,
        evidence={"note": "diagnostic only; no threshold breach"},
        computed_at=computed_at,
    )]


# ── 8. execution_quality_ranking ───────────────────────────────────
def evaluate_execution_quality_ranking(
    paths: Dict[str, Any], *, report_id: str,
    window_start: str, window_end: str,
) -> List[FactoryInsight]:
    if not paths:
        return []
    ranked = sorted(paths.items(),
                    key=lambda kv: kv[1].get("mean_score", 0.0), reverse=True)
    computed_at = _now()
    out = []
    for i, (key, st) in enumerate(ranked):
        n = int(st.get("n", 0))
        if n < 3:
            continue
        out.append(FactoryInsight(
            insight_id=_eid(), report_id=report_id,
            surface=FESurface.EXECUTION_QUALITY, target=f"path:{key}",
            window_start=window_start, window_end=window_end,
            n_samples=n, method="path_ranking_v1",
            metrics={"rank": i + 1,
                      "mean_score": float(st.get("mean_score", 0.0)),
                      "mean_slippage": float(st.get("mean_slippage", 0.0)),
                      "mean_delta": float(st.get("mean_delta", 0.0))},
            significance=round(min(1.0, n / 30.0), 4),
            severity=FESeverity.INFO,
            evidence={"path_key": key},
            computed_at=computed_at,
        ))
    return out


# ── 9. portfolio_health_trends ─────────────────────────────────────
def evaluate_portfolio_health_trends(
    trends: Dict[str, Any], *, report_id: str,
    window_start: str, window_end: str,
) -> List[FactoryInsight]:
    if not trends:
        return []
    out = []
    computed_at = _now()
    for bid, st in trends.items():
        n = int(st.get("n_events", 0))
        if n < 3:
            continue
        mh = float(st.get("mean_health", 0.0))
        mc = float(st.get("mean_correlation", 0.0))
        me = float(st.get("mean_style_entropy", 0.0))
        # Simple health composite
        health_score = mh - mc * 0.5 + me * 0.3
        out.append(FactoryInsight(
            insight_id=_eid(), report_id=report_id,
            surface=FESurface.PORTFOLIO_HEALTH, target=f"master_bot:{bid}",
            window_start=window_start, window_end=window_end,
            n_samples=n, method="composite_health_v1",
            metrics={"mean_health": round(mh, 4),
                      "mean_correlation": round(mc, 4),
                      "mean_style_entropy": round(me, 4),
                      "composite": round(health_score, 4)},
            significance=round(min(1.0, n / 30.0), 4),
            severity=(FESeverity.HIGH if health_score < 0.3
                        else FESeverity.MED if health_score < 0.5
                        else FESeverity.INFO),
            evidence={"master_bot_id": bid},
            computed_at=computed_at,
        ))
    return out


# ── 10. coverage_gap_detector ──────────────────────────────────────
def evaluate_coverage_gaps(
    strategies: Dict[str, Any], *, report_id: str,
    window_start: str, window_end: str, min_strategies_per_cell: int = 3,
) -> List[FactoryInsight]:
    """Simple diagnostic: count unique strategy hashes as coverage
    proxy. If total < min_strategies_per_cell × 24 (styles × regimes),
    emit a gap insight."""
    n_strategies = len(strategies)
    computed_at = _now()
    target_coverage = min_strategies_per_cell * 24
    return [FactoryInsight(
        insight_id=_eid(), report_id=report_id,
        surface=FESurface.COVERAGE_GAP,
        target="factory:total_active_strategies",
        window_start=window_start, window_end=window_end,
        n_samples=n_strategies, method="total_coverage_v1",
        metrics={"n_strategies": n_strategies,
                  "target_coverage": target_coverage,
                  "gap_ratio": round((target_coverage - n_strategies)
                                        / max(1, target_coverage), 4)},
        significance=round(min(1.0, (target_coverage - n_strategies)
                                  / max(1, target_coverage)), 4),
        severity=(FESeverity.MED if n_strategies < target_coverage // 2
                    else FESeverity.LOW if n_strategies < target_coverage
                    else FESeverity.INFO),
        evidence={"description":
                    "Aggregate coverage proxy. Phase J.2 will add per-cell breakdown."},
        computed_at=computed_at,
    )]
