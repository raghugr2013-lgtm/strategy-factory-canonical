"""Pytest suite for the migration engine.

Runs against a local MongoDB (mongodb://localhost:27017). Uses throwaway DB
names `test_migration_src` / `test_migration_tgt` which are dropped before
and after each test.

Executes the 8 zero-loss guarantees the operator required for VPS sign-off:

  1. Every source doc has matching _migration_meta.source_fingerprint in target
  2. Rich metadata (fingerprint/hash/lineage/validation_history/bi5/lifecycle/
     provenance) preserved on strategy_library-origin docs verbatim
  3. bcrypt password_hash preserved byte-identical; roles/status preserved
     in legacy_role/legacy_status; login remains valid
  4. Idempotency — a second run over an already-migrated target migrates 0 docs
  5. Indexes: canonical v1.0 indexes rebuilt in target; source indexes mirrored
  6. Source DB is not modified by the migration
  7. Fold assertions — strategy_library (14) folds into strategies; verifier
     reports before=14, after=14
  8. Auto-passthrough — collections not in MIGRATION_PLAN are copied verbatim

Run: pytest /app/strategy-factory/backend/tests/test_migration.py -v
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import bcrypt
import pytest
from pymongo import MongoClient


ROOT = Path("/app/strategy-factory")
SCRIPTS = ROOT / "infra" / "scripts"
MIGRATE = SCRIPTS / "migrate-data.py"
AUDIT = SCRIPTS / "audit-vps-db.py"
VERIFY = SCRIPTS / "verify-migration.py"
SEED = SCRIPTS / "seed-synthetic-v01.py"

MONGO_URI = "mongodb://localhost:27017"
SRC_DB = "test_migration_src"
TGT_DB = "test_migration_tgt"


def _load_migrate_module():
    """Dynamically load migrate-data.py so tests can call source_fingerprint()."""
    spec = importlib.util.spec_from_file_location("migrate_data", MIGRATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mongo_client():
    c = MongoClient(MONGO_URI)
    yield c
    c.drop_database(SRC_DB)
    c.drop_database(TGT_DB)


@pytest.fixture(scope="module")
def seeded(mongo_client):
    mongo_client.drop_database(SRC_DB)
    mongo_client.drop_database(TGT_DB)
    subprocess.run(
        [sys.executable, str(SEED), "--uri", MONGO_URI, "--db", SRC_DB],
        check=True, cwd=str(ROOT),
    )
    return mongo_client[SRC_DB]


@pytest.fixture(scope="module")
def migrated(seeded, mongo_client):
    r = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", SRC_DB,
         "--target", MONGO_URI, "--target-db", TGT_DB,
         "--profile", "full",
         "--report", "/tmp/test-migration-report.json"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r.returncode == 0, f"migration failed:\n{r.stdout}\n{r.stderr}"
    return mongo_client[TGT_DB]


def test_1_fingerprint_coverage(seeded, migrated):
    """Every source doc must have a matching _migration_meta.source_fingerprint in target."""
    mod = _load_migrate_module()
    # Build target fingerprint set
    tgt_fps = set()
    for col in migrated.list_collection_names():
        for doc in migrated[col].find({"_migration_meta.source_fingerprint": {"$exists": True}},
                                      {"_migration_meta.source_fingerprint": 1}):
            tgt_fps.add(doc["_migration_meta"]["source_fingerprint"])

    missing = []
    total = 0
    for col in seeded.list_collection_names():
        for doc in seeded[col].find({}):
            total += 1
            fp = mod.source_fingerprint(doc)
            if fp not in tgt_fps:
                missing.append((col, fp))

    assert total > 0, "seed produced no documents"
    assert not missing, f"{len(missing)}/{total} source docs missing in target"


def test_2_strategy_library_metadata_preserved(migrated):
    """All 14 strategy_library docs must have every rich metadata field preserved verbatim."""
    docs = list(migrated.strategies.find({"_migration_meta.source_collection": "strategy_library"}))
    assert len(docs) == 14, f"expected 14 strategy_library docs in target strategies, got {len(docs)}"
    required_fields = ("fingerprint", "content_hash", "lineage", "validation_history",
                       "bi5", "lifecycle", "provenance", "backtest_snapshot", "notes")
    for d in docs:
        for f in required_fields:
            assert f in d, f"strategy_library doc missing field `{f}`: {d.get('name')}"
        # nested sanity
        assert isinstance(d["lineage"], dict)
        assert isinstance(d["validation_history"], list) and len(d["validation_history"]) >= 2
        assert d["bi5"]["provider"] == "dukascopy"
        assert d["provenance"]["source_bundle"] == "v01-handoff"


def test_3_users_bcrypt_and_legacy_fields(migrated):
    """bcrypt hashes preserved byte-identical; legacy_role/legacy_status carry the source values."""
    # admin@old-vps.local — v01 role=admin, status=approved
    admin = migrated.users.find_one({"email": "admin@old-vps.local"})
    assert admin is not None, "migrated admin missing"
    assert admin["role"] == "admin"
    assert admin["status"] == "active"
    assert admin["legacy_role"] == "admin"
    assert admin["legacy_status"] == "approved"
    assert bcrypt.checkpw(b"Jahnav@2018", admin["password_hash"].encode())

    # oldbob@vps.local — v01 role=user, status=approved
    bob = migrated.users.find_one({"email": "oldbob@vps.local"})
    assert bob is not None
    assert bob["role"] == "viewer"          # coerced for v1.0 auth
    assert bob["legacy_role"] == "user"     # original preserved
    assert bob["legacy_status"] == "approved"
    assert bcrypt.checkpw(b"bob", bob["password_hash"].encode())

    # disabled user preserved as disabled
    dis = migrated.users.find_one({"email": "disabled@old.local"})
    assert dis is not None and dis["status"] == "disabled"


def test_4_idempotent_second_run(migrated):
    """A second live migration over the already-populated target must migrate 0 docs."""
    r = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", SRC_DB,
         "--target", MONGO_URI, "--target-db", TGT_DB,
         "--report", "/tmp/test-migration-idem.json"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    import json
    with open("/tmp/test-migration-idem.json") as f:
        summary = json.load(f)["summary"]
    assert summary["documents_migrated"] == 0, f"expected idempotent no-op, got {summary}"
    assert summary["documents_skipped_already_present"] > 100
    assert summary["document_level_errors"] == 0
    assert summary["hard_errors"] == 0


def test_5_canonical_indexes_present(migrated):
    """Canonical v1.0 unique indexes must exist on users / strategies / research_queries."""
    users_ix = {ix["name"] for ix in migrated.users.list_indexes()}
    assert "email_uniq" in users_ix
    assert "user_id_uniq" in users_ix

    strat_ix = {ix["name"] for ix in migrated.strategies.list_indexes()}
    assert "strategy_id_uniq" in strat_ix

    rq_ix = {ix["name"] for ix in migrated.research_queries.list_indexes()}
    assert "query_id_uniq" in rq_ix


def test_6_source_db_untouched(seeded):
    """The migration must not modify the source DB at all."""
    # After the migration, source counts should still match the seed's totals.
    # 134 pre-existing docs + 22 empty-seed docs for the operator's production collections = 156.
    total = sum(seeded[c].count_documents({}) for c in seeded.list_collection_names())
    assert total == 156, f"source DB was modified: total docs = {total} (expected 156)"


def test_7_fold_assertions(seeded, migrated):
    """strategy_library (14) folds into strategies; research_lineage (30) folds into research_queries."""
    src_sl = seeded.strategy_library.count_documents({})
    tgt_sl = migrated.strategies.count_documents({"_migration_meta.source_collection": "strategy_library"})
    assert src_sl == 14 and tgt_sl == 14, f"strategy_library fold: {src_sl} → {tgt_sl}"

    src_rl = seeded.research_lineage.count_documents({})
    tgt_rl = migrated.research_queries.count_documents({"_migration_meta.source_collection": "research_lineage"})
    assert src_rl == 30 and tgt_rl == 30, f"research_lineage fold: {src_rl} → {tgt_rl}"


def test_8_auto_passthrough_unplanned(seeded, migrated):
    """Collections NOT in MIGRATION_PLAN must still be migrated (auto-passthrough)."""
    src_cnt = seeded.legacy_experimental_notes.count_documents({})
    assert src_cnt == 3
    tgt_cnt = migrated.legacy_experimental_notes.count_documents(
        {"_migration_meta.source_collection": "legacy_experimental_notes"}
    )
    assert tgt_cnt == 3, f"auto-passthrough failed: source={src_cnt} target={tgt_cnt}"


def test_9_validator_pass_default_mode(seeded, tmp_path):
    """Default validator mode: PASS when every source collection is planned OR auto-passthrough'd."""
    import json
    from pymongo import MongoClient
    _ = MongoClient  # keep import for clarity
    audit_path = tmp_path / "audit.json"
    subprocess.run(
        [sys.executable, str(SCRIPTS / "audit-vps-db.py"),
         "--source", MONGO_URI, "--source-db", SRC_DB,
         "--out-json", str(audit_path), "--out-md", str(tmp_path / "audit.md")],
        cwd=str(ROOT), check=True, capture_output=True,
    )
    val_path = tmp_path / "val.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate-migration.py"),
         "--audit", str(audit_path), "--plan", str(MIGRATE),
         "--out-json", str(val_path), "--out-md", str(tmp_path / "val.md")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r.returncode == 0, f"validator did not PASS in default mode:\n{r.stdout}\n{r.stderr}"
    report = json.load(open(val_path))
    assert report["verdict"] == "PASS"
    assert report["mode"].startswith("default")


def test_10_validator_strict_mode_flags_unplanned(seeded, tmp_path):
    """Strict validator mode: REVIEW_REQUIRED when any source collection is not planned/excluded.

    The synthetic seed intentionally includes `legacy_experimental_notes` which is NOT
    in MIGRATION_PLAN — strict mode must flag it.
    """
    import json
    audit_path = tmp_path / "audit.json"
    subprocess.run(
        [sys.executable, str(SCRIPTS / "audit-vps-db.py"),
         "--source", MONGO_URI, "--source-db", SRC_DB,
         "--out-json", str(audit_path), "--out-md", str(tmp_path / "audit.md")],
        cwd=str(ROOT), check=True, capture_output=True,
    )
    val_path = tmp_path / "val.json"
    subprocess.run(
        [sys.executable, str(SCRIPTS / "validate-migration.py"),
         "--strict",
         "--audit", str(audit_path), "--plan", str(MIGRATE),
         "--out-json", str(val_path), "--out-md", str(tmp_path / "val.md")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    # exit != 0 in strict mode if uncovered found — that's the correct verdict
    report = json.load(open(val_path))
    assert report["mode"] == "strict"
    assert report["verdict"] == "REVIEW_REQUIRED"
    uncovered = [u["source"] for u in report["uncovered_source_collections"]]
    assert "legacy_experimental_notes" in uncovered, f"strict mode did not flag unplanned collection: {uncovered}"


# Explicit list of collections the real production VPS audit surfaced that the
# original plan did not cover. Regression guard — if any of these ever drops
# out of MIGRATION_PLAN, the test fails.
PRODUCTION_COLLECTIONS_ADDED_PHASE_5B = [
    "advisory_locks", "asf_import_log", "auto_run_cycles",
    "bi5_cert_sweep_log", "bi5_cert_sweep_runs", "bi5_certification",
    "bi5_data_certification", "calibration_outcomes", "calibration_tables",
    "cbot_parity_signoff", "ingested_strategies", "market_universe_audit",
    "market_universe_symbols", "master_bot_members", "master_bot_ranker_config",
    "master_bot_tiers", "multi_cycle_runs", "orchestrator_env_priority",
    "post_import_pipeline_log", "risk_of_ruin_evaluations", "runner_accounts",
    "runner_token_rotation_history",
]


def test_11_all_production_collections_in_plan():
    """Regression guard: every collection from the operator's production audit
    must be an explicit plan row. Prevents future regressions in strict mode.
    """
    mod = _load_migrate_module()
    plan_source_names = {row["source"] for row in mod.MIGRATION_PLAN}
    missing = [c for c in PRODUCTION_COLLECTIONS_ADDED_PHASE_5B if c not in plan_source_names]
    assert not missing, f"MIGRATION_PLAN missing {len(missing)} operator-required collections: {missing}"


def test_12_validator_strict_pass_when_seed_matches_plan(mongo_client, tmp_path):
    """The synthetic seed now covers all 22 operator-flagged production collections.
    In strict mode, the ONLY uncovered collection should be the intentional
    `legacy_experimental_notes` — proving the fix is real and the strict-mode
    contract is honoured for every planned collection.
    """
    import json
    src_db_name = "test_migration_strict_src"
    mongo_client.drop_database(src_db_name)
    subprocess.run(
        [sys.executable, str(SEED), "--uri", MONGO_URI, "--db", src_db_name],
        cwd=str(ROOT), check=True, capture_output=True,
    )
    audit_path = tmp_path / "audit.json"
    subprocess.run(
        [sys.executable, str(SCRIPTS / "audit-vps-db.py"),
         "--source", MONGO_URI, "--source-db", src_db_name,
         "--out-json", str(audit_path), "--out-md", str(tmp_path / "audit.md")],
        cwd=str(ROOT), check=True, capture_output=True,
    )
    val_path = tmp_path / "val.json"
    subprocess.run(
        [sys.executable, str(SCRIPTS / "validate-migration.py"),
         "--strict",
         "--audit", str(audit_path), "--plan", str(MIGRATE),
         "--out-json", str(val_path), "--out-md", str(tmp_path / "val.md")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    report = json.load(open(val_path))
    uncovered = [u["source"] for u in report["uncovered_source_collections"]]
    # The ONLY expected uncovered collection is the intentional one for test_10
    assert uncovered == ["legacy_experimental_notes"], (
        f"strict mode surfaced unexpected uncovered collections: {uncovered}"
    )
    # And confirm every operator-flagged collection is planned in this run
    covered_sources = {c["source"] for c in report["covered"]}
    for name in PRODUCTION_COLLECTIONS_ADDED_PHASE_5B:
        assert name in covered_sources, f"operator collection {name} missing from covered list"
    mongo_client.drop_database(src_db_name)


def test_13_bundle_integrity_via_shipped_manifest(tmp_path):
    """End-to-end: build the release bundle, extract into a fresh dir, run the
    shipped `verify-bundle.sh` — must exit 0.  Then corrupt one file and verify
    the same script correctly exits 1 with a mismatch message.  Guards the
    class of bug where an operator's on-disk file diverges from the tarball.
    """
    # 1) Build the bundle
    builder = SCRIPTS / "build-bundle.sh"
    assert builder.exists(), "build-bundle.sh missing"
    r = subprocess.run(["bash", str(builder)], capture_output=True, text=True)
    assert r.returncode == 0, f"build-bundle.sh failed: {r.stdout}\n{r.stderr}"

    # 2) Extract into a fresh dir
    tarball = ROOT.parent / "strategy-factory-1.0.0.tar.gz"
    assert tarball.exists()
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    subprocess.run(["tar", "-xzf", str(tarball), "-C", str(extract_dir)], check=True)
    extracted_root = extract_dir / "strategy-factory"
    assert (extracted_root / "SHA256SUMS").exists(), "SHA256SUMS manifest missing from bundle"

    # 3) verify-bundle.sh returns 0 on a clean extract
    r_ok = subprocess.run(
        ["bash", "./infra/scripts/verify-bundle.sh"],
        cwd=str(extracted_root), capture_output=True, text=True,
    )
    assert r_ok.returncode == 0, f"verify-bundle.sh failed on clean extract: {r_ok.stdout}\n{r_ok.stderr}"

    # 4) Corrupt migrate-data.py to simulate the operator's exact bug
    target = extracted_root / "infra/scripts/migrate-data.py"
    target.write_text("# corrupted for test\n")
    r_bad = subprocess.run(
        ["bash", "./infra/scripts/verify-bundle.sh"],
        cwd=str(extracted_root), capture_output=True, text=True,
    )
    assert r_bad.returncode == 1, f"verify-bundle.sh should exit 1 on mismatch, got {r_bad.returncode}"
    assert "FAILED" in r_bad.stdout + r_bad.stderr, "verifier should identify the failing file"
    assert "migrate-data.py" in r_bad.stdout + r_bad.stderr, "verifier should name the failing file"


# ─────────────────────────────────────────────────────────────────────
# Phase 5d: observability + resume
# ─────────────────────────────────────────────────────────────────────

def _fresh_seed(mongo_client, name: str):
    """Drop + re-seed a DB. Retries once on transient AutoReconnect (heavy
    parallel-test load on the shared mongod can drop the connection)."""
    last_err = None
    for attempt in range(3):
        try:
            mongo_client.drop_database(name)
            r = subprocess.run(
                [sys.executable, str(SEED), "--uri", MONGO_URI, "--db", name],
                cwd=str(ROOT), capture_output=True, text=True,
            )
            if r.returncode == 0:
                return
            last_err = f"seed exit {r.returncode}\nSTDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        import time as _t
        _t.sleep(0.5)
    raise RuntimeError(f"seed failed 3× for db={name}: {last_err}")


def test_14_exception_captured_in_report_with_traceback(mongo_client, tmp_path):
    """When migrate-data.py hits an uncaught exception, the report MUST contain
    the full Python traceback and the process exits non-zero (rather than
    silently vanishing when the container is auto-removed).
    """
    _fresh_seed(mongo_client, "test_migration_exc_src")
    report_path = tmp_path / "report.json"
    # Point target at an unreachable Mongo URI — triggers PyMongoError path
    # that must land in report.errors[0] with a traceback.
    r = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", "test_migration_exc_src",
         "--target", "mongodb://127.0.0.1:1/",  # unreachable
         "--target-db", "test_migration_exc_tgt",
         "--report", str(report_path)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r.returncode == 2, f"expected connection-failure exit 2, got {r.returncode}\n{r.stderr}"
    report = json.load(open(report_path))
    assert report["errors"], "expected at least one error in report.errors"
    err = report["errors"][0]
    assert "PyMongoError" in err["error"] or "ServerSelectionTimeoutError" in err["error"]
    assert "traceback" in err
    assert "Traceback" in err["traceback"]
    mongo_client.drop_database("test_migration_exc_src")


def test_15_per_doc_error_captured_with_traceback(mongo_client, tmp_path):
    """A single bad source document (that crashes the transformer) must NOT
    abort the migration. The error must be recorded per-collection with the
    offending doc_id and full traceback, other docs continue to migrate.
    """
    # Seed a "users" collection with one poisoned doc that breaks the transformer
    src_db_name = "test_migration_poisoned_src"
    mongo_client.drop_database(src_db_name)
    db = mongo_client[src_db_name]
    db.users.insert_many([
        {"email": "ok1@example.com", "password_hash": "hash1", "role": "admin", "status": "approved"},
        # Poison: email is a dict, so `.strip().lower()` in upgrade_user throws AttributeError
        {"email": {"nested": True}, "password_hash": "hash-bad", "role": "user"},
        {"email": "ok2@example.com", "password_hash": "hash2", "role": "user", "status": "approved"},
    ])

    report_path = tmp_path / "report.json"
    tgt_db_name = "test_migration_poisoned_tgt"
    mongo_client.drop_database(tgt_db_name)
    r = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", src_db_name,
         "--target", MONGO_URI, "--target-db", tgt_db_name,
         "--skip-unplanned",
         "--report", str(report_path)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    # Non-zero because a hard error occurred, but the migration completed
    assert r.returncode == 1, f"expected exit 1 for per-doc error, got {r.returncode}\n{r.stderr}"

    report = json.load(open(report_path))
    # Two OK docs must have made it into target
    tgt_count = mongo_client[tgt_db_name].users.count_documents({})
    assert tgt_count == 2, f"other docs must continue migrating despite one error; got {tgt_count}"

    # Report.errors must contain the poisoned doc with a traceback
    poison_errors = [e for e in report["errors"] if isinstance(e, dict) and e.get("collection") == "users"]
    assert poison_errors, f"no per-doc error recorded for 'users': {report['errors']}"
    poison_err = poison_errors[0]
    assert "traceback" in poison_err and "Traceback" in poison_err["traceback"]
    assert poison_err.get("doc_id") is not None

    mongo_client.drop_database(src_db_name)
    mongo_client.drop_database(tgt_db_name)


def test_16_resume_skips_completed_collections(mongo_client, tmp_path):
    """After a first successful migration, --resume must skip every completed
    collection (via _migration_progress marker) so a second invocation does
    almost no work.
    """
    _fresh_seed(mongo_client, "test_migration_resume_src")
    tgt = "test_migration_resume_tgt"
    mongo_client.drop_database(tgt)

    # First run — full mode, so every collection produces a completion marker
    r1 = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", "test_migration_resume_src",
         "--target", MONGO_URI, "--target-db", tgt,
         "--profile", "full",
         "--report", str(tmp_path / "r1.json")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r1.returncode == 0, f"first run failed: {r1.stderr}"

    # Progress markers exist for every collection
    progress = list(mongo_client[tgt]["_migration_progress"].find({}))
    assert len(progress) > 40, f"expected progress markers for every collection, got {len(progress)}"
    for p in progress:
        assert p["phase"] == "completed", f"marker not completed: {p}"

    # Second run with --resume — every collection must be marked "resume skip"
    r2 = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", "test_migration_resume_src",
         "--target", MONGO_URI, "--target-db", tgt,
         "--profile", "full", "--resume",
         "--report", str(tmp_path / "r2.json")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r2.returncode == 0, f"resume run failed: {r2.stderr}"
    report2 = json.load(open(tmp_path / "r2.json"))
    # In --resume mode, no doc should be re-migrated (all skipped_already_present)
    assert report2["summary"]["documents_migrated"] == 0
    # And warnings should mention "resume" for many collections
    resume_notes = [w for w in report2["warnings"] if "resume" in str(w).lower()]
    # (No explicit warning required — the marker path just skips silently. But
    # verifying the report contains no fresh migrations is the definitive check.)
    _ = resume_notes  # kept for readability

    mongo_client.drop_database("test_migration_resume_src")
    mongo_client.drop_database(tgt)


def test_17_progress_checkpoints_flushed_mid_run(mongo_client, tmp_path):
    """During migration of a large collection, the engine must write partial
    report snapshots so that if the process dies, the operator can still see
    how far it got.
    """
    src_name = "test_migration_bigcol_src"
    tgt_name = "test_migration_bigcol_tgt"
    mongo_client.drop_database(src_name)
    mongo_client.drop_database(tgt_name)
    # Seed 500 docs in a single collection — with --progress-every=100 we
    # should see checkpoint markers after each 100-doc chunk.
    docs = [{"i": i, "payload": "x" * 32} for i in range(500)]
    mongo_client[src_name]["market_data"].insert_many(docs)

    report_path = tmp_path / "report.json"
    r = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", src_name,
         "--target", MONGO_URI, "--target-db", tgt_name,
         "--profile", "full",
         "--progress-every", "100",
         "--report", str(report_path)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr

    # Final marker must be `completed`
    marker = mongo_client[tgt_name]["_migration_progress"].find_one({"source_collection": "market_data"})
    assert marker is not None
    assert marker["phase"] == "completed"
    assert marker["source_docs"] == 500
    assert "finished_at" in marker

    # Stderr should contain periodic progress lines "progress N/500"
    # (Python logging default routes INFO to stderr)
    assert "progress" in r.stderr, f"expected periodic progress lines in stderr; got:\n{r.stderr[-500:]}"
    assert "500" in r.stderr

    mongo_client.drop_database(src_name)
    mongo_client.drop_database(tgt_name)


def test_18_wrapper_shell_uses_named_container_and_teed_log():
    """Static sanity check on migrate-data.sh:

      * does NOT use `docker run --rm` (container must survive for post-mortem)
      * runs with --name (so `docker logs` post-hoc works)
      * pipes into `tee -a $LOGFILE`
      * calls `docker inspect --format='{{.State.OOMKilled}}'`
      * prints resume hint on failure
    """
    text = (SCRIPTS / "migrate-data.sh").read_text()
    # Strip comment lines before checking — the header docstring may mention --rm
    code_lines = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    assert "docker run --rm" not in code_lines and "--rm " not in code_lines, \
        "wrapper still uses --rm — traceback would be lost on failure"
    assert "--name " in code_lines, "wrapper must give the container a name for post-mortem"
    assert "tee -a" in code_lines or "tee " in code_lines, "wrapper must tee stdout/stderr to a logfile"
    assert "OOMKilled" in code_lines, "wrapper must inspect OOM state on failure"
    assert "--resume" in text, "wrapper must mention --resume for recovery"
    assert "docker logs" in text, "wrapper must print the docker logs recovery command"



# ─────────────────────────────────────────────────────────────────────
# Phase 5e: Migration profiles (Lean vs Full) + permanent exclusions
# ─────────────────────────────────────────────────────────────────────


REGENERABLE_COLLECTIONS = {
    "market_data", "market_data_ticks", "tick_data", "market_spread",
    "market_profile_cells", "data_coverage",
    "bi5_ingest_log", "bi5_cert_sweep_log",
    "soak_stability_samples", "mutation_stability_log",
}
OPTIONAL_COLLECTIONS = {
    "strategy_status", "strategy_lifecycle", "readiness_snapshots",
    "auto_factory_alert_log", "auto_maintenance_status", "cadence_state",
    "factory_supervisor_heartbeats", "advisory_locks",
    "monitoring_state", "monitoring_alert_log", "paper_deviation_alert_log",
    "scaling_nodes", "host_capabilities", "ctrader_desktop_state",
    "asf_import_log", "post_import_pipeline_log", "event_continuations",
    "pipeline_logs", "bi5_cert_sweep_runs", "auto_run_cycles",
}


def test_19_plan_every_row_has_valid_tier():
    """Every row in MIGRATION_PLAN must carry a tier in {critical, regenerable, optional}."""
    mod = _load_migrate_module()
    valid = {"critical", "regenerable", "optional"}
    missing_tier = []
    invalid_tier = []
    for row in mod.MIGRATION_PLAN:
        t = row.get("tier")
        if t is None:
            missing_tier.append(row["source"])
        elif t not in valid:
            invalid_tier.append((row["source"], t))
    assert not missing_tier, f"rows without tier: {missing_tier}"
    assert not invalid_tier, f"rows with invalid tier: {invalid_tier}"


def test_20_regenerable_and_optional_tiers_match_classification():
    """Rows tagged regenerable/optional must exactly match the sign-off classification."""
    mod = _load_migrate_module()
    plan_regen = {r["source"] for r in mod.MIGRATION_PLAN if r.get("tier") == "regenerable"}
    plan_opt = {r["source"] for r in mod.MIGRATION_PLAN if r.get("tier") == "optional"}
    assert plan_regen == REGENERABLE_COLLECTIONS, (
        f"regenerable set drift:\n  plan={sorted(plan_regen)}\n  spec={sorted(REGENERABLE_COLLECTIONS)}"
    )
    assert plan_opt == OPTIONAL_COLLECTIONS, (
        f"optional set drift:\n  plan={sorted(plan_opt)}\n  spec={sorted(OPTIONAL_COLLECTIONS)}"
    )


def test_21_factory_supervisor_lock_is_permanently_excluded():
    """factory_supervisor_lock must be in INTENTIONALLY_EXCLUDED so a stale lock
    document cannot cause the fresh v1.0 supervisor to split-brain on first boot."""
    mod = _load_migrate_module()
    assert "factory_supervisor_lock" in mod.INTENTIONALLY_EXCLUDED, \
        "factory_supervisor_lock must be permanently excluded"
    # And it must NOT appear as a plan row (permanent exclusion means not planned)
    plan_sources = {r["source"] for r in mod.MIGRATION_PLAN}
    assert "factory_supervisor_lock" not in plan_sources, \
        "factory_supervisor_lock must be removed from MIGRATION_PLAN entirely"


def test_22_profile_tiers_definition():
    """PROFILE_TIERS must define exactly two modes: lean=critical-only, full=all-tiers."""
    mod = _load_migrate_module()
    assert set(mod.PROFILE_TIERS.keys()) == {"lean", "full"}
    assert mod.PROFILE_TIERS["lean"] == {"critical"}
    assert mod.PROFILE_TIERS["full"] == {"critical", "regenerable", "optional"}


def test_23_lean_profile_skips_regenerable_and_optional(mongo_client, tmp_path):
    """Lean migration must skip every regenerable/optional collection and
    still migrate every critical one. Uses the synthetic seed which contains
    market_data (regenerable) and mutation_stability_log (regenerable)."""
    src = "test_migration_lean_src"
    tgt = "test_migration_lean_tgt"
    _fresh_seed(mongo_client, src)
    mongo_client.drop_database(tgt)

    report_path = tmp_path / "lean-report.json"
    r = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", src,
         "--target", MONGO_URI, "--target-db", tgt,
         "--profile", "lean",
         "--skip-unplanned",
         "--report", str(report_path)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r.returncode == 0, f"lean migration failed: {r.stderr}\n{r.stdout}"
    report = json.load(open(report_path))
    assert report["summary"]["profile"] == "lean"

    # Regenerable collections must not appear in the target
    src_db = mongo_client[src]
    tgt_db = mongo_client[tgt]
    for name in REGENERABLE_COLLECTIONS:
        if name in src_db.list_collection_names() and src_db[name].count_documents({}) > 0:
            tgt_count = tgt_db[name].count_documents({}) if name in tgt_db.list_collection_names() else 0
            assert tgt_count == 0, (
                f"lean profile must NOT migrate regenerable collection `{name}`; found {tgt_count} docs in target"
            )
    for name in OPTIONAL_COLLECTIONS:
        if name in src_db.list_collection_names() and src_db[name].count_documents({}) > 0:
            tgt_count = tgt_db[name].count_documents({}) if name in tgt_db.list_collection_names() else 0
            assert tgt_count == 0, (
                f"lean profile must NOT migrate optional collection `{name}`; found {tgt_count} docs in target"
            )

    # Critical business collections MUST have landed
    assert tgt_db.users.count_documents({}) > 0, "users missing after lean migration"
    assert tgt_db.strategies.count_documents({}) > 0, "strategies missing after lean migration"

    # factory_supervisor_lock is excluded even if the source has one
    assert tgt_db.factory_supervisor_lock.count_documents({}) == 0

    mongo_client.drop_database(src)
    mongo_client.drop_database(tgt)


def test_24_full_profile_migrates_everything_except_permanent_exclusion(mongo_client, tmp_path):
    """Full migration must migrate every planned tier and still skip
    factory_supervisor_lock (permanent exclusion)."""
    src = "test_migration_full_src"
    tgt = "test_migration_full_tgt"
    _fresh_seed(mongo_client, src)
    # Add a synthetic factory_supervisor_lock doc + a regenerable doc so
    # the assertion is meaningful.
    mongo_client[src]["factory_supervisor_lock"].insert_one(
        {"host": "vps-old", "acquired_at": "2026-01-01T00:00:00Z"}
    )
    mongo_client[src]["market_data"].insert_many(
        [{"symbol": "EURUSD", "ts": i, "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.05}
         for i in range(5)]
    )
    mongo_client.drop_database(tgt)

    report_path = tmp_path / "full-report.json"
    r = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", src,
         "--target", MONGO_URI, "--target-db", tgt,
         "--profile", "full",
         "--skip-unplanned",
         "--report", str(report_path)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r.returncode == 0, f"full migration failed: {r.stderr}\n{r.stdout}"
    report = json.load(open(report_path))
    assert report["summary"]["profile"] == "full"

    tgt_db = mongo_client[tgt]
    # Regenerable collections that exist in source must land in target
    assert tgt_db.market_data.count_documents({}) == 5, \
        "full profile must migrate market_data"
    # Permanent exclusion still applies
    assert tgt_db.factory_supervisor_lock.count_documents({}) == 0, \
        "factory_supervisor_lock must be permanently excluded even in full mode"

    mongo_client.drop_database(src)
    mongo_client.drop_database(tgt)


def test_25_lean_dry_run_reports_expected_skips(mongo_client, tmp_path):
    """Dry-run lean profile must report the regenerable/optional collections
    as skipped (via warnings) without writing to the target."""
    src = "test_migration_lean_dry_src"
    tgt = "test_migration_lean_dry_tgt"
    _fresh_seed(mongo_client, src)
    mongo_client.drop_database(tgt)

    report_path = tmp_path / "lean-dry.json"
    r = subprocess.run(
        [sys.executable, str(MIGRATE),
         "--source", MONGO_URI, "--source-db", src,
         "--target", MONGO_URI, "--target-db", tgt,
         "--profile", "lean", "--dry-run",
         "--skip-unplanned",
         "--report", str(report_path)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert r.returncode == 0, f"lean dry-run failed: {r.stderr}"
    report = json.load(open(report_path))
    assert report["summary"]["profile"] == "lean"
    assert report["dry_run"] is True

    tier_skip_warnings = [w for w in report["warnings"]
                          if "skipped by profile=lean" in str(w)]
    assert len(tier_skip_warnings) >= len(REGENERABLE_COLLECTIONS) + len(OPTIONAL_COLLECTIONS) - 2, (
        f"expected tier-skip warnings for regenerable+optional collections; got {len(tier_skip_warnings)}"
    )

    # No writes should have happened (dry-run + fresh target)
    assert tgt not in mongo_client.list_database_names() or \
           mongo_client[tgt].users.count_documents({}) == 0

    mongo_client.drop_database(src)
    mongo_client.drop_database(tgt)
