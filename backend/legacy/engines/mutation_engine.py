"""
Phase 14 — Forex-Specific Strategy Mutation Engine.

Given a base strategy (strategy_text + pair/timeframe/style + optional
parameters), produces 5–15 deterministic, structured variants covering
seven forex-specific mutation categories:

  1. trend_pullback           – higher-EMA trend filter + RSI pullback entry
  2. session_london_breakout  – London open range breakout (07–11 GMT)
  3. session_asian_range      – Asian range breakout (00–07 GMT)
  4. volatility_atr_breakout  – ATR(14)·N band breakout
  5. volatility_bollinger_squeeze – BB(20,2) contraction → expansion
  6. mean_reversion_rsi       – RSI(14) <30 long / >70 short
  7. mean_reversion_bollinger – BB lower/upper band reversal
  8. risk_reward_1_1          – SL/TP ratio 1:1
  9. risk_reward_1_1_5        – SL/TP ratio 1:1.5
  10. risk_reward_1_2         – SL/TP ratio 1:2
  11. filter_add_rsi          – inject RSI(14) filter (50-level confirmation)
  12. filter_add_volatility   – inject ATR(14)>threshold filter
  13. filter_add_trend        – inject EMA(200) higher-TF trend filter
  14. mtf_htf_confirmation    – higher-timeframe trend confirmation
  15. filter_remove_rsi       – drop RSI filter if present in base

No randomness. No LLM calls. Every variant is the result of a pure
text-transform template keyed on the base.

Purely additive — the engine never touches scoring, validation, saving,
Gem Factory, or the Challenge Manager. Callers may backtest each variant
via the existing `dashboard._backtest_only` path (requires real market
data to be loaded) or by supplying an external `prices` list.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

# Phase 28-A — Strategy-IR additive enrichment.
# Existing mutators still emit strategy_text + parameters unchanged. The
# shim below attaches a validated `strategy_ir` block when the mutation
# type is covered by the IR builders. Mutations not yet covered by v1
# IR (or builds that raise) pass through with no IR attached — caller
# can detect this via `strategy_ir is None` and treat the strategy as
# legacy (`ir_status: "legacy"`). Zero downstream consumer is required
# to change in Phase A.
from engines.strategy_ir_builders import build_ir_for_mutation as _build_ir

logger = logging.getLogger(__name__)

EVENTS_COLL = "mutation_events"
RUNS_COLL = "mutation_runs"
STABILITY_COLL = "mutation_stability_log"


def _derive_base_ir(base: Dict[str, Any]):
    """Phase 28-B+ — Synthesize the canonical base IR for the supplied
    base strategy by mirroring the legacy classifier.

    Phase 28-B++ — Composer-chain continuity. When the supplied base
    strategy ALREADY carries a valid ``strategy_ir`` (i.e. the base is
    itself the output of a prior composer mutation — or any IR-native
    save), the prior IR is returned verbatim so the next composer
    layer applies on top of the accumulated overlays. This preserves
    semantic lineage across iterative mutation cycles. The text-only
    derivation path below is the unchanged fallback for legacy bases
    that don't carry an IR.

    Pipeline:
        0. (Phase 28-B++) If ``base["strategy_ir"]`` is a valid IR
           (StrategyIR instance or schema-validating dict), return it.
        1. ``extract_params(base_text)`` detects strategy_type and
           the same fast/slow/rsi/bb config the legacy backtest engine
           uses.
        2. ``build_legacy_reference_ir`` constructs the canonical IR
           that the trust gate (Phase 28-B) proved bit-identical to
           ``_signal_<strategy_type>`` for the four legacy types.
        3. Composer mutators (filter_add_*, mtf_htf_*, filter_remove_rsi,
           risk_reward_*) receive this canonical base IR and can layer
           their semantic onto a real predicate tree instead of falling
           back to ``ir_status='legacy'``.

    Returns None when the base maps to a strategy_type not covered by
    IR v1 (``momentum`` → MACD vocabulary still pending) or when
    extraction itself fails. Pure function, no I/O, never raises.
    """
    # ── Phase 28-B++ short-circuit: preserve carried IR ─────────────
    existing = base.get("strategy_ir")
    if existing is not None:
        try:
            from engines.strategy_ir import StrategyIR, is_valid_ir
            if isinstance(existing, StrategyIR):
                return existing
            if is_valid_ir(existing):
                return StrategyIR.model_validate(existing)
        except Exception as e:                              # pragma: no cover
            logger.debug("carried strategy_ir invalid; falling back: %s", e)
    try:
        from engines.param_extractor import extract_params
        from engines.ir_interpreter import build_legacy_reference_ir
    except Exception:                                       # pragma: no cover
        return None
    text = base.get("strategy_text") or ""
    if not text:
        return None
    try:
        ex = extract_params(text)
    except Exception:                                       # pragma: no cover
        return None
    stype = ex.get("strategy_type") or "trend_following"
    if stype == "momentum":
        # Documented IR v1 gap — Phase B intentional limitation.
        return None
    overrides = ex.get("overrides") or {}
    indicators = ex.get("indicators") or {}
    # Use sensible defaults aligned with the trust-gate fixtures when
    # the base text doesn't pin a period. Composers don't depend on
    # the exact EMA periods; they layer additional predicates around
    # the base entry tree.
    try:
        fast = int(overrides.get("fast_period") or 20)
        slow = int(overrides.get("slow_period") or 50)
    except (TypeError, ValueError):
        fast, slow = 20, 50
    rsi_cfg = indicators.get("rsi") if isinstance(indicators, dict) else None
    bb_cfg = indicators.get("bollinger") if isinstance(indicators, dict) else None
    try:
        return build_legacy_reference_ir(
            stype,
            fast_period=fast, slow_period=slow,
            rsi_cfg=rsi_cfg, bb_cfg=bb_cfg,
            pair=base.get("pair", "EURUSD"),
            timeframe=base.get("timeframe", "H1"),
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("base_ir derivation failed: %s", e)
        return None


def _attach_ir(variant: dict, base: dict, base_ir=None) -> dict:
    """Phase 28-A/B shim: enrich a mutator's return dict with a validated
    Strategy-IR when a builder is available. Never raises; on failure
    the variant flows through with ``strategy_ir = None``.

    ``base_ir`` (Phase 28-B+): canonical base IR derived from the base
    strategy by ``_derive_base_ir``. Composer builders (filter_add_*,
    mtf_htf_*, filter_remove_rsi, risk_reward_*) consume this base_ir
    and produce IR-native composer mutations. When ``base_ir`` is None
    (momentum base, malformed text), composer mutations fall back to
    ``ir_status='legacy'`` — the legacy backtest path is unaffected.
    """
    mtype = variant.get("mutation_type")
    pair = base.get("pair") or variant.get("pair") or "EURUSD"
    tf = base.get("timeframe") or variant.get("timeframe") or "H1"
    try:
        ir = _build_ir(
            mtype, pair, tf,
            base_ir=base_ir,
            rr_ratio=(variant.get("parameters") or {}).get("rr_ratio"),
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("strategy_ir build failed for %s: %s", mtype, e)
        ir = None
    if ir is not None:
        # Pydantic v2 dump → JSON-safe dict (no numpy / no enums).
        variant["strategy_ir"] = ir.model_dump(mode="json")
        variant["ir_status"] = "ir_native"
        variant["ir_version"] = 1
    else:
        variant["strategy_ir"] = None
        variant["ir_status"] = "legacy"
    return variant


# ─────────────────────────────────────────────────────────────────────
# Public catalogue — used by /api/mutation/stats and for validation
# ─────────────────────────────────────────────────────────────────────

MUTATION_TYPES: tuple = (
    "trend_pullback",
    "session_london_breakout",
    "session_asian_range",
    "volatility_atr_breakout",
    "volatility_bollinger_squeeze",
    "mean_reversion_rsi",
    "mean_reversion_bollinger",
    "risk_reward_1_1",
    "risk_reward_1_1_5",
    "risk_reward_1_2",
    "filter_add_rsi",
    "filter_add_volatility",
    "filter_add_trend",
    "mtf_htf_confirmation",
    "filter_remove_rsi",
)

MAX_VARIANTS = 15
MIN_VARIANTS = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(text: str) -> str:
    h = hashlib.sha1()
    h.update((text or "").strip().lower().encode("utf-8"))
    return h.hexdigest()


def _htf(timeframe: str) -> str:
    """Pick a reasonable higher-timeframe pair for MTF confirmation."""
    tf = (timeframe or "").upper()
    return {
        "M1": "M15", "M5": "H1", "M15": "H4", "M30": "H4",
        "H1": "H4", "H4": "D1", "D1": "W1",
    }.get(tf, "H4")


# ─────────────────────────────────────────────────────────────────────
# Text transforms — one per mutation type
# ─────────────────────────────────────────────────────────────────────

def _wrap(base_text: str, pair: str, tf: str, variant_name: str,
          entry_long: str, entry_short: str, exit_rule: str,
          params_note: str = "") -> str:
    """Shared text template so every variant reads the same way."""
    lines = [
        f"STRATEGY: {variant_name} ({pair} {tf})",
        "",
        f"ENTRY LONG: {entry_long}",
        f"ENTRY SHORT: {entry_short}",
        f"EXIT: {exit_rule}",
    ]
    if params_note:
        lines += ["", f"PARAMETERS: {params_note}"]
    lines += ["", f"DERIVED FROM: {base_text.strip()[:200]}"]
    return "\n".join(lines)


def _mut_trend_pullback(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "Trend + RSI Pullback",
        entry_long="EMA(50) > EMA(200) AND price pulls back to EMA(20) AND RSI(14) crosses back above 40",
        entry_short="EMA(50) < EMA(200) AND price retraces to EMA(20) AND RSI(14) crosses back below 60",
        exit_rule="SL = ATR(14) * 1.5  |  TP = ATR(14) * 3.0 (1:2 RR)",
        params_note="EMA_fast=20, EMA_mid=50, EMA_slow=200, RSI=14, ATR=14",
    )
    return {
        "mutation_type": "trend_pullback",
        "strategy_text": text,
        "parameters": {"ema_fast": 20, "ema_mid": 50, "ema_slow": 200,
                       "rsi_period": 14, "atr_period": 14, "atr_sl_mult": 1.5, "atr_tp_mult": 3.0},
    }


def _mut_session_london(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "London Open Breakout",
        entry_long="Price breaks above the 06:00–07:00 GMT range high (between 07:00 and 11:00 GMT only)",
        entry_short="Price breaks below the 06:00–07:00 GMT range low (between 07:00 and 11:00 GMT only)",
        exit_rule="SL = range size  |  TP = 1.5 × range size  |  Close all by 16:00 GMT",
        params_note="session_window_start=06:00, session_window_end=07:00, entry_window=07:00-11:00 GMT",
    )
    return {
        "mutation_type": "session_london_breakout",
        "strategy_text": text,
        "parameters": {"range_start_gmt": "06:00", "range_end_gmt": "07:00",
                       "entry_window_start": "07:00", "entry_window_end": "11:00",
                       "close_all_gmt": "16:00"},
    }


def _mut_session_asian_range(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "Asian Range Breakout",
        entry_long="Price breaks above 00:00–07:00 GMT range high after 07:00 GMT",
        entry_short="Price breaks below 00:00–07:00 GMT range low after 07:00 GMT",
        exit_rule="SL = 50% of range  |  TP = 100% of range  |  Close by 15:00 GMT",
        params_note="range_window=00:00-07:00 GMT, entry_after=07:00 GMT, close_at=15:00 GMT",
    )
    return {
        "mutation_type": "session_asian_range",
        "strategy_text": text,
        "parameters": {"range_start_gmt": "00:00", "range_end_gmt": "07:00",
                       "entry_after_gmt": "07:00", "close_all_gmt": "15:00"},
    }


def _mut_volatility_atr_breakout(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "ATR Breakout",
        entry_long="Close > previous high + ATR(14) × 0.5",
        entry_short="Close < previous low  - ATR(14) × 0.5",
        exit_rule="SL = ATR(14) × 1.5  |  TP = ATR(14) × 3.0",
        params_note="ATR=14, breakout_mult=0.5, sl_mult=1.5, tp_mult=3.0",
    )
    return {
        "mutation_type": "volatility_atr_breakout",
        "strategy_text": text,
        "parameters": {"atr_period": 14, "breakout_mult": 0.5,
                       "sl_mult": 1.5, "tp_mult": 3.0},
    }


def _mut_volatility_bb_squeeze(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "Bollinger Squeeze Breakout",
        entry_long="BB(20,2) bandwidth in bottom 20% of last 100 bars AND close > upper band",
        entry_short="BB(20,2) bandwidth in bottom 20% of last 100 bars AND close < lower band",
        exit_rule="SL = middle band  |  TP = band-width projection × 2",
        params_note="BB_period=20, BB_stddev=2, squeeze_lookback=100, squeeze_percentile=20",
    )
    return {
        "mutation_type": "volatility_bollinger_squeeze",
        "strategy_text": text,
        "parameters": {"bb_period": 20, "bb_stddev": 2,
                       "squeeze_lookback": 100, "squeeze_pct": 20},
    }


def _mut_mean_reversion_rsi(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "RSI Mean Reversion",
        entry_long="RSI(14) < 30 AND previous RSI < 30 (confirmed oversold)",
        entry_short="RSI(14) > 70 AND previous RSI > 70 (confirmed overbought)",
        exit_rule="Exit when RSI crosses 50  |  SL = 20 pips  |  TP = 30 pips",
        params_note="RSI=14, oversold=30, overbought=70, exit_level=50",
    )
    return {
        "mutation_type": "mean_reversion_rsi",
        "strategy_text": text,
        "parameters": {"rsi_period": 14, "oversold": 30, "overbought": 70,
                       "exit_level": 50, "sl_pips": 20, "tp_pips": 30},
    }


def _mut_mean_reversion_bollinger(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "Bollinger Band Reversal",
        entry_long="Close < BB(20,2) lower band AND next close > lower band (reversal confirmation)",
        entry_short="Close > BB(20,2) upper band AND next close < upper band",
        exit_rule="Exit at BB middle band  |  SL = 1.5 × ATR(14)",
        params_note="BB_period=20, BB_stddev=2, ATR=14, sl_mult=1.5",
    )
    return {
        "mutation_type": "mean_reversion_bollinger",
        "strategy_text": text,
        "parameters": {"bb_period": 20, "bb_stddev": 2, "atr_period": 14,
                       "sl_mult": 1.5},
    }


def _mut_risk_reward(base: Dict[str, Any], ratio: float, label: str,
                     mutation_type: str) -> Dict[str, Any]:
    tp = int(20 * ratio) if ratio > 0 else 20
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        f"Base with {label} RR",
        entry_long="(same as base) — re-uses base entry logic",
        entry_short="(same as base) — re-uses base entry logic",
        exit_rule=f"SL = 20 pips  |  TP = {tp} pips  ({label} risk/reward)",
        params_note=f"sl_pips=20, tp_pips={tp}, rr_ratio={ratio}",
    )
    return {
        "mutation_type": mutation_type,
        "strategy_text": text,
        "parameters": {"sl_pips": 20, "tp_pips": tp, "rr_ratio": ratio},
    }


def _mut_filter_add_rsi(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "Base + RSI Confirmation",
        entry_long="(base long entry) AND RSI(14) > 50",
        entry_short="(base short entry) AND RSI(14) < 50",
        exit_rule="(same as base)",
        params_note="adds RSI(14) momentum filter to base",
    )
    return {
        "mutation_type": "filter_add_rsi",
        "strategy_text": text,
        "parameters": {"rsi_period": 14, "rsi_long_floor": 50, "rsi_short_ceiling": 50},
    }


def _mut_filter_add_volatility(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "Base + Volatility Filter",
        entry_long="(base long entry) AND ATR(14) > 20-period ATR average × 0.8",
        entry_short="(base short entry) AND ATR(14) > 20-period ATR average × 0.8",
        exit_rule="(same as base)",
        params_note="requires above-average volatility before entry (ATR ratio ≥ 0.8)",
    )
    return {
        "mutation_type": "filter_add_volatility",
        "strategy_text": text,
        "parameters": {"atr_period": 14, "atr_avg_period": 20, "atr_ratio_min": 0.8},
    }


def _mut_filter_add_trend(base: Dict[str, Any]) -> Dict[str, Any]:
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        "Base + Trend Filter",
        entry_long="(base long entry) AND close > EMA(200)",
        entry_short="(base short entry) AND close < EMA(200)",
        exit_rule="(same as base)",
        params_note="adds EMA(200) trend filter — only trade with the higher trend",
    )
    return {
        "mutation_type": "filter_add_trend",
        "strategy_text": text,
        "parameters": {"ema_trend_period": 200},
    }


def _mut_mtf_htf_confirmation(base: Dict[str, Any]) -> Dict[str, Any]:
    htf = _htf(base["timeframe"])
    text = _wrap(
        base["strategy_text"], base["pair"], base["timeframe"],
        f"Base + {htf} Trend Confirmation",
        entry_long=f"(base long entry) AND {htf} EMA(50) > {htf} EMA(200)",
        entry_short=f"(base short entry) AND {htf} EMA(50) < {htf} EMA(200)",
        exit_rule="(same as base)",
        params_note=f"higher timeframe = {htf}; EMAs 50/200 confirm trend direction",
    )
    return {
        "mutation_type": "mtf_htf_confirmation",
        "strategy_text": text,
        "parameters": {"htf": htf, "ema_fast": 50, "ema_slow": 200},
    }


def _mut_filter_remove_rsi(base: Dict[str, Any]) -> Dict[str, Any]:
    # Strip any RSI phrasing from the base text and emit a minimalist variant.
    original = (base.get("strategy_text") or "").strip()
    stripped = _strip_rsi_phrases(original)
    text = (
        f"STRATEGY: Base without RSI ({base['pair']} {base['timeframe']})\n\n"
        f"ENTRY: same as base but RSI clauses removed\n"
        f"EXIT: (same as base)\n\n"
        f"PARAMETERS: no RSI filter\n\n"
        f"DERIVED FROM (RSI-stripped): {stripped[:200]}"
    )
    return {
        "mutation_type": "filter_remove_rsi",
        "strategy_text": text,
        "parameters": {"rsi_removed": True},
    }


def _strip_rsi_phrases(text: str) -> str:
    import re
    # Remove "AND RSI(…) …" or "RSI … > N" clauses.
    patterns = [
        r"\s+AND\s+RSI\s*\(\s*\d+\s*\)[^.\n]*?(?=\sAND\s|\.|$)",
        r"\bRSI\s*\(\s*\d+\s*\)[^\n]*?(?=\s[A-Z][A-Z]+|\.|$)",
    ]
    out = text
    for p in patterns:
        out = re.sub(p, "", out, flags=re.IGNORECASE)
    return out.strip()


# Mutation registry — ordered, deterministic.
_MUTATIONS: List[tuple] = [
    ("trend_pullback",               _mut_trend_pullback),
    ("session_london_breakout",      _mut_session_london),
    ("session_asian_range",          _mut_session_asian_range),
    ("volatility_atr_breakout",      _mut_volatility_atr_breakout),
    ("volatility_bollinger_squeeze", _mut_volatility_bb_squeeze),
    ("mean_reversion_rsi",           _mut_mean_reversion_rsi),
    ("mean_reversion_bollinger",     _mut_mean_reversion_bollinger),
    ("risk_reward_1_1",              lambda b: _mut_risk_reward(b, 1.0, "1:1",   "risk_reward_1_1")),
    ("risk_reward_1_1_5",            lambda b: _mut_risk_reward(b, 1.5, "1:1.5", "risk_reward_1_1_5")),
    ("risk_reward_1_2",              lambda b: _mut_risk_reward(b, 2.0, "1:2",   "risk_reward_1_2")),
    ("filter_add_rsi",               _mut_filter_add_rsi),
    ("filter_add_volatility",        _mut_filter_add_volatility),
    ("filter_add_trend",             _mut_filter_add_trend),
    ("mtf_htf_confirmation",         _mut_mtf_htf_confirmation),
    ("filter_remove_rsi",            _mut_filter_remove_rsi),
]


# ─────────────────────────────────────────────────────────────────────
# Public: mutate_strategy
# ─────────────────────────────────────────────────────────────────────

def mutate_strategy(base_strategy: Dict[str, Any],
                    max_variants: int = MAX_VARIANTS) -> List[Dict[str, Any]]:
    """Deterministically produce up to `max_variants` structured variants
    of `base_strategy`. Returns [] if the base is missing required fields.
    """
    if not isinstance(base_strategy, dict):
        return []
    text = base_strategy.get("strategy_text")
    pair = base_strategy.get("pair")
    tf   = base_strategy.get("timeframe")
    if not text or not pair or not tf:
        return []

    n = max(MIN_VARIANTS, min(int(max_variants or MAX_VARIANTS), MAX_VARIANTS))
    base = {
        "strategy_text": str(text),
        "pair": str(pair).upper(),
        "timeframe": str(tf).upper(),
        "style": base_strategy.get("style") or "unknown",
        "parameters": base_strategy.get("parameters") or {},
        # Phase 28-B++ — carry any IR the base strategy already has so
        # _derive_base_ir can preserve it across mutation cycles.
        "strategy_ir": base_strategy.get("strategy_ir"),
    }

    variants: List[Dict[str, Any]] = []
    base_fp = _fingerprint(base["strategy_text"])
    # Phase 28-B+ — derive the canonical base IR ONCE per call so every
    # composer mutation receives the same semantic foundation. None when
    # the base maps to a strategy_type not yet covered by IR v1
    # (momentum) — composer mutations then flow through as legacy.
    base_ir = _derive_base_ir(base)
    for mtype, fn in _MUTATIONS[:n]:
        try:
            v = fn(base)
        except Exception as e:
            logger.debug("mutation %s failed: %s", mtype, e)
            continue
        v.setdefault("pair", base["pair"])
        v.setdefault("timeframe", base["timeframe"])
        v.setdefault("style", base["style"])
        v["derived_from"] = {
            "base_fingerprint": base_fp,
            "pair": base["pair"],
            "timeframe": base["timeframe"],
        }
        v["variant_fingerprint"] = _fingerprint(v["strategy_text"])
        v = _attach_ir(v, base, base_ir=base_ir)
        variants.append(v)
    return variants


# ─────────────────────────────────────────────────────────────────────
# Phase 15 — type-selected mutation (additive helper for Evolution Loop)
# ─────────────────────────────────────────────────────────────────────

def mutate_strategy_by_types(
    base_strategy: Dict[str, Any],
    mutation_types: List[str],
) -> List[Dict[str, Any]]:
    """Build variants ONLY for the given `mutation_types`, preserving the
    order supplied. Unknown types are silently skipped. Used by the
    Evolution Loop when weighted selection is active; the legacy
    `mutate_strategy` remains unchanged.
    """
    if not isinstance(base_strategy, dict) or not mutation_types:
        return []
    text = base_strategy.get("strategy_text")
    pair = base_strategy.get("pair")
    tf = base_strategy.get("timeframe")
    if not text or not pair or not tf:
        return []

    base = {
        "strategy_text": str(text),
        "pair": str(pair).upper(),
        "timeframe": str(tf).upper(),
        "style": base_strategy.get("style") or "unknown",
        "parameters": base_strategy.get("parameters") or {},
        # Phase 28-B++ — carry any IR the base strategy already has so
        # _derive_base_ir can preserve it across mutation cycles.
        "strategy_ir": base_strategy.get("strategy_ir"),
    }

    fn_by_type = {mt: fn for mt, fn in _MUTATIONS}
    variants: List[Dict[str, Any]] = []
    base_fp = _fingerprint(base["strategy_text"])
    # Phase 28-B+ — derive canonical base IR once for composer mutations.
    base_ir = _derive_base_ir(base)
    for mtype in mutation_types:
        fn = fn_by_type.get(mtype)
        if fn is None:
            continue
        try:
            v = fn(base)
        except Exception as e:
            logger.debug("mutation %s failed: %s", mtype, e)
            continue
        v.setdefault("pair", base["pair"])
        v.setdefault("timeframe", base["timeframe"])
        v.setdefault("style", base["style"])
        v["derived_from"] = {
            "base_fingerprint": base_fp,
            "pair": base["pair"],
            "timeframe": base["timeframe"],
        }
        v["variant_fingerprint"] = _fingerprint(v["strategy_text"])
        v = _attach_ir(v, base, base_ir=base_ir)
        variants.append(v)
    return variants


# ─────────────────────────────────────────────────────────────────────
# Backtest integration
# ─────────────────────────────────────────────────────────────────────

async def _load_real_prices(pair: str, timeframe: str) -> list:
    """Mirror of dashboard._load_real_prices. Lazy-imported from there to
    reuse the exact same query shape (incl. timeframe map)."""
    from api.dashboard import _load_real_prices as _loader
    return await _loader(pair, timeframe)


def _backtest_variant_sync(variant_text: str, pair: str, tf: str,
                           prices: list,
                           sim_config: Optional[Dict[str, Any]] = None) -> dict:
    """Sync wrapper around dashboard._backtest_only.

    `sim_config` (when provided) flows through to `run_backtest_logic`
    so auto-discovery callers can enable the Phase-4 signal-quality
    filter (`quality_filter`, `quality_threshold`) inside the variant
    evaluation loop — not as a post-filter at the API layer.
    """
    from api.dashboard import _backtest_only as _bt
    try:
        return _bt(variant_text, pair, tf, prices, sim_config=sim_config)
    except Exception as e:
        return {"error": str(e)[:240], "backtest": {}, "prescore": 0.0}


async def run_mutation_pipeline(
    base_strategy: Dict[str, Any],
    *,
    max_variants: int = MAX_VARIANTS,
    prices: Optional[List[float]] = None,
    triggered_by: str = "api",
    auto_save: bool = False,
    firm: str = "ftmo",
    sim_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mutate → backtest → rank → (optional) validate+save best → log.

    VPS Scaling P1.D — wrapped in `admission_gate(MUTATION)`. With
    `ENABLE_ADMISSION_CONTROL=false` (default) the gate is a no-op and
    behaviour is byte-identical to pre-P1.D. With the flag ON, the gate
    refuses when band=critical/unknown and defers (with retry_after=30s)
    when the MUTATION class cap is reached.
    """
    from engines.workload_classes import WorkloadClass
    from engines.admission_wrapper import admission_gate

    pair_for_meta = (base_strategy.get("pair") if isinstance(base_strategy, dict) else None) or "?"
    tf_for_meta   = (base_strategy.get("timeframe") if isinstance(base_strategy, dict) else None) or "?"
    async with admission_gate(
        WorkloadClass.MUTATION,
        metadata={"site": "mutation_engine.run_mutation_pipeline",
                  "pair": pair_for_meta, "timeframe": tf_for_meta,
                  "max_variants": max_variants,
                  "triggered_by": triggered_by},
    ):
        return await _run_mutation_pipeline_inner(
            base_strategy,
            max_variants=max_variants, prices=prices,
            triggered_by=triggered_by, auto_save=auto_save,
            firm=firm, sim_config=sim_config,
        )


async def _run_mutation_pipeline_inner(
    base_strategy: Dict[str, Any],
    *,
    max_variants: int = MAX_VARIANTS,
    prices: Optional[List[float]] = None,
    triggered_by: str = "api",
    auto_save: bool = False,
    firm: str = "ftmo",
    sim_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mutate → backtest → rank → (optional) validate+save best → log.

    Returns a structured summary. When `auto_save=True`, the highest-ranked
    variant is passed through the existing dashboard `_heavy_stage`
    (walk-forward + simulation + decision + prop-firm panel) and then the
    existing `strategy_library.save_strategy` — meaning the standard
    eligibility gate (`_is_eligible`) governs whether it actually persists.
    No bypass, no new save logic.
    """
    import asyncio
    import time as _time

    if not isinstance(base_strategy, dict):
        raise ValueError("base_strategy must be a dict")
    pair = (base_strategy.get("pair") or "").upper()
    tf = (base_strategy.get("timeframe") or "").upper()
    if not base_strategy.get("strategy_text") or not pair or not tf:
        raise ValueError("base_strategy requires strategy_text, pair, timeframe")

    started_iso = _now_iso()
    t0 = _time.perf_counter()
    run_id = uuid.uuid4().hex[:12]
    db = get_db()

    # Phase 14.4 — pipeline log (additive, best-effort)
    from engines.pipeline_logs import log_event as _plog  # local import
    await _plog(
        "mutation",
        f"Mutation run started ({pair}/{tf}, max_variants={max_variants})",
        level="info", run_id=run_id, pair=pair, timeframe=tf,
        meta={"triggered_by": triggered_by, "auto_save": bool(auto_save)},
    )

    # Price source — external override or real-data loader. The
    # loader returns a 3-tuple `(prices, highs, lows)`; the mutation
    # backtest is close-only so we keep just the prices list.
    if prices is None:
        prices_list, _highs, _lows = await _load_real_prices(pair, tf)
        price_source = "real"
    else:
        try:
            prices_list = [float(p) for p in prices]
        except Exception:
            raise ValueError("prices must be an array of numbers")
        price_source = "external"

    if not prices_list or len(prices_list) < 60:
        return {
            "status": "data_missing",
            "run_id": run_id,
            "pair": pair, "timeframe": tf,
            "price_source": price_source,
            "data_points": len(prices_list or []),
            "message": (
                f"Need at least 60 candles for {pair}/{tf}; have {len(prices_list or [])}. "
                "Download data via /api/download-data or pass `prices` in the body."
            ),
        }

    # Step 1 — mutate (Phase 15/16: regime-aware weighted selection).
    n = max(MIN_VARIANTS, min(int(max_variants or MAX_VARIANTS), MAX_VARIANTS))
    evolution_applied = False
    selected_types: Optional[List[str]] = None
    regime_used: Optional[str] = None

    # Phase 16 — classify current regime from the price window we already
    # loaded. Never raises; "unknown" on short series.
    try:
        from engines.regime_classifier import classify_regime
        regime_type = classify_regime(prices_list)
    except Exception as e:
        logger.debug("regime classification failed: %s", e)
        regime_type = "unknown"

    try:
        from engines.evolution_engine import (
            compute_mutation_weights, weighted_select_types,
        )
        # Phase 16 — try regime-specific weights first; fall back to global.
        weights = None
        if regime_type and regime_type != "unknown":
            weights = await compute_mutation_weights(regime_type=regime_type)
            if weights:
                regime_used = regime_type
        if weights is None:
            weights = await compute_mutation_weights()
    except Exception as e:
        logger.debug("evolution weights lookup failed: %s", e)
        weights = None
    if weights:
        selected_types = weighted_select_types(weights, n)
        variants = mutate_strategy_by_types(base_strategy, selected_types)
        evolution_applied = True
    else:
        variants = mutate_strategy(base_strategy, max_variants=max_variants)
    if not variants:
        return {"status": "no_variants", "run_id": run_id,
                "pair": pair, "timeframe": tf,
                "reason": "base_strategy missing fields"}

    # Step 2 — backtest each variant in a thread/process pool
    # (CPU-bound numpy work). When `USE_PROCESS_POOL=true`, the
    # ProcessPoolExecutor is used for true multi-core throughput;
    # otherwise we fall through to asyncio.to_thread (current default).
    from engines import cpu_pool as _cpu_pool

    async def _one(v: dict) -> dict:
        bt = await _cpu_pool.submit_cpu(
            _backtest_variant_sync, v["strategy_text"], pair, tf, prices_list,
            sim_config,
        )
        metrics = bt.get("backtest") or {}
        return {**v, "backtest": metrics,
                "prescore": bt.get("prescore"),
                "trades_count": bt.get("trades_count", 0),
                "error": bt.get("error")}

    results = await asyncio.gather(*[_one(v) for v in variants])

    # Step 3 — rank by (profit_factor desc, max_drawdown asc, trades desc)
    def _sort_key(r: dict) -> tuple:
        m = r.get("backtest") or {}
        pf = float(m.get("profit_factor") or 0.0)
        dd = float(m.get("max_drawdown_pct") or 100.0)
        trades = int(m.get("total_trades") or 0)
        return (-pf, dd, -trades)

    ranked = sorted(results, key=_sort_key)
    best = ranked[0] if ranked else None

    # Step 4 — log events (append-only)
    now = _now_iso()
    base_fp = _fingerprint(base_strategy["strategy_text"])
    # Phase 28 telemetry — classify legacy reasons + chain depth at
    # emit time so the read-only /api/mutation/ir-telemetry endpoint
    # can aggregate cheaply over the existing collection. Pure helpers,
    # never raise.
    from engines.ir_telemetry import (
        classify_legacy_reason as _classify_legacy_reason,
        compute_ir_chain_depth as _compute_chain_depth,
    )
    _base_text = base_strategy.get("strategy_text") or ""
    event_docs = []
    for rank, r in enumerate(ranked):
        m = r.get("backtest") or {}
        _ir_status = r.get("ir_status") or "unknown"
        _chain_depth = _compute_chain_depth(r.get("strategy_ir"))
        _legacy_reason = _classify_legacy_reason(
            mutation_type=r.get("mutation_type", ""),
            ir_status=_ir_status,
            base_strategy_text=_base_text,
        )
        event_docs.append({
            "run_id": run_id,
            "type": r["mutation_type"],
            "base_fingerprint": base_fp,
            "variant_fingerprint": r.get("variant_fingerprint"),
            "pair": pair, "timeframe": tf, "style": r.get("style"),
            "rank": rank,
            "metrics": {
                "profit_factor": m.get("profit_factor"),
                "max_drawdown_pct": m.get("max_drawdown_pct"),
                "total_trades": m.get("total_trades"),
                "win_rate": m.get("win_rate"),
                "total_return_pct": m.get("total_return_pct"),
            },
            "error": r.get("error"),
            "ts": now,
            # Phase 28 telemetry fields (additive; absent on historical
            # rows, which bucket as ``unknown`` in summarize_events).
            "ir_status": _ir_status,
            "ir_chain_depth": _chain_depth,
            "legacy_reason": _legacy_reason,
            # H-1 (IR persistence fix): also persist the IR itself on the
            # mutation_events row so ``cbot_parity._find_ir_for_strategy``
            # fallback path #2 (mutation_events lookup by
            # ``variant_fingerprint``) actually succeeds. Value is ``None``
            # on legacy (non-IR) variants — preserves the
            # ``ir_status`` semantic.
            "strategy_ir": r.get("strategy_ir"),
        })
    if event_docs:
        try:
            await db[EVENTS_COLL].insert_many(event_docs)
        except Exception as e:
            logger.warning("mutation event bulk insert failed: %s", e)

    runtime = round(_time.perf_counter() - t0, 2)

    # Step 5 — auto_save (optional). Runs the best variant through the
    # existing dashboard heavy stage + existing save_strategy. We pass
    # `source="mutation_engine"` so the persisted doc is clearly tagged,
    # and we attach `mutation_type` + `mutation_run_id` via a follow-up
    # update so save_strategy stays untouched.
    auto_save_result: Optional[Dict[str, Any]] = None
    if auto_save and best is not None and not best.get("error"):
        auto_save_result = await _auto_save_best(
            best=best,
            base_strategy=base_strategy,
            prices=prices_list,
            firm=firm,
            run_id=run_id,
            sim_config=sim_config,
        )

    # Step 5.1 — stability telemetry (additive, best-effort). Logs the
    # auto_save outcome to `mutation_stability_log` so drift / gate
    # behavior can be inspected over time. Never touches the existing
    # save pipeline or ranking; failures are swallowed.
    if auto_save and auto_save_result is not None:
        await _record_stability_log(
            run_id=run_id,
            auto_save_result=auto_save_result,
            best=best,
            pair=pair,
            timeframe=tf,
            ts=now,
            regime_type=regime_type,
        )

    # Phase 14.4 — pipeline log: mutation result + auto-save outcome
    if best is not None:
        m = (best.get("backtest") or {})
        await _plog(
            "mutation",
            f"Best variant: {best.get('mutation_type')} "
            f"(PF {m.get('profit_factor')}, trades {m.get('total_trades')})",
            level="success" if (m.get('profit_factor') or 0) >= 1.0 else "info",
            run_id=run_id, pair=pair, timeframe=tf,
            meta={"variant_fingerprint": best.get("variant_fingerprint"),
                  "runtime_sec": runtime},
        )
    else:
        await _plog(
            "mutation",
            "No viable variants produced",
            level="warn", run_id=run_id, pair=pair, timeframe=tf,
        )
    if auto_save and auto_save_result is not None:
        status = auto_save_result.get("status")
        level = "success" if status == "saved" else (
            "warn" if status in ("rejected", "duplicate", "skipped") else "error"
        )
        msg = {
            "saved":     f"Auto-save SUCCESS · strategy_id={auto_save_result.get('strategy_id')}",
            "duplicate": "Auto-save DUPLICATE · variant already in library",
            "rejected":  f"Auto-save REJECTED · {auto_save_result.get('reason')}",
            "skipped":   f"Auto-save SKIPPED · {auto_save_result.get('reason')}",
            "error":     f"Auto-save ERROR · {auto_save_result.get('reason')}",
        }.get(status, f"Auto-save {status}")
        await _plog(
            "auto_save", msg, level=level,
            run_id=run_id, pair=pair, timeframe=tf,
            strategy_id=auto_save_result.get("strategy_id"),
            meta={"mutation_type": auto_save_result.get("mutation_type"),
                  "trades_count": auto_save_result.get("trades_count"),
                  "verdict": auto_save_result.get("verdict")},
        )

    summary = {
        "status": "ok",
        "run_id": run_id,
        "triggered_by": triggered_by,
        "started_at": started_iso,
        "finished_at": now,
        "runtime_sec": runtime,
        "pair": pair, "timeframe": tf,
        "style": base_strategy.get("style"),
        "price_source": price_source,
        "data_points": len(prices_list),
        "base_fingerprint": base_fp,
        "totals": {
            "variants_generated": len(variants),
            "variants_backtested": len(ranked),
            "errors": sum(1 for r in ranked if r.get("error")),
        },
        "best_variant": {
            "mutation_type": best["mutation_type"] if best else None,
            "variant_fingerprint": best.get("variant_fingerprint") if best else None,
            "backtest": (best.get("backtest") if best else None),
            "prescore": best.get("prescore") if best else None,
            # Full text so frontend enrichment layers (e.g. description
            # generator) can consume the winning variant. Kept additive —
            # existing consumers can ignore it.
            "strategy_text": best.get("strategy_text") if best else None,
        },
        "variants": [
            {
                "mutation_type": r["mutation_type"],
                "variant_fingerprint": r.get("variant_fingerprint"),
                "backtest": r.get("backtest") or {},
                "prescore": r.get("prescore"),
                "error": r.get("error"),
                "strategy_text_preview": (r.get("strategy_text") or "")[:220],
            }
            for r in ranked
        ],
        "auto_save": auto_save,
        "auto_save_result": auto_save_result,
        # Phase 15/16 — evolution + regime telemetry (additive)
        "evolution": {
            "applied": evolution_applied,
            "selected_types": selected_types,
            "regime_type": regime_type,
            "regime_weights_used": regime_used,   # regime name if regime-specific
                                                  # weights were applied, else None
        },
    }
    try:
        await db[RUNS_COLL].insert_one({**summary})
    except Exception as e:
        logger.warning("mutation run persist failed: %s", e)
    return summary


# ─────────────────────────────────────────────────────────────────────
# Auto-save (additive; reuses existing dashboard heavy stage +
# strategy_library.save_strategy — no new validation, no new save,
# no bypass of the existing eligibility gate).
# ─────────────────────────────────────────────────────────────────────

# Default walk-forward params used by the auto-save heavy stage. They
# match the dashboard defaults so behavior is deterministic and mirrors
# the Gem Factory / dashboard save flow.
_AUTO_SAVE_WF_N_WINDOWS = 3
_AUTO_SAVE_WF_NUM_VARIANTS = 6

# Minimum trade count required for a mutation variant to be a valid
# auto-save candidate. Below this, win-rate / profit-factor metrics are
# statistically unreliable — we reject the variant BEFORE the heavy
# stage so no false-positive slips past the existing save pipeline.
# Matches the "full credit" trade threshold used by the dashboard
# `_prescore` (backend/api/dashboard.py).
MIN_TRADES_FOR_AUTO_SAVE = 30


async def _auto_save_best(
    *,
    best: Dict[str, Any],
    base_strategy: Dict[str, Any],
    prices: List[float],
    firm: str,
    run_id: str,
    sim_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Pass the best mutation variant through the EXISTING save pipeline.

    Flow (all reused — no new engines, no new thresholds):
      1. `api.dashboard._backtest_only`    — recover trades for the variant
      1.5 min-trade gate                   — reject if < MIN_TRADES_FOR_AUTO_SAVE
      2. `api.dashboard._resolve_rules`    — firm rules (same chain as dashboard)
      3. `api.dashboard._heavy_stage`      — walk-forward + simulation + decision + panel
      4. `strategy_ranking_engine.rank_strategies` — composite score + verdict
      5. `engines.strategy_library.save_strategy`  — eligibility gate + dedup + persist

    The variant is saved ONLY if (a) it produced ≥ MIN_TRADES_FOR_AUTO_SAVE
    trades AND (b) `save_strategy` allows it (TRADE or strong RISKY,
    prop_status != FAIL). No `force=True`, no bypass. Dedup is handled
    by the existing fingerprint logic.

    Returns a structured summary that is safe to embed in the
    `run_mutation_pipeline` response.
    """

    # Local imports to avoid circular imports at module import time.
    from api.dashboard import (
        _backtest_only, _heavy_stage, _resolve_rules,
    )
    from engines.strategy_ranking_engine import rank_strategies
    from engines.strategy_library import save_strategy

    pair = (best.get("pair") or base_strategy.get("pair") or "").upper()
    tf = (best.get("timeframe") or base_strategy.get("timeframe") or "").upper()
    style = best.get("style") or base_strategy.get("style") or "unknown"
    strategy_text = best.get("strategy_text") or ""
    parameters = best.get("parameters") or {}

    if not strategy_text or not pair or not tf:
        return {
            "status": "skipped",
            "reason": "best variant missing strategy_text/pair/timeframe",
            "mutation_type": best.get("mutation_type"),
            "strategy_id": None,
            "fingerprint": None,
        }

    # Step 1 — re-run the light backtest to recover trades (the pipeline
    # only stored summary metrics, not the raw trade list). This uses the
    # same engine the dashboard uses; no new backtest code. The same
    # `sim_config` (quality filter etc.) used during variant evaluation
    # flows through so the saved trade list matches what was ranked.
    try:
        from engines import cpu_pool as _cpu_pool
        light = await _cpu_pool.submit_cpu(
            _backtest_only, strategy_text, pair, tf, prices,
            None, None, sim_config,
        )
    except Exception as e:
        logger.warning("auto_save backtest failed: %s", e)
        return {
            "status": "error",
            "reason": f"backtest failed: {str(e)[:200]}",
            "mutation_type": best.get("mutation_type"),
            "strategy_id": None,
            "fingerprint": None,
        }
    light["_prices"] = prices

    # Step 1.5 — minimum-trade gate (additive, pre-heavy-stage).
    # Reject variants that didn't produce enough trades for statistically
    # meaningful metrics BEFORE spending heavy-stage CPU on them. This
    # never touches scoring, validation, or save_strategy — it's a
    # mutation-side guard against low-trade false positives.
    light_trades = int(light.get("trades_count") or 0)
    if light_trades < MIN_TRADES_FOR_AUTO_SAVE:
        return {
            "status": "rejected",
            "saved": False,
            "strategy_id": None,
            "reason": (
                f"insufficient_trades ({light_trades} < "
                f"{MIN_TRADES_FOR_AUTO_SAVE})"
            ),
            "fingerprint": None,
            "mutation_type": best.get("mutation_type"),
            "variant_fingerprint": best.get("variant_fingerprint"),
            "trades_count": light_trades,
            "min_trades_required": MIN_TRADES_FOR_AUTO_SAVE,
        }

    # Step 2 — resolve firm rules via the dashboard's own resolver.
    try:
        rules_config = await _resolve_rules(firm)
    except Exception as e:
        logger.warning("auto_save rules resolution failed: %s", e)
        return {
            "status": "error",
            "reason": f"rules resolution failed: {str(e)[:200]}",
            "mutation_type": best.get("mutation_type"),
            "strategy_id": None,
            "fingerprint": None,
        }

    # Step 3 — heavy stage (WF validation + simulation + decision + panel).
    try:
        from engines import cpu_pool as _cpu_pool
        heavy = await _cpu_pool.submit_cpu(
            _heavy_stage, light, rules_config,
            _AUTO_SAVE_WF_N_WINDOWS, _AUTO_SAVE_WF_NUM_VARIANTS, True,
        )
    except Exception as e:
        logger.warning("auto_save heavy_stage failed: %s", e)
        return {
            "status": "error",
            "reason": f"heavy_stage failed: {str(e)[:200]}",
            "mutation_type": best.get("mutation_type"),
            "strategy_id": None,
            "fingerprint": None,
        }

    # Step 4 — rank (single item) to derive composite score + verdict.
    # `include_rejects=True` so we can still report REJECT outcomes back
    # to the caller; the `save_strategy` gate will reject them anyway.
    ranked = rank_strategies(
        [heavy], top_n=1, include_rejects=True, attach_panel=False,
    )
    entry = ranked[0] if ranked else {}

    panel = heavy.get("prop_firm_panel") or {}

    # ─── TASK 1 — Pass-probability + Expected-value enrichment ──────
    # `_heavy_stage` (in api/dashboard.py) currently passes
    # `pass_probability=None` to `decide()` and `build_prop_firm_panel()`,
    # so every saved row had pass_probability = null. Compute it here
    # explicitly from the recovered trade list and the resolved firm
    # rules — additive, isolated to the auto-save path, never touches
    # the dashboard's interactive flow.
    pass_prob_value = heavy.get("pass_probability")
    pp_robustness: Dict[str, Any] = {}
    if pass_prob_value is None:
        try:
            from engines.pass_probability import estimate_pass_probability
            from engines import cpu_pool as _cpu_pool
            pp_res = await _cpu_pool.submit_cpu(
                estimate_pass_probability,
                light.get("trades") or [],
                rules_config,
                30,   # n_simulations — lighter than default 50 for cycle speed
            )
            pass_prob_value = pp_res.get("pass_probability")
            pp_robustness = pp_res.get("structural_robustness") or {}
        except Exception as e:
            logger.warning("auto_save pass_probability failed: %s", e)

    # Expected-value (always attempted; collapses safely on failure).
    expected_value_payload: Optional[Dict[str, Any]] = None
    try:
        from engines.expected_value import calculate_expected_value
        panel_dd = panel.get("max_drawdown") if panel else None
        bt_dd = (heavy.get("backtest") or {}).get("max_drawdown_pct")
        max_dd = panel_dd if panel_dd is not None else bt_dd
        ev_pp = float(pass_prob_value) if isinstance(pass_prob_value, (int, float)) else 0.0
        expected_value_payload = calculate_expected_value(
            pass_probability=ev_pp,
            firm_slug=(firm or "ftmo").lower(),
            structural_robustness_score=pp_robustness.get("score"),
            structural_robustness_label=pp_robustness.get("label"),
            strategy_max_dd_pct=float(max_dd) if isinstance(max_dd, (int, float)) else None,
        )
    except Exception as e:
        logger.warning("auto_save expected_value failed: %s", e)

    # ─── TASK 3 — OOS holdout gate (reject overfit) ─────────────────
    # Reject strategies whose OOS profit-factor degrades by more than
    # 30% vs in-sample. Uses the existing 80/20 holdout engine; no new
    # validation logic. Uses a smaller variant search (20 vs 60) to
    # keep auto-save latency bounded.
    oos_summary: Optional[Dict[str, Any]] = None
    try:
        from engines.oos_holdout import run_oos_holdout
        from engines import cpu_pool as _cpu_pool
        oos_res = await _cpu_pool.submit_cpu(
            run_oos_holdout,
            strategy_text, pair, tf, prices,
            0.80,             # train_pct
            20,               # num_variants — lighter than default 60
            sim_config or {},
        )
        if oos_res.get("success"):
            is_pf = float((oos_res.get("train_metrics") or {}).get("profit_factor") or 0.0)
            oos_pf = float((oos_res.get("oos_metrics") or {}).get("profit_factor") or 0.0)
            ratio = (oos_pf / is_pf) if is_pf > 0 else 0.0
            oos_summary = {
                "is_pf": round(is_pf, 3),
                "oos_pf": round(oos_pf, 3),
                "ratio": round(ratio, 3),
                "overfit_flagged": (oos_res.get("overfit") or {}).get("flagged"),
                "train_candles": oos_res.get("train_candles"),
                "oos_candles": oos_res.get("oos_candles"),
            }
            if is_pf > 0 and ratio < 0.7:
                return {
                    "status": "rejected",
                    "saved": False,
                    "strategy_id": None,
                    "reason": (
                        f"oos_gate_failed: OOS_PF/IS_PF={ratio:.2f} < 0.70 "
                        f"(IS={is_pf:.2f}, OOS={oos_pf:.2f})"
                    ),
                    "fingerprint": None,
                    "mutation_type": best.get("mutation_type"),
                    "variant_fingerprint": best.get("variant_fingerprint"),
                    "trades_count": light_trades,
                    "oos_holdout": oos_summary,
                    "pass_probability": pass_prob_value,
                    "expected_value": expected_value_payload,
                }
        else:
            oos_summary = {"error": oos_res.get("error")}
    except Exception as e:
        logger.warning("auto_save oos_holdout failed: %s", e)
        oos_summary = {"error": str(e)[:200]}

    # Keep the panel consistent with the new pass-prob value so the
    # downstream `_extract_core` path picks it up either way.
    if isinstance(panel, dict) and pass_prob_value is not None:
        panel["pass_probability"] = pass_prob_value

    card = {
        "strategy_text": strategy_text,
        "pair": pair,
        "timeframe": tf,
        "style": style,
        "parameters": parameters,
        "backtest": heavy.get("backtest"),
        "validation_report": heavy.get("validation_report"),
        "decision": heavy.get("decision"),
        "prop_firm_panel": panel,
        "pass_probability": pass_prob_value,
        "expected_value": expected_value_payload,
        "oos_holdout": oos_summary,
        "score": entry.get("score"),
        "verdict": entry.get("verdict"),
        "reason": entry.get("reason"),
        # H-1 (IR persistence fix): carry the IR built by ``_attach_ir``
        # through to ``save_strategy`` so ``cbot_parity.sign_off_parity``
        # can locate it via ``strategy_library.strategy_ir`` instead of
        # returning NO_IR. ``_extract_core`` was extended in lockstep to
        # whitelist this field. Value is ``None`` when the variant was
        # promoted under the legacy non-IR path.
        "strategy_ir": best.get("strategy_ir"),
    }

    # Step 5 — existing save pipeline. No `force` — the Phase 11
    # eligibility gate (`_is_eligible`) governs whether it actually
    # persists. Source tag makes the provenance visible downstream.
    save_res = await save_strategy(card, source="mutation_engine")

    # Additive: tag the saved doc with mutation metadata for traceability
    # without touching save_strategy itself.
    strategy_id = save_res.get("strategy_id")
    if save_res.get("status") == "saved" and strategy_id:
        try:
            from engines.strategy_library import COLLECTION as _LIB_COLL
            db = get_db()
            await db[_LIB_COLL].update_one(
                {"strategy_id": strategy_id},
                {"$set": {
                    "mutation_type": best.get("mutation_type"),
                    "mutation_run_id": run_id,
                    "mutation_base_fingerprint": (
                        best.get("derived_from") or {}
                    ).get("base_fingerprint"),
                    "mutation_variant_fingerprint": best.get("variant_fingerprint"),
                    # H-1 (IR persistence fix): populate the conventional
                    # ``strategy_hash`` field that
                    # ``cbot_parity._find_ir_for_strategy`` (cbot_parity.py:
                    # 106) queries. Value mirrors ``variant_fingerprint``
                    # — same hash, conventional field name.
                    "strategy_hash": best.get("variant_fingerprint"),
                    # TASK 1/3 — surface the new evaluation fields directly on
                    # the persisted doc so consumers (matcher, dashboard, UI)
                    # don't have to reach into nested payloads.
                    "expected_value": expected_value_payload,
                    "oos_holdout": oos_summary,
                }},
            )
        except Exception as e:
            logger.debug("auto_save metadata tag failed: %s", e)

    return {
        "status": save_res.get("status"),
        "saved": save_res.get("status") == "saved",
        "strategy_id": strategy_id,
        "reason": save_res.get("reason"),
        "fingerprint": save_res.get("fingerprint"),
        "mutation_type": best.get("mutation_type"),
        "variant_fingerprint": best.get("variant_fingerprint"),
        "score": entry.get("score"),
        "verdict": entry.get("verdict"),
        "prop_status": panel.get("status"),
        "pass_probability": pass_prob_value,
        "expected_value": expected_value_payload,
        "oos_holdout": oos_summary,
    }


# ─────────────────────────────────────────────────────────────────────
# Events / stats
# ─────────────────────────────────────────────────────────────────────

async def list_events(
    *, mutation_type: Optional[str] = None, limit: int = 100,
) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 500))
    q: Dict[str, Any] = {}
    if mutation_type:
        if mutation_type not in MUTATION_TYPES:
            raise ValueError(f"unknown mutation_type: {mutation_type}")
        q["type"] = mutation_type
    cur = db[EVENTS_COLL].find(q, {"_id": 0}).sort("ts", -1).limit(limit)
    return [d async for d in cur]


async def get_stats() -> Dict[str, Any]:
    """Rollup by mutation_type: count, avg_pf, avg_dd, success rate (pf ≥ 1)."""
    db = get_db()
    rollup: Dict[str, Dict[str, Any]] = {}
    async for e in db[EVENTS_COLL].find({}, {"_id": 0}):
        mt = e.get("type")
        if mt not in MUTATION_TYPES:
            continue
        m = e.get("metrics") or {}
        pf = m.get("profit_factor")
        dd = m.get("max_drawdown_pct")
        row = rollup.setdefault(mt, {
            "type": mt, "count": 0, "pf_sum": 0.0, "pf_n": 0,
            "dd_sum": 0.0, "dd_n": 0, "wins": 0,
        })
        row["count"] += 1
        if isinstance(pf, (int, float)):
            row["pf_sum"] += float(pf); row["pf_n"] += 1
            if pf >= 1.0:
                row["wins"] += 1
        if isinstance(dd, (int, float)):
            row["dd_sum"] += float(dd); row["dd_n"] += 1

    out = []
    for mt, r in rollup.items():
        out.append({
            "type": mt,
            "count": r["count"],
            "avg_pf": round(r["pf_sum"] / r["pf_n"], 4) if r["pf_n"] else None,
            "avg_dd_pct": round(r["dd_sum"] / r["dd_n"], 4) if r["dd_n"] else None,
            "success_rate": round(r["wins"] / r["count"], 4) if r["count"] else 0.0,
        })
    out.sort(key=lambda x: ((x["avg_pf"] if x["avg_pf"] is not None else -1),
                            x["success_rate"]), reverse=True)
    return {"by_type": out, "total_events": sum(r["count"] for r in rollup.values())}



# ─────────────────────────────────────────────────────────────────────
# Stability monitor (additive telemetry for mutation auto-save).
# Purely observational — writes to a dedicated collection and never
# mutates the save pipeline, the ranking, or the variants themselves.
# ─────────────────────────────────────────────────────────────────────


async def _record_stability_log(
    *,
    run_id: str,
    auto_save_result: Dict[str, Any],
    best: Optional[Dict[str, Any]],
    pair: str,
    timeframe: str,
    ts: str,
    regime_type: Optional[str] = None,
) -> None:
    """Persist a single auto-save outcome to `mutation_stability_log`.

    Best-effort; swallows errors so a DB hiccup never fails a mutation
    run. Called only when `auto_save=True` and `auto_save_result` is
    not None.
    """
    backtest = (best.get("backtest") or {}) if best else {}

    # Prefer the trades count the gate actually used (from the light
    # backtest done inside `_auto_save_best`), then fall back to the
    # ranked best-variant metrics.
    trades = auto_save_result.get("trades_count")
    if trades is None:
        trades = backtest.get("total_trades")
    try:
        trades = int(trades) if trades is not None else None
    except (TypeError, ValueError):
        trades = None

    status = auto_save_result.get("status")
    doc = {
        "run_id": run_id,
        "ts": ts,
        "pair": pair,
        "timeframe": timeframe,
        "mutation_type": auto_save_result.get("mutation_type"),
        "variant_fingerprint": auto_save_result.get("variant_fingerprint"),
        "trades": trades,
        "profit_factor": backtest.get("profit_factor"),
        "max_drawdown": backtest.get("max_drawdown_pct"),
        "auto_save_status": status,
        "saved": bool(auto_save_result.get("saved")),
        "rejection_reason": (
            auto_save_result.get("reason") if status != "saved" else None
        ),
        "strategy_id": auto_save_result.get("strategy_id"),
        "score": auto_save_result.get("score"),
        "verdict": auto_save_result.get("verdict"),
        "prop_status": auto_save_result.get("prop_status"),
        # Phase 16 — regime label attached at run start (may be "unknown"
        # on short/empty price series; never raises).
        "regime_type": regime_type,
    }
    try:
        db = get_db()
        await db[STABILITY_COLL].insert_one(doc)
    except Exception as e:
        logger.debug("stability log insert failed: %s", e)


async def list_stability_logs(
    *,
    mutation_type: Optional[str] = None,
    auto_save_status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Fetch stability log entries, newest first. Filterable by type
    and/or auto_save_status. Uppercase limit is 500."""
    db = get_db()
    limit = max(1, min(int(limit), 500))
    q: Dict[str, Any] = {}
    if mutation_type:
        if mutation_type not in MUTATION_TYPES:
            raise ValueError(f"unknown mutation_type: {mutation_type}")
        q["mutation_type"] = mutation_type
    if auto_save_status:
        q["auto_save_status"] = auto_save_status
    cur = db[STABILITY_COLL].find(q, {"_id": 0}).sort("ts", -1).limit(limit)
    return [d async for d in cur]


async def get_stability_stats() -> Dict[str, Any]:
    """Rollup of stability logs by mutation_type.

    For each mutation_type seen in the log, returns:
      * count         — total auto-save attempts logged
      * saved         — number of successful saves
      * success_rate  — saved / count  (0.0 if count == 0)
      * avg_pf        — arithmetic mean of recorded profit_factor
      * avg_trades    — arithmetic mean of recorded trades count
      * avg_drawdown  — arithmetic mean of recorded max_drawdown
      * rejection_reasons — {bucket: count} distribution for non-saved rows
    Sorted by (success_rate desc, avg_pf desc).

    Response also carries a global `rejection_reasons` rollup across all types.
    """
    db = get_db()
    rollup: Dict[str, Dict[str, Any]] = {}
    global_reasons: Dict[str, int] = {}
    async for e in db[STABILITY_COLL].find({}, {"_id": 0}):
        mt = e.get("mutation_type") or "unknown"
        row = rollup.setdefault(mt, {
            "mutation_type": mt, "count": 0, "saved": 0,
            "pf_sum": 0.0, "pf_n": 0,
            "trades_sum": 0, "trades_n": 0,
            "dd_sum": 0.0, "dd_n": 0,
            "rejection_reasons": {},
        })
        row["count"] += 1
        if e.get("auto_save_status") == "saved":
            row["saved"] += 1
        else:
            bucket = _bucket_rejection_reason(
                e.get("rejection_reason"), e.get("auto_save_status"),
            )
            if bucket:
                row["rejection_reasons"][bucket] = (
                    row["rejection_reasons"].get(bucket, 0) + 1
                )
                global_reasons[bucket] = global_reasons.get(bucket, 0) + 1
        pf = e.get("profit_factor")
        if isinstance(pf, (int, float)):
            row["pf_sum"] += float(pf)
            row["pf_n"] += 1
        tr = e.get("trades")
        if isinstance(tr, int):
            row["trades_sum"] += tr
            row["trades_n"] += 1
        dd = e.get("max_drawdown")
        if isinstance(dd, (int, float)):
            row["dd_sum"] += float(dd)
            row["dd_n"] += 1

    out: List[Dict[str, Any]] = []
    for mt, r in rollup.items():
        out.append({
            "mutation_type": mt,
            "count": r["count"],
            "saved": r["saved"],
            "success_rate": (
                round(r["saved"] / r["count"], 4) if r["count"] else 0.0
            ),
            "avg_pf": round(r["pf_sum"] / r["pf_n"], 4) if r["pf_n"] else None,
            "avg_trades": (
                round(r["trades_sum"] / r["trades_n"], 2) if r["trades_n"] else None
            ),
            "avg_drawdown": (
                round(r["dd_sum"] / r["dd_n"], 4) if r["dd_n"] else None
            ),
            "rejection_reasons": dict(r["rejection_reasons"]),
        })
    out.sort(
        key=lambda x: (x["success_rate"], x["avg_pf"] if x["avg_pf"] is not None else -1),
        reverse=True,
    )
    return {
        "by_type": out,
        "total_logs": sum(r["count"] for r in rollup.values()),
        "rejection_reasons": global_reasons,
    }


def _bucket_rejection_reason(reason, auto_save_status) -> Optional[str]:
    """Bucket a rejection_reason string into a short, stable label suitable for
    distribution counts. Additive helper — never raises, returns None if no
    reason is available.
    """
    if not reason:
        # Fall back to status so a non-saved row still contributes a bucket.
        if auto_save_status and auto_save_status != "saved":
            return str(auto_save_status)
        return None
    r = str(reason).lower()
    if "insufficient_trades" in r:
        return "insufficient_trades"
    if "weak risky" in r:
        return "weak_risky"
    if "risky too unstable" in r or "too unstable" in r:
        return "risky_unstable"
    if "prop_firm_panel status is fail" in r or "prop firm" in r and "fail" in r:
        return "prop_firm_fail"
    if "not saveable" in r:
        return "verdict_not_saveable"
    if "backtest failed" in r:
        return "backtest_error"
    if "heavy_stage failed" in r:
        return "heavy_stage_error"
    if "rules resolution failed" in r:
        return "rules_error"
    if "duplicate" in r:
        return "duplicate_fingerprint"
    if "missing" in r and "strategy_text" in r:
        return "missing_fields"
    return "other"
