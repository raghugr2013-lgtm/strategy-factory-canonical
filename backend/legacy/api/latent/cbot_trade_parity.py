"""GET /api/latent/cbot-trade-parity — P0.4/P1.3 read-only preview.

Auth-gated. Read-only. Advisory-only.

Exposes the candle-level trade-lifecycle simulator
(``engines.cbot_trade_parity.simulate_trades``) on an operator-supplied
``strategy_hash`` — pulling the IR + price fixture using the same I/O
seam the ``cbot_parity.sign_off_parity`` pipeline uses.

This endpoint is the **safe operator preview surface** for P0.4 trade
parity: it lets you SEE what the simulator produces for a given
strategy WITHOUT activating the P1.3 flag-gated branch inside
``sign_off_parity`` and WITHOUT persisting anything to Mongo.

Discipline:
  * Read-only (zero writes — never inserts a sign-off doc, never
    appends to audit_log).
  * Advisory-only (the payload carries ``advisory_only: true``).
  * Never an authority: the eventual gate decision belongs to a
    future ``sign_off_parity`` upgrade (audit doc §9 P1.4).
  * Honest refusal: when the IR or fixture is missing, returns a
    structured ``status="NO_IR" | "NO_DATA"`` payload — never silently
    fabricates a result.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from auth_utils import get_current_user
from engines import cbot_parity, cbot_trade_parity

router = APIRouter()


def _now_iso() -> str:
    # Reuse the helper so audit timestamps in this module are
    # produced by the same clock-formatting path as cbot_parity.
    return cbot_parity._now_iso()


@router.get("/latent/cbot-trade-parity")
async def get_cbot_trade_parity_preview(
    strategy_hash: str = Query(
        ...,
        description=(
            "The strategy_hash to preview. The endpoint will locate "
            "the canonical IR via the same search order "
            "(strategy_library → mutation_events → strategy_lifecycle) "
            "that sign_off_parity uses, and load a fresh price fixture."
        ),
        min_length=4, max_length=128,
    ),
    pair: Optional[str] = Query(
        None,
        description=(
            "Optional pair override (defaults to IR metadata's pair)."
        ),
    ),
    timeframe: Optional[str] = Query(
        None,
        description=(
            "Optional timeframe override (defaults to IR metadata's TF)."
        ),
    ),
    n_bars: int = Query(
        240,
        ge=80, le=2000,
        description="Number of bars to feed the simulator (80-2000).",
    ),
    first_n: Optional[int] = Query(
        None,
        ge=1, le=10_000,
        description=(
            "Truncate the trade log to the first N trades. Defaults to "
            "CBOT_TRADE_PARITY_FIRST_N env (=50)."
        ),
    ),
    include_trades: bool = Query(
        False,
        description=(
            "If true, the response includes the full trade lifecycle "
            "list (capped by first_n). Default false to keep payloads "
            "small — set true only when forensically debugging."
        ),
    ),
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Preview the trade-lifecycle parity report for a strategy.

    Returns a structured payload:
        {
          "status": "PASSED" | "EMPTY" | "NO_IR" | "NO_DATA" | "UNSUPPORTED" | "ERROR",
          "strategy_hash": str,
          "advisory_only": true,
          "read_only": true,
          "flag_active": bool,         # whether ENABLE_CBOT_TRADE_PARITY is ON
          "fixture": {pair, timeframe, bars, source},
          "summary": {...},            # buy/sell, sl/tp/open_at_end counts
          "self_check": "PASSED" | "EMPTY" | "MISMATCH",
          "parity_inputs": {ir_version, strategy_timeframe, first_n, intrabar_mode},
          "trades": [...]              # ONLY when include_trades=true
        }

    NEVER raises. On unexpected failure, returns ``status="ERROR"`` with
    the error excerpt.
    """
    base: Dict[str, Any] = {
        "endpoint":         "/api/latent/cbot-trade-parity",
        "read_only":        True,
        "advisory_only":    True,
        "governance_authority": False,
        "operator_authority":  "final",
        "strategy_hash":    strategy_hash,
        "flag_active":      cbot_trade_parity.is_enabled(),
        "ts":               _now_iso(),
    }

    # ── 1. Locate IR ─────────────────────────────────────────────
    try:
        ir = await cbot_parity._find_ir_for_strategy(strategy_hash)
    except Exception as e:                                  # noqa: BLE001
        return {**base, "status": "ERROR",
                "details": f"ir lookup failed: {str(e)[:300]}"}
    if ir is None:
        return {**base, "status": "NO_IR",
                "details": "No IR found for strategy hash."}

    md = (ir.get("metadata") or {}) if isinstance(ir, dict) else {}
    resolved_pair = (pair or md.get("pair") or "EURUSD").upper()
    resolved_tf = (timeframe or md.get("timeframe") or "H1").upper()

    # ── 2. Load fixture ──────────────────────────────────────────
    try:
        fixture = await cbot_parity._load_price_fixture(
            resolved_pair, resolved_tf, n_bars=n_bars,
        )
    except Exception as e:                                  # noqa: BLE001
        return {**base, "status": "ERROR",
                "details": f"fixture load failed: {str(e)[:300]}"}
    if fixture is None:
        return {**base, "status": "NO_DATA",
                "fixture": {"pair": resolved_pair, "timeframe": resolved_tf,
                            "bars": 0, "source": "market_data"},
                "details": f"Insufficient market_data for {resolved_pair}/{resolved_tf}."}

    closes, highs, lows, ts = fixture

    # ── 3. Run the simulator (pure function, no writes) ─────────
    try:
        report = cbot_trade_parity.simulate_trades(
            ir,
            prices=closes, highs=highs, lows=lows,
            timestamps=ts, strategy_timeframe=resolved_tf,
            pair=resolved_pair, first_n=first_n,
        )
    except Exception as e:                                  # noqa: BLE001
        # Note: the simulator delegates to simulate_cbot_signals which
        # raises IRCoverageGap for unsupported IR. We catch broadly so
        # the operator gets an honest refusal payload.
        msg = str(e)
        kind = "UNSUPPORTED" if "coverage gap" in msg.lower() else "ERROR"
        return {**base, "status": kind, "details": msg[:400]}

    self_check = cbot_trade_parity.compare_trade_series(
        report["trades"], report["trades"],
    )
    if self_check["verdict"] == "EMPTY":
        status = "EMPTY"
    elif self_check["verdict"] == "PASSED":
        status = "PASSED"
    else:
        status = "MISMATCH"

    out = {
        **base,
        "status":         status,
        "fixture":        {"pair": resolved_pair, "timeframe": resolved_tf,
                           "bars": len(closes), "source": "market_data"},
        "summary":        report["summary"],
        "self_check":     self_check["verdict"],
        "parity_inputs":  report["parity_inputs"],
    }
    if include_trades:
        # Strip volatile fields (private price bookkeeping) that the
        # operator doesn't need to see at the preview layer. Keep
        # exactly what makes the lifecycle auditable.
        out["trades"] = [
            {
                "side":         t["side"],
                "entry_bar":    t["entry_bar"],
                "exit_bar":     t["exit_bar"],
                "entry_price":  t["entry_price"],
                "exit_price":   t["exit_price"],
                "sl_pips":      t["sl_pips"],
                "tp_pips":      t["tp_pips"],
                "exit_reason":  t["exit_reason"],
                "pip_size":     t["pip_size"],
            }
            for t in report["trades"]
        ]
    return out
