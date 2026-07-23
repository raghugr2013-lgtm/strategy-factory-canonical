#!/usr/bin/env python3
"""
HKB Historical Knowledge Base — Production Migration Driver
============================================================

Executes the operator-approved migration of the 1-vCPU export bundle into
the production Strategy Factory Canonical database, applying the
provenance metadata required by the operator (2026-07-23):

    __migration_source    = 'hkb-1vcpu-20260611'
    __migration_timestamp = ISO-8601 UTC of this run
    __migration_version   = '1.0'
    __legacy              = True

Idempotent (upsert by _id). Feature Freeze v1.1.0-stage4 preserved — this
is a data load, no backend engine change.

STAGES
------
  1. WHITELISTED  — 22 collections, 19,773 docs, byte-compatible
  2. MARKET_DATA  — 1,053,512 rows OHLCV corpus
  3. GOVERNANCE_LEGACY — archive legacy governance_universe → governance_universe_legacy
  4. VERIFY       — reconcile source/target counts

Every document written also carries a canonical `_id`; upsert never
duplicates on re-run. Legacy `users` intentionally excluded.
"""
from __future__ import annotations
import os, sys, json, argparse, datetime as dt
from pymongo import MongoClient, ReplaceOne, ASCENDING

MIGRATION_SOURCE    = "hkb-1vcpu-20260611"
MIGRATION_VERSION   = "1.0"

# 22 whitelisted, non-market_data, non-conflict collections
WHITELIST = [
    "auto_factory_alert_log", "auto_mutation_cycles", "auto_mutation_runs",
    "auto_run_cycles", "challenge_rules", "ingested_strategies", "ingestion_runs",
    "llm_call_log", "market_environment_stats", "multi_cycle_runs",
    "mutation_events", "mutation_runs", "mutation_stability_log",
    "orchestrator_env_priority", "pipeline_logs", "prop_firm_rules",
    "research_runs", "strategy_library", "strategy_lifecycle",
    "strategy_lifecycle_history", "strategy_market_profile",
    "strategy_performance_history",
]

MARKET_DATA_COLLECTION = "market_data"


def stamp(doc: dict, ts_iso: str) -> dict:
    """Append the four provenance fields required by the operator."""
    doc["__migration_source"]    = MIGRATION_SOURCE
    doc["__migration_timestamp"] = ts_iso
    doc["__migration_version"]   = MIGRATION_VERSION
    doc["__legacy"]              = True
    return doc


def migrate_collection(src, tgt, cname: str, ts_iso: str, batch_size: int = 1000):
    src_col = src[cname]
    tgt_col = tgt[cname]
    total = src_col.estimated_document_count()
    print(f"  {cname:35s} src={total:>10,}  ", end="", flush=True)
    if total == 0:
        print("(empty, skipped)")
        return {"cname": cname, "src": 0, "written": 0, "skipped_empty": True}

    written = 0
    ops: list = []
    for doc in src_col.find({}, no_cursor_timeout=True):
        stamp(doc, ts_iso)
        ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
        if len(ops) >= batch_size:
            tgt_col.bulk_write(ops, ordered=False)
            written += len(ops)
            ops = []
    if ops:
        tgt_col.bulk_write(ops, ordered=False)
        written += len(ops)
    tgt_count = tgt_col.estimated_document_count()
    print(f"→ tgt={tgt_count:>10,}  written={written:>10,}")
    return {"cname": cname, "src": total, "written": written, "tgt": tgt_count}


def recreate_indexes(src, tgt, cname: str):
    """Copy any non-_id indexes from source to target."""
    idx_created = []
    for spec in src[cname].list_indexes():
        name = spec.get("name")
        if not name or name == "_id_":
            continue
        keys = list(spec.get("key", {}).items())
        try:
            tgt[cname].create_index(
                keys,
                name=name,
                unique=spec.get("unique", False),
                sparse=spec.get("sparse", False),
                background=True,
            )
            idx_created.append(f"{cname}.{name}")
        except Exception as e:
            print(f"    · index {cname}.{name} already exists / skipped ({e})")
    if idx_created:
        print(f"    · indexes recreated: {', '.join(idx_created)}")
    return idx_created


def archive_governance_legacy(src, tgt, ts_iso: str):
    """Move the legacy governance_universe doc into governance_universe_legacy."""
    src_doc = src.governance_universe.find_one()
    if not src_doc:
        print("  (no legacy governance_universe found — skipped)")
        return None
    # rename the _id so it never collides with the prod config doc
    src_doc["_id"] = f"config_legacy_{MIGRATION_SOURCE}"
    stamp(src_doc, ts_iso)
    tgt.governance_universe_legacy.replace_one({"_id": src_doc["_id"]}, src_doc, upsert=True)
    print(f"  archived → governance_universe_legacy._id={src_doc['_id']}")
    return src_doc["_id"]


def verify(src, tgt, cnames: list) -> dict:
    print("\n=== VERIFY ===")
    ok = True
    report = {"collections": {}, "provenance": {}}
    for c in cnames:
        s = src[c].estimated_document_count()
        t = tgt[c].estimated_document_count()
        prov = tgt[c].count_documents({"__migration_source": MIGRATION_SOURCE})
        report["collections"][c] = {"src": s, "tgt": t, "provenance_stamped": prov}
        status = "OK" if t >= s and prov >= s else "MISMATCH"
        if status != "OK":
            ok = False
        print(f"  {c:35s} src={s:>10,}  tgt={t:>10,}  stamped={prov:>10,}  [{status}]")
    report["all_ok"] = ok
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", required=True)
    ap.add_argument("--source", default="hkb_staging_20260723")
    ap.add_argument("--target", default="strategy_factory_v1")
    ap.add_argument("--skip-market-data", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = MongoClient(args.mongo)
    src = client[args.source]
    tgt = client[args.target]
    ts_iso = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    print(f"HKB Migration · source={args.source} · target={args.target}")
    print(f"provenance ts={ts_iso}\n")
    if args.dry_run:
        print("DRY RUN — no writes performed. Would migrate:")
        for c in WHITELIST:
            print(f"  {c:35s} src={src[c].estimated_document_count():>10,}")
        if not args.skip_market_data:
            print(f"  {MARKET_DATA_COLLECTION:35s} src={src[MARKET_DATA_COLLECTION].estimated_document_count():>10,}")
        return

    per_collection = []

    print("── STAGE 1: whitelist ────────────────────────────────────────")
    for c in WHITELIST:
        r = migrate_collection(src, tgt, c, ts_iso)
        per_collection.append(r)
        recreate_indexes(src, tgt, c)

    if not args.skip_market_data:
        print("\n── STAGE 2: market_data (bulk) ────────────────────────────")
        r = migrate_collection(src, tgt, MARKET_DATA_COLLECTION, ts_iso, batch_size=5000)
        per_collection.append(r)
        recreate_indexes(src, tgt, MARKET_DATA_COLLECTION)

    print("\n── STAGE 3: governance_universe_legacy archive ────────────")
    legacy_id = archive_governance_legacy(src, tgt, ts_iso)

    print("\n── STAGE 4: verify ────────────────────────────────────────")
    cnames = list(WHITELIST) + ([] if args.skip_market_data else [MARKET_DATA_COLLECTION])
    verify_report = verify(src, tgt, cnames)

    # Write report
    report = {
        "migration_source":    MIGRATION_SOURCE,
        "migration_timestamp": ts_iso,
        "migration_version":   MIGRATION_VERSION,
        "source_db":  args.source,
        "target_db":  args.target,
        "governance_legacy_id": legacy_id,
        "per_collection": per_collection,
        "verify_report": verify_report,
    }
    out_path = f"/app/hkb/reports/migration_run_{ts_iso.replace(':','').replace('-','')}.json"
    json.dump(report, open(out_path, "w"), indent=2, default=str)
    print(f"\nreport → {out_path}")
    print("DONE" if verify_report["all_ok"] else "COMPLETE WITH MISMATCHES — inspect the verify report")


if __name__ == "__main__":
    main()
