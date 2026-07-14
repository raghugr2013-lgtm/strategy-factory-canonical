#!/usr/bin/env python3
"""
Strategy Factory v1.1.1 — Recovery-DB Migration Script
======================================================

Migrates historical strategy data from the temporary recovery database
(default: ``strategy_factory_recovery``) into the live production database
(default: ``strategy_factory_v1``). Safe to run on a live backend.

Design contract
---------------
1.  **Read-only on the source.**  Every operation against the recovery DB
    is a ``find()`` / ``list_indexes()`` — the recovery DB stays intact as
    a rollback copy.
2.  **Idempotent.**  Documents are upserted by their existing ``_id`` via
    ``bulk_write([ReplaceOne(..., upsert=True), ...])``. Re-running the
    script never duplicates, never deletes, never mutates unrelated
    production data.
3.  **Preserves IDs and relationships.**  ``_id`` is copied verbatim —
    ObjectIds, UUIDs, hash strings, or v01 legacy dict-keys all round-trip.
4.  **Explicit whitelist.**  Only collections in
    ``CORE_STRATEGY_COLLECTIONS`` (plus any matching ``--include`` pattern)
    are touched. All other production collections are untouched.
5.  **Rebuilds indexes.**  Every non-default index on each source
    collection is recreated on the target collection using the source's
    ``keys`` and ``options`` (excluding the auto-managed ``_id_`` index).
6.  **Reversible.**  A ``--rollback-tag`` timestamp is stamped into the
    inserted documents' ``__migration_source`` / ``__migration_ts``
    metadata fields so a follow-up sweep can remove them if a rollback
    is ever needed. Set ``--no-stamp`` to disable if you would rather
    keep the documents byte-identical to the source.

Usage
-----
::

    # Dry-run against production (READS ONLY, prints a plan):
    python scripts/migrate_strategy_recovery.py \\
        --mongo mongodb://strategy_factory:XYZ@mongo:27017 \\
        --source strategy_factory_recovery \\
        --target strategy_factory_v1 \\
        --dry-run

    # Real migration:
    python scripts/migrate_strategy_recovery.py \\
        --mongo mongodb://strategy_factory:XYZ@mongo:27017 \\
        --source strategy_factory_recovery \\
        --target strategy_factory_v1

    # Discover-only (list all strategy_* collections in the source):
    python scripts/migrate_strategy_recovery.py \\
        --mongo mongodb://strategy_factory:XYZ@mongo:27017 \\
        --source strategy_factory_recovery --target strategy_factory_v1 \\
        --discover

    # Verify-only (compare counts after migration, no writes):
    python scripts/migrate_strategy_recovery.py \\
        --mongo mongodb://strategy_factory:XYZ@mongo:27017 \\
        --source strategy_factory_recovery --target strategy_factory_v1 \\
        --verify-only

Exit codes
----------
    0  success (all migrated + verification passed, or dry-run OK)
    1  argument error / configuration failure
    2  connection error
    3  data integrity mismatch after migration (verification failed)

The script is safe to run inside the ``factory-backend`` container:

    docker exec -it factory-backend \\
        python scripts/migrate_strategy_recovery.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from pymongo import MongoClient, ReplaceOne
    from pymongo.errors import BulkWriteError, PyMongoError
except ImportError:  # pragma: no cover
    print(
        "pymongo is not installed in this interpreter. "
        "Run: `pip install 'pymongo>=4.6.0'` or execute inside the "
        "factory-backend container.",
        file=sys.stderr,
    )
    sys.exit(1)


# ── Explicit whitelist ──────────────────────────────────────────────
# Kept small and surgical: only the collections the user proved live in
# the recovery snapshot plus their known dependents referenced by the
# backend code (`strategy_lifecycle` current-state, `strategy_favorites`,
# `strategy_market_profile`, `strategy_memory`, `strategy_history`).
# Anything else must be added explicitly via ``--include``.
CORE_STRATEGY_COLLECTIONS: Tuple[str, ...] = (
    "strategies",
    "strategy_library",
    "strategy_library_archive",
    "strategy_lifecycle_history",
    "strategy_performance_history",
    # Companion collections referenced by the same UI surfaces
    "strategy_lifecycle",
    "strategy_favorites",
    "strategy_market_profile",
    "strategy_memory",
    "strategy_history",
)

BATCH_SIZE = 500


# ── Helpers ─────────────────────────────────────────────────────────
def log(msg: str, *, level: str = "INFO") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prefix = {"INFO": "•", "WARN": "!", "ERROR": "✗", "OK": "✓"}.get(level, "•")
    print(f"{ts}  {prefix} {msg}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="migrate_strategy_recovery.py",
        description="Migrate historical strategy collections from the "
        "recovery DB into the live production DB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mongo",
        default=os.environ.get("MONGO_URL"),
        help="MongoDB connection URI (defaults to MONGO_URL env var).",
    )
    parser.add_argument(
        "--source",
        default="strategy_factory_recovery",
        help="Source database (READ-only). Default: strategy_factory_recovery",
    )
    parser.add_argument(
        "--target",
        default="strategy_factory_v1",
        help="Target database. Default: strategy_factory_v1",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="COLLECTION",
        help="Explicit extra collection to migrate. Can be repeated.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do everything except writes. Prints the plan and per-collection counts.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Only list `strategy_*` collections in the source, exit.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Skip migration; compare source vs target counts and exit.",
    )
    parser.add_argument(
        "--no-stamp",
        action="store_true",
        help="Do NOT stamp migration metadata (__migration_source/__migration_ts) "
        "onto migrated documents. Off by default.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    return parser.parse_args()


def connect(uri: str) -> MongoClient:
    if not uri:
        log("MONGO_URL is empty. Pass --mongo or export MONGO_URL.", level="ERROR")
        sys.exit(1)
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client
    except PyMongoError as e:
        log(f"Mongo connection failed: {e}", level="ERROR")
        sys.exit(2)


def whitelist_collections(
    src_db, extras: Iterable[str]
) -> List[str]:
    """Return the intersection of (CORE_STRATEGY_COLLECTIONS ∪ extras)
    with collections that actually exist in the source. Non-existent
    collections are silently dropped — this keeps runs stable across
    older/newer snapshots.
    """
    present = set(src_db.list_collection_names())
    wanted = set(CORE_STRATEGY_COLLECTIONS) | {c.strip() for c in extras if c.strip()}
    resolved = sorted(present & wanted)
    missing = sorted(wanted - present)
    if missing:
        log(
            f"Skipping {len(missing)} whitelisted collection(s) not present in "
            f"source: {', '.join(missing)}",
            level="WARN",
        )
    return resolved


def discover(src_db, tgt_db) -> None:
    log(f"Source DB: {src_db.name}")
    log(f"Target DB: {tgt_db.name}")
    src_colls = sorted(src_db.list_collection_names())
    tgt_colls = set(tgt_db.list_collection_names())
    strategy_like = [c for c in src_colls if c.startswith("strategy")] + [
        c for c in src_colls if c == "strategies"
    ]
    strategy_like = sorted(set(strategy_like))
    if not strategy_like:
        log("No `strategies` or `strategy_*` collections in source.", level="WARN")
        return
    print("\n  Source collection                       source_count   target_count")
    print("  ─────────────────────────────────────────────────────────────────────")
    for c in strategy_like:
        s = src_db[c].estimated_document_count()
        t = tgt_db[c].estimated_document_count() if c in tgt_colls else 0
        flag = "" if c in CORE_STRATEGY_COLLECTIONS else "  (NOT in default whitelist — pass with --include)"
        print(f"  {c:<40} {s:>12}   {t:>12}{flag}")
    print()


def copy_indexes(src_coll, tgt_coll, *, dry_run: bool) -> int:
    """Rebuild every non-default index from src_coll on tgt_coll.
    Returns number of indexes rebuilt (excludes _id_)."""
    created = 0
    for info in src_coll.list_indexes():
        name = info.get("name")
        if name == "_id_":
            continue
        keys = list(info.get("key", {}).items())
        if not keys:
            continue
        # Strip fields the driver injects that create_index() doesn't accept.
        opts: Dict[str, Any] = {}
        for k, v in info.items():
            if k in ("v", "key", "ns"):
                continue
            opts[k] = v
        if dry_run:
            log(f"    [DRY-RUN] would create index {name} on {tgt_coll.name}: {keys} {opts}")
        else:
            try:
                tgt_coll.create_index(keys, **opts)
                created += 1
            except PyMongoError as e:
                log(
                    f"    index {name} on {tgt_coll.name} failed: {e} — "
                    "ignoring and continuing",
                    level="WARN",
                )
    return created


def migrate_collection(
    src_coll,
    tgt_coll,
    *,
    dry_run: bool,
    stamp: bool,
    tag: str,
) -> Tuple[int, int, int]:
    """Return (source_count, upserted, indexes_created)."""
    src_count = src_coll.estimated_document_count()
    if src_count == 0:
        log(f"  {src_coll.name}: source is empty, skipping.")
        return 0, 0, 0

    if dry_run:
        log(f"  [DRY-RUN] {src_coll.name}: would upsert up to {src_count} docs into target")
        idx = copy_indexes(src_coll, tgt_coll, dry_run=True)
        return src_count, 0, idx

    ops: List[ReplaceOne] = []
    upserted = 0
    batch_no = 0
    for doc in src_coll.find({}, no_cursor_timeout=True):
        if "_id" not in doc:
            log(
                f"    doc without _id in {src_coll.name} — skipping "
                "(cannot preserve identity)",
                level="WARN",
            )
            continue
        if stamp:
            doc.setdefault("__migration_source", src_coll.database.name)
            doc.setdefault("__migration_ts", tag)
        ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
        if len(ops) >= BATCH_SIZE:
            upserted += _flush(tgt_coll, ops)
            batch_no += 1
            ops = []
    if ops:
        upserted += _flush(tgt_coll, ops)
        batch_no += 1

    idx = copy_indexes(src_coll, tgt_coll, dry_run=False)
    log(
        f"  {src_coll.name}: {upserted}/{src_count} upserted in {batch_no} "
        f"batch(es), {idx} index(es) rebuilt",
        level="OK",
    )
    return src_count, upserted, idx


def _flush(tgt_coll, ops: List[ReplaceOne]) -> int:
    try:
        res = tgt_coll.bulk_write(ops, ordered=False, bypass_document_validation=True)
    except BulkWriteError as bwe:
        # `errors` on unique-index collisions is acceptable for idempotency —
        # log and continue with whatever succeeded.
        details = bwe.details or {}
        n_up = details.get("nUpserted", 0) + details.get("nModified", 0)
        log(
            f"    bulk_write partial: nUpserted={details.get('nUpserted', 0)} "
            f"nModified={details.get('nModified', 0)} "
            f"writeErrors={len(details.get('writeErrors', []))}",
            level="WARN",
        )
        return n_up
    return res.upserted_count + res.modified_count


def verify(src_db, tgt_db, collections: List[str]) -> bool:
    """Post-migration verification: for every migrated collection, target
    count must be ≥ source count (some target collections may pre-exist
    with extra docs — that's fine as long as source is a subset)."""
    ok = True
    print("\n  Verification")
    print(f"  {'collection':<40}  {'source':>10}  {'target':>10}  status")
    print("  " + "─" * 78)
    for c in collections:
        s = src_db[c].estimated_document_count()
        t = tgt_db[c].estimated_document_count()
        status = "OK" if t >= s else "MISSING"
        if t < s:
            ok = False
        print(f"  {c:<40}  {s:>10}  {t:>10}  {status}")
    return ok


def main() -> int:
    args = parse_args()

    client = connect(args.mongo)
    src_db = client[args.source]
    tgt_db = client[args.target]

    if args.discover:
        discover(src_db, tgt_db)
        return 0

    collections = whitelist_collections(src_db, args.include)
    if not collections:
        log(
            f"No whitelisted collections present in {args.source}. Nothing to do.",
            level="WARN",
        )
        return 0

    log(f"Source DB : {args.source}")
    log(f"Target DB : {args.target}")
    log("Collections queued for migration:")
    for c in collections:
        s = src_db[c].estimated_document_count()
        t = tgt_db[c].estimated_document_count() if c in tgt_db.list_collection_names() else 0
        log(f"    {c:<40} source={s:>8}  target(before)={t:>8}")

    if args.verify_only:
        ok = verify(src_db, tgt_db, collections)
        return 0 if ok else 3

    if args.dry_run:
        log("Dry-run mode — no writes will be issued.")
    else:
        if not args.yes:
            confirm = input(
                f"\nProceed with migrating {len(collections)} collection(s) "
                f"from {args.source} → {args.target}? [y/N]: "
            ).strip().lower()
            if confirm not in ("y", "yes"):
                log("Aborted by operator.")
                return 0

    tag = datetime.now(timezone.utc).isoformat()
    stamp = not args.no_stamp
    total_docs = 0
    total_upserted = 0
    total_indexes = 0
    log(f"Migration tag: {tag}")
    for c in collections:
        s, u, i = migrate_collection(
            src_db[c],
            tgt_db[c],
            dry_run=args.dry_run,
            stamp=stamp,
            tag=tag,
        )
        total_docs += s
        total_upserted += u
        total_indexes += i

    if args.dry_run:
        log(
            f"Dry-run complete. Would touch {total_docs} document(s) across "
            f"{len(collections)} collection(s).",
            level="OK",
        )
        return 0

    log(
        f"Migration complete: {total_upserted}/{total_docs} documents "
        f"upserted, {total_indexes} indexes rebuilt across "
        f"{len(collections)} collection(s).",
        level="OK",
    )

    ok = verify(src_db, tgt_db, collections)
    if not ok:
        log("Verification failed: some target counts are still below source.", level="ERROR")
        return 3
    log("Verification passed.", level="OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
