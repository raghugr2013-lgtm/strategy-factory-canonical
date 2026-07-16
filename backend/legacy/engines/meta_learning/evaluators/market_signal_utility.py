"""Phase I — market_signal_utility evaluator (§7.5).

Same shape as weight_sensitivity but restricted to Phase G additive
weights. First-activation gate: caps recommendation delta at 0.05
when current weight is 0.0 (per design doc).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..stats import normalise_pnl, pearson, spearman
from ..types import MetaEvaluation, MetaSurface

MARKET_TARGETS = {
    "market_confidence": "BRAIN_W_MARKET_CONFIDENCE",
    "style_confidence":  "BRAIN_W_STYLE_CONFIDENCE",
    "opportunity":       "BRAIN_W_OPPORTUNITY",
}
METHOD = "phase_g_signal_utility_v1"


def evaluate_market_signal_utility(
    pairs: List[Dict[str, Any]], *, window_start: str, window_end: str,
    min_samples: int,
) -> List[MetaEvaluation]:
    if not pairs:
        return []
    computed_at = datetime.now(timezone.utc).isoformat()

    outcomes = [normalise_pnl(float((p.get("realised") or {}).get(
        "metrics", {}).get("realised_pnl") or 0.0)) for p in pairs]

    evaluations: List[MetaEvaluation] = []
    for signal_key, env_key in MARKET_TARGETS.items():
        xs: List[float] = []; ys: List[float] = []; ids: List[str] = []
        for i, p in enumerate(pairs):
            d = p.get("decision") or {}
            m = d.get("metrics") or {}
            sig = (m.get("signals") or {}).get(signal_key) if isinstance(
                m.get("signals"), dict) else m.get(signal_key)
            if sig is None:
                continue
            try:
                xs.append(float(sig)); ys.append(outcomes[i])
                ids.append(str(d.get("_id", "")))
            except (TypeError, ValueError):
                continue

        n = len(xs)
        r = pearson(xs, ys) if n >= 3 else 0.0
        rs = spearman(xs, ys) if n >= 3 else 0.0

        eid = "ml_eval_" + uuid.uuid4().hex[:12]
        evaluations.append(MetaEvaluation(
            evaluation_id=eid, account_id=None,
            surface=MetaSurface.MARKET_WEIGHT, target=env_key,
            window_start=window_start, window_end=window_end,
            n_samples=n,
            method=METHOD if n >= min_samples else METHOD + "_n_low",
            metrics={"pearson": round(r, 4), "spearman": round(rs, 4),
                      "signal_key": 0.0},  # signal_key stored in evidence
            significance=round(min(abs(r), abs(rs)), 4),
            evidence={"signal_key": signal_key,
                       "sample_ids": ids[:20], "total_evidence": len(ids)},
            computed_at=computed_at,
        ))
    return evaluations
