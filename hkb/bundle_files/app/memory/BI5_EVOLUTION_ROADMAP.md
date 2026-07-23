# BI5 Evolution Governance Roadmap

**Version:** 1.0
**Sealed:** 2026-05-16
**Status:** Roadmap + maturity-detection framework only — NO infrastructure evolution yet.
**Discipline:** additive · reversible · observable · anti-drift.

---

## Purpose & posture

This document is the **single institutional source of truth** for the
multi-phase evolution of the BI5 execution-realism layer. It does not
implement BI5-2 through BI5-6. It exists so the long-term execution-realism
roadmap cannot quietly drift or be forgotten under day-to-day work pressure.

**Operator authority is final.** The AI orchestrator MAY observe maturity
signals and report readiness. The AI orchestrator **MUST NEVER**
autonomously trigger phase transitions, fetch tick data, mutate storage
schemas, or activate replay infrastructure. Every phase transition is
an explicit operator decree.

---

## Current sealed state (baseline) — Phase 27.4

| Surface | Status |
|---|---|
| BI5 storage | Single-bucket `market_data{symbol, source="bi5", timeframe="1m"}` (OHLCV docs) |
| Realism evaluator | `engines/bi5_realism.py` reads 1m, resamples on demand |
| Ingestion routes | Soft-deprecation warning for non-1m BI5 ingest (still accepted) |
| UI | `DataUpload.js` still exposes TF dropdown for BI5 (semantic leakage) |
| Auto-maintenance | Per-TF BI5 maintenance (latent fragmentation footgun) |
| Tick storage | **None** |
| Tick replay | **None** |
| Microstructure modelling | **None** |
| cBot parity validation | **None** |

---

## Architectural dependency chain (must be honoured in order)

```
                BI5-1 (canonicalise ingestion)
                   │
                   ▼
                BI5-2 (tick storage substrate)
                   │
                   ▼
                BI5-3 (tick-derived realism)
                   │
                   ▼
                BI5-4 (tick replay engine)
                   │
                   ▼
                BI5-5 (spread / slippage / microstructure)
                   │
                   ▼
                BI5-6 (UI pivot)
```

Skipping levels is **forbidden**. BI5-4 cannot activate without BI5-3 in
production. BI5-5 cannot activate without BI5-4. UI (BI5-6) is intentionally
last so operators never operate on phantom data.

---

## Phase BI5-1 · Canonicalise ingestion semantics

### Purpose
Eliminate every BID/BI5 semantic-leakage point in the **current** codebase.
Lock BI5 storage to the single canonical bucket `(symbol, "bi5", "1m")`.
This is a clean-up phase, not a new-capability phase.

### Why it exists
The Phase 27.4 read side is correct (1m + resample). The ingest, UI, and
maintenance sides still treat BI5 as a per-TF candle source. That latent
fragmentation must be sealed before any tick work begins — otherwise BI5-2
inherits a broken contract.

### Architectural dependency chain
- None upstream. This is the foundation.
- Downstream: every later phase assumes 1m bucket is the only BI5 surface.

### Trigger conditions (any one is sufficient)
- Operator decision to begin BI5 maturation ladder.
- Detection of non-1m BI5 docs in `market_data` (latent footgun fired).
- Operational confusion reported by an operator using the UI.

### Maturity requirements
- Operator approval (explicit).
- Phase 30.2 universe governance must be sealed (it is — 266/266).
- No active BI5 sweep mid-flight (drain to idle).

### Observability signals (machine-detectable, computed by `bi5_maturity.py`)
| Signal | Threshold |
|---|---|
| `bi5_non_canonical_buckets` | 0 = healthy |
| `bi5_1m_coverage_pct` for active universe pairs | ≥ 80% |
| `bi5_ingest_log` rows | exist (or N/A if no historical ingest) |
| Number of distinct TFs in BI5 storage | 1 (canonical) |

### Recommended activation timing
- **Before** any tick work begins.
- **Independent** of survivor maturity — purely a hygiene seal.
- Can be done during the current observation window without disrupting it.

### Risks of premature activation
- Negligible. This is a hygiene step. The hard 400 on non-1m BI5 ingest
  blocks a footgun that is not in active use today.

### Compute / storage impact
- Compute: trivial (route guard + UI hide).
- Storage: monotonically decreasing (rejected fragments never persist).

### Trust-gate additions required
- `tests/test_bi5_canonical_lock.py`:
  - reject non-1m BI5 ingest via `/upload-data`, `/incremental/bi5`, `/import-server-file` (400)
  - `data_access.load_ohlc_bars(source="bi5", timeframe!="1m")` returns empty / errors
  - existing 1m read path unchanged (regression sentinel)

### Estimated scope
- 4 small edits: `api/data.py` (3 routes), `engines/data_maintenance.py` (1 scheduler), `frontend/DataUpload.js` (1 dropdown hide), `engines/data_access.py` (1 assertion).
- 1 new test file (~8 cases).

---

## Phase BI5-2 · Raw tick storage substrate

### Purpose
Introduce timeframe-agnostic tick storage so the rest of the realism
ladder has a physical substrate. Adds `market_data_ticks` collection with
raw bid/ask quotes per pair × timestamp.

### Why it exists
True execution realism requires `(bid, ask, bid_vol, ask_vol)` at the
quote-update granularity. Pre-aggregated OHLC cannot model spread,
slippage, partial fills, or quote-update timing.

### Architectural dependency chain
- **Upstream**: BI5-1 (canonical ingestion sealed).
- **Downstream**: BI5-3 (tick-derived realism consumes this).

### Trigger conditions (all must be true)
- BI5-1 sealed for ≥ 30 days under live operation.
- Operator approval (explicit).
- At least one `deployment_ready` strategy exists (proves the realism path
  is exercised).
- Universe boundary stable for ≥ 14 days (no operator pair/TF churn).

### Maturity requirements
- Phase 27.4 1m realism stream proven stable under ≥ 100 evaluations.
- Disk space budget approved (raw ticks ≈ 100–500 MB per pair per month).
- `dukascopy_bi5_fetcher` design reviewed (NOT auto-fetched — operator triggers).

### Observability signals
| Signal | Threshold |
|---|---|
| `deployment_ready_count` | ≥ 1 |
| `bi5_realism.evaluations_completed_30d` | ≥ 100 |
| `universe.last_change_age_days` | ≥ 14 |
| `bi5_canonical_lock_violations` | 0 |
| `disk_free_gb` (host) | ≥ 50 (operator-confirmed) |

### Recommended activation timing
- **After** the first cohort of `deployment_ready` strategies is observed.
- **After** survivor governance cadence has demonstrated stability.
- **NOT** during initial survivor accumulation (premature compute load).

### Risks of premature activation
| Risk | Severity |
|---|---|
| Storage cost without analytical payoff | Medium |
| Tick fetcher latency steals scheduler budget | Medium |
| Parallel-write window doubles BI5 ingest cost | Low (transient) |
| Operator cognitive load (new surface) | Low |

### Compute / storage impact
- Tick fetcher: a few minutes per (pair, week) on operator demand.
- Tick storage: ≈ 200–500 MB per pair per month at 50–100 ticks/sec average.
- Index `(symbol, ts)`: ≈ 10–15% overhead.

### Trust-gate additions required
- `tests/test_market_data_ticks_schema.py` — doc shape, indexes, no orphan ticks
- `tests/test_dukascopy_bi5_fetcher.py` — parse roundtrip, partial-file resilience
- `tests/test_bi5_parallel_write.py` — assert legacy 1m bucket continues to populate during tick parallel-write phase

### Estimated scope
- New module `data_engine/dukascopy_bi5_fetcher.py`
- New module `engines/tick_storage.py` (write API)
- New collection `market_data_ticks` + indexes
- New admin endpoints `POST /api/ticks/fetch`, `GET /api/ticks/coverage`
- No UI yet (BI5-6 owns UI pivot)

---

## Phase BI5-3 · Tick-derived realism

### Purpose
Switch the realism evaluator (`bi5_realism.py`) from "read 1m → resample"
to "read ticks → aggregate". Adds per-evaluation comparison artefact so
the operator can validate parity between the two paths before retiring
the 1m intermediate.

### Why it exists
Resampling 1m bars introduces aggregation artefacts (boundary alignment,
volume-weighted-vs-uniform price approximation). Tick-derived bars
eliminate these and become the authoritative realism source.

### Architectural dependency chain
- **Upstream**: BI5-2 (tick substrate exists, ≥ 30 days of tick coverage).
- **Downstream**: BI5-4 (tick replay reuses the tick aggregator).

### Trigger conditions (all must be true)
- BI5-2 sealed for ≥ 30 days.
- At least 3 active pairs in tick storage with ≥ 6 months coverage each.
- Operator approval (explicit).
- Parity validation passed: tick-derived `pf_ratio` vs 1m-resampled
  `pf_ratio` within 5% on ≥ 20 strategies.

### Maturity requirements
- Tick aggregator `tick_aggregator.py` boundary-tested vs Phase 27.4
  `_resample_1m_to_tf` (regression sentinel).
- `deployment_ready` cohort has ≥ 10 strategies (so realism evaluator
  has meaningful workload).
- Universe boundary stable (so test cohort is consistent).

### Observability signals
| Signal | Threshold |
|---|---|
| `tick_coverage_months` per universe pair | ≥ 6 |
| `tick_parity_passing_pct` (vs 1m baseline) | ≥ 95% |
| `tick_aggregator_boundary_regressions` | 0 |
| `deployment_ready_count` | ≥ 10 |

### Recommended activation timing
- Only after parity validation phase completes successfully.
- Default to **parallel-evaluation mode** for ≥ 30 days (both paths run,
  results compared) before retiring 1m intermediate.

### Risks of premature activation
| Risk | Severity |
|---|---|
| Tick gaps cause realism flakiness | HIGH — gates strategies incorrectly |
| Aggregator bug propagates to all promotion decisions | HIGH |
| Compute cost spikes (per-evaluation tick reads) | Medium |

### Compute / storage impact
- Per realism evaluation: 1 tick range read + 1 aggregation pass.
  Estimate 1–5 seconds per strategy at H1, 10–20 seconds at M1.
- No new storage.

### Trust-gate additions required
- `tests/test_tick_aggregator_boundary_parity.py` — output vs Phase 27.4 resampler ≤ 0.1% PF delta on regression set
- `tests/test_bi5_realism_tick_mode.py` — full pipeline using tick path
- Parity dashboard endpoint `GET /api/governance/bi5-parity` (admin-read)

---

## Phase BI5-4 · Tick replay engine

### Purpose
Build a deterministic tick-by-tick replay engine that simulates order
fills against actual quote ticks. Validates cBot parity for any
`deployment_ready` strategy before live deployment.

### Why it exists
Backtests on bars assume close-price fills, ignore intra-bar quote
volatility, and cannot detect cBot semantic divergence. Tick replay
closes this gap.

### Architectural dependency chain
- **Upstream**: BI5-3 (tick aggregator proven, parity validated).
- **Downstream**: BI5-5 (spread/slippage models plug into the replay loop).

### Trigger conditions (all must be true)
- BI5-3 sealed for ≥ 30 days under live operation.
- At least 1 cBot export performed via `/api/strategies/{hash}/export/cbot`.
- Operator approval (explicit).
- Replay determinism verified: same tick stream → byte-identical fill sequence over 10 reruns.

### Maturity requirements
- IR transpiler (Phase 28-C) sealed (it is).
- Tick aggregator (BI5-3) sealed.
- A "deployment_ready" cohort exists where parity validation becomes
  operationally meaningful.

### Observability signals
| Signal | Threshold |
|---|---|
| `cbot_exports_lifetime` | ≥ 1 |
| `deployment_ready_count` | ≥ 5 (so replay is non-trivial) |
| `tick_replay_determinism_pct` | 100% (no flakiness tolerated) |
| `transpiler_seal_intact` | true |

### Recommended activation timing
- Only after a few real cBot exports have been operator-validated against
  manual cTrader smoke runs. Tick replay then automates what the operator
  is doing by hand.

### Risks of premature activation
| Risk | Severity |
|---|---|
| Replay non-determinism is a CRITICAL bug class | HIGH — destroys gate trust |
| Replay diverges from cTrader semantics → false rejections | HIGH |
| Compute load per `deployment_ready` candidate | Medium |

### Compute / storage impact
- Per replay: 10 seconds – 10 minutes depending on strategy lifetime + TF.
- Replay logs persisted: ≈ 1–10 MB per replay (operator-tunable retention).

### Trust-gate additions required
- `tests/test_tick_replay_determinism.py` — N reruns → identical fills
- `tests/test_tick_replay_ir_parity.py` — IR semantics ≡ replay execution
- `tests/test_cbot_replay_parity.py` — replay fills ≡ cTrader simulator fills (when available)

---

## Phase BI5-5 · Spread / slippage / microstructure modelling

### Purpose
Add explicit models for execution brutality:
- Time-varying spread (session-aware widening at NY/Asia rollover)
- Volatility-adjusted slippage (large orders, fast markets)
- Quote-staleness modelling (last-tick risk)
- Partial-fill behaviour (per-firm policy)

### Why it exists
Even tick replay assumes you got the quoted price. Real execution differs:
spreads widen, fills slip, and partial fills break naive position sizing.

### Architectural dependency chain
- **Upstream**: BI5-4 (replay engine exists; models plug into the loop).
- **Downstream**: BI5-6 (UI surfaces the realism metrics).

### Trigger conditions (all must be true)
- BI5-4 sealed for ≥ 30 days.
- Operator-validated `deployment_ready` cohort of ≥ 5 strategies survived
  tick replay.
- Operator approval (explicit).

### Maturity requirements
- Empirical spread/slip distributions characterised per (pair, session).
- Per-firm execution policy documented.

### Observability signals
| Signal | Threshold |
|---|---|
| `replay_validated_deployment_ready_count` | ≥ 5 |
| `spread_distribution_empirical` (per pair) | exists |
| `firm_execution_policies` | documented |

### Recommended activation timing
- Only after replay engine has demonstrated operational reliability.
- Models START as opt-in (lifecycle gate uses them only on
  `force_realism_mode=brutal`); become default after additional 30-day
  observation.

### Risks of premature activation
| Risk | Severity |
|---|---|
| Over-aggressive models reject all strategies | HIGH (kills survivor pipeline) |
| Under-tuned models give false confidence | MEDIUM |
| Per-firm policy drift not modelled | MEDIUM |

### Compute / storage impact
- Per replay: ~10–20% overhead vs raw replay.
- Storage: model parameters (per pair, per firm) ≈ kilobytes.

### Trust-gate additions required
- `tests/test_spread_model_distribution.py`
- `tests/test_slippage_model_volatility_response.py`
- `tests/test_replay_with_microstructure_determinism.py`
- `tests/test_realism_brutal_vs_optimistic_gap.py` (gap must be operator-bounded)

---

## Phase BI5-6 · Execution-realism UI pivot

### Purpose
Replace the current TF-coupled BI5 controls with tick-native operator
surfaces:
- Tick coverage heatmap (per symbol × month)
- Range-only ingestion (pair + date-range, no TF dropdown)
- Derived-TF preview (read-only)
- Replay fidelity metrics (parity %, determinism, brutality gap)
- Microstructure inspector (spread / tick-rate / quote-staleness)

### Why it exists
The current UI implies TF-specific tick downloads, which is architecturally
wrong. Operators need surfaces that match the underlying timeframe-agnostic
storage model.

### Architectural dependency chain
- **Upstream**: BI5-5 (the realism stack is complete and operator-trusted).
- **Downstream**: none — this is the final UI consolidation.

### Trigger conditions (all must be true)
- BI5-1 through BI5-5 all sealed.
- Operator-trusted brutality calibration (≥ 30 days of brutal-mode runs
  without false rejection wave).

### Maturity requirements
- Backend tick coverage API ready (`GET /api/ticks/coverage` returns
  heatmap-ready JSON).
- Replay metrics API ready (`GET /api/governance/bi5-parity`).
- Microstructure API ready (`GET /api/ticks/microstructure`).

### Observability signals
| Signal | Threshold |
|---|---|
| All upstream phases (1..5) | sealed |
| Operator declares UI pivot ready | explicit |

### Recommended activation timing
- Only after backend realism stack has proven operationally trustworthy
  over a multi-month observation window.
- UI pivot is reversible: old `DataUpload.js` retained behind feature flag
  for ≥ 60 days post-pivot.

### Risks of premature activation
| Risk | Severity |
|---|---|
| Operator confusion (different mental model overnight) | MEDIUM |
| UI bugs corrupt operator's view of tick coverage | MEDIUM |
| Premature TF-dropdown removal blocks legitimate hybrid debugging | LOW |

### Compute / storage impact
- Frontend bundle: trivial.
- Backend: 2–3 new read endpoints; no new storage.

### Trust-gate additions required
- `tests/test_tick_coverage_endpoint.py`
- `tests/test_microstructure_endpoint.py`
- Frontend smoke: tick heatmap renders, no TF dropdown for BI5

---

## Maturity-detection framework

A **read-only** module `engines/bi5_maturity.py` computes per-phase
readiness signals on demand. It is consumed by:
- `GET /api/governance/bi5-maturity` (advisory only).
- Manual operator inspection.

**Critical constraint:** This framework only reports. It MUST NOT trigger
phase activations, fetch tick data, or modify storage. Every transition
requires an explicit operator action against an admin endpoint that does
not yet exist (and will not be added until each phase is itself activated).

### Maturity signal schema (per phase)

```jsonc
{
  "phase": "BI5-1",
  "name":  "Canonicalise ingestion semantics",
  "current_status": "not_started" | "in_progress" | "sealed",
  "ready_to_activate": true | false,
  "blockers": [ "<human-readable reason>", ... ],
  "signals": {
    "<signal_name>": { "value": <number|bool>, "threshold": <...>, "ok": <bool> },
    ...
  },
  "operator_actions_required": [ "<action>", ... ],
  "depends_on": [ "<phase_id>", ... ],
  "evaluated_at": "<iso>"
}
```

### Public read surface
```
GET /api/governance/bi5-maturity
  → { evaluated_at, phases: [BI5-1, BI5-2, BI5-3, BI5-4, BI5-5, BI5-6] }
```

Returns the maturity object for every phase in one call. Cheap, cached
60 seconds. Admin role NOT required (advisory visibility).

### Authority hierarchy

```
operator decree  >  maturity framework recommendation  >  silence
```

The framework can say "BI5-2 is ready to activate" but **only** the
operator can flip a phase live. The framework can also say "BI5-3 is
NOT ready — needs ≥ 10 deployment_ready strategies, currently 0" — that
information is what protects the system from premature escalation.

### Test coverage required
- `tests/test_bi5_maturity_signal_math.py` — pure-function correctness of every signal
- `tests/test_bi5_maturity_dependency_chain.py` — BI5-N ready ⇒ BI5-(<N) sealed
- `tests/test_bi5_maturity_api_endpoint.py` — endpoint shape + advisory-only

---

## Operator-decreed invariants

| # | Invariant |
|---|---|
| 1 | Phase activations require explicit operator action. AI never auto-activates. |
| 2 | Dependency chain (BI5-1 → ... → BI5-6) is strictly ordered. |
| 3 | Each phase must seal a 30-day observation window after activation before the next can begin. |
| 4 | Each phase activation lands in a separate session with its own ask_human approval. |
| 5 | Maturity framework is advisory only — it observes, never acts. |
| 6 | Roll-back path for every phase: each new collection / endpoint / module is additive and removable. |
| 7 | No phase may rewrite Phase 28 sealed surfaces (transpiler / IR / interpreter). |
| 8 | No phase may rewrite Phase 26.5 lifecycle gates. |
| 9 | No phase may introduce a new scheduler authority — single APScheduler under `ai_orchestrator`. |
| 10 | Universe Governance (Phase 30.2) applies to BI5 ingestion universes: tick-fetch invocations are filtered by allowed pairs. |

---

## How to read this document

When operator decides to begin a phase:
1. Re-read the phase entry here (purpose, dependencies, triggers).
2. Confirm maturity framework signals all green for that phase.
3. Open a dedicated session.
4. Approve activation via ask_human.
5. Implement phase scope (anti-drift, additive).
6. Land trust-gate.
7. Update this document's "Current sealed state" section.
8. Wait 30-day observation window before next phase.

---

## Document version & lineage

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-05-16 | Initial sealing of BI5 evolution governance roadmap. Maturity framework planned but not yet shipped — operator approval pending. |
