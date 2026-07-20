"""Phase 2 Stage 3.γ — Promote Bridge writer + audit (P2C.9 β).

The **one-way, audited** path from `strategy_knowledge_base.strategies`
(UKIE-KB) → production `strategies` collection. Individual promote /
demote only — no bulk sweep.

Design invariants (plan §2.3, §2.4, §5.5):

  * **Hard rails re-stamped at the writer.** Even if the KB row carries
    `learning_only=false, eligible_for_deploy=true` (mischievous data),
    the production row lands with the safe values.
  * **Audit-first.** Every attempt writes one row to
    `strategy_knowledge_base.promote_events` — success OR refusal.
    Refusal reasons are the primary audit signal.
  * **Rollback path.** Every promoted row carries `promoted_from` +
    `origin="ukie_promote"`; `demote_item()` deletes it (idempotent).
  * **Dry-run first.** Callers may request `dry_run=True` to preview
    the composed document without any Mongo write. The endpoint
    default follows `UKIE_PROMOTE_DRY_RUN` (default TRUE).

Feature flags:
  * `UKIE_PROMOTE_BRIDGE_ENABLED` — the master switch (checked by the
    router; the writer itself will refuse with `flag_off` if called
    directly with the flag off).
  * `UKIE_PROMOTE_DRY_RUN` — the default dry-run behaviour when the
    master switch is on.

No writes to production `strategies` when either master switch is off.
No reads of production `strategies` beyond the dedup lookup.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .constants import (
    KNOWLEDGE_DB_NAME,
    PIPELINE_CONTRACT_VERSION,
    PIPELINE_VERSION,
)
from .domains import KnowledgeDomain, storage_collection_for
from .promote import (
    PromoteOptions,
    PromoteVerdict,
    evaluate_promote,
    is_promote_bridge_enabled,
    is_promote_dry_run_default,
)

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────

PROMOTE_EVENTS_COLLECTION = "promote_events"

ORIGIN_UKIE_PROMOTE = "ukie_promote"

# Resolved outcome markers stamped on both PromoteResult and the audit event
RESOLVED_PROMOTED       = "promoted"
RESOLVED_REFUSED        = "refused"
RESOLVED_DRY_RUN        = "dry_run"
RESOLVED_DEMOTED        = "demoted"
RESOLVED_ALREADY_DEMOTED = "already_demoted"
RESOLVED_FLAG_OFF       = "flag_off"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Result shapes ────────────────────────────────────────────────────

@dataclass
class PromoteResult:
    """Outcome of a single promote / dry-run attempt.

    Attributes:
        resolved: `"promoted"` | `"refused"` | `"dry_run"` | `"flag_off"`.
        item_id: KB item `_id` (str).
        prod_strategy_id: Production `strategies._id` (str) — populated
            when `resolved="promoted"`.
        refuse_reason: From `PromoteVerdict.refuse_reason` when refused.
        event_id: The audit event's uuid (str).
        composed_doc: The production document that was (or would be)
            written. Present on `dry_run` and `promoted`.
        verdict: The full `PromoteVerdict` (as dict) for transparency.
        pipeline_version / contract_version: version stamps.
        processed_at: UTC ISO timestamp.
    """
    resolved:                    str
    item_id:                     Optional[str]
    prod_strategy_id:            Optional[str]
    refuse_reason:               Optional[str]
    event_id:                    str
    composed_doc:                Optional[Dict[str, Any]]
    verdict:                     Dict[str, Any]
    pipeline_version:            str
    pipeline_contract_version:   str
    processed_at:                str
    override_dedup:              bool                     = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DemoteResult:
    """Outcome of a rollback (demote) call."""
    resolved:                    str
    item_id:                     str
    deleted_count:               int
    event_id:                    str
    pipeline_version:            str
    pipeline_contract_version:   str
    processed_at:                str
    requested_by:                str
    reason:                      str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Bridge implementation ────────────────────────────────────────────

class PromoteBridge:
    """The audited promote / demote writer.

    Two Mongo surfaces, both injectable for tests:
      * `prod_db_getter()`  — production DB (contains `strategies`).
      * `kb_db_getter()`    — `strategy_knowledge_base` DB
                              (contains `strategies` sub-collection
                              AND the audit `promote_events` collection).
    """

    def __init__(
        self,
        prod_db_getter=None,
        kb_db_getter=None,
    ) -> None:
        self._prod_db_getter = prod_db_getter
        self._kb_db_getter = kb_db_getter

    # ── DB resolvers (lazy, fail-open on error) ──────────────────────

    def _prod_db(self):
        if self._prod_db_getter is not None:
            return self._prod_db_getter()
        try:
            from engines.db import get_db
            return get_db()
        except Exception as e:                                # pragma: no cover
            logger.warning("[promote_bridge] cannot resolve prod DB: %s", e)
            return None

    def _kb_db(self):
        if self._kb_db_getter is not None:
            return self._kb_db_getter()
        try:
            from engines.db import get_db
            return get_db().client[KNOWLEDGE_DB_NAME]
        except Exception as e:                                # pragma: no cover
            logger.warning("[promote_bridge] cannot resolve KB DB: %s", e)
            return None

    # ── Public API ────────────────────────────────────────────────────

    async def promote_item(
        self,
        item_id: str,
        opts: PromoteOptions,
        *,
        dry_run: Optional[bool] = None,
    ) -> PromoteResult:
        """Promote one KB item to production `strategies`.

        Args:
            item_id: The KB row's `_id` — str or ObjectId-parseable str.
            opts: Operator-supplied options (reason, requested_by, ...).
            dry_run: When None, follows `UKIE_PROMOTE_DRY_RUN`
                     (default TRUE). When True, evaluates preconditions
                     + composes the target doc but does NOT commit.
                     When False, commits on satisfaction.
        Never raises.
        """
        # Master switch — the router refuses with 503 when off, but be
        # defensive so direct calls also fail predictably.
        if not is_promote_bridge_enabled():
            event_id = uuid.uuid4().hex
            return PromoteResult(
                resolved=RESOLVED_FLAG_OFF,
                item_id=str(item_id) if item_id else None,
                prod_strategy_id=None,
                refuse_reason="promote_flag_off",
                event_id=event_id,
                composed_doc=None,
                verdict={},
                pipeline_version=PIPELINE_VERSION,
                pipeline_contract_version=PIPELINE_CONTRACT_VERSION,
                processed_at=_now_iso(),
                override_dedup=opts.override_dedup,
            )

        effective_dry_run = is_promote_dry_run_default() if dry_run is None else bool(dry_run)

        # 1. Load KB item
        kb_db = self._kb_db()
        item = await self._load_kb_item(kb_db, item_id)

        # 2. Load production dedup collision (if any)
        prod_db = self._prod_db()
        content_hash = str(item.get("content_hash") or "") if item else ""
        prod_dedup_id = await self._find_prod_dedup(prod_db, content_hash) if content_hash else None

        # 3. Evaluate preconditions
        verdict = evaluate_promote(item, opts, prod_dedup_id=prod_dedup_id)

        # 4. Compose target doc (only meaningful when `ok`)
        composed: Optional[Dict[str, Any]] = None
        prod_id: Optional[str] = None
        event_id = uuid.uuid4().hex

        if verdict.ok and item is not None:
            composed = self._compose_prod_doc(
                item=item,
                opts=opts,
                verdict=verdict,
                event_id=event_id,
                now=_now_iso(),
            )
            if effective_dry_run:
                resolved = RESOLVED_DRY_RUN
            else:
                prod_id = await self._insert_prod(prod_db, composed)
                resolved = RESOLVED_PROMOTED if prod_id else RESOLVED_REFUSED
                if not prod_id:
                    verdict.refuse_reason = "write_failed"
        else:
            resolved = RESOLVED_REFUSED

        # 5. Audit event — every attempt lands here
        await self._write_audit_event(
            kb_db=kb_db,
            event_id=event_id,
            item_id=str(item_id),
            opts=opts,
            verdict=verdict,
            resolved=resolved,
            prod_strategy_id=prod_id,
            dry_run=effective_dry_run,
        )

        return PromoteResult(
            resolved=resolved,
            item_id=str(item_id),
            prod_strategy_id=prod_id,
            refuse_reason=verdict.refuse_reason,
            event_id=event_id,
            composed_doc=composed,
            verdict=verdict.to_dict(),
            pipeline_version=PIPELINE_VERSION,
            pipeline_contract_version=PIPELINE_CONTRACT_VERSION,
            processed_at=_now_iso(),
            override_dedup=opts.override_dedup,
        )

    async def demote_item(
        self,
        item_id: str,
        *,
        requested_by: str,
        reason: str,
    ) -> DemoteResult:
        """Delete every production `strategies` row promoted from `item_id`.

        Idempotent: repeated calls after all copies are removed return
        `resolved="already_demoted", deleted_count=0`. Never touches
        the source KB row (that remains the source of truth).
        """
        if not is_promote_bridge_enabled():
            event_id = uuid.uuid4().hex
            return DemoteResult(
                resolved=RESOLVED_FLAG_OFF,
                item_id=str(item_id),
                deleted_count=0,
                event_id=event_id,
                pipeline_version=PIPELINE_VERSION,
                pipeline_contract_version=PIPELINE_CONTRACT_VERSION,
                processed_at=_now_iso(),
                requested_by=requested_by,
                reason=reason,
            )

        prod_db = self._prod_db()
        kb_db = self._kb_db()
        event_id = uuid.uuid4().hex
        deleted = 0
        if prod_db is not None:
            try:
                res = await prod_db["strategies"].delete_many({
                    "promoted_from":  str(item_id),
                    "origin":         ORIGIN_UKIE_PROMOTE,
                })
                deleted = int(getattr(res, "deleted_count", 0) or 0)
            except Exception as e:                             # noqa: BLE001
                logger.warning("[promote_bridge] demote delete failed: %s", e)
                deleted = 0

        resolved = RESOLVED_DEMOTED if deleted > 0 else RESOLVED_ALREADY_DEMOTED
        # Write a `demoted_event`
        if kb_db is not None:
            try:
                await kb_db[PROMOTE_EVENTS_COLLECTION].insert_one({
                    "event_id":                  event_id,
                    "attempted_at":              _now_iso(),
                    "attempted_by":              requested_by,
                    "item_id":                   str(item_id),
                    "resolved":                  resolved,
                    "refuse_reason":             None,
                    "prod_strategy_id":          None,
                    "override_dedup":            False,
                    "deleted_count":             deleted,
                    "reason":                    reason,
                    "pipeline_version":          PIPELINE_VERSION,
                    "pipeline_contract_version": PIPELINE_CONTRACT_VERSION,
                    "kind":                      "demote",
                })
            except Exception as e:                             # noqa: BLE001
                logger.warning("[promote_bridge] demote audit write failed: %s", e)

        return DemoteResult(
            resolved=resolved,
            item_id=str(item_id),
            deleted_count=deleted,
            event_id=event_id,
            pipeline_version=PIPELINE_VERSION,
            pipeline_contract_version=PIPELINE_CONTRACT_VERSION,
            processed_at=_now_iso(),
            requested_by=requested_by,
            reason=reason,
        )

    # ── Internals ─────────────────────────────────────────────────────

    async def _load_kb_item(self, kb_db, item_id: str) -> Optional[Dict[str, Any]]:
        if kb_db is None or not item_id:
            return None
        target = storage_collection_for(KnowledgeDomain.STRATEGY)
        # Try exact string match on `_id` first (test-friendly). If the
        # underlying store expects ObjectId, we try that as a fallback.
        try:
            doc = await kb_db[target].find_one({"_id": item_id})
            if doc is not None:
                return doc
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[promote_bridge] str _id lookup failed: %s", e)
        # ObjectId fallback (production Mongo)
        try:
            from bson import ObjectId
            oid = ObjectId(item_id)
        except Exception:                                      # noqa: BLE001
            return None
        try:
            return await kb_db[target].find_one({"_id": oid})
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[promote_bridge] oid _id lookup failed: %s", e)
            return None

    async def _find_prod_dedup(self, prod_db, content_hash: str) -> Optional[str]:
        if prod_db is None or not content_hash:
            return None
        try:
            hit = await prod_db["strategies"].find_one(
                {"content_hash": content_hash}, {"_id": 1},
            )
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[promote_bridge] prod dedup lookup failed: %s", e)
            return None
        if hit is None:
            return None
        return str(hit.get("_id"))

    @staticmethod
    def _derive_strategy_id(content_hash: str) -> str:
        """Deterministic production strategy_id from the KB content_hash.

        Mirrors the platform's UKIE-promote origin: the prefix labels
        the origin, and the hash uniquely identifies the source.
        """
        digest = (content_hash or "").split(":", 1)[-1][:16] or "unknown"
        return f"ukie-{digest}"

    def _compose_prod_doc(
        self,
        *,
        item: Dict[str, Any],
        opts: PromoteOptions,
        verdict: PromoteVerdict,
        event_id: str,
        now: str,
    ) -> Dict[str, Any]:
        """Compose the production `strategies` document.

        Hard rails (§2.3): `learning_only=True`, `eligible_for_deploy=False`
        stamped **regardless of item state** — a future Phase-3 approval
        loop is the only path that flips `eligible_for_deploy`.
        """
        # strategy_text — content_bytes decoded to utf-8 (best-effort).
        cb = item.get("content_bytes")
        if isinstance(cb, bytes):
            strategy_text = cb.decode("utf-8", errors="replace")
        elif isinstance(cb, str):
            strategy_text = cb
        else:
            strategy_text = ""

        extras = item.get("extras") or {}
        pair = extras.get("pair") if isinstance(extras, dict) else None
        timeframe = extras.get("timeframe") if isinstance(extras, dict) else None
        content_hash = str(item.get("content_hash") or "")

        return {
            "strategy_id":              self._derive_strategy_id(content_hash),
            "strategy_text":            strategy_text,
            "content_hash":             content_hash,
            "pair":                     pair,
            "timeframe":                timeframe,
            "source":                   ORIGIN_UKIE_PROMOTE,
            "origin":                   ORIGIN_UKIE_PROMOTE,
            "learning_only":            True,                                # HARD RAIL
            "eligible_for_deploy":      False,                               # HARD RAIL
            "promoted_from":            verdict.item_id,
            "promoted_by":              opts.requested_by,
            "promoted_at":              now,
            "promoted_reason":          opts.reason,
            "promote_event_id":         event_id,
            "override_dedup":           opts.override_dedup,
            "trust_tier":               verdict.trust_tier,
            "license":                  item.get("license"),
            "license_verdict":          item.get("license_verdict"),
            "promote_pipeline_version":          PIPELINE_VERSION,
            "promote_pipeline_contract_version": PIPELINE_CONTRACT_VERSION,
        }

    async def _insert_prod(self, prod_db, doc: Dict[str, Any]) -> Optional[str]:
        if prod_db is None:
            return None
        try:
            res = await prod_db["strategies"].insert_one(doc)
            return str(getattr(res, "inserted_id", "") or doc.get("strategy_id") or "")
        except Exception as e:                                 # noqa: BLE001
            logger.warning("[promote_bridge] prod insert failed: %s", e)
            return None

    async def _write_audit_event(
        self,
        *,
        kb_db,
        event_id: str,
        item_id: str,
        opts: PromoteOptions,
        verdict: PromoteVerdict,
        resolved: str,
        prod_strategy_id: Optional[str],
        dry_run: bool,
    ) -> None:
        if kb_db is None:
            return
        event = {
            "event_id":                  event_id,
            "attempted_at":              _now_iso(),
            "attempted_by":              opts.requested_by,
            "item_id":                   item_id,
            "resolved":                  resolved,
            "refuse_reason":             verdict.refuse_reason,
            "prod_strategy_id":          prod_strategy_id,
            "override_dedup":            opts.override_dedup,
            "dry_run":                   dry_run,
            "reason":                    opts.reason,
            "verdict":                   verdict.to_dict(),
            "pipeline_version":          PIPELINE_VERSION,
            "pipeline_contract_version": PIPELINE_CONTRACT_VERSION,
            "kind":                      "promote",
        }
        try:
            await kb_db[PROMOTE_EVENTS_COLLECTION].insert_one(event)
        except Exception as e:                                 # noqa: BLE001
            logger.warning("[promote_bridge] audit event write failed: %s", e)


# ── Module-level singleton ───────────────────────────────────────────

_BRIDGE: Optional[PromoteBridge] = None


def get_bridge() -> PromoteBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = PromoteBridge()
    return _BRIDGE


def _reset_for_tests() -> None:
    global _BRIDGE
    _BRIDGE = None
