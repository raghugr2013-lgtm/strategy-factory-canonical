"""ASF importer walker — classify every row in a `PackageReadResult`
into one or more `ApplyAction`s. Pure function; no DB writes.

Per `ASF_BACKEND_ARCHITECTURE.md §3.6`:
    - For each strategy doc: a `strategy_library` or
      `strategy_library_archive` action, plus dedup outcome.
    - For each lineage row: a `mutation_events` /
      `mutation_stability_log` action.
    - For each T3 row: a `strategy_lifecycle_history` /
      `strategy_performance_history` / `auto_factory_alert_log` action
      tagged ``imported=true``.

The walker reads the receiver DB (read-only) to determine canonical
matches; the upserter writes.
"""
from __future__ import annotations

import logging
from typing import List, Literal, Optional

from engines.asf.dedup_policy import apply_dedup
from engines.asf.schema import (
    ApplyAction,
    PackageReadResult,
    StrategyDoc,
)

logger = logging.getLogger(__name__)

Policy = Literal["skip", "merge", "replace"]


async def _find_canonical_strategy(
    db, fingerprint: str, strategy_hash: str,
) -> tuple[Optional[dict], Literal["fingerprint", "strategy_hash", "none"]]:
    """Match by fingerprint first (primary key per spec §13.1), then
    strategy_hash (alert case per §13.2)."""
    doc = await db["strategy_library"].find_one({"fingerprint": fingerprint})
    if doc:
        return doc, "fingerprint"
    if strategy_hash:
        doc = await db["strategy_library"].find_one({"strategy_hash": strategy_hash})
        if doc:
            return doc, "strategy_hash"
    return None, "none"


async def _walk_strategy(
    *,
    idx: int,
    sd: StrategyDoc,
    db,
    dedup_policy: Policy,
) -> ApplyAction:
    """Route a strategy doc to T1 (live library) or T2 (archive)."""
    tier = (sd.provenance.tier_class or "").upper() or None
    target = (
        "strategy_library" if tier == "T1"
        else "strategy_library_archive"
    )

    if tier == "T1":
        canonical, match_kind = await _find_canonical_strategy(
            db, sd.fingerprint, sd.strategy_hash,
        )
    else:
        # T2 archive: independent collection with its own keyspace.
        canonical = await db["strategy_library_archive"].find_one(
            {"fingerprint": sd.fingerprint}
        )
        match_kind = "fingerprint" if canonical else "none"

    outcome = apply_dedup(
        incoming=sd,
        canonical=canonical,
        policy=dedup_policy,
        match_kind=match_kind,
    )

    incoming_doc = sd.model_dump(mode="json")
    if outcome.outcome in ("merge", "replace") and outcome.merged_doc is not None:
        incoming_doc = outcome.merged_doc

    return ApplyAction(
        action_idx=idx,
        target_collection=target,
        dedup_outcome=outcome.outcome,
        match_kind=outcome.match_kind,
        incoming_id=sd.fingerprint,
        canonical_id=outcome.canonical_id,
        tier_class=tier,  # type: ignore[arg-type]
        incoming_doc=incoming_doc,
    )


async def walk(
    *,
    package: PackageReadResult,
    db,
    dedup_policy: Policy = "skip",
) -> List[ApplyAction]:
    """Produce a list of ApplyActions for every row in the package."""
    actions: List[ApplyAction] = []
    idx = 0

    # Strategies (T1 or T2 archive depending on tier_class).
    for sd in package.strategies:
        actions.append(
            await _walk_strategy(
                idx=idx, sd=sd, db=db, dedup_policy=dedup_policy,
            )
        )
        idx += 1

    # T2 lineage rows.
    for me in package.mutation_events:
        actions.append(ApplyAction(
            action_idx=idx,
            target_collection="mutation_events",
            dedup_outcome="fresh_insert",
            match_kind="none",
            incoming_id=str(me.get("event_id") or me.get("variant_fingerprint") or idx),
            tier_class="T2",
            incoming_doc=dict(me),
        ))
        idx += 1
    for ms in package.mutation_stability:
        actions.append(ApplyAction(
            action_idx=idx,
            target_collection="mutation_stability_log",
            dedup_outcome="fresh_insert",
            match_kind="none",
            incoming_id=str(ms.get("variant_fingerprint") or idx),
            tier_class="T2",
            incoming_doc=dict(ms),
        ))
        idx += 1

    # T3 audit rows.
    for lh in package.lifecycle_history:
        actions.append(ApplyAction(
            action_idx=idx,
            target_collection="strategy_lifecycle_history",
            dedup_outcome="fresh_insert",
            match_kind="none",
            incoming_id=str(lh.get("strategy_hash") or idx),
            tier_class="T3",
            incoming_doc={**dict(lh), "imported": True},
        ))
        idx += 1
    for ph in package.performance_history:
        actions.append(ApplyAction(
            action_idx=idx,
            target_collection="strategy_performance_history",
            dedup_outcome="fresh_insert",
            match_kind="none",
            incoming_id=str(ph.get("strategy_hash") or idx),
            tier_class="T3",
            incoming_doc={**dict(ph), "imported": True},
        ))
        idx += 1
    for al in package.alerts:
        actions.append(ApplyAction(
            action_idx=idx,
            target_collection="auto_factory_alert_log",
            dedup_outcome="fresh_insert",
            match_kind="none",
            incoming_id=str(al.get("strategy_hash") or idx),
            tier_class="T3",
            incoming_doc={**dict(al), "imported": True},
        ))
        idx += 1

    return actions
