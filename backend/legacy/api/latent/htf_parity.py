"""
P1.4 — Dormant HTF parity validation preview endpoint.

``POST /api/latent/htf-parity`` — auth-gated, read-only, advisory-only.

Two call modes:

* Live mode (``strategy_hash`` supplied): the endpoint resolves the
  IR via the same I/O seam used by ``cbot_parity.sign_off_parity``
  (``strategy_library`` → ``mutation_events`` → ``strategy_lifecycle``),
  loads a recent price fixture from market_data via
  ``data_access.load_ohlc_bars``, and runs
  ``engines.htf_parity.validate_htf_parity(...)``.

* Direct mode (``ir`` + ``fixture`` supplied): for unit-testing the
  validator without round-tripping through Mongo. Useful for the
  operator's local validation scripts and for the dormancy test
  suite.

Discipline:
    * NEVER writes.
    * NEVER triggers a backfill.
    * ``advisory_only=true``, ``governance_authority=false``,
      ``operator_authority="final"``.
    * The handler ALWAYS calls into the validator regardless of the
      ``ENABLE_HTF_PARITY_VALIDATION`` flag — the flag governs whether
      a future ``sign_off_parity`` wiring would consult the validator,
      not whether the operator can preview its output. The response
      surfaces ``flag_active`` so the operator can confirm the gate.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth_utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


_DEFAULT_FIXTURE_BARS = 240
_MIN_FIXTURE_BARS = 80


class HtfParityFixture(BaseModel):
    prices:     List[float] = Field(default_factory=list)
    highs:      List[float] = Field(default_factory=list)
    lows:       List[float] = Field(default_factory=list)
    timestamps: List[Any]   = Field(default_factory=list)


class HtfParityRequest(BaseModel):
    strategy_hash:     Optional[str] = None
    ir:                Optional[Dict[str, Any]] = None
    fixture:           Optional[HtfParityFixture] = None
    pair:              Optional[str] = None
    timeframe:         Optional[str] = None
    n_bars:            int = Field(default=_DEFAULT_FIXTURE_BARS, ge=_MIN_FIXTURE_BARS, le=2000)
    tolerance_pct:     Optional[float] = Field(default=None, ge=0.0, le=100.0)


@router.post("/latent/htf-parity")
async def post_htf_parity(
    req: HtfParityRequest,
    _user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run the HTF parity validator against either a stored strategy
    (``strategy_hash``) or a direct (``ir``, ``fixture``) pair.
    """
    from engines.htf_parity import is_enabled, validate_htf_parity

    base: Dict[str, Any] = {
        "endpoint":             "/api/latent/htf-parity",
        "read_only":            True,
        "advisory_only":        True,
        "governance_authority": False,
        "operator_authority":   "final",
        "flag_active":          is_enabled(),
    }

    # ── Resolve IR + fixture (live mode vs direct mode) ─────────────
    ir: Optional[Dict[str, Any]] = req.ir
    pair: Optional[str] = (req.pair or "").upper() or None
    tf: Optional[str] = (req.timeframe or "").upper() or None
    fixture_meta: Dict[str, Any] = {}
    prices: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    timestamps: List[Any] = []

    if req.fixture is not None and (req.fixture.prices or []):
        # Direct mode — caller supplies the bars.
        fx = req.fixture
        if not (len(fx.prices) == len(fx.highs) == len(fx.lows) == len(fx.timestamps)):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "fixture_length_mismatch",
                    "details": (
                        f"prices={len(fx.prices)} highs={len(fx.highs)} "
                        f"lows={len(fx.lows)} timestamps={len(fx.timestamps)}"
                    ),
                },
            )
        prices = list(fx.prices)
        highs = list(fx.highs)
        lows = list(fx.lows)
        timestamps = list(fx.timestamps)
        fixture_meta = {
            "source": "direct",
            "pair":   pair,
            "timeframe": tf,
            "bars":   len(prices),
        }
        if ir is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "error":   "ir_required_with_direct_fixture",
                    "details": "Pass `ir` alongside `fixture` in direct mode.",
                },
            )
    elif req.strategy_hash:
        # Live mode — resolve IR + fixture from Mongo.
        try:
            from engines.cbot_parity import _find_ir_for_strategy, _load_price_fixture
        except Exception as e:                              # pragma: no cover
            raise HTTPException(
                status_code=500,
                detail={"error": "cbot_parity_unavailable", "details": str(e)[:300]},
            )
        if ir is None:
            ir = await _find_ir_for_strategy(req.strategy_hash)
        if ir is None:
            return {
                **base,
                "verdict":          "NO_IR",
                "strategy_hash":    req.strategy_hash,
                "details":          (
                    "No IR found for strategy. Save via mutation_engine "
                    "or supply ir directly."
                ),
            }
        md = (ir.get("metadata") or {}) if isinstance(ir, dict) else {}
        pair = (pair or md.get("pair") or "EURUSD").upper()
        tf = (tf or md.get("timeframe") or "H1").upper()
        loaded = await _load_price_fixture(pair, tf, n_bars=req.n_bars)
        if loaded is None:
            return {
                **base,
                "verdict":          "NO_DATA",
                "strategy_hash":    req.strategy_hash,
                "fixture":          {"pair": pair, "timeframe": tf, "bars": 0, "source": "market_data"},
                "details":          (
                    f"Insufficient market_data for {pair}/{tf} "
                    f"(<{_MIN_FIXTURE_BARS} bars). Ingest data first."
                ),
            }
        closes, hi, lo, ts = loaded
        prices, highs, lows, timestamps = closes, hi, lo, ts
        fixture_meta = {
            "source":    "market_data",
            "pair":      pair,
            "timeframe": tf,
            "bars":      len(prices),
        }
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "missing_input",
                "details": (
                    "Supply either `strategy_hash` (live mode) "
                    "or `ir` + `fixture` (direct mode)."
                ),
            },
        )

    # ── Run the validator ───────────────────────────────────────────
    result = validate_htf_parity(
        ir,
        prices=prices, highs=highs, lows=lows,
        timestamps=timestamps,
        strategy_timeframe=tf or "H1",
        tolerance_pct=req.tolerance_pct,
    )

    return {
        **base,
        "strategy_hash":  req.strategy_hash,
        "fixture":        fixture_meta,
        **result,
    }
