"""Split evaluation model for strategies.

Phase 1.5 (historical KB audit) exposed that the legacy ``verdict``
field conflated two orthogonal concerns: *overfit risk* (a validity
concern) and *actual P&L outcome* (an outcome concern). 100% of the
imported corpus carried ``verdict = RISKY``, yet 28% actually produced
positive returns with PF > 1.0.

This module replaces the collapsed verdict with **six independent
dimensions**, each on a well-defined 0..100 scale (or an enum where
categorical is more honest than numeric). No dimension is derived from
another — they measure genuinely different things.

Usage:

    >>> ev = evaluate_from_legacy_metrics({
    ...     "profit_factor": 1.28,
    ...     "total_return_pct": 59.68,
    ...     "stability_score": 89.1,
    ...     "max_drawdown_pct": 0.02,
    ...     "win_rate": 39.2,
    ...     "total_trades": 441,
    ...     "oos_holdout": None,
    ... })
    >>> ev.deployment_readiness
    <DeploymentReadiness.PENDING_VALIDATION: 'pending_validation'>

The engine is *deliberately not deployment-authoritative*: it emits an
opinion, not an approval. The current-framework governance pipeline
retains final say over deployment admission.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel, Field


class DeploymentReadiness(str, Enum):
    """Enum for the deployment-readiness dimension.

    The four values are ordered from most-restrictive to most-permissive.
    Only ``READY`` is eligible for deployment queue admission, and even
    then only after the current-framework governance pipeline signs off.
    """

    NOT_READY = "not_ready"
    PENDING_VALIDATION = "pending_validation"
    NEEDS_OOS_HOLDOUT = "needs_oos_holdout"
    READY = "ready"


class StrategyEvaluation(BaseModel):
    """Six-dimensional evaluation of a strategy.

    Every dimension is independently derivable and independently
    consumable. Dashboards should render them as six separate signals
    (chart / gauge / chip), never collapsed into a single traffic-light
    verdict.
    """

    profitability: float | None = Field(
        None, ge=0, le=100,
        description="How well the strategy converts trades into P&L. "
                    "Compound of profit_factor (60%) and total_return (40%)."
    )
    robustness: float | None = Field(
        None, ge=0, le=100,
        description="Stability across sample windows. Penalised 30% if "
                    "no OOS holdout is available."
    )
    overfit_risk: float | None = Field(
        None, ge=0, le=100,
        description="Higher = more likely overfit. Derived from the "
                    "legacy 'overfit' score if present; otherwise "
                    "inferred from stability inversion. **Independent of "
                    "profitability** — a strategy can be profitable AND "
                    "overfit."
    )
    deployment_readiness: DeploymentReadiness = Field(
        DeploymentReadiness.NOT_READY,
        description="Gate for deployment admission. Never READY for KB "
                    "entries — those require full re-validation first."
    )
    confidence: float | None = Field(
        None, ge=0, le=100,
        description="How much evidence backs the other five dimensions. "
                    "Function of trade count and OOS coverage."
    )
    pass_probability: float | None = Field(
        None, ge=0, le=100,
        description="Estimated probability the strategy passes a live "
                    "forward-test. **Zero across 100% of the historical "
                    "corpus** — flagged as data-quality concern in "
                    "Phase 1.5 §10.A4; treat with scepticism until the "
                    "current-framework estimator is verified."
    )


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _profitability(pf: float, ret: float) -> float:
    pf_norm = _clip((pf - 0.5) / 1.5 * 100)
    ret_norm = _clip((ret + 100) / 2)
    return round(0.6 * pf_norm + 0.4 * ret_norm, 2)


def _robustness(stability: float, has_oos: bool) -> float:
    r = stability
    if not has_oos:
        r *= 0.7  # 30% penalty per §5 of Phase 1.5 rubric
    return round(_clip(r), 2)


def _overfit_risk(legacy_scores: Mapping[str, Any] | None, stability: float) -> float:
    """Prefer explicit `overfit` from legacy decision if present.

    Otherwise fall back to inverted stability — a stable strategy has
    lower overfit risk. This inversion is coarse and should be replaced
    by the current-framework's overfit estimator once available.
    """
    if legacy_scores and legacy_scores.get("overfit") is not None:
        try:
            return round(_clip(float(legacy_scores["overfit"])), 2)
        except (TypeError, ValueError):
            pass
    return round(_clip(100 - stability), 2)


def _confidence(total_trades: int, has_oos: bool) -> float:
    trade_conf = _clip(total_trades / 500 * 100) if total_trades else 0.0
    oos_bonus = 20.0 if has_oos else 0.0
    return round(_clip(0.8 * trade_conf + oos_bonus), 2)


def _readiness(
    profit: float, robust: float, overfit: float, has_oos: bool
) -> DeploymentReadiness:
    if not has_oos:
        return DeploymentReadiness.NEEDS_OOS_HOLDOUT
    if profit < 50 or robust < 50:
        return DeploymentReadiness.NOT_READY
    if overfit > 60:
        return DeploymentReadiness.NOT_READY
    return DeploymentReadiness.PENDING_VALIDATION
    # NB: PENDING_VALIDATION is the ceiling this function will award.
    # Only the current-framework governance pipeline can promote to
    # READY — and only after a live re-validation pass. This function
    # is deliberately incapable of emitting READY.


def evaluate_from_legacy_metrics(
    metrics: Mapping[str, Any],
    legacy_decision_scores: Mapping[str, Any] | None = None,
) -> StrategyEvaluation:
    """Compute the six dimensions from a historical metrics dict.

    ``metrics`` matches the shape stored in ``strategy_library``:
    ``profit_factor``, ``total_return_pct``, ``stability_score``,
    ``max_drawdown_pct``, ``win_rate``, ``total_trades``, ``oos_holdout``,
    ``pass_probability`` (legacy).

    ``legacy_decision_scores`` optionally supplies the nested
    ``decision.scores`` dict from the legacy verdict record (e.g.
    ``overfit``, ``ev_grade``).
    """
    m = metrics or {}
    pf = float(m.get("profit_factor") or 0)
    ret = float(m.get("total_return_pct") or 0)
    stab = float(m.get("stability_score") or 0)
    trades = int(m.get("total_trades") or 0)
    has_oos = bool(m.get("oos_holdout"))

    prof = _profitability(pf, ret)
    robust = _robustness(stab, has_oos)
    overfit = _overfit_risk(legacy_decision_scores, stab)
    conf = _confidence(trades, has_oos)
    ready = _readiness(prof, robust, overfit, has_oos)

    legacy_pp = m.get("pass_probability")
    try:
        pp = round(_clip(float(legacy_pp)), 2) if legacy_pp is not None else None
    except (TypeError, ValueError):
        pp = None

    return StrategyEvaluation(
        profitability=prof,
        robustness=robust,
        overfit_risk=overfit,
        deployment_readiness=ready,
        confidence=conf,
        pass_probability=pp,
    )
