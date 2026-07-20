# Backend Feature Freeze — v1.1.0-stage4

> **Status:** DRAFT — awaiting operator sign-off.
> Compiled: 2026-07-20.
> Backend commit: `3ed832a` (Stage 4 landing HEAD).
> Cumulative unit tests: **323 / 323 passing**.
> Production posture: **all Stage-4 flags OFF, zero behaviour change**.

This document declares the backend feature-complete. No new backend
features will be introduced after this freeze without explicit
operator approval. Activation, deployment, and validation work
proceeds against **this** state.

---

## 1. Feature inventory

### 1.1 Delivered subsystems

| # | Subsystem | Phase | Notes doc |
|---|---|---|---|
| 1 | Platform Foundation (auth, admin, health, dashboard) | Phase 1 | pre-existing |
| 2 | Platform Core (workload queue, orchestrator, budget tracker) | Phase 1 | pre-existing |
| 3 | CTS (Consolidated Trading Signal) | Phase 1 | pre-existing |
| 4 | Meta-Learning · MI · Execution · Portfolio · Factory-Eval | Phase 1 | pre-existing (retrofit health added in P4D.8) |
| 5 | BI5 ↔ BID shadow validation | Phase 2 Stage 2 | `BI5_BID_SHADOW_VALIDATION_REPORT.md` |
| 6 | UKIE Foundation (Domain Registry, Connector Protocol) | Phase 2 Stage 3.α | `PHASE_2_STAGE_3_ALPHA_NOTES.md` |
| 7 | UKIE Pipeline (routing · dedup · license · trust · repo cutover) | Phase 2 Stage 3.β | `PHASE_2_STAGE_3_BETA_NOTES.md` |
| 8 | Stage 3.γ — Promote Bridge + Retro-scoring | Phase 2 Stage 3.γ | `PHASE_2_STAGE_3_GAMMA_NOTES.md` |
| 9 | Connector Fleet (Arxiv · PDF · PropFirm · TradingView · InternalMongo) | Phase 4 P4A | `PHASE_4_P4A_CONNECTOR_FLEET_NOTES.md` |
| 10 | COE γ (retry · dead-letter · work recovery · admission · age boost · elastic · budget · operator ctl) | Phase 4 P4B | `PHASE_4_P4B_COE_GAMMA_NOTES.md` |
| 11 | UKIE γ (retrieval · ranking v2 · lifecycle · confidence · governance policy) | Phase 4 P4C | `PHASE_4_P4C_UKIE_GAMMA_NOTES.md` |
| 12 | Observability Finalisation | Phase 4 P4D | `PHASE_4_P4D_OBSERVABILITY_NOTES.md` |

Gate reports: `PHASE_2_VALIDATION_GATE_3_REPORT.md`,
`PHASE_2_VALIDATION_GATE_4_REPORT.md`,
`PHASE_4_VALIDATION_GATE_5_REPORT.md`.

### 1.2 Non-features (explicitly out of freeze scope)

- Frontend implementation
- Live network wiring for connectors (deferred to Coherent UKIE Activation)
- Aggregator wiring for retrofit health endpoints (activation step)
- OAuth token acquisition for prop-firm connectors (per-firm activation)
- Vector-search retrieval backend (Phase 5 candidate)
- Autonomous execution mode (post-72h validation)

---

## 2. API inventory

**Total `/api/*` routes: 71** across 18 groups.

| Group | Count | Highlights |
|---|---|---|
| `/api/knowledge/*` | 29 | UKIE (Stage 3 + Stage 4) — domains, connectors, pipeline, dry-run, promote (+ rollback), retro-score (+ rollback), query, lifecycle-sweep, endorsement, contradiction, governance, health, metrics, promote-events, retro-score-runs, connector-events, connector-health |
| `/api/coe/*` | 10 | COE metrics + state (pre-existing) + Stage-4 dead-letter (5) + circuit-breaker reset + queue pause/resume |
| `/api/auth/*` | 5 | Login / logout / refresh / me / register |
| `/api/health/*` | 5 | Global health surface (system + config + subsystem probes) |
| `/api/admin/*` | 4 | Admin console endpoints |
| `/api/data/*` | 3 | BI5 shadow diff (flag-gated) + market data |
| `/api/strategies/*` | 3 | Production strategy read/write (Stage 3.γ writer only via promote bridge) |
| `/api/research/*` | 2 | Research module endpoints |
| `/api/{execution, factory-eval, meta-learning, mi, portfolio}/health` | 5 | Stage-4 P4D.8 retrofits (all flag-gated) |
| Misc | 5 | dashboard, docs, readiness, version, openapi |

Every Stage-4 endpoint is flag-gated (returns HTTP 503 when off).
Pre-existing endpoints are untouched.

Full route list available via `GET /api/openapi.json`.

---

## 3. Database schema inventory

Two Mongo databases:

### 3.1 Main database (name from `DB_NAME`)

Pre-existing collections (representative — not exhaustive):
`users`, `strategies`, `ingested_strategies` (**READ-ONLY**),
`workload_events`, `research_notes`, `admin_events`,
`ai_workforce.circuit_breaker_state`, budget-tracker collections,
CTS collections, market data collections.

New in Stage 4 (lazy-created on first write; empty until activation):

| Collection | Owner | TTL (recommended, applied during activation) |
|---|---|---|
| `workload_dead_letter` | P4B.2 | 90d on `first_failed_at` |
| `coe_operator_events` | P4B.8 | 180d on `at` |

### 3.2 `strategy_knowledge_base` (UKIE-KB)

| Collection | Owner | Purpose | TTL |
|---|---|---|---|
| `strategies` / `research` / `market` / `execution` / `indicator` / `internal_history` | Stage 3.β repo | Per-domain KB rows (writes gated by `UKIE_GOVERNANCE_CUTOVER`) | per-domain policy (§5.3 of P4C notes) |
| `ingestion_runs` | Stage 3.α/β pipeline | Per-batch summary | 180d (recommended) |
| `promote_events` | Stage 3.γ Promote Bridge | Every promote / demote attempt | 180d |
| `retro_score_runs` | Stage 3.γ retro-scoring | Batch summaries + rollback events | 365d |
| `lifecycle_events` | P4C.3 sweeper | Per-(domain, run) audit | 180d |
| `knowledge_endorsement_events` | P4C.4 | One row per endorsement | 90d |
| `knowledge_contradiction_events` | P4C.4 | One row per contradiction pair | 365d |
| `promote_policies` | P4C.5 governance | Operator-authored policy documents | no TTL |
| `connector_events` | P4A/P4D.2 | Connector state transitions | 180d |

**Invariants:**
- `ingested_strategies` remains READ-ONLY. No Stage-4 code holds a
  write handle to it.
- Production `strategies` writes only via the Stage-3.γ promote
  bridge, with `learning_only=True, eligible_for_deploy=False`
  hard-stamped at the writer.
- Every UKIE-KB write carries the same hard rails.

---

## 4. Feature-flag inventory

**Total tracked flags: 40+.** All Stage-4 flags default OFF.
The list below is the operator's activation panel.

### 4.1 Stage 3 (UKIE foundation + pipeline + Stage 3.γ)

| Flag | Default | Purpose |
|---|---|---|
| `UKIE_DOMAIN_REGISTRY_ENABLED` | `false` | Master switch for `/api/knowledge/*` Stage-3.α foundation |
| `ENABLE_DOMAIN_ROUTING` | `false` | Stage-3.β pipeline stage |
| `ENABLE_DEDUP_CHECK` | `false` | Stage-3.β pipeline stage |
| `ENABLE_LICENSE_GATE` | `false` | Stage-3.β pipeline stage |
| `ENABLE_TRUST_SCORER` | `false` | Stage-3.β pipeline stage |
| `UKIE_GOVERNANCE_CUTOVER` | `false` | Governance cutover — gates Mongo writes to `strategy_knowledge_base` |
| `UKIE_PROMOTE_BRIDGE_ENABLED` | `false` | Stage-3.γ Promote Bridge master switch |
| `UKIE_PROMOTE_DRY_RUN` | `true` | Default dry-run when Promote Bridge is on |
| `UKIE_RETRO_SCORE_ENABLED` | `false` | Stage-3.γ retro-scoring master switch |

### 4.2 Stage 4 (Connector Fleet + COE γ + UKIE γ + Observability)

**P4A — Connector Fleet (6 flags)**
- `UKIE_CONNECTOR_FRAMEWORK_ENABLED` (master switch)
- `UKIE_CONNECTOR_ARXIV_ENABLED` · `_PDF_ENABLED` · `_PROPFIRM_ENABLED`
  · `_TRADINGVIEW_ENABLED` · `_INTERNAL_MONGO_ENABLED`

**P4B — COE γ (8 flags)**
- `COE_RETRY_ENABLED` · `COE_DEAD_LETTER_ENABLED`
- `COE_WORK_RECOVERY_ENABLED` · `COE_PROVIDER_AWARE_ADMISSION`
- `COE_AGE_BOOST_ENABLED` · `COE_ELASTIC_BAND_ENABLED`
- `COE_BUDGET_HARD_CAP_ENABLED` · `COE_OPERATOR_CONTROLS_ENABLED`

**P4C — UKIE γ (5 flags)**
- `UKIE_QUERY_API_ENABLED` · `UKIE_RANKING_V2_ENABLED`
- `UKIE_LIFECYCLE_SWEEP_ENABLED`
- `UKIE_CONFIDENCE_EVOLUTION_ENABLED` · `UKIE_GOVERNANCE_POLICY_ENABLED`

**P4D — Observability (15 flags)**
- `UKIE_HEALTH_PROVIDER_ENABLED` · `UKIE_METRICS_ENABLED`
- `UKIE_AUDIT_VISIBILITY_ENABLED` · `UKIE_CONNECTOR_EVENTS_PERSIST_ENABLED`
- `META_LEARNING_HEALTH_PROVIDER_ENABLED` · `MI_HEALTH_PROVIDER_ENABLED`
- `EXECUTION_HEALTH_PROVIDER_ENABLED` · `PORTFOLIO_HEALTH_PROVIDER_ENABLED`
- `FACTORY_EVAL_HEALTH_PROVIDER_ENABLED`
- 6 × `ALERT_*_ENABLED`

### 4.3 BI5 shadow
- `BI5_BID_DIFF_ENABLED` (default OFF)

### 4.4 Tunables (all optional, sensible defaults)
- `STALE_INFLIGHT_S`, `ORCH_AGE_BOOST_*`, `ELASTIC_HIGH_WATER`
- `ARXIV_API_KEY`, `INTERNAL_MONGO_BEARER_TOKEN`,
  `PROPFIRM_CLIENT_ID` / `PROPFIRM_CLIENT_SECRET` (all optional)

---

## 5. Operational runbooks (locations)

| Runbook | Location |
|---|---|
| Coherent UKIE Activation (phase A → E) | `PHASE_4_MASTER_PLAN.md §8.4` |
| BI5 shadow 24-hour observation | `BI5_BID_SHADOW_VALIDATION_REPORT.md §7` |
| Promote Bridge dry-run → commit | `PHASE_2_STAGE_3_GAMMA_NOTES.md §7` |
| Retro-scoring dry-run → commit | `PHASE_2_STAGE_3_GAMMA_NOTES.md §5` |
| Connector activation (per-connector) | `PHASE_4_P4A_CONNECTOR_FLEET_NOTES.md §7` |
| COE γ per-component activation | `PHASE_4_P4B_COE_GAMMA_NOTES.md §6` |
| UKIE γ retrieval + ranking activation | `PHASE_4_P4C_UKIE_GAMMA_NOTES.md §7` |
| Observability provisioning | `PHASE_4_P4D_OBSERVABILITY_NOTES.md §6` + `docs/observability/` |

Runbooks are documentation-first; concrete YAML/JSON configs ship
under `docs/observability/`.

---

## 6. Deployment checklist (VPS)

Pre-flight:
- [ ] `.env` populated from `.env.example` — every secret set;
      every Stage-4 flag left **OFF** at first boot
- [ ] MongoDB reachable at `MONGO_URL`, `DB_NAME` set
- [ ] Frontend build (deferred — not part of this freeze)
- [ ] Supervisor configs in `/etc/supervisor/conf.d/*`
- [ ] Nginx / kubernetes ingress: `/api/*` → backend, `/*` → frontend
- [ ] Emergent LLM key (if required at activation) — verified not
      needed at boot; only during activation

Boot verification:
- [ ] `curl $REACT_APP_BACKEND_URL/api/health` → 200
- [ ] `curl $REACT_APP_BACKEND_URL/api/version` matches
      `VERSION` file
- [ ] `/api/coe/state`, `/api/coe/metrics` return 200 (pre-existing)
- [ ] Every Stage-4 endpoint returns HTTP 503 (dormant state)

TTL indexes (apply once at first activation, not at freeze):
- [ ] `workload_dead_letter` — 90d on `first_failed_at`
- [ ] `lifecycle_events` — 180d on `at`
- [ ] `knowledge_endorsement_events` — 90d on `at`
- [ ] `knowledge_contradiction_events` — 365d on `at`
- [ ] `connector_events` — 180d on `at`

---

## 7. Rollback checklist

**Per-workstream (fast, ~30s each):**
- Promote Bridge: `UKIE_PROMOTE_BRIDGE_ENABLED=false` + restart
- Retro-scoring: `UKIE_RETRO_SCORE_ENABLED=false` + restart
- Connector Fleet: `UKIE_CONNECTOR_FRAMEWORK_ENABLED=false` (nuclear)
  or per-connector flag
- COE γ (any component): individual `COE_*_ENABLED=false` + restart
- UKIE γ (any component): individual `UKIE_*_ENABLED=false` + restart
- Observability (any): individual flag + restart

**Nuclear rollback (all Stage 3.γ + Stage 4 off):**
1. `sudo supervisorctl stop backend`
2. Set every flag from §4 to `false` in `.env`
3. `sudo supervisorctl start backend`
4. Verify `/api/health` returns 200 and every Stage-4 endpoint returns 503
5. Expected recovery: ≤ 60s

**Data rollback (per component):**
- Promote Bridge: `db.strategies.deleteMany({origin: "ukie_promote"})`
- Retro-score run: `db.strategy_knowledge_base.<coll>.deleteMany({retro_score_run_id: "<run_id>"})`
- Per-connector: `db.strategy_knowledge_base.<coll>.deleteMany({connector_name: "<name>"})`

---

## 8. Validation checklist (before enabling anything in production)

- [ ] All 34 Stage-4 flags verified OFF at boot
- [ ] `/api/health` returns 200
- [ ] `/api/knowledge/*` Stage-4 endpoints return 503
- [ ] `/api/coe/*` new endpoints return 503
- [ ] `/api/{meta-learning, mi, execution, portfolio, factory-eval}/health` return 503
- [ ] `/api/health/system` unchanged (no `ukie` block, no new subsystems)
- [ ] Production `strategies` collection unchanged (no ukie-origin rows)
- [ ] Legacy `ingested_strategies` unchanged (no writes)
- [ ] Unit test suite runnable against pod: `python -m pytest tests/` — 323/323

**Activation sequence** — follow `PHASE_4_MASTER_PLAN §8.4` phases A → E,
one flag at a time, 24h observation window between phases.

---

## 9. Known backlog (non-blocking for freeze)

Documented in prior notes; carried forward:
- Duplicate `operation_id` warning at `legacy/api/admin.py:list_users`
- Repo root accidental self-submodule pointer `strategy-factory-canonical`
- Optional nightly `mongodump` cron in `factory-mongo` compose
- Route-composition helper for cleaner sub-router mounting
  (P4A/P4C stack their sub-routers via `routes.append` /
  `routes.insert(0, ...)` — works but is order-sensitive)
- Vector-search retrieval backend (Phase 5, corpus-size gated)
- Frontend implementation (deferred — separate initiative)

None of the above blocks activation, VPS deployment, or validation.

---

## 10. Production readiness assessment

| Dimension | Status | Notes |
|---|---|---|
| Feature completeness (per master plan) | ✅ PASS | All Phase 1-2 + Phase 4 workstreams delivered |
| Test suite | ✅ PASS | 323/323 passing; 142 new tests for Stage 4 |
| Feature-flag dormancy | ✅ PASS | 34 Stage-4 flags verified OFF |
| Rollback SLA | ✅ PASS | ≤ 60s across every component |
| Backward compatibility | ✅ PASS | Zero shape change to Stage-1..3 surface |
| Stage 3.γ safety rails | ✅ PASS | Hard rails, promote discipline, legacy read-only, governance advisory-only — all intact |
| Documentation | ✅ PASS | Master plans + 5 workstream notes + 3 gate reports + observability configs + this freeze doc |
| Observability configs | ✅ SHIPPED | Grafana JSON + Alertmanager YAML (deployment during activation) |
| Deployment configs | ✅ SHIPPED | Supervisor + docker-compose files present |
| Secrets management | ⚠ MANUAL | `.env` populated per operator; no secrets committed |
| Live network paths | ⚠ DEFERRED | Wired during Coherent UKIE Activation (documented) |
| Aggregator wiring for retrofits | ⚠ DEFERRED | Single line in aggregator, applied during activation |
| Centralised TTL indexes | ⚠ DEFERRED | Applied during activation via `engines/db_indexes.py` |

**Verdict:** production-ready to deploy in a dormant state and enter
Coherent UKIE Activation via the sequenced phase A → E rollout.

---

## 11. Freeze declaration

**As of 2026-07-20, the backend is declared FEATURE-COMPLETE at
version `1.1.0-stage4` (commit `3ed832a`).**

No new backend features will be added without explicit operator
approval.

Post-freeze activities are:
1. **Coherent UKIE Activation** (staged phase A → E per Master Plan §8.4)
2. **VPS deployment**
3. **Paper broker validation**
4. **24-hour validation** (BI5 shadow + UKIE dormant baseline)
5. **72-hour validation**
6. **Recommendation Mode**
7. **Autonomous Mode**
8. **Frontend implementation**

Bug fixes and operational wiring (per the "deferred to activation"
items in §10) are permitted between the freeze and activation without
lifting the freeze.

Sign-off:

```
Approved by: ___________________________
Date:        ___________________________
Verdict:     [ ] FREEZE APPROVED   [ ] FREEZE APPROVED WITH CONDITIONS   [ ] REJECT
Conditions (if any):
______________________________________________________________
```

*Signed off (draft):* main agent, 2026-07-20.
