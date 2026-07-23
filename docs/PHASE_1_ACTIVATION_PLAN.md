# Phase 1 · Autonomous Factory Activation Plan

**Companion to:** `docs/IMPLEMENTATION_ROADMAP.md` (Phase 1),
`docs/AUTONOMOUS_FACTORY_READINESS.md`,
`docs/AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md`.
**Objective:** Make the existing Strategy Factory run continuously on
the VPS using capabilities that are ALREADY in the canonical repo.
Zero new engines. Zero new endpoints. Zero schema changes. OBSERVE
mode preserved. Backend Feature Freeze preserved.

---

## 1 · What changed in the repo (minimal, reversible)

Three files touched — one modified, one refined (backward-compatible
additive), one refined (activation flags propagated), and one env
template extended. The activation surface itself is entirely
env-driven.

| # | File | Kind of change | Behaviour when flags OFF |
|---|------|---------------|--------------------------|
| 1 | `backend/app/runner.py` | **Rewritten as a dispatcher** — heartbeat-only fallback when `FACTORY_RUNNER_OWNS_SCHEDULERS=false`; delegates to `legacy.factory_runner._main()` when true. Always refreshes `/tmp/factory_runner.hb` so the docker healthcheck stays green in both modes. | **Byte-equivalent to Phase-0 stub.** Emits the same log line, writes the same heartbeat, honours `ENABLE_FACTORY_RUNNER` the same way. |
| 2 | `backend/legacy/factory_runner.py` | **Additive** — refreshes `/tmp/factory_runner.hb` on start and every audit-heartbeat tick. Nothing else changed. | Zero effect (the sibling runner only executes when the dispatcher delegates to it). |
| 3 | `infra/compose/docker-compose.prod.yml` | Propagates Phase-1 activation env vars into `factory-backend` + `factory-runner` `environment:` blocks (compose --env-file only supplies interpolation; variables absent from the compose `environment:` block never reach `os.environ`). | Defaults preserve prior behaviour — every new flag is `${VAR:-false}` (or `observe`) so `docker compose up -d` without an updated `.env` boots exactly as it did before Phase 1. |
| 4 | `.env.example` | Extended with a well-commented Phase-1 activation block. All defaults OFF. | Dev overlay unaffected. |

**Zero new files under `backend/`.** No API contract change. No
database schema change. No `data-testid` change. No OBSERVE-mode
change.

---

## 2 · What was REUSED (nothing built)

Every autonomous cycle stage is powered by a subsystem that already
exists in the canonical repo. Reference IDs are from
`docs/CAPABILITY_INVENTORY.md`.

| Cycle stage | Reused subsystem | ID | Registered orchestrator task |
|-------------|------------------|----|------------------------------|
| Market data refresh | `data_engine/auto_data_maintainer.py` + BI5 pipeline | F5, F2, F3 | `market_data_topup` |
| Knowledge index refresh | `app/knowledge/*` + `KnowledgeRepository` | B1..B6 | `knowledge_index_refresh` |
| Market intelligence refresh | `engines/market_intel_engine/*` (8 observers) | I3 | `market_intelligence_refresh` |
| Strategy generation | `engines/strategy_engine.py` + IR + refinement + code gen | D1, D2 | `strategy_generate` |
| Validation | `engines/validation_engine.py` + walk-forward + monte-carlo | E2, E6 | `validation` |
| Backtesting | `engines/backtest_engine.py` + `backtest_pool` + `backtest_report` | E1 | `backtest` |
| Ranking | `engines/strategy_ranking_engine.py` + `ranking_engine.py` | D6 | `ranking` |
| Strategy Passport generation | `frontend/src/os/surfaces/StrategyPassport.jsx` + `research_lineage.py` + `strategy_memory.py` | M1, K10 | (rendered by frontend; backing endpoints reused) |
| Strategy persistence | `POST /api/strategies` (guarded by `StrategyRepository`) | A6, B2 | (natural byproduct of every task) |
| Meta-learning evaluation | `engines/meta_learning/*` (6 evaluators + collectors + applier) | I4 | `meta_learning_evaluation` |
| Factory evaluation | `engines/factory_eval/*` (collectors + evaluators + explainability + ledger) | I5 | `factory_evaluation` |

Additional supporting subsystems reused as-is:

- Scheduler tier (learning · continuous · orchestrator) — C1..C6.
- Budget tracker with restart rehydration — C5.
- Outcome-event ledger + meta-learning ledger + factory-eval ledger + market-intel ledger.
- Universal Health Contract — K7 / A3 (`/api/health/{system,subsystems,<name>}`).
- Advisory locks + admission controller + adaptive concurrency — K5, L6.
- Audit log writer + activation journal — K1, K2.

**Reused = 100 % of business logic.**

---

## 3 · What was REFINED (surgical, additive)

Two refinements — both narrow and reversible:

| # | Refinement | Rationale | Effect |
|---|-----------|-----------|--------|
| R1 | `backend/app/runner.py` reshaped into a backward-compatible dispatcher | The Phase-0 stub self-describes as a temporary artifact (`"Later phases will replace this stub with the recovered legacy.factory_runner:main() invocation"`). This IS that later phase. | When the activation flag is off, behaviour is byte-equivalent to the stub; when on, the recovered sibling runs. |
| R2 | `backend/legacy/factory_runner.py` heartbeat file write | The recovered runner only emitted Mongo audit heartbeats; the docker healthcheck expects `/tmp/factory_runner.hb`. Adding a file write inside the same heartbeat loop keeps the healthcheck contract unchanged. | Prevents the "healthy → running → still healthy" transition from stalling during scheduler restore (which can take longer than the docker `start_period`). |

Both refinements are additive; no existing logic path was removed.

---

## 4 · What was EXTENDED (compose env propagation)

Compose `environment:` blocks for `factory-backend` and
`factory-runner` gained the Phase-1 activation env vars with
production-safe defaults (`false` / `observe`). This is the standard
pattern already documented in the compose file's own comment block
(lines 80–91 of the pre-existing prod compose): a variable must be
enumerated in `environment:` for it to reach the container.

No engine code, no API code, no test, no schema was extended.

---

## 5 · What was NOT changed

- No new backend endpoint.
- No new backend engine.
- No new frontend component.
- No new database collection or index.
- No modification of any existing API contract.
- No modification of any OBSERVE-mode gate.
- No modification of any `data-testid`.
- No enabling of live trading (`EXEC_ENABLED=false` remains default).
- No enabling of autonomous promotions (`META_LEARNING_MODE=observe`
  + `FACTORY_EVAL_MODE=observe` remain default).
- No new environment variable was invented — every activation flag
  is already read by an existing engine (`ORCHESTRATOR_ENABLED` by
  `orchestrator/core.py:56`, `FACTORY_RUNNER_OWNS_SCHEDULERS` by
  `legacy/factory_runner.py:82`, etc.). We only propagated existing
  reads through compose.

---

## 6 · Deployment instructions (production VPS)

Run these steps as the docker-group user on the VPS with the canonical
checkout at `/opt/strategy-factory`. Every step is idempotent.

### 6.1 · Preserve a snapshot (mandatory)

```bash
cd /opt/strategy-factory
git rev-parse HEAD                                    # record current SHA
./infra/scripts/backup.sh                             # fresh Mongo dump into /var/backups/strategy-factory
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' > /tmp/pre-phase1-containers.txt
cp /opt/strategy-factory/.env /opt/strategy-factory/.env.pre-phase1  # chmod 600 preserved
```

### 6.2 · Pull the Phase 1 activation code

```bash
cd /opt/strategy-factory
git fetch origin --prune
git checkout main
git reset --hard origin/main
```

### 6.3 · Edit `/opt/strategy-factory/.env` — activation flags

Append (or update) these lines. Every one is documented in
`.env.example`.

```env
# Phase 1 activation
FACTORY_RUNNER_OWNS_SCHEDULERS=true
ORCHESTRATOR_ENABLED=true
BUDGET_PERSIST=true
MI_ENABLED=true

# Preserved defaults — DO NOT flip during Phase 1
LEARNING_SCHEDULER_ENABLED=false
LEARNING_CONTINUOUS_MODE=false
META_LEARNING_MODE=observe
FACTORY_EVAL_MODE=observe
EXEC_ENABLED=false
```

**Rationale for each flag:**

- `FACTORY_RUNNER_OWNS_SCHEDULERS=true` → the sibling process takes
  ownership of the persisted schedulers (auto-scheduler,
  orchestrator-scheduler, auto-data-maintainer). Uvicorn workers stay
  free for HTTP.
- `ORCHESTRATOR_ENABLED=true` → the Unified Autonomous Orchestration
  Engine (Phase B.2) auto-starts on boot. Every legacy scheduler with
  `subordinate_to_orchestrator=true` (default) becomes dormant while
  the orchestrator is running — **no duplicate schedulers**.
- `BUDGET_PERSIST=true` → the daily USD budget cap survives restarts.
- `MI_ENABLED=true` → market-intelligence indexes bootstrap on boot;
  the `market_intelligence_refresh` orchestrator task starts feeding
  the 8-observer suite.
- `LEARNING_*` flags left OFF because the orchestrator supersedes
  them. If you need to run WITHOUT the orchestrator for a validation
  session, flip `ORCHESTRATOR_ENABLED=false` and
  `LEARNING_CONTINUOUS_MODE=true` — never both simultaneously.
- `META_LEARNING_MODE=observe`, `FACTORY_EVAL_MODE=observe`,
  `EXEC_ENABLED=false` → the OBSERVE-mode contract. Meta-learning
  and factory-eval write ledgers + emit recommendations but never
  mutate policy without operator approval. Live execution stays off.

```bash
chmod 600 /opt/strategy-factory/.env
```

### 6.4 · Precheck + deploy

```bash
./infra/scripts/precheck.sh                           # must print "precheck OK"
./infra/scripts/deploy.sh                              # builds + up + health
```

`deploy.sh` will:
1. Rebuild the backend and runner images with the current commit's `app/runner.py` dispatcher.
2. `docker compose up -d` recreates only the containers whose config
   changed — every service picks up its new env block on restart.
3. `health.sh` runs; all six containers must return healthy.

### 6.5 · Verify the autonomous cycle came online

Green-path signals — run in order, stop on the first FAIL:

```bash
# 1. Runner delegated to legacy sibling
docker logs --tail 50 factory-runner | grep -E 'delegating to legacy.factory_runner|sibling runner ACTIVE'
# → expect one line of each

# 2. Orchestrator auto-started on boot
docker logs --tail 200 factory-backend | grep -E 'orchestrator auto-started'
# → "orchestrator auto-started on boot: ..."

# 3. Orchestrator status endpoint (auth required)
API_URL="https://$FACTORY_DOMAIN"
TOKEN=$(curl -s -X POST "$API_URL/api/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('access_token') or d.get('token'))")
curl -fsS -H "Authorization: Bearer $TOKEN" "$API_URL/api/orchestrator/status" | jq '{running, enabled_by_env, tick_count: .meta.tick_count, dispatched_total: .meta.dispatched_total, in_flight: (.in_flight|length)}'
# → running=true, tick_count > 0 within 60 s

# 4. Budget tracker rehydrated
docker logs --tail 200 factory-backend | grep -E 'budget_tracker rehydration'

# 5. Market intelligence bootstrapped
docker logs --tail 200 factory-backend | grep -E 'market_intelligence indexes bootstrapped'

# 6. Sibling audit heartbeats every 5 min
docker exec factory-mongo mongosh --quiet --eval \
  "db=db.getSiblingDB('$FACTORY_DB_NAME'); db.audit_log.find({event:/factory_runner/}).sort({ts:-1}).limit(3).forEach(printjson)"

# 7. Full readiness aggregate
docker exec factory-backend curl -fsS http://127.0.0.1:8001/api/readiness | jq
# → mongo=green, vie=green, redis=skipped is OK
```

If any step fails, jump to §7 (rollback).

### 6.6 · Ongoing observation

See `docs/AUTONOMOUS_CYCLE_HEALTH_DASHBOARD.md` for the full
observability matrix. Key ongoing commands:

```bash
# Tail every stage transition
./infra/scripts/compose.sh logs --tail 100 -f factory-backend factory-runner \
  | grep -E 'orchestrator|task=|readiness|budget|meta_learning|factory_eval|market_intelligence'

# Recent orchestrator decisions (top 20)
curl -fsS -H "Authorization: Bearer $TOKEN" "$API_URL/api/orchestrator/decisions?limit=20" | jq
```

---

## 7 · Rollback plan

### 7.1 · Env-only rollback (fast — no code change)

Turn every activation flag OFF and redeploy. The recovered runner
returns to heartbeat-only mode and the orchestrator halts.

```bash
sudo sed -i \
  -e 's/^FACTORY_RUNNER_OWNS_SCHEDULERS=.*/FACTORY_RUNNER_OWNS_SCHEDULERS=false/' \
  -e 's/^ORCHESTRATOR_ENABLED=.*/ORCHESTRATOR_ENABLED=false/' \
  -e 's/^MI_ENABLED=.*/MI_ENABLED=false/' \
  /opt/strategy-factory/.env

./infra/scripts/deploy.sh --skip-precheck
./infra/scripts/health.sh
```

`META_LEARNING_MODE=observe` + `FACTORY_EVAL_MODE=observe` +
`EXEC_ENABLED=false` are already at their production-safe defaults —
no live trading happened, no policy was applied.

### 7.2 · Full code rollback (if env-only isn't enough)

```bash
# 1. Note the pre-Phase-1 SHA captured in §6.1
PRE_SHA=$(cat /tmp/pre-phase1-sha.txt 2>/dev/null || echo "<paste from §6.1 output>")

cd /opt/strategy-factory
git fetch origin
git checkout $PRE_SHA           # detached HEAD — safe

# 2. Restore the pre-Phase-1 .env if the current file is suspect
sudo install -m 600 /opt/strategy-factory/.env.pre-phase1 /opt/strategy-factory/.env

# 3. Redeploy from the pre-Phase-1 code
./infra/scripts/deploy.sh --skip-precheck
./infra/scripts/health.sh
```

Every scheduler that had rehydrated its state from Mongo will resume
where it was. Volumes are never touched by this rollback.

### 7.3 · Ledger rollback (if OBSERVE writes are somehow undesirable)

Ledgers written during Phase 1 (`meta_learning_evaluations`,
`meta_learning_pending`, `factory_eval_reports`,
`factory_eval_recommendations`, `market_intelligence_snapshots`,
`outcome_events`) can be inspected and, if needed, restored from the
§6.1 mongodump archive with `./infra/scripts/restore.sh <archive>`.

**Under OBSERVE mode nothing in these ledgers alters production
strategy state.** No rollback should be needed unless an operator
explicitly flipped a `MODE` to `active` — which Phase 1 does not do.

---

## 8 · Sign-off gate

Phase 1 is considered complete when ALL of the following are true:

- [ ] `./infra/scripts/health.sh` exit 0 (all-green).
- [ ] `docker inspect factory-runner --format '{{.State.Health.Status}}'` → `healthy`.
- [ ] `GET /api/orchestrator/status` returns `running: true` with `tick_count > 0`.
- [ ] `GET /api/readiness` returns mongo=green + vie=green.
- [ ] `audit_log` contains at least one `factory_runner:startup` row from the current PID.
- [ ] `outcome_events` collection is receiving new rows (correlation with orchestrator tick).
- [ ] `meta_learning_evaluations` collection is receiving new evaluations (OBSERVE mode).
- [ ] `factory_eval_reports` collection is receiving new reports (OBSERVE mode).
- [ ] Tier-3 CI (`make tier3`) stays green for one full night after activation.

Once all eight gates close, the factory is considered continuously
operational. Any deviation returns to §7 rollback.

---

## 9 · What Phase 1 does NOT do (deliberate)

- Does not build any new engine.
- Does not duplicate any scheduler.
- Does not duplicate any orchestrator.
- Does not duplicate any validator.
- Does not duplicate any persistence layer.
- Does not modify production API behaviour.
- Does not enable live trading.
- Does not enable autonomous promotions.
- Does not touch the MongoDB `strategy_knowledge_base` DB (KB
  remains structurally read-only).
- Does not lift the Backend Feature Freeze.

Every deviation from these bullets requires a fresh planning pass.
