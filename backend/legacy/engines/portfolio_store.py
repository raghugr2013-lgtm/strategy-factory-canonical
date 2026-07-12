"""
P1 — Multi-Asset Portfolio Store.

Thin persistence layer on top of MongoDB `multi_asset_portfolios`
collection. Used by the `/api/dashboard/portfolios/*` endpoints to
save / list / load / delete validated multi-asset portfolios so the
frontend can reload them without re-running the pipeline, and future
flows (paper exec, live trading, forward testing) have a stable
anchor.

Schema (one doc per portfolio):
    {
      portfolio_id:   str (uuid4 hex),
      name:           str,
      pairs:          [str],
      timeframe:      str,
      style:          str,
      firm:           str,
      gate_config:    {threshold, max_dd_pct, seeds, population, generations},
      strategies: [
        {
          strategy_id, pair, timeframe, style, strategy_text,
          verdict, score, params,
          backtest: {profit_factor, max_drawdown_pct, net_profit,
                     total_trades, win_rate, total_return_pct},
          equity_curve, initial_balance, phase4, phase5,
        },
        ...
      ],
      combined_metrics:         {total_return_pct, max_drawdown_pct, volatility},
      diversification_grade:    'A'|'B'|'C'|'D'|'F',
      avg_correlation:          float,
      portfolio_risk_score:     float,
      asset_contributions_pct:  {PAIR: pct},
      num_strategies:           int,
      pairs_passed:             [str],
      pairs_rejected:           [{pair, reason, error}],
      source:                   'multi_asset_rollout',
      created_at, updated_at:   datetime (UTC ISO)
    }

Strict contract:
    * Functions never raise — return `{"success": False, "error": "..."}`.
    * `_id` is NEVER returned in responses.
    * `datetime.now(timezone.utc)` for timestamps.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "multi_asset_portfolios"

# Minimum bar for saving: diversification grade must be A or B and at
# least 2 pairs passed the gate. This prevents users from saving
# obvious failures.
SAVE_ALLOWED_GRADES = {"A", "B"}
MIN_PAIRS_PASSED = 2

# Response projection — explicitly excludes `_id` so it never leaks.
_RESPONSE_PROJECTION = {"_id": 0}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────

def _validate_for_save(portfolio_result: dict) -> tuple[bool, str | None]:
    """Return (ok, reason). Only PASS-grade portfolios can be saved."""
    port = (portfolio_result or {}).get("portfolio") or {}
    if not port:
        return False, "no_portfolio_block_in_result"
    grade = (port.get("diversification_grade") or "").upper()
    if grade not in SAVE_ALLOWED_GRADES:
        return False, f"grade_below_threshold: {grade or 'UNGRADED'} (allowed: {sorted(SAVE_ALLOWED_GRADES)})"
    passed = portfolio_result.get("pairs_passed") or []
    if len(passed) < MIN_PAIRS_PASSED:
        return False, f"fewer_than_{MIN_PAIRS_PASSED}_pairs_passed"
    if (port.get("num_strategies") or 0) < 2:
        return False, "fewer_than_two_strategies"
    return True, None


# ─────────────────────────────────────────────────────────────────────
# Normalisation — build a compact persisted-strategy record
# ─────────────────────────────────────────────────────────────────────

def _compact_strategy(card: dict) -> dict:
    bt = card.get("backtest") or {}
    return {
        "strategy_id": card.get("strategy_id"),
        "pair":        card.get("pair"),
        "timeframe":   card.get("timeframe"),
        "style":       card.get("style"),
        "strategy_text": card.get("strategy_text"),
        "verdict":     card.get("verdict"),
        "score":       card.get("score"),
        "params":      card.get("params") or (card.get("optimized") or {}).get("params"),
        "backtest": {
            "profit_factor":    _safe_float(bt.get("profit_factor")),
            "max_drawdown_pct": _safe_float(bt.get("max_drawdown_pct")),
            "net_profit":       _safe_float(bt.get("net_profit")),
            "total_return_pct": _safe_float(bt.get("total_return_pct")),
            "total_trades":     bt.get("total_trades"),
            "win_rate":         _safe_float(bt.get("win_rate")),
        },
        # Keep the compact equity curve the card already carries so the
        # portfolio can be rebuilt / replayed without re-running the
        # backtest engine.
        "equity_curve":     card.get("equity_curve"),
        "initial_balance":  card.get("initial_balance"),
        "phase4":           card.get("phase4"),
        "phase5":           card.get("phase5"),
    }


def _build_persisted_doc(
    *,
    name: str,
    portfolio_result: dict,
    request_echo: dict,
) -> dict:
    port = portfolio_result.get("portfolio") or {}
    cm = port.get("combined_metrics") or {}

    # Collect strategies across every passing pair.
    strategies: list[dict] = []
    for entry in portfolio_result.get("per_pair") or []:
        if not entry.get("passed"):
            continue
        for card in entry.get("top_strategies") or []:
            strategies.append(_compact_strategy({**card, "pair": entry.get("pair")}))

    now = _now_iso()
    return {
        "portfolio_id": uuid.uuid4().hex,
        "name":         name.strip(),
        "pairs":        list(request_echo.get("pairs") or []),
        "timeframe":    request_echo.get("timeframe"),
        "style":        request_echo.get("style"),
        "firm":         request_echo.get("firm"),
        "gate_config":  request_echo.get("gate_config") or {},
        "strategies":   strategies,
        "num_strategies":         port.get("num_strategies") or len(strategies),
        "combined_metrics": {
            "total_return_pct": _safe_float(cm.get("total_return_pct")),
            "max_drawdown_pct": _safe_float(cm.get("max_drawdown_pct")),
            "volatility":       _safe_float(cm.get("volatility")),
            "total_profit":     _safe_float(cm.get("total_profit")),
        },
        "diversification_grade":   (port.get("diversification_grade") or "").upper() or None,
        "avg_correlation":         _safe_float(port.get("avg_correlation")),
        "portfolio_risk_score":    _safe_float(port.get("portfolio_risk_score")),
        "asset_contributions_pct": port.get("asset_contributions_pct") or {},
        "pairs_passed":            list(portfolio_result.get("pairs_passed") or []),
        "pairs_rejected":          list(portfolio_result.get("pairs_rejected") or []),
        "source":     "multi_asset_rollout",
        "created_at": now,
        "updated_at": now,
    }


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

async def save_portfolio(
    *,
    name: str,
    portfolio_result: dict,
    request_echo: dict | None = None,
) -> dict:
    """Persist a validated multi-asset portfolio.

    Blocks when validation gates fail (grade < B, < 2 pairs passed).
    """
    if not name or not name.strip():
        return {"success": False, "error": "name_required"}
    ok, reason = _validate_for_save(portfolio_result)
    if not ok:
        return {"success": False, "error": "validation_failed", "reason": reason}
    try:
        db = get_db()
        doc = _build_persisted_doc(
            name=name,
            portfolio_result=portfolio_result,
            request_echo=request_echo or {},
        )
        await db[COLLECTION].insert_one(dict(doc))  # MongoDB mutates; we pass a copy
        return {
            "success": True,
            "portfolio_id": doc["portfolio_id"],
            "name":         doc["name"],
            "grade":        doc["diversification_grade"],
            "num_strategies": doc["num_strategies"],
            "created_at":   doc["created_at"],
        }
    except Exception as e:
        logger.warning("save_portfolio failed: %s", e)
        return {"success": False, "error": f"save_failed: {e}"}


async def list_portfolios(*, limit: int = 100) -> dict:
    """Return every saved portfolio (newest first), minus heavy fields.

    The list view intentionally strips `strategies` / `equity_curve`
    data so the grid load stays snappy; callers hit
    `load_portfolio(portfolio_id)` for the full record.
    """
    try:
        db = get_db()
        cursor = db[COLLECTION].find(
            {},
            {
                # Exclude the heavy fields from the list view + `_id`.
                "_id": 0,
                "strategies": 0,
            },
        ).sort("created_at", -1).limit(max(1, int(limit)))
        items = [doc async for doc in cursor]
        return {"success": True, "count": len(items), "items": items}
    except Exception as e:
        logger.warning("list_portfolios failed: %s", e)
        return {"success": False, "error": f"list_failed: {e}", "items": []}


async def load_portfolio(portfolio_id: str) -> dict:
    """Return the full portfolio doc including every pinned strategy."""
    if not portfolio_id:
        return {"success": False, "error": "portfolio_id_required"}
    try:
        db = get_db()
        doc = await db[COLLECTION].find_one(
            {"portfolio_id": portfolio_id},
            _RESPONSE_PROJECTION,
        )
        if not doc:
            return {"success": False, "error": "not_found"}
        return {"success": True, "portfolio": doc}
    except Exception as e:
        logger.warning("load_portfolio failed: %s", e)
        return {"success": False, "error": f"load_failed: {e}"}


async def delete_portfolio(portfolio_id: str) -> dict:
    if not portfolio_id:
        return {"success": False, "error": "portfolio_id_required"}
    try:
        db = get_db()
        res = await db[COLLECTION].delete_one({"portfolio_id": portfolio_id})
        if res.deleted_count == 0:
            return {"success": False, "error": "not_found"}
        return {"success": True, "portfolio_id": portfolio_id, "deleted": res.deleted_count}
    except Exception as e:
        logger.warning("delete_portfolio failed: %s", e)
        return {"success": False, "error": f"delete_failed: {e}"}


async def count_portfolios() -> int:
    """Small helper for tests / diagnostics."""
    try:
        db = get_db()
        return await db[COLLECTION].count_documents({})
    except Exception:
        return 0
