"""Ingested-strategy validator + simple quality scorer."""
from __future__ import annotations

import re
from typing import Tuple

from .schema import IngestedStrategy, ALLOWED_TYPES


# Pattern indicators of banned techniques. Case-insensitive.
_BANNED_PATTERNS = (
    r"\bmartingale\b",
    r"\bcost[-\s]?averag\w*",
    r"\bgrid\b.*\b(trad|bot|ea|strategy)\b",
    r"\bpyramid\w*",
    r"\bhedg\w+",
    r"\baveraging\s+down\b",
)
_BANNED_RE = re.compile("|".join(_BANNED_PATTERNS), re.IGNORECASE)

# Canonical indicator names we recognise (matches the generator's pool).
CANONICAL_INDICATORS = {
    "ema", "sma", "macd", "rsi", "bollinger bands", "donchian channel",
    "atr", "vwap", "session high/low", "session high", "session low",
}


MIN_CONFIDENCE = 0.60
MIN_INDICATOR_COUNT = 1
MAX_INDICATOR_COUNT = 5


def _contains_banned(text: str) -> bool:
    return bool(_BANNED_RE.search(text or ""))


def _simplicity_score(s: IngestedStrategy) -> float:
    """Prefer concise, readable entry/exit. Max 1.0."""
    txt = (s.entry_logic or "") + " " + (s.exit_logic or "")
    n = len(txt)
    if n < 20:
        return 0.2
    if n < 600:
        return 1.0
    if n < 1200:
        return 0.6
    return 0.3


def _indicator_clarity(s: IngestedStrategy) -> float:
    if not s.indicators:
        return 0.0
    recognised = sum(
        1 for ind in s.indicators
        if any(canon in ind.lower() for canon in CANONICAL_INDICATORS)
    )
    total = len(s.indicators)
    return recognised / total if total else 0.0


def _logical_consistency(s: IngestedStrategy) -> float:
    """Heuristic: both entry and exit present, risk model non-empty,
    type is canonical."""
    score = 0.0
    if s.entry_logic.strip():
        score += 0.4
    if s.exit_logic.strip():
        score += 0.3
    if s.risk_model and s.risk_model.lower() != "unknown":
        score += 0.2
    if s.type in ALLOWED_TYPES and s.type != "unknown":
        score += 0.1
    return min(1.0, score)


def validate(s: IngestedStrategy) -> Tuple[bool, str, float]:
    """Return (ok, reason, quality_score).

    `quality_score` ∈ [0, 1] = mean of simplicity + indicator_clarity +
    logical_consistency, always computed (even for rejects) so the UI can
    show the distribution.
    """
    # Hard rejects coming from the parser are honoured first.
    if s.rejection_reason:
        q = (_simplicity_score(s) + _indicator_clarity(s) + _logical_consistency(s)) / 3.0
        return False, s.rejection_reason, round(q, 3)

    if s.confidence < MIN_CONFIDENCE:
        q = (_simplicity_score(s) + _indicator_clarity(s) + _logical_consistency(s)) / 3.0
        return False, f"low_confidence ({s.confidence:.2f} < {MIN_CONFIDENCE})", round(q, 3)

    # Banned patterns across every text field.
    all_text = " ".join([
        s.name or "", s.entry_logic or "", s.exit_logic or "",
        s.risk_model or "", " ".join(s.indicators or []),
    ])
    if _contains_banned(all_text):
        q = (_simplicity_score(s) + _indicator_clarity(s) + _logical_consistency(s)) / 3.0
        return False, "banned_pattern (martingale/grid/hedging/pyramiding)", round(q, 3)

    # Structural checks
    if not s.entry_logic.strip():
        return False, "missing_entry_logic", 0.0
    if not s.exit_logic.strip():
        return False, "missing_exit_logic", 0.0

    n_ind = len(s.indicators or [])
    if n_ind < MIN_INDICATOR_COUNT:
        return False, "no_indicators", 0.0
    if n_ind > MAX_INDICATOR_COUNT:
        return False, f"too_many_indicators ({n_ind} > {MAX_INDICATOR_COUNT})", 0.0

    # Indicator sanity — require at least ONE canonical match. Unknown
    # indicators drop the clarity score but don't hard-fail unless ALL
    # are foreign.
    clarity = _indicator_clarity(s)
    if clarity <= 0.0:
        return False, "no_canonical_indicators", 0.0

    if s.type not in ALLOWED_TYPES:
        return False, f"unknown_type ({s.type!r})", 0.0

    simp = _simplicity_score(s)
    cons = _logical_consistency(s)
    q = round((simp + clarity + cons) / 3.0, 3)

    # Over-complex guard: if text length is huge AND clarity < 0.5
    if simp < 0.5 and clarity < 0.5:
        return False, "overly_complex", q

    return True, "ok", q
