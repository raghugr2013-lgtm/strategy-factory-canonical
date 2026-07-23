# Repository Audit — Orchestration Layer (Phase 2 Milestone)

_Generated: 2026-07-23. Read-only audit; no code changes in this document._

---

## Executive summary

**The orchestration layer already exists.** The `factory-backend` container
auto-bootstraps a production-ready `Unified Orchestrator`
(`legacy/engines/orchestrator/core.py`) on FastAPI startup whenever
`ORCHESTRATOR_ENABLED=true` — with **17 registered task adapters**,
signal-driven readiness scoring, workload-class capping, hard timeouts,
budget tracking, and a manual-dispatch API.

The Phase-1b Factory Supervisor I deployed last week
(`app/factory_supervisor.py`, `factory-runner` container) is a
**complementary APScheduler** — 5 cron-timed jobs for periodic
housekeeping / governance / observability, not a replacement for the
in-backend orchestrator.

**Consequence for this milestone.** A literal reading of the request
("wire every existing engine through the Factory Supervisor") would
**duplicate the Unified Orchestrator's job registry inside APScheduler**,
undermining its adaptive readiness/priority/budget/timeout logic and
creating dual-dispatch risk. **That is not the right activation.**

The correct activation is instead:

1. Turn ON the existing in-backend Orchestrator (`ORCHESTRATOR_ENABLED=true`).
2. Keep every engine's mode-gate at its default (`OBSERVE` / disabled) so
   nothing autonomous runs.
3. Repoint the Factory Supervisor's 5 cron jobs from `placeholder_tick`
   log lines to **thin observability hooks** that snapshot the
   orchestrator's state (no dispatch, no writes) — plus a governance job
   that invokes existing housekeeping utilities.

This treats the audit's discovery as the milestone's north star: **we
activate what already exists, we don't re-implement it**.

---

## 1. Repository audit (Phase 1)

### 1.1 Directory-level engine inventory

| Subsystem | Path | Files | Nature |
| --- | --- | ---: | --- |
| **Unified Orchestrator** | `legacy/engines/orchestrator/` | 24 | ⭐ Full task orchestrator with registry, scoring, dispatch |
| **Orchestrator tasks** | `legacy/engines/orchestrator/tasks/` | 19 | ⭐ 17 registered task adapters |
| Knowledge Engine | `legacy/engines/knowledge/` | 44 | Universal KIE — connectors, pipeline, retrieval, governance |
| Meta-Learning | `legacy/engines/meta_learning/` | 22 | Multi-collector / evaluator / applier pipeline |
| Execution | `legacy/engines/execution/` | 23 | Broker, ledger, lifecycle, replay, risk_monitor |
| Legacy Factory Supervisor | `legacy/engines/factory_supervisor/` | 23 | Distributed worker fleet + submission dispatcher |
| Market Intel | `legacy/engines/market_intel_engine/` | 16 | Regime/volatility/liquidity observers + ledger |
| Portfolio | `legacy/engines/portfolio/` | 10 | Allocation / promotion / retirement / rebuilder |
| COE-γ | `legacy/engines/coe_gamma/` | 10 | Elastic bands, dead-letter, provider admission |
| Brain | `legacy/engines/brain/` | 10 | Signals / policy / scorer / risk budget |
| ASF Importer | `legacy/engines/asf/` | 10 | Strategy Package importer (walker, upserter) |
| Strategy Ingestion | `legacy/engines/strategy_ingestion/` | 9 | Parser / normalizer / validator / injector |
| Factory Evaluation | `legacy/engines/factory_eval/` | 8 | Collectors + evaluators + explainability |
| Intelligence | `legacy/engines/intelligence/` | 7 | Regime, portfolio, master-bot builder |
| Learning | `legacy/engines/learning/` | 6 | Continuous scheduler, lineage, emitter |
| COE | `legacy/engines/coe/` | 5 | Workload queue (local + distributed) |
| CTS | `legacy/engines/cts/` | 5 | Candle time-series cache/resampler |
| AI Workforce | `legacy/engines/ai_workforce/` | 5 | Router / scorer / circuit breaker |
| Root-level engines | `legacy/engines/*.py` | ~180 | Backtest, mutation, monte_carlo, walk_forward, ranking, safety, ai_orchestrator, etc. |

**Grand total: 425 engine .py files under `backend/legacy/engines/`.**

### 1.2 Existing runtime layers (already wired in production)

| Layer | Container | Trigger | What it does |
| --- | --- | --- | --- |
| **Unified Orchestrator** | `factory-backend` | `ORCHESTRATOR_ENABLED=true` (auto-boot in `app/main.py`) | Ticks every ~1s; scores 17 tasks; dispatches by adaptive readiness/priority/budget |
| **Legacy sibling scheduler** | `factory-runner` (mode 2) | `FACTORY_RUNNER_OWNS_SCHEDULERS=true` | Restores persisted APScheduler jobs (BI5 sweep, auto-scheduler, auto-data-maintainer) |
| **Phase-1b Factory Supervisor** | `factory-runner` (mode 1) | `FACTORY_SUPERVISOR_ENABLED=true` ✅ *live in prod* | 5 cron jobs, currently placeholder-only |
| **Learning scheduler(s)** | `factory-backend` | `LEARNING_SCHEDULER_ENABLED` / `LEARNING_CONTINUOUS_MODE` | Auto-boot on startup if enabled |
| **Auto-data-maintainer** | `factory-backend` | Persisted config (`enabled=true`) | Resume-on-boot if previously enabled |

### 1.3 The 17 registered orchestrator tasks

Auto-registered when `import engines.orchestrator.tasks` runs (from
`app/main.py:179` on every backend boot):

| # | Task NAME | Workload class | Priority | Depends on | Mode gate | Notes |
| ---: | --- | --- | ---: | --- | --- | --- |
| 1 | `market_data_topup` | `market_data` | — | — | none in adapter | Backfills BI5 windows |
| 2 | `bi5_realism_sweep` | `market_data` | — | market_data_topup | none | Realism cert sweep |
| 3 | `knowledge_index_refresh` | `api_hot` | 55 | — | none | Rebuild retriever index |
| 4 | `strategy_generate` | `factory_cycle` | — | knowledge_index_refresh | none | New candidate seeding |
| 5 | `backtest` | `backtest` | — | — | none | Runs pending backtests |
| 6 | `validation` | `backtest` | — | backtest | none | OOS + walk-forward gate |
| 7 | `mutation` | `mutation` | 62 | backtest | ⚠ **no gate** | Delegates to `auto_mutation_runner.run_single_cycle` with `auto_save=True` |
| 8 | `optimization` | `mutation` | — | validation | none | Random/GA/param sweep |
| 9 | `learning_cycle` | `meta_learning` | — | validation | `LEARNING_SCHEDULER_ENABLED` | |
| 10 | `ranking` | `api_hot` | 50 | backtest | none | Read-only recompute |
| 11 | `master_bot_bundle_refresh` | `api_hot` | — | ranking | none | Read-only bundle refresh |
| 12 | `self_rebuild` | `factory_cycle` | — | — | flag-gated | Rebuild pipeline (dangerous — must stay off) |
| 13 | `market_intelligence_refresh` | `api_hot` | 65 | — | `MI_ENABLED` | |
| 14 | `broker_health_check` | `monitoring` | — | — | none | Read-only health probe |
| 15 | `execution_attribution` | `execution` | — | — | `EXEC_ENABLED` | Read from ledger only when OBSERVE |
| 16 | `meta_learning_evaluation` | `meta_learning` | 55 | execution_attribution | ⭐ `META_LEARNING_MODE=disabled` skips; default `observe` is read-only |
| 17 | `factory_evaluation` | `api_hot` | 45 | execution_attribution, meta_learning_evaluation | ⭐ `FACTORY_EVAL_MODE=disabled` skips; default `observe` is read-only |

### 1.4 Per-engine mode gates (verified from source)

Every mutation-capable engine has an explicit OBSERVE default in its
config module:

- `META_LEARNING_MODE` → default `observe`; states = disabled/observe/recommend/autonomous.
  Actions are read-only in `observe`; only `recommend`/`autonomous`
  trigger writes (`meta_learning/types.py:MetaMode.affects_platform_data`).
- `FACTORY_EVAL_MODE` → default `observe`; same 4 states, same guard.
- `MI_ENABLED` → prod compose default `false`.
- `EXEC_ENABLED` → prod compose default `false` (live trading kill switch).
- `UKIE_GOVERNANCE_POLICY_ENABLED` → default `false` (knowledge lifecycle policy).
- `ORCHESTRATOR_ENABLED` → default `false` (⭐ the master switch).

**Only two tasks lack an explicit engine-level OBSERVE gate:** `mutation`
and `optimization`. Both delegate directly to auto-runners that persist
strategies. For those, the orchestrator's per-task passive override
(`ORCH_TASK_MUTATION_PASSIVE=true`, `ORCH_TASK_OPTIMIZATION_PASSIVE=true`)
is the operator-facing kill switch — no code change needed.

---

## 2. Dependency verification (Phase 2)

### 2.1 Import graph — spot-check results

- `engines.orchestrator.core` imports only from within its own package
  (`budget_tracker`, `registry`, `types`) plus `engines.host_capability`,
  `engines.compute_probe`, `engines.queue_pressure`,
  `engines.adaptive_concurrency`, `engines.workload_classes`, `engines.coe`.
  **No circular imports observed.**
- `engines.orchestrator.tasks.*` — each adapter imports its target engine
  lazily (inside `run()`), so import-time cost is minimal even when a
  downstream engine has heavy transitive deps.
- **No adapter mutates data at import time.** Verified for the sampled 6
  tasks (mutation, factory_evaluation, meta_learning_evaluation,
  knowledge_index_refresh, market_intelligence_refresh, ranking).

### 2.2 Runtime dependencies

- **MongoDB** — required (schedulers use `engines.db.get_db()`;
  meta_learning + factory_eval + execution + market_intel all persist
  ledgers). Already provisioned.
- **VIE** — required for LLM-backed tasks (`strategy_generate`,
  `strategy_description`). Already provisioned as `factory-vie` service.
- **APScheduler + tzlocal** — already present in `requirements.txt`
  (transitive via `APScheduler>=3.11`).
- **CPU/RAM signals** — `host_capability` + `compute_probe` provide
  runtime introspection; degrade to `caps=None` gracefully if missing.

### 2.3 Feature-flag environment variables (activation surface)

Already enumerated in `app/core/config.py` `OPTIONAL_VARS` and
`docker-compose.prod.yml` for `factory-backend`. Nothing missing.

### 2.4 Wiring issues found in audit — **none requiring code changes**

- App boot (`app/main.py`) already imports
  `engines.orchestrator.tasks` (line 179) triggering registration.
- App boot already calls `get_orchestrator().start()` if enabled.
- Docker compose already enumerates all the relevant env vars on the
  `factory-backend` service.

---

## 3. Activation matrix (Phase 5 — target state)

The correct activation is **through the existing in-backend Orchestrator
in OBSERVE / passive mode**, not through the Factory Supervisor. The
Factory Supervisor becomes a periodic **observability + governance
layer**.

| Engine / task | Activation surface | Proposed value | Behavior |
| --- | --- | --- | --- |
| **Unified Orchestrator** | `ORCHESTRATOR_ENABLED` (backend) | `true` | Tick loop starts; scores every registered task per tick |
| `market_data_topup` | inherit | active | Idempotent BI5 backfill |
| `bi5_realism_sweep` | inherit | active | Read-only cert sweep |
| `knowledge_index_refresh` | inherit | active | Read-only |
| `strategy_generate` | `ORCH_TASK_STRATEGY_GENERATE_PASSIVE=true` | **passive** | Autonomous seeding OFF |
| `backtest` | inherit | active | Runs pending queued backtests only |
| `validation` | inherit | active | Read-only gate |
| `mutation` | `ORCH_TASK_MUTATION_PASSIVE=true` | **passive** | Autonomous mutation OFF |
| `optimization` | `ORCH_TASK_OPTIMIZATION_PASSIVE=true` | **passive** | Autonomous optimization OFF |
| `learning_cycle` | `LEARNING_SCHEDULER_ENABLED=false` | passive | Continuous learning OFF |
| `ranking` | inherit | active | Read-only recompute |
| `master_bot_bundle_refresh` | inherit | active | Read-only |
| `self_rebuild` | `ORCH_TASK_SELF_REBUILD_PASSIVE=true` | **passive** | Rebuild pipeline OFF (dangerous) |
| `market_intelligence_refresh` | `MI_ENABLED=true`, mode default | active | Observers write ledger snapshots (read-only observability) |
| `broker_health_check` | inherit | active | Read-only |
| `execution_attribution` | `EXEC_ENABLED=false` | passive | Live trading stays OFF |
| **`meta_learning_evaluation`** | `META_LEARNING_MODE=observe` | **active (OBSERVE)** | Evaluates + emits recommendations, **no auto-apply** |
| **`factory_evaluation`** | `FACTORY_EVAL_MODE=observe` | **active (OBSERVE)** | Emits insights + recommendations, **no auto-apply** |
| `UKIE governance policy` | `UKIE_GOVERNANCE_POLICY_ENABLED=false` | passive | Knowledge lifecycle policy OFF |

**Nothing autonomous. Nothing writes to strategy_library. Nothing sends
orders. Nothing auto-applies recommendations.** All 5 explicit "do
NOT enable" categories from the milestone brief are preserved.

### 3.1 Factory Supervisor's new (thin) role

Replace the 5 placeholder job bodies with **read-only observability
hooks** — they call the orchestrator's snapshot API, log the state, and
one job (`_job_governance`) invokes housekeeping utilities that already
exist. No dispatching, no engine invocation, no dual-orchestration.

| Cron job | New body | Wiring point |
| --- | --- | --- |
| `_job_orchestrator` (1m) | `snapshot = orchestrator.snapshot()`, emit as structured log line, alert if `not running` | `engines.orchestrator.get_orchestrator().snapshot()` — read-only |
| `_job_mutation` (15m) | Emit `runs_ok / runs_fail / last_completed_ts` for the `mutation` task from orchestrator counters | Same snapshot |
| `_job_factory_eval` (1h) | Emit factory-eval counters + `FEMode` state | Same snapshot + `factory_eval.config.mode()` |
| `_job_meta_learning` (6h) | Emit meta-learning counters + `MetaMode` state | Same snapshot + `meta_learning.config.mode()` |
| `_job_governance` (daily) | Invoke `audit_log` TTL housekeeping if configured; emit knowledge-registry health snapshot | `engines.knowledge.health_provider` (read-only) |

The Factory Supervisor's **cross-process** value is that it runs in the
sibling `factory-runner` container — so if the FastAPI worker crashes,
the runner keeps emitting orchestrator-liveness logs, giving operators
an independent observability channel.

---

## 4. Validation plan (Phase 4)

Before flipping `ORCHESTRATOR_ENABLED=true` in prod, we validate locally:

1. **Registry integrity** — `python -c "import engines.orchestrator.tasks;
   from engines.orchestrator import registry; print(sorted(registry.names()))"`
   → expect 17 names.
2. **No circular imports** — `python -c "import app.main"` completes
   without deadlock.
3. **OBSERVE-mode round-trip** — call `orchestrator.dispatch_task(name)`
   manually for `meta_learning_evaluation` and `factory_evaluation`;
   assert both return `ok=True` with `n_applied=0` in the payload.
4. **Passive kill-switches** — with `ORCH_TASK_MUTATION_PASSIVE=true`,
   assert `mutation` task appears in `snapshot.recent_decisions` with
   `reason="passive"` and `eligible=false`.
5. **Existing test suite** — run `pytest legacy/tests/ -k orchestrator`
   (217 test files exist under `legacy/tests/`). Any regressions block.
6. **Graceful shutdown** — SIGTERM the backend during a tick; confirm
   `orchestrator.stop()` finishes cleanly (already implemented in
   `core.py:571`).

---

## 5. Scheduler execution flow (target)

```
┌────────────────────────────┐        ┌────────────────────────────┐
│  factory-backend container │        │  factory-runner container  │
│  ────────────────────────  │        │  ────────────────────────  │
│                            │        │                            │
│  uvicorn workers           │        │  FactorySupervisor         │
│    │                       │        │  (APScheduler UTC)         │
│    │ boot                  │        │    │                       │
│    ▼                       │        │    ├─ orchestrator (1m)    │
│  Orchestrator singleton    │        │    │    → snapshot log     │
│    │                       │        │    ├─ mutation (15m)       │
│    │ tick every ~1s        │        │    │    → counters log     │
│    ▼                       │        │    ├─ factory_eval (1h)    │
│  gather_signals()          │        │    │    → counters log     │
│    → readiness scores 17   │        │    ├─ meta_learning (6h)   │
│    → dispatch top-K async  │        │    │    → counters log     │
│                            │        │    └─ governance (daily)   │
│  17 tasks:                 │        │         → cleanup + kb hb  │
│   backtest, ranking,       │        │                            │
│   validation, mutation*,   │        │  Reads (read-only) via     │
│   knowledge_refresh,       │◄───────┤  cross-process HTTP or DB  │
│   market_intel, meta_ml,   │  obsv  │  (no dispatch/write path)  │
│   factory_eval, …          │        │                            │
│                            │        │                            │
│  * "passive" tasks are     │        │                            │
│    scored but never fire   │        │                            │
└────────────────────────────┘        └────────────────────────────┘
```

Key properties:

* **Single dispatch authority** — only the backend Orchestrator ever
  calls `task.run(ctx)`. The Factory Supervisor never dispatches.
* **Failsafe observability** — even if backend crashes, the runner keeps
  emitting cron-timed heartbeat + last-known-good snapshots.
* **Env-driven per-task passivity** — operators can flip any dangerous
  task passive with one env var, no code change, no redeploy of images.

---

## 6. Production-readiness assessment

| Component | Ready? | Risk | Mitigation |
| --- | :---: | --- | --- |
| Unified Orchestrator core | ✅ | none observed | Existing code, already boot-wired |
| Task registry (17 adapters) | ✅ | mutation/optimization/self_rebuild lack engine gates | Passive via env |
| OBSERVE-mode engines | ✅ | none — default is safe | Verified in config modules |
| Factory Supervisor (my Phase-1b) | ✅ | placeholder bodies waste 5 cron slots | Repoint to observability |
| Backward compat (legacy sibling) | ✅ | Mode 2 (`FACTORY_RUNNER_OWNS_SCHEDULERS`) still functional | Untouched by proposed changes |
| Docker compose env plumbing | ✅ | supervisor env plumbed (commit 5078fef) | — |
| Tests (217 files) | ⚠ | not run yet against activated orchestrator | Phase-4 pre-flight |

**Overall verdict: PRODUCTION-READY to activate in OBSERVE mode via a
minimal, targeted change** — one env-flag flip on the backend, three
env-flag flips for passive kill switches, plus a code-only supervisor
job-body rewrite. No architecture changes. No new engines. No new
routes. Feature freeze preserved.
