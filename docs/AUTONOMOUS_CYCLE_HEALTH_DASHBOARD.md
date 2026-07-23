# Autonomous Cycle Health Dashboard

**Purpose:** a single reference that maps every stage of the
Autonomous Research Factory cycle to the concrete observability
signals — HTTP endpoint, ledger collection, log grep, and dashboard
metric — the operator can use to verify that the stage is running
continuously and correctly.

**Constraint:** every signal below is served by an endpoint or
collection that **already exists** in the canonical repo. Nothing in
this document requires a new engine.

**Companion to:** `docs/PHASE_1_ACTIVATION_PLAN.md`,
`docs/CAPABILITY_INVENTORY.md`,
`docs/AUTONOMOUS_FACTORY_READINESS.md`.

---

## 0 · Top-of-page verdict (30-second check)

```bash
API_URL="https://$FACTORY_DOMAIN"
TOKEN=$(curl -s -X POST "$API_URL/api/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('access_token') or d.get('token'))")

# One-shot: readiness + orchestrator + last tick
curl -fsS -H "Authorization: Bearer $TOKEN" "$API_URL/api/readiness" \
  | jq '{mongo: .checks.mongo.status, vie: .checks.vie.status}'

curl -fsS -H "Authorization: Bearer $TOKEN" "$API_URL/api/orchestrator/status" \
  | jq '{running, enabled_by_env, tick_count: .meta.tick_count, dispatched_total: .meta.dispatched_total, band: .meta.last_tick.band, in_flight: (.in_flight|length), last_error: .meta.last_error}'
```

**Green:** `mongo=green`, `vie=green`, `running=true`,
`tick_count` monotonically increasing, `last_error=null`, at least
one entry in `dispatched_total`, `band` ∈ (`normal`, `warn`).

**Red:** anything else → jump to the relevant section below.

---

## 1 · Container-level health

| Container | Health probe | Endpoint / file | Expected |
|-----------|--------------|-----------------|----------|
| factory-backend | Docker healthcheck | `curl -f http://127.0.0.1:8001/api/health` | HTTP 200 |
| factory-vie     | Docker healthcheck | `curl -f http://127.0.0.1:8100/health`     | HTTP 200 |
| factory-frontend | Docker healthcheck | `wget -qO- http://127.0.0.1/healthz`       | HTTP 200 |
| factory-runner  | Docker healthcheck | `test -f /tmp/factory_runner.hb`           | file present, refreshed every 30 s (dispatcher) / 300 s (sibling audit) |
| factory-mongo   | Docker healthcheck | `mongosh --eval "db.runCommand('ping').ok"` | `1` |
| caddy           | manual              | `docker logs caddy \| grep obtained`       | recent cert renewal, no errors |

```bash
for c in factory-backend factory-vie factory-frontend factory-runner factory-mongo caddy; do
  printf '%-20s %s\n' "$c" "$(docker inspect $c --format '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}n/a{{end}}')"
done
```

---

## 2 · Autonomous cycle stages — full observability matrix

For every stage: **task name** (orchestrator registry) · **endpoint(s)** ·
**ledger collection(s)** · **log grep** · **stage indicator that says
"the stage completed at least once"**.

### 2.1 · Stage: Market data refresh

- **Task:** `market_data_topup`
- **Endpoints:**
  - `GET /api/data/coverage` — per-symbol coverage %, BI5 last cert date.
  - `GET /api/data-maintenance/status` — auto-maintenance scheduler state.
  - `GET /api/data/bi5-bid-diff` — BI5 ↔ BID shadow-diff (flag-gated).
- **Collections:** `market_data`, `bi5_certification`, `auto_maintenance_status`.
- **Log grep:** `docker logs factory-backend | grep -E 'auto-maintenance|bi5_ingest|market_data_topup'`
- **Stage complete indicator:** `data-maintenance/status.last_run_at` moves forward on each cycle; coverage % monotonic non-decreasing.

### 2.2 · Stage: Knowledge index refresh

- **Task:** `knowledge_index_refresh`
- **Endpoints:**
  - `GET /api/knowledge/statistics` — total corpus, families, positive-return count.
  - `GET /api/knowledge/health` — corpus-size + backend.
  - `POST /api/knowledge/nearest` — ranked matches for a probe query.
- **Collections (isolated DB `strategy_knowledge_base`):** `strategy_kb_view`, `strategy_kb_champions`.
- **Log grep:** `docker logs factory-backend | grep -E 'knowledge_index_refresh|knowledge router'`
- **Stage complete indicator:** `statistics.total_strategies` stable (KB is read-only); `families` recount without error; `backend_available.rule_based=true`.

### 2.3 · Stage: Market intelligence refresh

- **Task:** `market_intelligence_refresh`
- **Endpoints (flag-gated, live when `MI_ENABLED=true`):**
  - `GET /api/market-intelligence/state`
  - `GET /api/market-intelligence/changes`
  - `GET /api/market-intelligence/intelligence`
  - `POST /api/market-intelligence/refresh`
- **Collections:** `market_intelligence_state`, `market_intelligence_snapshots`, `market_intelligence_changes`, `market_intelligence_events`.
- **Log grep:** `docker logs factory-backend | grep -E 'market_intelligence|MI '`
- **Stage complete indicator:** new snapshot rows in `market_intelligence_snapshots` on the expected cadence; `change_detection` scores updated.

### 2.4 · Stage: Strategy generation

- **Task:** `strategy_generate`
- **Endpoints:**
  - `POST /api/strategies/generate`
  - `POST /api/strategies` (persistence side of the flow — production-safe writes)
  - `GET /api/orchestrator/status` (`.in_flight` shows any active generation)
- **Collections:** `strategies`, `strategy_ir`, `research_lineage_events`, `outcome_events`.
- **Log grep:** `docker logs factory-backend | grep -E 'strategy_generate|strategy_engine|code_generator|compile_engine'`
- **Stage complete indicator:** new rows appear in `strategies` with `eligible_for_deploy=false` (draft state); IR persisted; a matching `strategy_generate_*` row lands in `outcome_events`.

### 2.5 · Stage: Backtesting

- **Task:** `backtest`
- **Endpoints:**
  - Manual dispatch: `POST /api/orchestrator/tasks/backtest/dispatch`
  - Live view: `GET /api/orchestrator/status` — `.in_flight[].task_name == "backtest"`.
- **Collections:** `backtest_runs`, `backtest_reports`.
- **Log grep:** `docker logs factory-backend | grep -E '\[orchestrator\] backtest|backtest_engine|backtest_pool'`
- **Stage complete indicator:** every strategy row surfaces `last_backtest_at`; report count in `backtest_reports` matches the orchestrator's `runs_ok.backtest`.

### 2.6 · Stage: Validation (walk-forward, monte-carlo, OOS holdout)

- **Task:** `validation`
- **Endpoints:**
  - `GET /api/validation/reports/<strategy_id>` (via legacy `strategies.py` side-effect routes).
- **Collections:** `validation_reports`, `walk_forward_results`, `monte_carlo_summaries`, `oos_holdout_verdicts`.
- **Log grep:** `docker logs factory-backend | grep -E 'validation_engine|walk_forward|monte_carlo|oos_holdout'`
- **Stage complete indicator:** validation verdict attached to the strategy row; `outcome_events` records a `validation_*` event.

### 2.7 · Stage: Ranking

- **Task:** `ranking`
- **Endpoints:**
  - `POST /api/rank-strategies`
  - `GET /api/strategies?sort=rank`
- **Collections:** `strategy_rankings`, `ranking_snapshots`.
- **Log grep:** `docker logs factory-backend | grep -E 'ranking_engine|strategy_ranking_engine'`
- **Stage complete indicator:** ranking snapshots write on cadence; strategies pick up `rank` field.

### 2.8 · Stage: Strategy Passport (assembled per strategy)

- **Task:** rendered by the frontend on demand (no dedicated orchestrator task — it composes the outputs of the earlier stages).
- **Endpoints backing the Passport:**
  - `GET /api/strategies/{hash}/history`
  - `GET /api/strategies/{hash}/market-scan`
  - `GET /api/strategies/{hash}/prop-analysis`
  - `GET /api/strategies/{hash}/match-challenges`
  - `GET /api/research-lineage/{strategy_id}`
  - `GET /api/library/{id}/details`
- **Collections:** unioned view over `strategies`, `research_lineage_events`, `market_intelligence_snapshots`, `prop_firm_analysis`, `challenge_matches`.
- **Frontend surface:** `frontend/src/os/surfaces/StrategyPassport.jsx` (Slice β) + Lineage tab hydrated by `adapters/timelineShim.js` (Slice γ).
- **Stage complete indicator:** Passport opens without console error; every tab renders with real data (no "PARTIAL LIVE" badges except for lifecycle-gated tabs).

### 2.9 · Stage: Strategy persistence

- **Task:** — (byproduct of every task that writes a strategy).
- **Endpoints:**
  - `POST /api/strategies` (creates)
  - `GET /api/strategies` (lists)
  - `GET /api/strategies/{id}` (fetches)
- **Guardrails:** `StrategyRepository` injects `eligible_for_deploy != false` filter; `KnowledgeRepository` stays read-only.
- **Log grep:** `docker logs factory-backend | grep -E '/api/strategies (POST|GET)'`
- **Stage complete indicator:** `strategies.countDocuments({})` grows in sync with `outcome_events.strategy_generate_*` rows.

### 2.10 · Stage: Meta-learning evaluation (OBSERVE mode)

- **Task:** `meta_learning_evaluation`
- **Endpoints:**
  - `GET /api/meta-learning/config` — must report `mode=observe`.
  - `GET /api/meta-learning/evaluations`
  - `GET /api/meta-learning/recommendations`
  - `GET /api/meta-learning/pending`
  - `POST /api/meta-learning/refresh`
- **Collections:** `meta_learning_evaluations`, `meta_learning_recommendations`, `meta_learning_pending`, `meta_learning_applications`, `meta_learning_overrides`.
- **Log grep:** `docker logs factory-backend | grep -E 'meta_learning|META_LEARNING_MODE'`
- **Stage complete indicator:** new rows in `meta_learning_evaluations` per orchestrator tick; **applications=0 in OBSERVE mode** (no autonomous policy changes).

### 2.11 · Stage: Factory evaluation (OBSERVE mode)

- **Task:** `factory_evaluation`
- **Endpoints:**
  - `GET /api/factory-eval/config` — must report `mode=observe`.
  - `GET /api/factory-eval/kpis`
  - `GET /api/factory-eval/reports`
  - `GET /api/factory-eval/insights`
  - `GET /api/factory-eval/recommendations`
  - `GET /api/factory-eval/pending`
  - `GET /api/factory-eval/providers/leaderboard`
  - `GET /api/factory-eval/strategies/top-contributors`
- **Collections:** `factory_eval_reports`, `factory_eval_kpis`, `factory_eval_recommendations`, `factory_eval_pending`, `factory_eval_applications`, `factory_eval_overrides`.
- **Log grep:** `docker logs factory-backend | grep -E 'factory_eval|FACTORY_EVAL_MODE'`
- **Stage complete indicator:** new rows in `factory_eval_reports` per orchestrator tick; **applications=0 in OBSERVE mode**.

### 2.12 · Cross-cutting: Budget guardrail

- **Endpoint:** `GET /api/orchestrator/status` — `.meta.budget` summary.
- **Collection:** `budget_state`.
- **Log grep:** `docker logs factory-backend | grep -E 'budget_tracker|budget:'`
- **Stage indicator:** `budget_used_usd` never exceeds `budget_cap_usd` in a single day; on cap-hit the orchestrator halts new task starts (`launched=[]` in decisions).

### 2.13 · Cross-cutting: Execution attribution (OBSERVE by default — `EXEC_ENABLED=false`)

- **Task:** `execution_attribution` (dormant with EXEC off).
- **Endpoints (dormant when EXEC off):**
  - `GET /api/execution/attribution`
  - `GET /api/execution/replay`
  - `GET /api/execution/journal`
- **Stage indicator when EXEC on:** `execution_orders`, `execution_fills`, `execution_positions` populate; broker-health-check task returns `ok`.

### 2.14 · Cross-cutting: Broker health

- **Task:** `broker_health_check`
- **Endpoints:** `GET /api/execution/broker-health` (flag-gated).
- **Log grep:** `docker logs factory-backend | grep -E 'broker_health_check|broker_health'`
- **Stage indicator:** heartbeat rows in `broker_health_events`.

---

## 3 · Orchestrator internals dashboard

| Metric | Where | Interpretation |
|--------|-------|----------------|
| Running | `/api/orchestrator/status.running` | Must be `true`. |
| Enabled by env | `.enabled_by_env` | Confirms `ORCHESTRATOR_ENABLED=true` reached the container. |
| Tick count | `.meta.tick_count` | Monotonically increasing (~1–5 s cadence per `ORCH_TICK_MS`). |
| Dispatched total | `.meta.dispatched_total` | Rising steadily. If flat, tasks are ineligible — inspect `/api/orchestrator/decisions`. |
| In-flight | `.in_flight[]` | Up to `ORCH_MAX_CONCURRENT_TASKS` (default 12). |
| Band | `.meta.last_tick.band` | `normal` / `warn` / `critical` / `unknown`. `critical` triggers 2× idle. |
| Last error | `.meta.last_error` | Null on green. If set, matches most recent task exit. |
| Recent decisions | `/api/orchestrator/decisions?limit=20` | Every candidate's `eligible`, `score`, `reason`. |

Manual dispatch (useful for smoke tests):

```bash
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  "$API_URL/api/orchestrator/tasks/backtest/dispatch" | jq
```

---

## 4 · Ledger reconciliation (weekly audit)

Sanity check that autonomous work is landing in ledgers:

```bash
docker exec factory-mongo mongosh --quiet --eval "
db = db.getSiblingDB('$FACTORY_DB_NAME');
print('audit_log recent:',              db.audit_log.countDocuments({ts: {\$gte: new Date(Date.now()-24*3600*1000).toISOString()}}));
print('outcome_events 24h:',            db.outcome_events.countDocuments({ts_dt: {\$gte: new Date(Date.now()-24*3600*1000)}}));
print('meta_learning_evaluations 24h:', db.meta_learning_evaluations.countDocuments({created_at: {\$gte: new Date(Date.now()-24*3600*1000)}}));
print('meta_learning_applications 24h:',db.meta_learning_applications.countDocuments({created_at: {\$gte: new Date(Date.now()-24*3600*1000)}}));
print('factory_eval_reports 24h:',      db.factory_eval_reports.countDocuments({created_at: {\$gte: new Date(Date.now()-24*3600*1000)}}));
print('factory_eval_applications 24h:', db.factory_eval_applications.countDocuments({created_at: {\$gte: new Date(Date.now()-24*3600*1000)}}));
print('market_intel snapshots 24h:',    db.market_intelligence_snapshots.countDocuments({created_at: {\$gte: new Date(Date.now()-24*3600*1000)}}));
"
```

**Expected in OBSERVE mode:**
- `audit_log`, `outcome_events`, `meta_learning_evaluations`,
  `factory_eval_reports`, `market_intel_snapshots` all > 0.
- `meta_learning_applications` and `factory_eval_applications` = 0
  (no autonomous policy application under OBSERVE — this is the
  contract).

If applications > 0 in OBSERVE mode, something has been mis-flagged —
inspect `/api/meta-learning/config` and `/api/factory-eval/config`
and confirm the mode string.

---

## 5 · Alert triggers (paste into your on-call rotation)

| Signal | Threshold | Fix |
|--------|-----------|-----|
| `orchestrator.running == false` for > 60 s | HIGH | Check `factory-backend` logs → orchestrator crash trace. Restart via `POST /api/orchestrator/start`. |
| `orchestrator.meta.last_error` non-null | MEDIUM | Task-specific — grep the task name in `factory-backend` logs. |
| `orchestrator.dispatched_total` flat for 5 min | MEDIUM | Every task ineligible — `GET /api/orchestrator/decisions?limit=20` and read `reason:`. Typical causes: budget cap hit, band=critical, upstream data stale. |
| `budget_used_usd` ≥ 95 % of cap | LOW → HIGH escalation | Verify `.env` cap; consider raising or leaving orchestrator to self-throttle. |
| `factory-runner` unhealthy | HIGH | `docker logs factory-runner` — if legacy sibling crashed, dispatcher falls back to heartbeat-only; grep for `falling back to heartbeat-only loop`. |
| `market_intelligence_snapshots` no new row for > cadence × 3 | MEDIUM | Task-level failure — check `market_intel_engine` logs. |
| `meta_learning_applications > 0` while `META_LEARNING_MODE=observe` | HIGH — CONTRACT BREACH | Immediately verify config endpoint; if flag was flipped by error, revert via `.env`. |

---

## 6 · Sample "daily green" log line pattern

A healthy factory produces roughly this cadence in the backend log
each day:

```
INFO orchestrator auto-started on boot: {'running': True, 'already_started': False, ...}
INFO budget_tracker rehydration on boot: loaded
INFO market_intelligence indexes bootstrapped
INFO meta_learning engine ready (mode=observe, cadence=…)
INFO factory_eval engine ready (mode=observe, cadence=…)
INFO [orchestrator] backtest → ok=True dur_ms=… reason=eligible
INFO [orchestrator] validation → ok=True dur_ms=… reason=eligible
INFO [orchestrator] market_intelligence_refresh → ok=True dur_ms=… reason=eligible
INFO [orchestrator] meta_learning_evaluation → ok=True dur_ms=… reason=eligible
INFO [orchestrator] factory_evaluation → ok=True dur_ms=… reason=eligible
```

Anything else warrants a look, but the shape above is your default
"green" fingerprint.

---

## 7 · Reference — the 17 registered orchestrator tasks

| Task | Workload class | Cadence source | Notes |
|------|----------------|----------------|-------|
| `backtest` | backtest | event-driven | Manual dispatch supported. |
| `mutation` | mutation | event-driven | |
| `optimization` | mutation | event-driven | |
| `ranking` | api_hot | periodic | Snapshotted. |
| `validation` | backtest | event-driven | |
| `strategy_generate` | agent | continuous seed | Uses `LEARNING_CONTINUOUS_*` seed. |
| `learning_cycle` | agent | continuous | |
| `market_data_topup` | market_data | scheduled (BI5 weekly + on-boot) | Subordinate scheduler resumes. |
| `knowledge_index_refresh` | knowledge | daily | |
| `market_intelligence_refresh` | knowledge | cadence-driven | Requires `MI_ENABLED=true`. |
| `master_bot_bundle_refresh` | agent | scheduled | |
| `meta_learning_evaluation` | meta_learning | cadence-driven | **OBSERVE default.** |
| `factory_evaluation` | meta_learning | cadence-driven | **OBSERVE default.** |
| `self_rebuild` | agent | on-signal | |
| `bi5_realism_sweep` | market_data | weekly | |
| `broker_health_check` | execution | frequent | |
| `execution_attribution` | execution | cadence-driven | Dormant when EXEC off. |

Every task is idempotent, ledger-backed, and honours OBSERVE mode.
