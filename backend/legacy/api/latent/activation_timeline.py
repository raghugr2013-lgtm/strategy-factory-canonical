"""GET /api/latent/activation-timeline — read-only forensic surface.

Returns the most recent `latent_capability:override_diff` audit_log
rows projected to the institutional governance fields. Pure read;
auth-gated; never mutates anything.

Companion endpoint:
    GET /api/latent/activation-timeline/summary
        Server-side aggregation over the same audit_log rows,
        returning per-flag {first_seen, last_seen, total_transitions,
        n_added_events, n_removed_events, n_changed_events}. Used by
        operators to assess governance volatility / feature churn /
        long-run dormant stability without scanning raw timelines.

Discipline:
    * Read-only
    * Auth-gated (mirrors every other /api/latent/* endpoint)
    * Observational-only — zero scheduler / orchestration interaction
    * Zero authority — no flag mutation, no activation capability
    * Aggregation-only — no derived governance decision, no scoring
    * No side effects beyond Mongo `find` + `aggregate`
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query

from auth_utils import get_current_user
from engines.db import get_db

router = APIRouter()

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
MAX_SUMMARY_FLAGS = 200


@router.get("/latent/activation-timeline")
async def get_activation_timeline(
    _user: Dict[str, Any] = Depends(get_current_user),
    limit: int = Query(
        default=DEFAULT_LIMIT,
        ge=1,
        le=MAX_LIMIT,
        description=(
            "Maximum number of override_diff rows to return (newest "
            f"first). Bounded at {MAX_LIMIT}."
        ),
    ),
    source: str | None = Query(
        default=None,
        max_length=60,
        description=(
            "Optional case-sensitive `source` filter "
            "(e.g. `server`, `factory_runner`). Omit for all sources."
        ),
    ),
) -> Dict[str, Any]:
    """Return the latest `latent_capability:override_diff` events.

    Each row exposes the activation transition surface only:
        ts                  — ISO timestamp the diff was written
        source              — process identifier (`server`, `factory_runner`, …)
        process_pid         — emitting process PID
        added               — flags newly overridden vs prior boot
        removed             — flags returned to dormant vs prior boot
        changed             — flags whose value mutated  ({from, to})
        n_added/n_removed/n_changed   — counts of each bucket
        previous_boot_ts    — ts of the prior boot_state used as baseline
        previous_boot_source — source of that prior boot_state
        previous_boot_pid   — pid of that prior boot_state

    Steady-state boots emit NO row, so this timeline contains ONLY
    transitions. Suitable for operator queries such as
    "when did ENABLE_RISK_OF_RUIN first go live?".
    """
    query: Dict[str, Any] = {"event": "latent_capability:override_diff"}
    if source:
        query["source"] = source

    projection = {
        "_id":                   0,
        "ts":                    1,
        "source":                1,
        "process_pid":           1,
        "added":                 1,
        "removed":               1,
        "changed":               1,
        "n_added":               1,
        "n_removed":             1,
        "n_changed":             1,
        "previous_boot_ts":      1,
        "previous_boot_source":  1,
        "previous_boot_pid":     1,
    }

    db = get_db()
    cur = (
        db["audit_log"]
        .find(query, projection)
        .sort("ts_dt", -1)
        .limit(limit)
    )
    rows: List[Dict[str, Any]] = [doc async for doc in cur]

    return {
        "count":  len(rows),
        "limit":  limit,
        "source": source,
        "events": rows,
    }



def _iso(dt: Any) -> str | None:
    """Best-effort BSON Date → ISO-8601 string. Returns None on
    unexpected types so the response stays JSON-serialisable."""
    if isinstance(dt, datetime):
        return dt.isoformat()
    return None


# Smallest representable denominator (1 second expressed in days) so
# that `churn_score = total_transitions / days_since_first_seen` stays
# finite even when first_seen and "now" collapse to the same instant
# (e.g. the very first transition this session). NOT a threshold — no
# operator-facing meaning is attached to it; it only prevents the
# arithmetic from producing inf / NaN.
_DAY_FLOOR_SECONDS = 1.0 / 86400.0


def _days_between(then: Any, now: datetime) -> float | None:
    """Return non-negative float days between `then` (BSON Date /
    datetime) and `now`. Returns None when `then` is unusable so the
    field appears as null in the JSON response."""
    if not isinstance(then, datetime):
        return None
    # Mongo strips tzinfo on read; normalise to UTC for comparison.
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    delta_seconds = (now - then).total_seconds()
    # Clamp negative (clock skew / future-dated row) to 0 — we report
    # observed-history math, not predictions.
    if delta_seconds < 0:
        delta_seconds = 0.0
    return round(delta_seconds / 86400.0, 6)


@router.get("/latent/activation-timeline/summary")
async def get_activation_timeline_summary(
    _user: Dict[str, Any] = Depends(get_current_user),
    source: str | None = Query(
        default=None,
        max_length=60,
        description=(
            "Optional case-sensitive `source` filter (e.g. `server`, "
            "`factory_runner`). Omit to aggregate across all sources."
        ),
    ),
    limit: int = Query(
        default=MAX_SUMMARY_FLAGS,
        ge=1,
        le=MAX_SUMMARY_FLAGS,
        description=(
            "Maximum number of flag rows to return (sorted by "
            f"total_transitions desc). Bounded at {MAX_SUMMARY_FLAGS}."
        ),
    ),
) -> Dict[str, Any]:
    """Per-flag governance-volatility summary.

    Aggregates over `latent_capability:override_diff` rows in
    `audit_log` and emits one record per flag that has ever appeared
    in any transition bucket. Schema:

        flag                  — the flag name
        first_seen            — ISO ts of the earliest transition row
                                that mentions the flag
        last_seen             — ISO ts of the latest transition row
                                that mentions the flag
        total_transitions     — number of transition rows that mentioned
                                the flag in ANY bucket
        n_added_events        — subset where flag was in `added`
        n_removed_events      — subset where flag was in `removed`
        n_changed_events      — subset where flag was in `changed`

    Derived dormancy / churn fields (purely arithmetic; NO thresholds,
    NO recommendations, NO governance authority — they exist only so
    the operator can quickly distinguish recency from stability):

        days_dormant          — float days between `last_seen` and now
                                (UTC). Always ≥ 0.
        days_since_first_seen — float days between `first_seen` and
                                now (UTC). Always ≥ 0.
        churn_score           — total_transitions / max(
                                days_since_first_seen, 1s-in-days
                                ). The 1-second floor keeps the
                                arithmetic finite for sub-second-old
                                first_seen values; it carries NO
                                operator-facing meaning.

    Sort order: `total_transitions desc, flag asc` — the most volatile
    governance items surface first. Steady-state boots contribute
    zero rows (only TRANSITIONS are aggregated), so a dormant flag
    that has never flipped will NOT appear here. This is intentional
    — the endpoint reports HISTORY, not the live manifest. Use
    `/api/latent/feature-flags` for the live dormancy state.
    """
    match: Dict[str, Any] = {"event": "latent_capability:override_diff"}
    if source:
        match["source"] = source

    pipeline: List[Dict[str, Any]] = [
        {"$match": match},
        {
            "$project": {
                "ts_dt": 1,
                "events": {
                    "$concatArrays": [
                        {
                            "$map": {
                                "input": {
                                    "$objectToArray": {
                                        "$ifNull": ["$added", {}],
                                    },
                                },
                                "as":   "e",
                                "in":   {"flag": "$$e.k", "bucket": "added"},
                            },
                        },
                        {
                            "$map": {
                                "input": {
                                    "$objectToArray": {
                                        "$ifNull": ["$removed", {}],
                                    },
                                },
                                "as":   "e",
                                "in":   {"flag": "$$e.k", "bucket": "removed"},
                            },
                        },
                        {
                            "$map": {
                                "input": {
                                    "$objectToArray": {
                                        "$ifNull": ["$changed", {}],
                                    },
                                },
                                "as":   "e",
                                "in":   {"flag": "$$e.k", "bucket": "changed"},
                            },
                        },
                    ],
                },
            },
        },
        {"$unwind": "$events"},
        {
            "$group": {
                "_id":               "$events.flag",
                "first_seen_dt":     {"$min": "$ts_dt"},
                "last_seen_dt":      {"$max": "$ts_dt"},
                "total_transitions": {"$sum": 1},
                "n_added_events": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$events.bucket", "added"]}, 1, 0,
                        ],
                    },
                },
                "n_removed_events": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$events.bucket", "removed"]}, 1, 0,
                        ],
                    },
                },
                "n_changed_events": {
                    "$sum": {
                        "$cond": [
                            {"$eq": ["$events.bucket", "changed"]}, 1, 0,
                        ],
                    },
                },
            },
        },
        {"$sort": {"total_transitions": -1, "_id": 1}},
        {"$limit": limit},
    ]

    rows: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    async for doc in get_db()["audit_log"].aggregate(pipeline):
        first_seen_dt = doc.get("first_seen_dt")
        last_seen_dt = doc.get("last_seen_dt")
        total_transitions = int(doc.get("total_transitions") or 0)
        days_dormant = _days_between(last_seen_dt, now)
        days_since_first_seen = _days_between(first_seen_dt, now)
        if days_since_first_seen is None:
            churn_score = None
        else:
            denom = max(days_since_first_seen, _DAY_FLOOR_SECONDS)
            churn_score = round(total_transitions / denom, 6)
        rows.append(
            {
                "flag":                  doc["_id"],
                "first_seen":            _iso(first_seen_dt),
                "last_seen":             _iso(last_seen_dt),
                "total_transitions":     total_transitions,
                "n_added_events":        int(doc.get("n_added_events") or 0),
                "n_removed_events":      int(doc.get("n_removed_events") or 0),
                "n_changed_events":      int(doc.get("n_changed_events") or 0),
                "days_dormant":          days_dormant,
                "days_since_first_seen": days_since_first_seen,
                "churn_score":           churn_score,
            }
        )

    return {
        "count":  len(rows),
        "limit":  limit,
        "source": source,
        "flags":  rows,
    }
