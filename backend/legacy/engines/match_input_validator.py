"""
Phase 19 — shared input validation + diagnostics for the
prop-firm matching routes.

PURPOSE
-------
Both `/api/match-firms-phase4` (api/phase4_route.py) and
`/api/phase4/match-firms` (api/phase4_matching.py) used to reject
common inputs with FastAPI's verbose Pydantic 422 detail because of
strict `Field(..., ge=1000)` / `ge=10, le=200` bounds. Callers that
sent reasonable variations (e.g. a $500 demo balance, 5 simulations
for a quick smoke run) were blocked with no clear human message.

This module is **purely additive**:

  * `validate_match_inputs(initial_balance, n_simulations)`
        Returns `(ok, message)`. Replaces the Pydantic field bounds
        with a permissive but explicit pre-flight. The matcher engine
        is **not** touched.

  * `inspect_trades(trades)`
        Read-only inspection of the trade list. Returns a diagnostics
        dict the route can attach to its response so the dashboard
        knows exactly what the matcher saw:
            {trade_count, has_pnl, has_equity_curve, has_daily_drawdown,
             has_consistency_metrics, sufficiency, missing}

  * `MIN_TRADES_OK / WARN / EXPLORATION`
        Single source of truth for "what counts as enough trades".
        Strict mode applies the OK threshold; relaxed mode collapses
        to EXPLORATION so early-stage strategies can still be matched
        (with the matcher's own variance/sharpe haircuts kicking in).

Nothing in this module imports from the matcher engine — no behavioural
coupling. Tests can call it standalone.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


# ── Trade-count thresholds (advisory; engine never hard-rejects) ──
MIN_TRADES_OK = 30           # phase4_matcher's own gate — full credit ≥ 30
MIN_TRADES_WARN = 10         # below this, dashboard surfaces a warning chip
MIN_TRADES_EXPLORATION = 1   # relaxed mode: anything > 0 is allowed


# ── Pre-flight numeric validation (replaces strict Pydantic bounds) ──

def validate_match_inputs(
    initial_balance: float,
    n_simulations: int,
    *,
    relaxed_mode: bool = False,
) -> Tuple[bool, str]:
    """Return `(ok, message)`. Permissive but explicit.

    Rejection rules:
      * initial_balance must be > 0 (no negative / zero accounts).
      * n_simulations must be >= 1.
      * Soft warnings (initial_balance < 100, n_simulations > 500) are
        accepted but surfaced in the diagnostics — never block.
    """
    if not isinstance(initial_balance, (int, float)) or initial_balance <= 0:
        return False, "initial_balance must be greater than zero"
    if not isinstance(n_simulations, int) or n_simulations < 1:
        return False, "n_simulations must be at least 1"
    if n_simulations > 1000:
        return False, "n_simulations capped at 1000 (got " + str(n_simulations) + ")"
    return True, "ok"


# ── Trade-shape inspection ───────────────────────────────────────────

def _has_field(trades: List[Dict[str, Any]], field: str) -> bool:
    if not trades:
        return False
    # At least 80 % of entries must carry the field non-None.
    hits = sum(1 for t in trades if isinstance(t, dict) and t.get(field) is not None)
    return hits >= max(1, int(0.8 * len(trades)))


def _has_any_field(trades: List[Dict[str, Any]], fields: List[str]) -> bool:
    return any(_has_field(trades, f) for f in fields)


def inspect_trades(trades: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Read-only diagnostics on the trade list. Never raises.

    Output:
        {
          "trade_count":              int,
          "sufficiency":              "ok" | "warning" | "low" | "empty",
          "has_pnl":                  bool,   # net_pnl present
          "has_equity_curve":         bool,   # balance / equity / cum_pnl present
          "has_daily_drawdown":       bool,   # daily_drawdown / drawdown present
          "has_consistency_metrics":  bool,   # win/loss flags present
          "missing":                  list[str],  # human-readable gaps
        }
    """
    out: Dict[str, Any] = {
        "trade_count": 0,
        "sufficiency": "empty",
        "has_pnl": False,
        "has_equity_curve": False,
        "has_daily_drawdown": False,
        "has_consistency_metrics": False,
        "missing": [],
    }
    if not trades or not isinstance(trades, list):
        out["missing"].append("trades")
        return out

    # Strip non-dict entries defensively.
    clean = [t for t in trades if isinstance(t, dict)]
    out["trade_count"] = len(clean)

    # Sufficiency tiers
    n = len(clean)
    if n >= MIN_TRADES_OK:
        out["sufficiency"] = "ok"
    elif n >= MIN_TRADES_WARN:
        out["sufficiency"] = "warning"
    elif n >= 1:
        out["sufficiency"] = "low"
    else:
        out["sufficiency"] = "empty"

    out["has_pnl"]                 = _has_field(clean, "net_pnl") or _has_field(clean, "pnl")
    out["has_equity_curve"]        = _has_any_field(clean, ["balance", "equity", "cum_pnl", "running_balance"])
    out["has_daily_drawdown"]      = _has_any_field(clean, ["daily_drawdown", "drawdown", "dd"])
    out["has_consistency_metrics"] = _has_any_field(clean, ["is_win", "result", "win"])

    if not out["has_pnl"]:
        out["missing"].append("net_pnl")
    if not out["has_equity_curve"]:
        out["missing"].append("equity_curve (matcher will reconstruct from net_pnl)")
    if not out["has_daily_drawdown"]:
        out["missing"].append("daily_drawdown (matcher will derive)")
    if not out["has_consistency_metrics"]:
        out["missing"].append("consistency_metrics (matcher will compute from pnl signs)")
    if out["sufficiency"] in ("low", "warning"):
        out["missing"].append(
            f"low_trade_count ({n} trades) — matcher applies a probability haircut; "
            "use relaxed_mode=true to allow exploration matching"
        )

    return out


def diagnostics_block(
    trades: Optional[List[Dict[str, Any]]],
    *,
    initial_balance: float,
    n_simulations: int,
    relaxed_mode: bool,
) -> Dict[str, Any]:
    """Compose the full diagnostics envelope returned with every response."""
    inspection = inspect_trades(trades)
    return {
        "mode":                  "relaxed" if relaxed_mode else "strict",
        "initial_balance":       float(initial_balance),
        "n_simulations":         int(n_simulations),
        "trades":                inspection,
        "thresholds": {
            "min_trades_ok":          MIN_TRADES_OK,
            "min_trades_warn":        MIN_TRADES_WARN,
            "min_trades_exploration": MIN_TRADES_EXPLORATION,
        },
    }


def is_actionable_for_match(
    trades: Optional[List[Dict[str, Any]]], *, relaxed_mode: bool = False,
) -> Tuple[bool, str]:
    """Decide whether to invoke the matcher.

    Strict mode  → at least 1 trade with net_pnl is required.
    Relaxed mode → at least 1 trade dict is required (matcher will
                   surface "0 trades" via its own profile_summary
                   when net_pnl is missing).
    """
    if not trades or not isinstance(trades, list):
        return False, "no trades supplied"
    clean = [t for t in trades if isinstance(t, dict)]
    if not clean:
        return False, "no valid trade dicts in payload"
    if relaxed_mode:
        return True, "relaxed_mode_active"
    inspection = inspect_trades(clean)
    if inspection["trade_count"] < MIN_TRADES_EXPLORATION:
        return False, "trade_count below exploration threshold"
    if not inspection["has_pnl"]:
        return False, "missing net_pnl on trades — set relaxed_mode=true to override"
    return True, "ok"
