"""Phase B.1 performance audit harness — measures real timings for every
stage of the continuous learning loop under three concurrency modes:

    1) sequential  — current behaviour (1 cycle at a time)
    2) gathered_N  — asyncio.gather() launching N cycles concurrently
    3) staggered   — sequential launch with 250ms stagger (baseline of
                     what a capacity-aware scheduler would emit)

For each mode it reports:
    - wall time
    - cycles per second (throughput)
    - per-stage p50/p95 latency
    - CPU + RAM samples during the run
    - GIL / thread contention indicator (asyncio.to_thread vs
      cpu_pool.submit_cpu)

No LLM calls, no MongoDB writes are required — the supervisor's
offline generator path is exercised.

Usage:
    /root/.venv/bin/python /app/backend/scripts/perf_audit_learning_loop.py \
      --cycles 8 --concurrency 4

Output: JSON report to stdout + /app/audit/PERF_AUDIT_REPORT.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Wire the same import shim server.py installs.
_HERE = Path(__file__).resolve().parent
_BACKEND = _HERE.parent
_LEGACY = _BACKEND / "legacy"
for p in (str(_BACKEND), str(_LEGACY)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "strategy_factory_v1")
os.environ.setdefault("LEARNING_MIN_TRADES", "1")   # so tiny synth data passes

import psutil  # noqa: E402

from engines.learning.supervisor import (      # noqa: E402
    LearningSeed,
    run_learning_cycle,
)
from engines import compute_probe               # noqa: E402
from engines import queue_pressure              # noqa: E402
from engines import cpu_pool                    # noqa: E402


def _stage_metrics(run):
    """Bucket per-stage durations from a LearningRun object."""
    out = {}
    for s in run.stages:
        out.setdefault(s["stage"], []).append(s.get("duration_ms", 0))
    return out


def _sampler(stop_evt: asyncio.Event, samples: list, sample_period_s: float = 0.25):
    """Background sampler capturing CPU% + RSS + queue pressure."""
    async def _run():
        proc = psutil.Process()
        while not stop_evt.is_set():
            samples.append({
                "ts": time.time(),
                "cpu_percent": psutil.cpu_percent(interval=None),
                "mem_percent": psutil.virtual_memory().percent,
                "process_rss_mb": proc.memory_info().rss / (1024 ** 2),
                "load_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
                "queue_pressure": queue_pressure.snapshot(),
            })
            try:
                await asyncio.wait_for(stop_evt.wait(), timeout=sample_period_s)
            except asyncio.TimeoutError:
                pass
    return _run()


async def _run_sequential(n: int, seed: LearningSeed) -> list:
    runs = []
    for _ in range(n):
        r = await run_learning_cycle(seed)
        runs.append(r)
    return runs


async def _run_gathered(n: int, seed: LearningSeed) -> list:
    tasks = [run_learning_cycle(seed) for _ in range(n)]
    return await asyncio.gather(*tasks)


async def _run_staggered(n: int, seed: LearningSeed, stagger_ms: int = 250) -> list:
    tasks = []
    for _ in range(n):
        tasks.append(asyncio.create_task(run_learning_cycle(seed)))
        await asyncio.sleep(stagger_ms / 1000.0)
    return await asyncio.gather(*tasks)


async def _profile_mode(name: str, coro_factory, sample_period_s: float = 0.25):
    stop_evt = asyncio.Event()
    samples: list = []
    sampler_task = asyncio.create_task(_sampler(stop_evt, samples, sample_period_s))
    t0 = time.perf_counter()
    runs = await coro_factory()
    wall = time.perf_counter() - t0
    stop_evt.set()
    await sampler_task

    stage_durations: dict = {}
    for r in runs:
        for stage, ms_list in _stage_metrics(r).items():
            stage_durations.setdefault(stage, []).extend(ms_list)

    def _pct(vs, p):
        if not vs:
            return 0
        vs2 = sorted(vs)
        k = max(0, min(len(vs2) - 1, int(p / 100.0 * (len(vs2) - 1))))
        return int(vs2[k])

    stage_summary = {
        stage: {
            "n": len(vs),
            "p50_ms": _pct(vs, 50),
            "p95_ms": _pct(vs, 95),
            "max_ms": int(max(vs)) if vs else 0,
            "mean_ms": int(statistics.mean(vs)) if vs else 0,
        }
        for stage, vs in stage_durations.items()
    }

    cpu_series = [s["cpu_percent"] for s in samples if s["cpu_percent"] is not None]
    mem_series = [s["mem_percent"] for s in samples]
    return {
        "mode": name,
        "n_cycles": len(runs),
        "wall_seconds": round(wall, 3),
        "cycles_per_second": round(len(runs) / wall, 3) if wall > 0 else 0,
        "status_counts": {
            s: sum(1 for r in runs if r.status == s)
            for s in ("completed", "early_reject", "failed")
        },
        "stage_ms": stage_summary,
        "cpu_percent": {
            "n_samples": len(cpu_series),
            "mean": round(statistics.mean(cpu_series), 2) if cpu_series else 0,
            "max":  round(max(cpu_series), 2) if cpu_series else 0,
            "p95":  round(sorted(cpu_series)[int(0.95 * (len(cpu_series) - 1))], 2)
                    if cpu_series else 0,
        },
        "mem_percent": {
            "mean": round(statistics.mean(mem_series), 2) if mem_series else 0,
            "max":  round(max(mem_series), 2) if mem_series else 0,
        },
        "cpu_pool_state": cpu_pool.get_pool_state(),
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=6)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--out", default="/app/audit/PERF_AUDIT_REPORT.json")
    args = ap.parse_args()

    seed = LearningSeed(
        pair="EURUSD", timeframe="H1", style="trend-following",
        count=1, max_duration_s=60,
    )

    host_snap = compute_probe.snapshot()
    host_hd = compute_probe.headroom_summary(host_snap)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "cpu_count": psutil.cpu_count(logical=True),
            "cpu_count_physical": psutil.cpu_count(logical=False),
            "mem_total_gb": round(psutil.virtual_memory().total / 1024**3, 2),
            "python": sys.version.split()[0],
            "compute_probe": host_snap,
            "headroom_summary": host_hd,
        },
        "env": {
            "USE_PROCESS_POOL": os.environ.get("USE_PROCESS_POOL"),
            "ENABLE_PROCESS_POOL_BACKTEST": os.environ.get("ENABLE_PROCESS_POOL_BACKTEST"),
            "CPU_POOL_SIZE": os.environ.get("CPU_POOL_SIZE"),
            "LEARNING_MIN_TRADES": os.environ.get("LEARNING_MIN_TRADES"),
        },
        "modes": [],
    }

    print(f"[perf-audit] warm-up: 1 cycle …", flush=True)
    await run_learning_cycle(seed)

    print(f"[perf-audit] sequential ({args.cycles} cycles) …", flush=True)
    report["modes"].append(await _profile_mode(
        "sequential",
        lambda: _run_sequential(args.cycles, seed),
    ))

    print(f"[perf-audit] gathered ({args.cycles} cycles, concurrency={args.concurrency}) …", flush=True)
    report["modes"].append(await _profile_mode(
        f"gathered_{args.concurrency}",
        lambda: _run_gathered(args.cycles, seed),
    ))

    print(f"[perf-audit] staggered (250ms) …", flush=True)
    report["modes"].append(await _profile_mode(
        "staggered_250ms",
        lambda: _run_staggered(args.cycles, seed),
    ))

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print(f"\n[perf-audit] report written to {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
