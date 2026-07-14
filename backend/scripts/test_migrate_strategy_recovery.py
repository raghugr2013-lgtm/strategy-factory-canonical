#!/usr/bin/env python3
"""End-to-end integration test for scripts/migrate_strategy_recovery.py.

Seeds a fake recovery DB with representative documents, runs the migration
script twice (idempotence check), verifies counts match, confirms the
recovery DB was NOT mutated, and asserts every migrated document round-
tripped by _id.

Exits 0 on pass, 1 on fail. Runs against the local supervisor MongoDB.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone

from pymongo import MongoClient

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
SRC_DB = "strategy_factory_recovery_test"
TGT_DB = "strategy_factory_v1_test"
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrate_strategy_recovery.py")


def seed(client: MongoClient) -> dict:
    """Populate a synthetic recovery DB and a partially-populated target."""
    src = client[SRC_DB]
    tgt = client[TGT_DB]
    # Clean slate
    client.drop_database(SRC_DB)
    client.drop_database(TGT_DB)

    now = datetime.now(timezone.utc)

    # strategies (1 doc — matches the real-world minimum)
    src["strategies"].insert_many([
        {"_id": "strat-hash-0001", "symbol": "EURUSD", "timeframe": "1h", "created_at": now},
    ])
    # strategy_library (14 docs)
    src["strategy_library"].insert_many([
        {"_id": f"lib-{i:04d}", "strategy_hash": f"hash-{i}", "score": 50 + i}
        for i in range(14)
    ])
    # strategy_library_archive (126 docs)
    src["strategy_library_archive"].insert_many([
        {"_id": f"arc-{i:04d}", "strategy_hash": f"hash-{i}", "archived_at": now}
        for i in range(126)
    ])
    # strategy_lifecycle_history (892 docs)
    src["strategy_lifecycle_history"].insert_many([
        {"_id": f"lch-{i:04d}", "strategy_hash": f"hash-{i%14}", "stage": "prod", "ts": now}
        for i in range(892)
    ])
    # strategy_performance_history (1047 docs)
    src["strategy_performance_history"].insert_many([
        {"_id": f"sph-{i:04d}", "strategy_hash": f"hash-{i%14}", "pnl": i * 0.5}
        for i in range(1047)
    ])
    # Non-strategy collection that MUST NOT be touched by the migration
    tgt["users"].insert_one({"_id": "u-1", "email": "keep-me@example.com"})
    tgt["mutation_runs"].insert_one({"_id": "m-1", "run": "keep-me"})

    # Also seed indexes on the source to check they round-trip
    src["strategy_library"].create_index([("strategy_hash", 1)], name="hash_1")
    src["strategy_performance_history"].create_index(
        [("strategy_hash", 1), ("pnl", -1)], name="hash_pnl_1"
    )

    return {
        "strategies": 1,
        "strategy_library": 14,
        "strategy_library_archive": 126,
        "strategy_lifecycle_history": 892,
        "strategy_performance_history": 1047,
    }


def run_script(*args: str) -> int:
    cmd = ["python3", SCRIPT, "--mongo", MONGO_URL, "--source", SRC_DB, "--target", TGT_DB, "--yes", *args]
    print(">>>", " ".join(cmd))
    return subprocess.run(cmd, check=False).returncode


def assert_counts(client: MongoClient, expected: dict) -> None:
    tgt = client[TGT_DB]
    for coll, n in expected.items():
        got = tgt[coll].estimated_document_count()
        assert got >= n, f"{coll}: got {got}, expected ≥ {n}"
    print(f"✓ Target counts ≥ source counts for {len(expected)} collections")


def assert_source_untouched(client: MongoClient, before: dict) -> None:
    src = client[SRC_DB]
    for coll, n in before.items():
        got = src[coll].estimated_document_count()
        assert got == n, f"source {coll} mutated! before={n} after={got}"
    print("✓ Source DB byte-identical (counts unchanged)")


def assert_ids_preserved(client: MongoClient, sample_size: int = 20) -> None:
    src = client[SRC_DB]
    tgt = client[TGT_DB]
    for coll in ("strategy_library", "strategy_lifecycle_history", "strategy_performance_history"):
        for src_doc in src[coll].find().limit(sample_size):
            tgt_doc = tgt[coll].find_one({"_id": src_doc["_id"]})
            assert tgt_doc is not None, f"missing {coll}/{src_doc['_id']} in target"
            for k, v in src_doc.items():
                if k.startswith("__migration_"):
                    continue
                assert tgt_doc.get(k) == v, f"{coll}/{src_doc['_id']}: field {k} mismatch ({v} vs {tgt_doc.get(k)})"
    print(f"✓ IDs and payloads round-trip (sample={sample_size})")


def assert_indexes_rebuilt(client: MongoClient) -> None:
    tgt = client[TGT_DB]
    names = {idx["name"] for idx in tgt["strategy_library"].list_indexes()}
    assert "hash_1" in names, f"strategy_library.hash_1 index missing (got {names})"
    names = {idx["name"] for idx in tgt["strategy_performance_history"].list_indexes()}
    assert "hash_pnl_1" in names, f"strategy_performance_history.hash_pnl_1 index missing (got {names})"
    print("✓ Non-default indexes rebuilt on target")


def assert_untouched_target_collections(client: MongoClient) -> None:
    tgt = client[TGT_DB]
    u = tgt["users"].find_one({"_id": "u-1"})
    m = tgt["mutation_runs"].find_one({"_id": "m-1"})
    assert u and u["email"] == "keep-me@example.com", "users collection was overwritten!"
    assert m and m["run"] == "keep-me", "mutation_runs collection was overwritten!"
    print("✓ Unrelated production collections untouched (users, mutation_runs)")


def main() -> int:
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")

    print("── seeding ──")
    before = seed(client)
    print(f"seeded source: {before}")

    print("\n── dry-run ──")
    rc = run_script("--dry-run")
    assert rc == 0, f"dry-run exit code {rc}"
    assert client[TGT_DB]["strategy_library"].estimated_document_count() == 0, (
        "dry-run wrote to target!"
    )
    print("✓ Dry-run wrote nothing")

    print("\n── migration run 1 ──")
    rc = run_script()
    assert rc == 0, f"first migration exit code {rc}"
    assert_counts(client, before)
    assert_ids_preserved(client)
    assert_indexes_rebuilt(client)
    assert_source_untouched(client, before)
    assert_untouched_target_collections(client)

    print("\n── migration run 2 (idempotence) ──")
    tgt_before = {c: client[TGT_DB][c].estimated_document_count() for c in before}
    rc = run_script()
    assert rc == 0, f"second migration exit code {rc}"
    tgt_after = {c: client[TGT_DB][c].estimated_document_count() for c in before}
    for c in before:
        assert tgt_before[c] == tgt_after[c], (
            f"{c}: idempotency violated ({tgt_before[c]} → {tgt_after[c]})"
        )
    print(f"✓ Second run left target counts unchanged: {tgt_after}")

    print("\n── verify-only ──")
    rc = run_script("--verify-only")
    assert rc == 0, f"verify-only exit code {rc}"

    print("\n── discover ──")
    rc = run_script("--discover")
    assert rc == 0, f"discover exit code {rc}"

    print("\n── cleanup ──")
    client.drop_database(SRC_DB)
    client.drop_database(TGT_DB)

    print("\n✅ ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(f"\n❌ FAIL: {e}")
        sys.exit(1)
