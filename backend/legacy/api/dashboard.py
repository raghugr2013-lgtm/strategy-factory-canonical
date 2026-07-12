"""
Phase 10 — Dashboard Pipeline Endpoint.

POST /api/dashboard/generate

Runs the full productization pipeline end-to-end on real market data and
returns the top-N ranked strategies ready for display in StrategyDashboard.

Flow:
  1. Generate N candidate strategies (existing strategy_engine)
  2. For each: backtest → validation(full, includes WF + holdout + basic)
                        → decision (Phase 8.5)
                        → challenge simulation (Phase 5)
                        → prop_firm_panel (Phase 9)
  3. Rank via strategy_ranking_engine (Phase 8.6)
  4. Refine TOP 3 via refinement_engine (Phase 8.7)
  5. Re-rank with refined versions folded back in
  6. Return {top_strategies, summary, pipeline_log}
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging

from engines.strategy_engine import generate_strategy_text
from engines.backtest_engine import run_backtest_logic, TIMEFRAME_MAP
from engines.validation_engine import run_validation
from engines.decision_engine import decide
from engines.prop_firm_panel import build_prop_firm_panel
from engines.challenge_simulator import simulate_challenge, get_firm_rules
from engines.rule_engine import get_rules_by_slug, rules_to_sim_config
from engines.strategy_ranking_engine import rank_strategies, rank_summary
from engines.refinement_engine import refine_top_candidates
from engines.safety_engine import run_safety_analysis
from engines.db import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Request model ─────────────────────────────────────────────────────

# Phase-1 UI cap — matches the frontend numeric input (1..MAX_STRATEGIES).
MAX_STRATEGIES = 50

# P0 — Minimum candle counts so the pipeline never passes half-loaded
# data into the backtest. Mirror `run_backtest_logic`'s internal gate
# so a clear 422 is returned instead of a `profit_factor: None` cascade
# further downstream.
MIN_CANDLES_FOR_LOAD = 60          # triggers "empty" return from _load_real_prices
MIN_CANDLES_FOR_BACKTEST = 200     # below this we 422 at the route


def _safe_float(v, default: float = 0.0) -> float:
    """Coerce a metric value to float. Used by the P2 optimiser
    before/after comparison block so a `None` or string from any
    upstream path can't break the delta computation."""
    try:
        return float(v) if v is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


class DashboardGenerateRequest(BaseModel):
    pair: str = "EURUSD"
    timeframe: str = "H1"
    style: str = "trend-following"
    count: int = 3              # candidate strategies to generate (keep small for UX)
    firm: str = "ftmo"
    top_n: int = 5              # final dashboard size
    refine_top: int = 2         # refine this many top candidates
    wf_n_windows: int = 3
    wf_num_variants: int = 6
    holdout_num_variants: int = 8
    # Smart-pipeline optimisation: after fast pre-score, run heavy
    # walk-forward validation ONLY on the top K candidates. Remaining
    # candidates keep their light backtest + basic metrics so they still
    # surface in the final ranking, just without OOS validation.
    prefilter_top: int = 10
    # Phase-1 fix: optional safety filter (default 0 = off so existing
    # callers see no behaviour change). Setting >0 drops candidates with
    # `safety.safety_score < min_safety_score` from the final top-N.
    min_safety_score: float = 0.0
    require_safe: bool = False
    # Phase-3 — opt-in parameter optimisation on the final top strategies.
    # When >0, runs `random_search_optimizer.fit_best_params` on the IS
    # slice for the top-K and replays the frozen winner on OOS via
    # `score_frozen_params`. Default 0 = no behaviour change.
    optimize_top: int = 0
    optimize_variants: int = 30
    # P2 — choose optimizer: "random_search" (default, legacy behaviour)
    # or "ga" which calls `engines.ga_optimizer.run_ga_search` with its
    # tournament selection + uniform crossover + gaussian mutation +
    # elitism. For GA, `optimize_variants` is re-interpreted as
    # `population_size × generations` budget (mapped below).
    optimizer: str = "random_search"
    ga_population: int = 20
    ga_generations: int = 8
    # Phase-3 — portfolio combiner. Default-on; emits a `portfolio` block
    # on the response when ≥2 top strategies have usable equity curves.
    enable_portfolio: bool = True
    # P2 — Signal Quality Score filter. Default-OFF (opt-in only). When
    # ON, entries with score < `quality_threshold` are rejected. Score
    # is always computed and exposed via the `phase4` telemetry block,
    # regardless of the filter flag, so the UI can show the filter-out
    # rate before / after the user enables the filter.
    quality_filter: bool = False
    quality_threshold: float = 60.0


# ── Helpers ───────────────────────────────────────────────────────────

async def _load_real_prices(pair: str, timeframe: str) -> tuple:
    """Load OHLC market data. Returns (prices, highs, lows).

    Thin wrapper over `engines.data_access.load_closes` — the canonical
    loader. Keeps the legacy tuple signature for call sites that read
    closes only. Interactive dashboard routes keep today's fail-fast
    behaviour (no auto-recovery) — auto systems use
    `data_access.load_with_recovery` directly.
    """
    from engines.data_access import load_closes
    return await load_closes(pair, timeframe)


async def _resolve_rules(firm: str) -> dict:
    """
    Resolve firm rules with explicit fallback chain (logged for traceability):
      1. DB challenge_rules  (supports both legacy "ftmo" AND Phase-3 slugs like "ftmo_100k_2step")
      2. Legacy preset by the given name
      3. Hard fallback to "ftmo" legacy preset
    """
    requested = (firm or "ftmo").lower()
    rule_doc = await get_rules_by_slug(requested)
    if rule_doc:
        cfg = await rules_to_sim_config(rule_doc)
        logger.info(
            f"[dashboard] rules resolved via challenge_rules DB — slug={requested!r} "
            f"firm_name={rule_doc.get('firm_name')!r} phase={rule_doc.get('phase')!r}"
        )
        assert cfg is not None, "rules_to_sim_config returned None for DB-resolved slug"
        return cfg
    legacy = get_firm_rules(firm)
    if legacy:
        logger.info(f"[dashboard] rules resolved via legacy preset — firm={firm!r}")
        return legacy
    default = get_firm_rules("ftmo")
    logger.warning(
        f"[dashboard] rules fallback to default FTMO preset — requested slug={firm!r} was not found"
    )
    return default


def _summary_metrics(bt: dict) -> dict:
    return {
        "net_profit": bt.get("net_profit", 0),
        "total_return_pct": bt.get("total_return_pct", 0),
        "win_rate": bt.get("win_rate", 0),
        "profit_factor": bt.get("profit_factor", 0),
        "max_drawdown_pct": bt.get("max_drawdown_pct", 0),
        "total_trades": bt.get("total_trades", 0),
    }


def _prescore(bt: dict) -> float:
    """
    Cheap pre-score from basic backtest metrics — used to shortlist
    candidates before running heavy walk-forward validation.

    Components (all 0–25):
      • win_rate contribution       (0 when WR=0, 25 when WR≥60)
      • profit_factor contribution  (0 when PF≤0.5, 25 when PF≥2.0)
      • drawdown penalty inverse    (25 when DD≤2%, 0 when DD≥20%)
      • trade-count sanity          (0 when <5 trades, 25 when ≥30)

    Candidates that didn't produce any trades collapse to 0 and get
    filtered out by the shortlisting step anyway.
    """
    total_trades = int(bt.get("total_trades", 0) or 0)
    if total_trades <= 0:
        return 0.0
    win_rate = float(bt.get("win_rate", 0) or 0)
    profit_factor = float(bt.get("profit_factor", 0) or 0)
    dd_pct = float(bt.get("max_drawdown_pct", 0) or 0)

    wr_pts = max(0.0, min(25.0, (win_rate / 60.0) * 25.0))
    pf_pts = max(0.0, min(25.0, ((profit_factor - 0.5) / 1.5) * 25.0)) if profit_factor > 0 else 0.0
    dd_pts = max(0.0, min(25.0, (1.0 - min(dd_pct, 20.0) / 20.0) * 25.0))
    tc_pts = max(0.0, min(25.0, (total_trades / 30.0) * 25.0))
    return round(wr_pts + pf_pts + dd_pts + tc_pts, 2)


def _backtest_only(
    strategy_text: str,
    pair: str, timeframe: str,
    prices: list,
    highs: list = None,
    lows: list = None,
    sim_config: dict | None = None,
) -> dict:
    """Light stage — backtest + prescore only. No validation / no sim."""
    bt = run_backtest_logic(
        strategy_text, pair, timeframe,
        external_prices=prices,
        external_highs=highs,
        external_lows=lows,
        data_source="real",
        data_points=len(prices),
        sim_config=sim_config,
    )
    trades = bt.get("trades", [])
    return {
        "strategy_text": strategy_text,
        "pair": pair, "timeframe": timeframe,
        "backtest": _summary_metrics(bt),
        "trades": trades,              # kept around for later heavy stages
        "trades_count": len(trades),
        "prescore": _prescore(bt),
        # Phase-1 surface: keep raw safety-relevant numbers + leakage flag
        # for the safety_engine + UI badges to consume downstream.
        "_raw_bt": bt,
    }


def _heavy_stage(
    light: dict,
    rules_config: dict,
    wf_n_windows: int, wf_num_variants: int,
    run_validation_stage: bool,
) -> dict:
    """
    Heavy stage — walk-forward validation + simulation + decision + panel.
    When `run_validation_stage=False` this degrades gracefully: the
    candidate gets a None validation_report (so decision is a basic
    `NO_VALIDATION` stub) while still receiving simulation + panel.
    Output schema matches the original `_process_candidate` exactly.
    """
    strategy_text = light["strategy_text"]
    pair, timeframe = light["pair"], light["timeframe"]
    trades = light.get("trades") or []
    prices = light.get("_prices") or []  # injected by the orchestrator

    validation_report = None
    if run_validation_stage and prices:
        try:
            wf = run_validation(
                strategy_text, pair, timeframe, prices,
                mode="walk_forward",
                wf_n_windows=wf_n_windows,
                wf_num_variants=wf_num_variants,
            )
            from engines.validation_report import build_validation_report
            validation_report = build_validation_report(
                walk_forward=wf, oos_holdout=None, basic=None,
            )
        except Exception as e:
            logger.warning(f"validation failed for candidate: {e}")

    simulation = None
    if trades:
        try:
            simulation = simulate_challenge(trades, rules_config)
        except Exception as e:
            logger.warning(f"simulation failed for candidate: {e}")

    decision_data = decide(
        validation_report=validation_report,
        expected_value=None,
        pass_probability=None,
    )
    panel = build_prop_firm_panel(
        simulation=simulation,
        pass_probability=None,
        validation_report=validation_report,
        decision=decision_data,
    )
    pass_prob = panel.get("pass_probability")

    # Phase-1 fix: surface the safety analysis on every candidate so the
    # dashboard cards + ranking + filtering can consume it.
    safety = None
    raw_bt = light.get("_raw_bt") or {}
    if raw_bt:
        try:
            safety = run_safety_analysis(raw_bt, timeframe=timeframe)
        except Exception as e:
            logger.warning(f"safety analysis failed for candidate: {e}")

    return {
        "strategy_text": strategy_text,
        "pair": pair, "timeframe": timeframe,
        "backtest": light["backtest"],
        "trades_count": light["trades_count"],
        "validation_report": validation_report,
        "decision": decision_data,
        "simulation": simulation,
        "prop_firm_panel": panel,
        "pass_probability": pass_prob,
        "expected_value": None,
        "prescore": light.get("prescore", 0),
        "validation_skipped": not run_validation_stage,
        "safety": safety,
        "_raw_bt": raw_bt,
    }


def _process_candidate(
    strategy_text: str,
    pair: str, timeframe: str,
    prices: list,
    rules_config: dict,
    wf_n_windows: int, wf_num_variants: int, holdout_num_variants: int,
) -> dict:
    """Legacy one-shot path — kept so existing callers / tests keep working."""
    light = _backtest_only(strategy_text, pair, timeframe, prices)
    light["_prices"] = prices
    return _heavy_stage(
        light, rules_config,
        wf_n_windows, wf_num_variants,
        run_validation_stage=True,
    )


def _downsample_curve(curve: list, max_points: int = 60) -> list | None:
    """Reduce an equity curve to ≤ `max_points` samples for UI / portfolio use.

    Uniform stride sampling — always keeps the first and last point so the
    shape is preserved for correlation maths in `analyze_portfolio`.
    Returns ``None`` when the curve is missing or has <2 samples.
    """
    try:
        if not curve or not isinstance(curve, list):
            return None
        if len(curve) <= 2:
            return list(curve)
        if len(curve) <= max_points:
            return list(curve)
        stride = max(1, len(curve) // max_points)
        out = [curve[0]]
        for i in range(stride, len(curve) - 1, stride):
            out.append(curve[i])
        out.append(curve[-1])
        return out
    except Exception:
        return None


def _shrink_for_dashboard(entry: dict, source: dict) -> dict:
    """Trim ranking entry + source into a compact UI-ready card payload."""
    panel = source.get("prop_firm_panel") or {}
    decision = source.get("decision") or {}
    dec_inner = decision.get("decision") if isinstance(decision.get("decision"), dict) else decision
    verdict = dec_inner.get("verdict") if isinstance(dec_inner, dict) else entry.get("verdict")
    safety = source.get("safety") or {}
    raw_bt = source.get("_raw_bt") or {}
    return {
        "rank": entry["rank"],
        "strategy_id": entry["strategy_id"],
        "score": entry["score"],
        "verdict": verdict or entry.get("verdict"),
        "confidence": (dec_inner or {}).get("confidence"),
        "reason": entry.get("reason"),
        "status": panel.get("status"),
        "pass_probability": panel.get("pass_probability"),
        "max_drawdown": panel.get("max_drawdown"),
        "daily_drawdown": panel.get("daily_drawdown"),
        "consistency_score": panel.get("consistency_score"),
        "recommendation": panel.get("recommendation"),
        "pair": source.get("pair"),
        "timeframe": source.get("timeframe"),
        "strategy_text": source.get("strategy_text"),
        "backtest": source.get("backtest"),
        "violations": panel.get("violations"),
        "refined": bool(source.get("_refined")),
        # Phase-1 fix: surface safety + OOS + leakage guard on every card.
        "safety": {
            "safety_score": safety.get("safety_score"),
            "grade": safety.get("grade"),
            "is_safe": safety.get("is_safe"),
            "flags": safety.get("flags") or [],
            "warnings": safety.get("warnings") or [],
        } if safety else None,
        "oos": {
            "total_trades": raw_bt.get("oos_total_trades"),
            "win_rate": raw_bt.get("oos_win_rate"),
            "profit_factor": raw_bt.get("oos_profit_factor"),
            "net_profit": raw_bt.get("oos_net_profit"),
            "max_drawdown_pct": raw_bt.get("oos_max_drawdown_pct"),
        } if raw_bt else None,
        "leakage_guard": raw_bt.get("_leakage_guard") if raw_bt else None,
        # Phase 2 + 3 telemetry — exposed on every card so the UI can
        # render a "phase telemetry" section (regime / ATR / trailing /
        # MTF). Always a thin pluck — never the full _raw_bt.
        "phase2": raw_bt.get("_phase2") if raw_bt else None,
        "phase3": raw_bt.get("_phase3") if raw_bt else None,
        "phase4": raw_bt.get("_phase4_signal_quality") if raw_bt else None,
        "phase5": raw_bt.get("_phase5_risk_calibration") if raw_bt else None,
        # P4 — compact equity curve for the multi-asset portfolio
        # combiner. Downsampled to ≤60 points to keep payloads tight.
        "equity_curve": _downsample_curve(raw_bt.get("equity_curve") or []) if raw_bt else None,
        "initial_balance": raw_bt.get("initial_balance") if raw_bt else None,
    }


# ── Endpoint ──────────────────────────────────────────────────────────

@router.post("/dashboard/generate")
async def dashboard_generate(req: DashboardGenerateRequest):
    """Smart two-stage pipeline: fast prescore → shortlist → heavy validation."""
    import asyncio
    import time
    import uuid as _uuid

    # Phase 14.4 — pipeline log (additive, best-effort).
    from engines.pipeline_logs import log_event as _plog
    run_id = _uuid.uuid4().hex[:12]

    t0 = time.perf_counter()
    pipeline_log: list = []

    def _stage(label: str, start: float):
        elapsed = round(time.perf_counter() - start, 2)
        pipeline_log.append(f"[{elapsed}s] {label}")
        return time.perf_counter()

    await _plog(
        "generation",
        f"Pipeline started · {req.pair}/{req.timeframe} style={req.style} count={req.count}",
        level="info", run_id=run_id, pair=req.pair, timeframe=req.timeframe,
        meta={"firm": req.firm},
    )

    t = time.perf_counter()
    prices, highs, lows = await _load_real_prices(req.pair, req.timeframe)

    # P0 — Strict candle-count gate. The backtest engine requires ≥200
    # bars; below that we return a structured 422 so the UI can show an
    # actionable message instead of a generic 500 / None-PF cascade.
    if len(prices) < MIN_CANDLES_FOR_BACKTEST:
        actual = len(prices)
        data_tf = TIMEFRAME_MAP.get(req.timeframe, req.timeframe.lower())
        msg = (
            f"Insufficient market data for {req.pair}/{req.timeframe} "
            f"(have {actual}, need ≥{MIN_CANDLES_FOR_BACKTEST}). "
            "Download or aggregate more candles via Market Data tab."
        )
        await _plog(
            "generation", msg,
            level="error", run_id=run_id, pair=req.pair, timeframe=req.timeframe,
            meta={"candles_found": actual, "min_required": MIN_CANDLES_FOR_BACKTEST,
                  "timeframe_db": data_tf},
        )
        logger.warning(
            "[data_pipeline] insufficient_candles pair=%s tf=%s tf_db=%s found=%d need=%d",
            req.pair, req.timeframe, data_tf, actual, MIN_CANDLES_FOR_BACKTEST,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "insufficient_data",
                "message": msg,
                "pair": req.pair,
                "timeframe": req.timeframe,
                "timeframe_db": data_tf,
                "candles_found": actual,
                "candles_required": MIN_CANDLES_FOR_BACKTEST,
            },
        )
    t = _stage(f"data loaded — {len(prices)} candles", t)

    # P2 — log signal-quality filter state up-front.
    if req.quality_filter:
        pipeline_log.append(
            f"signal-quality filter ON · threshold={req.quality_threshold}"
        )
    else:
        pipeline_log.append(
            f"signal-quality filter OFF (telemetry only · threshold={req.quality_threshold})"
        )

    rules_config = await _resolve_rules(req.firm)
    t = _stage(f"firm rules resolved — {rules_config.get('name', req.firm)}", t)

    count = max(1, min(int(req.count), MAX_STRATEGIES))

    # P2 — Build a sim_config to pass through to every backtest call so
    # that the Signal Quality filter (opt-in) is consistently applied to
    # IS, OOS, and refinement passes.
    bt_sim_config = {
        "quality_filter": bool(req.quality_filter),
        "quality_threshold": float(req.quality_threshold),
    }

    # ── Stage 1: generate + light backtest (concurrent) ──
    async def _gen_and_light(i: int):
        try:
            strategy_text = await generate_strategy_text(req.pair, req.timeframe, req.style)
        except Exception as e:
            pipeline_log.append(f"candidate {i+1}: generation failed — {e}")
            await _plog("generation", f"Candidate {i+1} generation failed: {e}",
                        level="error", run_id=run_id, pair=req.pair, timeframe=req.timeframe)
            return None
        light = await asyncio.to_thread(
            _backtest_only, strategy_text, req.pair, req.timeframe, prices, highs, lows,
            bt_sim_config,
        )
        light["strategy_id"] = f"cand_{i+1}"
        m = light.get("backtest") or {}
        await _plog(
            "backtest",
            f"cand_{i+1} backtest · PF {m.get('profit_factor')} · "
            f"WR {m.get('win_rate')}% · trades {m.get('total_trades')}",
            level="info", run_id=run_id,
            pair=req.pair, timeframe=req.timeframe,
            strategy_id=light["strategy_id"],
            meta={"prescore": light.get("prescore")},
        )
        return light

    light_items = await asyncio.gather(*[_gen_and_light(i) for i in range(count)])
    light_items = [l for l in light_items if l]
    t = _stage(
        f"stage 1 (generate + backtest) — {len(light_items)}/{count} candidates produced",
        t,
    )
    await _plog(
        "generation",
        f"Generated + backtested {len(light_items)}/{count} candidates",
        level="success" if light_items else "warn",
        run_id=run_id, pair=req.pair, timeframe=req.timeframe,
    )

    if not light_items:
        await _plog("generation", "No candidates produced", level="error",
                    run_id=run_id, pair=req.pair, timeframe=req.timeframe)
        raise HTTPException(status_code=500, detail="No candidates produced.")

    # ── Stage 2: fast pre-score + shortlist ──
    light_items.sort(key=lambda x: x.get("prescore", 0), reverse=True)
    shortlist_size = max(1, min(int(req.prefilter_top), len(light_items)))
    shortlist = light_items[:shortlist_size]
    skipped = light_items[shortlist_size:]

    if shortlist:
        best = shortlist[0]
        pipeline_log.append(
            f"prescore top={best['prescore']} "
            f"(WR={best['backtest'].get('win_rate',0)}% "
            f"PF={best['backtest'].get('profit_factor',0)} "
            f"DD={best['backtest'].get('max_drawdown_pct',0)}%)"
        )
    t = _stage(
        f"stage 2 (prescore) — shortlisted {len(shortlist)} / {len(light_items)}; "
        f"{len(skipped)} skipped for heavy validation",
        t,
    )

    # ── Stage 3: heavy validation on shortlist (concurrent) ──
    async def _heavy(light: dict, run_validation_stage: bool):
        light = {**light, "_prices": prices}
        item = await asyncio.to_thread(
            _heavy_stage, light, rules_config,
            req.wf_n_windows, req.wf_num_variants, run_validation_stage,
        )
        item["strategy_id"] = light["strategy_id"]
        msg = (
            f"{light['strategy_id']}: verdict="
            f"{item['decision']['decision']['verdict']} "
            f"panel={item['prop_firm_panel']['status']} "
            f"prob={item['prop_firm_panel'].get('pass_probability')}"
        )
        if not run_validation_stage:
            msg += " (validation skipped)"
        pipeline_log.append(msg)
        return item

    # Heavy path for shortlisted; light path (sim + panel only, no WF) for the rest
    candidates = await asyncio.gather(
        *[_heavy(l, True) for l in shortlist],
        *[_heavy(l, False) for l in skipped],
    )
    candidates = [c for c in candidates if c]
    t = _stage(
        f"stage 3 (heavy validation) — ran WF on {len(shortlist)}, "
        f"skipped WF on {len(skipped)}",
        t,
    )

    # ── Stage 4: ranking ──
    ranked_initial = rank_strategies(candidates, top_n=len(candidates), attach_panel=False)
    t = _stage(f"stage 4 (initial rank) — {len(ranked_initial)} ranked", t)

    # ── Stage 5: refine top-N (unchanged) ──
    candidates_by_id = {c["strategy_id"]: c for c in candidates}
    refine_input_by_id = {
        c["strategy_id"]: {
            "strategy_text": c["strategy_text"],
            "pair": c["pair"], "timeframe": c["timeframe"],
            "prices": prices,
            "rules_config": rules_config,
            "validation_report": c["validation_report"],
            "decision": c["decision"],
            "prop_firm_panel": c["prop_firm_panel"],
            "backtest": c["backtest"],
        }
        for c in candidates
    }
    refine_top = max(0, min(int(req.refine_top), len(ranked_initial)))

    # Phase-2 — adaptive refinement budget. When the top-K initial verdicts
    # are weak (no TRADE) or scores are below the strong-candidate
    # threshold, escalate refinement to (cycles=3, variants=8, mc=20).
    # Otherwise keep the cheap default (cycles=1, variants=3, mc=8).
    top_slice = ranked_initial[: max(1, refine_top)] if refine_top else ranked_initial[:1]
    has_trade = any((e.get("verdict") or "").upper() == "TRADE" for e in top_slice)
    top_score = max((float(e.get("score") or 0.0) for e in top_slice), default=0.0)
    weak_top = (not has_trade) or (top_score < 60.0)
    if weak_top and refine_top:
        ref_cycles, ref_variants, ref_mc = 3, 8, 20
        ref_top_eff = max(refine_top, min(3, len(ranked_initial)))
    else:
        ref_cycles, ref_variants, ref_mc = 1, 3, 8
        ref_top_eff = refine_top

    refined_results = await asyncio.to_thread(
        refine_top_candidates,
        ranked_initial,
        refine_input_by_id,
        ref_top_eff,
        ref_cycles,
        ref_variants,
        ref_mc,
        bt_sim_config,
    )
    improved = sum(1 for r in refined_results if r.get("improved"))
    t = _stage(
        f"stage 5 (refinement) — attempted {ref_top_eff} (weak={weak_top}, "
        f"cycles={ref_cycles}/variants={ref_variants}/mc={ref_mc}), improved {improved}",
        t,
    )

    # Fold refined back in
    for r in refined_results:
        if not r.get("improved"):
            continue
        sid = r.get("strategy_id")
        refined_bundle = r.get("refined_strategy") or {}
        rs = refined_bundle.get("refined_snapshot") or r.get("refined_snapshot") or {}
        refined_entry = {
            **candidates_by_id[sid],
            "strategy_id": f"{sid}_refined",
            "_refined": True,
            "validation_report": refined_bundle.get("validation_report"),
            "decision": refined_bundle.get("decision"),
            "prop_firm_panel": refined_bundle.get("prop_firm_panel"),
        }
        if rs:
            refined_entry["backtest"] = {
                **candidates_by_id[sid].get("backtest", {}),
                "max_drawdown_pct": rs.get("max_drawdown_pct"),
                "total_return_pct": rs.get("total_return_pct"),
                "profit_factor": rs.get("profit_factor"),
                "win_rate": rs.get("win_rate"),
            }
        refined_entry["pass_probability"] = (refined_entry.get("prop_firm_panel") or {}).get("pass_probability")
        candidates.append(refined_entry)
        candidates_by_id[refined_entry["strategy_id"]] = refined_entry

    # ── Stage 6: safety filter + final ranking ──
    # Phase-1 fix: drop unsafe candidates before final ranking when the
    # caller asked for a min_safety_score floor or `require_safe=True`.
    safety_pool = candidates
    safety_dropped = 0
    if (req.min_safety_score and req.min_safety_score > 0) or req.require_safe:
        kept = []
        for c in candidates:
            sf = c.get("safety") or {}
            score = sf.get("safety_score")
            is_safe = sf.get("is_safe")
            if req.require_safe and is_safe is False:
                safety_dropped += 1
                continue
            if req.min_safety_score and req.min_safety_score > 0:
                if score is None or score < req.min_safety_score:
                    safety_dropped += 1
                    continue
            kept.append(c)
        if kept:
            safety_pool = kept
        # If everything fails the gate, fall back to the unfiltered pool
        # so the user always gets *something* on the dashboard.
        pipeline_log.append(
            f"safety filter — kept {len(safety_pool)}/{len(candidates)}, "
            f"dropped {safety_dropped}"
        )

    final_ranking = rank_strategies(safety_pool, top_n=req.top_n, attach_panel=False)
    if not final_ranking:
        final_ranking = rank_strategies(
            safety_pool, top_n=req.top_n, include_rejects=True, attach_panel=False,
        )
    t = _stage(f"stage 6 (final rank) — top {len(final_ranking)} selected", t)

    top_strategies = [
        _shrink_for_dashboard(entry, candidates_by_id[entry["strategy_id"]])
        for entry in final_ranking
    ]

    # ── Phase-3 / P2 — opt-in parameter optimisation on the final top-K ──
    optimized_count = 0
    optimizer_choice = (req.optimizer or "random_search").lower()
    if optimizer_choice not in ("random_search", "ga"):
        optimizer_choice = "random_search"

    if req.optimize_top and req.optimize_top > 0 and final_ranking:
        opt_k = max(1, min(int(req.optimize_top), len(final_ranking)))
        # Use the same 70/30 split the backtest engine uses internally
        # so the optimisation is strictly comparable with the baseline
        # card's IS/OOS metrics.
        split_idx = int(len(prices) * 0.70)
        train_slice = prices[:split_idx]
        oos_slice = prices[split_idx:]

        # Lazy-import so cold paths don't pay the cost.
        if optimizer_choice == "ga":
            from engines.ga_optimizer import run_ga_search
        else:
            from engines.random_search_optimizer import fit_best_params, score_frozen_params

        for entry, card in zip(final_ranking[:opt_k], top_strategies[:opt_k]):
            try:
                src = candidates_by_id[entry["strategy_id"]]
                strategy_text = src["strategy_text"]

                # Baseline IS/OOS (already on the card — used for the
                # before/after delta reporting below).
                base_bt = card.get("backtest") or {}
                base_oos = card.get("oos") or {}
                before_is_pf = _safe_float(base_bt.get("profit_factor"))
                before_oos_pf = _safe_float(base_oos.get("profit_factor"))

                if optimizer_choice == "ga":
                    # `run_ga_search` does its own 70/30 split + OOS
                    # replay internally, so we pass full `prices`.
                    # P2 — sim_config carries the quality_filter so GA
                    # evaluates inside the same high-quality entry
                    # space as the live system.
                    res = await asyncio.to_thread(
                        run_ga_search,
                        strategy_text, req.pair, req.timeframe, prices,
                        train_ratio=0.70,
                        population_size=int(req.ga_population),
                        generations=int(req.ga_generations),
                        sim_config=bt_sim_config,
                    )
                    if not res.get("success"):
                        logger.info(
                            "GA optimiser skipped %s: %s",
                            entry.get("strategy_id"), res.get("error"),
                        )
                        continue
                    is_metrics = res.get("metrics") or {}
                    oos_metrics = res.get("oos_metrics") or {}
                    # P2 — per-segment signal-quality telemetry from
                    # the GA's IS / OOS evaluations (each metrics dict
                    # carries `_phase4_signal_quality` from the
                    # underlying backtest).
                    is_q = (is_metrics or {}).get("_phase4_signal_quality") or {}
                    oos_q = (oos_metrics or {}).get("_phase4_signal_quality") or {}
                    card["optimized"] = {
                        "optimizer": "ga",
                        "params": res.get("params"),
                        "is_metrics": is_metrics,
                        "is_fitness": res.get("fitness"),
                        "oos_metrics": oos_metrics,
                        "variants_evaluated": (res.get("_ga") or {}).get("evaluations"),
                        "_ga": res.get("_ga"),
                        "_constraints": res.get("_constraints"),
                        # P2-stability — OOS-aware tracking
                        "selection_score": res.get("selection_score"),
                        "pf_gap": res.get("pf_gap"),
                        # P2 — explicit before/after comparison block.
                        "comparison": {
                            "before_is_pf": before_is_pf,
                            "after_is_pf": _safe_float(is_metrics.get("profit_factor")),
                            "before_oos_pf": before_oos_pf,
                            "after_oos_pf": _safe_float(oos_metrics.get("profit_factor")),
                            "is_pf_delta": round(
                                _safe_float(is_metrics.get("profit_factor"))
                                - before_is_pf, 3),
                            "oos_pf_delta": round(
                                _safe_float(oos_metrics.get("profit_factor"))
                                - before_oos_pf, 3),
                            # PF gap (IS − OOS) for the optimised params.
                            # Positive = overfit toward IS, ideally near 0.
                            "pf_gap": round(
                                _safe_float(is_metrics.get("profit_factor"))
                                - _safe_float(oos_metrics.get("profit_factor")),
                                3),
                        },
                        # P2 — quality-aware optimization telemetry.
                        # Surfaces the avg score and filter % observed
                        # WHILE the optimizer searched.
                        "signal_quality": {
                            "filter_enabled": bt_sim_config.get("quality_filter"),
                            "threshold": bt_sim_config.get("quality_threshold"),
                            "is_avg_score": is_q.get("is_avg_score"),
                            "is_filter_pct": is_q.get("is_quality_filter_pct"),
                            "oos_avg_score": oos_q.get("oos_avg_score") or oos_q.get("is_avg_score"),
                            "oos_filter_pct": oos_q.get("oos_quality_filter_pct") or oos_q.get("is_quality_filter_pct"),
                        },
                    }
                else:
                    # P2 — pass sim_config (quality filter) to both IS
                    # fit and OOS scoring so the optimizer evaluates
                    # inside the same high-quality entry space.
                    fit = await asyncio.to_thread(
                        fit_best_params,
                        strategy_text, req.pair, req.timeframe, train_slice,
                        int(req.optimize_variants),
                        sim_config=bt_sim_config,
                    )
                    if not fit.get("success"):
                        continue
                    oos = await asyncio.to_thread(
                        score_frozen_params,
                        strategy_text, req.pair, req.timeframe, oos_slice,
                        fit["params"], fit["strategy_type"],
                        sim_config=bt_sim_config,
                    )
                    is_metrics = fit.get("metrics") or {}
                    oos_metrics = oos.get("metrics") if oos.get("success") else {}
                    is_q = (is_metrics or {}).get("_phase4_signal_quality") or {}
                    oos_q = (oos_metrics or {}).get("_phase4_signal_quality") or {}
                    card["optimized"] = {
                        "optimizer": "random_search",
                        "params": fit.get("params"),
                        "is_metrics": is_metrics,
                        "is_fitness": fit.get("fitness"),
                        "oos_metrics": oos_metrics,
                        "variants_evaluated": fit.get("variants_evaluated"),
                        "comparison": {
                            "before_is_pf": before_is_pf,
                            "after_is_pf": _safe_float(is_metrics.get("profit_factor")),
                            "before_oos_pf": before_oos_pf,
                            "after_oos_pf": _safe_float(oos_metrics.get("profit_factor")),
                            "is_pf_delta": round(
                                _safe_float(is_metrics.get("profit_factor"))
                                - before_is_pf, 3),
                            "oos_pf_delta": round(
                                _safe_float(oos_metrics.get("profit_factor"))
                                - before_oos_pf, 3),
                        },
                        "signal_quality": {
                            "filter_enabled": bt_sim_config.get("quality_filter"),
                            "threshold": bt_sim_config.get("quality_threshold"),
                            "is_avg_score": is_q.get("is_avg_score"),
                            "is_filter_pct": is_q.get("is_quality_filter_pct"),
                            "oos_avg_score": oos_q.get("oos_avg_score") or oos_q.get("is_avg_score"),
                            "oos_filter_pct": oos_q.get("oos_quality_filter_pct") or oos_q.get("is_quality_filter_pct"),
                        },
                    }
                optimized_count += 1
            except Exception as e:
                logger.warning(
                    "optimise_top (%s) failed for %s: %s",
                    optimizer_choice, entry.get("strategy_id"), e,
                )
        if optimized_count:
            if optimizer_choice == "ga":
                budget = req.ga_population * req.ga_generations
                pipeline_log.append(
                    f"phase-3 optimisation — GA on {optimized_count}/{opt_k} "
                    f"top strategies (pop={req.ga_population}, "
                    f"gens={req.ga_generations}, budget≈{budget})"
                )
            else:
                pipeline_log.append(
                    f"phase-3 optimisation — random search on {optimized_count}/{opt_k} "
                    f"top strategies (variants={req.optimize_variants})"
                )

    # ── Phase-3 — portfolio combiner ──
    portfolio_block = None
    if req.enable_portfolio and len(top_strategies) >= 2:
        try:
            from engines.portfolio_combiner import combine_top_strategies

            cards_with_raw = []
            for card in top_strategies:
                src = candidates_by_id.get(card.get("strategy_id")) or {}
                cards_with_raw.append({**card, "_raw_bt": src.get("_raw_bt") or {}})
            combo = await asyncio.to_thread(
                combine_top_strategies, cards_with_raw, top_n=len(cards_with_raw),
            )
            if combo.get("success"):
                p = combo["portfolio"] or {}
                portfolio_block = {
                    "num_strategies": p.get("num_strategies"),
                    "combined_metrics": p.get("combined_metrics"),
                    "avg_correlation": p.get("avg_correlation"),
                    "diversification_grade": p.get("diversification_grade"),
                    "portfolio_risk_score": p.get("portfolio_risk_score"),
                    "allocations": p.get("allocations"),
                    "suggested_allocations": p.get("suggested_allocations"),
                    "high_corr_pairs": p.get("high_corr_pairs"),
                    "warnings": p.get("warnings"),
                    "strategy_ids": combo.get("strategy_ids"),
                }
                pipeline_log.append(
                    f"phase-3 portfolio combiner — {p.get('num_strategies')} strategies, "
                    f"grade={p.get('diversification_grade')}, "
                    f"DD={p.get('combined_metrics', {}).get('max_drawdown_pct')}%"
                )
        except Exception as e:
            logger.warning("portfolio combiner failed: %s", e)
            pipeline_log.append(f"phase-3 portfolio combiner skipped — {e}")

    summary = rank_summary(candidates, top_n=req.top_n)
    verdict_counts = summary.get("verdict_counts", {})

    total_elapsed = round(time.perf_counter() - t0, 2)
    pipeline_log.append(f"TOTAL runtime: {total_elapsed}s")

    # Phase 14.4 — final pipeline log
    vc = verdict_counts or {}
    await _plog(
        "validation",
        f"Pipeline complete · TRADE {vc.get('TRADE', 0)} · "
        f"RISKY {vc.get('RISKY', 0)} · REJECT {vc.get('REJECT', 0)} · "
        f"top_n {len(top_strategies)} · {total_elapsed}s",
        level="success" if (vc.get("TRADE", 0) + vc.get("RISKY", 0)) > 0 else "warn",
        run_id=run_id, pair=req.pair, timeframe=req.timeframe,
        meta={"runtime_sec": total_elapsed, "total_candidates": len(candidates)},
    )

    return {
        "success": True,
        "pair": req.pair,
        "timeframe": req.timeframe,
        "firm": rules_config.get("name", req.firm),
        "candles": len(prices),
        "total_candidates": len(candidates),
        "refined_count": improved,
        "verdict_counts": verdict_counts,
        "top_strategies": top_strategies,
        "portfolio": portfolio_block,
        "pipeline_log": pipeline_log,
        "run_id": run_id,
        # Smart-pipeline telemetry (additive; old fields untouched)
        "timings": {
            "total_seconds": total_elapsed,
            "generated": len(light_items),
            "shortlisted_for_validation": len(shortlist),
            "skipped_validation": len(skipped),
            "optimized_top": optimized_count,
        },
    }



# ══════════════════════════════════════════════════════════════════════
# P4 — Multi-Asset Portfolio Rollout
# ══════════════════════════════════════════════════════════════════════

class MultiAssetGenerateRequest(BaseModel):
    """Request shape for `/dashboard/generate-portfolio`.

    Runs generation + optimization independently per pair, applies a
    per-asset quality gate (5-seed GA baseline, median OOS PF ≥
    threshold), then combines the survivors into a single portfolio
    block with per-asset contribution weights.
    """
    pairs: list[str]
    timeframe: str = "H1"
    style: str = "trend-following"
    firm: str = "ftmo"
    count: int = 3                # candidates per pair
    top_n_per_pair: int = 3       # how many top cards from each pair to pool
    refine_top: int = 0           # keep fast — portfolio mode is already expensive
    optimize_top: int = 0
    optimizer: str = "random_search"
    ga_population: int = 16
    ga_generations: int = 5
    quality_filter: bool = False
    quality_threshold: float = 60.0
    # Asset-gate controls
    gate_enabled: bool = True
    gate_threshold: float = 1.10
    gate_max_dd_pct: float = 30.0
    gate_seeds: list[int] = [7, 42, 101, 314, 2718]
    gate_population: int = 10
    gate_generations: int = 3


@router.post("/dashboard/generate-portfolio")
async def dashboard_generate_portfolio(req: MultiAssetGenerateRequest):
    """Run per-pair pipelines, apply the per-asset gate, and combine.

    Response shape:
        {
          "success": bool,
          "pairs_requested": [...],
          "per_pair": [
            {
              "pair", "timeframe",
              "gate": {..asset-gate result..},
              "passed": bool,
              "top_strategies": [...],     # empty if gate failed
              "candles", "elapsed_seconds",
              "error": str | None
            }
          ],
          "portfolio": {
            "success": bool, "asset_contributions_pct": {PAIR: pct},
            "combined_metrics", "diversification_grade",
            "suggested_allocations", "warnings", ...
          } | None,
          "pipeline_log": [...],
          "run_id": str,
        }
    """
    import asyncio
    import time
    import uuid as _uuid

    run_id = _uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    pipeline_log: list = []

    pairs_unique: list[str] = []
    for p in (req.pairs or []):
        if not isinstance(p, str):
            continue
        pu = p.strip().upper()
        if pu and pu not in pairs_unique:
            pairs_unique.append(pu)

    if len(pairs_unique) < 2:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "need_at_least_two_pairs",
                "pairs_requested": pairs_unique,
                "message": "Multi-asset rollout requires at least 2 unique pairs.",
            },
        )

    pipeline_log.append(
        f"multi-asset — {len(pairs_unique)} pairs · tf={req.timeframe} · "
        f"count/pair={req.count} · gate={'ON' if req.gate_enabled else 'OFF'} "
        f"(median OOS PF ≥ {req.gate_threshold})"
    )

    from engines.multi_asset_portfolio import (
        run_asset_gate, combine_per_pair_cards,
    )

    bt_sim_config = {
        "quality_filter": bool(req.quality_filter),
        "quality_threshold": float(req.quality_threshold),
    }

    per_pair_results: list[dict] = []

    for pair in pairs_unique:
        pair_t0 = time.perf_counter()
        pair_entry: dict = {
            "pair": pair,
            "timeframe": req.timeframe,
            "passed": False,
            "gate": None,
            "top_strategies": [],
            "candles": 0,
            "elapsed_seconds": 0.0,
            "error": None,
        }

        # 1) Load prices for the asset gate + downstream pipeline
        try:
            prices, highs, lows = await _load_real_prices(pair, req.timeframe)
        except Exception as e:
            pair_entry["error"] = f"load_failed: {e}"
            pair_entry["elapsed_seconds"] = round(time.perf_counter() - pair_t0, 2)
            per_pair_results.append(pair_entry)
            pipeline_log.append(f"  {pair}: load failed — {e}")
            continue

        pair_entry["candles"] = len(prices or [])

        if len(prices or []) < MIN_CANDLES_FOR_BACKTEST:
            pair_entry["error"] = (
                f"insufficient_data: have {pair_entry['candles']}, "
                f"need ≥{MIN_CANDLES_FOR_BACKTEST}"
            )
            pair_entry["elapsed_seconds"] = round(time.perf_counter() - pair_t0, 2)
            per_pair_results.append(pair_entry)
            pipeline_log.append(
                f"  {pair}: skipped — {pair_entry['error']}"
            )
            continue

        # 2) Asset gate (optional)
        if req.gate_enabled:
            gate = await asyncio.to_thread(
                run_asset_gate, pair, req.timeframe, prices,
                style=req.style,
                seeds=req.gate_seeds,
                threshold=req.gate_threshold,
                max_dd_pct=req.gate_max_dd_pct,
                population=req.gate_population,
                generations=req.gate_generations,
                sim_config=bt_sim_config,
            )
            pair_entry["gate"] = gate
            if not gate.get("passed"):
                pair_entry["elapsed_seconds"] = round(time.perf_counter() - pair_t0, 2)
                per_pair_results.append(pair_entry)
                pipeline_log.append(
                    f"  {pair}: gate FAIL ({gate.get('reason')}) · "
                    f"median OOS PF={gate.get('median_oos_pf')} · "
                    f"max OOS DD={gate.get('max_oos_dd')}%"
                )
                continue
            pipeline_log.append(
                f"  {pair}: gate PASS · median OOS PF={gate.get('median_oos_pf')} · "
                f"max OOS DD={gate.get('max_oos_dd')}%"
            )

        # 3) Per-pair full pipeline (reuse the existing generator)
        try:
            per_pair_req = DashboardGenerateRequest(
                pair=pair,
                timeframe=req.timeframe,
                style=req.style,
                firm=req.firm,
                count=req.count,
                top_n=req.top_n_per_pair,
                refine_top=req.refine_top,
                optimize_top=req.optimize_top,
                optimizer=req.optimizer,
                ga_population=req.ga_population,
                ga_generations=req.ga_generations,
                enable_portfolio=False,  # pair-level portfolio not needed; we combine later
                quality_filter=req.quality_filter,
                quality_threshold=req.quality_threshold,
            )
            per_pair_res = await dashboard_generate(per_pair_req)
        except HTTPException as he:
            pair_entry["error"] = f"pipeline_failed: {getattr(he, 'detail', he)!r}"
            pair_entry["elapsed_seconds"] = round(time.perf_counter() - pair_t0, 2)
            per_pair_results.append(pair_entry)
            pipeline_log.append(f"  {pair}: pipeline failed — {pair_entry['error']}")
            continue
        except Exception as e:
            logger.warning("per-pair pipeline failed for %s: %s", pair, e)
            pair_entry["error"] = f"pipeline_failed: {e}"
            pair_entry["elapsed_seconds"] = round(time.perf_counter() - pair_t0, 2)
            per_pair_results.append(pair_entry)
            pipeline_log.append(f"  {pair}: pipeline failed — {e}")
            continue

        top = (per_pair_res or {}).get("top_strategies") or []
        pair_entry["top_strategies"] = top
        pair_entry["passed"] = bool(top)
        pair_entry["elapsed_seconds"] = round(time.perf_counter() - pair_t0, 2)
        per_pair_results.append(pair_entry)
        pipeline_log.append(
            f"  {pair}: {len(top)} top strategies ready "
            f"({pair_entry['elapsed_seconds']}s)"
        )

    # 4) Combine survivors — pools cards that have `_raw_bt` so equity
    # curves can be used by the combiner. Since `_shrink_for_dashboard`
    # strips `_raw_bt`, we need to attach a synthetic equity bridge via
    # the backtest summary — `portfolio_combiner` handles both paths.
    combine_input = []
    for entry in per_pair_results:
        if not entry.get("passed"):
            continue
        combine_input.append({
            "pair": entry["pair"],
            "timeframe": entry["timeframe"],
            "passed": True,
            "cards": entry.get("top_strategies") or [],
        })

    portfolio_block = None
    if len(combine_input) >= 2:
        try:
            combo = await asyncio.to_thread(
                combine_per_pair_cards,
                combine_input,
                top_n_per_pair=req.top_n_per_pair,
            )
            if combo.get("success"):
                portfolio_block = combo
                pipeline_log.append(
                    f"portfolio combined — {combo.get('num_strategies')} strategies "
                    f"across {len(combine_input)} assets · "
                    f"grade={combo.get('diversification_grade')}"
                )
            else:
                pipeline_log.append(
                    f"portfolio combine skipped — {combo.get('reason')}"
                )
        except Exception as e:
            logger.warning("multi-asset combine failed: %s", e)
            pipeline_log.append(f"portfolio combine failed — {e}")

    total_elapsed = round(time.perf_counter() - t0, 2)
    pipeline_log.append(f"TOTAL multi-asset runtime: {total_elapsed}s")

    passed_pairs = [e["pair"] for e in per_pair_results if e.get("passed")]
    rejected_pairs = [
        {"pair": e["pair"],
         "reason": (e.get("gate") or {}).get("reason")
                   or ("error" if e.get("error") else "no_top_strategies"),
         "error": e.get("error")}
        for e in per_pair_results if not e.get("passed")
    ]

    return {
        "success": bool(portfolio_block) or bool(passed_pairs),
        "run_id": run_id,
        "pairs_requested": pairs_unique,
        "pairs_passed": passed_pairs,
        "pairs_rejected": rejected_pairs,
        "per_pair": per_pair_results,
        "portfolio": portfolio_block,
        "pipeline_log": pipeline_log,
        "timings": {
            "total_seconds": total_elapsed,
            "pairs_evaluated": len(per_pair_results),
            "pairs_in_portfolio": len(passed_pairs),
        },
    }

# Reverse map: DB timeframe ("1h") → canonical UI timeframe ("H1").
# We always expose the UI-canonical form so the rest of the pipeline
# (which expects H1 / M15 / etc.) keeps working without extra mapping.
_DB_TO_CANONICAL_TF = {
    "1m": "M1", "5m": "M5", "15m": "M15", "30m": "M30",
    "1h": "H1", "4h": "H4", "1d": "D1",
}


@router.get("/dashboard/datasets")
async def dashboard_datasets():
    """Return the inventory of every (pair, timeframe) combination in
    the `market_data` collection along with candle counts + a boolean
    `sufficient` flag so the UI can disable the Generate button before
    the user submits an invalid combination.

    Response shape:
    ```
    {
      "success": true,
      "min_candles": 200,
      "pairs": [
        {
          "pair": "GBPUSD",
          "timeframes": [
            {"tf": "H1", "candles": 6200, "sufficient": true},
            {"tf": "M30", "candles": 12267, "sufficient": true}
          ],
          "total_candles": 18467,
          "has_sufficient_data": true
        },
        ...
      ]
    }
    ```

    Iterated via a single Mongo aggregation so the endpoint is fast
    (≤ 50 ms even on a multi-million candle dataset).
    """
    db = get_db()

    # Aggregate candle counts per (symbol, timeframe).
    pipe = [
        {"$group": {
            "_id": {"symbol": "$symbol", "tf": "$timeframe"},
            "n": {"$sum": 1},
        }},
        {"$sort": {"_id.symbol": 1, "_id.tf": 1}},
    ]
    try:
        docs = [d async for d in db.market_data.aggregate(pipe)]
    except Exception as e:  # pragma: no cover — defensive fallback
        return {"success": False, "error": str(e), "pairs": []}

    grouped: dict = {}
    for d in docs:
        sym = (d.get("_id") or {}).get("symbol")
        tf_db = (d.get("_id") or {}).get("tf")
        n = int(d.get("n") or 0)
        if not sym or not tf_db:
            continue
        canonical_tf = _DB_TO_CANONICAL_TF.get(tf_db, tf_db.upper())
        pair_entry = grouped.setdefault(sym, {
            "pair": sym,
            "timeframes_map": {},  # merged while we iterate
        })
        # A single (symbol, timeframe) can appear under multiple
        # `source` values (e.g. bid_1m, bid_5m) — we count the MAX of
        # those slices rather than summing to avoid double-counting
        # overlapping aggregates.
        cur = pair_entry["timeframes_map"].get(canonical_tf, 0)
        if n > cur:
            pair_entry["timeframes_map"][canonical_tf] = n

    pairs = []
    for sym, entry in grouped.items():
        tfs = []
        total = 0
        has_sufficient = False
        for tf, n in sorted(entry["timeframes_map"].items()):
            ok = n >= MIN_CANDLES_FOR_BACKTEST
            if ok:
                has_sufficient = True
            total += n
            tfs.append({"tf": tf, "candles": n, "sufficient": ok})
        if not tfs:
            continue
        pairs.append({
            "pair": sym,
            "timeframes": tfs,
            "total_candles": total,
            "has_sufficient_data": has_sufficient,
        })

    # Sort: pairs with any sufficient data first, then by total candle
    # count DESC (so the UI's default selection lands on the richest
    # pair).
    pairs.sort(key=lambda p: (not p["has_sufficient_data"], -p["total_candles"]))

    return {
        "success": True,
        "min_candles": MIN_CANDLES_FOR_BACKTEST,
        "pairs": pairs,
    }



# ══════════════════════════════════════════════════════════════════════
# P2 — Quality Threshold Calibration
# ══════════════════════════════════════════════════════════════════════

class QualityProfileRequest(BaseModel):
    """Request model for the Signal-Quality calibration endpoint.

    Runs a single lightweight backtest with the quality filter OFF and
    returns the observed score distribution so the UI can suggest a
    data-driven threshold to the user."""
    pair: str = "EURUSD"
    timeframe: str = "H1"
    style: str = "trend-following"
    # Offset added to the IS mean score to derive the recommended
    # threshold. Positive = stricter. Default +5 keeps the suggestion
    # attainable (roughly the top half of observed scores).
    offset: float = 5.0
    # Histogram bucket count (1..20). Defaults to 10 × 10-point buckets.
    histogram_buckets: int = 10


# Style → template strategy text. Keeps the calibration path
# LLM-free and deterministic so users can call it safely at UI
# interaction speed (no API-key cost, no latency jitter).
_CALIB_STRATEGY_TEMPLATES = {
    "trend-following": "EMA(20)/EMA(50) trend-following SL=20 TP=40",
    "mean-reversion":  "RSI(14) mean-reversion buy<30 sell>70 SL=15 TP=25",
    "momentum":        "MACD(12,26,9) momentum RSI(14) SL=20 TP=40",
    "breakout":        "EMA(20) breakout SL=25 TP=50",
}


def _percentile(sorted_values: list, pct: float) -> float | None:
    """Inclusive linear-interpolation percentile. `pct` in [0, 100]."""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    p = max(0.0, min(100.0, float(pct))) / 100.0
    k = p * (len(sorted_values) - 1)
    lo = int(k)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = k - lo
    return round(float(sorted_values[lo]) * (1 - frac) + float(sorted_values[hi]) * frac, 2)


def _histogram(scores: list, n_buckets: int) -> list:
    """10-bucket histogram over [0, 100]. Returns
    `[{bucket_start, bucket_end, count}, ...]`. Always has exactly
    `n_buckets` entries so the UI can render a fixed-width bar chart.
    """
    n = max(1, min(20, int(n_buckets or 10)))
    step = 100.0 / n
    buckets = [{"bucket_start": round(i * step, 1),
                "bucket_end":   round((i + 1) * step, 1),
                "count": 0} for i in range(n)]
    for s in scores:
        try:
            v = float(s)
        except (TypeError, ValueError):
            continue
        v = max(0.0, min(100.0, v))
        idx = min(int(v / step), n - 1)
        buckets[idx]["count"] += 1
    return buckets


@router.post("/dashboard/quality-profile")
async def dashboard_quality_profile(req: QualityProfileRequest):
    """P2 — Calibrate the Signal-Quality threshold on live market data.

    Runs a deterministic template backtest on the requested pair /
    timeframe with the quality filter OFF, collects every trade's
    `entry_quality_score`, and returns distribution stats plus a
    recommended threshold.

    Response shape:
    ```
    {
      "success": true,
      "pair": "...", "timeframe": "...", "style": "...",
      "candles": 6200,
      "strategy_template": "EMA(20)/EMA(50) trend-following ...",
      "evaluated": {"is": 103, "oos": 47, "total": 150},
      "avg_score": {"is": 51.2, "oos": 50.8, "combined": 51.0},
      "distribution": {
         "min": 24.5, "max": 87.2,
         "p10": 31.0, "p25": 41.0, "p50": 51.0, "p75": 61.0, "p90": 72.0
      },
      "recommended_threshold": 56.0,
      "offset_applied": 5.0,
      "histogram": [{"bucket_start":0,"bucket_end":10,"count":0}, ...],
      "notes": [ "human-readable guidance" ]
    }
    ```

    Returns 422 when the pair/timeframe has insufficient candles —
    identical contract to `/generate`.
    """
    import time
    t0 = time.perf_counter()

    prices, highs, lows = await _load_real_prices(req.pair, req.timeframe)
    if len(prices) < MIN_CANDLES_FOR_BACKTEST:
        data_tf = TIMEFRAME_MAP.get(req.timeframe, req.timeframe.lower())
        raise HTTPException(
            status_code=422,
            detail={
                "error": "insufficient_data",
                "pair": req.pair,
                "timeframe": req.timeframe,
                "timeframe_db": data_tf,
                "candles_found": len(prices),
                "candles_required": MIN_CANDLES_FOR_BACKTEST,
                "message": (
                    f"Insufficient market data for {req.pair}/{req.timeframe} "
                    f"(have {len(prices)}, need ≥{MIN_CANDLES_FOR_BACKTEST})."
                ),
            },
        )

    strategy_text = _CALIB_STRATEGY_TEMPLATES.get(
        (req.style or "").lower(),
        _CALIB_STRATEGY_TEMPLATES["trend-following"],
    )

    # Filter OFF — we want every signal's score, not just the ones a
    # given threshold would have let through.
    import asyncio
    bt = await asyncio.to_thread(
        run_backtest_logic,
        strategy_text, req.pair, req.timeframe,
        prices, "real", len(prices),
        {"quality_filter": False, "quality_threshold": 0.0},
        None, None, None, None,
        highs, lows,
    )

    trades_is = bt.get("trades") or []
    # OOS trades are consumed inside run_backtest_logic but only a
    # summary surfaces at the top level. Fall back to the phase4 avg
    # score for OOS when per-trade OOS scores are not available.
    p4 = bt.get("_phase4_signal_quality") or {}

    is_scores = [float(t["entry_quality_score"]) for t in trades_is
                 if t.get("entry_quality_score") is not None]
    is_scores.sort()

    all_scores = list(is_scores)

    is_avg = round(sum(is_scores) / len(is_scores), 2) if is_scores else None
    oos_avg = p4.get("oos_avg_score")
    combined_avg = None
    if is_avg is not None and oos_avg is not None:
        # Weight by evaluated counts when available.
        is_n = p4.get("is_quality_evaluated") or len(is_scores) or 1
        oos_n = p4.get("oos_quality_evaluated") or 1
        combined_avg = round(
            (is_avg * is_n + float(oos_avg) * oos_n) / max(1, is_n + oos_n), 2,
        )
    elif is_avg is not None:
        combined_avg = is_avg
    elif oos_avg is not None:
        combined_avg = float(oos_avg)

    distribution = {
        "min": round(min(all_scores), 2) if all_scores else None,
        "max": round(max(all_scores), 2) if all_scores else None,
        "p10": _percentile(is_scores, 10),
        "p25": _percentile(is_scores, 25),
        "p50": _percentile(is_scores, 50),
        "p75": _percentile(is_scores, 75),
        "p90": _percentile(is_scores, 90),
    }

    offset = float(req.offset if req.offset is not None else 5.0)
    if combined_avg is not None:
        recommended = max(0.0, min(100.0, round(combined_avg + offset, 1)))
    else:
        recommended = None

    notes = []
    if is_avg is None and oos_avg is None:
        notes.append(
            "No signals evaluated — strategy template produced zero entries on this "
            "pair/timeframe. Try a different style."
        )
    elif recommended is not None and distribution.get("p75") is not None:
        if recommended > distribution["p75"]:
            notes.append(
                f"Recommended threshold {recommended} is above the 75th percentile — "
                f"expect aggressive filtering (~25% trade-retention)."
            )
        elif distribution.get("p25") is not None and recommended < distribution["p25"]:
            notes.append(
                f"Recommended threshold {recommended} is below the 25th percentile — "
                "filter will be very permissive."
            )

    return {
        "success": True,
        "pair": req.pair,
        "timeframe": req.timeframe,
        "style": req.style,
        "candles": len(prices),
        "strategy_template": strategy_text,
        "evaluated": {
            "is": int(p4.get("is_quality_evaluated") or 0),
            "oos": int(p4.get("oos_quality_evaluated") or 0),
            "total": int((p4.get("is_quality_evaluated") or 0)
                         + (p4.get("oos_quality_evaluated") or 0)),
        },
        "avg_score": {
            "is": is_avg,
            "oos": float(oos_avg) if oos_avg is not None else None,
            "combined": combined_avg,
        },
        "distribution": distribution,
        "recommended_threshold": recommended,
        "offset_applied": offset,
        "histogram": _histogram(is_scores, req.histogram_buckets),
        "notes": notes,
        "elapsed_seconds": round(time.perf_counter() - t0, 2),
    }
