"""Phase C.1 — Strategy Intelligence Engine.

Classifies every strategy along four axes so the Master Bot Builder can
assemble balanced, low-correlation bundles:

    style             — trend_following | mean_reversion | breakout | session_based | volatility_based | momentum | unknown
    regime_suitability — dict {trending|ranging|high_volatility|low_volatility|unknown -> confidence 0..1}
    risk_profile      — {sl_pips, tp_pips, rr_ratio, max_dd_pct, risk_per_trade_pct}
    confidence        — 0..1 — how well backtest evidence supports the classification

Pure classification — never mutates the strategy document. Consumed by
`portfolio_intelligence` and `master_bot_builder`.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

# Reuse the diversity catalogue the generator already publishes.
try:
    from engines.strategy_engine import STRATEGY_TYPES, INDICATOR_KEYWORDS
except Exception:  # pragma: no cover
    STRATEGY_TYPES = ("trend_following", "mean_reversion", "breakout",
                      "session_based", "volatility_based")
    INDICATOR_KEYWORDS: Dict[str, list] = {}


_STYLE_KEYWORDS = {
    "trend_following":  ["ema", "sma", "macd", "trend"],
    "mean_reversion":   ["rsi", "bollinger", "bb(", "oversold", "overbought", "mean revers"],
    "breakout":         ["donchian", "breakout", "channel"],
    "session_based":    ["session", "vwap", "london", "new york", "asian"],
    "volatility_based": ["atr", "volatility", "expand", "contract"],
    "momentum":         ["momentum", "macd"],
}


@dataclass
class StrategyClassification:
    strategy_hash:      str
    style:              str
    regime_suitability: Dict[str, float]
    risk_profile:       Dict[str, float]
    confidence:         float
    evidence:           Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _detect_style(text: str) -> str:
    lo = (text or "").lower()
    scores: Dict[str, int] = {}
    for style, kws in _STYLE_KEYWORDS.items():
        scores[style] = sum(1 for kw in kws if kw in lo)
    if not scores or max(scores.values()) == 0:
        return "unknown"
    return max(scores.items(), key=lambda kv: (kv[1], kv[0]))[0]


# Same regime→style preference table backtest_engine uses.
_REGIME_PREFERENCE = {
    "trend_following":  ("trending", "low_volatility"),
    "mean_reversion":   ("ranging", "low_volatility"),
    "momentum":         ("trending", "high_volatility"),
    "breakout":         ("trending", "high_volatility"),
    "volatility_based": ("high_volatility", "trending"),
    "session_based":    ("ranging", "high_volatility"),
}


def _regime_suitability(style: str) -> Dict[str, float]:
    out = {"trending": 0.25, "ranging": 0.25,
           "high_volatility": 0.25, "low_volatility": 0.25, "unknown": 0.5}
    for r in _REGIME_PREFERENCE.get(style, ()):
        out[r] = 0.9
    return out


def _risk_profile(bt: Optional[Dict[str, Any]], text: str) -> Dict[str, float]:
    bt = bt or {}
    # Best-effort numeric parse from the strategy text; fall back to
    # backtest-reported values.
    import re
    lo = text.lower()
    sl = None
    m = re.search(r"sl\s*=\s*(\d+)", lo)
    if m: sl = float(m.group(1))
    tp = None
    m = re.search(r"tp\s*=\s*(\d+)", lo)
    if m: tp = float(m.group(1))
    rr = round((tp / sl), 2) if (sl and tp and sl > 0) else float(bt.get("rr_ratio") or 0.0)
    return {
        "sl_pips":            float(sl or bt.get("sl_pips") or 0.0),
        "tp_pips":            float(tp or bt.get("tp_pips") or 0.0),
        "rr_ratio":           rr,
        "max_dd_pct":         float(bt.get("max_drawdown_pct") or 0.0),
        "risk_per_trade_pct": float(bt.get("risk_per_trade_pct") or 1.0),
    }


def _confidence(bt: Optional[Dict[str, Any]]) -> float:
    """Backtest-evidence-weighted confidence. Higher trade count + higher
    profit factor + lower drawdown = higher confidence. Bounded 0..1."""
    bt = bt or {}
    trades = int(bt.get("total_trades") or 0)
    pf     = float(bt.get("profit_factor") or 0.0)
    dd     = float(bt.get("max_drawdown_pct") or 100.0)
    # Sample-size term (saturates at 200 trades)
    n_term = min(1.0, trades / 200.0)
    # Profitability term (pf 1.0 → 0, pf 2.0 → ~0.5, pf 3.0 → ~0.66)
    pf_term = max(0.0, min(1.0, (pf - 1.0) / 3.0)) if pf > 0 else 0.0
    # Drawdown term (dd 5% → 0.9, dd 30% → 0.0)
    dd_term = max(0.0, min(1.0, 1.0 - dd / 30.0))
    return round(0.3 * n_term + 0.4 * pf_term + 0.3 * dd_term, 3)


def classify_strategy(strategy: Dict[str, Any]) -> StrategyClassification:
    """Classify one strategy document (as stored in `strategies` or
    `strategy_library`). Never raises — degrades to `style='unknown'` +
    `confidence=0.0` when the row is missing key fields.
    """
    text = str(strategy.get("strategy_text") or strategy.get("text") or "")
    bt = strategy.get("backtest_result") or strategy.get("bt") or {
        "profit_factor":    strategy.get("profit_factor"),
        "max_drawdown_pct": strategy.get("max_drawdown_pct"),
        "total_trades":     strategy.get("total_trades"),
        "win_rate":         strategy.get("win_rate"),
        "rr_ratio":         strategy.get("rr_ratio"),
    }
    style = _detect_style(text) if text else "unknown"
    return StrategyClassification(
        strategy_hash=str(strategy.get("strategy_hash")
                          or strategy.get("hash") or ""),
        style=style,
        regime_suitability=_regime_suitability(style),
        risk_profile=_risk_profile(bt, text),
        confidence=_confidence(bt),
        evidence={
            "profit_factor":    bt.get("profit_factor"),
            "max_drawdown_pct": bt.get("max_drawdown_pct"),
            "total_trades":     bt.get("total_trades"),
            "win_rate":         bt.get("win_rate"),
            "text_length":      len(text),
        },
    )
