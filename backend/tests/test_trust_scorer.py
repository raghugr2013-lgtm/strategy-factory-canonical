"""Phase 2 Stage 3.β — trust scorer tests (P2C.6)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.connector import RawKnowledgeItem, now_iso  # noqa: E402
from engines.knowledge.domains import KnowledgeDomain  # noqa: E402
from engines.knowledge.license_gate import LicenseOutcome, LicenseVerdict  # noqa: E402
from engines.knowledge.trust_scorer import (  # noqa: E402
    DEFAULT_PARSER_CONFIDENCE,
    TrustScore,
    is_enabled,
    score,
)


def _item(**extras) -> RawKnowledgeItem:
    return RawKnowledgeItem(
        domain=KnowledgeDomain.STRATEGY,
        connector_name="test",
        source_url="u", source_ref="r",
        content_hash="sha256:x",
        fetched_at=now_iso(),
        extras=dict(extras) if extras else {},
    )


def _verdict(outcome: LicenseOutcome, conf: float = 1.0) -> LicenseVerdict:
    return LicenseVerdict(
        outcome=outcome, spdx_id="MIT" if outcome is LicenseOutcome.PERMISSIVE else None,
        confidence=conf, method="spdx", evidence="test",
    )


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_TRUST_SCORER", raising=False)
    assert is_enabled() is False
    t = score(_item(), seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert t.scored is False
    assert t.tier is None


def test_permissive_license_holds_seed(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(), seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert t.scored is True
    assert t.tier == 3


def test_strong_copyleft_demotes(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(), seed_tier=4, license_verdict=_verdict(LicenseOutcome.STRONG_COPYLEFT))
    assert t.tier == 3


def test_proprietary_double_demote(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(), seed_tier=3, license_verdict=_verdict(LicenseOutcome.PROPRIETARY))
    assert t.tier == 1  # 3 - 2 → 1


def test_unknown_license_demotes(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(), seed_tier=3, license_verdict=_verdict(LicenseOutcome.UNKNOWN, conf=0.0))
    assert t.tier <= 2


def test_parser_confidence_high_boost(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(parser_confidence=0.98),
              seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert t.tier == 4


def test_parser_confidence_low_demote(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(parser_confidence=0.3),
              seed_tier=4, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert t.tier == 3


def test_parser_confidence_default_when_absent(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(), seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert t.parser_confidence == DEFAULT_PARSER_CONFIDENCE


def test_curated_flag_boosts(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(curated=True),
              seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert t.tier == 4


def test_high_stars_boost(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(stars=2000),
              seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert t.tier == 4


def test_high_citations_boost(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(citations=200),
              seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert t.tier == 4


def test_dedup_same_domain_forces_quarantine(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(),
              seed_tier=5, license_verdict=_verdict(LicenseOutcome.PERMISSIVE),
              dedup_status="duplicate_same_domain")
    assert t.tier == 1


def test_dedup_cross_domain_allowed(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(),
              seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE),
              dedup_status="duplicate_cross_domain")
    # Cross-domain dedup is allowed by design — no demotion
    assert t.tier == 3


def test_tier_bounded(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    # Extreme seed 5 + boost + high conf → clamped to 5
    t = score(_item(curated=True, parser_confidence=0.99),
              seed_tier=5, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert 1 <= t.tier <= 5
    assert t.tier == 5
    # Extreme demote — tier 1 floor
    t2 = score(_item(parser_confidence=0.1),
               seed_tier=1, license_verdict=_verdict(LicenseOutcome.PROPRIETARY))
    assert t2.tier == 1


def test_adjustments_ordered_and_traceable(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    t = score(_item(curated=True),
              seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    stages = [a["stage"] for a in t.adjustments]
    assert stages[0] == "seed"
    assert "license" in stages
    assert "parser_confidence" in stages
    assert "source_authority" in stages


def test_deterministic(monkeypatch):
    monkeypatch.setenv("ENABLE_TRUST_SCORER", "true")
    a = score(_item(stars=1500), seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    b = score(_item(stars=1500), seed_tier=3, license_verdict=_verdict(LicenseOutcome.PERMISSIVE))
    assert a.tier == b.tier
    assert a.adjustments == b.adjustments
