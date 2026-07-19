"""Phase 2, Stage 3.α — KnowledgeConnector Protocol tests (P2C.1).

Verifies:
  * Protocol satisfaction (`GithubConnector` and hand-rolled fakes)
  * Capability metadata surface — every operator-mandated capability
    flag is declared and defaults to False
  * Supporting dataclasses (`Reference`, `DiscoveryQuery`, `RateLimit`)
  * `RawKnowledgeItem` carries the `domain` field + hard-rail guardrails
  * Registry: register / lookup / list / per-domain filter
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import AsyncIterator, FrozenSet

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.connector import (  # noqa: E402
    ConnectorCapabilities,
    DiscoveryQuery,
    KnowledgeConnector,
    RateLimit,
    RawKnowledgeItem,
    Reference,
    now_iso,
)
from engines.knowledge.connectors.github import GithubConnector  # noqa: E402
from engines.knowledge.domains import KnowledgeDomain  # noqa: E402
from engines.knowledge.registry import (  # noqa: E402
    _reset_for_tests,
    connectors_for_domain,
    get_connector,
    list_connectors,
    register_connector,
)


# ── Capability metadata surface ──────────────────────────────────────

_MANDATED_CAPABILITY_FLAGS = {
    "supports_discovery",
    "supports_incremental_sync",
    "supports_versioning",
    "supports_rate_limits",
    "supports_metadata_only",
}


def test_capabilities_default_all_false():
    c = ConnectorCapabilities()
    d = c.to_dict()
    for f in _MANDATED_CAPABILITY_FLAGS:
        assert f in d, f"missing capability flag: {f}"
        assert d[f] is False, f"{f} default must be False (opt-in)"


def test_capabilities_frozen():
    c = ConnectorCapabilities(supports_discovery=True)
    with pytest.raises(Exception):
        c.supports_discovery = False  # type: ignore[misc]


def test_capabilities_to_dict_json_safe():
    import json
    c = ConnectorCapabilities(supports_discovery=True, supports_versioning=True)
    assert json.loads(json.dumps(c.to_dict()))["supports_discovery"] is True


# ── Supporting dataclasses ───────────────────────────────────────────

def test_rate_limit_shape():
    r = RateLimit(requests_per_minute=30, burst=5, cooloff_seconds=60.0)
    d = r.to_dict()
    assert d == {"requests_per_minute": 30, "burst": 5, "cooloff_seconds": 60.0}


def test_rate_limit_defaults_are_conservative():
    r = RateLimit()
    assert r.requests_per_minute is None   # no explicit cap
    assert r.burst is None
    assert r.cooloff_seconds > 0


def test_reference_carries_target_domain():
    ref = Reference(
        connector_name="github",
        source_url="https://github.com/foo/bar/blob/abc/x.py",
        source_ref="abc",
        target_domain=KnowledgeDomain.STRATEGY,
    )
    assert ref.target_domain is KnowledgeDomain.STRATEGY
    assert ref.source_ref == "abc"


def test_discovery_query_domain_scoped():
    q = DiscoveryQuery(domain=KnowledgeDomain.RESEARCH, query="mean reversion")
    assert q.domain is KnowledgeDomain.RESEARCH
    assert q.limit == 25  # sane default


# ── RawKnowledgeItem ─────────────────────────────────────────────────

def test_raw_item_carries_domain_field():
    item = RawKnowledgeItem(
        domain=KnowledgeDomain.STRATEGY,
        connector_name="test",
        source_url="https://example.com",
        source_ref="ref-1",
        content_hash="sha256:abc",
        fetched_at=now_iso(),
    )
    assert item.domain is KnowledgeDomain.STRATEGY
    assert item.learning_only is True                 # HARD RAIL
    assert item.eligible_for_deploy is False          # HARD RAIL


def test_raw_item_to_dict_omits_bytes():
    item = RawKnowledgeItem(
        domain=KnowledgeDomain.STRATEGY,
        connector_name="test",
        source_url="https://example.com",
        source_ref="r",
        content_hash="sha256:abc",
        fetched_at=now_iso(),
        content_bytes=b"secret bytes",
    )
    d = item.to_dict()
    assert "content_bytes" not in d
    assert d["content_hash"] == "sha256:abc"
    assert d["learning_only"] is True


def test_raw_item_defaults_json_safe():
    import json
    item = RawKnowledgeItem(
        domain=KnowledgeDomain.RESEARCH,
        connector_name="test",
        source_url="u",
        source_ref="r",
        content_hash="sha256:x",
        fetched_at=now_iso(),
    )
    raw = json.dumps(item.to_dict())
    parsed = json.loads(raw)
    assert parsed["domain"] == "research"


# ── GithubConnector — Protocol satisfaction + declaration ────────────

def test_github_connector_satisfies_protocol():
    c = GithubConnector()
    assert isinstance(c, KnowledgeConnector)


def test_github_connector_declares_strategy_domain_only():
    c = GithubConnector()
    assert c.supported_domains == frozenset({KnowledgeDomain.STRATEGY})
    assert c.name == "github"
    assert c.source_type == "code"
    assert 1 <= c.default_trust_tier <= 5


def test_github_connector_capabilities_honest():
    c = GithubConnector()
    caps = c.capabilities
    # Stage 3.α honest declaration:
    assert caps.supports_discovery is True         # collector already crawls
    assert caps.supports_versioning is True        # commit SHA available in URL
    assert caps.supports_rate_limits is True       # GITHUB_TOKEN respected
    assert caps.supports_incremental_sync is False # Stage 4
    assert caps.supports_metadata_only is False    # Stage 4


def test_github_connector_rate_limit_present():
    r = GithubConnector().rate_limit()
    assert r.requests_per_minute is not None and r.requests_per_minute > 0
    assert r.cooloff_seconds > 0


def test_github_connector_extract_ref():
    c = GithubConnector()
    assert c._extract_ref(
        "https://github.com/foo/bar/blob/abc1234/x.py"
    ) == "abc1234"
    # Missing /blob/ → falls back to URL
    assert c._extract_ref("https://example.com/foo") == "https://example.com/foo"


@pytest.mark.asyncio
async def test_github_connector_fetch_from_ref_extras():
    c = GithubConnector()
    ref = Reference(
        connector_name="github",
        source_url="https://github.com/foo/bar/blob/abc/x.py",
        source_ref="abc",
        target_domain=KnowledgeDomain.STRATEGY,
        extras={"raw_code": "//@version=5\nstrategy('t')", "ext": ".pine"},
    )
    item = await c.fetch(ref)
    assert item.domain is KnowledgeDomain.STRATEGY
    assert item.connector_name == "github"
    assert item.content_bytes is not None
    assert item.content_hash.startswith("sha256:")
    assert item.content_mime == "text/x-pine"
    assert item.learning_only is True
    assert item.eligible_for_deploy is False


@pytest.mark.asyncio
async def test_github_connector_discover_domain_mismatch_yields_nothing():
    c = GithubConnector()
    q = DiscoveryQuery(domain=KnowledgeDomain.RESEARCH)   # unsupported
    seen = []
    async for r in c.discover(q):
        seen.append(r)
    assert seen == []


# ── Registry ─────────────────────────────────────────────────────────

class _FakeArxivConnector:
    """Minimal fake to test Protocol satisfaction across multi-domain."""
    name: str = "arxiv"
    source_type: str = "paper"
    supported_domains: FrozenSet[KnowledgeDomain] = frozenset({KnowledgeDomain.RESEARCH})
    default_trust_tier: int = 5
    supported_licenses: FrozenSet[str] = frozenset({"*"})
    capabilities: ConnectorCapabilities = ConnectorCapabilities(
        supports_discovery=True,
        supports_incremental_sync=True,
        supports_versioning=True,
        supports_rate_limits=True,
        supports_metadata_only=True,
    )

    async def discover(self, query):    # pragma: no cover — fake for test
        if False:
            yield None
    async def fetch(self, ref):         # pragma: no cover — fake for test
        raise NotImplementedError
    def rate_limit(self) -> RateLimit:
        return RateLimit(requests_per_minute=10)


def test_registry_registers_default_github_at_import():
    # `engines.knowledge.registry._bootstrap_default_connectors` should
    # already have run — github is registered.
    c = get_connector("github")
    assert c is not None
    assert isinstance(c, KnowledgeConnector)


def test_registry_register_reset_flow():
    _reset_for_tests()
    assert list_connectors() == ()
    fake = _FakeArxivConnector()
    register_connector(fake)
    assert get_connector("arxiv") is fake
    assert len(list_connectors()) == 1
    # Reset restores clean state (test isolation)
    _reset_for_tests()
    assert list_connectors() == ()
    # Restore github so the router tests aren't affected
    from engines.knowledge.registry import _bootstrap_default_connectors
    _bootstrap_default_connectors()


def test_registry_rejects_non_protocol():
    class _NotAConnector:
        name = "bad"
    with pytest.raises(TypeError):
        register_connector(_NotAConnector())  # type: ignore[arg-type]


def test_registry_rejects_empty_name():
    class _EmptyName:
        name = ""
        source_type = "x"
        supported_domains = frozenset({KnowledgeDomain.STRATEGY})
        default_trust_tier = 1
        supported_licenses = frozenset({"*"})
        capabilities = ConnectorCapabilities()
        async def discover(self, q):    # pragma: no cover
            if False:
                yield None
        async def fetch(self, r):       # pragma: no cover
            raise NotImplementedError
        def rate_limit(self):
            return RateLimit()
    with pytest.raises(TypeError):
        register_connector(_EmptyName())


def test_registry_connectors_for_domain():
    _reset_for_tests()
    from engines.knowledge.registry import _bootstrap_default_connectors
    _bootstrap_default_connectors()
    register_connector(_FakeArxivConnector())
    strategy_cs = connectors_for_domain(KnowledgeDomain.STRATEGY)
    research_cs = connectors_for_domain(KnowledgeDomain.RESEARCH)
    assert any(c.name == "github" for c in strategy_cs)
    assert any(c.name == "arxiv" for c in research_cs)
    # arxiv NOT in strategy
    assert not any(c.name == "arxiv" for c in strategy_cs)
    _reset_for_tests()
    _bootstrap_default_connectors()
