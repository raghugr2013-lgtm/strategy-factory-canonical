"""Phase 2 Stage 3.β — trust scorer (P2C.6).

Five-tier ladder per `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md §3`:

  T5 — Authoritative
  T4 — Curated
  T3 — Standard
  T2 — Observational
  T1 — Quarantine

Inputs:
  * `connector.default_trust_tier` — the seed
  * `LicenseVerdict.outcome` — permissive vs copyleft vs proprietary
  * `parser_confidence` — float in [0, 1]; default 0.8 when absent
  * source-authority signal from `item.extras` (`stars`, `citations`,
    `curated=True`)
  * `dedup_status` — a prior-dedup exact-match refunds trust

Pure fn — no I/O. Deterministic. Feature-gated by
`ENABLE_TRUST_SCORER`; when off, returns tier `None` with `scored=False`
(pass-through — downstream trust filters must default to a floor).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .connector import RawKnowledgeItem
from .license_gate import LicenseOutcome, LicenseVerdict


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_enabled() -> bool:
    return _flag("ENABLE_TRUST_SCORER", False)


DEFAULT_PARSER_CONFIDENCE: float = 0.8
"""Applied when the connector / parser does not supply an explicit
`parser_confidence` in `RawKnowledgeItem.extras`. Rationale: absence of
a confidence signal means "we haven't measured it", not "it failed" —
0.8 keeps neutral items out of Quarantine while still allowing a strong
license / dedup signal to pull them up or down."""


@dataclass
class TrustScore:
    """Structured outcome of `score()`.

    Attributes:
        tier: 1..5 — the resolved trust tier (or None when flag off).
        seed_tier: The connector's declared `default_trust_tier`.
        parser_confidence: The value used (explicit or default).
        adjustments: Ordered list of `+N`/`-N` deltas with reasons —
            useful for audit + operator dashboards.
        scored: False when flag is off (pass-through).
    """

    tier:                Optional[int]
    seed_tier:           int
    parser_confidence:   float
    adjustments:         List[Dict[str, Any]]     = field(default_factory=list)
    scored:              bool                     = True

    def to_outcome(self) -> Dict[str, Any]:
        return {
            "tier":              self.tier,
            "seed_tier":         self.seed_tier,
            "parser_confidence": round(self.parser_confidence, 4),
            "adjustments":       list(self.adjustments),
            "scored":            self.scored,
        }


def _clamp(tier: int, low: int = 1, high: int = 5) -> int:
    return max(low, min(high, tier))


def _parser_confidence(item: RawKnowledgeItem) -> float:
    """Return the parser confidence to use (bounded to [0, 1])."""
    if item.extras:
        raw = item.extras.get("parser_confidence")
        if raw is not None:
            try:
                v = float(raw)
                if 0.0 <= v <= 1.0:
                    return v
            except (TypeError, ValueError):
                pass
    return DEFAULT_PARSER_CONFIDENCE


def score(
    item:               RawKnowledgeItem,
    *,
    seed_tier:          int,
    license_verdict:    LicenseVerdict,
    dedup_status:       str                       = "unique",
) -> TrustScore:
    """Score an item into T1..T5.

    Args:
        item: The `RawKnowledgeItem` being scored.
        seed_tier: The connector's `default_trust_tier` (1..5).
        license_verdict: The output of `license_gate.classify()`.
        dedup_status: `"unique"` | `"duplicate_same_domain"` |
            `"duplicate_cross_domain"` — from `dedup_check.check()`.

    Returns:
        `TrustScore` — bounded to 1..5.
    """
    if not is_enabled():
        return TrustScore(
            tier=None,
            seed_tier=seed_tier,
            parser_confidence=_parser_confidence(item),
            adjustments=[],
            scored=False,
        )

    seed = _clamp(int(seed_tier))
    conf = _parser_confidence(item)
    adjustments: List[Dict[str, Any]] = [
        {"stage": "seed", "delta": 0, "value": seed, "reason": "connector.default_trust_tier"},
    ]
    tier = seed

    # 1. License adjustment
    if license_verdict.outcome == LicenseOutcome.PERMISSIVE:
        delta = 0
    elif license_verdict.outcome == LicenseOutcome.WEAK_COPYLEFT:
        delta = 0                       # LGPL is fine for reference
    elif license_verdict.outcome == LicenseOutcome.STRONG_COPYLEFT:
        delta = -1                      # Not deployable — demote
    elif license_verdict.outcome == LicenseOutcome.PROPRIETARY:
        delta = -2                      # Quarantine-worthy signal
    else:  # UNKNOWN
        delta = -1                      # No license → quarantine-adjacent
    tier = _clamp(tier + delta)
    adjustments.append({
        "stage": "license",
        "delta": delta,
        "value": tier,
        "reason": license_verdict.outcome.value,
    })

    # 2. Parser confidence adjustment
    if conf < 0.5:
        delta = -1
    elif conf >= 0.95:
        delta = +1
    else:
        delta = 0
    tier = _clamp(tier + delta)
    adjustments.append({
        "stage": "parser_confidence",
        "delta": delta,
        "value": tier,
        "reason": f"parser_confidence={conf:.2f}",
    })

    # 3. Source-authority boost from extras
    if item.extras:
        stars = 0
        citations = 0
        try:
            stars = int(item.extras.get("stars") or 0)
        except (TypeError, ValueError):
            pass
        try:
            citations = int(item.extras.get("citations") or 0)
        except (TypeError, ValueError):
            pass
        curated = bool(item.extras.get("curated"))
        boost = 0
        reason = ""
        if curated:
            boost = +1
            reason = "curated=true"
        elif stars >= 1000 or citations >= 50:
            boost = +1
            reason = f"stars={stars},citations={citations}"
        if boost:
            tier = _clamp(tier + boost)
            adjustments.append({
                "stage": "source_authority",
                "delta": boost,
                "value": tier,
                "reason": reason,
            })

    # 4. Dedup outcome
    if dedup_status == "duplicate_same_domain":
        # Exact hash collision in the same domain — quarantine
        tier = _clamp(1)
        adjustments.append({
            "stage": "dedup",
            "delta": tier - seed_tier,
            "value": tier,
            "reason": "duplicate_same_domain",
        })
    # `duplicate_cross_domain` is allowed by design and does not adjust.

    return TrustScore(
        tier=tier,
        seed_tier=seed,
        parser_confidence=conf,
        adjustments=adjustments,
        scored=True,
    )
