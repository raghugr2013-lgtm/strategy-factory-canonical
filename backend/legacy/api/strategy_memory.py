"""Strategy Memory + Explorer API layer.

This is a thin HTTP shell over `engines.strategy_memory`. NONE of the
underlying mutation / evolution / scoring / ingestion code is touched.
All business logic lives in `engines/strategy_memory.py`.

Endpoints (all prefixed with `/api` by the main app):

    GET   /api/strategies/explorer
    GET   /api/strategies/{hash}/history
    POST  /api/strategies/{hash}/re-run
    GET   /api/strategies/{hash}/export
    GET   /api/strategies/{hash}/export/cbot          (cBot skeleton .cs)
    POST  /api/strategies/{hash}/favorite
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from engines import strategy_memory as sm

logger = logging.getLogger(__name__)

# Mounted at /api/strategies by server.py
router = APIRouter(prefix="/strategies", tags=["strategy-memory"])


# ── Schemas ──────────────────────────────────────────────────────────

class ReRunRequest(BaseModel):
    max_variants: int = Field(10, ge=1, le=20)
    auto_save: bool = True
    firm: str = Field("ftmo", min_length=2, max_length=40)


class FavoriteRequest(BaseModel):
    is_favorite: bool = True


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/explorer")
async def explorer(
    source: Optional[str] = Query(None, description="ingestion | mutation_runner | manual_rerun | dashboard"),
    strategy_type: Optional[str] = Query(None),
    min_pf: Optional[float] = Query(None),
    max_dd: Optional[float] = Query(None),
    min_runs: int = Query(0, ge=0, le=1000),
    favorites_only: bool = Query(False),
    limit: int = Query(500, ge=1, le=1000),
    # Phase 30 — Filtration Honesty (operator default = evidence-only)
    view_mode: str = Query(
        "evidence",
        description="evidence (default — hide null-metric rows) | library | lifecycle | inventory",
    ),
) -> Dict[str, Any]:
    rows = await sm.get_explorer_rollup(
        source=source,
        strategy_type=strategy_type,
        min_pf=min_pf,
        max_dd=max_dd,
        min_runs=min_runs,
        favorites_only=favorites_only,
        limit=limit,
    )
    # Phase 30 — view_mode filter (additive). Defaults hide inventory.
    if view_mode == "evidence":
        rows = [
            r for r in rows
            if r.get("best_pf") is not None
            or (r.get("avg_trades") is not None and float(r["avg_trades"]) > 0)
        ]
    elif view_mode == "library":
        rows = [r for r in rows if r.get("library_id")]
    elif view_mode == "lifecycle":
        try:
            from engines.strategy_lifecycle import get_lifecycle_map, LIFECYCLE_STAGES
            lc_map = await get_lifecycle_map([r["strategy_hash"] for r in rows])
            survivor_stages = set(LIFECYCLE_STAGES[1:])  # everything except exploratory
            rows = [
                r for r in rows
                if (lc_map.get(r["strategy_hash"]) or {}).get("current_stage") in survivor_stages
            ]
        except Exception as e:                              # pragma: no cover
            logger.debug("view_mode=lifecycle filter failed: %s", e)
    # view_mode == "inventory" → no extra filter (raw)
    # Enrich with `best_environment` from strategy_market_profile. This is
    # purely additive — rows without a scan have best_environment=None.
    try:
        from engines.market_intelligence import get_best_environments_map
        envs = await get_best_environments_map([r["strategy_hash"] for r in rows])
        for r in rows:
            r["best_environment"] = envs.get(r["strategy_hash"])
    except Exception as e:  # pragma: no cover
        logger.debug("best_environment enrich failed: %s", e)
    # Enrich with Prop-Firm analysis (default firm = ftmo).
    try:
        from engines.prop_firm_rule_engine import get_analyses_map, DEFAULT_FIRM
        pf_map = await get_analyses_map([r["strategy_hash"] for r in rows], firm_slug=DEFAULT_FIRM)
        for r in rows:
            r["prop_analysis"] = pf_map.get(r["strategy_hash"])
    except Exception as e:  # pragma: no cover
        logger.debug("prop_analysis enrich failed: %s", e)
    # Enrich with Phase 2 challenge matching.
    try:
        from engines.challenge_matching_engine import get_matches_map
        cm_map = await get_matches_map([r["strategy_hash"] for r in rows])
        for r in rows:
            r["challenge_match"] = cm_map.get(r["strategy_hash"])
    except Exception as e:  # pragma: no cover
        logger.debug("challenge_match enrich failed: %s", e)
    return {
        "count": len(rows),
        "strategies": rows,
        "filters_applied": {
            "source": source,
            "strategy_type": strategy_type,
            "min_pf": min_pf,
            "max_dd": max_dd,
            "min_runs": min_runs,
            "favorites_only": favorites_only,
        },
    }


@router.get("/{strategy_hash}/history")
async def history(
    strategy_hash: str,
    limit: int = Query(500, ge=1, le=2000),
) -> Dict[str, Any]:
    rows = await sm.get_history(strategy_hash, limit=limit)
    if not rows:
        raise HTTPException(status_code=404, detail="no history for strategy_hash")
    # Trend summary for the chart client
    pfs = [r.get("pf") for r in rows if isinstance(r.get("pf"), (int, float))]
    dds = [r.get("dd_pct") for r in rows if isinstance(r.get("dd_pct"), (int, float))]
    mutation_type_counts: Dict[str, int] = {}
    for r in rows:
        mt = r.get("mutation_type")
        if mt:
            mutation_type_counts[mt] = mutation_type_counts.get(mt, 0) + 1
    return {
        "strategy_hash": strategy_hash,
        "runs": len(rows),
        "history": rows,
        "summary": {
            "best_pf": max(pfs) if pfs else None,
            "avg_pf": round(sum(pfs) / len(pfs), 4) if pfs else None,
            "last_pf": pfs[-1] if pfs else None,
            "best_dd": min(dds) if dds else None,
            "mutation_type_counts": mutation_type_counts,
        },
    }


# Phase 24 — research-grade details drawer (cached only, no recompute).
@router.get("/library/{strategy_id}/details")
async def strategy_details(strategy_id: str) -> Dict[str, Any]:
    """Cached, research-grade details for the Explorer drawer.

    Returns metrics + badges + IS/OOS comparison + expectancy breakdown +
    pass-probability reasoning + run-level PF history + 'click_to_compute'
    placeholders for expensive visuals (equity curve, monthly heat-map,
    trade distribution). Never re-runs a backtest — Explorer stays fast.
    """
    details = await sm.get_strategy_details(strategy_id)
    if not details:
        raise HTTPException(status_code=404, detail="strategy not found")
    return details



@router.post("/{strategy_hash}/re-run")
async def re_run(strategy_hash: str, req: ReRunRequest) -> Dict[str, Any]:
    try:
        result = await sm.rerun_strategy(
            strategy_hash,
            max_variants=req.max_variants,
            auto_save=req.auto_save,
            firm=req.firm,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("rerun failed for %s", strategy_hash)
        raise HTTPException(status_code=500, detail=f"re-run failed: {type(e).__name__}: {str(e)[:160]}")
    best = (result.get("best_variant") or {}) if isinstance(result, dict) else {}
    bt = best.get("backtest") or {}
    auto_save = result.get("auto_save_result") or {} if isinstance(result, dict) else {}
    return {
        "strategy_hash": strategy_hash,
        "status": result.get("status") if isinstance(result, dict) else None,
        "run_id": result.get("run_id") if isinstance(result, dict) else None,
        "best_mutation_type": best.get("mutation_type"),
        "best_pf": bt.get("profit_factor"),
        "best_dd_pct": bt.get("max_drawdown_pct"),
        "best_trades": bt.get("total_trades"),
        "auto_save_status": auto_save.get("status"),
        "auto_save_reason": auto_save.get("reason"),
        "variants_generated": (result.get("totals") or {}).get("variants_generated") if isinstance(result, dict) else None,
    }


@router.get("/{strategy_hash}/export")
async def export_json(strategy_hash: str) -> Dict[str, Any]:
    try:
        data = await sm.export_strategy(strategy_hash)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    # Additive: attach best_environment from market_intelligence if present.
    try:
        from engines.market_intelligence import get_profile as _mi_profile
        prof = await _mi_profile(strategy_hash)
        data["best_environment"] = prof.get("best_environment")
        data["market_profile_cells"] = prof.get("cells") or []
    except Exception:
        pass
    # Additive: attach Prop-Firm analysis + safe-risk profile.
    try:
        from engines.prop_firm_rule_engine import get_saved_analysis, DEFAULT_FIRM
        saved = await get_saved_analysis(strategy_hash, firm_slug=DEFAULT_FIRM)
        if saved:
            data["prop_analysis"] = saved.get("analysis")
            data["prop_risk_profile"] = saved.get("risk_profile")
    except Exception:
        pass
    return data


@router.get("/{strategy_hash}/export/cbot")
async def export_cbot(
    strategy_hash: str,
    force: bool = False,
    reason: Optional[str] = None,
    renderer: str = Query("auto", regex="^(auto|skeleton|transpiler)$"),
):
    """Return a ready-to-drop-in cAlgo cBot for the strategy.

    Phase 1 P1.2 — Parity-faithful renderer routing:
      • renderer=auto (default) — if a PASSED parity sign-off exists AND
        the strategy IR is locatable, use the sealed Phase 28-C
        ir_transpiler.transpile_ir_to_csharp(...) wrapped with the
        existing safety_injector risk guards. Otherwise fall back to the
        legacy skeleton renderer with a prominent NON-TRADING warning.
      • renderer=transpiler — force the IR transpiler path; 422 if no IR.
      • renderer=skeleton — force the legacy skeleton path (diagnostic
        only; the skeleton's BuySignalCondition/SellSignalCondition
        return false and the resulting cBot does NOT trade).

    Phase 30 — Deployment gating (operator decision):
      • Default: 403 unless lifecycle.current_stage == "deployment_ready".
      • Admin override: ?force=true&reason=<≥8 chars>  → writes an
        audit_log row, returns the file.
    """
    # Phase 30 stage gate (additive, executed BEFORE the existing logic).
    try:
        from engines.strategy_lifecycle import get_lifecycle
        from engines.db import get_db as _get_db
        from datetime import datetime as _dt, timezone as _tz
        lc = await get_lifecycle(strategy_hash)
        stage = (lc or {}).get("current_stage")
        if stage != "deployment_ready":
            if not force:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        f"Phase 30 deployment gate: strategy is at stage="
                        f"{stage or 'none'}, must be 'deployment_ready'. "
                        f"Admin override: ?force=true&reason=<≥8 chars>."
                    ),
                )
            if not reason or len(reason) < 8:
                raise HTTPException(
                    status_code=400,
                    detail="force=true requires reason of ≥8 characters",
                )
            # Audit-log the override (permanent retention per operator decision)
            try:
                await _get_db()["audit_log"].insert_one({
                    "event":          "phase30_cbot_export_force_override",
                    "strategy_hash":  strategy_hash,
                    "stage_at_export": stage,
                    "reason":         reason,
                    "phase":          "30.0",
                    "ts":             _dt.now(_tz.utc).isoformat(),
                })
            except Exception as e:                          # pragma: no cover
                logger.debug("audit_log write failed: %s", e)
    except HTTPException:
        raise
    except Exception as e:                                  # pragma: no cover
        logger.debug("phase30 stage gate non-fatal failure: %s", e)
    try:
        data = await sm.export_strategy(strategy_hash)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Attach best_environment so the cBot banner carries the recommended
    # pair/TF into deployment artifacts.
    try:
        from engines.market_intelligence import get_profile as _mi_profile
        prof = await _mi_profile(strategy_hash)
        data["best_environment"] = prof.get("best_environment")
    except Exception:
        pass

    # Attach prop-firm analysis (default firm = ftmo) for safe_risk /
    # max_daily_loss / max_total_loss embedding in the robot skeleton.
    try:
        from engines.prop_firm_rule_engine import (
            get_saved_analysis, get_normalized_rules, DEFAULT_FIRM,
        )
        saved = await get_saved_analysis(strategy_hash, firm_slug=DEFAULT_FIRM)
        if saved and saved.get("analysis"):
            data["prop_analysis"] = saved["analysis"]
            data["prop_risk_profile"] = saved.get("risk_profile")
            data["prop_rules"] = await get_normalized_rules(DEFAULT_FIRM)
    except Exception:
        pass

    # ── Phase B.2 (soft) — parity sign-off advisory ─────────────
    # Look up parity sign-off FIRST so renderer branching below has it.
    parity_signoff_status = "MISSING"
    parity_fixtures_passed: Optional[int] = None
    parity_htf_mode: Optional[str] = None
    try:
        from engines import cbot_parity as _cp
        signoff = await _cp.get_signoff(strategy_hash)
        if _cp.is_passed(signoff):
            parity_signoff_status = "PASSED"
            parity_fixtures_passed = int(signoff.get("fixtures_passed") or 0) if signoff else None
            parity_htf_mode = (signoff or {}).get("htf_parity_mode")
        elif signoff:
            parity_signoff_status = str(signoff.get("status") or "UNKNOWN")
    except Exception:
        pass

    # ── Phase 1 P1.2 — Renderer routing ────────────────────────────
    # Decide which renderer to use. The IR transpiler is the parity-
    # faithful path; the skeleton is the legacy non-trading template.
    filename_base = _safe_filename(data.get("name"), strategy_hash)
    code: str
    renderer_used: str
    transpiler_warning: Optional[str] = None
    locatable_ir: Optional[Dict[str, Any]] = None

    if renderer in ("auto", "transpiler"):
        try:
            from engines.cbot_parity import _find_ir_for_strategy as _find_ir
            locatable_ir = await _find_ir(strategy_hash)
        except Exception as _e:
            logger.debug("IR lookup failed: %s", _e)

    use_transpiler = (
        renderer == "transpiler"
        or (renderer == "auto"
            and parity_signoff_status == "PASSED"
            and locatable_ir is not None)
    )

    if renderer == "transpiler" and locatable_ir is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "renderer=transpiler requires a locatable Strategy-IR for "
                f"{strategy_hash}. No IR found in library / mutation_events / "
                "lifecycle. Use renderer=auto (default) or omit the param."
            ),
        )

    if use_transpiler:
        try:
            from cbot_engine.ir_transpiler import (
                transpile_ir_to_csharp,
                UnsupportedIROperatorError,
            )
            from engines.safety_injector import inject_safety as _inject_safety

            transp = transpile_ir_to_csharp(
                locatable_ir,
                parity_status=parity_signoff_status,
                parity_fixtures_passed=parity_fixtures_passed,
            )
            raw_csharp = transp["csharp"]
            bot_name = transp.get("bot_name")
            parity_htf_mode = transp.get("htf_parity_mode") or parity_htf_mode

            # Pull prop-firm risk knobs from prop_analysis (already loaded above)
            prop_analysis = data.get("prop_analysis") or {}
            max_daily_loss_pct = float(
                prop_analysis.get("max_daily_loss_pct")
                or (data.get("prop_rules") or {}).get("max_daily_dd_pct")
                or 3.0
            )
            max_spread_pips = float(prop_analysis.get("max_spread_pips") or 3.0)
            risk_percent = float(prop_analysis.get("risk_percent") or 1.0)

            wrapped = _inject_safety(
                raw_csharp,
                bot_name=bot_name,
                risk_percent=risk_percent,
                max_daily_loss_pct=max_daily_loss_pct,
                max_spread_pips=max_spread_pips,
            )
            code = wrapped["code"]

            # Stamp parity + renderer header for trader visibility
            header = (
                "// ════════════════════════════════════════════════════════\n"
                "// PARITY-FAITHFUL EXPORT  (Phase 1 P1.2 renderer routing)\n"
                f"// strategy_hash      : {strategy_hash}\n"
                f"// renderer_used      : ir_transpiler\n"
                f"// parity_signoff     : {parity_signoff_status}\n"
                f"// parity_fixtures    : {parity_fixtures_passed if parity_fixtures_passed is not None else 'N/A'}\n"
                f"// htf_parity_mode    : {parity_htf_mode or 'N/A'}\n"
                f"// safety_injections  : {','.join(wrapped.get('injections') or []) or 'none'}\n"
                "// ════════════════════════════════════════════════════════\n"
            )
            code = header + code
            renderer_used = "ir_transpiler"
        except UnsupportedIROperatorError as _e:
            # Honest fallback to skeleton with the unsupported operator surfaced
            transpiler_warning = f"unsupported_ir_operator: {_e}"
            logger.warning("export_cbot transpiler refused (%s) → skeleton fallback", _e)
            use_transpiler = False
        except Exception as _e:
            transpiler_warning = f"transpiler_error: {_e}"
            logger.exception("export_cbot transpiler failed → skeleton fallback")
            use_transpiler = False

    if not use_transpiler:
        # Legacy skeleton path (non-trading template)
        code = _render_cbot_skeleton(data)
        warning_note = (
            "// ════════════════════════════════════════════════════════\n"
            "// ⚠ NON-TRADING SKELETON  (legacy renderer)\n"
            "// This template does NOT trade — BuySignalCondition() and\n"
            "// SellSignalCondition() both return false. Use only as a\n"
            "// starting point for manual implementation.\n"
            f"// strategy_hash    : {strategy_hash}\n"
            f"// renderer_used    : skeleton\n"
            f"// renderer_reason  : {renderer if renderer != 'auto' else 'no_passed_parity_or_no_ir'}\n"
            f"// parity_signoff   : {parity_signoff_status}\n"
            f"// ir_locatable     : {locatable_ir is not None}\n"
            + (f"// transpiler_warning: {transpiler_warning}\n" if transpiler_warning else "")
            + "// ════════════════════════════════════════════════════════\n"
        )
        code = warning_note + code
        renderer_used = "skeleton"

    filename = filename_base + ".cs"

    # ── Phase 30.1 · Δ2 — Institutional event (subordinate-only) ──
    try:
        from engines.alert_engine import emit_event as _emit_evt
        await _emit_evt(
            "DEPLOYMENT_EXPORTED",
            strategy_hash,
            {
                "filename":          filename,
                "force_override":    bool(force),
                "override_reason":   reason if force else None,
                "pair":              data.get("pair"),
                "timeframe":         data.get("timeframe"),
                "parity_signoff":    parity_signoff_status,
                "renderer_used":     renderer_used,
                "renderer_requested": renderer,
                "htf_parity_mode":   parity_htf_mode,
                "transpiler_warning": transpiler_warning,
            },
        )
    except Exception:                                       # pragma: no cover
        pass

    return PlainTextResponse(
        code,
        media_type="text/x-csharp",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Renderer-Used": renderer_used,
            "X-Parity-Signoff": parity_signoff_status,
        },
    )


@router.post("/{strategy_hash}/favorite")
async def favorite(strategy_hash: str, req: FavoriteRequest) -> Dict[str, Any]:
    return await sm.set_favorite(strategy_hash, req.is_favorite)


# ── cBot skeleton renderer ───────────────────────────────────────────

_CLASS_SAFE = re.compile(r"[^A-Za-z0-9]+")


def _safe_filename(name: Optional[str], strategy_hash: str) -> str:
    base = (name or "Strategy").strip() or "Strategy"
    base = _CLASS_SAFE.sub("_", base).strip("_") or "Strategy"
    return f"{base}_{strategy_hash[:8]}"


def _to_class_name(name: Optional[str], strategy_hash: str) -> str:
    base = (name or "Strategy").strip() or "Strategy"
    base = _CLASS_SAFE.sub("_", base).strip("_") or "Strategy"
    # C# identifiers can't start with a digit
    if base and base[0].isdigit():
        base = "S_" + base
    return f"{base}_{strategy_hash[:8]}"


def _render_cbot_skeleton(data: Dict[str, Any]) -> str:
    name = data.get("name") or "Unnamed Strategy"
    class_name = _to_class_name(name, data.get("strategy_hash") or "")
    pair = (data.get("pair") or "EURUSD").upper()
    timeframe = (data.get("timeframe") or "H1").upper()
    indicators: List[str] = list(data.get("indicators") or [])
    strategy_text = (data.get("strategy_text") or "").strip()
    perf = data.get("performance") or {}
    lib = data.get("library") or {}

    # Build comment block with stats
    def _fmt(v: Any) -> str:
        if v is None:
            return "n/a"
        if isinstance(v, float):
            return f"{v:.3f}"
        return str(v)

    perf_lines = [
        f"//   Runs            : {_fmt(perf.get('runs'))}",
        f"//   Best PF         : {_fmt(perf.get('best_pf'))}",
        f"//   Avg PF          : {_fmt(perf.get('avg_pf'))}",
        f"//   Last PF         : {_fmt(perf.get('last_pf'))}",
        f"//   Best DD %       : {_fmt(perf.get('best_dd'))}",
        f"//   Stability Score : {_fmt(perf.get('stability_score'))}",
    ]

    best_env = data.get("best_environment") or {}
    best_env_lines: List[str] = []
    if best_env:
        best_env_lines = [
            "// RECOMMENDED ENVIRONMENT (from strategy_market_profile):",
            f"//   Best Pair        : {best_env.get('pair')}",
            f"//   Best Timeframe   : {best_env.get('timeframe')}",
            f"//   PF               : {_fmt(best_env.get('pf'))}",
            f"//   DD %             : {_fmt(best_env.get('dd_pct'))}",
            f"//   Trades           : {_fmt(best_env.get('trades'))}",
            f"//   Score            : {_fmt(best_env.get('score'))}",
            f"//   Confidence       : {_fmt(best_env.get('confidence'))}",
        ]

    prop_analysis = data.get("prop_analysis") or {}
    prop_risk = data.get("prop_risk_profile") or {}
    prop_rules = data.get("prop_rules") or {}
    prop_lines: List[str] = []
    if prop_analysis or prop_rules:
        prop_lines = [
            f"// PROP-FIRM ANALYSIS ({(prop_rules.get('firm_name') or prop_rules.get('firm_slug') or 'ftmo').upper()}):",
            f"//   Verdict          : {prop_analysis.get('status') or 'n/a'}",
            f"//   Pass Probability : {_fmt(prop_analysis.get('pass_probability'))}%",
            f"//   Expected Days    : {_fmt(prop_analysis.get('expected_days_to_pass'))}",
            f"//   Risk Level       : {prop_analysis.get('risk_level') or 'n/a'}",
            f"//   Safe Risk/Trade  : {_fmt(prop_risk.get('recommended_risk_per_trade'))}%",
            f"//   Max Daily Loss   : {_fmt(prop_rules.get('max_daily_loss_pct'))}%",
            f"//   Max Total Loss   : {_fmt(prop_rules.get('max_total_loss_pct'))}%",
            f"//   Trailing DD      : {prop_rules.get('trailing_drawdown')}",
        ]

    # Sensible defaults for the risk-protection Robot parameters
    safe_risk = prop_risk.get("recommended_risk_per_trade")
    max_daily = prop_rules.get("max_daily_loss_pct")
    max_total = prop_rules.get("max_total_loss_pct")
    risk_per_trade_default = float(safe_risk) if isinstance(safe_risk, (int, float)) else 0.5
    daily_loss_default = float(max_daily) * 0.8 if isinstance(max_daily, (int, float)) else 4.0
    total_loss_default = float(max_total) * 0.8 if isinstance(max_total, (int, float)) else 8.0

    # Indicator placeholder fields (best-effort common names)
    indicator_fields: List[str] = []
    indicator_init: List[str] = []
    for raw in indicators[:8]:
        tok = _CLASS_SAFE.sub("", str(raw))
        if not tok:
            continue
        lower = tok.lower()
        field_name = f"_{lower}"
        if "rsi" in lower:
            indicator_fields.append(f"        private RelativeStrengthIndex {field_name};")
            indicator_init.append(f"            {field_name} = Indicators.RelativeStrengthIndex(Bars.ClosePrices, RsiPeriods);")
        elif "macd" in lower:
            indicator_fields.append(f"        private MacdCrossOver {field_name};")
            indicator_init.append(f"            {field_name} = Indicators.MacdCrossOver(26, 12, 9);")
        elif "ema" in lower or "movingaverage" in lower or "ma" == lower:
            indicator_fields.append(f"        private ExponentialMovingAverage {field_name};")
            indicator_init.append(f"            {field_name} = Indicators.ExponentialMovingAverage(Bars.ClosePrices, MaPeriods);")
        elif "sma" in lower:
            indicator_fields.append(f"        private SimpleMovingAverage {field_name};")
            indicator_init.append(f"            {field_name} = Indicators.SimpleMovingAverage(Bars.ClosePrices, MaPeriods);")
        elif "atr" in lower:
            indicator_fields.append(f"        private AverageTrueRange {field_name};")
            indicator_init.append(f"            {field_name} = Indicators.AverageTrueRange(14, MovingAverageType.Simple);")
        elif "bollinger" in lower or "bb" == lower:
            indicator_fields.append(f"        private BollingerBands {field_name};")
            indicator_init.append(f"            {field_name} = Indicators.BollingerBands(Bars.ClosePrices, 20, 2, MovingAverageType.Simple);")
        elif "stoch" in lower:
            indicator_fields.append(f"        private StochasticOscillator {field_name};")
            indicator_init.append(f"            {field_name} = Indicators.StochasticOscillator(9, 3, 3, MovingAverageType.Simple);")
        elif "adx" in lower:
            indicator_fields.append(f"        private DirectionalMovementSystem {field_name};")
            indicator_init.append(f"            {field_name} = Indicators.DirectionalMovementSystem(14);")
        else:
            indicator_fields.append(f"        // TODO: indicator '{raw}' — add corresponding cAlgo indicator here")
    if not indicator_fields:
        indicator_fields.append("        // TODO: no indicators detected — add them manually based on strategy_text")

    lib_params = lib.get("parameters") if isinstance(lib, dict) else None
    params_comment = ""
    if lib_params:
        try:
            params_comment = "// PARAMETERS (from mutation):\n// " + "\n// ".join(
                json.dumps(lib_params, indent=2, default=str).splitlines()
            )
        except Exception:
            params_comment = ""

    strategy_text_comment = "\n".join(
        f"// {line}" for line in (strategy_text or "(no strategy text recorded)").splitlines()[:40]
    )

    return f"""// ─────────────────────────────────────────────────────────────────────
// Auto-generated cBot skeleton by AI Strategy Factory (Strategy Memory)
// Strategy Name   : {name}
// Strategy Hash   : {data.get("strategy_hash")}
// Pair / TF       : {pair} / {timeframe}
// Indicators      : {", ".join(indicators) if indicators else "(none detected)"}
// Exported At     : {data.get("exported_at")}
// ─────────────────────────────────────────────────────────────────────
// PERFORMANCE (from strategy_performance_history):
{chr(10).join(perf_lines)}
{chr(10).join(best_env_lines) if best_env_lines else "// RECOMMENDED ENVIRONMENT: (no market-scan yet — run /market-scan to populate)"}
{chr(10).join(prop_lines) if prop_lines else "// PROP-FIRM ANALYSIS: (no analysis yet — POST /prop-analysis to populate)"}
// ─────────────────────────────────────────────────────────────────────
// STRATEGY TEXT:
{strategy_text_comment}
// ─────────────────────────────────────────────────────────────────────
{params_comment}

using System;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.Robots
{{
    [Robot(TimeZone = TimeZones.UTC, AccessRights = AccessRights.None)]
    public class {class_name} : Robot
    {{
        [Parameter("Volume (lots)", DefaultValue = 0.1, MinValue = 0.01, Step = 0.01)]
        public double VolumeLots {{ get; set; }}

        [Parameter("Stop Loss (pips)", DefaultValue = 25, MinValue = 1)]
        public int StopLossPips {{ get; set; }}

        [Parameter("Take Profit (pips)", DefaultValue = 50, MinValue = 1)]
        public int TakeProfitPips {{ get; set; }}

        [Parameter("RSI Periods", DefaultValue = 14, MinValue = 2)]
        public int RsiPeriods {{ get; set; }}

        [Parameter("MA Periods", DefaultValue = 20, MinValue = 2)]
        public int MaPeriods {{ get; set; }}

        // ── PROP-FIRM RISK PROTECTION (additive) ────────────────────
        [Parameter("Risk per trade (%)", DefaultValue = {risk_per_trade_default:.2f}, MinValue = 0.1, MaxValue = 5.0, Step = 0.1)]
        public double RiskPerTradePct {{ get; set; }}

        [Parameter("Max Daily Loss (%)", DefaultValue = {daily_loss_default:.2f}, MinValue = 0.5, MaxValue = 10.0, Step = 0.1)]
        public double MaxDailyLossPct {{ get; set; }}

        [Parameter("Max Total Loss (%)", DefaultValue = {total_loss_default:.2f}, MinValue = 1.0, MaxValue = 20.0, Step = 0.1)]
        public double MaxTotalLossPct {{ get; set; }}

        [Parameter("Auto Stop on Breach", DefaultValue = true)]
        public bool AutoStopOnBreach {{ get; set; }}

{chr(10).join(indicator_fields)}

        private const string Label = "{class_name}";
        private double _dayStartEquity;
        private DateTime _currentDay;
        private double _initialBalance;
        private bool _tradingHalted;

        protected override void OnStart()
        {{
{chr(10).join(indicator_init) if indicator_init else "            // TODO: initialise indicators here"}
            _initialBalance = Account.Balance;
            _dayStartEquity = Account.Equity;
            _currentDay = Server.Time.Date;
            _tradingHalted = false;
            Print("[{class_name}] Risk protection engaged: risk/trade={{0}}%, daily={{1}}%, total={{2}}%",
                RiskPerTradePct, MaxDailyLossPct, MaxTotalLossPct);
        }}

        protected override void OnTick()
        {{
            // Reset daily anchor on new day
            if (Server.Time.Date != _currentDay)
            {{
                _currentDay = Server.Time.Date;
                _dayStartEquity = Account.Equity;
            }}

            if (AutoStopOnBreach && !_tradingHalted)
            {{
                var dailyLossPct = (_dayStartEquity - Account.Equity) / _dayStartEquity * 100.0;
                var totalLossPct = (_initialBalance - Account.Equity) / _initialBalance * 100.0;
                if (dailyLossPct >= MaxDailyLossPct || totalLossPct >= MaxTotalLossPct)
                {{
                    _tradingHalted = true;
                    Print("[{class_name}] BREACH — halting trading. daily={{0}}% total={{1}}%",
                        dailyLossPct, totalLossPct);
                    foreach (var pos in Positions)
                    {{
                        if (pos.Label == Label) ClosePosition(pos);
                    }}
                }}
            }}
        }}

        protected override void OnBar()
        {{
            if (_tradingHalted) return;  // PROP-FIRM GUARD

            // ── ENTRY LOGIC ──────────────────────────────────────────
            // TODO: translate the strategy text above into concrete
            //       buy / sell signals using the initialised indicators.
            //
            // Example (trend-following skeleton):
            //
            //   if (BuySignalCondition())
            //       ExecuteMarketOrder(TradeType.Buy, SymbolName,
            //           Symbol.QuantityToVolumeInUnits(VolumeLots),
            //           Label, StopLossPips, TakeProfitPips);
            //
            //   if (SellSignalCondition())
            //       ExecuteMarketOrder(TradeType.Sell, SymbolName,
            //           Symbol.QuantityToVolumeInUnits(VolumeLots),
            //           Label, StopLossPips, TakeProfitPips);

            // ── EXIT LOGIC ───────────────────────────────────────────
            // Any bespoke exit conditions beyond SL / TP go here.
        }}

        protected override void OnStop()
        {{
            // Clean-up hook — no-op by default.
        }}

        // ── Helper placeholders (implement per strategy_text above) ──
        private bool BuySignalCondition() {{ return false; }}
        private bool SellSignalCondition() {{ return false; }}
    }}
}}
"""
