#!/usr/bin/env python3
"""Strategy Factory — VPS MongoDB Audit Utility.

Read-only inspection of the existing (v01) VPS MongoDB. Produces:

  1. A structured JSON report (machine-readable, feeds validate-migration.py)
  2. A human-readable Markdown report (drop into ops share / PR / ticket)

What it captures per DB:
  * every collection name
  * document count (exact)
  * approximate size / storage size / avg doc size
  * every index (with unique / TTL / partial flags)
  * a sample document (redacted for password_hash / api_key fields)
  * inferred "purpose" from a curated catalogue (users, strategies, …)
  * inferred relationships (foreign-key style references between collections)
  * domain roll-ups:
      - users:            total / by_role / by_status
      - strategies:       total / by_status / by_created_by (top 10)
      - research_queries: total / by_provider
      - validations:      total  (union of validation_reports + backtest_results)
      - config:           settings / prop_firm_* / governance_* rolled up

The utility is strictly read-only. It never writes to the source DB.

Usage (inside the VPS, next to the v01 Mongo):

    docker run --rm --network vqb-network -v "$(pwd):/work" -w /work \\
      python:3.12-slim sh -c "\\
        pip install -q pymongo==4.9.2 && \\
        python infra/scripts/audit-vps-db.py \\
          --source \"$SOURCE_MONGO_URL\" --source-db test_database \\
          --out-json /work/audit-report.json \\
          --out-md   /work/audit-report.md"

Exit codes: 0 = ok, 2 = connection failure.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError
except ImportError:
    sys.stderr.write("error: pymongo not installed. Run: pip install pymongo==4.9.2\n")
    sys.exit(2)


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("audit")


# ─────────────────────────────────────────────────────────────────────
# Curated catalogue: known Strategy Factory collections and their purpose.
# Anything NOT in this catalogue is reported as "unknown — needs classification".
# ─────────────────────────────────────────────────────────────────────
COLLECTION_CATALOGUE: Dict[str, Dict[str, Any]] = {
    # ── identity & auth ─────────────────────────────────────────────
    "users":            {"category": "identity",   "purpose": "Registered platform users (auth, RBAC)."},
    "refresh_tokens":   {"category": "identity",   "purpose": "JWT refresh-token rotation store (TTL indexed)."},
    "audit_log":        {"category": "identity",   "purpose": "Audit trail of user actions and admin events."},
    # ── core strategy engineering ──────────────────────────────────
    "strategies":       {"category": "strategy",   "purpose": "Canonical strategy definitions (IR, symbol, timeframe, metadata)."},
    "strategy_library": {"category": "strategy",   "purpose": "v01 cohort library (14 migrated strategies) — merged into `strategies` in v1.0."},
    "strategy_versions": {"category": "strategy",  "purpose": "Version history of strategy edits (Stage 2 dossier)."},
    "strategy_memory":  {"category": "strategy",   "purpose": "Long-lived per-strategy memory timeline (Stage 2 improvement engine)."},
    "lifecycle_events": {"category": "strategy",   "purpose": "Strategy lifecycle transitions (draft → validated → deployed)."},
    "mutation_pool":    {"category": "strategy",   "purpose": "Mutation candidates produced by the optimisation / improvement engines."},
    # ── research ────────────────────────────────────────────────────
    "research_lineage": {"category": "research",   "purpose": "v01 research lineage — renamed to `research_queries` in v1.0."},
    "research_queries": {"category": "research",   "purpose": "AI research queries (prompt, provider, response, created_by)."},
    # ── validation & backtesting ────────────────────────────────────
    "validation_reports": {"category": "validation", "purpose": "Walk-forward / Monte-Carlo / robustness reports."},
    "backtest_results":   {"category": "validation", "purpose": "Raw backtest artefacts (equity curves, metrics)."},
    "readiness_snapshots": {"category": "validation", "purpose": "Readiness gating snapshots (BI5/prop-firm/health)."},
    "bi5_certifications":  {"category": "validation", "purpose": "BI5 tick-data provenance certifications."},
    "survivor_registry":   {"category": "validation", "purpose": "Strategies that survived tightening cycles (Stage 2)."},
    # ── bots & exports ──────────────────────────────────────────────
    "master_bots":         {"category": "bots",       "purpose": "Master-bot definitions (multi-strategy composite bots)."},
    "master_bot_exports":  {"category": "bots",       "purpose": "Exported bot packages (ASF, MT4/5, cTrader)."},
    "portfolio_definitions": {"category": "bots",     "purpose": "Portfolio-level strategy compositions."},
    # ── market & governance ─────────────────────────────────────────
    "market_universe":      {"category": "market",    "purpose": "Symbol universe and metadata."},
    "market_intelligence":  {"category": "market",    "purpose": "Market intelligence signals / news / regimes."},
    "governance_universe":  {"category": "governance", "purpose": "Governance rules for symbol/timeframe permissioning."},
    "prop_firm_configs":    {"category": "governance", "purpose": "Prop-firm account configurations."},
    "prop_firm_rules":      {"category": "governance", "purpose": "Prop-firm rule sets (drawdown/consistency/etc)."},
    # ── config ──────────────────────────────────────────────────────
    "settings":             {"category": "config",     "purpose": "Key/value platform settings (upserted on `key`)."},
}


# Fields that must be masked in sample docs (secrets / PII).
REDACT_FIELDS = ("password_hash", "password", "api_key", "apikey", "secret", "token", "refresh_token", "bearer")


def _redact(doc: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "…"
    if isinstance(doc, dict):
        out = {}
        for k, v in doc.items():
            lk = str(k).lower()
            if any(rf in lk for rf in REDACT_FIELDS):
                out[k] = "***REDACTED***"
            elif k == "_id":
                out[k] = str(v)
            else:
                out[k] = _redact(v, depth + 1)
        return out
    if isinstance(doc, list):
        return [_redact(x, depth + 1) for x in doc[:5]] + (["…"] if len(doc) > 5 else [])
    if isinstance(doc, datetime):
        return doc.isoformat()
    try:
        json.dumps(doc)
        return doc
    except (TypeError, ValueError):
        return str(doc)


def _stringify(doc: Any) -> Any:
    """Recursively convert BSON/ObjectId/datetime to JSON-safe primitives (no redaction)."""
    if isinstance(doc, dict):
        return {str(k): _stringify(v) for k, v in doc.items()}
    if isinstance(doc, list):
        return [_stringify(x) for x in doc]
    if isinstance(doc, datetime):
        return doc.isoformat()
    try:
        json.dumps(doc)
        return doc
    except (TypeError, ValueError):
        return str(doc)


def _redact_uri(uri: str) -> str:
    try:
        if "@" in uri and "://" in uri:
            scheme, rest = uri.split("://", 1)
            if "@" in rest:
                creds, host = rest.split("@", 1)
                user = creds.split(":", 1)[0]
                return f"{scheme}://{user}:***@{host}"
        return uri
    except Exception:  # noqa: BLE001
        return "***"


# ─────────────────────────────────────────────────────────────────────
# Relationship inference
# ─────────────────────────────────────────────────────────────────────
FK_HINTS = (
    "user_id", "strategy_id", "query_id", "bot_id", "portfolio_id",
    "backtest_id", "validation_id", "created_by", "owner",
)


def infer_relationships(db, collections: List[str], sample_size: int = 20) -> List[Dict[str, str]]:
    """For each collection, scan a small sample and record fields that look like FKs into other collections."""
    rels: List[Dict[str, str]] = []
    for col in collections:
        keys: Counter = Counter()
        for doc in db[col].find({}, limit=sample_size):
            for k in doc.keys():
                lk = str(k).lower()
                for hint in FK_HINTS:
                    if lk == hint or lk.endswith("_" + hint) or lk.endswith(hint):
                        keys[k] += 1
                        break
        for k, cnt in keys.most_common():
            target = _guess_target_collection(k, collections)
            rels.append({"from": col, "field": k, "likely_target": target or "?", "sample_hits": cnt})
    return rels


def _guess_target_collection(field: str, collections: List[str]) -> Optional[str]:
    lf = field.lower()
    if lf in ("user_id", "created_by", "owner") and "users" in collections:
        return "users"
    if lf in ("strategy_id", "strategyid"):
        for c in ("strategies", "strategy_library"):
            if c in collections:
                return c
    if lf.startswith("query_"):
        for c in ("research_queries", "research_lineage"):
            if c in collections:
                return c
    if lf.startswith("bot_"):
        if "master_bots" in collections:
            return "master_bots"
    if lf.startswith("portfolio_"):
        if "portfolio_definitions" in collections:
            return "portfolio_definitions"
    if lf.startswith("backtest_"):
        if "backtest_results" in collections:
            return "backtest_results"
    if lf.startswith("validation_"):
        if "validation_reports" in collections:
            return "validation_reports"
    return None


# ─────────────────────────────────────────────────────────────────────
# Per-collection audit
# ─────────────────────────────────────────────────────────────────────
def audit_collection(db, col_name: str) -> Dict[str, Any]:
    col = db[col_name]
    try:
        stats = db.command("collStats", col_name)
    except PyMongoError:
        stats = {}

    doc_count = col.count_documents({})
    indexes = []
    for ix in col.list_indexes():
        ix_info = _stringify(ix)
        indexes.append({
            "name": ix_info.get("name"),
            "key": ix_info.get("key"),
            "unique": bool(ix_info.get("unique", False)),
            "expireAfterSeconds": ix_info.get("expireAfterSeconds"),
            "partialFilterExpression": ix_info.get("partialFilterExpression"),
        })

    sample_docs = [_redact(d) for d in col.find({}, limit=3)]
    field_set: Counter = Counter()
    for d in col.find({}, limit=100):
        for k in d.keys():
            field_set[k] += 1

    catalogue = COLLECTION_CATALOGUE.get(col_name, {"category": "unknown", "purpose": "Unknown — not in Strategy Factory catalogue."})

    return {
        "name": col_name,
        "category": catalogue["category"],
        "purpose": catalogue["purpose"],
        "document_count": doc_count,
        "size_bytes": stats.get("size", 0),
        "storage_size_bytes": stats.get("storageSize", 0),
        "avg_obj_size_bytes": stats.get("avgObjSize", 0),
        "indexes": indexes,
        "top_fields": [{"field": f, "seen_in_docs": c} for f, c in field_set.most_common(15)],
        "sample_documents": sample_docs,
    }


# ─────────────────────────────────────────────────────────────────────
# Domain roll-ups
# ─────────────────────────────────────────────────────────────────────
def _rollup_users(db) -> Dict[str, Any]:
    if "users" not in db.list_collection_names():
        return {"present": False}
    col = db["users"]
    by_role: Counter = Counter()
    by_status: Counter = Counter()
    for d in col.find({}, {"role": 1, "status": 1}):
        by_role[str(d.get("role") or "unknown")] += 1
        by_status[str(d.get("status") or "unknown")] += 1
    return {
        "present": True,
        "total": col.count_documents({}),
        "by_role": dict(by_role),
        "by_status": dict(by_status),
    }


def _rollup_strategies(db) -> Dict[str, Any]:
    present_cols = [c for c in ("strategies", "strategy_library") if c in db.list_collection_names()]
    if not present_cols:
        return {"present": False}
    total = 0
    by_status: Counter = Counter()
    by_creator: Counter = Counter()
    for c in present_cols:
        for d in db[c].find({}, {"status": 1, "created_by": 1, "owner": 1}):
            total += 1
            by_status[str(d.get("status") or "unknown")] += 1
            creator = d.get("created_by") or d.get("owner") or "unknown"
            by_creator[str(creator)] += 1
    return {
        "present": True,
        "source_collections": present_cols,
        "total": total,
        "by_status": dict(by_status),
        "top_creators": dict(by_creator.most_common(10)),
    }


def _rollup_research(db) -> Dict[str, Any]:
    present_cols = [c for c in ("research_queries", "research_lineage") if c in db.list_collection_names()]
    if not present_cols:
        return {"present": False}
    total = 0
    by_provider: Counter = Counter()
    for c in present_cols:
        for d in db[c].find({}, {"provider": 1, "model_provider": 1}):
            total += 1
            prov = d.get("provider") or d.get("model_provider") or "unknown"
            by_provider[str(prov)] += 1
    return {
        "present": True,
        "source_collections": present_cols,
        "total": total,
        "by_provider": dict(by_provider),
    }


def _rollup_validation(db) -> Dict[str, Any]:
    cols = [c for c in ("validation_reports", "backtest_results", "readiness_snapshots", "bi5_certifications", "survivor_registry")
            if c in db.list_collection_names()]
    if not cols:
        return {"present": False}
    return {
        "present": True,
        "collections": {c: db[c].count_documents({}) for c in cols},
    }


def _rollup_config(db) -> Dict[str, Any]:
    cols = [c for c in ("settings", "prop_firm_configs", "prop_firm_rules", "governance_universe", "market_universe", "market_intelligence")
            if c in db.list_collection_names()]
    if not cols:
        return {"present": False}
    return {
        "present": True,
        "collections": {c: db[c].count_documents({}) for c in cols},
    }


# ─────────────────────────────────────────────────────────────────────
# Markdown formatter
# ─────────────────────────────────────────────────────────────────────
def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# VPS Database Audit Report")
    lines.append("")
    lines.append(f"* Generated: `{report['generated_at']}`")
    lines.append(f"* Source URI: `{report['source']['uri']}`")
    lines.append(f"* Database: `{report['source']['db']}`")
    lines.append(f"* Collections: **{len(report['collections'])}**")
    lines.append(f"* Total documents: **{report['totals']['documents']:,}**")
    lines.append(f"* Total storage: **{report['totals']['storage_size_bytes']:,} bytes**")
    lines.append("")

    lines.append("## Domain roll-ups")
    lines.append("")
    for label, data in [
        ("Users", report["domain"]["users"]),
        ("Strategies", report["domain"]["strategies"]),
        ("Research", report["domain"]["research"]),
        ("Validation & backtesting", report["domain"]["validation"]),
        ("Config & governance", report["domain"]["config"]),
    ]:
        lines.append(f"### {label}")
        if not data.get("present"):
            lines.append("_Not present in source database._")
        else:
            lines.append("```json")
            lines.append(json.dumps(data, indent=2, default=str))
            lines.append("```")
        lines.append("")

    lines.append("## Collections")
    lines.append("")
    lines.append("| Collection | Category | Documents | Indexes | Purpose |")
    lines.append("|---|---|---:|---:|---|")
    for c in sorted(report["collections"], key=lambda x: (-x["document_count"], x["name"])):
        lines.append(f"| `{c['name']}` | {c['category']} | {c['document_count']:,} | {len(c['indexes'])} | {c['purpose']} |")
    lines.append("")

    unknown = [c for c in report["collections"] if c["category"] == "unknown"]
    if unknown:
        lines.append("## ⚠ Collections not in the Strategy Factory catalogue")
        lines.append("")
        lines.append("These collections were found in the source DB but are **not** in the canonical Strategy Factory catalogue. They will not be migrated by the default migration plan and require classification before deployment.")
        lines.append("")
        for c in unknown:
            lines.append(f"* `{c['name']}` — {c['document_count']:,} docs")
        lines.append("")
        lines.append("**Action:** for each collection above, add a row to `MIGRATION_PLAN` in `infra/scripts/migrate-data.py` (`upgrade_passthrough` is usually sufficient if the schema will be consumed as-is by Stage 2).")
        lines.append("")

    lines.append("## Inferred relationships")
    lines.append("")
    lines.append("| From | Field | Likely target |")
    lines.append("|---|---|---|")
    for r in report["relationships"]:
        lines.append(f"| `{r['from']}` | `{r['field']}` | `{r['likely_target']}` |")
    lines.append("")

    lines.append("## Per-collection detail")
    lines.append("")
    for c in sorted(report["collections"], key=lambda x: x["name"]):
        lines.append(f"### `{c['name']}` ({c['category']})")
        lines.append(f"* {c['document_count']:,} documents · {c['size_bytes']:,} bytes · {len(c['indexes'])} indexes")
        lines.append(f"* Purpose: {c['purpose']}")
        if c["indexes"]:
            lines.append("* Indexes:")
            for ix in c["indexes"]:
                extras: List[str] = []
                if ix["unique"]:
                    extras.append("unique")
                if ix["expireAfterSeconds"] is not None:
                    extras.append(f"ttl={ix['expireAfterSeconds']}s")
                extra = " · " + " · ".join(extras) if extras else ""
                lines.append(f"  * `{ix['name']}` on `{ix['key']}`{extra}")
        if c["top_fields"]:
            lines.append("* Top fields (from 100-doc sample): " + ", ".join(f"`{f['field']}`" for f in c["top_fields"]))
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Strategy Factory VPS Mongo audit (read-only)")
    ap.add_argument("--source", required=True, help="source Mongo URI (v01 VPS DB)")
    ap.add_argument("--source-db", default="test_database", help="source DB name")
    ap.add_argument("--out-json", default="audit-report.json", help="JSON report output path")
    ap.add_argument("--out-md", default="audit-report.md", help="Markdown report output path")
    args = ap.parse_args()

    log.info("Strategy Factory VPS audit — source=%s db=%s", _redact_uri(args.source), args.source_db)

    try:
        client = MongoClient(args.source, serverSelectionTimeoutMS=10000)
        client.admin.command("ping")
    except PyMongoError as e:
        log.error("connection failed: %s", e)
        return 2

    db = client[args.source_db]
    collection_names = sorted(db.list_collection_names())
    log.info("Found %d collections", len(collection_names))

    collections_report: List[Dict[str, Any]] = []
    total_docs = 0
    total_storage = 0
    for name in collection_names:
        log.info("  auditing %s", name)
        c = audit_collection(db, name)
        collections_report.append(c)
        total_docs += c["document_count"]
        total_storage += c["storage_size_bytes"]

    rels = infer_relationships(db, collection_names)

    domain = {
        "users":      _rollup_users(db),
        "strategies": _rollup_strategies(db),
        "research":   _rollup_research(db),
        "validation": _rollup_validation(db),
        "config":     _rollup_config(db),
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"uri": _redact_uri(args.source), "db": args.source_db},
        "totals": {"collections": len(collection_names), "documents": total_docs, "storage_size_bytes": total_storage},
        "domain": domain,
        "collections": collections_report,
        "relationships": rels,
        "unknown_collections": [c["name"] for c in collections_report if c["category"] == "unknown"],
    }

    with open(args.out_json, "w") as f:
        json.dump(report, f, indent=2, default=str)
    with open(args.out_md, "w") as f:
        f.write(render_markdown(report))

    log.info("JSON → %s", args.out_json)
    log.info("MD   → %s", args.out_md)
    log.info("collections=%d  documents=%d  unknown=%d",
             len(collection_names), total_docs, len(report["unknown_collections"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
