# MIGRATION COMPATIBILITY AUDIT
**Source deployment:** 1-vCPU AI Strategy Factory v10 (this pod)
**Target deployment:** 12-vCPU (newer architecture: Master Bot, Marketplace, Factory Supervisor, 4-axis scoring)
**Date:** 2026-02 (pre-migration)
**Discipline:** Read-only audit. No mutations. No exports yet. No code changes.

---

## 0. EXECUTIVE SUMMARY

The 1-vCPU deployment contains **substantive, irreplaceable strategy intelligence**:
- 140 validated strategies in `strategy_library` (complete with decisions, fingerprints, validation reports, prop firm panels, pass_probability)
- 878 lifecycle records + 878 history transitions (8-stage governance state)
- 1,042 mutation runs / 10,430 mutation events / 1,042 stability snapshots
- 55 ingested strategies + 11 ingestion runs
- 1,053,512 market_data rows (192 MB, BID 1m + BI5 streams)
- Governance Universe config, orchestrator priorities, prop-firm rule snapshots

The deployment **does NOT contain** the newer subsystems present on the 12-vCPU pod (Master Bot, Marketplace, Factory Supervisor, Strategy Dossier, Evidence/Market/Trust scoring). Their data must be **regenerated post-import**, not migrated.

**Risk classification:**
- Tier 1 (must migrate): strategy_library, strategy_lifecycle*, mutation_*, ingested_strategies, governance_universe, market_data, users, prop_firm_rules, challenge_rules
- Tier 2 (strongly recommended): research_runs, multi_cycle_runs, auto_mutation_*, auto_run_cycles, strategy_market_profile, market_environment_stats, strategy_performance_history, orchestrator_env_priority, pipeline_logs, llm_call_log, auto_factory_alert_log, prop_firm_pdfs/
- Tier 3 (can rebuild): auto_scheduler_config, orchestrator_scheduler_config, mutation_stability_log (derivable from mutation_runs)

---

## 1. SUBSYSTEM COMPATIBILITY MATRIX

Compatibility verdicts assume the target 12-vCPU codebase is a *superset* that adds Master Bot, Marketplace, Factory Supervisor, Pass Probability v2, Quality/Evidence/Market/Trust scoring, and Prop Firm Matching v2. Any field absent on the source side requires recomputation (see §3) — not blockers.

| # | Subsystem | Verdict | Reason |
|---|---|---|---|
| 1 | **Quality Score** | Requires recomputation | `ingested_strategies.quality_score` exists but is an ingestion-time heuristic. Newer system uses a richer post-validation Quality Score (multi-signal). Recompute from `strategy_library` survivors. |
| 2 | **Evidence Score** | Requires full regeneration | No `evidence_score` field anywhere on source. The lifecycle `evidence` blob carries raw counters only; the newer composite must be computed from history. |
| 3 | **Market Score** | Requires partial recomputation | `market_environment_stats` + `strategy_market_profile` provide raw inputs. Newer Market Score formula must be applied post-import. |
| 4 | **Trust Score** | Requires full regeneration | No `trust_score` field. Newer scoring needs deploy_score history, OOS evidence and stability — present in source but never combined. |
| 5 | **Pass Probability** | Compatible as-is (v1) | `strategy_library.pass_probability` is populated. If target uses v2 (per-firm), recompute per firm using `prop_firm_rules` snapshots after import. |
| 6 | **Portfolio Builder** | Requires full regeneration | Engine exists (`portfolio_builder_engine.py`) but `portfolio_builder_runs` collection is empty (0 docs). Must rebuild from survivors. |
| 7 | **Master Bot Builder** | Requires full regeneration | No master-bot artifacts on source. Generate from elite survivors post-import. |
| 8 | **Prop Firm Matching** | Requires recomputation | `prop_firm_rules` (3 firms) snapshots are migratable. Per-strategy `strategy_pass_analysis` / `strategy_risk_profile` / `strategy_challenge_match` are empty on source. Re-match after import using imported `strategy_library`. |
| 9 | **Marketplace** | Requires full regeneration | No marketplace_listings or readiness flags. Derive from survivors that pass Master Bot gate. |
| 10 | **Strategy Dossier** | Requires full regeneration | No `strategy_dossier` collection. Composable from existing fields once Evidence/Market/Trust are computed. |
| 11 | **Factory Supervisor** | Requires full regeneration | Source uses single-authority `ai_orchestrator` (G2). No supervisor records. Start fresh on target. |
| 12 | **Auto Selection** | Compatible after recomputation | `auto_selection_runs` empty on source. Use imported `strategy_lifecycle` + survivor pool to seed. |

---

## 2. SCHEMA COMPATIBILITY (per-field deltas)

### 2.1 `strategy_library` (140 docs) — TIER 1
**Present fields (source):**
`pair, timeframe, style, strategy_text, parameters, score, verdict, prop_status, pass_probability, stability_score, max_drawdown_pct, daily_drawdown_pct, profit_factor, total_return_pct, win_rate, total_trades, winning_trades, losing_trades, avg_win_usd, avg_loss_usd, avg_win_pips, avg_loss_pips, consistency_score, confidence, reason, recommendation, expected_value, oos_holdout, fingerprint, source, force_saved, validation_report, decision, prop_firm_panel, created_at, strategy_id, mutation_base_fingerprint, mutation_run_id, mutation_type, mutation_variant_fingerprint`

**Likely-missing on target import (newer fields):**
- `quality_score_v2` (recompute)
- `evidence_score` (recompute from lifecycle.evidence + history)
- `market_score` (recompute from market_environment_stats)
- `trust_score` (composite of deploy_score history + OOS + stability)
- `dossier_id` (post-pipeline)
- `master_bot_id` (post-pipeline)
- `marketplace_status` (post-pipeline)

**Migration plan:** Import as-is. New fields populated by §POST_IMPORT_PIPELINE.

### 2.2 `strategy_lifecycle` (878 docs) — TIER 1
**Present:** `strategy_hash, cool_down_until, current_stage, current_stage_since, evidence, flags, last_evaluated_at, library_id, research_run_id, stage_rank`

**Required by target (likely-new):**
- `deploy_score` (probably re-derived from history)
- `evidence_score` (recompute)
- `trust_score` (recompute)
- `supervisor_state` (Factory Supervisor)

**Migration plan:** Import all 878. Recompute composites.

### 2.3 `mutation_runs` (1,042 docs) — TIER 1
**Present:** `status, run_id, triggered_by, started_at, finished_at, runtime_sec, pair, timeframe, style, price_source, data_points, base_fingerprint, totals, best_variant, variants, auto_save, auto_save_result, evolution`

**Compatible as-is.** Newer Mutation Engine adds `idempotency_key` and `optimistic_version` (current 409 issue mitigation), but they are not retroactively required.

### 2.4 `ingested_strategies` (55 docs) — TIER 1
**Present:** `run_id, created_at, source, url, name, type, indicators, entry_logic, exit_logic, risk_model, timeframe, pair, confidence, quality_score, status, reason, raw_code_preview, injection`

**Compatible as-is.** `quality_score` here is the ingestion-time heuristic; newer Quality Score v2 is computed post-validation against `strategy_library`.

### 2.5 `governance_universe` (1 doc) — TIER 1
**Present:** `pairs, timeframes, styles, exploration_floor_pct, max_active_cells, breadth_vs_depth, updated_at, updated_by, audit_log, phase`

**Migration plan:** Import as authoritative seed. Operator may override on target.

### 2.6 `market_data` (1,053,512 docs / 192 MB / 58 MB on-disk) — TIER 1
**Present:** `symbol, source ∈ {bid_1m, bi5}, timeframe, timestamp, open, high, low, close, volume`

**Compatible as-is.** Schema is canonical. Indexes on `(symbol, source, timeframe, timestamp)` must be rebuilt on target.

### 2.7 `prop_firm_rules` (3 docs) — TIER 1
**Present:** firm rule snapshots with confidence + auto_approved flags.

**Compatible.** Per-strategy outputs (`strategy_pass_analysis`, `strategy_risk_profile`, `strategy_challenge_match`) are empty on source → re-match after import.

### 2.8 `mutation_events` (10,430 docs) / `mutation_stability_log` (1,042 docs) — TIER 2
**Present and compatible.** Provides multi-generation lineage useful for evolution analytics and the newer Evidence Score input. `mutation_stability_log` is derivable from `mutation_runs` but importing is cheaper than recomputing.

### 2.9 `research_runs` (16) / `multi_cycle_runs` (6) / `auto_mutation_runs` (7) / `auto_mutation_cycles` (143) / `auto_run_cycles` (86) — TIER 2
**Compatible.** Provide orchestration provenance. Useful for new Factory Supervisor backfill.

### 2.10 `strategy_market_profile` (792 docs) / `market_environment_stats` (9 docs) / `strategy_performance_history` (1,047 docs) — TIER 2
**Compatible.** Direct inputs to the newer Market Score / Trust Score computations.

### 2.11 `pipeline_logs` (3,165 docs) — TIER 2 (operational only)
**Compatible.** Not strategy intelligence; useful for forensics.

### 2.12 `users` (1 doc) — TIER 1
Admin seed account. Import (or re-seed via target deploy).

### 2.13 `challenge_rules` (3 docs) — TIER 1
Per-firm parsed challenge schemas. Compatible.

### 2.14 `llm_call_log` (5 docs) / `auto_factory_alert_log` (13 docs) — TIER 2 (audit trail)
Small; compatible.

### 2.15 `orchestrator_env_priority` (2 docs) — TIER 2
Knob state used by the env-priority scheduler. Compatible.

### 2.16 `auto_scheduler_config`, `orchestrator_scheduler_config` — TIER 3
Reconfigurable on target; rebuilding is trivial.

---

## 3. RECOMPUTATION DEPENDENCY GRAPH

The 12-vCPU pipeline depends on data that must exist *before* a higher-tier subsystem can run:

```
market_data                                  (Tier 1, import)
  └── strategy_market_profile/env_stats      (Tier 2, import)
        └── Market Score                     (recompute)

strategy_library                             (Tier 1, import)
  ├── lifecycle + lifecycle_history          (Tier 1, import)
  │     ├── Evidence Score                   (recompute)
  │     └── Trust Score                      (recompute)
  ├── mutation_runs + mutation_events        (Tier 1/2, import)
  │     └── Quality Score v2                 (recompute)
  ├── prop_firm_rules                        (Tier 1, import)
  │     ├── strategy_pass_analysis           (recompute)
  │     ├── strategy_risk_profile            (recompute)
  │     └── strategy_challenge_match         (recompute)
  ├── Pass Probability v2                    (recompute per firm)
  ├── Strategy Dossier                       (compose)
  ├── Portfolio Builder                      (regenerate)
  │     └── Master Bot Builder               (regenerate)
  │           └── Marketplace listings       (regenerate)
  └── Factory Supervisor state               (start fresh)
```

No subsystem requires source-deployment data that is missing — the pipeline is fully reconstitutable.

---

## 4. ID & FINGERPRINT CONTINUITY

All migrated strategies preserve:
- `strategy_id` (UUID)
- `fingerprint` (canonical hash) — primary join key
- `mutation_base_fingerprint`, `mutation_variant_fingerprint` — lineage chain
- `strategy_hash` (lifecycle index) — references `library_id`

**Verdict:** Identity continuity is intact across collections. No re-hash required if Mongo `_id` policy on target tolerates upsert-on-fingerprint (it does — `strategy_memory.py` upserts by `fingerprint`).

---

## 5. INDEXES TO REBUILD ON TARGET

| Collection | Required index | Rationale |
|---|---|---|
| market_data | `(symbol, source, timeframe, timestamp)` unique | dedupe + lookup |
| strategy_library | `fingerprint` unique | upsert key |
| strategy_lifecycle | `strategy_hash` unique | upsert key |
| mutation_runs | `run_id` unique, `(pair, timeframe, status)` | runner queries |
| mutation_events | `(run_id, base_fingerprint, variant_fingerprint)` | lineage |
| ingested_strategies | `run_id`, `(source, url)` | ingestion dedupe |
| pipeline_logs | `(ts desc)` TTL | log rotation |

Mongo dumps include indexes by default with `mongodump`, so no manual recreation is needed if `mongodump`/`mongorestore` is used end-to-end (see DOWNLOAD_MANIFEST.md).

---

## 6. CONFIGURATION COMPATIBILITY (.env)

| Variable | On source | On target action |
|---|---|---|
| MONGO_URL, DB_NAME | local mongo | **DO NOT MIGRATE** — target has its own |
| JWT_SECRET | set | regenerate on target |
| ADMIN_EMAIL/PASSWORD | set | re-seed on target |
| OPENAI/ANTHROPIC/DEEPSEEK_API_KEY | set | **operator must re-paste** (secrets) |
| EMERGENT_LLM_KEY | set (alias) | optional, phased out |
| MODEL_OPENAI/ANTHROPIC/DEEPSEEK | set | migrate |
| LLM_TASK_* routing | set | migrate |
| LLM_AUTO_FAILOVER, LLM_PRIMARY/FALLBACK | set | migrate |
| AUTONOMOUS_DISCOVERY_ENABLED | False (default) | **keep False on target** until decreed |

---

## 7. CRITICAL CONSTRAINTS (anti-drift)

1. The 8-stage lifecycle and stage_rank semantics are SEALED. Do not remap stages on import.
2. `fingerprint` is the immutable strategy identity; do not regenerate.
3. `governance_universe` is authoritative for what may run on target. Import before any autonomous loop.
4. All autonomy flags (`AUTONOMOUS_DISCOVERY_ENABLED`, `auto_replace_enabled`) must remain off until operator decrees.

---

## 8. KNOWN GAPS / OPEN QUESTIONS (for operator confirmation)

- Confirm whether the 12-vCPU target schedules `AutoMutationRunner` independently or via `orchestrator_scheduler` — affects whether `auto_mutation_runs` should import as live state or as historical record.
- Confirm whether target Master Bot expects an `equity_curve` field on `strategy_library` (not present on source) — if yes, must be derived from `validation_report`.
- Confirm marketplace listing gates (deploy_score threshold, OOS pass count) on target so we can map source survivors correctly.
