"""Strategy Factory v1.1.1 — AI Learning Layer (knowledge module).

Three-layer contract (see docs/AI_LEARNING_LAYER.md):

    L0 — source of truth
        strategy_library, strategy_library_archive,
        strategy_lifecycle_history, strategy_performance_history,
        mutation_events, mutation_runs
        (never mutated by this module)

    L1 — retriever
        knowledge.retriever.retrieve(pair, timeframe, style, top_k)
        knowledge.prompt_block.build_block(context)

    L2 — knowledge index (rebuilt periodically)
        collection: strategy_knowledge_index
        knowledge.indexer.rebuild(scope="incremental" | "full")

Phase 2 Stage 3.α (2026-02-19) adds the UKIE foundation:
    * `KnowledgeDomain` enum + `KnowledgeDomainSpec` registry
    * `KnowledgeConnector` Protocol with capability metadata
    * `GithubConnector` adapter wrapping the legacy collector
    * `/api/knowledge/domains` router (flag-gated: `UKIE_DOMAIN_REGISTRY_ENABLED`)

The Stage 3.α surface is additive and dormant by default. Downstream
pipeline stages (domain_router, license_gate, trust_scorer, dedup_check,
governance cutover) land in Stage 3.β.

Additive on top of the frozen v01 architecture. Recovered strategies
(carrying `__migration_source == "strategy_factory_recovery"`) are
learning-only — the retriever surfaces them; live-trading paths must
short-circuit any activation attempt on them.
"""
from .extractor import extract_features, StrategyFeatures      # noqa: F401
from .indexer import rebuild, get_index_status                 # noqa: F401
from .retriever import retrieve, KnowledgeContext              # noqa: F401
from .prompt_block import build_block, format_lookup_summary   # noqa: F401

# Phase 2 Stage 3.α — UKIE foundation
from .domains import (                                          # noqa: F401
    KnowledgeDomain,
    KnowledgeDomainSpec,
    KNOWLEDGE_DOMAIN_REGISTRY,
    get_domain,
    get_domain_spec,
    list_domains,
    storage_collection_for,
    is_searchable,
)
from .connector import (                                        # noqa: F401
    ConnectorCapabilities,
    DiscoveryQuery,
    KnowledgeConnector,
    RateLimit,
    RawKnowledgeItem,
    Reference,
)
from .registry import (                                         # noqa: F401
    connectors_for_domain,
    get_connector,
    list_connectors,
    register_connector,
)
