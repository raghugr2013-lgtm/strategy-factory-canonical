"""Strategy Knowledge subsystem — Phase 1.6.

The Strategy Memory package. Historical strategies from prior pods live
here as a **read-only** corpus. Everything under this package is
structurally forbidden from feeding the live deployment pipeline:

  * All KB documents carry ``learning_only == True`` and
    ``eligible_for_deploy == False`` at the document level.
  * The :class:`.repository.KnowledgeRepository` is the ONLY entry point
    to the ``strategy_knowledge_base`` database.
  * The production :class:`.repository.StrategyRepository` defaults its
    read filter to ``{eligible_for_deploy: True}`` — historical strategies
    are invisible to it unless an explicit
    ``include_knowledge_base=True`` opt-in is passed.

Public API:

* :func:`.canonical.canonical_hash` — structural fingerprint (16 hex).
* :class:`.evaluation.StrategyEvaluation` — six independent dimensions.
* :class:`.repository.StrategyRepository` — safe production reads.
* :class:`.repository.KnowledgeRepository` — explicit KB reads.
* :class:`.similarity.SimilarityBackend` — pluggable backend Protocol.
* :class:`.similarity.RuleBasedSimilarity` — canonical+Jaccard baseline.
* :func:`.router.get_router` — FastAPI router at ``/api/knowledge``.
"""

from .canonical import canonical_hash, normalise_strategy_text
from .evaluation import (
    DeploymentReadiness,
    StrategyEvaluation,
    evaluate_from_legacy_metrics,
)
from .repository import KnowledgeRepository, StrategyRepository
from .similarity import (
    RuleBasedSimilarity,
    SimilarityBackend,
    SimilarityMatch,
    StrategyQuery,
)

__all__ = [
    "canonical_hash",
    "normalise_strategy_text",
    "DeploymentReadiness",
    "StrategyEvaluation",
    "evaluate_from_legacy_metrics",
    "KnowledgeRepository",
    "StrategyRepository",
    "SimilarityBackend",
    "RuleBasedSimilarity",
    "SimilarityMatch",
    "StrategyQuery",
]
