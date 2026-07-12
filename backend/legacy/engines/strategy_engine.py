"""
Strategy generation engine — with FORCED STRUCTURAL DIVERSITY.

Every call to `generate_strategy_text(pair, timeframe, style)` now:
  1. Assigns a strategy_type (5 canonical types), respecting the caller's
     `style` hint only when it maps to a canonical type.
  2. Draws 1–2 indicators ONLY from that type's dedicated pool.
  3. Randomly picks a trade_frequency profile (low / medium / high).
  4. Randomly picks an entry_style and a risk_model.
  5. Injects all five axes into the LLM prompt with an explicit instruction
     to avoid the "EMA + RSI pullback" default.
  6. Validates the returned text:
        • contains at least one indicator keyword from the allowed pool
        • structural signature differs from the last N generations for
          the same (pair, timeframe)
     If validation fails, re-rolls the random config and retries (up to
     2 additional LLM calls, 3 total) before returning the best effort.

External signature is UNCHANGED — callers in api/dashboard.py,
api/strategies.py, api/pipeline.py, engines/auto_factory.py continue to
work without modification.
"""
from __future__ import annotations

import logging
import random
import re
import threading
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

# LLM is intentionally NOT used by default — the offline-safe renderer
# (see _render_strategy_text) produces structurally-diverse strategy
# texts deterministically so the pipeline runs without an LLM key.
# from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger(__name__)

# Lock guarding the recent-signature buffer + the per-call signature
# selection step. Multiple candidates are generated concurrently via
# asyncio.gather; without this lock two concurrent draws could land on
# the same signature.
_SIG_LOCK = threading.Lock()


# ── Diversity catalogues ─────────────────────────────────────────────

STRATEGY_TYPES: Tuple[str, ...] = (
    "trend_following",
    "mean_reversion",
    "breakout",
    "session_based",
    "volatility_based",
)

# Indicator pool PER TYPE. Generator picks 1-2 from the matching pool
# only — no cross-contamination, no EMA+RSI unless the type actually
# calls for both (and none of the five types do).
INDICATORS_BY_TYPE: Dict[str, List[str]] = {
    "trend_following":  ["EMA", "SMA", "MACD"],
    "mean_reversion":   ["RSI", "Bollinger Bands"],
    "breakout":         ["Donchian Channel", "ATR"],
    "session_based":    ["session high/low", "VWAP"],
    "volatility_based": ["ATR", "Bollinger Bands"],
}

# Keywords used for post-generation indicator validation (normalised,
# lowercase substrings searched in the LLM output).
INDICATOR_KEYWORDS: Dict[str, List[str]] = {
    "EMA":                ["ema"],
    "SMA":                ["sma"],
    "MACD":               ["macd"],
    "RSI":                ["rsi"],
    "Bollinger Bands":    ["bollinger", "bb("],
    "Donchian Channel":   ["donchian"],
    "ATR":                ["atr"],
    "session high/low":   ["session high", "session low", "range high", "range low", "session range"],
    "VWAP":               ["vwap"],
}

FREQUENCY_PROFILES: Dict[str, Tuple[int, int, str]] = {
    # label → (min_trades, max_trades, phrasing)
    "low":    (50,  150,  "50–150 trades over 1–3 years"),
    "medium": (150, 400,  "150–400 trades over 1–3 years"),
    "high":   (400, 1200, "400+ trades over 1–3 years (active scalping-grade frequency)"),
}

ENTRY_STYLES: Tuple[str, ...] = (
    "crossover",
    "pullback",
    "breakout",
    "reversal",
    "momentum",
)

RISK_MODELS: Tuple[str, ...] = (
    "fixed_rr_1_2",           # SL fixed, TP = 2× SL
    "fixed_rr_1_3",           # SL fixed, TP = 3× SL
    "atr_based",              # SL = ATR·k, TP = ATR·m
    "structure_based",        # SL = recent swing high/low, TP = next structure
    "trailing_stop",          # SL starts fixed, trails after +1R
)

RISK_MODEL_INSTRUCTIONS: Dict[str, str] = {
    "fixed_rr_1_2":
        "SL = 20 pips, TP = 40 pips (fixed 1:2 risk/reward). No ATR, no trailing.",
    "fixed_rr_1_3":
        "SL = 18 pips, TP = 54 pips (fixed 1:3 risk/reward). No ATR, no trailing.",
    "atr_based":
        "SL = ATR(14) × 1.5, TP = ATR(14) × 3.0 (volatility-scaled exits).",
    "structure_based":
        "SL placed at the most recent swing high (shorts) / swing low (longs) "
        "over the last 20 bars. TP at the next prior swing structure or a 1:2 "
        "minimum if structure is closer.",
    "trailing_stop":
        "Initial SL = 20 pips fixed. After price moves +1R in favour, trail "
        "the stop to break-even; after +2R, trail behind the last swing.",
}

# Suggested parameter ranges the LLM should pick exact values from.
# These ranges are intentionally type-specific so the same type doesn't
# always emit the same literal numbers.
PARAM_HINT_POOL: Dict[str, List[str]] = {
    "EMA":              ["fast 8 / slow 21", "fast 10 / slow 30", "fast 5 / slow 20", "period 50", "period 100"],
    "SMA":              ["fast 10 / slow 30", "fast 20 / slow 50", "period 100", "period 200"],
    "MACD":             ["12/26/9", "5/13/5 (fast scalping variant)", "19/39/9 (slow swing variant)"],
    "RSI":              ["period 7 (aggressive)", "period 14 (classic)", "period 21 (slow)"],
    "Bollinger Bands":  ["20 period / 2 stddev (classic)", "14 period / 1.8 stddev", "50 period / 2.5 stddev"],
    "Donchian Channel": ["20 period (classic Turtle)", "10 period (fast)", "55 period (slow)"],
    "ATR":              ["period 14 (classic)", "period 7 (fast)", "period 20 (smoothed)"],
    "session high/low": ["London 07:00–11:00 GMT", "New York 13:00–17:00 GMT", "Asian 00:00–07:00 GMT"],
    "VWAP":             ["session VWAP (daily reset)", "anchored VWAP from last swing"],
}


# ── Recent-generation signature memory (de-dup guard) ────────────────
# Per (pair, timeframe) — keep the last 8 structural signatures so back-
# to-back generations don't emit the same structure. Module-level, so it
# survives between API calls within the same process.

_RECENT_SIGS: Dict[Tuple[str, str], Deque[str]] = {}
_RECENT_MAX = 8


def _recent_key(pair: str, timeframe: str) -> Tuple[str, str]:
    return (pair.upper().strip(), timeframe.upper().strip())


def _remember_signature(pair: str, timeframe: str, sig: str) -> None:
    k = _recent_key(pair, timeframe)
    dq = _RECENT_SIGS.setdefault(k, deque(maxlen=_RECENT_MAX))
    dq.append(sig)


def _is_duplicate_signature(pair: str, timeframe: str, sig: str) -> bool:
    k = _recent_key(pair, timeframe)
    dq = _RECENT_SIGS.get(k)
    return bool(dq and sig in dq)


# ── Random config builder ────────────────────────────────────────────

# Map legacy `style` inputs onto canonical strategy_type when obvious.
_STYLE_TO_TYPE: Dict[str, str] = {
    "trend-following":  "trend_following",
    "trend_following":  "trend_following",
    "trend":            "trend_following",
    "mean-reversion":   "mean_reversion",
    "mean_reversion":   "mean_reversion",
    "reversion":        "mean_reversion",
    "breakout":         "breakout",
    "session":          "session_based",
    "session-based":    "session_based",
    "session_based":    "session_based",
    "volatility":       "volatility_based",
    "volatility-based": "volatility_based",
    "volatility_based": "volatility_based",
    # NOTE: "scalping" and "momentum" are frequency / entry-style axes,
    # not strategy types — so they fall through to random type selection.
}


def _resolve_strategy_type(
    style: str,
    rng: random.Random,
    weights: Optional[Dict[str, float]] = None,
) -> Tuple[str, bool]:
    """Return (strategy_type, caller_was_explicit).

    If `style` maps to one of the five canonical types, we honour it.
    Otherwise:
      * When `weights` is provided, draw from STRATEGY_TYPES weighted by
        those probabilities (Phase-2 history prior).
      * When `weights` is None, fall back to uniform random — preserving
        Phase-1 behaviour for callers that don't pass a prior.
    """
    key = (style or "").strip().lower()
    if key in _STYLE_TO_TYPE:
        return _STYLE_TO_TYPE[key], True
    if weights:
        ws = [max(0.0, weights.get(t, 0.0)) for t in STRATEGY_TYPES]
        if sum(ws) > 0:
            return rng.choices(STRATEGY_TYPES, weights=ws, k=1)[0], False
    return rng.choice(STRATEGY_TYPES), False


def _build_random_config(
    style: str,
    rng: random.Random,
    avoid_sig: Optional[str] = None,
    type_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, object]:
    """Assemble one full diversity configuration. Deterministic given the
    supplied `rng`. Never produces the same signature as `avoid_sig` if a
    different draw is possible.

    Phase-2: when `type_weights` is provided, the strategy_type axis is
    drawn from that distribution (weighted by historical performance for
    the active pair/timeframe). All other axes (indicators, frequency,
    entry style, risk model) remain uniformly random — only the type
    benefits from history.
    """
    for _ in range(6):
        stype, _ = _resolve_strategy_type(style, rng, weights=type_weights)
        pool = INDICATORS_BY_TYPE[stype]
        # Pick 1 or 2 indicators from the type's pool — never outside.
        k_ind = 1 if (len(pool) == 1 or rng.random() < 0.35) else 2
        k_ind = min(k_ind, len(pool))
        indicators = rng.sample(pool, k=k_ind)

        freq_label = rng.choice(list(FREQUENCY_PROFILES.keys()))
        entry_style = rng.choice(ENTRY_STYLES)
        risk_model = rng.choice(RISK_MODELS)

        sig = _signature(stype, indicators, freq_label, entry_style, risk_model)
        if sig != avoid_sig:
            param_hints = {ind: rng.choice(PARAM_HINT_POOL[ind]) for ind in indicators}
            return {
                "strategy_type": stype,
                "indicators": indicators,
                "trade_frequency": freq_label,
                "entry_style": entry_style,
                "risk_model": risk_model,
                "param_hints": param_hints,
                "signature": sig,
            }
    # Fallback — we tried 6 reshuffles; accept whatever the last draw was.
    param_hints = {ind: rng.choice(PARAM_HINT_POOL[ind]) for ind in indicators}
    return {
        "strategy_type": stype,
        "indicators": indicators,
        "trade_frequency": freq_label,
        "entry_style": entry_style,
        "risk_model": risk_model,
        "param_hints": param_hints,
        "signature": sig,
    }


def _signature(stype: str, indicators: List[str], freq: str,
               entry: str, risk: str) -> str:
    ind_key = "+".join(sorted(indicators)).lower()
    return f"{stype}|{ind_key}|{freq}|{entry}|{risk}"


# ── Prompt construction ──────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert quantitative trading strategy designer specialising in
PROP-FIRM-COMPLIANT, capital-preservation forex strategies.

You design forex strategies with STRICT STRUCTURAL DIVERSITY. Each strategy
you output must follow the EXACT `strategy_type`, `indicators`,
`trade_frequency`, `entry_style`, and `risk_model` the user specifies.
You MUST NOT fall back to generic EMA+RSI pullback logic unless those are
the exact indicators + entry_style requested.

═════════════ PROP-FIRM SAFETY HARD CONSTRAINTS ═════════════
Every strategy you emit MUST satisfy ALL of the following. These are
NON-NEGOTIABLE — they outrank any other optimisation goal.

A.  CAPITAL PRESERVATION FIRST. Strategy must prioritise LOW DRAWDOWN
    over HIGH PROFIT. Target peak drawdown < 5–8 % of account equity
    over a 1–3 year backtest. A strategy with PF=1.4 and DD=4 % is
    STRICTLY BETTER than one with PF=2.0 and DD=15 %.

B.  RISK PER TRADE ≤ 1 % of account equity. Express every stop loss in
    a way that, with proper position sizing, a single losing trade
    cannot exceed 1 % account loss. Wide stops (>40 pips on majors,
    >ATR×2.0) are FORBIDDEN.

C.  RISK-REWARD ≥ 1 : 1.5. TP distance must be at least 1.5× the SL
    distance. Targets of 1:2 or 1:3 are preferred. NEVER emit 1:1.

D.  ATR-BASED STOP LOSS PREFERRED. When `risk_model = atr_based`, use
    tight multipliers: k ∈ [0.8, 1.2] for SL, m ∈ [2.0, 3.0] for TP.
    For other risk_models, still describe SL in pips that correspond
    to ≤ ATR(14) × 1.2 on the requested timeframe (e.g. on EURUSD H1
    that is ~12–18 pips; on XAUUSD H1 ~120–180 pips).

E.  CONSERVATIVE BIAS. Avoid aggressive / high-frequency entries that
    over-trade in low-liquidity sessions. Prefer entries confirmed by
    a higher-timeframe bias OR a session filter (London / New York
    only when explicitly relevant). High-frequency strategies (400+
    trades) MUST add a quality-gate (e.g. ATR percentile rank) to
    avoid grinding through spread.

F.  FTMO-STYLE SUITABILITY. The strategy must be runnable inside a
    typical prop-firm rule set:
       • daily_loss_limit  ≈ 5 %
       • max_loss_limit    ≈ 10 %
       • profit_target     ≈ 8–10 %
    No martingale. No grid. No averaging into losers. No widening
    SL after entry. No correlated-pair stacking. Single-position
    sizing only.

If a request would force you to violate any of A–F (e.g. an aggressive
risk_model with a 400+ frequency), bend the parameters toward the safe
side (tighter SL, fewer entries) rather than break the constraint.
═══════════════════════════════════════════════════════════════

HARD RULES for every output:

1. INDICATORS — use ONLY the indicators the user names. Do not introduce
   any other indicator. If they ask for Donchian, do not add RSI. If they
   ask for Bollinger Bands, do not add EMA.

2. ENTRY — the entry logic must match the requested `entry_style`:
     • crossover  → indicator A crosses indicator B (or price crosses indicator)
     • pullback   → first establish the primary bias, then enter on a retracement
     • breakout   → enter on price breaking a level / channel / prior range
     • reversal   → enter when the indicator signals exhaustion and reverses
     • momentum   → enter on a strong continuation reading (no pullback)

3. RISK — follow the `risk_model` EXACTLY, BIASED TIGHT for prop safety:
     • fixed_rr_1_2       → SL fixed (TIGHT — see constraint B/D), TP = 2× SL, no trailing
     • fixed_rr_1_3       → SL fixed (TIGHT), TP = 3× SL, no trailing
     • atr_based          → SL = ATR × k, TP = ATR × m  (k ∈ [0.8, 1.2], m ∈ [2.0, 3.0])
     • structure_based    → SL at recent swing structure (no further than ATR×1.2 away),
                            TP at next prior structure ≥ 1.5× SL distance
     • trailing_stop      → initial fixed SL (TIGHT), then trail after +1R

4. TRADE FREQUENCY — tune thresholds/conditions so the backtest is likely
   to fall inside the requested band (50–150 / 150–400 / 400+).

5. FORMAT — use this exact structure:
   STRATEGY: [one-line name reflecting the type + indicators]
   TYPE: [strategy_type]
   INDICATORS: [list of indicators used, with parameters]
   FREQUENCY: [low|medium|high] ([expected trade count range])
   ENTRY LONG: [condition]
   ENTRY SHORT: [condition]
   EXIT: [stop loss rule] | [take profit rule] | [secondary exit if any]
   PARAMETERS: [key=value, ...]
   RISK_PROFILE: max_dd_target=<pct>%, risk_per_trade=<pct>%, rr_ratio=<n>

6. Keep the total response under 240 words. Be precise and mechanical.

You will be penalised if you emit EMA+RSI pullback logic when not asked,
OR if your strategy violates any of the prop-firm safety constraints
(A–F) above."""


def _format_user_prompt(
    pair: str, timeframe: str, cfg: Dict[str, object],
) -> str:
    freq_label = str(cfg["trade_frequency"])
    fmin, fmax, freq_text = FREQUENCY_PROFILES[freq_label]
    indicators = cfg["indicators"]
    param_hints = cfg.get("param_hints") or {}
    stype = cfg["strategy_type"]
    entry = cfg["entry_style"]
    risk = cfg["risk_model"]
    risk_text = RISK_MODEL_INSTRUCTIONS[risk]

    indicator_lines = []
    for ind in indicators:
        hint = param_hints.get(ind, "")
        indicator_lines.append(f"  - {ind}" + (f"  (suggested: {hint})" if hint else ""))
    ind_block = "\n".join(indicator_lines)

    return (
        f"Generate ONE forex trading strategy for {pair} on the {timeframe} timeframe.\n\n"
        f"strategy_type:     {stype}\n"
        f"indicators:        {', '.join(indicators)}\n"
        f"indicator details:\n{ind_block}\n"
        f"trade_frequency:   {freq_label}  (target: {freq_text})\n"
        f"entry_style:       {entry}\n"
        f"risk_model:        {risk}\n"
        f"risk instructions: {risk_text}\n\n"
        "PROP-FIRM SAFETY CONSTRAINTS (must satisfy ALL):\n"
        "  • Strategy must prioritize LOW DRAWDOWN over high profit.\n"
        "  • Target peak drawdown < 5–8% on a 1–3 year backtest.\n"
        "  • Risk per trade ≤ 1% of account equity.\n"
        "  • Risk-reward ratio ≥ 1:1.5 (prefer 1:2 or 1:3). NEVER 1:1.\n"
        "  • Stop loss MUST be tight: ≤ ATR(14) × 1.2 on the requested\n"
        "    timeframe. No wide stops.\n"
        "  • Strategy must be suitable for prop firm rules (FTMO-style:\n"
        "    daily-loss 5%, max-loss 10%, profit target 8–10%). No\n"
        "    martingale, grid, averaging-into-losers, or SL widening.\n\n"
        "REQUIREMENTS:\n"
        f"  1. Use ONLY the indicators listed above — no others.\n"
        f"  2. Entry logic MUST follow the `{entry}` style.\n"
        f"  3. Exit logic MUST follow the `{risk}` model (see risk instructions),\n"
        f"     biased toward TIGHT, controlled exits — capital preservation first.\n"
        f"  4. Target roughly {fmin}–{fmax} trades on 1–3 years of data, but if\n"
        f"     hitting that count would force unsafe risk parameters, prefer\n"
        f"     fewer trades over breaking the safety constraints.\n"
        f"  5. This strategy MUST be structurally different from common "
        f"EMA+RSI pullback strategies.\n"
        f"  6. End the response with a `RISK_PROFILE:` line stating the\n"
        f"     intended `max_dd_target`, `risk_per_trade`, and `rr_ratio`.\n"
        f"  7. Use the exact output format. Keep it under 240 words.\n"
    )


# ── Post-generation validation ───────────────────────────────────────

def _text_mentions(text: str, keywords: List[str]) -> bool:
    lo = text.lower()
    return any(kw in lo for kw in keywords)


def _validates_indicators(text: str, expected: List[str]) -> bool:
    """Require the text to reference at least one of the requested
    indicators by its canonical keyword. (We check 'at least one' rather
    than 'all' because a 2-indicator selection occasionally collapses to
    the dominant one in the LLM's phrasing — still structurally valid as
    long as NO outside indicator crept in is our aspiration, but the
    stricter check below handles drift.)"""
    if not expected:
        return True
    hit_any = False
    for ind in expected:
        if _text_mentions(text, INDICATOR_KEYWORDS[ind]):
            hit_any = True
            break
    return hit_any


# Indicators that, if they appear in text, indicate drift (a type-foreign
# indicator leaked in). Computed per call using the allowed pool.
_ALL_INDICATORS: List[str] = sorted(INDICATOR_KEYWORDS.keys())


def _has_drift(text: str, allowed: List[str]) -> bool:
    """Return True if the text references any indicator that is NOT in
    the allowed list. Used to reject EMA+RSI pullback drift from e.g. a
    breakout+Donchian request."""
    lo = text.lower()
    allowed_set = {a for a in allowed}
    for ind in _ALL_INDICATORS:
        if ind in allowed_set:
            continue
        for kw in INDICATOR_KEYWORDS[ind]:
            # Use word-boundary-ish check for short tokens like 'ema'/'rsi'
            if re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", lo):
                return True
    return False


# ── Offline-safe diverse renderer ────────────────────────────────────
# Produces structurally-different strategy texts WITHOUT calling an LLM.
# The text uses keywords + numbers that backtest_engine's param_extractor
# recognises — so different texts yield genuinely different backtests.

# Per-indicator numeric bands. Each call draws ONE concrete value from
# the band so two strategies of the same type still differ on numbers.
_PARAM_RANGES: Dict[str, Dict[str, Tuple[int, int]]] = {
    "EMA":              {"fast": (5, 21), "slow": (25, 100)},
    "SMA":              {"fast": (10, 30), "slow": (50, 200)},
    "MACD":             {"fast": (5, 19), "slow": (20, 39), "signal": (5, 12)},
    "RSI":              {"period": (7, 21), "buy": (20, 40), "sell": (60, 80)},
    "Bollinger Bands":  {"period": (14, 50), "stddev_x10": (15, 28)},  # /10 → 1.5..2.8
    "Donchian Channel": {"period": (10, 55)},
    "ATR":              {"period": (7, 21), "k_x10": (8, 12), "m_x10": (20, 30)},
    "VWAP":             {},
    "session high/low": {},
}

# Risk-model concrete numeric draws. Two strategies with the same risk
# model still differ on SL/TP since values are drawn per-call.
_SL_BAND = (10, 25)        # pips — tightened for prop-firm safety (was 10–40);
                           # caps risk-per-trade and matches ATR(14)×~1.0–1.2
                           # on majors at H1.
_RR_X10  = (15, 35)        # 1.5..3.5 RR — floor stays at 1.5 (constraint C)


def _render_strategy_text(pair: str, timeframe: str, cfg: Dict[str, object],
                          rng: random.Random) -> str:
    """Render the random config as a parseable, diverse strategy text.

    The text deliberately uses tokens that param_extractor recognises:
      • "EMA fast=N / slow=M" or "EMA(N)/EMA(M) crossover"
      • "RSI(period) > buy" / "RSI(period) < sell"
      • "MACD fast/slow/signal"
      • "BB(period, stddev)"
      • "SL=N pips, TP=M pips"
    so the backtest engine produces genuinely different metrics per call.
    """
    stype: str = cfg["strategy_type"]      # type: ignore[assignment]
    indicators: List[str] = cfg["indicators"]  # type: ignore[assignment]
    freq: str = cfg["trade_frequency"]     # type: ignore[assignment]
    entry: str = cfg["entry_style"]        # type: ignore[assignment]
    risk: str = cfg["risk_model"]          # type: ignore[assignment]

    # ── Per-indicator concrete values + a parseable INDICATORS line ──
    ind_lines: List[str] = []
    params_kv: List[str] = []

    chose_fast = chose_slow = None
    rsi_period = rsi_buy = rsi_sell = None
    macd_fast = macd_slow = macd_signal = None
    bb_period = bb_std = None
    don_period = None
    atr_period = atr_k = atr_m = None

    for ind in indicators:
        rng_band = _PARAM_RANGES.get(ind, {})
        if ind == "EMA":
            f = rng.randint(*rng_band["fast"])
            s = rng.randint(*rng_band["slow"])
            if f >= s:
                f, s = min(f, s) - 2, max(f, s)
                f = max(2, f)
            chose_fast, chose_slow = f, s
            ind_lines.append(f"EMA(fast={f})/EMA(slow={s})")
            params_kv.append(f"EMA fast={f}, EMA slow={s}")
        elif ind == "SMA":
            f = rng.randint(*rng_band["fast"])
            s = rng.randint(*rng_band["slow"])
            if f >= s:
                f, s = min(f, s) - 5, max(f, s)
                f = max(5, f)
            chose_fast, chose_slow = f, s
            ind_lines.append(f"SMA({f})/SMA({s})")
            params_kv.append(f"SMA fast={f}, SMA slow={s}")
        elif ind == "MACD":
            mf = rng.randint(*rng_band["fast"])
            ms = rng.randint(*rng_band["slow"])
            if mf >= ms:
                mf, ms = min(mf, ms), max(mf, ms) + 5
            sg = rng.randint(*rng_band["signal"])
            macd_fast, macd_slow, macd_signal = mf, ms, sg
            ind_lines.append(f"MACD({mf}/{ms}/{sg})")
            params_kv.append(f"MACD={mf}/{ms}/{sg}")
        elif ind == "RSI":
            p = rng.randint(*rng_band["period"])
            b = rng.randint(*rng_band["buy"])
            s = rng.randint(*rng_band["sell"])
            rsi_period, rsi_buy, rsi_sell = p, b, s
            ind_lines.append(f"RSI({p}) buy<{b}, sell>{s}")
            params_kv.append(f"RSI period={p}, RSI buy={b}, RSI sell={s}")
        elif ind == "Bollinger Bands":
            p = rng.randint(*rng_band["period"])
            sd_x10 = rng.randint(*rng_band["stddev_x10"])
            sd = sd_x10 / 10.0
            bb_period, bb_std = p, sd
            ind_lines.append(f"BB({p}, {sd:.1f})")
            params_kv.append(f"BB period={p}, BB stddev={sd:.1f}")
        elif ind == "Donchian Channel":
            p = rng.randint(*rng_band["period"])
            don_period = p
            ind_lines.append(f"Donchian({p})")
            params_kv.append(f"Donchian period={p}")
        elif ind == "ATR":
            p = rng.randint(*rng_band["period"])
            k = rng.randint(*rng_band["k_x10"]) / 10.0
            m = rng.randint(*rng_band["m_x10"]) / 10.0
            atr_period, atr_k, atr_m = p, k, m
            ind_lines.append(f"ATR({p}) k={k:.1f} m={m:.1f}")
            params_kv.append(f"ATR period={p}, ATR k={k:.1f}, ATR m={m:.1f}")
        elif ind == "VWAP":
            ind_lines.append("VWAP (session)")
            params_kv.append("VWAP=session")
        elif ind == "session high/low":
            sess = rng.choice(["London 07:00-11:00 GMT", "New York 13:00-17:00 GMT", "Asian 00:00-07:00 GMT"])
            ind_lines.append(f"Session range — {sess}")
            params_kv.append(f"session={sess}")

    # ── Entry rules using the chosen indicators + entry style ──
    primary_long = "Buy"
    primary_short = "Sell"
    if "EMA" in indicators or "SMA" in indicators:
        if entry == "crossover":
            primary_long = f"BUY when fast MA({chose_fast or '?'}) crosses ABOVE slow MA({chose_slow or '?'})"
            primary_short = f"SELL when fast MA({chose_fast or '?'}) crosses BELOW slow MA({chose_slow or '?'})"
        elif entry == "pullback":
            primary_long = f"BUY when price pulls back to MA({chose_fast or '?'}) in established uptrend"
            primary_short = f"SELL when price pulls back to MA({chose_fast or '?'}) in established downtrend"
        elif entry == "momentum":
            primary_long = f"BUY when price closes above MA({chose_fast or '?'}) with momentum"
            primary_short = f"SELL when price closes below MA({chose_fast or '?'}) with momentum"
        elif entry == "reversal":
            primary_long = f"BUY on bullish reversal candle near MA({chose_slow or '?'})"
            primary_short = f"SELL on bearish reversal candle near MA({chose_slow or '?'})"
        elif entry == "breakout":
            primary_long = f"BUY on close above MA({chose_slow or '?'}) by 0.2 ATR"
            primary_short = f"SELL on close below MA({chose_slow or '?'}) by 0.2 ATR"
    elif "RSI" in indicators:
        primary_long = f"BUY when RSI({rsi_period}) < {rsi_buy} (oversold reversal)"
        primary_short = f"SELL when RSI({rsi_period}) > {rsi_sell} (overbought reversal)"
    elif "MACD" in indicators:
        primary_long = f"BUY when MACD line crosses above signal line (MACD {macd_fast}/{macd_slow}/{macd_signal})"
        primary_short = "SELL when MACD line crosses below signal line"
    elif "Bollinger Bands" in indicators:
        primary_long = f"BUY when price touches lower BB({bb_period}, {bb_std:.1f}) band"
        primary_short = f"SELL when price touches upper BB({bb_period}, {bb_std:.1f}) band"
    elif "Donchian Channel" in indicators:
        primary_long = f"BUY on close above {don_period}-bar Donchian high (channel breakout)"
        primary_short = f"SELL on close below {don_period}-bar Donchian low"
    elif "ATR" in indicators:
        primary_long = f"BUY when price expands > ATR({atr_period}) × {atr_k:.1f}"
        primary_short = f"SELL when price contracts < ATR({atr_period}) × {atr_k:.1f}"
    elif "VWAP" in indicators:
        primary_long = "BUY when price reclaims VWAP from below"
        primary_short = "SELL when price loses VWAP from above"

    # ── Risk model → concrete SL/TP numbers ──
    sl = rng.randint(*_SL_BAND)
    rr = rng.randint(*_RR_X10) / 10.0
    tp = max(int(round(sl * rr)), sl + 5)
    if risk == "fixed_rr_1_2":
        tp = sl * 2
        exit_text = f"SL={sl} pips | TP={tp} pips (fixed 1:2 RR)"
    elif risk == "fixed_rr_1_3":
        tp = sl * 3
        exit_text = f"SL={sl} pips | TP={tp} pips (fixed 1:3 RR)"
    elif risk == "atr_based":
        # Prop-firm safety: keep SL multiplier tight (k∈[0.8,1.2]) and TP
        # multiplier delivering ≥ 1.5× RR (m∈[2.0,3.0]).
        ak = atr_k or rng.uniform(0.8, 1.2)
        am = atr_m or rng.uniform(2.0, 3.0)
        exit_text = f"SL={sl} pips (ATR×{ak:.1f}) | TP={tp} pips (ATR×{am:.1f})"
    elif risk == "structure_based":
        exit_text = f"SL={sl} pips at recent swing | TP={tp} pips at next structure"
    else:  # trailing_stop
        exit_text = f"SL={sl} pips initial | TP={tp} pips, trail after +1R"

    fmin, fmax, freq_text = FREQUENCY_PROFILES[freq]
    name_bits = "+".join(indicators)
    name = f"{stype.replace('_', ' ').title()} · {name_bits} · {entry} ({freq})"
    params_kv.append(f"SL={sl}, TP={tp}, risk_model={risk}")

    return (
        f"STRATEGY: {name}\n"
        f"TYPE: {stype}\n"
        f"INDICATORS: {', '.join(ind_lines)}\n"
        f"FREQUENCY: {freq} ({freq_text})\n"
        f"ENTRY LONG: {primary_long}\n"
        f"ENTRY SHORT: {primary_short}\n"
        f"EXIT: {exit_text}\n"
        f"PARAMETERS: {', '.join(params_kv)}\n"
    )


# ── Phase 18 — LLM generation path (additive, fully optional) ────────
#
# When `LLM_GENERATOR_ENABLED=true` AND `engines.llm_config.get_task_config`
# resolves a usable provider/key for the "strategy" task, we ask the LLM
# to render the SAME `cfg` the offline renderer would have used. The LLM
# output then runs through the EXISTING `_validates_indicators` +
# `_has_drift` checks. Any failure (flag off, no key, network/SDK error,
# validation rejection) falls back to `_render_strategy_text(cfg, rng)` —
# the proven offline path. So:
#   • External call signature is unchanged.
#   • Backtest engine, ranking, eligibility, evolution: all untouched.
#   • A misconfigured provider can NEVER break the generator.

_LLM_STATS: Dict[str, int] = {
    "llm_success": 0,
    "llm_validation_fail": 0,
    "llm_error": 0,
    "llm_disabled": 0,
    "offline_fallback": 0,
}


def get_generation_stats() -> Dict[str, int]:
    """Diagnostic counters — surfaced for tests + a possible future
    `GET /api/strategies/generation-stats` endpoint. Read-only copy."""
    return dict(_LLM_STATS)


def reset_generation_stats() -> None:
    """Test helper — clear counters between cases."""
    for k in _LLM_STATS:
        _LLM_STATS[k] = 0


# Hard ceiling on LLM call latency so a slow provider can't stall the
# auto-discovery loop. Tuned generously: gpt-4o-mini typical p99 ≈ 4s,
# Claude Sonnet ≈ 6s.
_LLM_TIMEOUT_SEC = 20.0


async def _try_llm_generation(
    pair: str,
    timeframe: str,
    cfg: Dict[str, object],
) -> Optional[str]:
    """Attempt LLM-based strategy rendering for the given diversity cfg.

    Returns the validated strategy text on success, or `None` on ANY
    failure path (flag off, missing key, missing SDK, network error,
    validation rejection). The caller is expected to fall back to
    `_render_strategy_text` whenever this returns None.

    Validation reuses the existing helpers so the LLM cannot smuggle a
    foreign indicator into the output:
      • `_validates_indicators(text, expected)` — at least one of the
        cfg's indicators must appear by canonical keyword.
      • `_has_drift(text, allowed)` — any indicator OUTSIDE the cfg's
        allowed pool triggers rejection.
    """
    # Lazy imports — keep the existing offline-only deployments working
    # even when emergentintegrations / llm_config aren't installed.
    try:
        from engines.llm_config import (
            is_llm_generator_enabled,
            get_task_config,
        )
    except Exception as e:                  # noqa: BLE001 — defensive
        logger.debug("llm_config unavailable: %s", e)
        return None

    if not is_llm_generator_enabled():
        _LLM_STATS["llm_disabled"] += 1
        return None

    task_cfg = get_task_config("strategy")
    api_key = task_cfg.get("api_key")
    provider = task_cfg.get("resolved_provider")
    model = task_cfg.get("model")
    if not api_key or not provider or not model:
        # Flag was on but no provider is actually configured.
        _LLM_STATS["llm_disabled"] += 1
        return None

    # Phase 1A: emergentintegrations SDK removed — all LLM calls now
    # route through the VIE HTTP service (see engines/llm_runner.py).
    user_prompt = _format_user_prompt(pair, timeframe, cfg)
    indicators: List[str] = list(cfg.get("indicators") or [])  # type: ignore[arg-type]

    try:
        from engines.llm_runner import run_chat as _run_chat
        text = await _run_chat("strategy", user_prompt, system_message=SYSTEM_PROMPT)
        if text is None:
            logger.warning(
                "LLM strategy generation: VIE returned no text — falling back to offline"
            )
            _LLM_STATS["llm_error"] += 1
            return None
    except Exception as e:                  # noqa: BLE001
        logger.warning(
            "LLM strategy generation failed (%s/%s): %s — falling back to offline",
            provider, model, str(e)[:160],
        )
        _LLM_STATS["llm_error"] += 1
        return None

    text = (text or "").strip()
    if not text:
        _LLM_STATS["llm_validation_fail"] += 1
        return None

    # Validation — reuse the EXISTING helpers (no new logic).
    if not _validates_indicators(text, indicators):
        logger.info(
            "LLM output failed indicator validation for %s — falling back",
            "+".join(indicators),
        )
        _LLM_STATS["llm_validation_fail"] += 1
        return None
    if _has_drift(text, indicators):
        logger.info(
            "LLM output drifted (foreign indicator) for %s — falling back",
            "+".join(indicators),
        )
        _LLM_STATS["llm_validation_fail"] += 1
        return None

    _LLM_STATS["llm_success"] += 1
    return text


# ── Public API ───────────────────────────────────────────────────────

async def generate_strategy_text(pair: str, timeframe: str, style: str) -> str:
    """Produce a structurally-DIVERSE strategy text.

    Each call:
      1. Draws a random config from the diversity catalogue (5 strategy
         types × 2-3 indicators × 3 frequencies × 5 entry styles ×
         5 risk models  → ≥1100 distinct structural signatures).
      2. Avoids the last 8 signatures used for (pair, timeframe).
      3. (Phase 18) When `LLM_GENERATOR_ENABLED` is on AND a provider is
         configured, asks the LLM to render the cfg. Output is validated
         via the existing `_validates_indicators` + `_has_drift` checks.
      4. On flag-off / no-key / LLM error / validation rejection, falls
         back to the offline deterministic renderer — same parseable
         tokens the backtest engine recognises.
      5. Remembers the signature so subsequent concurrent calls don't
         reuse it.

    Phase-2 — when the strategy_library is non-empty for the (pair,
    timeframe), the strategy_type axis is biased toward historically
    higher-scoring types. Every type retains a baseline floor so the
    generator never collapses into a single style.
    """
    rng = random.Random()  # OS entropy → genuine per-call diversity

    # Phase-2 — fetch the type-weights prior. Tolerant to a cold DB or
    # missing dependency: any failure falls back to uniform random.
    type_weights: Optional[Dict[str, float]] = None
    try:
        from engines.history_prior import get_type_weights
        type_weights = await get_type_weights(pair, timeframe)
    except Exception as e:                  # noqa: BLE001 — defensive
        logger.debug(f"history_prior unavailable, falling back to uniform: {e}")
        type_weights = None

    with _SIG_LOCK:
        recent = list(_RECENT_SIGS.get(_recent_key(pair, timeframe), []))
        cfg: Optional[Dict[str, object]] = None
        for _ in range(10):
            candidate = _build_random_config(
                style, rng, avoid_sig=None, type_weights=type_weights,
            )
            if candidate["signature"] not in recent:
                cfg = candidate
                break
        if cfg is None:
            cfg = _build_random_config(
                style, rng, avoid_sig=None, type_weights=type_weights,
            )
        _remember_signature(pair, timeframe, str(cfg["signature"]))

    # Phase 18 — try LLM first; on any failure fall back to the offline
    # renderer. The cfg is identical in both paths so the backtest
    # engine sees the same structural signature either way.
    llm_text = await _try_llm_generation(pair, timeframe, cfg)
    if llm_text is not None:
        return llm_text

    _LLM_STATS["offline_fallback"] += 1
    return _render_strategy_text(pair, timeframe, cfg, rng)
# ── Introspection helpers (used by tests + diagnostics; no API route) ─

def diversity_catalogue() -> Dict[str, object]:
    """Return the full catalogue of axes for external inspection."""
    return {
        "strategy_types":    list(STRATEGY_TYPES),
        "indicators_by_type": {k: list(v) for k, v in INDICATORS_BY_TYPE.items()},
        "frequency_profiles": {k: {"min": v[0], "max": v[1], "desc": v[2]}
                               for k, v in FREQUENCY_PROFILES.items()},
        "entry_styles":       list(ENTRY_STYLES),
        "risk_models":        list(RISK_MODELS),
    }


def build_config_for_debug(style: str = "", seed: Optional[int] = None) -> Dict[str, object]:
    """Build one random config WITHOUT calling the LLM — useful for unit
    tests and quick sanity checks."""
    rng = random.Random(seed) if seed is not None else random.Random()
    return _build_random_config(style or "", rng)


def recent_signatures_snapshot() -> Dict[str, List[str]]:
    """Return a copy of the recent-signature buffer (for diagnostics)."""
    return {f"{p}|{tf}": list(dq) for (p, tf), dq in _RECENT_SIGS.items()}


def reset_recent_signatures() -> None:
    """Clear the recent-signature memory (test helper)."""
    _RECENT_SIGS.clear()
