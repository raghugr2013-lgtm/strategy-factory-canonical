# POST_IMPORT_FEATURE_DEPENDENCY.md

**Audit type:** Dependency map for the 6-stage post-import pipeline (Profile → Score → Rank → Match → Portfolio → Master Bot).
**Purpose:** For each pipeline stage, enumerate every engine, UI surface, API endpoint, and MongoDB collection it depends on, and verify each dependency's parity class (A/B/C/D/E from `ROADMAP_PARITY_REPORT.md`). Final verdict: does any hidden / placeholder dependency block the pipeline?
**Status:** Read-only. No code modified. No imports performed. Pipeline has not run.
**Audience:** Operator (pre-import gate review) + future importer code.
**Sources cross-referenced:**

1. `ROADMAP_PARITY_REPORT.md` (18-surface classification)
2. `MISSING_OR_HIDDEN_FEATURES.md` (companion C/D inventory)
3. `POST_IMPORT_PIPELINE.md` (§2–§7 stage definitions)
4. `IMPORT_READINESS_REPORT.md` §2.5 (strategy identity model)
5. `MIGRATION_COMPATIBILITY_AUDIT.md` (fingerprint contract)
6. `MIGRATION_PRIORITY.md` (T1/T2/T3 tier policy)
7. `/app/backend/engines/{strategy_profiler,pass_probability,strategy_ranking_engine,phase4_matcher,portfolio_builder_engine,master_bot_engine,master_bot_ranker}.py`
8. `/app/backend/api/*.py` (router prefixes)
9. `/app/backend/.env` (feature-flag posture)

---

## 1. Dependency-class key (from `ROADMAP_PARITY_REPORT.md` §1)

| Code | Definition |
|---|---|
| **A** | Fully visible and operational |
| **B** | Visible but partial |
| **C** | Implemented but hidden (component or engine exists; not mounted in primary nav) |
| **D** | Placeholder only |
| **E** | Missing (no code, no surface) |

**Import-risk key:**

| Symbol | Meaning |
|---|---|
| 🟢 | No risk — dependency fully A-class |
| 🟡 | Low risk — dependency is C/D but operator-only-observability; pipeline runs without it |
| 🔴 | Hard blocker — dependency is C/D/E and the pipeline cannot complete without it |

---

## 2. Stage 1 — Re-Profile

**Engine:** `engines/strategy_profiler.py`
**Reads:** Every `strategy_library` doc with `provenance.source == "1vcpu_migration"` AND `stage == "IMPORTED_SEED"`.
**Writes:** `strategy_library.profiler.*`, `strategy_library.profiler.profiled_at`, `strategy_library.bi5_cert.coverage_pct`.

### 2.1 Required engines

| Engine | File | Class | Notes |
|---|---|---|---|
| Strategy Profiler | `engines/strategy_profiler.py` | A | Canonical |
| BI5 Maturity scorer | `engines/bi5_maturity.py` | A | Reads `bi5_ingest_log` |
| Market Universe Adapter | `engines/market_universe.py` + `market_universe_adapter` | A | DSR-3 ON; consumed by profiler |
| Strategy Library writer | `engines/strategy_library.py` | A | Idempotent upserts keyed by fingerprint |

### 2.2 Required UI surfaces

| Surface | Path | Class | Notes |
|---|---|---|---|
| Strategy Explorer (filter `stage=IMPORTED_SEED`) | `/c/explorer/explorer` | A | Operator inspects profiled rows |
| BI5 Health Panel | `/c/diag/bi5-health` | A | Operator verifies coverage before/after profile |
| Symbol Registry Panel (DSR) | `/c/governance/symbol-registry` | A | Operator confirms (pair) flag-enabled |
| Mission Control · Mission Briefing | `/c/dashboard/briefing` | A | Posture / ingestion KPI |
| Operator Inbox | global drawer | A | Surfaces `migration:stage_completed` events |

### 2.3 Required endpoints

| Endpoint | Used for | Class |
|---|---|---|
| `GET /api/strategies` | Explorer filter | A |
| `GET /api/diag/bi5/health` | BI5 panel | A |
| `GET /api/latent/market-universe` | DSR consultation | A |
| `GET /api/migration/post-import-pipeline/status/{run_id}` | New router — not yet written; queued | **E (planned)** |

### 2.4 Required collections

| Collection | Read / Write | Class |
|---|---|---|
| `strategy_library` | RW (write `profiler.*` + `bi5_cert.*`) | A |
| `bi5_ingest_log` | R (BI5 coverage) | A |
| `market_universe_symbols` | R (DSR enforcement) | A |
| `post_import_pipeline_log` | W (new, created at first run) | **E (planned — created on demand)** |
| `migration_checkpoints` | W (new, created at first run) | **E (planned — created on demand)** |

### 2.5 Dependency status

| Layer | Status |
|---|---|
| Engines | All A |
| UI | All A |
| Endpoints | 4 × A, 1 × E-planned (new pipeline router; ~30 LOC, queued for post-authorisation) |
| Collections | 3 × A, 2 × E-planned (auto-created at first pipeline run — non-blocking) |

**Import risk:** 🟢 None. The pipeline router is the only deferred deliverable and is intentionally held until operator authorisation per `POST_IMPORT_PIPELINE.md` §9 + `IMPORT_READINESS_REPORT.md` §2.6.

**Recommended remediation:** None at this stage. Write the pipeline router (~30 LOC) once the operator authorises post-import work; the two new collections will be created on the router's first write.

---

## 3. Stage 2 — Re-Score

**Engine:** `engines/pass_probability.py` (primary) + `engines/risk_of_ruin.py` (advisory) + `engines/lifecycle_decay.py` (advisory) + `engines/strategy_engine.py::extract_metrics` + `engines/master_bot_ranker.py` (deploy_score formula)
**Reads:** Profiled rows from Stage 1.
**Writes:** `strategy_library.pass_probability`, `strategy_library.risk_of_ruin`, `strategy_library.aging`, `strategy_library.deploy_score`, `strategy_library.validation_report.imported_revalidation`.

### 3.1 Required engines

| Engine | File | Class | Notes |
|---|---|---|---|
| Pass Probability scorer | `engines/pass_probability.py` | A | Canonical, used by Auto Factory |
| Risk-of-Ruin advisory | `engines/risk_of_ruin.py` | A | `RISK_OF_RUIN_WEIGHT=0.0` (advisory only) |
| Lifecycle Decay advisory | `engines/lifecycle_decay.py` | A | |
| Metrics extractor | `engines/strategy_engine.py::extract_metrics` | A | Canonical |
| Master Bot Ranker (deploy_score formula) | `engines/master_bot_ranker.py` | A | Composite formula |
| LLM bridge (Emergent integrations) | `emergentintegrations` package | **B** | Library present; `EMERGENT_LLM_KEY` ABSENT (see §3.5 risk) |

### 3.2 Required UI surfaces

| Surface | Path | Class | Notes |
|---|---|---|---|
| Strategy Score Reservation Card | `/c/explorer/score-rubric` | A | Operator-facing Quality/Evidence/Market/Trust scaffold |
| Strategy Explorer | `/c/explorer/explorer` | A | Re-scored rows visible |
| Mission Briefing — LLM budget chip | `/c/dashboard/briefing` | A | Operator monitors LLM spend |
| Operator Inbox | global drawer | A | Stage-completion events |

### 3.3 Required endpoints

| Endpoint | Used for | Class |
|---|---|---|
| `GET /api/strategies/{hash}` | Explorer detail | A |
| `POST /api/auto-factory/run` | NOT used directly by Stage 2 — but the readiness engine that gates it is the same one that gates Stage 2 LLM calls | A |
| LLM provider (`emergentintegrations`) | LLM-dependent re-score (optional) | **B** — gated by `EMERGENT_LLM_KEY` |

### 3.4 Required collections

| Collection | Read / Write | Class |
|---|---|---|
| `strategy_library` | RW | A |
| `validation_reports` | W (imported_revalidation entries) | A |
| `llm_call_log` | W (only if LLM-assisted re-score path) | A |

### 3.5 Dependency status

| Layer | Status |
|---|---|
| Engines | 5 × A, 1 × B (LLM bridge — key absent) |
| UI | All A |
| Endpoints | 2 × A, 1 × B (LLM-gated) |
| Collections | All A |

**Import risk:** 🟡 LOW — LLM key absence is documented in `IMPORT_READINESS_REPORT.md` §4 risk table (HIGH likelihood, mitigated by `llm_optional=true` mode).

**Recommended remediation:** Operator chooses ONE of:
- **Option A (recommended):** Set `EMERGENT_LLM_KEY` in `backend/.env` BEFORE Stage 2 starts. Re-score uses LLM for narrative quality cues (returns higher Evidence Score). Add credit via *Profile → Universal Key → Add Balance*.
- **Option B:** Run pipeline with `llm_optional=true`. Re-score falls back to heuristics-only (numeric Pass Probability + RoR + aging). Skip LLM-dependent quality cues; Evidence Score reserved as null pending LLM run.

Either path completes the stage; only the Evidence-Score depth differs.

---

## 4. Stage 3 — Re-Rank

**Engine:** `engines/strategy_ranking_engine.py` + `engines/ranking_engine.py`
**Reads:** Scored rows from Stage 2 across all (pair × timeframe × style) combos.
**Writes:** `strategy_library.rank.global`, `strategy_library.rank.per_cell`, `strategy_library.rank.computed_at`.

### 4.1 Required engines

| Engine | File | Class |
|---|---|---|
| Strategy Ranking Engine | `engines/strategy_ranking_engine.py` | A |
| Ranking Engine (cell-level) | `engines/ranking_engine.py` | A |

### 4.2 Required UI surfaces

| Surface | Path | Class |
|---|---|---|
| Strategy Explorer (sort by `rank.global` / `rank.per_cell`) | `/c/explorer/explorer` | A |
| Strategy Comparison | `/c/explorer/compare` | A |

### 4.3 Required endpoints

| Endpoint | Used for | Class |
|---|---|---|
| `GET /api/strategies?sort=rank.global` | Explorer sort | A |
| `GET /api/strategies/compare` | Comparison panel | A |

### 4.4 Required collections

| Collection | Read / Write | Class |
|---|---|---|
| `strategy_library` | RW (write `rank.*`) | A |

### 4.5 Dependency status

| Layer | Status |
|---|---|
| Engines | All A |
| UI | All A |
| Endpoints | All A |
| Collections | All A |

**Import risk:** 🟢 None.

**Recommended remediation:** None.

---

## 5. Stage 4 — Re-Match

**Engine:** `engines/phase4_matcher.py` + `engines/prop_firm_analysis.py` + `engines/challenge_matching_engine.py` + `engines/prop_firm_intelligence.py`
**Reads:** Top-ranked rows from Stage 3 (default top 100 per cell).
**Writes:** New collection `firm_match_imported`.

### 5.1 Required engines

| Engine | File | Class |
|---|---|---|
| Phase 4 Matcher | `engines/phase4_matcher.py` | A |
| Prop Firm Analysis | `engines/prop_firm_analysis.py` | A |
| Challenge Matching Engine | `engines/challenge_matching_engine.py` | A |
| Prop Firm Intelligence | `engines/prop_firm_intelligence.py` | A |
| Prop Firm Rules Review | `engines/prop_firm_rules_review.py` | A |

### 5.2 Required UI surfaces

| Surface | Path | Class | Notes |
|---|---|---|---|
| Prop Firms Admin | `/c/propfirm/admin` | A | Operator confirms current firm catalogue |
| Firm Match Panel | `/c/propfirm/match` | A | Surfaces firm-level matches |
| Rules Review | `/c/governance/rules` | A | Current firm rules consulted by matcher |
| Challenge Matching Panel | (orphan — `OperatorParityPanels.jsx::ChallengeMatchingPanel`) | **C** | Component exists, not mounted as section; reachable only via direct import |

### 5.3 Required endpoints

| Endpoint | Used for | Class |
|---|---|---|
| `GET /api/prop-firms` | Firm catalogue | A |
| `POST /api/match-firms-phase4` | Stage 4 dispatch | A |
| `POST /api/strategies/{hash}/match-challenges` | Challenge-template scoring | A |
| `GET /api/strategies/{hash}/challenge-match` | Challenge match read | A |
| `GET /api/challenge-matching/challenge-types` | Challenge template catalogue | A |
| `GET /api/challenge-matching/challenge-types/by-firm` | Firm → challenge template join | A |
| `GET /api/prop-firm-analysis/firms` | Firm analysis | A |
| `GET /api/prop-firm-intelligence/firms` | Firm intelligence | A |
| `GET /api/prop-firm-rules-review/*` | Rules review | A |

### 5.4 Required collections

| Collection | Read / Write | Class |
|---|---|---|
| `strategy_library` | R (top-ranked rows) | A |
| `prop_firms` | R (firm catalogue) | A |
| `prop_firm_rules` | R (current rule snapshot) | A |
| `firm_match_imported` | W (NEW — created at first run) | **E (planned — created on demand)** |

### 5.5 Dependency status

| Layer | Status |
|---|---|
| Engines | All A |
| UI | 3 × A · 1 × C (Challenge Matching Panel — observability only) |
| Endpoints | All A |
| Collections | 3 × A · 1 × E-planned (auto-created on first write) |

**Import risk:** 🟡 LOW — Challenge Matching Panel hidden means operator cannot drill into challenge-template detail without raw API calls. Pipeline itself completes via direct engine consumption.

**Recommended remediation:** Expose Challenge Matching Panel post-Stage-4 (P1 — `MISSING_OR_HIDDEN_FEATURES.md` §2.1, ~30 min mount). Without it, operator workflow:
- ✅ Pipeline still writes `firm_match_imported` correctly.
- ✅ `FirmMatchPanel` still shows firm-level matches.
- ❌ Operator must use Mongo shell or raw curl to inspect challenge-template breakdown until panel is exposed.

This is degraded UX, not a pipeline failure.

---

## 6. Stage 5 — Re-Portfolio

**Engine:** `engines/portfolio_builder_engine.py` + `engines/portfolio_combiner.py` + `engines/portfolio_intelligence_engine.py`
**Reads:** Top-ranked strategies (Stage 3) + firm matches (Stage 4).
**Writes:** New collection `portfolios_imported`.

### 6.1 Required engines

| Engine | File | Class |
|---|---|---|
| Portfolio Builder Engine | `engines/portfolio_builder_engine.py` | A |
| Portfolio Combiner | `engines/portfolio_combiner.py` | A |
| Portfolio Intelligence Engine | `engines/portfolio_intelligence_engine.py` | A |
| Anti-correlation Guardrails | (within `portfolio_builder_engine`) | A (dormant — see note below) |

**Note on anti-correlation:** `POST_IMPORT_PIPELINE.md` §6 marks this as "currently dormant." It is implemented inside the builder but not enabled by default. Operator-controlled — does not block pipeline.

### 6.2 Required UI surfaces

| Surface | Path | Class |
|---|---|---|
| Portfolio Builder | `/c/portfolio/builder` | A |
| Portfolio Panel | `/c/portfolio/panel` | A |
| Portfolio Intelligence | `/c/portfolio/intel` | A |
| Phase 14 Dual Scorecard reservation | `/c/portfolio/scorecards-reservations` | A (reservation card; live) |

### 6.3 Required endpoints

| Endpoint | Used for | Class |
|---|---|---|
| `GET /api/portfolio-builder/*` | Builder list/detail | A |
| `POST /api/portfolio-builder/build` | Re-portfolio dispatch | A |
| `GET /api/portfolio/*` | Live portfolios | A |
| `GET /api/portfolio-intelligence/*` | Intelligence summary | A |

### 6.4 Required collections

| Collection | Read / Write | Class |
|---|---|---|
| `strategy_library` | R (top-ranked) | A |
| `firm_match_imported` | R (Stage 4 output) | E-planned (created in Stage 4) |
| `portfolios` | R (existing portfolios for anti-correlation check) | A |
| `portfolios_imported` | W (NEW) | **E (planned — created on demand)** |

### 6.5 Dependency status

| Layer | Status |
|---|---|
| Engines | All A |
| UI | All A |
| Endpoints | All A |
| Collections | 2 × A · 2 × E-planned |

**Import risk:** 🟢 None. Both new collections are auto-created.

**Recommended remediation:** None at the pipeline level. **Optional**: operator may toggle anti-correlation guardrails ON before Stage 5 to enforce diversification on imported portfolios — flag-gated, off by default.

---

## 7. Stage 6 — Re-Masterbot

**Engine:** `engines/master_bot_engine.py` + `engines/master_bot_definition.py` + `engines/master_bot_ranker.py` (+ 5 other `master_bot_*.py` modules)
**Reads:** Stage 5 portfolio candidates.
**Writes:** New collection `master_bot_imported_candidates`.

### 7.1 Required engines

| Engine | File | Class |
|---|---|---|
| Master Bot Engine | `engines/master_bot_engine.py` | A |
| Master Bot Definition | `engines/master_bot_definition.py` | A |
| Master Bot Ranker | `engines/master_bot_ranker.py` | A |
| Master Bot Composer | `engines/master_bot_composer.py` | A |
| Master Bot Compiler | `engines/master_bot_compiler.py` | A |
| Master Bot Runtime | `engines/master_bot_runtime.py` | A |
| Master Bot Signer | `engines/master_bot_signer.py` | A |

### 7.2 Required UI surfaces

| Surface | Path | Class |
|---|---|---|
| Master Bot Dashboard | `/c/mutate/master-bot` | A |
| Master Bot Compile | `/c/mutate/master-bot-compile` | A |

### 7.3 Required endpoints

| Endpoint | Used for | Class |
|---|---|---|
| `GET /api/master-bot/runners` | Runner list | A |
| `POST /api/master-bot/compile` | Compile-on-demand | A |
| `GET /api/master-bot/definitions` | MB definition list | A |

### 7.4 Required collections

| Collection | Read / Write | Class |
|---|---|---|
| `portfolios_imported` | R (Stage 5 output) | E-planned (created in Stage 5) |
| `master_bots` | R (existing MBs for duplicate detection) | A |
| `master_bot_imported_candidates` | W (NEW) | **E (planned — created on demand)** |

### 7.5 Dependency status

| Layer | Status |
|---|---|
| Engines | All A |
| UI | All A |
| Endpoints | All A |
| Collections | 1 × A · 2 × E-planned |

**Import risk:** 🟢 None.

**Recommended remediation:** None.

---

## 8. Operator-only post-pipeline deployment gate

After Stage 6, **NO** imported artefact is auto-deployed. The operator promotes via existing UI flows (per `POST_IMPORT_PIPELINE.md` §8):

| Surface | Operator action | Effect |
|---|---|---|
| `/c/explorer/explorer` (filter `stage=IMPORTED_SEED`) | Click `Promote` on a strategy | `stage="PROVISIONAL"` |
| `/c/portfolio/builder` (filter `provenance.source=1vcpu_post_import`) | Click `Promote to Active` | Moves to `portfolios` |
| `/c/mutate/master-bot` (filter `provenance.source=1vcpu_post_import`) | Click `Compile` → `Deploy` | Adds to runner pool |

### 8.1 Required guard

| Guard | File | Status | Class |
|---|---|---|---|
| Auto-Selection 5-line guard (refuses to deploy `stage="IMPORTED_SEED"` while `stage_locked_until` is in the future) | `engines/auto_selection_engine.py` | NOT YET WRITTEN | **E (planned — ~5 LOC, queued for post-authorisation)** |

**Import risk:** 🔴 Hard blocker for *automated deployment safety* (not for the import itself). Without this guard, Auto-Selection could theoretically attempt to auto-deploy a freshly-imported `IMPORTED_SEED` row. The risk is mitigated by `stage_locked_until=ISO_date(+30 days)` per `MIGRATION_PRIORITY.md` §1 — but the guard is the belt-and-braces enforcement.

**Recommended remediation:** Write the 5-line guard at the moment operator authorises import (per `IMPORT_READINESS_REPORT.md` §6 Item 6). It MUST land **before** Auto-Selection is allowed to run against the imported set.

---

## 9. Global dependency roll-up

| Stage | Engines | UI | Endpoints | Collections | Overall risk |
|---|---|---|---|---|---|
| 1 · Re-Profile | ✅ all A | ✅ all A | ✅ A + 1 E-planned (pipeline router) | ✅ A + 2 E-planned | 🟢 |
| 2 · Re-Score | ✅ A + 1 B (LLM bridge) | ✅ all A | ✅ A + 1 B (LLM-gated) | ✅ all A | 🟡 (LLM optional) |
| 3 · Re-Rank | ✅ all A | ✅ all A | ✅ all A | ✅ all A | 🟢 |
| 4 · Re-Match | ✅ all A | ✅ A + 1 C (Challenge panel) | ✅ all A | ✅ A + 1 E-planned | 🟡 (observability only) |
| 5 · Re-Portfolio | ✅ all A | ✅ all A | ✅ all A | ✅ A + 2 E-planned | 🟢 |
| 6 · Re-Masterbot | ✅ all A | ✅ all A | ✅ all A | ✅ A + 2 E-planned | 🟢 |
| **Deployment Gate** | — | — | — | — | 🔴 *for safety* — guard must be written before Auto-Selection runs against imported set |

**Summary:**

* **Hard blockers:** 0 for the pipeline itself; 1 for the deployment guard (5 LOC, queued).
* **Soft blockers (degraded UX):** 1 — Challenge Matching panel hidden.
* **Operator-choice friction:** 1 — LLM key absence forces `llm_optional=true` or operator funds the universal key.
* **All E-planned items** are intentionally deferred: new collections auto-create on first write, the pipeline router (~30 LOC) is held until authorisation, and the 5-line guard is the same.

---

## 10. Final verdict

**No hidden (Class C), placeholder (Class D), or missing (Class E) surface blocks the 6-stage post-import pipeline from running end-to-end.**

The 7 hidden/orphan items catalogued in `MISSING_OR_HIDDEN_FEATURES.md` impact the **post-pipeline operator workflow** (drill-into-challenge detail, Factory Supervisor activation, Auto Learning loop) but not the pipeline execution itself. Every engine, endpoint, and operator-visible surface required for Stages 1–6 is Class A.

The 3 small code deliverables intentionally deferred:

1. `/api/migration/post-import-pipeline/*` router (~30 LOC)
2. `engines/auto_selection_engine.py` 5-line guard
3. Importer code itself (~150 LOC)

…are exactly the items called out in `IMPORT_READINESS_REPORT.md` §2.6 and `POST_IMPORT_PIPELINE.md` §9. None of them requires new surface work; all are pure backend implementations.

**Recommendation:** the post-import pipeline is dependency-green. Operator may proceed when ready by:

1. (Optional) Set `EMERGENT_LLM_KEY` and seed BI5 backfill for richest re-score.
2. Deliver export package to `/app/_migration_inbox/`.
3. Authorise the 3 small code deliverables (~185 LOC total).
4. Run the importer (tiered T3 → T2 → T1) then the 6-stage pipeline.
5. (Post-pipeline) authorise the P1 visibility recoveries from `MISSING_OR_HIDDEN_FEATURES.md` (~5 h spread across P1/P2/P3).

---

## 11. State of this document

* No code modified.
* No imports performed.
* Companion to `ROADMAP_PARITY_REPORT.md` + `MISSING_OR_HIDDEN_FEATURES.md`.
* Pipeline still gated awaiting operator authorisation per locked sequence.

**End of report.**
