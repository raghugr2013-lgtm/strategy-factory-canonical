# Phase 29 — Regime Layer · Implementation Map

**Status:** ✅ IMPLEMENTED & verified (2026-02 session)
**Posture:** observe-first · advisory-only flag · supplement-not-replace · on-read-only backfill
**Discipline (operator-enforced):** additive · reversible · trust-gated · scheduler-safe · lifecycle-safe · BI5-safe · transpiler-safe
**Goal:** filtration HONESTY (not throughput, not strategy quantity)

---

## 0. Operator decisions + GUARANTEES baked into this map

| # | Decision / Guarantee | Effect on map |
|---|---------|---------------|
| 1 | `REGIME_FRAGILE` advisory-only in 29.0 | Flag exists in `LIFECYCLE_FLAGS` taxonomy. **NEVER emitted to persisted lifecycle docs in 29.0.** Lifecycle gates byte-identical. Operator-decision-gated for 29.1. |
| 2 | `N ≥ 10 trades per regime` + `N ≥ 2 runs per regime` + `PF ≥ 1.0` floor | Constants in `engines/regime_performance.py`. Tunable later by operator decree. |
| 3 | Regime-stratified OOS = supplement | New companion `run_oos_holdout_regime_stratified()`. Original `run_oos_holdout` byte-identical (SHA-256 verified). |
| 4 | Legacy 167 strategies = on-read backfill only | **NO batch writes. NO lifecycle doc mutation by Phase 29.** All evidence computed live in `api/regime.py` endpoints from `strategy_performance_history` rows. |
| 5 | Roadmap 29 → 30 → 31 | Phase 29 touches NO correlation logic, NO fragility scoring, NO marginal-Sharpe calculation. |
| **G1** | **Regime evidence in 29.0 must NEVER retroactively alter `deploy_score`, lifecycle stage, PF history, historical rankings, or existing promotion outcomes.** | All evidence is observational. Zero writes to `strategy_library`, `strategy_lifecycle`, `auto_selection_runs`, `strategy_performance_history`. |
| **G2** | **`unknown` regime = insufficient classification confidence, NEVER negative evidence.** | The `unknown` bucket NEVER contributes to `breadth_count`, `regimes_breadth`, `regimes_adequate`, or `fragile`. Surfaces in `per_regime["unknown"]` as zero-evidence stats and via a separate `strategies_with_unknown_only` cohort counter. |

---

## 1. Files to ADD (six new files)

### 1.1 `backend/engines/regime_performance.py` (NEW · pure · zero I/O)
**Purpose:** Single source of truth for "what did this strategy do in each regime?" Computes per-regime aggregate stats from raw `strategy_performance_history` rows.

**Public surface (proposed):**
```python
REGIMES_CANONICAL = ("trending", "ranging", "high_volatility", "low_volatility")
REGIME_UNKNOWN = "unknown"            # surfaced separately, NEVER counted as evidence
MIN_TRADES_PER_REGIME = 10            # operator decision #2
MIN_RUNS_PER_REGIME = 2               # secondary requirement: ≥2 runs (not 1 lucky run)
PF_FLOOR_PER_REGIME = 1.0             # adequate-regime must also be profitable to count for breadth

@dataclass
class RegimeStats:
    regime: str            # one of REGIMES_CANONICAL or "unknown"
    n_runs: int
    trades_total: int
    pf_mean: Optional[float]    # arithmetic mean of run-level PFs
    pf_cov: Optional[float]     # std/|mean| across runs in this regime
    dd_pct_max: Optional[float]
    win_rate_mean: Optional[float]
    return_pct_mean: Optional[float]
    sample_adequate: bool       # n_runs ≥ 2 AND trades_total ≥ 10
    edge_positive: bool         # pf_mean ≥ 1.0 (only set when sample_adequate)

def compute_regime_performance(
    history_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Pure function. Bucket history rows by `regime` field. Return:
        {
          "per_regime":     { regime: RegimeStats-as-dict, ... },
          "regimes_seen":   list of all regime labels encountered,
          "regimes_adequate": list of regimes with sample_adequate=True,
          "regimes_breadth": list of regimes that are adequate AND edge_positive,
          "breadth_count":  int                # len(regimes_breadth)
          "fragile":        bool               # breadth_count < 2  (advisory)
          "computed_at":    iso str,
        }
    Honest refusal:
      • Rows missing `regime` field → bucketed under "unknown", excluded from
        every counter (regimes_adequate, regimes_breadth, breadth_count, fragile).
      • Rows missing `pf` → counted into n_runs only when `trades` is present;
        pf_mean / pf_cov honest-Null when no PFs available.
    """
```

**Determinism contract:** stable output for stable input. List sort order is alphabetical for `regimes_*` to allow bit-identical comparison in tests.

**Estimated size:** ~180 LoC + module docstring + type hints.

---

### 1.2 `backend/api/regime.py` (NEW · read-only router)
**Purpose:** Operator-visible surface for regime evidence. Read-only. No writes anywhere.

**Endpoints (all GET, all auth-gated by existing `AuthMiddleware`):**

| Endpoint | Auth | Returns | Notes |
|---|---|---|---|
| `GET /api/regime/strategy/{strategy_hash}` | yes | regime_performance payload for a single strategy (live compute from history rows) | 404 if no history rows; 200 with `regimes_seen: []` if 0 rows but valid hash. |
| `GET /api/regime/cohort-distribution` | yes | Aggregate distribution: histogram of `breadth_count` across all `strategy_lifecycle` rows; counts of strategies with `fragile=True`; per-regime occupancy in the cohort. | Computed on-read from rollup; capped at 500 strategies; cursor support: `?limit=N`. |
| `GET /api/lifecycle/regime-evidence/{strategy_hash}` | yes | Reads `regime_evidence` block from `strategy_lifecycle.evidence` if present (lifecycle was evaluated post-29.0); falls back to live compute otherwise. | Single-source view for operators inspecting a specific strategy's promotion narrative. |

**OUT OF SCOPE for 29.0:**
- ❌ POST endpoints (no writes)
- ❌ DELETE / PATCH
- ❌ Bulk endpoints that mutate lifecycle docs
- ❌ Endpoints that trigger backfill writes

**Estimated size:** ~140 LoC.

---

### 1.3 `backend/tests/test_regime_layer.py` (NEW · trust-gate · 7 tiers)

**Test taxonomy (target 32 tests):**

| Tier | Description | Test count |
|---|---|---|
| **1 — Determinism** | Same history rows → bit-identical `compute_regime_performance` output. Dict-key insertion-order shuffle, list-order shuffle of input rows, repeat-call same process all yield byte-equal `json.dumps(sort_keys=True)`. | 4 |
| **2 — Honest refusal** | Empty history → `breadth_count=0, fragile=True, regimes_seen=[]`. History rows missing `regime` → all bucketed under `"unknown"`, never inflate any counter. History rows missing `pf` → `pf_mean=None` (not `0.0`). Below `MIN_TRADES_PER_REGIME` → `sample_adequate=False`. Below `MIN_RUNS_PER_REGIME` → `sample_adequate=False`. Below `PF_FLOOR_PER_REGIME` → `edge_positive=False`. | 6 |
| **3 — Sample-adequacy semantics** | 1 row × 30 trades pf=1.5 → adequate=False (runs<2). 2 rows × 4 trades each pf=1.5 → adequate=False (trades<10). 2 rows × 5 trades each pf=1.5 → adequate=True. PF mean computed correctly. CoV computed correctly. | 5 |
| **4 — Flag emission** | Fixture A: 5 rows all in `trending` regime, PF=1.4 each → `breadth_count=1`, `fragile=True`. Fixture B: 3 rows trending PF=1.4 + 3 rows ranging PF=1.3 → `breadth_count=2`, `fragile=False`. Fixture C: 3 rows trending PF=1.4 + 3 rows ranging PF=0.7 → `breadth_count=1`, `fragile=True` (ranging adequate but not edge_positive). Fixture D: rows with `regime=None` → contributes only to `unknown` bucket, never to breadth. | 5 |
| **5 — Lifecycle integration (additive)** | `compute_lifecycle_state` called with synthetic history returns `evidence["regime_evidence"]` block; `flags` includes `REGIME_FRAGILE` when fragile=True; **`current_stage` is identical to pre-29 output for every fixture from `test_strategy_lifecycle_phase26_5.py`** (backward-compat guarantee). | 6 |
| **6 — API contract** | `GET /api/regime/strategy/{unknown_hash}` → 200 with empty `regimes_seen` (NOT 404 — it's a "no evidence yet" semantic, parallel to BI5_DATA_MISSING). `GET /api/regime/cohort-distribution` returns stable shape on empty cohort. `?limit=N` validation (1≤N≤500). Auth-required (401 without token). | 4 |
| **7 — Schema stability** | `regime_evidence` JSON shape is stable across regime-set permutations (alphabetical key order); missing regimes report `null` not absent; `breadth_count`/`fragile`/`computed_at` always present; LIFECYCLE_FLAGS taxonomy now includes `REGIME_FRAGILE` and nothing else has changed. | 2 |

**Estimated size:** ~520 LoC.

---

### 1.4 `backend/tests/test_regime_oos_stratified.py` (NEW · supplement-OOS gate)

**Tests (target 8):**
1. Bars labeled by regime via `_classify_regime` on rolling 100-bar windows.
2. Strict no-leakage within each regime stratum: train slice indices vs OOS slice indices disjoint.
3. Insufficient regime samples → that regime contributes `null`, not error.
4. Aggregate OOS PF is the trade-weighted blend of per-regime OOS PFs.
5. Determinism (same prices → same stratified output).
6. Original `run_oos_holdout` byte-identical when called on same input.
7. Returns separate object — does NOT write to `lib.oos_holdout`.
8. Output schema stable: always emits `per_regime: { trending, ranging, high_volatility, low_volatility }` even if regime never present (null contents).

**Estimated size:** ~180 LoC.

---

### 1.5 `backend/tests/test_walk_forward_regime_coverage.py` (NEW · WF supplement gate)

**Tests (target 5):**
1. `regime_coverage_summary(windows)` returns `regime_distribution: {trending: int, ranging: int, ...}` and `regime_entropy: float`.
2. Entropy = 0 when all windows in single regime; entropy = ln(k) when uniform across k regimes.
3. Function does NOT mutate input `windows` list.
4. Empty windows → returns shape with zeros, never raises.
5. Original `run_walk_forward()` output byte-identical when called on same input (additive guarantee).

**Estimated size:** ~110 LoC.

---

### 1.6 `memory/PHASE_29_PLAN.md` (NEW · this map + sign-off log)
Operator decisions, scope, exclusions, trust-gate ledger. Written before any code lands so the chronology stays clean (parallel to how Phase 28-A/B/B+/B++/Telemetry/C each landed a `*_COMPLETE.md`).

---

## 2. Files to EXTEND (three additive edits — strict additivity)

### 2.1 `backend/engines/strategy_lifecycle.py` (ADDITIVE only)

**Edits (no existing line modified):**

| Location | Add | Touched? |
|---|---|---|
| Line ~85 (`LIFECYCLE_FLAGS` set) | Append `"REGIME_FRAGILE"` to the set literal | flag set extended — NO behaviour change |
| Module body (new helper, ~end of file before persistence section) | `def _compute_regime_evidence_block(history_rows): ...` calling `engines.regime_performance.compute_regime_performance` and returning a serializable block | NEW helper, pure |
| `compute_lifecycle_state` (~line 357) | Inside function body, AFTER existing flag computation (line ~468, after STALE flag block), append: <br>` evidence_block["regime_evidence"] = _compute_regime_evidence_block(history_rows)` <br>` if evidence_block["regime_evidence"]["fragile"]: flags_out.append("REGIME_FRAGILE")` | **Only adds keys to existing dicts and appends to existing list. No existing gate signature touched. No stage decision logic modified.** |
| `compute_lifecycle_state_from_rollup` | Pass-through; the rollup adapter already calls `compute_lifecycle_state` so this gets regime_evidence for free | NO direct edit |

**Critical guarantee for the operator's "backward-compat" requirement:**
- `_gate_candidate`, `_gate_validated`, `_gate_stable`, `_gate_prop_safe`, `_gate_elite`, `_gate_portfolio_worthy`, `_gate_deployment_ready` — **bodies UNCHANGED**.
- `current_stage` decision logic — **UNCHANGED**.
- `STAGE_RANK`, `LIFECYCLE_STAGES`, `_BI5_FAIL_COOLDOWN_DAYS`, `_STALE_DAYS` — **UNCHANGED**.
- Existing flag emission (PARTIAL_REALISM, BI5_FAIL, STALE, MANUALLY_OVERRIDDEN, BI5_DATA_MISSING) — **UNCHANGED**.
- Hysteresis buffers — **UNCHANGED**.

**Total LoC delta:** ~25 lines added · zero lines removed · zero lines modified.

---

### 2.2 `backend/engines/oos_holdout.py` (ADDITIVE companion function)

**New companion function at end of file:**
```python
def run_oos_holdout_regime_stratified(
    strategy_text: str,
    pair: str,
    timeframe: str,
    prices: list,
    timestamps: Optional[list] = None,    # for regime labeling alignment
    train_pct: float = DEFAULT_TRAIN_PCT,
    num_variants: int = DEFAULT_NUM_VARIANTS,
    sim_config: dict = None,
    regime_window: int = 100,
) -> dict:
    """SUPPLEMENT to run_oos_holdout. Stratifies bars by trailing-window regime
    label, then 80/20s WITHIN each stratum. Returns per-regime OOS metrics
    plus aggregate. NEVER mutates `lib.oos_holdout` — operator decision #3.

    Returns:
        {
          "success": bool,
          "mode": "holdout_regime_stratified",
          "per_regime": {
              "trending":         {pf, dd, win_rate, trades, train_bars, oos_bars, ratio, edge_positive} or null,
              "ranging":          { ... } or null,
              "high_volatility":  { ... } or null,
              "low_volatility":   { ... } or null,
          },
          "aggregate":            { ... },   # trade-weighted blend
          "regimes_with_evidence": int,
          "_leakage_guard":       {...},
          "_note":                "supplement only — does not write lib.oos_holdout"
        }
    """
```

**Constraints:**
- Calls existing `fit_best_params` / `score_frozen_params` from `engines.random_search_optimizer` — no new optimizer.
- Reuses `_classify_regime` from `engines.regime_classifier`.
- Original `run_oos_holdout` byte-identical (line-diffed in trust gate Tier 6 of `test_regime_oos_stratified.py`).

**Total LoC delta:** ~120 lines added · zero lines removed · zero lines modified.

---

### 2.3 `backend/engines/walk_forward_engine.py` (ADDITIVE companion function)

**New companion function at end of file:**
```python
def regime_coverage_summary(
    windows: list[dict],
    classify_window_prices: Optional[Callable[[list], str]] = None,
) -> dict:
    """SUPPLEMENT to run_walk_forward. Annotates per-window train_regime and
    oos_regime by classifying the price slices, then aggregates a regime
    distribution + Shannon entropy. Does NOT mutate `windows`.

    Returns:
        {
          "windows_summary": [
              {"window": int, "train_regime": str, "oos_regime": str}, ...
          ],
          "regime_distribution_oos": {trending: int, ranging: int, ...},
          "regime_entropy_oos":      float,
          "windows_total":           int,
        }
    """
```

**Constraints:**
- `classify_window_prices` defaults to `engines.regime_classifier.classify_regime`.
- Pure function. Does not call optimizer. Does not write anywhere.
- Original `run_walk_forward` byte-identical.

**Total LoC delta:** ~90 lines added · zero lines removed · zero lines modified.

---

## 3. Files NOT TOUCHED (operator-mandated discipline)

| File / surface | Reason untouched |
|---|---|
| `cbot_engine/ir_transpiler.py`, `ir_emitter.py`, `ir_templates.py`, `ir_parity_simulator.py` | Phase 28-C SEALED |
| `engines/ir_interpreter.py` | Phase 28-B canonical truth |
| `engines/strategy_ir.py`, `strategy_ir_builders.py`, `strategy_ir_renderer.py` | Phase 28-A schema sealed |
| `engines/ir_telemetry.py` | Phase 28 Telemetry sealed |
| `engines/mutation_engine.py` | Phase 28-B++ cross-cycle continuity sealed |
| `engines/bi5_realism.py` | Phase 27.3/27.4 sealed; regime-conditioned BI5 is a Phase 29.2 candidate |
| `engines/orchestrator_scheduler.py`, `auto_scheduler.py`, `ai_orchestrator.py` | G2 sealed; **no new scheduler rule** in 29.0 |
| `engines/strategy_lifecycle.py::_gate_*` bodies | All seven gates untouched (operator decision #1 — advisory only) |
| `engines/oos_holdout.py::run_oos_holdout` | Original 80/20 byte-identical (operator decision #3) |
| `engines/walk_forward_engine.py::run_walk_forward` | Original byte-identical |
| `engines/portfolio_engine.py`, `portfolio_builder_engine.py` | Phase 31 territory |
| `engines/evolution_engine.py` | Phase 16/33 territory |
| `engines/auto_selection_engine.py::_compute_deploy_score` | Phase 31/Phase-29-followup territory |
| `engines/regime_classifier.py` | Phase 16 sealed; reused via import only |
| All frontend files | UI surface deferred to 29.1 after operator review of `regime_evidence` JSON shape |
| All `.env` files | No new env vars |
| Scheduler persistence (`orchestrator_scheduler_config`, `auto_scheduler_config`) | Both stay `enabled: false` |

---

## 4. Data-shape contracts (frozen for 29.0)

### 4.1 `regime_evidence` block (additive on `lifecycle.evidence`)
```json
{
  "regime_evidence": {
    "per_regime": {
      "trending":         {"n_runs":int,"trades_total":int,"pf_mean":float|null,
                           "pf_cov":float|null,"dd_pct_max":float|null,
                           "win_rate_mean":float|null,"return_pct_mean":float|null,
                           "sample_adequate":bool,"edge_positive":bool},
      "ranging":          { ... same shape ... },
      "high_volatility":  { ... same shape ... },
      "low_volatility":   { ... same shape ... },
      "unknown":          { ... same shape — never feeds breadth_count ... }
    },
    "regimes_seen":     ["trending","ranging"],
    "regimes_adequate": ["trending","ranging"],
    "regimes_breadth":  ["trending"],
    "breadth_count":    1,
    "fragile":          true,
    "computed_at":      "2026-02-XXTHH:MM:SS+00:00",
    "phase":            "29.0",
    "advisory_only":    true
  }
}
```

**Schema-stability guarantee:** `per_regime` ALWAYS has all 5 keys (4 canonical + `unknown`); when a regime has zero observations the value is the shape above with `n_runs=0, sample_adequate=False, pf_mean=null`. Never a missing key.

### 4.2 `LIFECYCLE_FLAGS` taxonomy after 29.0
```python
LIFECYCLE_FLAGS = {
    "PARTIAL_REALISM",
    "BI5_FAIL",
    "STALE",
    "MANUALLY_OVERRIDDEN",
    "BI5_DATA_MISSING",
    "REGIME_FRAGILE",     # NEW · advisory only · no stage cap
}
```

### 4.3 API response stability
All three new endpoints return JSON with stable top-level keys + `phase: "29.0"` + `advisory_only: true` so consumers can distinguish 29.0 advisory mode from any future hard-gate mode.

---

## 5. Trust-gate ledger (target 45 tests across 4 test files)

| Test file | Tests | Tier coverage |
|---|---|---|
| `test_regime_layer.py` | 32 | Determinism · Honest refusal · Sample-adequacy semantics · Flag emission · Lifecycle integration (backward-compat critical) · API contract · Schema stability |
| `test_regime_oos_stratified.py` | 8 | Leakage guard · Per-regime split correctness · Honest refusal on insufficient regime samples · Original-function byte-identity |
| `test_walk_forward_regime_coverage.py` | 5 | Entropy semantics · Empty-windows edge · No-mutation guarantee · Original-function byte-identity |
| **Regression sweep (re-run, must stay green)** | 242 existing + 45 new = **287 / 287** | Phase 28 (147), Phase 26.5 lifecycle (existing), Phase 26.5 lifecycle edge, G1, G2, G6, BI5 27.3/27.4, IR telemetry, backtest correctness, orchestrator scheduler, all phase tests |

**Acceptance criterion:** Phase 29 implementation is NOT considered complete until:
- 45/45 new tests pass.
- All 242 prior tests pass byte-identical (no flake-and-skip).
- A line-diff between pre-29 and post-29 `oos_holdout.py::run_oos_holdout` source is empty.
- A line-diff between pre-29 and post-29 `walk_forward_engine.py::run_walk_forward` source is empty.
- All seven `_gate_*` functions in `strategy_lifecycle.py` byte-identical (verified by AST-walk in a regression test).

---

## 6. Reversibility plan

Drop the four added files (`engines/regime_performance.py`, `api/regime.py`, plus three new test files) AND revert these additive edits in three files:
- `engines/strategy_lifecycle.py`: remove the `"REGIME_FRAGILE"` set member; remove the `_compute_regime_evidence_block` helper; remove the 2-line append inside `compute_lifecycle_state`.
- `engines/oos_holdout.py`: remove the `run_oos_holdout_regime_stratified` function (last ~120 LoC).
- `engines/walk_forward_engine.py`: remove the `regime_coverage_summary` function (last ~90 LoC).
- `server.py`: remove the `regime_router` registration line (the only mount-point change).

After reversal, `python -c "from engines import strategy_lifecycle; ..."` produces identical behaviour to pre-29. The `regime_evidence` block, if any persisted to `strategy_lifecycle.evidence`, becomes dead JSON — harmless, never read, no downstream consumer breaks.

---

## 7. Sequencing (six commits, each independently revertible)

| # | Commit | Touches | Tests added | Cumulative regression |
|---|---|---|---|---|
| 1 | Add `engines/regime_performance.py` (pure, no consumers yet) | 1 NEW file | 0 (engine has no consumers yet — test in commit #4) | 242/242 |
| 2 | Add `engines/oos_holdout.py::run_oos_holdout_regime_stratified` companion | 1 EXT file (additive) | `test_regime_oos_stratified.py` 8 tests | 250/250 |
| 3 | Add `engines/walk_forward_engine.py::regime_coverage_summary` companion | 1 EXT file (additive) | `test_walk_forward_regime_coverage.py` 5 tests | 255/255 |
| 4 | Add `regime_evidence` block + `REGIME_FRAGILE` flag to `strategy_lifecycle.py` | 1 EXT file (additive) | `test_regime_layer.py` Tier 1–5,7 = 27 tests | 282/282 |
| 5 | Add `api/regime.py` router + mount in `server.py` | 1 NEW + 1 EXT | `test_regime_layer.py` Tier 6 = 4 tests + manual curl probes | 286/286 |
| 6 | Add `memory/PHASE_29_PLAN.md` + `memory/PHASE_29_COMPLETE.md` | 2 NEW memory files | 0 (docs) | 286/286 |

Each commit can be reverted individually without breaking subsequent ones — Phase 29 is **fully decomposable**.

---

## 8. Open risks & guardrails

| Risk | Guardrail |
|---|---|
| Silent backfill on legacy 167 strategies via lifecycle re-evaluation cron | Phase 29.0 adds NO scheduler rule. `evaluate_cohort` already runs every tick once schedulers turn on; **this is acceptable because schedulers are persisted OFF**. When operator enables them later, the next tick will compute `regime_evidence` for the cohort lazily — **but only writes when stage changes OR first-touch is true**. Since 29.0's evidence is advisory and STAGE decision is unchanged, no spurious lifecycle history rows fire. Audited in `test_regime_layer.py` Tier 5. |
| Cache poisoning / stale `regime_evidence` on lifecycle docs | `regime_evidence.computed_at` ISO timestamp surfaces freshness. `phase: "29.0"` + `advisory_only: true` field marks evidence-mode for future migrations. |
| Performance hit from per-tick history scan | `evaluate_cohort` already loads rollup + bulk lifecycle lookups; adding `compute_regime_performance` per row is O(N) over history rows. For 167 strategies × ~5 history rows avg = ~835 row-evaluations per tick → trivial. Tested in Tier 1 with 5000-row fixture for determinism timing. |
| Operator misreading "advisory" as "informational only — safe to ignore" | API responses + lifecycle doc + memory docs all stamp `advisory_only: true` AND `phase: "29.0"`. Phase 29.1 (operator-decision-gated) is the moment that flips to false — single git commit, single field flip, audit-loud. |
| Regime taxonomy drift (e.g., classifier adds 5th regime) | `REGIMES_CANONICAL` is a tuple constant. Schema stability test (Tier 7) asserts the set. If Phase 16 classifier ever adds a regime, Phase 29 schema needs a coordinated version bump → new `phase: "29.X"` discriminator + migration plan. |
| Walk-forward regime entropy misinterpreted as a quality signal | Documented in module docstring: "entropy alone is not edge — a strategy with high regime entropy AND uniformly losing across regimes is uniformly bad, not uniformly robust." Phase 30 will fold this signal into fragility scoring; Phase 29 only exposes the raw number. |

---

## 9. Out-of-scope deferrals (Phase 29.1+ candidates)

- **29.1 — Promotion impact decision.** Should `REGIME_FRAGILE` cap promotion at `prop_safe`? Empirical evidence from 29.0's telemetry distributions informs this.
- **29.2 — Regime-conditioned BI5 realism.** Single-PF BI5 ratio decomposed per regime. Requires BI5 data ingested + regime-tagged.
- **29.3 — Regime-aware `_compute_deploy_score`.** Move from single-pool to regime-weighted blend in `auto_selection_engine`. Requires Phase 30 robustness signals to land first.
- **29.4 — Regime UI surface.** Explorer chip / Details panel pill / Dashboard cohort distribution. Backend evidence JSON must stabilise first.
- **29.5 — Regime-stratified OOS as `_gate_validated` input.** Promotion from "supplement" to "replacement" of the 80/20 path. Requires multi-week observation that stratified OOS produces correlated-but-not-redundant signal vs 80/20.

---

## 10. Estimated total impact

| Metric | Value |
|---|---|
| New files (code) | 2 (`engines/regime_performance.py` + `api/regime.py`) |
| New files (tests) | 3 |
| New files (memory) | 1 plan + 1 complete = 2 |
| Existing files extended | 4 (`strategy_lifecycle.py` + `oos_holdout.py` + `walk_forward_engine.py` + `server.py` router mount) |
| LoC added (production) | ~555 |
| LoC added (tests) | ~810 |
| LoC removed | **0** |
| LoC modified | **0** (only additions inside dicts/lists, no rewrites) |
| Sealed surfaces touched | **0** |
| Schedulers added | **0** |
| New env vars | **0** |
| Frontend changes | **0** in 29.0 |
| Backward-compat regression budget | **0 failed tests** in 242 existing |

---

## 11. Final sign-off checklist (operator presents `proceed` to authorise)

- [ ] §0 operator-decisions table is correct
- [ ] §1.1 `regime_performance.py` public surface is correct (constants, dataclass, function signature)
- [ ] §1.2 three GET endpoints are the right operator-facing surface (no PATCH/POST)
- [ ] §2.1 strategy_lifecycle additive edits are within the "no-existing-line-touched" discipline
- [ ] §2.2 + §2.3 supplement functions on `oos_holdout` and `walk_forward_engine` are properly bounded
- [ ] §4 data-shape contracts (regime_evidence schema + flag taxonomy) acceptable
- [ ] §5 trust-gate ledger of 45 new tests + 242 regression → 287/287 is the acceptance bar
- [ ] §7 commit sequencing OK to execute as a single Phase-29.0 implementation pass

If any checkbox is unclear, operator should request a refinement before authorising. **No code written until checklist is approved.**
