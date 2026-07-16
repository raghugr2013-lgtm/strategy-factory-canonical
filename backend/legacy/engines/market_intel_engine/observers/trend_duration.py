"""Observer: trend_duration.

Measures how long consecutive same-sign moves persist. Higher =
market trends persist longer (good for trend-followers), lower =
market reverses quickly (favours mean-reversion).
"""
from __future__ import annotations

from typing import List
from datetime import datetime, timezone

from ..types import MarketSnapshot, ObserverResult


def observe(snaps: List[MarketSnapshot]) -> ObserverResult:
    if not snaps or len(snaps) < 3:
        return ObserverResult(
            name="trend_duration", score=0.5,
            evidence={"n": len(snaps or []), "reason": "insufficient_data"},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    closes = [s.close for s in snaps]
    diffs = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    if not diffs:
        return ObserverResult(
            name="trend_duration", score=0.5,
            evidence={"n": len(snaps), "reason": "no_diffs"},
            ts=datetime.now(timezone.utc).isoformat(),
        )
    # Compute consecutive same-sign runs.
    runs: List[int] = []
    cur = 1
    prev_sign = _sign(diffs[0])
    for d in diffs[1:]:
        s = _sign(d)
        if s == prev_sign and s != 0:
            cur += 1
        else:
            runs.append(cur)
            cur = 1
            prev_sign = s
    runs.append(cur)
    avg_run = sum(runs) / len(runs) if runs else 1.0
    max_run = max(runs) if runs else 1
    # Persistence score — normalise so run≥8 counts as strongly trending.
    persistence = min(1.0, avg_run / 8.0)
    return ObserverResult(
        name="trend_duration",
        score=round(persistence, 4),
        evidence={
            "avg_run_bars":  round(avg_run, 2),
            "max_run_bars":  int(max_run),
            "n_runs":        len(runs),
        },
        ts=datetime.now(timezone.utc).isoformat(),
    )


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)
