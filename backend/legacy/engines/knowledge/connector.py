"""Phase 2 Stage 3.α — KnowledgeConnector Protocol (P2C.1).

Every knowledge source implements this Protocol. Connectors are HOW
knowledge is fetched; the `KnowledgeDomain` is WHAT the knowledge is
about. One connector may supply multiple domains (e.g. a book PDF →
`strategy` chapters + `research` appendices + `execution` broker notes).

Extensibility contract (operator directive, 2026-02-19):
  * Capability metadata declared upfront so future connectors plug
    in without interface changes.
  * A connector declares which capabilities it supports via
    `capabilities`. Callers MUST NOT assume a feature works — check the
    flag first. Implementation ships when the connector opts in.

Distribution-ready invariant:
  Protocol only — no I/O. Concrete connectors (GitHub, arXiv, PDF,
  PropFirm, TradingView, InternalMongo) live under
  `connectors/<name>.py` and are registered with the module registry
  at import time. Distributed workers instantiate the same Protocol
  regardless of node.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any, AsyncIterator, Dict, FrozenSet, List, Literal, Optional,
    Protocol, Set, Tuple, runtime_checkable,
)

from .domains import KnowledgeDomain


# ── Capabilities ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class ConnectorCapabilities:
    """Declarative metadata about what a connector can do.

    Every field defaults to `False` — a connector opts in to a
    capability by setting the corresponding flag. Stage 3.α ships the
    declaration surface only; the mechanisms are implemented per
    connector in Stage 3.β / Stage 4.

    Attributes:
        supports_discovery: Connector implements `discover()` yielding
            `Reference` objects without fetching content. If False,
            callers must feed references from a curated seed list.
        supports_incremental_sync: Connector can be re-invoked with a
            `since` cursor to fetch only new items. If False, every
            sweep is full.
        supports_versioning: Connector's `Reference.source_ref` is an
            immutable pointer (commit SHA / DOI / permalink) that lets
            us prove what we ingested. If False, only the URL is stable.
        supports_rate_limits: Connector honours `RateLimit` returned by
            `rate_limit()`; the scheduler will pace calls accordingly.
            If False, the scheduler applies a conservative default.
        supports_metadata_only: Connector can return a `RawKnowledgeItem`
            with `content_bytes` omitted (metadata + hash only), useful
            for coverage audits without paying the fetch cost.
    """

    supports_discovery:            bool = False
    supports_incremental_sync:     bool = False
    supports_versioning:           bool = False
    supports_rate_limits:          bool = False
    supports_metadata_only:        bool = False

    def to_dict(self) -> Dict[str, bool]:
        return {
            "supports_discovery":         self.supports_discovery,
            "supports_incremental_sync":  self.supports_incremental_sync,
            "supports_versioning":        self.supports_versioning,
            "supports_rate_limits":       self.supports_rate_limits,
            "supports_metadata_only":     self.supports_metadata_only,
        }


# ── Supporting shapes ────────────────────────────────────────────────

@dataclass(frozen=True)
class RateLimit:
    """Per-source rate declaration. The scheduler honours these
    values when `capabilities.supports_rate_limits=True`.

    Fields:
        requests_per_minute: Sustained cap. `None` = no explicit cap.
        burst: Optional burst budget (requests allowed above the
            sustained rate briefly). `None` = no burst allowance.
        cooloff_seconds: Suggested cool-off after a 429 / 403.
    """

    requests_per_minute:  Optional[int] = None
    burst:                Optional[int] = None
    cooloff_seconds:      float         = 60.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requests_per_minute": self.requests_per_minute,
            "burst":               self.burst,
            "cooloff_seconds":     self.cooloff_seconds,
        }


@dataclass(frozen=True)
class DiscoveryQuery:
    """Argument to `KnowledgeConnector.discover()`.

    Domain-scoped. A connector may support multiple domains — the
    query narrows the search to the caller's target.

    Fields:
        domain: The target Knowledge Domain for this discovery pass.
        query:  Free-form search string (connector-specific semantics).
        limit:  Soft cap on the number of references to yield.
        since:  Optional cursor for incremental sync (connector-specific
            format — ISO timestamp / commit-SHA / paging token).
        extras: Connector-specific extension bag (never assumed by the
            generic pipeline).
    """

    domain:  KnowledgeDomain
    query:   str                          = ""
    limit:   int                          = 25
    since:   Optional[str]                = None
    extras:  Optional[Dict[str, Any]]     = None


@dataclass(frozen=True)
class Reference:
    """A pointer to a fetchable resource — the output of `discover()`.

    Fields:
        connector_name: Which connector produced this reference.
        source_url:     Canonical URL of the resource.
        source_ref:     Immutable version pointer (commit SHA / DOI /
            permalink). May equal `source_url` when the connector
            doesn't support versioning.
        target_domain:  Domain the caller intends to route this into.
            The connector may override in `fetch()` if the content
            resolves to a different / additional domain.
        title:          Optional human label.
        extras:         Connector-specific bag.
    """

    connector_name:  str
    source_url:      str
    source_ref:      str
    target_domain:   KnowledgeDomain
    title:           Optional[str]         = None
    extras:          Optional[Dict[str, Any]] = None


# ── RawKnowledgeItem — canonical envelope for one fetched item ───────

@dataclass
class RawKnowledgeItem:
    """The shape every connector's `fetch()` returns.

    Full canonical form is defined in
    `PHASE_2C_KNOWLEDGE_INGESTION_REVIEW.md §1.3`; Stage 3.α ships the
    provenance + guardrail fields required by the foundation. Fields
    added by later stages (`trust_tier`, `trust_reasons`, parsed
    payload fields) will be additive.

    Guardrails:
        `learning_only=True` and `eligible_for_deploy=False` are HARD
        RAILS on every UKIE item, regardless of domain. See
        `PHASE_2_IMPLEMENTATION_MASTER_PLAN.md §3 invariants 3 + 4`.
    """

    # Domain assignment — the primary organising axis
    domain:              KnowledgeDomain

    # Provenance (mandatory per Phase-1.6)
    connector_name:      str
    source_url:          str
    source_ref:          str
    content_hash:        str
    fetched_at:          str                            # UTC ISO
    author:              Optional[str]                  = None
    license:             Optional[str]                  = None      # "MIT" | "unknown" | ...
    license_confidence:  float                          = 0.0

    # Payload
    content_bytes:       Optional[bytes]                = None
    content_mime:        Optional[str]                  = None      # "text/plain" | "application/pdf" | ...

    # Hard-rail guardrails (§5)
    learning_only:       bool                           = True
    eligible_for_deploy: bool                           = False

    # Trust (populated by trust_scorer in Stage 3.β)
    trust_tier:          Optional[int]                  = None      # 1..5
    trust_reasons:       Tuple[str, ...]                = field(default_factory=tuple)

    # Connector-specific extras (never assumed by the generic pipeline)
    extras:              Optional[Dict[str, Any]]       = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable form (bytes omitted — use `content_hash` instead)."""
        return {
            "domain":              self.domain.value,
            "connector_name":      self.connector_name,
            "source_url":          self.source_url,
            "source_ref":          self.source_ref,
            "content_hash":        self.content_hash,
            "fetched_at":          self.fetched_at,
            "author":              self.author,
            "license":             self.license,
            "license_confidence":  self.license_confidence,
            "content_mime":        self.content_mime,
            "learning_only":       self.learning_only,
            "eligible_for_deploy": self.eligible_for_deploy,
            "trust_tier":          self.trust_tier,
            "trust_reasons":       list(self.trust_reasons),
            "extras":              self.extras,
        }


# ── The Protocol ─────────────────────────────────────────────────────

@runtime_checkable
class KnowledgeConnector(Protocol):
    """Every knowledge source implements this Protocol.

    A connector declares which Knowledge Domain(s) it supports; the
    ingestion pipeline dispatches each fetched item by its `domain`
    field. Adding a new connector is one file under
    `engines/knowledge/connectors/<name>.py`; adding a new domain is
    one entry in `KNOWLEDGE_DOMAIN_REGISTRY`.

    Stage 3.α ships the interface and one adapter (`GithubConnector`)
    that wraps the existing `strategy_ingestion.collector` logic. The
    remaining five connectors land in Stage 4.
    """

    name:                str
    source_type:         str                              # "code" | "paper" | "post" | "book" | "docs"
    supported_domains:   FrozenSet[KnowledgeDomain]
    default_trust_tier:  int                              # 1..5 — used by trust_scorer
    supported_licenses:  FrozenSet[str]                   # {"MIT", "Apache-2.0", ...} — {"*"} = wildcard
    capabilities:        ConnectorCapabilities

    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[Reference]:
        """Yield `Reference`s matching the query without fetching content.

        Iff `capabilities.supports_discovery=False`, callers MUST NOT
        invoke this method — feed references from a curated seed list
        instead.
        """
        ...

    async def fetch(self, ref: Reference) -> RawKnowledgeItem:
        """Fetch full content + provenance for one `Reference`.

        The returned item's `domain` field is authoritative — a single
        fetch may resolve to a domain other than the one requested by
        `ref.target_domain` (e.g. a paper turns out to be a broker
        FAQ). Callers dispatch on the returned domain.
        """
        ...

    def rate_limit(self) -> RateLimit:
        """Declared rate limits. The scheduler honours these when
        `capabilities.supports_rate_limits=True`."""
        ...


# ── Helpers usable by connectors + tests ─────────────────────────────

def now_iso() -> str:
    """UTC ISO timestamp — connectors should use this for `fetched_at`."""
    return datetime.now(timezone.utc).isoformat()


def frozen(*items: KnowledgeDomain) -> FrozenSet[KnowledgeDomain]:
    """Concise `frozenset(...)` builder for a connector's declaration."""
    return frozenset(items)
