"""Phase I — threshold_calibration evaluator (§7.2).

Buckets decisions by `score_now` into 20 bins; computes mean realised
outcome per bin; finds the threshold that maximises
E[outcome | score >= t] × count(score >= t). One evaluation per
threshold env var.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..stats import bin_edges, bin_index, normalise_pnl
from ..types import MetaEvaluation, MetaSurface

THRESHOLD_TARGETS = (
    ("BRAIN_TRADE_NOW_THRESHOLD", "trade_now"),
    ("BRAIN_PAUSE_THRESHOLD",     "pause"),
    ("BRAIN_RETIRE_THRESHOLD",    "retire"),
)

METHOD = "bucketed_expected_uplift_v1"


def _score_from_decision(d: Dict[str, Any]) -> float:
    m = d.get("metrics") or {}
    for k in ("score_now", "score", "brain_score", "activation_score"):
        v = m.get(k)
        if v is not None:
            try: return float(v)
            except (TypeError, ValueError): continue
    return 0.0


def evaluate_threshold_calibration(
    pairs: List[Dict[str, Any]], *, window_start: str, window_end: str,
    min_samples: int, current_values: Dict[str, float],
) -> List[MetaEvaluation]:
    if not pairs:
        return []
    computed_at = datetime.now(timezone.utc).isoformat()

    scores: List[float] = []
    outcomes: List[float] = []
    for p in pairs:
        d = p.get("decision") or {}
        r = (p.get("realised") or {}).get("metrics") or {}
        s = _score_from_decision(d)
        pnl = float(r.get("realised_pnl") or 0.0)
        scores.append(s)
        outcomes.append(normalise_pnl(pnl))

    n = len(scores)
    edges = bin_edges(0.0, 1.0, 20)
    bin_stats: Dict[int, Dict[str, float]] = {}
    for s, o in zip(scores, outcomes):
        b = bin_index(s, edges)
        st = bin_stats.setdefault(b, {"n": 0.0, "sum": 0.0})
        st["n"] += 1.0
        st["sum"] += o

    # Compute optimal threshold: for each candidate t = edge, expected
    # uplift is mean outcome over scores >= t, weighted by count.
    best_t = 0.5
    best_score = -1e9
    for i, t in enumerate(edges[:-1]):
        total_n = 0.0
        total_sum = 0.0
        for b, st in bin_stats.items():
            if edges[b] >= t:
                total_n += st["n"]
                total_sum += st["sum"]
        if total_n < 1:
            continue
        mean_o = total_sum / total_n
        # Score = mean × sqrt(n) to prefer thresholds with statistical mass
        v = mean_o * (total_n ** 0.5)
        if v > best_score:
            best_score = v
            best_t = t

    evaluations: List[MetaEvaluation] = []
    for env_key, label in THRESHOLD_TARGETS:
        current = float(current_values.get(env_key, 0.5))
        eid = "ml_eval_" + uuid.uuid4().hex[:12]
        evaluations.append(MetaEvaluation(
            evaluation_id=eid, account_id=None,
            surface=MetaSurface.BRAIN_THRESHOLD, target=env_key,
            window_start=window_start, window_end=window_end,
            n_samples=n,
            method=METHOD if n >= min_samples else METHOD + "_n_low",
            metrics={
                "current": round(current, 4),
                "optimal_estimate": round(best_t, 4),
                "gap": round(best_t - current, 4),
                "score_at_optimal": round(best_score, 4),
                "n_bins": len(bin_stats),
            },
            significance=round(min(1.0, abs(best_t - current) * 2.0), 4),
            evidence={"label": label,
                       "bin_counts": {str(k): v["n"] for k, v in bin_stats.items()}},
            computed_at=computed_at,
        ))
    return evaluations
