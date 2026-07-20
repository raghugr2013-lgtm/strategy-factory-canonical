"""Phase 2 Stage 3.γ — Retro-scoring (P2C.11).

One-off idempotent backfill of the ~55 rows in the legacy
`ingested_strategies` collection into
`strategy_knowledge_base.strategies` via the Stage-3.β pipeline —
**without mutating the legacy collection at all**.

Design invariants (plan §3):

  * Read-only over legacy. `ingested_strategies` is never written to.
  * Writes go through the full Stage-3.β pipeline:
        domain_router → dedup_check → license_gate → trust_scorer
        → KnowledgeRepository.insert_ingested(...)
  * `KnowledgeRepository.insert_ingested()` honours `UKIE_GOVERNANCE_CUTOVER`.
    Retro-scoring CANNOT bypass the cutover — a "commit" run with
    the cutover OFF returns `dormant=N` and writes NOTHING (mirrors
    the pipeline semantics).
  * Idempotent — repo upsert is keyed on `(content_hash, domain)`.
    Re-running a retro-score returns `updated=N`, never duplicates.
  * Physical safety catch — the router requires the caller to submit
    `confirm_write="yes_write_the_kb"` on `dry_run=false`. Muscle-memory
    protection.
  * Every promoted row carries `retro_score_run_id` — the rollback
    filter.

Feature flags:
  * `UKIE_RETRO_SCORE_ENABLED` — the master switch (endpoint 503 when off).
  * `UKIE_GOVERNANCE_CUTOVER` — **additionally** required for any real
    Mongo write; enforced at the repository layer.
"""
from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from .connector import RawKnowledgeItem, now_iso
from .constants import (
    KNOWLEDGE_DB_NAME,
    PIPELINE_CONTRACT_VERSION,
    PIPELINE_VERSION,
)
from .domains import KnowledgeDomain, storage_collection_for
from .pipeline import _resolve_seed_tier
from . import dedup_check, domain_router, license_gate, trust_scorer
from .repository import (
    InsertResult,
    KnowledgeRepository,
    get_repository,
)

logger = logging.getLogger(__name__)


# ── Flag helpers ─────────────────────────────────────────────────────

def _flag(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def is_retro_score_enabled() -> bool:
    """`UKIE_RETRO_SCORE_ENABLED` — the master switch. Default OFF."""
    return _flag("UKIE_RETRO_SCORE_ENABLED", False)


CONFIRM_WRITE_TOKEN = "yes_write_the_kb"

RETRO_SCORE_RUNS_COLLECTION = "retro_score_runs"

LEGACY_COLLECTION = "ingested_strategies"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Result shapes ────────────────────────────────────────────────────

@dataclass
class RetroScoreSummary:
    """Aggregate outcome for one retro-scoring run.

    Landed in `strategy_knowledge_base.retro_score_runs` on every run —
    dry-run OR commit.
    """
    run_id:                      str
    started_at:                  str
    finished_at:                 str
    dry_run:                     bool
    requested_by:                str
    input_row_count:             int  = 0
    inserted:                    int  = 0
    updated:                     int  = 0
    rejected:                    int  = 0
    dormant:                     int  = 0
    errored:                     int  = 0
    trust_tier_counts:           Dict[str, int]  = field(default_factory=dict)
    license_outcome_counts:      Dict[str, int]  = field(default_factory=dict)
    domain_counts:               Dict[str, int]  = field(default_factory=dict)
    pipeline_version:            str = PIPELINE_VERSION
    pipeline_contract_version:   str = PIPELINE_CONTRACT_VERSION
    per_row_outcomes:            List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Legacy → canonical mapping (plan §3.2) ───────────────────────────

def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def legacy_row_to_item(row: Dict[str, Any]) -> Optional[RawKnowledgeItem]:
    """Map one legacy `ingested_strategies` row → canonical
    `RawKnowledgeItem`.

    Returns None when the row is unusable (missing `strategy_text`) —
    the caller counts these as `errored`.
    """
    text = row.get("strategy_text")
    if not text or not isinstance(text, (str, bytes)):
        return None
    body = text.encode("utf-8", errors="replace") if isinstance(text, str) else text
    content_hash = row.get("content_hash") or f"sha256:{_sha256_hex(body)}"
    fetched_at = row.get("fetched_at") or row.get("created_at") or now_iso()
    if isinstance(fetched_at, datetime):
        fetched_at = fetched_at.astimezone(timezone.utc).isoformat()
    domain = row.get("domain")
    if not domain:
        domain = KnowledgeDomain.STRATEGY
    elif isinstance(domain, str):
        try:
            domain = KnowledgeDomain(domain.lower())
        except ValueError:
            domain = KnowledgeDomain.STRATEGY
    extras: Dict[str, Any] = dict(row.get("extras") or {})
    if row.get("pair") and "pair" not in extras:
        extras["pair"] = row["pair"]
    if row.get("timeframe") and "timeframe" not in extras:
        extras["timeframe"] = row["timeframe"]
    return RawKnowledgeItem(
        domain=domain,
        connector_name=str(row.get("connector_name") or "github"),
        source_url=str(row.get("source_url") or ""),
        source_ref=str(row.get("source_ref") or row.get("source_url") or ""),
        content_hash=str(content_hash),
        fetched_at=str(fetched_at),
        content_bytes=body,
        content_mime=row.get("content_mime") or "text/plain",
        author=row.get("author"),
        license=row.get("license"),
        license_confidence=float(row.get("license_confidence") or 0.0),
        extras=extras or None,
    )


# ── Runner ───────────────────────────────────────────────────────────

class RetroScoreRunner:
    """Batch runner. Injectable Mongo getters + repository for tests."""

    def __init__(
        self,
        *,
        legacy_db_getter=None,
        kb_db_getter=None,
        repository: Optional[KnowledgeRepository] = None,
    ) -> None:
        self._legacy_db_getter = legacy_db_getter
        self._kb_db_getter = kb_db_getter
        self._repository = repository

    # ── DB resolvers ─────────────────────────────────────────────────

    def _legacy_db(self):
        if self._legacy_db_getter is not None:
            return self._legacy_db_getter()
        try:
            from engines.db import get_db
            return get_db()
        except Exception as e:                                # pragma: no cover
            logger.warning("[retro_score] cannot resolve legacy DB: %s", e)
            return None

    def _kb_db(self):
        if self._kb_db_getter is not None:
            return self._kb_db_getter()
        try:
            from engines.db import get_db
            return get_db().client[KNOWLEDGE_DB_NAME]
        except Exception as e:                                # pragma: no cover
            logger.warning("[retro_score] cannot resolve KB DB: %s", e)
            return None

    # ── Loader ───────────────────────────────────────────────────────

    async def _load_legacy_rows(self, batch_size: int) -> List[Dict[str, Any]]:
        db = self._legacy_db()
        if db is None:
            return []
        try:
            cur = db[LEGACY_COLLECTION].find({})
            rows: List[Dict[str, Any]] = []
            async for r in cur:
                rows.append(r)
                if batch_size and len(rows) >= batch_size * 10:  # safety cap
                    break
            return rows
        except Exception as e:                                 # noqa: BLE001
            logger.warning("[retro_score] legacy load failed: %s", e)
            return []

    # ── Main entry point ─────────────────────────────────────────────

    async def run(
        self,
        *,
        dry_run: bool          = True,
        batch_size: int        = 100,
        requested_by: str      = "operator",
        legacy_rows: Optional[List[Dict[str, Any]]] = None,
    ) -> RetroScoreSummary:
        """Execute one retro-scoring pass.

        Args:
            dry_run: True → do NOT commit to the KB (shadow-mode).
            batch_size: soft cap on per-batch chunking; ignored for
                small collections (≤55 legacy rows).
            requested_by: operator identifier — stamped on the run row.
            legacy_rows: injectable list of legacy rows (tests). When
                None, loads from `ingested_strategies` via Mongo.
        """
        run_id = uuid.uuid4().hex
        started = _now_iso()
        summary = RetroScoreSummary(
            run_id=run_id,
            started_at=started,
            finished_at="",
            dry_run=dry_run,
            requested_by=requested_by,
        )
        rows = legacy_rows if legacy_rows is not None else await self._load_legacy_rows(batch_size)
        summary.input_row_count = len(rows)

        repo = self._repository or get_repository()

        for legacy_row in rows:
            item = legacy_row_to_item(legacy_row)
            if item is None:
                summary.errored += 1
                summary.per_row_outcomes.append({
                    "legacy_id": str(legacy_row.get("_id") or ""),
                    "error":     "missing_or_invalid_strategy_text",
                })
                continue

            try:
                # domain routing
                routing = domain_router.route(item)
                # dedup (may pass-through)
                dedup = await dedup_check.check(item)
                # license gate
                lv = license_gate.classify(item)
                if lv.gated and lv.spdx_id:
                    item.license = lv.spdx_id
                    item.license_confidence = max(item.license_confidence, lv.confidence)
                # trust
                seed = _resolve_seed_tier(item)
                ts = trust_scorer.score(
                    item,
                    seed_tier=seed,
                    license_verdict=lv,
                    dedup_status=dedup.status,
                )
                if ts.scored and ts.tier is not None:
                    item.trust_tier = ts.tier
                    item.trust_reasons = tuple(a.get("reason", "") for a in ts.adjustments)

                # write (through the repo — honours UKIE_GOVERNANCE_CUTOVER)
                if dry_run:
                    write = InsertResult(
                        status="dormant",
                        domain=item.domain.value,
                        storage_collection=routing.storage_collection,
                        content_hash=item.content_hash or "",
                        reason="dry_run",
                    )
                elif dedup.status == "duplicate_same_domain":
                    write = InsertResult(
                        status="rejected",
                        domain=item.domain.value,
                        storage_collection=routing.storage_collection,
                        content_hash=item.content_hash or "",
                        reason="duplicate_same_domain",
                    )
                else:
                    write = await repo.insert_ingested(
                        item,
                        license_verdict=lv,
                        trust_score=ts,
                        retro_score_run_id=run_id,
                    )
            except Exception as e:                             # noqa: BLE001
                logger.exception("[retro_score] row crash")
                summary.errored += 1
                summary.per_row_outcomes.append({
                    "legacy_id": str(legacy_row.get("_id") or ""),
                    "error":     str(e)[:200],
                })
                continue

            # aggregate
            self._aggregate(summary, write, item, lv, ts)

        summary.finished_at = _now_iso()
        # persist the run row (dry-run OR commit — always audited)
        await self._persist_run_row(summary)
        return summary

    def _aggregate(
        self,
        summary: RetroScoreSummary,
        write: InsertResult,
        item: RawKnowledgeItem,
        lv,
        ts,
    ) -> None:
        s = write.status
        if s == "inserted":
            summary.inserted += 1
        elif s == "updated":
            summary.updated += 1
        elif s == "dormant":
            summary.dormant += 1
        elif s == "rejected":
            summary.rejected += 1
        elif s == "error":
            summary.errored += 1

        tier = ts.tier if getattr(ts, "scored", False) else None
        tier_key = f"T{tier}" if isinstance(tier, int) else "T?"
        summary.trust_tier_counts[tier_key] = summary.trust_tier_counts.get(tier_key, 0) + 1

        lic_outcome = getattr(lv, "outcome", None)
        lic_key = lic_outcome.value if lic_outcome is not None else "unknown"
        summary.license_outcome_counts[lic_key] = summary.license_outcome_counts.get(lic_key, 0) + 1

        d = item.domain.value
        summary.domain_counts[d] = summary.domain_counts.get(d, 0) + 1

        summary.per_row_outcomes.append({
            "content_hash": item.content_hash,
            "domain":       d,
            "status":       s,
            "trust_tier":   tier,
            "license":      lic_key,
        })

    async def _persist_run_row(self, summary: RetroScoreSummary) -> None:
        db = self._kb_db()
        if db is None:
            return
        try:
            row = summary.to_dict()
            # Store aggregate counts on the run row; per-row detail
            # already lives inline in `per_row_outcomes`.
            await db[RETRO_SCORE_RUNS_COLLECTION].insert_one(row)
        except Exception as e:                                 # noqa: BLE001
            logger.warning("[retro_score] run row persist failed: %s", e)

    # ── Rollback ─────────────────────────────────────────────────────

    async def rollback(self, run_id: str, *, requested_by: str, reason: str) -> Dict[str, Any]:
        """Delete every KB row carrying `retro_score_run_id == run_id`.

        Sweeps every domain sub-collection (retro-scoring may have
        landed rows in more than one). Idempotent — repeated calls
        after the first deletion return `deleted_count=0`.
        """
        db = self._kb_db()
        deleted = 0
        if db is None:
            return {
                "run_id":         run_id,
                "resolved":       "db_unavailable",
                "deleted_count":  0,
                "requested_by":   requested_by,
                "reason":         reason,
                "processed_at":   _now_iso(),
            }
        for domain in KnowledgeDomain:
            coll = storage_collection_for(domain)
            try:
                res = await db[coll].delete_many({"retro_score_run_id": run_id})
                deleted += int(getattr(res, "deleted_count", 0) or 0)
            except Exception as e:                             # noqa: BLE001
                logger.warning("[retro_score] rollback delete_many failed on %s: %s", coll, e)

        resolved = "rolled_back" if deleted > 0 else "already_rolled_back"

        # audit stamp on the run row (append a rollbacks entry)
        try:
            await db[RETRO_SCORE_RUNS_COLLECTION].update_one(
                {"run_id": run_id},
                {"$push": {"rollbacks": {
                    "requested_by":  requested_by,
                    "reason":        reason,
                    "deleted_count": deleted,
                    "resolved":      resolved,
                    "at":            _now_iso(),
                }}},
            )
        except Exception as e:                                 # noqa: BLE001
            logger.debug("[retro_score] rollback audit stamp failed: %s", e)
        return {
            "run_id":         run_id,
            "resolved":       resolved,
            "deleted_count":  deleted,
            "requested_by":   requested_by,
            "reason":         reason,
            "processed_at":   _now_iso(),
        }


# ── Module-level singleton ───────────────────────────────────────────

_RUNNER: Optional[RetroScoreRunner] = None


def get_runner() -> RetroScoreRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = RetroScoreRunner()
    return _RUNNER


def _reset_for_tests() -> None:
    global _RUNNER
    _RUNNER = None
