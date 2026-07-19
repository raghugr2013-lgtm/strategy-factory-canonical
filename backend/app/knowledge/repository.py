"""Safety-first repositories for strategy reads.

Two classes, one enforced invariant:

    ┌─────────────────────────────────────────────────────────────┐
    │  Production reads default to `{eligible_for_deploy: True}`. │
    │  Knowledge Base reads require an *explicit* opt-in.         │
    └─────────────────────────────────────────────────────────────┘

Before Phase 1.6, ``learning_only`` / ``eligible_for_deploy`` were
row-level guards that every caller had to remember to check. A single
missed filter could promote a historical, unvalidated strategy into a
live path. These wrappers make forgetting structurally impossible:

* :class:`StrategyRepository` — production reads. ``find`` and
  ``find_one`` inject ``{"eligible_for_deploy": True}`` into every
  query. Callers that explicitly want KB access must invoke a
  *different* class (:class:`KnowledgeRepository`).

* :class:`KnowledgeRepository` — Historical KB reads. Injects
  ``{"learning_only": True}`` into every query and refuses to write.

Both wrappers are deliberately thin — no ORM, no schema magic. They
are pymongo collection accessors with one method's worth of extra
safety, so the audit surface is tiny.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


class _ImmutableError(RuntimeError):
    """Raised when a caller tries to mutate a read-only KB."""


def _merge_filter(user_filter: Mapping[str, Any] | None,
                  mandatory: Mapping[str, Any]) -> dict:
    """Merge a mandatory safety filter into a user-supplied one.

    * If the caller does not constrain the safety-guarded field, the
      mandatory clause is added verbatim.
    * If the caller *does* constrain the field, the merge is allowed
      only when the caller's constraint is a strict tightening
      (i.e. equal to the mandatory clause). Any other value — most
      importantly ``False`` for ``eligible_for_deploy`` — raises
      :class:`_ImmutableError`. This blocks attempts to reach the KB
      through the production repo.
    """
    if not user_filter:
        return dict(mandatory)
    merged = dict(user_filter)
    for k, v in mandatory.items():
        if k in merged and merged[k] != v:
            raise _ImmutableError(
                f"forbidden filter override: caller set {k}={merged[k]!r} "
                f"but the safety guard requires {k}={v!r}. Use the correct "
                f"repository (StrategyRepository vs KnowledgeRepository) "
                f"instead of overriding the guard."
            )
        merged[k] = v
    return merged


# ── Production reads ────────────────────────────────────────────────

class StrategyRepository:
    """Production-safe reads over any strategy-bearing collection.

    Every ``find`` / ``find_one`` transparently injects the safety
    filter ``{"eligible_for_deploy": {"$ne": False}}`` into the caller's
    filter. Semantics:

    * A document with ``eligible_for_deploy == True`` is visible.
    * A document *without* the field is visible (backward compat for
      the pre-Phase-1.6 production ``strategies`` collection).
    * A document with ``eligible_for_deploy == False`` — i.e. every
      Historical Knowledge Base row — is **invisible**.

    This is the strongest guarantee that lets the safety net roll out
    without a data-migration wave and without any active-pool document
    being hidden by accident.

    Writes (``insert_one``, ``update_one``, ``delete_one``) are passed
    through untouched. This wrapper is a *read-side* safety net; the
    write side is protected by the existing governance pipeline.

    Works transparently over both ``pymongo.collection.Collection``
    (sync) and ``motor.motor_asyncio.AsyncIOMotorCollection`` (async)
    — the wrapper only injects the safety filter and delegates, so
    whichever call semantics the caller uses (``await find_one(...)``
    or the sync equivalent) continues to work.
    """

    SAFETY_FILTER = {"eligible_for_deploy": {"$ne": False}}

    def __init__(self, collection: Collection):
        self._c = collection

    @property
    def name(self) -> str:
        return self._c.name

    def find(self, filter: Mapping[str, Any] | None = None,
             projection: Mapping[str, Any] | None = None,
             *args, **kwargs):
        safe = _merge_filter(filter, self.SAFETY_FILTER)
        return self._c.find(safe, projection, *args, **kwargs)

    def find_one(self, filter: Mapping[str, Any] | None = None,
                 projection: Mapping[str, Any] | None = None,
                 *args, **kwargs):
        safe = _merge_filter(filter, self.SAFETY_FILTER)
        return self._c.find_one(safe, projection, *args, **kwargs)

    def count_documents(self, filter: Mapping[str, Any] | None = None,
                        *args, **kwargs) -> int:
        safe = _merge_filter(filter, self.SAFETY_FILTER)
        return self._c.count_documents(safe, *args, **kwargs)

    # Writes pass through unchanged — the safety here is on read.
    def insert_one(self, *args, **kwargs):
        return self._c.insert_one(*args, **kwargs)

    def update_one(self, *args, **kwargs):
        return self._c.update_one(*args, **kwargs)

    def delete_one(self, *args, **kwargs):
        return self._c.delete_one(*args, **kwargs)

    def raw(self) -> Collection:
        """Escape hatch for callers that *genuinely* need unguarded
        access — audit tooling, migrations, admin CLI. Every use of
        this should be visible in code review."""
        return self._c


# ── Knowledge Base reads (read-only) ────────────────────────────────

class KnowledgeRepository:
    """Read-only accessor for the historical Strategy Knowledge Base.

    Bound to a specific database (default: ``strategy_knowledge_base``)
    which is physically distinct from production. Every read
    transparently injects ``{"learning_only": True}``. Every write
    raises :class:`_ImmutableError`.

    The KB is intended to survive across pods and platform versions
    unchanged — it is an audit-quality corpus of historical experiments.
    Mutation of a KB row requires opening a new DB session with an
    admin identity outside this API, on purpose.
    """

    LEARNING_FILTER = {"learning_only": True}
    DEFAULT_DB_NAME = "strategy_knowledge_base"

    def __init__(self, database: Database, collection_name: str):
        self._db = database
        self._c: Collection = database[collection_name]

    @classmethod
    def open(cls, mongo_url: str,
             collection_name: str = "strategy_kb_view",
             db_name: str | None = None) -> "KnowledgeRepository":
        """Convenience constructor for callers that don't hold a DB handle."""
        db = MongoClient(mongo_url)[db_name or cls.DEFAULT_DB_NAME]
        return cls(db, collection_name)

    @property
    def name(self) -> str:
        return self._c.name

    def find(self, filter: Mapping[str, Any] | None = None,
             projection: Mapping[str, Any] | None = None,
             *args, **kwargs):
        safe = _merge_filter(filter, self.LEARNING_FILTER)
        return self._c.find(safe, projection, *args, **kwargs)

    def find_one(self, filter: Mapping[str, Any] | None = None,
                 projection: Mapping[str, Any] | None = None,
                 *args, **kwargs):
        safe = _merge_filter(filter, self.LEARNING_FILTER)
        return self._c.find_one(safe, projection, *args, **kwargs)

    def count_documents(self, filter: Mapping[str, Any] | None = None,
                        *args, **kwargs) -> int:
        safe = _merge_filter(filter, self.LEARNING_FILTER)
        return self._c.count_documents(safe, *args, **kwargs)

    def aggregate(self, pipeline: Iterable[Mapping[str, Any]], *args, **kwargs):
        # Prepend a mandatory match stage so aggregation cannot escape
        # the learning_only guard.
        guarded = [{"$match": dict(self.LEARNING_FILTER)}, *pipeline]
        return self._c.aggregate(guarded, *args, **kwargs)

    # ── Write refusals ──────────────────────────────────────────────
    def insert_one(self, *_a, **_kw):
        raise _ImmutableError("KnowledgeRepository is read-only; refusing insert_one")

    def insert_many(self, *_a, **_kw):
        raise _ImmutableError("KnowledgeRepository is read-only; refusing insert_many")

    def update_one(self, *_a, **_kw):
        raise _ImmutableError("KnowledgeRepository is read-only; refusing update_one")

    def update_many(self, *_a, **_kw):
        raise _ImmutableError("KnowledgeRepository is read-only; refusing update_many")

    def delete_one(self, *_a, **_kw):
        raise _ImmutableError("KnowledgeRepository is read-only; refusing delete_one")

    def delete_many(self, *_a, **_kw):
        raise _ImmutableError("KnowledgeRepository is read-only; refusing delete_many")

    def replace_one(self, *_a, **_kw):
        raise _ImmutableError("KnowledgeRepository is read-only; refusing replace_one")
