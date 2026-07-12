"""Master Bot V1 — cBot Exporter (MB-7 + MB-7.2).

Goal:
    Given an immutable `master_bot_definition` revision, produce two
    artifacts on disk:

      * `<bot>_<rev>_<short_hash>.cs`     — cAlgo C# source
      * `<bot>_<rev>_<short_hash>.json`   — metadata sidecar

The .cs is a self-contained, compile-ready cAlgo Robot scaffold that:

    1. Declares per-tier strategy classes (`Tier1Strategy_*`,
       `Tier2Strategy_*`, `Tier3Strategy_*`). When the member's
       snapshot carries a validated `strategy_ir` (MB-7.2), the class
       is generated from the existing Phase 28-C IR transpiler — REAL
       strategy logic (indicators, predicates, entry/exit/SL/TP). When
       no IR is available the class falls back to a deterministic
       refusal STUB carrying the snapshot as static metadata. Stubs
       never trade.

    2. Wires those classes into a `MasterBotShell` Robot with the
       constraint gate + multi-strategy dispatcher.

    3. Stamps lineage metadata in a header comment block plus a
       per-tier IR-vs-stub manifest line so operators can see which
       members shipped with real code vs refusal stubs.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db
from engines import master_bot_definition as mbd
from engines.strategy_ir import is_valid_ir
from cbot_engine.ir_transpiler import (
    transpile_ir_to_csharp,
    UnsupportedIROperatorError,
)

logger = logging.getLogger(__name__)

EXPORTS_COLL  = "master_bot_exports"
EXPORTER_VERSION = "v1.3"     # MB-7.1 — mode-specific dispatchers
EXPORT_DIR_DEFAULT = os.environ.get(
    "MASTER_BOT_EXPORT_DIR", "/app/data_imports/master_bots"
)

# Tier weight defaults (allocation-share-based). These are AUTHORITATIVE
# for the cBot shell — the definition's per-tier `allocation_share`
# overrides them.
DEFAULT_TIER_WEIGHTS = {"tier1": 0.50, "tier2": 0.33, "tier3": 0.17}


# ── Time helper ──────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_indexes() -> None:
    db = get_db()
    try:
        await db[EXPORTS_COLL].create_index("export_id", unique=True)
        await db[EXPORTS_COLL].create_index(
            [("master_bot_id", 1), ("created_at", -1)],
        )
        await db[EXPORTS_COLL].create_index("revision_id")
    except Exception:                                          # pragma: no cover
        logger.exception("master_bot_export: ensure_indexes failed")


# ── Identity helpers ────────────────────────────────────────────────

_NAME_RE = re.compile(r"[^A-Za-z0-9]")


def _csharp_safe(name: str, *, default: str = "X") -> str:
    sanitised = _NAME_RE.sub("", str(name or ""))
    if not sanitised or not sanitised[0].isalpha():
        sanitised = default + sanitised
    return sanitised or default


def _short_hash(h: Optional[str]) -> str:
    if not h:
        return "00000000"
    raw = h.split(":")[-1]
    return raw[:8]


def _class_name(prefix: str, strategy_hash: str) -> str:
    return f"{prefix}_{_csharp_safe(strategy_hash[:12], default='S')}"


# ── C# template ─────────────────────────────────────────────────────

_HEADER_TEMPLATE = """// =============================================================================
// AUTO-GENERATED — Master Bot V1 cBot shell
// DO NOT EDIT BY HAND. Regenerate via:
//   POST /api/master-bot/{{master_bot_id}}/export
//
// Master Bot:           {master_bot_name}  ({master_bot_id})
// Revision:             rev{rev}   ({revision_id})
// Definition hash:      {definition_hash}
// Exported at:          {exported_at}
// Exporter version:     {exporter_version}
// Definition engine:    {definition_engine_version}
// Ranker version:       {ranker_version}
// Ranker weights:       {ranker_weights}
// Runtime mode:         {runtime_mode}
//
// Members (enabled / total):
{member_summary_block}//
// LICENSE: Internal — AI Strategy Factory development branch.
// =============================================================================
"""

_SHELL_TEMPLATE = """using System;
using System.Collections.Generic;
using System.Linq;
using cAlgo.API;
using cAlgo.API.Indicators;
using cAlgo.API.Internals;

namespace cAlgo.MasterBot
{{
    /// <summary>
    /// Base contract for every tier strategy. Each generated
    /// Tier{{1,2,3}}Strategy_* class implements <see cref=\"Step\"/>.
    /// Step is called once per OnBar by the MasterBotShell dispatcher.
    /// </summary>
    public interface ITierStrategy
    {{
        string StrategyHash {{ get; }}
        string Pair         {{ get; }}
        string Timeframe    {{ get; }}
        string Style        {{ get; }}
        double Weight       {{ get; }}
        bool   Enabled      {{ get; set; }}
        void   OnStart(Robot robot);
        void   Step();
    }}

{tier_class_blocks}

    [Robot(AccessRights = AccessRights.None, AddIndicators = true)]
    public class {bot_class_name} : Robot
    {{
        // ── Configuration (frozen at export time) ────────────────
        public const string MASTER_BOT_ID      = \"{master_bot_id}\";
        public const string REVISION_ID        = \"{revision_id}\";
        public const string DEFINITION_HASH    = \"{definition_hash}\";
        public const string EXPORTER_VERSION   = \"{exporter_version}\";
        public const double TIER1_WEIGHT       = {tier1_weight};
        public const double TIER2_WEIGHT       = {tier2_weight};
        public const double TIER3_WEIGHT       = {tier3_weight};
        public const int    MAX_OPEN_POSITIONS = {max_open_positions};
        public const int    MAX_CONCURRENT_PER_PAIR = {max_concurrent_per_pair};
        public const double MAX_CORRELATION_PAIRS   = {max_correlation_pairs};

        // ── Tier rosters ─────────────────────────────────────────
        private readonly List<ITierStrategy> _t1 = new List<ITierStrategy>();
        private readonly List<ITierStrategy> _t2 = new List<ITierStrategy>();
        private readonly List<ITierStrategy> _t3 = new List<ITierStrategy>();

        protected override void OnStart()
        {{
            Print($\"[MasterBot] start id={{MASTER_BOT_ID}} rev={{REVISION_ID}}\");
{onstart_instantiations}

            foreach (var s in _t1.Concat(_t2).Concat(_t3))
                s.OnStart(this);
        }}

        protected override void OnBar()
        {{
            // Constraint gate — exit early when the firm rules say so.
            if (MAX_OPEN_POSITIONS > 0 && Positions.Count >= MAX_OPEN_POSITIONS)
                return;

{dispatcher_body}
        }}
{dispatcher_helpers}
    }}
}}
"""

# ── MB-7.1 — Mode-specific dispatcher templates ─────────────────────
#
# Each mode picks one of these strings as `dispatcher_body`. The
# `dispatcher_helpers` slot carries any per-mode private state +
# helper methods that live at the class scope. All three modes share
# the constraint gate above; per-mode logic begins after it.

_DISPATCHER_MULTI = """            // Mode: multi_strategy — every enabled member runs each bar.
            foreach (var s in _t1) if (s.Enabled) s.Step();
            foreach (var s in _t2) if (s.Enabled) s.Step();
            foreach (var s in _t3) if (s.Enabled) s.Step();"""

_DISPATCHER_HELPERS_MULTI = ""


_DISPATCHER_SINGLE = """            // Mode: single_active — tier-rank failover.
            // Choose the highest-ranked enabled strategy not in cooldown.
            var active = PickActive();
            if (active == null) return;
            try
            {{
                active.Step();
                _consecLoss.Remove(active.StrategyHash);
            }}
            catch (Exception ex)
            {{
                Print($\"[MasterBot] step_failed strategy={{active.StrategyHash}} ex={{ex.GetType().Name}} msg={{ex.Message}}\");
                _cooldownUntil[active.StrategyHash] = Server.Time.AddSeconds(COOLDOWN_SEC);
            }}"""

_DISPATCHER_HELPERS_SINGLE = """
        // ── Mode: single_active — failover state ──────────────────
        public const int COOLDOWN_SEC = 900;
        private readonly Dictionary<string, DateTime> _cooldownUntil = new Dictionary<string, DateTime>();
        private readonly Dictionary<string, int> _consecLoss = new Dictionary<string, int>();

        private ITierStrategy PickActive()
        {{
            // Tier order: tier1 → tier2 → tier3. Inside a tier, order_index ASC
            // (already preserved by the OnStart Add() order).
            foreach (var s in _t1.Concat(_t2).Concat(_t3))
            {{
                if (!s.Enabled) continue;
                DateTime until;
                if (_cooldownUntil.TryGetValue(s.StrategyHash, out until)
                    && Server.Time < until) continue;
                return s;
            }}
            return null;
        }}"""


_DISPATCHER_REGIME = """            // Mode: regime_aware — classify current regime, dispatch only
            // members whose snapshot.regime_fitness covers the active regime.
            var regime = ClassifyRegime();
            if (regime == \"unknown\") return;   // honest refusal — stay flat.

            foreach (var s in _t1) if (s.Enabled && RegimeOk(s, regime)) s.Step();
            foreach (var s in _t2) if (s.Enabled && RegimeOk(s, regime)) s.Step();
            foreach (var s in _t3) if (s.Enabled && RegimeOk(s, regime)) s.Step();"""

_DISPATCHER_HELPERS_REGIME = """
        // ── Mode: regime_aware — gating ───────────────────────────
        public const double MIN_REGIME_FITNESS = 0.20;
        public const int    REGIME_WINDOW_BARS = 50;

        private string ClassifyRegime()
        {{
            // V1: ATR-ratio + slope sign. Honest refusal on insufficient
            // history — never speculative.
            int n = REGIME_WINDOW_BARS;
            if (Bars.ClosePrices.Count < n + 2) return \"unknown\";
            double range = 0.0, sumRange = 0.0;
            for (int i = 1; i <= n; i++) sumRange += Math.Abs(Bars.HighPrices.Last(i) - Bars.LowPrices.Last(i));
            double avgRange = sumRange / n;
            double recent = Math.Abs(Bars.HighPrices.Last(1) - Bars.LowPrices.Last(1));
            double atrRatio = avgRange > 0 ? recent / avgRange : 0;
            double slope = Bars.ClosePrices.Last(1) - Bars.ClosePrices.Last(n);
            if (atrRatio > 1.6) return \"volatility\";
            if (Math.Abs(slope) / (avgRange * n + 1e-9) > 0.5) return \"trend\";
            return \"range\";
        }}

        private bool RegimeOk(ITierStrategy s, string regime)
        {{
            // V1: every IR-native strategy is treated as regime-fit
            // since per-member regime_fitness coverage maps are not
            // yet populated (future MB-11). Operators may toggle the
            // bot to multi_strategy mode if this is too permissive.
            return true;
        }}"""


_DISPATCHER_TEMPLATES = {
    "multi_strategy": (_DISPATCHER_MULTI,  _DISPATCHER_HELPERS_MULTI),
    "single_active":  (_DISPATCHER_SINGLE, _DISPATCHER_HELPERS_SINGLE),
    "regime_aware":   (_DISPATCHER_REGIME, _DISPATCHER_HELPERS_REGIME),
}

_STUB_STRATEGY_TEMPLATE = """    /// <summary>
    /// {tier_label} stub for strategy hash {strategy_hash}.
    /// Snapshot frozen at export time:
    ///   pair={pair}  tf={timeframe}  style={style}
    ///   PF={pf}  WR={wr}  PP={pp}  DS={ds}  score={score}
    ///   lifecycle={lifecycle}  notes={notes}
    /// IR was not attached at export — operator can swap this stub for
    /// the IR-transpiled implementation (POST /api/generate-cbot with
    /// strategy_ir, then paste the generated body inside Step()).
    /// </summary>
    public class {class_name} : ITierStrategy
    {{
        public string StrategyHash => \"{strategy_hash}\";
        public string Pair         => \"{pair}\";
        public string Timeframe    => \"{timeframe}\";
        public string Style        => \"{style}\";
        public double Weight       => {weight};
        public bool   Enabled      {{ get; set; }} = {enabled_csharp};

        private Robot _robot;
        public void OnStart(Robot robot) {{ _robot = robot; }}

        public void Step()
        {{
            // STUB — no trades opened. Replace with IR-transpiled body.
            // Per Master Bot V1 export contract: stub classes are
            // deterministic refusals, NEVER speculative trades.
        }}
    }}
"""


# ── MB-7.2 — IR-aware emission ─────────────────────────────────────
#
# Token list to delegate from the per-strategy class onto the parent
# Robot reference (`_robot`). Built from a survey of every emitter in
# `cbot_engine/ir_emitter.py` + `ir_templates.py`. New tokens may be
# added in future transpiler versions; this list is the conservative
# safe set we rewrite. Anything outside this set passes through
# unchanged (helper methods, locals, etc.).
_ROBOT_API_TOKENS = (
    "Bars", "Symbol", "Symbols", "Positions", "Indicators",
    "MarketData", "MarketSeries", "Print", "Account", "Server",
    "ExecuteMarketOrder", "ClosePosition", "ModifyPosition",
    "Notifications", "RunningMode", "Chart", "PendingOrders",
    "TimeInUtc", "History",
)

# Regex helpers compiled once.
import re as _re

_RE_ROBOT_ATTR = _re.compile(r"^\s*\[Robot\([^\]]*\)\]\s*$", _re.MULTILINE)
_RE_PARAM_ATTR = _re.compile(r"^\s*\[Parameter\([^\]]*\)\]\s*$", _re.MULTILINE)
_RE_NAMESPACE  = _re.compile(r"namespace\s+cAlgo\.Robots\s*\{")
_RE_CLASS_DECL = _re.compile(r"public\s+class\s+(\w+)\s*:\s*Robot")
_RE_ONSTART    = _re.compile(r"protected\s+override\s+void\s+OnStart\(\)")
_RE_ONBAR      = _re.compile(r"protected\s+override\s+void\s+OnBar\(\)")
_RE_USINGS     = _re.compile(r"^\s*using\s+[^;]+;\s*$", _re.MULTILINE)
_RE_HEADER     = _re.compile(r"^// ={5,}.*?^// ={5,}\s*$", _re.MULTILINE | _re.DOTALL)


def _delegate_token(src: str, token: str) -> str:
    """Prefix bare API tokens with `_robot.`. Skips occurrences that
    are already prefixed (`x.Bars`), inside string literals (heuristic),
    inside `<see cref=...>` doc comments, and right after `_robot.`."""
    # Build a regex that matches the token only when:
    #   * preceded by whitespace, `(`, `,`, `!`, `=`, `+`, `-`, `*`,
    #     `/`, `?`, `:` or start-of-line (NOT `.` or letter/digit/_)
    #   * not followed by a letter/digit/_ (avoid matching `BarsIndex`)
    pat = _re.compile(
        rf"(?<![A-Za-z0-9_.])({_re.escape(token)})(?![A-Za-z0-9_])",
    )
    return pat.sub(r"_robot.\1", src)


def _emit_ir_strategy_class(
    *,
    member: Dict[str, Any],
    ir_dict: Dict[str, Any],
    tier_label: str,
    class_name: str,
    transpile_result: Dict[str, Any],
) -> str:
    """Transform a per-strategy IR-transpiled cAlgo Robot into an
    `ITierStrategy`-conforming class that can be `new`-ed from the
    Master Bot shell's OnStart.

    Transformations (deterministic, regex-based, stable across the
    Phase 28-C transpiler scaffold):

      1. Strip the file-level `using …;` directives.
      2. Strip the file header comment block.
      3. Strip the `namespace cAlgo.Robots { … }` wrapper.
      4. Strip the `[Robot(...)]` attribute.
      5. Strip every `[Parameter(...)]` attribute (only valid on a
         Robot subclass). Property defaults inside the body are
         preserved.
      6. Rename the class declaration `public class X : Robot` →
         `public class <our_name> : ITierStrategy`.
      7. Replace `protected override void OnStart()` with
         `public void OnStart(Robot robot) { _robot = robot;`.
      8. Replace `protected override void OnBar()` with
         `public void Step()`.
      9. Prefix every cAlgo Robot API token (Bars, Symbol, Indicators,
         Print, ExecuteMarketOrder, …) with `_robot.` so the class
         operates against the parent robot's runtime context.
     10. Prepend the `ITierStrategy` boilerplate (StrategyHash, Pair,
         Timeframe, Style, Weight, Enabled, _robot field).

    The resulting class is compiled into the same .cs file as the
    Master Bot shell. cTrader's cAlgo runtime only registers the
    [Robot]-decorated class (our shell); the per-tier classes are
    plain helpers.
    """
    snap = member.get("snapshot") or {}
    src = transpile_result.get("csharp") or ""

    # 1+2+3 — strip preamble
    src = _RE_HEADER.sub("", src, count=1)
    src = _RE_USINGS.sub("", src)
    src = _RE_NAMESPACE.sub("", src, count=1)
    # Strip the *matching* trailing `}` of the namespace. We rely on
    # the fact that the namespace is the outermost wrapper; remove the
    # final closing brace before EOF.
    src = _re.sub(r"\}\s*\Z", "", src)

    # 4 — strip [Robot(...)] attribute
    src = _RE_ROBOT_ATTR.sub("", src)
    # 5 — strip [Parameter(...)] attributes (single-line; the scaffold
    # always emits them on their own line, never inline).
    src = _RE_PARAM_ATTR.sub("", src)

    # 6 — rename class header
    src = _RE_CLASS_DECL.sub(
        f"public class {class_name} : ITierStrategy",
        src, count=1,
    )

    # 7 — OnStart signature
    src = _RE_ONSTART.sub(
        "public void OnStart(Robot robot)",
        src, count=1,
    )
    # Inject `_robot = robot;` right after the opening brace of
    # OnStart. We locate it by string-search instead of regex to keep
    # the brace-balanced body intact.
    onstart_idx = src.find("public void OnStart(Robot robot)")
    if onstart_idx != -1:
        brace = src.find("{", onstart_idx)
        if brace != -1:
            src = (src[: brace + 1] + "\n            _robot = robot;"
                   + src[brace + 1 :])

    # 8 — OnBar → Step
    src = _RE_ONBAR.sub("public void Step()", src, count=1)

    # 9 — delegate cAlgo API tokens onto `_robot.`
    for tok in _ROBOT_API_TOKENS:
        src = _delegate_token(src, tok)

    # 10 — prepend ITierStrategy boilerplate. We splice it RIGHT after
    # the opening brace of the class declaration so the resulting
    # class is well-formed even when the body declares other fields
    # first.
    iface_block = (
        f"\n        public string StrategyHash => \"{member.get('strategy_hash') or ''}\";\n"
        f"        public string Pair         => \"{snap.get('pair') or 'UNKNOWN'}\";\n"
        f"        public string Timeframe    => \"{snap.get('timeframe') or 'UNKNOWN'}\";\n"
        f"        public string Style        => \"{snap.get('style') or 'mixed'}\";\n"
        f"        public double Weight       => {float(member.get('weight') or 1.0)};\n"
        f"        public bool   Enabled      {{ get; set; }} = {'true' if member.get('enabled') else 'false'};\n"
        f"        private Robot _robot;\n"
    )
    decl = f"public class {class_name} : ITierStrategy"
    idx = src.find(decl)
    if idx != -1:
        brace = src.find("{", idx)
        if brace != -1:
            src = src[: brace + 1] + iface_block + src[brace + 1 :]

    # Final cleanup — collapse 3+ blank lines and trim leading/trailing
    # whitespace so the embedded class is readable.
    src = _re.sub(r"\n{3,}", "\n\n", src).strip("\n")

    # Doc-comment header naming the source
    header = (
        f"    // ── {tier_label} · IR-transpiled · {member.get('strategy_hash') or ''}\n"
        f"    //    transpiler={transpile_result.get('transpiler_version')}  "
        f"ir_version={transpile_result.get('ir_version')}  "
        f"pair={snap.get('pair') or '?'}  tf={snap.get('timeframe') or '?'}\n"
    )
    return header + src + "\n"


def _try_emit_ir_class(
    member: Dict[str, Any], tier_label: str, class_name: str,
) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """Attempt to emit a real IR-backed class. Returns
    `(csharp_block, source_label, transpile_meta)`. On any failure
    (no IR, bad IR, transpiler refuses), returns
    `(None, reason, None)` and the caller falls back to the stub."""
    snap = member.get("snapshot") or {}
    ir = snap.get("strategy_ir")
    if not isinstance(ir, dict):
        return None, "no_ir", None
    if not is_valid_ir(ir):
        return None, "invalid_ir", None
    try:
        result = transpile_ir_to_csharp(ir)
    except UnsupportedIROperatorError as e:
        logger.warning(
            "master_bot_export: IR transpile refused for %s — %s",
            member.get("strategy_hash"), e,
        )
        return None, f"transpile_refused:{type(e).__name__}", None
    except Exception:                                          # pragma: no cover
        logger.exception(
            "master_bot_export: IR transpile crashed for %s",
            member.get("strategy_hash"),
        )
        return None, "transpile_crashed", None
    try:
        block = _emit_ir_strategy_class(
            member=member, ir_dict=ir, tier_label=tier_label,
            class_name=class_name, transpile_result=result,
        )
    except Exception:                                          # pragma: no cover
        logger.exception(
            "master_bot_export: IR class wrapping failed for %s",
            member.get("strategy_hash"),
        )
        return None, "wrapping_failed", None
    return block, "ir_native", {
        "transpiler_version": result.get("transpiler_version"),
        "ir_version":         result.get("ir_version"),
        "operators_used":     (result.get("metadata") or {}).get("operators_used"),
        "indicator_kinds_used": (result.get("metadata") or {}).get("indicator_kinds_used"),
    }


def _emission_summary(log: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Roll up per-member emission outcomes into operator-visible counts."""
    summary = {"total": len(log), "ir_native": 0, "stub": 0, "stub_reasons": {}}
    for entry in log:
        src = entry.get("source") or ""
        if src == "ir_native":
            summary["ir_native"] += 1
        else:
            summary["stub"] += 1
            # Strip the "stub:" prefix for clean reason aggregation.
            reason = src[5:] if src.startswith("stub:") else src
            summary["stub_reasons"][reason] = summary["stub_reasons"].get(reason, 0) + 1
    summary["ir_coverage_pct"] = round(
        100.0 * summary["ir_native"] / (summary["total"] or 1), 2,
    )
    return summary


def _member_summary_lines(payload: Dict[str, Any]) -> str:
    parts: List[str] = []
    for tier in payload.get("tiers") or []:
        tk = tier.get("tier_key")
        members = tier.get("members") or []
        total = len(members)
        enabled = sum(1 for m in members if m.get("enabled"))
        parts.append(f"//   {tk}: {enabled} enabled / {total} total")
        for m in members:
            snap = m.get("snapshot") or {}
            on = "ON " if m.get("enabled") else "OFF"
            parts.append(
                f"//     - [{on}] {m.get('strategy_hash')}  "
                f"{snap.get('pair') or '?'} / {snap.get('timeframe') or '?'}  "
                f"PF={snap.get('profit_factor')} PP={snap.get('pass_probability')} "
                f"DS={snap.get('deploy_score')}  score={snap.get('candidate_score')}"
            )
    return "\n".join(parts) + ("\n" if parts else "")


def _tier_weight(payload: Dict[str, Any], tier_key: str) -> float:
    for t in payload.get("tiers") or []:
        if t.get("tier_key") == tier_key:
            v = t.get("allocation_share")
            if isinstance(v, (int, float)):
                return float(v)
    return float(DEFAULT_TIER_WEIGHTS.get(tier_key, 0.0))


def _emit_stub_class(m: Dict[str, Any], tier_label: str, class_name: str) -> str:
    snap = m.get("snapshot") or {}
    return _STUB_STRATEGY_TEMPLATE.format(
        tier_label    = tier_label,
        class_name    = class_name,
        strategy_hash = m.get("strategy_hash") or "",
        pair          = snap.get("pair") or "UNKNOWN",
        timeframe     = snap.get("timeframe") or "UNKNOWN",
        style         = snap.get("style") or "mixed",
        pf            = snap.get("profit_factor"),
        wr            = snap.get("win_rate"),
        pp            = snap.get("pass_probability"),
        ds            = snap.get("deploy_score"),
        score         = snap.get("candidate_score"),
        lifecycle     = snap.get("lifecycle_stage") or "unknown",
        weight        = float(m.get("weight") or 1.0),
        enabled_csharp = "true" if m.get("enabled") else "false",
        notes         = (m.get("notes") or "").replace("*/", "*∕"),
    )


def _render_csharp(payload: Dict[str, Any], *, revision: Dict[str, Any]) -> Tuple[str, str, List[Dict[str, Any]]]:
    bot = payload.get("master_bot") or {}
    constraints = bot.get("constraints") or {}
    tier_class_blocks: List[str] = []
    onstart_lines: List[str] = []
    _emission_log: List[Dict[str, Any]] = []
    tier_prefix = {"tier1": "Tier1Strategy", "tier2": "Tier2Strategy", "tier3": "Tier3Strategy"}
    tier_field  = {"tier1": "_t1", "tier2": "_t2", "tier3": "_t3"}
    tier_labels = {"tier1": "Tier 1", "tier2": "Tier 2", "tier3": "Tier 3"}

    for tier in payload.get("tiers") or []:
        tk = tier.get("tier_key")
        if tk not in tier_prefix:
            continue
        for m in tier.get("members") or []:
            cls = _class_name(tier_prefix[tk], m.get("strategy_hash") or "S")
            # MB-7.2 — prefer real IR-transpiled logic when the member
            # snapshot carries a validated strategy_ir. Honest refusal
            # falls back to the deterministic stub.
            ir_block, source_label, ir_meta = _try_emit_ir_class(
                m, tier_labels[tk], cls,
            )
            if ir_block is not None:
                tier_class_blocks.append(ir_block)
                _emission_log.append({
                    "strategy_hash": m.get("strategy_hash"),
                    "tier":          tk,
                    "class_name":    cls,
                    "source":        source_label or "ir_native",
                    "ir_meta":       ir_meta,
                })
            else:
                tier_class_blocks.append(
                    _emit_stub_class(m, tier_labels[tk], cls),
                )
                _emission_log.append({
                    "strategy_hash": m.get("strategy_hash"),
                    "tier":          tk,
                    "class_name":    cls,
                    "source":        f"stub:{source_label or 'no_ir'}",
                    "ir_meta":       None,
                })
            onstart_lines.append(
                f"            {tier_field[tk]}.Add(new {cls}());"
            )

    if not onstart_lines:
        onstart_lines.append("            // (no members)")

    bot_class_name = "MasterBot_" + _csharp_safe(
        (bot.get("name") or "Bot") + "_" + _short_hash(revision.get("definition_hash")),
    )

    ranker = payload.get("ranker") or {}
    weights_repr = json.dumps(ranker.get("weights") or {}, sort_keys=True)
    runtime_mode = (payload.get("runtime") or {}).get("mode") or "multi_strategy"
    dispatcher_body, dispatcher_helpers = _DISPATCHER_TEMPLATES.get(
        runtime_mode, _DISPATCHER_TEMPLATES["multi_strategy"],
    )

    header = _HEADER_TEMPLATE.format(
        master_bot_name = bot.get("name") or "(unnamed)",
        master_bot_id   = bot.get("id") or "",
        rev             = revision.get("rev"),
        revision_id     = revision.get("revision_id") or "",
        definition_hash = revision.get("definition_hash") or "",
        exported_at     = _now_iso(),
        exporter_version = EXPORTER_VERSION,
        definition_engine_version = payload.get("definition_engine_version") or "v1.0",
        ranker_version  = ranker.get("version") or "v1.0",
        ranker_weights  = weights_repr,
        runtime_mode    = runtime_mode,
        member_summary_block = _member_summary_lines(payload),
    ).replace("{master_bot_id}", bot.get("id") or "")  # header has {{master_bot_id}}

    shell = _SHELL_TEMPLATE.format(
        tier_class_blocks       = "\n".join(tier_class_blocks),
        bot_class_name          = bot_class_name,
        master_bot_id           = bot.get("id") or "",
        revision_id             = revision.get("revision_id") or "",
        definition_hash         = revision.get("definition_hash") or "",
        exporter_version        = EXPORTER_VERSION,
        tier1_weight            = _tier_weight(payload, "tier1"),
        tier2_weight            = _tier_weight(payload, "tier2"),
        tier3_weight            = _tier_weight(payload, "tier3"),
        max_open_positions      = int(constraints.get("max_open_positions") or 0),
        max_concurrent_per_pair = int(constraints.get("max_concurrent_per_pair") or 0),
        max_correlation_pairs   = float(constraints.get("max_correlation_pairs") or 0.0),
        onstart_instantiations  = "\n".join(onstart_lines),
        dispatcher_body         = dispatcher_body,
        dispatcher_helpers      = dispatcher_helpers,
    )

    return header + "\n" + shell, bot_class_name, _emission_log


# ── Public: export ──────────────────────────────────────────────────

def _export_dir() -> str:
    out = os.environ.get("MASTER_BOT_EXPORT_DIR") or EXPORT_DIR_DEFAULT
    os.makedirs(out, exist_ok=True)
    return out


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


async def export_master_bot(
    master_bot_id: str,
    *,
    revision_id: Optional[str] = None,
    compile_if_missing: bool = True,
    force_parity: bool = False,
    actor: str = "admin",
) -> Dict[str, Any]:
    """Export the named revision (or compile a fresh one) into .cs +
    metadata sidecar. Returns a dict with paths + sha256 + ids.

    MB-10 — Parity gate: when `MB_PARITY_GATE_ENABLED=1` in the
    environment, every enabled member must have a PASSED parity
    sign-off (`cbot_parity_signoff.status == "PASSED"`) before the
    `.cs` is rendered. Missing or non-PASSED sign-offs raise
    `ParityGateError`. Admins can pass `force_parity=true` to bypass
    the gate for emergency exports — the verdict is still computed
    and stamped on the export row as `parity_verdict` for audit.
    """
    await ensure_indexes()

    # Resolve the definition revision.
    revision: Optional[Dict[str, Any]] = None
    if revision_id:
        revision = await mbd.get_definition(revision_id=revision_id)
        if not revision:
            raise ValueError("revision not found")
        if revision.get("master_bot_id") != master_bot_id:
            raise ValueError("revision does not belong to this master bot")
    else:
        revision = await mbd.get_definition(master_bot_id=master_bot_id)
        if not revision and compile_if_missing:
            revision = await mbd.compile_definition(
                master_bot_id, actor=actor,
            )
        if not revision:
            raise ValueError("no compiled definition; compile first or pass compile_if_missing=true")

    # MB-10 — parity gate (opt-in via env or admin force_parity).
    # On non-enforced runs we still compute the verdict for audit.
    from engines import parity_certification as parity
    gate_enabled = parity.is_parity_gate_enabled()
    parity_verdict: Optional[Dict[str, Any]] = None
    if gate_enabled and not force_parity:
        try:
            parity_verdict = await parity.assert_pass(
                revision.get("revision_id"), enforce=True,
            )
        except parity.ParityGateError:
            # Re-raise with structured detail; API layer translates to 409.
            raise
    else:
        # Advisory pass — record but never block.
        try:
            parity_verdict = await parity.assert_pass(
                revision.get("revision_id"), enforce=False,
            )
        except Exception:                                       # pragma: no cover
            logger.exception("master_bot_export: advisory parity check failed")

    payload = revision.get("payload") or {}
    bot = payload.get("master_bot") or {}
    bot_name_safe = _csharp_safe(bot.get("name") or "MasterBot", default="MasterBot")
    short = _short_hash(revision.get("definition_hash"))
    rev = int(revision.get("rev") or 0)
    base = f"{bot_name_safe}_rev{rev}_{short}"

    cs_text, csharp_class_name, emission_log = _render_csharp(payload, revision=revision)
    cs_bytes  = cs_text.encode("utf-8")
    cs_sha    = _sha256_bytes(cs_bytes)

    meta_doc = {
        "master_bot_id":  master_bot_id,
        "revision_id":    revision.get("revision_id"),
        "rev":            rev,
        "definition_hash": revision.get("definition_hash"),
        "exporter_version": EXPORTER_VERSION,
        "csharp_class":   csharp_class_name,
        "filename_cs":    f"{base}.cs",
        "filename_meta":  f"{base}.json",
        "sha256_cs":      cs_sha,
        "exported_at":    _now_iso(),
        "exported_by":    actor,
        # MB-7.2 — per-member emission report (real IR vs stub).
        "emission_log":   emission_log,
        "emission_summary": _emission_summary(emission_log),
        # MB-10 — parity verdict captured here for audit.
        "parity_verdict": parity_verdict,
        "parity_gate_enabled": gate_enabled,
        "parity_overridden":  bool(force_parity),
        "payload":        payload,
    }
    meta_bytes = json.dumps(meta_doc, sort_keys=True, indent=2).encode("utf-8")
    meta_sha   = _sha256_bytes(meta_bytes)
    meta_doc["sha256_meta"] = meta_sha

    out_dir = _export_dir()
    cs_path   = os.path.join(out_dir, f"{base}.cs")
    meta_path = os.path.join(out_dir, f"{base}.json")
    with open(cs_path, "wb") as f:
        f.write(cs_bytes)
    with open(meta_path, "wb") as f:
        # Re-write so sha256_meta is included in the file too.
        f.write(json.dumps(meta_doc, sort_keys=True, indent=2).encode("utf-8"))

    export_id = uuid.uuid4().hex
    db = get_db()
    export_row = {
        "export_id":     export_id,
        "master_bot_id": master_bot_id,
        "revision_id":   revision.get("revision_id"),
        "rev":           rev,
        "target":        "cs_text",
        "cs_path":       cs_path,
        "meta_path":     meta_path,
        "filename_cs":   f"{base}.cs",
        "filename_meta": f"{base}.json",
        "sha256_cs":     cs_sha,
        "sha256_meta":   meta_sha,
        "exporter_version": EXPORTER_VERSION,
        "csharp_class":  csharp_class_name,
        # MB-7.2 — emission summary surfaced on row for UI badges.
        "emission_summary": _emission_summary(emission_log),
        # MB-10 — parity verdict (advisory or enforced).
        "parity_verdict": parity_verdict,
        "parity_gate_enabled": gate_enabled,
        "parity_overridden":  bool(force_parity),
        "exported_by":   actor,
        "created_at":    _now_iso(),
    }
    await db[EXPORTS_COLL].insert_one(export_row)

    # Stamp the definition's export_targets slot.
    try:
        await mbd.record_export_target(
            revision.get("revision_id"),
            "cs_text",
            {
                "export_id":  export_id,
                "cs_path":    cs_path,
                "meta_path":  meta_path,
                "sha256_cs":  cs_sha,
                "sha256_meta": meta_sha,
                "exported_at": export_row["created_at"],
            },
        )
    except Exception:                                          # pragma: no cover
        logger.exception("master_bot_export: record_export_target failed")

    return {k: v for k, v in export_row.items() if k != "_id"}


async def list_exports(
    master_bot_id: str, *, limit: int = 50,
) -> List[Dict[str, Any]]:
    db = get_db()
    cur = db[EXPORTS_COLL].find(
        {"master_bot_id": master_bot_id}, {"_id": 0}
    ).sort("created_at", -1).limit(int(limit))
    return [d async for d in cur]


async def read_export_artifact(
    export_id: str, *, kind: str = "cs",
) -> Tuple[str, bytes]:
    """Return (filename, bytes) for the given export. kind ∈ {'cs','meta'}."""
    db = get_db()
    row = await db[EXPORTS_COLL].find_one(
        {"export_id": export_id}, {"_id": 0}
    )
    if not row:
        raise ValueError("export not found")
    if kind == "cs":
        path = row.get("cs_path")
        filename = row.get("filename_cs")
    elif kind == "meta":
        path = row.get("meta_path")
        filename = row.get("filename_meta")
    else:
        raise ValueError("kind must be 'cs' or 'meta'")
    if not path or not os.path.exists(path):
        raise ValueError("export artifact missing on disk")
    with open(path, "rb") as f:
        return filename, f.read()
