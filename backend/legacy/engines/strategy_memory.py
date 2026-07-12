"""Strategy Memory — visibility + control layer over existing data.

NO changes to mutation, scoring, `_is_eligible`, or `save_strategy`.
This module:

  * Computes a stable `strategy_hash` that identifies "same strategy
    across runs" (sha1 of normalised strategy text + pair + timeframe).
  * Records every mutation outcome to the NEW collection
    `strategy_performance_history` via `record_performance(...)` —
    called additively by ingestion.injector and auto_mutation_runner.
  * Aggregates the history into an Explorer rollup (best_pf, avg_pf,
    last_pf, run_count, stability_score).
  * Reads from the EXISTING `strategy_library` for baseline metrics on
    strategies that were saved by the existing auto-save path.
  * Re-runs a strategy via the EXISTING `run_mutation_pipeline`.
  * Exports a clean strategy card suitable for cBot conversion.
  * Persists `is_favorite` flags in a separate `strategy_favorites`
    collection so we never mutate `strategy_library` docs.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines.strategy_library import COLLECTION as LIBRARY_COLL

logger = logging.getLogger(__name__)

HISTORY_COLL = "strategy_performance_history"
FAVORITES_COLL = "strategy_favorites"

_WS_RE = re.compile(r"\s+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Hash identity ────────────────────────────────────────────────────

def _normalise_text(txt: str) -> str:
    if not txt:
        return ""
    t = txt.strip().lower()
    t = _WS_RE.sub(" ", t)
    # Collapse numeric params so two runs of the same strategy with
    # slightly different param values still hash to the same bucket.
    t = re.sub(r"\b\d+(?:\.\d+)?\b", "N", t)
    return t


def compute_strategy_hash(strategy_text: str, pair: str, timeframe: str) -> str:
    """Stable identifier used across runs. The user's spec suggests
    entry_logic+exit_logic+indicators; we use the full normalised text
    since that already embeds entry/exit/indicators and is always
    available from every pipeline, whereas parsed sub-fields are not."""
    raw = "||".join([
        (pair or "").upper().strip(),
        (timeframe or "").upper().strip(),
        _normalise_text(strategy_text or ""),
    ])
    return hashlib.sha1(raw.encode()).hexdigest()


# ── Recorder ─────────────────────────────────────────────────────────

async def record_performance(
    *,
    strategy_text: str,
    pair: str,
    timeframe: str,
    name: Optional[str] = None,
    type_: Optional[str] = None,
    indicators: Optional[List[str]] = None,
    source: str,                           # "mutation_runner" | "ingestion:<src>" | "manual_rerun" | "dashboard"
    mutation_run_id: Optional[str] = None,
    mutation_type: Optional[str] = None,   # best variant type
    regime: Optional[str] = None,
    pf: Optional[float] = None,
    dd_pct: Optional[float] = None,
    trades: Optional[int] = None,
    win_rate: Optional[float] = None,
    return_pct: Optional[float] = None,
    auto_save_status: Optional[str] = None,
    library_id: Optional[str] = None,
    research_run_id: Optional[str] = None,    # G1 — lineage handle
) -> str:
    """Append one row to `strategy_performance_history`. Returns the
    strategy_hash. Best-effort — never raises out of the caller."""
    h = compute_strategy_hash(strategy_text, pair, timeframe)
    doc = {
        "strategy_hash": h,
        "name": (name or "unnamed")[:200],
        "type": type_ or "unknown",
        "indicators": list(indicators or []),
        "pair": (pair or "").upper(),
        "timeframe": (timeframe or "").upper(),
        "source": source,
        "mutation_run_id": mutation_run_id,
        "mutation_type": mutation_type,
        "regime": regime,
        "pf": float(pf) if isinstance(pf, (int, float)) else None,
        "dd_pct": float(dd_pct) if isinstance(dd_pct, (int, float)) else None,
        "trades": int(trades) if isinstance(trades, (int, float)) else None,
        "win_rate": float(win_rate) if isinstance(win_rate, (int, float)) else None,
        "return_pct": float(return_pct) if isinstance(return_pct, (int, float)) else None,
        "auto_save_status": auto_save_status,
        "library_id": library_id,
        "research_run_id": research_run_id,
        "ts": _now_iso(),
    }
    try:
        db = get_db()
        await db[HISTORY_COLL].insert_one({**doc})
    except Exception as e:
        logger.warning("record_performance failed: %s", e)
    # G1 — attach to lineage doc (best-effort, no-op when rrid is None)
    if research_run_id:
        try:
            from engines import research_lineage
            await research_lineage.attach_child(
                research_run_id, "history_row", h,
            )
            if mutation_run_id:
                await research_lineage.attach_child(
                    research_run_id, "mutation_run", mutation_run_id,
                    extra={"strategy_hash": h, "pf": pf, "library_id": library_id},
                )
            if library_id:
                await research_lineage.attach_child(
                    research_run_id, "library_save", library_id,
                    extra={"strategy_hash": h, "pf": pf, "name": name},
                )
                await research_lineage.append_summary(
                    research_run_id, library_ids=[library_id],
                )
        except Exception as e:                              # pragma: no cover
            logger.debug("[lineage] attach in record_performance failed: %s", e)
    return h


async def record_from_mutation_result(
    *,
    strategy_text: str,
    pair: str,
    timeframe: str,
    source: str,
    mutation_result: Dict[str, Any],
    name: Optional[str] = None,
    type_: Optional[str] = None,
    indicators: Optional[List[str]] = None,
    research_run_id: Optional[str] = None,    # G1 — lineage handle
) -> str:
    """Extract metrics from a `run_mutation_pipeline` return dict and
    write one history row. Returns the strategy_hash."""
    if not isinstance(mutation_result, dict):
        mutation_result = {}
    best = (mutation_result.get("best_variant") or {}) if isinstance(mutation_result, dict) else {}
    bt = best.get("backtest") or {}
    evo = (mutation_result.get("evolution") or {}) if isinstance(mutation_result, dict) else {}
    auto_save = mutation_result.get("auto_save_result") or {}
    return await record_performance(
        strategy_text=strategy_text,
        pair=pair,
        timeframe=timeframe,
        name=name,
        type_=type_,
        indicators=indicators,
        source=source,
        mutation_run_id=mutation_result.get("run_id"),
        mutation_type=best.get("mutation_type"),
        regime=evo.get("regime_type"),
        pf=bt.get("profit_factor"),
        dd_pct=bt.get("max_drawdown_pct"),
        trades=bt.get("total_trades"),
        win_rate=bt.get("win_rate"),
        return_pct=bt.get("total_return_pct"),
        auto_save_status=auto_save.get("status"),
        library_id=auto_save.get("strategy_id"),
        research_run_id=research_run_id,
    )


# ── Aggregator (Explorer rollup) ─────────────────────────────────────

def _safe_stats(values: List[float]) -> Dict[str, Optional[float]]:
    """Return {mean, std, min, max, last} for a numeric series. Stability
    score = 1 / (1 + std/|mean|) clamped to [0,1]; 1.0 = perfectly
    consistent, 0.0 = highly volatile."""
    vs = [float(v) for v in values if isinstance(v, (int, float)) and not math.isnan(float(v))]
    if not vs:
        return {"mean": None, "std": None, "min": None, "max": None, "last": None, "stability": None}
    mean = sum(vs) / len(vs)
    variance = sum((v - mean) ** 2 for v in vs) / len(vs)
    std = math.sqrt(variance)
    denom = abs(mean) if abs(mean) > 1e-9 else 1e-9
    stability = 1.0 / (1.0 + std / denom)
    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "min": round(min(vs), 4),
        "max": round(max(vs), 4),
        "last": round(vs[-1], 4),
        "stability": round(max(0.0, min(1.0, stability)), 4),
    }


async def get_explorer_rollup(
    *,
    source: Optional[str] = None,
    strategy_type: Optional[str] = None,
    min_pf: Optional[float] = None,
    max_dd: Optional[float] = None,
    min_runs: int = 0,
    favorites_only: bool = False,
    limit: int = 500,
) -> List[Dict[str, Any]]:
    """Group `strategy_performance_history` rows by `strategy_hash` and
    return aggregate metrics per group. Merges in `strategy_library`
    info (if the hash maps to a saved doc) and `is_favorite` flags."""
    db = get_db()
    q: Dict[str, Any] = {}
    if source:
        # Allow source = "ingestion" to match "ingestion:*" prefixes.
        q["source"] = {"$regex": f"^{re.escape(source)}"}
    if strategy_type:
        q["type"] = strategy_type
    cursor = db[HISTORY_COLL].find(q, {"_id": 0}).sort("ts", 1)

    groups: Dict[str, Dict[str, Any]] = {}
    async for row in cursor:
        h = row.get("strategy_hash")
        if not h:
            continue
        g = groups.setdefault(h, {
            "strategy_hash": h,
            "name": row.get("name") or "unnamed",
            "type": row.get("type") or "unknown",
            "indicators": row.get("indicators") or [],
            "pair": row.get("pair"),
            "timeframe": row.get("timeframe"),
            "sources": set(),
            "pfs": [],
            "dds": [],
            "trades": [],
            "mutation_types": {},
            "regimes": {},
            "runs": 0,
            "auto_saved_count": 0,
            "first_seen": row.get("ts"),
            "last_seen": row.get("ts"),
            "library_id": row.get("library_id"),
        })
        g["runs"] += 1
        g["last_seen"] = row.get("ts")
        src = row.get("source") or "unknown"
        g["sources"].add(src)
        # Prefer richer name over "unnamed"
        if (not g["name"] or g["name"] == "unnamed") and row.get("name"):
            g["name"] = row["name"]
        if row.get("type") and row["type"] != "unknown":
            g["type"] = row["type"]
        if row.get("indicators"):
            g["indicators"] = row["indicators"]
        if row.get("library_id") and not g["library_id"]:
            g["library_id"] = row["library_id"]
        if isinstance(row.get("pf"), (int, float)):
            g["pfs"].append(float(row["pf"]))
        if isinstance(row.get("dd_pct"), (int, float)):
            g["dds"].append(float(row["dd_pct"]))
        if isinstance(row.get("trades"), (int, float)):
            g["trades"].append(int(row["trades"]))
        mt = row.get("mutation_type")
        if mt:
            g["mutation_types"][mt] = g["mutation_types"].get(mt, 0) + 1
        rg = row.get("regime")
        if rg:
            g["regimes"][rg] = g["regimes"].get(rg, 0) + 1
        if row.get("auto_save_status") == "saved":
            g["auto_saved_count"] += 1

    # Favorites set
    favorites: set = set()
    try:
        async for f in db[FAVORITES_COLL].find({"is_favorite": True}, {"_id": 0, "strategy_hash": 1}):
            if f.get("strategy_hash"):
                favorites.add(f["strategy_hash"])
    except Exception as e:
        logger.debug("favorites lookup failed: %s", e)

    out: List[Dict[str, Any]] = []
    for g in groups.values():
        pf_stats = _safe_stats(g["pfs"])
        dd_stats = _safe_stats(g["dds"])
        tr_stats = _safe_stats(g["trades"])
        entry = {
            "strategy_hash": g["strategy_hash"],
            "name": g["name"],
            "type": g["type"],
            "indicators": g["indicators"],
            "pair": g["pair"],
            "timeframe": g["timeframe"],
            "sources": sorted(g["sources"]),
            "runs": g["runs"],
            "auto_saved_count": g["auto_saved_count"],
            "best_pf": pf_stats["max"],
            "avg_pf": pf_stats["mean"],
            "last_pf": pf_stats["last"],
            "min_pf": pf_stats["min"],
            "best_dd": dd_stats["min"],
            "avg_dd": dd_stats["mean"],
            "last_dd": dd_stats["last"],
            "avg_trades": tr_stats["mean"],
            "stability_score": pf_stats["stability"],
            "mutation_types": g["mutation_types"],
            "regimes": g["regimes"],
            "first_seen": g["first_seen"],
            "last_seen": g["last_seen"],
            "library_id": g["library_id"],
            "is_favorite": g["strategy_hash"] in favorites,
        }
        # Apply filters
        if favorites_only and not entry["is_favorite"]:
            continue
        if entry["runs"] < min_runs:
            continue
        if min_pf is not None and (entry["best_pf"] is None or entry["best_pf"] < min_pf):
            continue
        if max_dd is not None and (entry["best_dd"] is None or entry["best_dd"] > max_dd):
            continue
        out.append(entry)

    # Enrich with library metrics for saved strategies
    lib_ids = [e["library_id"] for e in out if e.get("library_id")]
    if lib_ids:
        try:
            from bson import ObjectId
            obj_ids = []
            for sid in lib_ids:
                try:
                    obj_ids.append(ObjectId(sid))
                except Exception:
                    continue
            cur = db[LIBRARY_COLL].find(
                {"_id": {"$in": obj_ids}},
                {
                    "_id": 1, "verdict": 1, "score": 1,
                    "prop_firm_panel.status": 1, "prop_firm_panel.violations": 1,
                    "pass_probability": 1, "stability_score": 1,
                    "profit_factor": 1, "total_trades": 1,
                    "win_rate": 1, "max_drawdown_pct": 1,
                    "total_return_pct": 1, "expected_value": 1,
                    "oos_holdout": 1,
                    "winning_trades": 1, "losing_trades": 1,
                    "avg_win_usd": 1, "avg_loss_usd": 1,
                    "avg_win_pips": 1, "avg_loss_pips": 1,
                    "style": 1,
                },
            )
            lib_map: Dict[str, Dict[str, Any]] = {}
            async for d in cur:
                lib_map[str(d["_id"])] = {
                    "verdict": d.get("verdict"),
                    "score": d.get("score"),
                    "prop_status": (d.get("prop_firm_panel") or {}).get("status"),
                    "pass_probability": d.get("pass_probability"),
                    "stability_score": d.get("stability_score"),
                    "profit_factor": d.get("profit_factor"),
                    "total_trades": d.get("total_trades"),
                    "win_rate": d.get("win_rate"),
                    "max_drawdown_pct": d.get("max_drawdown_pct"),
                    "total_return_pct": d.get("total_return_pct"),
                    "expected_value": d.get("expected_value"),
                    "oos_holdout": d.get("oos_holdout"),
                    "winning_trades": d.get("winning_trades"),
                    "losing_trades": d.get("losing_trades"),
                    "avg_win_usd": d.get("avg_win_usd"),
                    "avg_loss_usd": d.get("avg_loss_usd"),
                    "avg_win_pips": d.get("avg_win_pips"),
                    "avg_loss_pips": d.get("avg_loss_pips"),
                    "style": d.get("style"),
                }
            for e in out:
                if e.get("library_id") and e["library_id"] in lib_map:
                    e["library"] = lib_map[e["library_id"]]
        except Exception as exc:
            logger.debug("library enrich failed: %s", exc)

    # ── Phase 24 — Validation transparency enrichment ─────────────────
    for e in out:
        _attach_validation_view(e)

    # ── Phase 26.5 — Lifecycle (8-stage) — additive on top of `stage` ──
    # Compute cohort p90 deploy_score ONCE per fetch, reuse for every row.
    cohort_p90: Optional[float] = None
    try:
        from engines.strategy_lifecycle import compute_cohort_p90_deploy_score
        cohort_libs = [e.get("library") or {} for e in out if e.get("library")]
        cohort_p90 = compute_cohort_p90_deploy_score(cohort_libs)
    except Exception as exc:
        logger.debug("cohort p90 compute failed: %s", exc)

    # Phase 27.3 — bulk-fetch persisted lifecycle docs (which hold the
    # BI5 realism block + last-known stage) so the Explorer rollup can
    # surface the realism pill without N+1 round-trips. One Mongo
    # query for the whole page — cheap and additive.
    lifecycle_doc_map: Dict[str, Dict[str, Any]] = {}
    try:
        hashes = [e.get("strategy_hash") for e in out if e.get("strategy_hash")]
        if hashes:
            from engines.strategy_lifecycle import get_lifecycle_map
            lifecycle_doc_map = await get_lifecycle_map(hashes)
    except Exception as exc:
        logger.debug("lifecycle doc map prefetch failed: %s", exc)

    for e in out:
        prior = lifecycle_doc_map.get(e.get("strategy_hash") or "")
        _attach_lifecycle_view(
            e,
            cohort_p90_deploy_score=cohort_p90,
            prior_lifecycle_doc=prior,
        )

    # Rank by best_pf desc, then stability desc, then runs desc
    out.sort(key=lambda e: (
        -(e["best_pf"] or 0),
        -(e["stability_score"] or 0),
        -e["runs"],
    ))
    return out[: max(1, min(limit, 1000))]


# ── Phase 24 — Explorer transparency / validation badges ──────────────

def _safe_num(v) -> Optional[float]:
    if isinstance(v, (int, float)) and v == v:        # not NaN
        return float(v)
    return None


def _attach_validation_view(e: Dict[str, Any]) -> None:
    """Compute the metrics block + badges + validation stage + confidence
    summary that the Explorer renders. Pure function over already-cached
    fields — never re-runs a backtest."""
    lib = e.get("library") or {}
    oos = lib.get("oos_holdout") or {}
    ev = lib.get("expected_value") or {}

    # Source of truth precedence: library (saved) → rollup history.
    total_trades = _safe_num(lib.get("total_trades"))
    if total_trades is None:
        total_trades = _safe_num(e.get("avg_trades"))     # avg trades / run

    is_pf = _safe_num(oos.get("is_pf"))
    if is_pf is None:
        is_pf = _safe_num(lib.get("profit_factor"))
    if is_pf is None:
        is_pf = _safe_num(e.get("best_pf"))

    oos_pf = _safe_num(oos.get("oos_pf"))
    oos_ratio = _safe_num(oos.get("ratio"))
    if oos_ratio is None and is_pf and oos_pf:
        oos_ratio = round(oos_pf / is_pf, 3) if is_pf > 0 else None

    win_rate = _safe_num(lib.get("win_rate"))
    max_dd = _safe_num(lib.get("max_drawdown_pct"))     # 0..1 fraction
    if max_dd is None:
        # rollup avg_dd is in percent (0..100) — normalize to fraction
        rd = _safe_num(e.get("avg_dd"))
        max_dd = (rd / 100.0) if rd is not None else None

    total_return = _safe_num(lib.get("total_return_pct"))
    avg_trade_pct = None
    if total_return is not None and total_trades and total_trades > 0:
        avg_trade_pct = round(total_return / total_trades, 4)

    expectancy = _safe_num(ev.get("expected_value"))
    rrr = _safe_num(ev.get("risk_reward_ratio"))
    breakeven_prob = _safe_num(ev.get("breakeven_probability"))

    pass_prob = _safe_num(lib.get("pass_probability"))
    # Normalize pass_probability to a 0..100 percent (some sources store 0..1).
    pass_prob_pct = pass_prob
    if pass_prob is not None and pass_prob <= 1.0:
        pass_prob_pct = round(pass_prob * 100.0, 1)

    stability = _safe_num(lib.get("stability_score"))
    if stability is None:
        # rollup stability is 0..1 — convert to 0..100 for parity with library_doc
        rs = _safe_num(e.get("stability_score"))
        stability = round(rs * 100.0, 1) if (rs is not None and rs <= 1.0) else rs

    metrics = {
        "total_trades": int(total_trades) if total_trades is not None else None,
        "is_pf": is_pf,
        "oos_pf": oos_pf,
        "oos_ratio": oos_ratio,
        "max_drawdown_pct": max_dd,
        "expectancy": expectancy,
        "avg_trade_pct": avg_trade_pct,
        "win_rate": win_rate,
        "stability_score": stability,
        "pass_probability_pct": pass_prob_pct,
        "risk_reward_ratio": rrr,
        "breakeven_probability": breakeven_prob,
        "total_return_pct": total_return,
    }

    # ── Phase 25 — Behavioral profile, win/loss split, streak, smoothness ──
    _attach_behavior_metrics(metrics, lib, total_trades, win_rate, rrr,
                             total_return, max_dd, stability)

    # ── Badges (additive set) ──
    badges: List[str] = []
    if total_trades is not None and total_trades < 30:
        badges.append("LOW_SAMPLE")
    if oos_ratio is not None and oos_ratio < 0.7:
        badges.append("OOS_WEAK")
    if (
        is_pf is not None and is_pf > 5.0
        and total_trades is not None and total_trades < 20
    ):
        badges.append("OVERFIT_RISK")
    if max_dd is not None and max_dd >= 0.10:
        badges.append("HIGH_DD")
    if (
        max_dd is not None and max_dd < 0.05
        and oos_ratio is not None and oos_ratio > 0.7
        and pass_prob_pct is not None and pass_prob_pct > 60.0
    ):
        badges.append("PROP_SAFE")
    if stability is not None and stability >= 60.0:
        badges.append("STABLE")
    # Phase 25 — equity smoothness (proxy: stability + DD).
    smoothness = (metrics.get("smoothness_label")
                  if isinstance(metrics, dict) else None)
    if smoothness == "SMOOTH":
        badges.append("SMOOTH")
    elif smoothness == "VOLATILE":
        badges.append("VOLATILE")

    # ── Validation stage ──
    has_library = bool(e.get("library_id"))
    runs = int(e.get("runs") or 0)
    if not has_library or runs < 3:
        stage = "exploratory"
    else:
        is_candidate = (
            is_pf is not None and is_pf >= 1.2
            and total_trades is not None and total_trades >= 30
        )
        is_validated = (
            is_candidate
            and oos_ratio is not None and oos_ratio >= 0.7
            and stability is not None and stability >= 60.0
        )
        is_prop_safe = (
            is_validated
            and max_dd is not None and max_dd < 0.05
            and pass_prob_pct is not None and pass_prob_pct >= 60.0
        )
        if is_prop_safe:
            stage = "prop_safe"
        elif is_validated:
            stage = "validated"
        elif is_candidate:
            stage = "candidate"
        else:
            stage = "exploratory"

    # ── Confidence summary (one-line at-a-glance string) ──
    parts: List[str] = []
    if total_trades is not None:
        parts.append(f"{total_trades} trades")
    if win_rate is not None:
        parts.append(f"WR {win_rate:.0f}%")
    if oos_ratio is not None:
        parts.append(f"OOS {oos_ratio:.2f}")
    if max_dd is not None:
        parts.append(f"DD {max_dd * 100:.1f}%")
    if "STABLE" in badges:
        parts.append("stable")
    elif stability is not None:
        parts.append(f"stab {stability:.0f}")
    if pass_prob_pct is not None and pass_prob_pct >= 1.0:
        parts.append(f"PP {pass_prob_pct:.0f}%")
    confidence_summary = " · ".join(parts) if parts else "no validation data"

    e["validation"] = {
        "metrics": metrics,
        "badges": badges,
        "stage": stage,
        "confidence_summary": confidence_summary,
    }


def _attach_lifecycle_view(
    e: Dict[str, Any],
    *,
    cohort_p90_deploy_score: Optional[float] = None,
    prior_lifecycle_doc: Optional[Dict[str, Any]] = None,
) -> None:
    """Phase 26.5 — attach the 8-stage lifecycle alongside the legacy 4-stage
    ``stage`` field. ADDITIVE only — never mutates ``validation.stage``.

    The pure-function call uses the rollup adapter so we don't need to scan
    the full history collection for every Explorer row. BI5 / cBot /
    portfolio inputs are not yet computed (those modules land in later
    phases) — gates fail safely and the strategy stays at PROP_SAFE / ELITE
    max for now.

    Phase 27.3 — when ``prior_lifecycle_doc`` is supplied (typically from
    a bulk prefetch in ``get_explorer_rollup``), the persisted
    ``bi5_realism`` block is fed into the gate computation AND surfaced
    on the validation view so the BI5 realism pill can render without an
    extra round-trip.
    """
    try:
        from engines.strategy_lifecycle import (
            compute_lifecycle_state_from_rollup,
        )
        bi5_block = (prior_lifecycle_doc or {}).get("bi5_realism")
        state = compute_lifecycle_state_from_rollup(
            e,
            cohort_p90_deploy_score=cohort_p90_deploy_score,
            bi5_realism=bi5_block,
            prior_state=prior_lifecycle_doc,
        )
        val = e.setdefault("validation", {})
        val["lifecycle_stage"]      = state["current_stage"]
        val["lifecycle_stage_rank"] = state["stage_rank"]
        val["lifecycle_flags"]      = state["flags"]
        val["lifecycle_cool_down_until"] = state["cool_down_until"]
        # Phase 27.3 — surface the realism block (if persisted) so the
        # frontend pill renders without a second API call.
        if bi5_block:
            val["bi5_realism"] = bi5_block
    except Exception as exc:                            # pragma: no cover
        logger.debug("lifecycle attach failed: %s", exc)


# ── Phase 25 — Behavior, streak, smoothness (cached fields only) ──────

import math as _math  # noqa: E402  (placed here to keep top-of-file edits minimal)


def _attach_behavior_metrics(
    metrics: Dict[str, Any],
    lib: Dict[str, Any],
    total_trades: Optional[float],
    win_rate: Optional[float],
    rrr: Optional[float],
    total_return: Optional[float],
    max_dd: Optional[float],
    stability: Optional[float],
) -> None:
    """Compute win/loss breakdown, behavioral profile, streak metrics, and
    equity-smoothness label using ONLY cached fields.  Mutates ``metrics``
    in-place — no backtest is re-run.

    win_rate is in 0..100 (percent). max_dd is a fraction (0..1).
    stability is in 0..100.
    """
    # ── Wins / losses ────────────────────────────────────────────────
    wins = lib.get("winning_trades")
    losses = lib.get("losing_trades")
    if (wins is None or losses is None) and (
        total_trades is not None and win_rate is not None and win_rate >= 0
    ):
        wins = int(round(total_trades * (win_rate / 100.0)))
        losses = int(total_trades - wins)
    avg_win = _safe_num(lib.get("avg_win_usd")) or _safe_num(lib.get("avg_win_pips"))
    avg_loss = _safe_num(lib.get("avg_loss_usd")) or _safe_num(lib.get("avg_loss_pips"))
    if avg_loss is not None:
        avg_loss = abs(avg_loss)
    metrics["wins"] = int(wins) if wins is not None else None
    metrics["losses"] = int(losses) if losses is not None else None
    metrics["avg_win"] = avg_win
    metrics["avg_loss"] = avg_loss

    # If RR isn't already set but we have avg_win / avg_loss, derive it.
    if (rrr is None or rrr == 0) and avg_win is not None and avg_loss not in (None, 0):
        try:
            rrr = round(avg_win / avg_loss, 3)
            metrics["risk_reward_ratio"] = rrr
        except ZeroDivisionError:
            pass

    # ── Behavioral profile ──────────────────────────────────────────
    style = (lib.get("style") or "").lower() if lib else ""
    metrics["behavioral_profile"] = _classify_behavior(
        win_rate, rrr, total_trades, style,
    )

    # ── Streak metrics (probabilistic from cached win_rate) ─────────
    if win_rate is not None and 0 < win_rate < 100 and total_trades is not None and total_trades > 0:
        loss_p = 1.0 - (win_rate / 100.0)
        try:
            # Expected worst losing run at 95 % confidence over N trades.
            expected_worst = (
                _math.log(0.05) / _math.log(loss_p) if 0 < loss_p < 1 else None
            )
            metrics["expected_max_consec_losses"] = (
                int(_math.ceil(expected_worst)) if expected_worst else None
            )
            # Simple geometric expected average run length.
            metrics["avg_consec_losses"] = round(loss_p / (1.0 - loss_p), 2)
        except (ValueError, ZeroDivisionError):
            metrics["expected_max_consec_losses"] = None
            metrics["avg_consec_losses"] = None
    else:
        metrics["expected_max_consec_losses"] = None
        metrics["avg_consec_losses"] = None

    # ── Recovery factor = total_return / max_dd ─────────────────────
    if total_return is not None and max_dd is not None and max_dd > 0:
        metrics["recovery_factor"] = round((total_return / 100.0) / max_dd, 2)
    else:
        metrics["recovery_factor"] = None

    # ── Equity smoothness label (proxy via stability + DD) ──────────
    metrics["smoothness_label"] = _classify_smoothness(stability, max_dd)


def _classify_behavior(
    win_rate: Optional[float],
    rrr: Optional[float],
    total_trades: Optional[float],
    style: str,
) -> Optional[str]:
    """Heuristic — pure function over 4 cached signals.  Returns one of:
    HIGH_WINRATE_SCALPER · TREND_FOLLOWER · MEAN_REVERSION ·
    ASYMMETRIC_BREAKOUT · LOW_FREQ_SWING · BALANCED · UNCLASSIFIED."""
    if win_rate is None and rrr is None and total_trades is None and not style:
        return None

    s = style or ""
    wr = win_rate
    r = rrr
    n = total_trades

    # Asymmetric breakout — low win-rate, large RR
    if r is not None and r >= 2.5 and wr is not None and wr < 45:
        return "ASYMMETRIC_BREAKOUT"

    # High-winrate scalper — very high win-rate, RR ≤ 1, lots of trades
    if wr is not None and wr >= 65 and (r is None or r <= 1.0) and (n is None or n >= 100):
        return "HIGH_WINRATE_SCALPER"

    # Style-driven hints
    if "scalp" in s and wr is not None and wr >= 55:
        return "HIGH_WINRATE_SCALPER"
    if any(k in s for k in ("trend", "momentum", "follow")):
        return "TREND_FOLLOWER"
    if any(k in s for k in ("mean", "revers", "range")):
        return "MEAN_REVERSION"
    if any(k in s for k in ("breakout", "breakdown", "volatility")):
        return "ASYMMETRIC_BREAKOUT" if (r is not None and r >= 1.8) else "TREND_FOLLOWER"
    if "swing" in s or (n is not None and n < 50 and wr is not None and wr >= 45):
        return "LOW_FREQ_SWING"

    # Generic RR-based classification
    if r is not None and wr is not None:
        if r >= 1.8 and wr < 55:
            return "TREND_FOLLOWER"
        if r <= 1.1 and wr >= 55:
            return "MEAN_REVERSION"

    return "BALANCED"


def _classify_smoothness(
    stability: Optional[float], max_dd: Optional[float],
) -> Optional[str]:
    """Smoothness proxy — uses stability_score (0..100) and DD fraction.
    SMOOTH: stability ≥ 70 AND max_dd < 0.05.
    VOLATILE: stability < 40 OR max_dd ≥ 0.15.
    Otherwise None (label hidden — neither badge fires)."""
    if stability is None and max_dd is None:
        return None
    if stability is not None and stability >= 70 and (max_dd or 0) < 0.05:
        return "SMOOTH"
    if (stability is not None and stability < 40) or (max_dd is not None and max_dd >= 0.15):
        return "VOLATILE"
    return None


async def get_strategy_details(strategy_id: str) -> Optional[Dict[str, Any]]:
    """Cached, research-grade details for the Explorer drawer.

    Pulls the saved library doc + recent performance history.  No
    backtest is re-run; expensive visuals (equity curve, per-trade
    distribution, monthly heat-map) are surfaced as 'click_to_compute'
    placeholders so the Explorer table stays fast.
    """
    db = get_db()
    from bson import ObjectId

    try:
        oid = ObjectId(strategy_id)
    except Exception:
        return None

    doc = await db[LIBRARY_COLL].find_one({"_id": oid})
    if not doc:
        return None

    sid = str(doc["_id"])
    fp = doc.get("fingerprint")

    # Find the strategy_hash that maps to this library_id (history is keyed
    # by hash; library has fingerprint).  Both can match — try library_id
    # first, fall back to fingerprint.
    history_hash: Optional[str] = None
    h_doc = await db[HISTORY_COLL].find_one(
        {"library_id": sid}, {"_id": 0, "strategy_hash": 1},
        sort=[("ts", -1)],
    )
    if h_doc and h_doc.get("strategy_hash"):
        history_hash = h_doc["strategy_hash"]
    elif fp:
        h_doc = await db[HISTORY_COLL].find_one(
            {"strategy_hash": fp}, {"_id": 0, "strategy_hash": 1},
            sort=[("ts", -1)],
        )
        if h_doc:
            history_hash = h_doc["strategy_hash"]

    history_rows: List[Dict[str, Any]] = []
    if history_hash:
        async for r in (
            db[HISTORY_COLL]
            .find({"strategy_hash": history_hash}, {"_id": 0})
            .sort("ts", 1)
            .limit(500)
        ):
            history_rows.append(r)

    pf_series = [
        {"ts": r.get("ts"), "pf": r.get("pf"),
         "dd_pct": r.get("dd_pct"), "trades": r.get("trades"),
         "regime": r.get("regime"), "source": r.get("source")}
        for r in history_rows
    ]

    pfs = [r["pf"] for r in pf_series if isinstance(r["pf"], (int, float))]
    dds = [r["dd_pct"] for r in pf_series if isinstance(r["dd_pct"], (int, float))]
    trades_per_run = [
        r["trades"] for r in pf_series if isinstance(r["trades"], (int, float))
    ]

    rollup_entry = {
        "library_id": sid,
        "library": {
            "verdict": doc.get("verdict"),
            "score": doc.get("score"),
            "prop_status": (doc.get("prop_firm_panel") or {}).get("status"),
            "pass_probability": doc.get("pass_probability"),
            "stability_score": doc.get("stability_score"),
            "profit_factor": doc.get("profit_factor"),
            "total_trades": doc.get("total_trades"),
            "win_rate": doc.get("win_rate"),
            "max_drawdown_pct": doc.get("max_drawdown_pct"),
            "total_return_pct": doc.get("total_return_pct"),
            "expected_value": doc.get("expected_value"),
            "oos_holdout": doc.get("oos_holdout"),
            "winning_trades": doc.get("winning_trades"),
            "losing_trades": doc.get("losing_trades"),
            "avg_win_usd": doc.get("avg_win_usd"),
            "avg_loss_usd": doc.get("avg_loss_usd"),
            "avg_win_pips": doc.get("avg_win_pips"),
            "avg_loss_pips": doc.get("avg_loss_pips"),
            "style": doc.get("style"),
        },
        "runs": len(history_rows),
        "best_pf": max(pfs) if pfs else doc.get("profit_factor"),
        "avg_dd": (sum(dds) / len(dds)) if dds else None,
        "avg_trades": (sum(trades_per_run) / len(trades_per_run)) if trades_per_run else None,
        "stability_score": doc.get("stability_score"),
    }
    _attach_validation_view(rollup_entry)
    # Phase 26.5 / 27.3 — lifecycle view + (when present) BI5 realism
    # block. We pull the persisted lifecycle doc by hash so the
    # realism pill on the details panel renders without a second call.
    try:
        from engines.strategy_lifecycle import get_lifecycle as _get_lc
        prior_doc = await _get_lc(history_hash or fp)
    except Exception:
        prior_doc = None
    _attach_lifecycle_view(rollup_entry, prior_lifecycle_doc=prior_doc)

    notes_blob = (doc.get("validation_report") or {}).get("notes")
    panel = doc.get("prop_firm_panel") or {}

    # Pass-probability narrative reasoning (text only — no recompute).
    reasoning_parts: List[str] = []
    if doc.get("reason"):
        reasoning_parts.append(str(doc["reason"]))
    if isinstance(notes_blob, list):
        reasoning_parts.extend([str(n) for n in notes_blob])
    elif isinstance(notes_blob, str) and notes_blob:
        reasoning_parts.append(notes_blob)
    violations = panel.get("violations") or {}
    triggered = [k for k, v in violations.items() if v]
    if triggered:
        reasoning_parts.append(f"Prop-firm violations triggered: {', '.join(triggered)}")
    if not reasoning_parts:
        reasoning_parts.append("No detailed reasoning recorded.")

    is_oos = doc.get("oos_holdout") or {}

    return {
        "strategy_id": sid,
        "strategy_hash": history_hash or fp,
        "fingerprint": fp,
        "name": doc.get("name") or "unnamed",
        "pair": doc.get("pair"),
        "timeframe": doc.get("timeframe"),
        "style": doc.get("style"),
        "validation": rollup_entry["validation"],
        "is_oos_comparison": {
            "is_pf": is_oos.get("is_pf") or doc.get("profit_factor"),
            "oos_pf": is_oos.get("oos_pf"),
            "ratio": is_oos.get("ratio"),
            "overfit_flagged": is_oos.get("overfit_flagged"),
            "train_candles": is_oos.get("train_candles"),
            "oos_candles": is_oos.get("oos_candles"),
        },
        "expectancy_breakdown": doc.get("expected_value"),
        "prop_firm_panel": panel,
        "validation_report_notes": notes_blob,
        "pass_probability_reasoning": reasoning_parts,
        "history": {
            "runs": len(history_rows),
            "pf_series": pf_series,
            "stats": {
                "best_pf": max(pfs) if pfs else None,
                "avg_pf": (sum(pfs) / len(pfs)) if pfs else None,
                "worst_dd_pct": max(dds) if dds else None,
                "avg_dd_pct": (sum(dds) / len(dds)) if dds else None,
                "avg_trades_per_run": (sum(trades_per_run) / len(trades_per_run))
                                      if trades_per_run else None,
            },
            "trades_per_run_distribution": _bucket_distribution(trades_per_run),
        },
        "computed_visuals": {
            "equity_curve":             {"status": "click_to_compute"},
            "drawdown_curve":           {"status": "click_to_compute"},
            "monthly_performance":      {"status": "click_to_compute"},
            "trade_distribution":       {"status": "click_to_compute"},
        },
    }


def _bucket_distribution(values: List[int], bucket_size: int = 50) -> List[Dict[str, Any]]:
    if not values:
        return []
    buckets: Dict[int, int] = {}
    for v in values:
        k = int(v // bucket_size)
        buckets[k] = buckets.get(k, 0) + 1
    out = []
    for k in sorted(buckets):
        out.append({
            "from": k * bucket_size,
            "to": (k + 1) * bucket_size,
            "count": buckets[k],
        })
    return out


# ── History reader ───────────────────────────────────────────────────

async def get_history(
    strategy_hash: str, *, limit: int = 500,
) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[HISTORY_COLL].find(
        {"strategy_hash": strategy_hash}, {"_id": 0},
    ).sort("ts", 1).limit(max(1, min(limit, 2000)))
    return [d async for d in cur]


async def find_representative(strategy_hash: str) -> Optional[Dict[str, Any]]:
    """Return the most recent history row for a hash, plus a canonical
    strategy_text for the row (re-synthesised from the last cached doc).
    Used by re-run + export."""
    db = get_db()
    row = await db[HISTORY_COLL].find_one(
        {"strategy_hash": strategy_hash}, {"_id": 0}, sort=[("ts", -1)],
    )
    if not row:
        return None
    # Synthesise a simple strategy_text from the recorded fields so the
    # mutation engine can derive variants. Kept deterministic.
    indicators_line = ", ".join(row.get("indicators") or []) or "(unspecified)"
    text = (
        f"STRATEGY: {row.get('name') or 'Saved Strategy'}\n"
        f"TYPE: {row.get('type') or 'unknown'}\n"
        f"INDICATORS: {indicators_line}\n"
        f"PAIR: {row.get('pair')}  TF: {row.get('timeframe')}\n"
        f"SOURCE: {row.get('source')}\n"
        f"ORIGIN: strategy_memory hash {strategy_hash[:8]}"
    )
    row["strategy_text"] = text
    return row


# ── Re-run (calls EXISTING mutation pipeline) ────────────────────────

async def rerun_strategy(strategy_hash: str, *, max_variants: int = 10,
                         auto_save: bool = True, firm: str = "ftmo",
                         strategy_text_override: Optional[str] = None) -> Dict[str, Any]:
    """Trigger a fresh `run_mutation_pipeline` for the given strategy_hash.
    If the hash maps to a saved library doc, we prefer its actual
    strategy_text; otherwise we synthesise one from the recorded fields.
    Records the outcome in history."""
    from engines.mutation_engine import run_mutation_pipeline

    rep = await find_representative(strategy_hash)
    if not rep:
        raise ValueError(f"strategy_hash {strategy_hash} not found in history")

    pair = (rep.get("pair") or "EURUSD").upper()
    timeframe = (rep.get("timeframe") or "H1").upper()
    # Prefer the actual library strategy_text if we have a library_id.
    text = strategy_text_override or ""
    if not text and rep.get("library_id"):
        try:
            from bson import ObjectId
            db = get_db()
            lib = await db[LIBRARY_COLL].find_one(
                {"_id": ObjectId(rep["library_id"])}, {"_id": 0, "strategy_text": 1},
            )
            if lib and lib.get("strategy_text"):
                text = lib["strategy_text"]
        except Exception:
            pass
    if not text:
        text = rep["strategy_text"]

    base = {
        "strategy_text": text,
        "pair": pair,
        "timeframe": timeframe,
        "style": rep.get("type") or "",
    }
    result = await run_mutation_pipeline(
        base,
        max_variants=max_variants,
        prices=None,
        triggered_by="memory_rerun",
        auto_save=auto_save,
        firm=firm,
    )
    await record_from_mutation_result(
        strategy_text=text,
        pair=pair,
        timeframe=timeframe,
        source="manual_rerun",
        mutation_result=result,
        name=rep.get("name"),
        type_=rep.get("type"),
        indicators=rep.get("indicators"),
    )
    return result


# ── Export ───────────────────────────────────────────────────────────

async def export_strategy(strategy_hash: str) -> Dict[str, Any]:
    rep = await find_representative(strategy_hash)
    if not rep:
        raise ValueError(f"strategy_hash {strategy_hash} not found")
    hist = await get_history(strategy_hash, limit=200)
    pfs = [h["pf"] for h in hist if isinstance(h.get("pf"), (int, float))]
    dds = [h["dd_pct"] for h in hist if isinstance(h.get("dd_pct"), (int, float))]
    pf_stats = _safe_stats(pfs)
    dd_stats = _safe_stats(dds)

    # If saved to library, include its canonical strategy_text and metrics
    library_doc = None
    if rep.get("library_id"):
        try:
            from bson import ObjectId
            db = get_db()
            library_doc = await db[LIBRARY_COLL].find_one(
                {"_id": ObjectId(rep["library_id"])}, {"_id": 0},
            )
            if library_doc and "decision" in library_doc:
                # Trim noisy fields for cBot payload
                library_doc = {
                    k: library_doc[k] for k in (
                        "strategy_text", "pair", "timeframe", "style",
                        "parameters", "verdict", "score",
                        "profit_factor", "max_drawdown_pct", "win_rate",
                        "total_trades", "total_return_pct",
                    ) if k in library_doc
                }
        except Exception:
            library_doc = None

    return {
        "strategy_hash": strategy_hash,
        "name": rep.get("name"),
        "type": rep.get("type"),
        "indicators": rep.get("indicators"),
        "pair": rep.get("pair"),
        "timeframe": rep.get("timeframe"),
        "strategy_text": (library_doc or {}).get("strategy_text") or rep["strategy_text"],
        "performance": {
            "runs": len(hist),
            "best_pf": pf_stats["max"],
            "avg_pf": pf_stats["mean"],
            "last_pf": pf_stats["last"],
            "min_pf": pf_stats["min"],
            "best_dd": dd_stats["min"],
            "avg_dd": dd_stats["mean"],
            "stability_score": pf_stats["stability"],
        },
        "library": library_doc,
        "exported_at": _now_iso(),
        "ready_for_cbot": library_doc is not None,
    }


# ── Favorites ────────────────────────────────────────────────────────

async def set_favorite(strategy_hash: str, is_favorite: bool) -> Dict[str, Any]:
    db = get_db()
    now = _now_iso()
    await db[FAVORITES_COLL].update_one(
        {"strategy_hash": strategy_hash},
        {"$set": {
            "strategy_hash": strategy_hash,
            "is_favorite": bool(is_favorite),
            "updated_at": now,
        }},
        upsert=True,
    )
    return {"strategy_hash": strategy_hash, "is_favorite": bool(is_favorite), "updated_at": now}
