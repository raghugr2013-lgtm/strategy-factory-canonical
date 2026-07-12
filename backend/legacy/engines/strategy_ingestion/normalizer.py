"""Normaliser — maps parsed fields onto our internal vocabulary so the
downstream mutation pipeline receives consistent inputs."""
from __future__ import annotations

from typing import List

from .schema import IngestedStrategy, ALLOWED_TYPES


_TYPE_ALIASES = {
    "trend": "trend_following",
    "trend-following": "trend_following",
    "trend following": "trend_following",
    "trending": "trend_following",
    "mean-reversion": "mean_reversion",
    "mean reversion": "mean_reversion",
    "reversion": "mean_reversion",
    "counter-trend": "mean_reversion",
    "break-out": "breakout",
    "break out": "breakout",
    "session": "session_based",
    "session-based": "session_based",
    "london open": "session_based",
    "ny session": "session_based",
    "asian range": "session_based",
    "volatility": "volatility_based",
    "volatility-based": "volatility_based",
    "vol-based": "volatility_based",
    "atr strategy": "volatility_based",
}

# Canonical indicator → lookup phrases. First match wins.
_IND_MAP = [
    ("EMA",              ["ema", "exponential moving"]),
    ("SMA",              ["sma", "simple moving"]),
    ("MACD",             ["macd"]),
    ("RSI",              ["rsi", "relative strength"]),
    ("Bollinger Bands",  ["bollinger", "bb(", "bband"]),
    ("Donchian Channel", ["donchian"]),
    ("ATR",              ["atr", "average true range"]),
    ("VWAP",             ["vwap", "volume weighted average"]),
    ("session high/low", ["session high", "session low", "range high", "range low", "session range"]),
]


def _normalise_type(t: str) -> str:
    key = (t or "").strip().lower()
    if key in ALLOWED_TYPES:
        return key
    return _TYPE_ALIASES.get(key, "unknown")


def _normalise_indicators(indicators: List[str]) -> List[str]:
    out: List[str] = []
    for raw in indicators or []:
        low = str(raw).lower()
        picked = None
        for canon, phrases in _IND_MAP:
            if any(p in low for p in phrases):
                picked = canon
                break
        if picked and picked not in out:
            out.append(picked)
    return out


_ALLOWED_TFS = {"M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"}


def _normalise_timeframe(tf: str) -> str:
    k = (tf or "").upper().replace(" ", "")
    # Accept "1H", "60m", etc.
    mapping = {
        "1M": "M1", "5M": "M5", "15M": "M15", "30M": "M30",
        "1H": "H1", "60M": "H1", "4H": "H4", "240M": "H4",
        "1D": "D1", "DAILY": "D1", "1W": "W1", "WEEKLY": "W1",
    }
    if k in mapping:
        return mapping[k]
    if k in _ALLOWED_TFS:
        return k
    return "H1"


def _normalise_pair(p: str) -> str:
    k = (p or "EURUSD").upper().replace("/", "").replace(" ", "")
    if len(k) in (6, 7, 8) and k.isalnum():
        return k
    return "EURUSD"


def normalise(s: IngestedStrategy) -> IngestedStrategy:
    """Return a copy of `s` with canonical fields. Non-destructive."""
    d = s.model_dump()
    d["type"] = _normalise_type(d.get("type", ""))
    d["indicators"] = _normalise_indicators(d.get("indicators") or [])
    d["timeframe"] = _normalise_timeframe(d.get("timeframe", "H1"))
    d["pair"] = _normalise_pair(d.get("pair", "EURUSD"))
    # Clamp confidence, strip trailing whitespace
    d["confidence"] = max(0.0, min(1.0, float(d.get("confidence") or 0.0)))
    d["entry_logic"] = str(d.get("entry_logic", "")).strip()
    d["exit_logic"] = str(d.get("exit_logic", "")).strip()
    d["risk_model"] = str(d.get("risk_model", "")).strip().lower()
    return IngestedStrategy(**d)
