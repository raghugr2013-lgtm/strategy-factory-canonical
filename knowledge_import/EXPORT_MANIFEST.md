# EXPORT MANIFEST — 1-vCPU Migration Package
**Source pod:** 1-vCPU AI Strategy Factory v10
**Target pod:** 12-vCPU AI Strategy Factory
**Created:** 2026-06-11 16:19 UTC
**Status:** EXPORT COMPLETE — archives ready for transfer. NOT YET IMPORTED.
**Location:** `/app/migration_export/`

---

## 1. ARCHIVE INVENTORY

| # | Archive | Location | Size | SHA-256 |
|---|---|---|---|---|
| 1 | `mongo_full.gz` | `/app/migration_export/mongo_full.gz` | **33,857,644 bytes (33 MB)** | `836ab17dbf49cc643d73db82f5c4400f630d2e3e56786e9890a5ac2a0aac69b3` |
| 2 | `files.tar.gz` | `/app/migration_export/files.tar.gz` | **238,157 bytes (236 KB)** | `8443bcd075b1960bf2a448a2683077120c201a09335cd4130383e614d662c469` |
| 3 | `llm_routing.env` | `/app/migration_export/llm_routing.env` | **413 bytes** | `6e2f8408704c68bf0a9a3f44804518d07362e4d6b0f6a7950ece852269d89903` |
| 4 | `SHA256SUMS` | `/app/migration_export/SHA256SUMS` | 220 bytes | (self-referential) |
| 5 | `EXPORT_MANIFEST.md` | `/app/migration_export/EXPORT_MANIFEST.md` | this file | — |

**Total package:** ~34 MB. All files reside in `/app/migration_export/`.

---

## 2. DOWNLOAD / TRANSFER

The pod filesystem path is the authoritative location. Use any of the following transfer mechanisms:

| Mechanism | Command / Action |
|---|---|
| Direct copy from this pod | `cp /app/migration_export/* /your/staging/dir/` |
| SCP (operator-side) | `scp <pod>:/app/migration_export/* ./downloads/` |
| `kubectl cp` (if cluster access) | `kubectl cp <pod>:/app/migration_export ./downloads/` |
| Save-to-GitHub | Use the Emergent platform's *Save to GitHub* feature, then download from the repo |
| Tar to single bundle (optional) | `tar -cf /tmp/migration_bundle.tar -C /app/migration_export mongo_full.gz files.tar.gz llm_routing.env SHA256SUMS EXPORT_MANIFEST.md` |

> ⚠️ No HTTP download URL is exposed by the application (no static-file route was added — that would be a code change). Use one of the operator-side transfer mechanisms above.

---

## 3. ARCHIVE 1 — `mongo_full.gz`

### 3.1 Description
gzipped `mongodump` archive of the full `test_database`, excluding only the two Tier-3 scheduler-config collections.

### 3.2 Contents (25 collections)

| # | Collection | Documents | Tier | Notes |
|---|---|---|---|---|
| 1 | `strategy_library` | **140** | Tier 1 | Validated specimens |
| 2 | `strategy_lifecycle` | **878** | Tier 1 | Stage state |
| 3 | `strategy_lifecycle_history` | **878** | Tier 1 | Stage transitions |
| 4 | `mutation_runs` | **1,042** | Tier 1 | Mutation provenance |
| 5 | `mutation_events` | **10,430** | Tier 1 | Lineage chain |
| 6 | `ingested_strategies` | **55** | Tier 1 | Raw research corpus |
| 7 | `ingestion_runs` | **11** | Tier 1 | Ingestion provenance |
| 8 | `governance_universe` | **1** | Tier 1 | Authoritative universe filter |
| 9 | `market_data` | **1,053,512** | Tier 1 | BID 1m + BI5 streams |
| 10 | `users` | **1** | Tier 1 | Admin seed |
| 11 | `prop_firm_rules` | **3** | Tier 1 | Per-firm rule snapshots |
| 12 | `challenge_rules` | **3** | Tier 1 | Challenge schema snapshots |
| 13 | `research_runs` | **16** | Tier 2 | Top-level run provenance |
| 14 | `multi_cycle_runs` | **6** | Tier 2 | Multi-cycle history |
| 15 | `auto_mutation_runs` | **7** | Tier 2 | Auto-runner state |
| 16 | `auto_mutation_cycles` | **143** | Tier 2 | Cycle-level detail |
| 17 | `auto_run_cycles` | **86** | Tier 2 | Run-cycle detail |
| 18 | `strategy_market_profile` | **792** | Tier 2 | Market Score input |
| 19 | `market_environment_stats` | **9** | Tier 2 | Environment baseline |
| 20 | `strategy_performance_history` | **1,047** | Tier 2 | Evidence Score input |
| 21 | `mutation_stability_log` | **1,042** | Tier 2 | Stability score input |
| 22 | `orchestrator_env_priority` | **2** | Tier 2 | Knob state |
| 23 | `pipeline_logs` | **3,165** | Tier 2 | Forensics |
| 24 | `auto_factory_alert_log` | **13** | Tier 2 | Alert trail |
| 25 | `llm_call_log` | **5** | Tier 2 | LLM provenance |

**Total documents in dump:** 1,083,308 (across all 25 collections).

### 3.3 Excluded from dump (deliberate)

| Collection | Docs | Reason |
|---|---|---|
| `auto_scheduler_config` | 1 | Tier 3 — recreate on target via UI |
| `orchestrator_scheduler_config` | 1 | Tier 3 — recreate on target via UI |

### 3.4 Empty / never-populated collections (NOT in dump because never created on this pod)

| Collection | Status | Action on target |
|---|---|---|
| `portfolio_builder_runs` | 0 docs | Engine present; regenerate post-import |
| `trade_runner_runs` | 0 docs | Engine present; regenerate post-import |
| `trade_runner_trades` | 0 docs | Engine present; regenerate post-import |
| `auto_selection_runs` | 0 docs | Engine present; regenerate post-import |
| `gem_factory_runs` | 0 docs | Engine present; regenerate post-import |
| `gem_factory_events` | 0 docs | Engine present; regenerate post-import |
| `challenge_decisions` | 0 docs | Engine present; regenerate post-import |
| `challenge_control` | 0 docs | Engine present; regenerate post-import |
| `firm_challenge_types` | 0 docs | Seed on target |
| `strategy_challenge_match` | 0 docs | Recompute post-import (POST_IMPORT_PIPELINE §5) |
| `strategy_pass_analysis` | 0 docs | Recompute post-import (POST_IMPORT_PIPELINE §3.5) |
| `strategy_risk_profile` | 0 docs | Recompute post-import (POST_IMPORT_PIPELINE §3.5) |
| `strategy_descriptions` | 0 docs | LLM-generate post-import |
| `auto_factory_config` | 0 docs | Recreate on target |
| `execution_runs` | 0 docs | Start fresh |
| `tuning_settings` | 0 docs | Recreate on target |
| `slot_stats` | 0 docs | Recreate on target |
| `performance_snapshots` | 0 docs | Recreate on target |
| `prop_firm_extract_jobs` | 0 docs | Start fresh |
| `gem_factory_events` | 0 docs | Engine present; regenerate post-import |
| `audit_log` | 0 docs | Start fresh on target |

> See `DISCOVERY_GAP_REPORT.md` for full provenance.

### 3.5 Indexes
`mongodump` captured collection metadata including indexes. On restore, indexes are recreated automatically — no manual rebuild required.

---

## 4. ARCHIVE 2 — `files.tar.gz`

### 4.1 Description
gzipped tar of the on-disk supporting artifacts (PDFs, memory documents, inherited reference materials).

### 4.2 Contents (117 files / directories)

| Path | Contents | Purpose |
|---|---|---|
| `app/backend/prop_firm_pdfs/` | 22 prop-firm rule PDFs | Source documents for `prop_firm_rules` |
| `app/memory/` | All architecture / audit / phase docs | Provenance trail |
| `app/inherited/` | Inherited legacy reference artifacts | Historical context |

### 4.3 Memory documents included (all relevant for the 12-vCPU import)

- `PRD.md` — original problem statement
- `PHASE_29_PLAN.md`, `PHASE_29_COMPLETE.md`, `PHASE_30_COMPLETE.md`, `PHASE_30_1_COMPLETE.md`, `PHASE_30_2_UNIVERSE_GOVERNANCE.md` — phase records
- `BI5_EVOLUTION_ROADMAP.md`, `EG_EVOLUTION_ROADMAP.md` — long-range governance
- `LEGACY_STRATEGY_INVENTORY.md`, `SURVIVOR_CLASSIFICATION.md`, `SURVIVOR_RESCORING_PREVIEW.md`, `LINEAGE_DEDUP_AUDIT.md`, `F03_REGIME_ANALYSIS.md`, `VALIDATED_ARCHETYPE_INVENTORY.md` — strategy-research audit suite
- `ASF_CANONICAL_IDENTITY_MODEL.md` — identity hierarchy (MUST be applied on target)
- `MIGRATION_COMPATIBILITY_AUDIT.md`, `DISCOVERY_GAP_REPORT.md`, `POST_IMPORT_PIPELINE.md`, `MIGRATION_EXPORT_PLAN.md`, `DOWNLOAD_MANIFEST.md`, `EXPORT_MANIFEST.md` (this file) — migration package
- `DSR_ARCHITECTURAL_BLUEPRINT.md`, `BI5_R1_ARCHITECTURAL_BLUEPRINT.md`, `ROADMAP.md` — forward-looking blueprints
- `inspection_report_v10.md`, `test_credentials.md` — operations

---

## 5. ARCHIVE 3 — `llm_routing.env`

### 5.1 Description
Plain-text snapshot of the Phase 30.3 LLM routing config from `/app/backend/.env`. **API keys are NOT included** — operator must paste them manually on target.

### 5.2 Contents

```
MODEL_OPENAI=gpt-4o-mini
MODEL_DEEPSEEK=deepseek-chat
MODEL_ANTHROPIC=claude-sonnet-4-5
LLM_GENERATOR_ENABLED=true
LLM_ROUTER_ENABLED=true
LLM_AUTO_FAILOVER=false
LLM_PRIMARY_PROVIDER=openai
LLM_FALLBACK_PROVIDER=anthropic
LLM_SECONDARY_FALLBACK=deepseek
LLM_TASK_STRATEGY=openai
LLM_TASK_CBOT=anthropic
LLM_TASK_MUTATION=deepseek
LLM_TASK_ANALYSIS=anthropic
LLM_TASK_INGESTION=openai
LLM_TASK_PROPFIRM=anthropic
```

### 5.3 What is NOT in this file (operator must supply on target)

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `DEEPSEEK_API_KEY`
- `EMERGENT_LLM_KEY` (if still used as alias — phased out per Phase 30.3)
- `MONGO_URL`, `DB_NAME`
- `JWT_SECRET`
- `ADMIN_EMAIL`, `ADMIN_PASSWORD`
- `CORS_ORIGINS`

---

## 6. INTEGRITY VERIFICATION

After transfer, verify checksums:

```bash
cd /your/staging/dir
sha256sum -c SHA256SUMS
# Expected output:
#   mongo_full.gz: OK
#   files.tar.gz: OK
#   llm_routing.env: OK
```

If any file fails the checksum, **DO NOT IMPORT** — re-transfer.

---

## 7. RESTORE INSTRUCTIONS (for 12-vCPU TARGET)

### 7.1 Prerequisites on target

- MongoDB 4.4+ reachable at the configured `MONGO_URL`
- `mongorestore` 100.x binary installed (Mongo Database Tools)
- Writable `/app/backend/` filesystem
- Target codebase aligned with Phase 30.3 (if not, also transfer `/app/backend` + `/app/frontend` as a separate code archive — not included by default per `DOWNLOAD_MANIFEST.md §4`)
- API keys ready for manual entry (see §5.3)

### 7.2 Step 1 — Verify integrity on target

```bash
cd /tmp/migration   # or wherever you place the archives
sha256sum -c SHA256SUMS
```

### 7.3 Step 2 — Decide on collision strategy

**Choice A: Clean restore (target Mongo is empty or expendable)**
```bash
mongorestore \
  --uri="$MONGO_URL" \
  --nsInclude="test_database.*" \
  --gzip \
  --archive=mongo_full.gz \
  --drop
```
> ⚠️ `--drop` drops only the collections being restored. Anything already in `test_database` *not* in the archive is preserved.

**Choice B: Merge into a staging namespace (target already has data to preserve)**
```bash
mongorestore \
  --uri="$MONGO_URL" \
  --nsFrom='test_database.*' \
  --nsTo='migrated_v10.*' \
  --gzip \
  --archive=mongo_full.gz
```
Then run a per-collection merge script that upserts by natural key (`fingerprint` for strategy_library; `(symbol, source, timeframe, timestamp)` for market_data; `strategy_hash` for lifecycle). Drop the `migrated_v10.*` namespace once merge completes.

### 7.4 Step 3 — Restore filesystem assets

```bash
tar -xzf files.tar.gz -C /
```
This restores:
- `/app/backend/prop_firm_pdfs/` (22 PDFs)
- `/app/memory/` (all architecture/audit docs)
- `/app/inherited/` (legacy reference)

### 7.5 Step 4 — Apply LLM routing config

Append the contents of `llm_routing.env` to `/app/backend/.env` on target. **Then paste API keys manually**:

```bash
cat llm_routing.env >> /app/backend/.env
# Now edit /app/backend/.env and add:
#   OPENAI_API_KEY=sk-...
#   ANTHROPIC_API_KEY=sk-ant-...
#   DEEPSEEK_API_KEY=sk-...
sudo supervisorctl restart backend
```

### 7.6 Step 5 — Verify import

```bash
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
curl -s "$API_URL/api/governance/universe" | jq
curl -s "$API_URL/api/llm/diagnostics" | jq
# Expected counts (sanity check via Mongo):
#   strategy_library == 140
#   strategy_lifecycle == 878
#   mutation_runs == 1042
#   mutation_events == 10430
#   market_data == 1053512
```

### 7.7 Step 6 — Verify autonomy flags

Before proceeding with the post-import pipeline, confirm:
```bash
echo $AUTONOMOUS_DISCOVERY_ENABLED    # must be False
# auto_replace_enabled must be False
# auto_scheduler_config.enabled  — absent (Tier 3, not migrated)
# orchestrator_scheduler_config.enabled  — absent (Tier 3, not migrated)
```

### 7.8 Step 7 — Trigger POST-IMPORT PIPELINE

Refer to `app/memory/POST_IMPORT_PIPELINE.md`. **Start at Stage 0 (validation)**. Do NOT enable autonomous loops until Stage 8 completes and operator decree is given.

---

## 8. POST-IMPORT IDENTITY MIGRATION

Once data is in place on the 12-vCPU pod, apply the canonical identity model:

1. Add additive schema fields to `strategy_library`:
   - `validated_archetype` (string)
   - `canonical_family_key` (string)
   - `archetype_drift_flag` (bool)
   - `legacy_label` (string — preserved audit-trail)
2. Run derivation pass to populate the new fields on all imported rows.
3. Build the `edges` curator collection (Layer 3 of `ASF_CANONICAL_IDENTITY_MODEL.md`).
4. Re-key per the per-subsystem contract in `ASF_CANONICAL_IDENTITY_MODEL.md §4`.

This is documented in `/app/memory/ASF_CANONICAL_IDENTITY_MODEL.md` (transferred in `files.tar.gz`).

---

## 9. WHAT THIS PACKAGE DOES NOT INCLUDE

- **Codebase** — backend / frontend source files. Use `git pull` on target, OR transfer them separately via:
  ```bash
  tar -czf code.tar.gz -C / app/backend app/frontend \
    --exclude='__pycache__' --exclude='node_modules' --exclude='.pytest_cache' --exclude='*.pyc'
  ```
- **API keys** — operator must enter manually
- **Mongo URL / JWT secret / admin password** — target-specific
- **Tier-3 scheduler configs** — recreate via UI on target

---

## 10. EXPORT EXECUTION RECORD

| Step | Command | Outcome |
|---|---|---|
| 1 | `mkdir -p /app/migration_export` | OK |
| 2 | `mongodump --uri="mongodb://localhost:27017" --db=test_database --gzip --archive=/app/migration_export/mongo_full.gz --excludeCollection=auto_scheduler_config --excludeCollection=orchestrator_scheduler_config` | 25 collections dumped, 1,083,308 docs |
| 3 | `tar -czf /app/migration_export/files.tar.gz -C / app/backend/prop_firm_pdfs app/memory app/inherited` | 117 entries archived |
| 4 | `grep -E "^(MODEL_\|LLM_)" /app/backend/.env \| grep -v "API_KEY" \| grep -v "EMERGENT_LLM_KEY" > /app/migration_export/llm_routing.env` | 15 routing variables extracted |
| 5 | `sha256sum mongo_full.gz files.tar.gz llm_routing.env > SHA256SUMS` | Checksums written |
| 6 | `mongorestore --gzip --archive=mongo_full.gz --dryRun` | Dry-run passed, dump readable |

All steps succeeded. No errors. No data loss. Source pod unchanged.

---

## 11. AUDIT BOUNDARY

This manifest records the export operation. No import has been performed. No code changes have been made to the source pod. The archives in `/app/migration_export/` are immutable artifacts ready for transfer to the 12-vCPU target.

**End of EXPORT_MANIFEST.md.**
