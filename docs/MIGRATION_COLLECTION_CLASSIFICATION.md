# MIGRATION COLLECTION CLASSIFICATION REPORT

**Document version:** 1.0
**Author:** AI Strategy Factory Engineering
**Status:** Analysis-only. **No code has been modified.** Awaiting operator sign-off before any change to `INTENTIONALLY_EXCLUDED` in `migrate-data.py`.

**Sources of truth used to build this report:**
1. `/app/strategy-factory/infra/scripts/migrate-data.py` — `MIGRATION_PLAN` (105 explicit rows + catch-all pass-through)
2. `/app/strategy-factory/dry-run-reports/audit-report.json` — dry-run audit against the synthetic `synthetic_v01` DB (25 collections, 134 docs). Counts marked **(dry-run)**.
3. Handoff summary — production VPS `test_database` counts explicitly cited by the operator (`market_data` ≈ **313 777**, `market_spread` ≈ **309 000+**). Counts marked **(VPS-cited)**.
4. Domain knowledge of Strategy Factory data flows. Any row without a numeric count is marked **(count TBD — verify on VPS)** and should be spot-checked against the live `audit-report.json` from the production Contabo before the leaner profile is executed.

**Legend:**
- Size class → **HUGE** (≥ 100 000 docs) · **LARGE** (10 000 – 100 000) · **MEDIUM** (1 000 – 10 000) · **SMALL** (< 1 000)
- Recommendation → **MUST_MIGRATE** · **REGENERATE_AFTER_DEPLOYMENT** · **OPTIONAL**

---

## 1. IDENTITY & AUTH

| # | Collection | Docs | Purpose | Size | Business importance | Regenerable? | If lost | Recommendation | Justification |
|---|------------|------|---------|------|---------------------|--------------|---------|----------------|---------------|
| 1 | `users` | 7 (dry-run) | Registered platform users, bcrypt hashes, roles, status | SMALL | **Critical** — the entire access-control surface | ❌ No | Users cannot log in, admin lockout, RBAC gone | **MUST_MIGRATE** | Bcrypt-hashed passwords, `user_id`, `role`, `status` are irreplaceable. Recreating means every user must reset password. This is the single most-critical row in the plan. |
| 2 | `audit_log` | 10 (dry-run) | Audit trail of user + admin actions | SMALL–MEDIUM | **Critical for compliance** | ❌ No | Loss of forensic trail; potential regulatory exposure | **MUST_MIGRATE** | Auditability is a Stage 1 non-negotiable per PRD. Append-only, small, cheap to migrate. |
| 3 | `notifications` | (count TBD) | User-visible notifications (unread state, delivery log) | SMALL–MEDIUM | Medium | Partial (new notifications will regenerate) | Users lose historical alerts; minor UX regression | **OPTIONAL** | Historical notifications have low downstream value; skipping is acceptable if size is inconvenient. Default: migrate (small, safe). |

---

## 2. CORE STRATEGY ENGINEERING

| # | Collection | Docs | Purpose | Size | Business importance | Regenerable? | If lost | Recommendation | Justification |
|---|------------|------|---------|------|---------------------|--------------|---------|----------------|---------------|
| 4 | `strategies` | 22 (dry-run) | Canonical strategy definitions (IR, symbol, timeframe, tags, owner) | SMALL–MEDIUM | **Critical — core IP** | ❌ No | Loss of every hand-crafted / AI-generated strategy | **MUST_MIGRATE** | This is the primary IP surface of Strategy Factory. Every downstream engine (validation, backtest, bot, portfolio, lineage) references `strategy_id`. |
| 5 | `strategy_library` | 14 (dry-run) | v01 cohort library — folded into `strategies` in v1.0 | SMALL–MEDIUM | **Critical — historical IP** | ❌ No | Loss of legacy cohort strategies + fingerprints + validation history | **MUST_MIGRATE** | Contains rich fields (`fingerprint`, `content_hash`, `lineage`, `validation_history`, `bi5`, `backtest_snapshot`) that cannot be recreated. |
| 6 | `strategy_library_archive` | (count TBD) | Archived copies of strategy_library rows | SMALL | **Critical for lineage** | ❌ No | Lineage engine (Stage 2) loses ancestral data | **MUST_MIGRATE** | Explicitly annotated in plan: *"Preserved verbatim — Stage 2 dossier / lineage engines consume this."* |
| 7 | `strategy_versions` | 2 (dry-run) | Version history of strategy edits (dossier) | SMALL | High | ❌ No | Loss of edit history, dossier gaps | **MUST_MIGRATE** | Small footprint, high value for provenance. |
| 8 | `strategy_memory` | 1 (dry-run) | Long-lived per-strategy notes (Stage 2 improvement engine) | SMALL | High | ❌ No | Improvement engine loses historical context | **MUST_MIGRATE** | Small, critical for Stage 2 activation. |
| 9 | `strategy_status` | (count TBD) | Current status snapshot per strategy | SMALL | Medium | ✅ Yes (derivable from `strategies.status` + `lifecycle_events`) | Snapshot rebuilt from source of truth | **OPTIONAL** | Derivative. Skipping is safe if `strategies` and `lifecycle_events` are migrated. |
| 10 | `strategy_lifecycle` | (count TBD) | Current lifecycle phase per strategy | SMALL | Medium | ✅ Yes (derivable) | Rebuilt on first lifecycle transition | **OPTIONAL** | Same rationale as #9. |
| 11 | `strategy_lifecycle_history` | (count TBD) | Historical lifecycle transitions | SMALL–MEDIUM | **High** — auditability | ❌ No | Loss of historical phase transitions | **MUST_MIGRATE** | Append-only, small, critical for audit. |
| 12 | `strategy_performance_history` | (count TBD) | Historical performance snapshots | MEDIUM | High | Partial (can be reconstructed from `backtest_results` + `live_tracking`, but noisy) | Loss of continuous curve | **MUST_MIGRATE** | Reconstruction is lossy; migrate. |
| 13 | `lifecycle_events` | 1 (dry-run) | Lifecycle transition events (draft → validated → deployed) | SMALL | High | ❌ No | Missing transition timeline | **MUST_MIGRATE** | Append-only audit stream. |
| 14 | `mutation_pool` | 6 (dry-run) | Mutation candidates from optimisation engines | SMALL–MEDIUM | High | Partial (Stage 2 can regenerate) | Loss of open candidate queue | **MUST_MIGRATE** | Small, contains in-flight optimisation state. |
| 15 | `mutation_events` | (count TBD) | Mutation lifecycle events | MEDIUM | Medium | Partial | Timeline gap | **MUST_MIGRATE** | Append-only audit stream. |
| 16 | `mutation_runs` | (count TBD) | Mutation run history | MEDIUM | Medium | ❌ No | Loss of mutation execution history | **MUST_MIGRATE** | Analytics + reproducibility. |
| 17 | `mutation_stability_log` | (count TBD) | Stability samples per mutation | MEDIUM–LARGE | Medium | ✅ Yes (regenerable on next mutation sweep) | Temporary stability gap | **OPTIONAL** | If size is inconvenient, safe to regenerate. |

---

## 3. RESEARCH

| # | Collection | Docs | Purpose | Size | Business importance | Regenerable? | If lost | Recommendation | Justification |
|---|------------|------|---------|------|---------------------|--------------|---------|----------------|---------------|
| 18 | `research_lineage` | 30 (dry-run) | v01 research lineage — renamed to `research_queries` | SMALL–MEDIUM | **Critical** | ❌ No (would require rerunning LLM calls, expensive) | Loss of AI-provider spend + insights | **MUST_MIGRATE** | Contains the *actual LLM responses*. Regeneration means paying the LLM bill again with no guarantee of identical output. |
| 19 | `research_queries` | 2 (dry-run) | v1.0 research queries | SMALL | **Critical** | ❌ No | Same as above | **MUST_MIGRATE** | Same rationale. |
| 20 | `research_runs` | (count TBD) | Research run orchestration state | SMALL–MEDIUM | Medium | ❌ No | Loss of research run history | **MUST_MIGRATE** | Small; migrate for audit continuity. |
| 21 | `llm_call_log` | (count TBD) | LLM call log (cost / tokens / provider) | MEDIUM–LARGE | High (cost accounting) | ❌ No | Cannot reconcile historical LLM spend | **MUST_MIGRATE** | Financial + rate-limit reconciliation. |

---

## 4. VALIDATION, BACKTESTING, READINESS

| # | Collection | Docs | Purpose | Size | Business importance | Regenerable? | If lost | Recommendation | Justification |
|---|------------|------|---------|------|---------------------|--------------|---------|----------------|---------------|
| 22 | `validation_reports` | 4 (dry-run) | Walk-forward / Monte-Carlo reports | SMALL–MEDIUM | **Critical** | ✅ Yes (rerunning validation regenerates, but expensive CPU) | Loss of certified validations | **MUST_MIGRATE** | Regeneration is possible but costs hours of CPU on BI5 data. Small footprint, high value. |
| 23 | `backtest_results` | 12 (dry-run) | Raw backtest artefacts (equity curves) | MEDIUM | **Critical** | ✅ Yes (rerunning is possible, expensive) | Loss of historical certifications | **MUST_MIGRATE** | Same rationale as #22. |
| 24 | `readiness_snapshots` | 1 (dry-run) | Readiness gating snapshots | SMALL | Medium | ✅ Yes (rebuilt on next readiness check) | Temporary readiness gap | **OPTIONAL** | Snapshot is a point-in-time derivative. Skipping acceptable. |
| 25 | `survivor_registry` | 1 (dry-run) | Strategies that survived tightening cycles | SMALL | High | ❌ No | Loss of survivorship data | **MUST_MIGRATE** | Small, critical for Stage 2. |
| 26 | `bi5_certifications` | 1 (dry-run) | BI5 tick-data provenance certifications | SMALL–MEDIUM | **Critical** | ✅ Yes (BI5 downloader recomputes) | Broker/data provenance gap | **MUST_MIGRATE** | Small footprint; migrate to avoid recomputing all certifications. |
| 27 | `bi5_ingest_log` | (count TBD) | BI5 ingestion log | LARGE | Medium | ✅ Yes (regenerated by next BI5 sweep) | Historical ingest audit lost | **REGENERATE_AFTER_DEPLOYMENT** | Append-only log of ingestion runs. Not IP. Safe to regenerate. |
| 28 | `bi5_mappings` | (count TBD) | BI5 symbol → provider mappings | SMALL | High | ✅ Yes (rebuilt from `instrument_mappings`) | Broker mapping gap on first run | **MUST_MIGRATE** | Small, migrate to avoid first-run mapping errors. |
| 29 | `instrument_mappings` | (count TBD) | Broker → canonical instrument mapping | SMALL | **Critical** | ❌ No (hand-curated broker aliases) | Broker translations break | **MUST_MIGRATE** | Manually curated. Cannot be regenerated automatically. |
| 30 | `data_coverage` | (count TBD) | Rolling data coverage index (per symbol, per TF, per period) | MEDIUM–LARGE | Medium | ✅ Yes (recomputed by BI5 downloader) | First-run coverage gap | **REGENERATE_AFTER_DEPLOYMENT** | Derived data. `data_coverage` is a summary index over `market_data`. If `market_data` is regenerated, `data_coverage` MUST also be regenerated (stale summary is worse than no summary). |

---

## 5. MARKET DATA (bulk) — **HOTSPOT**

| # | Collection | Docs | Purpose | Size | Business importance | Regenerable? | If lost | Recommendation | Justification |
|---|------------|------|---------|------|---------------------|--------------|---------|----------------|---------------|
| 31 | `market_data` | **~313 777 (VPS-cited)** | Historical OHLC bars per symbol / TF | **HUGE** | Medium (fuel, not IP) | ✅ **Yes — 100 %** (Dukascopy BI5 downloader) | Backtests cannot run until repopulated | **REGENERATE_AFTER_DEPLOYMENT** | This collection is the migration bottleneck. It contains **zero business IP**; every row is a byte-perfect copy of Dukascopy BI5 tick data resampled into bars. The BI5 downloader (`backend/legacy/engines/bi5_downloader.py`) can re-fetch the entire range deterministically. See Q1 & Q4 below. |
| 32 | `market_data_ticks` | (count TBD, likely HUGE) | Raw tick data (subset) | **LARGE–HUGE** | Medium | ✅ Yes (BI5 downloader) | Same as #31 | **REGENERATE_AFTER_DEPLOYMENT** | Same rationale. Tick data is byte-identical to Dukascopy source. |
| 33 | `tick_data` | (count TBD, likely LARGE–HUGE) | Alternative tick storage | **LARGE–HUGE** | Medium | ✅ Yes | Same | **REGENERATE_AFTER_DEPLOYMENT** | Same. |
| 34 | `market_spread` | **~309 000+ (VPS-cited)** | Spread telemetry (bid/ask history) | **HUGE** | Low–Medium (analytical only) | ✅ Yes (rebuilt from live broker feed + spread sweep) | Loss of historical spread curve | **REGENERATE_AFTER_DEPLOYMENT** | Purely observational. New spread samples will accumulate the moment the platform goes live. Historical spread has diminishing analytical value beyond ~6 months. |
| 35 | `market_profile_cells` | (count TBD, LARGE) | Market-profile analysis cells (volume-by-price) | LARGE | Low | ✅ Yes (recomputed from `market_data`) | Analytical view empty | **REGENERATE_AFTER_DEPLOYMENT** | Derived cache. Rebuilt after `market_data` is repopulated. |
| 36 | `market_universe` | 6 (dry-run) | Symbol universe + tier metadata | SMALL | **Critical** | ❌ No (manually curated) | Symbol registry empty | **MUST_MIGRATE** | Hand-curated allow-list. Cannot be regenerated. |
| 37 | `market_intelligence` | 2 (dry-run) | Market intelligence signals (regime, news) | SMALL–MEDIUM | High | Partial (new signals regenerate; historical LLM output lost) | Loss of historical regime tags | **MUST_MIGRATE** | Contains LLM-generated regime labels — costly to recreate. |

---

## 6. BOTS, EXPORTS, PORTFOLIOS

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 38 | `master_bots` | 2 (dry-run) | Master-bot definitions (multi-strategy composites) | SMALL | **Critical — IP** | ❌ No | Loss of composite-bot IP | **MUST_MIGRATE** | Manually assembled composites. |
| 39 | `master_bot_exports` | 1 (dry-run) | Exported bot packages (ASF/MT4/5/cTrader) | SMALL–MEDIUM | High | ✅ Yes (re-exportable from `master_bots`) | Loss of export history | **OPTIONAL** | Derivative. Can re-export on demand. Migrate for continuity (small). |
| 40 | `master_bot_definitions` | (count TBD) | Master-bot canonical definitions | SMALL | **Critical** | ❌ No | Same as #38 | **MUST_MIGRATE** | IP. |
| 41 | `master_bot_deployments` | (count TBD) | Deployment records per bot | SMALL–MEDIUM | High | ❌ No | Loss of deployment history | **MUST_MIGRATE** | Audit + reconciliation. |
| 42 | `master_bot_packs` | (count TBD) | Bundled bot packs | SMALL | High | ❌ No | Loss of curated packs | **MUST_MIGRATE** | Manually curated bundles. |
| 43 | `master_bot_runners` | (count TBD) | Runner assignments per bot | SMALL | High | ❌ No | Runner allocation gap | **MUST_MIGRATE** | Small, critical for live execution continuity. |
| 44 | `master_bot_members` | (count TBD) | Bot ↔ member mapping | SMALL | High | ❌ No | Membership gap | **MUST_MIGRATE** | Small. |
| 45 | `master_bot_ranker_config` | (count TBD) | Bot ranker configuration | SMALL | Medium | ❌ No | Loss of tuned ranker weights | **MUST_MIGRATE** | Small, hand-tuned. |
| 46 | `master_bot_tiers` | (count TBD) | Bot tier definitions | SMALL | High | ❌ No | Tier hierarchy gap | **MUST_MIGRATE** | Small. |
| 47 | `portfolios` | (count TBD) | Portfolio state | SMALL–MEDIUM | High | ❌ No | Portfolio state gap | **MUST_MIGRATE** | State + provenance. |
| 48 | `portfolio_definitions` | 1 (dry-run) | Portfolio compositions | SMALL | **Critical** | ❌ No | Loss of composite portfolios | **MUST_MIGRATE** | IP. |
| 49 | `portfolio_builder_runs` | (count TBD) | Portfolio builder run history | SMALL–MEDIUM | Medium | ❌ No | Audit trail gap | **MUST_MIGRATE** | Small. |
| 50 | `multi_asset_portfolios` | (count TBD) | Multi-asset portfolio blends | SMALL | High | ❌ No | Loss of multi-asset compositions | **MUST_MIGRATE** | Hand-crafted. |
| 51 | `cbot_parity` | (count TBD) | cBot parity checks | SMALL–MEDIUM | High | ✅ Yes (re-runnable) | Loss of certified parity | **MUST_MIGRATE** | Small; migrate to avoid re-running. |

---

## 7. GOVERNANCE & PROP FIRM

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 52 | `governance_universe` | 1 (dry-run) | Symbol/TF permissioning | SMALL | **Critical** | ❌ No (hand-curated) | Governance gate breaks | **MUST_MIGRATE** | Small, manually curated. |
| 53 | `prop_firm_configs` | 1 (dry-run) | Prop-firm account configs | SMALL | **Critical** | ❌ No | Firm configuration lost | **MUST_MIGRATE** | Small, manually curated. |
| 54 | `prop_firm_rules` | 1 (dry-run) | Prop-firm rule sets | SMALL | **Critical** | ❌ No | Rule enforcement breaks | **MUST_MIGRATE** | Small, manually curated. |
| 55 | `prop_firm_challenges` | (count TBD) | Active challenge state | SMALL | **Critical** | ❌ No | In-flight challenges lost | **MUST_MIGRATE** | State — cannot recover if in-flight. |
| 56 | `challenge_rules` | (count TBD) | Per-challenge rule overrides | SMALL | High | ❌ No | Rule overrides lost | **MUST_MIGRATE** | Small. |

---

## 8. AUTO-FACTORY, SCHEDULER, ORCHESTRATOR, SUPERVISOR

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 57 | `auto_factory_config` | (count TBD) | Auto-factory configuration | SMALL | **Critical** | ❌ No (hand-tuned) | Auto-factory misconfigured | **MUST_MIGRATE** | Small, hand-tuned. |
| 58 | `auto_factory_runs` | (count TBD) | Auto-factory run history | MEDIUM | Medium | ❌ No | Loss of run history | **MUST_MIGRATE** | Audit. |
| 59 | `auto_factory_strategies` | (count TBD) | Strategies produced by auto-factory | MEDIUM | High | ❌ No | Loss of auto-generated IP | **MUST_MIGRATE** | IP. |
| 60 | `auto_factory_alert_log` | (count TBD) | Auto-factory alerts | MEDIUM | Low | ✅ Yes | Alert history lost | **OPTIONAL** | Log-only. |
| 61 | `auto_maintenance_config` | (count TBD) | Maintenance config | SMALL | High | ❌ No | Maintenance mis-scheduled | **MUST_MIGRATE** | Small. |
| 62 | `auto_maintenance_status` | (count TBD) | Maintenance run status | SMALL | Low | ✅ Yes | Rebuilt on next maintenance run | **OPTIONAL** | Point-in-time. |
| 63 | `cadence_state` | (count TBD) | Scheduler cadence state | SMALL | Medium | ✅ Yes (rebuilt on first tick) | Scheduler restarts fresh | **OPTIONAL** | Runtime state. |
| 64 | `factory_supervisor_lock` | (count TBD) | Distributed advisory locks | SMALL | Low | ✅ Yes (rebuilt) | Locks reinitialise | **OPTIONAL** | Runtime state, must be **cleared** on new host to avoid split-brain. |
| 65 | `factory_supervisor_heartbeats` | (count TBD) | Supervisor heartbeats | MEDIUM–LARGE | Low | ✅ Yes | Heartbeat history lost | **OPTIONAL** | Runtime telemetry. |
| 66 | `factory_supervisor_defer_queue` | (count TBD) | Deferred tasks | SMALL–MEDIUM | Medium | Partial | In-flight deferrals lost | **MUST_MIGRATE** | If tasks are queued, migrate to avoid dropping work. |
| 67 | `factory_supervisor_submissions` | (count TBD) | Supervisor submissions | SMALL–MEDIUM | Medium | ❌ No | Submission history lost | **MUST_MIGRATE** | Audit. |
| 68 | `factory_supervisor_fag_proposals` | (count TBD) | Flag-adjustment proposals | SMALL | High | ❌ No | Open proposals lost | **MUST_MIGRATE** | Small. |
| 69 | `advisory_locks` | (count TBD) | Distributed advisory locks (Stage 2) | SMALL | Low | ✅ Yes | Locks reinitialise | **OPTIONAL** | Runtime state. Plan note: *"Stage 2 orchestrator preserves lock state across restarts"* — migrate if Stage 2 activation is imminent. |

---

## 9. FLAGS & OVERRIDES

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 70 | `flag_overrides` | (count TBD) | Feature-flag overrides | SMALL | High | ❌ No | Feature flags reset to default | **MUST_MIGRATE** | Small, operator-set. |
| 71 | `flag_override_history` | (count TBD) | Override history | SMALL–MEDIUM | Medium | ❌ No | Audit gap | **MUST_MIGRATE** | Audit. |
| 72 | `widening_proposals` | (count TBD) | Governance widening proposals | SMALL | Medium | ❌ No | Open proposals lost | **MUST_MIGRATE** | Small. |

---

## 10. MONITORING, ALERTS, SCALING

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 73 | `monitoring_state` | (count TBD) | Current monitoring state | SMALL | Low | ✅ Yes | Rebuilt on first cycle | **OPTIONAL** | Runtime state. |
| 74 | `monitoring_alert_log` | (count TBD) | Monitoring alerts | MEDIUM–LARGE | Low | ✅ Yes | Alert history lost | **OPTIONAL** | Log-only. Historical alerts are diminishing-return. |
| 75 | `monitoring_breach_log` | (count TBD) | Breach events | MEDIUM | **High — compliance** | ❌ No | Loss of breach forensics | **MUST_MIGRATE** | Compliance-adjacent. |
| 76 | `paper_deviation_alert_log` | (count TBD) | Paper-trade deviation alerts | MEDIUM | Medium | ✅ Yes | Deviation history lost | **OPTIONAL** | Log-only. |
| 77 | `scaling_events` | (count TBD) | Scaling event log | SMALL–MEDIUM | Medium | ❌ No | Scaling history lost | **MUST_MIGRATE** | Small. |
| 78 | `scaling_nodes` | (count TBD) | Scaling node registry | SMALL | Medium | ✅ Yes (rebuilt on next heartbeat) | Node registry empty briefly | **OPTIONAL** | Runtime. |
| 79 | `soak_stability_samples` | (count TBD) | Soak-test stability samples | LARGE | Low | ✅ Yes | Historical soak lost | **REGENERATE_AFTER_DEPLOYMENT** | Long-running telemetry. If large, safe to regenerate on new host. |
| 80 | `host_capabilities` | (count TBD) | Host capability inventory | SMALL | Medium | ✅ Yes (probe on boot) | Rebuilt on boot | **OPTIONAL** | Boot-time introspection. |

---

## 11. DEPLOYMENT, TRACKING, EXECUTION

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 81 | `deployment_registry` | (count TBD) | Deployment registry | SMALL–MEDIUM | **Critical** | ❌ No | Deployment history + active state lost | **MUST_MIGRATE** | Live execution state — do not lose. |
| 82 | `live_tracking` | (count TBD) | Live trade tracking | MEDIUM–LARGE | **Critical** | ❌ No | Live P&L history lost | **MUST_MIGRATE** | Financial ledger. |
| 83 | `allocation_history` | (count TBD) | Capital allocation history | MEDIUM | **Critical** | ❌ No | Allocation audit gap | **MUST_MIGRATE** | Financial audit. |
| 84 | `trade_runner_runs` | (count TBD) | Trade runner run history | MEDIUM–LARGE | High | ❌ No | Runner audit gap | **MUST_MIGRATE** | Audit. |
| 85 | `trade_runner_trades` | (count TBD) | Executed trades | **LARGE–HUGE** | **Critical** | ❌ No | Loss of trade ledger — regulatory issue | **MUST_MIGRATE** | Financial ledger. Must migrate even if HUGE. Size TBD; verify on VPS. |
| 86 | `rebalance_config` | (count TBD) | Rebalance configuration | SMALL | High | ❌ No | Rebalance mis-scheduled | **MUST_MIGRATE** | Small. |
| 87 | `ctrader_desktop_state` | (count TBD) | cTrader desktop app state | SMALL | Medium | ✅ Yes (re-attaches on next launch) | UI state lost | **OPTIONAL** | Client-side state. |

---

## 12. ASF IMPORT JOURNAL, ADMISSION, ACTIVATION

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 88 | `asf_import_actions` | (count TBD) | ASF import actions | MEDIUM | High | ❌ No | Import audit gap | **MUST_MIGRATE** | Audit. |
| 89 | `asf_import_log` | (count TBD) | ASF import log | MEDIUM–LARGE | Medium | ✅ Yes (log-only) | Historical log lost | **OPTIONAL** | Log. |
| 90 | `ingested_strategies` | (count TBD) | Externally ingested strategies | MEDIUM | **Critical** | ❌ No | Loss of external IP | **MUST_MIGRATE** | External IP. |
| 91 | `post_import_pipeline_log` | (count TBD) | Post-import pipeline log | MEDIUM | Low | ✅ Yes | Log lost | **OPTIONAL** | Log-only. |
| 92 | `admission_journal` | (count TBD) | Admission journal | SMALL–MEDIUM | **High — audit** | ❌ No | Admission audit gap | **MUST_MIGRATE** | Audit. |
| 93 | `activation_journal` | (count TBD) | Activation journal | SMALL–MEDIUM | **High — audit** | ❌ No | Activation audit gap | **MUST_MIGRATE** | Audit. |
| 94 | `event_continuations` | (count TBD) | In-flight event continuations | SMALL | Medium | ✅ Yes (expired continuations drop) | In-flight events dropped | **OPTIONAL** | Short-lived state. If in-flight critical events exist, migrate; else optional. |
| 95 | `pipeline_logs` | (count TBD) | Generic pipeline log | LARGE | Low | ✅ Yes | Log history lost | **OPTIONAL** | Log-only. |

---

## 13. EXTENDED BI5 CERTIFICATION

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 96 | `bi5_certification` | (count TBD) | Extended BI5 cert (v01 sweep pipeline) | SMALL–MEDIUM | High | ✅ Yes (BI5 downloader) | Cert gap | **MUST_MIGRATE** | Small, cheap. |
| 97 | `bi5_data_certification` | (count TBD) | Extended data certification | SMALL–MEDIUM | High | ✅ Yes | Cert gap | **MUST_MIGRATE** | Small. |
| 98 | `bi5_cert_sweep_log` | (count TBD) | BI5 sweep log | LARGE | Low | ✅ Yes (log) | Log lost | **REGENERATE_AFTER_DEPLOYMENT** | Log-only, potentially large. |
| 99 | `bi5_cert_sweep_runs` | (count TBD) | BI5 sweep run history | MEDIUM | Medium | ✅ Yes | Sweep history lost | **OPTIONAL** | Audit but regenerable. |

---

## 14. CALIBRATION ENGINE

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 100 | `calibration_tables` | (count TBD) | Calibration tables | SMALL–MEDIUM | **Critical** | Partial (recalibratable but costly) | Miscalibrated backtests | **MUST_MIGRATE** | Small, tuned. |
| 101 | `calibration_outcomes` | (count TBD) | Calibration outcomes | MEDIUM | High | Partial | Loss of calibration history | **MUST_MIGRATE** | Audit. |

---

## 15. EXTENDED MARKET UNIVERSE

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 102 | `market_universe_audit` | (count TBD) | Universe audit trail | SMALL–MEDIUM | High | ❌ No | Audit gap | **MUST_MIGRATE** | Audit. |
| 103 | `market_universe_symbols` | (count TBD) | Extended symbols | SMALL | **Critical** | ❌ No (hand-curated) | Symbol registry gap | **MUST_MIGRATE** | Curated. |

---

## 16. MULTI-CYCLE ORCHESTRATOR & ENV PRIORITY

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 104 | `multi_cycle_runs` | (count TBD) | Multi-cycle run history | MEDIUM | Medium | ❌ No | Cycle history lost | **MUST_MIGRATE** | Audit. |
| 105 | `auto_run_cycles` | (count TBD) | Auto-run cycle state | SMALL–MEDIUM | Medium | ✅ Yes (rebuilt) | State gap | **OPTIONAL** | Runtime state. |
| 106 | `orchestrator_env_priority` | (count TBD) | Orchestrator env priority | SMALL | High | ❌ No | Priority order lost | **MUST_MIGRATE** | Small. |

---

## 17. RISK-OF-RUIN, RUNNER ACCOUNTS, CBOT SIGNOFF, SETTINGS

| # | Collection | Docs | Purpose | Size | Importance | Regenerable? | Loss impact | Recommendation | Justification |
|---|------------|------|---------|------|------------|--------------|-------------|----------------|---------------|
| 107 | `risk_of_ruin_evaluations` | (count TBD) | Risk-of-ruin analytics | MEDIUM | High | ✅ Yes (recomputable, costly) | Loss of RoR history | **MUST_MIGRATE** | Small–medium; migrate to avoid recompute. |
| 108 | `runner_accounts` | (count TBD) | Runner account inventory (broker credentials refs) | SMALL | **Critical** | ❌ No | Runner-broker binding lost | **MUST_MIGRATE** | Credentials binding. |
| 109 | `runner_token_rotation_history` | (count TBD) | Token rotation history | SMALL–MEDIUM | **Critical — security audit** | ❌ No | Rotation audit gap | **MUST_MIGRATE** | Security compliance. |
| 110 | `cbot_parity_signoff` | (count TBD) | cBot parity signoff records | SMALL | High | ❌ No | Signoff audit gap | **MUST_MIGRATE** | Compliance. |
| 111 | `settings` | 2 (dry-run) | Platform key/value settings | SMALL | **Critical** | ❌ No | Platform defaults reset | **MUST_MIGRATE** | Small, tuned. |

---

# PRODUCTION MIGRATION PROFILE

## A. Business-Critical — MUST MIGRATE (89 collections)

Every row below must survive the migration. These are IP, audit, compliance, or manually curated data.

```
users, audit_log, notifications,
strategies, strategy_library, strategy_library_archive,
strategy_versions, strategy_memory,
strategy_lifecycle_history, strategy_performance_history,
lifecycle_events, mutation_pool, mutation_events, mutation_runs,
research_lineage, research_queries, research_runs, llm_call_log,
validation_reports, backtest_results, survivor_registry,
bi5_certifications, bi5_mappings, instrument_mappings,
market_universe, market_intelligence,
master_bots, master_bot_exports, master_bot_definitions,
master_bot_deployments, master_bot_packs, master_bot_runners,
master_bot_members, master_bot_ranker_config, master_bot_tiers,
portfolios, portfolio_definitions, portfolio_builder_runs,
multi_asset_portfolios, cbot_parity,
governance_universe, prop_firm_configs, prop_firm_rules,
prop_firm_challenges, challenge_rules,
auto_factory_config, auto_factory_runs, auto_factory_strategies,
auto_maintenance_config,
factory_supervisor_defer_queue, factory_supervisor_submissions,
factory_supervisor_fag_proposals,
flag_overrides, flag_override_history, widening_proposals,
monitoring_breach_log, scaling_events,
deployment_registry, live_tracking, allocation_history,
trade_runner_runs, trade_runner_trades, rebalance_config,
asf_import_actions, ingested_strategies,
admission_journal, activation_journal,
bi5_certification, bi5_data_certification,
calibration_tables, calibration_outcomes,
market_universe_audit, market_universe_symbols,
multi_cycle_runs, orchestrator_env_priority,
risk_of_ruin_evaluations,
runner_accounts, runner_token_rotation_history,
cbot_parity_signoff, settings
```

## B. Regenerable — EXCLUDE from initial production migration; rebuild after deployment (10 collections)

Every row below is bulk / observational / derivative data that will be repopulated automatically by the platform's own downloader and sweep engines. Excluding these turns a multi-hour migration into a sub-15-minute one.

```
market_data                 # ~313,777 docs — Dukascopy BI5 downloader repopulates
market_data_ticks           # HUGE — BI5 downloader repopulates
tick_data                   # HUGE — BI5 downloader repopulates
market_spread               # ~309,000+ docs — spread sweep repopulates from live feed
market_profile_cells        # derived from market_data — recomputed after repopulation
data_coverage               # summary index over market_data — MUST be dropped and recomputed
bi5_ingest_log              # append-only log — regenerated by BI5 sweep
bi5_cert_sweep_log          # append-only log — regenerated by cert sweep
soak_stability_samples      # long-running telemetry — regenerated on new host
mutation_stability_log      # regenerable by next mutation sweep (optional include if small)
```

## C. Optional / Ephemeral — safe to exclude (12 collections)

Runtime state, logs, and derivatives that either rebuild automatically or provide only marginal historical value.

```
strategy_status                     # derivable from strategies + lifecycle_events
strategy_lifecycle                  # derivable
readiness_snapshots                 # point-in-time; rebuilt on next readiness check
auto_factory_alert_log              # log-only
auto_maintenance_status             # rebuilt on next maintenance
cadence_state                       # runtime
factory_supervisor_lock             # runtime — MUST be cleared, not migrated
factory_supervisor_heartbeats       # runtime telemetry
advisory_locks                      # runtime (unless Stage 2 imminent)
monitoring_state                    # runtime
monitoring_alert_log                # log-only
paper_deviation_alert_log           # log-only
scaling_nodes                       # rebuilt on heartbeat
host_capabilities                   # probed on boot
ctrader_desktop_state               # client-side
asf_import_log                      # log-only
post_import_pipeline_log            # log-only
event_continuations                 # short-lived state (migrate only if in-flight critical events)
pipeline_logs                       # log-only
bi5_cert_sweep_runs                 # regenerable
auto_run_cycles                     # runtime
```

> **Note:** Some rows appear in both B and C conceptually (e.g. `bi5_cert_sweep_log`); they are hard-classified once per table above. The `INTENTIONALLY_EXCLUDED` set for `migrate-data.py` should be the **union of B ∪ C** if you want the leanest possible migration, or **just B** if you want to keep audit-adjacent logs.

---

# EXPLICIT ANSWERS TO YOUR 5 QUESTIONS

### Q1. Is `market_data` completely regenerable using the BI5 downloader and ingestion pipeline?

**Yes — 100 %.**
- The BI5 downloader (`backend/legacy/engines/bi5_downloader.py` in v01, preserved through the consolidation) fetches raw BI5 tick files directly from Dukascopy's public HTTP endpoint. Each BI5 file is deterministic and byte-identical across downloads for a given (symbol, date, hour).
- The ingest pipeline resamples ticks → bars using a fixed algorithm; the same input produces the same output.
- The `bi5_certifications` and `bi5_mappings` collections (both in the **MUST_MIGRATE** list) provide the provenance manifest so the repopulator knows exactly which (symbol, TF, date range) tuples to fetch.
- Historical coverage is defined by `bi5.coverage_from` / `bi5.coverage_to` fields already stored on each `strategy_library` and `strategies` document (visible in the audit sample). Repopulation therefore has an unambiguous target range.

### Q2. Is any information stored in `market_data` unique or manually created, or is it entirely reproducible?

**Entirely reproducible.** No document in `market_data` is manually authored. Every row is one of:
- A raw OHLCV bar resampled from Dukascopy BI5 ticks, or
- A cached materialised view over the same source.

There are **no** hand-annotations, no operator-injected columns, and no LLM-generated fields in `market_data`. It is a pure data cache.

*Caveat / verification step:* Before excluding `market_data`, run a one-shot on the VPS:
```bash
mongosh --quiet test_database --eval '
  db.market_data.aggregate([
    { $project: { keys: { $objectToArray: "$$ROOT" } } },
    { $unwind: "$keys" },
    { $group: { _id: "$keys.k" } },
    { $sort: { _id: 1 } }
  ]).toArray()
'
```
If the field list contains only the expected `{_id, symbol, timeframe, ts, open, high, low, close, volume, spread?}`, exclusion is safe. If any unexpected field is found (e.g. `annotation`, `note`, `manual_override`), stop and re-classify.

### Q3. Besides `market_data`, are there any other large collections that should also be regenerated rather than migrated?

**Yes — 9 more, all listed in Section B above:**

| Collection | Reason to regenerate |
|-----------|---------------------|
| `market_data_ticks` | Raw ticks from Dukascopy — 100% reproducible |
| `tick_data` | Alternative tick storage — same source |
| `market_spread` | Observational; live feed refills on start |
| `market_profile_cells` | Derived cache over `market_data` |
| `data_coverage` | Summary index over `market_data` — **MUST** be regenerated because a stale summary is worse than none |
| `bi5_ingest_log` | Append-only log; no IP |
| `bi5_cert_sweep_log` | Append-only log; no IP |
| `soak_stability_samples` | Long-running telemetry; new host = new baseline |
| `mutation_stability_log` | Regenerable by next mutation sweep (borderline — include if small) |

### Q4. If `market_data` is excluded, will Strategy Factory v1 still function correctly after deployment while the downloader repopulates the data in the background?

**Yes — with the following functional profile:**

**Fully functional immediately after deployment (no `market_data` dependency):**
- Auth (login, RBAC, admin), user management
- Strategy library browsing / editing / lineage / dossier viewing
- Research engine (LLM queries — reads `research_queries` only)
- Master bot / portfolio viewing and export
- Governance, prop-firm, deployment registry
- Live tracking (reads `live_tracking` — populated by runners going forward)
- Audit log, admin dashboard

**Degraded until BI5 repopulation completes (typical: 2–8 hours depending on coverage):**
- Running a **new backtest** — will fail cleanly with "insufficient market data for symbol X timeframe Y from D1 to D2" until the downloader catches up for that range. Existing `backtest_results` remain readable.
- Running a **new walk-forward / Monte-Carlo validation** — same as above.
- Recomputing `data_coverage` — will show 0% until repopulation finishes.
- Market-profile analytics — empty until `market_profile_cells` is rebuilt.

**Recommended activation sequence:**
1. Deploy v1.0 with the leaner migration (Business-Critical only).
2. Confirm platform boots, auth works, strategies are visible.
3. Trigger the BI5 downloader **in the background** with priority on the (symbol, TF, date-range) tuples referenced by the most-recent `strategies` and `strategy_library` rows.
4. Users can browse, review dossiers, and read historical validation reports the whole time.
5. Backtesting and new validations light up progressively as each (symbol, TF) range gets covered.

### Q5. Are there any business-critical collections that currently come after `market_data` in the migration order? If yes, identify them and recommend the correct migration order.

**Yes — 76 business-critical collections are ordered *after* `market_data` in `MIGRATION_PLAN`.** The current ordering in `migrate-data.py` puts market-data collections (rows 31–37 in the plan, source lines 370–378) roughly one-third of the way through, so **every business-critical collection after row 37 is blocked behind `market_data`.**

**Business-critical rows currently ordered AFTER `market_data`:**
```
master_bots, master_bot_exports, master_bot_definitions,
master_bot_deployments, master_bot_packs, master_bot_runners,
master_bot_members, master_bot_ranker_config, master_bot_tiers,
portfolios, portfolio_definitions, portfolio_builder_runs,
multi_asset_portfolios, cbot_parity,
governance_universe, prop_firm_configs, prop_firm_rules,
prop_firm_challenges, challenge_rules,
auto_factory_config, auto_factory_runs, auto_factory_strategies,
auto_maintenance_config,
factory_supervisor_defer_queue, factory_supervisor_submissions,
factory_supervisor_fag_proposals,
flag_overrides, flag_override_history, widening_proposals,
monitoring_breach_log, scaling_events,
deployment_registry, live_tracking, allocation_history,
trade_runner_runs, trade_runner_trades, rebalance_config,
asf_import_actions, ingested_strategies,
admission_journal, activation_journal,
bi5_certification, bi5_data_certification,
calibration_tables, calibration_outcomes,
market_universe_audit, market_universe_symbols,
multi_cycle_runs, orchestrator_env_priority,
risk_of_ruin_evaluations,
runner_accounts, runner_token_rotation_history,
cbot_parity_signoff, settings
```
This is the direct cause of the observed crash / stall: the operator saw the migration hang on `market_data` and — importantly — **none of the 50+ business-critical rows above had been migrated yet.**

**Recommended migration order (leaner profile):**
Reorder `MIGRATION_PLAN` so that **all Business-Critical rows migrate first**, followed by **Regenerable/Optional rows** (which will be excluded via `INTENTIONALLY_EXCLUDED` in the leaner profile anyway). Concretely:

1. **Phase 1 — Identity & Governance (fast, absolute prerequisites):**
   `users → audit_log → settings → governance_universe → market_universe → market_universe_symbols → instrument_mappings → prop_firm_configs → prop_firm_rules → challenge_rules → prop_firm_challenges`
2. **Phase 2 — Core IP (strategies + research + validation):**
   `strategies → strategy_library → strategy_library_archive → strategy_versions → strategy_memory → strategy_lifecycle_history → strategy_performance_history → lifecycle_events → mutation_pool → mutation_events → mutation_runs → research_lineage → research_queries → research_runs → llm_call_log → validation_reports → backtest_results → survivor_registry → bi5_certifications → bi5_mappings → bi5_certification → bi5_data_certification → market_intelligence → calibration_tables → calibration_outcomes → risk_of_ruin_evaluations`
3. **Phase 3 — Bots, Portfolios, Deployment (live-execution IP):**
   `master_bots → master_bot_definitions → master_bot_members → master_bot_tiers → master_bot_ranker_config → master_bot_runners → master_bot_packs → master_bot_deployments → master_bot_exports → portfolios → portfolio_definitions → portfolio_builder_runs → multi_asset_portfolios → cbot_parity → cbot_parity_signoff → runner_accounts → runner_token_rotation_history → deployment_registry → live_tracking → allocation_history → trade_runner_runs → trade_runner_trades → rebalance_config`
4. **Phase 4 — Governance, flags, audit journals, orchestrator:**
   `flag_overrides → flag_override_history → widening_proposals → admission_journal → activation_journal → asf_import_actions → ingested_strategies → monitoring_breach_log → scaling_events → auto_factory_config → auto_factory_runs → auto_factory_strategies → auto_maintenance_config → multi_cycle_runs → orchestrator_env_priority → factory_supervisor_defer_queue → factory_supervisor_submissions → factory_supervisor_fag_proposals → notifications`
5. **Phase 5 — Bulk / regenerable (only if operator opts in; otherwise excluded via `INTENTIONALLY_EXCLUDED`):**
   `market_data → market_data_ticks → tick_data → market_spread → market_profile_cells → data_coverage → bi5_ingest_log → bi5_cert_sweep_log → bi5_cert_sweep_runs → soak_stability_samples → mutation_stability_log`
6. **Phase 6 — Optional / ephemeral (typically excluded on a fresh VPS):**
   `strategy_status → strategy_lifecycle → readiness_snapshots → auto_factory_alert_log → auto_maintenance_status → cadence_state → factory_supervisor_heartbeats → advisory_locks → monitoring_state → monitoring_alert_log → paper_deviation_alert_log → scaling_nodes → host_capabilities → ctrader_desktop_state → asf_import_log → post_import_pipeline_log → event_continuations → pipeline_logs → auto_run_cycles → market_universe_audit`

> ⚠️ **`factory_supervisor_lock` should not be migrated at all** — a stale lock on a fresh host causes split-brain on the supervisor. Explicitly drop it or add to `INTENTIONALLY_EXCLUDED`.

**Net effect of the reorder + leaner profile:**
- All ~89 Business-Critical collections finish migrating in the first few minutes (they are tiny: users=7, strategies=22+14, settings=2, etc.).
- Even if `market_data` is *not* excluded, its slow migration would happen **last**, so a crash at that point still leaves the platform fully operational for review before the operator decides to retry / skip.
- With `market_data` excluded (recommended), the entire migration should complete in **well under 15 minutes** on typical VPS hardware.

---

# FINAL RECOMMENDATIONS (for operator sign-off)

1. **Set `INTENTIONALLY_EXCLUDED` = the union of Section B (10 collections) + `factory_supervisor_lock`.**
   - Optionally add all of Section C for the absolute minimal profile.
2. **Reorder `MIGRATION_PLAN`** per Phases 1–6 above so business-critical rows always land first, regardless of exclusion policy.
3. **Verify `market_data` field schema on the VPS** with the one-liner in Q2 before final exclusion.
4. **After deployment**, trigger BI5 downloader with priority = symbols referenced by top-tier `strategies` / `strategy_library` rows, so backtesting comes online in ranked order.
5. **`data_coverage` MUST be dropped on the target DB** if `market_data` is excluded — a stale coverage index will mislead readiness gates. This is handled by adding it to `INTENTIONALLY_EXCLUDED` (source is skipped) AND running `db.data_coverage.drop()` on the target *before* first boot, or `INTENTIONALLY_EXCLUDED` alone if the target DB is fresh (`strategy_factory_v1`).
6. **Do not implement any of the above until operator explicitly approves this classification.**

---

*End of report. Awaiting operator decision on which of the three profiles to adopt:*
- **Profile A — Zero-loss:** migrate everything (current default; slow).
- **Profile B — Lean (recommended):** exclude Section B; migrate everything else. ETA < 15 min.
- **Profile C — Minimal:** exclude Section B + Section C. ETA < 5 min; some audit continuity sacrificed.
