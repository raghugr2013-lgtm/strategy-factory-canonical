# Strategy Factory — Phase 1 Factory Validation Report

**Status:** template — fill in the placeholder blocks from the output of
`sudo -u <docker-user> /opt/strategy-factory/infra/scripts/phase1_validate.sh`.
**Companion to:** `docs/PHASE_1_ACTIVATION_PLAN.md` §8 (sign-off gate).

The purpose of this file is to keep a durable, git-tracked record of
each activation attempt so future ops passes can see exactly what was
observed post-flip. Every subsequent activation (or reactivation
after a rollback) appends a new dated block.

---

## Report metadata

| Field | Value |
|-------|-------|
| Report date (UTC) | `<paste timestamp from script header>` |
| Operator | `<name>` |
| VPS host | `<paste from script section 0>` |
| Repo SHA at activation | `<from section 1: HEAD SHA>` |
| Prior baseline SHA | `<the pre-Phase-1 SHA captured in PHASE_1_ACTIVATION_PLAN.md §6.1>` |
| Activation type | `first-time / re-activation / rollback-then-reactivate` |

---

## Section A · Operational state (from script §1–§2)

### A.1 · Repo hygiene

- [ ] HEAD SHA equals origin/main.
- [ ] Working tree clean.

### A.2 · Env file activation flags

Paste `_kv` block from script §2 verbatim:

```
FACTORY_RUNNER_OWNS_SCHEDULERS  <value>
ORCHESTRATOR_ENABLED            <value>
BUDGET_PERSIST                  <value>
MI_ENABLED                      <value>
LEARNING_SCHEDULER_ENABLED      <value>
LEARNING_CONTINUOUS_MODE        <value>
META_LEARNING_MODE              <value>   # must be `observe`
FACTORY_EVAL_MODE               <value>   # must be `observe`
EXEC_ENABLED                    <value>   # must be `false`
FACTORY_RUNNER_HEARTBEAT_SEC    <value>
```

Verdict:

- [ ] `FACTORY_RUNNER_OWNS_SCHEDULERS=true`, `ORCHESTRATOR_ENABLED=true`, `BUDGET_PERSIST=true`, `MI_ENABLED=true`.
- [ ] `META_LEARNING_MODE=observe`, `FACTORY_EVAL_MODE=observe`, `EXEC_ENABLED=false` — OBSERVE contract intact.
- [ ] `LEARNING_SCHEDULER_ENABLED=false`, `LEARNING_CONTINUOUS_MODE=false` — orchestrator supersedes them.

---

## Section B · Compose sanity (script §3)

- [ ] `docker compose --env-file .env -f infra/compose/docker-compose.prod.yml config` exits OK.
- [ ] Same command WITHOUT `--env-file` FAILS with a `SHARED_MONGO_URL` diagnostic — interpolation guards intact.

```
<paste script §3 output>
```

---

## Section C · Container inventory + healthchecks (script §4)

Paste script §4 output:

```
factory-backend    <state / hc>
factory-frontend   <state / hc>
factory-vie        <state / hc>
factory-runner     <state / hc>
factory-mongo      <state / hc>
caddy              <state / hc>

--- vqb-network membership ---
<paste>
```

Verdict:

- [ ] All six containers `running / healthy`.
- [ ] All six containers appear on `vqb-network`.
- [ ] No duplicate container names anywhere.

---

## Section D · Backend health + readiness (script §5)

Paste `/api/health` + `/api/readiness` JSON:

```json
<paste /api/health>
<paste /api/readiness>
```

Public URL:

```
<paste public probes>
```

Verdict:

- [ ] `/api/health` returns 200, `service:strategy-factory-backend`.
- [ ] `/api/readiness` reports `mongo=green`, `vie=green`, `redis=green|skipped`.
- [ ] Public URL returns 200 on both `/api/health` and `/`.

---

## Section E · Autonomous factory endpoints (script §6)

### E.1 · `/api/orchestrator/status`

```
running               <bool>
enabled_by_env        <bool>
tick_count            <int>
dispatched_total      <int>
last_error            <null | string>
last_tick.band        <normal | warn | critical | unknown>
last_tick.in_flight   <int>
in_flight (now)       <int>
task_names_count      <int, expect ≥ 17>
counters.runs_total   <dict>
counters.runs_ok      <dict>
counters.runs_fail    <dict>
```

Verdict:

- [ ] `running=true`.
- [ ] `enabled_by_env=true` (confirms env reached the container).
- [ ] `tick_count > 0` within 60 s of boot; monotonically increasing.
- [ ] `last_error=null`.
- [ ] `task_names_count >= 17`.
- [ ] `counters.runs_total` non-empty within 15 min.

### E.2 · `/api/orchestrator/decisions?limit=5`

```
<paste last 5 decision one-liners>
```

Verdict:

- [ ] `band` is `normal` or `warn` (not `critical`).
- [ ] Non-empty `launched` list appears at least once every ~30 s.

### E.3 · Meta-Learning + Factory-Eval mode

```
/api/meta-learning/config → mode=<must be observe>  cadence_s=<int>
/api/factory-eval/config → mode=<must be observe>  cadence_s=<int>
```

Verdict:

- [ ] Both report `mode=observe`.

### E.4 · Knowledge statistics

```
/api/knowledge/statistics → total_strategies=<int> families=<int> champions=<int>
```

Verdict:

- [ ] `total_strategies` matches the seeded corpus (baseline 140 rows post-KB-import).

---

## Section F · Ledger reconciliation, 24 h (script §7)

Paste script §7 verbatim:

```
audit_log(ts,24h)              <int>
outcome_events(ts_dt,24h)      <int>
strategies(created_at,24h)     <int>
backtest_reports(created_at)   <int>
validation_reports(created_at) <int>
ranking_snapshots(created_at)  <int>
meta_learning_evaluations      <int>
meta_learning_applications     <int>   # must be 0 in OBSERVE
factory_eval_reports           <int>
factory_eval_applications      <int>   # must be 0 in OBSERVE
market_intelligence_snapshots  <int>
research_lineage_events        <int>

Sibling runner heartbeats (last 30 min):
  factory_runner:startup   pid=<int>  <iso>
  factory_runner:heartbeat pid=<int>  <iso>
  factory_runner:heartbeat pid=<int>  <iso>
```

Verdict:

- [ ] `audit_log(24h) > 0`.
- [ ] `outcome_events(24h) > 0` — the loop is emitting events.
- [ ] `meta_learning_applications = 0` (CONTRACT — OBSERVE mode).
- [ ] `factory_eval_applications = 0` (CONTRACT — OBSERVE mode).
- [ ] At least one `factory_runner:heartbeat` in the last 15 min.

---

## Section G · Log fingerprints (script §8)

Paste the tail of section §8 (backend + runner):

```
<paste last 30 orchestrator-related backend log lines>

--- factory-runner ---
<paste last 40 runner log lines>
```

Verdict:

- [ ] Backend log contains `orchestrator auto-started on boot`.
- [ ] Backend log contains `budget_tracker rehydration on boot` (BUDGET_PERSIST=true).
- [ ] Backend log contains `market_intelligence indexes bootstrapped` (MI_ENABLED=true).
- [ ] Backend log contains at least one `[orchestrator] <task> → ok=True` line.
- [ ] Runner log contains `delegating to legacy.factory_runner`.
- [ ] Runner log contains `sibling runner ACTIVE` (or the legacy runner's equivalent).
- [ ] No `Traceback` in either log window.

---

## Section H · Heartbeat file freshness (script §9)

```
<paste hb line>
```

Verdict:

- [ ] File present, age < 120 s. GREEN.

---

## Section I · Restart-recovery drill

Run these steps AFTER Section H is green:

```bash
# 1. Snapshot the orchestrator state
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/orchestrator/status" | jq '.meta.tick_count, .meta.dispatched_total' > /tmp/pre-restart.json

# 2. Bounce the runner
docker restart factory-runner

# 3. Wait 90 s for the sibling to restore its schedulers + budget
sleep 90

# 4. Re-check
docker exec factory-backend curl -sS -m 5 -H "Authorization: Bearer $TOKEN" \
  "$API/api/orchestrator/status" | jq '.meta.tick_count, .meta.dispatched_total' > /tmp/post-restart.json
diff /tmp/pre-restart.json /tmp/post-restart.json

# 5. Repeat for factory-backend
docker restart factory-backend
sleep 90
docker exec factory-backend curl -fsS -m 5 "$API/api/health"
docker exec factory-backend curl -fsS -m 5 "$API/api/readiness" | jq
```

Fill in:

| Signal | Pre-restart | Post-restart | Δ | Verdict |
|--------|-------------|--------------|----|---------|
| `orchestrator.tick_count` | `<x>` | `<y>` | `<y-x>` | Increasing = healthy |
| `orchestrator.dispatched_total` | `<x>` | `<y>` | `<y-x>` | Increasing = healthy |
| Budget cap remembered? | check `/api/orchestrator/status.meta.budget` before + after | | | equal = healthy |
| Sibling heartbeat within 60 s of restart? | | | | yes = healthy |

Verdict:

- [ ] Orchestrator resumes automatically on backend restart (no manual `POST /api/orchestrator/start` needed).
- [ ] Sibling schedulers restore on runner restart within 90 s.
- [ ] Budget tracker rehydrates (BUDGET_PERSIST=true).
- [ ] No collection loses any row across either restart.

---

## Section J · Warnings + bottlenecks observed

Free-form. Log every YELLOW / MEDIUM signal here:

- `<e.g. "band=warn" seen 3 times in 30 min → investigate host cpu>`
- `<e.g. "task X ran 0 times in 24h" — check task readiness/dependency>`
- `<e.g. "meta_learning_evaluations flat since 06:00 UTC" — check MI cadence>`

---

## Section K · Final verdict

- [ ] All 8 sign-off gates in `PHASE_1_ACTIVATION_PLAN.md` §8 closed.
- [ ] Restart drill (§I) passed.
- [ ] OBSERVE contract intact (meta_learning_applications = factory_eval_applications = 0).
- [ ] Weekly ledger reconciliation snippet from `AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md` §4 scheduled in cron.

**Activation status:** `GREEN / YELLOW / RED`
**Signed:** `<operator>`  ·  `<UTC timestamp>`
