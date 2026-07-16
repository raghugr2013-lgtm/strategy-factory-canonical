"""Phase I — execution_quality_gate evaluator (§7.6).

Reads `execution_attribution.delta_predicted_realised` distribution
per broker/pair. If p95 negative delta is severely below zero over a
minimum sample count, recommend tightening `EXEC_QUALITY_MIN_SCORE`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..stats import mean
from ..types import MetaEvaluation, MetaSurface

METHOD = "delta_predicted_realised_p95_v1"


def _percentile(xs: List[float], p: float) -> float:
    xs = sorted(xs)
    if not xs:
        return 0.0
    k = max(0, min(len(xs) - 1, int(round(p * (len(xs) - 1)))))
    return xs[k]


def evaluate_execution_quality_gate(
    realised: List[Dict[str, Any]], *, window_start: str, window_end: str,
    min_samples: int,
) -> List[MetaEvaluation]:
    if not realised:
        return []
    computed_at = datetime.now(timezone.utc).isoformat()

    # Group deltas by pair (from evidence.request_id has no pair; fall back to global).
    by_pair: Dict[str, List[float]] = {}
    for row in realised:
        m = row.get("metrics") or {}
        delta = m.get("delta_predicted_realised")
        if delta is None:
            continue
        try:
            d = float(delta)
        except (TypeError, ValueError):
            continue
        pair = str(m.get("pair") or "ALL")
        by_pair.setdefault(pair, []).append(d)

    evaluations: List[MetaEvaluation] = []
    for pair, deltas in by_pair.items():
        n = len(deltas)
        p95_neg = _percentile(deltas, 0.05)  # 5th percentile (most negative)
        mean_delta = mean(deltas)
        eid = "ml_eval_" + uuid.uuid4().hex[:12]
        evaluations.append(MetaEvaluation(
            evaluation_id=eid, account_id=None,
            surface=MetaSurface.EXECUTION_GATE,
            target=f"EXEC_QUALITY_MIN_SCORE:{pair}",
            window_start=window_start, window_end=window_end,
            n_samples=n,
            method=METHOD if n >= max(30, min_samples // 2) else METHOD + "_n_low",
            metrics={"p95_neg_delta": round(p95_neg, 4),
                      "mean_delta": round(mean_delta, 4)},
            significance=round(min(1.0, abs(p95_neg) * 5.0), 4),
            evidence={"pair": pair, "n_samples": n},
            computed_at=computed_at,
        ))
    return evaluations
