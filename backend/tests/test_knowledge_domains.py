"""Phase 2, Stage 3.α — KnowledgeDomain registry tests (P2C.0).

Verifies:
  * Six canonical domains present with correct enum values
  * `KnowledgeDomainSpec` shape carries every operator-mandated field
  * Registry immutability (frozen dataclass; module-level constant)
  * Look-up helpers (`get_domain`, `get_domain_spec`, `list_domains`,
    `storage_collection_for`, `is_searchable`)
  * Extensibility contract — every field has a default so future
    domains can add spec fields without breaking existing callers
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LEGACY = Path(__file__).resolve().parents[1] / "legacy"
if str(_LEGACY) not in sys.path:
    sys.path.insert(0, str(_LEGACY))

from engines.knowledge.domains import (  # noqa: E402
    KNOWLEDGE_DOMAIN_REGISTRY,
    KnowledgeDomain,
    KnowledgeDomainSpec,
    get_domain,
    get_domain_spec,
    is_searchable,
    list_domains,
    storage_collection_for,
)


# ── Enum ─────────────────────────────────────────────────────────────

def test_six_canonical_domains_present():
    values = {d.value for d in KnowledgeDomain}
    assert values == {
        "strategy", "research", "indicator",
        "market", "execution", "internal_history",
    }


def test_enum_str_valued():
    # Members compare equal to their string values (subclass of str)
    assert KnowledgeDomain.STRATEGY == "strategy"
    assert KnowledgeDomain.RESEARCH == "research"


# ── Registry ─────────────────────────────────────────────────────────

def test_registry_has_all_six_domains():
    assert len(KNOWLEDGE_DOMAIN_REGISTRY) == 6
    for d in KnowledgeDomain:
        assert d in KNOWLEDGE_DOMAIN_REGISTRY


def test_list_domains_stable_order():
    specs = list_domains()
    assert len(specs) == 6
    # Order matches enum declaration order
    assert [s.domain for s in specs] == list(KnowledgeDomain)


# ── Spec shape (operator-mandated fields) ────────────────────────────

_REQUIRED_SPEC_FIELDS = {
    "domain", "display_name", "description",
    "storage_collection", "required_fields",
    "default_trust_floor", "ai_context_policy",
    "default_retention_policy", "searchable", "version",
}


def test_spec_carries_every_operator_mandated_field():
    for spec in list_domains():
        d = spec.to_dict()
        for f in _REQUIRED_SPEC_FIELDS:
            assert f in d, f"spec for {spec.domain} missing field: {f}"


def test_spec_field_types():
    for spec in list_domains():
        assert isinstance(spec.domain, KnowledgeDomain)
        assert isinstance(spec.display_name, str) and spec.display_name
        assert isinstance(spec.description, str) and spec.description
        assert isinstance(spec.storage_collection, str) and spec.storage_collection
        assert isinstance(spec.required_fields, tuple)
        assert isinstance(spec.default_trust_floor, int)
        assert 1 <= spec.default_trust_floor <= 5
        assert spec.ai_context_policy in ("verbatim", "quote", "summary", "off")
        assert spec.default_retention_policy in ("forever", "365d", "180d", "90d", "session")
        assert isinstance(spec.searchable, bool)
        assert isinstance(spec.version, int) and spec.version >= 1


def test_spec_is_frozen():
    spec = get_domain_spec(KnowledgeDomain.STRATEGY)
    with pytest.raises(Exception):
        spec.default_trust_floor = 1  # type: ignore[misc]


def test_storage_collections_unique():
    collections = [s.storage_collection for s in list_domains()]
    assert len(collections) == len(set(collections)), \
        "storage_collection must be unique across domains"


def test_execution_domain_high_trust_floor():
    # Execution domain owns broker/prop-firm rules — realism sweep
    # depends on this being tightly gated
    spec = get_domain_spec(KnowledgeDomain.EXECUTION)
    assert spec.default_trust_floor >= 4


def test_internal_history_max_trust():
    # Factory-produced knowledge is maximally trusted
    spec = get_domain_spec(KnowledgeDomain.INTERNAL_HISTORY)
    assert spec.default_trust_floor == 5


# ── Look-up helpers ──────────────────────────────────────────────────

def test_get_domain_by_value():
    assert get_domain("strategy") is KnowledgeDomain.STRATEGY
    assert get_domain("Research") is KnowledgeDomain.RESEARCH  # case-insensitive value
    assert get_domain("execution") is KnowledgeDomain.EXECUTION


def test_get_domain_by_enum_name():
    assert get_domain("STRATEGY") is KnowledgeDomain.STRATEGY
    assert get_domain("internal_history") is KnowledgeDomain.INTERNAL_HISTORY


def test_get_domain_unknown_raises():
    with pytest.raises(KeyError):
        get_domain("sentiment")


def test_get_domain_empty_raises():
    with pytest.raises(KeyError):
        get_domain("")


def test_storage_collection_for():
    assert storage_collection_for(KnowledgeDomain.STRATEGY) == "strategies"
    assert storage_collection_for(KnowledgeDomain.RESEARCH) == "research"
    assert storage_collection_for(KnowledgeDomain.INDICATOR) == "indicators"
    assert storage_collection_for(KnowledgeDomain.MARKET) == "market"
    assert storage_collection_for(KnowledgeDomain.EXECUTION) == "execution"
    assert storage_collection_for(KnowledgeDomain.INTERNAL_HISTORY) == "internal_history"


def test_is_searchable_defaults_true():
    for d in KnowledgeDomain:
        assert is_searchable(d) is True  # Stage 3.α ships all searchable


# ── Extensibility contract ───────────────────────────────────────────

def test_spec_defaults_allow_minimal_construction():
    """Every non-required field has a default — future domains can be
    added with only the primary fields specified."""
    s = KnowledgeDomainSpec(
        domain=KnowledgeDomain.STRATEGY,   # reused enum for the test
        display_name="Test",
        description="test desc",
        storage_collection="test_coll",
        required_fields=("f1",),
        default_trust_floor=3,
        ai_context_policy="summary",
    )
    assert s.default_retention_policy == "forever"
    assert s.searchable is True
    assert s.version == 1


def test_spec_to_dict_json_safe():
    import json
    for spec in list_domains():
        # Must be JSON-serialisable (no enum members, no tuples of enums)
        d = spec.to_dict()
        raw = json.dumps(d)
        parsed = json.loads(raw)
        assert parsed["domain"] == spec.domain.value
        assert isinstance(parsed["required_fields"], list)
