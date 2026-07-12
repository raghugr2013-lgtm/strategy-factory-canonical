# ROADMAP_READINESS_AUDIT.md — Deployment-Focused Assessment

**Mode:** Read-only audit. **No code modified. No phase started. No deployment performed.**
**Scope:** BI5 R3 · Shadow Mode · Phase 13 Dossier · Phase 14 Valuation · ASF Exporter · 12-vCPU Deployment readiness.
**Source-of-truth:** live code inspection of `/app/backend/engines/`, `/app/backend/api/`, `/app/frontend/src/components/`, live MongoDB collection presence on `test_database`.
**Constraints honoured:** No BI5 R3 · no Shadow Mode · no Phase 13 · no Phase 14 · no ASF Exporter · no deployment.

---

## 1. Executive summary — current roadmap position

| Phase / Gate | % complete | Live blocker? | Tier |
|---|---:|:--:|:--:|
| Migration restore + validation | 100% | — | done |
| BI5 R2 Step-0 calibration | 100% | — | done |
| R2 Batch (B-4 / B-5 / B-8) | 100% | — | done |
| ASF v1.0 spec + locked architecture | 100% | — | done |
| GATE 3 ASF migration importer | 100% (14 files, 28 tests green) | — | done |
| GATE 3 dry-run + wet-run | 100% | — | done |
| Post-import pipeline (revalidate + rescore + rematch) | 100% — outcome blocked at MISSING_FILLS / DATA_CERT_MISSING | data | done |
| M-1 → M-5 deployment packaging | 100% (10-file bundle, 10 KB tarball) | — | done |
| **HERE — Roadmap readiness audit** | 100% (this doc) | — | done |
| 12-vCPU VPS bring-up | **~85%** (only ops left) | none | **A** |
| BI5 R3 — B-3 tick-replay | **~25%** | none | C |
| BI5 R3 — B-6 simulate_fills | **~70%** | none | C |
| BI5 R3 — B-7 Trade Runner consolidation | **~60%** | none | C |
| Shadow Mode (trade-capture) | **~5%** | yes (post-deploy) | A/B |
| Phase 13 Dossier Engine | **0%** | none | C |
| Phase 14 Valuation Engine | **0%** | none | D |
| ASF Exporter | **~30%** (schema reusable from GATE 3) | none | C |

---

## 2. Per-phase deep dive

### 2.1 BI5 R3 — B-3 tick-replay

| Dimension | Status |
|---|---|
| Current completion | **~25%** |
| Existing modules | `engines/replay_priority.py` (83 LOC; ranking/prioritization only — not full replay) · `engines/bi5_maturity.py` |
| Existing DB structures | `bi5_data_certification` (R2 already populated) · `bi5_cert_sweep_runs` |
| Existing APIs | Cert sweep endpoint at `/api/admin/bi5/sweep` (R2 surface) |
| Existing UI | `Bi5CertPanel.jsx`, `BI5HealthPanel.jsx` (cert-side; no replay viewer yet) |
| Remaining modules | `engines/bi5_tick_replay.py` (tick-by-tick replay against historical archive) · `engines/bi5_replay_persistence.py` (replay store) |
| Remaining DB | `bi5_replay_results` (per-strategy per-symbol per-window replay outcome) |
| Remaining API | `POST /api/admin/bi5/replay` (operator-triggered) · `GET /api/diag/bi5/replay/{run_id}` |
| Remaining UI | Tick-replay viewer panel (optional; can ship later) |
| Est. LOC remaining | ~400 LOC (engine 250 + API 70 + tests 80) |
| Est. effort | ~3 dev-days |
| Credit risk | Medium — replay engines tend to need 2–3 iteration cycles |
| Critical or enhancement? | **Enhancement** — R2 cert sweep already certifies strategies; replay improves fidelity but is not a hard prerequisite for any other phase |
| Build before or after deploy? | **After** — replay runs against the archive, no DB-shape changes, additive |
| VPS-developable? | **YES** — entirely additive engine + endpoint |

### 2.2 BI5 R3 — B-6 simulate_fills

| Dimension | Status |
|---|---|
| Current completion | **~70%** |
| Existing modules | `engines/execution_simulator.py` (342 LOC) with `simulate_fill`, `simulate_fills`, `VenueProfile`, `FillResult`, `ExecutionReport`, `pick_decision_tick`, `pick_fill_tick`, `sample_latency_ms` |
| Existing DB structures | Reuses `bi5_data_certification` for context |
| Existing APIs | None — simulator is a callable module |
| Existing UI | None |
| Remaining modules | Wire `simulate_fills` into the BI5 cert sweep path so cert runs without live fills can fall back to a deterministic simulation · `engines/bi5_simfill_bridge.py` (sweep→simulator glue) |
| Remaining DB | `simulated_fills` collection (per-strategy per-window simulator output, for audit) |
| Remaining API | Optional `GET /api/diag/simfill/{strategy_hash}` for forensics |
| Remaining UI | None required for v1 |
| Est. LOC remaining | ~250 LOC (bridge 120 + persistence 60 + tests 70) |
| Est. effort | **~2 dev-days** |
| Credit risk | Low — simulator is well-tested already |
| Critical or enhancement? | **Mixed** — for the imported cohort to ever flip `requires_revalidation=false` WITHOUT shadow-mode, this is the only realistic path |
| Build before or after deploy? | **Either** — additive; cleanest on VPS where simfill output reflects production calibration |
| VPS-developable? | **YES** |

### 2.3 BI5 R3 — B-7 Trade Runner consolidation

| Dimension | Status |
|---|---|
| Current completion | **~60%** |
| Existing modules | `engines/trade_runner_engine.py` (415 LOC — `start_run`, `step_run`, `compute_position`, `go_no_go`, `_simulate_trade`, halt logic) · `engines/factory_runner_heartbeat.py` · `engines/runner_account_migration.py` · `engines/runner_registry.py` · `engines/runner_router.py` · `engines/runner_token_rotator.py` |
| Existing DB structures | Internal run state in-memory; persistence partial |
| Existing APIs | `/api/trade-runner/start` · `/step/{run_id}` · `/stop/{run_id}` · `/status/{run_id}` · `/runs` · `/config` (6 endpoints, 112 LOC) |
| Existing UI | `frontend/src/components/TradeRunner.js` |
| Remaining modules | Unify shadow vs simulated vs live paths · attach to live broker via existing `runner_router` · persistence layer for orders/fills |
| Remaining DB | `trade_runner_orders` · `trade_runner_fills` · `trade_runner_runs` (full persistence) |
| Remaining API | Endpoints already exist; consolidation is internal |
| Remaining UI | Polish TradeRunner.js to show shadow vs live mode badge |
| Est. LOC remaining | ~600 LOC (persistence 250 + path-unification 200 + UI 80 + tests 70) |
| Est. effort | ~4 dev-days |
| Credit risk | Medium-High — touches broker integration |
| Critical or enhancement? | **Critical for shadow-mode** (which is critical for promoting imported survivors) |
| Build before or after deploy? | **After** — consolidation is safer on the VPS where you can run alongside production with low-stakes test orders |
| VPS-developable? | **YES** — though prefer to draft on Emergent and validate on VPS |

### 2.4 Shadow Mode (trade-capture)

| Dimension | Status |
|---|---|
| Current completion | **~5%** |
| Existing modules | `engines/r5_shadow_comparator.py` (509 LOC) — but this is **READ-ONLY RECONCILIATION SHADOW** comparing legacy-vs-shadow code paths during refactors. NOT trade-capture shadow. |
| Existing DB structures | None for trade-capture shadow |
| Existing APIs | None |
| Existing UI | None |
| Remaining modules | `engines/shadow_mode_runner.py` (subscribes to live ticks, computes strategy signals against the strategy's text/IR, records "what would have happened" without sending real orders) · `engines/shadow_fill_recorder.py` (writes simulated fills + signals to `trade_runner_fills` with `shadow=true`) |
| Remaining DB | `shadow_mode_runs` · `shadow_signals` · `shadow_fills` (or reuse `trade_runner_*` with a flag) |
| Remaining API | `POST /api/admin/shadow/start` · `POST /api/admin/shadow/stop/{id}` · `GET /api/admin/shadow/{id}/fills` |
| Remaining UI | "Shadow runs" admin tile listing active captures and per-strategy progress |
| Est. LOC remaining | ~700 LOC (runner 350 + recorder 150 + API 100 + UI 100) |
| Est. effort | **~4-5 dev-days** |
| Credit risk | Medium — depends on broker tick subscription correctness |
| Critical or enhancement? | **Critical** — the ONLY documented path to flip `requires_revalidation=false` for the 14 imported survivors (per `POST_IMPORT_PIPELINE.md §11`) is shadow capture → BI5 cert sweep → per-merit verdict |
| Build before or after deploy? | **AFTER** — must run against live market data (12-vCPU VPS has a stable IP and broker connectivity; Emergent is ephemeral) |
| VPS-developable? | **YES — and preferred there.** Shadow mode by definition needs to run continuously against live ticks |

### 2.5 Phase 13 Dossier Engine

| Dimension | Status |
|---|---|
| Current completion | **0%** |
| Existing modules | None directly. Some adjacent data: `strategy_performance_history` (1,047 imported rows + ongoing), `mutation_events` (10,430 imported), `strategy_lifecycle_history` (878 imported) — all the raw material a dossier would assemble |
| Existing DB structures | Reusable: `strategy_library`, `mutation_events`, `strategy_lifecycle_history`, `strategy_performance_history`, `bi5_strategy_certifications`, `auto_factory_alert_log` |
| Existing APIs | None |
| Existing UI | None |
| Remaining modules | `engines/dossier_assembler.py` (queries all collections by strategy_hash, builds a single normalised dossier doc) · `engines/dossier_pdf_writer.py` (renders to PDF via reportlab — already a dependency) · `engines/dossier_persistence.py` (stores assembled dossiers) |
| Remaining DB | `dossier_artifacts` (one per strategy per assembly run) · `dossier_assembly_log` |
| Remaining API | `POST /api/dossier/assemble/{strategy_hash}` · `GET /api/dossier/{strategy_hash}` · `GET /api/dossier/{strategy_hash}/pdf` |
| Remaining UI | "Dossier" tab on each strategy detail page · per-cohort "Generate dossiers for all 14" admin batch button |
| Est. LOC remaining | **~1,500 LOC** (assembler 600 + PDF writer 350 + persistence 150 + API 150 + UI 250) |
| Est. effort | **~5 dev-days** |
| Credit risk | Medium — PDF rendering tends to need 1–2 polish cycles |
| Critical or enhancement? | **Enhancement** — operator-facing value but NOT a deployment blocker |
| Build before or after deploy? | **After** — purely additive; uses no new infrastructure |
| VPS-developable? | **YES** |

### 2.6 Phase 14 Valuation Engine

| Dimension | Status |
|---|---|
| Current completion | **0%** |
| Existing modules | None |
| Existing DB structures | None directly (Phase 13 Dossier output would be an input) |
| Existing APIs | None |
| Existing UI | None |
| Remaining modules | `engines/valuation_engine.py` (assigns a $ market value per strategy / per cohort / per master-bot based on PF · stability · regime fit · liquidity) · `engines/valuation_persistence.py` |
| Remaining DB | `strategy_valuation` · `valuation_runs` |
| Remaining API | `POST /api/valuation/compute` · `GET /api/valuation/{strategy_hash}` |
| Remaining UI | "Valuation" widget on strategy + cohort cards |
| Est. LOC remaining | **~1,200 LOC** (engine 700 + persistence 100 + API 150 + UI 250) |
| Est. effort | **~4-5 dev-days** |
| Credit risk | Medium-High — valuation methodology requires operator-in-the-loop calibration |
| Critical or enhancement? | **Enhancement** — useful for marketplace pricing; pure value-add, not a blocker |
| Build before or after deploy? | **After** — depends on Phase 13 Dossier ideally |
| VPS-developable? | **YES** |

### 2.7 ASF Exporter

| Dimension | Status |
|---|---|
| Current completion | **~30%** (schema, dedup, calibration_snapshot, package_reader are reusable from GATE 3 importer) |
| Existing modules (reusable) | `engines/asf/schema.py` (Pydantic v1.0 models) · `engines/asf/calibration_snapshot.py` · `engines/asf/dedup_policy.py` · `engines/asf/package_reader.py` |
| Existing DB structures | `asf_import_log`, `asf_import_actions` (reusable shape for export log) |
| Existing APIs | Importer surface at `/api/asf/import/*` (4 endpoints) |
| Existing UI | None |
| Remaining modules | `engines/asf/exporter/__init__.py` · `engines/asf/exporter/package_writer.py` (ZIP layout per spec §3) · `engines/asf/exporter/manifest_builder.py` · `engines/asf/exporter/migration_writer.py` (for the inverse of `migration_adapter`) · `engines/asf/disaster_recovery/scheduler.py` (cron-driven daily snapshots) · optional `engines/asf/marketplace/pki_signer.py` |
| Remaining DB | `asf_export_log` · `asf_artifact_registry` · `asf_snapshot_runs` |
| Remaining API | `POST /api/asf/export` · `GET /api/asf/export/{export_id}` · `POST /api/asf/snapshot/run` · `GET /api/asf/snapshot/runs` |
| Remaining UI | "ASF Exports" admin panel · "DR Snapshots" admin panel |
| Est. LOC remaining | **~1,800 LOC** (exporter core 800 + DR scheduler 300 + UI 300 + API 200 + tests 200) |
| Est. effort | **~6-7 dev-days** |
| Credit risk | Medium |
| Critical or enhancement? | **Enhancement** — only needed for: (a) backing up the VPS, (b) migrating to another pod, (c) marketplace. Daily mongodump (already in M-4 backup.sh) covers (a) |
| Build before or after deploy? | **After** — backups already covered by mongodump |
| VPS-developable? | **YES** |

### 2.8 12-vCPU VPS deployment

| Dimension | Status |
|---|---|
| Current completion | **~85%** (M-1 → M-5 done; only operator ops work remains) |
| Existing modules | `/app/deploy/` bundle (10 files, 10 KB tarball, validated YAML + nginx + 5 shell scripts) |
| Existing DB structures | `factory` DB on receiver pod ready for mongorestore on VPS |
| Existing APIs | `/api/health` · `/api/admin/bi5/sweep` · 4 ASF endpoints · all 12 in-process schedulers |
| Existing UI | Full React app ready for yarn build |
| Remaining modules | **None** — bundle is complete |
| Remaining DB | **None** — schema migrates with mongodump |
| Remaining API | **None** |
| Remaining UI | **None** (just `yarn build` step) |
| Est. LOC remaining | **0 dev LOC** (ops scripts already shipped) |
| Est. effort | **~6 ops-hours** (provision + scp + compose up + restore + certbot + probe + cron) |
| Credit risk | **Low** — work runs on VPS, not on Emergent compute |
| Critical or enhancement? | **Critical** — the operator's stated immediate goal |
| Build before or after deploy? | **N/A** (this IS the deploy) |
| VPS-developable? | n/a |

---

## 3. Final decision matrix

### A — Must build BEFORE 12-vCPU deployment

| Item | Why |
|---|---|
| 12-vCPU VPS bring-up itself | Operator's stated goal |

That's it. **One item.** Everything else is safer post-deploy.

### B — Strongly recommended BEFORE deployment

| Item | Why | Effort |
|---|---|---:|
| Final smoke run of `startup_probe.sh` on the deployment bundle (locally if possible) | Catches typos in env.example before VPS contact | 0.5 h |
| Decide DNS + domain name for the VPS | Required for LE cert | 0.5 h |
| Operator-rotate `JWT_SECRET` + `ADMIN_PASSWORD` + `EMERGENT_LLM_KEY` budget check | Security + LLM key budget validation | 0.5 h |

### C — Safe to build AFTER deployment

| Item | Why post-deploy is fine |
|---|---|
| Shadow Mode (trade-capture) | Needs stable IP + live ticks; VPS is the right environment |
| BI5 R3 — B-6 simulate_fills | Pure additive engine; no schema break |
| BI5 R3 — B-7 Trade Runner consolidation | Additive; can iterate against live broker on VPS |
| BI5 R3 — B-3 tick-replay | Pure additive; no schema break |
| Phase 13 Dossier Engine | Read-only aggregation over existing data |
| ASF Exporter | Daily mongodump already covers backup needs |

### D — Best deferred until much later

| Item | Reason |
|---|---|
| Phase 14 Valuation Engine | Depends on Phase 13 + operator methodology calibration; far from critical path |
| ASF marketplace / PKI signing | Only relevant once there's a second VPS or external buyer |

---

## 4. Remaining blockers to first live 12-vCPU factory operation

**Functional blockers:** **NONE.** The system runs end-to-end on Emergent today;
all the same code paths run on the VPS.

**Operational blockers (operator action only):**
1. VPS provisioning (provider, region, SSH key)
2. DNS A-record pointing at the VPS IP
3. Domain name for LE TLS cert
4. Operator-chosen admin credentials + JWT secret rotation
5. `scp` of the deployment bundle + Mongo dump

**Soft blockers (not strictly required but recommended):**
6. ETHUSD source-data acquisition strategy — without it, 11/14 imported survivors stay
   at `DATA_CERT_MISSING` indefinitely. Operator decides if/how to source.
7. Operator confirmation that the `1vcpu_2026_migration` cohort lock window
   (`2026-07-13`) is acceptable post-deploy.

---

## 5. Three execution paths

### 5.1 ⚡ FASTEST path to operational deployment

**Goal:** first live 12-vCPU factory in the shortest wall-clock time.

```
TODAY (4 h ops):
  ├─ Provision VPS (Ubuntu 22.04 · 12 vCPU · 32 GB · 200 GB)
  ├─ Point DNS at the VPS IP (10-min TTL propagation)
  ├─ scp factory-deploy-bundle.tgz + mongodump
  ├─ install.sh → docker compose up -d → mongorestore → certbot → startup_probe
  └─ Confirm STATUS: GREEN
TOMORROW (passive 24 h):
  └─ Sanity-watch /api/health + scheduler liveness
DAY 3+:
  └─ Operational. Hold all phase work until 72-h soak completes.
```

**Wall-clock to live: ~6 hours of operator time + 72-h soak.**
**Code on Emergent: 0 hours.** No phase started.
**Risk: low** — full code base is already shipped and tested.

### 5.2 💰 LOWEST-CREDIT path to operational deployment

**Goal:** zero additional Emergent compute spend.

```
This path is identical to §5.1.
No additional code work means no additional Emergent credits.
The deployment bundle already exists.
```

**Emergent credits consumed: ~zero.** All work after `compose up` is on the VPS.

### 5.3 🏆 HIGHEST-QUALITY path to operational deployment

**Goal:** "production-grade everywhere", maximal pre-deploy hardening.

```
PRE-DEPLOY (Emergent · ~3 dev-days):
  Day 1   B-6 simulate_fills bridge (~2 d) — enables synthetic re-cert without
          shadow-mode dependency; the 14 imported survivors can move from
          MISSING_FILLS to a real per-merit verdict immediately on the VPS.
  Day 2.5 Smoke + regression suite full pass
  Day 3   Re-package bundle with the new engine bits

DEPLOY (VPS · ~6 h ops):
  Same as §5.1
  
POST-DEPLOY (VPS · ~7 dev-days, additive):
  Days 4-6   B-7 Trade Runner consolidation + Shadow Mode
  Days 7-8   ETHUSD source-data ingest (operator-supplied archive) + cert sweep
  Days 9-11  Phase 13 Dossier Engine
  Days 12-13 ASF Exporter + DR scheduler
  
Phase 14 / Marketplace: deferred until cohort promotion data justifies them.
```

**Total: ~3 pre-deploy dev-days + 6 ops-hours + ~7 post-deploy dev-days.**
**Risk: lowest** — every cohort survivor has a credible promotion path on day 1.
**Credit cost: highest of the three** (~10 dev-days of Emergent work).

---

## 6. Per-item summary table (operator one-page reference)

| Item | Tier | Build where? | LOC remaining | Effort | Critical? | Build before deploy? | VPS-developable? |
|---|:--:|---|---:|---:|:--:|:--:|:--:|
| 12-vCPU VPS bring-up | **A** | VPS | 0 | 6 ops-h | yes | n/a | n/a |
| B-6 simulate_fills bridge | C (B in 🏆 path) | Either | ~250 | 2 d | mixed | optional | yes |
| Shadow Mode (trade-capture) | C (A for cohort progression) | **VPS** | ~700 | 4–5 d | yes (post-deploy) | no | **yes** |
| B-7 Trade Runner consolidation | C | Either | ~600 | 4 d | yes | no | yes |
| B-3 tick-replay | C | Either | ~400 | 3 d | no | no | yes |
| Phase 13 Dossier | C | Either | ~1,500 | 5 d | no | no | yes |
| ASF Exporter | C | Either | ~1,800 | 6–7 d | no | no | yes |
| Phase 14 Valuation | **D** | Either | ~1,200 | 4–5 d | no | no | yes |

---

## 7. Recommended operator decision

### 🎯 Top recommendation: **the ⚡ FASTEST path (§5.1).**

**Rationale:**
1. The deployment bundle is **already built, tested, and packaged** (10 KB tarball).
2. Every functional capability the operator needs on day 1 is **already in the code**.
3. The 14-strategy `1vcpu_2026_migration` cohort is **safely gated** (`IMPORTED_SEED`
   + `requires_*` flags + lock window until 2026-07-13). No risk of accidental
   deployment of unvalidated strategies in the first 5 months.
4. **Shadow-mode capture is the only credible promotion path**, and shadow-mode is
   architecturally a VPS-side activity (it needs a stable IP + continuous broker
   connection). Building shadow-mode on Emergent first wastes credits — it cannot
   meaningfully run there.
5. Phase 13 / 14 / ASF Exporter are **purely additive enhancements**. None of them
   block deployment, none of them change DB schemas of existing collections, all
   are VPS-developable.

### Suggested operator sequence

```
WEEK 1   Deploy. 72-h soak. Confirm everything green.
         Operator runs first audit on the VPS (mongodump, restore_drill,
         startup_probe daily).
WEEK 2   Build Shadow Mode on the VPS (live-tick subscription is easier from
         the production environment than from an ephemeral Emergent pod).
WEEK 3   Shadow-capture the 3 XAUUSD survivors for ~30 fills each.
         Re-run cert sweep → expect per-merit PASS / WARN / FAIL.
         Promote XAUUSD survivors that PASS.
WEEK 4   Decide ETHUSD source-data strategy. Either drop external Dukascopy
         ETHUSD .bi5 files into /data/bi5, OR configure a pull. Re-run cert
         sweep for the 11 ETHUSD survivors.
WEEK 5+  Either Phase 13 Dossier (operator-visible value) or BI5 R3 B-6/B-7
         (cohort progression depth) — operator's choice.
```

### Why NOT the 🏆 highest-quality path right now

* Adds 3 dev-days of Emergent credit consumption with **no functional gain that
  cannot also be achieved post-deploy**.
* B-6 simulate_fills, while useful, can ship as a post-deploy hotfix without any
  schema migration.
* Shadow mode is the credible promotion path; simulator is an alternative that
  the operator can choose to skip if shadow mode works first try.

### Why NOT defer deployment

* Every additional day on Emergent consumes compute credits with no progression
  toward the operator's stated goal ("first live 12-vCPU operation").
* Imported survivors are already locked until 2026-07-13 — five months of slack
  to promote them on the VPS at the operator's pace.

---

## 8. Constraints honoured

* ✅ No code modified during this audit.
* ✅ No BI5 R3 work started.
* ✅ No Shadow Mode work started.
* ✅ No Phase 13 work started.
* ✅ No Phase 14 work started.
* ✅ No ASF Exporter work started.
* ✅ No deployment performed.
* ✅ Single output document (`ROADMAP_READINESS_AUDIT.md`) as requested.

---

**End of ROADMAP_READINESS_AUDIT.md.**
**Status: audit complete; ⚡ FASTEST path recommended. Awaiting operator GO on VPS provisioning.**
