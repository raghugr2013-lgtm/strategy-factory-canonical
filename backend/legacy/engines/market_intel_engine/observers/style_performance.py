"""Observer: style_performance.

Q6 (operator-approved): base rolling style PF proxy on LIVE OUTCOME
EVENTS ONLY — drift-free, ignores backtest evidence. Accepts a slower
warm-up in exchange for signal integrity.

The observer looks at recent `outcome_events` rows whose `metrics`
carry both a `style` tag and an `action` (or `pf`) marker. It computes
a rolling proxy score per style ∈ [0..1] where 0.5 is neutral.

If the caller does not pass `recent_outcomes`, the observer returns a
neutral snapshot (0.5) — style_performance is only meaningful once
enough live outcomes have been accumulated.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from ..types import MarketSnapshot, ObserverResult


_KNOWN_STYLES = (
    "trend_following", "mean_reversion", "breakout",
    "momentum", "volatility_based", "session_based",
    "scalping", "swing",
)


def observe(snaps: List[MarketSnapshot],
             recent_outcomes: Optional[List[Dict[str, Any]]] = None,
             ) -> ObserverResult:
    """Score is the composite health across all known styles.
    `style_scores` is per-style; the aggregator picks each style's
    value individually for `style_confidence`."""
    ts = datetime.now(timezone.utc).isoformat()
    if not recent_outcomes:
        return ObserverResult(
            name="style_performance", score=0.5,
            evidence={
                "style_scores": {s: 0.5 for s in _KNOWN_STYLES},
                "n_outcomes": 0,
                "reason": "no_live_outcomes_yet",
            }, ts=ts,
        )
    # Bucket by style.
    per_style: Dict[str, List[float]] = {}
    for row in recent_outcomes:
        m = row.get("metrics") or {}
        ev = row.get("evidence") or {}
        style = (m.get("style") or ev.get("style")
                 or ev.get("active_style") or "").strip()
        if not style:
            continue
        # Preferred signals: realised PF; then score_now; then hitrate.
        signal = None
        if "profit_factor" in m:
            pf = float(m["profit_factor"] or 0.0)
            signal = _norm_pf(pf)
        elif "score_now" in m:
            signal = float(m["score_now"] or 0.0)
        elif "hit_rate" in m:
            signal = float(m["hit_rate"] or 0.0)
        if signal is None:
            continue
        per_style.setdefault(style, []).append(max(0.0, min(1.0, signal)))
    style_scores: Dict[str, float] = {s: 0.5 for s in _KNOWN_STYLES}
    for s, vals in per_style.items():
        if not vals:
            continue
        style_scores[s] = round(sum(vals) / len(vals), 4)
    active_vals = [v for v in style_scores.values() if v != 0.5]
    composite = (sum(active_vals) / len(active_vals)) if active_vals else 0.5
    return ObserverResult(
        name="style_performance",
        score=round(composite, 4),
        evidence={
            "style_scores": style_scores,
            "n_outcomes":   len(recent_outcomes),
        }, ts=ts,
    )


def _norm_pf(pf: float) -> float:
    if pf <= 1.0:
        return max(0.0, pf / 2.0)     # 0..0.5
    return min(1.0, 0.5 + (pf - 1.0) / 2.0)
