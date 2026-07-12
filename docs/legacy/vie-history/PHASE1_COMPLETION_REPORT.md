# P0B Phase 1 — Completion Report

**Scope**: BI5 Certification, Phase 1 — *pure-function* evaluators
(tick validation, spread analysis, slippage model, execution simulator).

**Working directory**: `/app/_review/deployment-ready/source/backend_main/backend/`

**Date**: 2026-01

---

## 1. Files Added

| Path                                                | Purpose                                                                 |
| --------------------------------------------------- | ----------------------------------------------------------------------- |
| `tests/test_slippage_model.py`                      | Unit tests for `engines/slippage_model.py` (§3).                        |
| `tests/test_execution_simulator.py`                 | Unit tests for `engines/execution_simulator.py` (§4).                   |
| `PHASE1_COMPLETION_REPORT.md`                       | This report.                                                            |

## 2. Files Modified

| Path                                | Change                                                                                                                                                                                                              |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `engines/tick_validator.py`         | `aggregate_window` — replaced rate-amortised `decode_fail` integrity formula with a categorical collapse: any `hours_decode_fail > 0` ⇒ `integrity = 0.0`. Clean-hour formula now `1 − (non_mono + zero_vol) / ticks_total`. |

No other production files were touched. The fix is a 3-line semantic
replacement inside `aggregate_window` with a comment explaining intent.

## 3. Public Functions Audited (Phase 1)

All four modules are BI5-side pure evaluators. No new public surface
was added in Phase 1 — only behavior corrections + test coverage.

### `engines/tick_validator.py`
- `classify_session(hour_utc) -> str`
- `validate_hour(ticks, *, hour_utc, symbol, status, prev_60m_sigma, reference_mid) -> HourValidation`
- `aggregate_window(hour_validations, *, weights=DEFAULT_WEIGHTS) -> BI5ScoreReport`
- Constants: `DEFAULT_WEIGHTS`, `DENSITY_TABLE`, `SESSION_BOUNDS_UTC`, `PASS_THRESHOLD`, `WARN_THRESHOLD`, `PRICE_OUTLIER_Z`, `EVALUATOR_VERSION`

### `engines/spread_analyzer.py`
- `get_tolerance_bps(symbol) -> float`
- `rollup_spread_minutes(ticks, *, symbol) -> List[SpreadBar]`
- `compute_spread_score(*, fill_spread, mid, assumed_cost_bps, tolerance_bps, symbol=None) -> SpreadScoreResult`
- `spread_score_from_fills(fills, *, symbol, assumed_cost_bps, tolerance_bps=None) -> SpreadScoreResult`
- Constants: `DEFAULT_TOLERANCE_BPS`, `SYMBOL_DEFAULT_BPS`, `EVALUATOR_VERSION`

### `engines/slippage_model.py`
- `rolling_adv_per_minute(volumes_per_minute, *, window=60) -> List[float]`
- `compute_slippage(*, side, bid, ask, mid_before, mid_after, order_size, adv_per_minute, k_impact=K_IMPACT, alpha=ALPHA) -> SlippageBreakdown`
- `slippage_score(*, fills, assumed_slippage_bps, tolerance_bps=TOLERANCE_BPS, k_impact=K_IMPACT, alpha=ALPHA) -> SlippageScoreResult`
- Constants: `K_IMPACT`, `ALPHA`, `TOLERANCE_BPS`, `EVALUATOR_VERSION`

### `engines/execution_simulator.py`
- `get_profile(name) -> VenueProfile`
- `pick_decision_tick(ticks, t_signal) -> Optional[Tick]`
- `pick_fill_tick(ticks, t_signal, delta_latency_ms, *, gap_max_ms=GAP_MAX_MS) -> Optional[Tick]`
- `sample_latency_ms(profile, *, rng=None) -> float`
- `simulate_fill(*, ticks, t_signal, side, order_size, adv_per_minute, profile, rng=None, k_impact, alpha) -> FillResult`
- `simulate_fills(signals, *, ticks, profile, adv_per_minute, rng=None, k_impact, alpha) -> ExecutionReport`
- Constants: `VENUE_PROFILES`, `GAP_MAX_MS`, `EVALUATOR_VERSION`

## 4. Tests Added

| File                                      | New tests | Notes                                                                                          |
| ----------------------------------------- | --------: | ---------------------------------------------------------------------------------------------- |
| `tests/test_slippage_model.py`            |        23 | Newly authored. Covers `rolling_adv_per_minute`, `compute_slippage` (incl. invalid-arg guards), `slippage_score` (incl. p95 vs. median, k_impact/alpha sensitivity). |
| `tests/test_execution_simulator.py`       |        20 | Newly authored. Covers profile lookup, latency sampler bounds, tick-walk helpers, single-fill paths (filled / no decision / no liquidity), population scoring incl. score-collapse on all-no-quote and rejection penalty. |

### Tests Pre-existing (Phase 1 surface)
| File                                      | Tests |
| ----------------------------------------- | ----: |
| `tests/test_tick_validator.py`            |    23 |
| `tests/test_spread_analyzer.py`           |    12 |

## 5. Total Tests Executed

```text
collected 78 items
tests/test_tick_validator.py        23 passed
tests/test_spread_analyzer.py       12 passed
tests/test_slippage_model.py        23 passed
tests/test_execution_simulator.py   20 passed
============================== 78 passed in 0.54s ==============================
```

## 6. Pass / Fail Counts

- **78 passed**
- **0 failed**
- **0 skipped**
- Runtime: ~0.6 s

## 7. Failing-Test Resolution (handoff item)

**Test**: `test_aggregate_window_decode_fail_collapses_integrity`

**Before fix**: `integrity = 0.9615` (assertion expected `< 0.05`).

**Root cause**:
`aggregate_window` was computing
```python
integrity_denom = max(1, ticks_total + hours_decode_fail * 1_000)
integrity = 1.0 - ((non_mono + zero_vol + hours_decode_fail * 1_000) / integrity_denom)
```
This treats each `decode_fail` as ≈1 000 *amortised* broken ticks. When
there are abundant clean ticks (25 000), the broken-tick *rate* gets
diluted and integrity stays ≈0.96. This contradicts:

1. The test name + assertion ("collapses_integrity", `< 0.05`).
2. The BI5 firewall ethos — a corrupt Dukascopy payload cannot be
   trusted; the hour is not certifiable.
3. The geometric-mean design already used in `aggregate_window`
   ("any zero collapses the score"), mirroring the `density == 0`
   treatment for fully-sparse windows.

**Decision**: Implementation was wrong, test is correct.

**Fix applied** (`engines/tick_validator.py` `aggregate_window`):
```python
if hours_decode_fail > 0:
    integrity = 0.0
elif ticks_total:
    integrity = 1.0 - ((non_mono + zero_vol) / ticks_total)
else:
    integrity = 1.0
```

**After fix**: `integrity = 0.0` (well below `0.05`). Geometric mean
correctly collapses the entire BI5 score to 0.0 ⇒ verdict = FAIL,
which is the certification-correct outcome for a corrupt window.

**Regression check**: all other `aggregate_window` tests continue to
pass (clean-data PASS verdict, sparse-density WARN/FAIL, weight
plumbing, etc.).

## 8. Dependency Diagram (Phase 1 only)

```
                ┌──────────────────────────┐
                │ engines/tick_validator.py│   (no intra-engine deps)
                └──────────────────────────┘
                              ▲
                              │ stdlib only
                              │ (dataclasses, datetime, math, typing)

                ┌──────────────────────────┐
                │ engines/spread_analyzer  │   (no intra-engine deps)
                └──────────────────────────┘
                              ▲
                              │ stdlib only
                              │ (dataclasses, datetime, statistics, typing)

                ┌──────────────────────────┐
                │ engines/slippage_model   │   (no intra-engine deps)
                └──────────────────────────┘
                              ▲
                              │ stdlib only
                              │ (dataclasses, statistics, typing)

                ┌──────────────────────────────┐
                │ engines/execution_simulator  │
                └──────────────────────────────┘
                              │
                              │ imports
                              ▼
                ┌──────────────────────────┐
                │ engines/slippage_model   │   (K_IMPACT, ALPHA,
                └──────────────────────────┘    compute_slippage,
                                                SlippageBreakdown)
```

External deps: `math`, `random`, `dataclasses`, `datetime`,
`statistics`, `typing`. **No third-party libraries.**

## 9. Firewall Confirmation

Audited each Phase 1 module for forbidden imports / IO. Results:

| Check                                                            | Status |
| ---------------------------------------------------------------- | :----: |
| No MongoDB client (`pymongo`, `motor`)                           |   ✅   |
| No HTTP clients (`requests`, `httpx`, `urllib`, `aiohttp`)       |   ✅   |
| No filesystem IO (`open`, `pathlib`, `read_text`, `write_text`)  |   ✅   |
| No imports from `api/*`                                          |   ✅   |
| No imports from `discovery` / `mutation` / `validation`          |   ✅   |
| No imports from `pass_probability`                               |   ✅   |
| No imports from `challenge_matching_engine` / `matching_engine`  |   ✅   |
| No imports from `portfolio_*` / `phase30_*`                      |   ✅   |
| No imports from `data_engine` (ingestion / archive / runner)     |   ✅   |
| FastAPI / SQLAlchemy / ORMs                                       |   ✅   |

Verification commands (run from `backend/`):
```bash
grep -nE "^(import|from) +(engines\.(discovery|mutation|validation|pass_probability|challenge|matching_engine|portfolio|phase30|gem_factory|market_universe|data_engine)|api|pymongo|motor|requests|httpx|urllib|aiohttp|fastapi|sqlalchemy)" \
  engines/{tick_validator,spread_analyzer,slippage_model,execution_simulator}.py

grep -nE "(open\(|Path\(|os\.path|pathlib|read_text|write_text|requests\.|urlopen)" \
  engines/{tick_validator,spread_analyzer,slippage_model,execution_simulator}.py
```
Both grep commands return zero matches.

Intra-Phase-1 import: `execution_simulator` imports
`compute_slippage`, `SlippageBreakdown`, `K_IMPACT`, `ALPHA` from
`slippage_model` — this is an *intra-Phase-1* dependency and does
**not** breach the firewall.

## 10. Open TODO(P1) — Symbol & Calibration Migration

Located via `grep -nE "TODO\(P1"` inside the four Phase 1 modules:

| Module                   | TODO(P1)                                                                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `tick_validator.py`      | `DENSITY_TABLE` and `SESSION_BOUNDS_UTC` are local constants for the P0B seed. Move them to `market_universe` once it is the single source of truth (R0–R5 promotion). |
| `tick_validator.py`      | Coarse hour bands; per-symbol DST-aware calendar deferred to P1 calendar via `market_universe`.                                                |
| `spread_analyzer.py`     | `DEFAULT_TOLERANCE_BPS` and `SYMBOL_DEFAULT_BPS` belong with the symbol registry; migrate to `market_universe`.                                |
| `slippage_model.py`      | `K_IMPACT`, `ALPHA`, `TOLERANCE_BPS` are P0B-seed constants. Move to per-symbol calibration history in `market_universe` once available.       |
| `execution_simulator.py` | `VENUE_PROFILES` is a P0B seed. Defaults should be persisted via the existing `api/admin_execution_realism.py` upsert path and resolved from Mongo. |

These are explicit deferred items per the locked architectural
decisions: BI5 modules stay self-contained until R0–R5
`market_universe` promotion lands.

## 11. Open TODO(P0B Phase 2) — Persistence & Adapters

Items deferred from Phase 1, explicitly out of scope:

1. **`engines/execution_simulator.py` — Phase 2 wiring**
   - Wire `VENUE_PROFILES` defaults into
     `api/admin_execution_realism.py` upsert path.
   - Loop `simulate_fill` from the BI5 certification orchestrator
     (`engines/bi5_certification.py` — to be authored in Phase 3).

2. **Spread-bar persistence**
   - `rollup_spread_minutes` returns `List[SpreadBar]`. Phase 2 must
     persist these into `market_spread` collection (no Mongo writes
     from Phase 1 modules themselves — kept pure on purpose).

3. **BI5 score persistence**
   - `aggregate_window` returns `BI5ScoreReport`. Phase 2 introduces
     the storage adapter that writes one row per `(symbol, window)`
     into `bi5_certification` collection, derived BI5 1m bars into
     `(symbol, "bi5", "1m")`, and leaves raw BI5 on the filesystem
     archive (Tier-1) per the locked Hybrid Architecture.

4. **Calibration loop for slippage**
   - Phase 2 introduces a calibration job that re-fits `k_impact` and
     `alpha` from observed paper-trading slippage and persists the
     symbol-level fit. The fitted values flow back into
     `slippage_score(..., k_impact=..., alpha=...)` calls.

5. **Strict typing on `Tick` protocol**
   - Phase 1 functions accept duck-typed tick objects (anything with
     `.ts_utc`, `.bid`, `.ask`, optionally `.bid_volume`, `.ask_volume`).
     Phase 2 should formalise a `Tick` Protocol/TypedDict so adapter
     boundaries are statically checkable.

---

## Phase 1 — APPROVED FOR HANDOFF

All Phase 1 acceptance criteria met:

- [x] Original failing test resolved with documented RCA + impl fix.
- [x] All four required test files exist:
      `test_tick_validator.py`, `test_spread_analyzer.py`,
      `test_slippage_model.py`, `test_execution_simulator.py`.
- [x] Phase 1 pytest suite: **78 passed / 0 failed**.
- [x] Firewall: zero Mongo / API / filesystem / forbidden-domain
      dependencies in any Phase 1 module.
- [x] Dependency diagram captured.
- [x] Open TODO(P1) and TODO(P0B Phase 2) catalogued for downstream
      handoff.

**Per the handoff brief: stop here and wait for approval before
beginning P0B Phase 2 (Persistence & Adapters).**
