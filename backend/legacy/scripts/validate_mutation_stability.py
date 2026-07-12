"""
Phase 14 Validation Harness — mutation + auto-save + stability logs.

Non-invasive, read-only. Exercises the full pipeline across a varied
matrix of inputs and prints a consolidated stability report. Never
mutates engine code and clears only the stability collection it created.

Run:
    cd /app/backend && python -m scripts.validate_mutation_stability
"""
from __future__ import annotations

import asyncio
import json
import math
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

from engines.db import get_db  # noqa: E402
from engines.mutation_engine import (  # noqa: E402
    MIN_TRADES_FOR_AUTO_SAVE,
    STABILITY_COLL,
    get_stability_stats,
    list_stability_logs,
    run_mutation_pipeline,
)
from engines.strategy_library import COLLECTION as LIB_COLL  # noqa: E402


def _sine(n: int, amp: float = 0.005, drift: float = 5e-5,
          period: float = 15.0, seed: float = 1.10) -> list:
    return [seed + amp * math.sin(i / period) + drift * i for i in range(n)]


def _ramp(n: int, start: float = 1.10, slope: float = 1e-4) -> list:
    return [start + slope * i for i in range(n)]


def _noisy(n: int, amp: float = 0.005, period: float = 15.0,
           seed: float = 1.10) -> list:
    # Still deterministic — uses cos+sin combination, no RNG.
    return [
        seed + amp * math.sin(i / period) + amp * 0.3 * math.cos(i / 7.0)
        + 3e-5 * i
        for i in range(n)
    ]


BASES = [
    {
        "label": "trend-rsi",
        "strategy_text": (
            "BUY when EMA(20) crosses above EMA(50) AND RSI(14) > 50. "
            "SL 20 pips TP 35 pips."
        ),
        "pair": "EURUSD", "timeframe": "H1", "style": "trend-following",
    },
    {
        "label": "mean-reversion-bb",
        "strategy_text": (
            "SELL when close > upper BB(20,2). BUY when close < lower BB(20,2). "
            "SL 30 pips TP 20 pips."
        ),
        "pair": "GBPUSD", "timeframe": "H1", "style": "mean-reversion",
    },
    {
        "label": "breakout-atr",
        "strategy_text": (
            "BUY when close > previous high + ATR(14)*0.5. SL = 1.5*ATR, TP = 3*ATR."
        ),
        "pair": "USDJPY", "timeframe": "H4", "style": "breakout",
    },
]


async def _run_case(*, label: str, base: dict, prices: list, run_tag: str,
                    repeat: int = 1) -> list:
    """Execute one case `repeat` times, returning each run's result."""
    results = []
    for i in range(repeat):
        r = await run_mutation_pipeline(
            base, max_variants=8, prices=prices,
            auto_save=True, firm="ftmo",
            triggered_by=f"validation_{run_tag}",
        )
        results.append({
            "label": label, "run_tag": run_tag, "iter": i,
            "status": r["status"],
            "best_mutation_type": (r.get("best_variant") or {}).get("mutation_type"),
            "best_variant_fingerprint": (r.get("best_variant") or {}).get("variant_fingerprint"),
            "best_backtest": (r.get("best_variant") or {}).get("backtest"),
            "auto_save_result": r.get("auto_save_result"),
        })
    return results


def _determinism_ok(runs: list) -> bool:
    """Every iteration of a case must yield the same
    (mutation_type, variant_fingerprint, profit_factor, trades, auto_save_status)."""
    if len(runs) < 2:
        return True
    keyfn = lambda r: (  # noqa: E731
        r["best_mutation_type"],
        r["best_variant_fingerprint"],
        (r["best_backtest"] or {}).get("profit_factor"),
        (r["best_backtest"] or {}).get("total_trades"),
        (r["auto_save_result"] or {}).get("status"),
        (r["auto_save_result"] or {}).get("variant_fingerprint"),
        (r["auto_save_result"] or {}).get("score"),
        (r["auto_save_result"] or {}).get("verdict"),
    )
    first = keyfn(runs[0])
    return all(keyfn(r) == first for r in runs[1:])


async def main():
    db = get_db()

    # Isolate the validation run — only touches the stability log and
    # cleans up after itself. Library docs produced are removed too.
    await db[STABILITY_COLL].delete_many({})
    await db[LIB_COLL].delete_many({"source": "mutation_engine"})

    # Matrix: (label, base_index, price_builder, repeats)
    cases = [
        # Low data → min-trade gate MUST reject
        ("low-data-sine-250",    0, _sine(250),  1),
        # More data with each base
        ("sine-500-trend",       0, _sine(500),  1),
        ("sine-500-meanrev",     1, _sine(500),  1),
        ("sine-500-breakout",    2, _sine(500),  1),
        ("sine-800-trend",       0, _sine(800),  1),
        ("noisy-600-trend",      0, _noisy(600), 1),
        ("ramp-700-trend",       0, _ramp(700),  1),
        # Determinism: identical input repeated 3×
        ("determinism-500",      0, _sine(500),  3),
        ("determinism-800",      1, _sine(800),  3),
    ]

    all_runs = []
    case_results = {}
    print("\n" + "=" * 70)
    print("PHASE 14 VALIDATION — MUTATION + AUTO-SAVE + STABILITY")
    print("=" * 70)
    print(f"MIN_TRADES_FOR_AUTO_SAVE = {MIN_TRADES_FOR_AUTO_SAVE}")
    print()

    for label, base_idx, prices, repeat in cases:
        base = BASES[base_idx]
        runs = await _run_case(
            label=label, base=base, prices=prices,
            run_tag=label, repeat=repeat,
        )
        case_results[label] = runs
        all_runs.extend(runs)

        r0 = runs[0]
        asr = r0["auto_save_result"] or {}
        bbt = r0["best_backtest"] or {}
        det_flag = ""
        if repeat > 1:
            det_flag = "  DETERMINISM=OK" if _determinism_ok(runs) else "  DETERMINISM=FAIL"
        print(
            f"[{label:<26}] base={base['label']:<18} "
            f"candles={len(prices):>4} "
            f"best={r0['best_mutation_type']:<28} "
            f"trades={int(bbt.get('total_trades') or 0):>3} "
            f"PF={bbt.get('profit_factor'):>5} "
            f"save={asr.get('status')}{det_flag}"
        )

    # ── Aggregate stats ──
    stats = await get_stability_stats()
    print("\n--- get_stability_stats() rollup ---")
    print(json.dumps(stats, indent=2, default=str))

    # ── Status distribution ──
    statuses = Counter(
        (r["auto_save_result"] or {}).get("status") for r in all_runs
    )
    print("\n--- Auto-save status distribution across all runs ---")
    print(json.dumps(dict(statuses), indent=2))

    # ── Reasons distribution ──
    reasons = Counter(
        (r["auto_save_result"] or {}).get("reason") for r in all_runs
        if (r["auto_save_result"] or {}).get("status") != "saved"
    )
    print("\n--- Rejection reasons distribution ---")
    print(json.dumps(dict(reasons), indent=2))

    # ── Determinism summary ──
    det_cases = {k: v for k, v in case_results.items() if len(v) > 1}
    print("\n--- Determinism check ---")
    for label, runs in det_cases.items():
        ok = _determinism_ok(runs)
        print(f"  {label}: {'PASS' if ok else 'FAIL'} ({len(runs)} iters)")

    # ── Min-trade gate assertion ──
    print("\n--- Min-trade gate behavior ---")
    gate_cases = [r for r in all_runs
                  if (r["auto_save_result"] or {}).get("reason", "").startswith("insufficient_trades")]
    if gate_cases:
        for g in gate_cases:
            asr = g["auto_save_result"]
            print(f"  {g['label']}: trades={asr.get('trades_count')} "
                  f"< {asr.get('min_trades_required')} → correctly rejected")
    else:
        print("  (no low-trade cases hit the gate — check fixtures)")

    # ── Stability log sanity ──
    total = await db[STABILITY_COLL].count_documents({})
    print("\n--- Stability log persistence ---")
    print(f"  {total} rows written to '{STABILITY_COLL}' "
          f"(expected {len(all_runs)})")

    # ── Raw sample (first 2 log docs for illustration) ──
    sample = await list_stability_logs(limit=2)
    print("\n--- Sample stability log entries (latest 2) ---")
    print(json.dumps(sample, indent=2, default=str))

    # ── Library-side check ──
    saved_docs = await db[LIB_COLL].count_documents({"source": "mutation_engine"})
    print("\n--- strategy_library rows tagged source=mutation_engine ---")
    print(f"  {saved_docs}")

    # ── Final verdict ──
    all_det_ok = all(_determinism_ok(v) for v in det_cases.values())
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    print(f"  Runs executed:         {len(all_runs)}")
    print(f"  Determinism cases:     {len(det_cases)}  "
          f"→ {'ALL PASS' if all_det_ok else 'FAIL'}")
    print(f"  Min-trade gate fires:  "
          f"{sum(1 for r in all_runs if (r['auto_save_result'] or {}).get('reason', '').startswith('insufficient_trades'))}")
    print(f"  Stability logs:        {total} (expected {len(all_runs)}) "
          f"→ {'OK' if total == len(all_runs) else 'MISMATCH'}")
    print(f"  Total saved variants:  {saved_docs}")

    # Cleanup (leave the env as we found it).
    await db[STABILITY_COLL].delete_many({})
    await db[LIB_COLL].delete_many({"source": "mutation_engine"})
    print("\n(cleaned validation artifacts)")


if __name__ == "__main__":
    asyncio.run(main())
