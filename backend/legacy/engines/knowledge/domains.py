"""Phase 2 Stage 3.α — KnowledgeDomain registry (P2C.0).

The primary organising axis of UKIE. Everything downstream — connectors,
pipeline stages, storage collections, AI consumption policy — dispatches
by `KnowledgeDomain`.

The registry is the SINGLE SOURCE OF TRUTH for domain metadata. Callers
MUST look up domain properties via `KNOWLEDGE_DOMAIN_REGISTRY` /
`get_domain_spec()` — no hard-coding of storage-collection names, trust
floors, or retention policies elsewhere in the codebase.

Extensibility contract (operator directive, 2026-02-19):
  * Every `KnowledgeDomainSpec` field carries a sensible default.
  * Adding a seventh domain is one entry in `KNOWLEDGE_DOMAIN_REGISTRY`;
    no changes to any other module are required for the domain to be
    discoverable via `list_domains()` and via `/api/knowledge/domains`.
  * Extending the spec with a new field is additive — existing callers
    continue to work unchanged because every consumer reads through
    `get_domain_spec()`, not by field-order tuple unpacking.

Distribution-ready invariant:
  Frozen dataclass. No I/O. No framework imports. Safe to import from
  any process, any worker, any node. The registry itself is a
  module-level constant so all subsystems agree on the same six specs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Literal, Mapping, Tuple


# ── Enum ─────────────────────────────────────────────────────────────

class KnowledgeDomain(str, Enum):
    """The six canonical Knowledge Domains.

    String-valued so JSON serialisation is transparent. Compare with the
    string literal (`domain == "research"`) or with the enum member
    (`domain is KnowledgeDomain.RESEARCH`) — both work.
    """

    STRATEGY          = "strategy"
    RESEARCH          = "research"
    INDICATOR         = "indicator"
    MARKET            = "market"
    EXECUTION         = "execution"
    INTERNAL_HISTORY  = "internal_history"


# ── AI consumption policy ────────────────────────────────────────────

AIContextPolicy = Literal["verbatim", "quote", "summary", "off"]
"""How an AI reasoning task may consume an item from this domain:

- `verbatim`  — the raw text may be included in the AI prompt as-is
- `quote`     — short excerpts (< N chars) may be quoted; no full body
- `summary`   — only a normalised / parsed summary may be exposed
- `off`       — the domain is not exposed to AI (e.g. audit-only)
"""


# ── Retention policy ─────────────────────────────────────────────────

RetentionPolicy = Literal["forever", "365d", "180d", "90d", "session"]
"""Default retention policy for items in this domain.

- `forever`   — no automatic expiry (curated / provenance-critical)
- `365d`      — retained for 365 days from `fetched_at`
- `180d`      — retained for 180 days
- `90d`       — retained for 90 days
- `session`   — cleared on next full ingestion cycle

Actual TTL enforcement is a Stage 3.β / observability deliverable;
this field is the declared default that consumers may honour.
"""


# ── Domain spec ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class KnowledgeDomainSpec:
    """Extensible metadata for one Knowledge Domain.

    Every field carries a sensible default so future stages can add
    fields without breaking existing callers. The **canonical vocabulary
    of a domain** — validators, normalisers, embedders — is intentionally
    NOT in this Stage-3.α foundation; those are added by Stage 3.β on
    top of this immutable base.

    Field roles (as agreed with the operator, 2026-02-19):

    Attributes:
        domain: The `KnowledgeDomain` enum member this spec belongs to.
        display_name: Human-readable label for dashboards / API surfaces.
        description: One-sentence description of what this domain holds.
        storage_collection: Mongo collection name inside
            `strategy_knowledge_base` where items land.
        required_fields: Tuple of `RawKnowledgeItem` field names that
            MUST be present after parsing. Enforced in Stage 3.β.
        default_trust_floor: Minimum tier (1..5) accepted for AI
            consumption from this domain. Trust ladder is defined in
            `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md §3`.
        ai_context_policy: How AI may consume items — see
            `AIContextPolicy` type.
        default_retention_policy: Declared default retention for items
            in this domain — see `RetentionPolicy` type. TTL enforcement
            arrives in Stage 3.β.
        searchable: If True, items in this domain are eligible for
            similarity search + retrieval. If False, the domain is
            audit-only.
        version: Spec schema version. Bumped when the domain's
            required-field set or storage layout changes in a
            non-backward-compatible way.
    """

    domain:                     KnowledgeDomain
    display_name:               str
    description:                str
    storage_collection:         str
    required_fields:            Tuple[str, ...]
    default_trust_floor:        int
    ai_context_policy:          AIContextPolicy
    default_retention_policy:   RetentionPolicy   = "forever"
    searchable:                 bool              = True
    version:                    int               = 1

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable form (JSON-safe)."""
        return {
            "domain":                    self.domain.value,
            "display_name":              self.display_name,
            "description":               self.description,
            "storage_collection":        self.storage_collection,
            "required_fields":           list(self.required_fields),
            "default_trust_floor":       self.default_trust_floor,
            "ai_context_policy":         self.ai_context_policy,
            "default_retention_policy":  self.default_retention_policy,
            "searchable":                self.searchable,
            "version":                   self.version,
        }


# ── The registry — SINGLE SOURCE OF TRUTH ────────────────────────────

KNOWLEDGE_DOMAIN_REGISTRY: Mapping[KnowledgeDomain, KnowledgeDomainSpec] = {
    KnowledgeDomain.STRATEGY: KnowledgeDomainSpec(
        domain=KnowledgeDomain.STRATEGY,
        display_name="Strategy Knowledge",
        description=(
            "Executable and near-executable trading strategies — Pine, "
            "MQL, Python, and other code artefacts."
        ),
        storage_collection="strategies",
        required_fields=(
            "connector_name", "source_url", "source_ref",
            "content_hash", "fetched_at", "content_bytes",
        ),
        default_trust_floor=3,        # T3 — Standard (public + license present)
        ai_context_policy="quote",    # short excerpts; full body via retrieval
        default_retention_policy="forever",
        searchable=True,
        version=1,
    ),
    KnowledgeDomain.RESEARCH: KnowledgeDomainSpec(
        domain=KnowledgeDomain.RESEARCH,
        display_name="Research Knowledge",
        description=(
            "Academic and practitioner research: papers, whitepapers, "
            "book chapters, quantitative articles."
        ),
        storage_collection="research",
        required_fields=(
            "connector_name", "source_url", "source_ref",
            "content_hash", "fetched_at",
        ),
        default_trust_floor=4,        # T4 — Curated (peer-reviewed / whitelisted)
        ai_context_policy="summary",  # abstracts + section summaries into prompts
        default_retention_policy="forever",
        searchable=True,
        version=1,
    ),
    KnowledgeDomain.INDICATOR: KnowledgeDomainSpec(
        domain=KnowledgeDomain.INDICATOR,
        display_name="Indicator Knowledge",
        description=(
            "Formal indicator definitions, parametrisations, and known "
            "failure modes."
        ),
        storage_collection="indicators",
        required_fields=(
            "connector_name", "source_url", "source_ref",
            "content_hash", "fetched_at",
        ),
        default_trust_floor=3,
        ai_context_policy="verbatim", # canonical definitions may be quoted whole
        default_retention_policy="forever",
        searchable=True,
        version=1,
    ),
    KnowledgeDomain.MARKET: KnowledgeDomainSpec(
        domain=KnowledgeDomain.MARKET,
        display_name="Market Knowledge",
        description=(
            "Instrument-specific microstructure, session behaviour, "
            "regime history, correlations."
        ),
        storage_collection="market",
        required_fields=(
            "connector_name", "source_url", "source_ref",
            "content_hash", "fetched_at",
        ),
        default_trust_floor=3,
        ai_context_policy="summary",
        default_retention_policy="365d",  # market microstructure ages faster than research
        searchable=True,
        version=1,
    ),
    KnowledgeDomain.EXECUTION: KnowledgeDomainSpec(
        domain=KnowledgeDomain.EXECUTION,
        display_name="Execution Knowledge",
        description=(
            "Broker specifics, prop-firm rules, slippage models, "
            "commission tables, latency profiles, order-type semantics."
        ),
        storage_collection="execution",
        required_fields=(
            "connector_name", "source_url", "source_ref",
            "content_hash", "fetched_at",
        ),
        default_trust_floor=4,        # rule sets need high trust — used by realism sweep
        ai_context_policy="verbatim", # rules must be quoted exactly, not summarised
        default_retention_policy="180d",  # broker/prop-firm rules churn
        searchable=True,
        version=1,
    ),
    KnowledgeDomain.INTERNAL_HISTORY: KnowledgeDomainSpec(
        domain=KnowledgeDomain.INTERNAL_HISTORY,
        display_name="Internal Historical Knowledge",
        description=(
            "Everything the Factory itself has produced — past "
            "strategies, outcome events, mutation lineage, meta-learning "
            "verdicts. Read-only mirror."
        ),
        storage_collection="internal_history",
        required_fields=(
            "connector_name", "source_url", "source_ref",
            "content_hash", "fetched_at",
        ),
        default_trust_floor=5,        # produced by Factory → maximally trusted
        ai_context_policy="summary",  # summarised into prompts, not verbatim (long docs)
        default_retention_policy="forever",
        searchable=True,
        version=1,
    ),
}
"""Immutable mapping of the six canonical Knowledge Domains.

Adding a seventh domain: append a new `KnowledgeDomain` enum member
and a new entry here. Every downstream consumer picks it up
automatically via `list_domains()`.
"""


# ── Pure accessors ───────────────────────────────────────────────────

def get_domain(name: str) -> KnowledgeDomain:
    """Resolve a domain name to its enum member.

    Accepts the string value (`"research"`) or the enum name
    (`"RESEARCH"`). Raises `KeyError` on unknown domain.
    """
    if not name:
        raise KeyError("empty domain name")
    key = name.strip()
    # Try value
    for d in KnowledgeDomain:
        if d.value == key.lower():
            return d
    # Try enum name (upper-case)
    upper = key.upper()
    if upper in KnowledgeDomain.__members__:
        return KnowledgeDomain[upper]
    raise KeyError(f"unknown knowledge domain: {name!r}")


def get_domain_spec(domain: KnowledgeDomain) -> KnowledgeDomainSpec:
    """Return the spec for a domain. Raises `KeyError` if not registered."""
    spec = KNOWLEDGE_DOMAIN_REGISTRY.get(domain)
    if spec is None:                                       # pragma: no cover
        raise KeyError(f"no spec registered for domain: {domain!r}")
    return spec


def list_domains() -> Tuple[KnowledgeDomainSpec, ...]:
    """Return all registered domain specs in stable enum order."""
    return tuple(KNOWLEDGE_DOMAIN_REGISTRY[d] for d in KnowledgeDomain)


def storage_collection_for(domain: KnowledgeDomain) -> str:
    """Convenience — the Mongo sub-collection name for a domain."""
    return get_domain_spec(domain).storage_collection


def is_searchable(domain: KnowledgeDomain) -> bool:
    """Convenience — whether items in this domain go into similarity search."""
    return get_domain_spec(domain).searchable
