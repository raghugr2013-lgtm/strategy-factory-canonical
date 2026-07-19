"""Phase 2 Stage 3.β — domain router tests (P2C.4)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.connector import RawKnowledgeItem, now_iso  # noqa: E402
from engines.knowledge.domain_router import RoutingDecision, is_enabled, route  # noqa: E402
from engines.knowledge.domains import KnowledgeDomain  # noqa: E402


def _item(domain: KnowledgeDomain) -> RawKnowledgeItem:
    return RawKnowledgeItem(
        domain=domain,
        connector_name="test",
        source_url="https://example.com/x",
        source_ref="ref",
        content_hash="sha256:x",
        fetched_at=now_iso(),
    )


def test_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("ENABLE_DOMAIN_ROUTING", raising=False)
    assert is_enabled() is False


def test_flag_on(monkeypatch):
    monkeypatch.setenv("ENABLE_DOMAIN_ROUTING", "true")
    assert is_enabled() is True


def test_route_returns_decision_with_flag_on(monkeypatch):
    monkeypatch.setenv("ENABLE_DOMAIN_ROUTING", "true")
    d = route(_item(KnowledgeDomain.RESEARCH))
    assert isinstance(d, RoutingDecision)
    assert d.domain is KnowledgeDomain.RESEARCH
    assert d.storage_collection == "research"
    assert d.routed is True
    assert d.reason == "ok"


def test_route_returns_pass_through_when_flag_off(monkeypatch):
    monkeypatch.delenv("ENABLE_DOMAIN_ROUTING", raising=False)
    d = route(_item(KnowledgeDomain.EXECUTION))
    assert d.routed is False
    assert d.reason == "flag_off_pass_through"
    # Storage collection still resolved (deterministic)
    assert d.storage_collection == "execution"


def test_route_every_domain(monkeypatch):
    monkeypatch.setenv("ENABLE_DOMAIN_ROUTING", "true")
    expected = {
        KnowledgeDomain.STRATEGY:         "strategies",
        KnowledgeDomain.RESEARCH:         "research",
        KnowledgeDomain.INDICATOR:        "indicators",
        KnowledgeDomain.MARKET:           "market",
        KnowledgeDomain.EXECUTION:        "execution",
        KnowledgeDomain.INTERNAL_HISTORY: "internal_history",
    }
    for d, coll in expected.items():
        r = route(_item(d))
        assert r.domain is d
        assert r.storage_collection == coll


def test_outcome_shape(monkeypatch):
    monkeypatch.setenv("ENABLE_DOMAIN_ROUTING", "true")
    d = route(_item(KnowledgeDomain.STRATEGY))
    o = d.to_outcome()
    assert o == {
        "domain": "strategy",
        "storage_collection": "strategies",
        "routed": True,
        "reason": "ok",
    }
