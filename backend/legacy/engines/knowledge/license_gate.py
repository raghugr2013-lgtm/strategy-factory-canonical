"""Phase 2 Stage 3.β — license gate (P2C.5).

Five-outcome classifier:

  PERMISSIVE      — MIT, Apache-2.0, BSD-*, MPL-2.0, ISC, Unlicense
  WEAK_COPYLEFT   — LGPL-*
  STRONG_COPYLEFT — GPL-*, AGPL-*
  PROPRIETARY     — explicit "proprietary" / "commercial only" markers
  UNKNOWN         — no license text detected; low confidence

Two-tier detection:
  1. SPDX-id direct match (from `item.license` or `item.extras["spdx_id"]`).
  2. Heuristic — LICENSE-file / license-header regex on
     `item.content_bytes` when SPDX is absent.

Confidence:
  * SPDX exact match → 1.0
  * Heuristic phrase match → 0.75
  * Heuristic keyword match → 0.5
  * No detection → 0.0 (outcome UNKNOWN)

Pure fn per stage — no I/O. Feature-gated by `ENABLE_LICENSE_GATE`.
When off: returns UNKNOWN with `gated=False` and does not mutate the
item's declared `license` field.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .connector import RawKnowledgeItem


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_enabled() -> bool:
    return _flag("ENABLE_LICENSE_GATE", False)


class LicenseOutcome(str, Enum):
    PERMISSIVE      = "permissive"
    WEAK_COPYLEFT   = "weak_copyleft"
    STRONG_COPYLEFT = "strong_copyleft"
    PROPRIETARY     = "proprietary"
    UNKNOWN         = "unknown"


# ── SPDX taxonomy ────────────────────────────────────────────────────

_SPDX_PERMISSIVE = {
    "mit", "apache-2.0", "apache 2.0", "apache2",
    "bsd-3-clause", "bsd-2-clause", "bsd 3-clause", "bsd 2-clause",
    "isc", "mpl-2.0", "mpl 2.0",
    "unlicense", "0bsd", "cc0-1.0", "cc0",
}
_SPDX_WEAK_COPYLEFT = {
    "lgpl-3.0", "lgpl-2.1", "lgpl-2.0", "lgpl 3.0", "lgpl 2.1",
    "lgpl-3.0-only", "lgpl-2.1-only",
}
_SPDX_STRONG_COPYLEFT = {
    "gpl-3.0", "gpl-2.0", "gpl-3.0-only", "gpl-2.0-only",
    "gpl 3.0", "gpl 2.0", "agpl-3.0", "agpl-3.0-only", "agpl 3.0",
}
_SPDX_PROPRIETARY = {
    "proprietary", "commercial", "commercial-only", "all rights reserved",
}


# ── Heuristic regexes ────────────────────────────────────────────────

_HEUR_PERMISSIVE = re.compile(
    r"\b(mit|apache\s*2(?:\.0)?|bsd\s*3-clause|bsd\s*2-clause|isc|mpl\s*2(?:\.0)?|"
    r"unlicense|cc0)\s+licen[cs]e\b",
    re.IGNORECASE,
)
_HEUR_WEAK_COPYLEFT = re.compile(
    r"\blesser\s+general\s+public\s+licen[cs]e\b|\blgpl\b",
    re.IGNORECASE,
)
_HEUR_STRONG_COPYLEFT = re.compile(
    r"\b(gnu\s+)?general\s+public\s+licen[cs]e\b|\bgpl\b|\bagpl\b",
    re.IGNORECASE,
)
_HEUR_PROPRIETARY = re.compile(
    r"\ball\s+rights\s+reserved\b|\bproprietary\b|\bcommercial\s+use\s+only\b",
    re.IGNORECASE,
)


def _classify_spdx(text: str) -> Optional[Tuple[LicenseOutcome, str]]:
    key = (text or "").strip().lower()
    if not key:
        return None
    if key in _SPDX_PERMISSIVE:
        return LicenseOutcome.PERMISSIVE, key
    if key in _SPDX_WEAK_COPYLEFT:
        return LicenseOutcome.WEAK_COPYLEFT, key
    if key in _SPDX_STRONG_COPYLEFT:
        return LicenseOutcome.STRONG_COPYLEFT, key
    if key in _SPDX_PROPRIETARY:
        return LicenseOutcome.PROPRIETARY, key
    return None


def _classify_heuristic(text: str) -> Tuple[LicenseOutcome, float, str]:
    """Return `(outcome, confidence, matched_phrase)`."""
    if not text:
        return LicenseOutcome.UNKNOWN, 0.0, ""
    # Strongest signal first — full-phrase "X License" patterns
    m = _HEUR_PERMISSIVE.search(text)
    if m:
        return LicenseOutcome.PERMISSIVE, 0.75, m.group(0)
    m = _HEUR_WEAK_COPYLEFT.search(text)
    if m:
        return LicenseOutcome.WEAK_COPYLEFT, 0.75, m.group(0)
    m = _HEUR_STRONG_COPYLEFT.search(text)
    if m:
        return LicenseOutcome.STRONG_COPYLEFT, 0.75, m.group(0)
    m = _HEUR_PROPRIETARY.search(text)
    if m:
        return LicenseOutcome.PROPRIETARY, 0.5, m.group(0)
    return LicenseOutcome.UNKNOWN, 0.0, ""


@dataclass
class LicenseVerdict:
    outcome:    LicenseOutcome
    spdx_id:    Optional[str]                    # normalised SPDX id when detected
    confidence: float                            # 0.0..1.0
    method:     str                              # "spdx" | "heuristic" | "none"
    evidence:   str                              # short quoted phrase / SPDX id
    gated:      bool                             = True

    def to_outcome(self) -> Dict[str, Any]:
        return {
            "outcome":    self.outcome.value,
            "spdx_id":    self.spdx_id,
            "confidence": round(self.confidence, 4),
            "method":     self.method,
            "evidence":   self.evidence,
            "gated":      self.gated,
        }


def classify(item: RawKnowledgeItem) -> LicenseVerdict:
    """Classify an item's license. Never raises."""
    if not is_enabled():
        return LicenseVerdict(
            outcome=LicenseOutcome.UNKNOWN,
            spdx_id=None,
            confidence=0.0,
            method="none",
            evidence="ENABLE_LICENSE_GATE is off",
            gated=False,
        )

    # 1. SPDX-id direct
    spdx_candidate = (item.license or "").strip()
    if not spdx_candidate and item.extras:
        spdx_candidate = str(item.extras.get("spdx_id") or "").strip()
    hit = _classify_spdx(spdx_candidate) if spdx_candidate else None
    if hit is not None:
        outcome, key = hit
        return LicenseVerdict(
            outcome=outcome,
            spdx_id=key,
            confidence=1.0,
            method="spdx",
            evidence=spdx_candidate,
        )

    # 2. Heuristic on content bytes
    text = ""
    if item.content_bytes:
        # Bounded read — first 32 KB is enough for a LICENSE preamble
        try:
            text = item.content_bytes[:32_768].decode("utf-8", errors="replace")
        except Exception:                                     # pragma: no cover
            text = ""
    outcome, conf, phrase = _classify_heuristic(text)
    return LicenseVerdict(
        outcome=outcome,
        spdx_id=None,
        confidence=conf,
        method="heuristic" if conf > 0.0 else "none",
        evidence=phrase[:120],
    )
