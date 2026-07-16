"""Phase I — weight_sensitivity evaluator (§7.1).

For each scoring weight (BRAIN_W_*), compute Pearson correlation
between the weighted component contribution at decision time and the
realised normalised PnL. Returns one MetaEvaluation per weight.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..stats import normalise_pnl, pearson, spearman
from ..types import MetaEvaluation, MetaSurface


# Target env-var keys must match brain/config.py exactly.
WEIGHT_TARGETS = {
    "regime_fit":       "BRAIN_W_REGIME_FIT",
    "confidence":       "BRAIN_W_CONFIDENCE",
    "recent_pf":        "BRAIN_W_RECENT_PF",
    "long_pf":          "BRAIN_W_LONG_PF",
    "dd_penalty":       "BRAIN_W_DD",
    "prediction_acc":   "BRAIN_W_PRED_ACC",
    "corr_penalty":     "BRAIN_W_CORR",
    "session_fit":      "BRAIN_W_SESSION",
    "liquidity_fit":    "BRAIN_W_LIQUIDITY",
    "market_confidence":"BRAIN_W_MARKET_CONFIDENCE",
    "style_confidence": "BRAIN_W_STYLE_CONFIDENCE",
    "opportunity":      "BRAIN_W_OPPORTUNITY",
}

METHOD = "pearson+spearman_component_vs_realised_pnl_v1"


def evaluate_weight_sensitivity(
    pairs: List[Dict[str, Any]], *, window_start: str, window_end: str,
    min_samples: int,
) -> List[MetaEvaluation]:
    """`pairs`: list of {"decision":..., "realised":...} joined by
    `brain_decision_id` (via collectors.execution_realised.join)."""
    if not pairs:
        return []
    computed_at = datetime.now(timezone.utc).isoformat()
    evaluations: List[MetaEvaluation] = []

    # Extract normalised outcome per pair.
    outcomes = []
    for p in pairs:
        r = (p.get("realised") or {}).get("metrics") or {}
        pnl = float(r.get("realised_pnl") or 0.0)
        outcomes.append(normalise_pnl(pnl))

    for comp_key, env_target in WEIGHT_TARGETS.items():
        xs: List[float] = []
        ys: List[float] = []
        evidence_ids: List[str] = []
        for i, p in enumerate(pairs):
            d = p.get("decision") or {}
            m = d.get("metrics") or {}
            comps = (m.get("components") or m.get("brain_components") or {})
            if not isinstance(comps, dict):
                continue
            v = comps.get(comp_key)
            if v is None:
                continue
            try:
                xs.append(float(v))
                ys.append(outcomes[i])
                evidence_ids.append(str(d.get("_id", "")))
            except (TypeError, ValueError):
                continue

        n = len(xs)
        r = pearson(xs, ys) if n >= 3 else 0.0
        rs = spearman(xs, ys) if n >= 3 else 0.0
        significance = min(abs(r), abs(rs))

        eval_id = "ml_eval_" + uuid.uuid4().hex[:12]
        evaluations.append(MetaEvaluation(
            evaluation_id=eval_id,
            account_id=None,
            surface=MetaSurface.BRAIN_WEIGHT,
            target=env_target,
            window_start=window_start,
            window_end=window_end,
            n_samples=n,
            method=METHOD if n >= min_samples else METHOD + "_n_low",
            metrics={
                "pearson": round(r, 4),
                "spearman": round(rs, 4),
                "mean_component": round(sum(xs) / n, 4) if n else 0.0,
                "mean_outcome":   round(sum(ys) / n, 4) if n else 0.0,
            },
            significance=round(significance, 4),
            evidence={
                "component_key": comp_key,
                "sample_ids": evidence_ids[:20],  # cap for storage
                "total_evidence": len(evidence_ids),
            },
            computed_at=computed_at,
        ))
    return evaluations
