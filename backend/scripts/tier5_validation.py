"""Tier 5 · Production validation harness.

Runs the paper-broker drill in a loop for a fixed duration
(default 24h). Aggregates PASS/FAIL across every iteration and
writes a single canonical report at the end.

Usage:
  python3 tier5_validation.py --duration-hours 24 --backend mongo
  python3 tier5_validation.py --duration-hours 72 --backend mongo
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--duration-hours", type=float, default=24.0)
    p.add_argument("--backend", type=str, default="mongo",
                    choices=["mongo", "memory"])
    p.add_argument("--iterations", type=int, default=0,
                    help="0 = run for duration; N = run N iterations then stop")
    p.add_argument("--interval-s", type=int, default=900,
                    help="Sleep between drill iterations (default 15 min)")
    p.add_argument("--orders", type=int, default=100,
                    choices=[10, 100, 500, 1000])
    p.add_argument("--json", type=str, required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    end = time.time() + args.duration_hours * 3600
    iterations: list = []
    i = 0
    while True:
        i += 1
        if args.iterations > 0 and i > args.iterations:
            break
        if args.iterations == 0 and time.time() >= end:
            break
        t0 = time.time()
        cmd = ["python3", "/app/backend/scripts/paper_flow_drill.py",
                "--orders", str(args.orders), "--backend", args.backend]
        r = subprocess.run(cmd, capture_output=True, text=True,
                            env={**os.environ,
                              "PYTHONPATH": "/app/backend:/app/backend/legacy"},
                            timeout=600)
        ok = r.returncode == 0
        iterations.append({
            "i": i,
            "ts": datetime.now(timezone.utc).isoformat(),
            "duration_s": round(time.time() - t0, 2),
            "ok": ok,
            "returncode": r.returncode,
            "stderr_tail": r.stderr[-500:] if r.stderr else "",
        })
        print(f"iter {i:04d}  {'PASS' if ok else 'FAIL'}  "
              f"({round(time.time() - t0, 2)}s)")
        if args.iterations == 0:
            time.sleep(args.interval_s)

    verdict = "PASS" if all(x["ok"] for x in iterations) else "FAIL"
    n_pass = sum(1 for x in iterations if x["ok"])
    report = {
        "verdict": verdict,
        "backend": args.backend,
        "duration_hours": args.duration_hours,
        "n_iterations": len(iterations),
        "n_passed": n_pass,
        "n_failed": len(iterations) - n_pass,
        "started_at": iterations[0]["ts"] if iterations else "",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "iterations": iterations,
    }
    with open(args.json, "w") as f:
        json.dump(report, f, indent=2)
    print()
    print(f"Tier 5 · verdict={verdict} · {n_pass}/{len(iterations)} iterations passed")
    print(f"Report: {args.json}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
