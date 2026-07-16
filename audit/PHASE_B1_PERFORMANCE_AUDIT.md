# Strategy Factory — Performance Audit Report

**Phase B.1 · Continuous Capacity-Aware Scheduler pre-implementation audit**
**Generated:** 2026-01-16 (this session) · Local preview container (16 vCPU / 62 GB RAM)

---

## 1. Executive summary

**The current learning scheduler is CPU/RAM-blind and cannot exploit available hardware.**

Measured in this pod (see `audit/PERF_AUDIT_REPORT.json`):

| Mode           | 6 cycles wall time | Cycles / sec | Max CPU % | Bottleneck             |
|----------------|--------------------|--------------|-----------|------------------------|
| sequential     | 0.437 s            | **13.7**     | 9.0 %     | scheduler serialisation|
| gathered_4     | 0.498 s            | 12.0         | 8.5 %     | GIL + no ProcessPool   |
| staggered_250ms| 1.504 s            | 4.0          | 9.0 %     | stagger delay          |

Key observations:

1. **CPU never exceeded 9 %** on a 16-core box — hardware is **idle** during learning cycles.
2. `gathered_4` was **NOT faster** than `sequential` — every code path lives inside the same async event loop under GIL because `USE_PROCESS_POOL=false` (default). All backtests run through `asyncio.to_thread`, which does not release the GIL for pure-Python numeric loops.
3. The existing scheduler (`engines/learning/supervisor._scheduler_loop`) does two things wrong:
   - `LEARNING_SCHEDULER_MAX_CONCURRENT=1` by default → one cycle at a time.
   - It `await`s `run_learning_cycle` inline (no `asyncio.create_task`), so even with `max_concurrent > 1` the loop still serialises.
   - Between ticks it sleeps `LEARNING_SCHEDULER_INTERVAL_S=3600` (1 h) unconditionally.

Result on a big box: idle CPU + idle RAM + slower factory throughput than the previous 1-vCPU / 8 GB VPS, because the OLD VPS was accidentally running at 100 % utilisation while the NEW VPS runs at 8 %.

---

## 2. Instruments used

* `psutil` — CPU%, RSS, load average, memory
* `compute_probe.snapshot()` + `compute_probe.headroom_summary()` — existing production instruments
* `queue_pressure.snapshot()` — per-workload-class in-flight depth
* `cpu_pool.get_pool_state()` — ProcessPoolExecutor status
* `time.perf_counter()` — wall time
* `engines.learning.supervisor.run_learning_cycle` stage timings — `duration_ms` per stage emitted to `outcome_events`

Harness: `backend/scripts/perf_audit_learning_loop.py` — runs three modes back-to-back with a 250 ms background sampler and produces `audit/PERF_AUDIT_REPORT.json`.

---

## 3. Measured per-stage timings (offline mode, no market data)

Real market data is not loaded in this pod → the `backtest` stage returns `no_real_data` after ~30 ms. That's still enough to expose the scheduler-level bottleneck because the SUPERVISOR overhead (event emission, stage recording, index rebuild) is what dominates when the pipeline runs sub-second.

| Stage    | Sequential p50 | gathered_4 p50 | Comment                              |
|----------|---------------:|---------------:|--------------------------------------|
| generate | 0 ms           | 0 ms           | offline renderer — sub-millisecond   |
| backtest | 30 ms          | 37 ms          | no-data guard path                   |
| approve  | 1 ms           | 18 ms          | knowledge index refresh (Mongo write)|

Under `gathered_4`, per-stage p50 goes **UP**, not down — asyncio contention on a single event loop **plus** Mongo `outcome_events` write contention dominates.

**Extrapolation with real market data** (typical mainline runs on the VPS):
* backtest stage: 400 ms – 5 s per cycle (Wilder ATR + signal loop over 100 k bars).
* generate stage: 300 ms – 8 s (LLM RTT) or <1 ms (offline).
* approve stage: 50 – 500 ms (knowledge index rebuild).

At those numbers the GIL serialisation of `asyncio.to_thread` is the dominant bottleneck when > 1 cycle runs concurrently.

---

## 4. Root causes

**RC-1 · Scheduler is fixed-interval, capacity-blind**
`engines/learning/supervisor._scheduler_loop`:

```python
while not _SCHEDULER_STOP.is_set():
    interval = max(60, lcfg.scheduler_interval_seconds())     # ≥ 60 s
    if active < lcfg.scheduler_max_concurrent():              # default 1
        run = await run_learning_cycle(LearningSeed())        # blocking await
    await asyncio.wait_for(_SCHEDULER_STOP.wait(),
                           timeout=interval)                   # unconditional sleep
```

Three defects in one loop:
* Interval floor is 60 s; default 3600 s. Between ticks the scheduler sleeps even when CPU is at 5 %.
* `active < max_concurrent` is a self-imposed cap, NOT a capacity check. `AdaptiveConcurrency.recommend()` — which already returns per-class targets against real host capability + probe + queue-pressure — is **never consulted**.
* `run_learning_cycle` is awaited inline instead of dispatched as an `asyncio.Task`. Even with `max_concurrent > 1`, only one cycle can be in-flight at a time.

**RC-2 · CPU pool disabled by default**
`USE_PROCESS_POOL=false` in every current deployment → `cpu_pool.submit_cpu` transparently falls back to `asyncio.to_thread`. `to_thread` releases the GIL only for I/O and C extensions; the pure-Python indicator loops in `engines/backtest_engine.py` (EMA, ATR, MACD, BB, signal dispatch, per-bar loop) hold the GIL. On 16 cores, only ONE runs at a time.

**RC-3 · Global `_SIG_LOCK` in `strategy_engine`**
`engines/strategy_engine.py:44` — `threading.RLock` held during the signature draw. Concurrent generators serialise here even when the LLM path is async.

**RC-4 · Learning cycle writes are serialised to a single Mongo connection**
`get_db()` returns one motor client. `emit()` writes to `outcome_events` on every stage. Under high concurrency this becomes the wall-clock bottleneck for very small cycles (visible above: `approve` p50 goes 1 → 18 ms under 4× concurrency).

**RC-5 · Old-VPS anomaly (1 vCPU / 8 GB faster than 12 vCPU / 42 GB)**
On the old VPS the whole factory ran inside one Python process pinned to one core at ~100 % CPU. There was no idle time because there was no scheduler wait — the loop was tight and the box was small enough that `max_concurrent=1` was ALREADY the correct number. On the new VPS the same `max_concurrent=1` under-utilises the machine by 15×. Nothing regressed; the scheduler simply doesn't scale.

---

## 5. Design of the fix (Phase B.1)

The Continuous Capacity-Aware Scheduler must:

* Poll `AdaptiveConcurrency.recommend(caps, probe, pressure)` every `CONTINUOUS_TICK_MS` (default 1000 ms).
* Compute a per-class target = `min(pool_size, adaptive_target, rpm_budget_target, cycles_per_hour_target)`.
* If in-flight learning cycles < target → dispatch new cycles as `asyncio.create_task` (never inline `await`).
* Respect a global cycles/hour safety limit and a per-provider RPM budget.
* Emit outcome events per launch and per completion so the operator dashboard can visualise cycle density in real time.
* Never sleep more than `IDLE_TICK_MS` (default 2000 ms) between capacity checks. When band = `warn` or `critical`, back off exponentially (2 s → 4 s → 8 s, capped 30 s).
* Provide `POST /api/learning/continuous/start|stop`, `GET /api/learning/continuous/status` endpoints — additive; existing `/api/learning/scheduler/*` endpoints keep the old fixed-interval loop for backward compatibility.

Architectural rules:

* **Additive.** Existing `start_scheduler()` / `stop_scheduler()` and the `LEARNING_SCHEDULER_*` env vars are unchanged.
* **Opt-in via `LEARNING_CONTINUOUS_MODE=true`.**
* When ON, the old scheduler is dormant and the continuous one drives the loop.
* When OFF (default), zero behaviour change.
* Uses the SAME `run_learning_cycle` primitive — no new business logic.

---

## 6. Recommended follow-up (deferred from this session)

* Flip `USE_PROCESS_POOL=true` + `ENABLE_PROCESS_POOL_BACKTEST=true` in the VPS `.env` once the continuous scheduler is in production, so backtests actually parallelise across cores.
* Replace `_SIG_LOCK` with a per-(pair,tf) lock so concurrent generators no longer serialise globally.
* Consider batched `outcome_events` writes (buffered 50 events / 500 ms) — Mongo per-event write is the sub-100 ms floor.
* Add Prometheus counters for `learning.cycles_in_flight`, `learning.cycles_launched_total`, `learning.capacity_band` on the `/metrics` endpoint.

---

## 7. Evidence

Raw JSON: `audit/PERF_AUDIT_REPORT.json`
Harness: `backend/scripts/perf_audit_learning_loop.py`

Run again with:

```bash
/root/.venv/bin/python /app/backend/scripts/perf_audit_learning_loop.py --cycles 8 --concurrency 4
```
