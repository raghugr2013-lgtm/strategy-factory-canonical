# VPS Migration Playbook — Zero-Loss Deployment of Strategy Factory v1.0

**Objective.** Prove — before deploying the canonical Strategy Factory v1.0 to production — that every existing collection, document, index, user, strategy, research query, validation report, and configuration value on the current VPS can be migrated with zero loss into the v1.0 `strategy_factory` database. Only after the migration is verified end-to-end do we deploy production.

This playbook chains four utilities and produces four reports that together form the sign-off packet for the deployment.

```
  ┌──────────────────┐   ┌──────────────────────┐   ┌─────────────────┐   ┌──────────────────────┐
  │ audit-vps-db.py  │──▶│ validate-migration.py│──▶│ migrate-data.py │──▶│ verify-migration.py  │
  │ (read-only scan) │   │  (plan coverage)     │   │  (idempotent)   │   │ (post-migration QA)  │
  └────────┬─────────┘   └──────────┬───────────┘   └────────┬────────┘   └──────────┬───────────┘
           ▼                        ▼                        ▼                       ▼
     audit-report                validation             migration              verification
     .json + .md                 -report .json/.md      -report .json          -report .json/.md
```

All four utilities ship in `infra/scripts/`. A single-command orchestrator, `infra/scripts/deploy-dry-run.sh`, exercises the full pipeline against a synthetic v01 dataset so operators can prove the plumbing before touching real data.

---

## 1. Ordered milestones

| # | Milestone | Utility | Output | Gating rule |
|---|---|---|---|---|
| 1 | Snapshot source DB | `mongodump` | archive on host | must exist before step 2 |
| 2 | Audit source DB | `audit-vps-db.py` | `audit-report.{json,md}` | operator reviews collection roll-ups |
| 3 | Validate coverage | `validate-migration.py` | `validation-report.{json,md}` | **verdict must be `PASS`** — add plan rows for any uncovered collections and re-validate |
| 4 | Migration dry-run | `migrate-data.py --dry-run` | `migration-report.dryrun.json` | `hard_errors == 0`, source counts match expectation |
| 5 | Migration live | `migrate-data.py` | `migration-report.json` | `hard_errors == 0`, `document_level_errors == 0` |
| 6 | Verify target | `verify-migration.py` | `verification-report.{json,md}` | **verdict `PASS`** or only documented manual actions remain |
| 7 | Deploy canonical stack | `deploy.sh` + `bootstrap-vps.sh` | live app at `https://strategy.coinnike.com` | `health.sh` green |
| 8 | Manual: reassign roles | Admin UI | — | migrated users default to `viewer` unless they were `admin` in v01 |
| 9 | Freeze Strategy Factory v1.0 | git tag + `VERSION` | tag `v1.0.0` | after successful production run |

---

## 2. Utility catalogue

### 2.1 `infra/scripts/audit-vps-db.py`

Read-only inspection of the source Mongo. Produces exhaustive JSON + Markdown covering:

- Every collection (name, document count, storage size, indexes)
- Sample documents (secrets masked)
- Domain roll-ups: `users` (by role, by status), `strategies` (with `strategy_library` folded), `research` (by provider), `validation`, `config`
- Inferred relationships between collections (via FK-style field hints)
- Collections **not** in the Strategy Factory catalogue — flagged for classification

Never writes. Safe to run any number of times.

```bash
docker run --rm --network vqb-network -v "$(pwd):/work" -w /work \
  python:3.12-slim sh -c "\
    pip install -q pymongo==4.9.2 && \
    python infra/scripts/audit-vps-db.py \
      --source \"$SOURCE_MONGO_URL\" --source-db test_database \
      --out-json /work/audit-report.json \
      --out-md   /work/audit-report.md"
```

### 2.2 `infra/scripts/validate-migration.py`

Static coverage check. AST-parses `migrate-data.py` for its `MIGRATION_PLAN`, reads the audit JSON, and answers: **is every source collection covered by a plan row?**

Emits verdict `PASS` or `REVIEW_REQUIRED` and, for each uncovered collection, a ready-to-paste plan row.

```bash
python infra/scripts/validate-migration.py \
  --audit    audit-report.json \
  --plan     infra/scripts/migrate-data.py \
  --out-json validation-report.json \
  --out-md   validation-report.md
```

Exit code is `0` (pass) or `1` (uncovered collections found). **Fix uncovered collections in `migrate-data.py` before continuing.**

### 2.3 `infra/scripts/migrate-data.py`

The migration engine (already documented in `STRATEGY_MIGRATION_GUIDE.md`). Idempotent, upsert-on-natural-key, produces `migration-report.json` with per-collection counts (`migrated`, `skipped_already_present`, `upgraded`, `errors`) and a summary block.

### 2.4 `infra/scripts/verify-migration.py`

Post-migration integrity check. Compares audit vs target:

- Every source collection is represented in target (accounting for documented renames: `strategy_library → strategies`, `research_lineage → research_queries`)
- Canonical indexes are present on `users`, `strategies`, `research_queries`
- Every migrated user has `email`, `password_hash`, `role`, `status`, `user_id`
- Every migrated strategy has `strategy_id`, `name`, `created_by`
- Optional live API smoke tests against `/api/health`, `/api/version`, `/api/auth/login`, `/api/auth/me`, `/api/strategies`, `/api/research/history`, `/api/admin/users`, `/api/admin/providers`

Produces a **Migration Verification Report** with a hard `PASS` / `REVIEW_REQUIRED` verdict and an explicit list of any manual actions remaining.

```bash
python infra/scripts/verify-migration.py \
  --audit    audit-report.json \
  --target   "$SHARED_MONGO_URL" --target-db strategy_factory_v1 \
  --migration-report migration-report.json \
  --api-base "https://strategy.coinnike.com" \
  --admin-email  "$V01_ADMIN_EMAIL" \
  --admin-password "$V01_ADMIN_PASSWORD" \
  --out-json verification-report.json \
  --out-md   verification-report.md
```

### 2.5 `infra/scripts/deploy-dry-run.sh`

One-shot orchestrator. Seeds a synthetic v01 dataset via `seed-synthetic-v01.py`, runs steps 2–6 above against local Mongo, and drops all reports into `dry-run-reports/`. Use it any time you touch the migration plan or transformers to prove the pipeline still holds.

```bash
./infra/scripts/deploy-dry-run.sh
# with live API smoke:
API_BASE=http://localhost:8001 ADMIN_EMAIL=admin@old-vps.local ADMIN_PASSWORD='...' \
  ./infra/scripts/deploy-dry-run.sh
```

---

## 3. Operational runbook — VPS

### 3.1 Pre-flight

```bash
ssh contabo
sudo -i
cd /opt

# 1) Snapshot the source DB (immutable safety net)
mkdir -p /var/backups/strategy-factory
docker run --rm --network vqb-network -v /var/backups/strategy-factory:/dump mongo:7.0 \
  mongodump --uri "$SOURCE_MONGO_URL" \
  --archive="/dump/v01-pre-migrate-$(date -u +%Y%m%d).archive.gz" --gzip

# 2) Extract the canonical bundle (if not already unpacked)
tar -xzf strategy-factory-1.0.0.tar.gz -C /opt/
cd /opt/strategy-factory
```

**Reconcile side databases (mandatory when the source Mongo instance hosts more than one Strategy Factory DB).**

Before assuming which DB is authoritative, list every DB on the source Mongo and identify the one the currently-running production backend reads from:

```bash
# List every DB and its collection counts
mongosh "$SOURCE_MONGO_URL" --quiet --eval '
  db.adminCommand("listDatabases").databases.forEach(d => {
    if (["admin","local","config"].includes(d.name)) return;
    const sib = db.getSiblingDB(d.name);
    print(d.name.padEnd(30),
          "users:", (sib.users.countDocuments({}) || 0),
          "strategies:", (sib.strategies.countDocuments({}) || 0),
          "strategy_library:", (sib.strategy_library.countDocuments({}) || 0));
  });
'

# Confirm which DB the CURRENT production backend is bound to
grep DB_NAME /opt/vqb-strategy-factory/backend/.env    # or wherever the OLD deployment lives
```

The canonical source is **the DB the running backend has `DB_NAME=` pointed at**. All other same-shape DBs on the same Mongo (e.g. a leftover `strategy_factory` from an earlier exploratory run) are historical; do not migrate from them.

If two candidate DBs exist, run this to see whether any is our engine's output:

```bash
mongosh "$SOURCE_MONGO_URL" --quiet --eval '
  ["test_database","strategy_factory"].forEach(name => {
    const s = db.getSiblingDB(name);
    const stamped = s.strategies.countDocuments({"_migration_meta.source_fingerprint":{$exists:true}})
                   + s.strategy_library.countDocuments({"_migration_meta.source_fingerprint":{$exists:true}});
    print(name, " stamped by migration engine:", stamped);
  });
'
```

A `stamped > 0` result means that DB is a prior migration output, not a source. Leave it alone.

**Write the reconciled values into `/opt/strategy-factory/.env`:**

```env
# Source — the DB the OLD live backend uses
SOURCE_MONGO_URL=mongodb://factory_user:<v01_password>@mongo:27017/?authSource=admin
SOURCE_MONGO_DB=test_database

# Target — a FRESH DB name so the migration cannot conflict with any
# pre-existing DB on the same Mongo instance. Any leftover DB called
# `strategy_factory` on the source Mongo (from earlier experiments)
# is preserved untouched.
SHARED_MONGO_URL=mongodb://factory_user:<v10_password>@mongo:27017/strategy_factory_v1?authSource=admin
FACTORY_DB_NAME=strategy_factory_v1
```

The canonical v1.0 backend reads its DB name from `FACTORY_DB_NAME`, so this single environment variable also switches the running app to the migrated data post-deploy — no code change required.

### 3.2 Bundle integrity check (mandatory, immediately after extract)

The bundle ships with an in-tree `SHA256SUMS` manifest covering every file plus a `verify-bundle.sh` runner. Run this **before** touching any migration command:

```bash
cd /opt/strategy-factory
./infra/scripts/verify-bundle.sh
```

Expected output:
```
▸ Verifying 1037 files against SHA256SUMS…
✓ All files match the manifest — extraction is intact.
```

If it fails, one file on disk differs from what shipped — usually because an earlier bundle was extracted first and the newer file was skipped. The verifier prints exact recovery steps.

Do **not** proceed with the migration until this check is green.

### 3.3 Audit (READ-ONLY)

```bash
docker run --rm --network vqb-network -v "$PWD:/work" -w /work \
  -e SOURCE_MONGO_URL python:3.12-slim sh -c "\
    pip install -q pymongo==4.9.2 && \
    python infra/scripts/audit-vps-db.py \
      --source \"$SOURCE_MONGO_URL\" --source-db test_database \
      --out-json /work/audit-report.json \
      --out-md   /work/audit-report.md"

less audit-report.md    # sanity-check the domain roll-ups
```

**Sign-off rule:** every collection in the source appears with a reasonable purpose, and totals match your expectation.

### 3.3 Validate coverage

```bash
python3 infra/scripts/validate-migration.py \
  --audit audit-report.json \
  --plan  infra/scripts/migrate-data.py \
  --out-json validation-report.json \
  --out-md   validation-report.md

echo "verdict: $(python3 -c 'import json; print(json.load(open("validation-report.json"))["verdict"])')"
```

**Sign-off rule:** verdict is `PASS`. If not, add the suggested plan rows to `migrate-data.py` and re-run. Do not proceed to the live migration with `REVIEW_REQUIRED`.

### 3.4 Dry-run migration

```bash
./infra/scripts/migrate-data.sh --dry-run
```

Read `/var/log/strategy-factory/migration-<timestamp>.json`. Confirm `hard_errors == 0` and `documents_migrated` matches the audit's `source.total_documents` (minus any already-present target rows if you've partially migrated).

### 3.5 Live migration

```bash
./infra/scripts/migrate-data.sh
```

### 3.6 Verify

```bash
docker run --rm --network vqb-network -v "$PWD:/work" -w /work \
  -e SHARED_MONGO_URL python:3.12-slim sh -c "\
    pip install -q pymongo==4.9.2 && \
    python infra/scripts/verify-migration.py \
      --audit audit-report.json \
      --target \"$SHARED_MONGO_URL\" --target-db strategy_factory_v1 \
      --migration-report /var/log/strategy-factory/migration-<timestamp>.json \
      --out-json verification-report.json \
      --out-md   verification-report.md"
```

**Sign-off rule:** verdict is `PASS`, or the only listed manual actions are the documented "re-assign roles" note.

### 3.7 Deploy canonical stack

Only now — with all four reports produced and verified — do we deploy:

```bash
./infra/scripts/precheck.sh
./infra/scripts/bootstrap-vps.sh      # first time only
./infra/scripts/deploy.sh
./infra/scripts/health.sh             # must be green
```

Log in at `https://strategy.coinnike.com` as the migrated v01 admin (their old password still works — bcrypt hashes are preserved verbatim).

### 3.8 Re-run verify against live API

```bash
python3 infra/scripts/verify-migration.py \
  --audit audit-report.json \
  --target "$SHARED_MONGO_URL" --target-db strategy_factory_v1 \
  --migration-report /var/log/strategy-factory/migration-<timestamp>.json \
  --api-base https://strategy.coinnike.com \
  --admin-email "$V01_ADMIN_EMAIL" \
  --admin-password "$V01_ADMIN_PASSWORD" \
  --out-json verification-final.json \
  --out-md   verification-final.md
```

**Sign-off rule:** every API smoke row is `ok: true`.

### 3.9 Freeze v1.0

```bash
cd /opt/strategy-factory
cat VERSION
git tag -a v1.0.0 -m "Strategy Factory v1.0.0 — canonical baseline"
# push tag through your Save-to-GitHub flow
```

Stage 2 activation begins only after this tag exists.

---

## 4. Rollback

The source DB is never modified. Rollback is:

```bash
# 1) Drop the target (source stays intact)
docker exec factory-backend python -c "\
import os, pymongo; \
pymongo.MongoClient(os.environ['MONGO_URL']).drop_database(os.environ['DB_NAME']); \
print('dropped')"

# 2) Restore mongodump if you need to roll target back to a specific snapshot
docker run --rm --network vqb-network -v /var/backups/strategy-factory:/dump mongo:7.0 \
  mongorestore --uri "$SHARED_MONGO_URL" --archive=/dump/<snapshot>.archive.gz --gzip

# 3) Re-run dry-run + live migration
./infra/scripts/migrate-data.sh --dry-run
./infra/scripts/migrate-data.sh
```

The migration is idempotent — you can also just re-run without dropping. Upserts on natural keys never overwrite already-migrated documents.

---

## 5. Sign-off packet

Attach these five artefacts to the deployment ticket:

1. `audit-report.md` — what was in the source
2. `validation-report.md` — coverage of migration plan, verdict `PASS`
3. `migration-report.json` — every doc moved, with counts, verdict `hard_errors: 0`
4. `verification-report.md` — before/after, spot checks, API smoke, verdict `PASS`
5. Manual actions completed — screenshot / notes of Admin → Users role reassignments

When all five are present and green, the migration is complete and Strategy Factory v1.0 is frozen as the canonical baseline. Stage 2 activation follows `docs/STAGE2_ACTIVATION_GUIDE.md`.
