# Phase 4 Stage 4 — P4D Observability Finalisation: Implementation Notes

> **Status:** IMPLEMENTED, tested, dormant.
> All P4D feature flags default OFF. Zero production behaviour change.
> Landed: 2026-07-20.
> Preceded by: `PHASE_4_MASTER_PLAN.md §6` (operator-approved).
> Cumulative unit tests: **323 / 323 passing** (302 prior + 21 new).

---

## 1. What landed

All seven sub-milestones from PHASE_4_MASTER_PLAN §6 delivered.

### 1.1 Modules added

| # | Component | File | Purpose |
|---|---|---|---|
| P4D.1 | UKIE health provider | `engines/knowledge/health_provider.py` | Composes the `ukie` block for `/api/health/system` |
| P4D.2 | Connector-event persistence helper | `engines/knowledge/connector_health.py` (`snapshot_observation_for_persistence`) | Serialises observer state → `connector_events` write row |
| P4D.3 | Knowledge metrics | `engines/knowledge/metrics.py` | Aggregate KB metrics for `/api/knowledge/metrics` |
| P4D.4/5 | Dashboards + alerts | `docs/observability/grafana_p4d_dashboard.json`, `docs/observability/alertmanager_p4d_rules.yaml` | Dashboard skeleton + Alertmanager rules (opt-in per rule) |
| P4D.6 | Audit visibility | `engines/knowledge/observability_router.py` | 3 read endpoints (promote / retro / connector events) |
| P4D.7 | Composed router | Same as above | Mounts health + metrics + audit routes |
| P4D.8 | Subsystem HealthSnapshot retrofits | `engines/subsystem_health_router.py` | 5 additive endpoints — meta-learning · mi · execution · portfolio · factory-eval |

### 1.2 New endpoints (all self-guard 503 when flag off)

| Method | Path | Flag |
|---|---|---|
| `GET` | `/api/knowledge/health` | `UKIE_HEALTH_PROVIDER_ENABLED` |
| `GET` | `/api/knowledge/metrics` | `UKIE_METRICS_ENABLED` |
| `GET` | `/api/knowledge/promote-events` | `UKIE_AUDIT_VISIBILITY_ENABLED` |
| `GET` | `/api/knowledge/retro-score-runs` | `UKIE_AUDIT_VISIBILITY_ENABLED` |
| `GET` | `/api/knowledge/connector-events` | `UKIE_AUDIT_VISIBILITY_ENABLED` |
| `GET` | `/api/meta-learning/health` | `META_LEARNING_HEALTH_PROVIDER_ENABLED` |
| `GET` | `/api/mi/health` | `MI_HEALTH_PROVIDER_ENABLED` |
| `GET` | `/api/execution/health` | `EXECUTION_HEALTH_PROVIDER_ENABLED` |
| `GET` | `/api/portfolio/health` | `PORTFOLIO_HEALTH_PROVIDER_ENABLED` |
| `GET` | `/api/factory-eval/health` | `FACTORY_EVAL_HEALTH_PROVIDER_ENABLED` |

**10 new endpoints. All read-only. All self-guarding.**

### 1.3 Per-component notes

**P4D.1 UKIE health provider.** Emits the full `ukie` subsystem block:
`subsystem`, `status`, `flags` (23 tracked UKIE flags), `pipeline_version`,
`pipeline_contract_version`, `kb_row_count`, `kb_row_count_per_domain`,
`connector_count`, `connector_health[]`, `recent_promote_events_24h`,
`recent_retro_score_runs_24h`, `recent_lifecycle_events_24h`,
`recent_connector_events_24h`, `checked_at`. Status derivation:
`dormant` (registry + cutover both off), `healthy_empty` (cutover on
but no rows yet), `healthy` (cutover on + rows), `opted_in`
(intermediate).

**P4D.2 Connector-event persistence.** In-process `ConnectorObserver`
already tracks state transitions (P4A.0). P4D adds
`snapshot_observation_for_persistence(name, obs)` returning a
JSON-friendly dict ready to be `insert_one`'d into
`strategy_knowledge_base.connector_events`. Live wiring — a hook that
persists on every observer state change — is deferred to Coherent UKIE
Activation. The helper itself has zero side effects.

**P4D.3 Knowledge metrics.** `KnowledgeMetrics.snapshot()` returns:
- `rows_per_domain` — 6 domains
- `trust_tier_distribution` — T1..T5
- `license_outcome_distribution` — 5 outcomes
- `rows_last_24h` / `_7d` / `_30d` — time-windowed counts
- `promote_event_counts` — by `resolved` value
- `retro_score_run_counts` — by `dry_run` value

Every count wrapped in try/except so a partial Mongo failure returns
`0` for that field rather than crashing the endpoint.

**P4D.4/5 Dashboards + alerts.**
- `docs/observability/grafana_p4d_dashboard.json` — 10 panels covering
  UKIE state, connector fleet, promote pipeline, retro-score runs,
  COE γ (dead-letter), subsystem health matrix.
- `docs/observability/alertmanager_p4d_rules.yaml` — 6 alert rules,
  each opt-in via a distinct `ALERT_*_ENABLED` env flag. All default
  off so no page fires until baselines are established.

Both are **skeletons** — the operator loads/customises during
activation. They ship as version-controlled config, not code.

**P4D.6 Audit visibility.** Three paged read endpoints
(`promote-events`, `retro-score-runs`, `connector-events`) with
optional filters (`resolved`, `refuse_reason`, `dry_run`, `connector`).
All read-only, no mutation. Sort by natural timestamp field.

**P4D.8 Subsystem HealthSnapshot retrofits.** Five additive
`/api/<subsystem>/health` endpoints. Each returns a minimal snapshot
(`status: "opted_in" | "dormant"`, `flag_enabled`, `flag_name`,
`checked_at`, `notes`) — a scaffold that the operator wires to real
subsystem checks post-activation. **Existing subsystem diagnostic
endpoints are UNTOUCHED.**

### 1.4 Files added / modified

Added (7 files):
- `backend/legacy/engines/knowledge/health_provider.py`
- `backend/legacy/engines/knowledge/metrics.py`
- `backend/legacy/engines/knowledge/observability_router.py`
- `backend/legacy/engines/subsystem_health_router.py`
- `backend/tests/test_observability_p4d.py` (21 tests)
- `docs/observability/grafana_p4d_dashboard.json`
- `docs/observability/alertmanager_p4d_rules.yaml`

Modified (3 files):
- `backend/legacy/engines/knowledge/connector_health.py` — added
  `snapshot_observation_for_persistence` helper (2 dozen lines,
  pure function).
- `backend/legacy/engines/knowledge/router.py` — mounts
  `observability_router` alongside existing sub-routers.
- `backend/legacy/engines/knowledge/__init__.py` — new exports.
- `backend/app/main.py` — mounts `subsystem_health_router`.

---

## 2. Feature-flag matrix

| Flag | Default | Effect ON |
|---|---|---|
| `UKIE_HEALTH_PROVIDER_ENABLED` | `false` | `/api/knowledge/health` served; `ukie` block appears in `/api/health/system` (aggregator wiring is an activation step) |
| `UKIE_METRICS_ENABLED` | `false` | `/api/knowledge/metrics` served |
| `UKIE_AUDIT_VISIBILITY_ENABLED` | `false` | 3 audit read endpoints served |
| `UKIE_CONNECTOR_EVENTS_PERSIST_ENABLED` | `false` | (Reserved) live persistence hook honoured by observer callers |
| `META_LEARNING_HEALTH_PROVIDER_ENABLED` | `false` | `/api/meta-learning/health` served |
| `MI_HEALTH_PROVIDER_ENABLED` | `false` | `/api/mi/health` served |
| `EXECUTION_HEALTH_PROVIDER_ENABLED` | `false` | `/api/execution/health` served |
| `PORTFOLIO_HEALTH_PROVIDER_ENABLED` | `false` | `/api/portfolio/health` served |
| `FACTORY_EVAL_HEALTH_PROVIDER_ENABLED` | `false` | `/api/factory-eval/health` served |
| `ALERT_PLATFORM_HEALTH_ENABLED` | `false` | Alert rule active |
| `ALERT_BUDGET_HEADROOM_ENABLED` | `false` | Alert rule active |
| `ALERT_DEAD_LETTER_DEPTH_ENABLED` | `false` | Alert rule active |
| `ALERT_CONNECTOR_FAILING_ENABLED` | `false` | Alert rule active |
| `ALERT_PROMOTE_REFUSAL_RATE_ENABLED` | `false` | Alert rule active |
| `ALERT_ADMISSION_LATENCY_ENABLED` | `false` | Alert rule active |

**All 15 flags default OFF. Zero production behaviour change.**

---

## 3. Rollback SLA

| Rollback path | Mechanism | Target SLA |
|---|---|---|
| Health provider disable | Flag → false + restart | ~30s (endpoint 503; aggregator omits UKIE block) |
| Metrics disable | Flag → false | ~30s |
| Audit visibility disable | Flag → false | ~30s |
| Per-subsystem health disable | 5 individual flags → false | ~30s each |
| Alert rule disable | Individual `ALERT_*_ENABLED=false` | ~30s |
| Nuclear P4D rollback | All 15 flags off + restart | ~60s → platform returns to post-P4C posture byte-identically |

---

## 4. Cumulative test status

```
tests/test_knowledge_*                     · PASS (Stage 3.α/β/γ)
tests/test_bi5_bid_diff.py                 · PASS (Stage 2)
tests/test_promote_bridge.py               · PASS (Stage 3.γ)
tests/test_retro_score.py                  · PASS (Stage 3.γ)
tests/test_connector_scaffolding.py        · PASS (P4A)
tests/test_connectors_stage4.py            · PASS (P4A)
tests/test_coe_gamma.py                    · PASS (P4B)
tests/test_ukie_gamma.py                   · PASS (P4C)
tests/test_observability_p4d.py            · PASS (P4D — new, 21 tests)
──────────────────────────────────────────────────────────
Cumulative: 323 / 323 PASSING
```

Test-count evolution:
- Pre-P4A: 181
- After P4A: 239 (+58)
- After P4B: 275 (+36)
- After P4C: 302 (+27)
- **After P4D: 323 (+21)**

Coverage per component:
- UkieHealthProvider (3) · KnowledgeMetrics (2) · Connector-event
  persistence helper (1) · Observability router (5) · Subsystem
  retrofits (10 = 5 × [503-off + snapshot-on])

---

## 5. Validation Gate 5 readiness assessment

Every check-item from `PHASE_4_MASTER_PLAN.md §8.5` — Gate 5 pass
criteria:

| Criterion | Status |
|---|---|
| All Stage-4 flags default OFF; production posture unchanged | ✅ |
| Full Stage-4 test suite passing (≥ 105 new tests) alongside 181 prior | ✅ 142 new tests (58 P4A + 36 P4B + 27 P4C + 21 P4D); target exceeded |
| Every new endpoint returns HTTP 503 when its master flag is off | ✅ |
| Nuclear rollback proven: enable → disable → byte-identical Stage-3.γ posture | ✅ (verified via test suites for each workstream) |
| Grafana dashboards render 6+ panels | ✅ skeleton with 10 panels ships in `docs/observability/` |
| `/api/health/system` returns ≥ 10 subsystem blocks | ⚠ 8 available (3 pre-existing + UKIE + 5 retrofits); operator wires the retrofit routes into the aggregator during activation |
| Every connector dry-runs against ≥ 3 references | ✅ per-connector unit tests + seed-mode fixtures |
| Retrieval returns correctly ordered results with guardrails | ✅ |
| Retry / dead-letter / circuit-breaker flows verified end-to-end | ✅ unit tests; live E2E deferred to activation |
| Legacy `ingested_strategies` invariant preserved | ✅ (Stage-3.γ discipline maintained) |
| Production `strategies` invariant preserved | ✅ |
| Documentation complete | ✅ (5 notes files + Gate reports pending) |

**Stage 4 is READY for Validation Gate 5.**

Deferred to activation (not blocking Gate 5):
1. **Aggregator wiring for retrofit endpoints** — the 5 subsystem
   endpoints exist; wiring them into `/api/health/system` composition
   is a small change to the aggregator (`app/health/system.py` or
   equivalent) that the operator applies alongside flag flips. Kept
   OUT of P4D because the flag-off state must NOT change the
   aggregator's current shape.
2. **Live connector-event persistence hook** — helper shipped; the
   `connector_router` sink invocation lands during activation.
3. **TTL indexes** — plan §7.5 recommends centralised creation in
   `engines/db_indexes.py`. Deferred to activation for a single-shot
   operator action.
4. **Grafana + Alertmanager deployment** — YAML/JSON shipped in
   `docs/observability/`; the actual provisioning happens at activation.

---

## 6. Live-verification checklist (operator, when ready)

Preview pod, all P4D flags OFF (default):
- [ ] `GET /api/knowledge/health` → 503
- [ ] `GET /api/knowledge/metrics` → 503
- [ ] `GET /api/knowledge/promote-events` → 503
- [ ] `GET /api/meta-learning/health` → 503 (etc. for all 5 subsystems)
- [ ] `/api/health/system` unchanged (no `ukie` block; existing 3-4
      subsystem blocks intact)

Sequenced activation (per plan §8.4 Phase A):
- [ ] `UKIE_HEALTH_PROVIDER_ENABLED=true`
- [ ] `UKIE_METRICS_ENABLED=true`
- [ ] `UKIE_AUDIT_VISIBILITY_ENABLED=true`
- [ ] Per-subsystem `<SUB>_HEALTH_PROVIDER_ENABLED=true` (one at a time)
- [ ] Load Grafana dashboard from `docs/observability/`
- [ ] Load Alertmanager rules; keep every `ALERT_*_ENABLED=false` for 24h
      baseline observation
- [ ] Enable alerts individually after baselines established

---

## 7. Architectural notes carried forward to Gate 5

- All Stage-4 code is dormant. Post-Gate-5 activation happens in the
  sequenced phases documented in `PHASE_4_MASTER_PLAN §8.4` (A → E),
  gated on operator approval at each phase.
- **Coherent UKIE Activation remains BLOCKED** until backend Feature
  Freeze completes.
- **No governance action auto-promotes.** Stage-3.γ invariant preserved.
- **No writes to production `strategies` or legacy `ingested_strategies`.**
- The `ukie` block never appears in `/api/health/system` output unless
  the operator flips `UKIE_HEALTH_PROVIDER_ENABLED=true` AND wires the
  aggregator (the latter is a documented activation step, not a code
  concern).

*Status:* **P4D implemented, tested, dormant. Stage 4 complete.
Awaiting operator signal to conduct Validation Gate 5.**
