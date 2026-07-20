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


def _flag_env(name: str, default: bool = False) -> bool:
    import os
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _framework_enabled() -> bool:
    """`UKIE_CONNECTOR_FRAMEWORK_ENABLED` — Stage-4 scaffold master switch."""
    return _flag_env("UKIE_CONNECTOR_FRAMEWORK_ENABLED", False)


def _connector_flag_on(instance: KnowledgeConnector) -> bool:
    """A connector is visible iff its `flag_name` env is on.

    Legacy connectors that predate Stage 4 (no `flag_name` attribute)
    remain visible unconditionally — this preserves Stage-3.α behaviour
    exactly (`GithubConnector`, etc.). Stage-4 connectors that declare
    `flag_name` become invisible when the flag is off.

    When the Stage-4 master switch (`UKIE_CONNECTOR_FRAMEWORK_ENABLED`)
    is off, per-connector filtering is bypassed and Stage-4 connectors
    are hidden — so the registry behaves EXACTLY as Stage 3.α did.
    """
    flag_name = getattr(instance, "flag_name", None)
    if not flag_name:
        return True                                             # legacy — always on
    if not _framework_enabled():
        return False                                            # framework off → hide Stage-4 connectors
    return _flag_env(flag_name, False)


def get_connector(name: str) -> Optional[KnowledgeConnector]:
    """Return the registered connector, or `None` if not present /
    flag-hidden."""
    with _REGISTRY_LOCK:
        c = _CONNECTOR_REGISTRY.get(name)
    if c is None:
        return None
    return c if _connector_flag_on(c) else None


def list_connectors() -> Tuple[KnowledgeConnector, ...]:
    """Return every registered + flag-enabled connector in registration order."""
    with _REGISTRY_LOCK:
        vals = tuple(_CONNECTOR_REGISTRY.values())
    return tuple(c for c in vals if _connector_flag_on(c))


def connectors_for_domain(domain: KnowledgeDomain) -> Tuple[KnowledgeConnector, ...]:
    """Return flag-enabled connectors declaring support for `domain`."""
    return tuple(
        c for c in list_connectors()
        if domain in c.supported_domains
    )


def _reset_for_tests() -> None:
    """Test-only — clear the connector registry (domain registry is immutable)."""
    with _REGISTRY_LOCK:
        _CONNECTOR_REGISTRY.clear()


# ── Bootstrap default connectors ─────────────────────────────────────

def _bootstrap_default_connectors() -> None:
    """Register the connectors that ship with Stage 3.α + Stage 4.

    Stage 3.α: `GithubConnector` (unflagged; always visible).
    Stage 4:   `ArxivConnector`, `PdfConnector`, `PropFirmConnector`,
               `TradingViewConnector`, `InternalMongoConnector` —
               each flag-gated per PHASE_4_MASTER_PLAN §3.8.
    """
    try:
        from .connectors.github import GithubConnector
        register_connector(GithubConnector())
    except Exception as e:  # noqa: BLE001
        logger.debug("[knowledge.registry] github connector bootstrap skipped: %s", e)

    # Stage 4 connectors — each is FLAG-GATED. When
    # `UKIE_CONNECTOR_FRAMEWORK_ENABLED` is off (production default),
    # `list_connectors()` filters them out entirely.
    for module_name, class_name in [
        ("arxiv",           "ArxivConnector"),
        ("pdf",             "PdfConnector"),
        ("propfirm",        "PropFirmConnector"),
        ("tradingview",     "TradingViewConnector"),
        ("internal_mongo",  "InternalMongoConnector"),
    ]:
        try:
            mod = __import__(f"engines.knowledge.connectors.{module_name}",
                             fromlist=[class_name])
            cls = getattr(mod, class_name)
            register_connector(cls())
        except Exception as e:  # noqa: BLE001
            logger.debug("[knowledge.registry] %s bootstrap skipped: %s", class_name, e)


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
