"""
Strategy parameter extractor.
Parses AI-generated strategy text to extract indicator parameters,
strategy type, and trading rules. Returns structured config for
the backtest engine.
"""
import re
import logging

logger = logging.getLogger(__name__)

# Strategy type keywords
_TYPE_KEYWORDS = {
    "mean_reversion": ["MEAN REVERSION", "REVERSION", "OVERSOLD", "OVERBOUGHT", "BOLLINGER", "BB BAND", "BOUNCE"],
    "breakout": ["BREAKOUT", "BREAK OUT", "BREAK ABOVE", "BREAK BELOW", "BREAKS ABOVE", "BREAKS BELOW", "CHANNEL"],
    "momentum": ["MOMENTUM", "MACD", "HISTOGRAM", "SIGNAL LINE"],
    "scalping": ["SCALP", "SCALPING", "QUICK", "FAST TRADE"],
    "trend_following": ["TREND", "CROSSOVER", "CROSS OVER", "EMA", "SMA", "MOVING AVERAGE"],
}


def extract_params(strategy_text: str) -> dict:
    """
    Extract ALL trading parameters from strategy text.
    Returns overrides for the backtest engine plus full indicator config.
    """
    text = strategy_text.upper()
    raw = {}

    # --- Core MA params ---
    fast = _extract_fast_period(text)
    if fast:
        raw["fast_ma"] = fast
    slow = _extract_slow_period(text)
    if slow:
        raw["slow_ma"] = slow
    sl = _extract_stop_loss(text)
    if sl:
        raw["stop_loss"] = sl
    tp = _extract_take_profit(text)
    if tp:
        raw["take_profit"] = tp

    # --- RSI params ---
    rsi_period = _extract_rsi_period(text)
    if rsi_period:
        raw["rsi_period"] = rsi_period
    rsi_buy = _extract_rsi_threshold(text, "buy")
    if rsi_buy is not None:
        raw["rsi_buy_threshold"] = rsi_buy
    rsi_sell = _extract_rsi_threshold(text, "sell")
    if rsi_sell is not None:
        raw["rsi_sell_threshold"] = rsi_sell

    # --- MACD params ---
    macd = _extract_macd_params(text)
    if macd:
        raw["macd"] = macd

    # --- Bollinger Bands params ---
    bb = _extract_bollinger_params(text)
    if bb:
        raw["bollinger"] = bb

    # --- Strategy type ---
    strategy_type = _detect_strategy_type(text)
    raw["strategy_type"] = strategy_type

    # --- Build param_overrides for backtest engine ---
    overrides = {}
    if fast:
        overrides["fast_period"] = fast
    if slow:
        overrides["slow_period"] = slow
    if sl:
        overrides["sl_pips"] = sl
    if tp:
        overrides["tp_pips"] = tp

    # Indicator config (separate from core overrides)
    indicators = {}
    if rsi_period:
        indicators["rsi"] = {
            "period": rsi_period,
            "buy_threshold": rsi_buy if rsi_buy is not None else 50,
            "sell_threshold": rsi_sell if rsi_sell is not None else 50,
        }
    if macd:
        indicators["macd"] = macd
    if bb:
        indicators["bollinger"] = bb

    # Validate: fast < slow
    if "fast_period" in overrides and "slow_period" in overrides:
        if overrides["fast_period"] >= overrides["slow_period"]:
            overrides["fast_period"], overrides["slow_period"] = (
                overrides["slow_period"], overrides["fast_period"]
            )
            raw["_swapped"] = True

    # Validate: TP > SL
    if "sl_pips" in overrides and "tp_pips" in overrides:
        if overrides["tp_pips"] <= overrides["sl_pips"]:
            overrides["tp_pips"] = int(overrides["sl_pips"] * 1.5)
            raw["_tp_adjusted"] = True

    core_count = sum(1 for k in ["fast_period", "slow_period", "sl_pips", "tp_pips"] if k in overrides)
    indicator_count = len(indicators)
    confidence = core_count + indicator_count
    total_possible = 4 + 3  # 4 core + RSI + MACD + BB

    logger.info(
        f"Param extraction: {core_count}/4 core, {indicator_count} indicators, "
        f"type={strategy_type} — "
        f"fast={overrides.get('fast_period')}, slow={overrides.get('slow_period')}, "
        f"SL={overrides.get('sl_pips')}, TP={overrides.get('tp_pips')}, "
        f"RSI={'yes' if 'rsi' in indicators else 'no'}, "
        f"MACD={'yes' if 'macd' in indicators else 'no'}, "
        f"BB={'yes' if 'bollinger' in indicators else 'no'}"
    )

    return {
        "overrides": overrides if overrides else None,
        "indicators": indicators if indicators else None,
        "strategy_type": strategy_type,
        "extracted": raw,
        "confidence": confidence,
        "total_possible": total_possible,
        "complete": core_count == 4,
    }


def _detect_strategy_type(text: str) -> str:
    """Detect strategy type from the strategy text.

    P0 fix — honour the explicit `TYPE:` declaration first (the
    generator always emits one like ``TYPE: trend_following``) before
    falling back to keyword scoring over free-text description.

    Before this fix, a trend-following strategy whose description
    happened to contain "scalping-grade frequency" would be scored as
    `scalping` because the keyword scan scored the whole text. The
    signal dispatcher then dispatched to the wrong family silently.
    """
    # 1) Explicit declaration wins. Accept the canonical names used by
    #    the generator + a few common aliases.
    canonical = {
        "trend_following", "trend-following",
        "mean_reversion",  "mean-reversion",
        "breakout", "momentum", "scalping",
    }
    alias_map = {
        "trend-following": "trend_following",
        "mean-reversion":  "mean_reversion",
    }
    m = re.search(r"\bTYPE\s*[:=]\s*([A-Z][A-Z_\-]+)", text, re.IGNORECASE)
    if m:
        raw = m.group(1).strip().lower().replace(" ", "_")
        if raw in canonical:
            return alias_map.get(raw, raw)

    # 2) Fallback — keyword scoring. Ignores case; matches against the
    #    already-uppercased `text` the rest of the extractor uses.
    up = text.upper() if text == text.lower() or text == text.upper() else text
    scores = {}
    for stype, keywords in _TYPE_KEYWORDS.items():
        scores[stype] = sum(1 for kw in keywords if kw in up)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "trend_following"


# ── Core MA extractors ──

def _extract_fast_period(text: str) -> int | None:
    patterns = [
        r'FAST\s*=\s*(\d+)',
        r'(?:EMA|SMA|MA)\s*(\d+)\s*/\s*\d+',
        r'FAST\s+(?:EMA|SMA|MA)\s*\(?(\d+)\)?',
        r'(?:FAST|SHORT[- ]?TERM)\s*[:\s]*(\d+)',
        r'(\d+)[- ]*PERIOD\s+(?:FAST\s+)?(?:EMA|SMA|MA)',
        r'(?:EMA|SMA|MA)\s*\(\s*(\d+)\s*\)',
        r'(?:EMA|SMA|MA)\s+(\d+)\s+CROSS',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = int(m.group(1))
            if 2 <= val <= 50:
                return val
    return None


def _extract_slow_period(text: str) -> int | None:
    patterns = [
        r'SLOW\s*=\s*(\d+)',
        r'(?:EMA|SMA|MA)\s*\d+\s*/\s*(\d+)',
        r'SLOW\s+(?:EMA|SMA|MA)\s*\(?(\d+)\)?',
        r'(?:SLOW|LONG[- ]?TERM)\s*[:\s]*(\d+)',
        r'(\d+)[- ]*PERIOD\s+(?:SLOW\s+)?(?:EMA|SMA|MA)',
        r'CROSS\w*\s+\w+\s+(?:EMA|SMA|MA)\s+(\d+)',
        r'(?:AND|ABOVE|BELOW|VS|VERSUS)\s+(?:EMA|SMA|MA)\s+(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = int(m.group(1))
            if 5 <= val <= 200:
                return val
    all_periods = re.findall(r'(\d+)[- ]*PERIOD\s+(?:EMA|SMA|MA)', text)
    if len(all_periods) >= 2:
        nums = sorted([int(x) for x in all_periods])
        if nums[-1] >= 5:
            return nums[-1]
    return None


def _extract_stop_loss(text: str) -> int | None:
    patterns = [
        r'SL\s*=?\s*(\d+)',
        r'STOP\s*LOSS\s*[:\s]*(\d+)\s*(?:PIP|P\b)',
        r'SL\s+(\d+)\s*(?:PIP|P\b)',
        r'STOP\s*LOSS\s*(?:OF\s+)?(\d+)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = int(m.group(1))
            if 5 <= val <= 200:
                return val
    return None


def _extract_take_profit(text: str) -> int | None:
    patterns = [
        r'TP\s*=?\s*(\d+)',
        r'TAKE\s*PROFIT\s*[:\s]*(\d+)\s*(?:PIP|P\b)',
        r'TP\s+(\d+)\s*(?:PIP|P\b)',
        r'TAKE\s*PROFIT\s*(?:OF\s+|AT\s+)?(\d+)',
        r'PROFIT\s+(?:AT\s+|OF\s+)?(\d+)\s*(?:PIP|P\b)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = int(m.group(1))
            if 5 <= val <= 500:
                return val
    return None


# ── RSI extractors ──

def _extract_rsi_period(text: str) -> int | None:
    patterns = [
        r'RSI\s*=?\s*(\d+)',
        r'RSI\s*\(\s*(\d+)\s*\)',
        r'RSI\s+(\d+)',
        r'(\d+)[- ]*PERIOD\s+RSI',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = int(m.group(1))
            if 2 <= val <= 50:
                return val
    return None


def _extract_rsi_threshold(text: str, direction: str) -> int | None:
    """Extract RSI threshold for buy or sell signals."""
    if direction == "buy":
        patterns = [
            r'RSI\s*\d*\s*[><]\s*(\d+)\s*.*?(?:LONG|BUY)',
            r'(?:LONG|BUY).*?RSI\s*\d*\s*[><]\s*(\d+)',
            r'RSI\s*\d*\s*>\s*(\d+)',
            r'RSI\s*\d*\s*(?:ABOVE|OVER)\s*(\d+)',
            r'RSI.*?<\s*(\d+).*?(?:OVERSOLD|BUY)',
        ]
    else:
        patterns = [
            r'RSI\s*\d*\s*[><]\s*(\d+)\s*.*?(?:SHORT|SELL)',
            r'(?:SHORT|SELL).*?RSI\s*\d*\s*[><]\s*(\d+)',
            r'RSI\s*\d*\s*<\s*(\d+)',
            r'RSI\s*\d*\s*(?:BELOW|UNDER)\s*(\d+)',
            r'RSI.*?>\s*(\d+).*?(?:OVERBOUGHT|SELL)',
        ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = int(m.group(1))
            if 10 <= val <= 90:
                return val
    return None


# ── MACD extractors ──

def _extract_macd_params(text: str) -> dict | None:
    """Extract MACD parameters if present."""
    if "MACD" not in text:
        return None
    result = {"fast": 12, "slow": 26, "signal": 9}
    m = re.search(r'MACD\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', text)
    if m:
        result = {"fast": int(m.group(1)), "slow": int(m.group(2)), "signal": int(m.group(3))}
    else:
        m2 = re.search(r'MACD\s+(\d+)\s*/\s*(\d+)\s*/\s*(\d+)', text)
        if m2:
            result = {"fast": int(m2.group(1)), "slow": int(m2.group(2)), "signal": int(m2.group(3))}
    return result


# ── Bollinger Bands extractors ──

def _extract_bollinger_params(text: str) -> dict | None:
    """Extract Bollinger Band parameters if present."""
    has_bb = any(kw in text for kw in ["BOLLINGER", "BB BAND", "BB(", "BBAND"])
    if not has_bb:
        return None
    result = {"period": 20, "std_dev": 2.0}
    m = re.search(r'(?:BOLLINGER|BB)\s*\(\s*(\d+)\s*,\s*([\d.]+)\s*\)', text)
    if m:
        result = {"period": int(m.group(1)), "std_dev": float(m.group(2))}
    else:
        m2 = re.search(r'(\d+)[- ]*PERIOD\s+(?:BOLLINGER|BB)', text)
        if m2:
            result["period"] = int(m2.group(1))
        m3 = re.search(r'([\d.]+)\s*(?:STANDARD|STD)\s*DEV', text)
        if m3:
            result["std_dev"] = float(m3.group(1))
    return result
