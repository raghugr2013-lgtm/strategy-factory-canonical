"""
Phase-2 — generation prior from history.

Reads the saved `strategy_library` collection and returns per-(pair, timeframe)
weights for each canonical strategy_type, biased toward types that have
historically produced higher composite scores on that pair/tf.

Design constraints:
  * Read-only: never writes to the DB.
  * Cached (TTL `_CACHE_TTL_SECONDS`) so generation calls don't pay a Mongo
    round trip per draw.
  * Robust to a cold DB: when the library is empty or all rows for the
    pair/tf score below the floor, returns uniform weights. Generation
    falls back to the existing diversity behaviour with no surprise.
  * No look-ahead: weights come from rows older than the current call —
    the library only contains strategies whose backtests have already
    finished.

The exposed contract is intentionally tiny so callers don't need a
locked-down API:

    weights = await get_type_weights("EURUSD", "H1")
    # → {"trend_following": 0.27, "mean_reversion": 0.31, ...}

A floor of `BASELINE_WEIGHT` is always applied so every type retains
some probability of being drawn — preventing the system from collapsing
into a single type after a couple of lucky outcomes.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Tuple

from engines.db import get_db
from engines.strategy_engine import STRATEGY_TYPES

logger = logging.getLogger(__name__)

# Public knobs — kept conservative so the prior nudges the prior, not
# overrides it.
BASELINE_WEIGHT = 0.10           # min fractional weight per type
SAMPLE_FLOOR = 3                 # need at least this many rows per type
                                 # before contributing to the weighting
SCORE_FIELD_CANDIDATES = (
    "composite_score",
    "score",
    "ranking_score",
    "decision_score",
)

_CACHE: Dict[Tuple[str, str], Tuple[float, Dict[str, float]]] = {}
_CACHE_TTL_SECONDS = 60.0


def _uniform_weights() -> Dict[str, float]:
    n = len(STRATEGY_TYPES)
    return {t: 1.0 / n for t in STRATEGY_TYPES}


def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        return _uniform_weights()
    return {k: v / total for k, v in weights.items()}


def _apply_floor(weights: Dict[str, float], floor: float = BASELINE_WEIGHT) -> Dict[str, float]:
    """Mix uniform floor into weights so every type retains baseline
    probability. floor=0.10 means 90% data-driven, 10% uniform."""
    uniform = 1.0 / len(STRATEGY_TYPES)
    floored = {
        t: weights.get(t, 0.0) * (1.0 - floor) + uniform * floor
        for t in STRATEGY_TYPES
    }
    return _normalize(floored)


async def _aggregate_pair_tf(pair: str, timeframe: str) -> Dict[str, float]:
    """Aggregate raw per-type score sums for the (pair, timeframe). Returns
    a dict {strategy_type → mean_score} only including types with at
    least `SAMPLE_FLOOR` saved rows. May be empty when the library is
    cold for this pair/tf."""
    db = get_db()
    if db is None:
        return {}
    try:
        # We try several score field names. Whichever exists first wins.
        # We aggregate in Mongo for speed but keep code simple by doing
        # this in Python for clarity — the strategy_library is bounded
        # in size by design (top-N saves per cycle), so no perf concern.
        cursor = db.strategy_library.find(
            {"pair": pair, "timeframe": timeframe},
            {
                "_id": 0,
                "strategy_type": 1,
                "composite_score": 1, "score": 1,
                "ranking_score": 1, "decision_score": 1,
                "verdict": 1,
            },
        )
        rows = await cursor.to_list(length=2000)
    except Exception as e:                  # noqa: BLE001 — defensive
        logger.warning(f"history_prior: read failed: {e}")
        return {}

    if not rows:
        return {}

    scores: Dict[str, list] = {t: [] for t in STRATEGY_TYPES}
    for r in rows:
        st = (r.get("strategy_type") or "").strip()
        if st not in scores:
            continue
        score = None
        for fld in SCORE_FIELD_CANDIDATES:
            v = r.get(fld)
            if isinstance(v, (int, float)) and v >= 0:
                score = float(v)
                break
        if score is None:
            # Fallback: derive a coarse score from verdict so every saved
            # strategy still contributes signal even when ranking
            # metadata is missing.
            verdict = (r.get("verdict") or "").upper()
            score = {"TRADE": 75.0, "RISKY": 50.0}.get(verdict, 25.0)
        scores[st].append(score)

    means: Dict[str, float] = {}
    for t, vals in scores.items():
        if len(vals) >= SAMPLE_FLOOR:
            means[t] = sum(vals) / len(vals)
    return means


async def get_type_weights(pair: str, timeframe: str) -> Dict[str, float]:
    """Return per-type generation weights for (pair, timeframe).

    Always returns a dict with one entry per canonical strategy type.
    When history is too sparse, returns uniform weights (each type ~ 0.20
    for 5 types). Otherwise blends the history mean with a uniform floor.

    Caching: result is memoised for `_CACHE_TTL_SECONDS`. Cache key is
    (pair, timeframe). The TTL is short on purpose — the dashboard
    pipeline saves new strategies after each cycle and the prior should
    pick those up within a minute.
    """
    key = (pair, timeframe)
    now = time.time()
    cached = _CACHE.get(key)
    if cached and (now - cached[0] < _CACHE_TTL_SECONDS):
        return dict(cached[1])

    means = {}
    try:
        means = await _aggregate_pair_tf(pair, timeframe)
    except Exception as e:                  # noqa: BLE001 — defensive
        logger.warning(f"history_prior: aggregator failed: {e}")
        means = {}

    if not means:
        weights = _uniform_weights()
    else:
        # Convert means → relative weights. Higher mean score → larger
        # weight. We zero-out types with no data so they fall back to the
        # uniform floor in `_apply_floor`.
        raw = {t: max(0.0, means.get(t, 0.0)) for t in STRATEGY_TYPES}
        weights = _apply_floor(_normalize(raw))

    _CACHE[key] = (now, dict(weights))
    return weights


def clear_cache() -> None:
    """Test helper — flush the TTL cache."""
    _CACHE.clear()
