"""
P2 — Signal Quality Score (entry quality filter)

A pure, additive scoring module that grades every entry candidate on a
0–100 scale using three components:

  1. Trend strength       (40 %) — |fast_ma − slow_ma| normalised by
                                    price, plus HTF EMA alignment with
                                    the proposed entry side.
  2. Volatility regime    (30 %) — ATR percentile rank vs the trailing
                                    100-bar window. Peaks at the 30–70 %
                                    band (avoid both dead and exploding
                                    markets).
  3. Session liquidity    (30 %) — GMT-hour multiplier from the existing
                                    `_session_spread_multiplier` table:
                                    London/NY peak ⇒ 100, Asian thin ⇒
                                    ~30, off-session ⇒ ~60.

The final score is a weighted average of the three components (each in
0–100). The module never raises; missing inputs collapse to a neutral
50 for that component so the filter never silently kills every entry.

This file does NOT change strategy logic. It only computes a score that
the backtest loop can use as a filter (entry_quality_score ≥ threshold)
and that downstream telemetry can surface.
"""

from __future__ import annotations

# ── Component weights (sum = 1.0) ─────────────────────────────────────
W_TREND = 0.40
W_VOL = 0.30
W_SESSION = 0.30

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULT_THRESHOLD = 60          # accept entries with score ≥ 60
NEUTRAL_COMPONENT_SCORE = 50.0  # used when an input is missing/insufficient
VOL_WINDOW = 100                # trailing window for ATR percentile rank
HTF_LOOKBACK = 4                # bars back to check HTF EMA slope

_SESSION_HOUR_SCORE: dict = {
    # 0..23 (GMT hour) — peak liquidity ⇒ 100, Asian thin ⇒ 30
    0: 35, 1: 30, 2: 30, 3: 35, 4: 40, 5: 45, 6: 60,
    7: 90, 8: 100, 9: 100, 10: 100, 11: 85,
    12: 80, 13: 100, 14: 100, 15: 100, 16: 95, 17: 85,
    18: 70, 19: 60, 20: 50, 21: 45, 22: 40, 23: 35,
}


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if x is None:
        return NEUTRAL_COMPONENT_SCORE
    try:
        x = float(x)
    except (TypeError, ValueError):
        return NEUTRAL_COMPONENT_SCORE
    if x != x:  # NaN
        return NEUTRAL_COMPONENT_SCORE
    return max(lo, min(hi, x))


def _safe_get(arr, i):
    if not arr or i is None or i < 0 or i >= len(arr):
        return None
    return arr[i]


def _hour_from_timestamp(ts) -> int | None:
    if ts is None:
        return None
    try:
        if isinstance(ts, str):
            import re
            m = re.search(r"T(\d{2}):", ts) or re.search(r"\s(\d{2}):", ts)
            if m:
                return int(m.group(1)) % 24
            return None
        h = getattr(ts, "hour", None)
        if h is None:
            return None
        return int(h) % 24
    except (TypeError, ValueError):
        return None


# ── Component scorers ────────────────────────────────────────────────

def score_trend_strength(
    *,
    side: str,
    fast_ma_i,
    slow_ma_i,
    price_i,
    htf_ema_i=None,
    htf_ema_back=None,
) -> float:
    """Return 0–100. Combines MA-spread strength + HTF alignment.

    Strength = |fast − slow| / price, scaled so a 0.20 % spread ≈ 60 pts
    and 0.50 % spread saturates at ~85. HTF alignment adds up to 15 pts
    when HTF EMA slope confirms the entry direction; subtracts 15 pts
    when it opposes; 0 when HTF data is missing.
    """
    if fast_ma_i is None or slow_ma_i is None or not price_i or price_i <= 0:
        return NEUTRAL_COMPONENT_SCORE
    try:
        spread_pct = abs(float(fast_ma_i) - float(slow_ma_i)) / float(price_i)
    except (TypeError, ValueError, ZeroDivisionError):
        return NEUTRAL_COMPONENT_SCORE

    # Direction match — fast above slow ⇒ favours BUY, below ⇒ SELL.
    side_up = (side or "").upper() == "BUY"
    fast_above = float(fast_ma_i) > float(slow_ma_i)
    direction_aligned = (side_up and fast_above) or ((not side_up) and (not fast_above))

    # Spread → base score. 0 % ⇒ 30, 0.20 % ⇒ 60, 0.50 % ⇒ ~85, capped 90.
    base = 30.0 + min(60.0, spread_pct * 30000.0)
    if not direction_aligned:
        # MA alignment opposes the proposed side. Penalise sharply but
        # not to zero — the strategy may have a counter-trend reason.
        base = max(20.0, base - 25.0)

    # HTF alignment bonus / penalty.
    htf_bonus = 0.0
    if htf_ema_i is not None and htf_ema_back is not None:
        try:
            slope_up = float(htf_ema_i) > float(htf_ema_back)
            slope_dn = float(htf_ema_i) < float(htf_ema_back)
            if (side_up and slope_up) or ((not side_up) and slope_dn):
                htf_bonus = 15.0
            elif (side_up and slope_dn) or ((not side_up) and slope_up):
                htf_bonus = -15.0
        except (TypeError, ValueError):
            htf_bonus = 0.0

    return _clamp(base + htf_bonus)


def score_volatility_regime(*, atr_vals, i: int) -> float:
    """Return 0–100. ATR percentile rank within the trailing
    `VOL_WINDOW` bars; score peaks at 30–70 percentile.

    Logic:
      * Insufficient samples ⇒ neutral 50.
      * Percentile p in [0,1].
      * Score = 100 − 200·|p − 0.5|, clamped to [10, 100].
        - p=0.5 ⇒ 100 (ideal middle-of-the-road volatility)
        - p=0.1 or p=0.9 ⇒ 20
        - p=0.0 / 1.0 ⇒ 10  (dead market or exploding)
    """
    if not atr_vals or i is None or i < 0:
        return NEUTRAL_COMPONENT_SCORE
    cur = _safe_get(atr_vals, i)
    if cur is None or cur <= 0:
        return NEUTRAL_COMPONENT_SCORE

    lo = max(0, i - VOL_WINDOW + 1)
    window = [v for v in atr_vals[lo:i + 1] if v is not None and v > 0]
    if len(window) < 20:
        return NEUTRAL_COMPONENT_SCORE

    # Percentile rank of `cur` within window
    n = len(window)
    less = sum(1 for v in window if v < cur)
    eq = sum(1 for v in window if v == cur)
    p = (less + 0.5 * eq) / n  # 0..1

    score = 100.0 - 200.0 * abs(p - 0.5)
    return _clamp(score, 10.0, 100.0)


def score_session(*, timestamp) -> float:
    """Return 0–100 from the GMT-hour liquidity table.

    No timestamp ⇒ neutral 60 (slightly above neutral because most
    backtests run on data that includes peak hours)."""
    h = _hour_from_timestamp(timestamp)
    if h is None:
        return 60.0
    return _clamp(float(_SESSION_HOUR_SCORE.get(h, 60)))


# ── Composite scorer ─────────────────────────────────────────────────

def compute_entry_quality_score(
    *,
    side: str,
    i: int,
    seg_prices: list,
    fast_ma: list,
    slow_ma: list,
    atr_vals: list | None = None,
    htf_ema: list | None = None,
    seg_timestamps: list | None = None,
    htf_lookback: int = HTF_LOOKBACK,
) -> dict:
    """Compute the composite 0–100 entry-quality score and breakdown.

    Returns a dict:
      {
        "score": float (0..100, rounded to 1dp),
        "components": {
            "trend": float,
            "volatility": float,
            "session": float,
        },
        "weights": {"trend": 0.4, "volatility": 0.3, "session": 0.3},
      }

    Defensive: never raises; missing inputs collapse to neutral 50 in
    the affected component so the composite still yields a meaningful
    score.
    """
    price_i = _safe_get(seg_prices, i)
    fast_i = _safe_get(fast_ma, i)
    slow_i = _safe_get(slow_ma, i)

    htf_i = _safe_get(htf_ema, i) if htf_ema else None
    htf_back = _safe_get(htf_ema, max(0, i - htf_lookback)) if htf_ema else None

    ts_i = _safe_get(seg_timestamps, i) if seg_timestamps else None

    s_trend = score_trend_strength(
        side=side,
        fast_ma_i=fast_i,
        slow_ma_i=slow_i,
        price_i=price_i,
        htf_ema_i=htf_i,
        htf_ema_back=htf_back,
    )
    s_vol = score_volatility_regime(atr_vals=atr_vals, i=i)
    s_session = score_session(timestamp=ts_i)

    composite = (
        W_TREND * s_trend
        + W_VOL * s_vol
        + W_SESSION * s_session
    )
    composite = _clamp(composite)

    return {
        "score": round(composite, 1),
        "components": {
            "trend": round(s_trend, 1),
            "volatility": round(s_vol, 1),
            "session": round(s_session, 1),
        },
        "weights": {"trend": W_TREND, "volatility": W_VOL, "session": W_SESSION},
    }
