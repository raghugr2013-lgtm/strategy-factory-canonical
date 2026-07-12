# POST_IMPORT_PIPELINE.md

**Purpose:** Define the deterministic 6-stage processing pipeline that runs against the 1-vCPU imported strategies after they land in `strategy_library` as `IMPORTED_SEED`.
**Status:** Plan only. Pipeline has not run.
**Triggers:** Manually, after `IMPORT_READINESS_REPORT.md` is green AND tiered import (`MIGRATION_PRIORITY.md`) has completed.
**Per operator directive:** *"Imported strategies are reference intelligence — not deployable."* This pipeline transforms them into evidence-backed candidates that the operator can then optionally promote to deployment.

---

## 1. Pipeline overview

```
       ┌─ Stage 1 · Re-Profile     (canonical profiler over current market data)
       │
       ├─ Stage 2 · Re-Score       (Pass Probability + RoR + aging + stability)
       │
       ├─ Stage 3 · Re-Rank        (canonical ranking engine)
       │
       ├─ Stage 4 · Re-Match       (Phase 4 firm matcher vs current prop firm catalogue)
       │
       ├─ Stage 5 · Re-Portfolio   (portfolio builder over re-ranked T1)
       │
       └─ Stage 6 · Re-Masterbot   (Master Bot composer over re-ranked portfolios)
```

Each stage:
* reads from canonical Mongo collections
* writes to canonical Mongo collections
* logs to `post_import_pipeline_log` (new collection at first run)
* updates `provenance.requires_revalidation`/`requires_rematching` flags on the imported strategies
* checkpoints to `migration_checkpoints` so the pipeline can resume from any stage

---

## 2. Stage 1 — Re-Profile

**Engine:** `engines/strategy_profiler.py`
**Reads:** Every `strategy_library` doc with `provenance.source == "1vcpu_migration"` AND `stage == "IMPORTED_SEED"`.
**Writes:**
* `strategy_library.profiler.*` — current-market-data signature
* `strategy_library.profiler.profiled_at` — timestamp
* `strategy_library.bi5_cert.coverage_pct` — recomputed from current BI5 store

**Pre-conditions:**
* Market data for the (pair, timeframe) is present (operator runs `python -m scripts.bi5_one_shot_backfill` first if needed).
* DSR registry has the (pair) flag-enabled.

**Idempotency:** safe to re-run; overwrites only `profiler.*` and `bi5_cert.*` fields.

**Estimated cost (12-vCPU pod):**
* ~1 s per strategy single-threaded
* Activate `ENABLE_PROCESS_POOL_BACKTEST=true` + `USE_PROCESS_POOL=true` for >500 strategies → ~150 ms/strategy on 10 workers
* 500 strategies → ~75 s with pool ON

**Outcome:** Imported strategies now have current-market profile attached. Any strategy whose profile can't be computed (no data) flagged `profile_failed=true` and skipped from subsequent stages.

---

## 3. Stage 2 — Re-Score

**Engine:** `engines/pass_probability.py` + `engines/risk_of_ruin.py` (advisory) + `engines/lifecycle_decay.py` (advisory) + `engines/strategy_engine.py::extract_metrics`

**Reads:** Profiled rows from Stage 1.
**Writes (all on the same doc):**
* `pass_probability` — float 0..1
* `risk_of_ruin` — float (computed; weight gated by `RISK_OF_RUIN_WEIGHT=0.0` so deploy_score is unaffected)
* `aging` — dict with decay metrics
* `deploy_score` — composite (Pass Probability + market signature + stability) per `engines/master_bot_ranker.py` formula
* `validation_report.imported_revalidation` — fresh validation summary

**Idempotency:** safe to re-run.

**Estimated cost:** ~500 ms per strategy. 500 strategies → ~4 min.

**Outcome:** Each imported strategy now has a fresh score computed against current data + current firm rules. The original 1-vCPU `metrics` block is preserved as `legacy_attributes.metrics` for evidence.

---

## 4. Stage 3 — Re-Rank

**Engine:** `engines/strategy_ranking_engine.py` + `engines/ranking_engine.py`

**Reads:** Scored rows from Stage 2 across all (pair × timeframe × style) combos.
**Writes:**
* `strategy_library.rank.global` — global rank within imported set
* `strategy_library.rank.per_cell` — rank within (pair × timeframe × style) cell
* `strategy_library.rank.computed_at` — timestamp

**Idempotency:** safe to re-run.

**Estimated cost:** O(N log N) sort + index updates. 500 strategies → ~5 s.

**Outcome:** Operator can browse the imported set ordered by current-pod merit.

---

## 5. Stage 4 — Re-Match

**Engine:** `engines/phase4_matcher.py` + `engines/prop_firm_analysis.py` + `engines/challenge_matching_engine.py`

**Reads:** Top-ranked rows from Stage 3 (operator-controllable threshold; default top 100 per cell).
**Writes:**
* `firm_match_imported` — new collection of `{strategy_fingerprint, firm_id, challenge_template, pass_probability, ...}` rows
* `strategy_library.provenance.requires_rematching` → flipped to `false`

**Pre-conditions:**
* Prop Firm catalogue is current (operator confirms `/c/propfirm/admin` shows expected firms).

**Idempotency:** safe to re-run; old matches replaced.

**Estimated cost:** ~200 ms per (strategy × firm) pair. 100 strategies × 10 firms = ~3 min.

**Outcome:** Each top imported strategy has a list of compatible prop-firm challenges with pass-probability estimates against the **current** firm rule set.

---

## 6. Stage 5 — Re-Portfolio

**Engine:** `engines/portfolio_builder_engine.py` + `engines/portfolio_combiner.py` + `engines/portfolio_intelligence_engine.py`

**Reads:**
* Top-ranked imported strategies (Stage 3)
* Firm matches (Stage 4)
* Anti-correlation guardrails (currently dormant — see flag)

**Writes:**
* `portfolios_imported` — new collection of candidate portfolios
* Each portfolio doc carries `provenance.source = "1vcpu_post_import"` and `provenance.requires_operator_review = true`

**Idempotency:** safe to re-run; previous candidates retained with `superseded=true` flag.

**Pre-conditions:** Stage 4 completed.

**Estimated cost:** O(N²) combinatorial — capped at top 100 strategies → ~30 s.

**Outcome:** Portfolio Builder (`/c/portfolio/builder`) shows fresh, evidence-backed portfolio candidates with the imported survivors as components. Operator can promote one to live `portfolios` collection via the existing UI.

---

## 7. Stage 6 — Re-Masterbot

**Engine:** `engines/master_bot_engine.py` + `engines/master_bot_definition.py` + `engines/master_bot_ranker.py`

**Reads:** Stage 5 portfolio candidates.
**Writes:**
* `master_bot_imported_candidates` — new collection of Master Bot definitions
* Each MB candidate carries `provenance.source = "1vcpu_post_import"` and `provenance.requires_operator_review = true`

**Pre-conditions:** Stage 5 completed.

**Estimated cost:** ~5 s per Master Bot candidate. Caps at top 10 portfolios → ~50 s.

**Outcome:** Master Bot Dashboard (`/c/mutate/master-bot`) shows imported-derived MB candidates that the operator can compile + deploy via the existing UI.

---

## 8. The deployment gate (operator-only)

After Stage 6 finishes, NONE of the imported strategies/portfolios/master-bots are auto-promoted. The operator promotes each via the existing flows:

| Surface | Operator action | Effect |
|---|---|---|
| `/c/explorer/explorer` filter `stage=IMPORTED_SEED` | review individual strategy | `Promote` button → `stage="PROVISIONAL"` |
| `/c/portfolio/builder` filter `provenance.source=1vcpu_post_import` | review candidate portfolio | `Promote to Active` |
| `/c/mutate/master-bot` filter `provenance.source=1vcpu_post_import` | review candidate Master Bot | `Compile` then `Deploy` |

The `engines/auto_selection_engine.py` 5-line guard ensures Auto-Selection never auto-deploys these candidates while the locks are in place.

---

## 9. Execution interface

The pipeline is exposed at `/api/migration/post-import-pipeline/*` (new router, ~30 LOC, queued for implementation when the operator authorises the import) with these endpoints:

```
POST /api/migration/post-import-pipeline/start
  body: { stages: ["all"] | ["profile","score","rank","match","portfolio","masterbot"] }
  → returns run_id

GET  /api/migration/post-import-pipeline/status/{run_id}
  → returns per-stage progress + counters + last error

POST /api/migration/post-import-pipeline/pause/{run_id}
POST /api/migration/post-import-pipeline/resume/{run_id}
POST /api/migration/post-import-pipeline/abort/{run_id}
```

UI surface: a new section `governance/post-import` (mounted as part of the post-import authorisation task, not as part of P1 recovery).

---

## 10. Observability

Every stage writes:
* `post_import_pipeline_log` — append-only structured rows
* `migration_checkpoints` — single row per stage with state

The pipeline emits `audit_log` entries at every stage transition so the activation-timeline endpoint (`/api/latent/activation-timeline`) captures the operator's migration window for posterity.

The existing **Notification Drawer** + **Operator Inbox** surfaces will receive `migration:stage_completed` events (rendered as advisory rows) — no new UI required.

---

## 11. Failure handling

| Failure | Behaviour |
|---|---|
| Stage 1 fails for a single strategy (e.g. missing market data) | Strategy flagged `profile_failed=true`; pipeline continues. |
| Stage 1 fails for >50% of strategies | Pipeline auto-pauses; operator alerted to run BI5 backfill before resuming. |
| LLM quota exceeded mid-stage 2 | Pipeline pauses; operator tops up `EMERGENT_LLM_KEY`; resume from checkpoint. |
| Stage 4 finds no matching firms | Pipeline completes Stage 4 with `matches=0` and continues to Stage 5; operator decides. |
| Mongo write failure | Stage aborts with backoff; operator inspects `post_import_pipeline_log` last row; manual resume. |

All failures are non-destructive — no canonical row is modified in-place.

---

## 12. Total pipeline ETA (500 strategies, single-threaded)

| Stage | Time |
|---|---|
| 1 · Re-Profile | ~8 min |
| 2 · Re-Score | ~4 min |
| 3 · Re-Rank | ~5 s |
| 4 · Re-Match | ~3 min |
| 5 · Re-Portfolio | ~30 s |
| 6 · Re-Masterbot | ~50 s |
| **TOTAL** | **~17 min** |

With `USE_PROCESS_POOL=true` + `ENABLE_PROCESS_POOL_BACKTEST=true` + `ENABLE_PROCESS_POOL_MUTATION=true` on the 12-vCPU pod, total drops to ~5 min.

---

## 13. Status

* Plan only.
* Awaits authorisation gate: `IMPORT_READINESS_REPORT.md` green → operator drops export → `MIGRATION_PRIORITY.md` tiered import completes → operator authorises pipeline start.
* No code has been written or executed.
