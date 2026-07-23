# Phase 26 — Autonomous Research Pipeline Consolidation
## Architecture Analysis · Maturity Map · Consolidation Roadmap

> **Read-only deliverable.** No code changed. No new systems added.
> Goal: clarify what already exists, what already self-runs, what is fragmented,
> and what the minimum glue is to reach a single autonomous research factory.

---

## TASK 1 — Current Orchestration Map

### 1.1 The two existing scheduler loops

| Scheduler | File | Cadence | What it triggers | Enabled by | Survives restart |
|---|---|---|---|---|---|
| **Auto-discovery scheduler** | `engines/auto_scheduler.py` | every 15 min (configurable 1–1440) | `auto_mutation_runner.run_single_cycle(...)` → ONE pair × TF, alternates EURUSD ↔ XAUUSD on H1 | `POST /api/auto/scheduler/start` | yes (`auto_scheduler_config` Mongo doc, `restore_if_enabled()` at startup) |
| **AI orchestrator scheduler** | `engines/orchestrator_scheduler.py` | every 15 min | `ai_orchestrator.run_tick(execute=True)` → observe → decide → may execute `trigger_multi_cycle` | `POST /api/orchestrator/scheduler/start` | yes (`orchestrator_scheduler_config`) |

Both use the same APScheduler engine, both have `max_instances=1 + coalesce=True` (no overlap), both restore on FastAPI startup. **They run independently of each other** — there is no master schedule.

### 1.2 Who calls whom (verified by grep + reading)

```
                       ┌─────────────────────────────────┐
                       │ orchestrator_scheduler (15-min) │
                       └────────────────┬────────────────┘
                                        │
                                        ▼
                            ai_orchestrator.run_tick
                                        │
              ┌─────────────────────────┼──────────────────────────┐
              │                         │                          │
              ▼                         ▼                          ▼
  env_priority.consume_recent_cycles  decide()              env_priority.pick_environments(8)
  (reads auto_run_cycles, updates     (rule-book, returns           │
   per-env multipliers, decays idle)   recommendations)             │
                                        │                          │
                                        ▼                          │
                                   execute(actions)                │
                                        │                          │
                                        ▼                          │
              ┌──────────────────────── trigger_multi_cycle ◄──────┘
              │                              (uses adaptive_scan)
              ▼
   multi_cycle_runner.start_multi_cycle(scan=[(EURUSD,H1),...])
                       │
                       │  loop over scan list (1 cycle per env)
                       ▼
        auto_mutation_runner.run_single_cycle(pair, tf, ...)
                       │
                       │  batch_size strategies per env
                       ▼
              _run_one_strategy(pair, tf, style)
              │
              ├─► strategy_engine.generate_strategy_text   (LLM)
              ├─► mutation_engine.run_mutation_pipeline    (10 variants, real BID)
              │       │
              │       ├─► evolution_engine (regime-aware mutation-type weights)
              │       ├─► backtest_engine.run_backtest_logic (regime_filter + session_spread ON)
              │       ├─► oos_holdout (IS/OOS split, ratio, overfit flag)
              │       ├─► validation_engine + validation_report
              │       ├─► safety_engine + ranking
              │       ├─► pass_probability (Monte Carlo)
              │       └─► auto-save gate → strategy_library (decision/score/verdict)
              │
              └─► strategy_memory.record_from_mutation_result
                  → strategy_performance_history collection
                  → feeds Explorer rollup + behavioral profile

    ┌─────────────────────────────────┐
    │ auto_scheduler (15-min)         │  ← runs INDEPENDENTLY of the chain above
    └────────────────┬────────────────┘
                     │
                     ▼
        auto_mutation_runner.run_single_cycle(pair=alternated, tf="H1")
        (writes to auto_run_cycles, which env_priority then reads on the
         orchestrator's next tick → feedback closes here)
```

### 1.3 What is **already autonomous** today

| # | Capability | Owned by | Trigger |
|---|---|---|---|
| 1 | Periodic discovery on rotating env | `auto_scheduler` → `run_single_cycle` | APScheduler |
| 2 | Adaptive multi-env scan over 8 picks | `orchestrator_scheduler` → `run_tick` → `trigger_multi_cycle` | APScheduler + rule firing |
| 3 | Per-env productivity learning (PF / pass_prob / survivors / OOS / DD EMAs) | `env_priority.consume_recent_cycles` | Called every orchestrator tick |
| 4 | Idle-env decay back to neutral | `env_priority._decay_idle` | Called every orchestrator tick |
| 5 | Mutation-type weight evolution (regime-aware) | `evolution_engine` (read by `mutation_engine`) | Inside every variant generation |
| 6 | Validation gates (regime filter, session spread, IS/OOS, prop status, DD, weak-risky) | `backtest_engine` + auto-save gate inside library | Inside every variant |
| 7 | Performance history recording + behavioral profile | `strategy_memory` | Hook inside `_run_one_strategy` |
| 8 | Explorer rollup + validation badges + behavioral profile classification | `strategy_memory.get_explorer_rollup` + `_attach_validation_view` + `_attach_behavior_metrics` | On every Explorer fetch |
| 9 | Promote-best advisory rule | `ai_orchestrator` rule `PROMOTE_BEST` | Inside `run_tick` when score ≥ 60 |
| 10 | Data preflight + Dukascopy auto-recovery | `data_access.load_with_recovery` | Inside every cycle |
| 11 | Auto data maintenance | `auto_data_maintainer` (background) | Independent loop |
| 12 | LLM key safety + rate-limit retries | `llm_config` + `emergentintegrations` | Inside `strategy_engine` |

### 1.4 What still requires **manual triggering**

| # | Workflow | Endpoint / button | Why it is still manual |
|---|---|---|---|
| A | **Auto Selection** (deploy_score over Explorer rollup) | `POST /api/auto-selection/run` | No scheduler hook |
| B | **Portfolio Builder** (3–5 strategies, risk allocation, blended metrics) | `POST /api/portfolio-builder/build` | No scheduler hook |
| C | **Prop-firm batch analysis** (FTMO compliance + pass_prob across library) | "Analyze all (FTMO)" button → `POST /api/prop-firm-analysis/batch` | Cost-conscious; intended as on-demand |
| D | **Challenge matching batch** (best firm × challenge for top eligible) | "Match Eligible (top 3)" button → `POST /api/challenge-matching/run-eligible` | Cost-conscious; intended as on-demand |
| E | **Market scan** (pair × TF grid evaluation per strategy) | "Scan eligible (top 3)" / per-row → `POST /api/market-intelligence/scan-eligible` | Heavy; intended as on-demand |
| F | **Manual strategy generation (Workspace tab)** | `POST /api/strategy-generate` | Operator debug tool |
| G | **Strategy ingestion** (CSV/JSON upload of pre-existing strategies) | `POST /api/ingestion/run` | Manual upload only |
| H | **Multi-cycle "Run 5 cycles" button** | `POST /api/multi-cycle/start` | Operator debug — orchestrator already auto-triggers it conditionally |
| I | **Auto Factory tab** (universe-grid brute-force) | `POST /api/auto-factory/run` | Separate code path (`auto_factory.py`) — see redundancy section |
| J | **Manual re-run / mutation-pipeline-on-strategy-X** | Explorer "↻" button | Debug tool |
| K | **cBot export** (per-strategy `.cs` skeleton) | Explorer "</>" button → `GET /api/strategies/.../export-cbot` | Per-strategy click — never runs autonomously |
| L | **Final deployable report** | _does not exist_ | Missing system |
| M | **Promotion ladder execution** (validated → prop_safe → portfolio → cBot → deployed) | _does not exist_ | Missing system |

### 1.5 Redundancy / fragmentation found

| Area | Symptoms | Recommendation |
|---|---|---|
| **Auto-factory triplet** | `engines/auto_factory.py` + `engines/auto_factory_engine.py` + `engines/auto_factory_phase55.py` (all do "generate → backtest → filter → store"); UI exposes both `Auto Factory` and `Auto Factory (Legacy)` tabs | Pick one, mark the other two `legacy/`, fold their universe-pair × style logic into `env_priority` (style as a third dimension) |
| **Two discovery loops** | `auto_scheduler` (single-env rotation) + `orchestrator_scheduler` (multi-env adaptive). Both can fire cycles every 15 min — they don't conflict (lock-protected) but they **double the LLM cost** and emit decisions independently | Make `auto_scheduler` an internal subscriber of `orchestrator` rather than a parallel scheduler. The orchestrator already decides whether to trigger; the bare 15-min cron is redundant when the orchestrator is on |
| **Three matching engines** | `engines/matching_engine.py` + `engines/challenge_matching_engine.py` + `engines/phase4_matcher.py` (different signatures, all map strategy → firm) | Audit which one each caller uses — likely `phase4_matcher` is the deprecated version |
| **Two ranking engines** | `ranking_engine.py` + `strategy_ranking_engine.py` (the latter is "v2") | Move all callers to v2; keep v1 imports as thin re-exports |
| **Validation gate duplication** | `validation_engine.py` + `validation_report.py` + the inline gate inside `strategy_library.save_strategy` + `_attach_validation_view` in `strategy_memory.py` all compute slightly different "is this good" signals | Single source: `_attach_validation_view` already reads cached library fields. Make it the canonical view; the others should produce the inputs, not their own verdicts |
| **Strategy creation paths** | LLM (`strategy_engine`) + ingestion (`strategy_ingestion`) + manual generate (`Workspace` tab) all create rows in `strategy_library`, but use different write paths and different telemetry hooks | All three should funnel through the same "candidate enrolment" function so every new candidate gets the same backtest + validation + history record (most of this is already true via `_run_one_strategy`, but `Workspace` and `ingestion` have parallel code paths) |
| **UI button clutter** | Explorer header has three batch buttons (`Match Eligible`, `Analyze all`, `Scan eligible`) that are really debug tools — they should be auto-fired by the orchestrator on a slower cadence (hourly/daily) | Demote to "Power Tools" sub-menu; surface their results passively in Explorer |
| **Tabs overlapping** | `Auto Factory` + `Auto Factory (Legacy)` + `Workspace` + `Pipeline` + `Optimization` + `Multi-Cycle` are all variants of "trigger generation"; some are kept for back-compat | Group under a single collapsible "Manual Tools" section in `More` menu — the Dashboard becomes the one visible orchestrator view |

### 1.6 Diversification flow — what is and isn't covered

| Axis | Where it's controlled | Adaptive? | Gaps |
|---|---|---|---|
| **Pair** | `env_priority.tiers[*].pairs` (3 tiers) | ✅ Yes — multipliers learn per-env | Adding a new pair is config-only |
| **Timeframe** | `env_priority.tiers[*].timeframes` (per-tier list) | ✅ Yes — joint pair×TF env key | `1m` gated behind `allow_noisy_scans=False` |
| **Style** | LLM prompt only — `auto_scheduler` passes `style=""`, so the LLM picks freely; `auto_factory` brute-forces 4 styles uniformly | ❌ **No adaptive learning** on style | **Biggest gap.** No `style` dimension in `env_priority`. No "trend follower vs mean-reversion does better on EURUSD H4" feedback loop |
| **Adaptive allocation** | `env_priority._build_weights` (tier weights × adaptive multipliers, per-env cap, exploratory floor) | ✅ Yes — sound design (EMA + decay + cap) | Style not included; behavioral_profile not consumed |
| **Mutation flow** | `mutation_engine` + `evolution_engine` (regime-aware mutation-type weights from `mutation_stability_log`) | ✅ Yes — type weights re-fit each cycle | Per-(pair, TF, style) regime weights would be richer than per-regime |
| **Validation flow** | `oos_holdout` + `validation_engine` + auto-save gate (`insufficient_trades`, `prop_status_fail`, `oos_gate_failed`, `weak_risky`, `data_missing`) | ✅ Hard rules, no learning | Gates are constants — no adaptive thresholds tied to env regime |
| **Promotion flow** | Stage ladder in `_attach_validation_view`: `exploratory → candidate → validated → prop_safe` (cached fields only) | ⚠️ **Computed but not acted upon** | Nothing automatically advances a `prop_safe` strategy into the portfolio or cBot pipeline |
| **Behavioral profile** | `_classify_behavior` in `strategy_memory` (HIGH_WINRATE_SCALPER / TREND_FOLLOWER / MEAN_REVERSION / ASYMMETRIC_BREAKOUT / LOW_FREQ_SWING / BALANCED / UNCLASSIFIED) | ❌ Surfaced but not consumed by any decision system | Should feed `env_priority` + portfolio builder + prop-firm matcher |

### 1.7 What works internally that the UI does not surface

| Capability | Where it lives | UI status |
|---|---|---|
| Validation stage ladder (`exploratory/candidate/validated/prop_safe`) | `_attach_validation_view` | ✅ now visible (Phase 24/25) |
| Behavioral profile classification | `_attach_behavior_metrics` + `_classify_behavior` | ✅ now visible (Phase 25) |
| Per-env adaptive multiplier + EMA features | `env_priority` (state collection) | ⚠️ `EnvPriorityPanel` exists but is buried inside Orchestrator panel |
| Rule-book firing reasons (NO_SAVES / LOW_PF / OOS_GATE_DOMINANT / etc.) | `ai_orchestrator.decide()` | ⚠️ Surfaced in last-tick payload but no historical timeline |
| Mutation-type evolution (which types win in which regime) | `evolution_engine` | ❌ No UI surface |
| Cycle telemetry (saves_per_run, pfs_per_run, rejection_breakdown buckets) | `ai_orchestrator.observe_state()` | ⚠️ Last-tick only; no longitudinal chart |
| Deploy score (`auto_selection`) | `auto_selection_engine._compute_deploy_score` | ❌ Tab is hidden behind "More" menu |
| Pass-probability narrative reasoning + prop-firm panel violations | `get_strategy_details` | ✅ visible in details drawer |

---

## TASK 2 — Adaptive Autonomous Research Model

### 2.1 Where current behaviour sits on the exploration ↔ exploitation continuum

The factory **already implements Phase 1 + early Phase 2**:

- **Phase 1 (broad exploration)** — `env_priority` cold-starts every env at neutral multiplier `1.0`; tier weights `0.7 / 0.2 / 0.1` ensure CORE pairs get the bulk of cycles but EXPLORATORY (BTC/ETH on 5–15m) is never starved (5 % floor enforced).
- **Phase 2 (adaptive concentration)** — after each cycle, `consume_recent_cycles` blends 5 normalized features (pf, pass_prob, survivors, oos_pf, drawdown) into a 0..1 score, maps to a `[0.5, 2.0]` multiplier with EMA smoothing (α = 0.2). Decay rate 0.02 pulls idle envs back to neutral over ~35 ticks (~9 hr), preventing permanent bias from old performance.

**What works well today:**

- Hard cap (`max_env_share=0.80`) prevents runaway concentration on a single env.
- Exploratory floor preserves serendipity.
- Safety gate (`allow_noisy_scans`) keeps `1m` timeframes off unless explicitly opened.
- Pure functions over cached features — reproducible, debuggable, no LLM in the decision loop.

**What is missing for true adaptive research-grade allocation:**

| # | Gap | Why it matters | Minimum addition |
|---|---|---|---|
| 1 | **Style is not part of the env key** | The system can learn "EURUSD H1 is productive" but cannot learn "EURUSD H1 + scalping is productive while EURUSD H1 + breakout is not". Currently style is left to the LLM prompt to pick. | Add `style` as a third dimension in `env_priority` env-key → from `pair|tf` to `pair|tf|style`; tier-3 fan-out becomes manageable because not every style applies to every TF |
| 2 | **Behavioral profile is not consumed by env_priority** | We classify a strategy as `ASYMMETRIC_BREAKOUT` but the orchestrator does not down-rank that profile when prop-firm prep is the goal. | New score weight `behavior_profile_fitness` keyed on the active goal (prop-firm-pass vs. raw PF) |
| 3 | **No stable "research-run" identifier** | Each cycle in the orchestrator chain has its own `run_id`, but downstream artifacts (selection → portfolio → cBot → report) are not linked back to the originating tick. | One `research_run_id` propagated through the chain, persisted on every produced artifact |
| 4 | **No promotion automation** | `_attach_validation_view` already computes the `prop_safe` stage label, but nothing automatically pushes those strategies forward. | Add a passive "promotion poller" in `ai_orchestrator` that runs once a cycle and emits `promote_to_portfolio` recommendations when stage flips to `prop_safe` |
| 5 | **No goal model** | The orchestrator has one fixed goal: "discover survivors". A research-grade factory should accept goals like "build a 3-strategy FTMO portfolio for $10k account" or "find drift-resistant XAUUSD strategies". | Lightweight `research_goal` doc that biases tier weights, behavioral-profile preferences, and acceptable badge set |
| 6 | **No longitudinal feedback on rules** | Rule fires (e.g. `LOW_PF_DIVERSITY`) but we don't know if the diversity boost actually fixed the problem. | Persist every recommendation + outcome (was avg_pf ≥ 1.0 in the next 3 ticks?), surface as rule effectiveness scorecard |
| 7 | **Mutation-type weights are global** | `evolution_engine` learns regime-specific mutation weights but not env-specific. EURUSD M5 and BTCUSD H4 share the same weights when in the same regime. | Either (a) per-env weights or (b) per-(env, regime) — only worth doing once we have ≥ 100 cycles per env |

### 2.2 Recommended adaptive model

```
                          ┌──────────────────────────────────────────┐
                          │              research_goal               │
                          │  (mode, target firm, target portfolio    │
                          │   size, behavioral preferences)          │
                          └──────────────────┬───────────────────────┘
                                             │ biases
                                             ▼
                  ┌─────────────────────────────────────────────────┐
                  │              env_priority (extended)            │
                  │   tiers indexed by (pair, timeframe, style)     │
                  │   with EMAs and multipliers per tuple           │
                  └──────────────────┬──────────────────────────────┘
                                     │ samples N tuples
                                     ▼
                ai_orchestrator.run_tick → trigger_multi_cycle
                                     │
                                     ▼  N parallel/sequential single cycles
                       auto_mutation_runner.run_single_cycle
                                     │
                                     ▼
                       (per-strategy mutation + validation)
                                     │
                                     ▼
                       strategy_memory.record_from_mutation_result
                                     │
                                     ▼
                       behavioral_profile + stage classification
                                     │
                                     ▼
              (next orchestrator tick reads → feedback closes)
```

Score weights become a function of `research_goal.mode`:

- **mode = "discovery"** → keep current weights (PF heavy, exploratory floor 5 %)
- **mode = "prop-prep"** → boost `pass_prob` + `dd` weights, prefer `HIGH_WINRATE_SCALPER` + `TREND_FOLLOWER` profiles, drop floor to 2 %
- **mode = "diversify"** → boost survivors weight, force minimum 2 distinct styles per portfolio

---

## TASK 3 — Target End-State

### 3.1 Stage-by-stage mapping

| # | Stage | Owned by today | Self-running today? | Glue still needed |
|---|---|---|---|---|
| 1 | Environment selection | `env_priority` | ✅ yes — adaptive | Add `style` dimension; surface `EnvPriorityPanel` on Dashboard |
| 2 | Strategy generation | `strategy_engine.generate_strategy_text` (LLM) + `strategy_ingestion` (file) | ✅ yes (inside cycle) | Funnel `Workspace` + `ingestion` through the same enrolment hook used by `_run_one_strategy` |
| 3 | Mutation | `mutation_engine.run_mutation_pipeline` + `evolution_engine` | ✅ yes — regime-aware weights | Per-env or per-(env, regime) weights when sample size justifies |
| 4 | Validation | `backtest_engine` + `oos_holdout` + `validation_engine` + auto-save gate + `_attach_validation_view` | ✅ yes — hard rules | Make `_attach_validation_view` the single verdict; deduplicate v1/v2 ranking |
| 5 | OOS filtering | `oos_holdout` (IS/OOS split, ratio threshold) | ✅ yes — inside cycle | None — works |
| 6 | Behavioral analysis | `_attach_behavior_metrics` + `_classify_behavior` | ✅ classified but not consumed | Feed back into `env_priority` weights; expose in Auto-Selection deploy_score |
| 7 | Survivor promotion | Stage ladder computed by `_attach_validation_view` → `exploratory/candidate/validated/prop_safe` | ❌ computed but never acted upon | New rule in `ai_orchestrator.decide()`: when a strategy flips to `prop_safe`, emit `promote_to_portfolio` action |
| 8 | Portfolio assembly | `portfolio_builder_engine.build_portfolio` | ❌ manual click | Periodic (hourly/daily) auto-build hooked into the orchestrator scheduler; persist with goal-linked `research_run_id` |
| 9 | cBot export | `cbot_pipeline.build_reliable_cbot` + `code_generator.generate_code` + `compile_engine.validate` | ❌ per-row click | When a strategy is promoted to a saved portfolio, auto-generate + compile-check the cBot in the background; flag failures back to the promotion ladder |
| 10 | Final deployment report | _no system_ | ❌ does not exist | New module `engines/deployment_report.py` that joins (portfolio + per-strategy validation + cBot status + firm match + risk allocation) into a single signed artifact |

### 3.2 What should become "internal-only" (hidden from default UI)

These tabs/buttons remain in the codebase as power-user tooling but disappear from the default Dashboard view because the orchestrator drives them:

- `Auto Factory (Legacy)` — already labelled legacy
- `Pipeline` — superseded by orchestrator + multi-cycle
- `Workspace` — manual generate; demote to "Manual Tools" sub-menu
- `Optimization` — keep accessible but hidden behind a "Research Tools" menu
- Explorer header buttons (`Match Eligible`, `Analyze all`, `Scan eligible`) — these become orchestrator-driven background jobs; surface as "auto-status" pills instead of buttons

What stays prominent on the Dashboard:

- **Orchestrator State** (cycle telemetry, last decisions, env_priority allocation, rule firings)
- **Explorer** (research-grade strategy view with stage / behavior / badges)
- **Portfolio** (auto-assembled top portfolios with deploy reports)
- **Market Data** (so users can monitor/import data)
- **Admin** (users + system controls)

### 3.3 Minimum-glue roadmap (no engine rewrites)

| Step | Effort | Dependency | Outcome |
|---|---|---|---|
| **G1** Add `research_run_id` plumbing through `ai_orchestrator → multi_cycle_runner → auto_mutation_runner → strategy_library/strategy_performance_history` | S | none | Every artifact links back to the originating tick |
| **G2** Demote `auto_scheduler` to be an internal sub-loop of `orchestrator_scheduler` (or simply require both-on-or-both-off) | S | G1 | One scheduler to rule them all; no parallel discovery loops |
| **G3** Extend `env_priority` env key from `pair|tf` to `pair|tf|style`; backfill old state by collapsing on style="*" | M | G2 | Style diversification becomes adaptive |
| **G4** Add `behavior_profile` to env_priority feature mix (configurable weight, default 0) | S | G3 | Behavioral profile feeds the allocator |
| **G5** Add `research_goal` config doc + `mode` switch (discovery / prop-prep / diversify) that flips score-weights presets | M | G4 | One-knob research mode |
| **G6** Add new `ai_orchestrator` rules: `PROMOTE_TO_PORTFOLIO`, `AUTO_BUILD_PORTFOLIO`, `EXPORT_CBOT_FOR_PORTFOLIO`, `GENERATE_DEPLOYMENT_REPORT` (all advisory at first; execute behind a flag) | M | G5 | The promotion ladder becomes traversable autonomously |
| **G7** New module `engines/deployment_report.py` — joins portfolio + cBot + firm match + risk allocation into a signed JSON+PDF artifact | M | G6 | The factory has a final-output |
| **G8** UI consolidation — collapse `Auto Factory (Legacy) / Pipeline / Workspace / Optimization` under a "Research Tools" sub-menu; promote `Orchestrator State` + `Portfolio` to top-level | S | G6 | Surface matches reality |
| **G9** Effectiveness scorecard for orchestrator rules (did `LOW_PF_DIVERSITY` actually fix avg_pf in the next 3 ticks?) | M | G1 | Rules become falsifiable |
| **G10** (Optional) Per-env mutation-type weights when sample ≥ 100 cycles | L | G3 | Mutation engine becomes locality-aware |

**Estimated total: 6–8 sessions of work.** No engine rewrites. No duplicate pipelines. Each step is additive and behind a feature flag.

### 3.4 Final picture — "research-grade autonomous quant factory"

```
                       set research_goal (one click)
                                    │
                                    ▼
                        orchestrator scheduler tick (15 min)
                                    │
                  ┌─────────────────┼─────────────────────┐
                  │                 │                     │
                  ▼                 ▼                     ▼
        env_priority pick    mutation + validation   promotion poller
        (pair × tf × style)        cycle              (validated ↑ prop_safe ↑
                  │                 │                  portfolio_candidate)
                  └────────┬────────┘                     │
                           ▼                              ▼
                 strategy_performance_history    auto-build portfolio
                           │                              │
                           ▼                              ▼
                 behavioral / stage classification   auto-export cBot + compile
                           │                              │
                           ▼                              ▼
                       Explorer view              deployment report (signed)
                                                          │
                                                          ▼
                                                    Trader downloads .cs + report
```

Every box already exists in the codebase **except** the promotion poller, the auto-portfolio cron, the auto-cBot-export, and the deployment report (steps **G6 + G7**). Everything else is consolidation, glue, and visibility.

---

## Summary

- **The autonomous skeleton is already in place.** Two schedulers, one rule-book, one adaptive allocator, one validation gate, one performance ledger.
- **The biggest single gap is the promotion ladder** — we classify `prop_safe` strategies but no system promotes them.
- **The second-biggest gap is style diversification** — `env_priority` does pair × TF, not pair × TF × style.
- **The third-biggest gap is the final deployable report** — there is no end-of-pipeline artifact joining portfolio + cBot + firm match.
- **Most of the visible "manual buttons" are debug tools** — they will become internal jobs once the promotion ladder closes.

**Recommendation:** prioritise G1 → G2 → G6 → G7 (research_run_id, scheduler unification, promotion rules, deployment report). G3–G5 (style + goal model) follow naturally after the ladder closes. G9–G10 (rule scorecards, per-env mutation weights) are quality-of-life improvements once sample size grows.
