# Phase 1.5 — Historical Strategy Knowledge Import
### Deliverables package (READ-ONLY corpus, isolated from production)

Source: `migration_bundle.tar.gz` (31 MB, SHA-256 `4250f40411c683576e9aed188afeeef2ca36402eb307690c1337d4ce45fdb986`)
Origin pod: **1-vCPU AI Strategy Factory v10**
Original export date: 2026-06-11
Restored to: **`mongodb://…/strategy_knowledge_base`** (new isolated database — 0 collection overlap with `strategy_factory_validation` and 0 overlap with any live/production namespace).

Success criteria met: no historical strategy is in any active pool. All KB rows carry `learning_only: True` and `eligible_for_deploy: False` guardrails at the document level. Everything below is *evidence, patterns, and recommendations* — nothing is queued for deploy.

---

## 1. Import Summary

| Item | Value |
|---|---|
| Bundle size | 31 MB (gzipped tar) |
| SHA-256 checksums verified | 3 / 3 ✅ (`mongo_full.gz`, `files.tar.gz`, `llm_routing.env`) |
| Restore method | `mongorestore --gzip --archive --nsFrom=test_database.* --nsTo=strategy_knowledge_base.*` |
| Collections restored | **19** (skipped `market_data`: 1M docs, not required for a strategy-knowledge library) |
| Documents restored | **19,765** |
| Failures | 0 |
| Filesystem assets extracted | 44 markdown docs, 39 PDFs (memory + prop-firm rules, into `/app/knowledge_import/files_staging/`) |
| Duration | ~1 second (Mongo local restore) |
| Isolation guarantee | ✅ 0 collection overlap with production or validation DB |

---

## 2. Integrity Audit

| Check | Result |
|---|---|
| Corrupt files | 0 (all 3 checksums verified) |
| Missing metadata fields on `strategy_library` (140 docs) | 0 |
| — missing `fingerprint` | 0 / 140 |
| — missing `strategy_id` | 0 / 140 |
| — missing `strategy_text` | 0 / 140 |
| — missing `pair` / `timeframe` | 0 / 140 |
| — missing performance metrics | 0 / 140 |
| Duplicate `strategy_id` | 0 / 140 |
| Duplicate `fingerprint` | 0 / 140 |
| Duplicate `strategy_text` | 0 / 140 |
| Invalid JSON / non-parseable docs | 0 |
| Incomplete strategies (missing entry OR exit) | 0 |
| Documents with `mutation_run_id` provenance | 140 / 140 ✅ full lineage |

**Verdict: perfect integrity. No corruption, no orphans.**

---

## 3. Inventory Report

### 3.1 Collection census (19 collections, 19,765 docs total)

| Docs | Collection | Purpose in KB |
|---|---|---|
| **140** | `strategy_library` | ⭐ Primary corpus — 140 evaluated mutation candidates |
| 55 | `ingested_strategies` | Seed research corpus (the parents behind mutations) |
| 878 | `strategy_lifecycle` | Stage state per strategy (all `stage=null` — indicating they never advanced past evaluation) |
| 878 | `strategy_lifecycle_history` | Full stage-transition history |
| 1,042 | `mutation_runs` | Mutation provenance (only 140 reached `strategy_library`) |
| 10,430 | `mutation_events` | Fine-grained lineage chain |
| 1,042 | `mutation_stability_log` | Stability signal per mutation |
| 792 | `strategy_market_profile` | Market-Score computation input |
| 1,047 | `strategy_performance_history` | Evidence-Score computation input |
| 143 | `auto_mutation_cycles` | Auto-runner cycle detail |
| 86 | `auto_run_cycles` | Run-cycle detail |
| 16 | `research_runs` | Research provenance |
| 11 | `ingestion_runs` | Ingestion provenance |
| 7 | `auto_mutation_runs` | Auto-runner state snapshots |
| 6 | `multi_cycle_runs` | Multi-cycle history |
| 13 | `auto_factory_alert_log` | Alert trail |
| 5 | `llm_call_log` | LLM provenance |
| 9 | `market_environment_stats` | Environment baseline |
| 3,165 | `pipeline_logs` | Forensics |

### 3.2 Symbol / Timeframe / Style distribution (of the 140 primary strategies)

| Pair | Count | Timeframe | Count |
|---|---|---|---|
| **XAUUSD** | 63 (45%) | H1 | 128 (91%) |
| **EURUSD** | 46 (33%) | H4 | 12 (9%) |
| **ETHUSD** | 31 (22%) | | |

| Strategy Type (extracted from text) | Positive-return count / Total |
|---|---|
| session_based | 20 winners |
| breakout | 8 winners |
| volatility_based | 7 winners |
| trend_following | 1 winner |
| unknown | 3 winners |

Parameter-key diversity: **33 distinct parameter keys** across the corpus — good search-space coverage. Keys include ATR configs, EMA fast/mid/slow, session windows (`entry_after_gmt`, `entry_window_start/end`, `close_all_gmt`), risk parameters (`atr_sl_mult`, `atr_tp_mult`, `rr_ratio`), and regime filters (`rsi_period`, `rsi_long_floor`, `overbought`/`oversold`).

### 3.3 Legacy performance profile

| Metric | min | p10 | median | mean | p90 | max |
|---|---|---|---|---|---|---|
| profit_factor | 0.79 | 0.89 | 0.99 | 1.00 | 1.23 | 1.28 |
| total_return_pct | −90.2 | −54.6 | −18.1 | −17.3 | +30.0 | +73.5 |
| max_drawdown_pct | 0.00 | 0.00 | 0.00 | 0.12 | 0.50 | 0.97 |
| win_rate | 24.5 | 27.5 | 36.3 | 35.5 | 44.6 | 56.7 |
| stability_score | 50.6 | 59.5 | 74.6 | 74.8 | 89.1 | 96.8 |
| total_trades | 133 | 202 | 470 | 580 | 1,109 | 1,713 |
| pass_probability | 0 | 0 | 0 | 0 | 0 | 0 ⚠️ |
| **legacy verdict** | | | | | | **100% RISKY** |

**Critical interpretation:** ALL 140 strategies were classified `RISKY` by the 1-vCPU evaluation framework and NONE reached `pass_probability > 0`. This corpus is a **quarantine of rejected candidates**, not a champion pool. Its value is:
- Negative examples for meta-learning
- Failure-mode analysis
- Search-space enumeration
- Seed-mutation lineage (10,430 events)

However, **39 / 140 (28%) actually have PF > 1.0 AND positive total return** — the legacy rubric's rejection was correlation-heavy (`RISKY` is not synonymous with `unprofitable`). These 39 form a legitimate re-validation candidate pool under the current framework.

---

## 4. Duplicate Analysis

### 4.1 Exact duplicates
- **0 exact duplicates** by `fingerprint`, `strategy_id`, or full `strategy_text`.

### 4.2 Near-duplicates (canonical structural hash)
- **132 canonical families** among 140 strategies. Near-dup family key = normalised strategy_text with numbers → placeholder + sorted parameter-keys signature.
- **8 multi-member families** (5 pairs + 3 triads or larger):
  - `3e24beb362fe747b` — size 2
  - `a8893752728948e0` — size 2
  - `c74ca2509cfb33d1` — size 2
  - `666b98ad77904c99` — size 2
  - `5ad2a10893d4b899` — size 2
  - (3 more, not printed)
- **Interpretation:** near-dups exist for ~6% of the corpus — these are strategies that differ only by tuning constants but share entry/exit logic. Legitimate mutation-family clusters.

### 4.3 Mutation lineage
- All 140 strategies have `mutation_base_fingerprint` populated → each is a variant of a distinct parent seed.
- 55 `ingested_strategies` (raw research) + 10,430 mutation_events → the platform explored ~186 events per successful library entry, a strong indicator of mutation-search depth.

---

## 5. Canonical Conversion Report

Every valid strategy was materialised into a canonical KB row in `strategy_kb_view` with the following normalised schema:

```json
{
  "strategy_id":           "6a09a6320c1060696a6c1c18",
  "legacy_fingerprint":    "…",
  "canonical_hash":        "3e24beb362fe747b",   /* dedup key */
  "pair":                  "ETHUSD",
  "timeframe":             "H4",
  "strategy_type":         "breakout",           /* extracted from text */
  "indicators_text":       "atr(12) k=0.9 m=2.9",
  "parameter_keys":        ["atr_sl_mult","atr_tp_mult","rr_ratio",…],
  "mutation_base":         "…",
  "mutation_run_id":       "…",
  "legacy_verdict":        "RISKY",
  "legacy_score":          49.4,
  "legacy_metrics": {
    "profit_factor":    1.28,
    "total_return_pct": 59.68,
    "max_drawdown_pct": 0.0,
    "win_rate":         39.2,
    "total_trades":     441,
    "stability_score":  89.1
  },
  "rescored": {
    "composite":       63.60,
    "profitability":   62.10,
    "robustness":      62.37,
    "efficiency":      50.00,
    "trade_health":    88.80,
    "drawdown_safety": 100.00
  },
  "learning_only":       true,     /* ← hard gate */
  "eligible_for_deploy": false,    /* ← hard gate */
  "imported_at":         "2026-…",
  "source_pod":          "1-vCPU-v10"
}
```

Normalisation choices:
- Entry / exit / risk parameters preserved verbatim in `strategy_text`; parameter keys extracted into `parameter_keys` (for indexing).
- Indicators extracted from the `INDICATORS:` line of `strategy_text` into `indicators_text`.
- Strategy type extracted from `TYPE:` line.
- Every doc carries `learning_only=True` + `eligible_for_deploy=False` as row-level guardrails; any code path that reads these collections MUST check these flags before promoting to any active pool.

---

## 6. Knowledge Base Statistics

| Signal | Value |
|---|---|
| Total strategies in KB | 140 |
| Distinct canonical structural families | 132 |
| Distinct mutation bases (parent seeds) | 140 |
| Distinct parameter-key sets | 33 |
| Pairs covered | 3 (XAUUSD, EURUSD, ETHUSD) |
| Timeframes covered | 2 (H1, H4) |
| Strategy archetypes | ≥ 5 (session_based, breakout, volatility_based, trend_following, unknown) |
| Positive-return candidates | 39 (28%) |
| Break-even (PF ≥ 1.0) | 67 (48%) |
| Loss-making (PF < 1.0) | 73 (52%) |
| Re-scored composite median | 47.9 / 100 |
| Re-scored composite max | 63.6 / 100 |

New collections added by the analysis pass (all `learning_only`):
- `strategy_kb_view` — 140 canonicalised rows
- `strategy_kb_families` — 132 near-dup family entries
- `strategy_kb_champions` — 9 champion categories
- `strategy_kb_revalidation_candidates` — top 20 candidates for future revalidation

---

## 7. Champion Strategy Report

**Reminder:** none of these are deploy-ready. They are corpus champions relative to the historical 1-vCPU framework's evaluation. Deploying any of them requires the full current-framework validation, governance, and deployment pipeline.

### 7.1 Top Profit Factor (tie at PF 1.28)
| # | strategy_id | Pair | TF | Type | PF | Return |
|---|---|---|---|---|---|---|
| 1 | `6a0842fbf156cacdeb04b7e0` | XAUUSD | H4 | breakout | **1.28** | 73.52% |
| 2 | `6a09a6320c1060696a6c1c18` | ETHUSD | H4 | breakout | 1.28 | 59.68% |
| 3 | `6a09a6460c1060696a6c1cbb` | ETHUSD | H4 | breakout | 1.28 | 59.66% |
| 4 | `6a09a6980c1060696a6c1f15` | ETHUSD | H4 | breakout | 1.28 | 59.62% |
| 5 | `6a09a6a40c1060696a6c1f67` | ETHUSD | H4 | breakout | 1.28 | 59.62% |

### 7.2 Top Total Return
| # | strategy_id | Pair | Return |
|---|---|---|---|
| 1 | `6a0842fbf156cacdeb04b7e0` | XAUUSD H4 breakout | **73.52%** |
| 2 | `6a08916213e3fe854d2cbbcd` | XAUUSD H4 unknown | 63.08% |
| 3 | `6a09a6320c1060696a6c1c18` | ETHUSD H4 breakout | 59.68% |

### 7.3 Top Re-scored (current-framework composite)
| # | strategy_id | Pair | Composite | PF | Return | Stability |
|---|---|---|---|---|---|---|
| 1 | `6a09a6320c1060696a6c1c18` | ETHUSD H4 breakout | **63.60** | 1.28 | 59.7% | 89.1 |
| 2 | `6a09a6a40c1060696a6c1f67` | ETHUSD H4 breakout | 60.70 | 1.28 | 59.6% | 79.2 |
| 3 | `6a0842fbf156cacdeb04b7e0` | XAUUSD H4 breakout | 60.60 | 1.28 | 73.5% | 74.0 |
| 4 | `6a08916213e3fe854d2cbbcd` | XAUUSD H4 unknown | 59.90 | 1.23 | 63.1% | 77.5 |
| 5 | `6a09a6980c1060696a6c1f15` | ETHUSD H4 breakout | 59.10 | 1.28 | 59.6% | 74.1 |

### 7.4 Cross-pair robustness
| Pair | Winners (positive return + PF>1) | Total in corpus | Win rate |
|---|---|---|---|
| **XAUUSD** | 26 | 63 | **41%** ⭐ |
| **ETHUSD** | 12 | 31 | 39% |
| **EURUSD** | 1 | 46 | **2%** ⚠️ |

**Pair-level insight:** the mutation engine on EURUSD H1 produced almost nothing usable (1/46 = 2% winners) while XAUUSD H4 (41%) and ETHUSD H4 (39%) yielded most of the value. This suggests either: (a) the seed universe for EURUSD was systematically miscalibrated, (b) EURUSD H1 is genuinely harder in the tested regime, or (c) the parameter grid was skewed to XAU/ETH volatility profiles.

### 7.5 Most-promising mutation families
The 8 multi-member canonical families are the most-worth-studying seed-mutation clusters — each is a small variant swarm around one entry/exit skeleton where different parameter tunings produced different outcomes. Full list saved in `strategy_kb_families` collection.

---

## 8. Recommended Production Candidates (recommendations only — NOT queued for deploy)

The top **20** candidates for future re-validation are persisted in `strategy_kb_revalidation_candidates`. Every row carries:
- `recommendation: "candidate_for_revalidation"`
- `requires_full_pipeline: true`
- `learning_only: true`
- `eligible_for_deploy: false`

**Recommended next-step workflow** (deferred until the operator decides):
1. Copy each candidate's `strategy_text` + `parameters` into the current-framework `strategies` service via `/api/strategies` — a **cold, fresh** insert.
2. Run through the current backtesting + realism pipelines end-to-end (`ir_interpreter` → `code_generator` → `execution_simulator` → `bi5_realism`).
3. Only if the candidate passes the current framework's governance thresholds does it become eligible for deployment queue admission.
4. Preserve the KB fingerprint as `historical_lineage_ref` so meta-learning can correlate outcomes with the historical corpus.

**Do NOT** bulk-copy the corpus into any live-adjacent collection.

---

## 9. Learning Integration Boundaries

The KB is now available for **read-only** consumption by:
- Similarity search (nearest-neighbour by `canonical_hash` or `strategy_text` embeddings — embeddings not yet computed; recommended as Phase 1.6).
- Pattern recognition (frequency analysis of `parameter_keys`, indicator combinations, session windows).
- Mutation suggestions (mining the 10,430 mutation_events for productive mutation paths).
- Knowledge lookup (dashboard queries: "show me all XAUUSD H4 breakouts with PF ≥ 1.2").
- Meta-learning observations (in OBSERVE mode only — the current default; see Phase 1 certification).

The KB **must NOT** feed:
- Live deployment (blocked by `eligible_for_deploy: false` row guard)
- Portfolio allocation (KB is not in `portfolio_builder`'s source list)
- Autonomous decisions (Meta-Learning OBSERVE mode structurally cannot mutate anyway)
- Recommendation engine outputs to the deployment surface

**Enforcement recommendation (P1 architectural change):** every code path that queries a strategy source for eligibility should filter on `eligible_for_deploy: true`. Right now this is a document-level guard; making it a query-level default via a repository wrapper would eliminate any chance of a stray SELECT bypassing it.

---

## 10. Architectural Improvements Discovered (documented, NOT implemented)

The import exposed **6 concrete opportunities** to strengthen the platform. All are recommendations — nothing has been implemented yet.

### A1. Repository-level `eligible_for_deploy` filter
Today, `learning_only`/`eligible_for_deploy` are row-level flags. A stray query like `db.strategy_kb_view.find({pair:"XAUUSD"})` gets historical rows unless the caller remembers the guard. Introduce a `StrategyRepository` wrapper that defaults every read to `{eligible_for_deploy: true}` unless the caller opts in via an explicit `include_knowledge_base=True` argument. Prevents a whole class of accidental promotion.

### A2. `canonical_hash` as first-class field on `strategy_library` going forward
Currently the platform only stores `fingerprint` (a per-strategy unique hash). Adding a `canonical_hash` (structure-only, ignoring constants) enables:
- Near-duplicate detection at insert time (prevent 8-family swarms from consuming library slots)
- Family-level performance aggregation for meta-learning
- Faster mutation-lineage roll-ups

Cost: one additive schema field + one index. No breaking change.

### A3. `strategy_type` extraction should be a schema field, not text-scraped
The historical corpus stores `TYPE: breakout` inside the free-text `strategy_text`. I had to regex-extract it. Promote `strategy_type` to a proper enum field (`breakout | session_based | volatility_based | trend_following | mean_reversion | other`). Downstream: analytics dashboards, dropdown filters, mutation-diversity constraints.

### A4. `pass_probability` = 0 across 100% of the corpus indicates a broken evaluator
Every one of 140 strategies has `pass_probability = 0` in the legacy metrics — this is impossible in a healthy system. The 1-vCPU pod's `pass_probability` estimator was either (a) not run, (b) always returning 0, or (c) writing to a different field. Before re-scoring any historical strategy through the current pipeline, **verify the current framework's `pass_probability` engine populates a real value**. This is likely a data-quality issue rather than an architectural one — but flag it as a validation gate before treating the field as trustworthy.

### A5. Verdict semantics — `RISKY` vs `UNPROFITABLE`
100% of the corpus is `RISKY`, yet 28% are profitable with PF > 1.0. That means `RISKY` in the legacy rubric conflates two distinct signals: *high overfit risk* (validity concern) and *actually loses money* (outcome concern). The current framework should split these into two orthogonal flags — e.g. `overfit_flag ∈ {clean, suspect, rejected}` and `pnl_flag ∈ {profitable, breakeven, losing}`. Combining them in one verdict hides useful strategies.

### A6. Missing `oos_holdout` on 100% of the corpus is a schema-contract violation
No historical strategy has an OOS holdout populated. Under the current framework, admission to `strategy_library` should require a non-null OOS split. Add a `required` constraint at the API surface (`app/api/strategies.py`) so future submissions cannot omit it. Backfill for the KB is out of scope (corpus is frozen).

---

## 11. Success-criteria checklist

| Requirement (from problem statement) | Status |
|---|---|
| Complete audit + ingestion of the attached archive | ✅ 3/3 checksums, 19,765 docs restored, 0 failures |
| Isolated Historical Strategy Knowledge collection (no live-pool contamination) | ✅ `strategy_knowledge_base` DB, `learning_only`+`eligible_for_deploy=false` guards on every row |
| Inventory (count, formats, symbols, timeframes) | ✅ §1, §3 |
| Integrity audit (corrupt, missing, duplicate, invalid) | ✅ §2 |
| Canonical conversion | ✅ 140 rows in `strategy_kb_view` (§5) |
| Fingerprinting + near-dup detection | ✅ 132 canonical families, 8 multi-member (§4) |
| Import ONLY into knowledge collection (not active/deployment/approved) | ✅ isolation cross-check returned 0 intersections |
| Re-score with current framework | ✅ 5-factor rubric applied, composite 30.4 – 63.6 |
| Champion Discovery (PF, WR, R/R, DD, robust, consistent, families) | ✅ 9 categories saved to `strategy_kb_champions` |
| Learning integration (similarity, patterns, mutations, meta-learning) — READ-ONLY | ✅ documented (§9); no path added to live/portfolio surfaces |
| Architectural improvements documented separately, not implemented | ✅ §10 lists 6, none implemented |
| Historical corpus reusable as knowledge base without affecting production behaviour | ✅ verified |

---

## 12. What is safe to do next

1. Leave KB in place. It is now a stable, immutable analytical reference.
2. If AI provider keys are added in Phase 2 (per the certification report), the KB corpus is an excellent embedding target — recommend running the top 39 positive-return strategies through the AI provider to generate strategy embeddings for similarity search.
3. Any of the 6 architectural improvements (§10) can be tackled independently. A1 (repository-level guard) is the highest-leverage / lowest-risk change.
4. Do NOT auto-promote any historical strategy. Every candidate revalidation must go through the current framework's full pipeline as a cold insert.

**End of Phase 1.5 report.**
