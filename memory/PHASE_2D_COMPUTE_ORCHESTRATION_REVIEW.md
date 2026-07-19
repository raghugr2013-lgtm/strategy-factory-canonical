# Phase 2D — Compute & Resource Orchestration Audit
### Evolving the Strategy Factory into a Unified Compute Orchestration Engine (COE)

> **Status:** review only — no code changes.
> This document audits the existing execution / worker / scheduler /
> queue / resource management substrate at commit `829f31d` and
> proposes its **evolutionary** upgrade into a Compute Orchestration
> Engine that can safely execute the entire Strategy Factory workload
> — AI (VIE), BI5 ingestion, market data, strategy generation,
> backtesting, validation, knowledge ingestion, meta-learning,
> execution intelligence, monitoring & analytics — with maximum
> throughput and strict fault isolation.

---

## 0. Current state

### 0.1 The compute stack is already deeper than most greenfield designs

```
                              ┌────────────────────────────────────────┐
                              │  Boot bootstraps (app/main.py lifespan)│
                              └────────────────┬───────────────────────┘
                                               │ conditional on flags
       ┌───────────────────────────────────────┼─────────────────────────────────────────────────┐
       │                                       │                                                 │
       ▼                                       ▼                                                 ▼
┌──────────────┐          ┌────────────────────────────────────────┐          ┌─────────────────────────────┐
│ APScheduler  │          │  Unified Orchestrator (Phase B.2)      │          │  Learning Continuous         │
│ jobs         │          │  asyncio tick — 17 task adapters       │          │  Scheduler (Phase B.1)       │
│ (cron/       │          │  scores + dispatches by                │          │  asyncio, capacity-aware     │
│  interval)   │          │  workload-class caps + budget headroom │          │  RPM + hourly governors      │
└──────┬───────┘          └────────────────────┬───────────────────┘          └────────────┬────────────────┘
       │                                       │  ▲                                          │
       │ subordinate_to_orchestrator=True      │  │                                          │
       ▼                                       │  │                                          ▼
┌─────────────────────────┐                    │  │                              ┌────────────────────────┐
│ auto_scheduler          │────subordinates────┘  │                              │ learning.supervisor    │
│ (discovery cycles)      │                       │                              │ ._scheduler_loop       │
│ orchestrator_scheduler  │                       │                              │ (legacy fixed-interval)│
│  ├── ai_orch tick       │                       │                              └────────────────────────┘
│  └── weekly BI5 realism │                       │
│ auto_data_maintainer    │                       │
│  (BID/BI5 top-ups)      │                       │
└─────────────────────────┘                       │
                                                  │
                                                  ▼
                              ┌────────────────────────────────────────┐
                              │        Admission control substrate     │
                              │  (async with admission_gate(WLC): ...) │
                              │                                        │
                              │  gate() → admit | defer | refuse       │
                              │  based on 4 signals:                   │
                              │   ① host_capability   (tier: s/m/l/xl) │
                              │   ② compute_probe     (live cpu/mem)   │
                              │   ③ queue_pressure    (rolling window) │
                              │   ④ adaptive_concurrency (per-class    │
                              │       target: bt / mut / factory / …)  │
                              └────────────────────┬───────────────────┘
                                                   │
                                                   ▼
                              ┌────────────────────────────────────────┐
                              │       Execution primitives             │
                              │                                        │
                              │  cpu_pool (ProcessPoolExecutor,        │
                              │    dormant by default — falls through  │
                              │    to asyncio.to_thread when off)      │
                              │                                        │
                              │  backtest_pool / mutation_pool         │
                              │    → thin opt-in wrappers over cpu_pool│
                              │                                        │
                              │  asyncio.to_thread                     │
                              │    → default hot path                  │
                              │                                        │
                              │  asyncio tasks                         │
                              │    → learning cycles, orchestrator     │
                              │      tick, scheduler bodies, all HTTP  │
                              └────────────────────┬───────────────────┘
                                                   │
                                                   ▼
                              ┌────────────────────────────────────────┐
                              │  Cross-cutting: budget_tracker,        │
                              │  scaling_events, research_lineage,     │
                              │  ai_workforce.circuit_breaker/router,  │
                              │  workload_classes, feature_flags       │
                              └────────────────────────────────────────┘
```

Files (`backend/legacy/engines/`):

| Layer | Files |
|---|---|
| Host detection | `host_capability.py` (315), `compute_probe.py` (153) |
| Sizing (pure) | `adaptive_pool_sizer.py`, `adaptive_concurrency.py` |
| Workload taxonomy | `workload_classes.py` (5 classes) |
| Admission | `admission_controller.py` (295), `admission_wrapper.py` (223), `queue_pressure.py` (238) |
| Pools | `cpu_pool.py` (171), `backtest_pool.py`, `mutation_pool.py` |
| Orchestrator | `orchestrator/core.py` (531), `orchestrator/registry.py`, `orchestrator/budget_tracker.py` (344), `orchestrator/types.py`, `orchestrator/tasks/*` (17 adapters) |
| Schedulers | `orchestrator_scheduler.py` (325), `auto_scheduler.py` (409), `learning/supervisor.py` (555), `learning/continuous_scheduler.py` (463), `data_engine/auto_data_maintainer.py` |
| Governance | `feature_flags.py` (1494), `scaling_events.py`, `research_lineage.py`, `activation_governance.py` |
| Provider routing | `ai_workforce/router.py`, `ai_workforce/circuit_breaker.py`, `ai_workforce/scorer.py`, `ai_workforce/telemetry.py` |

### 0.2 What is production-grade today (KEEP verbatim)

| Component | Verdict | Why it stays |
|---|---|---|
| **Layered pure-function capacity math** (host → sizer → adaptive → admission) | ✅ | Each layer is unit-testable in isolation; no I/O in the hot path — the same shape ML orchestrators (Kubernetes, Nomad) reach after years of iteration. |
| **`async with admission_gate(WLC):` wrap-site pattern** | ✅ | One canonical primitive at every CPU-bound entry — matches Google Borg's `alloc` semantics. `queue_pressure.incr()` synchronous BEFORE first `await` → no double-admit races. |
| **Feature-gated dormant paths** (`USE_PROCESS_POOL`, `ENABLE_ADMISSION_CONTROL`, `LEARNING_CONTINUOUS_MODE`, `ORCHESTRATOR_ENABLED`) | ✅ | 60-second rollback discipline. Every new layer added additively — pre-flag behaviour is byte-identical. |
| **Five canonical workload classes** with fixed vocabulary | ✅ core | The idea is right (small closed set, per-class caps + advisory profile). The set itself is now too small — see §0.4/G1. |
| **Honest-refusal semantics** (`admit` / `defer:30s` / `refuse`) with journal | ✅ | Backpressure surface every consumer can react to. Verdict carries `retry_after_sec` — API layer can map to HTTP `429`/`503` cleanly. |
| **Subordination protocol** between schedulers (`auto_scheduler` defers when `orchestrator_scheduler` runs; both defer when `Orchestrator` is authoritative) | ✅ concept | Prevents double-firing of the same discovery cycle. But complexity is O(N²) as new schedulers appear — see §0.3/B1. |
| **Universal task Protocol** (`NAME, WORKLOAD_CLASS, DEPENDS_ON, MIN_INTERVAL_S, PRIORITY_BASE, CPU_ESTIMATE_CORES, RAM_ESTIMATE_MB, AI_PROVIDER_REQUIRED, COST_ESTIMATE_USD, BUSINESS_VALUE, PASSIVE`) | ✅ | Class-level metadata means the scorer never has to invoke the task to decide whether to run it. Every new task adds one file, zero orchestrator changes. |
| **17 task adapters covering the factory pipeline** | ✅ | `strategy_generate, backtest, validation, mutation, optimization, learning_cycle, ranking, master_bot_bundle_refresh, self_rebuild, market_intelligence_refresh, broker_health_check, execution_attribution, meta_learning_evaluation, factory_evaluation, market_data_topup, bi5_realism_sweep, knowledge_index_refresh` — the workload universe is already modelled. |
| **Budget tracker with 4-dim provider selection** (cost × quality × latency × availability) | ✅ | Provider-agnostic; `choose_provider()` degrades to any subset of the weights. Consumed by VIE. |
| **Deterministic scoring** — `score = priority_base × business × pressure × dep_readiness × budget_headroom / resource_cost_factor` | ✅ | Pure function, easy to reason about, easy to A/B via env overrides (`ORCH_TASK_<NAME>_PRIORITY_BASE`). |
| **Passive flag** (`PASSIVE=True` + `ORCH_TASK_<NAME>_PASSIVE=false` operator override) | ✅ | Every task can be individually disabled without redeploy. |
| **Rolling-window queue pressure bands** (idle / normal / high / critical) | ✅ | Categorical output the admission controller consumes; sample-driven, memory-bounded. |
| **APScheduler + AsyncIO cohabitation** with `max_instances=1, coalesce=True` | ✅ | Belt-and-braces guard against overlapping ticks even if a tick overruns. |
| **`AsyncIOScheduler(timezone="UTC")`** consistency across all schedulers | ✅ | No local-time drift bugs; DST-safe. |
| **Circuit breaker + scorer per AI provider** (`ai_workforce/`) | ✅ | Feeds `budget_tracker.choose_provider()`; already vendor-independent. |

### 0.3 Bottlenecks (measurable today)

| # | Bottleneck | Impact | Evidence |
|---|---|---|---|
| **B1** | **Scheduler proliferation.** Five independent scheduler surfaces live in-process today (`auto_scheduler`, `orchestrator_scheduler`, `learning.supervisor._scheduler_loop`, `learning.continuous_scheduler`, `data_engine.auto_data_maintainer`). Each has its own start/stop, its own config collection, its own subordination hooks. | Ownership ambiguity; each new scheduler requires N-1 subordination checks. Adding a 6th (e.g. UKIE ingestion) costs 5 code edits. | `orchestrator_scheduler.py:132–160` — hand-coded fall-through into `orchestrator.is_active()` → then into `orchestrator_scheduler.is_active()` — the chain is fragile and untested against reordering. |
| **B2** | **ProcessPool is DORMANT.** `USE_PROCESS_POOL=false` is the default; every backtest still runs on `asyncio.to_thread` → single-thread GIL-bound. Numpy-heavy loops in `backtest_engine.run_backtest_logic` never see multi-core. | On an 8-core VPS the effective backtest throughput is 1 core, not 8. Mutation pipelines that fan out to 20 children serialise. | `cpu_pool.py:39-41` (`is_enabled` returns False by default). `backtest_pool.py:44-49` (needs *both* `USE_PROCESS_POOL=true` AND `ENABLE_PROCESS_POOL_BACKTEST=true`). No production deployment has both flags on. |
| **B3** | **No cross-process payload strategy.** Even if `USE_PROCESS_POOL=true`, arguments must be picklable — no Mongo cursors, no framework objects, no closures. The `run_backtest_logic` signature is *already* clean (plain lists/dicts) but every OTHER cpu-bound path (mutation genetic ops, strategy IR walkers, ranking) has code paths that hold DB handles at the boundary. | Migration to pool routing per-call requires an audit at every wrap site. | `mutation_pool.py:41-53` — the doc explicitly says "functions submitted MUST be top-level (importable), args + returns MUST be picklable, no DB handles" but the enforcement is discipline, not typing. |
| **B4** | **No persistent budget / queue state.** `BudgetTracker` is in-memory; on process restart the daily USD counter resets to 0. `queue_pressure._depth` and `_window` are also in-memory. | A restart mid-day can silently double the daily provider spend if all traffic reroutes back to the same provider. Rolling-window snapshots are useless for the first `window_sec` after boot. | `budget_tracker.py:37` — "Not persisted in this first cut (matches Q5 direction: one architectural change per phase)." `queue_pressure.py:38-52` — deque + dict, no Mongo mirror. |
| **B5** | **Global hard-cap coarse.** `ORCH_MAX_CONCURRENT_TASKS=12` is the only backstop over ALL classes combined. If BACKTEST + MUTATION + FACTORY_CYCLE fill the ceiling simultaneously, event-driven paths (KNOWLEDGE, MARKET_DATA, EXECUTION) starve. | Priority inversion: a low-priority factory cycle can block a high-priority broker_health_check. | `orchestrator/core.py:73` — `max_concurrent_tasks() default 12`, no per-class *guaranteed* reservations. |
| **B6** | **Backtest engine is one monolith.** `backtest_engine.run_backtest_logic` is a single top-level function called end-to-end per strategy. No stage decomposition (data-load → strategy-eval → metrics), so partial failures re-run everything. | ≥ 30% wasted CPU when a strategy fails at metrics computation with an OOM in the eval loop — the eval work was already sunk. | `learning/supervisor.py:259-291` calls `run_backtest_logic` monolithically; the only checkpoint is "did the whole thing return?". |
| **B7** | **Knowledge / ingestion / MI refresh tasks share the AGENT class.** `AGENT` is `max_parallel_hint="unlimited"` and only band-gated. Meanwhile `KNOWLEDGE_INDEX_REFRESH` can be I/O + CPU heavy (embedding rebuild). | A cascading knowledge rebuild in the middle of a factory cycle burst can starve BACKTEST for I/O. | `workload_classes.py:36-42` — no I/O class; `agent` covers ingestion + knowledge + MI + monitoring alike. |
| **B8** | **No dead-letter or retry policy.** A `Task.run()` that throws sets `_runs_fail[name] += 1` and moves on. No exponential backoff, no requeue with jitter, no crash budget. | Same broken task keeps burning slots every tick; noisy in ops logs. | `orchestrator/core.py:325-338` — `_dispatch` finally-block increments counters, never requeues. |
| **B9** | **Observability is rich in-memory but not exported.** Every layer exposes `snapshot()`; none emit to Prometheus / OTLP / ELK. `/api/*` diagnostic endpoints work but require polling. | Impossible to alert on backpressure events reactively. | No `prometheus_client` import anywhere; `scaling_events.emit()` writes only to Mongo. |
| **B10** | **Producer/consumer coupling.** API endpoints (e.g. `/api/backtest/run`) submit synchronously; there's no queue-then-return-job-id pattern. Long jobs occupy a request thread. | Frontend can time out on a 90 s backtest; parallel requests fight for uvicorn workers. | `legacy/api/backtest.py` — every "run" endpoint awaits `run_backtest_logic` inline. |

### 0.4 Architectural gaps

| # | Gap | Severity | Why it matters for the full workload |
|---|---|---|---|
| **G1** | **Workload taxonomy too small.** 5 classes for a 12-subsystem factory. Missing: `MARKET_DATA_INGEST`, `KNOWLEDGE_INGEST`, `EXECUTION_LIVE`, `MONITORING`, `META_LEARNING`, `RESEARCH_LINEAGE`. | Critical | Without per-class SLAs and reservations, priority scheduling is best-effort. |
| **G2** | **No priority tier separation** (interactive vs. background vs. batch). All tasks compete on the same `score`. | Major | A user-triggered `POST /api/backtest/run` shares the same queue as a scheduled `factory_evaluation` — the user waits. |
| **G3** | **No workload reservations.** Adaptive concurrency computes CAPS (upper bounds); no FLOORS (guaranteed minimums). | Major | Under pressure, low-`priority_base` classes can be starved to zero forever. |
| **G4** | **Fault isolation only at the async-task boundary.** `try/except` wraps `task.run(ctx)`; segfaults / OOM in a `ProcessPoolExecutor` worker crash the *whole* pool. | Major | One misbehaving strategy text (e.g. infinite loop in eval) takes down every concurrent backtest. |
| **G5** | **No horizontal / multi-node story.** Every counter, deque, and pool is in-process. A "second VPS" cannot participate. | Major (future) | Blocks scaling beyond a single 32-core box. |
| **G6** | **No standardized "job envelope."** Tasks accept `OrchestratorContext` and produce `TaskResult`; API endpoints take request bodies. There is no unified `WorkloadRequest` that can be persisted, resumed, or forwarded to a remote worker. | Major | Prerequisite for any queue-based / distributed design. |
| **G7** | **Meta-learning and monitoring are modeled as tasks, not as continuous streams.** `factory_evaluation` runs on-demand; `broker_health_check` is a discrete task. But both are conceptually always-on. | Moderate | Wastes score / dispatch cycles on things that should be tail-streaming. |
| **G8** | **No provider-aware admission gate.** `admission_gate` decides on host capacity + workload class; it does not consult `ai_workforce.circuit_breaker` for the target provider. | Moderate | A BACKTEST that requires an LLM (via VIE) can be admitted on capacity grounds but its provider circuit is OPEN → it fails immediately. |
| **G9** | **No SLA / latency budget per class.** Nothing declares "a BACKTEST must complete in 60 s or be killed." Timeouts live inside each engine, not at the orchestrator layer. | Moderate | Rogue tasks can hang and hold a workload slot indefinitely. |
| **G10** | **`compute_probe` samples on demand.** Every gate call may trigger a psutil read. | Minor | On a hot admission path (say 500 admits/min) we do 500 syscall bursts. |
| **G11** | **Circular imports risk in `admission_wrapper`** — module imports `admission_controller, queue_pressure, scaling_events, workload_classes`, all of which import each other; the workload_classes / admission chain is documented as needing deferred imports. | Minor | Slow accidents on module refactor. |
| **G12** | **APScheduler doesn't share the same async loop as `Orchestrator` core.** APScheduler runs its jobs on the AsyncIOScheduler internal loop; the Orchestrator runs on the main FastAPI loop. Cross-scheduler signalling is via Mongo config + `is_active()` polls. | Minor | Complicates the subordination protocol. |
| **G13** | **Monitoring & analytics is not represented at all in `workload_classes`.** MI observers, DB metric collectors, dashboard refreshers are just `asyncio.create_task` sprinkled in engine startup. | Moderate | Cannot be capacity-gated. |
| **G14** | **No cost-of-preemption model.** A running task cannot be safely aborted mid-flight; the orchestrator cannot preempt a low-priority task to make room for a high-priority one. | Moderate | Priority inversion under critical band. |

---

## 1. Target architecture — the Compute Orchestration Engine (COE)

### 1.1 Guiding principles (unchanged from existing platform philosophy)

1. **Additive & feature-gated.** Every layer added under a flag; default OFF means byte-identical behaviour to today.
2. **Pure functions over I/O.** Sizing, scoring, admission continue as read-only pure functions with injectable inputs — unit-testable, deterministic, no boot-time surprises.
3. **One canonical primitive per concern.** `admission_gate` stays the single wrap-site; a new `workload_queue.submit()` becomes the single job-envelope primitive.
4. **Honest refusal over silent buffering.** Every admission decision is `admit | defer(retry_after) | refuse`, journaled with a reason.
5. **Rollback in 60 seconds.** Every new capability is a flag flip away from being dormant.
6. **Operator authority.** Every automated decision has an env override (`ORCH_TASK_*`, `ORCH_BUDGET_*`, `WORKLOAD_PROFILE`, forthcoming `WORKLOAD_RESERVATION_*`).
7. **Distribution-ready from day one** *(operator directive, 2026-02-19)*. The current VPS is the **first compute node**, never the permanent architecture. Every counter, queue, budget, and pressure snapshot in COE α/β lives behind a Protocol whose local implementation is single-node today and whose distributed implementation is COE γ+ — the switch is a driver swap. No single-node assumptions may leak into API surface or engine code. Concretely: `WorkloadQueue`, `BudgetTracker`, `queue_pressure`, `host_capability` all define `LocalDriver` (α/β) and `DistributedDriver` (γ+) implementations under the SAME interface. If a design decision would make it harder to distribute later, choose the other decision.
8. **Measurable health everywhere** *(operator directive, 2026-02-19)*. Every subsystem produces a `HealthSnapshot` (see `PHASE_2_CONSOLIDATED_REVIEW.md §5.1`) — including COE itself. COE's `HealthSnapshot` aggregates queue depth, pool state, reservation satisfaction, dead-letter count, and admission-refusal rate into a single deterministic `health_score`. Ships in COE α as `engines/health/contract.py`; every downstream subsystem imports this contract.

### 1.2 Extended workload class taxonomy (10 classes)

The 5-class vocabulary is frozen inside `workload_classes.py` for backwards
compatibility with 17 already-registered task adapters and every wrap
site. We **extend, never rename**.

```python
class WorkloadClass(str, Enum):
    # KEEP — existing 5, semantics unchanged
    API_HOT           = "api_hot"          # interactive request handlers
    BACKTEST          = "backtest"         # CPU-bound strategy eval
    MUTATION          = "mutation"         # CPU-bound GA / IR mutation
    FACTORY_CYCLE     = "factory_cycle"    # aggregate discovery ticks
    AGENT             = "agent"            # LLM-heavy orchestration
    # ADD — new classes for the full factory workload
    MARKET_DATA       = "market_data"      # BI5/BID ingest, tick pulls
    KNOWLEDGE         = "knowledge"        # UKIE connectors + index refresh
    EXECUTION         = "execution"        # broker calls, order lifecycle
    MONITORING        = "monitoring"       # dashboards, alert engines, MI observers
    META_LEARNING     = "meta_learning"    # factory-eval / policy update
```

Per-class defaults extend the existing `_PROFILE_DEFAULTS` table with
**reservations** (guaranteed minimum concurrency) alongside caps:

| Class | `cpu_share` | `mem_cap_mb` | `max_parallel_hint` | **reservation** (new) | Rationale |
|---|---|---|---|---|---|
| `API_HOT` | 0.10 | 200 | unlimited | 2 | Users must never wait. |
| `BACKTEST` | 0.45 | 1024 | pool_size | 1 | The workhorse; deserves most of the pool. |
| `MUTATION` | 0.25 | 768 | pool_size | 1 | Second heaviest; must never starve. |
| `FACTORY_CYCLE` | 0.05 | 256 | 1 | 0 | Discovery — best-effort. |
| `AGENT` | 0.05 | 512 | unlimited | 1 | LLM orchestration reserved slot. |
| `MARKET_DATA` | 0.03 | 512 | 2 | 1 | Never lose a BI5 tick. |
| `KNOWLEDGE` | 0.05 | 768 | 2 | 0 | Bursty; best-effort. |
| `EXECUTION` | 0.02 | 256 | unlimited | 2 | Live trades are latency-critical. |
| `MONITORING` | 0.01 | 128 | unlimited | 1 | Small but always-on. |
| `META_LEARNING` | 0.05 | 512 | 1 | 0 | Runs during quiet windows. |

**Reservations** are enforced by the admission gate: even when overall
pressure is `critical`, up to `reservation` slots per class are still
admitted (subject to actual host capacity — critical CPU/mem still
refuses everything).

Operator override: `ORCH_RESERVATION_<CLASS>=<int>`.

### 1.3 Queue architecture — priority lanes + workload-class queues

Today the "queue" is implicit — `queue_pressure._depth` counts in-flight
work, and `orchestrator/core.py._tick` re-scores every candidate every
tick. There is no queue *of waiting work* — the scheduler either
dispatches immediately or the caller retries.

**Target:** introduce an in-memory (later Mongo-mirrored) **`WorkloadQueue`**
with **three priority lanes** per class:

```
    ┌──────────────── WorkloadQueue ────────────────┐
    │                                                │
    │  For each WorkloadClass:                       │
    │                                                │
    │  ┌─────────────────────────────────────────┐   │
    │  │  P0 (interactive)   ← API_HOT + user    │   │
    │  │    triggered work                        │   │
    │  ├─────────────────────────────────────────┤   │
    │  │  P1 (scheduled)     ← orchestrator ticks│   │
    │  ├─────────────────────────────────────────┤   │
    │  │  P2 (background)    ← factory / meta    │   │
    │  └─────────────────────────────────────────┘   │
    │                                                │
    │  submit(req: WorkloadRequest) → job_id         │
    │  next(cls, cap) → Optional[WorkloadRequest]    │
    │  peek(cls) → depth per lane                    │
    │  cancel(job_id)                                │
    │                                                │
    └────────────────────────────────────────────────┘
```

Where a `WorkloadRequest` is the unified job envelope introduced in §4.

**Priority lane resolution:** the COE tick pops from P0 → P1 → P2 within
each class, subject to reservation floors. Once a P0 lane is drained,
lower lanes see slot availability. **A class' reservation is always
served from the highest-priority lane first.**

**No overtaking across classes:** BACKTEST P0 does NOT starve
EXECUTION P0. Reservations guarantee this — each class keeps its
minimum concurrency regardless of P0 depth elsewhere.

**Backing store — three phases (§3):**

- **Phase COE.α** — in-memory `dict[WorkloadClass, list[deque[P0], deque[P1], deque[P2]]]` protected by `RLock`, identical semantics to `queue_pressure._depth` today.
- **Phase COE.β** — Mongo-mirrored (`workload_queue` collection) so restarts don't drop enqueued P0 jobs. Reads stay in-memory.
- **Phase COE.γ** — pluggable backend (Redis Streams / RabbitMQ) for multi-node. The `WorkloadQueue` interface stays; only the driver swaps.

### 1.4 Worker classification & pool topology

Today there is exactly one shared pool (`cpu_pool.ProcessPoolExecutor`),
default 4 workers, dormant. Every other execution path is `asyncio.to_thread`
inside the FastAPI event loop.

**Target:** three worker categories, each with its own scheduling
discipline, matching the classes they serve:

```
                                ┌──────────────────────────────┐
                                │  Class → Worker mapping      │
                                └──────────────────────────────┘

┌───────────────────────────┐  ┌───────────────────────────┐  ┌──────────────────────────────┐
│  Async workers            │  │  CPU workers              │  │  I/O workers                 │
│  (event loop tasks)       │  │  (ProcessPoolExecutor)    │  │  (asyncio.to_thread          │
│                           │  │                           │  │   + connection pools)         │
│  Classes:                 │  │  Classes:                 │  │  Classes:                    │
│    API_HOT                │  │    BACKTEST               │  │    MARKET_DATA               │
│    AGENT                  │  │    MUTATION               │  │    KNOWLEDGE                 │
│    EXECUTION              │  │    FACTORY_CYCLE (fanout) │  │    MONITORING                │
│    META_LEARNING          │  │                           │  │                              │
│                           │  │  Cardinality:             │  │  Cardinality:                │
│  Cardinality:             │  │    = adaptive_pool_sizer  │  │    = 2× (unlimited soft cap) │
│    unlimited (soft caps   │  │      output (2/4/8/16)    │  │                              │
│      via reservation)     │  │                           │  │  Isolation:                  │
│                           │  │  Isolation:               │  │    thread-per-task; DB /     │
│  Isolation:               │  │    OS-process; segfault   │  │    HTTP timeouts enforced    │
│    coroutine cancellation │  │    of one worker ≠ pool   │  │                              │
│    on timeout             │  │    death (see §1.7)       │  │                              │
└───────────────────────────┘  └───────────────────────────┘  └──────────────────────────────┘
```

**Existing `cpu_pool` becomes the CPU worker.** No name changes; we
promote the flag `USE_PROCESS_POOL=true` to the default in Phase COE.β
once the pool is proven under load. `backtest_pool` and `mutation_pool`
adoption wrappers stay — their double-gate (`USE_PROCESS_POOL` AND
`ENABLE_PROCESS_POOL_*`) is the migration control.

**I/O workers get their own bounded thread pool** so a burst of BI5
top-ups can't starve the ProcessPoolExecutor:

```python
# New: engines/io_pool.py — mirror of cpu_pool.py
io_pool = ThreadPoolExecutor(max_workers=_resolve_io_pool_size())
```

Sized to `min(32, 4 × effective_cpu_count)`; feature-gated
(`USE_IO_POOL=true`, default off — falls through to `asyncio.to_thread`).

### 1.5 Priority scheduling & fairness

The current scorer is:

```python
score = priority_base × business_value
       × pressure                    # freshness multiplier
       × dep_readiness               # 0..1 dependency satisfaction
       × budget_headroom             # 1.0 if affordable, 0 otherwise
       / resource_cost_factor        # cpu_pressure + mem_pressure
```

**Keep it verbatim; extend it with:**

1. **Lane weight.** `lane_multiplier = {P0: 4.0, P1: 1.0, P2: 0.25}`. Tie-break by lane before FIFO within-lane.
2. **Provider readiness.** If `task.AI_PROVIDER_REQUIRED` and the router reports **all** providers `open` (breaker), drop the score to `0` this tick — deferred, not refused. Journaled as `provider_unavailable`.
3. **Age boost.** For jobs waiting `> class.max_defer_age` (default P0=5s, P1=30s, P2=300s), multiply score by `1 + (age_s / max_defer_age)` to prevent P2 starvation.

The score remains **deterministic and inspectable** — the `/api/orchestrator/decisions` endpoint shows the derivation for every candidate.

**Fairness invariant:** within a class, jobs in the same lane are
served FIFO (age-boost overrides only across ticks). Across classes,
reservations guarantee every class dispatches at least
`reservation_slots` per second when the queue is non-empty.

### 1.6 Dynamic resource allocation

`adaptive_concurrency.recommend(caps, probe, pressure)` already
returns per-class caps. Extend with:

1. **Reservation floors.** New field `ConcurrencyReservations` returned
   alongside `ConcurrencyTargets`. Reservation floors do **not**
   over-ride the `critical` band refuse rule — they cannot force work
   through a hot host.
2. **Elastic band.** Between `ok` and `warn`, dynamically re-balance:
   if BACKTEST queue depth > 3× MUTATION depth, transfer 1 slot from
   MUTATION → BACKTEST (subject to reservation floors). Pure fn over
   the queue snapshot.
3. **Provider concurrency budget.** Add a per-provider concurrency cap
   in `BudgetTracker` (in-flight LLM calls per provider, mirroring the
   RPM window). Consumed by the AGENT class admission and by any BACKTEST
   that requires generation.
4. **Cost-aware admission.** Refuse BACKTEST when
   `budget.can_afford_global(est_cost) == False` even if capacity
   allows. Today this is checked in `orchestrator/core._score_task` but
   only if `AI_PROVIDER_REQUIRED=True`; extend to all cost-bearing
   classes.

### 1.7 Parallel execution & fault isolation

Three isolation levels, ordered by cost:

| Level | Boundary | Protects against | Applicable classes |
|---|---|---|---|
| **L1 — Coroutine cancellation** | `asyncio.wait_for(coro, timeout)` inside `admission_gate` | Runaway async loops, hung awaits | API_HOT, AGENT, EXECUTION, META_LEARNING |
| **L2 — Thread + join timeout** | `asyncio.to_thread` + `future.cancel()` on timeout | Blocking I/O, sync-only libraries | MARKET_DATA, KNOWLEDGE, MONITORING |
| **L3 — OS process** | `ProcessPoolExecutor` with per-worker restart on failure | Segfault, OOM, C-extension crash, infinite eval loop | BACKTEST, MUTATION, FACTORY_CYCLE fanout |

**Per-worker crash policy** (new):

```python
# engines/cpu_pool.py — extend ProcessPoolExecutor lifecycle
if worker_died:                          # PID exit without result
    _pool_stats["crash_count"] += 1
    _pool_stats["last_crash_at"] = now
    if _pool_stats["crash_count"] > POOL_CRASH_THRESHOLD:  # default 5/min
        emit(EVENT_POOL_UNHEALTHY, {...})   # scaling_events
        # Automatically recycle: shutdown(wait=False) → _executor = None
        # Next submit_cpu re-creates a fresh pool
```

Python 3.11+ `ProcessPoolExecutor` already isolates worker crashes
from the caller (raises `BrokenProcessPool`). We add the **auto-recycle
and crash-budget** discipline on top.

**Per-task SLA / hard timeout** (new): every `Task` protocol member
gains `HARD_TIMEOUT_S: float`. The dispatcher wraps `task.run(ctx)` in
`asyncio.wait_for(..., timeout=HARD_TIMEOUT_S)`. On timeout: task
recorded as failed, worker process (if any) killed, crash-budget
tick incremented.

**Sane defaults per class:**

| Class | HARD_TIMEOUT_S |
|---|---|
| API_HOT | 30 |
| BACKTEST | 180 |
| MUTATION | 300 |
| FACTORY_CYCLE | 420 |
| AGENT | 120 |
| MARKET_DATA | 180 |
| KNOWLEDGE | 600 |
| EXECUTION | 30 |
| MONITORING | 60 |
| META_LEARNING | 1800 |

### 1.8 Backpressure handling

Today's admission gate produces `admit | defer:30s | refuse`; the
caller sees these as raised `AdmissionDeferred` / `AdmissionRefused`.
That's the primitive — extend it with:

1. **Producer-visible pressure signal.** Every API endpoint that
   submits work receives the current class' `pressure_band` in
   response headers (`X-COE-Pressure: normal | high | critical`) and
   optionally in the response body when the client asks. Frontend
   can throttle before hitting the gate.
2. **Retry-After propagation.** Existing `retry_after_sec` on
   `AdmissionVerdict` propagates to HTTP `Retry-After: N` headers on
   `429 / 503` responses at the API layer.
3. **Client credits (future).** A pluggable "leaky bucket per API
   key / per user" between the API layer and the queue. Not needed
   for single-tenant COE.β; reserved slot in the interface.
4. **Shed-load bands.**
    - `pressure_band = idle`  → admit everything.
    - `pressure_band = normal` → admit all except lane P2 with score < 5.
    - `pressure_band = high` → admit only P0 + reservations.
    - `pressure_band = critical` → admit reservations only; defer P0, refuse P1 + P2.
5. **Queue depth alarm.** When class depth > `class.max_lane_depth`
   (default 100) at any lane, emit `EVENT_QUEUE_OVERFLOW`; the API
   layer can flip to reject-mode for that class for `cooldown_s`.

### 1.9 Failure isolation & recovery

**Layered retry policy** (new — replaces "counter increment only"):

```
┌─── retry policy per class (env-tunable) ────────────────────────┐
│                                                                 │
│  transient      → retry with exponential backoff                │
│                   (network, DB timeout, provider 5xx)           │
│  persistent     → move to dead-letter after N attempts          │
│                   (schema error, missing dependency)            │
│  crash          → dead-letter immediately, emit alert            │
│                   (worker died, HARD_TIMEOUT)                   │
│                                                                 │
│  Class defaults (env override via ORCH_RETRY_<CLASS>_*):        │
│    API_HOT       — no retry (users retry themselves)             │
│    BACKTEST      — 2 attempts, backoff 1s→4s                    │
│    MUTATION      — 3 attempts, backoff 2s→8s→30s                │
│    FACTORY_CYCLE — 1 attempt                                    │
│    AGENT         — 2 attempts (VIE reroutes provider)           │
│    MARKET_DATA   — 5 attempts, backoff 5s→60s (BI5 idempotent)  │
│    KNOWLEDGE     — 3 attempts                                   │
│    EXECUTION     — 0 attempts (broker-idempotency required)     │
│    MONITORING    — 3 attempts, silent                           │
│    META_LEARNING — 1 attempt (heavy; operator inspects failures)│
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Dead-letter store** — new Mongo collection `workload_dead_letter`
with `job_envelope, attempt_count, first_failed_at, last_failed_at,
class_reason_history, resolved`. Read-only diagnostic endpoint
`/api/coe/dead-letter` for operators; requeue via
`POST /api/coe/dead-letter/{id}/requeue`.

**Failure blast radius:** every failure is scoped to a single job
envelope. A crash in the CPU worker does not affect the AGENT class,
whose work runs on the event loop. A hung MARKET_DATA thread does
not block a BACKTEST process. This is a direct consequence of the
per-class worker mapping in §1.4.

### 1.10 Horizontal scalability & future distributed execution

The design must not paint us into a single-node corner. The COE
architecture is single-node in phases α/β but the **contracts stay
distribution-ready**:

| Contract | α / β today | γ (multi-node) |
|---|---|---|
| `WorkloadRequest` | Python dataclass in-memory | Serialisable JSON, Mongo-persisted, worker-agnostic |
| `WorkloadQueue.submit / next` | `dict + deque + RLock` | Redis Streams / RabbitMQ / SQS driver behind the same interface |
| `queue_pressure` | in-process counters | mirrored via Redis atomic increments; snapshot aggregates all nodes |
| `budget_tracker` | in-process | Mongo-backed (see §2.2) so all nodes see the same daily USD spend |
| `host_capability` | one row per boot | one row per node; the COE tick aggregates the *cluster* recommendation |
| `admission_gate` | reads local snapshot | reads a shared snapshot (Redis pub/sub of node reports); local decision on the local pool |
| `feature_flags` | env + Mongo | same — no change needed |
| Task adapters | `@registry.register` at import | unchanged; each node imports the same registry, and jobs carry `class` — any node with capacity for that class can execute |

**Placement policy** (γ): a lightweight "coordinator" role — one node
elected via Redis lock — decides which node dequeues each job.
Everything else remains local. This mirrors HashiCorp Nomad's
"scheduler + client" split.

**Node self-registration** (γ): each node writes its
`host_capability` row on boot; the coordinator reads all rows and
maintains a cluster capacity view. Same `HostCapability` dataclass,
now with `is_leader: bool`.

None of these β→γ changes affect the α/β contract. That's the point.

---

## 2. Cross-cutting concerns

### 2.1 Observability & tracing

Today's `/api/orchestrator/decisions`, `/api/scaling/*`,
`/api/learning/metrics`, `/api/latent/*` provide rich in-memory
inspection. The **next step** is exportable telemetry:

1. **Prometheus text endpoint** at `/api/coe/metrics` — one canonical
   exporter aggregating counters from `orchestrator`, `queue_pressure`,
   `budget_tracker`, `cpu_pool`, `admission_controller`. Zero external
   dependencies (`prometheus_client` is single-file).
2. **OpenTelemetry hooks (optional)** — span-per-`Task.run()`,
   attributes: `task_name, workload_class, lane, score,
   duration_ms, ok, provider (if any), retries, dead_letter (if any)`.
   OTLP export is the only new dep; guarded by `OTEL_ENABLED=false`.
3. **Structured `scaling_events`** already exist; keep them as
   the immutable audit trail. Add `EVENT_QUEUE_OVERFLOW`,
   `EVENT_POOL_UNHEALTHY`, `EVENT_RESERVATION_STARVED`,
   `EVENT_DEAD_LETTER_INSERTED`.
4. **Per-class runtime dashboard** — no new backend needed;
   existing `/api/orchestrator/state` + `/api/scaling/pressure`
   + `/api/learning/continuous/state` cover most of it. Add
   `/api/coe/state` as the aggregating meta-endpoint.

### 2.2 Persistence for restart survival

Every counter currently in-memory should have an optional Mongo
mirror, flag-gated:

| Counter | Collection | Behaviour |
|---|---|---|
| `queue_pressure._depth` (per class in-flight) | ephemeral (not persisted) | Rebuilds on boot from `workload_queue` in-flight rows. |
| `queue_pressure._window` (rolling samples) | `queue_pressure_samples` (capped, TTL 24h) | Persisted so post-restart dashboards have history. |
| `budget_tracker._daily_*` + `_monthly_*` | `budget_state` (one row per (provider, day)) | **Critical** — prevents restart-doubles daily USD. |
| `WorkloadQueue.enqueue` | `workload_queue` (one row per unfinished job) | P0 recovery on boot; P1/P2 discarded (they'll be re-scheduled by their driver). |
| `scaling_events` | `scaling_events` already persisted | Keep as-is. |

All writes are best-effort — Mongo failure logs a warning and the
in-memory path continues. Reads are startup-only (warm cache).

### 2.3 Governance & operator control

Existing env variables (`ORCH_TASK_*`, `USE_PROCESS_POOL`,
`ENABLE_ADMISSION_CONTROL`, `LEARNING_CONTINUOUS_*`,
`ORCHESTRATOR_ENABLED`, `WORKLOAD_PROFILE`, `CPU_POOL_SIZE`) stay.
New ones:

| Variable | Default | Purpose |
|---|---|---|
| `COE_ENABLED` | `false` | Master flag for Phase COE.α — when off, all new subsystems are dormant. |
| `COE_LANES_ENABLED` | `false` | Turn on P0/P1/P2 lane semantics (Phase COE.α). |
| `COE_RESERVATIONS_ENABLED` | `false` | Enforce per-class reservation floors. |
| `COE_RETRY_ENABLED` | `false` | Wire retry policy at the dispatcher. |
| `COE_DEAD_LETTER_ENABLED` | `false` | Enable dead-letter collection writes. |
| `ORCH_RESERVATION_<CLASS>` | table | Operator override for reservation floors. |
| `ORCH_HARD_TIMEOUT_<CLASS>` | table | Operator override for per-class timeout. |
| `ORCH_RETRY_<CLASS>_ATTEMPTS` | table | Retry attempts. |
| `ORCH_RETRY_<CLASS>_BACKOFF_MS` | `500,2000,10000` | Backoff schedule. |
| `USE_IO_POOL` | `false` | Enable dedicated I/O thread pool. |
| `USE_PROCESS_POOL_DEFAULT_ON` | `false` | Flip Phase COE.β — enable CPU pool by default. |
| `COE_METRICS_ENABLED` | `false` | Expose `/api/coe/metrics` for Prometheus. |
| `OTEL_ENABLED` | `false` | Turn on OpenTelemetry span export. |

Everything above is orthogonal — any subset can be enabled
independently. Rollback = flip flag off.

---

## 3. Evolutionary migration plan

The upgrade rides on the existing feature-flag + subordination
discipline. Phases are ordered so **every phase is production-ready
in isolation** and can be paused indefinitely.

### Phase COE.α — Foundations (2-3 weeks, no visible behaviour change)

1. **Extend `WorkloadClass` enum** with 5 new classes; add `_PROFILE_DEFAULTS` rows. Backwards compatible — 17 existing task adapters keep their assignments.
2. **Introduce `WorkloadRequest` dataclass** in `engines.orchestrator.types`. Not yet used by any wrap site; new API for future submitters.
3. **Introduce `WorkloadQueue`** (in-memory) — protected by `RLock`, 3 lanes × N classes, `RESERVATIONS_ENABLED` flag off. When off, `WorkloadQueue.submit()` immediately falls through to today's `orchestrator.dispatch_task()`.
4. **Add reservation field to `ConcurrencyTargets`** — pure fn extension, existing callers ignore the new field.
5. **Add HARD_TIMEOUT_S to Task Protocol** — default 300s. Update the 17 task adapters with class-appropriate values.
6. **Wire `asyncio.wait_for` around `task.run(ctx)`** in `orchestrator/core.py._dispatch` — this closes the "hung task holds a slot forever" gap without any queue changes.
7. **Add per-worker crash budget** in `cpu_pool.py` with auto-recycle on threshold trip.
8. **Introduce `budget_state` Mongo persistence** — writes at every `record()`, reads at boot. Feature-gated `BUDGET_PERSIST=true`.

**Ship criteria:** all existing tests pass unchanged. Flags default off. `/api/orchestrator/state` shows new fields with sensible defaults. Zero behaviour change with flags off.

### Phase COE.β — Lanes + reservations + I/O pool (3-4 weeks)

1. **Turn on `WorkloadQueue` in-memory** (`COE_LANES_ENABLED=true`). API endpoints that used to call engines directly gain a lane assignment: user-triggered → P0, scheduled → P1, factory-triggered → P2. This is a **backwards-compatible shim** — the engine is still called; the queue is a pass-through until the dispatcher is switched.
2. **Switch dispatcher to consume from `WorkloadQueue.next()`** in the Orchestrator tick. The pure-function scorer runs on **queued** candidates (not the entire registry), then dispatches from lane P0 → P1 → P2 with reservation enforcement.
3. **Enable reservations** (`COE_RESERVATIONS_ENABLED=true`). Every class dispatches at least `reservation` jobs per tick when its queue is non-empty.
4. **Land `io_pool.py`** and route MARKET_DATA, KNOWLEDGE, MONITORING through it.
5. **Land Prometheus exporter** at `/api/coe/metrics`.
6. **Land `X-COE-Pressure` response header** and `Retry-After` propagation.

**Ship criteria:** operator toggles the flag; latency histograms show P0 requests never wait behind P2. Regression suite: no existing endpoint behaviour changes with lanes off.

### Phase COE.γ — Retry policy, dead-letter, provider-aware admission (2-3 weeks)

1. **Land retry executor** — wraps `task.run(ctx)` with per-class backoff schedule + attempt counter (fields already in `WorkloadRequest`).
2. **Land dead-letter collection** + read/requeue API.
3. **Provider-aware admission gate** — consult `ai_workforce.circuit_breaker` for the target provider before admitting AGENT / BACKTEST-requiring-LLM.
4. **Age-boost score adjustment** to prevent P2 starvation.
5. **Elastic band redistribution** between BACKTEST ↔ MUTATION.
6. **OpenTelemetry span export** (optional; `OTEL_ENABLED=false` default).

**Ship criteria:** operator can inject a controlled failure (kill LLM provider) and watch: (a) provider circuit opens, (b) new BACKTEST jobs defer with `provider_unavailable`, (c) VIE reroutes, (d) provider closes, (e) queue drains.

### Phase COE.δ — Multi-node substrate (future, optional)

1. **Swap `WorkloadQueue` driver** to Redis Streams / RabbitMQ / SQS behind the same interface.
2. **Mongo-persisted `queue_pressure` snapshot** aggregated cluster-wide.
3. **Coordinator election** via Redis lock.
4. **Per-node `host_capability` rows**, cluster capacity view.
5. **Job placement policy** — the coordinator selects the least-loaded eligible node.

**Ship criteria:** two VPS boxes join the same cluster; a submitted P0 backtest can execute on either. Rollback = point at the local driver again.

---

## 4. Contracts (canonical API surface)

### 4.1 `WorkloadRequest` — the unified job envelope

```python
@dataclass
class WorkloadRequest:
    # Identity
    job_id:              str                       # uuid; assigned on submit
    class_:              WorkloadClass
    lane:                Literal["P0", "P1", "P2"] = "P1"
    task_name:           str                        # matches registry key
    # Origin
    submitted_by:        str                        # api|scheduler|orchestrator|<user_id>
    submitted_at:        str                        # iso
    parent_job_id:       Optional[str] = None        # for correlated work
    correlation_id:      Optional[str] = None        # research_run_id, learning_run_id
    # Payload — free-form dict, MUST be JSON-serialisable
    payload:             Dict[str, Any] = field(default_factory=dict)
    # Execution hints
    est_cost_usd:        float = 0.0
    est_cpu_cores:       float = 0.5
    est_ram_mb:          int = 256
    est_duration_s:      float = 30.0
    hard_timeout_s:      Optional[float] = None      # overrides class default
    # Retry state
    attempt:             int = 0
    max_attempts:        int = 1                    # class default when 0
    last_error:          Optional[str] = None
    last_failed_at:      Optional[str] = None
    # Governance
    idempotency_key:     Optional[str] = None       # de-dup guard
    provider_hint:       Optional[str] = None       # for AGENT/BACKTEST-LLM
```

### 4.2 `WorkloadQueue` — the unified dispatch surface

```python
class WorkloadQueue(Protocol):
    async def submit(self, req: WorkloadRequest) -> str: ...
    async def next(self, cls: WorkloadClass, cap: int) -> Optional[WorkloadRequest]: ...
    async def cancel(self, job_id: str) -> bool: ...
    async def peek(self, cls: WorkloadClass) -> Dict[str, int]: ...  # {lane:depth}
    async def snapshot(self) -> Dict[str, Any]: ...
```

Backends: `InMemoryQueue` (α/β), `MongoMirroredQueue` (β), `RedisQueue` (γ).

### 4.3 `Task` Protocol — extended (backwards compatible)

```python
# Add ONE optional field to the existing Protocol
HARD_TIMEOUT_S: float = 300.0    # NEW — was implicit inside engines
RETRY_POLICY:   Literal["default", "aggressive", "none"] = "default"  # NEW
```

Everything else in `types.Task` stays. Existing 17 adapters get a
one-line addition per class in a mechanical edit.

### 4.4 `admission_gate` — extended verdict

The verdict dataclass gains **two** optional fields, keeping the
existing `admit | defer | refuse` decision unchanged:

```python
@dataclass
class AdmissionVerdict:
    # ... existing fields unchanged
    reservation_hit:   bool = False       # NEW — served by reservation floor
    provider_state:    Optional[str] = None   # NEW — closed|half_open|open|null
```

### 4.5 `/api/coe/*` endpoints (new)

| Endpoint | Purpose |
|---|---|
| `GET  /api/coe/state` | Aggregate: queue depths per class × lane, in-flight, reservations, pressure band, budget |
| `GET  /api/coe/metrics` | Prometheus text exposition |
| `POST /api/coe/jobs` | Submit a `WorkloadRequest`; returns `job_id` |
| `GET  /api/coe/jobs/{job_id}` | Envelope + status (queued/running/done/dead-lettered) |
| `POST /api/coe/jobs/{job_id}/cancel` | Cancel a queued job (running jobs cannot be preempted in β) |
| `GET  /api/coe/dead-letter` | List failed envelopes |
| `POST /api/coe/dead-letter/{job_id}/requeue` | Move back to lane P1 |
| `GET  /api/coe/reservations` | Current reservation floors + operator overrides |
| `POST /api/coe/reservations/{class}` | Set reservation floor (superuser only) |

All under the existing `Depends(get_current_user)` auth pattern.

---

## 5. Open questions (for the consolidated review)

1. **Do we persist `queue_pressure` samples to Mongo?** Cost: ~10 KB/hour/host. Benefit: post-restart dashboards. Recommend YES.
2. **Do we allow `preemption` of running jobs?** Adds complexity (task-side cancellation contract). Recommend NO for β; revisit in γ once multi-node exposes idempotency requirements.
3. **Should `AGENT` and `META_LEARNING` share the same LLM concurrency budget?** They can compete for the same providers. Recommend a **single provider-scoped budget** cutting across classes (already the case in `BudgetTracker`), plus **separate class caps** for CPU/mem — which is exactly today's design.
4. **Do we need a per-tenant fairness layer?** Not for single-tenant Strategy Factory. Reserve the hook (`WorkloadRequest.tenant_id`) but leave the layer dormant.
5. **What is the acceptable P0 tail latency?** Recommend `p95 < 200 ms admission latency` and `p99 < 1 s dispatch latency` as SLA targets. Measured via `/api/coe/metrics`.
6. **Do we run the orchestrator tick faster than 1 s?** Today `ORCH_TICK_MS=1000`. With lanes + reservations, P0 responsiveness benefits from `250 ms` — but the score computation cost grows linearly. Recommend `tick_ms=1000` default, `500 ms` under `COE_TICK_FAST=true` for interactive-heavy deployments.

---

## 6. Non-goals for Phase 2 (explicitly excluded)

- **A new scheduler.** APScheduler + AsyncIO cohabitation stays. No cron replacement.
- **Container/Kubernetes migration.** COE.γ is Redis/RabbitMQ, not k8s.
- **Rewriting `backtest_engine`.** The stage-decomposition observation in B6 is *diagnostic*; the engine itself is stable and out of scope for orchestration.
- **New provider integrations.** Handled by Phase 2A (VIE).
- **New knowledge sources.** Handled by Phase 2C (UKIE).
- **Live-trading execution logic.** Handled by the existing execution engine; COE just gives it a class + reservations.

---

## 7. Verdict

The Strategy Factory's compute substrate is **unusually mature** for
a pre-Phase-2 codebase. Five layered pure-function libraries, an
async orchestrator with 17 registered tasks, a budget tracker with
provider selection, and a subordination protocol between three
schedulers exist and work. The gaps are **evolutionary, not
structural**:

1. Extend the 5-class taxonomy to 10.
2. Add three priority lanes (P0/P1/P2) and reservation floors.
3. Add a canonical `WorkloadRequest` envelope + `WorkloadQueue`
   primitive on top of the existing counters.
4. Give the CPU pool a crash budget; the I/O work its own thread pool.
5. Wire retry + dead-letter + provider-aware admission.
6. Persist budget + rolling samples so restarts don't lose accounting.
7. Keep the multi-node door open — nothing in α/β/γ prevents it.

No layer of the existing system needs to be discarded. Every new
capability is a flag away from being dormant. The invariants
(honest refusal, additive extension, pure-function core, operator
authority) hold through every migration step.

---

*Reviewed against:* `orchestrator/core.py`, `admission_controller.py`,
`admission_wrapper.py`, `queue_pressure.py`, `workload_classes.py`,
`cpu_pool.py`, `backtest_pool.py`, `mutation_pool.py`,
`adaptive_concurrency.py`, `adaptive_pool_sizer.py`,
`host_capability.py`, `compute_probe.py`, `auto_scheduler.py`,
`orchestrator_scheduler.py`, `learning/supervisor.py`,
`learning/continuous_scheduler.py`, `orchestrator/budget_tracker.py`,
`orchestrator/registry.py`, `orchestrator/types.py`,
`orchestrator/tasks/*` (17 adapters), `ai_workforce/*`,
`feature_flags.py`, `scaling_events.py`, `research_lineage.py`,
`app/main.py` (lifespan bootstrap).

*Status:* **Architecture review only. No code changes proposed for immediate implementation. Approval required before Phase 2 implementation begins.**
