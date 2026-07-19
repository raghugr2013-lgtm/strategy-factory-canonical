# Phase 28-A — Strategy-IR Foundation — COMPLETE

**Date:** 2026-05-13
**Status:** ✅ Schema + builders + renderer + mutation IR emission + 35 tests pass
**Discipline:** additive · reversible · lifecycle-safe · orchestration-safe · discovery-isolated · zero placeholder signals

## What landed

| Phase A artefact | File | Lines | Status |
|---|---|---|---|
| IR Pydantic schema + operator vocabulary | `backend/engines/strategy_ir.py` | 332 | ✅ lint clean |
| Per-mutation IR builders (7 root + 5 composer + risk_reward) | `backend/engines/strategy_ir_builders.py` | 365 | ✅ lint clean |
| IR → human-readable renderer | `backend/engines/strategy_ir_renderer.py` | 153 | ✅ lint clean |
| Mutation engine additive `_attach_ir` shim (2 splice points) | `backend/engines/mutation_engine.py` | +52 / −0 | ✅ lint clean (pre-existing E702s unchanged) |
| Schema invariant tests | `backend/tests/test_strategy_ir_schema.py` | 230 | ✅ 20/20 pass |
| Mutation emits IR tests | `backend/tests/test_mutation_emits_ir.py` | 180 | ✅ 15/15 pass |

**Total:** ~1310 LoC added · 1 splice block in existing code · 0 deletions · 0 signature changes.

## Operator-locked decisions encoded

| # | Decision | Implementation |
|---|---|---|
| 1 | IR scope = existing mutation vocabulary only | `_TF_TO_PANDAS` + 8 operator categories cover every existing `_mut_*` function; no regime / no state-machine extensions |
| 2 | LLM does NOT generate executable logic | All builders are hand-written deterministic Python; no LLM calls anywhere in the IR path |
| 3 | Legacy cohort = `ir_status: "legacy"` | Composer mutations (`filter_add_*`, `mtf_htf_*`, `filter_remove_rsi`, `risk_reward_*`) emit `ir_status="legacy"` when no base IR is threaded through; existing 70 library strategies are untouched and will be flagged `legacy` by future migration |
| 4 | Curated parameter exposure | Schema declares only essential params per indicator; cBot transpiler in Phase C consumes this list |
| 5 | Strict A → B → C ordering | Phase A is foundation only — no interpreter, no transpiler. `engines/backtest_engine.py` is **completely untouched** |
| 6 | Trust gate ±2% PF · ±5% DD · exact trades | Reserved for Phase B; documented in `strategy_ir.py` module docstring |

## Architectural promise — held

| Promise | Evidence |
|---|---|
| **Additive** | Every `_mut_*` function returns the same dict shape as before, with `strategy_ir`, `ir_status`, `ir_version` appended. `strategy_text` and `parameters` unchanged. |
| **Reversible** | Single-commit revert: drop the 3 new files + revert the 52-line shim block. Existing strategies travel unchanged. |
| **Lifecycle-safe** | `engines/strategy_lifecycle.py` not touched. Gates, hysteresis, cool-downs unchanged. |
| **Orchestration-safe** | `engines/ai_orchestrator.py`, `engines/orchestrator_scheduler.py`, `engines/auto_scheduler.py` not touched. |
| **Discovery-isolated** | `engines/multi_cycle_runner.py`, `engines/auto_factory*`, `engines/optimization_engine.py`, `engines/validation_engine.py`, `engines/oos_holdout.py`, `engines/walk_forward_engine.py`, `engines/env_priority.py`: zero changes. |
| **Backtest untouched** | `engines/backtest_engine.py` is bit-identical. The IR currently does not participate in any backtest. Phase B will introduce the interpreter behind a flag. |
| **BI5 separation preserved** | Phase 27.4 work untouched. The IR is strategy-level; it has zero interaction with the data-source separation. |
| **No placeholder signals** | The IR is genuine executable structure — predicate trees with finite operator vocabulary, indicator declarations, exit specs, risk block. Nothing in the IR module produces dummy outputs. |

## IR vocabulary — frozen for Phase A

```
LOGICAL    : AND, OR, NOT
COMPARISON : GT, LT, GE, LE, EQ, NEQ
CROSS      : CROSS_UP, CROSS_DOWN
RANGE      : RANGE_BREAK_UP, RANGE_BREAK_DOWN
TIME       : AT_TIME, IN_GMT_WINDOW
BAND       : BAND_TOUCH_UPPER/LOWER, BAND_BREAK_UPPER/LOWER
VOLATILITY : ATR_RATIO_ABOVE
HTF        : HTF_SLOPE_UP, HTF_SLOPE_DOWN
SQUEEZE    : BB_SQUEEZE_PERCENTILE

INDICATORS : EMA, RSI, ATR, BOLLINGER, HTF_EMA
EXIT       : pips, atr_mult, range_fraction, band_mid, indicator_cross
           + optional time_exit (close_all_gmt)
SESSION    : gmt_window (open / close / force_flat_at)
RISK       : percent_of_balance (capped at 10%)
```

## Mutation coverage matrix

| Mutation type | IR coverage Phase A | Reason |
|---|---|---|
| `trend_pullback` | ✅ ir_native | Root builder |
| `session_london_breakout` | ✅ ir_native | Root builder |
| `session_asian_range` | ✅ ir_native | Root builder |
| `volatility_atr_breakout` | ✅ ir_native | Root builder |
| `volatility_bollinger_squeeze` | ✅ ir_native | Root builder |
| `mean_reversion_rsi` | ✅ ir_native | Root builder |
| `mean_reversion_bollinger` | ✅ ir_native | Root builder |
| `filter_add_rsi` | ⏸ legacy (Phase B target) | Composer needs base IR threading |
| `filter_add_volatility` | ⏸ legacy (Phase B target) | Composer needs base IR threading |
| `filter_add_trend` | ⏸ legacy (Phase B target) | Composer needs base IR threading |
| `mtf_htf_confirmation` | ⏸ legacy (Phase B target) | Composer needs base IR threading |
| `filter_remove_rsi` | ⏸ legacy (Phase B target) | Composer needs base IR threading |
| `risk_reward_1_1`, `risk_reward_1_1_5`, `risk_reward_1_2` | ⏸ legacy (Phase B target) | Composer needs base IR threading |

**Phase A success metric: 7/7 root mutations emit valid IR.** ✅

## Test results

```
NEW Phase 28-A tests:    35 / 35 PASS
Phase 27.4 BI5 suite:    28 / 28 PASS (no regression)
Lifecycle phase 26.5:    PASS (no regression)
G6 progression:          21 / 22 PASS (1 pre-existing test-isolation
                         failure — db pollution from real-data lifecycle
                         rows drowning out test fixtures at limit=20;
                         unrelated to Phase 28-A)
G2 subordination:        PASS (no regression)
G1 research_lineage:     PASS (no regression)
Orchestrator scheduler:  PASS (no regression)
Data-access recovery:    PASS (no regression)
Data pipeline regression:PASS (no regression)
Data load endpoint:      PASS (no regression)
─────────────────────────────────────────────
                       138 / 139 PASS  +  35 NEW = 173 total
```

The single failure is a **pre-existing test isolation bug** — the test seeds
2 `TEST_G6_feed_*` rows then queries `recent_transitions(limit=20)`, but the
real `strategy_lifecycle_history` collection (511 rows from autonomous
emergence) drowns out the test fixtures. This is a fixture-isolation issue
in the test, NOT a regression from Phase 28-A code. The test was passing
when the collection was empty; it fails now that real data exists.

## Architectural posture — ready for Phase B

| Item | State |
|---|---|
| IR schema | Frozen at `IR_VERSION=1`. Operator vocabulary covered. |
| Mutation engine emits IR | ✅ 7/7 root mutations. Composer threading reserved for Phase B. |
| Backtest engine | Untouched. Still dispatches to the 4 legacy signal functions. |
| cBot generator | Untouched (still emits the offline-mode stub). Phase C territory. |
| Library docs | Will start carrying `strategy_ir` field on the *next* mutation cycle. Existing 70 strategies remain `strategy_ir=None`. |
| Lifecycle / orchestrator / BI5 / scheduler | Untouched. |
| Backwards compat | 100%. Every legacy consumer continues working. |

## What Phase B will do (NOT this phase)

1. Build `engines/ir_interpreter.py` — pure-function evaluator over the IR
   that produces signal series consumable by `backtest_engine.run_backtest_logic`.
2. Add a single branch in `_signal_at(i)`:
   ```python
   if strategy_profile.get("strategy_ir"):
       return ir_interpreter.signal_at(i)
   else:
       return _legacy_dispatch(i)   # current 4-function path
   ```
3. Trust-gate validation: build 4 reference IRs equivalent to the legacy
   `trend_following / mean_reversion / momentum / breakout` shapes, backtest
   the same strategy via both paths, assert PF parity within ±2%, DD parity
   within ±5%, exact trade count match.
4. Thread the base IR through `mutate_strategy_*` callers so composer
   mutations (filter_add_*, mtf_htf_*, etc.) become `ir_native`.
5. Zero changes to lifecycle, orchestrator, BI5, schedulers.

## What Phase C will do (NOT this phase)

Build `cbot_engine/ir_transpiler.py` — deterministic IR→C# emitter with one
template per operator. Replaces the offline-mode stub. Curated parameter
exposure per operator decision.

## Live verification (post-restart)

```
backend health     : ✓ /api/health 200
backend boot       : ✓ all 4 startup hooks fired
schedulers         : ✓ both still disabled (per pre-deploy discipline)
mutation_engine    : ✓ imports cleanly with new shim
strategy_ir module : ✓ imports cleanly; Pydantic v2 validation works
no service restart : ✓ frontend untouched; supervisor frontend RUNNING
```

🟢 **Phase 28-A landed cleanly. The factory now has a canonical rule
representation for every new strategy that emerges from the 7 root
mutators. Standing by for Phase B (interpreter + trust gate) on your
signal.**
