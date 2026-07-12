"""ASF dedup policy — implements `skip` / `merge` / `replace` per
`ASF_PACKAGE_V1_SPEC.md §13`.

Pure function. Receives an incoming `StrategyDoc` and an optional
canonical Mongo document; returns a `DedupOutcome` describing what the
upserter should do.
"""
from __future__ import annotations

from typing import Literal, Optional

from engines.asf.schema import DedupOutcome, StrategyDoc

Policy = Literal["skip", "merge", "replace"]
MatchKind = Literal["fingerprint", "strategy_hash", "composite", "none"]


def _is_null_or_missing(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def apply_dedup(
    *,
    incoming: StrategyDoc,
    canonical: Optional[dict],
    policy: Policy = "skip",
    match_kind: MatchKind = "none",
) -> DedupOutcome:
    """Decide the dedup outcome for a single incoming strategy.

    Args:
        incoming   — Pydantic StrategyDoc parsed from the package.
        canonical  — Existing strategy_library doc, or None for fresh.
        policy     — operator-chosen behaviour: skip | merge | replace.
        match_kind — fingerprint | strategy_hash | composite | none.

    Behaviour:
        - No canonical row             -> fresh_insert.
        - `policy="skip"` + canonical  -> skip (canonical wins).
        - `policy="merge"` + canonical -> fill only null/missing keys
                                          on canonical from incoming;
                                          never overwrite non-null.
        - `policy="replace"`+canonical -> overwrite, preserving
                                          canonical._id and
                                          provenance.discovered_at.
        - `match_kind="strategy_hash"` (no fingerprint match) ->
          forced "skip" regardless of policy, per spec §13.2.
    """
    if canonical is None:
        return DedupOutcome(
            outcome="fresh_insert",
            match_kind="none",
            canonical_id=None,
        )

    canonical_id = (
        str(canonical.get("_id"))
        if canonical.get("_id") is not None else None
    )

    # Spec §13.2 — strategy_hash-only match alerts the operator and
    # defaults to skip regardless of policy.
    if match_kind == "strategy_hash":
        return DedupOutcome(
            outcome="skip",
            match_kind="strategy_hash",
            canonical_id=canonical_id,
        )

    if policy == "skip":
        return DedupOutcome(
            outcome="skip",
            match_kind=match_kind,
            canonical_id=canonical_id,
        )

    incoming_doc = incoming.model_dump(mode="json")

    if policy == "merge":
        merged = dict(canonical)
        for k, v in incoming_doc.items():
            if k == "_id":
                continue
            if _is_null_or_missing(canonical.get(k)):
                merged[k] = v
        # provenance.discovered_at is preserved on merges by virtue of
        # the canonical value being non-null.
        return DedupOutcome(
            outcome="merge",
            match_kind=match_kind,
            canonical_id=canonical_id,
            merged_doc=merged,
        )

    # policy == "replace"
    replaced = dict(incoming_doc)
    if canonical_id is not None:
        replaced["_id"] = canonical.get("_id")
    canon_prov = canonical.get("provenance") or {}
    discovered = canon_prov.get("discovered_at")
    if discovered:
        prov = dict(replaced.get("provenance") or {})
        prov["discovered_at"] = discovered
        replaced["provenance"] = prov
    return DedupOutcome(
        outcome="replace",
        match_kind=match_kind,
        canonical_id=canonical_id,
        merged_doc=replaced,
    )
