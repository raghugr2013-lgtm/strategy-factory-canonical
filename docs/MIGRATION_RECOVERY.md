# Recovery-DB Migration Runbook — Strategy Factory v1.1.1

**Purpose:** Move historical strategy data (Strategy Library, Explorer rollup, lifecycle & performance history) from the temporary `strategy_factory_recovery` database into the live `strategy_factory_v1` database on the production VPS.

**Author-signed properties of the migration script (`scripts/migrate_strategy_recovery.py`):**
- Read-only on the source — the recovery DB is left untouched as a rollback copy.
- Idempotent — safe to re-run any number of times (`ReplaceOne(upsert=True)` keyed by original `_id`).
- Preserves document IDs and every field.
- Rebuilds non-default indexes on the target.
- Explicit collection whitelist — never touches unrelated production collections.
- Stamps each migrated doc with `__migration_source` and `__migration_ts` so a rollback sweep is a one-liner.

## Collections migrated (whitelist)

Core (from the recovery snapshot):
- `strategies`
- `strategy_library`
- `strategy_library_archive`
- `strategy_lifecycle_history`
- `strategy_performance_history`

Companion (only migrated if present in the source snapshot — silently skipped otherwise):
- `strategy_lifecycle` (current-state)
- `strategy_favorites`
- `strategy_market_profile`
- `strategy_memory`
- `strategy_history`

To migrate anything else from the recovery snapshot, pass `--include COLLECTION_NAME` (repeatable).

---

## Step 1 — Preflight on the VPS

```bash
# ssh into the box
ssh coinnike-vps

# Get a shell inside factory-backend
docker exec -it factory-backend bash

# Sanity: confirm both DBs are reachable
python3 -c "
from pymongo import MongoClient; import os
c = MongoClient(os.environ['MONGO_URL'])
print('recovery:', c['strategy_factory_recovery'].command('dbstats')['collections'], 'collections')
print('v1      :', c['strategy_factory_v1'].command('dbstats')['collections'], 'collections')
"
```

## Step 2 — Discover what's in the recovery DB

```bash
python3 scripts/migrate_strategy_recovery.py \
    --source strategy_factory_recovery \
    --target strategy_factory_v1 \
    --discover
```

Expected output (production numbers you already validated):

```
  strategies                                          1              0
  strategy_library                                   14              0
  strategy_library_archive                          126              0
  strategy_lifecycle_history                        892              0
  strategy_performance_history                     1047              0
```

If any additional `strategy_*` collection appears with `(NOT in default whitelist — pass with --include)`, add it via `--include`.

## Step 3 — Dry-run

Prints the plan, per-collection counts, and every index it would rebuild. Writes nothing.

```bash
python3 scripts/migrate_strategy_recovery.py \
    --source strategy_factory_recovery \
    --target strategy_factory_v1 \
    --dry-run
```

## Step 4 — Real migration

```bash
python3 scripts/migrate_strategy_recovery.py \
    --source strategy_factory_recovery \
    --target strategy_factory_v1
# → interactive prompt "Proceed? [y/N]"
```

To run non-interactively (e.g. from a deploy pipeline), add `--yes`.

Expected result:

```
✓   strategies: 1/1 upserted in 1 batch(es), 0 index(es) rebuilt
✓   strategy_library: 14/14 upserted in 1 batch(es), N index(es) rebuilt
✓   strategy_library_archive: 126/126 upserted in 1 batch(es), N index(es) rebuilt
✓   strategy_lifecycle_history: 892/892 upserted in 2 batch(es), N index(es) rebuilt
✓   strategy_performance_history: 1047/1047 upserted in 3 batch(es), N index(es) rebuilt
✓ Migration complete: 2080/2080 documents upserted, N indexes rebuilt across 5 collection(s).
✓ Verification passed.
```

## Step 5 — Verify from the UI

Log into `https://strategy.coinnike.com` as an admin. Check:

| Module | What to look for |
|---|---|
| **Strategy Explorer** (`/api/strategies/explorer`) | 14 rows appear, each with best_pf / best_dd / stability_score. Filter by `view_mode=inventory` if you want to see rows with no metrics. |
| **Strategy Library** (`/api/library/list`) | 14 items in the "active" library + 126 in the archive tab. |
| **Lifecycle history** (`/api/strategies/{hash}/history`) | Click any Explorer row → history tab shows the 892 lifecycle rows split across hashes. |
| **Performance history** (`/api/strategies/{hash}/history`) | Same panel — performance chart populates from the 1047 rows. |

If any of these still show empty:

```bash
# Backend-side check with curl:
TOKEN=$(curl -s -X POST https://strategy.coinnike.com/api/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"email":"YOUR_ADMIN","password":"YOUR_PASSWORD"}' \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -H "Authorization: Bearer $TOKEN" \
    'https://strategy.coinnike.com/api/library/list' \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('items:', len(d.get('items',[])))"

curl -s -H "Authorization: Bearer $TOKEN" \
    'https://strategy.coinnike.com/api/strategies/explorer?view_mode=inventory' \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('rows:', d.get('count',len(d.get('strategies',[]))))"
```

## Step 6 — Post-migration verify-only sweep (safe, read-only)

```bash
python3 scripts/migrate_strategy_recovery.py \
    --source strategy_factory_recovery \
    --target strategy_factory_v1 \
    --verify-only
```

Exit code 0 = target counts ≥ source counts across all whitelisted collections.

---

## Rollback

The recovery DB is untouched, so rollback is straightforward:

### Option A — Purge only the migrated documents (recommended)

Every migrated document carries a stable marker (`__migration_source == "strategy_factory_recovery"`). To remove them cleanly:

```bash
docker exec -it factory-backend python3 - <<'PY'
from pymongo import MongoClient
import os
c = MongoClient(os.environ["MONGO_URL"])
db = c["strategy_factory_v1"]
for coll in ("strategies", "strategy_library", "strategy_library_archive",
             "strategy_lifecycle_history", "strategy_performance_history",
             "strategy_lifecycle", "strategy_favorites",
             "strategy_market_profile", "strategy_memory", "strategy_history"):
    n = db[coll].delete_many({"__migration_source": "strategy_factory_recovery"}).deleted_count
    print(f"{coll}: purged {n}")
PY
```

Any documents that were already in the target before the migration (i.e. without the marker) are preserved.

### Option B — Drop the entire target and restore from a backup

`strategy_factory_recovery` is the safety copy — you can always re-run the migration from it after purging.

### If you passed `--no-stamp`

The migration metadata is not present. Fall back to option B.

---

## Idempotence & re-runs

Running the migration a second (or hundredth) time is safe:
- Each doc's `_id` is used as the upsert key.
- `bulk_write([ReplaceOne(..., upsert=True), ...])` on an existing doc issues a `modified` op, not a duplicate insert.
- The `__migration_ts` stamp is only added on the first write (`setdefault`), so the timestamp of the very first migration is preserved even after re-runs.

Confirmed by the integration test at `scripts/test_migrate_strategy_recovery.py` — target counts don't change between the first and second `--yes` run.

---

## What the script will NOT do

- Touch `users`, `refresh_tokens`, `mutation_runs`, `mutation_events`, `market_data`, `tick_data`, `pipeline_logs`, `research_queries`, `audit_log`, `challenge_rules`, `data_coverage`, `llm_call_log`, `rebalance_config`, `live_tracking`, or any other collection not on the whitelist.
- Delete any document, ever.
- Create indexes on the target that weren't already present on the source.
- Modify any doc on the source (recovery) DB.

---

## Files

| Path | Purpose |
|---|---|
| `scripts/migrate_strategy_recovery.py` | The migration script itself (CLI + idempotent bulk-upsert). |
| `scripts/test_migrate_strategy_recovery.py` | Integration test proving all six safety properties (read-only source, idempotence, ID preservation, index rebuild, unrelated collection safety, verify-only). Runs against local MongoDB. |
| `docs/MIGRATION_RECOVERY.md` | This runbook. |
