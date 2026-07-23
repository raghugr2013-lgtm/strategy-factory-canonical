# DISCOVERY GAP REPORT
**Source:** 1-vCPU AI Strategy Factory v10 (this pod)
**Target:** 12-vCPU deployment (newer architecture)
**Scope:** Read-only gap analysis. Identifies what exists, what is missing, and what was deprecated.

---

## 1. FEATURES PRESENT ON 12-vCPU, ABSENT ON 1-vCPU

These subsystems exist in code/intent on the target but have **no equivalent collection, engine, or data** on this 1-vCPU deployment:

| # | Feature | Evidence on source | Action |
|---|---|---|---|
| 1 | **Master Bot System** | No `*master_bot*` files, no collections | Regenerate post-import from survivors |
| 2 | **Marketplace** | No `*marketplace*` files, no listings collection | Regenerate post-Master-Bot |
| 3 | **Factory Supervisor** | No `factory_supervisor*` files; source uses single-authority `ai_orchestrator` | Start fresh on target |
| 4 | **Strategy Dossier** | No `*dossier*` references; no collection | Compose from imported strategy_library + recomputed scores |
| 5 | **Evidence Score** (composite) | `strategy_lifecycle.evidence` carries raw counters; no `evidence_score` field | Recompute from lifecycle + history |
| 6 | **Market Score** (composite) | `strategy_market_profile` + `market_environment_stats` provide inputs; no composite field | Recompute |
| 7 | **Trust Score** (composite) | No `trust_score` anywhere | Recompute from deploy_score history + OOS + stability |
| 8 | **Quality Score v2** | `ingested_strategies.quality_score` is ingestion-time heuristic only | Recompute v2 post-validation |
| 9 | **Pass Probability v2** (per firm) | Source has scalar `pass_probability` on library; not per-firm | Recompute per (strategy, firm) |
| 10 | **Per-strategy prop-firm analysis** | Collections `strategy_pass_analysis`, `strategy_risk_profile`, `strategy_challenge_match` are empty (engines exist) | Re-match after import |
| 11 | **Portfolio Builder artifacts** | Engine present, `portfolio_builder_runs` collection empty | Rebuild |
| 12 | **Trade Runner artifacts** | Engine present, `trade_runner_runs`/`trade_runner_trades` empty | Rebuild |
| 13 | **Auto Selection artifacts** | Engine present, `auto_selection_runs` empty | Rebuild |
| 14 | **Gem Factory runs** | Engine present, `gem_factory_runs` / `gem_factory_events` empty | Rebuild |
| 15 | **Challenge Decisions** | Engine present, `challenge_decisions` / `challenge_control` empty | Rebuild |
| 16 | **Audit Log** | Engine references `audit_log` collection — empty on source | Start fresh on target |
| 17 | **Strategy Descriptions** | Engine references `strategy_descriptions` — empty | Recompute on demand |
| 18 | **Execution Runs** | `execution_runs` referenced — empty | Start fresh |

**Engines present but never produced data on source (collection exists in code, 0 docs in DB):**
- `portfolio_builder_runs`, `trade_runner_runs`, `trade_runner_trades`
- `auto_selection_runs`, `gem_factory_runs`, `gem_factory_events`
- `challenge_decisions`, `challenge_control`
- `firm_challenge_types`, `strategy_challenge_match`
- `strategy_pass_analysis`, `strategy_risk_profile`
- `strategy_descriptions`, `auto_factory_config`, `execution_runs`
- `tuning_settings`, `slot_stats`, `performance_snapshots`
- `prop_firm_extract_jobs`

These represent latent functionality on the source that was never exercised in production.

---

## 2. FEATURES PRESENT ON 1-vCPU, NO LONGER USED

| Feature | Status on 1-vCPU | Disposition for migration |
|---|---|---|
| `EMERGENT_LLM_KEY` alias | Still configured; Phase 30.3 phased it out | Do not migrate; keep direct provider keys |
| `mutation_stability_log` | 1,042 docs; redundant with `mutation_runs` | Tier 3 — migrate if cheap, else recompute |
| `pipeline_logs` (3,165 docs) | Operational only | Tier 2 — keep for forensics, rotate after import |
| `auto_factory_alert_log` (13 docs) | Pre-30.3 alerting | Tier 2 — keep for trail |
| `orchestrator_scheduler_config` / `auto_scheduler_config` | Single docs | Tier 3 — recreate on target |

No deprecated *data shapes* would block migration.

---

## 3. MISSING METADATA REQUIRED BY NEWER SCORING SYSTEMS

For each newer score, the input fields actually present on this deployment:

### 3.1 Quality Score v2 (multi-signal post-validation)
Required: `total_trades`, `profit_factor`, `win_rate`, `expected_value`, `stability_score`, `consistency_score`, `oos_holdout`, `validation_report`.
**Status:** ALL PRESENT on `strategy_library`. ✅ No gap.

### 3.2 Evidence Score (longitudinal evidence weight)
Required: `lifecycle.evidence` blob, `strategy_lifecycle_history` (stage transitions over time), `strategy_performance_history`.
**Status:** ALL PRESENT (878 lifecycle, 878 history, 1,047 perf history). ✅ No gap.

### 3.3 Market Score (regime-adjusted environmental fitness)
Required: `strategy_market_profile`, `market_environment_stats`, market_data coverage for the (pair, timeframe).
**Status:** PRESENT but partial — `market_environment_stats` has only 9 cells. Some pairs/timeframes may need on-the-fly bootstrap from `market_data`. ⚠️ Minor gap.

### 3.4 Trust Score (composite credibility)
Required: deploy_score history, OOS pass counts, stability over generations.
**Status:** Deploy_score history is NOT explicitly stored — must be derived from `strategy_lifecycle_history.evidence_snapshot`. ⚠️ Partial gap — composable but needs a derivation pass.

### 3.5 Pass Probability v2 (per-firm)
Required: per (strategy, firm) drawdown analysis vs firm rule snapshot.
**Status:** firm rules PRESENT (3 firms), but per-strategy analysis empty. ⚠️ Must compute post-import (a `strategy_pass_analysis` regeneration).

---

## 4. MISSING FIELDS REQUIRED BY MASTER BOT GENERATION

(Hypothesized from typical Master Bot patterns — confirm with target codebase before importing.)

| Required input | On source? | Gap action |
|---|---|---|
| Survivor strategies (lifecycle stage ≥ deployed/elite) | YES (`strategy_lifecycle.current_stage`) | None |
| Strategy IR / parameter blob | YES (`strategy_library.parameters`, `strategy_text`) | None |
| Fingerprint identity | YES | None |
| Equity curve (per-strategy time series) | NOT directly stored | Derive from `validation_report` if curve embedded, else regenerate from backtest |
| Per-strategy correlation matrix vs others | NOT stored | Recompute on target post-import |
| OOS evidence flag | YES (`oos_holdout`) | None |
| Prop-firm clearance | YES (`prop_firm_panel`, `prop_status`) | None |
| Master Bot family/group tag | NOT present | Assign at generation time |

**Verdict:** Master Bot generation can proceed once survivors are imported. Equity curves and correlation matrices are recomputed, not migrated.

---

## 5. MISSING FIELDS REQUIRED BY MARKETPLACE READINESS

| Required input | On source? | Gap action |
|---|---|---|
| `deploy_score` | NOT direct field; only `score` and stage_rank | Derive from lifecycle progression |
| `marketplace_status` | NOT present | Set by readiness gate post-Master-Bot |
| Listing metadata (price, author, license) | NOT present | Operator-supplied or default |
| Verification trail (audit_log, OOS, stability) | PRESENT (composable) | None |
| Strategy description (human-readable) | Engine present, collection empty | Generate via LLM post-import |

**Verdict:** Marketplace is a post-pipeline output, not a migration target.

---

## 6. SUMMARY OF GAPS

| Severity | Count | Examples |
|---|---|---|
| 🔴 Blocking (must resolve before import) | 0 | — |
| 🟡 Recompute required post-import | 9 | Quality v2, Evidence, Market, Trust, Pass-Prob v2, dossiers, descriptions, pass_analysis, risk_profile |
| 🟢 Optional / regenerable | 6 | Portfolio runs, trade runner, auto selection, gem factory, master bot, marketplace |

**Conclusion:** **No data on the 1-vCPU deployment is incompatible** with the 12-vCPU architecture. Every gap is either *recomputable* from migrated primary data or *regenerable* from survivors.
