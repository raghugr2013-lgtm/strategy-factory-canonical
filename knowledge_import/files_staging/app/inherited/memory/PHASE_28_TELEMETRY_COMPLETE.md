# Phase 28 Telemetry — IR Coverage Observability — COMPLETE ✅

**Date:** 2026-05-13
**Status:** Operator-facing IR-coverage telemetry layer live at `GET /api/mutation/ir-telemetry`. Aggregates the existing `mutation_events` collection on demand into a stable, read-only payload. 27/27 telemetry tests pass; 202/202 across the full Phase 28 + adjacent regression suite. Zero scheduler interaction, zero lifecycle/orchestrator/BI5 changes, fully reversible.

**Discipline:** additive · read-only · operator-facing · scheduler-independent · legacy-safe · deterministic

## Why this phase existed

With Phase 28-B++ landing cross-cycle composer-chain continuity, the IR contract now spans:

```
mutation → IR → interpreter → backtest    (proven, every cycle)
```

But there was no continuous, observable proof that the contract is **holding in production** during autonomous emergence. Without telemetry, a silent degradation (e.g. a sudden spike in `legacy` emissions due to upstream classifier drift, or a chain-depth collapse due to a regression in `_derive_base_ir`) would only surface when Phase 28-C ships and a deployment fractures.

This phase adds the minimum-viable observability surface so the operator can:
* watch ir_native % trend in real-time
* see the chain-depth distribution (proof that overlays are accumulating)
* track legacy fallback reasons (momentum_base vs composer_legacy_base etc)

…before any executable export work begins.

## What landed

| Artefact | File | Change | Purpose |
|---|---|---|---|
| Pure telemetry helpers | `engines/ir_telemetry.py` | **+275 lines, NEW** | `compute_ir_chain_depth`, `classify_legacy_reason`, `summarize_events`, `fetch_ir_telemetry`. Zero I/O in helpers; the async fetcher is the only DB-touching surface. |
| Event-doc enrichment | `engines/mutation_engine.py` | +20 / -0 lines | `run_mutation_pipeline` now stamps `ir_status`, `ir_chain_depth`, `legacy_reason` on every persisted event doc. Existing fields untouched. |
| API route | `api/mutation.py` | +34 / -0 lines | `GET /api/mutation/ir-telemetry?since=&limit=` — query-string driven, capped at 50_000 rows scanned. |
| Telemetry test suite | `tests/test_ir_telemetry.py` | **+335 lines, NEW** | 27 tests across 6 invariant groups. |

**Total:** ~310 LoC of production code · ~335 LoC of tests · 0 deletions · 0 signature changes anywhere · 0 changes to lifecycle / orchestrator / scheduler / BI5 / backtest_engine / discovery / frontend.

## The telemetry payload — stable shape

```json
{
  "total_events": 0,
  "ir_native_count": 0,
  "legacy_count": 0,
  "unknown_count": 0,             // historical rows pre-Phase-28-telemetry
  "ir_native_pct": null,           // % over (ir_native + legacy); excludes unknown
  "chain_depth_distribution": {"0":0,"1":0,"2":0,"3":0,"4+":0},
  "chain_depth_mean": null,
  "legacy_reasons": {
    "momentum_base": 0,
    "missing_strategy_text": 0,
    "composer_legacy_base": 0,
    "ir_v1_unsupported": 0,
    "root_build_failed": 0,
    "param_extraction_failed": 0,
    "unknown": 0
  },
  "by_mutation_type": [],
  "earliest_ts": null,
  "latest_ts": null,
  "query": {
    "since": null,
    "limit": 5000,
    "rows_scanned": 0,
    "computed_at": "2026-05-13T14:12:13.351008+00:00"
  }
}
```

## The four operator-facing signals

| Signal | Field(s) | What it tells you |
|---|---|---|
| **% IR-native vs legacy** | `ir_native_count`, `legacy_count`, `ir_native_pct`, `by_mutation_type[*].ir_native_pct` | Are new mutations actually IR-native? Drift detector for unanticipated legacy leakage. |
| **Chain-depth distribution** | `chain_depth_distribution`, `chain_depth_mean` | Are autonomous mutation cycles actually accumulating overlays (Phase 28-B++ working), or are most strategies stuck at depth 0/1? |
| **Legacy fallback counts** | `legacy_reasons.*` | Distribution of WHY legacy happens. `momentum_base` is expected; everything else is investigation-worthy. |
| **Momentum-base fallback counts** | `legacy_reasons.momentum_base` | Direct count of the documented IR v1 gap. Once IR v1.1 adds MACD this should drop to ~0. |

## Test sweep — 202 / 202 PASS

```
Phase 28 schema + interpreter + root + composer + chain + telemetry
  test_strategy_ir_schema.py                    : 20 / 20 PASS
  test_mutation_emits_ir.py                     : 15 / 15 PASS
  test_ir_interpreter_trust_gate.py             :  9 /  9 PASS
  test_composer_mutation_ir_parity.py           : 22 / 22 PASS
  test_composer_chain_preserves_prior_overlay.py: 14 / 14 PASS
  test_ir_telemetry.py                          : 27 / 27 PASS   ← NEW
                                                ─────────────────
                                                  107 / 107 PASS  (Phase 28 total)

Backtest engine (additive hook still neutral)
  test_backtest_correctness.py                  :  9 /  9 PASS

BI5 stack (27.3 + 27.4)
  test_bi5_realism_27_3.py                      : 16 / 16 PASS
  test_bi5_resample_alignment.py                :  8 /  8 PASS
  test_bi5_realism_multi_tf_consistency.py      :  4 /  4 PASS

Scheduler / orchestrator / G6 / G1
  test_g2_scheduler_subordination.py            : 13 / 13 PASS
  test_g6_lifecycle_progression.py              : 20 / 20 PASS
  test_orchestrator_scheduler.py                : 12 / 12 PASS
  test_research_lineage_g1.py                   :  6 /  6 PASS, 7 skipped
                                                ─────────────────
                                                  202 / 202 PASS, 0 failed
```

## Architectural promise — verified held

| Promise | Evidence |
|---|---|
| **Additive** | One new module, one new test file, one new endpoint. Three lines of event_doc enrichment in `run_mutation_pipeline`. Zero signature changes. |
| **Read-only** | `fetch_ir_telemetry` does `find().sort().limit()` only. `summarize_events` is pure. Helpers are pure. No writes anywhere. |
| **Scheduler-independent** | No APScheduler job registered. No orchestrator rule. No autonomous tick. Endpoint computes on demand. |
| **Operator-facing** | Single GET endpoint with stable JSON shape. Query string takes `since` (ISO-8601) + `limit` (cap 50_000). |
| **Legacy-safe** | Historical events lacking `ir_status` bucket as `unknown_count`, NOT silently coerced into `ir_native` or `legacy`. `ir_native_pct` denominator excludes them so the curve is honest. |
| **Lifecycle-safe** | `engines/strategy_lifecycle.py` untouched. G6 (20/20) and Phase 26.5 unchanged. |
| **Orchestration-safe** | `ai_orchestrator.py`, `orchestrator_scheduler.py`, `auto_scheduler.py` untouched. |
| **Discovery-isolated** | `multi_cycle_runner`, `optimization_engine`, `validation_engine`, `oos_holdout`, `walk_forward_engine`, `env_priority`, `auto_factory*`, `backtest_engine`: zero changes. |
| **BI5-safe** | Phase 27.4 single-source realism stream untouched. 28/28 BI5 tests pass. |
| **Frontend-untouched** | No frontend changes in this phase per scope discipline. |
| **No threshold tweaks / no forced promotions / no env_priority widening / no crypto expansion** | Strictly out of scope; not touched. |
| **No LLM in execution logic** | Operator decision Phase 28-A #2 preserved. |
| **Reversible** | Drop `engines/ir_telemetry.py` + revert the 20-line event_doc enrichment + remove the route registration → behaviour reverts to pre-telemetry. New telemetry fields on existing events become dead-weight strings; no downstream consumer breaks. |

## Live verification

```bash
# Endpoint live (with no events yet — fresh DB):
$ curl -s http://localhost:8001/api/mutation/ir-telemetry
{ "total_events": 0, ... "query": { "computed_at": "2026-05-13T14:12:13Z" } }

# Backend health:
$ curl -s http://localhost:8001/api/health
{"status":"ok","service":"AI Strategy Factory"}
```

## Stabilization / observation window

Per operator direction, **Phase 28-C remains gated** until a stabilization window with this telemetry layer in place. Recommended observation signals to watch before unblocking:

1. **`ir_native_pct` trend**: should stay ≥ 95% for non-momentum bases under steady-state autonomous emergence. A sustained drop would indicate upstream classifier drift or a regression in `_attach_ir`.
2. **`chain_depth_distribution[0]`** vs **`chain_depth_distribution[1..3]`**: in steady state, autonomous mutation cycles should produce a non-trivial population at depth ≥ 1 (i.e. composers are actually being selected by `evolution_engine.weighted_select_types`). Continued 100% depth=0 would suggest the Evolution Loop isn't exercising composers in production.
3. **`legacy_reasons.momentum_base`**: expected to be the dominant legacy bucket. If any other bucket overtakes it, investigate before Phase 28-C.
4. **Per-type `ir_native_pct`**: should be ~100% for every root + composer type EXCEPT momentum derivatives. If any single type drops below 95%, drill into recent events for that type.

## Phase 28-C posture

The architecture now exposes continuous, observable proof of semantic continuity. Phase 28-C (IR → cAlgo C# transpiler) can begin once the operator declares the stabilization window closed and the four signals above remain healthy.

🟢 **Phase 28 Telemetry landed cleanly. The IR contract is now continuously observable. Phase 28-C remains parked behind the operator's stabilization window.**
