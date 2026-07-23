# Phase 26.5 — Strategy Lifecycle State-Machine Design
## (Design only — no code changes. Read this before implementing G6/G7.)

> **Intent.** Unify the disparate "is this strategy good?" signals (stage, verdict, score, deploy_score, badges, behavioral profile) into a **single, deterministic, cached-only lifecycle state machine** that takes a candidate from "just generated" all the way to "downloadable cBot + signed deployment report" — with explicit graduation gates at each step and explicit demotion rules so the system **converges instead of looping forever**.

---

## 0. The problem we're solving

The current factory has **four disjoint quality concepts**:

| Concept | Lives in | Values | Used by |
|---|---|---|---|
| `stage` | `_attach_validation_view` (recomputed) | `exploratory / candidate / validated / prop_safe` | Explorer chip, badges |
| `verdict` | `strategy_library.save_strategy` (persisted) | `TRADE / RISKY / REJECT` | Library save gate |
| `score` | inside library doc (persisted) | continuous 0..100 | `PROMOTE_BEST` rule, threshold = 60 |
| `deploy_score` | `auto_selection_engine` (recomputed) | continuous, weighted | Portfolio Builder pool ordering |

Each was added in a different phase; none of them progresses a strategy beyond `prop_safe`. **Nothing automatically promotes a strategy past validation into a portfolio, a cBot, or a deployment report.** Result: the system keeps researching but never graduates anyone.

We solve this by **collapsing all four concepts into one ordered lifecycle ladder** with deterministic gate functions, explicit demotion paths, and a single ownership module.

---

## 1. The 8-state lifecycle

```
        ┌─────────────┐  evidence accrues / library save
   ┌──► │ EXPLORATORY ├────────────────────────────────┐
   │    └─────────────┘                                │
   │                                                   ▼
   │    ┌─────────────┐  IS_PF ≥ 1.2 ∧ trades ≥ 30 ∧ saved
   │    │  CANDIDATE  │ ◄──────────────────────────────┤
   │    └──────┬──────┘                                │
   │ demote   │ OOS_ratio ≥ 0.7 ∧ stability ≥ 60      │
   │          ▼                                        │
   │    ┌─────────────┐                                │
   │    │  VALIDATED  │                                │
   │    └──────┬──────┘                                │
   │ demote   │ ≥ 5 runs ∧ cross-run PF stable ∧       │
   │          │ behavior_profile ≠ UNCLASSIFIED        │
   │          ▼                                        │
   │    ┌─────────────┐                                │
   │    │   STABLE    │  ←  NEW  (multi-run consistency)
   │    └──────┬──────┘                                │
   │ demote   │ DD < 5% ∧ pass_prob ≥ 60% ∧            │
   │          │ smoothness ∈ {SMOOTH, null}            │
   │          ▼                                        │
   │    ┌─────────────┐                                │
   │    │  PROP_SAFE  │                                │
   │    └──────┬──────┘                                │
   │ demote   │ deploy_score ≥ p90 of cohort ∧         │
   │          │ regime-stable across ≥ 2 regimes       │
   │          ▼                                        │
   │    ┌─────────────┐                                │
   │    │    ELITE    │  ←  NEW  (top decile + regime  │
   │    └──────┬──────┘          robust)               │
   │ demote   │ portfolio fit + correlation safe +     │
   │          │ verified-firm match_score ≥ 0.8        │
   │          ▼                                        │
   │    ┌──────────────────┐                           │
   │    │ PORTFOLIO_WORTHY │  ←  NEW  (selected for a  │
   │    └────────┬─────────┘          live portfolio)  │
   │ demote     │ BI5 realism: PF degradation < 25 %   │
   │            │ ∧ cBot compile_engine.validate OK    │
   │            ▼                                      │
   │    ┌──────────────────┐                           │
   └────┤ DEPLOYMENT_READY │  ←  NEW  (terminal)       │
        └──────────────────┘                           │
              │                                         │
              │ realism drift / firm rule change        │
              └─────────────────────────────────────────┘
                    (decay back to PORTFOLIO_WORTHY)
```

8 states. Monotonic forward path with explicit demotion arrows. Every gate is a **pure function over cached fields** — no backtest re-run, no LLM call, except the BI5 realism check at the final gate (which runs **once per strategy** when it earns PORTFOLIO_WORTHY).

---

## 2. Gate definitions (entry criteria, deterministic)

### 2.1 EXPLORATORY (entry-level, default)
- **Entry**: any row recorded in `strategy_performance_history` (i.e. it has been run at least once in the mutation pipeline).
- **Demotion source**: none — this is the floor.
- **Source of truth**: existence in history collection.

### 2.2 CANDIDATE (basic statistical floor)
- **Entry — ALL must hold**:
  1. `library_id` is set (i.e. survived auto-save gate, so verdict ∈ {TRADE, strong-RISKY} and prop_status ≠ FAIL).
  2. `runs ≥ 3` (multi-run evidence, not a single lucky backtest).
  3. `IS_PF ≥ 1.2` AND `total_trades ≥ 30`.
- **Why**: matches today's `candidate` stage. Filters out 1-shot wonders and overfit micro-samples.
- **Demotion**: drop to EXPLORATORY only if `library_id` becomes invalid (rare) or `total_trades` recomputes to < 20.

### 2.3 VALIDATED (survives out-of-sample)
- **Entry — CANDIDATE plus**:
  1. `OOS_ratio ≥ 0.7` (out-of-sample PF retains ≥ 70 % of in-sample PF).
  2. `stability_score ≥ 60` (single-doc stability — what the library already computes).
  3. Badge `OVERFIT_RISK` is **not** present.
- **Why**: matches today's `validated` stage. Hard OOS gate — this is where most overfit strategies fail.
- **Demotion to CANDIDATE**: if a recomputed `OOS_ratio` drops below `0.6` (5 % buffer to prevent flip-flop).

### 2.4 STABLE (multi-run consistency) — **NEW**
- **Entry — VALIDATED plus**:
  1. `runs ≥ 5` in `strategy_performance_history`.
  2. **Cross-run PF stability**: `std(pfs) / |mean(pfs)| ≤ 0.25` (already computed by `_safe_stats` as `stability` — different scale; we reuse the same EMA but with a 5-run window).
  3. `behavioral_profile ∉ {UNCLASSIFIED, BALANCED}` — we know what *kind* of strategy this is.
  4. `behavioral_profile` consistent across last 3 runs (no chameleon strategies that flip from `TREND_FOLLOWER` to `MEAN_REVERSION`).
- **Why bridge VALIDATED→PROP_SAFE matters**: today's `validated` stage looks at *one* library snapshot. STABLE adds the cross-run lens — a strategy that scored well once but degrades on subsequent reruns should not progress.
- **Demotion to VALIDATED**: if last 3 runs have `OOS_ratio < 0.6`, OR cross-run stability degrades below 0.35.

### 2.5 PROP_SAFE (passes prop-firm rules at conservative risk)
- **Entry — STABLE plus**:
  1. `max_drawdown_pct < 0.05` (under 5 %).
  2. `pass_probability_pct ≥ 60` (Monte Carlo prop-firm pass probability).
  3. `smoothness_label ∈ {SMOOTH, null}` (NOT VOLATILE).
  4. Behavioural profile ∉ {ASYMMETRIC_BREAKOUT} **unless** `expected_max_consec_losses ≤ 5` (asymmetric breakouts can pass only if their losing streaks fit inside daily-loss limits).
- **Why**: same as today's `prop_safe`, plus the new behavioral guard. Asymmetric breakout strategies can technically pass FTMO with low DD but blow on a 7-loss streak that hits daily-loss limit — the behavioral profile gate prevents this.
- **Demotion**: same demotion rules as STABLE (down-grade to STABLE on DD spike).

### 2.6 ELITE (top decile + regime robust) — **NEW**
- **Entry — PROP_SAFE plus**:
  1. `deploy_score ≥ p90` of all PROP_SAFE strategies in the last 30 days (compute the p90 cutoff once per orchestrator tick, cache in `lifecycle_state` doc).
  2. **Regime survival**: appears with `OOS_ratio ≥ 0.7` in **at least 2 distinct `regime_type` values** in `strategy_performance_history` (regimes already recorded by `mutation_engine`).
  3. `runs ≥ 10` (sample-size guard for the percentile claim).
  4. `recovery_factor ≥ 1.5` (already computed by `_attach_behavior_metrics`).
- **Why distinct from PROP_SAFE**: PROP_SAFE means "passes the bar". ELITE means "actually superior to its peers, in multiple market regimes". This is the first stage where the orchestrator can confidently say "we have a real edge here", not just a survivor.
- **Demotion to PROP_SAFE**: if percentile cutoff slips, OR regime count drops to 1 (e.g. trending-only strategy in a permanent ranging regime).

### 2.7 PORTFOLIO_WORTHY (fits in an actual portfolio) — **NEW**
- **Entry — ELITE plus**:
  1. **Correlation safe**: when added to existing PORTFOLIO_WORTHY strategies, `pair × timeframe` is unique OR style is unique (we already have the de-dup logic in `portfolio_builder_engine._apply_diversification`).
  2. **Verified firm match**: at least one entry in `strategy_challenge_match` with `match_score ≥ 0.8` AND firm `status == "approved"` (the existing `prop_firm_review_rules` flag).
  3. **Style/profile diversity contribution**: adding this strategy doesn't push the portfolio above `max_same_type=2`.
- **Why**: a strategy that is excellent on its own may still be *redundant* relative to existing winners. PORTFOLIO_WORTHY means "would meaningfully improve the existing top portfolio".
- **Demotion to ELITE**: when a higher-scoring strategy in the same pair/style replaces it, OR when the firm whose challenge it matched gets unverified.

### 2.8 DEPLOYMENT_READY (BI5 realism + cBot validates) — **NEW, terminal**
- **Entry — PORTFOLIO_WORTHY plus**:
  1. **BI5 realism gate** (the only EXPENSIVE gate in the lifecycle):
     - Run a tick-level replay via `paper_execution_engine.start_run(source="bi5")` over the last 60 days of BI5 data.
     - Compute `realism_pf = bi5_replay_pf / bid_backtest_pf`.
     - Pass criterion: `realism_pf ≥ 0.75` (BI5 PF retains ≥ 75 % of BID PF after spread/slippage/gap effects).
     - If `0.50 ≤ realism_pf < 0.75`: stays at PORTFOLIO_WORTHY with `PARTIAL_REALISM` flag (advisory, surfaced in UI).
     - If `realism_pf < 0.50`: hard fail — strategy demoted to STABLE with `BI5_FAIL` badge for 30 days, preventing wasted re-promotion.
  2. **cBot compiles**: `compile_engine.validate(generated_code)` returns `is_valid == True` AND `cbot_pipeline.build_reliable_cbot()` returns no errors.
  3. **Risk allocation locked**: `safe_risk_per_trade` from `prop_firm_panel` is set and ≤ 1.0 % of account equity.
- **Why this is the only place BI5 belongs**: see § 4.
- **Demotion**: see § 3.3.

---

## 3. Demotion / decay model

A pure forward-monotonic system would accumulate zombie elites — strategies that earned their stage months ago but no longer reflect reality. We avoid this with three demotion mechanisms:

### 3.1 Hard demotion (immediate, on metric drift)
Recomputed every orchestrator tick. Each gate has a **slightly stricter "stay" threshold than its "enter" threshold** (5–10 % buffer) to prevent flip-flop:

| From → To | Trigger |
|---|---|
| ANY → CANDIDATE | `library_id` becomes invalid OR `total_trades < 20` |
| VALIDATED → CANDIDATE | recomputed `OOS_ratio < 0.6` |
| STABLE → VALIDATED | last 3 runs show `OOS_ratio < 0.6` OR cross-run stability < 0.35 |
| PROP_SAFE → STABLE | `max_drawdown_pct ≥ 0.07` (vs entry 0.05) OR pass_prob < 50 |
| ELITE → PROP_SAFE | percentile cutoff slips OR distinct regime count drops to 1 |
| PORTFOLIO_WORTHY → ELITE | superseded in portfolio OR firm gets unverified |
| DEPLOYMENT_READY → PORTFOLIO_WORTHY | BI5 realism re-check (monthly cron) shows `realism_pf < 0.65` (5 % buffer below entry) |

### 3.2 TTL (soft decay back to re-validate)
- **Any state ≥ STABLE**: if no new performance row in 30 days, soft-demote to one stage below and re-evaluate. Prevents stale data from holding strategy in an unjustified state.
- **DEPLOYMENT_READY**: forcibly re-runs BI5 realism check every 60 days regardless of demotion triggers. Keeps deployment certification fresh.

### 3.3 BI5 hard fail cool-down
- A strategy that fails the BI5 gate gets a 30-day `BI5_FAIL` cool-down — during this period it cannot be promoted past STABLE even if metrics improve. Prevents repeated wasted replays.
- After 30 days, the cool-down auto-clears and the strategy can climb the ladder again.

### 3.4 Manual override (last resort)
- Operator can force-promote (`POST /api/lifecycle/{hash}/force-stage`) or force-demote any strategy with audit logging. Required for: edge cases, compliance reviews, fast-tracking emergency strategy releases.
- Force-promotion to DEPLOYMENT_READY still requires a passing BI5 check — operator cannot bypass tick-level realism.

---

## 4. Where BI5 fits (and where it does not)

### 4.1 BI5 is NOT an early-stage gate
BID candles drive stages 1–7 because:
- **Cheap & abundant** — 36-month retention vs BI5's 6-month, faster I/O, smaller storage.
- **Statistically sufficient for shape** — IS/OOS, drawdown, behavioral profile, regime survival are all valid signals on candle data.
- **Repeatable** — every cycle re-tests on the same candle set; comparable across strategies.

### 4.2 BI5 IS the realism certificate
Tick-level replay is the only way to measure:
- **Spread variance per session** (London open vs Asian close)
- **Slippage on stop orders during volatility spikes**
- **Weekend gap impact for FX**
- **Order-book microstructure effects** (e.g. partial fills on size)

These effects can shave 10–35 % off a BID-measured PF. A strategy that looks great on candles but degrades 50 % on tick replay is **probably curve-fit to mid-bar prices** and will fail in live trading.

### 4.3 Why only at the final gate
Running BI5 replay for every CANDIDATE would:
- Burn 100× more I/O than BID backtest (millions of tick rows vs thousands of candles).
- Produce noisy results when sample size is small (a 50-trade strategy on tick data has wide CI).
- Block the discovery loop — research-grade systems do many cheap experiments, then a few expensive ones.

By placing BI5 only at PORTFOLIO_WORTHY → DEPLOYMENT_READY:
- We run it on **dozens of strategies per month**, not thousands.
- We run it on strategies that have already passed 7 cheap gates — high prior probability of success.
- We make it the *certifying* check, not the *filtering* check.

### 4.4 BI5 implementation plan (already mostly there)
| Already exists | Need to add |
|---|---|
| `paper_execution_engine.start_run(source="bi5", tick_ms=...)` | `realism_pf` calculator + threshold gate (one new function) |
| BI5 data collection + retention (`auto_data_maintainer`) | Trigger from lifecycle state machine when stage flip happens |
| BID backtest PF stored in `strategy_library.profit_factor` | `bi5_realism` block on library doc — `{realism_pf, last_checked_at, status}` |
| `cbot_pipeline.build_reliable_cbot` + `compile_engine.validate` | One call after BI5 gate passes; persist artifact to `cbots` collection |
| Per-strategy "click to compute" stub in `StrategyDetailsPanel` | Becomes a passive status pill ("BI5: 0.82 ✓") instead of a button |

### 4.5 BI5 cohort sweep (cron)
Every Sunday at 03:00 UTC, the orchestrator scheduler runs a single batch:
```
for strategy in PORTFOLIO_WORTHY ∪ DEPLOYMENT_READY:
    if last_realism_check > 60 days OR not present:
        run BI5 replay (last 60 days)
        update bi5_realism block
        recompute lifecycle stage
```
This is the only place tick-level replay runs. It's bounded, predictable, and cheap (a few dozen strategies, not thousands).

---

## 5. Persistence & ownership

### 5.1 New collection: `strategy_lifecycle`
One document per strategy_hash. Single source of truth.
```
{
  strategy_hash: str,
  current_stage: "exploratory" | ... | "deployment_ready",
  current_stage_since: iso_datetime,
  evidence_at_promotion: {
    is_pf: float, oos_ratio: float, stability: float,
    behavioral_profile: str, deploy_score: float,
    regimes_survived: [str], realism_pf: float?,
  },
  flags: ["PARTIAL_REALISM" | "BI5_FAIL" | "STALE" | ...],
  cool_down_until: iso_datetime?,
  last_evaluated_at: iso_datetime,
  history: [
    { stage, entered_at, demoted_at?, reason, evidence }
  ],
  research_run_id: str?,         # links back to G1 lineage
  bi5_realism: { pf_ratio, last_checked_at, sample_days } | null,
  cbot_artifact_id: str | null,  # set when DEPLOYMENT_READY
}
```

### 5.2 New module: `engines/strategy_lifecycle.py`
Pure functions only:
```
def compute_lifecycle_state(
    *,
    library_doc: dict,
    history_rows: list,
    cohort_p90_deploy_score: float,
    bi5_realism: dict | None,
) -> { current_stage, evidence, flags, cool_down_until }
```
Called from:
- `_attach_validation_view` (replaces the inline `stage` ladder).
- New `lifecycle_evaluator` orchestrator job (every tick).
- The promotion poller (G6).

### 5.3 New rules in `ai_orchestrator.decide`
Additive rules, no removal of existing rules:
- `LIFECYCLE_PROMOTE_TO_STABLE` (advisory log)
- `LIFECYCLE_PROMOTE_TO_PROP_SAFE` (advisory log)
- `LIFECYCLE_PROMOTE_TO_ELITE` (advisory log)
- `LIFECYCLE_PROMOTE_TO_PORTFOLIO_WORTHY` → triggers `auto_build_portfolio` (this is **G6 + G7's main hook**)
- `LIFECYCLE_TRIGGER_BI5_CHECK` → triggers BI5 replay job (only fires for PORTFOLIO_WORTHY without recent realism check)
- `LIFECYCLE_PROMOTE_TO_DEPLOYMENT_READY` → triggers cBot compile + report generation
- `LIFECYCLE_DEMOTE` → logs cause + adds to demotion history

### 5.4 New rules surface in Explorer
- Stage chip already shown (Phase 24/25). Extend to show all 8 stages with corresponding tone (deeper green for higher stages, amber for cool-down, blue for partial-realism flag).
- New "Lifecycle Timeline" sub-card in `StrategyDetailsPanel` showing the history array as a horizontal stage timeline.
- "BI5 realism" pill on the row, showing `0.82 ✓` or `0.62 ⚠ partial` or `cool-down 14d`.

---

## 6. Convergence math — why this stops "infinite research"

Today's loop:
```
generate → mutate → save → ??? → loop forever
```
After lifecycle:
```
generate → mutate → save → CANDIDATE → VALIDATED → STABLE
   → PROP_SAFE → ELITE → PORTFOLIO_WORTHY → DEPLOYMENT_READY → DELIVER
                                                      ↑
                                                      end of pipeline:
                                                      operator downloads
                                                      .cs + report
```

**Quantitative target**: out of every 100 EXPLORATORY strategies, we expect (rough order-of-magnitude with the gates above):
- ~25 reach CANDIDATE (75 % filtered by IS_PF + trade count)
- ~10 reach VALIDATED (60 % filtered by OOS gate)
- ~5 reach STABLE (50 % filtered by cross-run consistency)
- ~3 reach PROP_SAFE (40 % filtered by DD/pass_prob)
- ~1 reaches ELITE (66 % filtered by p90 + regime test)
- ~0.5 reach PORTFOLIO_WORTHY (50 % filtered by correlation/firm match)
- ~0.3 reach DEPLOYMENT_READY (40 % filtered by BI5 realism)

So the system **delivers ~3 deployable cBots per 1000 generated strategies**. At current cadence (15-min cycles, ~3 strategies/cycle, 96 cycles/day) that's ~290 strategies/day → **~1 deployment-ready strategy/day in steady state**. Plenty for a 3–5 strategy portfolio.

This is the convergence number that gives the system a **finishing condition**: when 5 PORTFOLIO_WORTHY strategies are DEPLOYMENT_READY, the orchestrator can throttle discovery (drop to 1-hour cadence) until a strategy demotes or expires. This is the difference between "infinite research" and "autonomous research factory".

---

## 7. UI surface — what the user sees

The lifecycle becomes the **single primary axis** in the Explorer:

| Stage | Chip color | Where it appears |
|---|---|---|
| EXPLORATORY | zinc-500 | Explorer (default for new) |
| CANDIDATE | sky-400 | Explorer + Details |
| VALIDATED | emerald-400 | Explorer + Details |
| STABLE | emerald-500 (deeper) | Explorer + Details |
| PROP_SAFE | amber-300 | Explorer + Details + "FTMO Ready" filter |
| ELITE | violet-400 | Explorer + Details + new "Elite" tab |
| PORTFOLIO_WORTHY | violet-500 | Explorer + Details + auto-added to next portfolio assembly |
| DEPLOYMENT_READY | gold-400 (the only premium tone) | Explorer + Details + Dashboard "Ready to Deploy" widget + auto-emails report |

The current 4-stage chip stays compatible: existing UI code reading `stage in ['exploratory', 'candidate', 'validated', 'prop_safe']` continues to work. The new 4 stages are additive.

---

## 8. Implementation order (after this design is approved)

This is not the implementation — just the order in which to build:

1. **G1 — `research_run_id` lineage** (1 session)
   - Plumb a single id through `ai_orchestrator → multi_cycle_runner → auto_mutation_runner → strategy_library / strategy_performance_history / strategy_lifecycle`.
   - Foundation for everything else.

2. **`engines/strategy_lifecycle.py` module** (1 session)
   - Pure-function `compute_lifecycle_state()`.
   - Wire to `_attach_validation_view` (extends, doesn't replace; old 4-stage labels still computed).
   - New `strategy_lifecycle` collection.
   - **No new rules in orchestrator yet** — just the model.

3. **G2 — scheduler unification** (1 session)
   - Make `auto_scheduler` an internal mode of `orchestrator_scheduler` (single APScheduler instance, single config, single restore path).
   - No behaviour change for users.

4. **G6 — promotion ladder rules** (2 sessions)
   - Add `LIFECYCLE_PROMOTE_TO_*` and `LIFECYCLE_DEMOTE` rules to `ai_orchestrator.decide`.
   - Add `auto_build_portfolio` execution hook (calls existing `portfolio_builder_engine.build_portfolio()` with `persist=True`).
   - Add `lifecycle_evaluator` job that runs every orchestrator tick.

5. **BI5 realism gate** (1 session)
   - One new function `engines/bi5_realism.py::evaluate(strategy_hash) → realism_pf`.
   - Calls existing `paper_execution_engine.start_run(source="bi5")`, computes ratio, persists to library.
   - New orchestrator rule `LIFECYCLE_TRIGGER_BI5_CHECK` (Sunday 03:00 UTC sweep).

6. **G7 — deployment report** (1 session)
   - New module `engines/deployment_report.py` joins (lifecycle + portfolio + cBot + firm match + risk allocation + BI5 realism) into a signed JSON+Markdown artifact.
   - Triggered automatically when a strategy reaches DEPLOYMENT_READY.
   - Surfaced in UI as a download link + a new "Deploy" tab.

**Total: ~7 sessions of additive, no-engine-rewrite work.**

After this, the factory has:
- One scheduler.
- One lifecycle.
- One promotion ladder.
- One final artifact.
- One UI surface to monitor it all.

The legacy tabs (`Auto Factory Legacy`, `Workspace`, `Optimization`, `Pipeline`) remain as power-user tools, hidden in the "More" menu.

---

## 9. Open questions for confirmation

Before any implementation begins, please confirm:

1. **Are the 8 stages above the right granularity?** Or should we collapse STABLE+PROP_SAFE into one (since they share entry data) — keeping 7 stages? My recommendation: keep 8; the multi-run consistency check in STABLE is a real signal that single-snapshot PROP_SAFE doesn't capture.

2. **Is the BI5 60-day window appropriate?** Trade-off: shorter window = faster sweep, less data; longer = more accurate realism, more I/O. 60 days is a balance. Could be 30 if BI5 retention shrinks, 90 if storage allows.

3. **Should DEPLOYMENT_READY auto-deliver?** Options:
   a. Auto-generate cBot + report, surface in UI, wait for operator click → download.
   b. Auto-generate AND auto-email/auto-webhook to a configured endpoint.
   My recommendation: (a) — keeps a human in the loop for the final delivery step. Add (b) as a configurable option later.

4. **Demotion buffers (5 %, 10 %)** — these are anti-flip-flop margins. Tunable per-gate. Default values above are conservative; we can iterate.

5. **Cohort window for ELITE percentile** — 30 days? 90 days? Trade-off: shorter = more reactive to recent regime, longer = more stable but may carry stale winners. Recommend 30 days with a 10-strategy minimum cohort size (use 90-day window if cohort < 10).

6. **Manual override audit** — should force-promotions / demotions be visible to all users, or only to admins in a separate audit log? Recommend admin-only audit log + visible "manually overridden" pill on the strategy.

---

## 10. Summary (one screen)

- **8-state lifecycle** (4 existing + 4 new) replaces the disjoint stage / verdict / score / deploy_score concepts with a single deterministic ladder.
- **Each gate is a pure function over cached metrics**, so Explorer responsiveness is preserved.
- **BI5 lives at the final gate only** — it's the realism certificate, not a filter. Runs in a Sunday 03:00 UTC sweep on PORTFOLIO_WORTHY strategies.
- **Demotion + TTL + cool-down** prevent zombie elites and infinite re-promotion of bad strategies.
- **Convergence math**: ~1 DEPLOYMENT_READY strategy/day at current cadence — gives the orchestrator a finishing condition.
- **Implementation is additive**: 7 sessions of work, no engine rewrites, no duplicate pipelines, full back-compat with existing 4-stage chip.

This is the design. Approve, push back, or refine before any code is written.
