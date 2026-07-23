# Strategy Synthesis Architectural Gap — Deep Analysis

**Date:** 2026-05-13
**Status:** Analysis only — NO code changes proposed for this phase
**Scope:** Identify why exported cBots have placeholder signals despite real backtest
metrics; propose institutional-grade synthesis architecture.

---

## 1. TL;DR

The system has **three rule representations** that are *all out of sync with each other*:

```
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ MUTATION ENGINE  │    │  BACKTEST ENGINE │    │   CBOT EXPORT    │
│ (mutation_engine)│    │ (backtest_engine)│    │(cbot_engine/gen) │
└────────┬─────────┘    └────────┬─────────┘    └────────┬─────────┘
         │                       │                       │
         ▼                       ▼                       ▼
  strategy_text (rich        4 hardcoded            generator.py:
  English rules describ-     signal functions       offline stub →
  ing sessions, ATR          dispatched by          SimpleBot{BuyOnce}
  breakouts, etc.) +         keyword-detected
  parameters dict            strategy_type          OR code_generator.py:
                             (only 4 dispatch       template with 3
                             types, no session       hardcoded styles
                             logic at all)           NOT matching backtest
                                                     evaluator either
```

**Root cause of placeholder cBots:** The factory has **no single canonical rule
representation** that all three engines share. Each engine has its own view, and
the export path is the most lossy of the three.

This is the next major architectural phase: introduce a **Strategy Intermediate
Representation (Strategy-IR)** as the single source of truth, consumed by
backtest and emitted as cAlgo C# by the export transpiler.

---

## 2. Forensic Findings

### 2.1 How strategies are currently represented internally

A library doc (`strategy_library` collection) carries:

| Field | Format | Lossy? | Used by |
|---|---|---|---|
| `strategy_text` | Free-form English | **YES — extreme** | Param extractor (keyword grep), human readers |
| `parameters` | Stringified Python dict | NO | Optimizer overrides; **NOT** consumed by signal logic |
| `mutation_type` | Short label string (e.g. `session_asian_range`) | LOSSY (label-only) | Bookkeeping only |
| `style` | Coarse string (`mean_reversion`, `unknown`, …) | YES | UI display |
| `fingerprint` | SHA1 of strategy_text | n/a | Identity |
| (none) | — | — | No rule AST · no expression tree · no IR |

**There is no rule-tree storage anywhere in MongoDB.** I grepped for
`rule_tree`, `ast`, `expression`, `dsl`, `ir`, `rule_graph` across all 88
engines and 43 routers — zero matches. The closest thing to a structured
representation is the `parameters` dict, which carries indicator periods but
**never** the actual entry/exit predicates.

### 2.2 Whether mutations preserve formal rule structures

**They do not.** Inspecting `engines/mutation_engine.py`:

```python
# mutation_engine.py:116 — typical mutator output
def _mut_trend_pullback(base):
    text = _wrap(..., 
        entry_long="EMA(50) > EMA(200) AND price pulls back to EMA(20) AND RSI(14) crosses back above 40",
        entry_short="EMA(50) < EMA(200) AND price retraces to EMA(20) AND RSI(14) crosses back below 60",
        exit_rule="SL = ATR(14) * 1.5  |  TP = ATR(14) * 3.0",
    )
    return {
        "mutation_type": "trend_pullback",
        "strategy_text": text,                # ← rule semantics live HERE as English
        "parameters": {"ema_fast": 20, "ema_mid": 50, "ema_slow": 200,
                       "rsi_period": 14, "atr_period": 14,
                       "atr_sl_mult": 1.5, "atr_tp_mult": 3.0},
    }
```

The mutation **knows** the rule structure (it just wrote it as English in
`entry_long`/`entry_short`), but it **discards** that structure the moment
it serialises to text. Downstream consumers must re-parse English.

### 2.3 Whether the backtest engine executes mutation-specific logic

**It cannot.** `engines/backtest_engine.py:715`:

```python
def _signal_at(i: int):
    if strategy_type == "mean_reversion":
        return _signal_mean_reversion(i, seg_prices, rsi_vals, rsi_cfg, bb_upper, bb_lower)
    if strategy_type == "momentum":
        return _signal_momentum(i, macd_line, macd_signal, macd_hist, rsi_vals, rsi_cfg)
    if strategy_type == "breakout":
        return _signal_breakout(i, seg_prices, fast_ma, rsi_vals, rsi_cfg)
    return _signal_trend_following(i, seg_prices, fast_ma, slow_ma, rsi_vals, rsi_cfg)
```

These are **four pure Python functions** with **fixed logic** — no awareness of:
* session windows (06:00–07:00 GMT, Asian range, etc.)
* ATR breakouts (`Close > previous high + ATR×0.5`)
* range-based exits (`SL = 50% of range`)
* multi-leg pullback rules
* time-based exits (`Close all by 16:00 GMT`)

`strategy_type` is derived by **keyword extraction**:

```python
# engines/param_extractor.py:13
_TYPE_KEYWORDS = {
    "mean_reversion": ["MEAN REVERSION", "REVERSION", "OVERSOLD", "OVERBOUGHT",
                      "BOLLINGER", "BB BAND", "BOUNCE"],
    "breakout":       ["BREAKOUT", "BREAK OUT", "BREAKS ABOVE", "BREAKS BELOW", "CHANNEL"],
    "momentum":       ["MOMENTUM", "MACD", "HISTOGRAM", "SIGNAL LINE"],
    "scalping":       ["SCALP", "SCALPING", "QUICK", "FAST TRADE"],
    "trend_following":["TREND", "CROSSOVER", "CROSS OVER", "EMA", "SMA", "MOVING AVERAGE"],
}
```

So `session_asian_range` (a session-window breakout) hits **"BREAKS ABOVE"**
→ classified as `breakout` → backtested with the **`_signal_breakout`
function** which is just *"price crosses above fast MA + RSI filter"*.

**The session window, GMT timing, range computation: all completely ignored
by the backtest engine.** Yet the engine produces real PF/DD numbers. Those
numbers reflect the *fallback* signal logic, **not the strategy the mutation
actually described.**

This is the cohort-level explanation for the earlier finding that **all 70
survivors are verdict=RISKY with pass_probability=0**: most of them are
session-/range-/ATR-based strategies being silently mis-backtested as
generic EMA crossovers.

### 2.4 Whether `strategy_text` is lossy

**Catastrophically.** The text contains the full rule, but every downstream
consumer either (a) keyword-classifies it to one of 4 buckets, (b) regex-extracts
a handful of integers, or (c) ignores it entirely. The information content
of the text far exceeds what any consumer recovers.

### 2.5 Whether executable conditions exist upstream but aren't exported

**Partially.** The four hardcoded backtest signal functions ARE real executable
logic. But:

1. They're **only four shapes** (trend_following, mean_reversion, momentum,
   breakout) — they cannot represent the dozens of mutation types the
   mutation engine produces.
2. The export path **does not even reproduce these four shapes faithfully**:

| Engine | trend_following logic |
|---|---|
| `backtest_engine._signal_trend_following` | **Cross-detection:** `fast[i] > slow[i] AND fast[i-1] <= slow[i-1]` |
| `engines/code_generator._entry_logic("trend_following")` | **State check:** `_emaFast.LastValue > _emaSlow.LastValue` (fires every bar while above — not just on the crossing bar) |
| `cbot_engine/generator.generate_cbot_code` | **Stub:** `ExecuteMarketOrder(Buy, ...)` once. No conditions. |

So even for the simplest case, **three engines disagree on what a "trend
following" strategy is.** The backtest reports PF based on cross-detection;
the template export trades on every bar above; the LLM export trades once
and stops.

### 2.6 The two-cBot-generator problem

The codebase contains two parallel cBot generators:

| Path | File | What it does today | Status |
|---|---|---|---|
| A | `cbot_engine/generator.py` | LLM stub (offline mode) → returns hardcoded SimpleBot | What's wired to the export API today |
| B | `engines/code_generator.py` | Template-based, 3 strategy_type styles supported | Exists, untested in production export flow |

Both are dead-ends in their current form:
* Path A has the *right ambition* (LLM-driven, strategy-type-aware prompt,
  indicator-context builder) but the actual `generate_cbot_code` body is a
  stub.
* Path B has the *right discipline* (template-driven, no LLM) but only
  knows 3 styles and mismatches the backtest evaluator's actual semantics.

---

## 3. The Architectural Gap, Named

> **The factory produces statistical survivors using a fallback signal evaluator
> that bears no relationship to the rules the survivors were supposedly based
> on, and exports cBots from a path that bears no relationship to either.**

Three independent rule representations:

| Representation | Truth status |
|---|---|
| Mutation text + params | The *intended* strategy |
| Backtest evaluator (4 fixed functions) | The *actually-tested* strategy |
| cBot export | The *deployed* placeholder |

For institutional-grade execution, all three must converge on a **single
canonical rule representation**.

---

## 4. Proposed Architecture: Strategy Intermediate Representation (Strategy-IR)

### 4.1 The Core Idea

Introduce a **Strategy-IR** — a structured, versioned, JSON-serialisable rule
tree — as the single source of truth. Every engine that touches strategy
semantics consumes the IR; never the English text.

```
┌────────────────────────────────────────────────────────────────┐
│  MUTATION ENGINE                                               │
│  Emits Strategy-IR (structured)                                │
│  Renders strategy_text from IR (human-readable derivative)     │
└──────────────────────────────┬─────────────────────────────────┘
                               │
                               ▼  (Strategy-IR — canonical)
                  ┌────────────┴────────────┐
                  │   strategy_library      │
                  │   strategy_ir: {...}    │  ← NEW canonical field
                  │   strategy_text: "..."  │  ← human-readable view (derived)
                  └────────────┬────────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                                 ▼
    ┌──────────────────┐               ┌──────────────────┐
    │ IR INTERPRETER   │               │  IR → C# TRANSPILER │
    │ (backtest path)  │               │  (export path)      │
    │                  │               │                     │
    │ executes IR      │               │ emits cAlgo C# code │
    │ against bars     │               │ that mirrors the IR │
    │ → PF, DD, trades │               │ exactly 1:1         │
    └──────────────────┘               └──────────────────┘
              ▲                                 ▲
              │                                 │
       SAME IR; SAME SEMANTICS — backtest and live execute the same strategy
```

**Architectural promise:** the cBot deployed to cTrader executes **bit-identical
semantics** to what the backtest evaluated. The OOS gate, the lifecycle
classifier, the BI5 realism layer — all of them become trustworthy because the
thing being measured is the thing being deployed.

### 4.2 IR Schema (proposed, JSON-serialisable)

```jsonc
{
  "ir_version": 1,
  "id": "sha1-of-canonical-ir",
  "metadata": {
    "name": "Trend + RSI Pullback",
    "pair": "EURUSD",
    "timeframe": "H1",
    "mutation_lineage": ["base_hash", "mutation_op_id"],
    "behavioral_profile_hint": "TREND_FOLLOWER"
  },

  "indicators": [
    {"id": "ema_fast",  "kind": "EMA", "params": {"period": 20, "source": "close"}},
    {"id": "ema_mid",   "kind": "EMA", "params": {"period": 50}},
    {"id": "ema_slow",  "kind": "EMA", "params": {"period": 200}},
    {"id": "rsi_main",  "kind": "RSI", "params": {"period": 14}},
    {"id": "atr_main",  "kind": "ATR", "params": {"period": 14}}
  ],

  "session_filter": {                          // optional
    "kind": "gmt_window",
    "open":  "07:00",
    "close": "11:00",
    "force_flat_at": "16:00"
  },

  "volatility_filter": {                       // optional
    "kind": "atr_ratio",
    "indicator": "atr_main",
    "min_ratio": 0.8,
    "baseline_period": 20
  },

  "entry_long": {
    "op": "AND",
    "args": [
      {"op": "GT",  "args": [{"ref":"ema_mid"},  {"ref":"ema_slow"}]},
      {"op": "LE",  "args": [{"price":"close"},  {"ref":"ema_fast"}]},
      {"op": "CROSS_UP", "args": [{"ref":"rsi_main"}, {"const":40}]}
    ]
  },

  "entry_short": {                            // mirror of entry_long
    "op": "AND",
    "args": [
      {"op": "LT",  "args": [{"ref":"ema_mid"},  {"ref":"ema_slow"}]},
      {"op": "GE",  "args": [{"price":"close"},  {"ref":"ema_fast"}]},
      {"op": "CROSS_DOWN", "args": [{"ref":"rsi_main"}, {"const":60}]}
    ]
  },

  "exit": {
    "stop_loss":   {"kind": "atr_mult", "indicator": "atr_main", "mult": 1.5},
    "take_profit": {"kind": "atr_mult", "indicator": "atr_main", "mult": 3.0},
    "reverse_exit": false,
    "time_exit":   null
  },

  "risk": {
    "kind": "percent_of_balance",
    "percent": 1.0,
    "max_concurrent_positions": 1,
    "max_spread_pips": 3.0
  },

  "state_machine": null                       // populated for path-dependent rules
}
```

**Design properties:**

* **Pure data** — no code, no callables, no `eval()`. JSON-serialisable end-to-end.
* **Tree-structured predicates** with finite operator vocabulary
  (`AND`, `OR`, `NOT`, `GT`, `LT`, `GE`, `LE`, `EQ`, `CROSS_UP`,
  `CROSS_DOWN`, `BAND_TOUCH`, `RANGE_BREAK`, `TIME_WINDOW`, etc.).
* **Operand types** — `{ref: indicator_id}`, `{const: number}`,
  `{price: "close"|"open"|"high"|"low"}`, `{bar_offset: N}`, etc.
* **Stateful constructs** when needed: `state_machine` block for path-dependent
  logic (e.g. "exit half at 1R, trail the rest"). Each state has entry
  conditions and exit conditions referencing the same operator vocabulary.
* **Versioned** — `ir_version: 1` so future evolutions don't break old strategies.

### 4.3 Operator Vocabulary (Phase 1 — minimum-viable)

Sufficient to express **every existing mutation type** plus standard
trend/MR/momentum/breakout:

| Category | Operators |
|---|---|
| Logical | `AND, OR, NOT` |
| Comparison | `GT, LT, GE, LE, EQ, NEQ` |
| Cross | `CROSS_UP, CROSS_DOWN` |
| Range | `RANGE_BREAK_UP, RANGE_BREAK_DOWN, RANGE_TOUCH_HIGH, RANGE_TOUCH_LOW` |
| Time | `IN_GMT_WINDOW, IS_SESSION, AT_TIME` |
| Indicator-shape | `BAND_TOUCH_UPPER, BAND_TOUCH_LOWER, BAND_BREAK_UPPER, BAND_BREAK_LOWER` |
| Volatility | `ATR_RATIO_ABOVE, ATR_RATIO_BELOW` |
| Multi-TF | `HTF_SLOPE_UP, HTF_SLOPE_DOWN` |

Phase 2 can add: regime-aware operators, custom indicator expressions,
state-machine transitions for advanced exits (trailing stops, partial exits,
re-entries).

### 4.4 Mutation Engine — Emits IR Directly

Each `_mut_*` function returns an IR object. The English `strategy_text`
becomes a **rendering** of the IR (a `render_ir_to_text(ir)` pretty-printer)
rather than the source of truth.

Example refactor sketch (NOT implementing — design only):

```python
# engines/mutation_engine.py — proposed future shape
def _mut_session_asian_range(base: dict) -> dict:
    ir = {
        "ir_version": 1,
        "metadata": {"name": "Asian Range Breakout", ...},
        "indicators": [],
        "session_filter": None,
        "entry_long": {
            "op": "AND", "args": [
                {"op": "AT_TIME", "after": "07:00", "before": "15:00"},
                {"op": "RANGE_BREAK_UP",
                 "window_start_gmt": "00:00",
                 "window_end_gmt":   "07:00"}
            ]
        },
        "entry_short": { /* mirrored */ },
        "exit": {
            "stop_loss":   {"kind": "range_fraction", "ratio": 0.5},
            "take_profit": {"kind": "range_fraction", "ratio": 1.0},
            "time_exit":   {"close_all_gmt": "15:00"}
        },
        "risk": _DEFAULT_RISK,
    }
    return {
        "mutation_type": "session_asian_range",
        "strategy_ir":   ir,
        "strategy_text": render_ir_to_text(ir),
        "parameters":    ir_to_legacy_params(ir),  # back-compat alias
    }
```

Critical: **the text becomes derived**, not authoritative.

### 4.5 Backtest Engine — IR Interpreter

A new `engines/ir_interpreter.py` module evaluates IR expressions
bar-by-bar:

```python
# Proposed — design only
class IRInterpreter:
    def __init__(self, ir: dict, bars: BarSeries):
        self.ir = ir
        self.bars = bars
        self.indicator_arrays = self._precompute_indicators()

    def signal_at(self, i: int) -> Optional[Literal["BUY","SELL"]]:
        if not self._session_allows(i): return None
        if not self._volatility_allows(i): return None
        if self._eval(self.ir["entry_long"], i):  return "BUY"
        if self._eval(self.ir["entry_short"], i): return "SELL"
        return None

    def _eval(self, node: dict, i: int) -> bool:
        op = node["op"]
        if op == "AND":  return all(self._eval(a, i) for a in node["args"])
        if op == "OR":   return any(self._eval(a, i) for a in node["args"])
        if op == "GT":   return self._operand(node["args"][0], i) > self._operand(node["args"][1], i)
        if op == "CROSS_UP":
            a0, a1 = node["args"]
            return (self._operand(a0,i)   >  self._operand(a1,i)
                and self._operand(a0,i-1) <= self._operand(a1,i-1))
        # ... rest of the operator vocabulary
```

Then `backtest_engine.run_backtest_logic` calls `IRInterpreter(ir, bars)`
instead of `_signal_at(i)`. The four hardcoded functions become **legacy
fallbacks** for strategies without an IR (back-compat).

**Critical property:** the interpreter operator set defines the IR's expressive
power. The cBot transpiler MUST cover the exact same operator set.

### 4.6 cBot Transpiler — IR → cAlgo C#

A new `cbot_engine/ir_transpiler.py` walks the IR and emits cAlgo C# 1:1:

| IR construct | cAlgo C# emission |
|---|---|
| `indicators: [{id:"ema_fast", kind:"EMA", params:{period:20}}]` | `private ExponentialMovingAverage _emaFast;` + `_emaFast = Indicators.ExponentialMovingAverage(Bars.ClosePrices, EmaFastPeriod);` |
| `{op:"CROSS_UP", args:[{ref:"ema_fast"}, {ref:"ema_slow"}]}` | `(_emaFast.Result.Last(1) > _emaSlow.Result.Last(1) && _emaFast.Result.Last(2) <= _emaSlow.Result.Last(2))` |
| `{op:"AT_TIME", after:"07:00", before:"15:00"}` | `(Server.Time.TimeOfDay >= new TimeSpan(7,0,0) && Server.Time.TimeOfDay < new TimeSpan(15,0,0))` |
| `{op:"RANGE_BREAK_UP", window_start_gmt:"00:00", window_end_gmt:"07:00"}` | Emits a `ComputeRangeHigh(...)` helper + `Bars.ClosePrices.Last(1) > _rangeHigh` |
| `exit.stop_loss: {kind:"atr_mult", mult:1.5}` | `var slPips = _atr.Result.LastValue * 1.5 / Symbol.PipSize;` |
| `exit.time_exit: {close_all_gmt:"16:00"}` | `if (Server.Time.TimeOfDay >= new TimeSpan(16,0,0)) ClosePosition(p);` |

**Each operator has exactly one emission template.** The transpiler is a
pure walk-and-emit; no LLM, no free-text. Output is deterministic and
auditable.

**Architectural promise (institutional-grade):** *any* IR that backtests
in the interpreter compiles to a cBot that executes the same logic. There
is no semantic drift between research and execution.

### 4.7 Parameter Externalisation

The IR carries default values inline. The cBot transpiler emits them as
`[Parameter("EmaFastPeriod", DefaultValue = 20)]` so the operator can tune
them in cTrader without re-exporting. This preserves operator agency in
production without losing the canonical default.

---

## 5. Migration Plan — Additive and Reversible

The factory has produced 70 library strategies and 511 lifecycle docs against
the legacy representation. A clean-cut rewrite would lose all that. The
migration must be additive.

### Phase A — IR Definition + Mutation Emission (≈ 4 weeks of design + impl)
1. Author the IR schema as a Pydantic model in `engines/strategy_ir.py`.
2. Add `strategy_ir: dict` field to library docs (optional, nullable).
3. Refactor mutation engine's `_mut_*` functions to emit IR (preserving the
   English text as a `render_ir_to_text(ir)` derivative for human readability).
4. Existing strategies without IR continue working via the legacy path.

### Phase B — IR Interpreter in Backtest (≈ 3 weeks)
1. Implement `engines/ir_interpreter.py` with the Phase-1 operator vocabulary.
2. Add a single branch in `backtest_engine.run_backtest_logic`:
   ```python
   if strategy_profile.get("strategy_ir"):
       signal_engine = IRInterpreter(strategy_profile["strategy_ir"], bars)
   else:
       signal_engine = LegacySignalDispatcher(strategy_text)  # status quo
   ```
3. **Critical validation step**: for the 4 existing strategy types, hand-build
   their IR equivalents and prove that IR-backtest == legacy-backtest within
   numerical tolerance on a fixed dataset. This is the **trust gate**.

### Phase C — IR-Native cBot Transpiler (≈ 3 weeks)
1. Build `cbot_engine/ir_transpiler.py` with a template per IR operator.
2. Replace the `cbot_engine/generator.generate_cbot_code` stub with a call to
   the transpiler.
3. The legacy `engines/code_generator.py` template path stays available as a
   fallback for IR-less strategies (back-compat).

### Phase D — Backfill & Lifecycle Re-Eval (operational, not code)
1. Decide policy for the existing 70 library strategies:
   - **Option A — Discard**: mark them as legacy / non-deployable; they served
     their statistical-emergence purpose but cannot be IR-transpiled without
     an LLM re-extraction step.
   - **Option B — Re-extract**: build a one-shot text→IR re-parser for the
     existing cohort. Higher effort, preserves continuity.
   - **Option C — Hybrid** (recommended): mark the 70 as `ir_status: "legacy"`
     and let the next round of mutation produce IR-native survivors. The
     legacy cohort acts as a control group during the IR rollout.
2. Re-run the lifecycle classifier on IR-native survivors — now `pf` and
   `total_trades` reflect the *actual* strategy, not the fallback evaluator.

### Phase E — Cleanup (after IR is fully adopted)
1. Deprecate `engines/code_generator.py` (template path) and
   `cbot_engine/generator.py` (LLM stub).
2. Remove the `LegacySignalDispatcher` branch from the backtest engine.
3. Remove keyword-based `strategy_type` detection from `param_extractor.py`.

**At no point during phases A–D is the existing factory operationally broken.**
Every phase is additive; every phase is reversible by reverting the IR-aware
branch and falling back to the legacy path.

---

## 6. Why This Is Worth Doing

### Without Strategy-IR
* Backtest results measure the fallback signal evaluator, not the strategy
  the mutation engine described.
* Lifecycle classifier ranks strategies by the wrong metrics.
* BI5 realism certification certifies the wrong rules.
* cBot exports are placeholder — no path to a real cTrader demo without
  ad-hoc per-strategy hand-coding.
* PF/DD/OOS metrics are essentially noise about a 4-shape signal-bank, not
  a discovery process about real strategy space.

### With Strategy-IR
* Backtest measures exactly what the mutation engine intended.
* Survivors are genuinely diverse (session, range, breakout, MR, momentum,
  multi-leg, stateful) — not just 4 shapes wearing different text masks.
* Lifecycle progression reflects real edge.
* BI5 realism certifies the executable rules.
* `cBot export` is now a deterministic, auditable transpilation step. The
  rule the cBot trades is provably the rule the backtest measured.
* The factory becomes ready for institutional standards (audit trail,
  reproducibility, semantic versioning of rule trees).

### Operator-Facing Wins
* Demo deployment becomes trustworthy: shadow performance of the cBot
  should match the backtest within execution-cost noise.
* The "no Tier-1 demo-ready survivors" finding from the previous report
  becomes solvable structurally — once strategies are evaluated on their
  real logic, real survivors will emerge.

---

## 7. What This Plan Carefully Avoids

* **No hack placeholder signals.** No "stub LLM with `BuyOnce` calls".
* **No LLM-dependent transpilation.** The IR transpiler is a deterministic
  template walk; LLMs remain available only as an *upstream* strategy
  ideation source (the discovery engine), never as the rule encoder.
* **No rewrite of the backtest engine internals.** The sim loop, the cost
  model, the BI5 path, the lifecycle gates, the orchestrator, the
  scheduler, the auto_mutation pipeline — all of those stay. The IR
  interpreter slots in *before* the signal dispatch, replacing only the
  `_signal_at(i)` function.
* **No data migration trauma.** Existing 70 strategies travel as `ir_status:
  "legacy"`. The 511 lifecycle docs travel unchanged. The 200k market_data
  rows travel unchanged.
* **No breaking of the BID/BI5 separation philosophy.** Phase 27.4 work
  remains untouched. The IR is a strategy-level construct; it has zero
  interaction with the data-source separation.

---

## 8. Effort & Risk Profile

| Phase | Est. effort | Risk to existing system | Reversibility |
|---|---|---|---|
| A — IR schema + mutation emission | 3–4 wks | None (additive field) | Trivial |
| B — IR interpreter + trust-gate validation | 3 wks | Low (gated by validation; IR strategies opt-in) | Trivial |
| C — IR → cBot transpiler | 2–3 wks | None (replaces stub) | Trivial |
| D — Backfill / Hybrid | 1 wk operational decision | None | n/a |
| E — Cleanup / deprecation | 1 wk | Low (gated by full Phase A–D maturity) | Hard — happens last |

**Highest-leverage phase to start with:** Phase A. Defining the IR schema
forces architectural clarity. Once that's published and agreed, Phases B
and C can proceed in parallel.

---

## 9. Open Questions for the Operator

1. **IR scope ambition** — Phase 1 vocabulary covers all *existing* mutations.
   Do we also want native support for *future* constructs (regime-aware
   entries, custom indicator expressions, state-machine exits) in v1? Or
   defer to v2 of the IR?
2. **LLM role** — should LLMs remain as a strategy-ideation source that emits
   IR directly (with the LLM constrained to a strict JSON schema)? Or do we
   keep LLM strictly out of the encoding step and use it only for the human-
   readable text rendering?
3. **Legacy cohort policy** — preferred policy for the existing 70 library
   strategies: discard / re-extract / hybrid?
4. **Operator parameter exposure** — for the cBot transpiler, do we expose
   every IR parameter as a `[Parameter]` (operator tunable) or only specific
   ones (avoid bloat)? Default: all.
5. **Phase ordering** — Phase A then B, or Phase A then B + C in parallel?
6. **Validation tolerance for Phase B trust-gate** — what numerical tolerance
   is acceptable between legacy-backtest and IR-backtest of the same
   strategy_type? Default proposal: **PF within ±2%, trade count exact match,
   DD within ±5%.**

---

## 10. Awaiting Approval

This document is the sole deliverable for this phase. No code changes have
been made. The next step on your signal is **Phase A — IR schema definition
+ mutation engine emission**, executed under the same controlled discipline:

* additive
* reversible
* lifecycle-safe
* orchestration-safe
* discovery-isolated
* zero placeholder signals
* institutional-quality output, not skeleton wrappers

When you approve Phase A, the deliverables will be:
1. `engines/strategy_ir.py` — Pydantic schema + operator vocabulary
2. `engines/strategy_ir_renderer.py` — `render_ir_to_text(ir) -> str`
3. Refactored `engines/mutation_engine.py` `_mut_*` functions to emit IR
4. `tests/test_strategy_ir_schema.py` — schema invariants
5. `tests/test_mutation_emits_ir.py` — every mutation type emits valid IR
6. Zero changes to backtest, lifecycle, orchestrator, BI5, frontend, schedulers.
