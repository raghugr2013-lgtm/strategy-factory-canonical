"""Phase 2 Stage 4 P4C.2 — UKIE ranking v2.

Pure composition helper that layers Stage-4 augmentations on top of
the Phase-1.6 base similarity score:

  score = base_similarity
        × trust_multiplier(trust_tier)
        × license_multiplier(license_outcome)
        × recency_multiplier(inserted_at, now)
        × contested_penalty(contested_flag)
        × endorsement_boost(endorsements_30d)

When `UKIE_RANKING_V2_ENABLED` is off, every multiplier collapses to
1.0 → the base similarity score is preserved byte-identically. This
guarantees Stage-1..3 ranking behaviour is unchanged until an
operator flips the flag.

`strong_copyleft` / `proprietary` licence outcomes yield a multiplier
of 0.0 — structurally hiding them from ranking output (regardless of
`min_trust_tier`). Callers should still enforce the `license_outcomes`
whitelist at the caller boundary, but the ranker refuses to surface
them either way.
"""
from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_ranking_v2_enabled() -> bool:
    return _flag("UKIE_RANKING_V2_ENABLED", False)


# ── Multiplier tables (tunable via env at activation time) ───────────

_TRUST_MULTS: Dict[int, float] = {5: 1.15, 4: 1.10, 3: 1.00, 2: 0.85, 1: 0.65}
_LICENSE_MULTS: Dict[str, float] = {
    "permissive":      1.00,
    "weak_copyleft":   0.95,
    "strong_copyleft": 0.00,     # structurally hidden
    "proprietary":     0.00,     # structurally hidden
    "unknown":         0.85,
}
_RECENCY_BOOST_YOUNG_MULT: float = 1.10   # < 30d
_RECENCY_STALE_MULT:       float = 0.95   # > 365d
_YOUNG_S:  int = 30  * 86_400
_STALE_S:  int = 365 * 86_400
_CONTESTED_MULT: float = 0.80             # applied when `contested=true`
_ENDORSEMENT_STEP: float = 0.02           # per endorsement in the last 30d
_ENDORSEMENT_CAP:  float = 0.20           # +20 % maximum


# ── Data shapes ──────────────────────────────────────────────────────

@dataclass
class RankingBreakdown:
    """Per-item component contributions — surfaced in query responses
    so the operator can debug ranking decisions."""
    base_similarity:      float
    trust_multiplier:     float = 1.0
    license_multiplier:   float = 1.0
    recency_multiplier:   float = 1.0
    contested_multiplier: float = 1.0
    endorsement_boost:    float = 1.0
    final_score:          float = 0.0
    reasons:              list  = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Multiplier helpers ───────────────────────────────────────────────

def trust_multiplier(trust_tier: Optional[int]) -> float:
    if not isinstance(trust_tier, int):
        return 1.0
    return _TRUST_MULTS.get(trust_tier, 1.0)


def license_multiplier(license_outcome: Optional[str]) -> float:
    if not license_outcome:
        return _LICENSE_MULTS["unknown"]
    return _LICENSE_MULTS.get(license_outcome, _LICENSE_MULTS["unknown"])


def recency_multiplier(
    inserted_at_iso: Optional[str],
    *,
    now: Optional[datetime] = None,
) -> float:
    if not inserted_at_iso:
        return 1.0
    try:
        ts = datetime.fromisoformat(inserted_at_iso)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        return 1.0
    now = now or datetime.now(timezone.utc)
    age_s = max(0, (now - ts).total_seconds())
    if age_s < _YOUNG_S:
        return _RECENCY_BOOST_YOUNG_MULT
    if age_s > _STALE_S:
        return _RECENCY_STALE_MULT
    return 1.0


def contested_multiplier(contested_flag: Optional[bool]) -> float:
    return _CONTESTED_MULT if bool(contested_flag) else 1.0


def endorsement_multiplier(endorsements_30d: int) -> float:
    if not endorsements_30d or endorsements_30d <= 0:
        return 1.0
    return 1.0 + min(_ENDORSEMENT_CAP, endorsements_30d * _ENDORSEMENT_STEP)


# ── Public composer ─────────────────────────────────────────────────

def compose(
    *,
    base_similarity:     float,
    trust_tier:          Optional[int]      = None,
    license_outcome:     Optional[str]      = None,
    inserted_at_iso:     Optional[str]      = None,
    contested_flag:      Optional[bool]     = None,
    endorsements_30d:    int                = 0,
    now:                 Optional[datetime] = None,
) -> RankingBreakdown:
    """Layer Stage-4 augmentations over the base similarity.

    When `UKIE_RANKING_V2_ENABLED` is off, every multiplier is 1.0 and
    `final_score == base_similarity` — byte-identical to Phase-1.6.
    """
    base = max(0.0, float(base_similarity))
    if not is_ranking_v2_enabled():
        return RankingBreakdown(
            base_similarity=base,
            final_score=base,
            reasons=["ranking_v2_disabled"],
        )

    tm = trust_multiplier(trust_tier)
    lm = license_multiplier(license_outcome)
    rm = recency_multiplier(inserted_at_iso, now=now)
    cm = contested_multiplier(contested_flag)
    em = endorsement_multiplier(int(endorsements_30d or 0))

    final = base * tm * lm * rm * cm * em

    reasons = []
    if lm == 0.0:
        reasons.append(f"license_zeroed:{license_outcome}")
    if cm < 1.0:
        reasons.append("contested_penalty")
    if em > 1.0:
        reasons.append(f"endorsement_boost_{endorsements_30d}")
    if rm > 1.0:
        reasons.append("recency_young")
    elif rm < 1.0:
        reasons.append("recency_stale")

    return RankingBreakdown(
        base_similarity=base,
        trust_multiplier=tm,
        license_multiplier=lm,
        recency_multiplier=rm,
        contested_multiplier=cm,
        endorsement_boost=em,
        final_score=final,
        reasons=reasons,
    )
