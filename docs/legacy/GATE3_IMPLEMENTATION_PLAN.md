# GATE3_IMPLEMENTATION_PLAN.md — Final Build Plan for ASF Migration Importer

**Status:** **READY FOR AUTHORISATION** — read-only planning document. No code written. No imports performed.
**Compiled from:** `ASF_PACKAGE_V1_SPEC.md` (v1.0 LOCKED) · `ASF_BACKEND_ARCHITECTURE.md` (LOCKED) · `MIGRATION_PRIORITY.md` (LOCKED, with operator amendments below) · `PACKAGE_INSPECTION_REPORT.md` (verdict 🟡 AMBER, adapter architecture valid without modification).
**Operator decisions applied:**
| Decision | Value |
|---|---|
| PF floor (T1 filter #2) | **1.20** (relaxed from 1.30) |
| `provenance.relaxation_reason` audit tag | **`"pf_floor_1.20"`** on every relaxed-tier survivor |
| `stage_locked_until` window | **+30 days** (default) |
| Lineage ancestor depth cap | **5 generations** (default) |
| Out-of-scope skip list | **Default per `ASF_BACKEND_ARCHITECTURE.md`** — `market_data`, `users`, `pipeline_logs`, `ingestion_runs`, `*_cycles`, `research_runs`, `llm_call_log`, `challenge_rules`, `prop_firm_rules`, `orchestrator_env_priority` |

**Pending operator decision before code starts (1 callout):** See §1.2 — strict vs. soft win_rate.

---

## 1. Concrete T1/T2/T3 outcome (now refined against the actual package)

### 1.1 Counts at PF ≥ 1.20

| Filter combination | T1 candidates |
|---|---:|
| Strict #1 (trades≥30) + Strict #2 (PF≥1.20) | **14** |
| + Strict #3 (win_rate≥0.40) | **1** |
| + Strict #4 (max_dd≤0.20) | **14** (all 14 have max_dd=0) |
| + #5–#6 soft-pass (per `MIGRATION_PRIORITY.md §2` legacy footnote) | **14** |
| + Strict #3 AND #4 simultaneously | **1** |

### 1.2 ⚠️ Operator callout — strict vs. soft win_rate

13 of the 14 candidates carry `win_rate ∈ [38.2, 39.4]` — narrowly **below** the strict 0.40 threshold (#3). Per `MIGRATION_PRIORITY.md §2`, rows failing #3 strictly should drop to T2, NOT receive a soft pass.

Operator options (please confirm before code starts):

| Option | T1 count | Behaviour |
|---|---:|---|
| **A — strict win_rate** | **1** | Single T1 survivor (`fp=455f09c9...`, XAUUSD/H4, PF=1.28, WR=40.0). Cleanest dedup signal; least operator surprise. |
| **B — relax win_rate to 0.38** | **14** | All 14 PF-passing candidates clear. Adds `provenance.relaxation_reason="pf_floor_1.20+wr_floor_0.38"`. |
| **C — soft-pass win_rate (#3 becomes advisory)** | **14** | Treat #3 like #5/#6: legacy soft-pass. Adds `provenance.relaxation_reason="pf_floor_1.20+wr_soft"`. |

**Recommendation:** **Option B** — explicit floor relaxation is more auditable than soft-pass overrides; preserves the spirit of `MIGRATION_PRIORITY.md §2` (strict numeric filters; only #5/#6 are soft because the legacy schema literally lacked the fields).

### 1.3 Data-quality observation (advisory only — no design impact)

All 14 PF-passing candidates carry `max_drawdown_pct = 0`. This is a legacy data anomaly (DD never re-computed for these variants), NOT a real zero-drawdown property. The adapter does NOT fabricate a DD — it preserves the legacy `0` value and flags `metrics.max_drawdown_pct_quality="not_recomputed_in_source"` under `extensions.migration.*`. Post-import pipeline (Phase 13 Dossier / revalidation) will recompute against live BI5-cached data.

### 1.4 Tier distribution (final)

| Tier | Count (Option B) | Action |
|---|---:|---|
| **T1** | 14 | Insert into live `strategy_library` with `stage="IMPORTED_SEED"`, `stage_locked_until=ISO(today+30d)`, `provenance.source="1vcpu_migration"`, `provenance.tier_class="T1"`, `provenance.relaxation_reason="pf_floor_1.20+wr_floor_0.38"`, `provenance.requires_revalidation=true` |
| **T2 — strategy_library** | 126 | Insert into `strategy_library_archive` read-only |
| **T2 — mutation_events** | 10,430 | Insert into receiver's `mutation_events` |
| **T2 — mutation_stability_log** | 1,042 | Insert into receiver's `mutation_stability_log` |
| **T3 — lifecycle_history** | 878 | Insert into receiver's `strategy_lifecycle_history` with `imported=true`, un-joined |
| **T3 — performance_history** | 1,047 | Insert into receiver's `strategy_performance_history` with `imported=true`, un-joined |
| **T3 — alerts** | 13 | Insert into receiver's `auto_factory_alert_log` with `imported=true` |
| **Skipped** | 1,053,512 + 5+11+86+143+6+16+3+3+2+5+792+9+1 | Per default skip list (§Decision row 4) |
| **Total receiver writes** | **~13,550** | All idempotent (skip / merge / replace per dedup policy) |

---

## 2. File-by-file build manifest (14 files, ~860 LOC budget)

Build order is bottom-up — leaf modules first, then walker/upserter/verifier, then adapter, then API. Each file is independently importable + unit-testable.

### 2.1 New files

| # | File | Est. LOC | Purpose | Tests |
|---|---|---:|---|---|
| 1 | `backend/engines/asf/__init__.py` | 5 | Package marker, version constant `ASF_VERSION = "1.0"` | — |
| 2 | `backend/engines/asf/schema.py` | **~250** | Pydantic v2 models: `Manifest`, `StrategyDoc`, `FingerprintInputs`, `Metrics`, `Lineage`, `Bi5Cert`, `Bi5CertWindow`, `Explorer`, `PortfolioAssignment`, `MasterBotMembership`, `Lifecycle`, `Provenance`, `MutationEvent`, `MutationStability`, `LifecycleHistoryEntry`, `PerformanceSnapshot`, `Alert`, `CalibrationSnapshot`, `PackageReadResult`. All models `extra="allow"` to preserve unknown keys per spec §12.1. | `test_asf_schema.py` |
| 3 | `backend/engines/asf/package_reader.py` | **~80** | In-memory variant only (per `ASF_BACKEND_ARCHITECTURE.md §3.9` — ZIP variant deferred). Public API: `parse_in_memory(payload: dict) -> PackageReadResult`. Validates against schema; computes manifest SHA-256s if not provided (migration synthesises them). | — |
| 4 | `backend/engines/asf/calibration_snapshot.py` | **~50** | Public API: `build_receiver_snapshot(db) -> CalibrationSnapshot`. Pulls `tick_validator_version` (= `"tick_validator@P0B-v2"`), `density_table` (post-R2 Step-0 Option A snapshot), `thresholds={"PASS_THRESHOLD":0.85,"WARN_THRESHOLD":0.70}`, `ranker_version` (`"master_bot_ranker@v1.1"`). | covered in `test_asf_migration_adapter.py` |
| 5 | `backend/engines/asf/dedup_policy.py` | **~60** | `apply_dedup(incoming, canonical, policy, match_kind) -> DedupOutcome`. Implements `skip` / `merge` / `replace` per spec §13. Pure function. | `test_asf_dedup_policy.py` |
| 6 | `backend/engines/asf/importer/__init__.py` | 3 | Package marker. | — |
| 7 | `backend/engines/asf/importer/walker.py` | **~120** | `walk(package, package_type, tier_filters, dedup_default) -> list[ApplyAction]`. Pure; no DB writes. Classifies each row by collection target + dedup outcome + tier_class (migration only). | covered in adapter tests |
| 8 | `backend/engines/asf/importer/upserter.py` | **~140** | `apply(actions, db, dry_run, audit) -> ImportResult`. Routes each action to canonical primitive (`strategy_library.save_strategy()`, etc.); writes `strategy_lifecycle_history` `event_type="asf_import"` row per inserted strategy; writes `asf_import_log` + `asf_import_actions`. Idempotent. | covered in adapter tests |
| 9 | `backend/engines/asf/importer/verifier.py` | **~80** | `verify(import_id, db) -> ImportVerification`. Re-reads inserted rows, checks fingerprint integrity. Cert-replay path is no-op for the 1-vCPU package (no exported cert windows). Emits `verified` / `verified_with_warnings`. | covered in adapter tests |
| 10 | `backend/engines/asf/importer/migration_adapter.py` | **~180** | **THE GATE 3 CORE FILE.** Public API: `async def adapt_1vcpu_to_asf_v1(inbox_dir, db, operator_overrides) -> PackageReadResult`. Detects format A (`mongodump --archive --gzip`) and runs the 15 transforms enumerated in §3 below. Returns in-memory `PackageReadResult` — never writes to disk. | `test_asf_migration_adapter.py` |
| 11 | `backend/api/asf.py` | **~80** | 4 admin endpoints (see §4). Auth via existing admin guard. | covered by endpoint smoke in `test_asf_migration_adapter.py` |
| 12 | `backend/tests/test_asf_schema.py` | **~80** | Schema round-trip · unknown-key preservation · enum coverage · scale invariants. | — |
| 13 | `backend/tests/test_asf_dedup_policy.py` | **~80** | All 3 policies · match_kind matrix · `_id` + `discovered_at` preservation on replace. | — |
| 14 | `backend/tests/test_asf_migration_adapter.py` | **~140** | Fixture: trimmed 1-vCPU `asf_inspect` dump. Asserts: 14 T1 / 126 T2 / 878+1,047+13 T3 with PF=1.20 + WR=0.38 floors · `provenance.relaxation_reason` present · lineage walk depth=5 · `calibration_drift_detected=false` · idempotency (run twice → identical receipts) · auto-selection guard blocks IMPORTED_SEED. | — |

### 2.2 Modified files (3 small edits)

| # | File | Change | LOC |
|---|---|---|---:|
| 15 | `backend/engines/auto_selection_engine.py` | Add 5-line guard at top of candidate loop: skip if `stage=="IMPORTED_SEED"` AND `stage_locked_until > now()`. Per `ASF_BACKEND_ARCHITECTURE.md §6.3`. | 5 |
| 16 | `backend/engines/strategy_library.py` | Add explicit `await collection.create_index("fingerprint", unique=True)` call, invokable from `upserter.py` before bulk T1 insert. Per `ASF_BACKEND_ARCHITECTURE.md §6.4`. | 3 |
| 17 | `backend/server.py` | One-line router include: `app.include_router(asf_router, prefix="/api")`. | 1 |

### 2.3 New Mongo collections (lazy-create — no migrations)

| Collection | Index | Created by |
|---|---|---|
| `asf_import_log` | `(import_id)` unique · `(created_at)` desc | `upserter.py` on first write |
| `asf_import_actions` | `(import_id, action_idx)` unique | `walker.py` → `upserter.py` |
| `strategy_library_archive` | `(fingerprint)` non-unique · `(imported_at)` desc | `upserter.py` on first T2 write |
| `migration_checkpoints` | `(import_id, step)` unique | `upserter.py` per step |

All four follow the lazy-create-on-first-write convention used by `bi5_cert_sweep_runs` (R2). No schema migration required.

### 2.4 Total LOC budget

| Layer | LOC |
|---|---:|
| Schema models | 250 |
| Reader / dedup / calibration / walker / upserter / verifier | 530 |
| Adapter (`migration_adapter.py`) | 180 |
| API | 80 |
| Modified files | 9 |
| Tests | 300 |
| **TOTAL** | **~1,350 LOC** (160 LOC above the `ASF_BACKEND_ARCHITECTURE.md §7.2` original ~1,190 estimate; the 14% growth absorbs the additional `relaxation_reason` audit tagging + the WR=0.38 floor logic) |

---

## 3. The 15 adapter transforms (locked sequence)

Each transform is field-level, deterministic, side-effect-free. Sequence matters for two pairs (T13 must follow T1; T11 must follow all others). Every transform is unit-tested.

| # | Transform | Source → Target | Notes |
|---|---|---|---|
| **T1** | Flatten → Nest metrics | `{total_trades, profit_factor, win_rate, max_drawdown_pct, stability_score}` (root) → `metrics.{...}` (nested) | |
| **T2** | Win-rate scale normalise | `win_rate ÷ 100` | 44.3 → 0.443 |
| **T3** | Compute `strategy_hash` | `sha256(strategy_text)` → 64-hex | required by spec §4 |
| **T4** | Synthesise `fingerprint_inputs.params_canon` | `engines/strategy_library._canon_params(row.parameters)` | reuses existing function |
| **T5** | Rename `parameters` → `params` | direct | |
| **T6** | Rename `mutation_base_fingerprint` → `lineage.parent_fingerprint` | direct | null if absent |
| **T7** | Walk `mutation_events` to populate `lineage.ancestors[]` | bounded depth = 5 | sets `ancestors_complete=false` |
| **T8** | Synthesise `lifecycle` block | T1: `stage="IMPORTED_SEED"`, `stage_locked_until=ISO(today+30d)`; T2/T3: preserve legacy under `extensions.migration.legacy_stage` | |
| **T9** | Synthesise `provenance` block | `source="1vcpu_migration"`, `tier_class`, `requires_revalidation=true`, `requires_rematching=true`, `discovered_at=row.created_at`, **`relaxation_reason="pf_floor_1.20+wr_floor_0.38"`** for all T1 | per operator decision |
| **T10** | Rename `validation_report.walk_forward.success` → `.passed` | direct | preserves all other walk_forward fields |
| **T11** | Inject calibration snapshot from receiving pod | tick_validator@P0B-v2 · post-R2 density table · PASS=0.85/WARN=0.70 · ranker@v1.1 | sets `calibration_drift_detected=false` trivially |
| **T12** | Empty/null defaults | `bi5_cert=null` · `explorer=null` · `portfolio_assignments=[]` · `master_bot_memberships=[]` · `metrics.sharpe=null` · `metrics.sortino=null` · `metrics.calmar=null` | |
| **T13** | Tier classification | PF≥1.20 + trades≥30 + WR≥0.38 + DD≤0.20 → T1; rest → T2 | Option B |
| **T14** | T3 un-joined ingest | lifecycle_history / performance_history / alert_log → receiver collections w/ `imported=true` | no FK to library |
| **T15** | Drop out-of-scope collections | per skip list (Decision row 4) | `market_data` 1.05M rows are not loaded into memory; mongodump streamed past |

---

## 4. API surface (GATE 3 scope only)

Per `ASF_BACKEND_ARCHITECTURE.md §3.10` — locked.

| Method | Path | Auth | Behaviour |
|---|---|---|---|
| `POST` | `/api/asf/import/migration` | admin | Body: `{ inbox_path: "/app/_migration_inbox/", dry_run: true, operator_overrides: { pf_floor: 1.20, wr_floor: 0.38, lineage_depth: 5, lock_days: 30 } }`. Runs `migration_adapter` → `walker` → `verifier`. Returns `import_id` + receipt. NO writes (dry-run). |
| `GET` | `/api/asf/import/{import_id}` | admin | Returns full receipt (per-collection counts, tier_breakdown, warnings, verifier report). |
| `POST` | `/api/asf/import/{import_id}/commit` | admin | Applies staged actions via `upserter`. Writes 14 T1 + 126 T2 (library_archive) + 10,430+1,042 T2 + 878+1,047+13 T3 ≈ **13,550 rows**. Idempotent re-runs are no-ops (dedup `skip`). |
| `POST` | `/api/asf/import/{import_id}/abort` | admin | Discards staged actions; emits one `audit_log` row. |

All other `/api/asf/*` endpoints (export, snapshots, generic import) reserved → return `503 Not Implemented` per architecture §3.10.

---

## 5. Idempotency contract

| Layer | Guarantee | Test |
|---|---|---|
| **T1 inserts** | Unique-fingerprint index pre-created before bulk insert; re-runs detect 14 existing fingerprints and skip per default policy | `test_asf_migration_adapter::test_t1_idempotent_re_run` |
| **T2 archive inserts** | `strategy_library_archive` keyed on `(fingerprint, imported_at)`; re-runs detect by `(fingerprint, source_export_id)` and skip | `test_asf_migration_adapter::test_t2_idempotent_re_run` |
| **T3 un-joined inserts** | Each row carries `(strategy_hash, source_export_id, imported=true)`; composite-key dedup on re-run | `test_asf_migration_adapter::test_t3_idempotent_re_run` |
| **Adapter conversion** | Deterministic — same input mongodump produces byte-identical in-memory `PackageReadResult` | `test_asf_migration_adapter::test_adapter_determinism` |
| **Receipt** | Same `import_id` returns identical receipt; `commit` is one-shot (second `commit` on same id returns `409 Conflict`) | `test_asf_migration_adapter::test_commit_one_shot` |
| **Auto-selection guard** | T1 strategies with `stage="IMPORTED_SEED"` AND `stage_locked_until > now()` are invisible to auto-deploy | `test_asf_migration_adapter::test_imported_seed_blocked` |

---

## 6. Dry-run → wet-run flow (post-build, separately authorised)

```
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 0  Operator drops `migration_bundle.tar.gz` into                │
│         /app/_migration_inbox/                                        │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 1  POST /api/asf/import/migration  { dry_run: true,             │
│           operator_overrides: { pf_floor: 1.20, wr_floor: 0.38,      │
│           lineage_depth: 5, lock_days: 30 } }                        │
│         → adapter loads dump · walker classifies all rows ·          │
│           verifier sanity-checks · NO writes                          │
│         → returns import_id + receipt with:                           │
│             • tier_breakdown {T1:14, T2:11556, T3:1938}              │
│             • warnings list (lineage_orphan ×140 expected)            │
│             • calibration_drift_detected: false                       │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 2  GET /api/asf/import/{import_id}                              │
│         → operator reviews receipt; if acceptable proceed             │
│         → if NOT acceptable POST /abort and re-tune overrides         │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 3  POST /api/asf/import/{import_id}/commit                      │
│         → upserter writes 13,550 rows · emits 13,550 audit_log rows  │
│         → verifier re-reads · returns status="verified" or           │
│           "verified_with_warnings"                                    │
│         → duration estimate: 60–120 s (per MIGRATION_PRIORITY.md §6) │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 4  Operator validates live state:                                │
│         • 14 strategies visible in StrategyLibrary UI with            │
│           stage="IMPORTED_SEED" badge                                 │
│         • Auto-Selection panel does NOT surface them as deployable   │
│         • Dossier engine (when it ships) can navigate T3 evidence    │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (T+30 days, separately authorised)
┌──────────────────────────────────────────────────────────────────────┐
│ STEP 5  Post-import pipeline (POST_IMPORT_PIPELINE.md)               │
│         re-validates each T1 against live BI5 data, recomputes       │
│         metrics, flips requires_revalidation=false on pass, makes    │
│         the strategy deployable via existing Auto-Selection UI.      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 7. Refined effort estimate

| Item | Hours |
|---|---:|
| `schema.py` (250 LOC + roundtrip tests) | 4 |
| `dedup_policy.py` + tests | 2 |
| `package_reader.py` (in-memory variant) | 2 |
| `calibration_snapshot.py` | 1 |
| `walker.py` + `upserter.py` + `verifier.py` | 6 |
| `migration_adapter.py` (the 15 transforms + lineage walker + format-A detect) | 8 |
| `api/asf.py` (4 endpoints) | 2 |
| `auto_selection_engine.py` 5-line guard + test | 1 |
| `strategy_library.py` index pre-create | 0.5 |
| `server.py` router include | 0.5 |
| `test_asf_migration_adapter.py` (fixture build + 8 scenarios) | 5 |
| **Subtotal — implementation** | **32 h** |
| Self-review + lint + screenshot smoke | 2 |
| `testing_agent_v3_fork` invocation + iteration on findings | 4 |
| **TOTAL** | **~38 h ≈ 4.5 dev-days** |

This is ~0.5 day above the original blueprint estimate (~3-4 d). The 0.5-d overrun is owed entirely to:
* `relaxation_reason` audit-tag plumbing across 3 files (~1 h)
* WR=0.38 floor + the additional walk_forward.success→passed rename test (~1 h)
* Larger test fixture (full asf_inspect trim) (~2 h)

No architectural surprise; no rework risk.

---

## 8. Risk register — implementation-time

| # | Risk | Probability | Mitigation |
|---|---|---|---|
| **R1** | `engines/strategy_library._canon_params()` signature drift since the spec was written | Low | Existing function unit-tested in R2; signature stable. Adapter wraps it with `try/except` and falls back to a deterministic sort+json.dumps if signature changes. |
| **R2** | `mongodump --archive --gzip` streaming consumes >2 GB RAM for the 1.05M `market_data` rows | Low | Adapter skips `market_data` by collection name **at the streaming layer** (before deserialisation); never loads into memory. Tested via fixture. |
| **R3** | `strategy_library_archive` collection name collides with future ASF DR exporter | Very low | Architecture §4 reserves the collection name; DR exporter (deferred) will use `asf_artifact_registry` instead. |
| **R4** | Auto-selection guard breaks an existing legacy code path | Very low | 5-line `if/continue` at the very top of the loop; test asserts ordinary non-IMPORTED_SEED candidates still flow through. |
| **R5** | Bulk insert of 13,550 rows blocks the event loop | Low | Upserter chunks at 500 rows per `await collection.insert_many()`. Estimated wall time 60–120 s; not blocking under FastAPI's async loop. |
| **R6** | Operator forgets `dry_run=true` and writes happen unexpectedly | Low | API default is `dry_run=true`; `commit` is a separate endpoint requiring explicit `import_id` echo. Two-step gate. |
| **R7** | Receiver's canonical `strategy_library` already contains a `provenance.source="1vcpu_migration"` row from an aborted prior run | Very low | Receiver currently shows 0 rows from that source. If present in future, dedup `skip` policy makes re-runs no-op. |
| **R8** | Test fixture file >10 MB bloats the repo | Low | Fixture is a hand-trimmed JSON (~50 KB) covering the 14 T1 candidates + 5 representative T2 + 5 T3 + 1 lineage chain. |

---

## 9. GATE 3 acceptance criteria (per `ASF_BACKEND_ARCHITECTURE.md §9`)

Each criterion is mapped to a specific test in `test_asf_migration_adapter.py`:

| # | Criterion | Test |
|---|---|---|
| 1 | `engines/asf/importer/migration_adapter.py` exists and imports | `test_module_importable` |
| 2 | Dry-run on the 1-vCPU package produces a receipt classifying every row into T1/T2/T3 | `test_dry_run_full_classification` (asserts 14/11556/1938) |
| 3 | Receipt distinguishes `fingerprint` vs `strategy_hash`-only matches | `test_match_kind_distinction` |
| 4 | Calibration drift surfaces a `calibration_drift_warning` — non-fatal | `test_no_drift_when_receiver_matches` |
| 5 | Commit writes via `save_strategy()` — never bypassing native primitives | `test_commit_uses_save_strategy` (mock-spy on `save_strategy`) |
| 6 | T1 rows tagged `stage="IMPORTED_SEED"`, `stage_locked_until=ISO(today+30d)` | `test_t1_tagging` |
| 7 | 5-line auto-selection guard blocks IMPORTED_SEED candidates | `test_imported_seed_blocked` |
| 8 | Unique-fingerprint index pre-created before bulk insert | `test_index_precreate` (spy on `create_index`) |
| 9 | Post-import verifier re-reads every row and reports drift / mismatches | `test_verifier_reports_clean_status` |
| 10 | Tests cover schema · dedup · adapter format A · T1/T2/T3 classification · calibration drift | the file itself |
| **11 (added)** | Every T1 row carries `provenance.relaxation_reason="pf_floor_1.20+wr_floor_0.38"` | `test_relaxation_reason_tagged` |
| **12 (added)** | Out-of-scope collections (market_data, users, etc.) NEVER appear in the receipt | `test_skip_list_enforced` |
| **13 (added)** | Idempotency: second commit on same `import_id` returns 409 | `test_commit_one_shot` |

---

## 10. What is **NOT** built in GATE 3

Locked exclusions — these ship in later, separately authorised phases:

* `engines/asf/exporter/*` (entire export side) — Phase 7.3 in `ASF_BACKEND_ARCHITECTURE.md`
* `engines/asf/disaster_recovery/*` (DR scheduler + restore) — Phase 7.4
* `engines/asf/package_writer.py` (ZIP writer) — Phase 7.3
* Generic `POST /api/asf/import` for arbitrary `.asfpkg` files (only the migration endpoint ships)
* `frontend/src/components/asf/*` UI panels — Phase 7.5
* PKI signing — Phase 7.6
* `asf_artifact_registry` + `asf_snapshot_runs` collections — Phase 7.4

---

## 11. Authorisation checklist

Before code starts, please confirm:

- [ ] **Option A / B / C** for win_rate handling (§1.2) — recommended **B**
- [ ] Adapter file path is `backend/engines/asf/importer/migration_adapter.py` (locked)
- [ ] 14 work items + 3 modified files + 4 lazy-create collections is the full GATE 3 surface
- [ ] LOC budget ~1,350 / effort ~4.5 dev-days is acceptable
- [ ] Acceptance criteria §9 (10 locked + 3 added) gate the GO-LIVE
- [ ] Build proceeds via `testing_agent_v3_fork` after implementation; no dry-run or wet-run until separate authorisation

When confirmed, the receiving agent will:
1. Build the 14 files + apply the 3 modifications in dependency order.
2. Run `mcp_lint_python` after each file.
3. Run the local pytest suite (`pytest backend/tests/test_asf_*.py -v`).
4. Take **one** smoke screenshot of the running pod.
5. Invoke `testing_agent_v3_fork` with the full GATE 3 test brief.
6. Fix all findings.
7. Hand back to operator for dry-run authorisation against the actual `migration_bundle.tar.gz`.

---

**End of GATE3_IMPLEMENTATION_PLAN.md.**
**Status: READY FOR AUTHORISATION. Awaiting operator GO on §11 checklist.**
