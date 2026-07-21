# Coherent UKIE Activation Plan (v2)

> **Status:** ✅ **PLAN APPROVED 2026-07-20** — activation execution remains operator-directed (staged Phase A → E per §5–§9). Ratification does not constitute a flag-flip.
> Compiled: 2026-07-20 · Revised: 2026-07-20 (v2 — post operator review).
> Backend: v1.1.0-stage4, feature-frozen (see `BACKEND_FEATURE_FREEZE.md` — approved 2026-07-20).
> Companion contract: Design Freeze v1.0 (`memory/DESIGN_FREEZE_v1.0.md`) governs the frontend independently. This activation plan may be executed in parallel with Sprint 1 frontend work; each has its own gating.
> Precondition: Backend Feature Freeze ✅ approved 2026-07-20.
>
> **v2 changes vs v1**: (1) preview-vs-production scope preamble; (2)
> Phase 0 baseline snapshot section; (3) Assumptions section; (4)
> Phase E rewritten around native Alertmanager silences (freeze-clean —
> no delivery-layer proxy); (5) retro-scoring wording clarified; (6)
> Stage-4 test subset naming corrected; (7) total activation timeline
> visibility; (8) risk register added; (9) sequencing rationale line;
> (10) sampling cadences per phase. See
> `COHERENT_UKIE_ACTIVATION_PLAN_REVIEW.md` for the underlying review.
>
> This plan sequences the activation of every Phase 2 Stage 3 + Phase 4
> feature that currently sits dormant. Nothing is enabled at
> ratification; flags flip only during the phases below, one at a time,
> with 24-hour observation windows between phases (adjustable per
> operator judgement).

---

## 0. Target environment & scope

**This plan targets the VPS production pod.**

If a phase is executed against the preview pod for rehearsal, the
following steps become **no-ops** (skip and document the skip):
- A.10 Grafana dashboard provisioning
- Every step in Phase E (Alertmanager silences)
- Any TTL retention assertion that depends on a long-lived DB

Rehearsal execution is encouraged and does not consume activation
budget. Only production execution counts for gate advancement.

---

## 1. Guiding principles

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
   remain locked until the full validation stack (paper broker + 24 h
   + 72 h) has passed.

---

## 2. Total activation timeline

| Phase | Steps | Wall-clock (24 h/step baseline) |
|---|---|---|
| A — Observability | 10 | ~7 days (some steps batched safely inside one 24 h window) |
| B — COE γ resilience | 8 | ~8 days |
| C — UKIE γ retrieval | 6 | ~6 days |
| D — Connector fleet + cutover | 18 | ~15 days (heaviest phase) |
| E — Alertmanager silences | 6 | ~4 days |
| **Total** | **48** | **~40 days** at the conservative cadence |

Operator may compress by extending single 24 h windows to cover
multiple in-phase steps of the same component class (e.g., A.1–A.8
inside one window). Reversing a phase resets its window.

---

## 3. Preconditions (before Phase A)

- [ ] Backend v1.1.0-stage4 deployed and healthy on the target pod
- [ ] `.env` populated; every Stage-3/Stage-4 flag confirmed OFF at boot
- [ ] `COE_HEALTH_CONTRACT_ENABLED=true` on the target pod (existing
      Phase 2 Stage 1 dependency — verify at Phase 0)
- [ ] Stage-4 targeted test subset passing (`pytest tests/test_ukie_gamma.py
      tests/test_coe_gamma.py tests/test_promote_bridge.py
      tests/test_retro_score.py tests/test_health_contract.py
      tests/test_observability_p4d.py` and adjacent). The historical
      "323/323 passing" figure refers to this subset — **not** the full
      `tests/` directory, which contains pre-existing HTTP-integration
      suites that require a live external URL to run.
- [ ] Mongo reachable; `strategy_knowledge_base` DB accessible
- [ ] Grafana + Alertmanager deployed on target pod (skeleton configs
      applied, alerts silent) — production only
- [ ] Emergent LLM key available and non-expired **only if** Phase B.4
      breaker probing is planned in this activation window (other
      Phase B steps do not exercise LLM traffic)
- [ ] Operator + on-call engineer identified for each 24 h window;
      escalation ladder documented

---

## 4. Phase 0 — baseline snapshot (mandatory)

Before flipping any flag, capture a baseline. This is what "no
regression" (§5.3, §6.3, etc.) is measured against.

Run against the target pod:

```
BASE=$REACT_APP_BACKEND_URL

# 1. Health baseline
curl -s "$BASE/api/health"                        > /tmp/p0_health.json
curl -s "$BASE/api/health/system"                 > /tmp/p0_health_system.json
curl -s "$BASE/api/health/subsystems"             > /tmp/p0_subsystems.json

# 2. COE baseline
curl -s "$BASE/api/coe/state"                     > /tmp/p0_coe_state.json
curl -s "$BASE/api/coe/metrics"                   > /tmp/p0_coe_metrics.json

# 3. Version
curl -s "$BASE/api/version"                       > /tmp/p0_version.json

# 4. Confirm every Stage-4 endpoint is dormant (503)
for ep in knowledge/health knowledge/query knowledge/metrics \
          knowledge/promote-events knowledge/retro-score-runs \
          knowledge/connector-events \
          meta-learning/health mi/health execution/health \
          portfolio/health factory-eval/health \
          coe/dead-letter; do
    printf "%s: " "$ep"; curl -so /dev/null -w "%{http_code}\n" "$BASE/api/$ep"
done
```

Record:
- `platform_health_score` in `p0_health_system.json` (baseline).
- Mongo document counts for legacy `ingested_strategies` and
  production `strategies` collections (invariant-check baselines).
- Every Stage-4 endpoint above returning `503` (dormant).

---

## 5. Phase A — Observability first (read-only, safe)

**Goal:** enable every dormant read-only surface to establish
baselines BEFORE flipping any writer.

**Rationale for A first**: read paths cannot violate invariants;
starting here lets the operator populate dashboards with real data
so subsequent phases have a "before" to diff against.

### 5.1 Activation sequence

| Step | Flag / Action | Verify |
|---|---|---|
| A.1 | `UKIE_HEALTH_PROVIDER_ENABLED=true` | `GET /api/knowledge/ukie/health` → 200 with `status:"dormant"` (Stage-4 endpoint intentionally mounted at `/ukie/health` to avoid collision with the pre-existing Phase-1 KB probe at `/api/knowledge/health` — see Phase 0 finding P0-F1) |
| A.2 | `META_LEARNING_HEALTH_PROVIDER_ENABLED=true` | `GET /api/meta-learning/health` → 200 |
| A.3 | `MI_HEALTH_PROVIDER_ENABLED=true` | `GET /api/mi/health` → 200 |
| A.4 | `EXECUTION_HEALTH_PROVIDER_ENABLED=true` | `GET /api/execution/health` → 200 |
| A.5 | `PORTFOLIO_HEALTH_PROVIDER_ENABLED=true` | `GET /api/portfolio/health` → 200 |
| A.6 | `FACTORY_EVAL_HEALTH_PROVIDER_ENABLED=true` | `GET /api/factory-eval/health` → 200 |
| A.7 | `UKIE_METRICS_ENABLED=true` | `GET /api/knowledge/metrics` → 200 with zero counts |
| A.8 | `UKIE_AUDIT_VISIBILITY_ENABLED=true` | `GET /api/knowledge/promote-events`, `/retro-score-runs`, `/connector-events` all → 200 with `count: 0` |
| A.9 | *(no flag — verify aggregator wiring lands automatically)* | `GET /api/health/system` returns the 5 retrofit `subsystems[]` entries after A.2–A.6 are on; returns top-level `ukie` block after A.1 is on. Aggregator composition was landed as freeze-permitted W2 wiring — no additional deploy step needed. |
| A.10 | Provision `docs/observability/grafana_p4d_dashboard.json` (production only; no-op in preview) | Dashboards render all panels within 5 s |

### 5.2 Monitoring checkpoints (during 24 h window)

Sampling cadence: `platform_health_score` every 5 min; endpoint
liveness probes every 30 s; log-scan every 15 min.

- `/api/health/system` continues returning 200
- `platform_health_score` remains ≥ (baseline − 5 points)
- No new error rows in `/var/log/supervisor/backend.*.log`
- Every subsystem health endpoint returns `flag_enabled: true`
- Dashboards populate; alerts remain silent

### 5.3 Success criteria
- All 10 endpoints return 200
- `/api/health/system` shape includes 5 retrofit entries + a
  top-level `ukie` block
- `platform_health_score` measured at 24 h mark is within 5 points of
  the Phase-0 baseline (p95 over the whole window)
- Dashboards render all panels within 5 s

### 5.4 Abort criteria
- Any endpoint returns 5xx
- `platform_health_score` drops > 5 points sustained 5 min
- Backend restarts unexpectedly

### 5.5 Rollback
1. Flip Phase-A flags to `false` in `.env`
2. `sudo supervisorctl restart backend`
3. Verify Phase-A endpoints return 503
4. Recovery SLA: ≤ 60 s

---

## 6. Phase B — COE γ resilience

**Goal:** enable the eight COE γ components in dependency order so
retry / dead-letter / recovery / admission are all in place before
UKIE γ starts producing operator-visible surfaces.

**Rationale for B before C**: COE γ resilience is exercised against
existing pre-Stage-4 workload traffic (already flowing today).
Enabling C first would produce empty-KB retrieval traffic (safer in
isolation) but would delay real-world stress-testing of the
resilience layer that C ultimately depends on. Reverse the order
only if activation-window traffic to the COE is unusually low.

### 6.1 Activation sequence (one flag per 24 h)

| Step | Flag | Wire-up |
|---|---|---|
| B.1 | `COE_RETRY_ENABLED=true` | RetryExecutor composed into WorkloadQueue submit path |
| B.2 | `COE_DEAD_LETTER_ENABLED=true` | TTL index on `workload_dead_letter.first_failed_at_dt` (90 d) auto-applied at boot via `engines/db_indexes.py` (freeze-permitted W1 wiring). Writers currently emit ISO strings — TTL becomes active once writers populate the `*_dt` companion; safe no-op until then. |
| B.3 | `COE_WORK_RECOVERY_ENABLED=true` | Requeue + dead-letter hooks wired at boot |
| B.4 | `COE_PROVIDER_AWARE_ADMISSION=true` | `breaker_state_lookup` wired to `engines.ai_workforce.circuit_breaker`. **Only** this component requires the Emergent LLM key path be healthy for verification. |
| B.5 | `COE_AGE_BOOST_ENABLED=true` | `+ compute_age_boost().delta` added to orchestrator's `_score_task` |
| B.6 | `COE_ELASTIC_BAND_ENABLED=true` | Redistributor's plan applied on scoring pass |
| B.7 | `COE_BUDGET_HARD_CAP_ENABLED=true` | BudgetHardCap composed with existing soft-cap warning |
| B.8 | `COE_OPERATOR_CONTROLS_ENABLED=true` | Audit sink wired to `coe_operator_events` |

### 6.2 Monitoring checkpoints

Sampling cadence: metrics every 1 min; dead-letter depth every 5
min; admission latency percentile every 5 min.

- `/api/coe/metrics` shows retry rate ≥ 0, no anomalies
- `/api/coe/dead-letter/depth` remains at 0 in normal operation
- Admission p95 latency stays < 200 ms
- Budget headroom trends match pre-activation baseline
- Circuit breaker states visible on dashboard

### 6.3 Success criteria (per component)
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

### 6.4 Abort criteria (any component)
- Retry storm: `retry_rate_per_class` > 10× baseline sustained 5 min
- Dead-letter depth > 100
- Admission p95 latency > 500 ms sustained 5 min
- Any provider circuit stuck OPEN > 30 min without operator action
- `platform_health_score` < 80

### 6.5 Rollback
Per component: flip the component's `COE_*_ENABLED=false` + restart.
Nuclear: all 8 flags off + restart. SLA ≤ 60 s.
Data preserved: `workload_dead_letter` + `coe_operator_events` rows
remain for audit.

---

## 7. Phase C — UKIE γ retrieval

**Goal:** enable retrieval + ranking + lifecycle + confidence +
governance policy. Every capability is read-only OR advisory. No
UKIE-KB writes yet — `UKIE_GOVERNANCE_CUTOVER` still OFF.

### 7.1 Activation sequence

| Step | Flag / Action | Verify |
|---|---|---|
| C.1 | `UKIE_QUERY_API_ENABLED=true` | `POST /api/knowledge/query` → 200 with `matches: []` (KB empty) |
| C.2 | *(no flag — TTL indexes land automatically)* | TTL indexes on `lifecycle_events.at_dt`, `knowledge_endorsement_events.at_dt`, `knowledge_contradiction_events.at_dt`, `connector_events.at_dt` auto-applied via `engines/db_indexes.py` KB_TTL_SPECS. Same *_dt discipline as B.2 — safe no-op until writers populate. Verify via `db.<coll>.getIndexes()`. |
| C.3 | `UKIE_LIFECYCLE_SWEEP_ENABLED=true` | `POST /api/knowledge/lifecycle-sweep {"dry_run":true}` → 200 with zero-count summary |
| C.4 | `UKIE_RANKING_V2_ENABLED=true` | Query same as C.1; ranking breakdown appears; `final_score == 0` (empty KB) |
| C.5 | `UKIE_CONFIDENCE_EVOLUTION_ENABLED=true` | Endorsement + contradiction endpoints return 200 |
| C.6 | `UKIE_GOVERNANCE_POLICY_ENABLED=true` | Seed a policy in `promote_policies` (canonical example in Appendix A); evaluate endpoint returns advisory tags |

### 7.2 Monitoring checkpoints

Sampling cadence: query latency every 5 min; audit-collection
counts every 15 min.

- `/api/knowledge/query` p95 latency < 100 ms (empty KB baseline)
- Ranking breakdown includes v2 multipliers when v2 flag on
- Lifecycle sweep dry-run reports per-domain counts without touching Mongo
- Governance advisory tags NEVER call the promote bridge (verify via
  `/api/knowledge/promote-events` — count stays at 0)

### 7.3 Success criteria
- `POST /api/knowledge/query` returns ordered results respecting
  ai_context_policy (no `content_bytes` in response for any domain)
- Ranking-v2 breakdown reasons visible
- Lifecycle sweep audit rows land in `lifecycle_events` on non-dry-run
- Endorsement + contradiction event stores accept rows
- Governance verdict stamps `advisory_tags` WITHOUT touching
  trust_tier / license / hard rails

### 7.4 Abort criteria
- Any writer touches production `strategies` (should NEVER happen);
  **immediate escalation** — halt activation, page operator, do NOT
  continue to next phase, root-cause investigation required
- Governance produces an auto-promote call (should NEVER happen —
  advisory-only invariant); **immediate escalation**
- Query p95 > 500 ms sustained 5 min
- Any KB row observed with `learning_only=false` OR
  `eligible_for_deploy=true`; **immediate escalation**

### 7.5 Rollback
Per component: flip the flag off + restart. All Stage-4 collections
preserved (audit history intact).

---

## 8. Phase D — Connector fleet + governance cutover

**Goal:** enable the Stage-3 pipeline + Stage-4 connectors + the
governance cutover. **This is the first phase that writes to the
UKIE-KB.**

**PRECONDITION:** Phases A–C stable for at least 24 h each. No open
abort conditions.

### 8.1 Activation sequence — Stage 3 first

| Step | Flag | Verify |
|---|---|---|
| D.1 | `UKIE_DOMAIN_REGISTRY_ENABLED=true` | `GET /api/knowledge/domains` → 200 with 6 domains |
| D.2 | `ENABLE_DOMAIN_ROUTING=true` | Pipeline routing stage active in dry-run |
| D.3 | `ENABLE_LICENSE_GATE=true` | License-gate stage active |
| D.4 | `ENABLE_TRUST_SCORER=true` | Trust scorer stage active |
| D.5 | `ENABLE_DEDUP_CHECK=true` | Dedup stage active |
| D.6 | `POST /api/knowledge/dry-run` | Preview pipeline output on synthetic fixture. Confirm legacy `ingested_strategies` is untouched (read-only invariant). |

### 8.2 The critical cutover

| Step | Flag | Verify |
|---|---|---|
| D.7 | `UKIE_GOVERNANCE_CUTOVER=true` | **The cutover flag itself does not produce writes.** It unblocks the code path that lets connectors persist rows into `strategy_knowledge_base`. With connectors STILL disabled, expect zero writes over 24 h — because nothing is producing items yet. Any observed KB row growth during this window is an anomaly requiring immediate investigation. |

### 8.3 Connector fleet activation

| Step | Flag | Wire-up |
|---|---|---|
| D.8 | `UKIE_CONNECTOR_FRAMEWORK_ENABLED=true` | Verify Stage-4 connectors visible in `list_connectors()` |
| D.9 | `UKIE_CONNECTOR_INTERNAL_MONGO_ENABLED=true` | Read-only source. Wire `db_getter` to `<source_db>.<source_collection>` (concrete DB/collection to be confirmed by operator before Phase D begins — this is the last "deferred to activation" wiring item from Freeze doc §10). Observe `/api/knowledge/ukie/health.kb_row_count` growth. |
| D.10 | `UKIE_CONNECTOR_ARXIV_ENABLED=true` | Wire live `aiohttp.ClientSession` (or curated seed list) + `ARXIV_API_KEY`. Observe RESEARCH domain row growth. |
| D.11 | `UKIE_CONNECTOR_PDF_ENABLED=true` | Wire live client + curated seed URLs. |
| D.12 | `UKIE_CONNECTOR_PROPFIRM_ENABLED=true` | Wire per-firm allow-list + optional OAuth (`PROPFIRM_CLIENT_ID` / `PROPFIRM_CLIENT_SECRET`). |
| D.13 | `UKIE_CONNECTOR_TRADINGVIEW_ENABLED=true` | Wire curated seed of Pine scripts. |
| D.14 | `UKIE_CONNECTOR_EVENTS_PERSIST_ENABLED=true` | Wire observer callback → `connector_events` writes |

### 8.4 Promote Bridge activation (per-item, dry-run first)

| Step | Flag | Verify |
|---|---|---|
| D.15 | `UKIE_PROMOTE_BRIDGE_ENABLED=true` (with `UKIE_PROMOTE_DRY_RUN=true`) | `POST /api/knowledge/promote/{kb_id}` in dry-run — no writes to production `strategies` |
| D.16 | After N successful dry-runs, individual commit | `POST /api/knowledge/promote/{kb_id}?dry_run=0` — one item at a time |

### 8.5 Retro-scoring (optional, one-shot)

Retro-scoring **reads** legacy `ingested_strategies` and **writes**
per-domain KB rows into `strategy_knowledge_base.*`. It does **NOT**
mutate the legacy collection — the "read-only" invariant on
`ingested_strategies` is preserved end to end.

| Step | Flag | Verify |
|---|---|---|
| D.17 | `UKIE_RETRO_SCORE_ENABLED=true` | `POST /api/knowledge/retro-score {"dry_run":true}` — preview output (no writes anywhere) |
| D.18 | Real run | `POST /api/knowledge/retro-score {"dry_run":false, "confirm_write":"yes_write_the_kb"}` — one-time backfill. The `confirm_write` token must be **exactly** `"yes_write_the_kb"` (verbatim string discriminator in `retro_score_router.py`). |

### 8.6 Monitoring checkpoints

Sampling cadence: connector health every 5 min; KB row count every
15 min; legacy invariant every 30 min.

- `/api/knowledge/ukie/health.kb_row_count` grows predictably per connector
- `/api/knowledge/connectors/{name}/health.state = "healthy"` for
  every enabled connector
- **Legacy `ingested_strategies` remains READ-ONLY** — zero writes;
  verify via Mongo `db.currentOp()` scan for update/insert against
  that collection
- Every KB row carries `learning_only=true, eligible_for_deploy=false`
  (spot-check via `/api/knowledge/query`)
- `/api/knowledge/promote-events` grows only for explicit operator
  promote calls

### 8.7 Success criteria
- Each connector's `health.state` transitions to `healthy`
- KB row growth matches connector output (per-connector counts audited).
  Per-connector minimum throughput is not gated — a connector
  producing 1 row in 24 h is acceptable **if** its `health.state ==
  "healthy"` and error count is zero. Zero-throughput + healthy is a
  legitimate "quiet source" state.
- Zero rows with `learning_only=false` observed
- Promote-events audit trail complete
- Legacy `ingested_strategies` write count = 0 (measured over the
  whole phase, not just checkpoints)

### 8.8 Abort criteria
- **Any write to legacy `ingested_strategies` observed** →
  immediate escalation: halt activation, page operator, do NOT
  proceed. Root-cause required.
- **Any production `strategies` row without `origin="ukie_promote"`
  or with `eligible_for_deploy=true`** → immediate escalation.
- Connector failure rate > 50 % sustained 30 min
- KB write errors > 5 % sustained 15 min

### 8.9 Rollback (per phase D step)
- Per-connector: `UKIE_CONNECTOR_<NAME>_ENABLED=false` + restart
- Framework: `UKIE_CONNECTOR_FRAMEWORK_ENABLED=false`
- Cutover rollback: `UKIE_GOVERNANCE_CUTOVER=false` — KB writes stop;
  KB rows preserved for audit
- Data rollback (per connector): `db.strategy_knowledge_base.<coll>.deleteMany({connector_name:"<name>"})`
- Data rollback (retro-score): `POST /api/knowledge/retro-score/rollback/{run_id}`
- Data rollback (promote-bridge): per-item `POST /api/knowledge/promote/{kb_id}/rollback`
- Nuclear: flip all D-phase flags off + `deleteMany({origin:"ukie_promote"})` on prod strategies
- Cross-reference: nuclear-rollback checklist lives in
  `BACKEND_FEATURE_FREEZE.md §7`.

---

## 9. Phase E — Alerting (native Alertmanager silences)

**Goal:** activate the six alert rules once 24 h of live baselines
have been observed under Phase D.

**Mechanism (operator review v2 decision — Batch 3 Option a):**

The Alertmanager rules in `docs/observability/alertmanager_p4d_rules.yaml`
carry `flag: ALERT_<NAME>_ENABLED` labels. These labels **do not gate
rule firing** — they are decorative labels used for filtering,
silencing, and routing inside Alertmanager. No Python backend code
consumes them. Consequently, "enabling" an alert in this plan means
**removing (or narrowing) the Alertmanager silence** that keeps the
rule quiet, not flipping an env flag.

No new backend delivery layer is being added (that would break the
freeze). Operator uses Alertmanager's native silence mechanism
throughout.

### 9.1 Prerequisite (once, on production)

Deploy the rule bundle:
```
# Apply the rules
kubectl -n monitoring apply -f docs/observability/alertmanager_p4d_rules.yaml
# Or: `cp docs/observability/alertmanager_p4d_rules.yaml \
#        /etc/alertmanager/rules/factory-stage-4-p4d.yaml \
#      && systemctl reload alertmanager`
```

Immediately create a broad silence covering all six rules — so no
alert fires during the 24 h baseline observation:
```
amtool silence add matchers='source="p4d"' \
  --duration=48h \
  --comment="Baseline observation window before Phase E arm"
```

### 9.2 Activation sequence (arm rules by REMOVING the silence, one at a time)

Each step is executed by narrowing / expiring the Phase-E-wide
silence and (optionally) creating a rule-specific silence to allow
one rule to fire while others remain muted.

| Step | Rule label | Action |
|---|---|---|
| E.1 | `FactoryPlatformHealthDegraded` (severity: high) | `amtool silence expire <id>` for this rule; verify threshold `factory_platform_health_score < 60` triggers a synthetic test alert |
| E.2 | `FactoryBudgetHeadroomLow` (severity: high) | Expire silence; verify `< 10 %` of hard cap threshold |
| E.3 | `FactoryDeadLetterDepthHigh` (severity: medium) | Expire silence; verify `> 100` depth threshold |
| E.4 | `FactoryConnectorFailing` (severity: medium) | Expire silence |
| E.5 | `FactoryPromoteRefusalRateHigh` (severity: low) | Expire silence; verify `> 50 %` sustained 30 min threshold |
| E.6 | `FactoryAdmissionLatencyHigh` (severity: medium) | Expire silence; verify `p95 > 200 ms` threshold |

### 9.3 Monitoring cadence
Alerts are silent by design during Phases A–D. During Phase E each
rule is armed one at a time; a synthetic breach is injected in
preview and verified to fire; the same rule is then armed in
production. Sampling cadence is Alertmanager's own (interval: 30 s
per the YAML).

### 9.4 Success criteria
- Each rule fires correctly against a synthetic breach in preview
- No false-positive alerts fire in the first 24 h of production arming
- On-call receives paging as configured (verify via test route)

### 9.5 Rollback
Re-silence the rule with `amtool silence add matchers='alertname="<X>"'`
(effectively an unarm). Silences apply within seconds. No backend
restart required.

### 9.6 What is NOT changing (freeze-compliance note)

- No `ALERT_*_ENABLED` env variable will be added to `.env`.
- No Python delivery-layer proxy will be authored.
- No new backend code will be introduced.
- The YAML file's `flag:` labels remain as informational tags only.

The activation mechanism for Phase E is entirely Alertmanager-native.

---

## 10. Assumptions (made explicit before activation)

These assumptions are baked into the plan; if any is invalidated
before Phase A begins, the plan must be revised.

1. **`COE_HEALTH_CONTRACT_ENABLED=true`** in the target environment
   (existing Phase 2 Stage 1 dependency, verified at Phase 0).
2. **Grafana + Alertmanager** are already deployed on the target pod
   (production only; preview skips).
3. **`engines/db_indexes.py` W1 additions have been merged** (freeze-
   permitted operational wiring; verified in test suite).
4. **`engines/subsystem_health_router.py` W2 additions have been
   merged** — retrofit providers auto-register at import; UKIE
   provider composed inside `/api/health/system` when its flag is on
   (freeze-permitted operational wiring; verified in test suite).
5. **Per-connector secrets/wire-ups** are landed BEFORE the
   corresponding D.9–D.13 flag flip.
6. **Retro-score's `confirm_write` token is exactly
   `"yes_write_the_kb"`** — verbatim.
7. **`.env` is the authoritative flag surface.** No process-manager
   overrides, no k8s ConfigMap override, no `os.environ` mutations
   at runtime.
8. **The target environment has one backend replica.** Multi-replica
   activation requires all replicas to see the same `.env` at the
   same time; the plan implicitly assumes single-node.
9. **Emergent LLM key** is optional at boot (per Freeze doc §6) but
   required for Phase B.4 breaker-probe verification. Confirm live
   in Phase 0 baseline if B.4 is planned in the activation window.
10. **The Freeze remains in effect** during the entire 40-day
    activation. Bug fixes and operational wiring are permitted; new
    endpoints or new flags are NOT.

---

## 11. Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Mongo hot-path index build blocks writes | LOW (background=True) | MEDIUM | Apply TTL indexes BEFORE first writes to a collection (Phase B.2, C.2 both precede their first-write phase). |
| R2 | `COE_HEALTH_CONTRACT_ENABLED` unexpectedly off in production | LOW | HIGH | Confirm at Phase 0 baseline; if off, halt activation until enabled. |
| R3 | `.env` drift across a 40-day activation | MEDIUM | MEDIUM | Snapshot `.env` after each phase completion; diff at abort. |
| R4 | Emergent LLM key expiry during activation | LOW | LOW-MED | Verify key TTL at Phase 0; re-issue if activation window > key lifetime. |
| R5 | Preview pod database is transient | HIGH (in preview) | LOW | Preview execution treated as rehearsal only; production is the source of truth for gate advancement. |
| R6 | TTL index no-op due to ISO-string field type | HIGH (today) | LOW | TTL indexes are declared against `*_dt` companion fields (audit_log pattern). Silent no-op until writers populate. Adding writer discipline is a post-activation follow-up if retention starts to matter. |

---

## 12. Overall success — activation complete

Coherent UKIE Activation is complete when:

- All Phase A–E steps landed successfully
- 24 h continuous observation window at end of Phase E shows
  `platform_health_score` within 5 points of Phase-0 baseline
- No abort conditions triggered in any phase
- KB row count growth stable (± 20 % over 24 h)
- Every audit collection has TTL indexes applied (verified in
  `db.<coll>.getIndexes()` output)
- Grafana dashboards populated; alerts armed in production
- Legacy `ingested_strategies` invariant preserved (write count = 0)
- Production `strategies` invariant preserved (every ukie-origin row
  carries `learning_only=true, eligible_for_deploy=false`)

**Post-activation roadmap:**
1. VPS deployment (if activation was in preview)
2. Paper broker validation
3. 24-hour validation
4. 72-hour validation
5. Recommendation Mode
6. Autonomous Mode
7. Frontend implementation

---

## 13. Overall abort

If **any** phase abort criterion fires:

1. Execute that phase's rollback (≤ 60 s target)
2. Investigate; document root cause in a follow-up doc under
   `/app/memory/`
3. Do NOT proceed to the next phase until the root cause is
   understood and remediated
4. If two consecutive phases abort, halt activation entirely; call
   an operator review before any re-attempt

Immediate-escalation invariant breaches (any of the below) → halt,
page, root-cause; do not continue even if rollback appears clean:
- Write observed to legacy `ingested_strategies`
- Production `strategies` row without `origin="ukie_promote"`
- Governance produces an auto-promote call

---

## 14. Operator sign-off checklist

- [ ] Preview-vs-production scope confirmed (§0)
- [ ] Total activation duration acknowledged (~40 days at conservative
      cadence — §2)
- [ ] Phase 0 baseline captured (§4)
- [ ] Phase A–E sequences reviewed and accepted
- [ ] Success criteria numeric where possible
- [ ] Abort criteria numeric where possible
- [ ] Rollback procedure documented for each phase
- [ ] TTL indexes verified auto-applied via `db_indexes.py` (§B.2, C.2)
- [ ] Aggregator wiring verified live (`/api/health/system` includes
      retrofits + `ukie` block when flags on)
- [ ] Phase E mechanism understood (native Alertmanager silences,
      no delivery-layer proxy — §9)
- [ ] Emergent LLM key availability confirmed for B.4 (if in scope)
- [ ] Monitoring dashboards + alerts staged (silent)
- [ ] On-call engineer + operator identified for each 24 h window
- [ ] Escalation ladder documented

Sign-off:

```
Approved by: ___________________________
Date:        ___________________________
Verdict:     [ ] ACTIVATION APPROVED   [ ] APPROVED-WITH-CONDITIONS   [ ] REJECT
Conditions:
______________________________________________________________
```

---

## 15. Production posture (until sign-off)

- All Stage 4 feature flags remain OFF
- No runtime behaviour changes
- No live connector wiring
- No governance cutover
- No production deployment

---

## Appendix A — canonical `promote_policies` seed

Reference document for Phase C.6. Insert into
`strategy_knowledge_base.promote_policies` as a starting policy the
operator can iterate on. Advisory-only — never bypasses hard rails.

```json
{
  "policy_id": "policy_default_v1",
  "name": "Default advisory promote policy",
  "description": "Advisory tags applied to promote candidates. Never bypasses trust_tier, license, or hard rails.",
  "created_at": "<iso-utc>",
  "created_by": "operator",
  "rules": [
    {
      "when": {"domain": "strategies", "trust_tier_min": "verified"},
      "advisory_tag": "eligible_for_shadow_promote"
    },
    {
      "when": {"domain": "strategies", "trust_tier": "unverified"},
      "advisory_tag": "requires_manual_review"
    },
    {
      "when": {"license_class": "restricted"},
      "advisory_tag": "license_flag_review_required"
    }
  ],
  "hard_rails": {
    "learning_only_always_true": true,
    "eligible_for_deploy_always_false": true
  }
}
```

---

*Draft signed off:* main agent, 2026-07-20 (v2 revised).
