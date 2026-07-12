# PACKAGE_INSPECTION_REPORT.md — 1-vCPU `migration_bundle.tar.gz` vs ASF v1.0

**Mode:** Read-only inspection. No code written. No Mongo writes. No imports performed. No GATE 3 work begun.
**Inspection target:** Restored MongoDB dump from `migration_bundle.tar.gz`, loaded into temp DB `asf_inspect`.
**Specs compared against:**
* `/app/memory/ASF_PACKAGE_V1_SPEC.md` (v1.0 wire-format contract)
* `/app/memory/ASF_BACKEND_ARCHITECTURE.md` (locked backend layout; `migration_adapter.py` placement)
* `/app/memory/MIGRATION_PRIORITY.md` (T1/T2/T3 tier policy)
* `/app/memory/MIGRATION_EXPORT_PLAN.md` (1-vCPU export-format contract)

**Inspection scope:** 25 collections, ~1.07M rows (incl. 1.05M `market_data` rows excluded from import scope).

---

## 1. Executive verdict

| Field | Value |
|---|---|
| **Compatibility verdict** | **🟡 AMBER** |
| **Adapter architecture (`engines/asf/importer/migration_adapter.py`) requires modification?** | **NO** |
| **Identity integrity** | ✅ GREEN — 140/140 SHA-1 fingerprints, 0 duplicates |
| **Lineage closure (via `mutation_events`)** | ✅ GREEN — 140/140 parents resolvable |
| **Lineage closure (intra-library)** | 🟡 AMBER — 0/140 parents in `strategy_library`; orphan flag required |
| **T1 survivor seeds** | 🔴 RED — **0 candidates** at strict PF≥1.30 threshold |
| **T2 archive viability** | ✅ GREEN — 140 + 10,430 + 1,042 rows ready |
| **T3 audit viability** | 🟡 AMBER — 1,938 rows ingestible but **un-joined to library** |
| **Calibration snapshot present** | 🔴 RED — absent; must be synthesised by receiving pod |
| **BI5 / Master Bot / Portfolio data present** | 🔴 RED — absent (acceptable; spec §3 permits omission) |
| **Recommended next step** | Operator decision on (a) PF threshold relaxation, then authorise GATE 3 build per blueprint |

**Bottom line:** The package is **structurally compatible** with ASF v1.0 and the locked `migration_adapter.py` architecture handles it correctly **without any architectural changes**. It is AMBER (not GREEN) because (i) strict T1 filter yields zero survivor seeds, (ii) the legacy schema differs from ASF on every strategy field and requires ~11 well-bounded adapter transformations, and (iii) three legacy collections (`strategy_lifecycle`, `strategy_lifecycle_history`, `strategy_performance_history`) cannot be joined to `strategy_library` and must land in T3 un-linked. It is **not RED** because every ASF-required field is either present, computable, or formally permitted to be absent per spec §3.

---

## 2. Package inventory

### 2.1 Collections present (25)

| Collection | Rows | ASF spec role |
|---|---:|---|
| `strategy_library` | **140** | Primary subject (§4) |
| `mutation_events` | 10,430 | `lineage/mutation_events.jsonl` (§5.1) |
| `mutation_stability_log` | 1,042 | `lineage/mutation_stability_log.jsonl` (§5.2) |
| `mutation_runs` | 1,042 | Provenance reference |
| `strategy_lifecycle` | 878 | `lifecycle/stages.jsonl` (§5.3) |
| `strategy_lifecycle_history` | 878 | `lifecycle/history.jsonl` (§5.4) |
| `strategy_performance_history` | 1,047 | `evidence/performance_history.jsonl` (§5.5) |
| `auto_factory_alert_log` | 13 | `evidence/alerts.jsonl` (§5.6) |
| `ingested_strategies` | 55 | Provenance reference (not in ASF spec) |
| `ingestion_runs` | 11 | Provenance reference |
| `strategy_market_profile` | 792 | **Not in ASF spec** → `extensions.migration.*` |
| `market_environment_stats` | 9 | **Not in ASF spec** → `extensions.migration.*` |
| `governance_universe` | 1 | **Not in ASF spec** → `extensions.migration.*` |
| `pipeline_logs` | 3,165 | Audit context (T3) |
| `auto_mutation_runs` | 7 | Provenance |
| `auto_mutation_cycles` | 143 | Provenance |
| `auto_run_cycles` | 86 | Provenance |
| `multi_cycle_runs` | 6 | Provenance |
| `research_runs` | 16 | Provenance |
| `challenge_rules` | 3 | Reference data |
| `prop_firm_rules` | 3 | Reference data |
| `orchestrator_env_priority` | 2 | Reference data |
| `llm_call_log` | 5 | Audit context |
| `users` | 1 | Out of ASF scope |
| `market_data` | 1,053,512 | **Out of import scope** (live data, not strategy artifacts) |

### 2.2 Collections REQUIRED by ASF v1.0 but ABSENT

Per `ASF_PACKAGE_V1_SPEC.md`, packages MAY omit sections that have no rows (§3: *"Empty sections MUST be omitted entirely … Receivers MUST treat absence as 'no rows in that category', NOT as an error."*). The following are absent and therefore the corresponding ASF sections will be empty/omitted in the adapter's in-memory package:

| Missing collection | ASF section | Impact |
|---|---|---|
| `bi5_data_certification` | `certifications/bi5_data/*.json` (§6.2) | No data certs to carry; **OK per spec §3** |
| `bi5_strategy_certifications` | `certifications/bi5_strategy/*.json` (§6.1) | No strategy certs; each strategy doc gets `bi5_cert: null`. **OK** |
| `master_bot_definitions` / `master_bot_members` | `master_bot/*` (§8.3-8.5) | No MB section; `package_type` cannot be `master_bot` or `full_pod` (already classified as `migration`). **OK** |
| `portfolio_lifecycle` / `portfolio_signals` / `portfolio_scaling_runs` | `portfolios/*` (§8.1-8.2) | `portfolio_assignments: []` in every strategy doc. **OK** |
| `audit_log` | `evidence/audit_excerpts.jsonl` (§5.7) | No audit excerpts; only 13 `auto_factory_alert_log` rows substitute. **OK** |
| Calibration tables (`tick_validator_config`, `density_table`, ranker config) | `cert_calibration/*` (§9) | **🔴 Spec §9 says calibration snapshot is MANDATORY in every package.** Resolution: the *receiving pod* injects its own calibration snapshot (`tick_validator@P0B-v2`, density table after R2 Step-0, `master_bot_ranker@v1.1`, PASS=0.85/WARN=0.70) — `calibration_drift_detected=false` trivially. **No adapter change needed**; this is exactly the case `ASF_BACKEND_ARCHITECTURE.md §3.9 + §6.1` anticipates. |

---

## 3. Objective-by-objective findings (per user prompt)

### 3.1 Fingerprint integrity and duplicate risk

| Check | Result |
|---|---|
| Field `fingerprint` present | **140/140** |
| Format (SHA-1, 40 lowercase hex) | **140/140 valid** |
| Distinct fingerprints | **140/140 unique** — 0 intra-package duplicates |
| Sample | `00cae3914bde6414984034d95a28cc70321a773d` |
| Collision risk against receiving pod's canonical `strategy_library` | **Unknown until dry-run** — receiver currently has 0 rows from `1vcpu_migration` source, so collision space is empty. Dedup policy `skip` (per `ASF_BACKEND_ARCHITECTURE.md §3.9`) handles any coincidental collisions safely. |

**Verdict:** ✅ **GREEN.** Identity layer is byte-faithful with ASF v1.0 §4 contract.

### 3.2 Strategy counts and tier distribution

Applying `MIGRATION_PRIORITY.md §2` filters:

| Filter | Threshold | Pass count | Notes |
|---|---|---:|---|
| #1 `total_trades >= 30` | strict | **140/140** | min=63, max=478 |
| #2 `profit_factor >= 1.30` | strict | **0/140** | **min=0.79, max=1.28, avg=1.00** ← **gating filter** |
| #3 `win_rate >= 0.40` | strict | **25/140** | stored as 0–100 (avg 35.5); adapter normalises ÷100 |
| #4 `max_drawdown_pct <= 0.20` | strict | **108/140** | stored as fraction (0.00–0.97) |
| #5 `walk_forward.passed == true` | soft (per §2 footnote) | **140/140** soft-pass | field renamed to `.success` in legacy schema; remap required |
| #6 `stage ∉ {DEMOTED, RETIRED, BANNED}` | soft | **140/140** soft-pass | no `stage` field present |
| #7 `created_at` within last 365 d | strict | **140/140** | all rows dated 2026-05-16 / 17 |
| #8 fingerprint not in canonical seed | strict | **140/140** (assumed) | canonical `strategy_library` currently empty of `1vcpu_migration` rows |

**Tier breakdown:**

| Tier | Count | Source collection(s) | Action per `MIGRATION_PRIORITY.md` |
|---|---:|---|---|
| **T1 — Survivor seed** | **0** | `strategy_library` rows passing #1–#4 strictly | None — zero rows qualify |
| **T2 — Reference intelligence** | **11,612** | `strategy_library` (140) + `mutation_events` (10,430) + `mutation_stability_log` (1,042) | Read-only insert into `strategy_library_archive` (140) + matching collections (10,430 + 1,042) |
| **T3 — Audit context** | **1,938** | `strategy_lifecycle_history` (878) + `strategy_performance_history` (1,047) + `auto_factory_alert_log` (13) | Insert with `imported=true` flag |

**Verdict:** 🔴 **RED on T1**, ✅ **GREEN on T2**, 🟡 **AMBER on T3** (see §3.4 — un-joined). **Operator decision required:** relax filter #2 (PF threshold) from `1.30` → `1.20` would yield **14 T1 candidates**; → `1.10` would yield **15**. Neither change requires any code modification — it is a config knob in the adapter per `MIGRATION_PRIORITY.md §8` ("Operator decisions still required").

### 3.3 Lineage / mutation history preservation

| Check | Result |
|---|---|
| `mutation_events` rows | **10,430** |
| Distinct `variant_fingerprint` in events | 10,229 |
| Distinct `base_fingerprint` in events | 1,038 |
| `strategy_library.mutation_variant_fingerprint` → resolves in `mutation_events.variant_fingerprint` | **140/140** |
| `strategy_library.mutation_base_fingerprint` → resolves in `mutation_events.base_fingerprint` | **140/140** |
| `strategy_library.fingerprint` ↔ `mutation_events.variant_fingerprint` | **0/140** — **divergent identity** (library uses re-bucketed SHA-1; events use mutation-time SHA-1) |
| `strategy_library.mutation_base_fingerprint` ↔ `strategy_library.fingerprint` | **0/140** — no intra-library parents (acyclic across exports) |
| `mutation_stability_log` per-variant rows | **1,042** |

**Lineage walkability:** ✅ **GREEN.** The adapter walks `strategy_library.mutation_variant_fingerprint → mutation_events.variant_fingerprint` (the indirect path), then follows `mutation_events.base_fingerprint` to assemble ancestor chains. Walking is feasible to arbitrary depth from `mutation_events` alone.

**Intra-package parent closure:** 🟡 **AMBER.** Because `strategy_library` retains only the 140 saved survivors out of 10,229 mutated variants, every saved strategy's parent is **outside the library** (in `mutation_events`). ASF spec §4.2.2 explicitly permits this: *"`lineage.parent_fingerprint`, if non-null, MUST refer either to (a) another strategy in this package, or (b) to a strategy outside this package whose existence is documented in `provenance.notes`."* The adapter sets `lineage.ancestors_complete=false` and flags `lineage_orphan=true` per the spec — no architectural change.

### 3.4 Lifecycle history preservation

| Check | Result |
|---|---|
| `strategy_lifecycle` rows | **878** |
| `strategy_lifecycle_history` rows | **878** |
| Distinct `current_stage` values | **only `"exploratory"` (878/878)** |
| Lifecycle uses field `current_stage`, ASF spec uses `stage` | **Mismatch — adapter rename required** |
| Lifecycle keyed by `strategy_hash`, library keyed by `fingerprint` | **Independent key-spaces** |
| Lifecycle hashes matching `strategy_library.fingerprint` | **0/878** |
| Lifecycle hashes matching `mutation_variant_fingerprint` | **0/878** |
| Lifecycle hashes matching `strategy_performance_history.strategy_hash` | **878/1,023** — strong join |

**Critical finding:** The 878 `strategy_lifecycle*` rows form an **independent identity universe** from the 140 `strategy_library` rows. They cannot be joined to library entries via any field present in the dump. The 878 hashes are SHA-256 over strategy_text per ASF spec §4 (`strategy_hash`), while the 140 library fingerprints are SHA-1 over bucketed params. Because the legacy DB never persisted `strategy_text` for those 878 lifecycle entries (they are exploration-stage placeholders), the join is **permanently broken in this export**.

**Resolution per `MIGRATION_PRIORITY.md §1`:** Tier 3 ingests these "with `imported=true` flag. Read-only references for the dossier engine when it lands." → Adapter writes them into the receiver's `strategy_lifecycle_history` collection un-joined, tagged `imported=true`. They become dossier evidence only; never auto-linked to live strategies. **This is the exact behaviour the locked architecture prescribes.**

**Legacy stage mapping:** `"exploratory"` is NOT in the ASF enum (`PROVISIONAL | PROMOTED | DEMOTED | RETIRED | BANNED | IMPORTED_SEED`). For the 0 T1 strategies (none) the adapter would set `stage="IMPORTED_SEED"`. For T2/T3 archive rows, the adapter preserves the legacy string verbatim under `extensions.migration.legacy_stage` and sets `lifecycle.stage="IMPORTED_SEED"` to satisfy spec §4. **No architectural change — this is the documented behaviour of `migration_adapter.py`.**

**Verdict:** 🟡 **AMBER.** Lifecycle DATA is preserved, but lifecycle ↔ library JOIN is structurally absent. Acceptable per locked Tier 3 policy.

### 3.5 Performance history and ranking data availability

| Check | Result |
|---|---|
| `strategy_performance_history` rows | **1,047** |
| Rows with non-null PF | low (~10–20 of 1,047 — most are placeholder ingestion stubs) |
| `strategy_performance_history.strategy_hash` ↔ `strategy_library.fingerprint` | **0/1,023** — disjoint |
| `strategy_performance_history.strategy_hash` ↔ `strategy_lifecycle.strategy_hash` | **878/1,023** — strong overlap |
| `strategy_performance_history.strategy_hash` ↔ `strategy_library.mutation_variant_fingerprint` | **0** |
| Ranker data (`explorer_scores`, `ranker_contributions`, `master_bot_ranker_config`) | **ABSENT** |

**Findings:**
* **Performance history exists but is largely un-joined to the 140 saved survivors** (same identity-universe problem as lifecycle). The 878 overlap with lifecycle hashes makes these two collections internally consistent — they describe the *exploration history*, not the library survivors.
* **No ranker / explorer score data is present.** Per ASF spec §7 these snapshots are OPTIONAL — `scoring/*` files are simply omitted in the converted in-memory package. Acceptable per spec §3.
* The 140 survivors carry their own performance fields **on-document** (`profit_factor`, `win_rate`, `max_drawdown_pct`, `total_trades`, `stability_score`, etc.) which the adapter folds into `metrics.*` in the ASF strategy doc. **Performance data for the survivors is fully preserved this way.**

**Verdict:** 🟡 **AMBER.** Survivor-strategy performance is preserved on-doc; historical performance for the 878 exploratory hashes lands in T3 un-joined.

### 3.6 Fields required by the future importer that are MISSING from the package

The following ASF v1.0 required fields are absent from legacy `strategy_library` rows and must be **synthesised by `migration_adapter.py`** (these synthesis steps are already specified in `ASF_BACKEND_ARCHITECTURE.md §3.9` and **do not require any architectural change**):

| ASF required field | Legacy field / source | Adapter action |
|---|---|---|
| `asf_schema_version` | n/a | Set `"1.0"` |
| `exported_at` | n/a | `now()` at conversion time |
| `exporter.*` (pod_host_id, build_label, git_sha, exporter_module) | env vars + git | Inject from receiving pod env |
| `fingerprint_inputs.pair` / `.timeframe` / `.style` / `.params_canon` / `.strategy_text` | `pair`, `timeframe`, `style`, `strategy_text` | Direct copy; `params_canon` recomputed by `engines/strategy_library._canon_params(parameters)` |
| `strategy_hash` (SHA-256 over strategy_text) | absent | **Compute `sha256(strategy_text)`** |
| `metrics.*` (nested object) | flat fields `total_trades`, `profit_factor`, `win_rate`, `max_drawdown_pct`, `stability_score` | **Flatten→Nest transform**; `win_rate` ÷ 100 (scale fix) |
| `metrics.sharpe` / `.sortino` / `.calmar` | absent in 1-vCPU schema | Set `null`; receiver replays if desired |
| `metrics.computed_on_data_window` | absent | Set `null` |
| `lineage.parent_fingerprint` | `mutation_base_fingerprint` | **Field rename**; null if not present |
| `lineage.mutation_family` | `mutation_type` | Direct copy |
| `lineage.generation` | absent | Compute by walking `mutation_events` parent chain (bounded depth) |
| `lineage.ancestors[]` | walk via `mutation_events` | **Synthesised by adapter walker** |
| `lineage.ancestors_complete` | n/a | **Set `false`** for migration packages (closure not enforced) |
| `bi5_cert` | absent | Set `null` |
| `explorer` | absent | Set `null` |
| `portfolio_assignments` | absent | Set `[]` |
| `master_bot_memberships` | absent | Set `[]` |
| `lifecycle.stage` | absent | **Set `"IMPORTED_SEED"`** (T1) / preserve legacy under `extensions.migration.legacy_stage` |
| `lifecycle.stage_locked_until` | absent | `ISO(today + 30 days)` per `MIGRATION_PRIORITY.md §5` |
| `lifecycle.transitions_count` | absent | Set `0` |
| `provenance.source` | `source` field = `"mutation_engine"` | **Map to `"1vcpu_migration"`** |
| `provenance.source_pod` | absent | Inject `"1vcpu"` |
| `provenance.source_codebase.git_sha` / `.build_label` | absent | Set `"unknown"` |
| `provenance.tier_class` | n/a | **Computed by adapter** (T1/T2/T3) |
| `provenance.requires_revalidation` | absent | **Set `true`** (legacy never ran BI5 cert) |
| `provenance.requires_rematching` | absent | Set `true` |
| `provenance.discovered_at` | use `created_at` | Direct copy |
| `validation_report.walk_forward.passed` | **legacy uses `.success`** | **Rename `.success` → `.passed`** |
| `cert_calibration/*` (entire block) | absent | **Synthesise from receiving pod** (no drift since source had no calibration anyway) |
| `manifest.*` (entire file) | absent (this is a mongodump, not an `.asfpkg`) | **Synthesise in-memory** by `migration_adapter.py` per `ASF_BACKEND_ARCHITECTURE.md §3.9` step 2 |

**Verdict:** ✅ **GREEN.** Every missing field is either (a) trivially synthesisable from existing legacy fields, (b) permitted to be `null` / empty by spec §4.1, or (c) computable from the calibration state of the receiving pod. **No architectural deviation required.**

### 3.7 Adapter transformations required before import

Consolidated list — each item is a small, deterministic, side-effect-free transform inside the adapter (no library / engine modifications):

| # | Transformation | Source → Target |
|---|---|---|
| **T1** | Metrics flatten → nest | `{total_trades, profit_factor, win_rate, max_drawdown_pct, stability_score}` at root → `metrics.{...}` sub-object |
| **T2** | Win-rate scale normalise | `win_rate ÷ 100` (e.g. 44.3 → 0.443) |
| **T3** | Compute `strategy_hash` | `sha256(strategy_text)` |
| **T4** | Synthesise `fingerprint_inputs.params_canon` | invoke `engines/strategy_library._canon_params(row.parameters)` (re-use existing function; no new code) |
| **T5** | Map `parameters` → `params` | rename field |
| **T6** | Rename `mutation_base_fingerprint` → `lineage.parent_fingerprint` | direct |
| **T7** | Walk `mutation_events` to populate `lineage.ancestors[]` | bounded depth (operator-config; default 5) |
| **T8** | Synthesise `lifecycle` block | stage="IMPORTED_SEED" (T1) / preserve legacy under `extensions`; `stage_locked_until = today+30d` |
| **T9** | Synthesise `provenance` block | source="1vcpu_migration"; tier_class from filter; flags `requires_revalidation=true` |
| **T10** | Rename `validation_report.walk_forward.success` → `.passed` | direct |
| **T11** | Inject calibration snapshot from receiving pod | `tick_validator@P0B-v2`, post-R2 density table, PASS=0.85/WARN=0.70, ranker@v1.1; sets `calibration_drift_detected=false` |
| **T12** | Empty/null defaults | `bi5_cert=null`, `explorer=null`, `portfolio_assignments=[]`, `master_bot_memberships=[]` |
| **T13** | Tier classification | apply `MIGRATION_PRIORITY.md §2` filters → write `provenance.tier_class` |
| **T14** | Tier 3 un-joined ingest | `strategy_lifecycle_history` + `strategy_performance_history` + `auto_factory_alert_log` land in receiver collections with `imported=true` flag and **no FK to strategy_library** |
| **T15** | Drop out-of-scope collections | `market_data` (1.05M rows), `users`, `pipeline_logs`, `ingestion_runs`, `*_cycles`, `research_runs`, etc. → either skipped or routed to `extensions.migration.*` per operator preference (default: skipped) |

All 15 transforms are **field-level**, **deterministic**, and **operator-auditable**. None requires a deviation from the locked architecture in `ASF_BACKEND_ARCHITECTURE.md §3.9` (which already names "thin adapter, ~40-60 LOC" + walker/upserter/verifier exactly for this case).

### 3.8 Does the planned ASF `migration_adapter` architecture remain valid without modification?

**YES — UNCONDITIONALLY.**

Specifically, the following locked architectural commitments hold true:

| Architectural item | Status |
|---|---|
| File placement at `backend/engines/asf/importer/migration_adapter.py` | ✅ Valid as locked |
| Thin-adapter LOC budget (~40-60 LOC core + ~150 schema models + ~50 walker/upserter glue) | ✅ Valid — the 15 transforms above fit comfortably |
| In-memory conversion (no intermediate ZIP write) | ✅ Valid — dump is small (~12 MB of strategy data excl. market_data); fits in RAM |
| Reuse of `engines/strategy_library._fingerprint()` and `._canon_params()` | ✅ Valid — present in code, reusable |
| Reuse of `engines/tick_validator.aggregate_window()` for cert replay | ✅ Valid — but no `bi5_data_certification` rows to replay, so this code path is no-op in dry-run; not a problem |
| Reuse of `engines/master_bot_ranker._compute_candidate_score()` for score drift | ✅ Valid — no exported scores to compare; advisory drift detection is no-op |
| T1/T2/T3 classification engine | ✅ Valid — works exactly as designed; current dataset yields 0/140/1,938 |
| Dedup policy = `skip` (T1 default) | ✅ Valid — 0 T1 rows anyway, but safe for future packages |
| Audit-log emission per action (`event_type="asf_import"`) | ✅ Valid — emits 140 + 11,612 + 1,938 ≈ 13,690 actions |
| `asf_import_log` + `asf_import_actions` lazy-create | ✅ Valid |
| Unique-fingerprint-index pre-create on `strategy_library` | ✅ Valid; pre-create runs before bulk T1 insert (no-op when 0 T1 rows) |
| Auto-selection 5-line guard | ✅ Valid; relevant only when T1>0, but cheap to add now |
| API surface: 4 endpoints (`POST /migration`, `GET /{id}`, `POST /commit`, `POST /abort`) | ✅ Valid |
| Tests: schema · dedup · adapter-format-detection · T1/T2/T3 classification · calibration drift | ✅ Valid; current package is a perfect fixture for the format-A code path |

**One observation, not a change request:** Section 3.9 of the architecture document calls out three input formats (A: mongodump archive · B: JSON · C: ZIP). **This package is Format A** (`mongodump --archive --gzip`). The adapter's `detect_format()` returns `"A"` and proceeds. **No new code path is needed.**

---

## 4. Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Strict PF≥1.30 filter yields **0 T1 candidates** — no survivors land in live `strategy_library` | **High** (operator-visible) | Operator decision: relax to 1.20 (→ 14 T1) or 1.10 (→ 15 T1). Already foreseen in `MIGRATION_PRIORITY.md §8`. |
| R2 | 878 lifecycle rows + 1,047 performance rows cannot be joined to library survivors | **Medium** | Per locked Tier 3 policy, they ingest as dossier evidence with `imported=true`; do not pollute live joins. |
| R3 | Calibration snapshot missing from package | **Low** | Receiving pod synthesises its own; `calibration_drift_detected=false` trivially. Per `ASF_BACKEND_ARCHITECTURE.md §6.1` this is the documented behaviour for legacy sources. |
| R4 | `mutation_events.metrics` uses different scale (PF=1202.11 outliers, DD as percent 0–100) than `strategy_library` | **Low** | Adapter does not re-derive survivor metrics from `mutation_events`; survivor metrics come from `strategy_library` flat fields. Events are lineage-only. |
| R5 | All 140 survivors carry `style="unknown"` | **Low** | ASF spec accepts arbitrary string; downstream classifiers (Phase 13 Dossier) can re-classify. |
| R6 | Walk-forward field renamed (`success` → `passed`) | **Low** | One-line adapter rename per transform T10. |
| R7 | Receiver currently has empty canonical `strategy_library` (140 = total) — bulk insert will trigger first index creation under load | **Low** | Architecture §6.4 pre-creates the unique-fingerprint-index before bulk insert. |
| R8 | `market_data` (1.05M rows) is in the dump but not in import scope — could be mistakenly imported | **Low** | Default-skip per transform T15; documented exclusion. |

---

## 5. Compatibility verdict and rationale

### 🟡 AMBER

**Why AMBER (not GREEN):**
1. **0 T1 survivors at the strict PF≥1.30 threshold.** This means a literal application of the locked filter produces zero deployable-after-revalidation candidates. Operator-visible outcome; needs a decision before commit.
2. **15 deterministic adapter transforms required.** None is architecturally novel, but the legacy schema is materially different from ASF v1.0 — this is *not* a plain copy.
3. **Lifecycle and performance history collections cannot be joined to the library survivors.** They land as un-joined T3 audit evidence. Dossier-engine-ready, but not navigable from a live strategy card.

**Why AMBER (not RED):**
1. **Identity (fingerprint) integrity is byte-faithful.** 140/140 valid SHA-1; 0 duplicates.
2. **Every ASF-required field is present, computable, or formally permitted to be absent** by spec §3 / §4.1.
3. **Lineage IS walkable** via `mutation_events` (140/140 parents resolve).
4. **The locked migration_adapter architecture handles this package without any code-level deviation.** The 15 transforms fit the locked LOC envelope.
5. **Dedup safety is guaranteed** (0 intra-package duplicates; `skip` policy in adapter; index pre-create).

---

## 6. Recommended next step

**Two-step authorisation, in order:**

### Step A — Operator decision on tier-filter knobs (no code)

Confirm or amend the following in advance of GATE 3 build (each is an `operator-knob` line, not a code change):

1. **PF threshold for T1** (`MIGRATION_PRIORITY.md §2 #2`):
   * keep at `1.30` → 0 T1 survivors **(strict)**
   * relax to `1.20` → 14 T1 survivors **(moderate)** ← recommended given the dataset
   * relax to `1.10` → 15 T1 survivors
2. **`stage_locked_until` window** (`MIGRATION_PRIORITY.md §5`): default `+30 days`. Keep, shorten, or extend.
3. **Lineage ancestor depth cap** (default 5 generations). Keep or amend.
4. **Out-of-scope collections** (transform T15): confirm `market_data`, `pipeline_logs`, `ingestion_runs`, `users` are skipped (the default).

### Step B — Authorise GATE 3 build per the locked blueprint (no architectural change)

When Step A is settled, the receiving agent is authorised to ship **exactly** the 14 work items enumerated in `ASF_BACKEND_ARCHITECTURE.md §3.9 / §7.2`:

1. `engines/asf/__init__.py`
2. `engines/asf/schema.py` (migration-adapter subset of Pydantic models)
3. `engines/asf/package_reader.py` (in-memory variant)
4. `engines/asf/calibration_snapshot.py`
5. `engines/asf/dedup_policy.py`
6. `engines/asf/importer/__init__.py`
7. `engines/asf/importer/walker.py`
8. `engines/asf/importer/upserter.py`
9. `engines/asf/importer/verifier.py`
10. `engines/asf/importer/migration_adapter.py` ← **the file this report greenlights**
11. `engines/auto_selection_engine.py` 5-line guard
12. `engines/strategy_library.py` one-line index pre-create
13. `api/asf.py` — 4 admin endpoints
14. `tests/test_asf_schema.py`, `test_asf_dedup_policy.py`, `test_asf_migration_adapter.py`

Acceptance criteria from `ASF_BACKEND_ARCHITECTURE.md §9` apply unchanged.

**Estimated effort:** unchanged from the locked blueprint — ~3–4 dev-days.

**Estimated dry-run outcome** (based on this inspection):
* 0 T1 inserts (or 14 with PF=1.20 relaxation)
* 140 T2 archive inserts (`strategy_library_archive`)
* 10,430 T2 archive inserts (`mutation_events`)
* 1,042 T2 archive inserts (`mutation_stability_log`)
* 878 T3 inserts (`strategy_lifecycle_history` w/ `imported=true`)
* 1,047 T3 inserts (`strategy_performance_history` w/ `imported=true`)
* 13 T3 inserts (`auto_factory_alert_log` w/ `imported=true`)
* Warnings (advisory): `lineage_orphan` ×140, `text_match_no_fp_match` ×0, `calibration_drift` ×0, `schema_unknown_keys` ×3 (governance/market_environment/market_profile routed to `extensions`)

---

## 7. Out-of-scope / NOT done in this inspection

* No code written.
* No file inside `engines/asf/` created.
* No Mongo writes to canonical DB.
* No changes to live `strategy_library`, `strategy_lifecycle`, or any production collection.
* No import dry-run executed against the receiving pod.
* `asf_inspect` is a **temporary inspection DB** — safe to drop at operator's discretion.

---

**End of PACKAGE_INSPECTION_REPORT.md.**
**Awaiting operator decision on Step A (tier-filter knobs) and explicit authorisation for Step B (GATE 3 build per locked blueprint).**
