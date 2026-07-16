"""Observer: session_stats.

Per-session behaviour: mean directional bias, hit rate, dominant
regime. Emits a dict `session_pnl_bias` on the state so the Brain can
match strategies to the session they thrive in.
"""
from __future__ import annotations

from typing import Dict, List
from datetime import datetime, timezone

from ..types import MarketSnapshot, ObserverResult


def observe(snaps: List[MarketSnapshot]) -> ObserverResult:
    if not snaps or len(snaps) < 5:
        return ObserverResult(
            name="session_stats", score=0.5,
            evidence={"n": len(snaps or []), "reason": "insufficient_data",
                      "bias": {}},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    per_session: Dict[str, List[float]] = {}
    for i in range(1, len(snaps)):
        ret = (snaps[i].close - snaps[i - 1].close) / (snaps[i - 1].close or 1.0)
        per_session.setdefault(snaps[i].session or "unknown", []).append(ret)
    bias: Dict[str, float] = {}
    consistency: List[float] = []
    for sess, rets in per_session.items():
        if not rets:
            continue
        mean = sum(rets) / len(rets)
        wins = sum(1 for r in rets if r > 0)
        hitrate = wins / len(rets)
        bias[sess] = round(mean * 10000.0, 4)  # bp
        consistency.append(abs(hitrate - 0.5) * 2.0)  # 0..1 (0 random, 1 perfectly directional)
    score = min(1.0, sum(consistency) / max(1, len(consistency))) if consistency else 0.5
    return ObserverResult(
        name="session_stats",
        score=round(score, 4),
        evidence={"bias": bias, "n_sessions": len(bias)},
        ts=datetime.now(timezone.utc).isoformat(),
    )
