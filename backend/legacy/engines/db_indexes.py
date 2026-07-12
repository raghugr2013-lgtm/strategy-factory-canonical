"""
Phase A.1 / A.2 — Mongo index hardening + retention TTLs.

ADDITIVE: every index here is declared idempotently. Re-running this
helper is safe; Mongo's `create_index` is a no-op when an equivalent
index already exists, and an error when the spec conflicts.

Discipline:
  * No index modifies existing data (creates only).
  * TTL retention is operator-tunable via env var so the discipline
    can be relaxed/tightened without code changes.
  * Failures are logged at WARNING but never raise — index hardening
    is best-effort and must NEVER block backend startup.

Consumed by `server.py` startup hook `_ensure_mongo_indexes`.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Tuple

from pymongo import ASCENDING, DESCENDING

from engines.db import get_db

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# TTL retention (operator-tunable; defaults conservative)
# ─────────────────────────────────────────────────────────────────────
PIPELINE_LOGS_TTL_DAYS = int(os.environ.get("PIPELINE_LOGS_TTL_DAYS", "30"))
LLM_CALL_LOG_TTL_DAYS = int(os.environ.get("LLM_CALL_LOG_TTL_DAYS", "90"))
# Phase 2 P2.8.b — bounded audit_log retention. Only docs that carry a
# BSON Date `ts_dt` are eligible for reaping; legacy writers without
# `ts_dt` are left untouched (additive, non-destructive).
AUDIT_LOG_TTL_DAYS = int(os.environ.get("AUDIT_LOG_RETENTION_DAYS", "90"))
# Phase A.2 — P0B Phase 2 — bounded market_spread retention. Older bars can always
# be re-derived from the Tier-1 BI5 archive on the filesystem.
MARKET_SPREAD_TTL_DAYS = int(os.environ.get("MARKET_SPREAD_TTL_DAYS", "180"))

# R0 — market_universe_audit retention. Approved at 90 days (decision §7.3).
MARKET_UNIVERSE_AUDIT_TTL_DAYS = int(
    os.environ.get("MARKET_UNIVERSE_AUDIT_TTL_DAYS", "90")
)


# ─────────────────────────────────────────────────────────────────────
# Index specifications
#
# Each entry is (collection, keys, options). `options` may include
# `name`, `unique`, `background`, `expireAfterSeconds`, etc.
#
# DO NOT change index names once they exist in production — Mongo
# treats name drift as "conflicting spec" and refuses to create.
# ─────────────────────────────────────────────────────────────────────
INDEX_SPECS: List[Tuple[str, List[Tuple[str, int]], Dict[str, Any]]] = [
    # Lifecycle hot-path: every gate evaluation reads by strategy_hash.
    ("strategy_lifecycle",
     [("strategy_hash", ASCENDING)],
     {"name": "ix_lifecycle_strategy_hash", "unique": False, "background": True}),

    # Mutation events: read by run + chronological scan.
    ("mutation_events",
     [("run_id", ASCENDING)],
     {"name": "ix_mut_events_run", "background": True}),
    ("mutation_events",
     [("type", ASCENDING), ("ts", DESCENDING)],
     {"name": "ix_mut_events_type_ts", "background": True}),

    # Audit log: every governance read is chronological.
    ("audit_log",
     [("ts", DESCENDING)],
     {"name": "ix_audit_ts", "background": True}),
    ("audit_log",
     [("event", ASCENDING), ("ts", DESCENDING)],
     {"name": "ix_audit_event_ts", "background": True}),

    # Phase 30.1 institutional event dedup key.
    ("auto_factory_alert_log",
     [("strategy_hash", ASCENDING), ("event_type", ASCENDING), ("run_id", ASCENDING)],
     {"name": "ix_alert_dedup", "background": True}),

    # LLM call log — cost monitoring queries by provider + time.
    ("llm_call_log",
     [("ts", DESCENDING)],
     {"name": "ix_llm_ts", "background": True}),
    ("llm_call_log",
     [("provider", ASCENDING), ("ts", DESCENDING)],
     {"name": "ix_llm_provider_ts", "background": True}),

    # Per-strategy + regime breakdown queries (Phase 29 on-read).
    ("strategy_performance_history",
     [("strategy_hash", ASCENDING), ("ts", DESCENDING)],
     {"name": "ix_perf_hist_hash_ts", "background": True}),
    ("strategy_performance_history",
     [("strategy_hash", ASCENDING), ("regime", ASCENDING)],
     {"name": "ix_perf_hist_hash_regime", "background": True}),

    # Pipeline log read paths.
    ("pipeline_logs",
     [("ts", DESCENDING)],
     {"name": "ix_pipe_ts", "background": True}),
    ("pipeline_logs",
     [("run_id", ASCENDING), ("ts", DESCENDING)],
     {"name": "ix_pipe_run_ts", "background": True}),

    # cBot parity sign-off lookup (Phase B.1).
    ("cbot_parity_signoff",
     [("strategy_hash", ASCENDING)],
     {"name": "ix_cbot_parity_hash", "unique": True, "background": True}),

    # Mutation stability log filter paths.
    ("mutation_stability_log",
     [("mutation_type", ASCENDING), ("ts", DESCENDING)],
     {"name": "ix_mut_stab_type_ts", "background": True}),
    ("mutation_stability_log",
     [("auto_save_status", ASCENDING), ("ts", DESCENDING)],
     {"name": "ix_mut_stab_status_ts", "background": True}),

    # ─── Phase 2 P2.8 — additional indexes for scale ────────────────
    # Explorer hot paths: by hash for individual lookups, by created_at
    # for the default reverse-chronological list view.
    ("strategy_library",
     [("strategy_hash", ASCENDING)],
     {"name": "ix_lib_hash", "background": True}),
    ("strategy_library",
     [("created_at", DESCENDING)],
     {"name": "ix_lib_created_at", "background": True}),

    # env_priority.consume_recent_cycles() cursor by finished_at.
    ("auto_run_cycles",
     [("finished_at", DESCENDING)],
     {"name": "ix_auto_run_finished", "background": True}),

    # multi_cycle_runner.list_runs(limit) sorts by started_at desc.
    ("multi_cycle_runs",
     [("started_at", DESCENDING)],
     {"name": "ix_mc_runs_started", "background": True}),

    # strategy_lifecycle.recent_transitions(since_iso) filters by transition_at.
    ("strategy_lifecycle_history",
     [("transition_at", DESCENDING)],
     {"name": "ix_lifecycle_hist_transition", "background": True}),

    # survivor_registry.fetch_survivor_universe scans by current_stage.
    ("strategy_lifecycle",
     [("current_stage", ASCENDING)],
     {"name": "ix_lifecycle_stage", "background": True}),

    # NOTE: advisory_locks.expires_at_dt is indexed by the TTL spec
    # below (ttl_advisory_locks). Mongo allows only ONE index per key,
    # and the TTL index itself is a B-tree usable for the stale-lock
    # eviction query in advisory_lock.try_acquire(). No extra plain
    # index needed here.

    # ─── Phase 4 P4.14 latent — Risk-of-Ruin evaluations ────────────
    ("risk_of_ruin_evaluations",
     [("strategy_hash", ASCENDING), ("ts_dt", DESCENDING)],
     {"name": "ix_ror_strategy_ts", "background": True}),
    ("risk_of_ruin_evaluations",
     [("ts_dt", DESCENDING)],
     {"name": "ix_ror_ts", "background": True}),

    # ─── Phase 4 P4.16 latent — Calibration outcomes + tables ──────
    ("calibration_outcomes",
     [("strategy_hash", ASCENDING), ("realized_outcome", ASCENDING),
      ("prediction_at_dt", DESCENDING)],
     {"name": "ix_calib_strategy_outcome_ts", "background": True}),
    ("calibration_outcomes",
     [("realized_outcome", ASCENDING), ("predicted_pp", ASCENDING)],
     {"name": "ix_calib_outcome_pp", "background": True}),
    ("calibration_tables",
     [("built_at_dt", DESCENDING)],
     {"name": "ix_calib_table_built", "background": True}),

    # ─── P0B Phase 2 — BI5 certification & market_spread ────────────
    # market_spread: per-minute OHLC spread bars derived from BI5 ticks.
    # Domain key is (symbol, minute_utc) — unique upserts guarantee
    # idempotent re-ingest. minute-only index supports time-range scans
    # for spread audits / charting.
    ("market_spread",
     [("symbol", ASCENDING), ("minute_utc", ASCENDING)],
     {"name": "ix_spread_sym_min", "unique": True, "background": True}),
    ("market_spread",
     [("minute_utc", DESCENDING)],
     {"name": "ix_spread_min", "background": True}),

    # bi5_data_certification: one document per (symbol, window) — the
    # per-feed BI5 data-quality certification. The strategy-level
    # `bi5_certification` collection is owned by the Phase 3
    # orchestrator and is NOT declared here (it doesn't exist yet).
    # Audit-grade evidence — NO TTL.
    ("bi5_data_certification",
     [("symbol", ASCENDING),
      ("window_start_utc", ASCENDING),
      ("window_end_utc", ASCENDING)],
     {"name": "ix_bi5datacert_sym_window", "unique": True, "background": True}),
    ("bi5_data_certification",
     [("symbol", ASCENDING), ("certified_at_dt", DESCENDING)],
     {"name": "ix_bi5datacert_sym_ts", "background": True}),
    ("bi5_data_certification",
     [("verdict", ASCENDING), ("certified_at_dt", DESCENDING)],
     {"name": "ix_bi5datacert_verdict", "background": True}),
    ("bi5_data_certification",
     [("certified_at_dt", DESCENDING)],
     {"name": "ix_bi5datacert_ts", "background": True}),

    # ─── P0B Phase 3 — strategy-level bi5_certification ─────────────
    # Distinct from bi5_data_certification: this is the per-strategy
    # gate (Elite Survivor → BI5 Certified → Deployable). Audit-trail
    # semantics: every cert run creates a NEW row.
    ("bi5_certification",
     [("strategy_id", ASCENDING), ("certification_timestamp", DESCENDING)],
     {"name": "ix_bi5cert_strategy_ts", "unique": True, "background": True}),
    ("bi5_certification",
     [("pair", ASCENDING), ("certification_timestamp", DESCENDING)],
     {"name": "ix_bi5cert_pair_ts", "background": True}),
    ("bi5_certification",
     [("timeframe", ASCENDING), ("certification_timestamp", DESCENDING)],
     {"name": "ix_bi5cert_tf_ts", "background": True}),
    ("bi5_certification",
     [("style", ASCENDING), ("certification_timestamp", DESCENDING)],
     {"name": "ix_bi5cert_style_ts", "background": True}),
    ("bi5_certification",
     [("mutation_family", ASCENDING), ("certification_timestamp", DESCENDING)],
     {"name": "ix_bi5cert_family_ts", "background": True,
      "partialFilterExpression": {"mutation_family": {"$type": "string"}}}),
    ("bi5_certification",
     [("certification_verdict", ASCENDING), ("certification_timestamp", DESCENDING)],
     {"name": "ix_bi5cert_verdict_ts", "background": True}),
    ("bi5_certification",
     [("composite_score", DESCENDING)],
     {"name": "ix_bi5cert_composite", "background": True}),
    ("bi5_certification",
     [("certification_timestamp", DESCENDING)],
     {"name": "ix_bi5cert_ts", "background": True}),

    # ─── R0 — market_universe registry + audit indexes ─────────────
    # Aliases multikey lookup (e.g. resolve "GOLD"→XAUUSD, "NAS100"→US100).
    ("market_universe_symbols",
     [("aliases", ASCENDING)],
     {"name": "ix_mu_aliases", "background": True}),
    # Audit time-range queries per symbol.
    ("market_universe_audit",
     [("symbol", ASCENDING), ("ts_dt", DESCENDING)],
     {"name": "ix_mu_audit_symbol_ts", "background": True}),
    # Global recent audit listing (forensics across all symbols).
    ("market_universe_audit",
     [("ts_dt", DESCENDING)],
     {"name": "ix_mu_audit_ts", "background": True}),
]


# Per-collection TTL configurations: {collection: (key, ttl_seconds, name)}
TTL_SPECS: List[Tuple[str, str, int, str]] = [
    # `pipeline_logs.ts` is an ISO string in production; Mongo's TTL
    # requires a BSON Date. We document this and skip TTL when the field
    # type can't be guaranteed — operator can convert to BSON Date later.
    # Instead, we add a `created_at_dt` companion if needed.
    # For now, only enable TTL on collections we control end-to-end.
    ("llm_call_log", "ts_dt", LLM_CALL_LOG_TTL_DAYS * 86400, "ttl_llm_call_log"),
    ("pipeline_logs", "ts_dt", PIPELINE_LOGS_TTL_DAYS * 86400, "ttl_pipeline_logs"),

    # Phase 2 P2.8.b — bounded audit_log retention. Only writers that
    # populate `ts_dt` (e.g. engines.audit_log_writer.write_event and
    # factory_runner._audit) get reaped; legacy ISO-only writers stay.
    ("audit_log", "ts_dt", AUDIT_LOG_TTL_DAYS * 86400, "ttl_audit_log"),

    # Phase 2 P2.7 — advisory_locks crash-recovery TTL. expireAfterSeconds=0
    # means "delete docs whose expires_at_dt is in the PAST" — i.e. Mongo
    # itself reaps stale locks even if no acquirer ever returns. The app
    # also evicts proactively in advisory_lock.try_acquire(); this is a
    # belt-and-braces safety net for crashed workers under cross-worker
    # uvicorn scaling (Phase 2 P2.7 worker ramp).
    ("advisory_locks", "expires_at_dt", 0, "ttl_advisory_locks"),

    # P0B Phase 2 — bounded market_spread retention. Older bars can be
    # re-derived from the Tier-1 BI5 filesystem archive at any time.
    ("market_spread", "created_at_dt",
     MARKET_SPREAD_TTL_DAYS * 86400, "ttl_market_spread"),

    # R0 — market_universe_audit retention (90 days approved default).
    ("market_universe_audit", "ts_dt",
     MARKET_UNIVERSE_AUDIT_TTL_DAYS * 86400, "ttl_market_universe_audit"),
]


async def ensure_indexes() -> Dict[str, Any]:
    """Best-effort idempotent index creation. Never raises.

    Returns a structured summary { created: [...], existed: [...],
    errors: [...] } suitable for logging / a diagnostic endpoint.
    """
    db = get_db()
    created: List[str] = []
    existed: List[str] = []
    errors: List[Dict[str, str]] = []

    for coll_name, keys, options in INDEX_SPECS:
        try:
            existing = await db[coll_name].index_information()
            name = options.get("name") or "_".join(f"{k}_{d}" for k, d in keys)
            if name in existing:
                existed.append(f"{coll_name}.{name}")
                continue
            await db[coll_name].create_index(keys, **options)
            created.append(f"{coll_name}.{name}")
            logger.info("[db_indexes] created %s.%s", coll_name, name)
        except Exception as e:                               # pragma: no cover
            err = {"collection": coll_name, "spec": str(keys), "error": str(e)[:200]}
            errors.append(err)
            logger.warning("[db_indexes] failed %s/%s: %s", coll_name, keys, e)

    # TTL indexes — separate loop so a TTL conflict doesn't block normal indexes.
    for coll_name, field, ttl_sec, name in TTL_SPECS:
        try:
            existing = await db[coll_name].index_information()
            if name in existing:
                # Verify TTL value; recreate only if env changed.
                cur_ttl = existing[name].get("expireAfterSeconds")
                if cur_ttl != ttl_sec:
                    await db[coll_name].drop_index(name)
                    await db[coll_name].create_index(
                        [(field, ASCENDING)],
                        name=name, expireAfterSeconds=ttl_sec, background=True,
                    )
                    created.append(f"{coll_name}.{name}(retuned)")
                    logger.info("[db_indexes] retuned TTL %s.%s → %ds", coll_name, name, ttl_sec)
                else:
                    existed.append(f"{coll_name}.{name}")
                continue
            await db[coll_name].create_index(
                [(field, ASCENDING)],
                name=name, expireAfterSeconds=ttl_sec, background=True,
            )
            created.append(f"{coll_name}.{name}")
            logger.info("[db_indexes] created TTL %s.%s ttl=%ds", coll_name, name, ttl_sec)
        except Exception as e:                               # pragma: no cover
            err = {"collection": coll_name, "ttl_index": name, "error": str(e)[:200]}
            errors.append(err)
            logger.warning("[db_indexes] TTL failed %s/%s: %s", coll_name, name, e)

    return {
        "created": created,
        "existed": existed,
        "errors": errors,
        "ttl_days": {
            "pipeline_logs": PIPELINE_LOGS_TTL_DAYS,
            "llm_call_log": LLM_CALL_LOG_TTL_DAYS,
            "market_spread": MARKET_SPREAD_TTL_DAYS,
            "market_universe_audit": MARKET_UNIVERSE_AUDIT_TTL_DAYS,
        },
    }


async def get_index_summary() -> Dict[str, Any]:
    """Read-only diagnostic snapshot of which target indexes exist."""
    db = get_db()
    out: Dict[str, Any] = {"collections": {}}
    seen = set()
    for coll_name, _, options in INDEX_SPECS:
        if coll_name in seen:
            continue
        seen.add(coll_name)
        try:
            info = await db[coll_name].index_information()
            out["collections"][coll_name] = sorted(info.keys())
        except Exception as e:                               # pragma: no cover
            out["collections"][coll_name] = {"error": str(e)[:200]}
    return out
