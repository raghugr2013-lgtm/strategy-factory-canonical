"""Strategy Market Intelligence — pair × timeframe optimisation.

Additive visibility / scanner layer. Reuses the EXISTING backtest engine
(`engines.backtest_engine.run_backtest_logic`) and EXISTING real-price
loader (`api.dashboard._load_real_prices`). It does NOT touch the
mutation engine, scoring, `_is_eligible`, or the ingestion pipeline.

Persists results to the NEW collection `strategy_market_profile`.

Eligibility rule (defined by the product spec):
    a strategy is considered for scanning when its rollup metrics in
    `strategy_performance_history` satisfy  best_pf >= 1.2 AND runs >= 3.

Scoring (per-cell):
    score = PF * dd_factor * trade_factor * stability_factor
      where dd_factor   = max(0.2, 1 - dd/50)         # 0% DD -> 1, 50% DD -> 0
            trade_factor= min(1.0, trades/50)         # 50+ trades -> full weight
            stability_factor = 0.9 + 0.1*pf/10        # tiny tilt
    A penalty of 0.1 is applied when PF < 1.0.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db
from engines import strategy_memory as sm
from engines.backtest_engine import run_backtest_logic

logger = logging.getLogger(__name__)

PROFILE_COLL = "strategy_market_profile"
ENV_STATS_COLL = "market_environment_stats"

DEFAULT_PAIRS = ["EURUSD", "GBPUSD", "XAUUSD"]
DEFAULT_TIMEFRAMES = ["M30", "H1", "H4"]
OPTIONAL_TIMEFRAMES = ["M15"]

# Eligibility gates (product spec)
MIN_PF_FOR_SCAN = 1.2
MIN_RUNS_FOR_SCAN = 3
MAX_STRATEGIES_PER_CYCLE = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Scoring ──────────────────────────────────────────────────────────

def score_cell(
    *, pf: Optional[float], dd_pct: Optional[float],
    trades: Optional[int], win_rate: Optional[float] = None,
) -> Optional[float]:
    """Return a single-number score for a (pair, tf) cell.
    None when there isn't enough info."""
    if pf is None or dd_pct is None or trades is None:
        return None
    try:
        pf_f = float(pf)
        dd_f = float(dd_pct)
        tr_f = int(trades)
    except (TypeError, ValueError):
        return None
    dd_factor = max(0.2, 1.0 - (dd_f / 50.0))
    trade_factor = min(1.0, tr_f / 50.0) if tr_f > 0 else 0.0
    stability_factor = 0.9 + min(0.1, max(0.0, pf_f / 100.0))
    s = pf_f * dd_factor * trade_factor * stability_factor
    if pf_f < 1.0:
        s *= 0.1  # heavy penalty for losing environments
    return round(s, 4)


# ── Helpers ──────────────────────────────────────────────────────────

async def _load_prices(pair: str, timeframe: str) -> List[float]:
    # Defer import so tests can monkey-patch without triggering dashboard imports
    from api.dashboard import _load_real_prices
    # `_load_real_prices` returns a 3-tuple `(prices, highs, lows)` —
    # market intelligence only needs the close series.
    prices, _highs, _lows = await _load_real_prices(pair.upper(), timeframe.upper())
    return prices


async def _resolve_strategy_text(strategy_hash: str) -> Optional[Dict[str, Any]]:
    rep = await sm.find_representative(strategy_hash)
    if not rep:
        return None
    # Prefer library text if it's mapped to a saved doc
    text = None
    if rep.get("library_id"):
        try:
            from bson import ObjectId
            db = get_db()
            lib = await db[sm.LIBRARY_COLL].find_one(
                {"_id": ObjectId(rep["library_id"])}, {"_id": 0, "strategy_text": 1},
            )
            if lib and lib.get("strategy_text"):
                text = lib["strategy_text"]
        except Exception:
            text = None
    return {
        "strategy_text": text or rep["strategy_text"],
        "name": rep.get("name"),
        "type": rep.get("type"),
        "indicators": rep.get("indicators"),
    }


async def _existing_cell(
    strategy_hash: str, pair: str, timeframe: str,
) -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[PROFILE_COLL].find_one(
        {"strategy_hash": strategy_hash, "pair": pair.upper(), "timeframe": timeframe.upper()},
        {"_id": 0},
    )


# ── Scanner ──────────────────────────────────────────────────────────

async def scan_strategy(
    strategy_hash: str,
    *,
    pairs: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Run the pair × timeframe grid for ONE strategy. Returns a compact
    summary. Missing pair/TF data → `no_data` cell (not an error).
    `force=True` overwrites existing cells."""
    # R3 — route through market_universe_adapter. Byte-identical when
    # flag OFF (the adapter falls back to DEFAULT_PAIRS).
    if pairs is None:
        try:
            from engines.market_universe_adapter import get_intelligence_pairs
            pairs = get_intelligence_pairs()
        except Exception:                                   # pragma: no cover
            pairs = DEFAULT_PAIRS
    pairs = [p.upper() for p in pairs]
    timeframes = [tf.upper() for tf in (timeframes or DEFAULT_TIMEFRAMES)]

    info = await _resolve_strategy_text(strategy_hash)
    if not info:
        return {"status": "not_found", "strategy_hash": strategy_hash}

    db = get_db()
    cells: List[Dict[str, Any]] = []
    no_data: List[str] = []
    skipped: List[str] = []
    errors: List[Dict[str, Any]] = []

    for pair in pairs:
        for tf in timeframes:
            label = f"{pair}/{tf}"
            if not force:
                prev = await _existing_cell(strategy_hash, pair, tf)
                if prev and prev.get("status") == "scored":
                    skipped.append(label)
                    cells.append(prev)
                    continue
            try:
                prices = await _load_prices(pair, tf)
            except Exception as e:
                logger.debug("market-scan price load failed %s: %s", label, e)
                prices = []
            if not prices:
                doc = {
                    "strategy_hash": strategy_hash,
                    "pair": pair,
                    "timeframe": tf,
                    "status": "no_data",
                    "pf": None, "dd_pct": None, "trades": None, "win_rate": None,
                    "score": None,
                    "ts": _now_iso(),
                }
                await db[PROFILE_COLL].update_one(
                    {"strategy_hash": strategy_hash, "pair": pair, "timeframe": tf},
                    {"$set": doc}, upsert=True,
                )
                no_data.append(label)
                cells.append(doc)
                continue

            try:
                bt = run_backtest_logic(
                    strategy_text=info["strategy_text"],
                    pair=pair,
                    timeframe=tf,
                    external_prices=prices,
                    data_source="bid_1m",
                    data_points=len(prices),
                )
            except Exception as e:
                logger.exception("market-scan backtest failed %s", label)
                errors.append({"cell": label, "error": str(e)[:200]})
                continue

            pf = bt.get("profit_factor")
            dd = bt.get("max_drawdown_pct")
            trades = bt.get("total_trades")
            wr = bt.get("win_rate")
            score = score_cell(pf=pf, dd_pct=dd, trades=trades, win_rate=wr)

            doc = {
                "strategy_hash": strategy_hash,
                "pair": pair,
                "timeframe": tf,
                "status": "scored",
                "pf": float(pf) if isinstance(pf, (int, float)) else None,
                "dd_pct": float(dd) if isinstance(dd, (int, float)) else None,
                "trades": int(trades) if isinstance(trades, (int, float)) else None,
                "win_rate": float(wr) if isinstance(wr, (int, float)) else None,
                "score": score,
                "data_points": len(prices),
                "ts": _now_iso(),
                "name": info.get("name"),
                "type": info.get("type"),
            }
            await db[PROFILE_COLL].update_one(
                {"strategy_hash": strategy_hash, "pair": pair, "timeframe": tf},
                {"$set": doc}, upsert=True,
            )
            cells.append(doc)

    # Update aggregate environment stats (learning layer)
    await _update_environment_stats([c for c in cells if c.get("status") == "scored"])

    best = _pick_best(cells)
    return {
        "status": "ok",
        "strategy_hash": strategy_hash,
        "name": info.get("name"),
        "scanned": len(cells),
        "cells": cells,
        "best_environment": best,
        "no_data": no_data,
        "skipped": skipped,
        "errors": errors,
    }


def _pick_best(cells: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    scored = [c for c in cells if c.get("status") == "scored" and isinstance(c.get("score"), (int, float))]
    if not scored:
        return None
    top = max(scored, key=lambda c: c.get("score") or 0.0)
    # Confidence = top_score / max(second, 1e-6) normalised to [0,1]
    scores = sorted([c.get("score") or 0.0 for c in scored], reverse=True)
    if len(scores) > 1 and scores[0] > 0:
        spread = max(0.0, (scores[0] - scores[1])) / scores[0]
    else:
        spread = 1.0
    confidence = round(min(1.0, 0.5 + 0.5 * spread), 3)
    return {
        "pair": top["pair"],
        "timeframe": top["timeframe"],
        "pf": top.get("pf"),
        "dd_pct": top.get("dd_pct"),
        "trades": top.get("trades"),
        "score": top.get("score"),
        "confidence": confidence,
    }


# ── Batch eligible ───────────────────────────────────────────────────

async def _eligible_hashes(limit: int) -> List[Dict[str, Any]]:
    """Return up to `limit` rollups (PF≥1.2 ∧ runs≥3) that do NOT yet have
    at least one `scored` cell in strategy_market_profile. Ordered by
    best_pf desc, stability desc, runs desc."""
    rollups = await sm.get_explorer_rollup(
        min_pf=MIN_PF_FOR_SCAN, min_runs=MIN_RUNS_FOR_SCAN, limit=500,
    )
    if not rollups:
        return []
    db = get_db()
    hashes = [r["strategy_hash"] for r in rollups]
    scanned = set()
    async for d in db[PROFILE_COLL].find(
        {"strategy_hash": {"$in": hashes}, "status": "scored"},
        {"_id": 0, "strategy_hash": 1},
    ):
        scanned.add(d["strategy_hash"])
    pending = [r for r in rollups if r["strategy_hash"] not in scanned]
    return pending[: max(1, int(limit))]


async def scan_eligible(
    *,
    limit: int = MAX_STRATEGIES_PER_CYCLE,
    pairs: Optional[List[str]] = None,
    timeframes: Optional[List[str]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Find up to `limit` eligible strategies and scan each."""
    limit = max(1, min(int(limit), 10))
    candidates = await _eligible_hashes(limit)
    if not candidates and force:
        # If caller forces and nothing is "pending", fall back to the top
        # eligible ones and rescan them.
        candidates = (await sm.get_explorer_rollup(
            min_pf=MIN_PF_FOR_SCAN, min_runs=MIN_RUNS_FOR_SCAN, limit=limit,
        ))[:limit]
    summaries: List[Dict[str, Any]] = []
    for c in candidates:
        try:
            s = await scan_strategy(
                c["strategy_hash"], pairs=pairs, timeframes=timeframes, force=force,
            )
        except Exception as e:
            logger.exception("scan_eligible: failure for %s", c["strategy_hash"])
            s = {"status": "error", "strategy_hash": c["strategy_hash"], "error": str(e)[:200]}
        summaries.append({
            "strategy_hash": c["strategy_hash"],
            "name": c.get("name"),
            "best_environment": s.get("best_environment"),
            "scanned": s.get("scanned"),
            "status": s.get("status"),
            "no_data": s.get("no_data"),
        })
    return {
        "status": "ok",
        "eligible_considered": len(candidates),
        "max_per_cycle": MAX_STRATEGIES_PER_CYCLE,
        "scanned": summaries,
    }


# ── Read-side ────────────────────────────────────────────────────────

async def get_profile(strategy_hash: str) -> Dict[str, Any]:
    db = get_db()
    cursor = db[PROFILE_COLL].find({"strategy_hash": strategy_hash}, {"_id": 0})
    cells = [d async for d in cursor]
    return {
        "strategy_hash": strategy_hash,
        "cells": cells,
        "best_environment": _pick_best(cells),
        "scanned_at": max((c.get("ts") or "" for c in cells), default=None),
    }


async def get_best_environments_map(hashes: List[str]) -> Dict[str, Dict[str, Any]]:
    """Bulk: {hash -> best_environment} for many hashes. Used by Explorer."""
    if not hashes:
        return {}
    db = get_db()
    cursor = db[PROFILE_COLL].find(
        {"strategy_hash": {"$in": list(set(hashes))}}, {"_id": 0},
    )
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    async for d in cursor:
        grouped.setdefault(d["strategy_hash"], []).append(d)
    out: Dict[str, Dict[str, Any]] = {}
    for h, cells in grouped.items():
        best = _pick_best(cells)
        if best:
            out[h] = best
    return out


# ── Environment learning ─────────────────────────────────────────────

async def _update_environment_stats(scored_cells: List[Dict[str, Any]]) -> None:
    """Aggregate avg PF / avg score per (pair, tf) across ALL strategies.
    Stored as flat docs so it's O(n) to read later."""
    if not scored_cells:
        return
    db = get_db()
    by_env: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for c in scored_cells:
        by_env.setdefault((c["pair"], c["timeframe"]), []).append(c)
    for (pair, tf), cells in by_env.items():
        # Recompute from ALL historical cells, not just the fresh ones,
        # to keep the aggregate honest.
        cursor = db[PROFILE_COLL].find(
            {"pair": pair, "timeframe": tf, "status": "scored"},
            {"_id": 0, "pf": 1, "score": 1, "trades": 1},
        )
        pfs: List[float] = []
        scores: List[float] = []
        trades: List[int] = []
        async for d in cursor:
            if isinstance(d.get("pf"), (int, float)):
                pfs.append(float(d["pf"]))
            if isinstance(d.get("score"), (int, float)):
                scores.append(float(d["score"]))
            if isinstance(d.get("trades"), (int, float)):
                trades.append(int(d["trades"]))
        doc = {
            "pair": pair,
            "timeframe": tf,
            "samples": len(pfs),
            "avg_pf": round(sum(pfs) / len(pfs), 4) if pfs else None,
            "avg_score": round(sum(scores) / len(scores), 4) if scores else None,
            "avg_trades": round(sum(trades) / len(trades), 1) if trades else None,
            "max_pf": round(max(pfs), 4) if pfs else None,
            "updated_at": _now_iso(),
        }
        await db[ENV_STATS_COLL].update_one(
            {"pair": pair, "timeframe": tf}, {"$set": doc}, upsert=True,
        )


async def get_environment_rankings(limit: int = 100) -> List[Dict[str, Any]]:
    db = get_db()
    cursor = db[ENV_STATS_COLL].find({}, {"_id": 0})
    rows = [d async for d in cursor]
    rows.sort(key=lambda r: (-(r.get("avg_score") or 0.0), -(r.get("samples") or 0)))
    return rows[: max(1, min(limit, 500))]
