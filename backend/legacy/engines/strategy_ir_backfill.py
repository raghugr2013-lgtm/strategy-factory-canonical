"""MB-7.2 — Strategy IR back-fill engine.

Persists a validated `strategy_ir` block onto every `strategy_library`
row that does not yet have one. Resolution order, per
`STRATEGY_IR_AUDIT.md §5`:

    1. `mutation_variants` carry-forward — when a mutation_variant
       row exists for the same strategy_hash with
       `ir_status == "ir_native"`, copy its IR.
    2. Canonical builders — when the library row's `strategy_type`
       maps to a known IR root builder, synthesise a fresh IR with
       the library row's `pair` / `timeframe`.
    3. Honest refusal — leave `strategy_ir = null` and stamp
       `ir_status = "legacy"`. The exporter will fall back to the
       deterministic refusal stub for that one member.

Idempotent: re-running the back-fill on the same library is a no-op
(rows that already have a non-null IR are skipped unless `force=True`).

NEVER mutates any field outside `strategy_ir`, `ir_status`,
`ir_version`, and `ir_source` on the library row. No new collection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines.strategy_ir import StrategyIR, is_valid_ir
from engines.strategy_ir_builders import (
    build_mean_reversion_bollinger,
    build_mean_reversion_rsi,
    build_session_asian_range,
    build_session_london_breakout,
    build_trend_pullback,
    build_volatility_atr_breakout,
    build_volatility_bb_squeeze,
)

logger = logging.getLogger(__name__)


# ── strategy_type → canonical builder map ───────────────────────────
#
# The library tags strategies with informal strings (e.g. "bb_squeeze",
# "trend_breakout", "rsi_mean"). The canonical IR builders cover the
# Phase 28-A taxonomy: trend / mean-reversion / session / volatility.
#
# Each library tag is mapped via substring match, in priority order, to
# the most semantically appropriate builder. Anything unmatched →
# honest refusal (no IR persisted).

_TAG_BUILDER_MAP = (
    # tag fragments (lowercased)        builder
    (("bb_squeeze", "squeeze", "bollinger_squeeze"),       build_volatility_bb_squeeze),
    (("atr_breakout", "volatility_breakout"),              build_volatility_atr_breakout),
    (("london", "london_breakout", "session_london"),      build_session_london_breakout),
    (("asian", "asian_range", "session_asian"),            build_session_asian_range),
    (("rsi_mean", "rsi_reversion", "mean_rsi", "rsi"),     build_mean_reversion_rsi),
    (("bollinger_mean", "bb_mean", "mean_bollinger",
      "bollinger_reversion", "bollinger"),                 build_mean_reversion_bollinger),
    (("trend_breakout", "trend_pullback", "ema_pull",
      "ema_trend", "pullback", "trend", "macd_cross"),     build_trend_pullback),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_builder(strategy_type: Optional[str]):
    if not strategy_type:
        return None
    s = str(strategy_type).strip().lower()
    if not s:
        return None
    for fragments, builder in _TAG_BUILDER_MAP:
        if any(frag in s for frag in fragments):
            return builder
    return None


def synth_ir_for_library_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pure helper — given a library row dict, return a JSON-safe IR
    dict, or None when no canonical builder applies."""
    builder = _resolve_builder(row.get("strategy_type"))
    if builder is None:
        return None
    pair = row.get("pair") or "EURUSD"
    tf = row.get("timeframe") or "H1"
    try:
        ir: StrategyIR = builder(pair, tf)
        ir_dict = ir.model_dump(mode="json")
        # Round-trip-validate so we never persist a broken IR.
        if not is_valid_ir(ir_dict):
            return None
        return ir_dict
    except Exception:                                          # pragma: no cover
        logger.exception(
            "strategy_ir_backfill: builder failed for %s/%s/%s",
            row.get("strategy_type"), pair, tf,
        )
        return None


async def _carry_forward_from_mutation_variant(
    strategy_hash: str,
) -> Optional[Dict[str, Any]]:
    """If a mutation_variant row exists with ir_status='ir_native' for
    this hash, return its strategy_ir dict. Otherwise None."""
    db = get_db()
    cur = db["mutation_variants"].find(
        {"strategy_hash": strategy_hash,
         "ir_status": "ir_native",
         "strategy_ir": {"$ne": None}},
        {"_id": 0, "strategy_ir": 1, "ir_version": 1},
    ).limit(1)
    async for doc in cur:
        ir = doc.get("strategy_ir")
        if isinstance(ir, dict) and is_valid_ir(ir):
            return ir
    return None


async def coverage_stats() -> Dict[str, Any]:
    """Snapshot of current IR coverage across the library."""
    db = get_db()
    total = await db["strategy_library"].count_documents({})
    with_ir = await db["strategy_library"].count_documents(
        {"strategy_ir": {"$ne": None, "$exists": True}},
    )
    without_ir = total - with_ir
    # Break down by source.
    by_source: Dict[str, int] = {}
    cur = db["strategy_library"].find(
        {"strategy_ir": {"$ne": None, "$exists": True}},
        {"_id": 0, "ir_source": 1, "ir_version": 1},
    )
    async for d in cur:
        src = d.get("ir_source") or "unknown"
        by_source[src] = by_source.get(src, 0) + 1
    # Type breakdown for transparency.
    types: Dict[str, Dict[str, int]] = {}
    cur = db["strategy_library"].find(
        {}, {"_id": 0, "strategy_type": 1, "strategy_ir": 1},
    )
    async for d in cur:
        t = d.get("strategy_type") or "(unknown)"
        slot = types.setdefault(t, {"total": 0, "with_ir": 0})
        slot["total"] += 1
        if d.get("strategy_ir"):
            slot["with_ir"] += 1
    return {
        "total":          total,
        "with_ir":        with_ir,
        "without_ir":     without_ir,
        "coverage_pct":   round(100.0 * with_ir / (total or 1), 2),
        "by_ir_source":   by_source,
        "by_strategy_type": types,
        "computed_at":    _now_iso(),
    }


async def backfill_library(
    *,
    force: bool = False,
    actor: str = "system",
) -> Dict[str, Any]:
    """Apply the back-fill across the whole `strategy_library`.

    Returns a structured report:
      {
        "total":             5,
        "before":            { coverage_pct: 0.0, ... },
        "after":             { coverage_pct: 80.0, ... },
        "updated":           [ { strategy_hash, source, builder }, ... ],
        "refused":           [ { strategy_hash, strategy_type, reason }, ... ],
        "skipped_existing":  [ ... ],   # only when force=False
      }
    """
    db = get_db()
    before = await coverage_stats()

    cur = db["strategy_library"].find(
        {} if force
        else {"$or": [
            {"strategy_ir": None},
            {"strategy_ir": {"$exists": False}},
        ]},
        {"_id": 0},
    )
    rows = [d async for d in cur]

    updated: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for row in rows:
        h = row.get("strategy_hash")
        if not h:
            continue
        if (not force) and row.get("strategy_ir"):
            skipped.append({"strategy_hash": h, "reason": "already has IR"})
            continue
        # 1) mutation_variant carry-forward
        ir = await _carry_forward_from_mutation_variant(h)
        source = "mutation_variant" if ir is not None else None
        # 2) canonical synth
        if ir is None:
            ir = synth_ir_for_library_row(row)
            if ir is not None:
                source = "canonical_builder"
        # 3) honest refusal
        if ir is None:
            refused.append({
                "strategy_hash": h,
                "strategy_type": row.get("strategy_type"),
                "pair":          row.get("pair"),
                "timeframe":     row.get("timeframe"),
                "reason":        "no canonical builder for strategy_type",
            })
            continue

        await db["strategy_library"].update_one(
            {"strategy_hash": h},
            {"$set": {
                "strategy_ir":  ir,
                "ir_version":   int(ir.get("ir_version") or 1),
                "ir_status":    "ir_native",
                "ir_source":    source,
                "ir_backfilled_at": _now_iso(),
                "ir_backfilled_by": actor,
            }},
        )
        updated.append({
            "strategy_hash": h,
            "strategy_type": row.get("strategy_type"),
            "ir_source":     source,
        })

    after = await coverage_stats()
    return {
        "total":            len(rows),
        "before":           before,
        "after":            after,
        "updated":          updated,
        "refused":          refused,
        "skipped_existing": skipped,
        "actor":            actor,
        "ran_at":           _now_iso(),
    }


async def get_ir_for_hash(strategy_hash: str) -> Optional[Dict[str, Any]]:
    """One-shot lookup, used by the candidate-pool enricher and the
    member-add snapshot writer. Returns the validated IR dict or
    None. Reads library first, then mutation_variants as a fallback
    (covers strategies that survived without ever being promoted into
    the library)."""
    if not strategy_hash:
        return None
    db = get_db()
    row = await db["strategy_library"].find_one(
        {"strategy_hash": strategy_hash},
        {"_id": 0, "strategy_ir": 1},
    )
    if row and isinstance(row.get("strategy_ir"), dict) and is_valid_ir(row["strategy_ir"]):
        return row["strategy_ir"]
    # Library miss → check mutation_variants.
    return await _carry_forward_from_mutation_variant(strategy_hash)
