"""Phase I — Proposers (evaluation → recommendation).

Each proposer consumes MetaEvaluation rows for its target surface
and emits MetaRecommendation candidates. Recommendations are:
  * bounded by max_delta_per_tick
  * guarded by sig_threshold on evaluation.significance
  * carry a full evidence chain (evaluation_id + inputs)
  * tagged with severity + risk_band
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from . import config as mlcfg
from .stats import clamp, p_value_from_r
from .types import (
    MetaEvaluation, MetaRecStatus, MetaRecommendation, MetaRiskBand,
    MetaSeverity, MetaSurface,
)


def _severity(magnitude: float) -> str:
    a = abs(magnitude)
    if a < 0.005: return MetaSeverity.INFO
    if a < 0.015: return MetaSeverity.LOW
    if a < 0.04:  return MetaSeverity.MED
    return MetaSeverity.HIGH


def _risk_band(surface: str, delta: float, *, first_activation: bool = False) -> str:
    """Design §Q8: green/amber/red classifier."""
    a = abs(delta)
    if first_activation:
        return MetaRiskBand.RED
    if surface == MetaSurface.BRAIN_WEIGHT and a <= 0.02:
        return MetaRiskBand.GREEN
    if a <= 0.10 and surface in (MetaSurface.BRAIN_THRESHOLD, MetaSurface.MARKET_WEIGHT):
        return MetaRiskBand.AMBER
    if a > 0.10:
        return MetaRiskBand.RED
    return MetaRiskBand.AMBER


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_iso() -> str:
    return (datetime.now(timezone.utc)
            + timedelta(days=mlcfg.rec_ttl_days())).isoformat()


def _new_rec_id() -> str:
    return "ml_rec_" + uuid.uuid4().hex[:12]


def _passes_significance(ev: MetaEvaluation) -> bool:
    """Q5: require both |ρ| ≥ threshold AND p-value < 0.05."""
    thr = mlcfg.sig_threshold()
    if ev.significance < thr:
        return False
    r = float(ev.metrics.get("pearson") or ev.significance)
    if p_value_from_r(r, ev.n_samples) >= 0.05:
        return False
    return True


def _below_min_samples(ev: MetaEvaluation) -> bool:
    return ev.n_samples < mlcfg.min_samples()


def propose_brain_weight(
    ev: MetaEvaluation, *, current: float, mode: str,
) -> List[MetaRecommendation]:
    if ev.surface != MetaSurface.BRAIN_WEIGHT:
        return []
    if _below_min_samples(ev) or not _passes_significance(ev):
        return []
    r = float(ev.metrics.get("pearson") or 0.0)
    step = mlcfg.weight_step()
    max_d = mlcfg.max_delta_per_tick()
    delta = clamp(r * step * 10.0, -max_d, +max_d)  # scale-up factor
    if abs(delta) < 1e-4:
        return []
    proposed = clamp(current + delta, 0.0, 1.0)
    delta_final = proposed - current
    return [MetaRecommendation(
        recommendation_id=_new_rec_id(),
        evaluation_id=ev.evaluation_id,
        surface=ev.surface, target=ev.target,
        current_value=round(current, 6),
        proposed_value=round(proposed, 6),
        proposed_delta=round(delta_final, 6),
        expected_uplift=round(abs(r) * abs(delta_final), 6),
        confidence=round(ev.significance, 4),
        severity=_severity(delta_final),
        risk_band=_risk_band(ev.surface, delta_final),
        rationale=f"pearson={r:+.3f} n={ev.n_samples} → nudge weight by {delta_final:+.4f}",
        evidence={"evaluation_id": ev.evaluation_id,
                   "n_samples": ev.n_samples,
                   "sample_ids": ev.evidence.get("sample_ids", [])[:10]},
        guardrails={"max_delta_per_tick": max_d,
                     "weight_step": step,
                     "sig_threshold": mlcfg.sig_threshold()},
        mode=mode, status=MetaRecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


def propose_brain_threshold(
    ev: MetaEvaluation, *, current: float, mode: str,
) -> List[MetaRecommendation]:
    if ev.surface != MetaSurface.BRAIN_THRESHOLD:
        return []
    if _below_min_samples(ev):
        return []
    gap = float(ev.metrics.get("gap") or 0.0)
    if abs(gap) < 0.02:
        return []
    delta = clamp(gap, -0.05, +0.05)
    proposed = clamp(current + delta, 0.0, 1.0)
    return [MetaRecommendation(
        recommendation_id=_new_rec_id(),
        evaluation_id=ev.evaluation_id,
        surface=ev.surface, target=ev.target,
        current_value=round(current, 6),
        proposed_value=round(proposed, 6),
        proposed_delta=round(proposed - current, 6),
        expected_uplift=round(float(ev.metrics.get("score_at_optimal") or 0.0), 6),
        confidence=round(ev.significance, 4),
        severity=_severity(proposed - current),
        risk_band=_risk_band(ev.surface, proposed - current),
        rationale=f"optimal={ev.metrics.get('optimal_estimate')} vs current={current}",
        evidence={"evaluation_id": ev.evaluation_id},
        guardrails={"max_delta_step": 0.05},
        mode=mode, status=MetaRecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


def propose_market_weight(
    ev: MetaEvaluation, *, current: float, mode: str,
) -> List[MetaRecommendation]:
    """First-activation gate: from 0.0, cap first recommendation at 0.05."""
    if ev.surface != MetaSurface.MARKET_WEIGHT:
        return []
    if _below_min_samples(ev) or not _passes_significance(ev):
        return []
    r = float(ev.metrics.get("pearson") or 0.0)
    if abs(r) < mlcfg.sig_threshold():
        return []

    first_activation = current == 0.0
    max_d = 0.05 if first_activation else mlcfg.max_delta_per_tick()
    delta = clamp(r * mlcfg.weight_step() * 10.0, -max_d, +max_d)
    proposed = clamp(current + delta, 0.0, 1.0)
    return [MetaRecommendation(
        recommendation_id=_new_rec_id(),
        evaluation_id=ev.evaluation_id,
        surface=ev.surface, target=ev.target,
        current_value=round(current, 6),
        proposed_value=round(proposed, 6),
        proposed_delta=round(proposed - current, 6),
        expected_uplift=round(abs(r) * abs(delta), 6),
        confidence=round(ev.significance, 4),
        severity=_severity(proposed - current),
        risk_band=_risk_band(ev.surface, proposed - current,
                              first_activation=first_activation),
        rationale=(f"first-activation cap 0.05" if first_activation
                     else f"pearson={r:+.3f}"),
        evidence={"evaluation_id": ev.evaluation_id,
                   "first_activation": first_activation},
        guardrails={"max_delta_first_activation": 0.05},
        mode=mode, status=MetaRecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


def propose_execution_gate(
    ev: MetaEvaluation, *, current: float, mode: str,
) -> List[MetaRecommendation]:
    if ev.surface != MetaSurface.EXECUTION_GATE:
        return []
    p95_neg = float(ev.metrics.get("p95_neg_delta") or 0.0)
    if p95_neg >= -0.15:  # not severe enough
        return []
    delta = clamp(abs(p95_neg) * 0.10, 0.005, 0.05)  # tighten
    proposed = clamp(current + delta, 0.0, 1.0)
    return [MetaRecommendation(
        recommendation_id=_new_rec_id(),
        evaluation_id=ev.evaluation_id,
        surface=ev.surface, target=ev.target,
        current_value=round(current, 6),
        proposed_value=round(proposed, 6),
        proposed_delta=round(delta, 6),
        expected_uplift=round(abs(p95_neg) * 0.5, 6),
        confidence=round(ev.significance, 4),
        severity=MetaSeverity.MED,
        risk_band=MetaRiskBand.AMBER,
        rationale=f"p95_neg_delta={p95_neg} → tighten gate",
        evidence={"evaluation_id": ev.evaluation_id,
                   "p95_neg_delta": p95_neg},
        guardrails={"max_delta_per_tick": 0.05},
        mode=mode, status=MetaRecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]


def propose_confidence_calibration(
    ev: MetaEvaluation, *, current: float, mode: str,
) -> List[MetaRecommendation]:
    if ev.surface != MetaSurface.CONFIDENCE_CALIBRATION:
        return []
    if _below_min_samples(ev):
        return []
    gap = float(ev.metrics.get("mean_gap") or 0.0)
    if gap < mlcfg.calib_gap_min():
        return []
    # If confidence is systematically higher than realised → shrink toward 1 - gap
    delta = clamp(-gap * 0.5, -0.10, 0.0)
    proposed = clamp(current + delta, 0.0, 1.0)
    if abs(delta) < 1e-4:
        return []
    return [MetaRecommendation(
        recommendation_id=_new_rec_id(),
        evaluation_id=ev.evaluation_id,
        surface=ev.surface, target=ev.target,
        current_value=round(current, 6),
        proposed_value=round(proposed, 6),
        proposed_delta=round(delta, 6),
        expected_uplift=round(gap, 6),
        confidence=round(ev.significance, 4),
        severity=_severity(delta),
        risk_band=_risk_band(ev.surface, delta),
        rationale=f"mean_reliability_gap={gap:.3f} → shrink confidence",
        evidence={"evaluation_id": ev.evaluation_id},
        guardrails={"max_delta_step": 0.10},
        mode=mode, status=MetaRecStatus.PENDING,
        created_at=_now_iso(), expires_at=_expires_iso(),
    )]
