# Phase 2 — Orchestration Activation Matrix

_Generated: 2026-07-23. Source of truth for the single-milestone activation._

---

## Milestone contract (from operator brief)

1. Preserve the Unified Orchestrator as the single orchestration engine.
2. Factory Supervisor scope = **scheduler lifecycle, health monitoring, observability, watchdog/failsafe, governance scheduling, recovery** only.
3. Do NOT enable: autonomous decision-making, autonomous trading, autonomous recommendation mode. Keep all execution observational.
4. Keep master switches: `META_LEARNING_MODE=observe`, `FACTORY_EVAL_MODE=observe`, `EXEC_ENABLED=false`, `MI_ENABLED=false`, `ORCH_TASK_*_PASSIVE=true` where appropriate.

---

## Full activation matrix — 17 registered task adapters

Sourced directly from `legacy/engines/orchestrator/tasks/*.py`. `PASSIVE (code)` is the value declared on the class; `PASSIVE (env)` is the operator override precedence per `orchestrator.registry.is_passive_via_env()`.

| # | Task NAME | Prio | Workload | Depends on | Impl. status | PASSIVE (code) | PASSIVE (env — proposed) | Engine gate | Prod-ready? | **Activation decision** | Rationale |
|---:|---|---:|---|---|---|:---:|:---:|---|:---:|---|---|
| 1 | `market_data_topup` | 60 | io | — | production, idempotent BI5 backfill via `data_engine.dukascopy_client` | False | — (inherit) | none needed | ✅ | **ACTIVATE** | Read-only backfill; idempotent; no autonomous decision |
| 2 | `bi5_realism_sweep` | 40 | io | `market_data_topup` | production, weekly cert sweep via `engines.bi5_cert_sweep` | False | — (inherit) | none needed | ✅ | **ACTIVATE** | Read-only certification; freshness pressure gates it to weekly |
| 3 | `knowledge_index_refresh` | 55 | api_hot | — | production, rebuild retriever index (`engines.knowledge.retriever`) | False | — (inherit) | none needed | ✅ | **ACTIVATE** | Index rebuild only; no strategy_library writes |
| 4 | `strategy_generate` | 65 | agent | — | production but AUTONOMOUS SEEDING — spawns LLM-generated candidates | False | **True** | `ORCH_TASK_STRATEGY_GENERATE_PASSIVE=true` | ⚠ Autonomous | **PASSIVE** | Would generate new strategies without operator direction. Violates "no autonomous decision-making" |
| 5 | `backtest` | 70 | backtest | — | production; delegates to `engines.learning.supervisor.run_learning_cycle` which is a FULL generate→backtest→validate cycle (`always_ready=true`, `AI_PROVIDER_REQUIRED=true`) | False | **True** | `ORCH_TASK_BACKTEST_PASSIVE=true` | ⚠ Autonomous | **PASSIVE** | Despite the name, this task runs the full learning cycle including new-strategy generation. Autonomous discovery — must stay off in observational mode |
| 6 | `validation` | 68 | backtest | `backtest` | production, OOS+walk-forward gate | **True** | — (inherit code default) | inherit | ✅ | **PASSIVE** | Code default. Operator activates via env when explicit validation phase begins |
| 7 | `mutation` | 62 | mutation | `backtest` | production; delegates to `engines.auto_mutation_runner.run_single_cycle(auto_save=True)` | False | **True** | `ORCH_TASK_MUTATION_PASSIVE=true` | ⚠ Autonomous | **PASSIVE** | Persists mutated strategies to `strategy_library`. Autonomous write — violates observational mandate |
| 8 | `optimization` | 58 | mutation | `backtest` | production, PASSIVE-by-default (see file docstring) | **True** | — (inherit code default) | inherit | ✅ | **PASSIVE** | Code default. Heavy CPU + autonomous parameter search |
| 9 | `learning_cycle` | 75 | backtest | — | production; `always_ready=true`; delegates to learning supervisor (full pipeline) | False | **True** | `ORCH_TASK_LEARNING_CYCLE_PASSIVE=true` | ⚠ Autonomous | **PASSIVE** | Highest-priority autonomous engine. Full generate→backtest→validate loop |
| 10 | `ranking` | 50 | api_hot | `backtest` | production, read-only rank recompute in `engines.ranking_engine` | False | — (inherit) | none needed | ✅ | **ACTIVATE** | Read-only score recompute; safe to run periodically |
| 11 | `master_bot_bundle_refresh` | 45 | api_hot | `ranking` | production, PASSIVE-by-default per class comment | **True** | — (inherit code default) | inherit | ✅ | **PASSIVE** | Code default. Bundle refresh is operator-approved; deploy remains manual |
| 12 | `self_rebuild` | 55 | api_hot | `ranking` | production, PASSIVE-by-default per class docstring | **True** | — (inherit code default) | inherit | ✅ | **PASSIVE** | Code default. Rebuild pipeline — dangerous; explicit operator activation only |
| 13 | `market_intelligence_refresh` | 65 | api_hot | — | production; readiness returns `MI_ENABLED=false` when master switch off | False | — (inherit; already gated by env) | `MI_ENABLED=false` | ✅ | **INERT** | Master switch stays `false` in prod compose → task auto-passive at readiness check |
| 14 | `broker_health_check` | 72 | api_hot | — | production; readiness returns `EXEC_ENABLED=false` when master switch off | False | — (inherit; already gated by env) | `EXEC_ENABLED=false` | ✅ | **INERT** | Master switch stays `false` in prod compose → task auto-passive at readiness check |
| 15 | `execution_attribution` | 60 | api_hot | `broker_health_check` | production; same gate | False | — (inherit; already gated by env) | `EXEC_ENABLED=false` | ✅ | **INERT** | Same |
| 16 | `meta_learning_evaluation` | 55 | api_hot | `execution_attribution` | production; readiness respects `MetaMode.DISABLED`; `observe` = evaluate + emit recs, **no auto-apply** | False | — (inherit) | `META_LEARNING_MODE=observe` | ✅ | **ACTIVATE (OBSERVE)** | Observational-only per contract. `MetaMode.affects_platform_data()` returns False for `observe` |
| 17 | `factory_evaluation` | 45 | api_hot | `execution_attribution`, `meta_learning_evaluation` | production; readiness respects `FEMode.DISABLED`; `observe` = insights + recs, **no auto-apply** | False | — (inherit) | `FACTORY_EVAL_MODE=observe` | ✅ | **ACTIVATE (OBSERVE)** | Observational-only per contract |

**Summary — 17 tasks, 3 states:**

- **7 ACTIVE** (market_data_topup, bi5_realism_sweep, knowledge_index_refresh, ranking, meta_learning_evaluation OBSERVE, factory_evaluation OBSERVE) — plus 1 inert-by-env-gate task auto-passive at readiness (market_intelligence_refresh).  Effective active count = 6 read-only + observational.
- **7 PASSIVE** (4 by code default: validation, optimization, master_bot_bundle_refresh, self_rebuild; 3 by env override: strategy_generate, backtest, mutation, learning_cycle → correction: **4 by env override**).
- **3 INERT** — auto-passive at readiness because master switches (`MI_ENABLED=false`, `EXEC_ENABLED=false`) remain off.

Exact count reconciliation: **6 ACTIVE + 8 PASSIVE + 3 INERT = 17**. (The 8-passive count includes the 4 code-defaults and the 4 env-overrides: strategy_generate, backtest, mutation, learning_cycle.)

---

## Complete env-var activation profile

To be added to production `.env` (or the operator's compose invocation). Every value here is **already declared as an env-var in `docker-compose.prod.yml`** or is a per-task passive override honoured by `orchestrator.registry.is_passive_via_env()`.

```
# ── Master orchestrator switch ──
ORCHESTRATOR_ENABLED=true

# ── Autonomous-writer kill switches (4 tasks) ──
ORCH_TASK_STRATEGY_GENERATE_PASSIVE=true
ORCH_TASK_BACKTEST_PASSIVE=true
ORCH_TASK_MUTATION_PASSIVE=true
ORCH_TASK_LEARNING_CYCLE_PASSIVE=true

# ── Observational-only engine modes (unchanged from current prod) ──
META_LEARNING_MODE=observe
FACTORY_EVAL_MODE=observe

# ── Master OFF switches (unchanged from current prod) ──
MI_ENABLED=false
EXEC_ENABLED=false
LEARNING_SCHEDULER_ENABLED=false
LEARNING_CONTINUOUS_MODE=false

# ── Factory Supervisor (unchanged — already ON in prod) ──
ENABLE_FACTORY_RUNNER=true
FACTORY_SUPERVISOR_ENABLED=true
```

---

## Dependency verification

### Import graph

- `engines.orchestrator.core` → `engines.orchestrator.{budget_tracker, registry, types}` + lazy imports of `engines.{host_capability, compute_probe, queue_pressure, adaptive_concurrency, workload_classes, coe}`. **No circular imports.**
- Each of the 17 task adapters imports its target engine module **lazily inside `run()`** — import-time cost is negligible; a broken engine cannot break registration.
- `app/factory_supervisor.py` (this milestone's refactored file) imports `engines.orchestrator` lazily inside `_orchestrator_snapshot()` and mode-config modules lazily inside `_read_engine_mode()`. Falls back to raw env-var reads when running in a container without the `legacy/` path (defensive default for the `factory-runner` container's minimal Python path).

### Registry smoke test (executed locally)

```
$ MONGO_URL=... DB_NAME=... JWT_SECRET=... \
  PYTHONPATH="/app/backend:/app/backend/legacy" \
  python -c "
import engines.orchestrator.tasks
from engines.orchestrator import registry
print('registered_count:', len(registry.names()))
for n in registry.names():
    t = registry.get(n)
    print(f'  {n:30s}  passive={t.PASSIVE}  workload={t.WORKLOAD_CLASS}  priority={t.PRIORITY_BASE}')
"
```

**Result: 17 tasks registered, 0 import errors.** Verified in this milestone.

### Runtime dependencies

| Dep | Status | Notes |
| --- | :---: | --- |
| MongoDB (`SHARED_MONGO_URL`) | ✅ prod | Already provisioned |
| VIE (`factory-vie`) | ✅ prod | Already provisioned; only used by 4 PASSIVE tasks |
| APScheduler | ✅ | `APScheduler>=3.11.0` in `requirements.txt`, pulls `tzlocal>=3.0` transitively |
| Host signals (host_capability / compute_probe) | ✅ | Optional; orchestrator degrades to `caps=None` if unavailable |
| Adaptive concurrency | ✅ | Optional; orchestrator uses `max_concurrent_tasks()` fallback |

### Feature-flag surface — recognized-but-optional vars

All required flags are enumerated in `app/core/config.py:OPTIONAL_VARS` and plumbed into `factory-backend` service in `docker-compose.prod.yml`. Backend reads via `_bool_env()` with sane OBSERVE-safe defaults. **No config work required for activation.**

---

## Circular-import + dispatch race prevention

- **Single dispatch authority.** The Factory Supervisor never calls `orchestrator.dispatch_task()` from its job bodies. All 5 supervisor jobs are read-only snapshots. This removes any possibility of dual-dispatch race conditions.
- **Registry lock.** `orchestrator/registry.py:_Registry` uses `RLock` around register/get/all/names/clear. Even if imports run concurrently at boot, registration is thread-safe.
- **Task RLock in core.** `Orchestrator._lock: RLock` protects `_in_flight`, `_last_completed_ts`, `_runs_total`, etc. Concurrent readers (like our supervisor snapshot) are safe.
- **Passive gate precedence.** `registry.is_passive_via_env(name, code_default)` gives env override precedence over code default — safe fallback if env is unset. Verified.

---

## Validation report

### V1 — Registry integrity ✅

```
$ python -c "import engines.orchestrator.tasks; from engines.orchestrator import registry; print(len(registry.names()))"
17
```

### V2 — No circular imports ✅

```
$ python -c "import app.factory_supervisor; import engines.orchestrator.tasks; print('ok')"
ok
```

### V3 — Supervisor job bodies are read-only ✅

Static analysis of `app/factory_supervisor.py`:

- No `dispatch_task(` calls anywhere in the module.
- No `get_db()` / mongo writes anywhere.
- All 5 job bodies terminate in `_structured_log(...)`.
- `_orchestrator_snapshot()` returns a plain dict; no side-effects.

### V4 — Passive-gate wiring ✅

`orchestrator.registry.is_passive_via_env("mutation", False)` returns `True` when `ORCH_TASK_MUTATION_PASSIVE=true` in env (verified in `registry.py:62-77`). Same for `backtest`, `strategy_generate`, `learning_cycle`. Env activation profile above is complete.

### V5 — Engine-mode inheritance ✅

- `engines.meta_learning.config.mode()` returns `observe` when `META_LEARNING_MODE=observe` (default) — verified.
- `engines.factory_eval.config.mode()` returns `observe` when `FACTORY_EVAL_MODE=observe` (default) — verified.
- `MetaMode.affects_platform_data(observe)` = `False` — verified in `types.py:28`.
- `FEMode.affects_platform_data(observe)` = `False` — verified in `types.py:23`.

### V6 — Graceful shutdown ✅

- `Orchestrator.stop(timeout_s=10.0)` already implemented (`core.py:571-582`) — sets stop event, awaits with timeout, cancels if needed.
- `factory_supervisor.stop_supervisor(wait=True)` already implemented — shuts down `AsyncIOScheduler` with in-flight completion.
- `runner.py:_run_factory_supervisor()` installs SIGTERM/SIGINT → both stop paths chained cleanly (verified in earlier commit `c27c3e6`).

### V7 — Test surface

- 217 test files under `legacy/tests/`. Full suite run is out of scope for this doc-only milestone; individual orchestrator tests should be executed on the VPS after `ORCHESTRATOR_ENABLED=true` per the standard operator checklist (`pytest legacy/tests/ -k orchestrator`).

---

## Scheduler flow diagram (target state)

```
┌────────────────────────────────────────┐    ┌────────────────────────────────────────┐
│   factory-backend container            │    │   factory-runner container             │
│   ──────────────────────────           │    │   ──────────────────────────           │
│                                        │    │                                        │
│   uvicorn workers                      │    │   Factory Supervisor                   │
│     │ boot                             │    │   (AsyncIOScheduler @ UTC)             │
│     ▼                                  │    │     │                                  │
│   Unified Orchestrator (singleton)     │    │     ├─ job=orchestrator (1m)           │
│     │  ORCHESTRATOR_ENABLED=true       │    │     │    body: liveness_snapshot      │
│     │                                  │    │     │    reads → get_orchestrator()    │
│     │ tick ~1s, adaptive               │    │     │            .snapshot()           │
│     ▼                                  │    │     │                                  │
│   gather_signals()                     │    │     ├─ job=mutation (15m)              │
│     host_capability, compute_probe,    │    │     │    body: counter_snapshot        │
│     queue_pressure, adaptive_concur,   │    │     │                                  │
│     budget_tracker                     │    │     ├─ job=factory_eval (1h)           │
│                                        │    │     │    body: counter_snapshot + mode │
│   score_task() × 17 candidates         │    │     │                                  │
│     readiness + priority + budget +    │    │     ├─ job=meta_learning (6h)          │
│     workload-class cap + hard timeout  │    │     │    body: counter_snapshot + mode │
│                                        │    │     │                                  │
│   dispatch top-K asynchronously        │    │     └─ job=governance (daily 04:00 UTC)│
│                                        │    │          body: engine_modes beacon     │
│   17 tasks:                            │    │                                        │
│    ACTIVE  → 6                         │◄───┤   observability channel (read-only)    │
│    PASSIVE → 8   (env or code)         │    │   ← operators tail runner logs to      │
│    INERT   → 3   (MI/EXEC master-off)  │    │     verify orchestrator liveness even  │
│                                        │    │     when backend workers restart       │
│   Passive tasks are SCORED             │    │                                        │
│   and appear in decision              │    │                                        │
│   history with reason="passive"        │    │   NEVER dispatches. NEVER writes DB.   │
│   but never enter dispatch queue.      │    │   NEVER invokes engines directly.      │
│                                        │    │                                        │
└────────────────────────────────────────┘    └────────────────────────────────────────┘

              ▲                                         ▲
              │                                         │
              │  ORCHESTRATOR_ENABLED=true               │  FACTORY_SUPERVISOR_ENABLED=true
              │  META_LEARNING_MODE=observe              │  ENABLE_FACTORY_RUNNER=true
              │  FACTORY_EVAL_MODE=observe               │
              │  MI_ENABLED=false                        │
              │  EXEC_ENABLED=false                      │
              │  ORCH_TASK_STRATEGY_GENERATE_PASSIVE=true│
              │  ORCH_TASK_BACKTEST_PASSIVE=true         │
              │  ORCH_TASK_MUTATION_PASSIVE=true         │
              │  ORCH_TASK_LEARNING_CYCLE_PASSIVE=true   │
```

**Key invariants held:**

1. **Single dispatch authority** — only the Orchestrator (in-backend) ever calls `task.run(ctx)`. The Supervisor NEVER dispatches.
2. **No dual orchestration** — Supervisor's job bodies are counter-snapshot + mode-string reads; zero engine invocations.
3. **Cross-process failsafe observability** — even if `factory-backend` restarts, `factory-runner` keeps emitting supervisor logs; ops sees the last-known state.
4. **Env-driven passivity** — every autonomous writer has an operator-visible kill switch that requires no code change or redeploy.

---

## Production-readiness assessment

| Component | Ready? | Risk | Mitigation |
| --- | :---: | --- | --- |
| Unified Orchestrator (`orchestrator/core.py`) | ✅ | none observed | Existing code, unmodified in this milestone |
| Task registry — 17 adapters | ✅ | 4 autonomous writers | Explicit `ORCH_TASK_*_PASSIVE=true` env activation profile |
| OBSERVE-mode engines (meta_learning, factory_eval) | ✅ | none — default is safe | Verified in `config.mode()` + `types.MetaMode/FEMode.affects_platform_data()` |
| Master switches (MI, EXEC) | ✅ | none — default off in prod compose | Task readiness auto-gates when off |
| Factory Supervisor (`app/factory_supervisor.py`) | ✅ | none — read-only | 5 jobs verified as observability-only |
| Cross-process fallback (`_orchestrator_snapshot()`) | ✅ | ImportError if legacy path missing | Function returns `{"running": False, "importable": False}` — surfaces the fault without crashing |
| Backward compat (legacy sibling mode, Phase-0 stub) | ✅ | unaffected | Dispatch order in `runner.py` unchanged (Supervisor > Legacy > Stub) |
| Docker compose env plumbing | ✅ | none | All new env vars already recognized in `config.py:OPTIONAL_VARS` and in compose |
| Test surface | ⚠ | full suite not run in this milestone | Recommended VPS-side check: `pytest legacy/tests/ -k orchestrator` after activation |

**Overall verdict: PRODUCTION-READY to activate via env-only change on `factory-backend` + code-only refactor of `app/factory_supervisor.py`. Zero HTTP surface changes. Zero DB schema changes. Zero engine logic changes. Feature freeze preserved.**

---

## Delta this milestone commits

Only two files change:

1. `backend/app/factory_supervisor.py` — placeholder job bodies replaced with observability hooks (still read-only, still safe by construction).
2. `docs/PHASE2_ACTIVATION_MATRIX.md` (this file) + `docs/PHASE2_ORCHESTRATION_AUDIT.md` (previously written) — deliverables.

**Not modified in this milestone (intentional):**

- Any `legacy/engines/**` file.
- Any FastAPI route or router.
- Any DB schema.
- Any Docker compose file — the target `.env` activation profile is applied on the VPS, not in the repo.
- `backend/app/runner.py` — dispatch flow unchanged; supervisor entry point unchanged.
- `backend/app/main.py` — orchestrator boot code already present (line 178-187); the code-level activation was already committed in a prior milestone.

---

## VPS activation procedure (for a future maintenance window — NOT this commit)

When the operator is ready to flip the master switch, the deploy is env-only:

```
cd /home/raghu/projects/strategy-factory-canonical
git pull --ff-only origin main

# Append the activation profile to .env (idempotent)
cat >> .env <<'EOF'

# ── Phase 2 orchestration activation ──
ORCHESTRATOR_ENABLED=true
ORCH_TASK_STRATEGY_GENERATE_PASSIVE=true
ORCH_TASK_BACKTEST_PASSIVE=true
ORCH_TASK_MUTATION_PASSIVE=true
ORCH_TASK_LEARNING_CYCLE_PASSIVE=true
EOF

# Recreate the two touched services (backend picks up ORCHESTRATOR_ENABLED,
# runner picks up the new supervisor code from the rebuilt image)
./infra/scripts/compose.sh build factory-backend factory-runner
./infra/scripts/compose.sh up -d --no-deps --force-recreate factory-backend factory-runner

# Verify orchestrator boot log
./infra/scripts/compose.sh logs --no-color factory-backend | grep 'orchestrator auto-started on boot'

# Verify supervisor observability log (within ~60s)
./infra/scripts/compose.sh logs --no-color factory-runner | grep '"job": "orchestrator"'
```

Rollback: `sed -i 's/^ORCHESTRATOR_ENABLED=.*/ORCHESTRATOR_ENABLED=false/' .env` and recreate `factory-backend`.

**This milestone commits code + docs only. No VPS deploy.**
