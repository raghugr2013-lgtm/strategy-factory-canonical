"""
Phase 1+2 scaffolding — Widening history (READ-ONLY forensic audit).

Reconstructs a chronological record of every governance widening event
from the institutional `audit_log` surface. For each event we pair the
override diff with the activation stage transition it represents AND a
bounded 24-hour pre-window of orchestration context.

Discipline:
  * Strictly READ-ONLY. No writes, no env mutation, no scheduler
    interaction, no flag mutation, no automatic activation.
  * Forensic. Reconstructs what HAPPENED, never what should happen now.
  * Pure aggregation over collections that already persist independently.
  * Per-row context enrichment is best-effort and isolated; a probe
    failure on one row never masks the others.
  * Honest gaps: env-only flags (e.g. ``USE_PROCESS_POOL``) are NOT
    written into `audit_log.boot_state.active_overrides`, so historical
    stage detection for those markers is best-effort — the response
    surfaces this fact verbatim rather than hallucinating accuracy.

Public surface:
  build_history(limit=50, since=None, source=None, include_boot_states=False)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines.safe_to_widen import stage_from_active_overrides

logger = logging.getLogger(__name__)

# Default + bounded windows.
DEFAULT_LIMIT = 50
MAX_LIMIT = 500
CONTEXT_WINDOW_HOURS = 24


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Any) -> Optional[str]:
    """Best-effort BSON Date / datetime → ISO-8601 string."""
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return None


async def _prior_boot_state(
    db, *, before_dt: datetime, source: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Most recent `latent_capability:boot_state` row strictly before
    `before_dt`. Honours an optional source filter."""
    query: Dict[str, Any] = {
        "event":  "latent_capability:boot_state",
        "ts_dt":  {"$lt": before_dt},
    }
    if source:
        query["source"] = source
    return await db["audit_log"].find_one(
        query,
        {
            "_id": 0, "ts": 1, "ts_dt": 1, "source": 1, "process_pid": 1,
            "flag_count": 1, "overridden_count": 1, "all_dormant": 1,
            "active_overrides": 1, "scopes": 1,
        },
        sort=[("ts_dt", -1)],
    )


async def _factory_runner_alive_during(
    db, *, start_dt: datetime, end_dt: datetime,
) -> Dict[str, Any]:
    """Whether ANY `factory_runner:*` audit row was emitted in the
    window. Used to answer "was the sibling alive at the moment of
    this widening?".

    Returns:
        {
          "seen":  bool,
          "first_ts": iso | None,
          "last_ts":  iso | None,
          "count":  int,
        }
    """
    try:
        cursor = db["audit_log"].find(
            {
                "event": {"$regex": r"^factory_runner:"},
                "ts_dt": {"$gte": start_dt, "$lte": end_dt},
            },
            {"_id": 0, "ts": 1, "ts_dt": 1},
        )
        rows: List[Dict[str, Any]] = [d async for d in cursor]
        if not rows:
            return {"seen": False, "first_ts": None, "last_ts": None, "count": 0}
        rows.sort(key=lambda r: r.get("ts_dt") or datetime.min)
        return {
            "seen":     True,
            "first_ts": _iso(rows[0].get("ts_dt")),
            "last_ts":  _iso(rows[-1].get("ts_dt")),
            "count":    len(rows),
        }
    except Exception as e:                                   # pragma: no cover
        logger.debug("[widening_history] factory_runner_alive_during failed: %s", e)
        return {"seen": False, "first_ts": None, "last_ts": None, "count": 0,
                "error": str(e)[:200]}


async def _context_window(
    db, *, end_dt: datetime, hours: int = CONTEXT_WINDOW_HOURS,
) -> Dict[str, Any]:
    """24-hour-pre-window context snapshot for a widening event.

    Pulls cheap aggregate counts from collections we already maintain.
    Each probe is wrapped so one Mongo hiccup cannot crash the response.
    """
    start_dt = end_dt - timedelta(hours=int(hours))
    out: Dict[str, Any] = {
        "window_hours":  int(hours),
        "window_start":  _iso(start_dt),
        "window_end":    _iso(end_dt),
    }

    # auto_run_cycles in the window — count + error count.
    try:
        start_iso = start_dt.isoformat()
        end_iso   = end_dt.isoformat()
        n_total = await db["auto_run_cycles"].count_documents({
            "finished_at": {"$gte": start_iso, "$lte": end_iso},
        })
        n_err = await db["auto_run_cycles"].count_documents({
            "finished_at": {"$gte": start_iso, "$lte": end_iso},
            "status": {"$in": ["error", "timeout"]},
        })
        out["auto_cycles"] = {
            "total":      int(n_total),
            "errors":     int(n_err),
            "error_rate": round(n_err / n_total, 3) if n_total > 0 else None,
        }
    except Exception as e:                                   # pragma: no cover
        out["auto_cycles"] = {"error": str(e)[:200]}

    # multi_cycle_runs that started in the window.
    try:
        start_iso = start_dt.isoformat()
        end_iso   = end_dt.isoformat()
        n_mc = await db["multi_cycle_runs"].count_documents({
            "started_at": {"$gte": start_iso, "$lte": end_iso},
        })
        n_mc_err = await db["multi_cycle_runs"].count_documents({
            "started_at": {"$gte": start_iso, "$lte": end_iso},
            "status": {"$in": ["error", "stopped"]},
        })
        out["multi_cycle_runs"] = {"total": int(n_mc), "non_clean": int(n_mc_err)}
    except Exception as e:                                   # pragma: no cover
        out["multi_cycle_runs"] = {"error": str(e)[:200]}

    # Lifecycle transitions in the window.
    try:
        start_iso = start_dt.isoformat()
        end_iso   = end_dt.isoformat()
        n_lc = await db["strategy_lifecycle_history"].count_documents({
            "transition_at": {"$gte": start_iso, "$lte": end_iso},
        })
        out["lifecycle_transitions"] = {"total": int(n_lc)}
    except Exception as e:                                   # pragma: no cover
        out["lifecycle_transitions"] = {"error": str(e)[:200]}

    # factory_runner liveness in the window.
    out["factory_runner_window"] = await _factory_runner_alive_during(
        db, start_dt=start_dt, end_dt=end_dt,
    )
    return out


async def _governance_universe_changes(
    db, *, since: Optional[datetime] = None, limit: int = 50,
) -> List[Dict[str, Any]]:
    """Pull the operator-decreed universe audit_log array. Each row
    documents one `save_universe()` call with `{ts, by, change}`."""
    try:
        doc = await db["governance_universe"].find_one(
            {"_id": "config"},
            {"_id": 0, "audit_log": 1},
        )
        rows = (doc or {}).get("audit_log") or []
        if since:
            since_iso = since.isoformat()
            rows = [r for r in rows if (r.get("ts") or "") >= since_iso]
        # Newest first.
        rows.sort(key=lambda r: r.get("ts") or "", reverse=True)
        return rows[: int(limit)]
    except Exception as e:                                   # pragma: no cover
        logger.debug("[widening_history] universe audit fetch failed: %s", e)
        return []


def _summarise_diff(diff_row: Dict[str, Any]) -> Dict[str, Any]:
    """Compact summary of the diff buckets for the timeline entry."""
    added   = diff_row.get("added")   or {}
    removed = diff_row.get("removed") or {}
    changed = diff_row.get("changed") or {}
    return {
        "n_added":   int(diff_row.get("n_added")   or len(added)),
        "n_removed": int(diff_row.get("n_removed") or len(removed)),
        "n_changed": int(diff_row.get("n_changed") or len(changed)),
        "added":     added,
        "removed":   removed,
        "changed":   changed,
    }


def _post_diff_overrides(
    prior_overrides: Dict[str, Any], diff: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply the diff to the prior active-overrides dict to reconstruct
    the post-widening active-overrides set."""
    out = dict(prior_overrides or {})
    for k, v in (diff.get("added") or {}).items():
        out[k] = v
    for k in (diff.get("removed") or {}).keys():
        out.pop(k, None)
    for k, change in (diff.get("changed") or {}).items():
        if isinstance(change, dict) and "to" in change:
            out[k] = change["to"]
    return out


async def build_history(
    *,
    limit: int = DEFAULT_LIMIT,
    since: Optional[datetime] = None,
    source: Optional[str] = None,
    include_boot_states: bool = False,
    include_context: bool = True,
    include_universe: bool = True,
) -> Dict[str, Any]:
    """Build the forensic widening history payload. Never raises."""
    limit = max(1, min(int(limit), MAX_LIMIT))
    db = get_db()

    # ── Override-diff rows (the canonical "widening events"). ────
    match: Dict[str, Any] = {"event": "latent_capability:override_diff"}
    if source:
        match["source"] = source
    if since is not None:
        match["ts_dt"] = {"$gte": since}

    projection = {
        "_id": 0, "ts": 1, "ts_dt": 1, "source": 1, "process_pid": 1,
        "added": 1, "removed": 1, "changed": 1,
        "n_added": 1, "n_removed": 1, "n_changed": 1,
        "previous_boot_ts": 1, "previous_boot_source": 1, "previous_boot_pid": 1,
    }

    diff_rows: List[Dict[str, Any]] = []
    try:
        cur = (
            db["audit_log"]
            .find(match, projection)
            .sort("ts_dt", -1)
            .limit(limit)
        )
        async for d in cur:
            diff_rows.append(d)
    except Exception as e:                                   # pragma: no cover
        logger.debug("[widening_history] override_diff fetch failed: %s", e)

    # ── Enrich each diff with stage transition + context window. ──
    events: List[Dict[str, Any]] = []
    for row in diff_rows:
        ts_dt = row.get("ts_dt")
        if not isinstance(ts_dt, datetime):
            continue
        if ts_dt.tzinfo is None:
            ts_dt = ts_dt.replace(tzinfo=timezone.utc)

        diff = _summarise_diff(row)

        # Prior boot_state → prior overrides.
        prior_boot = await _prior_boot_state(db, before_dt=ts_dt)
        prior_overrides = (prior_boot or {}).get("active_overrides") or {}

        # Was factory_runner observed at any time BEFORE this widening?
        # (Stage S0 marker for historical detection.)
        try:
            fr_before = await db["audit_log"].find_one(
                {
                    "event": {"$regex": r"^factory_runner:"},
                    "ts_dt": {"$lt": ts_dt},
                },
                {"_id": 0, "ts": 1},
            )
            fr_seen_before = bool(fr_before)
        except Exception:                                    # pragma: no cover
            fr_seen_before = False

        post_overrides = _post_diff_overrides(prior_overrides, diff)
        # Stage detection: factory_runner_seen toggles S0; the registry
        # overrides drive S2–S9. S1 (USE_PROCESS_POOL) is env-only and
        # NOT in active_overrides — best-effort, see disclaimer below.
        stage_before, _ = stage_from_active_overrides(
            prior_overrides, factory_runner_seen=fr_seen_before,
        )
        stage_after, stage_next = stage_from_active_overrides(
            post_overrides, factory_runner_seen=fr_seen_before,
        )

        entry: Dict[str, Any] = {
            "ts":            _iso(ts_dt),
            "event":         "override_diff",
            "source":        row.get("source"),
            "process_pid":   row.get("process_pid"),
            "diff":          diff,
            "prior_boot": {
                "ts":              _iso((prior_boot or {}).get("ts_dt"))
                                   or (prior_boot or {}).get("ts"),
                "source":          (prior_boot or {}).get("source"),
                "process_pid":     (prior_boot or {}).get("process_pid"),
                "flag_count":      (prior_boot or {}).get("flag_count"),
                "overridden_count": (prior_boot or {}).get("overridden_count"),
                "all_dormant":     (prior_boot or {}).get("all_dormant"),
                "active_overrides": prior_overrides,
            },
            "post_active_overrides": post_overrides,
            "stage_transition": {
                "before": stage_before,
                "after":  stage_after,
                "next":   stage_next,
                "advanced": stage_before != stage_after,
            },
            "previous_boot_ts":     row.get("previous_boot_ts"),
            "previous_boot_source": row.get("previous_boot_source"),
            "previous_boot_pid":    row.get("previous_boot_pid"),
        }

        if include_context:
            entry["context_24h_before"] = await _context_window(
                db, end_dt=ts_dt, hours=CONTEXT_WINDOW_HOURS,
            )

        events.append(entry)

    out: Dict[str, Any] = {
        "ts":                 _now().isoformat(),
        "read_only":          True,
        "governance_authority": False,
        "operator_authority": "final",
        "phase":              "scaffolding-1",
        "filters": {
            "limit":               limit,
            "since":               _iso(since),
            "source":              source,
            "include_boot_states": bool(include_boot_states),
            "include_context":     bool(include_context),
            "include_universe":    bool(include_universe),
        },
        "events_count":       len(events),
        "events":             events,
        "disclaimer": (
            "Historical stage reconstruction is BEST-EFFORT. Env-only "
            "markers (USE_PROCESS_POOL, FACTORY_RUNNER_OWNS_SCHEDULERS) "
            "are not persisted in `audit_log.boot_state.active_overrides`, "
            "so stage S1 cannot be derived forensically from this surface "
            "alone — only stages S0 and S2–S9 (which gate on feature_flags "
            "registry entries) are fully reconstructable."
        ),
    }

    # ── Optional: interleave bare boot_state rows for the FULL ────
    # activation timeline (override_diff rows alone hide steady-state
    # boots). Off by default to keep the payload small.
    if include_boot_states:
        boot_rows: List[Dict[str, Any]] = []
        try:
            bs_match: Dict[str, Any] = {"event": "latent_capability:boot_state"}
            if source:
                bs_match["source"] = source
            if since is not None:
                bs_match["ts_dt"] = {"$gte": since}
            cur = (
                db["audit_log"]
                .find(
                    bs_match,
                    {
                        "_id": 0, "ts": 1, "ts_dt": 1, "source": 1, "process_pid": 1,
                        "flag_count": 1, "overridden_count": 1, "all_dormant": 1,
                        "active_overrides": 1,
                    },
                )
                .sort("ts_dt", -1)
                .limit(limit * 4)   # boots are more frequent than diffs
            )
            async for d in cur:
                boot_rows.append({
                    "ts":               _iso(d.get("ts_dt")) or d.get("ts"),
                    "event":            "boot_state",
                    "source":           d.get("source"),
                    "process_pid":      d.get("process_pid"),
                    "flag_count":       d.get("flag_count"),
                    "overridden_count": d.get("overridden_count"),
                    "all_dormant":      d.get("all_dormant"),
                    "active_overrides": d.get("active_overrides") or {},
                })
        except Exception as e:                               # pragma: no cover
            logger.debug("[widening_history] boot_state fetch failed: %s", e)
        out["boot_states_count"] = len(boot_rows)
        out["boot_states"]       = boot_rows

    # ── Optional: governance universe operator-decree changes. ────
    if include_universe:
        out["universe_changes"] = await _governance_universe_changes(
            db, since=since, limit=min(limit, 50),
        )

    return out
