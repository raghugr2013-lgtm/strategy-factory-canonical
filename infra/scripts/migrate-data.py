#!/usr/bin/env python3
"""Strategy Factory — MongoDB migration utility.

Zero-loss migration from the current v01-based VPS deployment into the
v1.0 canonical `strategy_factory_v1` database.

Two supported profiles:

    --profile lean   (DEFAULT — production deployment)
        Migrates only business-critical collections. Skips regenerable
        bulk data (market_data, ticks, spreads, caches) and ephemeral
        runtime state (locks, heartbeats, transient logs). Typical ETA:
        minutes. After deployment the platform's own BI5 downloader
        and sweep engines repopulate the excluded data.

    --profile full   (OPT-IN — disaster recovery / exact env replication)
        Migrates every planned collection across all tiers. Includes
        multi-hour datasets (~313k market_data docs, ~309k market_spread).

In both profiles, `factory_supervisor_lock` is PERMANENTLY excluded via
INTENTIONALLY_EXCLUDED to prevent supervisor split-brain on a fresh host.

Usage (from the VPS, next to a running mongo:7.0 container on vqb-network):

    # Dry run — lean profile (default), no writes
    docker run --rm --network vqb-network -v "$(pwd):/work" -w /work \\
        python:3.12-slim sh -c \\
        "pip install -q pymongo==4.9.2 && python infra/scripts/migrate-data.py \\
            --source \"$SOURCE_MONGO_URL\" --source-db test_database \\
            --target \"$SHARED_MONGO_URL\" --target-db strategy_factory_v1 \\
            --dry-run"

    # Live lean-profile production migration (recommended default)
    docker run --rm --network vqb-network -v "$(pwd):/work" -w /work \\
        python:3.12-slim sh -c \\
        "pip install -q pymongo==4.9.2 && python infra/scripts/migrate-data.py \\
            --source \"$SOURCE_MONGO_URL\" --source-db test_database \\
            --target \"$SHARED_MONGO_URL\" --target-db strategy_factory_v1 \\
            --report /work/migration-report.json"

    # Full-migration (disaster recovery / archival replication)
    docker run --rm --network vqb-network -v "$(pwd):/work" -w /work \\
        python:3.12-slim sh -c \\
        "pip install -q pymongo==4.9.2 && python infra/scripts/migrate-data.py \\
            --source \"$SOURCE_MONGO_URL\" --source-db test_database \\
            --target \"$SHARED_MONGO_URL\" --target-db strategy_factory_v1 \\
            --profile full \\
            --report /work/migration-report.json"

The script is idempotent — safe to re-run. It uses `upsert=True` keyed on
domain identifiers (user_id/email, strategy_id, query_id, jti), so a
second run over already-migrated docs is a no-op.

Exit codes: 0 = success, 1 = validation errors, 2 = connection failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import signal
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from bson import ObjectId
    from pymongo import MongoClient, ASCENDING, DESCENDING
    from pymongo.errors import PyMongoError, DuplicateKeyError
except ImportError:
    sys.stderr.write("error: pymongo not installed. Run: pip install pymongo==4.9.2\n")
    sys.exit(2)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("migrate")

# ─────────────────────────────────────────────────────────────────────
# Report accumulator — every action lands here, dumped at the end.
# ─────────────────────────────────────────────────────────────────────


class Report:
    def __init__(self) -> None:
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.finished_at: Optional[str] = None
        self.dry_run: bool = False
        self.source: dict = {}
        self.target: dict = {}
        self.collections: Dict[str, dict] = {}
        self.errors: List[Any] = []   # list of {collection, doc_id?, error, traceback?} or legacy strings
        self.warnings: List[str] = []
        self.summary: dict = {}

    def start(self, name: str, source_count: int) -> None:
        self.collections[name] = {
            "source_count": source_count,
            "migrated": 0,
            "skipped_already_present": 0,
            "upgraded": 0,
            "errors": 0,
            "notes": [],
        }

    def note(self, name: str, msg: str) -> None:
        self.collections.setdefault(name, {}).setdefault("notes", []).append(msg)

    def finish(self) -> None:
        self.finished_at = datetime.now(timezone.utc).isoformat()
        total_migrated = sum(c["migrated"] for c in self.collections.values())
        total_upgraded = sum(c["upgraded"] for c in self.collections.values())
        total_skipped = sum(c["skipped_already_present"] for c in self.collections.values())
        total_errors = sum(c["errors"] for c in self.collections.values())
        # Merge, don't replace — preserves keys set before .finish() (e.g. profile).
        self.summary.update({
            "collections_processed": len(self.collections),
            "documents_migrated": total_migrated,
            "documents_upgraded_in_place": total_upgraded,
            "documents_skipped_already_present": total_skipped,
            "document_level_errors": total_errors,
            "hard_errors": len(self.errors),
            "warnings": len(self.warnings),
        })

    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "dry_run": self.dry_run,
            "source": self.source,
            "target": self.target,
            "collections": self.collections,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


# ─────────────────────────────────────────────────────────────────────
# Schema upgrade transformers — one per collection that has changed.
# Each transformer takes a source doc and returns (target_doc, upgraded_bool).
# Return `None` to skip the doc entirely (with a warning).
# ─────────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_datetime(v: Any, default: Optional[datetime] = None) -> datetime:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return default or _now()


# ─────────────────────────────────────────────────────────────────────
# Fingerprint — stable per-document hash of the SOURCE doc, computed on the
# raw source (excluding _id, which is regenerated on the target). Stamped
# onto every migrated doc under `_migration_meta.source_fingerprint` so the
# verifier can prove zero-loss without any schema knowledge.
# ─────────────────────────────────────────────────────────────────────


def _canonical(v: Any) -> Any:
    """JSON-safe canonicalisation of any BSON value for stable hashing."""
    if isinstance(v, dict):
        return {str(k): _canonical(v[k]) for k in sorted(v.keys()) if k != "_id"}
    if isinstance(v, (list, tuple)):
        return [_canonical(x) for x in v]
    if isinstance(v, datetime):
        return v.replace(microsecond=0).isoformat() if v.tzinfo else v.replace(tzinfo=timezone.utc, microsecond=0).isoformat()
    if isinstance(v, ObjectId):
        return f"$oid:{v}"
    if isinstance(v, bytes):
        return f"$bin:{v.hex()}"
    return v


def source_fingerprint(doc: dict) -> str:
    """SHA-256 hex digest of the canonical JSON of the source document (minus _id)."""
    payload = json.dumps(_canonical(doc), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _stamp(out: dict, source_doc: dict, source_col: str, transformer: str) -> dict:
    """Attach `_migration_meta` sub-doc so the verifier can prove the migration lineage.

    Never overwrites an existing `_migration_meta` on re-runs (idempotency)."""
    if "_migration_meta" in out and isinstance(out["_migration_meta"], dict):
        return out
    out["_migration_meta"] = {
        "source_collection": source_col,
        "source_fingerprint": source_fingerprint(source_doc),
        "source_id": str(source_doc.get("_id")) if source_doc.get("_id") is not None else None,
        "transformer": transformer,
        "migrated_at": _now().isoformat(),
    }
    return out


def upgrade_user(doc: dict) -> Tuple[Optional[dict], bool]:
    """v01 users → v1.0 users.

    Preserves every source field verbatim. The original v01 `role` and `status`
    values are additionally stored as `legacy_role` / `legacy_status` so no
    metadata is lost — the active `role`/`status` fields are coerced to
    v1.0-valid literals so Pydantic auth still works. Bcrypt hashes are
    preserved byte-identical, so users log in with their v01 password.
    """
    out = dict(doc)
    out.pop("_id", None)   # let target Mongo assign fresh _id

    upgraded = False
    email = (out.get("email") or "").strip().lower()
    if not email:
        return None, False   # skip: user without email is not migrateable

    out["email"] = email

    # Preserve original role/status verbatim so nothing is lost.
    if "role" in out and "legacy_role" not in out:
        out["legacy_role"] = out["role"]
    if "status" in out and "legacy_status" not in out:
        out["legacy_status"] = out["status"]

    # user_id
    if not out.get("user_id"):
        out["user_id"] = uuid.uuid4().hex[:16]
        upgraded = True

    # status → coerce to v1.0 literal (active|disabled). Preserves legacy_status.
    old_status = (out.get("status") or "").lower() if out.get("status") else ""
    if old_status in ("pending", "approved", ""):
        new_status = "active"
    elif old_status in ("active", "disabled"):
        new_status = old_status
    else:
        new_status = "active"
    if new_status != out.get("status"):
        out["status"] = new_status
        upgraded = True

    # role → coerce to v1.0 literal (admin|developer|researcher|operator|viewer).
    # Preserves legacy_role for admin review.
    if out.get("role") in (None, "", "user"):
        out["role"] = "viewer"
        upgraded = True
    elif out["role"] not in ("admin", "developer", "researcher", "operator", "viewer"):
        out["role"] = "viewer"
        upgraded = True

    # datetimes
    out["created_at"] = _ensure_datetime(out.get("created_at"))
    out["updated_at"] = _ensure_datetime(out.get("updated_at"), default=out["created_at"])

    return out, upgraded


def upgrade_strategy(doc: dict) -> Tuple[Optional[dict], bool]:
    """v01 strategies → v1.0 strategies.

    Preserves every field except normalising identifiers, timestamps, and status.
    Stage 2 engines read arbitrary extra fields (ir, tags, symbol, timeframe,
    …) as-is, so we do NOT strip anything.
    """
    out = dict(doc)
    out.pop("_id", None)

    upgraded = False
    if not out.get("strategy_id"):
        # try common alternate keys
        for alt in ("id", "sid", "strategyId"):
            if out.get(alt):
                out["strategy_id"] = str(out[alt])
                upgraded = True
                break
        if not out.get("strategy_id"):
            out["strategy_id"] = uuid.uuid4().hex[:16]
            upgraded = True

    if not out.get("name"):
        out["name"] = out.get("title") or f"Strategy {out['strategy_id'][:6]}"
        upgraded = True

    if not out.get("status"):
        out["status"] = "draft"
        upgraded = True

    if "tags" not in out or not isinstance(out.get("tags"), list):
        out["tags"] = []
        upgraded = True

    if not out.get("created_by"):
        out["created_by"] = out.get("owner") or "unknown"
        upgraded = True

    out["created_at"] = _ensure_datetime(out.get("created_at"))
    out["updated_at"] = _ensure_datetime(out.get("updated_at"), default=out["created_at"])

    return out, upgraded


def upgrade_research_query(doc: dict) -> Tuple[Optional[dict], bool]:
    """v01 research_lineage or research_queries → v1.0 research_queries."""
    out = dict(doc)
    out.pop("_id", None)
    upgraded = False

    if not out.get("query_id"):
        out["query_id"] = out.get("id") or uuid.uuid4().hex[:16]
        upgraded = True
    if not out.get("prompt"):
        out["prompt"] = out.get("query") or out.get("text") or ""
        upgraded = True
    if not out.get("provider"):
        out["provider"] = out.get("model_provider") or "unknown"
        upgraded = True
    if not out.get("created_by"):
        out["created_by"] = out.get("user_id") or "unknown"
        upgraded = True

    out["created_at"] = _ensure_datetime(out.get("created_at"))
    return out, upgraded


def upgrade_passthrough(doc: dict) -> Tuple[Optional[dict], bool]:
    """No schema change — just strip _id so target assigns fresh."""
    out = dict(doc)
    out.pop("_id", None)
    return out, False


# ─────────────────────────────────────────────────────────────────────
# Migration plan — which source collection maps to which target collection,
# what the natural key is (for upsert idempotency), and which transformer runs.
# ─────────────────────────────────────────────────────────────────────

# Every row is tagged with a `tier` used by the two supported profiles:
#   • "critical"    — always migrated (Lean + Full)
#   • "regenerable" — bulk / derivable data; migrated ONLY in Full mode
#   • "optional"    — ephemeral / runtime state / logs; migrated ONLY in Full mode
#
# Rows are grouped by Phase (1–6) so business-critical data always lands
# BEFORE any bulk/regenerable data — that way an interruption during the
# large collections still leaves the platform in a fully operational state.
#
# Phase 1 → Identity & Governance (fast, absolute prerequisites)
# Phase 2 → Core IP (strategies + research + validation + calibration)
# Phase 3 → Bots, Portfolios, Deployment, Execution ledger
# Phase 4 → Flags, Audit journals, Orchestrator, Monitoring
# Phase 5 → Bulk / Regenerable (Full mode only)
# Phase 6 → Optional / Ephemeral runtime state & logs (Full mode only)
MIGRATION_PLAN: List[Dict[str, Any]] = [
    # ═════════════════════════════════════════════════════════════════
    # PHASE 1 — IDENTITY & GOVERNANCE (critical, ~fast)
    # ═════════════════════════════════════════════════════════════════
    {"source": "users", "target": "users", "key": "email", "xform": upgrade_user, "tier": "critical"},
    {"source": "audit_log", "target": "audit_log", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "notifications", "target": "notifications", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "settings", "target": "settings", "key": "key", "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "governance_universe", "target": "governance_universe", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "market_universe", "target": "market_universe", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "market_universe_symbols", "target": "market_universe_symbols", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "market_universe_audit", "target": "market_universe_audit", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "instrument_mappings", "target": "instrument_mappings", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "prop_firm_configs", "target": "prop_firm_configs", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "prop_firm_rules", "target": "prop_firm_rules", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "challenge_rules", "target": "challenge_rules", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "prop_firm_challenges", "target": "prop_firm_challenges", "key": None, "xform": upgrade_passthrough, "tier": "critical"},

    # ═════════════════════════════════════════════════════════════════
    # PHASE 2 — CORE IP (strategies + research + validation + calibration)
    # ═════════════════════════════════════════════════════════════════
    {"source": "strategies", "target": "strategies", "key": "strategy_id", "xform": upgrade_strategy, "tier": "critical"},
    {"source": "strategy_library", "target": "strategies", "key": "strategy_id", "xform": upgrade_strategy, "tier": "critical",
     "note": "v01 strategy_library folded into strategies collection"},
    {"source": "strategy_library_archive", "target": "strategy_library_archive", "key": None, "xform": upgrade_passthrough, "tier": "critical",
     "note": "Preserved verbatim — Stage 2 dossier / lineage engines consume this"},
    {"source": "strategy_versions", "target": "strategy_versions", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "strategy_memory", "target": "strategy_memory", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "strategy_lifecycle_history", "target": "strategy_lifecycle_history", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "strategy_performance_history", "target": "strategy_performance_history", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "lifecycle_events", "target": "lifecycle_events", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "mutation_pool", "target": "mutation_pool", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "mutation_events", "target": "mutation_events", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "mutation_runs", "target": "mutation_runs", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "research_lineage", "target": "research_queries", "key": "query_id", "xform": upgrade_research_query, "tier": "critical",
     "note": "v01 research_lineage becomes research_queries in v1.0"},
    {"source": "research_queries", "target": "research_queries", "key": "query_id", "xform": upgrade_research_query, "tier": "critical"},
    {"source": "research_runs", "target": "research_runs", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "llm_call_log", "target": "llm_call_log", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "validation_reports", "target": "validation_reports", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "backtest_results", "target": "backtest_results", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "survivor_registry", "target": "survivor_registry", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "bi5_certifications", "target": "bi5_certifications", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "bi5_mappings", "target": "bi5_mappings", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "bi5_certification", "target": "bi5_certification", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "bi5_data_certification", "target": "bi5_data_certification", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "calibration_tables", "target": "calibration_tables", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "calibration_outcomes", "target": "calibration_outcomes", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "market_intelligence", "target": "market_intelligence", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "risk_of_ruin_evaluations", "target": "risk_of_ruin_evaluations", "key": None, "xform": upgrade_passthrough, "tier": "critical"},

    # ═════════════════════════════════════════════════════════════════
    # PHASE 3 — BOTS, PORTFOLIOS, DEPLOYMENT, EXECUTION LEDGER
    # ═════════════════════════════════════════════════════════════════
    {"source": "master_bots", "target": "master_bots", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "master_bot_definitions", "target": "master_bot_definitions", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "master_bot_members", "target": "master_bot_members", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "master_bot_tiers", "target": "master_bot_tiers", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "master_bot_ranker_config", "target": "master_bot_ranker_config", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "master_bot_runners", "target": "master_bot_runners", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "master_bot_packs", "target": "master_bot_packs", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "master_bot_deployments", "target": "master_bot_deployments", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "master_bot_exports", "target": "master_bot_exports", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "portfolios", "target": "portfolios", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "portfolio_definitions", "target": "portfolio_definitions", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "portfolio_builder_runs", "target": "portfolio_builder_runs", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "multi_asset_portfolios", "target": "multi_asset_portfolios", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "cbot_parity", "target": "cbot_parity", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "cbot_parity_signoff", "target": "cbot_parity_signoff", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "runner_accounts", "target": "runner_accounts", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "runner_token_rotation_history", "target": "runner_token_rotation_history", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "deployment_registry", "target": "deployment_registry", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "live_tracking", "target": "live_tracking", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "allocation_history", "target": "allocation_history", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "trade_runner_runs", "target": "trade_runner_runs", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "trade_runner_trades", "target": "trade_runner_trades", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "rebalance_config", "target": "rebalance_config", "key": None, "xform": upgrade_passthrough, "tier": "critical"},

    # ═════════════════════════════════════════════════════════════════
    # PHASE 4 — FLAGS, AUDIT JOURNALS, ORCHESTRATOR, MONITORING (critical)
    # ═════════════════════════════════════════════════════════════════
    {"source": "flag_overrides", "target": "flag_overrides", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "flag_override_history", "target": "flag_override_history", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "widening_proposals", "target": "widening_proposals", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "admission_journal", "target": "admission_journal", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "activation_journal", "target": "activation_journal", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "asf_import_actions", "target": "asf_import_actions", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "ingested_strategies", "target": "ingested_strategies", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "monitoring_breach_log", "target": "monitoring_breach_log", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "scaling_events", "target": "scaling_events", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "auto_factory_config", "target": "auto_factory_config", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "auto_factory_runs", "target": "auto_factory_runs", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "auto_factory_strategies", "target": "auto_factory_strategies", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "auto_maintenance_config", "target": "auto_maintenance_config", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "multi_cycle_runs", "target": "multi_cycle_runs", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "orchestrator_env_priority", "target": "orchestrator_env_priority", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "factory_supervisor_defer_queue", "target": "factory_supervisor_defer_queue", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "factory_supervisor_submissions", "target": "factory_supervisor_submissions", "key": None, "xform": upgrade_passthrough, "tier": "critical"},
    {"source": "factory_supervisor_fag_proposals", "target": "factory_supervisor_fag_proposals", "key": None, "xform": upgrade_passthrough, "tier": "critical"},

    # ═════════════════════════════════════════════════════════════════
    # PHASE 5 — BULK / REGENERABLE (Full-mode only; excluded in Lean)
    #    All rows below are byte-reproducible from the BI5 downloader,
    #    the live spread sweep, or on the next mutation/soak cycle.
    # ═════════════════════════════════════════════════════════════════
    {"source": "market_data", "target": "market_data", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Historical OHLC bars — repopulated deterministically by the Dukascopy BI5 downloader"},
    {"source": "market_data_ticks", "target": "market_data_ticks", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Raw tick data — BI5 downloader regenerates byte-identically"},
    {"source": "tick_data", "target": "tick_data", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Alternative tick storage — BI5 downloader regenerates"},
    {"source": "market_spread", "target": "market_spread", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Spread telemetry — live spread sweep rebuilds from broker feed"},
    {"source": "market_profile_cells", "target": "market_profile_cells", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Derived cache over market_data"},
    {"source": "data_coverage", "target": "data_coverage", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Summary index over market_data — MUST be regenerated when market_data is repopulated"},
    {"source": "bi5_ingest_log", "target": "bi5_ingest_log", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Append-only log; no IP; next BI5 sweep repopulates"},
    {"source": "bi5_cert_sweep_log", "target": "bi5_cert_sweep_log", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Append-only log; next cert sweep repopulates"},
    {"source": "soak_stability_samples", "target": "soak_stability_samples", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Long-running host telemetry; new host = new baseline"},
    {"source": "mutation_stability_log", "target": "mutation_stability_log", "key": None, "xform": upgrade_passthrough, "tier": "regenerable",
     "note": "Operational stability telemetry (variance samples per mutation); rebuilt on next mutation sweep — NOT an evolutionary-learning store"},

    # ═════════════════════════════════════════════════════════════════
    # PHASE 6 — OPTIONAL / EPHEMERAL (Full-mode only; excluded in Lean)
    #    Runtime state, transient caches, and log-only collections.
    # ═════════════════════════════════════════════════════════════════
    {"source": "strategy_status", "target": "strategy_status", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Derivable from strategies + lifecycle_events"},
    {"source": "strategy_lifecycle", "target": "strategy_lifecycle", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Derivable from lifecycle_events"},
    {"source": "readiness_snapshots", "target": "readiness_snapshots", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Point-in-time; rebuilt on next readiness check"},
    {"source": "auto_factory_alert_log", "target": "auto_factory_alert_log", "key": None, "xform": upgrade_passthrough, "tier": "optional"},
    {"source": "auto_maintenance_status", "target": "auto_maintenance_status", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Rebuilt on next maintenance run"},
    {"source": "cadence_state", "target": "cadence_state", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Scheduler runtime state; rebuilds on first tick"},
    {"source": "factory_supervisor_heartbeats", "target": "factory_supervisor_heartbeats", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Supervisor heartbeat telemetry"},
    {"source": "advisory_locks", "target": "advisory_locks", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Runtime lock table; Stage 2 orchestrator rebuilds — migrate ONLY if Stage 2 activation is imminent"},
    {"source": "monitoring_state", "target": "monitoring_state", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Current monitoring snapshot; rebuilt on first cycle"},
    {"source": "monitoring_alert_log", "target": "monitoring_alert_log", "key": None, "xform": upgrade_passthrough, "tier": "optional"},
    {"source": "paper_deviation_alert_log", "target": "paper_deviation_alert_log", "key": None, "xform": upgrade_passthrough, "tier": "optional"},
    {"source": "scaling_nodes", "target": "scaling_nodes", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Node registry rebuilt on heartbeat"},
    {"source": "host_capabilities", "target": "host_capabilities", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Probed on boot"},
    {"source": "ctrader_desktop_state", "target": "ctrader_desktop_state", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Client-side UI state"},
    {"source": "asf_import_log", "target": "asf_import_log", "key": None, "xform": upgrade_passthrough, "tier": "optional"},
    {"source": "post_import_pipeline_log", "target": "post_import_pipeline_log", "key": None, "xform": upgrade_passthrough, "tier": "optional"},
    {"source": "event_continuations", "target": "event_continuations", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Short-lived continuation state; typically expired on new deployment"},
    {"source": "pipeline_logs", "target": "pipeline_logs", "key": None, "xform": upgrade_passthrough, "tier": "optional"},
    {"source": "bi5_cert_sweep_runs", "target": "bi5_cert_sweep_runs", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "BI5 sweep run history; regenerable by next sweep"},
    {"source": "auto_run_cycles", "target": "auto_run_cycles", "key": None, "xform": upgrade_passthrough, "tier": "optional",
     "note": "Auto-run cycle state; rebuilt on first tick"},
    # NOTE: `factory_supervisor_lock` is NOT in the plan — it is PERMANENTLY
    # excluded via INTENTIONALLY_EXCLUDED below to avoid split-brain on the
    # fresh v1.0 host. See migration-profile documentation.
]

# ─────────────────────────────────────────────────────────────────────
# INTENTIONALLY_EXCLUDED — permanent, unconditional exclusion. Applies to
# BOTH lean and full profiles. Nothing in this set is ever migrated,
# regardless of --profile.
#
# `factory_supervisor_lock` is permanently excluded because a stale lock
# document on a fresh v1.0 host would cause the supervisor to split-brain
# on first boot — it must be initialised empty on the new deployment.
# ─────────────────────────────────────────────────────────────────────
INTENTIONALLY_EXCLUDED: "set[str]" = {
    "factory_supervisor_lock",
}

# ─────────────────────────────────────────────────────────────────────
# Migration profiles — which tiers of the plan are executed.
#
#   "lean" (DEFAULT — production deployment)
#       Only tier="critical" is migrated. Business IP, auth, audit,
#       compliance, and hand-curated configuration land in the target.
#       Bulk regenerable datasets (market_data, ticks, spreads, caches)
#       and ephemeral runtime state (locks, heartbeats, transient logs)
#       are skipped and either rebuilt by the platform after boot
#       (BI5 downloader, live spread sweep, mutation sweep, …) or
#       initialised fresh. Typical ETA: minutes.
#
#   "full" (OPT-IN — disaster recovery / exact env replication / archival)
#       All three tiers (critical + regenerable + optional) are
#       migrated. Includes multi-hour datasets like market_data
#       (~313k docs) and market_spread (~309k docs).
#       INTENTIONALLY_EXCLUDED is still honoured.
# ─────────────────────────────────────────────────────────────────────
PROFILE_TIERS: Dict[str, set] = {
    "lean": {"critical"},
    "full": {"critical", "regenerable", "optional"},
}


TARGET_INDEXES = {
    "users": [
        ("email", ASCENDING, {"unique": True, "name": "email_uniq"}),
        ("user_id", ASCENDING, {"unique": True, "name": "user_id_uniq"}),
    ],
    "refresh_tokens": [
        ("jti", ASCENDING, {"unique": True, "name": "jti_uniq"}),
        ("user_id", ASCENDING, {"name": "by_user"}),
        ("expires_at", ASCENDING, {"expireAfterSeconds": 0, "name": "ttl"}),
    ],
    "strategies": [
        ("strategy_id", ASCENDING, {"unique": True, "name": "strategy_id_uniq"}),
        ("created_by", ASCENDING, {"name": "by_creator"}),
        ("created_at", DESCENDING, {"name": "by_created_at"}),
    ],
    "research_queries": [
        ("query_id", ASCENDING, {"unique": True, "name": "query_id_uniq"}),
        ("created_by", ASCENDING, {"name": "by_creator"}),
        ("created_at", DESCENDING, {"name": "by_created_at"}),
    ],
    "audit_log": [
        ("ts_dt", DESCENDING, {"name": "by_ts_dt"}),
    ],
}


# ─────────────────────────────────────────────────────────────────────
# Migration executor
# ─────────────────────────────────────────────────────────────────────


def migrate_collection(
    src_db,
    tgt_db,
    plan_row: Dict[str, Any],
    report: Report,
    dry_run: bool,
    resume: bool = False,
    progress_every: int = 10_000,
    report_path: Optional[str] = None,
) -> None:
    src_name = plan_row["source"]
    tgt_name = plan_row["target"]
    key = plan_row.get("key")
    xform = plan_row["xform"]

    if src_name not in src_db.list_collection_names():
        log.info("  %-28s  (skipped — not present in source)", src_name)
        return

    # Resume: if this collection was already completed in a prior run, skip.
    if resume and not dry_run:
        marker = tgt_db["_migration_progress"].find_one({"source_collection": src_name, "phase": "completed"})
        if marker is not None:
            log.info("  %-28s  (resume — already completed at %s)", src_name, marker.get("finished_at"))
            report.start(src_name, marker.get("source_docs", 0))
            report.collections[src_name]["skipped_already_present"] = marker.get("source_docs", 0)
            report.note(src_name, "resume: marker present, collection skipped")
            return

    src = src_db[src_name]
    tgt = tgt_db[tgt_name]
    source_count = src.count_documents({})

    report.start(src_name, source_count)
    if plan_row.get("note"):
        report.note(src_name, plan_row["note"])

    if source_count == 0:
        log.info("  %-28s  (empty)", src_name)
        _mark_progress(tgt_db, src_name, source_count, "completed", dry_run)
        return

    log.info("  %-28s  → %-24s  (%d docs)", src_name, tgt_name, source_count)

    xform_name = getattr(xform, "__name__", "unknown")
    t0 = time.time()
    processed = 0

    # Use no_cursor_timeout for long collections; iterate lazily via batch_size.
    cursor = src.find({}, no_cursor_timeout=True).batch_size(1000)
    try:
        for doc in cursor:
            processed += 1
            try:
                new_doc, upgraded = xform(doc)
                if new_doc is None:
                    report.collections[src_name]["errors"] += 1
                    report.warnings.append(f"{src_name}: skipped doc _id={doc.get('_id')}")
                    continue

                _stamp(new_doc, doc, src_name, xform_name)

                if upgraded:
                    report.collections[src_name]["upgraded"] += 1

                if dry_run:
                    report.collections[src_name]["migrated"] += 1
                elif key and new_doc.get(key) is not None:
                    fp = new_doc["_migration_meta"]["source_fingerprint"]
                    existing = tgt.find_one(
                        {"$or": [{key: new_doc[key]}, {"_migration_meta.source_fingerprint": fp}]},
                        {"_id": 1},
                    )
                    if existing is not None:
                        report.collections[src_name]["skipped_already_present"] += 1
                    else:
                        try:
                            tgt.insert_one(new_doc)
                            report.collections[src_name]["migrated"] += 1
                        except DuplicateKeyError:
                            report.collections[src_name]["skipped_already_present"] += 1
                else:
                    fp = new_doc["_migration_meta"]["source_fingerprint"]
                    existing = tgt.find_one(
                        {"_migration_meta.source_fingerprint": fp},
                        {"_id": 1},
                    )
                    if existing is not None:
                        report.collections[src_name]["skipped_already_present"] += 1
                    else:
                        try:
                            tgt.insert_one(new_doc)
                            report.collections[src_name]["migrated"] += 1
                        except DuplicateKeyError:
                            report.collections[src_name]["skipped_already_present"] += 1
            except Exception as e:  # noqa: BLE001
                report.collections[src_name]["errors"] += 1
                report.errors.append({
                    "collection": src_name,
                    "doc_id": str(doc.get("_id")),
                    "error": f"{type(e).__name__}: {e}",
                    "traceback": traceback.format_exc(),
                })
                # Continue — per-doc errors do not abort the migration.

            # Periodic checkpoint: log progress + flush report snapshot to disk.
            if processed % progress_every == 0:
                elapsed = time.time() - t0
                rate = processed / elapsed if elapsed > 0 else 0
                col_stats = report.collections[src_name]
                log.info(
                    "    %s  progress %d/%d  (%.0f docs/s)  migrated=%d skipped=%d errors=%d",
                    src_name, processed, source_count, rate,
                    col_stats["migrated"], col_stats["skipped_already_present"], col_stats["errors"],
                )
                _mark_progress(tgt_db, src_name, source_count, "in_progress", dry_run,
                               processed=processed,
                               migrated=col_stats["migrated"],
                               errors=col_stats["errors"])
                if report_path:
                    _flush_report(report, report_path)
    finally:
        try:
            cursor.close()
        except Exception:  # noqa: BLE001
            pass

    _mark_progress(tgt_db, src_name, source_count, "completed", dry_run,
                   processed=processed,
                   migrated=report.collections[src_name]["migrated"],
                   errors=report.collections[src_name]["errors"])


def _mark_progress(tgt_db, src_name: str, source_docs: int, phase: str, dry_run: bool,
                   **extra) -> None:
    """Upsert a progress marker in `_migration_progress` so `--resume` works after interruption."""
    if dry_run:
        return
    try:
        doc = {
            "source_collection": src_name,
            "source_docs": source_docs,
            "phase": phase,
            **extra,
        }
        if phase == "completed":
            doc["finished_at"] = _now()
        else:
            doc["updated_at"] = _now()
        tgt_db["_migration_progress"].update_one(
            {"source_collection": src_name},
            {"$set": doc},
            upsert=True,
        )
    except PyMongoError as e:
        log.warning("  · failed to write progress marker for %s: %s", src_name, e)


def _flush_report(report: "Report", path: str) -> None:
    """Atomically flush the current report snapshot to disk mid-run."""
    try:
        tmp = path + ".partial"
        with open(tmp, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        os.replace(tmp, path)
    except OSError as e:
        log.warning("  · failed to flush partial report: %s", e)


def migrate_unplanned_collections(src_db, tgt_db, report: Report, dry_run: bool,
                                  resume: bool = False,
                                  progress_every: int = 10_000,
                                  report_path: Optional[str] = None) -> None:
    """Catch-all pass-through for collections NOT in MIGRATION_PLAN.

    Guarantees zero-loss even when the production schema contains collections
    the plan didn't anticipate. Every such collection is copied verbatim (with
    `_migration_meta.source_fingerprint` stamped for verification) into a
    target collection of the same name, and a warning is recorded so an
    operator can decide whether the transformer needs bespoke handling later.
    """
    planned = {row["source"] for row in MIGRATION_PLAN}
    src_cols = set(src_db.list_collection_names())
    unplanned = sorted(src_cols - planned - INTENTIONALLY_EXCLUDED)
    if not unplanned:
        return

    log.info("Unplanned collections (auto-passthrough): %s", ", ".join(unplanned))
    for name in unplanned:
        report.warnings.append(f"unplanned collection auto-passthrough: {name}")
        migrate_collection(
            src_db, tgt_db,
            {"source": name, "target": name, "key": None, "xform": upgrade_passthrough,
             "note": "auto-passthrough (not in MIGRATION_PLAN)"},
            report, dry_run,
            resume=resume, progress_every=progress_every, report_path=report_path,
        )


def ensure_target_indexes(tgt_db, dry_run: bool, report: Report, src_db=None) -> None:
    """Rebuild canonical v1.0 indexes AND mirror any source indexes we don't already own."""
    log.info("Ensuring target indexes…")
    # 1) Canonical v1.0 indexes (authoritative for the new schema)
    for col_name, specs in TARGET_INDEXES.items():
        for field, direction, opts in specs:
            desc = f"{col_name}.{field} ({opts.get('name')})"
            if dry_run:
                log.info("  [dry] would ensure %s", desc)
                continue
            try:
                tgt_db[col_name].create_index([(field, direction)], **opts)
                log.info("  ✓ %s", desc)
            except PyMongoError as e:
                report.warnings.append(f"index {desc} failed: {e}")
                log.warning("  ! %s failed: %s", desc, e)

    # 2) Mirror source indexes for every collection (skip _id_ implicit index).
    #    Any conflicting name is skipped gracefully.
    if src_db is None:
        return
    log.info("Mirroring source indexes into target…")
    for col_name in src_db.list_collection_names():
        try:
            src_indexes = list(src_db[col_name].list_indexes())
        except PyMongoError:
            continue
        for ix in src_indexes:
            name = ix.get("name", "")
            if name == "_id_":
                continue
            keys = list(ix.get("key", {}).items())
            if not keys:
                continue
            opts: Dict[str, Any] = {"name": name}
            if ix.get("unique"):
                opts["unique"] = True
            if ix.get("sparse"):
                opts["sparse"] = True
            if "expireAfterSeconds" in ix:
                opts["expireAfterSeconds"] = ix["expireAfterSeconds"]
            if "partialFilterExpression" in ix:
                opts["partialFilterExpression"] = ix["partialFilterExpression"]
            desc = f"{col_name}.{[k for k,_ in keys]} ({name})"
            if dry_run:
                log.info("  [dry] would mirror %s", desc)
                continue
            try:
                tgt_db[col_name].create_index(keys, **opts)
                log.info("  ✓ mirrored %s", desc)
            except PyMongoError as e:
                # A conflicting index of the same name+different spec is not fatal.
                report.warnings.append(f"mirror index {desc} skipped: {e}")
                log.info("  · mirror %s skipped: %s", desc, e)


def preflight(src_db, tgt_db, report: Report) -> None:
    src_cols = sorted(src_db.list_collection_names())
    tgt_cols = sorted(tgt_db.list_collection_names())
    report.source["collections"] = src_cols
    report.source["total_documents"] = sum(src_db[c].estimated_document_count() for c in src_cols)
    report.target["collections_before"] = tgt_cols
    report.target["total_documents_before"] = sum(tgt_db[c].estimated_document_count() for c in tgt_cols)

    log.info("Source DB: %d collections, ~%d total docs", len(src_cols), report.source["total_documents"])
    log.info("Target DB: %d collections, ~%d total docs (before)", len(tgt_cols), report.target["total_documents_before"])


def postflight(tgt_db, report: Report) -> None:
    tgt_cols = sorted(tgt_db.list_collection_names())
    report.target["collections_after"] = tgt_cols
    report.target["total_documents_after"] = sum(tgt_db[c].estimated_document_count() for c in tgt_cols)


def main() -> int:
    ap = argparse.ArgumentParser(description="Strategy Factory Mongo migration")
    ap.add_argument("--source", required=True, help="source Mongo URI (v01 VPS DB)")
    ap.add_argument("--source-db", default="test_database", help="source DB name (v01 default: test_database)")
    ap.add_argument("--target", required=True, help="target Mongo URI (v1.0 canonical)")
    ap.add_argument("--target-db", default="strategy_factory_v1", help="target DB name")
    ap.add_argument("--dry-run", action="store_true", help="report only, no writes")
    ap.add_argument("--report", default="migration-report.json", help="path to write JSON report")
    ap.add_argument("--skip-unplanned", action="store_true",
                    help="do NOT auto-passthrough source collections that are absent from MIGRATION_PLAN (default: auto-passthrough with warning)")
    ap.add_argument("--profile", choices=["lean", "full"], default="lean",
                    help="migration profile: 'lean' (default; production — migrates only tier=critical rows, "
                         "skipping regenerable bulk data and ephemeral runtime state) or 'full' "
                         "(migrates every tier — for disaster-recovery or exact environment replication).")
    ap.add_argument("--resume", action="store_true",
                    help="skip source collections already marked completed in target `_migration_progress`; use to continue an interrupted migration without re-processing already-migrated collections")
    ap.add_argument("--progress-every", type=int, default=10_000,
                    help="log progress + checkpoint report/progress every N docs (default: 10000)")
    args = ap.parse_args()

    report = Report()
    report.dry_run = args.dry_run
    report.source["uri_host"] = _redact(args.source)
    report.source["db"] = args.source_db
    report.target["uri_host"] = _redact(args.target)
    report.target["db"] = args.target_db
    report_path = args.report

    log.info("Strategy Factory migration — %s%s", "DRY RUN" if args.dry_run else "LIVE",
             " (RESUME)" if args.resume else "")
    log.info("source=%s db=%s", report.source["uri_host"], args.source_db)
    log.info("target=%s db=%s", report.target["uri_host"], args.target_db)
    log.info("profile=%s (tiers=%s)", args.profile, sorted(PROFILE_TIERS[args.profile]))
    log.info("report=%s  progress_every=%d", report_path, args.progress_every)
    report.summary["profile"] = args.profile
    report.summary["profile_tiers"] = sorted(PROFILE_TIERS[args.profile])

    # Signal handling: on SIGTERM/SIGINT we want to flush the report and re-raise
    # so the wrapper sees the correct exit code.
    def _sig(signum, _frame):
        log.error("received signal %d — flushing partial report", signum)
        report.warnings.append(f"received signal {signum}; partial report flushed")
        _flush_report(report, report_path)
        raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    try:
        src_client = MongoClient(args.source, serverSelectionTimeoutMS=10000)
        tgt_client = MongoClient(args.target, serverSelectionTimeoutMS=10000)
        src_client.admin.command("ping")
        tgt_client.admin.command("ping")
    except PyMongoError as e:
        log.error("connection failed: %s", e)
        report.errors.append({
            "collection": "<connection>",
            "error": f"PyMongoError: {e}",
            "traceback": traceback.format_exc(),
        })
        _flush_report(report, report_path)
        return 2

    src_db = src_client[args.source_db]
    tgt_db = tgt_client[args.target_db]

    exit_code = 0
    try:
        preflight(src_db, tgt_db, report)

        log.info("Migrating collections…")
        allowed_tiers = PROFILE_TIERS[args.profile]
        for row in MIGRATION_PLAN:
            if row["source"] in INTENTIONALLY_EXCLUDED:
                report.warnings.append(f"{row['source']}: excluded via INTENTIONALLY_EXCLUDED (permanent)")
                log.info("  %-32s  (skipped — permanently excluded)", row["source"])
                continue
            row_tier = row.get("tier", "critical")
            if row_tier not in allowed_tiers:
                report.warnings.append(
                    f"{row['source']}: tier={row_tier} skipped by profile={args.profile}"
                )
                log.info("  %-32s  (skipped — tier=%s not in profile=%s)",
                         row["source"], row_tier, args.profile)
                continue
            migrate_collection(
                src_db, tgt_db, row, report, args.dry_run,
                resume=args.resume,
                progress_every=args.progress_every,
                report_path=report_path,
            )

        if not args.skip_unplanned:
            migrate_unplanned_collections(
                src_db, tgt_db, report, args.dry_run,
                resume=args.resume,
                progress_every=args.progress_every,
                report_path=report_path,
            )

        ensure_target_indexes(tgt_db, args.dry_run, report, src_db=src_db)

        postflight(tgt_db, report)
    except KeyboardInterrupt:
        log.error("migration interrupted by signal — see report")
        report.errors.append({
            "collection": "<runtime>",
            "error": "KeyboardInterrupt",
            "traceback": traceback.format_exc(),
        })
        exit_code = 130
    except Exception as e:  # noqa: BLE001
        # Full traceback into the report AND to stderr so the wrapper's log can see it
        tb = traceback.format_exc()
        log.error("UNCAUGHT EXCEPTION — %s: %s\n%s", type(e).__name__, e, tb)
        report.errors.append({
            "collection": "<runtime>",
            "error": f"{type(e).__name__}: {e}",
            "traceback": tb,
        })
        exit_code = 3

    # Always finalise and flush the report, even on partial failure.
    try:
        report.finish()
        with open(report_path, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        log.info("Report → %s", report_path)
        log.info("Summary: %s", json.dumps(report.summary, indent=2))
    except OSError as e:
        log.error("failed to write final report: %s", e)
        if exit_code == 0:
            exit_code = 4

    if exit_code != 0:
        return exit_code
    if report.errors:
        log.warning("%d hard error(s) occurred; see report.errors", len(report.errors))
        return 1
    return 0


def _redact(uri: str) -> str:
    # hide password in the report
    try:
        if "@" in uri and "://" in uri:
            scheme, rest = uri.split("://", 1)
            if "@" in rest:
                creds, host = rest.split("@", 1)
                if ":" in creds:
                    user = creds.split(":", 1)[0]
                    return f"{scheme}://{user}:***@{host}"
        return uri
    except Exception:  # noqa: BLE001
        return "***"


if __name__ == "__main__":
    sys.exit(main())
