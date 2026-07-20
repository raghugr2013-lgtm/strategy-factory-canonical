# Coherent UKIE Activation Plan (v1)

> **Status:** DRAFT — awaiting operator sign-off.
> Compiled: 2026-07-20.
> Backend: v1.1.0-stage4, commit `3ed832a`, feature-frozen.
> Precondition: Backend Feature Freeze ✅ approved 2026-07-20.
>
> This plan sequences the activation of every Phase 2 Stage 3 + Phase 4
> feature that currently sits dormant. Nothing is enabled at ratification;
> flags flip only during the phases below, one at a time, with 24-hour
> observation windows between phases (adjustable per operator judgement).

---

## 0. Guiding principles

1. **One flag at a time.** Never batch flag flips across component
   boundaries.
2. **Observation-gated.** Every phase requires a 24-h observation
   window before the next. Extend on operator judgement; never
   compress below 4 h without a documented reason.
3. **Every phase has a documented rollback.** Executed within 60 s
   of an abort decision.
4. **Success + abort criteria are numeric** wherever possible.
   Vibes-based judgement is not an activation criterion.
5. **No implementation work.** Bug fixes and operational wiring only.
   New features require lifting the freeze.
6. **Nothing autonomous.** Recommendation Mode + Autonomous Mode
   remain locked until the full validation stack (paper broker + 24h + 72h)
   has passed.

---

## 1. Preconditions (before Phase A)

- [ ] Backend v1.1.0-stage4 deployed and healthy (baseline)
- [ ] `.env` populated; every Stage-3/Stage-4 flag confirmed OFF at boot
- [ ] Cumulative unit tests 323/323 passing in preview
- [ ] Mongo reachable; `strategy_knowledge_base` DB accessible
- [ ] Grafana + Alertmanager deployed (skeleton configs applied,
      alerts silent)
- [ ] Emergent LLM key available (only needed once AGENT tasks are
      exercised in later phases)
- [ ] Operator + on-call engineer identified for the 24 h window

---

## 2. Phase A — Observability first (read-only, safe)

**Goal:** enable every dormant read-only surface to establish
baselines BEFORE flipping any writer.

### 2.1 Activation sequence

| Step | Flag | Verify |
|---|---|---|
| A.1 | `UKIE_HEALTH_PROVIDER_ENABLED=true` | `GET /api/knowledge/health` → 200 with `status:"dormant"` |
| A.2 | `META_LEARNING_HEALTH_PROVIDER_ENABLED=true` | `GET /api/meta-learning/health` → 200 |
| A.3 | `MI_HEALTH_PROVIDER_ENABLED=true` | `GET /api/mi/health` → 200 |
| A.4 | `EXECUTION_HEALTH_PROVIDER_ENABLED=true` | `GET /api/execution/health` → 200 |
| A.5 | `PORTFOLIO_HEALTH_PROVIDER_ENABLED=true` | `GET /api/portfolio/health` → 200 |
| A.6 | `FACTORY_EVAL_HEALTH_PROVIDER_ENABLED=true` | `GET /api/factory-eval/health` → 200 |
| A.7 | `UKIE_METRICS_ENABLED=true` | `GET /api/knowledge/metrics` → 200 with zero counts |
| A.8 | `UKIE_AUDIT_VISIBILITY_ENABLED=true` | `GET /api/knowledge/promote-events`, `/retro-score-runs`, `/connector-events` all → 200 with `count: 0` |
| A.9 | Aggregator wiring | Add UKIE + 5 retrofits to `/api/health/system` composition; deploy |
| A.10 | Grafana dashboard | Provision `docs/observability/grafana_p4d_dashboard.json` |

### 2.2 Monitoring checkpoints (during 24 h window)

- `/api/health/system` continues returning 200
- `platform_health_score` remains ≥ 95 (pre-activation baseline)
- No new error rows in `/var/log/supervisor/backend.*.log`
- Every subsystem health endpoint returns `flag_enabled: true`
- Dashboards populate; alerts remain silent (opt-in per rule)

### 2.3 Success criteria
- All 10 endpoints return 200
- `/api/health/system` shape includes `ukie` block
- Zero regression in pre-existing `platform_health_score`
- Dashboards render all panels within 5 s

### 2.4 Abort criteria
- Any endpoint returns 5xx
- `platform_health_score` drops > 5 points
- Backend restarts unexpectedly

### 2.5 Rollback
1. Flip Phase-A flags to `false` in `.env`
2. `sudo supervisorctl restart backend`
3. Verify Phase-A endpoints return 503
4. Recovery SLA: ≤ 60 s

---

## 3. Phase B — COE γ resilience (safe when properly gated)

**Goal:** enable the eight COE γ components in dependency order so
retry / dead-letter / recovery / admission are all in place before
UKIE γ starts producing operator-visible surfaces.

### 3.1 Activation sequence (one flag per 24 h)

| Step | Flag | Wire-up |
|---|---|---|
| B.1 | `COE_RETRY_ENABLED=true` | RetryExecutor composed into WorkloadQueue submit path |
| B.2 | `COE_DEAD_LETTER_ENABLED=true` | Apply TTL index on `workload_dead_letter.first_failed_at` (90 d) |
| B.3 | `COE_WORK_RECOVERY_ENABLED=true` | Requeue + dead-letter hooks wired at boot |
| B.4 | `COE_PROVIDER_AWARE_ADMISSION=true` | `breaker_state_lookup` wired to `engines.ai_workforce.circuit_breaker` |
| B.5 | `COE_AGE_BOOST_ENABLED=true` | `+ compute_age_boost().delta` added to orchestrator's `_score_task` |
| B.6 | `COE_ELASTIC_BAND_ENABLED=true` | Redistributor's plan applied on scoring pass |
| B.7 | `COE_BUDGET_HARD_CAP_ENABLED=true` | BudgetHardCap composed with existing soft-cap warning |
| B.8 | `COE_OPERATOR_CONTROLS_ENABLED=true` | Audit sink wired to `coe_operator_events` |

### 3.2 Monitoring checkpoints
- `/api/coe/metrics` shows retry rate ≥ 0, no anomalies
- `/api/coe/dead-letter/depth` remains at 0 in normal operation
- Admission p95 latency stays < 200 ms
- Budget headroom trends match pre-activation baseline
- Circuit breaker states visible on dashboard

### 3.3 Success criteria (per component)
- **B.1** retry: after seeding a mock transient failure, task
  succeeds on retry; `attempts > 1` visible in logs
- **B.2** dead-letter: exhausted retry produces a row; `GET /api/coe/dead-letter` returns it
- **B.3** work recovery: kill backend mid-task; on restart, stale
  in-flight row is either requeued or dead-lettered (verify counts
  in sweep response)
- **B.4** admission: force circuit OPEN in preview → task returns
  `provider_unavailable`; force HALF_OPEN → task admits with
  `probe=true`
- **B.5** age boost: task queued > 60 s shows priority delta > 0
- **B.6** elastic band: seed BACKTEST depth > `ELASTIC_HIGH_WATER`
  + MUTATION depth 0 → plan.active=true
- **B.7** budget hard-cap: force used_usd ≥ hard_cap in preview →
  AGENT admissions return `budget_hard_cap_reached`
- **B.8** operator controls: circuit-reset writes one
  `coe_operator_events` row

### 3.4 Abort criteria (any component)
- Retry storm: `retry_rate_per_class` > 10× baseline sustained 5 min
- Dead-letter depth > 100
- Admission p95 latency > 500 ms sustained 5 min
- Any provider circuit stuck OPEN > 30 min without operator action
- `platform_health_score` < 80

### 3.5 Rollback
Per component: flip the component's `COE_*_ENABLED=false` + restart.
Nuclear: all 8 flags off + restart. SLA ≤ 60 s.
Data preserved: `workload_dead_letter` + `coe_operator_events` rows
remain for audit.

---

## 4. Phase C — UKIE γ retrieval (still no KB writes)

**Goal:** enable retrieval + ranking + lifecycle + confidence +
governance policy. Every capability is read-only OR advisory. No
UKIE-KB writes yet — `UKIE_GOVERNANCE_CUTOVER` still OFF.

### 4.1 Activation sequence

| Step | Flag | Verify |
|---|---|---|
| C.1 | `UKIE_QUERY_API_ENABLED=true` | `POST /api/knowledge/query` → 200 with `matches: []` (KB empty) |
| C.2 | Apply TTL indexes | `lifecycle_events` (180 d), `knowledge_endorsement_events` (90 d), `knowledge_contradiction_events` (365 d), `connector_events` (180 d) |
| C.3 | `UKIE_LIFECYCLE_SWEEP_ENABLED=true` | `POST /api/knowledge/lifecycle-sweep {"dry_run":true}` → 200 with zero-count summary |
| C.4 | `UKIE_RANKING_V2_ENABLED=true` | Query same as C.1; ranking breakdown appears; `final_score == 0` (empty KB) |
| C.5 | `UKIE_CONFIDENCE_EVOLUTION_ENABLED=true` | Endorsement + contradiction endpoints return 200 |
| C.6 | `UKIE_GOVERNANCE_POLICY_ENABLED=true` | Seed a policy in `promote_policies`; evaluate endpoint returns advisory tags |

### 4.2 Monitoring checkpoints
- `/api/knowledge/query` p95 latency < 100 ms (empty KB baseline)
- Ranking breakdown includes v2 multipliers when v2 flag on
- Lifecycle sweep dry-run reports per-domain counts without touching Mongo
- Governance advisory tags NEVER call the promote bridge (verify via
  `/api/knowledge/promote-events` — count stays at 0)

### 4.3 Success criteria
- `POST /api/knowledge/query` returns ordered results respecting
  ai_context_policy (no `content_bytes` in response for any domain)
- Ranking-v2 breakdown reasons visible
- Lifecycle sweep audit rows land in `lifecycle_events` on non-dry-run
- Endorsement + contradiction event stores accept rows
- Governance verdict stamps `advisory_tags` WITHOUT touching
  trust_tier / license / hard rails

### 4.4 Abort criteria
- Any writer touches production `strategies` (should NEVER happen)
- Governance produces an auto-promote call (should NEVER happen —
  advisory-only invariant)
- Query p95 > 500 ms sustained 5 min
- Any KB row observed with `learning_only=false` OR
  `eligible_for_deploy=true`

### 4.5 Rollback
Per component: flip the flag off + restart. All Stage-4 collections
preserved (audit history intact).

---

## 5. Phase D — Connector fleet (new KB writers)

**Goal:** enable the Stage-3 pipeline + Stage-4 connectors + the
governance cutover. **This is the first phase that writes to the
UKIE-KB.**

**PRECONDITION:** Phases A–C stable for at least 24 h each. No open
abort conditions.

### 5.1 Activation sequence — Stage 3 first

| Step | Flag | Verify |
|---|---|---|
| D.1 | `UKIE_DOMAIN_REGISTRY_ENABLED=true` | `GET /api/knowledge/domains` → 200 with 6 domains |
| D.2 | `ENABLE_DOMAIN_ROUTING=true` | Pipeline routing stage active in dry-run |
| D.3 | `ENABLE_LICENSE_GATE=true` | License-gate stage active |
| D.4 | `ENABLE_TRUST_SCORER=true` | Trust scorer stage active |
| D.5 | `ENABLE_DEDUP_CHECK=true` | Dedup stage active |
| D.6 | `POST /api/knowledge/dry-run` | Preview pipeline output on synthetic fixture |

### 5.2 The critical cutover

| Step | Flag | Verify |
|---|---|---|
| D.7 | `UKIE_GOVERNANCE_CUTOVER=true` | **First real writes to `strategy_knowledge_base`.** Monitor for 24 h with connectors STILL disabled — writes should be zero (no connectors producing items yet) |

### 5.3 Connector fleet activation

| Step | Flag | Wire-up |
|---|---|---|
| D.8 | `UKIE_CONNECTOR_FRAMEWORK_ENABLED=true` | Verify Stage-4 connectors visible in `list_connectors()` |
| D.9 | `UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED=true` | Read-only source. Wire `db_getter`. Observe `/api/knowledge/health.kb_row_count` growth. |
| D.10 | `UKIE_CONNECTOR_ARXIV_ENABLED=true` | Wire live `aiohttp.ClientSession` (or curated seed list). Observe RESEARCH domain row growth. |
| D.11 | `UKIE_CONNECTOR_PDF_ENABLED=true` | Wire live client + curated seed URLs. |
| D.12 | `UKIE_CONNECTOR_PROPFIRM_ENABLED=true` | Wire per-firm allow-list + optional OAuth. |
| D.13 | `UKIE_CONNECTOR_TRADINGVIEW_ENABLED=true` | Wire curated seed of Pine scripts. |
| D.14 | `UKIE_CONNECTOR_EVENTS_PERSIST_ENABLED=true` | Wire observer callback → `connector_events` writes |

### 5.4 Promote Bridge activation (per-item, dry-run first)

| Step | Flag | Verify |
|---|---|---|
| D.15 | `UKIE_PROMOTE_BRIDGE_ENABLED=true` (with `UKIE_PROMOTE_DRY_RUN=true`) | `POST /api/knowledge/promote/{kb_id}` in dry-run — no writes to production `strategies` |
| D.16 | After N successful dry-runs, individual commit | `POST /api/knowledge/promote/{kb_id}?dry_run=0` — one item at a time |

### 5.5 Retro-scoring (optional, one-shot)

| Step | Flag | Verify |
|---|---|---|
| D.17 | `UKIE_RETRO_SCORE_ENABLED=true` | `POST /api/knowledge/retro-score {"dry_run":true}` — preview |
| D.18 | Real run | `POST /api/knowledge/retro-score {"dry_run":false, "confirm_write":"yes_write_the_kb"}` — one time, backfilling legacy `ingested_strategies` |

### 5.6 Monitoring checkpoints
- `/api/knowledge/health.kb_row_count` grows predictably per connector
- `/api/knowledge/connectors/{name}/health.state = "healthy"` for
  every enabled connector
- Zero writes to legacy `ingested_strategies` (verify via Mongo audit)
- Every KB row carries `learning_only=true, eligible_for_deploy=false`
  (spot-check via `/api/knowledge/query`)
- `/api/knowledge/promote-events` grows only for explicit operator
  promote calls

### 5.7 Success criteria
- Each connector's `health.state` transitions to `healthy`
- KB row growth matches connector output (per-connector counts audited)
- Zero rows with `learning_only=false` observed
- Promote-events audit trail complete
- Legacy `ingested_strategies` write count = 0

### 5.8 Abort criteria
- Any write to legacy `ingested_strategies` observed
- Any production `strategies` row without `origin="ukie_promote"` or
  with `eligible_for_deploy=true`
- Connector failure rate > 50 % sustained 30 min
- KB write errors > 5 % sustained 15 min

### 5.9 Rollback (per phase D step)
- Per-connector: `UKIE_CONNECTOR_<NAME>_ENABLED=false` + restart
- Framework: `UKIE_CONNECTOR_FRAMEWORK_ENABLED=false`
- Cutover rollback: `UKIE_GOVERNANCE_CUTOVER=false` — KB writes stop;
  KB rows preserved for audit
- Data rollback (per connector): `db.strategy_knowledge_base.<coll>.deleteMany({connector_name:"<name>"})`
- Data rollback (retro-score): `POST /api/knowledge/retro-score/rollback/{run_id}`
- Data rollback (promote-bridge): per-item `POST /api/knowledge/promote/{kb_id}/rollback`
- Nuclear: flip all D-phase flags off + `deleteMany({origin:"ukie_promote"})` on prod strategies

---

## 6. Phase E — Alerting

**Goal:** activate the six Alertmanager rules once 24 h of live
baselines have been observed under Phase D.

### 6.1 Activation sequence
| Step | Flag |
|---|---|
| E.1 | `ALERT_PLATFORM_HEALTH_ENABLED=true` (threshold: score < 60) |
| E.2 | `ALERT_BUDGET_HEADROOM_ENABLED=true` (threshold: < 10 % of hard cap) |
| E.3 | `ALERT_DEAD_LETTER_DEPTH_ENABLED=true` (threshold: > 100) |
| E.4 | `ALERT_CONNECTOR_FAILING_ENABLED=true` |
| E.5 | `ALERT_PROMOTE_REFUSAL_RATE_ENABLED=true` (> 50 % sustained 30 min) |
| E.6 | `ALERT_ADMISSION_LATENCY_ENABLED=true` (p95 > 200 ms sustained 5 min) |

### 6.2 Success criteria
- Each rule fires correctly against a synthetic breach in preview
- No false-positive alerts fire in the first 24 h

### 6.3 Rollback
Per rule: `ALERT_<NAME>_ENABLED=false` + reload Alertmanager.

---

## 7. Overall success — activation complete

Coherent UKIE Activation is complete when:

- All Phase A–E flags on
- 24 h continuous observation window shows platform health ≥ 95
- No abort conditions triggered in any phase
- KB row count growth stable (± 20 % over 24 h)
- Every audit collection has TTL indexes applied
- Grafana dashboards populated; alerts armed but not firing in
  steady state
- Legacy `ingested_strategies` invariant preserved
- Production `strategies` invariant preserved

**Post-activation roadmap remains:**
1. VPS deployment (if activation was in preview)
2. Paper broker validation
3. 24-hour validation
4. 72-hour validation
5. Recommendation Mode
6. Autonomous Mode
7. Frontend implementation

---

## 8. Overall abort

If **any** phase abort criterion fires:

1. Execute that phase's rollback (≤ 60 s target)
2. Investigate; document root cause in a follow-up doc under `/app/memory/`
3. Do NOT proceed to the next phase until the root cause is
   understood and remediated
4. If two consecutive phases abort, halt activation entirely; call
   an operator review before any re-attempt

---

## 9. Operator sign-off checklist

- [ ] Phase A–E sequences reviewed and accepted
- [ ] Success criteria numeric where possible
- [ ] Abort criteria numeric where possible
- [ ] Rollback procedure documented for each phase
- [ ] TTL index list confirmed for Phase C.2 + D.6
- [ ] Emergent LLM key availability confirmed for AGENT-dependent
      COE γ tests in Phase B
- [ ] Monitoring dashboards + alerts staged (silent)
- [ ] On-call engineer + operator identified for the 24 h windows

Sign-off:

```
Approved by: ___________________________
Date:        ___________________________
Verdict:     [ ] ACTIVATION APPROVED   [ ] APPROVED-WITH-CONDITIONS   [ ] REJECT
Conditions:
______________________________________________________________
```

---

## 10. Production posture (until sign-off)

- All Stage 4 feature flags remain OFF
- No runtime behaviour changes
- No live connector wiring
- No governance cutover
- No production deployment

*Draft signed off:* main agent, 2026-07-20.
