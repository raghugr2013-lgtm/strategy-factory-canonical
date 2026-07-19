"""Phase 2 Stage 3.β — domain router (P2C.4).

Pure dispatch. Given a `RawKnowledgeItem`, resolves its target
`KnowledgeDomain` via the registry and returns a `RoutingDecision`
capturing the resolved spec + storage collection.

The router NEVER hard-codes an enum value at a decision site — every
lookup goes through `get_domain_spec()` so a new domain lights up
without touching this file.

Feature-gated by `ENABLE_DOMAIN_ROUTING`. When off: the item is
returned unchanged with `routed=False` — pipeline continues on the
Stage-1 pass-through path.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .connector import RawKnowledgeItem
from .domains import (
    KnowledgeDomain,
    KnowledgeDomainSpec,
    get_domain_spec,
    storage_collection_for,
)

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_enabled() -> bool:
    return _flag("ENABLE_DOMAIN_ROUTING", False)


@dataclass
class RoutingDecision:
    """The output of `route()`.

    Attributes:
        item: The item that was routed. Untouched by this stage.
        domain: The resolved `KnowledgeDomain`.
        spec: The frozen spec for that domain.
        storage_collection: Mongo collection name where the item
            should be written on successful pipeline exit.
        routed: True when the routing was performed (flag ON);
            False when routing was skipped (flag OFF — pass-through).
        reason: Free-form diagnostic.
    """

    item:               RawKnowledgeItem
    domain:             KnowledgeDomain
    spec:               KnowledgeDomainSpec
    storage_collection: str
    routed:             bool                       = True
    reason:             str                        = ""

    def to_outcome(self) -> Dict[str, Any]:
        """Serialisable outcome record — safe for logging + Mongo."""
        return {
            "domain":             self.domain.value,
            "storage_collection": self.storage_collection,
            "routed":             self.routed,
            "reason":             self.reason,
        }


def route(item: RawKnowledgeItem) -> RoutingDecision:
    """Route an item to its domain lane.

    Never raises to the caller. If the flag is off, returns a
    pass-through decision that carries the item's declared domain
    unchanged. If the flag is on but the domain is unknown (should
    not happen — RawKnowledgeItem.domain is typed), falls back to
    STRATEGY with a diagnostic reason.
    """
    domain = item.domain
    try:
        spec = get_domain_spec(domain)
    except KeyError:
        # Should be unreachable — RawKnowledgeItem.domain is enum-typed.
        # Defensive fallback so the pipeline never crashes on bad input.
        logger.warning("[domain_router] unknown domain %r — falling back to STRATEGY", domain)
        domain = KnowledgeDomain.STRATEGY
        spec = get_domain_spec(domain)
    return RoutingDecision(
        item=item,
        domain=domain,
        spec=spec,
        storage_collection=spec.storage_collection,
        routed=is_enabled(),
        reason="ok" if is_enabled() else "flag_off_pass_through",
    )
