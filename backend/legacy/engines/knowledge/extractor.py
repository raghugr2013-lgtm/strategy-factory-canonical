"""Structural feature extractor for the knowledge index.

Given a raw strategy document from `strategy_library`,
`strategy_library_archive`, or a live `strategies` doc, return a
compact `StrategyFeatures` object with normalised fields the retriever
can rank against.

Deterministic — same input yields same output. Fast — pure Python
string / regex, no I/O.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Canonical indicator vocabulary ─────────────────────────────────
# Everything the strategy_engine, mutation_engine and validator know
# about. Anything outside this set is dropped by the extractor.
KNOWN_INDICATORS = {
    "ema", "sma", "wma", "hma",
    "rsi", "stoch", "cci", "williams_r",
    "macd", "adx", "atr", "bollinger", "keltner", "donchian",
    "supertrend", "vwap", "pivot", "fibonacci",
    "ichimoku", "psar", "obv", "mfi", "cmf",
    "roc", "momentum", "aroon", "chaikin",
}

STRATEGY_TYPES = (
    "trend_following", "trend",
    "mean_reversion", "reversion",
    "breakout",
    "session_based", "session",
    "volatility_based", "volatility",
    "scalp", "scalping",
    "swing",
    "grid",
)

TYPE_ALIASES = {
    "trend": "trend_following", "trending": "trend_following",
    "reversion": "mean_reversion", "mr": "mean_reversion",
    "session": "session_based",
    "volatility": "volatility_based",
    "scalping": "scalp",
}

RISK_MODELS = {
    "fixed_stop_loss", "fixed_sl", "atr_stop", "atr_trailing",
    "trailing_stop", "chandelier", "time_stop", "pct_risk",
    "kelly", "half_kelly", "fixed_fractional", "volatility_scaled",
}

FILTERS = {
    "session_filter", "regime_filter", "news_filter", "spread_filter",
    "adx_filter", "volatility_filter", "trend_filter", "vix_filter",
    "correlation_filter",
}


_INDICATOR_RE = re.compile(r"\b(" + "|".join(sorted(KNOWN_INDICATORS, key=len, reverse=True)) + r")\b", re.IGNORECASE)
_RISK_RE      = re.compile(r"\b(" + "|".join(sorted(RISK_MODELS,       key=len, reverse=True)) + r")\b", re.IGNORECASE)
_FILTER_RE    = re.compile(r"\b(" + "|".join(sorted(FILTERS,           key=len, reverse=True)) + r")\b", re.IGNORECASE)
_TYPE_RE      = re.compile(r"\b(" + "|".join(sorted(STRATEGY_TYPES,    key=len, reverse=True)) + r")\b", re.IGNORECASE)

_ENTRY_LONG_RE  = re.compile(r"ENTRY LONG\s*:\s*(.+?)(?:\n[A-Z ]+:|\Z)", re.DOTALL | re.IGNORECASE)
_ENTRY_SHORT_RE = re.compile(r"ENTRY SHORT\s*:\s*(.+?)(?:\n[A-Z ]+:|\Z)", re.DOTALL | re.IGNORECASE)
_EXIT_RE        = re.compile(r"EXIT\s*:\s*(.+?)(?:\n[A-Z ]+:|\Z)",       re.DOTALL | re.IGNORECASE)
_RISK_LINE_RE   = re.compile(r"RISK MODEL\s*:\s*(.+?)(?:\n[A-Z ]+:|\Z)", re.DOTALL | re.IGNORECASE)
_TYPE_LINE_RE   = re.compile(r"TYPE\s*:\s*(\S+)",                        re.IGNORECASE)


def _norm_type(v: Optional[str]) -> str:
    if not v:
        return "unknown"
    v = str(v).strip().lower()
    return TYPE_ALIASES.get(v, v)


def _uniq_sorted(items: List[str]) -> List[str]:
    return sorted({(x or "").strip().lower() for x in items if x})


def _snippet(text: str, limit: int = 240) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", " ", str(text)).strip()
    return t if len(t) <= limit else t[: limit - 1] + "…"


@dataclass
class StrategyFeatures:
    strategy_hash: str
    pair: str
    timeframe: str
    strategy_type: str
    style: str
    indicators: List[str]
    filters: List[str]
    risk_model: List[str]
    entry_long: str
    entry_short: str
    exit: str
    verdict: str                 # "win" | "loss" | "neutral"
    best_pf: Optional[float]
    best_dd: Optional[float]
    stability_score: Optional[float]
    lifecycle_terminal_stage: Optional[str]
    mutation_family: Optional[str]
    source: str                  # e.g. "strategy_library" | "archive" | "live"
    is_recovered: bool           # __migration_source stamped?
    knowledge_summary_text: str
    knowledge_signature: str     # sha1 over stable feature subset — used to de-dup index rows

    # Metadata carried through for filtering / display
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_index_doc(self) -> Dict[str, Any]:
        return {
            "_id": f"{self.source}:{self.strategy_hash}",
            "strategy_hash": self.strategy_hash,
            "pair": self.pair,
            "timeframe": self.timeframe,
            "strategy_type": self.strategy_type,
            "style": self.style,
            "indicators": self.indicators,
            "filters": self.filters,
            "risk_model": self.risk_model,
            "entry_long": self.entry_long,
            "entry_short": self.entry_short,
            "exit": self.exit,
            "verdict": self.verdict,
            "best_pf": self.best_pf,
            "best_dd": self.best_dd,
            "stability_score": self.stability_score,
            "lifecycle_terminal_stage": self.lifecycle_terminal_stage,
            "mutation_family": self.mutation_family,
            "source": self.source,
            "is_recovered": self.is_recovered,
            "knowledge_summary_text": self.knowledge_summary_text,
            "knowledge_signature": self.knowledge_signature,
        }


def _verdict(best_pf: Optional[float], best_dd: Optional[float]) -> str:
    if best_pf is None:
        return "neutral"
    try:
        if best_pf >= 1.5 and (best_dd is None or best_dd <= 15.0):
            return "win"
        if best_pf < 1.05 or (best_dd is not None and best_dd >= 30.0):
            return "loss"
    except (TypeError, ValueError):
        pass
    return "neutral"


def _fp(*items: str) -> str:
    return hashlib.sha1("|".join(items).encode()).hexdigest()[:16]


def extract_features(
    doc: Dict[str, Any],
    *,
    source: str = "strategy_library",
    perf_rollup: Optional[Dict[str, Any]] = None,
    lifecycle_terminal: Optional[str] = None,
) -> StrategyFeatures:
    """Convert one Mongo doc into a `StrategyFeatures`.

    Robust to missing fields — any string field defaults to "" and any
    list field to []. The extractor never raises on malformed input.

    `perf_rollup` (optional) is the per-hash rollup from
    `strategy_performance_history` (best_pf / best_dd / stability_score).
    Pass what you have; missing values are represented as None.
    """
    strategy_hash = str(doc.get("strategy_hash") or doc.get("_id") or "")
    pair          = str(doc.get("pair") or doc.get("symbol") or doc.get("instrument") or "").upper()
    timeframe     = str(doc.get("timeframe") or doc.get("tf") or "").lower()
    raw_type      = doc.get("type") or doc.get("strategy_type")
    raw_style     = doc.get("style") or doc.get("regime") or ""

    # Prefer structured fields, fall back to text parsing.
    text_blocks: List[str] = []
    for k in ("text", "strategy_text", "raw_text", "description"):
        v = doc.get(k)
        if isinstance(v, str) and v.strip():
            text_blocks.append(v)
    text = "\n".join(text_blocks)

    entry_long  = str(doc.get("entry_long")  or "").strip()
    entry_short = str(doc.get("entry_short") or "").strip()
    exit_logic  = str(doc.get("exit_logic")  or doc.get("exit") or "").strip()
    risk_line   = str(doc.get("risk_model")  or "").strip()

    if text and not entry_long:
        m = _ENTRY_LONG_RE.search(text)
        if m:
            entry_long = _snippet(m.group(1))
    if text and not entry_short:
        m = _ENTRY_SHORT_RE.search(text)
        if m:
            entry_short = _snippet(m.group(1))
    if text and not exit_logic:
        m = _EXIT_RE.search(text)
        if m:
            exit_logic = _snippet(m.group(1))
    if text and not risk_line:
        m = _RISK_LINE_RE.search(text)
        if m:
            risk_line = _snippet(m.group(1))

    # Indicators: prefer structured list, else scan text.
    raw_indicators = doc.get("indicators")
    if isinstance(raw_indicators, list):
        indicators = _uniq_sorted([str(x) for x in raw_indicators])
    else:
        indicators = _uniq_sorted(_INDICATOR_RE.findall(text)) if text else []

    filters    = _uniq_sorted(_FILTER_RE.findall(text)) if text else []
    risk_toks  = _uniq_sorted(_RISK_RE.findall(text + " " + risk_line))
    # Also honour any structured risk list.
    if isinstance(doc.get("risk_tags"), list):
        risk_toks = _uniq_sorted(risk_toks + [str(x) for x in doc["risk_tags"]])

    # Type
    if not raw_type and text:
        m = _TYPE_LINE_RE.search(text)
        if m:
            raw_type = m.group(1)
    if not raw_type and text:
        m = _TYPE_RE.search(text)
        if m:
            raw_type = m.group(1)
    strategy_type = _norm_type(raw_type or "unknown")

    # Style (fallback: derive from type)
    style = str(raw_style or "").lower().strip() or strategy_type

    # Perf rollup
    best_pf = None
    best_dd = None
    stability_score = None
    if perf_rollup:
        best_pf = perf_rollup.get("best_pf") or perf_rollup.get("pf")
        best_dd = perf_rollup.get("best_dd") or perf_rollup.get("dd_pct")
        stability_score = perf_rollup.get("stability_score")
    else:
        best_pf = doc.get("best_pf") or doc.get("score") or doc.get("pf")
        best_dd = doc.get("best_dd") or doc.get("dd_pct")
        stability_score = doc.get("stability_score")

    verdict = _verdict(
        float(best_pf) if isinstance(best_pf, (int, float)) else None,
        float(best_dd) if isinstance(best_dd, (int, float)) else None,
    )

    mutation_family = str(doc.get("mutation_family") or doc.get("family") or "").strip() or None
    is_recovered = bool(doc.get("__migration_source"))

    # One-paragraph natural-language summary for prompt injection.
    parts = [
        f"{strategy_type} on {pair or '?'} {timeframe or '?'}",
        f"indicators: {', '.join(indicators) if indicators else '—'}",
    ]
    if entry_long:
        parts.append(f"entry: {entry_long}")
    if exit_logic:
        parts.append(f"exit: {exit_logic}")
    if risk_toks:
        parts.append(f"risk: {', '.join(risk_toks)}")
    if best_pf is not None:
        parts.append(f"pf={best_pf}")
    if best_dd is not None:
        parts.append(f"dd={best_dd}%")
    parts.append(f"verdict={verdict}")
    summary = " · ".join(parts)

    signature = _fp(
        strategy_hash or "-", pair or "-", timeframe or "-",
        strategy_type, ",".join(indicators), ",".join(risk_toks), verdict,
    )

    return StrategyFeatures(
        strategy_hash=strategy_hash or signature,
        pair=pair or "UNKNOWN",
        timeframe=timeframe or "unknown",
        strategy_type=strategy_type,
        style=style,
        indicators=indicators,
        filters=filters,
        risk_model=risk_toks,
        entry_long=_snippet(entry_long),
        entry_short=_snippet(entry_short),
        exit=_snippet(exit_logic),
        verdict=verdict,
        best_pf=float(best_pf) if isinstance(best_pf, (int, float)) else None,
        best_dd=float(best_dd) if isinstance(best_dd, (int, float)) else None,
        stability_score=float(stability_score) if isinstance(stability_score, (int, float)) else None,
        lifecycle_terminal_stage=lifecycle_terminal,
        mutation_family=mutation_family,
        source=source,
        is_recovered=is_recovered,
        knowledge_summary_text=_snippet(summary, 400),
        knowledge_signature=signature,
    )
