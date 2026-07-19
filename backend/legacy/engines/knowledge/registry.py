"""Phase 2 Stage 3.α — Knowledge module registry.

Two registries live in this module:
  * The **domain registry** — imported from `.domains`; six canonical
    Knowledge Domains (single source of truth).
  * The **connector registry** — the set of `KnowledgeConnector`
    instances registered at import time or by explicit call.

Both are pure Python module-level constants — no I/O, no framework
imports. Safe to consult from anywhere.
"""
from __future__ import annotations

import logging
from threading import Lock
from typing import Dict, FrozenSet, List, Optional, Tuple

from .connector import KnowledgeConnector
from .domains import (
    KNOWLEDGE_DOMAIN_REGISTRY,
    KnowledgeDomain,
    KnowledgeDomainSpec,
    get_domain,
    get_domain_spec,
    list_domains,
    storage_collection_for,
    is_searchable,
)

logger = logging.getLogger(__name__)


# ── Connector registry ───────────────────────────────────────────────

_CONNECTOR_REGISTRY: Dict[str, KnowledgeConnector] = {}
_REGISTRY_LOCK = Lock()


def register_connector(instance: KnowledgeConnector) -> None:
    """Register a `KnowledgeConnector` instance under its `name`.

    Later `register_connector()` calls with the same `name` replace
    the earlier registration — supports test isolation and hot-swap
    in future development environments.

    Raises `TypeError` if the argument does not satisfy the Protocol
    (fail fast so wiring bugs surface at boot).
    """
    if not isinstance(instance, KnowledgeConnector):
        raise TypeError(
            f"register_connector: {type(instance).__name__} does not "
            f"satisfy KnowledgeConnector Protocol"
        )
    name = getattr(instance, "name", None)
    if not name or not isinstance(name, str):
        raise TypeError("connector.name must be a non-empty string")
    with _REGISTRY_LOCK:
        _CONNECTOR_REGISTRY[name] = instance
    logger.debug("[knowledge.registry] registered connector: %s", name)


def get_connector(name: str) -> Optional[KnowledgeConnector]:
    """Return the registered connector, or `None` if not present."""
    with _REGISTRY_LOCK:
        return _CONNECTOR_REGISTRY.get(name)


def list_connectors() -> Tuple[KnowledgeConnector, ...]:
    """Return all registered connectors in registration order (dict-insert)."""
    with _REGISTRY_LOCK:
        return tuple(_CONNECTOR_REGISTRY.values())


def connectors_for_domain(domain: KnowledgeDomain) -> Tuple[KnowledgeConnector, ...]:
    """Return connectors declaring support for `domain`."""
    with _REGISTRY_LOCK:
        return tuple(
            c for c in _CONNECTOR_REGISTRY.values()
            if domain in c.supported_domains
        )


def _reset_for_tests() -> None:
    """Test-only — clear the connector registry (domain registry is immutable)."""
    with _REGISTRY_LOCK:
        _CONNECTOR_REGISTRY.clear()


# ── Bootstrap default connectors ─────────────────────────────────────

def _bootstrap_default_connectors() -> None:
    """Register the connectors that ship with Stage 3.α.

    Stage 3.α: `GithubConnector` only. Stage 4 adds the remaining four
    (`ArxivConnector`, `PdfConnector`, `PropFirmConnector`,
    `TradingViewConnector`) + `InternalMongoConnector`.
    """
    try:
        from .connectors.github import GithubConnector
        register_connector(GithubConnector())
    except Exception as e:  # noqa: BLE001
        # Boot must never fail because of a connector wiring error —
        # log at DEBUG (registry consumers already handle empty state).
        logger.debug("[knowledge.registry] github connector bootstrap skipped: %s", e)


_bootstrap_default_connectors()


# ── Convenience re-exports ───────────────────────────────────────────

__all__ = [
    # domain registry re-exports
    "KNOWLEDGE_DOMAIN_REGISTRY",
    "KnowledgeDomain",
    "KnowledgeDomainSpec",
    "get_domain",
    "get_domain_spec",
    "list_domains",
    "storage_collection_for",
    "is_searchable",
    # connector registry
    "register_connector",
    "get_connector",
    "list_connectors",
    "connectors_for_domain",
    "_reset_for_tests",
]
