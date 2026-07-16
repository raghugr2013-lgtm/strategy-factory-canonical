"""Observer: correlation_matrix.

Rolling pairwise correlation of THIS pair vs the rest of the observed
universe. High avg-correlation → diversification is failing (a shock
will hit every strategy). Low correlation → healthy universe.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from datetime import datetime, timezone
from math import sqrt

from ..types import MarketSnapshot, ObserverResult


def _returns(closes: List[float]) -> List[float]:
    if len(closes) < 2:
        return []
    return [(closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes)) if closes[i - 1]]


def _pearson(a: List[float], b: List[float]) -> Optional[float]:
    n = min(len(a), len(b))
    if n < 5:
        return None
    a = a[-n:]; b = b[-n:]
    mean_a = sum(a) / n; mean_b = sum(b) / n
    num = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
    den_a = sqrt(sum((x - mean_a) ** 2 for x in a))
    den_b = sqrt(sum((x - mean_b) ** 2 for x in b))
    if den_a == 0 or den_b == 0:
        return None
    return num / (den_a * den_b)


def observe(snaps: List[MarketSnapshot],
             universe_snaps: Optional[Dict[str, List[MarketSnapshot]]] = None,
             ) -> ObserverResult:
    """`universe_snaps` is a mapping pair→snaps (excluding self). If
    missing or empty the observer returns a neutral score with
    `avg_correlation=None`."""
    ts = datetime.now(timezone.utc).isoformat()
    if not snaps or len(snaps) < 20:
        return ObserverResult(name="correlation_matrix", score=0.5,
                              evidence={"reason": "insufficient_data",
                                        "avg_correlation": None}, ts=ts)
    self_rets = _returns([s.close for s in snaps])
    if not universe_snaps:
        return ObserverResult(name="correlation_matrix", score=0.5,
                              evidence={"reason": "no_universe",
                                        "avg_correlation": None}, ts=ts)
    corrs: Dict[str, float] = {}
    for other, other_snaps in universe_snaps.items():
        if not other_snaps or len(other_snaps) < 20:
            continue
        c = _pearson(self_rets, _returns([s.close for s in other_snaps]))
        if c is None:
            continue
        corrs[other] = round(c, 4)
    if not corrs:
        return ObserverResult(name="correlation_matrix", score=0.5,
                              evidence={"reason": "no_correlations_computed",
                                        "avg_correlation": None,
                                        "pairwise": {}}, ts=ts)
    abs_corrs = [abs(v) for v in corrs.values()]
    avg = sum(abs_corrs) / len(abs_corrs)
    # score = 1 - |avg_corr| → 1.0 means uncorrelated (healthy).
    score = max(0.0, min(1.0, 1.0 - avg))
    return ObserverResult(
        name="correlation_matrix",
        score=round(score, 4),
        evidence={
            "avg_correlation":  round(avg, 4),
            "pairwise":         corrs,
            "n_pairs":          len(corrs),
        }, ts=ts,
    )
