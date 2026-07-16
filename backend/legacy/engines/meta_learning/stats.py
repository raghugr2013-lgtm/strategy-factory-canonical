"""Phase I — pure-function statistical helpers.

Zero external deps (no numpy/scipy). Deterministic. Used by every
evaluator so replays produce byte-identical recommendation ids.
"""
from __future__ import annotations

import math
from typing import List, Sequence, Tuple


def mean(xs: Sequence[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def stddev(xs: Sequence[float]) -> float:
    xs = list(xs)
    n = len(xs)
    if n < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    xs = list(xs); ys = list(ys)
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    mx, my = mean(xs[:n]), mean(ys[:n])
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    dx = math.sqrt(sum((xs[i] - mx) ** 2 for i in range(n)))
    dy = math.sqrt(sum((ys[i] - my) ** 2 for i in range(n)))
    if dx == 0.0 or dy == 0.0:
        return 0.0
    r = num / (dx * dy)
    return max(-1.0, min(1.0, r))


def spearman(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Rank-correlation robustness check (Q5)."""
    xs = list(xs); ys = list(ys)
    n = min(len(xs), len(ys))
    if n < 3:
        return 0.0
    rx = _ranks(xs[:n])
    ry = _ranks(ys[:n])
    return pearson(rx, ry)


def _ranks(xs: Sequence[float]) -> List[float]:
    ordered = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and xs[ordered[j + 1]] == xs[ordered[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[ordered[k]] = avg_rank
        i = j + 1
    return ranks


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def normalise_pnl(pnl: float, *, cap: float = 100.0) -> float:
    """Squash realised PnL to [-1, 1] using a soft tanh-lite.

    Sign-preserving and deterministic. `cap` is the PnL magnitude that
    saturates to |1|.
    """
    if cap <= 0.0:
        return 0.0
    x = pnl / cap
    return clamp(x, -1.0, 1.0)


def bin_edges(lo: float, hi: float, n: int) -> List[float]:
    if n <= 0 or hi <= lo:
        return [lo, hi] if hi > lo else [lo]
    step = (hi - lo) / n
    return [lo + i * step for i in range(n + 1)]


def bin_index(x: float, edges: Sequence[float]) -> int:
    n = len(edges) - 1
    if n <= 0:
        return 0
    if x <= edges[0]:
        return 0
    if x >= edges[-1]:
        return n - 1
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if edges[mid + 1] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def p_value_from_r(r: float, n: int) -> float:
    """Approximate two-sided p-value for Pearson r via t-distribution
    (no scipy). Good-enough for our sig-floor gate (Q5).
    """
    if n < 3:
        return 1.0
    denom = math.sqrt(max(1e-12, 1.0 - r * r))
    t = r * math.sqrt(max(1, n - 2)) / denom
    # Wilson-Hilferty-ish two-tail approximation via z.
    # Use erfc for a normal approximation (df≥30 acceptable; conservative below).
    z = t / math.sqrt(1.0 + (t * t) / max(1, 2 * (n - 2)))
    return math.erfc(abs(z) / math.sqrt(2.0))
