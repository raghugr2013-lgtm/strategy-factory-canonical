# Strategy Migration Guide — v01 VPS → Strategy Factory v1.0

**Objective:** zero-loss migration of the existing MongoDB on the current VPS into the new canonical `strategy_factory` database with schema upgrades applied automatically and a machine-readable report produced.

**This capability ships as five files:**

- `infra/scripts/audit-vps-db.py`     — read-only source audit → `audit-report.{json,md}` (see `VPS_MIGRATION_PLAYBOOK.md §2.1`)
- `infra/scripts/validate-migration.py` — static plan-coverage check → `validation-report.{json,md}`
- `infra/scripts/migrate-data.py`     — the idempotent migration engine (transformers + upsert-on-natural-key + JSON report)
- `infra/scripts/migrate-data.sh`     — thin Bash wrapper that runs the engine inside an ephemeral `python:3.12-slim` container joined to `vqb-network`
- `infra/scripts/verify-migration.py` — post-migration integrity + live API smoke → `verification-report.{json,md}`

Plus one orchestrator that exercises the full pipeline against a synthetic v01 dataset for confidence-building:

- `infra/scripts/deploy-dry-run.sh` — seeds a synthetic v01, runs audit → validate → migrate (dry + live) → verify, drops all reports into `dry-run-reports/`

The complete VPS runbook — from `mongodump` snapshot through production deployment sign-off — lives in [`VPS_MIGRATION_PLAYBOOK.md`](./VPS_MIGRATION_PLAYBOOK.md). This document is the transformer / schema reference; the playbook is the operational sequence.

All five files ship in the v1.0.0 bundle.

---

## 0. Zero-loss guarantees (proven invariants)

Every guarantee below is enforced by the migration engine and asserted by the verifier's report. Any failed assertion produces `verdict: REVIEW_REQUIRED` and blocks deployment sign-off.

| # | Guarantee | How it's enforced |
|---|---|---|
| 1 | **Every source doc lands in the target with matching identity** | Each migrated doc carries `_migration_meta.source_fingerprint` = SHA-256 of the canonical source doc (minus `_id`). The verifier re-scans the source and asserts every fingerprint exists in the target. Missing count must be `0`. |
| 2 | **All source metadata preserved verbatim** | Transformers copy `dict(source_doc)` verbatim and only *add* / normalise fields — never strip. `strategy_library` docs' `fingerprint`, `content_hash`, `lineage`, `validation_history`, `bi5`, `lifecycle`, `provenance`, `backtest_snapshot`, `notes` all survive byte-identical. |
| 3 | **Users, bcrypt hashes, and roles preserved** | `password_hash` copied verbatim (bcrypt is version-compatible; v01 login still works). Original `role` and `status` copied to `legacy_role` / `legacy_status`; the active fields are coerced only to valid v1.0 literals so Pydantic auth accepts them. |
| 4 | **Idempotent** | Re-running the migration is a no-op: for keyed collections we check both the natural key AND the `_migration_meta.source_fingerprint`; for keyless collections we check fingerprint only. Even strategies whose `strategy_id` was synthesised (uuid4) on the first run are correctly matched on subsequent runs. |
| 5 | **Existing indexes preserved / recreated** | The engine (a) rebuilds every canonical v1.0 index (`users.email_uniq`, `strategies.strategy_id_uniq`, …) and (b) mirrors every non-conflicting source index into the target (excluding the implicit `_id_`). |
| 6 | **Source is never modified** | The migration script uses only `.find({})` on the source connection — never `.update_*`, `.delete_*`, `.drop*`. |
| 7 | **Automatic schema adaptation** | Any source collection **not** in `MIGRATION_PLAN` and **not** in `INTENTIONALLY_EXCLUDED` is auto-passthrough'd verbatim with a warning (disable with `--skip-unplanned`). This prevents silent data loss when production has collections the plan didn't anticipate. |
| 8 | **Verification report emits explicit before/after per collection AND per fold** | The verifier reports source docs vs migrated docs per source collection, plus explicit fold assertions (e.g. `strategy_library: 14 before / 14 after`). |

---

## 0.1 Scope & coverage policy

Strategy Factory v1.0 is a **zero-loss migration by default**: every collection in the source database is migrated. Three exhaustive states describe every source collection:

1. **Planned** — an explicit row in `MIGRATION_PLAN` (in `infra/scripts/migrate-data.py`). Routed through the correct transformer (e.g. `upgrade_user`) or the generic `upgrade_passthrough`. Currently the plan enumerates every canonical Strategy Factory v1.0 collection (identity, strategies, research, validation, market data, bots, portfolios, governance, prop-firm, auto-factory, monitoring, deployment, ASF import journal, settings).
2. **Intentionally excluded** — an entry in `INTENTIONALLY_EXCLUDED` (module-level `set` in `migrate-data.py`). Empty by default. Populate on the VPS with a rationale comment per entry — e.g. for very large ephemeral collections you want to regenerate post-deploy rather than migrate.
3. **Auto-passthrough** — safety net for any source collection the operator's DB has that the plan didn't foresee. Migrated verbatim (same target collection name, `upgrade_passthrough` transformer) with a warning in the report. Disable with `--skip-unplanned`.

The **validator** (`validate-migration.py`) asserts this contract:

* **Default mode**: verdict `PASS` when every source collection falls into one of the three states above.
* **Strict mode** (`--strict`): verdict `PASS` only when every source collection is Planned or Intentionally Excluded (no reliance on auto-passthrough). Use strict mode when you want to explicitly ratify the plan.

The operator on the VPS can drive the choice by either:

* Adding rows to `MIGRATION_PLAN` (explicit — recommended for strict-mode compliance)
* Adding collection names to `INTENTIONALLY_EXCLUDED` with a rationale comment
* Leaving them to auto-passthrough (default — safest for zero-loss)

---

## 1. What is migrated (guaranteed preserved)

| v01 collection (source) | v1.0 collection (target) | Transformer | Notes |
|---|---|---|---|
| `users` | `users` | `upgrade_user` | Status remapping + role defaulting + user_id backfill (schema change — see §3.1) |
| `strategies` | `strategies` | `upgrade_strategy` | Identifiers + timestamps normalised; **every** custom field preserved verbatim (ir, tags, symbol, timeframe, versions, custom metrics — nothing stripped) |
| `strategy_library` | **folded into** `strategies` | `upgrade_strategy` | The v01 "14 migrated strategies" cohort lives here. Merged into the unified `strategies` collection. |
| `strategy_versions` | `strategy_versions` | pass-through | Preserved for Stage 2 dossier |
| `research_lineage` | **renamed to** `research_queries` | `upgrade_research_query` | v01 lineage becomes v1.0 research queries |
| `research_queries` | `research_queries` | `upgrade_research_query` | If both source collections exist, both are migrated with upsert idempotency |
| `validation_reports` | `validation_reports` | pass-through | Full backtest / walk-forward / MC reports preserved |
| `backtest_results` | `backtest_results` | pass-through | |
| `master_bots` | `master_bots` | pass-through | |
| `master_bot_exports` | `master_bot_exports` | pass-through | |
| `portfolio_definitions` | `portfolio_definitions` | pass-through | |
| `mutation_pool` | `mutation_pool` | pass-through | |
| `market_universe` | `market_universe` | pass-through | |
| `market_intelligence` | `market_intelligence` | pass-through | |
| `prop_firm_configs` | `prop_firm_configs` | pass-through | |
| `prop_firm_rules` | `prop_firm_rules` | pass-through | |
| `governance_universe` | `governance_universe` | pass-through | |
| `survivor_registry` | `survivor_registry` | pass-through | |
| `readiness_snapshots` | `readiness_snapshots` | pass-through | |
| `bi5_certifications` | `bi5_certifications` | pass-through | |
| `settings` | `settings` | pass-through | Upserted on `key` |
| `audit_log` | `audit_log` | pass-through | |
| `lifecycle_events` | `lifecycle_events` | pass-through | |
| `strategy_memory` | `strategy_memory` | pass-through | Full memory timeline preserved |

**Anything NOT in this table** is still visible in the source DB — the migration script does not delete or modify the source. If the migration report shows a source collection that wasn't in the plan, add it to `MIGRATION_PLAN` in `migrate-data.py` with `upgrade_passthrough` and re-run — the script is idempotent.

**Never dropped:** the source database. Only additive writes into the target. Your v01 VPS Mongo remains intact throughout.

**Never modified:** any doc that already exists in the target with the same natural key. The script uses `$setOnInsert` on upsert, so re-running never overwrites already-migrated documents.

---

## 2. Indexes rebuilt in the target

After document migration, the script rebuilds every canonical v1.0 index:

- `users`: unique on `email` and `user_id`
- `refresh_tokens`: unique on `jti`, TTL on `expires_at`, non-unique on `user_id`
- `strategies`: unique on `strategy_id`, non-unique on `created_by` and `created_at`
- `research_queries`: unique on `query_id`, non-unique on `created_by` and `created_at`
- `audit_log`: descending on `ts_dt`

The Phase 1 backend's `ensure_indexes()` also runs on every boot — the migration's index build is defensive, not the sole source of truth.

---

## 3. Automatic schema upgrades

### 3.1 `users`

| Field | v01 source | v1.0 target | Transform |
|---|---|---|---|
| `_id` | ObjectId | ObjectId (new) | dropped from source doc; target Mongo assigns fresh |
| `user_id` | missing / inconsistent | `uuid4().hex[:16]` | backfilled if absent |
| `email` | mixed case | `email.strip().lower()` | normalised |
| `password_hash` | bcrypt | bcrypt | **preserved verbatim** — bcrypt hashes are compatible; users can log in with their existing passwords immediately |
| `status` | `pending` / `approved` | `active` / `disabled` | `pending`, `approved`, empty, or missing → `active`; `disabled` preserved |
| `legacy_status` | — | copy of the v01 `status` | **new field** — preserves the original v01 status verbatim for audit |
| `role` | `user` (single role) | one of `admin`/`developer`/`researcher`/`operator`/`viewer` | If source role is `user`, empty, or unknown → `viewer` (safest default). Any existing `admin` is preserved. |
| `legacy_role` | — | copy of the v01 `role` | **new field** — preserves the original v01 role verbatim for audit |
| `created_at` | may be str or datetime | tz-aware `datetime` in UTC | coerced |
| `updated_at` | may be missing | defaults to `created_at` | backfilled |
| `_migration_meta` | — | `{source_collection, source_fingerprint, source_id, transformer, migrated_at}` | **new sub-document** — stamped on every migrated doc for post-migration verification |

**Post-migration action for admins:** log in as your Phase 1 seeded admin, go to **Admin → Users**, and re-assign roles to the migrated accounts. Every user starts as `viewer` unless they were explicitly `admin` in v01. `legacy_role` / `legacy_status` on each document tell you exactly what the source values were.

### 3.2 `strategies` (and `strategy_library` merged in)

| Field | v01 source | v1.0 target | Transform |
|---|---|---|---|
| `_id` | ObjectId | ObjectId (new) | dropped, target assigns |
| `strategy_id` | may be `id`, `sid`, `strategyId`, or missing | `strategy_id` (str) | backfilled from any of the alternate keys, else `uuid4().hex[:16]` |
| `name` | may be `title` or missing | non-empty string | backfilled from title or `Strategy <id6>` |
| `status` | inconsistent | `"draft"` if missing | preserved otherwise |
| `tags` | list or missing | list | `[]` if missing or wrong type |
| `created_by` | may be `owner` or missing | string | backfilled from owner or `"unknown"` |
| `created_at` / `updated_at` | inconsistent | tz-aware UTC datetime | coerced |
| everything else (ir, symbol, timeframe, custom metrics, versions, prop-firm binding, backtest snapshots, custom Stage 2 fields, …) | as-is | **as-is** | **not touched** — Stage 2 engines expect the legacy shape |

### 3.3 `research_queries` (was `research_lineage`)

| Field | v01 source | v1.0 target | Transform |
|---|---|---|---|
| `query_id` | may be `id` or missing | string | backfilled |
| `prompt` | may be `query` or `text` | string | backfilled |
| `provider` | may be `model_provider` or missing | string | backfilled, defaults to `"unknown"` |
| `created_by` | may be `user_id` or missing | string | backfilled |
| `created_at` | inconsistent | tz-aware datetime | coerced |

### 3.4 Pass-through collections

Every other collection is copied byte-identical to the target with `_id` regenerated. Nothing else is touched. Stage 2 engines are the sole consumers of these collections and they read the v01 shapes directly.

---

## 4. Migration report

At the end of every run, a JSON report is written (default: `/var/log/strategy-factory/migration-<timestamp>.json`).

Report shape:

```json
{
  "started_at": "2026-02-15T10:00:00+00:00",
  "finished_at": "2026-02-15T10:02:14+00:00",
  "dry_run": false,
  "source": {
    "uri_host": "mongodb://factory_user:***@old-mongo:27017",
    "db": "test_database",
    "collections": ["users", "strategies", "strategy_library", ...],
    "total_documents": 4213
  },
  "target": {
    "uri_host": "mongodb://factory_user:***@mongo:27017",
    "db": "strategy_factory",
    "collections_before": ["users"],
    "collections_after": ["users", "strategies", "research_queries", ...],
    "total_documents_before": 1,
    "total_documents_after": 4214
  },
  "collections": {
    "users": {
      "source_count": 8,
      "migrated": 7,
      "skipped_already_present": 1,
      "upgraded": 8,
      "errors": 0,
      "notes": []
    },
    "strategy_library": {
      "source_count": 14,
      "migrated": 14,
      "skipped_already_present": 0,
      "upgraded": 14,
      "errors": 0,
      "notes": ["v01 strategy_library folded into strategies collection"]
    },
    ...
  },
  "errors": [],
  "warnings": [],
  "summary": {
    "collections_processed": 19,
    "documents_migrated": 4213,
    "documents_upgraded_in_place": 22,
    "documents_skipped_already_present": 1,
    "document_level_errors": 0,
    "hard_errors": 0,
    "warnings": 0
  }
}
```

**Acceptance rule:** `summary.hard_errors == 0` and `summary.document_level_errors == 0`, and `summary.documents_migrated` matches your expectation (usually equal to `source.total_documents` minus any duplicates already present).

---

## 5. Recommended procedure (VPS)

### 5.1 Pre-flight

Before touching anything, snapshot the source DB. Even though the migration is read-only against the source, a backup is cheap:

```bash
docker run --rm --network vqb-network -v /var/backups:/dump mongo:7.0 \
  mongodump --uri "$SOURCE_MONGO_URL" --archive=/dump/v01-pre-migrate-$(date -u +%Y%m%d).archive.gz --gzip
```

### 5.2 Configure

Add to `/opt/strategy-factory/.env` (in addition to the values already there for the v1.0 deployment):

```env
SOURCE_MONGO_URL=mongodb://factory_user:<v01_password>@old-mongo:27017/?authSource=admin
SOURCE_MONGO_DB=test_database
# SHARED_MONGO_URL is already set — that's the v1.0 target
```

If both source and target are on the **same** Mongo instance (common on the VPS where you're just switching DB names), point both env vars at the same URI with different DB names.

### 5.3 Dry-run first (mandatory)

```bash
cd /opt/strategy-factory
chmod +x infra/scripts/migrate-data.sh
./infra/scripts/migrate-data.sh --dry-run
```

Inspect the report at `/var/log/strategy-factory/migration-<timestamp>.json`. Verify:

- `source.collections` lists everything you expect
- `collections.<name>.source_count` matches document counts in the v01 DB (spot-check with `mongosh --eval 'db.<name>.countDocuments({})'`)
- `hard_errors == 0`
- `summary.documents_migrated` is what you expect (this is the "would be migrated" count in dry-run mode)

### 5.4 Live migration

```bash
./infra/scripts/migrate-data.sh
```

Wait for `[migrate] done → /var/log/strategy-factory/migration-<timestamp>.json`.

Post-check:

```bash
# Confirm the 14-strategy cohort is present in the target
docker exec factory-backend python -c "
import os, pymongo
db = pymongo.MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
print('strategies:', db.strategies.count_documents({}))
print('users:',      db.users.count_documents({}))
print('research:',   db.research_queries.count_documents({}))"
```

Then log into `https://strategy.coinnike.com/`, go to **Admin → Users**, and re-assign roles for the migrated users (they will all be `viewer` unless they were explicitly `admin` in v01).

### 5.5 Rollback

If the dry-run or the report reveals a problem after the live run:

```bash
# Drop the target DB and restart migration (source is untouched)
docker exec factory-backend python -c "
import os, pymongo
c = pymongo.MongoClient(os.environ['MONGO_URL'])
c.drop_database(os.environ['DB_NAME'])
print('dropped')"

# Re-run
./infra/scripts/migrate-data.sh --dry-run
./infra/scripts/migrate-data.sh
```

Because the script is idempotent, you can also just re-run without dropping — duplicates are skipped, upgrades are re-applied.

---

## 6. Idempotency guarantees

- **Upsert on natural keys.** Collections with a domain key (`users.email`, `strategies.strategy_id`, `research_queries.query_id`, `settings.key`) use `update_one({key}, {$setOnInsert}, upsert=True)`. Re-running the migration inserts nothing that's already present.
- **`_id` regeneration.** Source `_id` is never carried over; the target Mongo assigns fresh ObjectIds. This eliminates cross-cluster ObjectId conflicts.
- **Source is read-only.** The script never `.update_*`, `.delete_*`, or `.drop()` on the source connection. Even if the target write fails, the source is untouched.
- **Report append.** Each run gets its own timestamped report; nothing overwrites the previous one.

---

## 7. Adding a new collection to the plan (post-migration)

If you discover a collection in v01 that wasn't in `MIGRATION_PLAN`:

1. Open `infra/scripts/migrate-data.py`.
2. Add a row to `MIGRATION_PLAN`. If the schema is unchanged, use `upgrade_passthrough`:
   ```python
   {"source": "your_collection", "target": "your_collection", "key": None, "xform": upgrade_passthrough},
   ```
3. If the schema needs an upgrade, write a small `upgrade_your_collection(doc) -> (out, upgraded)` function following the pattern of `upgrade_user`.
4. Re-run `./infra/scripts/migrate-data.sh` — only the new collection is imported (already-migrated collections skip on the natural key).

---

## 8. What the migration does NOT do (out of scope)

- **Does not migrate BI5 tick data.** BI5 is filesystem-based, not in Mongo. The Backtesting pillar activation (`docs/STAGE2_ACTIVATION_GUIDE.md §2.5`) covers BI5 volume provisioning and one-time backfill separately.
- **Does not migrate ASF package artefacts on disk.** If v01 wrote `.asf` files to a host directory, `scp` them into the same location on the new VPS before enabling the Export pillar.
- **Does not migrate v01's `.env` values.** Provider keys and JWT secrets are new-in-place on the v1.0 VPS (see `docs/PRODUCTION_CONFIGURATION.md`). Nothing is imported from the source `.env`.
- **Does not migrate Prometheus/Grafana dashboards.** Those live on the shared monitoring stack — untouched by this migration.
- **Does not migrate the source `refresh_tokens` collection.** v01 refresh tokens are format-incompatible with v1.0's rotation scheme; users simply log in again (their bcrypt hashes are preserved, so the password still works). This is by design — no forged token can survive the migration.

---

## 9. Sign-off checklist

- [ ] Source DB backed up (`mongodump` archive stored on host)
- [ ] `--dry-run` completed, report reviewed
- [ ] `source.total_documents` in report matches your expectation
- [ ] `hard_errors == 0` and `document_level_errors == 0`
- [ ] Live migration completed
- [ ] Post-migration counts checked in target
- [ ] Migrated user roles re-assigned in Admin → Users
- [ ] `./infra/scripts/health.sh` still green (Mongo status still green)
- [ ] Login with a migrated v01 user succeeds using their v01 password

When all 9 boxes are ticked, the migration is complete. Nothing from the v01 VPS Mongo has been lost.
