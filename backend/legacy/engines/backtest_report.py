"""
Phase 7.5 — Backtest Intelligence Layer (foundation).

Produces a structured JSON report from backtest artifacts that the UI layer
(Report Dashboard, Trade Visualization, Deep Dive Panel) will consume in a
later phase.

This module is intentionally LEAN: only the core metrics + equity/DD curves
+ a trimmed trade list with the canonical fields. No MAE/MFE, no advanced
analytics, no visualization. Recomputation is avoided — it consumes what
backtest_engine / challenge_simulator already computed.

Used as a post-processing step: it never mutates inputs and its output is
attached to the existing response under the new `report` key (additive).
"""

from __future__ import annotations

from typing import Iterable, Optional


# Canonical trade fields the UI layer will expect. Missing fields are filled
# with safe defaults (None / derived) — existing trade dicts are not mutated.
_REQUIRED_TRADE_FIELDS = (
    "entry_time", "entry_price",
    "exit_time", "exit_price",
    "direction", "sl", "tp", "outcome",
)


class BacktestReport:
    """Build a structured report (pure data, JSON-serialisable)."""

    def __init__(
        self,
        trades: list,
        equity_curve: list,
        config: Optional[dict] = None,
        initial_balance: float = 10000.0,
        drawdown_curve: Optional[list] = None,
    ):
        self.trades = trades or []
        self.equity_curve = equity_curve or []
        self.config = config or {}
        self.initial_balance = float(initial_balance)
        self._drawdown_curve = drawdown_curve

    # ── Public API ───────────────────────────────────────────────
    def build(self) -> dict:
        return {
            "summary": self._summary(),
            "equity_curve": list(self.equity_curve),
            "drawdown_curve": self._drawdown_curve_resolved(),
            "trades": [self._normalize_trade(t) for t in self.trades],
            "config": self._config_snapshot(),
        }

    # ── Summary metrics (core only) ──────────────────────────────
    def _summary(self) -> dict:
        trades = self.trades
        total = len(trades)
        wins = [t for t in trades if float(t.get("net_pnl", 0) or 0) > 0]
        losses = [t for t in trades if float(t.get("net_pnl", 0) or 0) < 0]
        gross_win = sum(float(t.get("net_pnl", 0) or 0) for t in wins)
        gross_loss = sum(float(t.get("net_pnl", 0) or 0) for t in losses)  # negative
        net_profit = gross_win + gross_loss

        profit_factor = None
        if gross_loss < 0:
            profit_factor = round(gross_win / abs(gross_loss), 2)
        elif gross_win > 0:
            profit_factor = float("inf")

        win_rate = round((len(wins) / total) * 100.0, 2) if total else 0.0
        max_dd = self._max_drawdown_from_curve()

        return {
            "net_profit": round(net_profit, 2),
            "max_drawdown": round(max_dd, 2),
            "profit_factor": profit_factor,
            "win_rate": win_rate,
            "total_trades": total,
        }

    # ── Drawdown helpers ─────────────────────────────────────────
    def _drawdown_curve_resolved(self) -> list:
        if self._drawdown_curve is not None:
            return list(self._drawdown_curve)
        return _compute_drawdown_curve(self.equity_curve)

    def _max_drawdown_from_curve(self) -> float:
        dd = self._drawdown_curve_resolved()
        return max(dd) if dd else 0.0

    # ── Trade normalization ──────────────────────────────────────
    def _normalize_trade(self, t: dict) -> dict:
        """Return a shallow copy with canonical UI-facing fields populated.
        Never mutates the input. Missing fields get safe defaults.
        """
        out = dict(t)
        # Canonical aliases — populate only if absent.
        out.setdefault("direction", t.get("side"))
        out.setdefault("sl", t.get("sl_price"))
        out.setdefault("tp", t.get("tp_price"))
        out.setdefault("outcome", t.get("result"))
        out.setdefault("entry_time", t.get("entry_timestamp") or t.get("entry_idx"))
        out.setdefault("exit_time", t.get("exit_timestamp") or t.get("exit_idx"))
        # Ensure the required keys always exist (even if None).
        for k in _REQUIRED_TRADE_FIELDS:
            out.setdefault(k, None)
        return out

    # ── Config passthrough ───────────────────────────────────────
    def _config_snapshot(self) -> dict:
        """Echo a compact subset of config (execution + sim params) for
        audit trail in the report. Never fabricates values."""
        cfg = self.config or {}
        out = {"initial_balance": self.initial_balance}
        for k in ("pair", "timeframe", "strategy_type", "fast_period",
                  "slow_period", "sl_pips", "tp_pips", "risk_percent"):
            if k in cfg:
                out[k] = cfg[k]
        exec_cfg = cfg.get("execution")
        if isinstance(exec_cfg, dict):
            out["execution"] = {
                "enabled": bool(exec_cfg.get("enabled")),
                "spread": float(exec_cfg.get("spread") or 0.0),
                "max_slippage": float(exec_cfg.get("max_slippage") or 0.0),
                "commission_per_trade": float(exec_cfg.get("commission_per_trade") or 0.0),
            }
        return out


# ── Module-level helpers ──────────────────────────────────────────

def _compute_drawdown_curve(equity_curve: Iterable[float]) -> list:
    """Running peak-to-equity drop (USD). Parallel to equity_curve length.
    Each point is max(0, peak - equity). A flat equity curve → all zeros.
    """
    out: list = []
    peak = float("-inf")
    for v in equity_curve:
        val = float(v)
        if val > peak:
            peak = val
        out.append(round(peak - val, 2))
    return out


def build_report(
    trades: list,
    equity_curve: list,
    config: Optional[dict] = None,
    initial_balance: float = 10000.0,
    drawdown_curve: Optional[list] = None,
) -> dict:
    """Convenience wrapper. Returns the structured report dict."""
    return BacktestReport(
        trades=trades,
        equity_curve=equity_curve,
        config=config,
        initial_balance=initial_balance,
        drawdown_curve=drawdown_curve,
    ).build()
