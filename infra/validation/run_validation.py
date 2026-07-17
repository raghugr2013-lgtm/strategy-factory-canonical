"""Production Validation Suite — entrypoint.

Usage:
  python -m infra.validation.run_validation
  python -m infra.validation.run_validation --module strategy
  python -m infra.validation.run_validation --module portfolio
  python -m infra.validation.run_validation --module execution
  python -m infra.validation.run_validation --full
  python -m infra.validation.run_validation --report-only
  python -m infra.validation.run_validation --tier5
  python -m infra.validation.run_validation --tier5 \
      --tier5-hours 24 --tier5-interval-s 300

Zero external dependencies beyond `requests`. `psutil` optional (Tier 5).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Type

from . import config
from .auth import require_session
from .modules import ProbeResult, ModuleRunner
from .modules.authentication         import AuthenticationModule
from .modules.execution_intelligence import ExecutionIntelligenceModule
from .modules.factory_evaluation     import FactoryEvaluationModule
from .modules.health                 import HealthModule
from .modules.market_intelligence    import MarketIntelligenceModule
from .modules.meta_learning          import MetaLearningModule
from .modules.portfolio              import PortfolioModule
from .modules.propfirm               import PropFirmModule
from .modules.strategy_engineering   import StrategyEngineeringModule
from .reporter import render_console, write_reports


MODULES: Dict[str, Type[ModuleRunner]] = {
    HealthModule.NAME:                  HealthModule,
    AuthenticationModule.NAME:          AuthenticationModule,
    StrategyEngineeringModule.NAME:     StrategyEngineeringModule,
    PortfolioModule.NAME:               PortfolioModule,
    PropFirmModule.NAME:                PropFirmModule,
    MarketIntelligenceModule.NAME:      MarketIntelligenceModule,
    ExecutionIntelligenceModule.NAME:   ExecutionIntelligenceModule,
    MetaLearningModule.NAME:            MetaLearningModule,
    FactoryEvaluationModule.NAME:       FactoryEvaluationModule,
}

MODULE_ALIASES = {
    "strategy":      StrategyEngineeringModule.NAME,
    "portfolio":     PortfolioModule.NAME,
    "execution":     ExecutionIntelligenceModule.NAME,
    "market":        MarketIntelligenceModule.NAME,
    "propfirm":      PropFirmModule.NAME,
    "meta":          MetaLearningModule.NAME,
    "factory":       FactoryEvaluationModule.NAME,
    "auth":          AuthenticationModule.NAME,
    "health":        HealthModule.NAME,
}


def _select(module_arg: str) -> List[Type[ModuleRunner]]:
    if not module_arg or module_arg == "all":
        return list(MODULES.values())
    key = MODULE_ALIASES.get(module_arg, module_arg)
    if key not in MODULES:
        sys.stderr.write(
            f"Unknown module '{module_arg}'. "
            f"Available: {', '.join(sorted(MODULES) + sorted(MODULE_ALIASES))}\n")
        sys.exit(2)
    return [MODULES[key]]


def run_once(selected: List[Type[ModuleRunner]]) -> Dict:
    started = datetime.now(timezone.utc)
    t0 = time.time()
    sess = require_session()
    all_rows: List[ProbeResult] = []
    for cls in selected:
        mod = cls()
        rows = mod.run(sess)
        all_rows.extend(rows)
    finished = datetime.now(timezone.utc)
    duration_s = time.time() - t0
    meta = {
        "run_id": started.strftime("%Y%m%dT%H%M%SZ"),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_s": duration_s,
        "base_url": config.BASE_URL,
        "modules": [c.NAME for c in selected],
    }
    return {"meta": meta, "rows": all_rows}


def cmd_run(args) -> int:
    selected = _select(args.module or "all")
    result = run_once(selected)
    rows = result["rows"]
    meta = result["meta"]

    print(render_console(rows))
    files = write_reports(rows, meta)
    print()
    print(f"Reports written to: {config.REPORTS_DIR}")
    for k, p in files.items():
        print(f"  {k}: {p.name}")

    # Exit code: 0 if no FAIL else 1
    fail = sum(1 for r in rows if r.status == "FAIL")
    return 0 if fail == 0 else 1


def cmd_report_only(args) -> int:
    """Print the most recent stored report to stdout."""
    p = config.REPORTS_DIR / "validation_summary.txt"
    if not p.exists():
        sys.stderr.write("No prior report found. Run a validation first.\n")
        return 2
    print(p.read_text())
    return 0


def cmd_tier5(args) -> int:
    """24-hour continuous validation with system-metrics collection."""
    duration_h = args.tier5_hours or config.TIER5_DURATION_HOURS
    interval_s = args.tier5_interval_s or config.TIER5_INTERVAL_SECONDS
    end_at = time.time() + duration_h * 3600

    # Optional psutil
    try:
        import psutil
        have_psutil = True
    except ImportError:
        have_psutil = False

    metrics = {"cycles": [], "meta": {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "duration_hours": duration_h,
        "interval_seconds": interval_s,
        "base_url": config.BASE_URL,
        "psutil_available": have_psutil,
    }}

    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    metrics_path = config.REPORTS_DIR / "tier5_metrics.json"
    md_path      = config.REPORTS_DIR / "tier5_report.md"

    cycle_no = 0
    while time.time() < end_at:
        cycle_no += 1
        cy_t0 = time.time()
        result = run_once(list(MODULES.values()))
        rows = result["rows"]
        pass_n = sum(1 for r in rows if r.status == "PASS")
        fail_n = sum(1 for r in rows if r.status == "FAIL")
        warn_n = sum(1 for r in rows if r.status == "WARN")
        avg_ms = (sum(r.duration_ms for r in rows) / len(rows)) if rows else 0.0

        cycle_metric = {
            "cycle": cycle_no,
            "ts": datetime.now(timezone.utc).isoformat(),
            "duration_s": round(time.time() - cy_t0, 3),
            "pass": pass_n, "fail": fail_n, "warn": warn_n,
            "avg_ms": round(avg_ms, 2),
        }
        if have_psutil:
            cycle_metric["cpu_pct"]    = psutil.cpu_percent(interval=None)
            cycle_metric["ram_pct"]    = psutil.virtual_memory().percent
            cycle_metric["ram_used_mb"]= round(psutil.virtual_memory().used
                                                / 1024 / 1024, 2)
        metrics["cycles"].append(cycle_metric)
        metrics_path.write_text(json.dumps(metrics, indent=2))

        stamp = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
        print(f"[{stamp}] cycle {cycle_no:>4d}  "
              f"PASS={pass_n:>3d} FAIL={fail_n:>2d} WARN={warn_n:>2d} "
              f"avg_ms={avg_ms:>6.1f} "
              + (f"cpu={cycle_metric.get('cpu_pct',0):>4.1f}% "
                  f"ram_used={cycle_metric.get('ram_used_mb',0):>6.0f}MB"
                  if have_psutil else ""))

        # Sleep until next interval
        remaining = interval_s - (time.time() - cy_t0)
        if remaining > 0 and time.time() + remaining < end_at:
            time.sleep(remaining)

    # Final markdown
    _write_tier5_md(md_path, metrics)
    print(f"\nTier 5 complete. Metrics: {metrics_path}. Report: {md_path}")
    return 0


def _write_tier5_md(path: Path, metrics: dict) -> None:
    m = metrics["meta"]
    cycles = metrics["cycles"]
    total_pass = sum(c["pass"] for c in cycles)
    total_fail = sum(c["fail"] for c in cycles)
    total_warn = sum(c["warn"] for c in cycles)
    lines = [
        f"# Tier 5 Validation Report",
        f"",
        f"- Started: {m['started_at']}",
        f"- Duration target: {m['duration_hours']}h",
        f"- Interval: {m['interval_seconds']}s",
        f"- Base URL: {m['base_url']}",
        f"- Cycles completed: {len(cycles)}",
        f"- Aggregate: PASS={total_pass} FAIL={total_fail} WARN={total_warn}",
        f"",
        "## Per-cycle metrics",
        "",
        "| # | ts | dur_s | pass | fail | warn | avg_ms | cpu% | ram% | ram_MB |",
        "|---|----|-------|------|------|------|--------|------|------|--------|",
    ]
    for c in cycles:
        lines.append(
            f"| {c['cycle']} | {c['ts']} | {c['duration_s']} | "
            f"{c['pass']} | {c['fail']} | {c['warn']} | {c['avg_ms']} | "
            f"{c.get('cpu_pct','-')} | {c.get('ram_pct','-')} | "
            f"{c.get('ram_used_mb','-')} |")
    path.write_text("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Strategy Factory — Production Validation Suite")
    p.add_argument("--module", help="one module to run (or an alias)")
    p.add_argument("--full",   action="store_true",
                    help="run every module (default)")
    p.add_argument("--report-only", action="store_true",
                    help="print the most recent stored report")
    p.add_argument("--tier5", action="store_true",
                    help="run continuously for 24h (default) or --tier5-hours")
    p.add_argument("--tier5-hours", type=int, default=None,
                    help="tier5 duration in hours (default 24)")
    p.add_argument("--tier5-interval-s", type=int, default=None,
                    help="tier5 iteration cadence in seconds (default 300)")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.report_only:
        return cmd_report_only(args)
    if args.tier5:
        return cmd_tier5(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
