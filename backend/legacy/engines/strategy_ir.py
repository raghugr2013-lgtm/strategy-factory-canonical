"""Strategy Intermediate Representation (Strategy-IR) — Phase 28-A.

This module defines the **canonical** rule representation for AI Strategy
Factory v10. Every engine that touches strategy semantics (mutation engine,
backtest engine, cBot transpiler) must consume the IR; never the English
``strategy_text``.

Architectural promise — Phase 28-A scope:
    * Schema definition only. NO interpreter, NO transpiler in this phase.
    * Operator vocabulary covers the existing mutation_engine vocabulary
      exactly — no regime-aware, no state-machine extensions yet.
    * Additive: legacy strategies (no IR) continue working via existing
      keyword-extraction path.
    * Reversible: removing the IR field on a library doc restores legacy
      behaviour.
    * Lifecycle-safe / orchestration-safe / discovery-isolated: this
      module is consumed exclusively by the mutation engine in Phase A;
      no other engine imports it yet.

Trust gate (Phase B, NOT this phase):
    PF parity within ±2%, DD parity within ±5%, exact trade-count match
    between legacy backtest and IR-backtest on the four hardcoded
    strategy_types.
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

IR_VERSION = 1

# ── Operator vocabulary ────────────────────────────────────────────────
# Frozen for Phase A. Every operator listed here MUST have:
#   * A documented semantic (see comments below)
#   * A matching emission template in the Phase-C cBot transpiler
#   * A matching evaluator in the Phase-B IR interpreter

LogicalOp = Literal["AND", "OR", "NOT"]
ComparisonOp = Literal["GT", "LT", "GE", "LE", "EQ", "NEQ"]
CrossOp = Literal["CROSS_UP", "CROSS_DOWN"]
RangeOp = Literal[
    "RANGE_BREAK_UP",      # close breaks above a computed range high
    "RANGE_BREAK_DOWN",    # close breaks below a computed range low
]
TimeOp = Literal[
    "AT_TIME",             # bar's GMT time within [after, before]
    "IN_GMT_WINDOW",       # alias used by session filter
]
BandOp = Literal[
    "BAND_TOUCH_UPPER",    # high >= upper BB band
    "BAND_TOUCH_LOWER",    # low  <= lower BB band
    "BAND_BREAK_UPPER",    # close > upper BB band
    "BAND_BREAK_LOWER",    # close < lower BB band
]
VolatilityOp = Literal[
    "ATR_RATIO_ABOVE",     # current ATR / SMA(ATR, baseline_period) >= min
]
HTFOp = Literal[
    "HTF_SLOPE_UP",        # HTF EMA fast > HTF EMA slow AND rising
    "HTF_SLOPE_DOWN",      # HTF EMA fast < HTF EMA slow AND falling
]
SqueezeOp = Literal[
    "BB_SQUEEZE_PERCENTILE",   # bandwidth in bottom N-percentile of lookback
]

PredicateOp = Union[
    LogicalOp, ComparisonOp, CrossOp, RangeOp, TimeOp, BandOp,
    VolatilityOp, HTFOp, SqueezeOp,
]


# ── Operand types ──────────────────────────────────────────────────────

class IndicatorRef(BaseModel):
    """Reference to a declared indicator by id."""
    model_config = ConfigDict(extra="forbid")
    ref: str = Field(..., description="Indicator id (declared in the indicators block).")


class ConstOperand(BaseModel):
    """Numeric literal."""
    model_config = ConfigDict(extra="forbid")
    const: float


class PriceOperand(BaseModel):
    """Reference to a bar price stream."""
    model_config = ConfigDict(extra="forbid")
    price: Literal["open", "high", "low", "close"]
    bar_offset: int = Field(0, ge=0, le=20, description="0 = current bar, 1 = previous, etc.")


Operand = Union[IndicatorRef, ConstOperand, PriceOperand]


# ── Indicator declarations ────────────────────────────────────────────

class EMAIndicator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["EMA"]
    params: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_params(self):
        if "period" not in self.params:
            raise ValueError("EMA indicator requires params.period")
        if not isinstance(self.params["period"], int) or self.params["period"] < 2:
            raise ValueError("EMA params.period must be int >= 2")
        return self


class RSIIndicator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["RSI"]
    params: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_params(self):
        p = self.params.get("period", 14)
        if not isinstance(p, int) or p < 2:
            raise ValueError("RSI params.period must be int >= 2")
        self.params.setdefault("period", 14)
        return self


class ATRIndicator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["ATR"]
    params: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_params(self):
        p = self.params.get("period", 14)
        if not isinstance(p, int) or p < 2:
            raise ValueError("ATR params.period must be int >= 2")
        self.params.setdefault("period", 14)
        return self


class BollingerIndicator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["BOLLINGER"]
    params: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_params(self):
        p = self.params.get("period", 20)
        s = self.params.get("std_dev", 2.0)
        if not isinstance(p, int) or p < 2:
            raise ValueError("BOLLINGER params.period must be int >= 2")
        if not isinstance(s, (int, float)) or s <= 0:
            raise ValueError("BOLLINGER params.std_dev must be > 0")
        self.params.setdefault("period", 20)
        self.params.setdefault("std_dev", 2.0)
        return self


class HTFEMAIndicator(BaseModel):
    """Higher-timeframe EMA — used by mtf_htf_confirmation mutations."""
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["HTF_EMA"]
    params: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_params(self):
        if "period" not in self.params:
            raise ValueError("HTF_EMA requires params.period")
        if "htf" not in self.params:
            raise ValueError("HTF_EMA requires params.htf (e.g. 'H4')")
        return self


Indicator = Union[
    EMAIndicator, RSIIndicator, ATRIndicator,
    BollingerIndicator, HTFEMAIndicator,
]


# ── Predicate tree ─────────────────────────────────────────────────────

class Predicate(BaseModel):
    """Recursive predicate node. Every IR predicate has an ``op`` and an
    ``args`` list. Specific operators add typed fields via ``extras``."""
    model_config = ConfigDict(extra="allow")

    op: PredicateOp
    args: List[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_op_shape(self):
        op = self.op
        if op in ("AND", "OR"):
            if len(self.args) < 2:
                raise ValueError(f"{op} requires >= 2 args")
        elif op == "NOT":
            if len(self.args) != 1:
                raise ValueError("NOT requires exactly 1 arg")
        elif op in ("GT", "LT", "GE", "LE", "EQ", "NEQ"):
            if len(self.args) != 2:
                raise ValueError(f"{op} requires exactly 2 args")
        elif op in ("CROSS_UP", "CROSS_DOWN"):
            if len(self.args) != 2:
                raise ValueError(f"{op} requires 2 args (a, b) — true when a crosses b")
        elif op in ("RANGE_BREAK_UP", "RANGE_BREAK_DOWN"):
            # Requires window_start_gmt + window_end_gmt extras.
            extras = self.__pydantic_extra__ or {}
            if "window_start_gmt" not in extras or "window_end_gmt" not in extras:
                raise ValueError(
                    f"{op} requires window_start_gmt + window_end_gmt"
                )
        elif op in ("AT_TIME", "IN_GMT_WINDOW"):
            extras = self.__pydantic_extra__ or {}
            if "after" not in extras or "before" not in extras:
                raise ValueError(f"{op} requires after + before (HH:MM GMT)")
        elif op in ("BAND_TOUCH_UPPER", "BAND_TOUCH_LOWER",
                    "BAND_BREAK_UPPER", "BAND_BREAK_LOWER"):
            extras = self.__pydantic_extra__ or {}
            if "indicator" not in extras:
                raise ValueError(f"{op} requires `indicator` (BB id)")
        elif op == "ATR_RATIO_ABOVE":
            extras = self.__pydantic_extra__ or {}
            for k in ("indicator", "baseline_period", "min_ratio"):
                if k not in extras:
                    raise ValueError(f"ATR_RATIO_ABOVE requires `{k}`")
        elif op in ("HTF_SLOPE_UP", "HTF_SLOPE_DOWN"):
            extras = self.__pydantic_extra__ or {}
            for k in ("htf_ema_fast", "htf_ema_slow"):
                if k not in extras:
                    raise ValueError(f"{op} requires `{k}`")
        elif op == "BB_SQUEEZE_PERCENTILE":
            extras = self.__pydantic_extra__ or {}
            for k in ("indicator", "lookback", "percentile"):
                if k not in extras:
                    raise ValueError(f"BB_SQUEEZE_PERCENTILE requires `{k}`")
        return self


# ── Filter blocks ─────────────────────────────────────────────────────

class SessionFilter(BaseModel):
    """Optional GMT window during which the strategy is allowed to trade.
    ``force_flat_at`` (HH:MM GMT) forces position close at that hour."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["gmt_window"] = "gmt_window"
    open: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    close: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    force_flat_at: Optional[str] = Field(None, pattern=r"^\d{2}:\d{2}$")


class VolatilityFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["atr_ratio"] = "atr_ratio"
    indicator: str
    baseline_period: int = Field(20, ge=2, le=500)
    min_ratio: float = Field(0.8, gt=0.0)


# ── Exit block ────────────────────────────────────────────────────────

class StopLossPips(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["pips"] = "pips"
    pips: float = Field(..., gt=0)


class StopLossATR(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["atr_mult"] = "atr_mult"
    indicator: str
    mult: float = Field(..., gt=0)


class StopLossRangeFraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["range_fraction"] = "range_fraction"
    ratio: float = Field(..., gt=0)
    window_start_gmt: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    window_end_gmt: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class StopLossBandMid(BaseModel):
    """SL at the middle band of a BB indicator."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["band_mid"] = "band_mid"
    indicator: str


StopLossSpec = Union[StopLossPips, StopLossATR, StopLossRangeFraction, StopLossBandMid]


class TakeProfitPips(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["pips"] = "pips"
    pips: float = Field(..., gt=0)


class TakeProfitATR(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["atr_mult"] = "atr_mult"
    indicator: str
    mult: float = Field(..., gt=0)


class TakeProfitRangeFraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["range_fraction"] = "range_fraction"
    ratio: float = Field(..., gt=0)
    window_start_gmt: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    window_end_gmt: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class TakeProfitBandMid(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["band_mid"] = "band_mid"
    indicator: str


class TakeProfitIndicatorCross(BaseModel):
    """Exit when an indicator crosses a level — used by RSI mean-reversion."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["indicator_cross"] = "indicator_cross"
    indicator: str
    level: float


TakeProfitSpec = Union[
    TakeProfitPips, TakeProfitATR, TakeProfitRangeFraction,
    TakeProfitBandMid, TakeProfitIndicatorCross,
]


class TimeExit(BaseModel):
    """Force-flat at a GMT time (independent of SL/TP)."""
    model_config = ConfigDict(extra="forbid")
    close_all_gmt: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class ExitBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stop_loss: StopLossSpec
    take_profit: TakeProfitSpec
    time_exit: Optional[TimeExit] = None
    reverse_exit: bool = False


# ── Risk block ────────────────────────────────────────────────────────

class RiskBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["percent_of_balance"] = "percent_of_balance"
    percent: float = Field(1.0, gt=0, le=10.0)
    max_concurrent_positions: int = Field(1, ge=1, le=10)
    max_spread_pips: float = Field(3.0, gt=0)


# ── Root model ────────────────────────────────────────────────────────

class StrategyIR(BaseModel):
    """The single canonical rule representation."""

    model_config = ConfigDict(extra="forbid")

    ir_version: Literal[1] = 1
    metadata: dict = Field(default_factory=dict)
    indicators: List[Indicator] = Field(default_factory=list)
    session_filter: Optional[SessionFilter] = None
    volatility_filter: Optional[VolatilityFilter] = None
    entry_long: Predicate
    entry_short: Predicate
    exit: ExitBlock
    risk: RiskBlock = Field(default_factory=RiskBlock)

    @model_validator(mode="after")
    def _check_indicator_refs(self):
        """Every IndicatorRef and every indicator-id referenced by exit /
        filter blocks must resolve to a declared indicator."""
        declared = {ind.id for ind in self.indicators}

        def walk_args(args):
            for a in args or []:
                if isinstance(a, dict):
                    if "ref" in a and a["ref"] not in declared:
                        raise ValueError(
                            f"Predicate references undeclared indicator id='{a['ref']}'"
                        )
                    if "op" in a:
                        walk_args(a.get("args"))
                elif isinstance(a, Predicate):
                    walk_args(a.args)
                elif isinstance(a, BaseModel):
                    sub = a.model_dump()
                    if "ref" in sub and sub["ref"] not in declared:
                        raise ValueError(
                            f"Predicate references undeclared indicator id='{sub['ref']}'"
                        )

        walk_args([self.entry_long])
        walk_args([self.entry_short])

        # Exit + filter indicator refs.
        for spec in (self.exit.stop_loss, self.exit.take_profit):
            ind_id = getattr(spec, "indicator", None)
            if ind_id and ind_id not in declared:
                raise ValueError(
                    f"Exit references undeclared indicator id='{ind_id}'"
                )
        if self.volatility_filter and self.volatility_filter.indicator not in declared:
            raise ValueError(
                f"volatility_filter references undeclared indicator "
                f"id='{self.volatility_filter.indicator}'"
            )
        return self


# ── Helpers (read-only, no mutation of inputs) ────────────────────────

def validate_ir(payload: dict) -> StrategyIR:
    """Parse + validate a raw IR dict. Raises ``ValidationError`` on
    malformed input. Returns a fully-typed StrategyIR."""
    return StrategyIR.model_validate(payload)


def is_valid_ir(payload: Any) -> bool:
    """Cheap truthy check — used by callers that want to gate on
    'has this strategy got a real IR or just a legacy text?'"""
    if not isinstance(payload, dict):
        return False
    try:
        validate_ir(payload)
        return True
    except Exception:
        return False


__all__ = [
    "IR_VERSION",
    "StrategyIR", "Predicate",
    "IndicatorRef", "ConstOperand", "PriceOperand",
    "EMAIndicator", "RSIIndicator", "ATRIndicator",
    "BollingerIndicator", "HTFEMAIndicator",
    "SessionFilter", "VolatilityFilter",
    "ExitBlock", "RiskBlock", "TimeExit",
    "StopLossPips", "StopLossATR", "StopLossRangeFraction", "StopLossBandMid",
    "TakeProfitPips", "TakeProfitATR", "TakeProfitRangeFraction",
    "TakeProfitBandMid", "TakeProfitIndicatorCross",
    "validate_ir", "is_valid_ir",
]
