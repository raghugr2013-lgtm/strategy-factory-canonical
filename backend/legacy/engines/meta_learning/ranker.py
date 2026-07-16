"""Phase I — Ranker.

Score = expected_uplift × confidence × (1 − risk_penalty(risk_band))
Ties broken by lowest recent-application load. Recommendations
below `META_LEARNING_RANK_FLOOR` are marked EXPIRED and preserved
for audit but hidden from `/pending`.
"""
from __future__ import annotations

from typing import Dict, List

from . import config as mlcfg
from .types import MetaRecStatus, MetaRecommendation, MetaRiskBand


_RISK_PENALTY = {
    MetaRiskBand.GREEN: 0.0,
    MetaRiskBand.AMBER: 0.5,
    MetaRiskBand.RED:   1.0,
}


def _score(r: MetaRecommendation) -> float:
    penalty = _RISK_PENALTY.get(r.risk_band, 1.0)
    return float(r.expected_uplift) * float(r.confidence) * (1.0 - penalty)


def rank_and_filter(
    recs: List[MetaRecommendation],
    *, recent_load: Dict[str, int] = None,
) -> List[MetaRecommendation]:
    """Return the input list mutated in place: sorted DESC by score;
    below-floor recommendations have status set to EXPIRED.
    """
    recent_load = recent_load or {}
    floor = mlcfg.rank_floor()
    for r in recs:
        r_score = _score(r)
        # Store the score inline for API introspection.
        r.evidence = dict(r.evidence or {})
        r.evidence["ranker_score"] = round(r_score, 6)
        r.evidence["recent_load"] = int(recent_load.get(r.target, 0))
        if r_score < floor:
            r.status = MetaRecStatus.EXPIRED
    recs.sort(key=lambda x: (
        -_score(x),
        recent_load.get(x.target, 0),
    ))
    return recs
