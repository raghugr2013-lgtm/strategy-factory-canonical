"""
Multi-indicator backtest engine.
Supports: EMA/SMA crossover, RSI, MACD, Bollinger Bands.
Auto-detects strategy type from text and applies matching signal logic.
Realistic simulation with spread, slippage, commission, position sizing.
"""

import hashlib
import math
import random
import re
import logging
from datetime import datetime, timezone
from engines.param_extractor import extract_params
from engines.execution_engine import apply_execution_to_trades, resolve_config as resolve_exec_config
from engines.backtest_report import build_report as _build_report, _compute_drawdown_curve
from engines.regime_classifier import classify_regime as _classify_regime
from engines.signal_quality import compute_entry_quality_score as _compute_quality

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# Static data / constants
# ══════════════════════════════════════════════════════════════

PRICE_DATA = {
    "EURUSD": [
        1.0850, 1.0865, 1.0842, 1.0878, 1.0891, 1.0873, 1.0856, 1.0901, 1.0923, 1.0910,
        1.0895, 1.0932, 1.0948, 1.0935, 1.0918, 1.0960, 1.0945, 1.0972, 1.0988, 1.0965,
        1.0943, 1.0920, 1.0955, 1.0978, 1.0995, 1.0982, 1.0960, 1.0938, 1.0915, 1.0942,
        1.0968, 1.0985, 1.1002, 1.0990, 1.0975, 1.0958, 1.0980, 1.1010, 1.1025, 1.1008,
        1.0992, 1.0975, 1.0950, 1.0935, 1.0960, 1.0982, 1.1005, 1.1020, 1.1035, 1.1015,
    ],
    "GBPUSD": [
        1.2650, 1.2678, 1.2642, 1.2695, 1.2720, 1.2705, 1.2680, 1.2735, 1.2760, 1.2745,
        1.2718, 1.2755, 1.2780, 1.2768, 1.2740, 1.2790, 1.2775, 1.2810, 1.2835, 1.2820,
        1.2795, 1.2770, 1.2805, 1.2830, 1.2855, 1.2840, 1.2815, 1.2790, 1.2765, 1.2795,
        1.2825, 1.2850, 1.2875, 1.2860, 1.2835, 1.2810, 1.2840, 1.2870, 1.2895, 1.2878,
        1.2855, 1.2830, 1.2805, 1.2790, 1.2815, 1.2845, 1.2870, 1.2890, 1.2910, 1.2895,
    ],
    "USDJPY": [
        149.50, 149.75, 149.30, 149.90, 150.10, 149.85, 149.60, 150.20, 150.45, 150.30,
        150.05, 150.50, 150.70, 150.55, 150.25, 150.80, 150.65, 151.00, 151.25, 151.10,
        150.85, 150.55, 150.90, 151.15, 151.40, 151.25, 150.95, 150.70, 150.45, 150.75,
        151.05, 151.30, 151.55, 151.40, 151.15, 150.90, 151.20, 151.50, 151.75, 151.55,
        151.30, 151.05, 150.80, 150.60, 150.85, 151.15, 151.40, 151.60, 151.80, 151.65,
    ],
    "XAUUSD": [
        2620.50, 2625.30, 2618.70, 2630.10, 2635.80, 2628.40, 2622.60, 2638.90, 2645.20, 2640.50,
        2633.80, 2648.60, 2655.30, 2650.10, 2642.70, 2658.40, 2652.80, 2665.10, 2672.50, 2668.20,
        2660.40, 2652.30, 2662.80, 2670.50, 2678.30, 2673.10, 2665.40, 2658.20, 2650.80, 2660.30,
        2668.50, 2675.80, 2683.20, 2678.90, 2672.10, 2665.30, 2673.50, 2682.40, 2690.10, 2685.30,
        2678.40, 2670.50, 2662.80, 2656.30, 2665.20, 2673.80, 2681.50, 2688.30, 2695.10, 2690.40,
    ],
    "US100": [
        20850.0, 20920.0, 20780.0, 20980.0, 21050.0, 20950.0, 20870.0, 21100.0, 21180.0, 21120.0,
        21050.0, 21220.0, 21300.0, 21250.0, 21150.0, 21350.0, 21280.0, 21420.0, 21500.0, 21450.0,
        21350.0, 21250.0, 21380.0, 21480.0, 21560.0, 21500.0, 21400.0, 21300.0, 21220.0, 21350.0,
        21450.0, 21550.0, 21630.0, 21580.0, 21480.0, 21380.0, 21480.0, 21600.0, 21700.0, 21650.0,
        21550.0, 21450.0, 21350.0, 21280.0, 21380.0, 21480.0, 21580.0, 21650.0, 21730.0, 21680.0,
    ],
    "BTCUSD": [
        95200.0, 95800.0, 94500.0, 96300.0, 97100.0, 96200.0, 95400.0, 97500.0, 98200.0, 97600.0,
        96800.0, 98500.0, 99200.0, 98700.0, 97800.0, 99800.0, 99100.0, 100500.0, 101200.0, 100600.0,
        99500.0, 98400.0, 99800.0, 100800.0, 101500.0, 100900.0, 100000.0, 99200.0, 98300.0, 99500.0,
        100400.0, 101200.0, 102000.0, 101500.0, 100600.0, 99800.0, 100800.0, 101800.0, 102600.0, 102000.0,
        101100.0, 100200.0, 99300.0, 98600.0, 99600.0, 100600.0, 101500.0, 102200.0, 103000.0, 102400.0,
    ],
    "ETHUSD": [
        3550.0, 3580.0, 3520.0, 3610.0, 3650.0, 3620.0, 3570.0, 3670.0, 3710.0, 3690.0,
        3650.0, 3720.0, 3760.0, 3740.0, 3700.0, 3780.0, 3750.0, 3810.0, 3850.0, 3830.0,
        3790.0, 3750.0, 3800.0, 3840.0, 3880.0, 3860.0, 3820.0, 3780.0, 3740.0, 3790.0,
        3830.0, 3870.0, 3910.0, 3890.0, 3850.0, 3810.0, 3850.0, 3900.0, 3940.0, 3920.0,
        3880.0, 3840.0, 3800.0, 3770.0, 3810.0, 3850.0, 3890.0, 3920.0, 3960.0, 3940.0,
    ],
}

TIMEFRAME_MAP = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d",
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d",
}

DEFAULT_SPREADS = {
    "EURUSD": 1.2, "GBPUSD": 1.5, "USDJPY": 1.3,
    "XAUUSD": 3.0, "US100": 2.0, "BTCUSD": 5.0, "ETHUSD": 3.0,
}
PIP_VALUES = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "USDJPY": 6.67,
    "XAUUSD": 10.0, "US100": 1.0, "BTCUSD": 1.0, "ETHUSD": 1.0,
}
PIP_UNITS = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01,
    "XAUUSD": 0.10, "US100": 1.0, "BTCUSD": 1.0, "ETHUSD": 0.10,
}

# P2 — Non-forex assets with large pip-units relative to price noise.
# Fixed-pip stops like SL=20 on XAU (=$2 of a $2 000 move) sit inside
# normal noise and trigger a near-100 % loss rate. Default these pairs
# to ATR-based stops unless the caller explicitly opts out via
# `sim_config.atr_stops=false`.
FOREX_PAIRS = {"EURUSD", "GBPUSD", "USDJPY", "EURGBP", "USDCAD", "AUDUSD", "NZDUSD", "USDCHF"}

# Default ATR multipliers used when the caller enables auto-ATR but the
# strategy text doesn't specify atr_k / atr_m (e.g. a forex-tuned
# template re-run on XAU). Tuned for a 1 : 2 stop-to-target ratio on a
# 14-bar ATR — generous enough to sit outside noise, tight enough to
# keep lot sizing reasonable.
DEFAULT_AUTO_ATR_K = 1.5
DEFAULT_AUTO_ATR_M = 3.0

# P2 — Drawdown floor. When equity drops below this fraction of the
# initial balance we halt trading in the segment (the account is
# effectively ruined; continuing compounds the loss and produces
# the DD-9 397 % artefact the XAU validation surfaced).
DEFAULT_RUIN_FLOOR = 0.10


# ══════════════════════════════════════════════════════════════
# Indicator calculations
# ══════════════════════════════════════════════════════════════

def _sma(prices: list, period: int) -> list:
    """Simple Moving Average. Returns list same length as prices, None for warm-up."""
    out = []
    for i in range(len(prices)):
        if i < period - 1:
            out.append(None)
        else:
            out.append(sum(prices[i - period + 1:i + 1]) / period)
    return out


def _ema(prices: list, period: int) -> list:
    """Exponential Moving Average."""
    out = [None] * len(prices)

    if len(prices) < period:
        return out

    # Seed with SMA
    out[period - 1] = sum(prices[:period]) / period

    k = 2.0 / (period + 1)

    for i in range(period, len(prices)):
        out[i] = prices[i] * k + out[i - 1] * (1 - k)

    return out

def _rsi(prices: list, period: int = 14) -> list:
    """Relative Strength Index (Wilder's smoothing)."""
    out = [None] * len(prices)

    if len(prices) < period + 1:
        return out

    gains = []
    losses = []

    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    # First average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100 - (100 / (1 + rs))

    # Subsequent values (Wilder smoothing)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            out[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i + 1] = 100 - (100 / (1 + rs))

    return out

def _macd(train_prices: list, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """MACD line, signal line, histogram. Returns 3 lists."""
    ema_fast = _ema(train_prices, fast)
    ema_slow = _ema(train_prices, slow)
    macd_line = [None] * len(train_prices)
    for i in range(len(train_prices)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]
    # Signal line = EMA of MACD line
    valid_macd = [v for v in macd_line if v is not None]
    if len(valid_macd) < signal:
        return macd_line, [None] * len(train_prices), [None] * len(train_prices)
    signal_line = [None] * len(train_prices)
    start_idx = next(i for i, v in enumerate(macd_line) if v is not None)
    # Seed signal with SMA of first `signal` MACD values
    seed_vals = [macd_line[j] for j in range(start_idx, min(start_idx + signal, len(train_prices))) if macd_line[j] is not None]
    if len(seed_vals) < signal:
        return macd_line, signal_line, [None] * len(train_prices)
    sig_start = start_idx + signal - 1
    signal_line[sig_start] = sum(seed_vals) / signal
    k = 2.0 / (signal + 1)
    for i in range(sig_start + 1, len(train_prices)):
        if macd_line[i] is not None and signal_line[i - 1] is not None:
            signal_line[i] = macd_line[i] * k + signal_line[i - 1] * (1 - k)
    histogram = [None] * len(train_prices)
    for i in range(len(train_prices)):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]
    return macd_line, signal_line, histogram


def _bollinger(train_prices: list, period: int = 20, std_dev: float = 2.0) -> tuple:
    """Bollinger Bands. Returns (middle, upper, lower) lists."""
    middle = _sma(train_prices, period)
    upper = [None] * len(train_prices)
    lower = [None] * len(train_prices)
    for i in range(period - 1, len(train_prices)):
        m = middle[i]
        if m is None:
            continue
        window = train_prices[i - period + 1:i + 1]
        variance = sum((p - m) ** 2 for p in window) / period
        sd = math.sqrt(variance)
        upper[i] = m + std_dev * sd
        lower[i] = m - std_dev * sd
    return middle, upper, lower


def _deterministic_seed(strategy_text: str) -> int:
    return int(hashlib.md5(strategy_text.encode()).hexdigest()[:8], 16)


# ══════════════════════════════════════════════════════════════
# Phase 2 — ATR + regime + risk-model helpers (additive)
# ══════════════════════════════════════════════════════════════

def _atr(highs: list, lows: list, closes: list, period: int = 14) -> list:
    """Wilder ATR(period). Returns list aligned with `closes`. Falls back
    to absolute close-to-close range when high/low not provided."""
    n = len(closes)
    out: list = [None] * n
    if n < period + 1:
        return out
    # True range per bar
    tr: list = [0.0]
    for i in range(1, n):
        if highs and lows and i < len(highs) and i < len(lows):
            h, lo = highs[i], lows[i]
            pc = closes[i - 1]
            tr.append(max(h - lo, abs(h - pc), abs(lo - pc)))
        else:
            tr.append(abs(closes[i] - closes[i - 1]))
    # Seed with simple average of first `period` TRs
    seed = sum(tr[1:period + 1]) / period
    out[period] = seed
    # Wilder smoothing
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


# Strategy type → preferred market regimes. When regime classifier
# returns one of these (or "unknown"), the signal is allowed through.
# When the regime is anything else, the entry is suppressed.
_REGIME_PREFERENCE: dict = {
    "trend_following":  {"trending", "low_volatility", "unknown"},
    "mean_reversion":   {"ranging", "low_volatility", "unknown"},
    "momentum":         {"trending", "high_volatility", "unknown"},
    "breakout":         {"trending", "high_volatility", "unknown"},
    "scalping":         {"ranging", "low_volatility", "unknown"},
    "volatility_based": {"high_volatility", "trending", "unknown"},
    "session_based":    {"ranging", "high_volatility", "unknown"},
}

# Trailing-window length used by the in-loop regime classifier. Phase 2
# uses 100 bars by default (matches `regime_classifier.WINDOW_DEFAULT`).
_REGIME_WINDOW = 100


def _parse_risk_model(strategy_text: str) -> dict:
    """Phase 2 — parse risk_model + ATR k/m from the strategy text the
    diversity generator emits.

    Returns:
        {
          "model": "fixed_rr_1_2" | "fixed_rr_1_3" | "atr_based" |
                   "structure_based" | "trailing_stop" | None,
          "atr_k": float | None,    # SL multiplier
          "atr_m": float | None,    # TP multiplier
        }
    Falls back to {"model": None, ...} when nothing matches — caller then
    keeps the existing static SL/TP behaviour (Phase-1 contract).
    """
    text = (strategy_text or "")
    low = text.lower()
    model = None
    if "atr_based" in low or "atr-based" in low or "atr×" in low or "atr ×" in low or "atr·" in low or "(atr×" in low:
        model = "atr_based"
    elif "trailing_stop" in low or "trailing stop" in low or "trail after +1r" in low or "trail behind" in low:
        model = "trailing_stop"
    elif "fixed_rr_1_3" in low or "1:3 risk" in low or "1:3 rr" in low or "(fixed 1:3 rr)" in low:
        model = "fixed_rr_1_3"
    elif "fixed_rr_1_2" in low or "1:2 risk" in low or "1:2 rr" in low or "(fixed 1:2 rr)" in low:
        model = "fixed_rr_1_2"
    elif "structure_based" in low or "swing high" in low or "swing low" in low or "next structure" in low:
        model = "structure_based"
    # ATR multipliers. Generator emits formats like:
    #   "SL=17 pips (ATR×1.4) | TP=29 pips (ATR×2.1)"
    #   "ATR k=1.5 m=3.0"
    # We accept both: first ATR×N → atr_k, second ATR×N → atr_m.
    atr_k = None
    atr_m = None
    cross_matches = re.findall(r"atr[\s×x*\u00d7]\s*([0-9]+\.?[0-9]*)", low)
    if len(cross_matches) >= 1:
        try:
            atr_k = float(cross_matches[0])
        except ValueError:
            atr_k = None
    if len(cross_matches) >= 2:
        try:
            atr_m = float(cross_matches[1])
        except ValueError:
            atr_m = None
    if atr_k is None:
        mk = re.search(r"atr[^a-z0-9]{0,4}k\s*=\s*([0-9]+\.?[0-9]*)", low)
        if mk:
            try:
                atr_k = float(mk.group(1))
            except ValueError:
                atr_k = None
    if atr_m is None:
        mm = re.search(r"atr[^a-z0-9]{0,4}m\s*=\s*([0-9]+\.?[0-9]*)", low)
        if mm:
            try:
                atr_m = float(mm.group(1))
            except ValueError:
                atr_m = None
    return {"model": model, "atr_k": atr_k, "atr_m": atr_m}


# Session-aware spread multipliers. Ports `regime_classifier`-style
# scale-free logic to a simple GMT-hour table. London 07-11 GMT and NY
# 13-17 GMT are tightest; Asian 00-07 GMT is widest. Hours outside
# active sessions use a mild widening factor.
_SESSION_SPREAD_MULTIPLIER: dict = {
    # 0..23 (GMT hour)
    0: 1.6, 1: 1.7, 2: 1.7, 3: 1.6, 4: 1.5, 5: 1.4, 6: 1.2,
    7: 1.0, 8: 1.0, 9: 1.0, 10: 1.0, 11: 1.1,
    12: 1.1, 13: 1.0, 14: 1.0, 15: 1.0, 16: 1.0, 17: 1.1,
    18: 1.2, 19: 1.3, 20: 1.4, 21: 1.5, 22: 1.5, 23: 1.6,
}


def _session_spread_multiplier(timestamp) -> float:
    """Return a spread multiplier for the given timestamp (ISO string,
    datetime, or `None`). Falls back to 1.0 when the hour can't be
    derived. Phase 2 — additive only; default-on with a multiplier of
    1.0 means callers without timestamps see no behaviour change."""
    if not timestamp:
        return 1.0
    try:
        if isinstance(timestamp, str):
            # Cheap path — just grab the hour digits when present.
            # Examples: "2024-01-01T13:00:00+00:00", "2024-01-01 03:30"
            m = re.search(r"T(\d{2}):", timestamp)
            if not m:
                m = re.search(r"\s(\d{2}):", timestamp)
            if m:
                hour = int(m.group(1)) % 24
                return _SESSION_SPREAD_MULTIPLIER.get(hour, 1.0)
            return 1.0
        # datetime-like object
        hour = getattr(timestamp, "hour", None)
        if hour is None:
            return 1.0
        return _SESSION_SPREAD_MULTIPLIER.get(int(hour) % 24, 1.0)
    except (TypeError, ValueError):
        return 1.0


# ══════════════════════════════════════════════════════════════
# Signal generators per strategy type
# ══════════════════════════════════════════════════════════════

def _signal_trend_following(i: int, prices, fast_ma, slow_ma, rsi_vals, rsi_cfg) -> str | None:
    """EMA crossover + optional RSI filter."""
    if fast_ma[i] is None or slow_ma[i] is None:
        return None
    if fast_ma[i - 1] is None or slow_ma[i - 1] is None:
        return None
    cross_up = fast_ma[i] > slow_ma[i] and fast_ma[i - 1] <= slow_ma[i - 1]
    cross_down = fast_ma[i] < slow_ma[i] and fast_ma[i - 1] >= slow_ma[i - 1]
    if not cross_up and not cross_down:
        return None
    # Apply RSI filter if available
    if rsi_cfg and rsi_vals[i] is not None:
        if cross_up and rsi_vals[i] < rsi_cfg["buy_threshold"]:
            return None  # RSI doesn't confirm
        if cross_down and rsi_vals[i] > rsi_cfg["sell_threshold"]:
            return None
    return "BUY" if cross_up else "SELL"


def _signal_mean_reversion(i: int, prices, rsi_vals, rsi_cfg, bb_upper, bb_lower) -> str | None:
    """RSI oversold/overbought + optional BB band touch."""
    if rsi_vals[i] is None:
        return None
    buy_thresh = rsi_cfg.get("buy_threshold", 30) if rsi_cfg else 30
    sell_thresh = rsi_cfg.get("sell_threshold", 70) if rsi_cfg else 70
    # BB confirmation
    if bb_lower and bb_lower[i] is not None:
        if rsi_vals[i] < buy_thresh and prices[i] <= bb_lower[i]:
            return "BUY"
        if rsi_vals[i] > sell_thresh and prices[i] >= bb_upper[i]:
            return "SELL"
    # RSI-only signals
    if rsi_vals[i] < buy_thresh:
        return "BUY"
    if rsi_vals[i] > sell_thresh:
        return "SELL"
    return None


def _signal_momentum(i: int, macd_line, signal_line, histogram, rsi_vals, rsi_cfg) -> str | None:
    """MACD signal line crossover + optional RSI filter."""
    if macd_line[i] is None or signal_line[i] is None:
        return None
    if macd_line[i - 1] is None or signal_line[i - 1] is None:
        return None
    cross_up = macd_line[i] > signal_line[i] and macd_line[i - 1] <= signal_line[i - 1]
    cross_down = macd_line[i] < signal_line[i] and macd_line[i - 1] >= signal_line[i - 1]
    if not cross_up and not cross_down:
        return None
    if rsi_cfg and rsi_vals[i] is not None:
        if cross_up and rsi_vals[i] < rsi_cfg.get("buy_threshold", 40):
            return None
        if cross_down and rsi_vals[i] > rsi_cfg.get("sell_threshold", 60):
            return None
    return "BUY" if cross_up else "SELL"


def _signal_breakout(i: int, prices, fast_ma, rsi_vals, rsi_cfg) -> str | None:
    """Price crosses above/below EMA + RSI confirmation."""
    if fast_ma[i] is None or fast_ma[i - 1] is None:
        return None
    cross_above = prices[i] > fast_ma[i] and prices[i - 1] <= fast_ma[i - 1]
    cross_below = prices[i] < fast_ma[i] and prices[i - 1] >= fast_ma[i - 1]
    if not cross_above and not cross_below:
        return None
    if rsi_cfg and rsi_vals[i] is not None:
        if cross_above and rsi_vals[i] < rsi_cfg.get("buy_threshold", 55):
            return None
        if cross_below and rsi_vals[i] > rsi_cfg.get("sell_threshold", 45):
            return None
    return "BUY" if cross_above else "SELL"


# ══════════════════════════════════════════════════════════════
# Indicator computation helper (Phase-1 correctness fix)
# ══════════════════════════════════════════════════════════════

def _compute_indicators_for_segment(
    seg_prices: list,
    *,
    fast_period: int,
    slow_period: int,
    indicators_cfg: dict | None,
    strategy_type: str,
    seg_highs: list | None = None,
    seg_lows: list | None = None,
    atr_period: int = 14,
    htf_factor: int = 4,
    htf_period: int = 50,
) -> dict:
    """
    Compute ALL indicator arrays from `seg_prices` ONLY.

    Phase-1 correctness fix:
      * Train and OOS each call this independently — no shared arrays.
      * No leakage: every indicator is computed in-segment.
      * Output shape is always equal to len(seg_prices) so signal
        generators can index safely.

    Phase-2 addition:
      * Computes ATR(`atr_period`, default 14) when high/low arrays are
        provided. Used by ATR-adaptive exits + trailing stops. The array
        is `[None]*n` when H/L are missing, so callers can detect that
        and fall back to static SL/TP.
    """
    n = len(seg_prices)

    fast_ma = _ema(seg_prices, fast_period)
    slow_ma = _ema(seg_prices, slow_period)

    rsi_cfg = None
    rsi_vals = [None] * n
    if indicators_cfg and "rsi" in indicators_cfg:
        rsi_cfg = indicators_cfg["rsi"]
        rsi_vals = _rsi(seg_prices, rsi_cfg["period"])
    elif strategy_type in ("mean_reversion", "momentum", "breakout"):
        rsi_cfg = {"period": 14, "buy_threshold": 50, "sell_threshold": 50}
        if strategy_type == "mean_reversion":
            rsi_cfg = {"period": 14, "buy_threshold": 30, "sell_threshold": 70}
        rsi_vals = _rsi(seg_prices, 14)

    macd_line = [None] * n
    macd_signal = [None] * n
    macd_hist = [None] * n
    macd_cfg = None
    if indicators_cfg and "macd" in indicators_cfg:
        macd_cfg = indicators_cfg["macd"]
        macd_line, macd_signal, macd_hist = _macd(
            seg_prices, macd_cfg["fast"], macd_cfg["slow"], macd_cfg["signal"],
        )
    elif strategy_type == "momentum":
        macd_cfg = {"fast": 12, "slow": 26, "signal": 9}
        macd_line, macd_signal, macd_hist = _macd(seg_prices, 12, 26, 9)

    bb_mid = [None] * n
    bb_upper = [None] * n
    bb_lower = [None] * n
    bb_cfg = None
    if indicators_cfg and "bollinger" in indicators_cfg:
        bb_cfg = indicators_cfg["bollinger"]
        bb_mid, bb_upper, bb_lower = _bollinger(
            seg_prices, bb_cfg["period"], bb_cfg["std_dev"],
        )
    elif strategy_type == "mean_reversion":
        bb_cfg = {"period": 20, "std_dev": 2.0}
        bb_mid, bb_upper, bb_lower = _bollinger(seg_prices, 20, 2.0)

    # Phase-2 — ATR(14). Computed from H/L when present; otherwise from
    # close-to-close range (less ideal but never wrong).
    atr_vals = _atr(seg_highs or [], seg_lows or [], seg_prices, period=atr_period)

    # Phase-3 — Higher-timeframe (HTF) confirmation series. We coarsen
    # `seg_prices` by every Kth bar (default 4 ⇒ H1→H4) and compute an
    # EMA(`htf_period`) on the coarse series, then upsample back to the
    # segment length. The signal logic uses this to gate entries by HTF
    # trend direction — e.g. only allow longs when HTF EMA is rising.
    # Computed in-segment, so no leakage.
    htf_factor = max(1, int(htf_factor))
    htf_period = max(2, int(htf_period))
    if htf_factor >= 2 and n >= htf_factor * (htf_period + 5):
        coarse = seg_prices[::htf_factor]
        coarse_ema = _ema(coarse, htf_period)
        # Upsample by repeating each coarse value `htf_factor` times.
        htf_ema_series: list = []
        for v in coarse_ema:
            htf_ema_series.extend([v] * htf_factor)
        htf_ema_series = htf_ema_series[:n]
        # Pad if rounding left it short
        while len(htf_ema_series) < n:
            htf_ema_series.append(htf_ema_series[-1] if htf_ema_series else None)
    else:
        htf_ema_series = [None] * n

    return {
        "fast_ma": fast_ma,
        "slow_ma": slow_ma,
        "rsi_vals": rsi_vals,
        "rsi_cfg": rsi_cfg,
        "macd_line": macd_line,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "macd_cfg": macd_cfg,
        "bb_mid": bb_mid,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_cfg": bb_cfg,
        "atr_vals": atr_vals,
        "atr_period": atr_period,
        "htf_ema": htf_ema_series,
        "htf_factor": htf_factor,
        "htf_period": htf_period,
    }


def _run_segment_loop(
    seg_prices: list,
    seg_highs: list,
    seg_lows: list,
    seg_timestamps: list | None,
    *,
    indicators: dict,
    strategy_type: str,
    fast_period: int,
    slow_period: int,
    sl_pips: float,
    tp_pips: float,
    pip_unit: float,
    pip_value_per_lot: float,
    spread_pips: float,
    commission_per_lot: float,
    risk_percent: float,
    initial_balance: float,
    exec_enabled: bool,
    rng: random.Random,
    bar_index_offset: int = 0,
    # Phase-2 additions (all default-safe so Phase-1 tests still pass)
    risk_meta: dict | None = None,
    regime_filter_enabled: bool = False,
    asym_slip_enabled: bool = False,
    session_spread_enabled: bool = False,
    # Phase-3 additions
    htf_filter_enabled: bool = False,
    # P2 — Signal Quality Score (entry-quality filter). Default OFF —
    # strictly opt-in. When enabled, entries with score < threshold are
    # rejected. When disabled, the score is still computed and aggregated
    # for telemetry, but never blocks an entry.
    quality_filter_enabled: bool = False,
    # Phase 28-B — Strategy-IR additive hook. When supplied, the signal
    # path delegates to the IR interpreter instead of the legacy
    # ``_signal_<strategy_type>`` dispatch. None preserves legacy
    # behaviour bit-identically.
    strategy_ir: dict | None = None,
    quality_threshold: float = 60.0,
    # P2 — ruin guard: halt the segment when balance drops below
    # `ruin_floor × initial_balance`. Default 0.10 (10 % of starting).
    # Set to 0 or None to disable.
    ruin_floor: float = DEFAULT_RUIN_FLOOR,
) -> dict:
    """
    Run the trading loop on a single contiguous price segment.

    Phase-1 correctness fix:
      * Indicators MUST be computed from `seg_prices` only and passed in.
      * Highs / lows are populated on each closed trade so the
        execution_engine's intrabar SL/TP flip can activate downstream.
      * No look-ahead: PnL is computed at the current bar only; entries
        and exits use only data up to and including bar `i`.

    Phase-2 additions (all opt-in, never break Phase-1 invariants):
      * Regime gate: when enabled, classifies the trailing 100-bar
        window via `regime_classifier.classify_regime` and suppresses
        entries when the regime ≠ strategy_type's preferred set.
        "unknown" regimes (insufficient samples) are always allowed.
      * ATR-adaptive exits: when `risk_meta["model"] == "atr_based"`,
        each new entry's SL/TP are derived from ATR(14) at the entry
        bar using the strategy's k/m multipliers. Falls back to static
        SL/TP when ATR is None.
      * Trailing stop: when `risk_meta["model"] == "trailing_stop"`,
        the stop moves to break-even after +1R and trails behind price
        by `1 × ATR` after +2R.
      * Asymmetric slippage: losers receive a wider random slip band
        (more realistic adverse fills); winners get a tighter band.
      * Session-aware spread: hourly multiplier scaled by the entry
        timestamp's GMT hour (Asian thin → wider; London/NY peak →
        flat).
    """
    fast_ma = indicators["fast_ma"]
    slow_ma = indicators["slow_ma"]
    rsi_vals = indicators["rsi_vals"]
    rsi_cfg = indicators["rsi_cfg"]
    macd_line = indicators["macd_line"]
    macd_signal = indicators["macd_signal"]
    macd_hist = indicators["macd_hist"]
    macd_cfg = indicators["macd_cfg"]
    bb_upper = indicators["bb_upper"]
    bb_lower = indicators["bb_lower"]
    bb_cfg = indicators["bb_cfg"]
    atr_vals = indicators.get("atr_vals") or [None] * len(seg_prices)
    htf_ema = indicators.get("htf_ema") or [None] * len(seg_prices)

    risk_meta = risk_meta or {}
    risk_model_name = risk_meta.get("model")
    atr_k = risk_meta.get("atr_k")
    atr_m = risk_meta.get("atr_m")

    preferred_regimes = _REGIME_PREFERENCE.get(strategy_type, set())

    # Warm-up — same rules as the legacy implementation.
    warmup = slow_period + 1
    if macd_cfg:
        warmup = max(warmup, macd_cfg["slow"] + macd_cfg["signal"] + 1)
    if bb_cfg:
        warmup = max(warmup, bb_cfg["period"] + 1)

    n = len(seg_prices)
    trades: list = []
    position = None
    balance = initial_balance
    peak_balance = initial_balance
    max_drawdown_usd = 0.0
    total_commission = 0.0
    total_spread_cost = 0.0
    total_slippage_cost = 0.0
    equity_curve = [round(initial_balance, 2)]

    # Phase-2 — counters for telemetry. Surfaced in the segment return
    # so callers can inspect how aggressively the new gates fired.
    regime_blocked_count = 0
    atr_used_count = 0
    trailing_used_count = 0
    htf_blocked_count = 0  # Phase-3
    # P2 — Signal Quality Score telemetry. `evaluated` counts every
    # signal that produced a score (filter on or off); `blocked` counts
    # entries rejected by the threshold; `score_sum` is used to derive
    # the average score on the segment.
    quality_evaluated_count = 0
    quality_blocked_count = 0
    quality_score_sum = 0.0
    # P2 — ruin-guard telemetry
    ruin_floor_abs = (
        float(initial_balance) * float(ruin_floor)
        if ruin_floor and ruin_floor > 0 else None
    )
    ruin_triggered = False
    ruin_index = None

    # Phase 28-B — additive hook: if a Strategy-IR is supplied, build
    # the interpreter once and route every per-bar signal call through
    # it. Otherwise fall back to the legacy strategy_type dispatch.
    _ir_interp = None
    if strategy_ir is not None:
        try:
            from engines.ir_interpreter import IRInterpreter as _IR
            _ir_interp = _IR(
                strategy_ir,
                prices=seg_prices, highs=seg_highs, lows=seg_lows,
                timestamps=seg_timestamps,
                strategy_timeframe=(
                    (strategy_ir.get("metadata") or {}).get("timeframe") or "H1"
                ),
            )
        except Exception:                                # pragma: no cover
            _ir_interp = None  # silently fall back; legacy path remains correct

    def _signal_at(i: int):
        if _ir_interp is not None:
            return _ir_interp.signal_at(i)
        if strategy_type == "mean_reversion":
            return _signal_mean_reversion(i, seg_prices, rsi_vals, rsi_cfg, bb_upper, bb_lower)
        if strategy_type == "momentum":
            return _signal_momentum(i, macd_line, macd_signal, macd_hist, rsi_vals, rsi_cfg)
        if strategy_type == "breakout":
            return _signal_breakout(i, seg_prices, fast_ma, rsi_vals, rsi_cfg)
        return _signal_trend_following(i, seg_prices, fast_ma, slow_ma, rsi_vals, rsi_cfg)

    def _regime_allows(i: int) -> bool:
        """Phase-2 — regime gate. Returns True when the trailing window's
        regime ∈ preferred_regimes for `strategy_type`. Insufficient
        samples (`unknown`) is always allowed so we never starve the
        early-bar period."""
        if not regime_filter_enabled or not preferred_regimes:
            return True
        lo = max(0, i - _REGIME_WINDOW + 1)
        window = seg_prices[lo:i + 1]
        if len(window) < 30:
            return True
        try:
            r = _classify_regime(window, window=_REGIME_WINDOW)
            regime_label = r.get("regime") if isinstance(r, dict) else r
        except Exception:
            return True
        return regime_label in preferred_regimes

    def _htf_allows(i: int, side: str) -> bool:
        """Phase-3 — multi-TF confirmation gate.

        Returns True when the higher-timeframe EMA at bar `i` confirms
        the entry direction:
          * BUY  → HTF EMA must be rising over the last `htf_factor` bars.
          * SELL → HTF EMA must be falling.
        Bars without an HTF EMA (warm-up) are allowed through so we
        don't starve the early period of the segment.
        """
        if not htf_filter_enabled:
            return True
        if i >= len(htf_ema) or htf_ema[i] is None:
            return True
        # Compare to a value 1 HTF-bar back (= htf_factor base bars)
        lookback = max(0, i - 4)
        if htf_ema[lookback] is None:
            return True
        slope_up = htf_ema[i] > htf_ema[lookback]
        slope_dn = htf_ema[i] < htf_ema[lookback]
        if side == "BUY":
            return slope_up
        if side == "SELL":
            return slope_dn
        return True

    for i in range(warmup, n):
        signal = None
        entry_quality = None  # populated only when an entry passes all gates
        if position is None and not ruin_triggered:
            sig_raw = _signal_at(i)
            if sig_raw is not None:
                if not _regime_allows(i):
                    regime_blocked_count += 1
                elif not _htf_allows(i, sig_raw):
                    htf_blocked_count += 1
                else:
                    # P2 — Compute signal-quality score for the candidate
                    # entry. Always evaluated (telemetry), only used as a
                    # gate when `quality_filter_enabled=True`.
                    q = _compute_quality(
                        side=sig_raw,
                        i=i,
                        seg_prices=seg_prices,
                        fast_ma=fast_ma,
                        slow_ma=slow_ma,
                        atr_vals=atr_vals,
                        htf_ema=htf_ema,
                        seg_timestamps=seg_timestamps,
                    )
                    quality_evaluated_count += 1
                    quality_score_sum += float(q["score"])
                    if quality_filter_enabled and q["score"] < quality_threshold:
                        quality_blocked_count += 1
                    else:
                        signal = sig_raw
                        entry_quality = q

        # ── Entry ──
        if signal and position is None:
            # Phase-2 — session-aware spread (entry side)
            ts_at_i = seg_timestamps[i] if seg_timestamps and i < len(seg_timestamps) else None
            sess_mult = _session_spread_multiplier(ts_at_i) if session_spread_enabled else 1.0
            effective_spread = spread_pips * sess_mult

            slippage = 0.0 if exec_enabled else rng.uniform(0, 0.5)
            raw_price = seg_prices[i]
            if signal == "BUY":
                entry_price = raw_price + (effective_spread / 2 + slippage) * pip_unit
            else:
                entry_price = raw_price - (effective_spread / 2 + slippage) * pip_unit

            # Phase-2 — ATR-adaptive SL/TP (per-trade overrides). Falls
            # back to the static sl_pips/tp_pips when ATR is None or the
            # risk_model isn't an ATR variant.
            this_sl_pips = float(sl_pips)
            this_tp_pips = float(tp_pips)
            atr_at_i = atr_vals[i] if i < len(atr_vals) else None
            if risk_model_name in ("atr_based", "trailing_stop") and atr_at_i and atr_at_i > 0:
                k = atr_k if atr_k and atr_k > 0 else 1.5
                m = atr_m if atr_m and atr_m > 0 else 3.0
                atr_pips = atr_at_i / pip_unit
                this_sl_pips = max(2.0, atr_pips * k)
                this_tp_pips = max(2.0, atr_pips * m)
                atr_used_count += 1

            risk_amount = balance * (risk_percent / 100.0)
            lot_size = risk_amount / (this_sl_pips * pip_value_per_lot) if this_sl_pips > 0 else 0.01
            lot_size = round(max(lot_size, 0.01), 2)
            position = {
                "entry_price": entry_price,
                "raw_entry": raw_price,
                "entry_idx": i,
                "direction": signal,
                "lot_size": lot_size,
                "entry_slippage": slippage,
                "entry_spread_mult": sess_mult,
                "this_sl_pips": this_sl_pips,
                "this_tp_pips": this_tp_pips,
                "trail_active": False,    # set after +1R / +2R milestones
                "trail_stop_pips": None,  # current trailing stop in pips
                "mfe_pips": 0.0,
                "mae_pips": 0.0,
                # P2 — entry-quality score snapshot for this trade
                "entry_quality": entry_quality,
            }

        # ── Exit ──
        elif position is not None:
            raw_price = seg_prices[i]
            entry = position["entry_price"]
            this_sl_pips = position["this_sl_pips"]
            this_tp_pips = position["this_tp_pips"]
            if position["direction"] == "BUY":
                pnl_pips_raw = (raw_price - entry) / pip_unit
            else:
                pnl_pips_raw = (entry - raw_price) / pip_unit

            if pnl_pips_raw > position["mfe_pips"]:
                position["mfe_pips"] = pnl_pips_raw
            if pnl_pips_raw < position["mae_pips"]:
                position["mae_pips"] = pnl_pips_raw

            # P6 audit fix #2 — intracandle MAE/MFE using bar high/low.
            # Closes-only measurement underestimates the real intra-trade
            # low. When the loader provides highs/lows, recompute the
            # adverse and favourable excursions for THIS bar using the
            # bar extremes and widen MAE/MFE accordingly.
            bar_hi = seg_highs[i] if seg_highs and i < len(seg_highs) else None
            bar_lo = seg_lows[i] if seg_lows and i < len(seg_lows) else None
            if bar_hi is not None and bar_lo is not None:
                if position["direction"] == "BUY":
                    bar_adverse = (bar_lo - entry) / pip_unit       # ≤ 0
                    bar_favourable = (bar_hi - entry) / pip_unit    # ≥ 0
                else:
                    bar_adverse = (entry - bar_hi) / pip_unit
                    bar_favourable = (entry - bar_lo) / pip_unit
                if bar_adverse < position["mae_pips"]:
                    position["mae_pips"] = bar_adverse
                if bar_favourable > position["mfe_pips"]:
                    position["mfe_pips"] = bar_favourable

            # Phase-2 — trailing stop semantics. After +1R move SL to BE;
            # after +2R, trail behind price by 1 × ATR (or by sl_pips
            # when ATR is unavailable). Never relax stop.
            if risk_model_name == "trailing_stop":
                atr_at_i = atr_vals[i] if i < len(atr_vals) else None
                # Distance the price has moved from BE in the favorable
                # direction — measured in pips off the entry.
                fav_pips = pnl_pips_raw  # positive = favorable
                if fav_pips >= this_sl_pips * 2.0 and atr_at_i and atr_at_i > 0:
                    # Trail behind price by 1 ATR (in pips)
                    atr_pips = atr_at_i / pip_unit
                    new_trail = max(0.0, fav_pips - atr_pips)
                    if position["trail_stop_pips"] is None or new_trail > position["trail_stop_pips"]:
                        position["trail_stop_pips"] = new_trail
                        position["trail_active"] = True
                        trailing_used_count += 1
                elif fav_pips >= this_sl_pips and not position["trail_active"]:
                    # Move stop to break-even (0 pips) — never relaxes.
                    position["trail_stop_pips"] = 0.0
                    position["trail_active"] = True
                    trailing_used_count += 1

            # Effective SL: the static SL or the (better) trail.
            effective_sl_pips = -this_sl_pips
            if position["trail_stop_pips"] is not None:
                # Trail stop is expressed as pips of FAVORABLE move below
                # which we exit. Convert to a pnl_pips_raw threshold.
                effective_sl_pips = position["trail_stop_pips"]

            hit_sl = pnl_pips_raw <= effective_sl_pips
            hit_tp = pnl_pips_raw >= this_tp_pips
            last_bar = i == n - 1

            reverse_signal = False
            rev = _signal_at(i)
            if rev is not None and rev != position["direction"]:
                reverse_signal = True

            # P6 audit fix #3 — weekend / FX-rollover gap handling.
            # FX closes Friday ~21:00 UTC and reopens Sunday ~21:00 UTC.
            # Real accounts see Monday-open gap past stops frequently;
            # our sim previously held through the weekend at the last
            # Friday close with zero adverse impact — a major false-PASS
            # vector. Force-close any open position on the last Friday
            # bar ≥ 20:00 UTC with a conservative extra spread penalty
            # so the trade reflects the weekend-carry risk.
            weekend_boundary = False
            ts_at_i = seg_timestamps[i] if seg_timestamps and i < len(seg_timestamps) else None
            if ts_at_i is not None:
                try:
                    if isinstance(ts_at_i, str):
                        _dt = datetime.fromisoformat(ts_at_i.replace("Z", "+00:00"))
                    else:
                        _dt = ts_at_i
                    if getattr(_dt, "tzinfo", None) is None:
                        _dt = _dt.replace(tzinfo=timezone.utc)
                    _dt_utc = _dt.astimezone(timezone.utc) if _dt.tzinfo != timezone.utc else _dt
                    # Friday = weekday 4 (Mon=0). Carry-risk window: 20:00 UTC Fri → end of day.
                    if _dt_utc.weekday() == 4 and _dt_utc.hour >= 20:
                        weekend_boundary = True
                except (TypeError, ValueError):
                    pass

            if hit_sl or hit_tp or last_bar or reverse_signal or weekend_boundary:
                # Phase-2 — asymmetric slippage + session-aware spread on
                # the EXIT side. Losers eat a wider random slip; winners
                # see tighter fills. Session multiplier applies to the
                # spread component.
                ts_at_i_exit = seg_timestamps[i] if seg_timestamps and i < len(seg_timestamps) else None
                sess_mult_exit = _session_spread_multiplier(ts_at_i_exit) if session_spread_enabled else 1.0
                effective_spread_exit = spread_pips * sess_mult_exit
                if exec_enabled:
                    exit_slippage = 0.0
                else:
                    if asym_slip_enabled:
                        # Pre-classify: if the bar's pnl_pips_raw is
                        # negative, treat as adverse-fill side.
                        is_loser_bar = pnl_pips_raw < 0
                        if is_loser_bar:
                            exit_slippage = rng.uniform(0.2, 1.5)
                        else:
                            exit_slippage = rng.uniform(0.0, 0.3)
                    else:
                        exit_slippage = rng.uniform(0, 0.5)
                if position["direction"] == "BUY":
                    exit_price = raw_price - (effective_spread_exit / 2 + exit_slippage) * pip_unit
                else:
                    exit_price = raw_price + (effective_spread_exit / 2 + exit_slippage) * pip_unit

                # P6 audit fix #3 — weekend-carry penalty. Forcing a
                # close at Friday 20:00 UTC is half the fix; the other
                # half is charging the trade an adverse 3× spread so
                # a strategy that routinely carries positions over the
                # weekend isn't artificially rewarded for avoiding
                # Monday-open gap risk.
                if weekend_boundary and not (hit_sl or hit_tp):
                    gap_penalty_pips = 3.0 * max(effective_spread_exit, 1.0)
                    if position["direction"] == "BUY":
                        exit_price -= gap_penalty_pips * pip_unit
                    else:
                        exit_price += gap_penalty_pips * pip_unit

                if position["direction"] == "BUY":
                    final_pnl_pips = (exit_price - entry) / pip_unit
                else:
                    final_pnl_pips = (entry - exit_price) / pip_unit

                lot = position["lot_size"]
                gross_pnl_usd = final_pnl_pips * pip_value_per_lot * lot
                commission = commission_per_lot * lot
                # Spread cost on this trade reflects the session-weighted
                # average of entry and exit multipliers.
                avg_spread_pips = (
                    spread_pips * position["entry_spread_mult"]
                    + spread_pips * sess_mult_exit
                ) / 2.0
                spread_cost = avg_spread_pips * pip_value_per_lot * lot
                slippage_cost = (position["entry_slippage"] + exit_slippage) * pip_value_per_lot * lot
                net_pnl_usd = gross_pnl_usd - commission

                balance += net_pnl_usd
                total_commission += commission
                total_spread_cost += spread_cost
                total_slippage_cost += slippage_cost

                if balance > peak_balance:
                    peak_balance = balance
                dd = peak_balance - balance
                if dd > max_drawdown_usd:
                    max_drawdown_usd = dd

                # P2 — ruin guard: if the new balance has dropped below
                # the floor, flag the segment and stop opening new
                # positions for the remainder of the run. Any already-
                # open position is already closed at this point in the
                # branch; new entries are short-circuited by the
                # `ruin_triggered` check at the top of the loop.
                if (ruin_floor_abs is not None
                        and not ruin_triggered
                        and balance <= ruin_floor_abs):
                    ruin_triggered = True
                    ruin_index = i

                equity_curve.append(round(balance, 2))

                exit_reason = (
                    "TP" if hit_tp else (
                        "SL" if hit_sl else (
                            "WEEKEND" if weekend_boundary else (
                                "REV" if reverse_signal else "CLOSED"))))
                if position["direction"] == "BUY":
                    sl_price_lvl = entry - this_sl_pips * pip_unit
                    tp_price_lvl = entry + this_tp_pips * pip_unit
                else:
                    sl_price_lvl = entry + this_sl_pips * pip_unit
                    tp_price_lvl = entry - this_tp_pips * pip_unit

                entry_idx_local = position["entry_idx"]
                # Global bar index (for cross-segment uniqueness when caller
                # passes `bar_index_offset`).
                entry_idx_global = entry_idx_local + bar_index_offset
                exit_idx_global = i + bar_index_offset

                if seg_timestamps and entry_idx_local < len(seg_timestamps):
                    entry_time_val = seg_timestamps[entry_idx_local]
                    exit_time_val = seg_timestamps[i] if i < len(seg_timestamps) else seg_timestamps[-1]
                else:
                    entry_time_val = f"bar_{entry_idx_global}"
                    exit_time_val = f"bar_{exit_idx_global}"

                mae_pips = round(-position["mae_pips"], 1)
                mfe_pips = round(position["mfe_pips"], 1)
                mae_usd = round(mae_pips * pip_value_per_lot * lot, 2)
                mfe_usd = round(mfe_pips * pip_value_per_lot * lot, 2)
                risk_usd = this_sl_pips * pip_value_per_lot * lot
                r_multiple = round(net_pnl_usd / risk_usd, 2) if risk_usd > 0 else 0.0

                # Phase-1 fix: populate candle high/low for the EXIT bar so
                # the execution_engine's intrabar SL/TP race can activate.
                exit_hi = seg_highs[i] if seg_highs and i < len(seg_highs) else None
                exit_lo = seg_lows[i] if seg_lows and i < len(seg_lows) else None

                trade = {
                    "direction": position["direction"],
                    "side": position["direction"],
                    "entry_price": round(position["raw_entry"], 5),
                    "exit_price": round(raw_price, 5),
                    "entry_time": entry_time_val,
                    "exit_time": exit_time_val,
                    "entry_idx": entry_idx_global,
                    "exit_idx": exit_idx_global,
                    "pnl_pips": round(final_pnl_pips, 1),
                    "lot_size": lot,
                    "gross_pnl": round(gross_pnl_usd, 2),
                    "commission": round(commission, 2),
                    "net_pnl": round(net_pnl_usd, 2),
                    "balance": round(balance, 2),
                    "result": exit_reason,
                    "outcome": exit_reason,
                    "sl_price": round(sl_price_lvl, 5),
                    "tp_price": round(tp_price_lvl, 5),
                    "sl": round(sl_price_lvl, 5),
                    "tp": round(tp_price_lvl, 5),
                    "sl_loss_amount": round(this_sl_pips * pip_value_per_lot * lot, 2),
                    "pip_value": pip_value_per_lot,
                    "lots": lot,
                    "mae": mae_pips,
                    "mfe": mfe_pips,
                    "mae_usd": mae_usd,
                    "mfe_usd": mfe_usd,
                    # P6 audit fix #1 — expose the real MAE in USD as
                    # `floating_min_pnl` so `challenge_simulator`
                    # consumes the measured floating equity low
                    # instead of the `net_pnl × 2` estimate. `mae_usd`
                    # is stored as a positive magnitude (see the
                    # `-position["mae_pips"]` negation above); the
                    # simulator expects floating_min_pnl ≤ 0 for
                    # adverse excursions, so we negate here. Zero stays
                    # zero (no excursion).
                    "floating_min_pnl": -mae_usd,
                    "r_multiple": r_multiple,
                }
                if exit_hi is not None:
                    trade["candle_high"] = exit_hi
                if exit_lo is not None:
                    trade["candle_low"] = exit_lo
                # P2 — surface entry-quality score on the closed trade
                # (None when filter never ran, e.g. malformed inputs).
                eq = position.get("entry_quality")
                if eq:
                    trade["entry_quality_score"] = eq.get("score")
                    trade["entry_quality_components"] = eq.get("components")
                trades.append(trade)
                position = None

    return {
        "trades": trades,
        "balance": balance,
        "peak_balance": peak_balance,
        "max_drawdown_usd": max_drawdown_usd,
        "total_commission": total_commission,
        "total_spread_cost": total_spread_cost,
        "total_slippage_cost": total_slippage_cost,
        "equity_curve": equity_curve,
        "warmup": warmup,
        # Phase-2 telemetry
        "regime_blocked": regime_blocked_count,
        "atr_used": atr_used_count,
        "trailing_used": trailing_used_count,
        # Phase-3 telemetry
        "htf_blocked": htf_blocked_count,
        # P2 — Signal Quality telemetry
        "quality_evaluated": quality_evaluated_count,
        "quality_blocked": quality_blocked_count,
        "quality_score_sum": quality_score_sum,
        "quality_filter_enabled": quality_filter_enabled,
        "quality_threshold": quality_threshold,
        # P2 — Ruin-guard telemetry
        "ruin_triggered": ruin_triggered,
        "ruin_index": ruin_index,
        "ruin_floor_abs": ruin_floor_abs,
    }


# ══════════════════════════════════════════════════════════════
# Main backtest function
# ══════════════════════════════════════════════════════════════

def _build_signal_quality_block(
    train_run: dict, oos_run: dict,
    enabled: bool, threshold: float,
) -> dict:
    """P2 — Build the `_phase4_signal_quality` telemetry block.

    Surfaces:
      * filter on/off + threshold
      * IS / OOS average score (over EVALUATED entries)
      * IS / OOS filtered-out percentage
      * IS / OOS evaluated + blocked counters
    Defensive: any zero-evaluated segment yields avg_score=None and
    filter_pct=0.0 instead of dividing by zero.
    """
    def _avg(s, n):
        return round(float(s) / float(n), 2) if n and n > 0 else None

    def _pct(blocked, evaluated):
        return round(100.0 * (blocked or 0) / (evaluated or 1), 2) if evaluated else 0.0

    is_eval = int(train_run.get("quality_evaluated", 0) or 0)
    is_blk = int(train_run.get("quality_blocked", 0) or 0)
    is_sum = float(train_run.get("quality_score_sum", 0.0) or 0.0)
    oos_eval = int(oos_run.get("quality_evaluated", 0) or 0)
    oos_blk = int(oos_run.get("quality_blocked", 0) or 0)
    oos_sum = float(oos_run.get("quality_score_sum", 0.0) or 0.0)

    return {
        "quality_filter_enabled": bool(enabled),
        "quality_threshold": float(threshold),
        "is_avg_score": _avg(is_sum, is_eval),
        "oos_avg_score": _avg(oos_sum, oos_eval),
        "is_quality_evaluated": is_eval,
        "oos_quality_evaluated": oos_eval,
        "is_quality_blocked": is_blk,
        "oos_quality_blocked": oos_blk,
        "is_quality_filter_pct": _pct(is_blk, is_eval),
        "oos_quality_filter_pct": _pct(oos_blk, oos_eval),
    }


def run_backtest_logic(strategy_text: str, pair: str, timeframe: str,
                       external_prices: list = None, data_source: str = "sample",
                       data_points: int = 0, sim_config: dict = None,
                       param_overrides: dict = None,
                       indicators_override: dict = None,
                       strategy_type_override: str = None,
                       external_timestamps: list = None,
                       external_highs: list = None,
                       external_lows: list = None,
                       strategy_ir: dict | None = None) -> dict:
    """
    Full multi-indicator backtest engine.
    Extracts strategy type + indicators from text, computes all relevant
    indicators, and applies matching signal logic.

    indicators_override: dict with keys like "rsi", "macd", "bollinger"
        to override extracted indicator configs (used by optimizer).
    strategy_type_override: str to force strategy type (used by optimizer).
    external_highs / external_lows: optional OHLC high/low arrays aligned
        with `external_prices`. When provided, the per-trade candle range
        is attached so the execution_engine's intrabar SL/TP flip can
        activate.
    strategy_ir: Phase 28-B additive hook — when supplied, signal
        generation routes through the IR interpreter instead of the
        legacy ``_signal_<strategy_type>`` dispatch. None preserves
        bit-identical legacy behaviour.
    """

# ══════════════════════════════════════════════════════════════
# STRICT REAL DATA MODE (NO FAKE DATA ALLOWED)
# ══════════════════════════════════════════════════════════════

    if not external_prices or len(external_prices) < 200:
        # P0 — structured, non-crashing error. All downstream code
        # already handles the `error` key; we also zero out every
        # metric that _could_ be `None` so the refinement / mutation
        # paths never multiply a NoneType by a float.
        return {
            "error": "no_real_data",
            "message": f"No real market data available for {pair}/{timeframe}. Please load data first.",
            "data_source": "none",
            "data_points": len(external_prices or []),
            "candles_required": 200,
            "total_trades": 0,
            # Scalar defaults — NEVER None, so `x * 1.15` can't crash.
            "profit_factor": 0.0,
            "oos_profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "oos_max_drawdown_pct": 0.0,
            "total_return_pct": 0.0,
            "oos_total_return_pct": 0.0,
            "net_profit": 0.0,
            "oos_net_profit": 0.0,
            "win_rate": 0.0,
            "oos_win_rate": 0.0,
            "sharpe_ratio": 0.0,
            "oos_sharpe_ratio": 0.0,
            "initial_balance": 10000.0,
            "final_balance": 10000.0,
            "oos_total_trades": 0,
        }

    prices = external_prices
    data_source = "real"
    data_points = len(prices)

# ═══════════════════════════════════════════════════════
# OOS SPLIT (70% train / 30% test)
# ═══════════════════════════════════════════════════════

    split_idx = int(len(prices) * 0.7)

    train_prices = prices[:split_idx]
    test_prices = prices[split_idx:]

    # Phase-1 fix: split highs/lows/timestamps the same way so OOS gets
    # its own aligned slice (no leakage, no length mismatches).
    train_highs = (external_highs[:split_idx] if external_highs else None)
    test_highs = (external_highs[split_idx:] if external_highs else None)
    train_lows = (external_lows[:split_idx] if external_lows else None)
    test_lows = (external_lows[split_idx:] if external_lows else None)
    train_timestamps = (external_timestamps[:split_idx] if external_timestamps else None)
    test_timestamps = (external_timestamps[split_idx:] if external_timestamps else None)

    seed = _deterministic_seed(strategy_text)
    rng = random.Random(seed)

    # ── Parameter extraction ──
    po = param_overrides or {}
    extraction = None
    indicators_cfg = None
    strategy_type = "trend_following"

    if not param_overrides:
        extraction = extract_params(strategy_text)
        if extraction["overrides"]:
            po = extraction["overrides"]
        indicators_cfg = extraction.get("indicators")
        strategy_type = extraction.get("strategy_type", "trend_following")
    else:
        # Even with param_overrides, detect strategy type from text
        # so the correct signal logic is used
        extraction = extract_params(strategy_text)
        strategy_type = extraction.get("strategy_type", "trend_following")
        indicators_cfg = extraction.get("indicators")

    # Allow explicit overrides from optimizer
    if strategy_type_override:
        strategy_type = strategy_type_override
    if indicators_override:
        indicators_cfg = indicators_override

    fast_period = po.get("fast_period", 5 + (seed % 4))
    slow_period = po.get("slow_period", 13 + (seed % 9))
    sl_pips = po.get("sl_pips", 15 + (seed % 11))
    tp_pips = po.get("tp_pips", int(sl_pips * 1.5) + (seed % 10))

    param_source = "overrides" if param_overrides else (
        "extracted" if (extraction and extraction["overrides"]) else "seed"
    )

    # ── Simulation config ──
    cfg = sim_config or {}
    # Execution-realism handoff: when `execution.enabled=True` the unified
    # execution_engine becomes the SOLE source of spread/slippage/commission
    # costs. The internal legacy costs are zeroed so we don't double-count.
    # When execution is absent or disabled, the legacy path is preserved
    # verbatim for backward compatibility.
    exec_cfg_resolved = resolve_exec_config(cfg)
    exec_enabled = bool(exec_cfg_resolved.get("enabled"))
    if exec_enabled:
        spread_pips = 0.0
        commission_per_lot = 0.0
    else:
        spread_pips = cfg.get("spread_pips", DEFAULT_SPREADS.get(pair, 1.5))
        commission_per_lot = cfg.get("commission_per_lot", 7.0)
    risk_percent = cfg.get("risk_percent", 1.0)
    initial_balance = cfg.get("initial_balance", 10000.0)
    pip_unit = PIP_UNITS.get(pair, 0.0001)
    pip_value_per_lot = PIP_VALUES.get(pair, 10.0)

    # ── Phase-1 fix: compute indicators SEPARATELY for train and OOS ──
    # `train_inds` is used for the in-sample loop AND for active_indicators
    # reporting; `oos_inds` is used only for the OOS loop. There is now
    # zero shared state between the two segments.
    # Phase-3 — multi-timeframe HTF confirmation params (default H1→H4).
    mtf_factor = int(cfg.get("mtf_factor", 4))
    mtf_period = int(cfg.get("mtf_period", 50))
    train_inds = _compute_indicators_for_segment(
        train_prices,
        fast_period=fast_period, slow_period=slow_period,
        indicators_cfg=indicators_cfg, strategy_type=strategy_type,
        seg_highs=train_highs, seg_lows=train_lows,
        htf_factor=mtf_factor, htf_period=mtf_period,
    )
    oos_inds = _compute_indicators_for_segment(
        test_prices,
        fast_period=fast_period, slow_period=slow_period,
        indicators_cfg=indicators_cfg, strategy_type=strategy_type,
        seg_highs=test_highs, seg_lows=test_lows,
        htf_factor=mtf_factor, htf_period=mtf_period,
    )

    # Phase-2 — risk-model parsing (additive). When we can parse it, the
    # segment loop applies ATR-adaptive SL/TP or trailing-stop semantics
    # for that single trade. When we can't, callers fall back to the
    # static `sl_pips` / `tp_pips` from extraction or the seed defaults.
    risk_meta = _parse_risk_model(strategy_text)

    # Phase-2 — regime gate is opt-in per call but DEFAULT-ON for the
    # mainline pipelines. Disable via `sim_config["regime_filter"] = False`
    # to fall back to Phase-1 behaviour (e.g. for unit tests).
    # P1 — Simplified default filter stack.
    # Previously both regime_filter and mtf_filter defaulted ON, which on
    # real forex data choked ~100 % of signals (live repro: 554 regime
    # blocks, 227 MTF blocks on a single run). The P1 rule is: keep only
    # the ATR-based exits as a default protection; MTF + Regime are
    # OPT-IN via `sim_config["mtf_filter"]=True` / `regime_filter=True`.
    regime_filter_enabled = bool(cfg.get("regime_filter", False))
    # Phase-2 — asymmetric slippage / session-aware spread are also
    # default-on; flip via `sim_config["asym_slippage"] = False` /
    # `sim_config["session_spread"] = False`.
    asym_slip_enabled = bool(cfg.get("asym_slippage", True))
    session_spread_enabled = bool(cfg.get("session_spread", True))
    # Phase-3 — multi-timeframe gate. P1 update: default-OFF so
    # strategies actually produce trades on real data. Opt-in via
    # `sim_config["mtf_filter"] = True` (H1 entry confirmed by H4
    # trend).
    mtf_filter_enabled = bool(cfg.get("mtf_filter", False))

    # P2 — Signal Quality Score filter. Default-OFF (opt-in only) to
    # match the P1 simplification rule: never starve the engine by
    # default. When ON, an entry is rejected if its 0–100 quality
    # score is below `quality_threshold`. Score is always computed
    # (even when filter is OFF) so the dashboard can surface average
    # score + filter-out rate as telemetry for diagnostic purposes.
    quality_filter_enabled = bool(cfg.get("quality_filter", False))
    quality_threshold = float(cfg.get("quality_threshold", 60.0))

    # P2 — Auto-ATR stops for non-forex assets. Non-forex pairs (XAU,
    # indices, crypto) have pip-units so large that fixed SL=20-pip
    # stops sit inside normal price noise and lose ~100 % of trades.
    # When `atr_stops=true` (default for non-forex, opt-in otherwise)
    # we force the risk model to `atr_based` with sensible defaults,
    # overriding the strategy text's static SL/TP contract.
    pair_upper = (pair or "").upper()
    auto_atr_default = pair_upper not in FOREX_PAIRS
    atr_stops_enabled = bool(cfg.get("atr_stops", auto_atr_default))
    if atr_stops_enabled:
        # If the strategy text already declared atr_k/atr_m we keep
        # them; otherwise we plug in the class defaults so the run
        # can still proceed on a forex-tuned template.
        if risk_meta.get("model") not in ("atr_based", "trailing_stop"):
            risk_meta = dict(risk_meta)
            risk_meta["model"] = "atr_based"
        if not risk_meta.get("atr_k"):
            risk_meta["atr_k"] = DEFAULT_AUTO_ATR_K
        if not risk_meta.get("atr_m"):
            risk_meta["atr_m"] = DEFAULT_AUTO_ATR_M

    # P2 — Ruin floor (balance <= `ruin_floor × initial_balance`).
    # Default 0.10 ⇒ stop trading once the account is at 10 % of start.
    ruin_floor = float(cfg.get("ruin_floor", DEFAULT_RUIN_FLOOR))

    rsi_cfg = train_inds["rsi_cfg"]
    macd_cfg = train_inds["macd_cfg"]
    bb_cfg = train_inds["bb_cfg"]

    # Track which indicators are active
    active_indicators = ["EMA"]
    if rsi_cfg:
        active_indicators.append(f"RSI({rsi_cfg['period']})")
    if macd_cfg:
        active_indicators.append(f"MACD({macd_cfg['fast']}/{macd_cfg['slow']}/{macd_cfg['signal']})")
    if bb_cfg:
        active_indicators.append(f"BB({bb_cfg['period']},{bb_cfg['std_dev']})")
    if risk_meta.get("model"):
        active_indicators.append(f"RISK({risk_meta['model']})")

    # ── In-sample (train) trading loop ──
    train_run = _run_segment_loop(
        train_prices, train_highs, train_lows, train_timestamps,
        indicators=train_inds, strategy_type=strategy_type,
        fast_period=fast_period, slow_period=slow_period,
        sl_pips=sl_pips, tp_pips=tp_pips,
        pip_unit=pip_unit, pip_value_per_lot=pip_value_per_lot,
        spread_pips=spread_pips, commission_per_lot=commission_per_lot,
        risk_percent=risk_percent, initial_balance=initial_balance,
        exec_enabled=exec_enabled, rng=rng, bar_index_offset=0,
        risk_meta=risk_meta,
        regime_filter_enabled=regime_filter_enabled,
        asym_slip_enabled=asym_slip_enabled,
        session_spread_enabled=session_spread_enabled,
        htf_filter_enabled=mtf_filter_enabled,
        quality_filter_enabled=quality_filter_enabled,
        quality_threshold=quality_threshold,
        ruin_floor=ruin_floor,
        strategy_ir=strategy_ir,
    )
    trades = train_run["trades"]
    balance = train_run["balance"]
    peak_balance = train_run["peak_balance"]
    max_drawdown_usd = train_run["max_drawdown_usd"]
    total_commission = train_run["total_commission"]
    total_spread_cost = train_run["total_spread_cost"]
    total_slippage_cost = train_run["total_slippage_cost"]
    equity_curve = train_run["equity_curve"]
    # warmup is exposed by _run_segment_loop for completeness; not used
    # again in the outer scope (each segment does its own warmup).

    # ── Execution realism pass (unified) ──
    # When enabled, execution_engine applies spread / slippage / commission /
    # intrabar flip to the trade list. Internal spread_pips/commission_per_lot
    # were already zeroed above, so there is no double-counting.
    if exec_enabled and trades:
        trades = apply_execution_to_trades(trades, cfg)
        # Recompute balance, equity curve, drawdown, and cost totals from
        # the adjusted trades.
        balance = initial_balance
        peak_balance = initial_balance
        max_drawdown_usd = 0.0
        equity_curve = [round(initial_balance, 2)]
        total_commission = 0.0
        total_spread_cost = 0.0
        total_slippage_cost = 0.0
        for t in trades:
            balance += t.get("net_pnl", 0)
            if balance > peak_balance:
                peak_balance = balance
            dd = peak_balance - balance
            if dd > max_drawdown_usd:
                max_drawdown_usd = dd
            equity_curve.append(round(balance, 2))
            total_spread_cost += t.get("_exec_spread_cost", 0.0)
            total_slippage_cost += t.get("_exec_slippage_cost", 0.0)
            total_commission += t.get("_exec_commission_cost", 0.0)
            # Keep the 'balance' field on each trade in sync with the replay
            t["balance"] = round(balance, 2)
            t["commission"] = round(t.get("_exec_commission_cost", 0.0), 2)

    # ═══════════════════════════════════════════════════════
    # OOS TEST (REAL VALIDATION — Phase-1 correctness rewrite)
    # ═══════════════════════════════════════════════════════
    # Strict OOS: same trading-loop semantics as the train pass
    # (SL/TP/spread/slippage/commission/risk-sizing all applied), but
    # uses ONLY indicators computed on `test_prices` and ONLY current/past
    # bars. No look-ahead, no shared train arrays.
    oos_rng = random.Random(seed ^ 0xA5A5A5A5)
    oos_run = _run_segment_loop(
        test_prices, test_highs, test_lows, test_timestamps,
        indicators=oos_inds, strategy_type=strategy_type,
        fast_period=fast_period, slow_period=slow_period,
        sl_pips=sl_pips, tp_pips=tp_pips,
        pip_unit=pip_unit, pip_value_per_lot=pip_value_per_lot,
        spread_pips=spread_pips, commission_per_lot=commission_per_lot,
        risk_percent=risk_percent, initial_balance=initial_balance,
        exec_enabled=exec_enabled, rng=oos_rng,
        bar_index_offset=split_idx,
        risk_meta=risk_meta,
        regime_filter_enabled=regime_filter_enabled,
        asym_slip_enabled=asym_slip_enabled,
        session_spread_enabled=session_spread_enabled,
        htf_filter_enabled=mtf_filter_enabled,
        quality_filter_enabled=quality_filter_enabled,
        quality_threshold=quality_threshold,
        ruin_floor=ruin_floor,
        strategy_ir=strategy_ir,
    )
    oos_trades_full = oos_run["trades"]
    if exec_enabled and oos_trades_full:
        oos_trades_full = apply_execution_to_trades(oos_trades_full, cfg)

    oos_total = len(oos_trades_full)
    oos_winning = [t for t in oos_trades_full if t["net_pnl"] > 0]
    oos_losing = [t for t in oos_trades_full if t["net_pnl"] <= 0]
    oos_win_rate = (len(oos_winning) / oos_total * 100) if oos_total else 0
    oos_gross_win = abs(sum(t["gross_pnl"] for t in oos_winning))
    oos_gross_loss = abs(sum(t["gross_pnl"] for t in oos_losing))
    oos_pf = (oos_gross_win / oos_gross_loss) if oos_gross_loss > 0 else 0
    oos_profit = sum(t["net_pnl"] for t in oos_trades_full)
    oos_balance = initial_balance + oos_profit
    # OOS drawdown (based on net_pnl ordering, mirrors IS path)
    oos_peak = initial_balance
    oos_run_balance = initial_balance
    oos_max_dd_usd = 0.0
    for t in oos_trades_full:
        oos_run_balance += t["net_pnl"]
        if oos_run_balance > oos_peak:
            oos_peak = oos_run_balance
        dd = oos_peak - oos_run_balance
        if dd > oos_max_dd_usd:
            oos_max_dd_usd = dd
    oos_max_dd_pct = (oos_max_dd_usd / oos_peak * 100) if oos_peak > 0 else 0

    # ── Aggregate metrics ──
    total_trades = len(trades)
    winning = [t for t in trades if t["net_pnl"] > 0]
    losing = [t for t in trades if t["net_pnl"] <= 0]
    win_rate = (len(winning) / total_trades * 100) if total_trades > 0 else 0
    total_pnl_pips = sum(t["pnl_pips"] for t in trades)
    net_profit = balance - initial_balance
    total_return_pct = (net_profit / initial_balance) * 100
    max_dd_pct = (max_drawdown_usd / peak_balance * 100) if peak_balance > 0 else 0

    max_drawdown_pips = 0
    running = 0
    peak_pips = 0
    for t in trades:
        running += t["pnl_pips"]
        if running > peak_pips:
            peak_pips = running
        dd = peak_pips - running
        if dd > max_drawdown_pips:
            max_drawdown_pips = dd

    avg_win = (sum(t["net_pnl"] for t in winning) / len(winning)) if winning else 0
    avg_loss = (sum(t["net_pnl"] for t in losing) / len(losing)) if losing else 0
    avg_win_pips = (sum(t["pnl_pips"] for t in winning) / len(winning)) if winning else 0
    avg_loss_pips = (sum(t["pnl_pips"] for t in losing) / len(losing)) if losing else 0
    gross_wins = abs(sum(t["gross_pnl"] for t in winning))
    gross_losses = abs(sum(t["gross_pnl"] for t in losing))
    profit_factor = (gross_wins / gross_losses) if gross_losses > 0 else 0
    risk_adjusted = round(total_return_pct / max_dd_pct, 2) if max_dd_pct > 0 else 0

    return {
        "pair": pair,
        "oos_total_trades": oos_total,
        "oos_win_rate": round(oos_win_rate, 2),
        "oos_net_profit": round(oos_profit, 2),
        "oos_profit_factor": round(oos_pf, 2),
        "oos_max_drawdown_pct": round(oos_max_dd_pct, 2),
        "oos_max_drawdown_usd": round(oos_max_dd_usd, 2),
        "oos_final_balance": round(oos_balance, 2),
        "_leakage_guard": {
            "indicators_in_segment": True,
            "no_look_ahead": True,
            "is_oos_isolated": True,
        },
        "_phase2": {
            "risk_model": risk_meta.get("model"),
            "atr_k": risk_meta.get("atr_k"),
            "atr_m": risk_meta.get("atr_m"),
            "regime_filter_enabled": regime_filter_enabled,
            "asym_slip_enabled": asym_slip_enabled,
            "session_spread_enabled": session_spread_enabled,
            "is_regime_blocked": train_run.get("regime_blocked", 0),
            "oos_regime_blocked": oos_run.get("regime_blocked", 0),
            "is_atr_used": train_run.get("atr_used", 0),
            "oos_atr_used": oos_run.get("atr_used", 0),
            "is_trailing_used": train_run.get("trailing_used", 0),
            "oos_trailing_used": oos_run.get("trailing_used", 0),
        },
        "_phase3": {
            "mtf_filter_enabled": mtf_filter_enabled,
            "mtf_factor": mtf_factor,
            "mtf_period": mtf_period,
            "is_mtf_blocked": train_run.get("htf_blocked", 0),
            "oos_mtf_blocked": oos_run.get("htf_blocked", 0),
        },
        "_phase4_signal_quality": _build_signal_quality_block(
            train_run, oos_run, quality_filter_enabled, quality_threshold,
        ),
        # P2 — Asset-aware risk calibration telemetry. Surfaces what the
        # engine actually DID for this pair: whether auto-ATR was forced
        # on, which multipliers were used, whether the ruin-guard fired,
        # and at which bar. UI / validators use this to verify the
        # calibration matches the intended policy for the asset.
        "_phase5_risk_calibration": {
            "pair": pair_upper,
            "is_forex": pair_upper in FOREX_PAIRS,
            "atr_stops_enabled": atr_stops_enabled,
            "atr_k": risk_meta.get("atr_k"),
            "atr_m": risk_meta.get("atr_m"),
            "risk_model": risk_meta.get("model"),
            "ruin_floor": ruin_floor,
            "ruin_floor_usd": (
                float(initial_balance) * ruin_floor if ruin_floor else None
            ),
            "is_ruin_triggered": bool(train_run.get("ruin_triggered")),
            "oos_ruin_triggered": bool(oos_run.get("ruin_triggered")),
            "is_ruin_index": train_run.get("ruin_index"),
            "oos_ruin_index": oos_run.get("ruin_index"),
        },
        "timeframe": timeframe,
        "data_source": data_source,
        "data_points": data_points if data_points else len(train_prices),
        "total_trades": total_trades,
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round(win_rate, 1),
        "total_pnl_pips": round(total_pnl_pips, 1),
        "avg_win_pips": round(avg_win_pips, 1),
        "avg_loss_pips": round(avg_loss_pips, 1),
        "max_drawdown_pips": round(max_drawdown_pips, 1),
        "profit_factor": round(profit_factor, 2),
        "initial_balance": initial_balance,
        "final_balance": round(balance, 2),
        "net_profit": round(net_profit, 2),
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_usd": round(max_drawdown_usd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "risk_adjusted_return": risk_adjusted,
        "total_commission": round(total_commission, 2),
        "total_spread_cost": round(total_spread_cost, 2),
        "total_slippage_cost": round(total_slippage_cost, 2),
        "total_costs": round(total_commission + total_spread_cost + total_slippage_cost, 2),
        "execution_summary": {
            "enabled": exec_enabled,
            "total_spread_cost": round(total_spread_cost, 2) if exec_enabled else 0.0,
            "total_slippage_cost": round(total_slippage_cost, 2) if exec_enabled else 0.0,
            "total_commission": round(total_commission, 2) if exec_enabled else 0.0,
            "total_execution_cost": round(total_commission + total_spread_cost + total_slippage_cost, 2) if exec_enabled else 0.0,
        },
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "simulation": {
            "spread_pips": spread_pips,
            "risk_percent": risk_percent,
            "commission_per_lot": commission_per_lot,
            "initial_balance": initial_balance,
            "execution": {
                "enabled": exec_enabled,
                "spread": float(exec_cfg_resolved.get("spread") or 0.0),
                "max_slippage": float(exec_cfg_resolved.get("max_slippage") or 0.0),
                "commission_per_trade": float(exec_cfg_resolved.get("commission_per_trade") or 0.0),
                "intrabar_mode": exec_cfg_resolved.get("intrabar_mode"),
            },
        },
        "parameters": {
            "fast_sma": fast_period,
            "slow_sma": slow_period,
            "stop_loss_pips": sl_pips,
            "take_profit_pips": tp_pips,
            "source": param_source,
        },
        "indicators_used": active_indicators,
        "strategy_type": strategy_type,
        "extraction": {
            "confidence": extraction["confidence"] if extraction else None,
            "complete": extraction["complete"] if extraction else None,
            "raw": extraction["extracted"] if extraction else None,
        } if extraction else None,
        "equity_curve": equity_curve,
        "trades": trades,
        # Phase 7.5 — price series exposed so the UI Chart View can plot
        # trade markers at their bar indices. Safe/additive.
        "prices": list(prices),
        # Phase 7.5 — Backtest Intelligence Layer (foundation, additive only).
        "report": _build_report(
            trades=trades,
            equity_curve=equity_curve,
            config={
                "pair": pair,
                "timeframe": timeframe,
                "strategy_type": strategy_type,
                "fast_period": fast_period,
                "slow_period": slow_period,
                "sl_pips": sl_pips,
                "tp_pips": tp_pips,
                "risk_percent": risk_percent,
                "execution": {
                    "enabled": exec_enabled,
                    "spread": float(exec_cfg_resolved.get("spread") or 0.0),
                    "max_slippage": float(exec_cfg_resolved.get("max_slippage") or 0.0),
                    "commission_per_trade": float(exec_cfg_resolved.get("commission_per_trade") or 0.0),
                },
            },
            initial_balance=initial_balance,
            drawdown_curve=_compute_drawdown_curve(equity_curve),
        ),
    }
