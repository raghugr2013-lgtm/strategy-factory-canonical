"""
Phase 2 — Rule Enforcement Layer.

Pure, reusable validation primitives called by the Phase 1 simulator.

Exports:
  - validate_position_size(trade, max_lot_per_trade)
  - pre_simulation_exposure_check(trades, max_total_exposure)
  - ExposureTracker          — aggregate notional across open positions
  - TrailingDrawdownTracker  — distinct static / trailing_balance / trailing_equity

Drawdown semantics (corrected from legacy):
  static           → floor = initial_balance - max_total_dd_usd       (immutable)
  trailing_balance → floor = peak_CLOSED_balance - max_total_dd_usd   (ratchets on realized PnL)
  trailing_equity  → floor = peak_FLOATING_equity - max_total_dd_usd  (ratchets on equity incl. floating)

Back-compat alias:
  "trailing" → "trailing_equity"   (matches historical behavior of _calc_total_dd
                                    which always used peak_equity)

No side effects outside the caller's tracker instances. No DB, no network.
"""

from __future__ import annotations

from typing import Any, Optional


# ═══════════════════════════════════════════════════════════════════════
# Drawdown-type constants
# ═══════════════════════════════════════════════════════════════════════
STATIC = "static"
TRAILING_BALANCE = "trailing_balance"
TRAILING_EQUITY = "trailing_equity"
_VALID_DD_TYPES = {STATIC, TRAILING_BALANCE, TRAILING_EQUITY}


def normalize_dd_type(dd_type: Optional[str]) -> str:
    """Normalize drawdown-type string. Legacy 'trailing' → 'trailing_equity'."""
    if dd_type is None or dd_type == "":
        return STATIC
    if dd_type == "trailing":
        return TRAILING_EQUITY
    if dd_type in _VALID_DD_TYPES:
        return dd_type
    raise ValueError(
        f"Unknown trailing DD type: {dd_type!r}. "
        f"Expected one of: static, trailing_balance, trailing_equity."
    )


# ═══════════════════════════════════════════════════════════════════════
# Position sizing
# ═══════════════════════════════════════════════════════════════════════
def get_trade_lot_size(trade: dict) -> Optional[float]:
    """Extract lot size using the keys the simulator accepts."""
    for key in ("lot_size", "volume", "lots"):
        v = trade.get(key)
        if v is not None:
            return float(v)
    return None


def get_trade_notional(trade: dict) -> float:
    """
    Aggregate-exposure contribution for a single trade.

    Preference:
      1. explicit 'notional'
      2. lot_size * entry_price  (when both present)
      3. lot_size                (treated as notional unit)
      4. 0.0                     (no size info — trade ignored for exposure)
    """
    n = trade.get("notional")
    if n is not None:
        return float(n)
    lot = get_trade_lot_size(trade)
    if lot is None:
        return 0.0
    price = trade.get("entry_price") or trade.get("price")
    if price is not None:
        return float(lot) * float(price)
    return float(lot)


def validate_position_size(
    trade: dict,
    max_lot_per_trade: Optional[float],
) -> Optional[dict]:
    """Return a violation dict if `trade.lot_size > max_lot_per_trade`, else None."""
    if max_lot_per_trade is None:
        return None
    lot = get_trade_lot_size(trade)
    if lot is None:
        return None
    if lot > max_lot_per_trade:
        return {
            "type": "lot_size_exceeded",
            "lot_size": float(lot),
            "limit": float(max_lot_per_trade),
        }
    return None


# ═══════════════════════════════════════════════════════════════════════
# Aggregate exposure
# ═══════════════════════════════════════════════════════════════════════
class ExposureTracker:
    """Aggregate notional across open positions.

    Event-driven: `open(id, notional)` on position open, `close(id)` on close.
    Returns a violation dict from `open()` when the projected aggregate exceeds
    `max_total_exposure`; the position is NOT recorded in that case.
    """

    def __init__(self, max_total_exposure: Optional[float] = None) -> None:
        self.max_total_exposure = max_total_exposure
        self._open: dict[Any, float] = {}
        self._peak: float = 0.0

    @property
    def current(self) -> float:
        return sum(self._open.values())

    @property
    def peak(self) -> float:
        return self._peak

    def open(self, trade_id: Any, notional: float) -> Optional[dict]:
        if notional <= 0:
            return None
        projected = self.current + float(notional)
        if (
            self.max_total_exposure is not None
            and projected > self.max_total_exposure
        ):
            return {
                "type": "exposure_exceeded",
                "current_exposure": self.current,
                "trade_notional": float(notional),
                "projected_exposure": projected,
                "limit": float(self.max_total_exposure),
            }
        self._open[trade_id] = float(notional)
        if projected > self._peak:
            self._peak = projected
        return None

    def close(self, trade_id: Any) -> None:
        self._open.pop(trade_id, None)


def _trade_entry_ts(trade: dict) -> Optional[str]:
    v = (
        trade.get("entry_time")
        or trade.get("open_time")
        or trade.get("timestamp")
    )
    return str(v) if v is not None else None


def _trade_exit_ts(trade: dict) -> Optional[str]:
    v = (
        trade.get("exit_time")
        or trade.get("close_time")
        or trade.get("timestamp")
    )
    return str(v) if v is not None else None


def pre_simulation_exposure_check(
    trades: list,
    max_total_exposure: Optional[float],
) -> Optional[dict]:
    """
    Walk trades in time order and detect the first aggregate-exposure breach.

    - Trades with explicit entry_time != exit_time participate in overlap tracking.
    - Trades that are instantaneous (single timestamp or entry==exit) are checked
      only against the per-trade notional cap (they cannot overlap themselves).
    - When entry==exit for a given trade, exits are processed before entries at
      the same timestamp so released exposure is available to the next entry.
    """
    if max_total_exposure is None:
        return None

    events: list[tuple[str, str, int, float]] = []
    for i, t in enumerate(trades):
        notional = get_trade_notional(t)
        if notional <= 0:
            continue

        entry_ts = _trade_entry_ts(t)
        exit_ts = _trade_exit_ts(t)

        # Instantaneous trade — a single notional check against the cap.
        if entry_ts is None or exit_ts is None or entry_ts == exit_ts:
            if notional > max_total_exposure:
                return {
                    "type": "exposure_exceeded",
                    "trade_index": i,
                    "current_exposure": 0.0,
                    "trade_notional": notional,
                    "projected_exposure": notional,
                    "limit": float(max_total_exposure),
                    "at_time": entry_ts or "",
                }
            continue

        events.append((entry_ts, "entry", i, notional))
        events.append((exit_ts, "exit", i, notional))

    # At the same timestamp, process exits first (free capacity before new entry).
    events.sort(key=lambda e: (e[0], 0 if e[1] == "exit" else 1))

    tracker = ExposureTracker(max_total_exposure)
    for ts, kind, idx, notional in events:
        if kind == "exit":
            tracker.close(idx)
        else:
            v = tracker.open(idx, notional)
            if v is not None:
                v["trade_index"] = idx
                v["at_time"] = ts
                return v
    return None


# ═══════════════════════════════════════════════════════════════════════
# Trailing drawdown
# ═══════════════════════════════════════════════════════════════════════
class TrailingDrawdownTracker:
    """
    Encapsulates the three total-DD variants behind one API.

      static           → floor = initial_balance - max_total_dd_usd
      trailing_balance → floor = peak_balance    - max_total_dd_usd
      trailing_equity  → floor = peak_equity     - max_total_dd_usd

    The simulator feeds:
      - update_balance(balance) after each realized PnL change.
      - update_equity(equity)   after each equity observation (realized or floating).
    """

    def __init__(
        self,
        dd_type: str,
        initial_balance: float,
        max_total_dd_usd: float,
    ) -> None:
        self.dd_type = normalize_dd_type(dd_type)
        self.initial_balance = float(initial_balance)
        self.max_total_dd_usd = float(max_total_dd_usd)
        self.peak_balance = float(initial_balance)
        self.peak_equity = float(initial_balance)
        self._max_dd_usd_seen = 0.0

    # ── state updates ──
    def update_balance(self, balance: float) -> None:
        b = float(balance)
        if b > self.peak_balance:
            self.peak_balance = b

    def update_equity(self, equity: float) -> None:
        e = float(equity)
        if e > self.peak_equity:
            self.peak_equity = e

    # ── floor & drawdown ──
    @property
    def floor(self) -> float:
        if self.dd_type == STATIC:
            return self.initial_balance - self.max_total_dd_usd
        if self.dd_type == TRAILING_BALANCE:
            return self.peak_balance - self.max_total_dd_usd
        # TRAILING_EQUITY
        return self.peak_equity - self.max_total_dd_usd

    def drawdown(self, equity: float) -> float:
        """Current total drawdown in USD at a given equity point (never negative)."""
        if self.dd_type == STATIC:
            return max(0.0, self.initial_balance - float(equity))
        if self.dd_type == TRAILING_BALANCE:
            return max(0.0, self.peak_balance - float(equity))
        # TRAILING_EQUITY
        return max(0.0, self.peak_equity - float(equity))

    def observe(self, equity: float) -> float:
        """Compute drawdown at `equity` and record the worst seen. Returns dd."""
        dd = self.drawdown(equity)
        if dd > self._max_dd_usd_seen:
            self._max_dd_usd_seen = dd
        return dd

    def is_breached(self, equity: float) -> bool:
        return self.drawdown(equity) > self.max_total_dd_usd

    @property
    def max_drawdown_usd(self) -> float:
        return self._max_dd_usd_seen
