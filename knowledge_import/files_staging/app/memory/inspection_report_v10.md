# AI Strategy Factory v10 — Inspection Report

**Inspection date:** 2026-02 (this session)
**Inheritance source:** `archive.zip` extracted to `/app/inherited/`
**Discipline:** read-only · zero code changes · zero file moves · zero schema modifications
**Inspector verdict on operator hypothesis:** **CONFIRMED with code-level evidence.** See §6.

---

## 0. Inspection boundary

| Action                               | Performed? |
|--------------------------------------|------------|
| ZIP extraction to `/app/inherited/`  | ✅ |
| Memory-doc reconciliation (17 files) | ✅ |
| Source-tree mapping (91 engines, 43 API routers, 115 test files, 48k+ LoC) | ✅ |
| Targeted code reads of every claimed seam (lifecycle, regime, mutation, walk-forward, OOS, portfolio, BI5 realism, transpiler, IR) | ✅ |
| Code changes                         | ❌ (forbidden by operator) |
| Backend / frontend boot              | ❌ (operator scope: inspection only) |
| Test execution                       | ❌ (would be re-verification, not inspection) |
| Schedulers touched                   | ❌ |
| `/app/` (template) modified          | ❌ — inherited code lives isolated in `/app/inherited/` |

---

## 1. Memory chronology (reconciled)

Memory docs present **inside the ZIP** (under `memory/`); zero conflict with `/app/memory/` which contained only `.gitkeep` + a test-credentials stub. So the inherited chronology is canonical.

| # | Doc | Date | Era marker |
|---|-----|------|-----------|
| 1 | `ARCHITECTURE_ANALYSIS_PHASE26.md`     | 2026-05-09 | Pre-G2/G6 baseline |
| 2 | `STRATEGY_LIFECYCLE_DESIGN_PHASE26_5.md` | 2026-05-09 | 8-stage model spec |
| 3 | `ARCHITECTURE_GAP_ANALYSIS_PHASE27.md` | 2026-05-09 | Gap map: G2, G6, BI5, G7 |
| 4 | `ARCHITECTURE_STATE.md`                | 2026-05-09 | Post-implementation verification |
| 5 | `BI5_ARCHITECTURE_ANALYSIS.md`         | 2026-05-10 | BI5 realism design |
| 6 | `BI5_REALISM_IMPLEMENTATION_PLAN.md`   | 2026-05-10 | Phase 27.3 plan |
| 7 | `PHASE_27_4_COMPLETE.md`               | 2026-05-10 | BI5 single-source resample |
| 8 | `STRATEGY_SYNTHESIS_ARCHITECTURE.md`   | 2026-05-13 | Composer / IR design |
| 9 | `PHASE_28_A_COMPLETE.md`               | 2026-05-13 | IR schema + builders |
| 10 | `PHASE_28_B_COMPLETE.md`              | 2026-05-13 | IR interpreter |
| 11 | `PHASE_28_B_PLUS_COMPLETE.md`         | 2026-05-13 | Composer-chain continuity |
| 12 | `DEPLOY_READY.md`                     | 2026-05-13 | Cold-boot deploy state |
| 13 | `PHASE_28_TELEMETRY_COMPLETE.md`      | 2026-05-13 | `/api/mutation/ir-telemetry` |
| 14 | `PHASE_28_B_PLUS_PLUS_COMPLETE.md`    | 2026-05-13 | Cross-cycle continuity |
| 15 | `PHASE_28_C_COMPLETE.md`              | 2026-05-14 | IR→cAlgo transpiler (147/147 P28, 242/242 regression) |
| 16 | `PRD.md`                              | 2026-05-14 | 47 KB consolidated PRD |

→ Chronology is internally consistent. Phase 28-C is the most-recent seal. Schedulers persisted OFF at the seal point.

---

## 2. Codebase footprint (verified)

```
backend/
  api/             43 routers (260 OpenAPI paths)
  engines/         91 .py modules + strategy_ingestion/ subpkg (7 files)
  cbot_engine/     5 modules — generator (legacy) + ir_emitter + ir_parity_simulator
                   + ir_templates + ir_transpiler  (Phase 28-C surface)
  data_engine/     8 modules — BID/BI5 separation enforced at data_manager.py
                   ALLOWED_SOURCES = ("bid_1m", "bi5")  DEFAULT_SOURCE = "bid_1m"
  config/symbols.py    7 symbols × 7 timeframes universe
  tests/           115 pytest files
frontend/          React 19 / CRACO / Tailwind / Radix UI
                   AuthGate + 46 components + 1 root App.js
memory/            17 architecture docs (reconciled above)
```

LOC verified: `walk_forward_engine.py` 267, `oos_holdout.py` 163, `mutation_engine.py` 1528, `validation_engine.py` 351, `portfolio_builder_engine.py` 386, `multi_cycle_runner.py` 449, `auto_selection_engine.py` 225, `strategy_lifecycle.py` 882, `regime_classifier.py` 127.

---

## 3. Architecture map — verified at code level

### 3.1 Phase 28 SEALED stack (147/147 tests)

```
  strategy_text
    → engines.param_extractor.extract_params
    → engines.strategy_ir_builders.build_legacy_reference_ir       (28-A)
    → composer mutation                                            (28-A → 28-B+)
    → carried strategy_ir across cycles                            (28-B++)
    → engines.ir_telemetry (observable)                            (Telemetry)
    → engines.ir_interpreter.IRInterpreter  ← canonical truth      (28-B)
    → engines.backtest_engine (additive IR hook, neutral)          (28-B)
    → cbot_engine.ir_transpiler → cBot.cs (deterministic, honest   (28-C)
       refusal on unsupported v1 operators; 7-tier trust gate,
       40/40 pass; TRANSPILER_VERSION=1.0.0; HTF_PARITY_MODE
       loudly stamped on every artefact)
```

**Operator-declared invariants verified in code:**
- Interpreter never bypassed — `cbot_engine/ir_parity_simulator.py` delegates signal computation directly to `IRInterpreter`, not a duplicate Python emitter.
- Transpiler refuses MACD / unsupported operators with loud 422 (`UnsupportedIROperatorError`) at both schema (Pydantic enum) and v1 coverage layers.
- IR `_id` never leaks to API: confirmed `find_one(... , {"_id": 0})` patterns and Pydantic response models throughout.
- LLM-free execution: zero LLM imports in any `engines/ir_*.py`, `cbot_engine/ir_*.py`, or `strategy_lifecycle.py`. LLM consumers limited to `engines/llm_config.py` + `engines/strategy_engine.py` (research-side narratives).

### 3.2 Orchestration authority (G2)

- `engines/orchestrator_scheduler.py` is the **single APScheduler instance** per backend boot.
- `engines/auto_scheduler.py` exposes `subordinate_to_orchestrator: true` (default) — when both run, auto_scheduler defers to `orchestrator_scheduler.is_active()`.
- BI5 weekly sweep (`SUN 03:00 UTC`, `realism_sweep`) mounted on the **same** APScheduler instance.
- Persistence: `orchestrator_scheduler_config._id="default"` + `auto_scheduler_config` — both `enabled: false` in the inherited state; `restore_if_enabled` startup hooks honour the persisted value.
- Cooldown: 120 s wall-clock on `/orchestrator/tick` blocks human/scheduler overlap.

### 3.3 Lifecycle progression engine (G6) — `engines/strategy_lifecycle.py` (882 LoC)

| Element                                 | Code location | Observation |
|-----------------------------------------|--------------|-------------|
| Stages                                  | `LIFECYCLE_STAGES` (8) | Closed taxonomy, ordered ranks 0–7 |
| Flags                                   | `LIFECYCLE_FLAGS` (5) | `PARTIAL_REALISM`, `BI5_FAIL`, `STALE`, `MANUALLY_OVERRIDDEN`, `BI5_DATA_MISSING` — closed set |
| Hysteresis                              | `compute_lifecycle_state` lines 393–402 | validated 0.10 OOS, stable 0.10 CoV, prop_safe 0.02 DD, deployment_ready 0.10 BI5 |
| BI5 cool-down                           | `_BI5_FAIL_COOLDOWN_DAYS = 30` | Caps stage at `stable` for 30 days post BI5_FAIL |
| STALE flag                              | `_STALE_DAYS = 30` | Fires on stages ≥ stable when last_run_at >30d |
| Cohort p90 deploy_score                 | `compute_cohort_p90_deploy_score` line 332 | Linear-interp percentile, fails closed when cohort <10 |
| Audit log                               | `upsert_lifecycle` lines 587–650 | Append-only `strategy_lifecycle_history` on every transition |
| Orchestrator wiring                     | `evaluate_cohort` line 746–881 | Pure-cached pass over rollup; fires every tick via Rule 8 |

### 3.4 BI5 realism (Phase 27.3/27.4)

- `engines/bi5_realism.py` (separate inspection — module mass and gating verified by `ARCHITECTURE_STATE.md`).
- Eligible stages locked to `("portfolio_worthy", "deployment_ready")` — confirmed.
- Loader: `data_access.load_with_recovery(source="bi5", auto_recover=False)` — never auto-downloads.
- Resample alignment: `bi5_realism._resample_1m_to_tf` pandas left-closed left-labelled (Phase 27.4) — 8/8 alignment tests pass.

### 3.5 Lineage (G1) — `engines/research_lineage.py`

- Root document per orchestrator-driven trigger, attaches children (`history_row`, `mutation_run`, `library_save`).
- 4 read-only endpoints under `/api/research-runs/*`.
- Cold-start row from 2026-05-09 14:58 confirms WRITE path works in production-boot conditions.

### 3.6 Regime layer — STATE NOTE

**The Phase-16 regime classifier ALREADY EXISTS** (`engines/regime_classifier.py`, 127 LoC) and IS wired into:

| Site | What it does | Effect on filtration |
|------|---------------|----------------------|
| `engines/backtest_engine.py:17 + _regime_allows()` line 749 | Entry gate — when `regime_filter_enabled` and `preferred_regimes` set per strategy_type, blocks entries when current trailing-100-bar regime ∉ preferred set. Telemetry: `regime_blocked_count`. | **Reduces in-sample trade count**; doesn't condition reporting. |
| `engines/mutation_engine.py:721` | Classifies current regime once per cycle; queries `evolution_engine.compute_mutation_weights(regime_type=...)` for regime-conditioned variant-type weights. Falls back to global weights. | **Biases mutation toward variant types that historically did well in this regime**. |
| `engines/strategy_memory.py:106` | Stamps `regime` field on every `strategy_performance_history` row. | Provides the data substrate for any future per-regime breakdown. |
| `engines/strategy_lifecycle.py:387` + `_gate_elite` line 198 | `_gate_elite` requires `distinct_regimes >= 2` (counted from history). | **Symbolic** — only counts distinct labels, doesn't require profitable performance in each. |
| `api/mutation.py:201` | `describe_regime` exposes vol + trend ratio for UI. | Diagnostic-only. |

**What the regime layer does NOT do today:**
- ❌ Compute PF/DD/Sharpe/WR **per regime** (no `regime_performance` engine)
- ❌ Stratify OOS holdout by regime (`engines/oos_holdout.py` is single 80/20)
- ❌ Stratify walk-forward windows by regime coverage (`engines/walk_forward_engine.py` is time-rolling only)
- ❌ Require profitable evidence in ≥2 regimes for promotion (only counts labels)
- ❌ Emit a `REGIME_FRAGILE` lifecycle flag
- ❌ Compute regime-aware deploy_score (the current `_compute_deploy_score` in `auto_selection_engine.py` is single-pool)
- ❌ Apply per-regime BI5 realism (BI5 sweep computes a single PF ratio)

---

## 4. Filtration gate audit — gate by gate

### 4.1 `_gate_candidate` (`strategy_lifecycle.py` line 114)
**Rules:** has library_id, runs ≥ 3, profit_factor ≥ 1.2, total_trades ≥ 30.
**Verdict:** floor gate, single-pool aggregates. No regime, no walk-forward, no fragility evidence. Appropriate for its level.

### 4.2 `_gate_validated` (line 129)
**Rules:** `oos_holdout.ratio ≥ 0.7 - bufs[oos_ratio]`, `stability_score ≥ 60`, no `OVERFIT_RISK` badge.
**Verdict:** uses `oos_holdout.ratio` (single 80/20 holdout, `engines/oos_holdout.py`). **Walk-forward exists (`engines/walk_forward_engine.py`) but is NOT the source of this gate's evidence** — its rolling-window `aggregate.stability_score` could be plumbed in but isn't gating today.

### 4.3 `_gate_stable` (line 157)
**Rules:** ≥ 5 PF-bearing runs, cross-run CoV ≤ 0.25 (+ hysteresis 0.10), behavioral_profile classified ≠ {empty, UNCLASSIFIED, BALANCED}.
**Verdict:** cross-run variance is the key signal but it's **not regime-segmented** — a strategy with 5 high-PF runs all in the SAME regime passes the same as 5 runs spread across regimes.

### 4.4 `_gate_prop_safe` (line 174)
**Rules:** max_drawdown_pct < 0.05 (+ hysteresis 0.02), pass_probability ≥ 60%, smoothness ≠ VOLATILE, ASYMMETRIC_BREAKOUT path has `expected_max_consec_losses ≤ 5`.
**Verdict:** appropriate for prop-firm safety; **no execution-friction sensitivity** (spread/slippage/commission perturbation not tested).

### 4.5 `_gate_elite` (line 198) — STRUCTURAL HINGE
**Rules:** `cohort_p90_deploy_score` cleared, runs ≥ 10, `distinct_regimes ≥ 2`, `recovery_factor ≥ 1.5`.
**Code-level observation:** the cohort p90 is computed on `deploy_score`s drawn from `auto_selection_engine._compute_deploy_score`, which is:
```
  raw = pass_prob×0.45 + match_score×0.25 + pf_component×0.15
      + stability×0.10 + env_conf×0.05    # pf_component saturates at PF=1.5
```
None of `pf_component`, `stability`, `pass_probability` are **regime-conditioned**. The `distinct_regimes ≥ 2` floor is **categorical, not evidential** — it counts labels on history rows; it does not require the strategy to be profitable in each regime.

**Verdict:** this is the **highest-leverage filtration hinge in the architecture** and currently the most regime-blind. ELITE is the last gate before PORTFOLIO_WORTHY → DEPLOYMENT_READY (where BI5 realism is the only remaining hard check).

### 4.6 `_gate_portfolio_worthy` (line 223)
**Rules:** portfolio_membership.is_member, firm_match_score ≥ 0.8, firm_status approved.
**Verdict:** **does not check** marginal Sharpe contribution, correlation-to-portfolio, or diversification grade. `engines/portfolio_engine.py` has all the primitives (Pearson, `max_pair_corr`, `avg_correlation`, correlation-penalty, correlation-bonus) — but they are invoked **inside** the portfolio builder (`portfolio_builder_engine._apply_diversification`), not as a precondition for entering PORTFOLIO_WORTHY.

### 4.7 `_gate_deployment_ready` (line 237)
**Rules:** `bi5_realism.pf_ratio ≥ 0.75` (+ hysteresis 0.10), cBot compiled & valid, `safe_risk_per_trade ≤ 1%`.
**Verdict:** BI5 realism is **single-PF ratio against the cached library PF** — not regime-segmented, not under multiple friction scenarios. Cool-down on `<0.50` is the only loud-fail. Robust at its level; can be deepened later.

---

## 5. Detected bottlenecks (ranked)

### Bottleneck #1 — REGIME-BLIND FILTRATION (highest ROI)
**Evidence:** §4.5. The `distinct_regimes ≥ 2` rule on ELITE counts **labels** drawn from `strategy_performance_history.regime`. The classifier stamps the *input window's regime*, not the *trade execution regime*. A trend-following strategy could have:
- 5 runs all originally classified as `trending` data windows
- But also 5 runs labeled `ranging` because the window slid into a quiet patch
- 0 trades in the ranging runs (`_regime_allows` blocked entries)
- A deceptively "regime-broad" history with all profitable trades concentrated in a single regime

→ Under autonomous emergence, the system will **systematically promote strategies whose edge has not been proven outside their preferred regime**.

### Bottleneck #2 — FRAGILITY-BLIND PROMOTION
**Evidence:** `overfit_score` is subtractive in `strategy_ranking_engine` (weight 0.40) and gated in `phase4_matcher` (`BEST_MAX_OVERFIT=40`). It is **NOT** an input to any `_gate_*` in `strategy_lifecycle.py`. Parameter-sensitivity (perturb each param ±X%, observe PF delta) and execution-friction stress (spread/slippage/commission perturbation) do not exist as standalone modules. `engines/strategy_refinement_engine.py` has trade-shuffle bootstrap + Gaussian perturbation but its output is informational, not lifecycle-gating.

### Bottleneck #3 — POST-HOC PORTFOLIO CORRELATION
**Evidence:** §4.6. Correlation gating happens **after** PORTFOLIO_WORTHY graduation in `portfolio_builder_engine._apply_diversification`. The lifecycle is not portfolio-aware — two strategies that are perfectly correlated can both be PORTFOLIO_WORTHY and both ELITE, wasting cohort-p90 oxygen.

### Bottleneck #4 — WALK-FORWARD NOT GATING
**Evidence:** §4.2. `engines/walk_forward_engine.py` produces `aggregate.stability_score`, `oos_profitable_ratio`, `mean_degradation_pct` per strategy — but `_gate_validated` reads `lib.oos_holdout.ratio` (single 80/20 from `engines/oos_holdout.py`) **only**. The richer walk-forward telemetry is dormant evidence.

### Bottleneck #5 — LIFECYCLE-BLIND ROBUSTNESS
**Evidence:** Phase 5/6 robustness modules (`test_phase5_block_monte_carlo.py`, `test_phase5_structural_robustness.py`, `test_phase6_mutation_guard.py`, `engines/monte_carlo_engine.py`) exist and are tested. None feed a `_gate_*` function. No `FRAGILE` flag in `LIFECYCLE_FLAGS`.

### Bottleneck #6 — REGIME-MONOCULTURE DRIFT RISK
**Evidence:** `engines/evolution_engine.compute_mutation_weights(regime_type=current_regime)` biases mutation toward variants that did well in the *current* data regime. Over many cycles this is a **selection pressure** toward regime-monoculture if no counter-pressure exists (Phase 33 in the roadmap — anti-correlation mutation pressure).

### Bottleneck #7 — SINGLE-PF BI5 REALISM
**Evidence:** `engines/bi5_realism.evaluate` produces a single `pf_ratio` against cached library PF. It is not regime-stratified and not multi-scenario (friction sweep). Sufficient at its level but a candidate for Phase 29-followup once regime evidence exists.

---

## 6. Validation of operator hypothesis

> "The architecture now faithfully preserves semantics and execution continuity, but still lacks institutional-grade filtration gates separating 'lucky backtests' from 'persistent deployable edges.'"

**VERDICT: CONFIRMED.** Six concrete proofs from code:

1. **Single-pool deploy_score saturates at PF=1.5** (`auto_selection_engine.py:52`), so PF beyond 1.5 carries zero marginal ranking weight — but **no regime-conditioned slice replaces it**. A strategy with PF=2.5 in trending + PF=0.6 in ranging has the same `pf_component` as one with PF=1.5 in both.
2. **`distinct_regimes ≥ 2`** is the only regime gate and it counts labels not edge presence (§5.1).
3. **OOS gate uses single 80/20** (`engines/oos_holdout.py:23`), 0.7 ratio + 0.10 hysteresis (lenient under regime drift).
4. **`overfit_score` flows in ranking but never gates lifecycle** (§5.2).
5. **Correlation logic is post-promotion** (§5.3), so the library can fill with mutually-redundant ELITEs.
6. **Walk-forward telemetry is dormant evidence** (§5.4) — the engine runs but its output never reaches a `_gate_*`.

The execution and semantic continuity story is **strong** (Phase 28 sealed). The promotion-gate intelligence story is **shallow**. The mismatch is the bottleneck.

---

## 7. Highest-risk surfaces (in priority order)

1. **`_gate_elite` cohort-p90 + distinct_regimes** — structural hinge; regime-blind today.
2. **`strategy_lifecycle._BI5_FAIL_COOLDOWN_DAYS = 30`** — single-PF cool-down; if regime-conditioned BI5 lands later, careful with the cool-down semantics.
3. **`evolution_engine.compute_mutation_weights(regime_type=...)` selection-pressure** — monoculture drift without an orthogonality counter-pressure.
4. **Schedulers persisted OFF** — first production tick is a manual operator action. Phase 29 must NOT auto-enable them.
5. **`oos_holdout.ratio` lenient threshold (0.7)** under regime drift — relaxing this further is forbidden by operator discipline; raising it would block too much. The right move is regime-stratified OOS, not threshold tweaking.
6. **Phase 28-C transpiler / interpreter / IR schema** are SEALED — Phase 29 must not modify them. The IR has no native regime concept today; if regime evidence ever needs to flow into the transpiler it goes through composer overlays, never through emitter logic.
7. **`portfolio_engine` correlation logic is invoked but not gating** — easy to mistakenly start auto-promoting on `avg_correlation` without proper hysteresis/cool-down design.

---

## 8. Recommended Phase 29 — Regime Layer (proposal)

**Discipline:** additive · reversible · trust-gated · observe-then-gate · zero modifications to sealed Phase 28 / G2 / G6 / BI5 / orchestrator.

### 8.1 What to ADD (six surgical additions)

| Module / change | Status | Scope |
|---|---|---|
| **`engines/regime_performance.py`** (NEW) | Pure function | Given a strategy hash's history rows, return per-regime `{trades, pf, dd, sharpe, win_rate, sample_adequate}`. Deterministic, no I/O. Honest refusal (`None`) on insufficient samples. |
| **`engines/strategy_lifecycle.py`** (ADDITIVE, no existing gate modified) | New helpers | `_compute_regime_evidence(history_rows)`, `_regime_breadth_score(regime_perf)`, `_regime_consistency_cov(regime_perf)`. Stamps `regime_evidence` block onto `evidence` dict. **`REGIME_FRAGILE` added to `LIFECYCLE_FLAGS` as advisory (not demoting in 29.0).** |
| **`engines/oos_holdout.py`** (ADDITIVE) | Companion function | `run_oos_holdout_regime_stratified()` — splits prices by regime label first, then 80/20s within each. Original `run_oos_holdout` untouched. |
| **`engines/walk_forward_engine.py`** (ADDITIVE) | Companion function | `regime_coverage_summary(windows)` annotates each OOS window with its regime distribution. Original `run_walk_forward` untouched. |
| **`api/regime.py`** (NEW router) | Read-only | `GET /api/regime/strategy/{hash}`, `GET /api/regime/cohort-distribution`, `GET /api/lifecycle/regime-evidence/{hash}`. No writes. |
| **`tests/test_regime_layer.py`** (NEW) | Trust gate | 7 tiers · Determinism · Honest refusal on insufficient samples · Flag emission · Backward-compat (all existing lifecycle tests untouched) · Telemetry shape · Schema stability · Lifecycle integration. Target: 25–35 tests. |

### 8.2 What to NOT touch

- ❌ `_gate_elite` rule body (its `distinct_regimes ≥ 2` rule stays — additive evidence only)
- ❌ `_gate_validated` thresholds
- ❌ Any threshold anywhere
- ❌ Mutation engine (Phase 16 regime-weighted mutation already in place)
- ❌ Transpiler / interpreter / IR schema
- ❌ BI5 realism — Phase 29.2 candidate (regime-conditioned BI5) after observation window
- ❌ Schedulers — must remain `enabled: false`
- ❌ Legacy `validation.stage` 4-stage label — additive only
- ❌ Frontend — UI surfaces to be drafted in 29.1 after operator review of `regime_evidence` JSON shape

### 8.3 Operator decisions required before Phase 29 implementation

1. **Demotion authority** — should `REGIME_FRAGILE` be advisory only in Phase 29.0 (recommended), or should it cap promotion at `prop_safe` like `BI5_FAIL` caps at `stable`?
2. **Sample-adequacy threshold per regime** — recommend N≥10 trades per regime to count as evidential. Confirm or override.
3. **OOS-stratified variant** — should regime-stratified OOS supplement, replace, or be a separate evidence channel from the existing 80/20 `oos_holdout`? Recommendation: **supplement** (additive — keep existing one as the gate input for v1).
4. **Backfill posture** — apply `regime_performance` to legacy 70-strategy library? Recommendation: **on-read only** (compute lazily when an endpoint asks; no batch write).
5. **Phase 29 ↔ Phase 31 ordering** — current roadmap is 29→30→31. Confirm portfolio-correlation gates (Phase 31) wait until regime evidence is mature. Recommendation: **yes** — regime evidence makes correlation more meaningful.

### 8.4 Convergence math (back-of-envelope)

Inherited cohort: 167 strategies, all in `exploratory`. Once data ingestion warms the cohort:
- Existing pipeline produces ~2 300 candidates/day (per `ARCHITECTURE_GAP_ANALYSIS_PHASE27.md §3.3`).
- Adding regime-evidence as a flag (not a gate) does NOT throttle throughput.
- If 29.1 promotes the flag to a soft-cap at `prop_safe`, expected effect: 15–30% reduction in `elite` arrivals, but the surviving cohort will have **demonstrated multi-regime edge**.
- Phase 29.0 is therefore **zero-throughput-cost observation**. Phase 29.1 is the gating decision.

---

## 9. Single-glance posture

```
PHASE 28 + G1 + G2 + G6 + BI5     : ✅ SEALED, 242/242 regression, 147/147 P28
SCHEDULERS                         : ⏸ enabled=false, persisted, awaits operator
DATABASE                           : 167 strategies (all exploratory), 0 BI5 ingested
SEMANTIC CONTINUITY                : ✅ deterministic IR → cAlgo C# bridge proven
FILTRATION QUALITY                 : ⚠ regime-blind ELITE gate (highest-leverage hinge)
                                     ⚠ fragility evidence dormant
                                     ⚠ portfolio-correlation post-hoc
                                     ⚠ walk-forward evidence dormant
HYPOTHESIS                         : ✅ CONFIRMED — "execution-faithful, filtration-shallow"
RECOMMENDED NEXT                   : Phase 29 (Regime Layer) — observe-first, no demotion
                                     in v1; trust-gated additive module + read-only API
                                     + new flag advisory; sealed surfaces untouched.
```

---

## 10. Inspection deliverable boundary

This document is the read-only deliverable promised in the operator brief. **No code changed.** The inherited tree under `/app/inherited/` is bit-identical to the uploaded archive minus the ZIP file itself. The existing `/app` template (FastAPI + React skeleton) remains untouched as instructed.

**Awaiting operator approval** of:
- Phase 29 scope as outlined in §8
- The five open questions in §8.3
- Whether to begin Phase 29 implementation, request a deeper sub-inspection (e.g., BI5_ARCHITECTURE_ANALYSIS reconciliation, IR composer overlay reading), or refine the proposal further.

No implementation will begin without explicit operator sign-off.
