"""Phase 28 telemetry — IR coverage observability.

Pure, read-only, scheduler-independent. Surfaces four operator-facing
signals over the existing ``mutation_events`` stream:

    1. % of new mutations emitted as ``ir_native`` vs ``legacy``
    2. mutation chain-depth distribution (# of accumulated composer
       overlays in the final IR)
    3. legacy fallback counts (root vs composer)
    4. momentum-base fallback counts (the documented IR v1 gap)

Architectural promise:
    * additive only — no edits to lifecycle / orchestrator / scheduler /
      BI5 / backtest / discovery
    * read-only — never writes; aggregates over an existing collection
    * scheduler-independent — no APScheduler jobs, no autonomous ticks;
      the endpoint is computed on-demand against the live collection
    * legacy-safe — events emitted before Phase 28-B++ telemetry
      enrichment (no ``ir_status`` field) bucket as ``unknown`` so the
      historical curve is honest, not fabricated.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── Overlay markers (deterministic heuristic) ────────────────────────
# Each composer that *adds* an indicator declares a stable id. Counting
# how many of these are present in the final IR is a faithful estimator
# of chain depth: a base trend_following IR has none; a base + RSI gate
# has one; a base + RSI + HTF + volatility has three.
#
# Composers that don't add an indicator (``filter_remove_rsi`` and
# ``risk_reward_*``) still represent a mutation-step in the chain, so
# they contribute +1 via the metadata.mutation_type check below.
_OVERLAY_INDICATOR_IDS: frozenset = frozenset({
    "rsi_filter",     # filter_add_rsi
    "ema_trend",      # filter_add_trend
    "atr_filter",     # filter_add_volatility
    "htf_ema_fast",   # mtf_htf_confirmation (pair counts once)
})

_NON_INDICATOR_COMPOSER_PREFIXES: tuple = (
    "risk_reward_",
)

_NON_INDICATOR_COMPOSERS: frozenset = frozenset({
    "filter_remove_rsi",
})

# Legacy-reason buckets — stable strings for distribution counts.
LEGACY_REASON_MOMENTUM = "momentum_base"
LEGACY_REASON_MISSING_TEXT = "missing_strategy_text"
LEGACY_REASON_COMPOSER_NO_BASE_IR = "composer_legacy_base"
LEGACY_REASON_UNSUPPORTED_TYPE = "ir_v1_unsupported"
LEGACY_REASON_ROOT_BUILD_FAILED = "root_build_failed"
LEGACY_REASON_PARAM_EXTRACT_FAILED = "param_extraction_failed"
LEGACY_REASON_UNKNOWN = "unknown"

_KNOWN_LEGACY_REASONS: tuple = (
    LEGACY_REASON_MOMENTUM,
    LEGACY_REASON_MISSING_TEXT,
    LEGACY_REASON_COMPOSER_NO_BASE_IR,
    LEGACY_REASON_UNSUPPORTED_TYPE,
    LEGACY_REASON_ROOT_BUILD_FAILED,
    LEGACY_REASON_PARAM_EXTRACT_FAILED,
    LEGACY_REASON_UNKNOWN,
)

_ROOT_MUTATION_TYPES: frozenset = frozenset({
    "trend_pullback", "session_london_breakout", "session_asian_range",
    "volatility_atr_breakout", "volatility_bollinger_squeeze",
    "mean_reversion_rsi", "mean_reversion_bollinger",
})

_COMPOSER_INDICATOR_TYPES: frozenset = frozenset({
    "filter_add_rsi", "filter_add_volatility", "filter_add_trend",
    "mtf_htf_confirmation", "filter_remove_rsi",
})


# ── Pure helpers ─────────────────────────────────────────────────────

def compute_ir_chain_depth(ir_dict: Optional[Dict[str, Any]]) -> int:
    """Return the count of accumulated composer overlays in the IR.

    Heuristic (intentionally simple — telemetry, not parsing):
        * each declared indicator whose id is in ``_OVERLAY_INDICATOR_IDS``
          counts as +1 overlay (rsi_filter, ema_trend, atr_filter,
          htf_ema_fast — htf_ema_slow is paired and not counted twice)
        * metadata.mutation_type in ``_NON_INDICATOR_COMPOSERS`` or
          starting with a ``_NON_INDICATOR_COMPOSER_PREFIXES`` entry
          counts as +1 overlay (risk_reward_*, filter_remove_rsi)

    Returns 0 for None / non-dict / IRs with no overlays (i.e. a root
    base IR before any composer has been applied). Never raises.
    """
    if not isinstance(ir_dict, dict):
        return 0
    depth = 0
    indicators = ir_dict.get("indicators") or []
    if isinstance(indicators, list):
        declared_ids = {
            i.get("id") for i in indicators
            if isinstance(i, dict) and i.get("id")
        }
        depth += len(declared_ids & _OVERLAY_INDICATOR_IDS)
    md = ir_dict.get("metadata") or {}
    mt = (md.get("mutation_type") or "") if isinstance(md, dict) else ""
    if isinstance(mt, str):
        if mt in _NON_INDICATOR_COMPOSERS:
            depth += 1
        elif any(mt.startswith(p) for p in _NON_INDICATOR_COMPOSER_PREFIXES):
            depth += 1
    return depth


def classify_legacy_reason(
    *,
    mutation_type: str,
    ir_status: str,
    base_strategy_text: Optional[str],
) -> Optional[str]:
    """Bucket a legacy variant into one of the seven stable reason
    strings above. Returns None for ir_native variants. Never raises.

    Used at event-emit time so persisted ``mutation_events`` carry a
    deterministic reason and historical aggregation stays cheap.
    """
    if ir_status == "ir_native":
        return None
    if not isinstance(mutation_type, str):
        return LEGACY_REASON_UNKNOWN
    if not base_strategy_text or not isinstance(base_strategy_text, str):
        return LEGACY_REASON_MISSING_TEXT

    # Attempt the same classifier the mutation engine uses; honest
    # bucket on failure rather than fabricating a result.
    stype: Optional[str] = None
    try:
        from engines.param_extractor import extract_params
        ex = extract_params(base_strategy_text)
        stype = (ex.get("strategy_type") or "").lower() or None
    except Exception:
        return LEGACY_REASON_PARAM_EXTRACT_FAILED

    if stype == "momentum":
        return LEGACY_REASON_MOMENTUM

    if mutation_type in _ROOT_MUTATION_TYPES:
        # Root mutator should always build IR; if it didn't, the
        # builder itself failed (rare — caught defensively).
        return LEGACY_REASON_ROOT_BUILD_FAILED

    if (mutation_type in _COMPOSER_INDICATOR_TYPES
            or any(mutation_type.startswith(p)
                   for p in _NON_INDICATOR_COMPOSER_PREFIXES)):
        # Composer with no derivable base IR (non-momentum, non-empty
        # text) → unusual. Most often this means the base text didn't
        # classify into a v1-supported strategy_type.
        return LEGACY_REASON_COMPOSER_NO_BASE_IR

    return LEGACY_REASON_UNSUPPORTED_TYPE


# ── Aggregation ──────────────────────────────────────────────────────

def summarize_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate a list of mutation_events into IR coverage telemetry.

    Output shape (stable; consumed by /api/mutation/ir-telemetry and
    optionally by an operator-facing panel):

        {
          "total_events": int,
          "ir_native_count": int,
          "legacy_count": int,
          "unknown_count": int,                  # legacy historical
                                                 # rows lacking ir_status
          "ir_native_pct": float|None,           # % of (ir_native + legacy)
          "chain_depth_distribution": {
              "0": int, "1": int, "2": int, "3": int, "4+": int,
          },
          "chain_depth_mean": float|None,
          "legacy_reasons": { reason: count, ... },
          "by_mutation_type": [
              { "type": str, "count": int,
                "ir_native": int, "legacy": int,
                "ir_native_pct": float|None },
              ...
          ],
          "earliest_ts": str|None,
          "latest_ts": str|None,
        }

    Pure function. Never raises. Events missing fields bucket as
    ``unknown`` so historical curves are honest, not retro-fabricated.
    """
    total = 0
    ir_native = 0
    legacy = 0
    unknown = 0
    depth_buckets: Dict[str, int] = {"0": 0, "1": 0, "2": 0, "3": 0, "4+": 0}
    depth_sum = 0
    depth_n = 0
    reasons: Dict[str, int] = {r: 0 for r in _KNOWN_LEGACY_REASONS}
    by_type: Dict[str, Dict[str, int]] = {}
    earliest: Optional[str] = None
    latest: Optional[str] = None

    for e in events or []:
        total += 1
        ir_status = e.get("ir_status")
        mt = e.get("type") or e.get("mutation_type") or "unknown"
        type_row = by_type.setdefault(
            mt, {"count": 0, "ir_native": 0, "legacy": 0}
        )
        type_row["count"] += 1

        if ir_status == "ir_native":
            ir_native += 1
            type_row["ir_native"] += 1
        elif ir_status == "legacy":
            legacy += 1
            type_row["legacy"] += 1
            reason = e.get("legacy_reason") or LEGACY_REASON_UNKNOWN
            if reason not in reasons:
                reasons[reason] = 0
            reasons[reason] += 1
        else:
            unknown += 1

        depth = e.get("ir_chain_depth")
        if isinstance(depth, int) and depth >= 0:
            depth_sum += depth
            depth_n += 1
            if depth >= 4:
                depth_buckets["4+"] += 1
            else:
                depth_buckets[str(depth)] += 1

        ts = e.get("ts")
        if isinstance(ts, str):
            if earliest is None or ts < earliest:
                earliest = ts
            if latest is None or ts > latest:
                latest = ts

    denom = ir_native + legacy
    ir_native_pct = round(100.0 * ir_native / denom, 2) if denom else None
    depth_mean = round(depth_sum / depth_n, 3) if depth_n else None

    by_type_rows: List[Dict[str, Any]] = []
    for mt, r in by_type.items():
        d = r["ir_native"] + r["legacy"]
        by_type_rows.append({
            "type": mt,
            "count": r["count"],
            "ir_native": r["ir_native"],
            "legacy": r["legacy"],
            "ir_native_pct": round(100.0 * r["ir_native"] / d, 2) if d else None,
        })
    by_type_rows.sort(key=lambda x: (-x["count"], x["type"]))

    return {
        "total_events": total,
        "ir_native_count": ir_native,
        "legacy_count": legacy,
        "unknown_count": unknown,
        "ir_native_pct": ir_native_pct,
        "chain_depth_distribution": depth_buckets,
        "chain_depth_mean": depth_mean,
        "legacy_reasons": reasons,
        "by_mutation_type": by_type_rows,
        "earliest_ts": earliest,
        "latest_ts": latest,
    }


async def fetch_ir_telemetry(
    db: Any, *,
    since: Optional[str] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    """Aggregate ``mutation_events`` into an IR-coverage telemetry
    payload. Read-only.

    Args:
        db: motor / pymongo-style async DB handle.
        since: optional ISO-8601 timestamp lower bound (inclusive).
        limit: hard cap on rows scanned (defaults to 5_000, capped at
            50_000 to keep the endpoint bounded under any load).
    """
    limit = max(1, min(int(limit), 50_000))
    q: Dict[str, Any] = {}
    if since:
        q["ts"] = {"$gte": since}
    projection = {
        "_id": 0,
        "type": 1, "ts": 1,
        "ir_status": 1, "ir_chain_depth": 1, "legacy_reason": 1,
    }
    cur = db["mutation_events"].find(q, projection).sort("ts", -1).limit(limit)
    events = [d async for d in cur]
    summary = summarize_events(events)
    summary["query"] = {
        "since": since, "limit": limit,
        "rows_scanned": len(events),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }
    return summary


__all__ = [
    "compute_ir_chain_depth",
    "classify_legacy_reason",
    "summarize_events",
    "fetch_ir_telemetry",
    "LEGACY_REASON_MOMENTUM", "LEGACY_REASON_MISSING_TEXT",
    "LEGACY_REASON_COMPOSER_NO_BASE_IR", "LEGACY_REASON_UNSUPPORTED_TYPE",
    "LEGACY_REASON_ROOT_BUILD_FAILED", "LEGACY_REASON_PARAM_EXTRACT_FAILED",
    "LEGACY_REASON_UNKNOWN",
]
