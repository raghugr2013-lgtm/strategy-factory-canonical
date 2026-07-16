"""Phase C.2 — Portfolio Intelligence Engine.

Scores strategies by their CONTRIBUTION to a portfolio (marginal Sharpe,
diversification benefit, style-balance uplift) instead of their solo
metrics. Enables the Master Bot Builder to reject strategies that score
high solo but overlap with everything already in a bundle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class PortfolioScore:
    strategy_hash:          str
    solo_score:             float      # composite of pf / dd / win_rate
    diversification_bonus:  float      # 0..1 — how much this differs from the existing bundle
    correlation_penalty:    float      # 0..1 — subtract when heavily correlated
    contribution_score:     float      # final: solo × (1 + bonus - penalty)
    reasons:                List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _solo_score(bt: Dict[str, Any]) -> float:
    pf  = float(bt.get("profit_factor") or 0.0)
    dd  = float(bt.get("max_drawdown_pct") or 100.0)
    wr  = float(bt.get("win_rate") or 0.0)
    tr  = int(bt.get("total_trades") or 0)
    # Composite (matches the backtest-evidence weighting used elsewhere).
    pf_term = max(0.0, min(1.0, (pf - 1.0) / 3.0))
    dd_term = max(0.0, min(1.0, 1.0 - dd / 30.0))
    wr_term = max(0.0, min(1.0, wr / 100.0))
    n_term  = min(1.0, tr / 200.0)
    return round(0.35 * pf_term + 0.3 * dd_term + 0.15 * wr_term + 0.2 * n_term, 4)


def _style_frequencies(existing: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    freq: Dict[str, int] = {}
    for s in existing:
        st = str(s.get("style") or "unknown")
        freq[st] = freq.get(st, 0) + 1
    return freq


def _equity_curves_correlation(
    a: Optional[List[float]], b: Optional[List[float]]
) -> Optional[float]:
    """Pearson correlation between two equity curves. Returns None on
    insufficient data. Never raises."""
    if not a or not b:
        return None
    n = min(len(a), len(b))
    if n < 20:
        return None
    xa = a[:n]; xb = b[:n]
    mean_a = sum(xa) / n
    mean_b = sum(xb) / n
    num = sum((xa[i] - mean_a) * (xb[i] - mean_b) for i in range(n))
    var_a = sum((v - mean_a) ** 2 for v in xa)
    var_b = sum((v - mean_b) ** 2 for v in xb)
    denom = math.sqrt(var_a * var_b)
    if denom <= 0:
        return None
    return round(num / denom, 4)


def portfolio_contribution_score(
    candidate: Dict[str, Any],
    existing_bundle: List[Dict[str, Any]],
) -> PortfolioScore:
    """Score `candidate`'s contribution to `existing_bundle`.

    `candidate` and each element of `existing_bundle` must expose at least:
        - strategy_hash
        - style       (from classify_strategy)
        - backtest    (dict with profit_factor / max_drawdown_pct / …)
        - equity_curve (optional list[float]; enables correlation penalty)
    """
    bt = candidate.get("backtest") or {}
    solo = _solo_score(bt)
    reasons: List[str] = []

    # Diversification bonus — reward under-represented styles.
    cand_style = str(candidate.get("style") or "unknown")
    freq = _style_frequencies(existing_bundle)
    total_in_bundle = max(1, sum(freq.values()))
    cand_share = freq.get(cand_style, 0) / total_in_bundle
    # Under-represented → bonus up to 0.3
    diversification_bonus = round(max(0.0, 0.3 * (1.0 - cand_share)), 4)
    if diversification_bonus > 0.15:
        reasons.append(f"style_underrepresented:{cand_style}")
    elif not existing_bundle:
        # Empty bundle → full bonus for the first pick
        diversification_bonus = 0.3
        reasons.append("first_pick_full_bonus")

    # Correlation penalty — average |corr| against existing equity curves.
    cand_eq = candidate.get("equity_curve") or []
    corrs = []
    for e in existing_bundle:
        c = _equity_curves_correlation(cand_eq, e.get("equity_curve"))
        if c is not None:
            corrs.append(abs(c))
    correlation_penalty = 0.0
    if corrs:
        avg_corr = sum(corrs) / len(corrs)
        # Correlation > 0.7 → heavy penalty; < 0.3 → none
        correlation_penalty = round(max(0.0, min(0.5, (avg_corr - 0.3) * 0.7)), 4)
        if correlation_penalty > 0.2:
            reasons.append(f"high_correlation:{avg_corr:.2f}")

    contribution = round(solo * (1.0 + diversification_bonus - correlation_penalty), 4)
    contribution = max(0.0, contribution)

    return PortfolioScore(
        strategy_hash=str(candidate.get("strategy_hash") or ""),
        solo_score=solo,
        diversification_bonus=diversification_bonus,
        correlation_penalty=correlation_penalty,
        contribution_score=contribution,
        reasons=reasons,
    )
