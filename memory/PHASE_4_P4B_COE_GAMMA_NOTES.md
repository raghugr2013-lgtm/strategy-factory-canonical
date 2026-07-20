# Phase 4 Stage 4 — P4B COE γ: Implementation Notes

> **Status:** IMPLEMENTED, tested, dormant.
> All P4B feature flags default OFF. Zero production behaviour change.
> Landed: 2026-07-20.
> Preceded by: `PHASE_4_MASTER_PLAN.md §4` (operator-approved).
> Cumulative Phase-2 + P4A + P4B unit tests: **275 / 275 passing**
> (239 prior + 36 new P4B).

---

## 1. What landed

All eight sub-milestones from PHASE_4_MASTER_PLAN §4 delivered as a
standalone `engines/coe_gamma/` package. The pre-existing orchestrator
is UNMODIFIED — every P4B component composes via injected hooks,
mirroring the Stage 3.γ pattern of "additive alongside, not woven into".

### 1.1 Package layout

```
backend/legacy/engines/coe_gamma/
├── __init__.py            (public exports)
├── retry_executor.py      (P4B.1 — per-class exponential backoff)
├── dead_letter.py         (P4B.2 — `workload_dead_letter` collection)
├── work_recovery.py       (P4B.3 — stale in-flight sweep)
├── provider_admission.py  (P4B.4 — circuit-breaker-aware admission)
├── age_boost.py           (P4B.5 — priority delta for waiting tasks)
├── elastic_bands.py       (P4B.6 — BACKTEST ↔ MUTATION capacity loans)
├── budget_hard_cap.py     (P4B.7 — daily USD hard-cap enforcer)
├── operator_controls.py   (P4B.8 — circuit reset, queue pause/resume)
└── router.py              (COE γ endpoints)
```

### 1.2 New endpoints (all self-guard with HTTP 503 when flag off)

| Method | Path | Component | Flag |
|---|---|---|---|
| `GET`  | `/api/coe/dead-letter` | List rows | `COE_DEAD_LETTER_ENABLED` |
| `GET`  | `/api/coe/dead-letter/depth` | Non-discarded, non-requeued count | `COE_DEAD_LETTER_ENABLED` |
| `GET`  | `/api/coe/dead-letter/{row_id}` | One row | `COE_DEAD_LETTER_ENABLED` |
| `POST` | `/api/coe/dead-letter/{row_id}/requeue` | Mark requeued | `COE_DEAD_LETTER_ENABLED` |
| `POST` | `/api/coe/dead-letter/{row_id}/discard` | Soft-delete | `COE_DEAD_LETTER_ENABLED` |
| `POST` | `/api/coe/circuit-breaker/{provider}/reset` | Force circuit CLOSED (audited) | `COE_OPERATOR_CONTROLS_ENABLED` |
| `POST` | `/api/coe/queue/pause` | Refuse new admissions for a class | `COE_OPERATOR_CONTROLS_ENABLED` |
| `POST` | `/api/coe/queue/resume` | Resume admissions | `COE_OPERATOR_CONTROLS_ENABLED` |

Pre-existing `/api/coe/metrics` and `/api/coe/state` are UNTOUCHED.

### 1.3 Per-component notes

**P4B.1 — RetryExecutor.** Class-keyed policies match plan §4.1:
`market_data`=5×(2→60s), `agent`=3×(4→30s), `backtest`=2×(10→60s),
`execution`=0 retries (fail fast), `monitoring`/`knowledge`=3×(2→30s),
`meta_learning`=3×(5→60s). When `COE_RETRY_ENABLED=false`, the executor
is a **pure pass-through** — one attempt, no backoff, `RetryOutcome`
returned. Event sink is injected (Mongo write path deferred to operator
wiring during Coherent UKIE Activation).

**P4B.2 — DeadLetterRepository.** Backs
`strategy_knowledge_base`-independent `workload_dead_letter`
collection. Fields per plan §4.2: `row_id`, `workload_class`,
`task_kind`, `task_id`, `error_class`, `error_message`, timestamps,
`attempts`, `provider`, `payload_snapshot`, `requeued_at`,
`discarded_at`. Every method short-circuits with a `flag_off` status
marker when the flag is off — the collection is never touched.
Depth query excludes requeued + discarded rows for the alert path.

**P4B.3 — WorkRecovery.** Sweeps `workload_events` for
`status="in_flight"` older than `STALE_INFLIGHT_S` (default 300s).
Per-row disposition delegated to injected `requeue_hook` /
`dead_letter_hook` — the sweeper doesn't decide retry-budget policy
itself. Idempotent; safe to invoke on every backend boot.

**P4B.4 — ProviderAwareAdmission.** Two-line decision surface. When
`COE_PROVIDER_AWARE_ADMISSION=false`, always admits with reason
`flag_off_pass_through`. When on, gates only `agent` + `backtest`
classes; consults an injected `breaker_state_lookup` callable
(operator wires this to `engines.ai_workforce.circuit_breaker` during
activation). HALF_OPEN → `admit=True, probe=True` (the VIE can then
issue exactly one probe request).

**P4B.5 — AgeBoost.** Pure math. Composable with the orchestrator's
`_score_task` via a single add. Threshold + interval + delta + cap
all env-tunable (`ORCH_AGE_BOOST_S`, `ORCH_AGE_BOOST_INTERVAL_S`,
`ORCH_AGE_BOOST_DELTA`, `ORCH_AGE_BOOST_MAX`). When the flag is off,
returns `delta=0.0` — scoring behaves exactly like Stage-1..3.

**P4B.6 — ElasticBandRedistributor.** Snapshot-based BACKTEST ↔
MUTATION loan planner. Loan fires when
`backtest_depth ≥ ELASTIC_HIGH_WATER` AND `mutation_depth == 0`.
Loan amount capped at 50% of the donor's reservation. Returns an
`ElasticBandPlan(active=True, ...)` that the orchestrator applies as a
scoring-pass kwarg. When the flag is off, `active=False`.

**P4B.7 — BudgetHardCap.** Composable hard cap layered ABOVE the
existing soft-cap surface (`orchestrator/budget_tracker`). Gates
`agent` + `backtest` classes only. Returns
`BudgetHardCapDecision(admit=False, reason="budget_hard_cap_reached")`
when `today_used_usd ≥ today_hard_cap`. When off, always admits.

**P4B.8 — OperatorControls.** Three admin actions:
- `circuit_reset` — force a provider's circuit CLOSED via injected hook
- `queue_pause` / `queue_resume` — set an in-memory predicate that the
  admission gate consults
Every action produces one `coe_operator_events` row (via injected sink)
carrying `action_id`, `kind`, `target`, `requested_by`, `reason`, `at`,
`pipeline_version_note`.

### 1.4 Files added / modified

Added (10 files):
- 9 modules in `backend/legacy/engines/coe_gamma/`
- `backend/tests/test_coe_gamma.py` (36 tests)

Modified (1 file):
- `backend/app/main.py` — mounts the COE γ router at boot (log line
  `mounted COE γ router` on success).

---

## 2. Feature-flag matrix

| Flag | Default | Effect ON |
|---|---|---|
| `COE_RETRY_ENABLED` | `false` | Per-class exponential-backoff retries active |
| `COE_DEAD_LETTER_ENABLED` | `false` | Dead-letter endpoints served; `workload_dead_letter` writes enabled |
| `COE_WORK_RECOVERY_ENABLED` | `false` | Boot-time stale in-flight sweep active |
| `COE_PROVIDER_AWARE_ADMISSION` | `false` | Circuit-breaker consulted before `agent`/`backtest` admission |
| `COE_AGE_BOOST_ENABLED` | `false` | Waiting tasks earn priority delta |
| `COE_ELASTIC_BAND_ENABLED` | `false` | BACKTEST ↔ MUTATION capacity loans active |
| `COE_BUDGET_HARD_CAP_ENABLED` | `false` | Daily USD hard cap enforced on `agent`/`backtest` |
| `COE_OPERATOR_CONTROLS_ENABLED` | `false` | Operator endpoints served |

Tunables (all optional):
- `STALE_INFLIGHT_S` (default `300`)
- `ORCH_AGE_BOOST_S` / `_INTERVAL_S` / `_DELTA` / `_MAX`
- `ELASTIC_HIGH_WATER` (default `50`)

**Every flag defaults OFF. Zero production behaviour change.**

---

## 3. Rollback SLA

| Rollback path | Mechanism | Target SLA |
|---|---|---|
| Retry disable | `COE_RETRY_ENABLED=false` + supervisor restart | ~30s |
| Dead-letter disable | `COE_DEAD_LETTER_ENABLED=false` + restart | ~30s (endpoints 503; collection preserved for audit) |
| Work-recovery disable | `COE_WORK_RECOVERY_ENABLED=false` + restart | ~30s |
| Provider-aware admission disable | `COE_PROVIDER_AWARE_ADMISSION=false` | ~30s |
| Age-boost disable | `COE_AGE_BOOST_ENABLED=false` | ~30s (scoring returns to Stage-1..3) |
| Elastic bands disable | `COE_ELASTIC_BAND_ENABLED=false` | ~30s |
| Budget hard-cap disable | `COE_BUDGET_HARD_CAP_ENABLED=false` | ~30s |
| Operator controls disable | `COE_OPERATOR_CONTROLS_ENABLED=false` | ~30s |
| Nuclear P4B rollback | Flip every `COE_*_ENABLED=false` + restart | ~60s |

All meet the 60-s platform SLA.

---

## 4. Cumulative test status

```
tests/test_knowledge_*.py + tests/test_domain_router.py +
tests/test_license_gate.py + tests/test_trust_scorer.py +
tests/test_dedup_and_repository.py + tests/test_bi5_bid_diff.py +
tests/test_promote_bridge.py + tests/test_retro_score.py +
tests/test_connector_scaffolding.py + tests/test_connectors_stage4.py +
tests/test_coe_gamma.py
──────────────────────────────────────────────────────────────
Cumulative UKIE + BI5 + Stage-4 P4A + P4B unit tests: 275 / 275 PASSING
```

Test-count evolution:
- Pre-P4A baseline: 181
- After P4A: 239 (+58)
- **After P4B: 275 (+36 P4B)**
- Test coverage per component:
  - RetryExecutor — 5 tests (pass-through, retry-and-succeed, exhaust,
    non-retryable, policy fallback)
  - Dead-letter — 5 tests (flag-off, record+list, requeue, discard,
    depth)
  - Work recovery — 2 tests (flag-off, sweep with stale rows)
  - Provider-aware admission — 5 tests (flag-off, class-not-gated,
    open, half-open, closed)
  - Age boost — 4 tests (flag-off, below threshold, above threshold
    growth, cap)
  - Elastic bands — 4 tests (flag-off, below high-water, active loan,
    donor busy)
  - Budget hard-cap — 4 tests (flag-off, class-not-gated, reached,
    headroom)
  - Operator controls — 3 tests (flag-off, reset+audit, pause/resume)
  - Router — 4 tests (dead-letter 503s, operator 503s, list flow,
    circuit-reset flow)

---

## 5. Architectural recommendations before proceeding to P4C

1. **Composition is explicit and one-way.** Every P4B module imports
   only from its own package + stdlib. Wiring into the pre-existing
   orchestrator is done by the operator during activation via
   dependency injection — this keeps P4B fully unit-testable and
   preserves the orchestrator's cognitive load exactly as-is.
2. **`workload_dead_letter` TTL is a boot concern.** The plan calls
   for a TTL index on `first_failed_at` (default 90 days). This is
   NOT applied by the module because index creation should be
   idempotent + centralised. Recommend adding to
   `engines/db_indexes.py` during activation. Not blocking for P4B.
3. **Work recovery reads `workload_events`.** That collection is
   populated by the pre-existing orchestrator. When
   `COE_WORK_RECOVERY_ENABLED=true` is flipped WITHOUT the
   orchestrator having ever written to that collection, the sweep is
   simply a no-op — safe. No coupling required.
4. **Provider-aware admission uses a lookup callable, not a symbol
   import.** This dodges the circuit-breaker module's import-time
   side effects and keeps every P4B test hermetic. When wiring
   during activation, prefer a lightweight adapter:
   `lambda p: circuit_breaker.get_state(p)`.
5. **Age boost + elastic bands are additive to scoring.** They land
   as `+ compute_age_boost(...).delta` and an ElasticBandPlan
   snapshot the orchestrator applies at scoring time. Both are
   pure functions — no ordering hazards.
6. **Budget hard-cap sits ABOVE the existing soft-cap.** Do not
   modify the pre-existing soft-cap warning surface. When both
   fire, the hard cap wins.

**Recommendation:** proceed to **P4C — UKIE γ** (retrieval + ranking
+ lifecycle + confidence evolution + governance policy language).
P4B leaves the platform in a clean state; nothing in P4C touches
COE surfaces.

---

## 6. Live-verification checklist (operator, when ready)

Preview pod, all COE γ flags OFF (default):
- [ ] `GET /api/coe/dead-letter` → 503
- [ ] `POST /api/coe/circuit-breaker/openai/reset` (body: reason+by) → 503
- [ ] `GET /api/coe/metrics` and `GET /api/coe/state` UNCHANGED
      (pre-existing endpoints)

With `COE_DEAD_LETTER_ENABLED=true`:
- [ ] `GET /api/coe/dead-letter` → 200, `count=0`
- [ ] `GET /api/coe/dead-letter/depth` → 200, `depth=0`
- [ ] `GET /api/coe/dead-letter/unknown-id` → 404

With `COE_OPERATOR_CONTROLS_ENABLED=true` + wired breaker hook:
- [ ] `POST /api/coe/circuit-breaker/openai/reset`
      `{"requested_by":"op","reason":"reopen"}` → 200
      `{"status":"reset","provider":"openai","action_id":"..."}`
- [ ] `POST /api/coe/queue/pause`
      `{"workload_class":"agent","requested_by":"op","reason":"drain"}`
      → 200 `{"status":"paused",...}`
- [ ] `POST /api/coe/queue/resume` (same body) → 200
      `{"status":"resumed",...}`

Rollback:
- [ ] Every flag → `false` + restart → every new endpoint returns 503,
      no writes to `workload_dead_letter`, orchestrator behaviour
      byte-identical to Stage 3.γ.

---

*Status:* **P4B implemented, tested, dormant. Awaiting operator signal
to proceed to P4C — UKIE γ.**
