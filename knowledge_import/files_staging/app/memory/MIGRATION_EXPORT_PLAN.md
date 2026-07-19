# MIGRATION EXPORT PLAN
**Source:** 1-vCPU AI Strategy Factory v10 (this pod)
**Target:** 12-vCPU deployment
**Status:** PLAN ONLY — no archives created yet, no exports executed.
**Discipline:** Read-only audit phase. Operator approval required before §6 (Execution).

---

## 1. EXPORT STRATEGY OVERVIEW

Two parallel export tracks:

| Track | Contents | Tool |
|---|---|---|
| **A. Mongo dump** | All Tier-1 + Tier-2 collections | `mongodump --gzip --archive` |
| **B. Filesystem dump** | `prop_firm_pdfs/`, `memory/` markdown, `inherited/` artifacts | `tar -czf` |

Both tracks produce single-file archives for transfer convenience.

A third optional track (track C, code snapshot) is **not required** if the target already has the latest codebase — see §4.

---

## 2. WHAT TO EXPORT (mapped to tiers)

### TIER 1 — MUST MIGRATE (export & import unconditionally)

| Collection / asset | Approx. size | Rationale |
|---|---|---|
| `strategy_library` (140 docs) | ~1.1 MB | Validated survivor inventory |
| `strategy_lifecycle` (878 docs) | ~0.5 MB | Stage state |
| `strategy_lifecycle_history` (878 docs) | ~0.5 MB | Transition history |
| `mutation_runs` (1,042 docs) | ~7.8 MB | Evolution provenance |
| `mutation_events` (10,430 docs) | ~5.0 MB | Lineage chain |
| `ingested_strategies` (55 docs) | ~0.1 MB | Raw research corpus |
| `governance_universe` (1 doc) | <1 KB | Authoritative universe filter |
| `market_data` (1,053,512 docs) | ~192 MB logical / ~58 MB storage | OHLCV BID + BI5 |
| `users` (1 doc) | <1 KB | Admin seed |
| `prop_firm_rules` (3 docs) | <1 KB | Per-firm rule snapshots |
| `challenge_rules` (3 docs) | <1 KB | Challenge schema snapshots |
| `prop_firm_pdfs/` (22 files, 160 KB) | 160 KB | Source PDFs for rule extraction |
| `.env` task routing block (LLM_TASK_*, MODEL_*) | <1 KB | Hybrid LLM routing |

**Tier-1 total (compressed):** ~70–90 MB

### TIER 2 — STRONGLY RECOMMENDED

| Collection | Docs | Size | Rationale |
|---|---|---|---|
| `research_runs` | 16 | 0.2 MB | Top-level run provenance |
| `multi_cycle_runs` | 6 | 0.07 MB | Multi-cycle history |
| `auto_mutation_runs` | 7 | <1 KB | Auto-runner state |
| `auto_mutation_cycles` | 143 | 0.6 MB | Cycle-level detail |
| `auto_run_cycles` | 86 | 0.3 MB | Run-cycle detail |
| `strategy_market_profile` | 792 | 0.2 MB | Market Score input |
| `market_environment_stats` | 9 | <1 KB | Environment baseline |
| `strategy_performance_history` | 1,047 | 0.5 MB | Evidence Score input |
| `mutation_stability_log` | 1,042 | 0.5 MB | Stability score input |
| `orchestrator_env_priority` | 2 | <1 KB | Knob state |
| `pipeline_logs` | 3,165 | 1.0 MB | Forensics |
| `auto_factory_alert_log` | 13 | <1 KB | Alert trail |
| `llm_call_log` | 5 | <1 KB | LLM provenance |

**Tier-2 total (compressed):** ~2–4 MB

### TIER 3 — CAN REBUILD (optional / skip)

| Collection | Docs | Disposition |
|---|---|---|
| `auto_scheduler_config` | 1 | Recreate on target via UI |
| `orchestrator_scheduler_config` | 1 | Recreate on target via UI |

**Tier-3 total:** negligible. **Recommend skipping.**

---

## 3. WHAT NOT TO EXPORT

- Container artifacts: `archive.zip` (230 MB legacy bundle), `__pycache__/`, `.pytest_cache/`, `node_modules/`
- Secrets file `.env` (operator pastes secrets manually on target)
- Backend codebase if target is already on latest (otherwise see §4)
- Frontend codebase if target is already on latest

---

## 4. CODE SNAPSHOT — OPTIONAL TRACK C

**Skip if:** target 12-vCPU deployment already runs the latest codebase from your VCS (`git pull` on target is the canonical sync path).

**Include if:** target is behind and needs the in-pod changes (Phase 30.1 / 30.2 / 30.3, advisory roadmaps, governance UI).

If included: `tar -czf code.tar.gz /app/backend /app/frontend --exclude='__pycache__' --exclude='node_modules' --exclude='.pytest_cache' --exclude='*.pyc'`

---

## 5. EXPORT COMMANDS (PLAN — DO NOT EXECUTE YET)

### 5.1 Mongo dump (Tier 1 + Tier 2)
```bash
# Single-archive gzip dump of full DB (excludes Tier-3 only by post-filter)
mongodump \
  --uri="mongodb://localhost:27017" \
  --db=test_database \
  --gzip \
  --archive=/tmp/migration/mongo_full.gz \
  --excludeCollection=auto_scheduler_config \
  --excludeCollection=orchestrator_scheduler_config
```
Estimated time: **~60–120 s** (192 MB logical → ~25–35 MB compressed).
Estimated archive size: **~30–40 MB compressed**.

### 5.2 Filesystem dump (PDFs + markdown)
```bash
mkdir -p /tmp/migration
tar -czf /tmp/migration/files.tar.gz \
  /app/backend/prop_firm_pdfs \
  /app/memory \
  /app/inherited
```
Estimated archive size: **~600 KB**.

### 5.3 .env routing extract
```bash
grep -E "^(MODEL_|LLM_TASK_|LLM_PRIMARY|LLM_FALLBACK|LLM_SECONDARY|LLM_ROUTER|LLM_AUTO_FAILOVER|LLM_GENERATOR_ENABLED)" \
  /app/backend/.env > /tmp/migration/llm_routing.env
```
Estimated size: <1 KB. **Operator must paste API keys separately on target.**

### 5.4 Sanity checksum
```bash
cd /tmp/migration && sha256sum mongo_full.gz files.tar.gz llm_routing.env > SHA256SUMS
```

---

## 6. APPROVAL GATE

Before any of §5 runs:
- [ ] Operator confirms Tier-1/Tier-2 list above.
- [ ] Operator confirms target 12-vCPU deployment has compatible Mongo version (4.4+).
- [ ] Operator confirms code track C inclusion or exclusion.
- [ ] Operator confirms `/tmp/migration` (or alternate path) is writable on source.

**Until operator decree, NO commands run. This is the audit boundary.**

---

## 7. IMPORT (HIGH-LEVEL ON TARGET)

```bash
# On target 12-vCPU pod
mongorestore --uri="<target-mongo-uri>" --gzip --archive=mongo_full.gz --nsInclude='test_database.*'
tar -xzf files.tar.gz -C /
# Paste LLM_TASK_*/MODEL_* keys from llm_routing.env into target's /app/backend/.env
# Re-seed admin user via /api/auth/init or accept imported users doc
# Trigger POST_IMPORT_PIPELINE.md (Stage 0 first)
```

See **POST_IMPORT_PIPELINE.md** for the full re-hydration sequence.

---

## 8. ARCHIVE SIZE SUMMARY

| Archive | Estimated size |
|---|---|
| `mongo_full.gz` (Tier-1 + Tier-2) | ~30–40 MB |
| `files.tar.gz` (PDFs + memory + inherited) | ~600 KB |
| `llm_routing.env` (routing block, no secrets) | <1 KB |
| **TOTAL** | **~31–41 MB** |

Comfortably within any transfer mechanism (HTTP download, S3, scp).
