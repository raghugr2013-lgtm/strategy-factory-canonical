# Ecosystem Exploration Governance Framework (EG Roadmap)

**Version:** 1.0
**Sealed:** 2026-05-16
**Status:** Roadmap + maturity-detection framework only — NO autonomous allocation escalation.
**Discipline:** additive · reversible · observable · anti-drift.

---

## Purpose & posture

This document is the single institutional source of truth for the
multi-phase evolution of pair × timeframe × style exploration governance.
It does **NOT** implement EG-2 through EG-6. It exists so the long-term
exploration roadmap cannot quietly drift, fragment, or be forgotten under
day-to-day work pressure.

**Operator authority is final.** The orchestrator MAY observe ecosystem
maturity signals and report readiness. The orchestrator **MUST NEVER**:
- escalate ecosystem-wide simultaneous execution
- introduce a new scheduler authority
- mutate universe configuration autonomously
- rebalance compute allocation without operator approval

Every phase transition is an explicit operator decree.

---

## Architectural philosophy

Three principles anchor every EG phase:

1. **Intelligent rotation over brute parallelism.**
   The system explores ecosystems sequentially over time, not all at once.

2. **Memory over amnesia.**
   Every cell carries its exploration history; no cell gets repeatedly
   re-explored while another starves.

3. **Recommendation over autonomous escalation.**
   The orchestrator surfaces "ecosystem X is mature for deeper exploration"
   as advisory. The operator decides.

---

## Architectural dependency chain

```
                EG-1 (universe boundary — DONE in Phase 30.2)
                   │
                   ▼
                EG-2 (exploration memory layer)
                   │
                   ▼
                EG-3 (rotational ecosystem scheduler)
                   │
                   ▼
                EG-4 (adaptive allocation observation)
                   │
                   ▼
                EG-5 (exploration / exploitation governance)
                   │
                   ▼
                EG-6 (full ecosystem autonomy — deferred indefinitely)
```

Skipping levels is forbidden. EG-4 cannot activate without EG-3 producing
real rotation data. EG-5 cannot activate without EG-4 producing real
recommendations to evaluate. EG-6 is intentionally last and remains
deferred until empirical evidence justifies activation.

---

## Phase EG-1 · Universe Boundary Governance

### Status
**SEALED** in Phase 30.2 (2026-05-16). Documented here for canonical
roadmap completeness.

### Purpose
Define the operator-decreed ALLOWED RESEARCH UNIVERSE. Pair, timeframe,
and style allowlist that every default scan authority filters through.

### What already exists
- `governance_universe` Mongo collection (single config doc, audit_log cap=50)
- `GET/POST /api/governance/universe` (admin-write on POST)
- `GET /api/governance/universe/preview` (intersection diagnostic across A1–A6)
- 6 authority wirings: multi_cycle_runner · ai_orchestrator (DIVERSITY_SCAN + RULE 12) · env_priority · gem_factory_engine · auto_factory_phase55
- Frontend `UniverseGovernancePanel.jsx` (Dashboard tab)
- 25/25 trust-gate tests (`test_universe_governance.py`)
- Initial seed: EURUSD/XAUUSD × H1/H4 × {trend-following, mean-reversion, breakout} · floor=5% · max_active_cells=8 · breadth_vs_depth=0.5

### Governance inheritance rules
- Manual `scan=[(pair,tf),...]` payloads **bypass** the universe filter (operator-explicit always wins).
- `env_priority` retains adaptive allocation authority **inside** the allowed universe.
- Auto-data-maintenance (`auto_data_maintainer.py`) intentionally maintains the broader `SYMBOL_CONFIG` set so the operator can widen universe later without delay.
- Empty intersection at A1/A2/A3/A6 → warn-and-fallback (anti-blackhole).
- Empty intersection at A5 (gem_factory explicit args) → fail-loud 400.

### What remains future work
- Universe-widening recommendation (EG-2/3/4 surface readiness signals).
- Universe rotation memory (EG-2 tracks "when was this cell last touched").
- Universe coverage health scoring (EG-2 stagnation detection).

---

## Phase EG-2 · Exploration Memory Layer

### Purpose
Per ecosystem cell `(pair, timeframe, style)`, persistently track:
- last explored timestamp
- exploration count (cycles run against this cell)
- mutation cycles executed against this cell
- survivor yield (strategies that reached ≥ validated)
- PF productivity (median PF of saves)
- lifecycle progression quality (count by terminal stage)
- regime breadth (Phase 29 regime coverage achieved)
- stagnation score (cycles-since-last-validated)
- compute allocation history (sampled by env_priority + RULE triggers)
- starvation detection (cells with > N days no exploration)

### Why it exists
Without explicit memory, the system has no concept of "this cell has been
exhaustively explored vs this cell has never been touched." env_priority
provides EMA weighting but no per-cell historical record. This phase adds
that record so EG-3/EG-4 can make informed rotation and allocation
recommendations.

### Architectural dependencies
- **Upstream**: EG-1 (universe must be canonical).
- **Downstream**: EG-3 (rotation reads memory), EG-4 (allocation reads memory).

### Maturity triggers (any one)
- Operator decision to begin ecosystem memory accumulation.
- First 100+ saves in `strategy_performance_history` across at least 4 cells (so memory has signal to compute).
- Detection of cell starvation in env_priority telemetry.

### Activation conditions (all must be true)
- EG-1 sealed (it is).
- Universe stable for ≥ 14 days (no churn that would invalidate cell identity).
- At least 1 evidential cycle has populated `strategy_performance_history`.
- Operator approval (explicit, dedicated session).

### Observability requirements
- New Mongo collection `ecosystem_cell_memory`, single doc per `(pair, tf, style)`.
- Per-cell document shape:
  ```
  {
    cell_key: "EURUSD/H1/trend-following",
    pair, timeframe, style,
    first_explored_at, last_explored_at,
    exploration_count,
    mutation_cycles,
    saves_count,
    survivor_count_by_stage: { exploratory: N, candidate: N, ..., deployment_ready: N },
    median_pf, p95_pf,
    regime_breadth_pct,
    stagnation_score,
    last_recommendation_at,
    audit_log: [...]
  }
  ```
- `GET /api/governance/ecosystem-memory` (read-only).
- Per-cell read endpoint: `GET /api/governance/ecosystem-memory/{cell_key}`.

### Risks of premature activation
| Risk | Severity |
|---|---|
| Storage cost without signal (empty Mongo writes) | LOW |
| Stagnation score noisy on cold cells | MEDIUM (mitigate with warmup threshold) |
| Memory becomes "truth" before evidential reality justifies | MEDIUM |
| Operator over-trusts cell scores during early observation | MEDIUM |

### Compute / storage impact
- Storage: ≈ 1 KB per cell × N_pairs × N_TFs × N_styles. At realistic 8×3×3 = 72 cells → ~72 KB. Trivial.
- Compute: one read + one upsert per cycle save. Negligible.

### Trust-gate additions required
- `tests/test_ecosystem_memory_schema.py` — doc shape, idempotent upsert
- `tests/test_ecosystem_memory_stagnation_math.py` — score correctness
- `tests/test_ecosystem_memory_starvation_detection.py`
- `tests/test_ecosystem_memory_api_endpoints.py` — advisory-only read shape

### Estimated scope
- New module `engines/ecosystem_memory.py` (~ 200 lines)
- New collection `ecosystem_cell_memory`
- 2 new read endpoints
- Hook into `strategy_memory.record_performance` for per-cell upsert
- No UI yet (admin-CLI inspect for the first 30 days)

---

## Phase EG-3 · Rotational Ecosystem Scheduler

### Purpose
A new orchestrator rule (NOT a new scheduler authority) that produces
**deterministic, fairness-weighted cell rotation recommendations**.
Recommends one cell per tick using starvation + productivity weighting,
emitted as `log_recommendation` until operator approves execute mode.

### Why it exists
env_priority handles tier weighting but does not guarantee fairness across
cells within a tier — a hot cell can monopolise sampling for hours.
EG-3 introduces explicit rotation memory so every cell gets visited within
a bounded revisit cadence.

### Rotation philosophy
- **Deterministic by default**: round-robin across the universe.
- **Adaptive overlay**: starvation-prioritised — cells with longest
  `last_explored_at` move to the front.
- **Productivity-weighted**: ties broken by historical median PF.
- **Bounded revisit cadence**: no cell can be skipped > N rotation slots
  (operator-tunable; default = 1× universe size).

### Architectural dependencies
- **Upstream**: EG-2 (per-cell memory exists).
- **Downstream**: EG-4 (allocation tunes rotation pressure).

### Maturity triggers (all must be true)
- EG-2 sealed for ≥ 30 days.
- ≥ 100 saves recorded in `ecosystem_cell_memory`.
- At least 4 cells with `exploration_count ≥ 5` (so rotation has real history).
- Operator approval.

### Activation conditions
- Universe stable for ≥ 30 days.
- Multi-cycle runner has executed ≥ 50 cycles total under EG-2 memory.
- Operator approval.

### Observability requirements
- New `RULE 13 ROTATIONAL_CELL_ADVISORY` in `ai_orchestrator.decide()` (advisory-only initially).
- Per-tick telemetry: next rotation target + 3-deep candidate list + starvation scores.
- `GET /api/governance/rotation-schedule` (read-only preview of next N rotation cells).

### Risks of premature activation
| Risk | Severity |
|---|---|
| Round-robin forces compute on unproductive cells | MEDIUM |
| Starvation override degrades exploitation of hot cells | HIGH |
| New rule competes with env_priority weights | MEDIUM (mitigate: EG-3 is purely advisory until EG-4 unifies them) |
| Rotation thrash if revisit-cadence too short | MEDIUM |

### Compute / storage impact
- Compute: one pure-function call per orchestrator tick. Negligible.
- Storage: rotation state on the orchestrator config doc. Trivial.

### Trust-gate additions required
- `tests/test_eg3_rotation_determinism.py` — same memory state → same rotation
- `tests/test_eg3_starvation_priority.py` — longest-idle cell surfaces first
- `tests/test_eg3_revisit_cadence_bound.py` — no cell skipped > N slots
- `tests/test_eg3_advisory_only.py` — RULE 13 emits only `log_recommendation`

---

## Phase EG-4 · Adaptive Allocation Observation

### Purpose
Introduce ecosystem-level allocation recommendations. The orchestrator
synthesises EG-2 memory + EG-3 rotation + env_priority weights and emits
advisory directives such as:
- "Deepen exploitation: EURUSD/H1/trend has 6 consecutive validated saves
  → recommend 3× allocation share"
- "Broaden exploration: GBPUSD/H4/breakout has not been touched in 14 days
  → recommend single discovery cycle"
- "Rebalance: 80% of saves concentrated in 1 cell → recommend exploration
  injection"

Recommendations land in `audit_log` and on the GovernanceCard (small pill).
Operator decides whether to act.

### Why it exists
EG-3 produces rotation order but not allocation intensity. EG-4 turns
"which cell next" into "how much compute to commit." Without EG-4, the
system has no concept of "this cell deserves 3 cycles in a row" vs
"this cell deserves 1 trial."

### Architectural dependencies
- **Upstream**: EG-2 + EG-3 sealed.
- **Downstream**: EG-5 unifies recommendations into a coherent policy.

### Maturity triggers (all must be true)
- EG-3 sealed for ≥ 30 days.
- ≥ 200 cycles executed under EG-3 rotation.
- ≥ 5 strategies reached `deployment_ready` (proves productive cells exist).
- Operator approval.

### Activation conditions
- EG-2 and EG-3 sealed and observed.
- Universe stable for ≥ 60 days.
- Operator approval after reviewing 30 days of EG-3 telemetry.

### Observability requirements
- New `RULE 14 ECOSYSTEM_ALLOCATION_ADVISORY` (advisory-only).
- `GET /api/governance/ecosystem-allocation-advisory` (read-only).
- Per-cell recommendation log in `audit_log`.

### Risks of premature activation
| Risk | Severity |
|---|---|
| Recommendation noise drowns operator attention | HIGH |
| False-positive exploitation calls (early-cycle lucky PF) | HIGH |
| Premature exploration calls waste compute | MEDIUM |
| Operator over-trusts allocation advice during empirical infancy | HIGH |

### Compute / storage impact
- Compute: per-tick aggregation across EG-2 memory. ~50 ms at 100 cells.
- Storage: per-recommendation row in `audit_log` (already permanent retention).

### Trust-gate additions required
- `tests/test_eg4_recommendation_math.py` — exploitation / exploration scoring correctness
- `tests/test_eg4_advisory_only.py` — no execution actions emitted
- `tests/test_eg4_audit_log_emission.py` — every recommendation persisted
- `tests/test_eg4_recommendation_dedup.py` — same state → same recommendation, deduped

---

## Phase EG-5 · Exploration vs Exploitation Governance

### Purpose
Formalise the **policy** that EG-4 recommendations follow. Defines the
operator-decreed compute split (default: 70% exploitative / 30%
exploratory) and surfaces it as a single governance dial.

### Why it exists
EG-4 produces recommendations cell-by-cell. EG-5 unifies them into one
coherent policy lever: "I want 70/30 today" → orchestrator allocates
accordingly. Without EG-5, EG-4's recommendations are noise without a
guiding ratio.

### Policy mechanics
- New operator-decreed config `exploration_pct` (default 30%, range 5–95).
- Lives on `governance_universe` (already has `breadth_vs_depth` placeholder
  — EG-5 promotes this into binding policy).
- EG-4 recommendations weight by this ratio: exploitation candidates compete for the 70% bucket, exploration candidates for the 30% bucket.
- Operator can adjust ratio per session; audit_log records every change.

### Architectural dependencies
- **Upstream**: EG-4 sealed (recommendations exist to govern).
- **Downstream**: EG-6 (autonomy applies the policy without operator intervention).

### Maturity triggers (all must be true)
- EG-4 sealed for ≥ 30 days.
- Operator has observed ≥ 100 EG-4 recommendations.
- Distribution of recommendations spans both exploit + explore (not 100% one-sided).
- ≥ 10 `deployment_ready` strategies (proves exploitative pressure has produced value).

### Activation conditions
- EG-4 sealed and observed.
- Operator approval.
- Phase 30.4 (`auto_replace_enabled=True`) — only after replacement engine is trusted to act on exploit advice.

### Observability requirements
- `exploration_pct` surfaced on UniverseGovernancePanel (replace placeholder slider with binding control).
- `GET /api/governance/exploration-budget` (current bucket split).
- Per-cycle audit_log row: "this cycle came from exploit bucket vs explore bucket."

### Risks of premature activation
| Risk | Severity |
|---|---|
| Premature exploitation lock-in (over-trust on lucky early survivors) | HIGH |
| Over-exploration starves promising cells | HIGH |
| Operator misuses ratio dial during empirical infancy | HIGH |
| Replacement engine acts on noisy exploitation signals | HIGH |

### Compute / storage impact
- Compute: ratio multiplication on existing weights. Negligible.
- Storage: per-cycle attribution row. ~1 KB per cycle.

### Trust-gate additions required
- `tests/test_eg5_exploration_pct_validation.py` — range, persistence
- `tests/test_eg5_bucket_attribution.py` — every cycle correctly attributed
- `tests/test_eg5_replacement_engine_consumes_buckets.py` — replacement decisions reflect exploit bucket
- `tests/test_eg5_audit_log_attribution.py`

---

## Phase EG-6 · Full Ecosystem Autonomy

### Status
**Deferred indefinitely.** Activation criteria documented here for
institutional completeness, not because activation is imminent.

### Purpose
The orchestrator autonomously executes the EG-5 policy without per-cycle
operator approval. All advisory rules (RULE 13 ROTATIONAL, RULE 14
ALLOCATION, RULE 12 AUTONOMOUS_DISCOVERY) flip to execute mode.
Universe-widening also becomes autonomous within operator-decreed limits.

### Why it exists in the roadmap
Future-state institutional completeness. Operators of mature evolutionary
research systems eventually want the system to **operate** the ecosystem,
not just **report on** it. EG-6 is the destination — but only after EG-1
through EG-5 produce mature, trustworthy behaviour over months.

### Architectural dependencies
- **Upstream**: EG-1 through EG-5 sealed with ≥ 90 days observation each.
- **Downstream**: none — this is the terminal phase.

### Readiness criteria (all required)
- Stable survivor cadence: ≥ 1 new `deployment_ready` per 30-day window for ≥ 6 months.
- Lifecycle governance proven: 0 false-positive promotions in last 90 days.
- Orchestrator maturity: 0 hung schedulers / job timeouts in last 90 days.
- Replacement engine trusted: ≥ 20 replacement_executed events in last 90 days, 0 operator overrides.
- Compute allocation quality proven: ≥ 80% of EG-4 recommendations matched operator decision when reviewed.
- BI5-5 spread/slip models active (real execution realism in place).
- Phase 31 portfolio intelligence active (correlation gates).

### Activation conditions
- All upstream phases sealed for ≥ 90 days each.
- Operator decree in a dedicated session.
- Trust-gate certification of every autonomous rule.
- Rollback plan documented and rehearsed.

### Observability requirements
- Full audit_log retention (permanent).
- Per-decision attribution: every autonomous action tagged with rule_id + EG phase that authorized it.
- Operator override count tracked monthly.
- Anomaly detection on autonomy decisions (statistical drift sentinel).

### Risks of premature activation
| Risk | Severity |
|---|---|
| Autonomous compute explosion | **CRITICAL** |
| Autonomous universe widening into untested pairs | **CRITICAL** |
| Autonomous replacement of legitimate survivors | **CRITICAL** |
| Loss of operator institutional trust | **CRITICAL** |
| Cascade failure across allocation surfaces | **CRITICAL** |

### Compute / storage impact
- Compute: bounded by max_active_cells and ratio policy (no escalation beyond EG-5 caps).
- Storage: same as EG-5.

### Trust-gate additions required
- Full autonomy regression suite (≥ 50 cases covering rule execute mode)
- Rollback drill test (autonomy can be disabled in < 1 minute)
- Operator-override-honored test
- Anomaly-detection sentinel test

---

## Maturity-Detection Framework

A read-only module `engines/ecosystem_maturity.py` computes per-phase
readiness signals on demand. Consumed by:
- `GET /api/governance/ecosystem-maturity` (advisory).
- Manual operator inspection.

### Critical constraint
The framework **reports only**. It MUST NOT:
- mutate `governance_universe`
- trigger orchestrator rules
- modify `ecosystem_cell_memory`
- change scheduler intervals
- escalate autonomy flags

Every phase activation requires an explicit operator session.

### Per-phase signal schema

```jsonc
{
  "phase": "EG-1",
  "name":  "Universe Boundary Governance",
  "current_status": "not_started" | "in_progress" | "sealed",
  "ready_to_activate": true | false,
  "blockers": [ "<human-readable reason>", ... ],
  "signals": {
    "<signal_name>": { "value": <num|bool|str>, "threshold": <...>, "ok": <bool> }
  },
  "operator_actions_required": [ ... ],
  "depends_on": [ ... ],
  "evaluated_at": "<iso>"
}
```

### Public read surface
```
GET /api/governance/ecosystem-maturity
  → { evaluated_at, sealed_phases, phases: [EG-1, EG-2, EG-3, EG-4, EG-5, EG-6] }
```

### Authority hierarchy
```
operator decree  >  ecosystem maturity recommendation  >  silence
```

---

## Operator-decreed invariants

| # | Invariant |
|---|---|
| 1 | Phase activations require explicit operator session + ask_human approval. |
| 2 | Dependency chain (EG-1 → ... → EG-6) is strictly ordered. |
| 3 | Each phase must observe ≥ 30 days under live operation before the next can begin. |
| 4 | EG-6 cannot activate until ≥ 6 months of stable EG-5 operation. |
| 5 | No phase introduces a new APScheduler authority — all rules live inside `ai_orchestrator`. |
| 6 | No phase rewrites Phase 26.5 lifecycle gates. |
| 7 | No phase rewrites Phase 28 sealed surfaces (transpiler / IR / interpreter). |
| 8 | All recommendations are advisory until execute-mode is explicitly enabled per rule. |
| 9 | Universe Governance (EG-1) defines the boundary — every later phase operates **within** it. |
| 10 | Manual `scan=[...]` payloads always bypass any EG-phase rotation/allocation logic. |

---

## Lineage

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-05-16 | Initial sealing of EG roadmap. Maturity framework planned. EG-1 documented as already sealed (Phase 30.2). |
