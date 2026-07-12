#!/usr/bin/env python3
"""
P2 — Per-Asset Stability Validation (pre-multi-asset rollout)

Runs a controlled suite of deterministic backtests + GA optimizations
on GBPUSD/H1 and XAUUSD/H1 and reports OOS PF consistency, drawdown
stability, trade quality, and IS↔OOS PF gap.

Stability gates (pass/fail per asset):
  • OOS PF:     median ≥ 1.10  (target "not losing money OOS")
  • IS↔OOS gap: median |pf_gap| ≤ 0.60  (target "no severe overfit")
  • OOS DD:     max ≤ 30 %  (target "recoverable drawdown")
  • Quality:    avg score ≥ 40  (target "entries not noise")
  • Determinism: same seed → identical PF (bit-exact)

Runs:
  A) Baseline static strategy, quality filter OFF (sanity)
  B) Baseline static strategy, quality filter ON @ calibrated threshold
  C) GA optimizer, 5 seeds, filter OFF — for OOS PF seed-variance
  D) GA optimizer, 5 seeds, filter ON  — for OOS PF seed-variance
     under quality-aware search.

Outputs a JSON report to /app/test_reports/stability_<asset>.json and
prints a summary table.

No core engine changes are made — pure validation.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics as stats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from engines.backtest_engine import run_backtest_logic  # noqa: E402
from engines.ga_optimizer import run_ga_search  # noqa: E402


# ── Config ───────────────────────────────────────────────────────────
STRATEGY_TEMPLATE = "EMA(20)/EMA(50) trend-following SL=20 TP=40"
GA_SEEDS = [7, 42, 101, 314, 2718]
GA_POP = 10
GA_GENS = 3
CALIB_OFFSET = 5.0  # recommended_threshold = avg + offset


# ── Stability gates ─────────────────────────────────────────────────
GATES = {
    "oos_pf_median_min": 1.10,
    "oos_pf_gap_abs_median_max": 0.60,
    "oos_dd_max_max": 30.0,
    "quality_avg_min": 40.0,
}


TF_UI_TO_DB = {
    "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
    "H1": "1h", "H4": "4h", "D1": "1d",
}


async def _load(db, symbol: str, timeframe: str) -> dict:
    tf_db = TF_UI_TO_DB.get(timeframe.upper(), timeframe.lower())
    docs = [d async for d in db.market_data.find(
        {"symbol": symbol, "timeframe": tf_db},
        {"_id": 0, "open": 1, "high": 1, "low": 1, "close": 1, "timestamp": 1},
    ).sort("timestamp", 1)]
    return {
        "closes": [d["close"] for d in docs],
        "highs": [d["high"] for d in docs],
        "lows": [d["low"] for d in docs],
        "timestamps": [d["timestamp"] for d in docs],
        "n": len(docs),
    }


def _safe(x):
    if x is None:
        return None
    try:
        return round(float(x), 3)
    except (TypeError, ValueError):
        return None


def _run_baseline(data, filter_on: bool, threshold: float, symbol: str, timeframe: str) -> dict:
    sim_config = {"quality_filter": filter_on, "quality_threshold": threshold}
    bt = run_backtest_logic(
        STRATEGY_TEMPLATE, symbol, timeframe,
        external_prices=data["closes"],
        external_highs=data["highs"],
        external_lows=data["lows"],
        external_timestamps=data["timestamps"],
        data_source="real",
        sim_config=sim_config,
    )
    p4 = bt.get("_phase4_signal_quality") or {}
    p5 = bt.get("_phase5_risk_calibration") or {}
    return {
        "is_pf":     _safe(bt.get("profit_factor")),
        "is_dd":     _safe(bt.get("max_drawdown_pct")),
        "is_trades": bt.get("total_trades") or 0,
        "oos_pf":    _safe(bt.get("oos_profit_factor")),
        "oos_dd":    _safe(bt.get("oos_max_drawdown_pct")),
        "oos_trades": bt.get("oos_total_trades") or 0,
        "pf_gap":    (
            _safe((bt.get("profit_factor") or 0) - (bt.get("oos_profit_factor") or 0))
        ),
        "quality_is_avg":   p4.get("is_avg_score"),
        "quality_oos_avg":  p4.get("oos_avg_score"),
        "quality_is_pct":   p4.get("is_quality_filter_pct"),
        "quality_oos_pct":  p4.get("oos_quality_filter_pct"),
        "atr_stops_enabled": p5.get("atr_stops_enabled"),
        "risk_model": p5.get("risk_model"),
        "is_ruin_triggered": p5.get("is_ruin_triggered"),
        "oos_ruin_triggered": p5.get("oos_ruin_triggered"),
    }


def _run_ga(data, filter_on: bool, threshold: float, seed: int, symbol: str, timeframe: str) -> dict:
    t0 = time.perf_counter()
    res = run_ga_search(
        STRATEGY_TEMPLATE, symbol, timeframe, data["closes"],
        train_ratio=0.70, population_size=GA_POP, generations=GA_GENS,
        sim_config={"quality_filter": filter_on, "quality_threshold": threshold},
        rng_seed=seed,
    )
    if not res.get("success"):
        return {"ok": False, "reason": res.get("error", "unknown"), "seed": seed}
    m_is = res.get("metrics") or {}
    m_oos = res.get("oos_metrics") or {}
    p4_is = (m_is or {}).get("_phase4_signal_quality") or {}
    p4_oos = (m_oos or {}).get("_phase4_signal_quality") or {}
    return {
        "ok": True,
        "seed": seed,
        "seconds": round(time.perf_counter() - t0, 2),
        "is_pf":    _safe(m_is.get("profit_factor")),
        "is_dd":    _safe(m_is.get("max_drawdown_pct")),
        "is_trades": m_is.get("total_trades") or 0,
        "oos_pf":   _safe(m_oos.get("profit_factor")),
        "oos_dd":   _safe(m_oos.get("max_drawdown_pct")),
        "oos_trades": m_oos.get("total_trades") or 0,
        "pf_gap": _safe((m_is.get("profit_factor") or 0) - (m_oos.get("profit_factor") or 0)),
        "quality_is_avg":  p4_is.get("is_avg_score"),
        "quality_oos_avg": p4_oos.get("oos_avg_score") or p4_oos.get("is_avg_score"),
        "params": res.get("params"),
    }


def _pct(vs, p):
    if not vs:
        return None
    try:
        return round(float(stats.quantiles(vs, n=100)[int(p) - 1]), 3)
    except Exception:
        return _safe(sorted(vs)[0]) if vs else None


def _summ(runs, key):
    vs = [r[key] for r in runs if r.get("ok", True) and r.get(key) is not None]
    if not vs:
        return {"n": 0, "min": None, "max": None, "median": None, "p25": None, "p75": None}
    return {
        "n": len(vs),
        "min": _safe(min(vs)),
        "max": _safe(max(vs)),
        "median": _safe(stats.median(vs)),
        "p25": _pct(vs, 25),
        "p75": _pct(vs, 75),
    }


def _evaluate_gates(ga_runs: list, baseline_on: dict) -> dict:
    """Apply stability gates; return per-gate pass/fail + overall."""
    ok_runs = [r for r in ga_runs if r.get("ok")]
    if not ok_runs:
        return {"overall": "FAIL", "reason": "no GA runs succeeded"}

    pf_oos = [r["oos_pf"] for r in ok_runs if r["oos_pf"] is not None]
    pf_gap_abs = [abs(r["pf_gap"]) for r in ok_runs if r["pf_gap"] is not None]
    dd_oos = [r["oos_dd"] for r in ok_runs if r["oos_dd"] is not None]

    q_avg = baseline_on.get("quality_is_avg") or baseline_on.get("quality_oos_avg") or 0

    checks = {
        "oos_pf_median_ok": (
            (stats.median(pf_oos) if pf_oos else 0) >= GATES["oos_pf_median_min"]
        ),
        "pf_gap_median_ok": (
            (stats.median(pf_gap_abs) if pf_gap_abs else 99) <= GATES["oos_pf_gap_abs_median_max"]
        ),
        "dd_max_ok": (
            (max(dd_oos) if dd_oos else 99) <= GATES["oos_dd_max_max"]
        ),
        "quality_avg_ok": (
            float(q_avg or 0) >= GATES["quality_avg_min"]
        ),
    }
    overall = "PASS" if all(checks.values()) else "PARTIAL"
    if not any(checks.values()):
        overall = "FAIL"
    return {"overall": overall, "checks": checks, "gates": GATES}


async def validate_asset(symbol: str, timeframe: str) -> dict:
    print("\n══════════════════════════════════════════════")
    print(f" Validating {symbol}/{timeframe}")
    print("══════════════════════════════════════════════")
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    try:
        data = await _load(db, symbol, timeframe)
    finally:
        client.close()

    if data["n"] < 200:
        return {
            "asset": f"{symbol}/{timeframe}",
            "success": False,
            "error": f"insufficient data (have {data['n']}, need ≥200)",
        }

    print(f"  Loaded {data['n']} candles")

    # A — Baseline filter OFF
    base_off = _run_baseline(data, False, 0.0, symbol, timeframe)
    print(
        f"  Baseline OFF: IS PF={base_off['is_pf']} DD={base_off['is_dd']}% "
        f"trades={base_off['is_trades']} | OOS PF={base_off['oos_pf']} "
        f"DD={base_off['oos_dd']}% trades={base_off['oos_trades']} | "
        f"avg_score={base_off['quality_is_avg']} · atr={base_off.get('atr_stops_enabled')}"
    )

    # Calibrate threshold
    is_avg = float(base_off.get("quality_is_avg") or 50.0)
    threshold = max(0.0, min(100.0, round(is_avg + CALIB_OFFSET, 1)))

    # B — Baseline filter ON
    base_on = _run_baseline(data, True, threshold, symbol, timeframe)
    print(
        f"  Baseline ON  @ thr={threshold}: IS PF={base_on['is_pf']} "
        f"DD={base_on['is_dd']}% trades={base_on['is_trades']} | "
        f"OOS PF={base_on['oos_pf']} DD={base_on['oos_dd']}% "
        f"trades={base_on['oos_trades']} | filtered: "
        f"IS {base_on.get('quality_is_pct')}% / OOS {base_on.get('quality_oos_pct')}%"
    )

    # C — GA filter OFF × 5 seeds
    print(f"  Running GA × {len(GA_SEEDS)} seeds (filter OFF)…")
    ga_off = [_run_ga(data, False, 0.0, s, symbol, timeframe) for s in GA_SEEDS]
    # D — GA filter ON × 5 seeds
    print(f"  Running GA × {len(GA_SEEDS)} seeds (filter ON @ {threshold})…")
    ga_on = [_run_ga(data, True, threshold, s, symbol, timeframe) for s in GA_SEEDS]

    for label, runs in (("GA OFF", ga_off), ("GA ON", ga_on)):
        print(f"  {label}:")
        for r in runs:
            if r.get("ok"):
                print(
                    f"    seed={r['seed']:>4}  IS PF={r['is_pf']}  "
                    f"OOS PF={r['oos_pf']}  OOS DD={r['oos_dd']}%  "
                    f"trades={r['oos_trades']}  gap={r['pf_gap']}  "
                    f"[{r['seconds']}s]"
                )
            else:
                print(f"    seed={r['seed']:>4}  FAILED: {r.get('reason')}")

    gates_on = _evaluate_gates(ga_on, base_on)
    gates_off = _evaluate_gates(ga_off, base_off)

    summary = {
        "asset": f"{symbol}/{timeframe}",
        "success": True,
        "candles": data["n"],
        "threshold": threshold,
        "baseline_off": base_off,
        "baseline_on": base_on,
        "ga_off_runs": ga_off,
        "ga_on_runs": ga_on,
        "ga_off_summary": {
            "oos_pf": _summ(ga_off, "oos_pf"),
            "oos_dd": _summ(ga_off, "oos_dd"),
            "pf_gap": _summ(ga_off, "pf_gap"),
            "oos_trades": _summ(ga_off, "oos_trades"),
        },
        "ga_on_summary": {
            "oos_pf": _summ(ga_on, "oos_pf"),
            "oos_dd": _summ(ga_on, "oos_dd"),
            "pf_gap": _summ(ga_on, "pf_gap"),
            "oos_trades": _summ(ga_on, "oos_trades"),
        },
        "stability_gates_off": gates_off,
        "stability_gates_on": gates_on,
    }

    print(f"\n  ── Gates (filter OFF): {gates_off.get('overall')}")
    for k, v in (gates_off.get("checks") or {}).items():
        print(f"     {k}: {'✓' if v else '✗'}")
    print(f"  ── Gates (filter ON):  {gates_on.get('overall')}")
    for k, v in (gates_on.get("checks") or {}).items():
        print(f"     {k}: {'✓' if v else '✗'}")

    return summary


async def main():
    out_dir = Path("/app/test_reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for symbol, timeframe in (("GBPUSD", "H1"), ("XAUUSD", "H1")):
        res = await validate_asset(symbol, timeframe)
        results.append(res)
        out = out_dir / f"stability_{symbol}_{timeframe}.json"
        out.write_text(json.dumps(res, indent=2, default=str))
        print(f"  → Report: {out}")

    combined = out_dir / "stability_validation.json"
    combined.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "strategy": STRATEGY_TEMPLATE,
        "ga_config": {"population": GA_POP, "generations": GA_GENS, "seeds": GA_SEEDS},
        "gates": GATES,
        "assets": results,
    }, indent=2, default=str))
    print(f"\n✓ Combined report: {combined}")

    print("\n══════════════════════════════════════════════")
    print("  FINAL VERDICT")
    print("══════════════════════════════════════════════")
    all_pass = True
    for r in results:
        if not r.get("success"):
            print(f"  {r['asset']}: ERROR — {r.get('error')}")
            all_pass = False
            continue
        off = r["stability_gates_off"]["overall"]
        on = r["stability_gates_on"]["overall"]
        print(f"  {r['asset']}: OFF={off} · ON={on}")
        if on not in ("PASS", "PARTIAL"):
            all_pass = False

    print()
    if all_pass:
        print("  → System appears STABLE — multi-asset rollout recommended.")
    else:
        print("  → Stability issues detected — review per-asset report before rollout.")


if __name__ == "__main__":
    asyncio.run(main())
