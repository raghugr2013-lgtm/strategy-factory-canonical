# DOWNLOAD MANIFEST
**Purpose:** Single source-of-truth for what to package, exact commands to produce each archive, exact import commands on the 12-vCPU target, and tier classification.
**Status:** PLAN — no archives created. Awaits operator approval.
**Companion docs:** MIGRATION_EXPORT_PLAN.md, MIGRATION_COMPATIBILITY_AUDIT.md, POST_IMPORT_PIPELINE.md, DISCOVERY_GAP_REPORT.md

---

## 1. TIER MATRIX (final)

| Tier | Meaning | Total docs | Logical size | Compressed |
|---|---|---|---|---|
| **Tier 1 — MUST migrate** | Irreplaceable strategy intelligence | ~1,058,531 | ~204 MB | ~30–40 MB |
| **Tier 2 — STRONGLY recommended** | Useful but partially recomputable | ~7,333 | ~3.4 MB | ~1 MB |
| **Tier 3 — Can rebuild** | Trivially recreatable on target | 2 | <1 KB | skip |

---

## 2. EXACT FILES, FOLDERS, COLLECTIONS

### TIER 1 — MongoDB collections (DB: `test_database`)
1. `strategy_library` — 140 docs (~1.1 MB)
2. `strategy_lifecycle` — 878 docs (~0.5 MB)
3. `strategy_lifecycle_history` — 878 docs (~0.5 MB)
4. `mutation_runs` — 1,042 docs (~7.8 MB)
5. `mutation_events` — 10,430 docs (~5.0 MB)
6. `ingested_strategies` — 55 docs (~0.1 MB)
7. `governance_universe` — 1 doc (<1 KB)
8. `market_data` — 1,053,512 docs (~192 MB logical)
9. `users` — 1 doc (<1 KB)
10. `prop_firm_rules` — 3 docs (<1 KB)
11. `challenge_rules` — 3 docs (<1 KB)

### TIER 1 — Filesystem
- `/app/backend/prop_firm_pdfs/` (22 files, ~160 KB)

### TIER 1 — Configuration (text only, secrets excluded)
- LLM task routing block from `/app/backend/.env`:
  `MODEL_OPENAI, MODEL_ANTHROPIC, MODEL_DEEPSEEK,`
  `LLM_TASK_STRATEGY, LLM_TASK_CBOT, LLM_TASK_MUTATION,`
  `LLM_TASK_ANALYSIS, LLM_TASK_INGESTION, LLM_TASK_PROPFIRM,`
  `LLM_GENERATOR_ENABLED, LLM_ROUTER_ENABLED, LLM_AUTO_FAILOVER,`
  `LLM_PRIMARY_PROVIDER, LLM_FALLBACK_PROVIDER, LLM_SECONDARY_FALLBACK`

### TIER 2 — MongoDB collections
12. `research_runs` — 16 docs
13. `multi_cycle_runs` — 6 docs
14. `auto_mutation_runs` — 7 docs
15. `auto_mutation_cycles` — 143 docs
16. `auto_run_cycles` — 86 docs
17. `strategy_market_profile` — 792 docs
18. `market_environment_stats` — 9 docs
19. `strategy_performance_history` — 1,047 docs
20. `mutation_stability_log` — 1,042 docs
21. `orchestrator_env_priority` — 2 docs
22. `pipeline_logs` — 3,165 docs
23. `auto_factory_alert_log` — 13 docs
24. `llm_call_log` — 5 docs

### TIER 2 — Filesystem (provenance + docs)
- `/app/memory/` (markdown roadmaps, phase docs, audit docs)
- `/app/inherited/` (legacy reference artifacts, ~460 KB)

### TIER 3 — Skip (recreate on target)
- `auto_scheduler_config` (1 doc) — set via Governance UI on target
- `orchestrator_scheduler_config` (1 doc) — set via Governance UI on target

### EXCLUDED (do NOT migrate)
- `archive.zip` (230 MB legacy bundle in repo root)
- All `__pycache__/`, `.pytest_cache/`, `node_modules/`
- Raw `.env` (secrets must be operator-pasted on target)
- `test_reports/`, `tests/` (regenerable; not strategy intelligence)

---

## 3. EXPORT COMMANDS (PLAN — operator approval required)

### 3.1 Prep
```bash
mkdir -p /tmp/migration && cd /tmp/migration
```

### 3.2 Mongo dump — single archive, gzip
```bash
mongodump \
  --uri="mongodb://localhost:27017" \
  --db=test_database \
  --gzip \
  --archive=/tmp/migration/mongo_full.gz \
  --excludeCollection=auto_scheduler_config \
  --excludeCollection=orchestrator_scheduler_config
```
- Estimated runtime: 60–120 s
- Estimated output size: 30–40 MB

### 3.3 Filesystem tar
```bash
tar -czf /tmp/migration/files.tar.gz \
  -C / \
  app/backend/prop_firm_pdfs \
  app/memory \
  app/inherited
```
- Estimated size: ~600 KB

### 3.4 LLM routing block extract (no secrets)
```bash
grep -E "^(MODEL_|LLM_)" /app/backend/.env \
  | grep -v "API_KEY" \
  | grep -v "EMERGENT_LLM_KEY" \
  > /tmp/migration/llm_routing.env
```
- Estimated size: <1 KB

### 3.5 Checksums + manifest
```bash
cd /tmp/migration
sha256sum mongo_full.gz files.tar.gz llm_routing.env > SHA256SUMS
ls -la > LISTING.txt
```

### 3.6 (Optional) Combined download bundle
```bash
cd /tmp/migration
tar -cf migration_bundle.tar mongo_full.gz files.tar.gz llm_routing.env SHA256SUMS LISTING.txt
```
- Estimated final bundle: ~31–41 MB

---

## 4. IMPORT INSTRUCTIONS — TARGET 12-vCPU POD

### 4.1 Prerequisites on target
- Mongo 4.4+ available at the configured `MONGO_URL`
- `mongorestore` binary available in the container
- Writable `/app/backend/` filesystem
- Target codebase up to date

### 4.2 Restore order

**Step 1 — Transfer the bundle** to the target pod (scp, S3, HTTP download — operator's choice).

**Step 2 — Verify integrity:**
```bash
cd /tmp/migration && sha256sum -c SHA256SUMS
```

**Step 3 — Restore Mongo (single archive):**
```bash
mongorestore \
  --uri="$MONGO_URL" \
  --nsInclude="test_database.*" \
  --gzip \
  --archive=/tmp/migration/mongo_full.gz \
  --drop  # ⚠ drops only the collections being restored; preserves anything new on target
```
> ⚠️ **Operator decides** whether `--drop` is appropriate. If the 12-vCPU pod already contains *its own* strategy intelligence that should be preserved, OMIT `--drop` and rely on natural upsert semantics — but be aware `mongorestore` does NOT upsert; it inserts. For collisions, see §4.5 (collision handling).

**Step 4 — Restore filesystem assets:**
```bash
tar -xzf /tmp/migration/files.tar.gz -C /
```

**Step 5 — Merge LLM routing into target `.env`** (manual — append/replace):
```bash
# Operator pastes contents of llm_routing.env into target's /app/backend/.env
# Then pastes API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, DEEPSEEK_API_KEY) manually.
sudo supervisorctl restart backend
```

**Step 6 — Verify import:**
```bash
curl -s "$REACT_APP_BACKEND_URL/api/governance/universe" | jq
curl -s "$REACT_APP_BACKEND_URL/api/llm/diagnostics"     | jq
# Confirm strategy_library count == 140, mutation_runs == 1042, market_data == 1,053,512
```

**Step 7 — Trigger POST_IMPORT_PIPELINE** (Stage 0 first, then per operator decree).

### 4.3 Auto-flag safety check
After import, verify on target:
- `AUTONOMOUS_DISCOVERY_ENABLED=False`
- `auto_replace_enabled=False`
- `auto_scheduler_config.enabled=False` (or absent — Tier 3 not migrated)
- `orchestrator_scheduler_config.enabled=False` (or absent)

**Re-enable only after Stage 8 of POST_IMPORT_PIPELINE completes and operator decrees.**

### 4.4 Index rebuild check
`mongorestore` recreates indexes from the archive. Verify:
```javascript
db.market_data.getIndexes()
db.strategy_library.getIndexes()
db.strategy_lifecycle.getIndexes()
```
Expect unique indexes on `(symbol,source,timeframe,timestamp)`, `fingerprint`, and `strategy_hash`.

### 4.5 Collision handling (if target already has data)
If the target already runs and has its own collections, **do NOT use `--drop`**. Instead:
1. Restore into a staging namespace: `--nsFrom='test_database.*' --nsTo='migrated_v10.*'`
2. Run a per-collection merge script that upserts by natural key (fingerprint / strategy_hash / (symbol,source,timeframe,timestamp)).
3. Drop the `migrated_v10.*` namespace once merge is complete.

---

## 5. ARCHIVE SIZE SUMMARY

| Archive | Estimated size |
|---|---|
| `mongo_full.gz` | 30–40 MB |
| `files.tar.gz` | ~600 KB |
| `llm_routing.env` | <1 KB |
| **TOTAL bundle** | **~31–41 MB** |

---

## 6. APPROVAL CHECKLIST (operator)

- [ ] Tier classification reviewed and approved
- [ ] `--drop` vs. merge strategy decided (§4.5)
- [ ] Target pod has compatible Mongo + `mongorestore`
- [ ] Target codebase confirmed to include Phase 30.1/30.2/30.3 (else add code track C from MIGRATION_EXPORT_PLAN §4)
- [ ] API keys ready for manual paste on target
- [ ] Autonomy flags will remain OFF on target until post-import pipeline completes

**Once all boxes are checked, the export commands in §3 may be executed.**
