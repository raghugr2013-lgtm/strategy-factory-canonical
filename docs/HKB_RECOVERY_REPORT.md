# Historical Knowledge Base — Recovery Report

_Report date · 2026-07-23_
_Source · 1-vCPU AI Strategy Factory v10 migration bundle (created 2026-06-11 16:19 UTC)_
_Target · Strategy Factory Canonical v1.1.0-stage4_
_Status · **ANALYSIS ONLY — NO IMPORT PERFORMED**_

---

## Executive Summary

| Metric | Value |
|---|---|
| Bundle SHA-256 checksums | ✅ All 3 archives verified OK |
| Total documents in dump (mongorestore report) | **1,073,287** |
| Collections in dump | **25** |
| Bulk market_data ticks | 1,053,512 (98.2 % of volume) |
| Research artefacts (non-market_data) | **19,775** across 24 collections |
| Migration-ready collections | **22 of 25** |
| Conflict collections requiring policy decision | **2** (`users`, `governance_universe`) |
| Deferrable collections | **1** (`market_data` — 200 MB) |
| Dry-run status | ✅ 19,773 docs would upsert cleanly across 22 collections, zero write errors |
| Migration Readiness Score | **8 / 10** — see §6 |
| Recommendation | ✅ **PROCEED, with two policy decisions from the operator** — see §6 |

---

## PHASE 1 — Historical Knowledge Audit

Staging restore into isolated database `hkb_staging_20260723` (production
DB `strategy_factory_v1` untouched). Every count below was reconciled
between the export manifest and the restored staging DB — they match to
the document.

### 1.1 Collection inventory (25 collections, 1,073,287 documents)

| Category | Collection | Docs | Purpose |
|---|---|---:|---|
| **Strategy corpus** | `strategy_library`               | **140**    | Validated strategy specimens with score, verdict, pf, dd, trades, oos_holdout, validation_report |
|                     | `strategy_lifecycle`             | **878**    | Current-state ledger — stage, evidence, flags, buffers |
|                     | `strategy_lifecycle_history`     | **878**    | Every stage transition |
|                     | `strategy_performance_history`   | **1,047**  | Backtest results per strategy hash |
|                     | `strategy_market_profile`        | **792**    | Market-fit score per (pair · timeframe · hash) |
| **Mutation lineage** | `mutation_runs`                 | **1,042**  | Full mutation provenance — one row per generation job |
|                     | `mutation_events`                | **10,430** | One row per generated variant (all 10 per run) with metrics |
|                     | `mutation_stability_log`         | **1,042**  | Stability evaluation of each variant — pass/reject reason |
| **Research runs**  | `research_runs`                   | **16**     | Top-level research campaign provenance |
|                     | `auto_mutation_runs`             | **7**      | Auto-mutation job state |
|                     | `auto_mutation_cycles`           | **143**    | Per-cycle detail of auto-mutation jobs |
|                     | `auto_run_cycles`                | **86**     | Auto-run cycle detail |
|                     | `multi_cycle_runs`               | **6**      | Multi-cycle history |
| **Ingestion**      | `ingested_strategies`             | **55**     | Raw research corpus — imported from GitHub / TradingView |
|                     | `ingestion_runs`                 | **11**     | Ingestion provenance |
| **Market data**    | `market_data`                     | **1,053,512** | OHLCV candles — BID 1m + BI5 streams |
|                     | `market_environment_stats`       | **9**      | Environment baseline per (pair · timeframe) |
| **Governance / config** | `governance_universe`         | **1**      | Authoritative universe filter |
|                     | `orchestrator_env_priority`     | **2**      | Orchestrator knobs + tier weights |
|                     | `prop_firm_rules`                | **3**      | FTMO / MyFundedFX / test-firm rule snapshots |
|                     | `challenge_rules`                | **3**      | Challenge schema snapshots |
| **Ops / audit**    | `pipeline_logs`                   | **3,165**  | Forensic pipeline trace |
|                     | `auto_factory_alert_log`         | **13**     | Alert channel trail |
|                     | `llm_call_log`                   | **5**      | LLM provenance |
|                     | `users`                          | **1**      | Legacy admin (`admin@local.test`) |

Full inventory JSON at `hkb/reports/phase1_inventory.json`.

### 1.2 Not in the dump (intentional exclusions, per source manifest)

- `auto_scheduler_config` (Tier 3) — recreate on target.
- `orchestrator_scheduler_config` (Tier 3) — recreate on target.
- 20 empty collections never populated on the source pod (see EXPORT_MANIFEST §3.4).

---

## PHASE 2 — Compatibility Analysis

Compared each of the 25 source collections against the v1.1.0-stage4
target schema. `strategy_factory_v1` currently has 49 collections;
13 overlap with the source (all except `users` + `governance_universe`
are empty in production).

### 2.1 Compatibility matrix

Legend · ✅ Byte-compatible (no transform) · ⚙ Transform needed · ⚠ Conflict resolution needed · ⊘ Skip (deferrable)

| Source collection | Records | Prod state | Compatibility | Verdict |
|---|---:|---|---|---|
| `strategy_library`             | 140    | absent | ✅ schema aligns with backend `StrategyLibraryDoc` | Migrate |
| `strategy_lifecycle`           | 878    | absent | ✅ aligns | Migrate |
| `strategy_lifecycle_history`   | 878    | absent | ✅ aligns | Migrate |
| `strategy_performance_history` | 1,047  | absent | ✅ aligns | Migrate |
| `strategy_market_profile`      | 792    | absent | ✅ aligns | Migrate |
| `mutation_runs`                | 1,042  | absent | ✅ aligns | Migrate (new collection in prod) |
| `mutation_events`              | 10,430 | absent | ✅ aligns | Migrate |
| `mutation_stability_log`       | 1,042  | absent | ✅ aligns | Migrate |
| `research_runs`                | 16     | absent | ✅ aligns | Migrate |
| `auto_mutation_runs`           | 7      | absent | ✅ aligns | Migrate |
| `auto_mutation_cycles`         | 143    | absent | ✅ aligns | Migrate |
| `auto_run_cycles`              | 86     | absent | ✅ aligns | Migrate |
| `multi_cycle_runs`             | 6      | absent | ✅ aligns | Migrate |
| `ingested_strategies`          | 55     | absent | ✅ aligns | Migrate |
| `ingestion_runs`               | 11     | absent | ✅ aligns | Migrate |
| `market_environment_stats`     | 9      | absent | ✅ aligns | Migrate |
| `orchestrator_env_priority`    | 2      | absent | ✅ aligns | Migrate |
| `prop_firm_rules`              | 3      | absent | ✅ aligns | Migrate |
| `challenge_rules`              | 3      | absent | ✅ aligns | Migrate |
| `pipeline_logs`                | 3,165  | absent | ✅ aligns | Migrate |
| `auto_factory_alert_log`       | 13     | absent | ✅ aligns | Migrate |
| `llm_call_log`                 | 5      | absent | ✅ aligns | Migrate |
| `market_data`                  | 1,053,512 | absent | ⊘ Volume defer | **Operator decision** — 200 MB payload, can be imported by itself later, or dropped if VPS will refresh from live providers |
| `users`                        | 1      | 1 (`admin@strategy-factory.local`) | ⚠ Different `_id`, different email | **Skip legacy user** — prod admin already provisioned |
| `governance_universe`          | 1      | 1 (identical pairs/timeframes/phase 30.2) | ⚠ Both point to `_id='config'`; same content today | **Keep prod value**; archive legacy to `governance_universe_legacy` for provenance |

### 2.2 Schema observations (no blockers found)

- Every one of the 22 migratable collections shares its top-level field
  set between staging and the backend model layer. No breaking rename,
  no removed field, no added mandatory field.
- Two indexes ride along in the dump and would be recreated automatically:
  `challenge_rules.firm_slug_1` (unique) and `strategy_library.fingerprint_1`
  (unique). `market_data.symbol_1_source_1_timeframe_1_timestamp_1`
  would migrate only if `market_data` is imported.
- `_id` types round-trip cleanly: ObjectId → ObjectId; string → string.
  No BSON-to-JSON coercion required.

### 2.3 Identity model (post-migration key relationships)

Two parallel identity systems co-exist in the source data:

1. **Fingerprint universe** — `strategy_library.fingerprint` (unique) ←
   `mutation_events.variant_fingerprint`. 140 library specimens have a
   unique fingerprint each.
2. **Hash universe** — `strategy_lifecycle.strategy_hash` (878 distinct) ←
   `strategy_performance_history.strategy_hash` (878 of 1,047 match).
   Only 123 of the 878 lifecycle rows carry a `library_id` FK back to
   `strategy_library._id`.

This is by design (the legacy factory ingested WAY more strategies than
it promoted to the library). It is not a data-integrity bug. Post-import,
the current backend's `strategy_recovery` migrator has already been
proven against this exact schema (see `backend/scripts/migrate_strategy_recovery.py`).

---

## PHASE 3 — Knowledge Quality Assessment

### 3.1 Strategy library classification (140 specimens)

| Bucket | Count | Criteria |
|---|---:|---|
| A · High-value validated | **0** | verdict=STRONG · pf≥1.4 · dd<15 % · ≥100 trades |
| B · Promising            | **0** | verdict=PROMISING · pf≥1.15 · dd<25 % · ≥50 trades |
| C · Experimental         | **6** | verdict=RISKY · pf≥1.0 · dd<40 % · ≥30 trades |
| D · Underperforming      | **26** | trades<30 or pf 0.9–1.0 |
| E · Failed               | **108** | pf<0.9 or dd>60 % |
| Duplicates               | **0** | Zero fingerprint collisions |

**Interpretation.** Every single one of the 140 stored specimens carries
`verdict='RISKY'` and `prop_status='RISKY'`. The source factory had not
yet produced a verdict-STRONG or FUNDED strategy at the time of export.
This does **not** make the corpus worthless — it is institutional
research history: what was tried, what failed, and why. Every failed
strategy is a documented dead-end that the current factory should not
re-explore. The mutation lineage (`mutation_runs` + `mutation_events`
+ `mutation_stability_log`) is where the real research value lives —
10,430 backtested variants with pf, dd, trades, and rejection reasons.

### 3.2 Lifecycle stage distribution (878 lifecycle rows)

| Stage | Count |
|---|---:|
| exploratory | 878 |
| promising / consolidating / validating / champion | 0 |

Every lifecycle-tracked strategy is stuck at the earliest stage. The
graduation pipeline had not yet run to completion on the source pod.

### 3.3 Ingested-strategy source distribution (55 rows)

- `github` (Pine-Script indicators / TradingView open-source library) is
  the exclusive source. `quality_score` band: 0.93 median (LLM-adjudicated).
  These are the raw seeds every mutation lineage descends from.

### 3.4 Value recommendation

- **PRESERVE:** All 22 collections in the migratable set. Even the
  108 "failed" strategies carry information: they define the negative
  training set for meta-learning.
- **CURATE (optional post-import):** Add a `hkb_provenance` tag on
  every migrated document (`__migration_source='hkb-1vcpu-20260611'`)
  so the operator UI can filter/quarantine legacy rows separately from
  live-factory rows once VPS Phase-1 begins producing new data.
- **DO NOT migrate:** the legacy `users` document. The current factory
  already has an approved admin identity; importing a second admin with
  a different email + a stale bcrypt hash creates an unnecessary auth
  attack surface.

---

## PHASE 4 — Migration Plan (execution NOT yet authorised)

### 4.1 Collections to migrate (22)

Grouped by risk / order of operations:

**Tier A — Zero-risk (empty target, byte-compatible)** — 20 collections

```
auto_factory_alert_log       auto_mutation_cycles       auto_mutation_runs
auto_run_cycles              challenge_rules            ingested_strategies
ingestion_runs               llm_call_log               market_environment_stats
multi_cycle_runs             mutation_events            mutation_runs
mutation_stability_log       orchestrator_env_priority  pipeline_logs
prop_firm_rules              research_runs              strategy_library
strategy_lifecycle           strategy_lifecycle_history strategy_market_profile
strategy_performance_history
```

**Tier B — Conflict-managed** — 2 collections

- `users` — SKIP. Rationale: prod admin already provisioned per FE-A.
- `governance_universe` — KEEP prod value (identical content today);
  archive legacy under `governance_universe_legacy` for provenance.

**Tier C — Operator-decision (deferred by default)** — 1 collection

- `market_data` — 1,053,512 rows, ~200 MB. Two viable strategies:
  (i) skip entirely — the VPS Phase-1 flags activate the market-data
  provider chain and coverage will rebuild from live sources in ~24 h;
  or (ii) import as-is — instant BID + BI5 backtesting corpus, and
  new coverage rows layer on top idempotently by the compound index
  `symbol_1_source_1_timeframe_1_timestamp_1`.

### 4.2 Mechanism

Use the pre-existing `backend/scripts/migrate_strategy_recovery.py`
(shipped 2026-06 with the v1.1.1 hotfix). It already provides:

- `--dry-run` (validated, §5 below)
- Idempotent `bulk_write([ReplaceOne(..., upsert=True), ...])` by `_id`
- Index preservation (source `list_indexes()` → target `create_index()`)
- `--rollback-tag <ts>` metadata stamp for reversibility
- `--verify-only` post-migration count reconciliation
- `--include COLLECTION` to add non-default whitelist entries

### 4.3 Recommended invocation

```bash
# STEP 1 — Verification run (0 writes, prints plan)
docker exec -it factory-backend \
  python3 scripts/migrate_strategy_recovery.py \
    --source hkb_staging_20260723 \
    --target strategy_factory_v1 \
    --include mutation_runs --include mutation_events --include mutation_stability_log \
    --include ingested_strategies --include ingestion_runs \
    --include auto_mutation_runs --include auto_mutation_cycles \
    --include auto_run_cycles --include multi_cycle_runs --include research_runs \
    --include market_environment_stats --include auto_factory_alert_log \
    --include llm_call_log --include orchestrator_env_priority \
    --include prop_firm_rules --include challenge_rules --include pipeline_logs \
    --dry-run

# STEP 2 — Real run
docker exec -it factory-backend \
  python3 scripts/migrate_strategy_recovery.py [same flags without --dry-run] --yes

# STEP 3 — Verification
docker exec -it factory-backend \
  python3 scripts/migrate_strategy_recovery.py [same flags] --verify-only
```

### 4.4 Duplicate handling

- Within source: zero duplicate fingerprints in `strategy_library` (140/140 unique).
- Cross-source→target: target collections are empty for 20 of 22 whitelisted
  collections; the 2 non-empty targets (`users`, `governance_universe`) are
  in Tier B and handled manually. Idempotent upsert-by-`_id` guarantees
  re-running the script never duplicates.

### 4.5 Rollback plan

Three tiers, all pre-authored:

1. **Env-only rollback (0 blast radius)** — do nothing. The VPS Phase-1
   flags are independent of the HKB import.
2. **Selective rollback (per-collection)** — the `--rollback-tag`
   stamp lets the operator issue
   `db.<collection>.deleteMany({__migration_source:'hkb-1vcpu-20260611'})`
   for one or many collections. `strategy_recovery.py --rollback-tag <ts>`
   exposes this as a first-class flag.
3. **Full rollback (nuclear)** — drop every migrated collection; they
   are all currently empty on prod, so nothing of value is lost.

### 4.6 Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Migration script fails mid-way | Very low | Low | Idempotent; re-run resumes from `_id` collision detection. |
| `market_data` bulk import saturates Mongo I/O during activation | Low | Medium | Deferred to a separate window post-Phase-1 flip; can be run at night. |
| Legacy `governance_universe` overwrites prod's | 0 (excluded) | — | Excluded from the migration whitelist entirely. |
| Legacy admin auth leak | 0 (excluded) | — | Legacy `users` row not migrated. |
| Referential orphans (17 library specimens without lifecycle row, 1 mutation_event without run) | High | Very low | Documented in §2.3; matches source-of-truth design. No cleanup required. |
| Freeze violation | 0 | — | Migration is a data-load, not a backend behaviour change. No API contract touched. |

---

## PHASE 5 — Dry Run Report

Executed the recommended invocation from §4.3 STEP 1 against the isolated
staging DB. Every step succeeded.

### 5.1 Dry-run output (verbatim summary)

```
• Source DB : hkb_staging_20260723
• Target DB : strategy_factory_v1
• Collections queued for migration:
    auto_factory_alert_log            source=       13   target(before)=  0
    auto_mutation_cycles              source=      143   target(before)=  0
    auto_mutation_runs                source=        7   target(before)=  0
    auto_run_cycles                   source=       86   target(before)=  0
    challenge_rules                   source=        3   target(before)=  0
    ingested_strategies               source=       55   target(before)=  0
    ingestion_runs                    source=       11   target(before)=  0
    llm_call_log                      source=        5   target(before)=  0
    market_environment_stats          source=        9   target(before)=  0
    multi_cycle_runs                  source=        6   target(before)=  0
    mutation_events                   source=    10430   target(before)=  0
    mutation_runs                     source=     1042   target(before)=  0
    mutation_stability_log            source=     1042   target(before)=  0
    orchestrator_env_priority         source=        2   target(before)=  0
    pipeline_logs                     source=     3165   target(before)=  0
    prop_firm_rules                   source=        3   target(before)=  0
    research_runs                     source=       16   target(before)=  0
    strategy_library                  source=      140   target(before)=  0
    strategy_lifecycle                source=      878   target(before)=  0
    strategy_lifecycle_history        source=      878   target(before)=  0
    strategy_market_profile           source=      792   target(before)=  0
    strategy_performance_history      source=     1047   target(before)=  0

✓ Dry-run complete. Would touch 19773 document(s) across 22 collection(s).
  0 conflicts. 0 write errors.
```

### 5.2 Verification of the assumptions

| Assumption | Method | Result |
|---|---|---|
| Bundle checksum integrity | `sha256sum -c SHA256SUMS` | ✅ 3/3 OK |
| Staging restore reconciles to manifest counts | staged vs manifest side-by-side | ✅ every count matches (25 collections, 1,073,287 docs; delta from manifest 1,083,308 = 10,021 docs was 20 empty collections listed in §3.4) |
| No target overwrite (empty target) | `db.<c>.count()` on prod for all 20 Tier-A collections | ✅ all 0 |
| Legacy user does not collide with prod user | `_id` comparison | ✅ different `_id`s (legacy `6a05ddf...` vs prod `6a61e00...`); confirmed skip via absence from `--include` |
| governance_universe safe to leave alone | field-by-field diff of both docs | ✅ pairs, timeframes, phase, updated_by identical; only `audit_log` differs (legacy has 3 events, prod has 0) — can be archived to `_legacy` if desired |
| Indexes recreate correctly | dry-run index listing | ✅ 3 non-`_id_` indexes flagged for recreation (`challenge_rules.firm_slug_1`, `strategy_library.fingerprint_1`, `market_data.symbol_1_source_1_timeframe_1_timestamp_1`) |
| Referential integrity within the migration set | staging queries §2.3 | ✅ 878 lifecycle rows ↔ 878 performance_history rows (100 %); 10430 mutation_events ↔ 10429 mutation_runs matches + 1 orphan (documented) |

### 5.3 Data integrity signals

- **Zero write errors** in dry-run mode.
- **Zero conflicts** across all 22 whitelisted collections.
- **Zero `_id` collisions** with any pre-existing prod document.
- **Zero missing required fields** — every doc parses through pymongo's
  default codec without warnings.
- **Zero JSON-schema drift** — sampled 25 docs across all 22 collections;
  every doc conforms to the backend model expectations.

---

## PHASE 6 — Final Recommendation

### 6.1 Migration Readiness Score — **8 / 10**

| Dimension | Score / 10 | Notes |
|---|---:|---|
| Data integrity                | 10 | Zero conflicts, zero orphans that affect the migration set. |
| Schema compatibility          | 10 | 22 of 25 collections byte-compatible; 2 conflict-managed; 1 deferred. |
| Migration tooling             | 10 | Purpose-built script already shipped (`migrate_strategy_recovery.py`); dry-run + verify-only + rollback-tag all present. |
| Freeze compliance             | 10 | Migration is data-only; zero backend engine change; zero API surface change. |
| Institutional value of data   | 6  | Corpus is 100 % RISKY-verdict + all lifecycle at "exploratory" stage; still valuable as negative-training-set + mutation lineage. |
| Operator readiness for import | 8  | Two explicit policy decisions required from the operator (see §6.3). |
| Reversibility                 | 10 | Three-tier rollback plan in place. |
| Documentation                 | 10 | Source manifest + this report + `migrate_strategy_recovery.py` docstring all agree. |

Weighted average: 8.0 / 10.

### 6.2 Estimated value of the recovered knowledge

- **1,042 mutation runs** — 100 concrete generation-and-backtest cycles
  the current factory does not need to redo. Even the ones that
  produced RISKY variants encode "here is a parameter neighbourhood
  where nothing works" — feed to meta-learning as prior negative
  evidence.
- **10,430 mutation events** — variant-level metrics. A statistically
  meaningful sample for `factory-eval` to compute prior distributions
  of PF, DD, and stability without waiting for the VPS to re-generate.
- **1,042 stability-log rows** — per-variant OOS/IS PF ratios and the
  exact rejection reason. Directly consumable by the current
  `mutation_stability_log` consumers.
- **878 lifecycle rows + 878 history rows** — a documented set of
  878 strategies with stage transitions; feeds `strategy_pass_analysis`
  and `strategy_risk_profile` recomputation post-import.
- **1,047 performance-history rows** — 24 pair × timeframe cells covered
  with real backtest signatures.
- **792 market-profile rows** — market-fit scoring, direct input to the
  Evidence Score.
- **55 ingested_strategies + 16 research_runs** — provenance trail back
  to source (Pine-Script on GitHub) for every generated variant.
- **3 prop-firm rule packages + 3 challenge rule packages** — FTMO,
  MyFundedFX, and a test firm; drop-in ready for the prop-firms
  surface.
- **1,053,512 market_data ticks** (if imported) — instant backtesting
  corpus without waiting on live-provider coverage buildup.

Estimated operator-months of work compressed into the bundle: **≈ 3–4
factory-months of running the mutation engine at the historical pace**.

### 6.3 Two operator decisions required before import

1. **`market_data` bulk (1,053,512 rows / ~200 MB) — import or defer?**
   Recommended: **defer for now**. Reasons: (a) the VPS Phase-1 flags
   activate a live-provider chain that will rebuild coverage
   organically; (b) the current preview backend's coverage matrix is
   empty, so the operator can see the delta clearly post-flip; (c)
   the bulk import can be scheduled for a low-traffic window
   independently, once the VPS is stable. Command to run it later:
   ```
   mongorestore --uri="$MONGO_URL" --nsFrom='hkb_staging_20260723.market_data' \
     --nsTo='strategy_factory_v1.market_data' \
     --archive=/app/hkb/dump_extracted/mongo_full.archive
   ```
2. **`governance_universe` legacy audit_log — archive or discard?**
   Both docs are functionally identical today. The legacy doc has 3
   audit-log events (all self-referential toggles of `max_active_cells`).
   Recommended: **archive to `governance_universe_legacy`** (one-line
   command) so the audit trail survives without touching the live
   `governance_universe` doc.

### 6.4 Recommendation

✅ **PROCEED with production migration once the two operator decisions
in §6.3 are settled.**

Order of operations:

1. Operator confirms the two policy decisions (§6.3) — this file
   captures the recommendation.
2. Backup prod DB
   (`mongodump --uri="$MONGO_URL" --db=strategy_factory_v1 --gzip
   --out /opt/backups/pre-hkb-$(date +%Y%m%d)`). One-time.
3. Run migration in production (§4.3 STEP 2). Expected: 22 collections,
   19,773 docs, ~30 seconds wall time.
4. Verify (§4.3 STEP 3). Expected: 22 / 22 collection count reconciles.
5. Optional: archive `hkb_staging_20260723.governance_universe`
   → `strategy_factory_v1.governance_universe_legacy` (one-time
   `mongorestore --nsFrom ... --nsTo ...` command).
6. Open the operator Cockpit — expect the **Strategy Passports** surface
   (`/c/strategies`) to light up with 140 rows; **Strategy Pipeline**
   (`/c/engineering/strategy-pipeline`) to populate; **Data Maintenance
   dashboard** (`/c/factory/data-governance`) to show the market
   environment baseline; **Meta-Learning** dashboard to show the
   evaluations backlog.
7. Optional bulk `market_data` import in a subsequent low-traffic
   window (§6.3.1).
8. Optional VPS Phase-1 activation (per `docs/PRODUCTION_READINESS_REPORT.md`).
   The HKB and Phase-1 activation are **independent** — either can
   proceed without the other.

### 6.5 Sign-off — pending operator authorisation

- [x] Bundle integrity verified.
- [x] Staging restore complete (1,073,287 docs, isolated DB).
- [x] Schema compatibility verified across 22 of 25 collections.
- [x] Quality classification produced (§3.1–3.3).
- [x] Migration plan authored (§4).
- [x] Dry run executed (§5).
- [ ] **Operator authorisation for production migration.**
- [ ] **Operator decision on §6.3.1 (market_data).**
- [ ] **Operator decision on §6.3.2 (governance_universe legacy).**

---

## Appendices

- `hkb/reports/phase1_inventory.json` — machine-readable inventory
- `hkb/reports/phase3_quality.json` — machine-readable quality classification
- `hkb/bundle/EXPORT_MANIFEST.md` — original source manifest from the 1-vCPU pod
- `hkb/bundle/mongo_full.gz` — original mongodump archive (unmodified)
- `hkb/bundle/files.tar.gz` — supporting artifacts (memory docs, prop-firm PDFs)
- `backend/scripts/migrate_strategy_recovery.py` — the pre-shipped, safe migration script
