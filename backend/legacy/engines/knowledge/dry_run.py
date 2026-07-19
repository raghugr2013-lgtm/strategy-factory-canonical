"""Phase 2 Stage 3.β — dry-run harness.

Runs the full UKIE pipeline in shadow mode: every stage executes, but
the repository write is bypassed regardless of the
`UKIE_GOVERNANCE_CUTOVER` flag. The output is a `PipelineSummary` with
per-item outcomes + aggregate tallies.

Three input sources supported per operator directive (2026-02-19):

  1. `items=[…]`                         — explicit list of `RawKnowledgeItem`
                                            or dicts (converted).
  2. `last_n_from_ingestion_runs=N`      — replay from Mongo:
                                            reads N most recent rows
                                            from `strategy_knowledge_base.ingestion_runs`
                                            and reconstructs items.
  3. `synthetic_fixture=<name>`          — deterministic fixture set
                                            defined in this module.

All three may be combined; the harness concatenates them in the order
listed above.

Called from:
  * The router (`POST /api/knowledge/dry-run`) — admin gated.
  * CLI / operator scripts via the `run_dry()` fn.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .connector import RawKnowledgeItem, now_iso
from .constants import KNOWLEDGE_DB_NAME
from .domains import KnowledgeDomain
from .pipeline import PipelineSummary, run_batch, set_last_summary

logger = logging.getLogger(__name__)


# ── Synthetic fixtures (deterministic) ───────────────────────────────

def _fixture_stage_3_beta_default() -> List[RawKnowledgeItem]:
    """Small deterministic corpus — used by regression tests + the
    default `POST /api/knowledge/dry-run` invocation.

    Covers:
      * Every KnowledgeDomain (6 items minimum)
      * PERMISSIVE / WEAK_COPYLEFT / STRONG_COPYLEFT / PROPRIETARY / UNKNOWN
      * A within-domain hash collision candidate (so dedup fires)
    """
    ts = "2026-02-19T00:00:00+00:00"
    corpus: List[RawKnowledgeItem] = []

    def _mk(
        domain: KnowledgeDomain,
        body: bytes,
        *,
        connector: str = "github",
        license_: Optional[str] = None,
        extras: Optional[Dict[str, Any]] = None,
        source_ref: str = "abc123",
    ) -> RawKnowledgeItem:
        digest = hashlib.sha256(body).hexdigest()
        return RawKnowledgeItem(
            domain=domain,
            connector_name=connector,
            source_url=f"https://example.com/{domain.value}/{source_ref}",
            source_ref=source_ref,
            content_hash=f"sha256:{digest}",
            fetched_at=ts,
            content_bytes=body,
            content_mime="text/plain",
            license=license_,
            license_confidence=0.0,
            author="fixture",
            extras=extras or {},
        )

    corpus.append(_mk(KnowledgeDomain.STRATEGY,   b"//@version=5\nstrategy('MIT MA cross')",
                       license_="MIT", source_ref="s-mit"))
    corpus.append(_mk(KnowledgeDomain.RESEARCH,   b"MIT-licensed research paper on regime detection.",
                       license_="MIT", extras={"citations": 120, "parser_confidence": 0.95},
                       source_ref="r-mit"))
    corpus.append(_mk(KnowledgeDomain.INDICATOR,  b"Apache 2.0 licensed RSI indicator",
                       license_="Apache-2.0", source_ref="i-apache"))
    corpus.append(_mk(KnowledgeDomain.MARKET,     b"Market note. Content covered by GPL-3.0 licence.",
                       license_="GPL-3.0", source_ref="m-gpl"))
    corpus.append(_mk(KnowledgeDomain.EXECUTION,  b"Proprietary broker rules. All rights reserved.",
                       license_=None, source_ref="e-prop"))
    corpus.append(_mk(KnowledgeDomain.INTERNAL_HISTORY,
                       b"Internal mirror of strategy_id=abc - no license attached.",
                       connector="internal_mongo", source_ref="ih-none"))
    # Within-domain collision candidate — same bytes / domain, second insert
    corpus.append(_mk(KnowledgeDomain.STRATEGY,   b"//@version=5\nstrategy('MIT MA cross')",
                       license_="MIT", source_ref="s-mit-dup"))
    return corpus


_FIXTURES = {
    "stage_3_beta_default": _fixture_stage_3_beta_default,
}


def synthetic_fixture(name: str) -> List[RawKnowledgeItem]:
    """Return a deterministic fixture corpus by name. Empty when unknown."""
    fn = _FIXTURES.get(name)
    return fn() if fn else []


# ── Item coercion ────────────────────────────────────────────────────

def _coerce_item(x: Any) -> Optional[RawKnowledgeItem]:
    """Accept a `RawKnowledgeItem`, a dict, or None. Returns None on
    unrecognised shape."""
    if x is None:
        return None
    if isinstance(x, RawKnowledgeItem):
        return x
    if isinstance(x, dict):
        try:
            dom_raw = x.get("domain") or ""
            dom = KnowledgeDomain(dom_raw) if not isinstance(dom_raw, KnowledgeDomain) else dom_raw
        except (ValueError, KeyError):
            logger.debug("[dry_run] unknown domain in dict item: %r", x.get("domain"))
            return None
        payload = x.get("content_bytes")
        if isinstance(payload, str):
            payload = payload.encode("utf-8", errors="replace")
        return RawKnowledgeItem(
            domain=dom,
            connector_name=str(x.get("connector_name") or "unknown"),
            source_url=str(x.get("source_url") or ""),
            source_ref=str(x.get("source_ref") or ""),
            content_hash=str(x.get("content_hash") or ""),
            fetched_at=str(x.get("fetched_at") or now_iso()),
            content_bytes=payload,
            content_mime=x.get("content_mime"),
            license=x.get("license"),
            license_confidence=float(x.get("license_confidence") or 0.0),
            author=x.get("author"),
            extras=x.get("extras") or {},
        )
    return None


# ── Mongo replay ─────────────────────────────────────────────────────

async def _replay_from_ingestion_runs(n: int, db_getter=None) -> List[RawKnowledgeItem]:
    """Best-effort reconstruction of items from the last N ingestion
    runs recorded in `strategy_knowledge_base.ingestion_runs`.

    The Stage-3.α surface does not yet write to this collection — this
    replay path returns an empty list gracefully until Stage 3.β lands
    the write. Also fail-open on Mongo issues.
    """
    if n <= 0:
        return []
    try:
        if db_getter is not None:
            db = db_getter()
        else:
            from engines.db import get_db
            db = get_db().client[KNOWLEDGE_DB_NAME]
    except Exception as e:                                    # pragma: no cover
        logger.debug("[dry_run] replay DB unavailable: %s", e)
        return []
    try:
        cur = db["ingestion_runs"].find({}, sort=[("finished_at", -1)]).limit(int(n))
        rows = [d async for d in cur]
    except Exception as e:                                    # noqa: BLE001
        logger.debug("[dry_run] replay query failed: %s", e)
        return []
    out: List[RawKnowledgeItem] = []
    for row in rows:
        raw_items = row.get("items") or row.get("outcomes") or []
        for r in raw_items:
            it = _coerce_item(r)
            if it is not None:
                out.append(it)
    return out


# ── Public entry point ───────────────────────────────────────────────

async def run_dry(
    *,
    items:                       Optional[Sequence[Any]]     = None,
    last_n_from_ingestion_runs:  int                         = 0,
    synthetic_fixture_name:      Optional[str]               = None,
    db_getter=None,
) -> PipelineSummary:
    """Run the pipeline in shadow mode over the concatenated corpus.

    Order of concatenation: `items` → `synthetic_fixture` → `replay`.
    """
    corpus: List[RawKnowledgeItem] = []
    if items:
        for x in items:
            it = _coerce_item(x)
            if it is not None:
                corpus.append(it)
    if synthetic_fixture_name:
        corpus.extend(synthetic_fixture(synthetic_fixture_name))
    if last_n_from_ingestion_runs and last_n_from_ingestion_runs > 0:
        corpus.extend(await _replay_from_ingestion_runs(last_n_from_ingestion_runs, db_getter=db_getter))
    summary = await run_batch(corpus, dry_run=True)
    set_last_summary(summary)
    return summary
