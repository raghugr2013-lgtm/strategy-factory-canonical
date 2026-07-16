"""Phase D.3 — Portfolio Health Engine.

Continuous monitor. Returns a HealthReport with per-signal booleans + one
overall health_score 0..1. When any threshold trips → `rebalance_required=True`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config as pcfg
from .types import PortfolioMember, PortfolioState


@dataclass
class HealthReport:
    master_bot_id:        str
    ts:                   str
    health_score:         float           # 0..1
    rebalance_required:   bool
    signals:              Dict[str, Any] = field(default_factory=dict)
    diagnostics:          Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _style_concentration(members: List[PortfolioMember]) -> Dict[str, float]:
    if not members:
        return {}
    counts: Dict[str, int] = {}
    for m in members:
        counts[m.style] = counts.get(m.style, 0) + 1
    total = len(members)
    return {s: round(c / total, 4) for s, c in counts.items()}


def _avg_pairwise_correlation(members: List[PortfolioMember]) -> Optional[float]:
    curves = [m.equity_curve for m in members if len(m.equity_curve) >= 20]
    if len(curves) < 2:
        return None
    corrs = []
    for i in range(len(curves)):
        for j in range(i + 1, len(curves)):
            a = curves[i]; b = curves[j]
            n = min(len(a), len(b))
            xa = a[:n]; xb = b[:n]
            ma = sum(xa) / n; mb = sum(xb) / n
            num = sum((xa[k] - ma) * (xb[k] - mb) for k in range(n))
            va = sum((v - ma) ** 2 for v in xa)
            vb = sum((v - mb) ** 2 for v in xb)
            den = math.sqrt(va * vb)
            if den <= 0:
                continue
            corrs.append(abs(num / den))
    if not corrs:
        return None
    return round(sum(corrs) / len(corrs), 4)


def _worst_drawdown(members: List[PortfolioMember]) -> float:
    if not members:
        return 0.0
    return max(float((m.backtest or {}).get("max_drawdown_pct") or 0.0) for m in members)


def _avg_confidence(members: List[PortfolioMember]) -> float:
    if not members:
        return 0.0
    return round(sum(m.confidence for m in members) / len(members), 4)


def portfolio_health(state: PortfolioState) -> HealthReport:
    """Snapshot health of `state`. Never raises."""
    members = state.members
    ts = datetime.now(timezone.utc).isoformat()

    if not members:
        return HealthReport(state.master_bot_id, ts, 0.0, True,
                            signals={"empty_portfolio": True},
                            diagnostics={"member_count": 0})

    style_conc = _style_concentration(members)
    max_style = max(style_conc.values()) if style_conc else 0.0
    over_style_cap = max_style > pcfg.max_style_share()

    avg_corr = _avg_pairwise_correlation(members)
    over_corr = (avg_corr is not None) and (avg_corr >= pcfg.correlation_max())

    worst_dd = _worst_drawdown(members)
    over_dd = worst_dd >= pcfg.drawdown_pause_pct()

    avg_conf = _avg_confidence(members)
    under_conf = avg_conf < pcfg.confidence_min_active()

    n_active = sum(1 for m in members if m.status == "active")
    diversity = len(set(m.style for m in members))
    low_diversity = diversity < 3

    signals = {
        "over_style_cap":   over_style_cap,
        "over_correlation": over_corr,
        "over_drawdown":    over_dd,
        "under_confidence": under_conf,
        "low_diversity":    low_diversity,
    }
    tripped = sum(1 for v in signals.values() if v is True)
    health_score = round(max(0.0, 1.0 - 0.2 * tripped), 3)
    rebalance = tripped > 0

    return HealthReport(
        master_bot_id=state.master_bot_id,
        ts=ts,
        health_score=health_score,
        rebalance_required=rebalance,
        signals=signals,
        diagnostics={
            "member_count":       len(members),
            "active_count":       n_active,
            "distinct_styles":    diversity,
            "style_concentration": style_conc,
            "avg_pairwise_correlation": avg_corr,
            "worst_drawdown_pct": worst_dd,
            "avg_confidence":     avg_conf,
        },
    )
