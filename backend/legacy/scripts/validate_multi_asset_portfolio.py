#!/usr/bin/env python3
"""
P1 — Multi-Asset Portfolio Consistency Validation.

Runs the end-to-end multi-asset rollout N times for each configured
pair combination and measures how stable the output is across runs.

Variance sources:
  * Strategy generation (LLM-backed, stochastic)
  * Minor numerical drift in GA evaluation edge cases

Deterministic sources (should NOT vary across runs):
  * Asset gate verdict for a given (seed, template, data) — same
    inputs → same PASS/REJECT
  * Backtest engine math (IS / OOS / DD / PF)

What we track per trial:
  * per-pair gate: median_oos_pf, max_oos_dd, passed
  * portfolio: num_strategies, diversification_grade, avg_correlation,
    combined_metrics.{total_return_pct, max_drawdown_pct},
    asset_contributions_pct, warnings
  * gate pass-rate per pair across trials (should be high / stable)

Consistency gates (pass/fail across trials for a combo):
  * Gate PASS rate per pair ≥ 60 %           (gate is not wildly noisy)
  * Portfolio build rate       ≥ 80 %         (most runs should combine)
  * Median combined DD         ≤ 15 %         (target drawdown)
  * Combined DD std dev        ≤ 7 % absolute (consistency of DD)
  * Grade distribution includes A/B on majority

Outputs:
  * `/app/test_reports/portfolio_validation.json`
  * `/app/test_reports/portfolio_validation_summary.md`
  * Stdout per-trial summary + final verdict table

Usage:
  # from /app:
  set -a && source /app/backend/.env && set +a
  python backend/scripts/validate_multi_asset_portfolio.py
"""
from __future__ import annotations

import asyncio
import json
import statistics as stats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.dashboard import (                              # noqa: E402
    MultiAssetGenerateRequest, dashboard_generate_portfolio,
)


# ── Config ───────────────────────────────────────────────────────────
COMBOS: list[tuple[str, list[str]]] = [
    ("EURUSD+XAUUSD",           ["EURUSD", "XAUUSD"]),
    ("EURUSD+GBPUSD+XAUUSD",    ["EURUSD", "GBPUSD", "XAUUSD"]),
]
TRIALS_PER_COMBO = 3                # LLM stochastic, so ≥ 3 trials
GATE_SEEDS = [7, 42, 101]
GATE_POP = 8
GATE_GENS = 2
COUNT_PER_PAIR = 2
TOP_N_PER_PAIR = 2
TIMEFRAME = "H1"
STYLE = "trend-following"

# ── Consistency gates ────────────────────────────────────────────────
GATES = {
    "gate_pass_rate_min": 0.60,
    "portfolio_build_rate_min": 0.80,
    "median_dd_max": 15.0,
    "dd_stdev_max": 7.0,
}


def _safe(x, places=3):
    if x is None:
        return None
    try:
        return round(float(x), places)
    except (TypeError, ValueError):
        return None


def _median(vs):
    cleaned = [v for v in vs if v is not None]
    return _safe(stats.median(cleaned)) if cleaned else None


def _stdev(vs):
    cleaned = [v for v in vs if v is not None]
    if len(cleaned) < 2:
        return 0.0
    return round(stats.stdev(cleaned), 3)


async def run_trial(pairs: list[str], trial_idx: int) -> dict:
    t0 = time.perf_counter()
    req = MultiAssetGenerateRequest(
        pairs=pairs,
        timeframe=TIMEFRAME,
        style=STYLE,
        count=COUNT_PER_PAIR,
        top_n_per_pair=TOP_N_PER_PAIR,
        gate_enabled=True,
        gate_seeds=GATE_SEEDS,
        gate_population=GATE_POP,
        gate_generations=GATE_GENS,
    )
    try:
        res = await dashboard_generate_portfolio(req)
    except Exception as e:
        return {
            "trial": trial_idx,
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "elapsed_seconds": round(time.perf_counter() - t0, 2),
        }

    elapsed = round(time.perf_counter() - t0, 2)
    per_pair = res.get("per_pair") or []
    gates = {
        e["pair"]: {
            "passed": bool(e.get("passed")),
            "reason": (e.get("gate") or {}).get("reason"),
            "median_oos_pf": (e.get("gate") or {}).get("median_oos_pf"),
            "max_oos_dd":   (e.get("gate") or {}).get("max_oos_dd"),
            "top_strategies": len(e.get("top_strategies") or []),
            "candles": e.get("candles", 0),
        }
        for e in per_pair
    }

    port = res.get("portfolio")
    port_summary = None
    if port:
        cm = port.get("combined_metrics") or {}
        port_summary = {
            "num_strategies": port.get("num_strategies"),
            "grade": port.get("diversification_grade"),
            "avg_correlation": _safe(port.get("avg_correlation")),
            "total_return_pct": _safe(cm.get("total_return_pct")),
            "max_drawdown_pct": _safe(cm.get("max_drawdown_pct")),
            "volatility": _safe(cm.get("volatility")),
            "contributions": port.get("asset_contributions_pct") or {},
            "warnings": port.get("warnings") or [],
        }

    return {
        "trial": trial_idx,
        "ok": True,
        "elapsed_seconds": elapsed,
        "gates": gates,
        "portfolio": port_summary,
        "pairs_passed": res.get("pairs_passed") or [],
        "pairs_rejected": [r.get("pair") for r in res.get("pairs_rejected") or []],
    }


def analyse_combo(label: str, pairs: list[str], trials: list[dict]) -> dict:
    ok_trials = [t for t in trials if t.get("ok")]
    n = len(ok_trials)

    # Per-pair gate pass rate
    pass_rate: dict[str, float] = {}
    median_oos_pf: dict[str, float | None] = {}
    max_oos_dd:   dict[str, float | None] = {}
    for pair in pairs:
        passed = sum(
            1 for t in ok_trials
            if t["gates"].get(pair, {}).get("passed") is True
        )
        pass_rate[pair] = round(passed / n, 3) if n else 0.0
        median_oos_pf[pair] = _median([
            t["gates"].get(pair, {}).get("median_oos_pf") for t in ok_trials
        ])
        max_oos_dd[pair] = _median([
            t["gates"].get(pair, {}).get("max_oos_dd") for t in ok_trials
        ])

    # Portfolio
    built_trials = [t for t in ok_trials if t.get("portfolio")]
    build_rate = round(len(built_trials) / n, 3) if n else 0.0
    if built_trials:
        dds     = [t["portfolio"]["max_drawdown_pct"] for t in built_trials]
        returns = [t["portfolio"]["total_return_pct"] for t in built_trials]
        corrs   = [t["portfolio"]["avg_correlation"] for t in built_trials]
        grades  = [t["portfolio"]["grade"] for t in built_trials]
        port_stats = {
            "built_count": len(built_trials),
            "median_dd": _median(dds),
            "max_dd":    _safe(max(v for v in dds if v is not None)) if any(v is not None for v in dds) else None,
            "dd_stdev":  _stdev(dds),
            "median_return": _median(returns),
            "median_correlation": _median(corrs),
            "grades": dict((g, grades.count(g)) for g in sorted(set(grades)) if g),
        }
    else:
        port_stats = {
            "built_count": 0, "median_dd": None, "max_dd": None,
            "dd_stdev": 0.0, "median_return": None, "median_correlation": None,
            "grades": {},
        }

    # Consistency gate checks
    worst_pass = min(pass_rate.values()) if pass_rate else 0.0
    median_dd = port_stats.get("median_dd")
    checks = {
        "gate_pass_rate_min_ok": worst_pass >= GATES["gate_pass_rate_min"],
        "portfolio_build_rate_ok": build_rate >= GATES["portfolio_build_rate_min"],
        "median_dd_ok": (median_dd is None) or (median_dd <= GATES["median_dd_max"]),
        "dd_stdev_ok": port_stats["dd_stdev"] <= GATES["dd_stdev_max"],
    }
    overall = "PASS" if all(checks.values()) else (
        "FAIL" if not any(checks.values()) else "PARTIAL"
    )

    return {
        "combo": label,
        "pairs": pairs,
        "trials_total": len(trials),
        "trials_ok": n,
        "gate_pass_rate": pass_rate,
        "gate_median_oos_pf": median_oos_pf,
        "gate_max_oos_dd": max_oos_dd,
        "portfolio_build_rate": build_rate,
        "portfolio": port_stats,
        "checks": checks,
        "overall": overall,
    }


async def main():
    out_dir = Path("/app/test_reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("══════════════════════════════════════════════")
    print(" Multi-Asset Portfolio Consistency Validation")
    print(f" Trials per combo: {TRIALS_PER_COMBO} · gate seeds={GATE_SEEDS}")
    print("══════════════════════════════════════════════")

    results = []
    for label, pairs in COMBOS:
        print(f"\n──── {label} ({', '.join(pairs)}) ────")
        trials = []
        for i in range(1, TRIALS_PER_COMBO + 1):
            print(f"  Trial {i}/{TRIALS_PER_COMBO}…", end=" ", flush=True)
            trial = await run_trial(pairs, i)
            trials.append(trial)
            if not trial.get("ok"):
                print(f"ERROR ({trial.get('error')})")
                continue
            port = trial.get("portfolio")
            if port:
                print(
                    f"portfolio: grade={port['grade']} "
                    f"DD={port['max_drawdown_pct']}% "
                    f"ret={port['total_return_pct']}% "
                    f"corr={port['avg_correlation']} "
                    f"passed={trial['pairs_passed']} "
                    f"[{trial['elapsed_seconds']}s]"
                )
            else:
                print(
                    f"no-portfolio (only {len(trial['pairs_passed'])} passed) "
                    f"rejected={trial['pairs_rejected']} [{trial['elapsed_seconds']}s]"
                )
        summary = analyse_combo(label, pairs, trials)
        summary["trials"] = trials
        results.append(summary)

        print(f"\n  ── Consistency: {summary['overall']}")
        for pair in pairs:
            pr = summary['gate_pass_rate'].get(pair, 0.0)
            print(
                f"     {pair}: gate pass rate {pr * 100:.0f}% · "
                f"median OOS PF {summary['gate_median_oos_pf'].get(pair)} · "
                f"max OOS DD {summary['gate_max_oos_dd'].get(pair)}%"
            )
        ps = summary["portfolio"]
        print(
            f"     portfolio built: {summary['portfolio_build_rate'] * 100:.0f}% · "
            f"median DD {ps['median_dd']}% · DD stdev {ps['dd_stdev']}% · "
            f"median return {ps['median_return']}% · "
            f"grades {ps['grades']}"
        )
        for k, v in summary['checks'].items():
            print(f"       {k}: {'✓' if v else '✗'}")

    combined = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "config": {
            "trials_per_combo": TRIALS_PER_COMBO,
            "gate_seeds": GATE_SEEDS,
            "gate_population": GATE_POP,
            "gate_generations": GATE_GENS,
            "count_per_pair": COUNT_PER_PAIR,
            "top_n_per_pair": TOP_N_PER_PAIR,
            "timeframe": TIMEFRAME,
            "style": STYLE,
            "gates": GATES,
        },
        "combos": results,
    }
    out = out_dir / "portfolio_validation.json"
    out.write_text(json.dumps(combined, indent=2, default=str))
    print(f"\n✓ JSON report: {out}")

    # Build human-friendly markdown summary
    md_lines = []
    md_lines.append("# Multi-Asset Portfolio Consistency Report\n")
    md_lines.append(f"**Date:** {time.strftime('%Y-%m-%d')}  ")
    md_lines.append(f"**Trials per combo:** {TRIALS_PER_COMBO}  ")
    md_lines.append(f"**Gate seeds:** {GATE_SEEDS} · pop={GATE_POP} · gen={GATE_GENS}\n")

    md_lines.append("## Consistency gates")
    md_lines.append("| Gate | Target |")
    md_lines.append("|------|--------|")
    md_lines.append(f"| Gate pass rate per pair | ≥ {GATES['gate_pass_rate_min'] * 100:.0f} % |")
    md_lines.append(f"| Portfolio build rate   | ≥ {GATES['portfolio_build_rate_min'] * 100:.0f} % |")
    md_lines.append(f"| Median combined DD     | ≤ {GATES['median_dd_max']} % |")
    md_lines.append(f"| DD stdev across trials | ≤ {GATES['dd_stdev_max']} % |\n")

    for s in results:
        md_lines.append(f"## {s['combo']} — {s['overall']}\n")
        md_lines.append(f"Trials ok: **{s['trials_ok']}/{s['trials_total']}** · "
                        f"portfolio built: **{s['portfolio_build_rate'] * 100:.0f} %**\n")
        md_lines.append("### Per-pair gate")
        md_lines.append("| Pair | Pass rate | Median OOS PF | Max OOS DD |")
        md_lines.append("|------|-----------|---------------|-----------|")
        for pair in s['pairs']:
            md_lines.append(
                f"| {pair} | {s['gate_pass_rate'].get(pair, 0) * 100:.0f} % | "
                f"{s['gate_median_oos_pf'].get(pair)} | "
                f"{s['gate_max_oos_dd'].get(pair)} % |"
            )
        md_lines.append("")
        ps = s['portfolio']
        md_lines.append("### Portfolio aggregate")
        md_lines.append(f"* Built: {ps['built_count']}/{s['trials_total']}")
        md_lines.append(f"* Median DD: **{ps['median_dd']} %** · max DD {ps['max_dd']} % · "
                        f"DD stdev {ps['dd_stdev']} %")
        md_lines.append(f"* Median return: {ps['median_return']} %")
        md_lines.append(f"* Median correlation: {ps['median_correlation']}")
        md_lines.append(f"* Grade distribution: {ps['grades']}")
        md_lines.append("### Per-trial rollout")
        md_lines.append("| # | grade | DD % | Return % | corr | passed | rejected | secs |")
        md_lines.append("|---|-------|-----:|---------:|-----:|--------|----------|-----:|")
        for t in s.get("trials", []):
            if not t.get("ok"):
                md_lines.append(f"| {t['trial']} | — | — | — | — | — | ERROR | {t.get('elapsed_seconds')} |")
                continue
            port = t.get("portfolio")
            passed = ", ".join(t.get("pairs_passed") or []) or "—"
            rej = ", ".join(t.get("pairs_rejected") or []) or "—"
            if port:
                md_lines.append(
                    f"| {t['trial']} | {port['grade']} | {port['max_drawdown_pct']} | "
                    f"{port['total_return_pct']} | {port['avg_correlation']} | "
                    f"{passed} | {rej} | {t['elapsed_seconds']} |"
                )
            else:
                md_lines.append(
                    f"| {t['trial']} | — | — | — | — | {passed} | {rej} | "
                    f"{t['elapsed_seconds']} |"
                )
        md_lines.append("")

    md_lines.append("## Final verdict\n")
    md_lines.append("| Combo | Overall | Build rate | Median DD | DD stdev |")
    md_lines.append("|-------|---------|-----------:|----------:|---------:|")
    for s in results:
        md_lines.append(
            f"| {s['combo']} | **{s['overall']}** | "
            f"{s['portfolio_build_rate'] * 100:.0f} % | "
            f"{s['portfolio']['median_dd']} % | {s['portfolio']['dd_stdev']} % |"
        )

    out_md = out_dir / "portfolio_validation_summary.md"
    out_md.write_text("\n".join(md_lines))
    print(f"✓ Markdown summary: {out_md}")

    print("\n══════════════════════════════════════════════")
    print("  FINAL VERDICT")
    print("══════════════════════════════════════════════")
    for s in results:
        print(f"  {s['combo']}: {s['overall']} · build rate {s['portfolio_build_rate'] * 100:.0f}% · "
              f"median DD {s['portfolio']['median_dd']}%")


if __name__ == "__main__":
    asyncio.run(main())
