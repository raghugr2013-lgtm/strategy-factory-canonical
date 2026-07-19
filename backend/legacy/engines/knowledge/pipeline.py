"""Phase 2 Stage 3.β — UKIE pipeline composition.

Runs the four stages + repository write in order:

    domain_router → dedup_check → license_gate → trust_scorer → repository

Each stage is INDEPENDENTLY feature-gated (see individual modules).
A disabled stage is a **pass-through** — the item continues to the
next stage unchanged, with an outcome marker indicating "skipped".

The pipeline runner is intentionally thin — it composes pure/near-pure
stages. All I/O is delegated to `repository.insert_ingested()` (Mongo
write) and `dedup_check.check()` (Mongo read). Both fail-open on
error (log + degrade to pass-through) so a Mongo blip cannot block
ingestion.

Feature-gate hierarchy:
  * `UKIE_GOVERNANCE_CUTOVER=false` — even if every stage flag is on,
    the repository write is dormant. Safe default.
  * A stage's individual flag being off makes that stage a
    pass-through but does not affect other stages.

Outcome record — stamped on every pipeline invocation:
  * `pipeline_version` — bump for implementation changes
  * `pipeline_contract_version` — bump for semantic changes
  * `processed_at` — UTC ISO timestamp
  * Per-stage outcome dicts
  * Repository result

Not-persisted by the pipeline itself; the outcome is returned to the
caller who chooses whether to log / persist / diff.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from . import dedup_check, domain_router, license_gate, trust_scorer
from .connector import RawKnowledgeItem
from .constants import PIPELINE_CONTRACT_VERSION, PIPELINE_VERSION
from .repository import (
    InsertResult,
    KnowledgeRepository,
    get_repository,
    is_cutover_enabled,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PipelineOutcome:
    """One item's traversal of the pipeline.

    Aggregates every stage's outcome + the repository result, plus the
    two version stamps + wall-clock timestamp. Safe to log, serialise,
    diff, or replay.
    """

    item_hash:                   str
    item_domain:                 str
    pipeline_version:            str
    pipeline_contract_version:   str
    processed_at:                str
    routing:                     Dict[str, Any]
    dedup:                       Dict[str, Any]
    license_verdict:             Dict[str, Any]
    trust_score:                 Dict[str, Any]
    write:                       Dict[str, Any]
    duration_ms:                 float             = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineSummary:
    """Aggregate outcome for a batch run."""

    started_at:                  str
    finished_at:                 str
    pipeline_version:            str
    pipeline_contract_version:   str
    dry_run:                     bool
    total:                       int
    inserted:                    int = 0
    updated:                     int = 0
    dormant:                     int = 0
    rejected:                    int = 0
    errored:                     int = 0
    trust_tier_counts:           Dict[str, int]   = field(default_factory=dict)
    license_outcome_counts:      Dict[str, int]   = field(default_factory=dict)
    domain_counts:               Dict[str, int]   = field(default_factory=dict)
    outcomes:                    List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


async def run_one(
    item: RawKnowledgeItem,
    *,
    dry_run: bool = False,
    repository: Optional[KnowledgeRepository] = None,
) -> PipelineOutcome:
    """Run one item through the full pipeline.

    Args:
        item: The `RawKnowledgeItem` to process.
        dry_run: If True, the repository is bypassed regardless of the
            `UKIE_GOVERNANCE_CUTOVER` flag. Used by the dry-run harness.
        repository: Injectable repository (tests).
    """
    t0 = datetime.now(timezone.utc)

    # Stage 1 — domain routing
    routing = domain_router.route(item)

    # Stage 2 — dedup (may be pass-through)
    dedup = await dedup_check.check(item)

    # Stage 3 — license gate
    license_verdict = license_gate.classify(item)
    # Feed license outcome onto the item so downstream consumers
    # (Repository, retriever) can rely on `item.license` being canonical.
    if license_verdict.gated and license_verdict.spdx_id:
        item.license = license_verdict.spdx_id
        item.license_confidence = max(item.license_confidence, license_verdict.confidence)

    # Stage 4 — trust score
    seed = _resolve_seed_tier(item)
    ts = trust_scorer.score(
        item,
        seed_tier=seed,
        license_verdict=license_verdict,
        dedup_status=dedup.status,
    )
    # Stamp trust onto the item (repository re-reads for storage)
    if ts.scored and ts.tier is not None:
        item.trust_tier = ts.tier
        item.trust_reasons = tuple(a.get("reason", "") for a in ts.adjustments)

    # Stage 5 — repository write (or bypass in dry-run)
    if dry_run:
        write_result = InsertResult(
            status="dormant",
            domain=item.domain.value,
            storage_collection=routing.storage_collection,
            content_hash=item.content_hash or "",
            reason="dry_run",
        )
    elif dedup.status == "duplicate_same_domain":
        # Refuse the write on same-domain hash collision — this is the
        # invariant tested by the master-plan Gate 3 checklist.
        write_result = InsertResult(
            status="rejected",
            domain=item.domain.value,
            storage_collection=routing.storage_collection,
            content_hash=item.content_hash or "",
            reason="duplicate_same_domain",
        )
    else:
        repo = repository or get_repository()
        write_result = await repo.insert_ingested(
            item,
            license_verdict=license_verdict,
            trust_score=ts,
        )

    duration_ms = (datetime.now(timezone.utc) - t0).total_seconds() * 1000.0
    return PipelineOutcome(
        item_hash=item.content_hash or "",
        item_domain=item.domain.value,
        pipeline_version=PIPELINE_VERSION,
        pipeline_contract_version=PIPELINE_CONTRACT_VERSION,
        processed_at=_now_iso(),
        routing=routing.to_outcome(),
        dedup=dedup.to_outcome(),
        license_verdict=license_verdict.to_outcome(),
        trust_score=ts.to_outcome(),
        write=write_result.to_dict(),
        duration_ms=round(duration_ms, 3),
    )


async def run_batch(
    items: Iterable[RawKnowledgeItem],
    *,
    dry_run: bool = False,
    repository: Optional[KnowledgeRepository] = None,
) -> PipelineSummary:
    """Run a batch of items and return an aggregate summary."""
    started = _now_iso()
    summary = PipelineSummary(
        started_at=started,
        finished_at="",
        pipeline_version=PIPELINE_VERSION,
        pipeline_contract_version=PIPELINE_CONTRACT_VERSION,
        dry_run=dry_run,
        total=0,
    )
    for item in items:
        summary.total += 1
        try:
            outcome = await run_one(item, dry_run=dry_run, repository=repository)
        except Exception as e:  # noqa: BLE001
            logger.exception("[pipeline] run_one crashed for %s", item.content_hash)
            summary.errored += 1
            summary.outcomes.append({
                "item_hash": item.content_hash or "",
                "error":     str(e)[:200],
            })
            continue
        # Aggregate
        write_status = outcome.write.get("status", "")
        if write_status == "inserted":
            summary.inserted += 1
        elif write_status == "updated":
            summary.updated += 1
        elif write_status == "dormant":
            summary.dormant += 1
        elif write_status == "rejected":
            summary.rejected += 1
        elif write_status == "error":
            summary.errored += 1
        tier = outcome.trust_score.get("tier")
        tier_key = f"T{tier}" if isinstance(tier, int) else "T?"
        summary.trust_tier_counts[tier_key] = summary.trust_tier_counts.get(tier_key, 0) + 1
        lic = outcome.license_verdict.get("outcome") or "unknown"
        summary.license_outcome_counts[lic] = summary.license_outcome_counts.get(lic, 0) + 1
        d = outcome.item_domain
        summary.domain_counts[d] = summary.domain_counts.get(d, 0) + 1
        summary.outcomes.append(outcome.to_dict())
    summary.finished_at = _now_iso()
    return summary


# ── Diagnostics ──────────────────────────────────────────────────────

def pipeline_status() -> Dict[str, Any]:
    """Snapshot of enabled stages + versions — used by the router
    `/api/knowledge/pipeline/status` endpoint."""
    return {
        "pipeline_version":            PIPELINE_VERSION,
        "pipeline_contract_version":   PIPELINE_CONTRACT_VERSION,
        "stages": {
            "domain_router":   {"enabled": domain_router.is_enabled()},
            "dedup_check":     {"enabled": dedup_check.is_enabled()},
            "license_gate":    {"enabled": license_gate.is_enabled()},
            "trust_scorer":    {"enabled": trust_scorer.is_enabled()},
        },
        "governance_cutover": {"enabled": is_cutover_enabled()},
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _resolve_seed_tier(item: RawKnowledgeItem) -> int:
    """Resolve the connector's `default_trust_tier` for the item's
    connector. Falls back to 3 (Standard) when the connector is not
    registered."""
    try:
        from .registry import get_connector
        c = get_connector(item.connector_name)
        if c is not None:
            return int(getattr(c, "default_trust_tier", 3))
    except Exception:                                         # pragma: no cover
        pass
    return 3


# ── Last-run cache (in-memory) ───────────────────────────────────────

_LAST_SUMMARY: Optional[PipelineSummary] = None


def set_last_summary(s: PipelineSummary) -> None:
    global _LAST_SUMMARY
    _LAST_SUMMARY = s


def get_last_summary() -> Optional[PipelineSummary]:
    return _LAST_SUMMARY


def _reset_last_summary_for_tests() -> None:
    global _LAST_SUMMARY
    _LAST_SUMMARY = None
