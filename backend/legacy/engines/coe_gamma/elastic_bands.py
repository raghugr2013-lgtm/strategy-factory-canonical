"""Phase 2 Stage 4 P4B.6 — Elastic band redistribution.

BACKTEST ↔ MUTATION capacity loans. When BACKTEST queue depth exceeds
`ELASTIC_HIGH_WATER` and MUTATION is idle (queue empty), MUTATION
reservations temporarily loan capacity to BACKTEST. Reservations
restored on the next scoring cycle when either condition breaks.

Feature flag: `COE_ELASTIC_BAND_ENABLED` (default OFF). When off,
`compute_plan()` returns a no-op plan → reservations remain at their
static values.

Pure math — the orchestrator applies the plan via a single kwarg on
its scoring pass.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


def _flag(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "y", "on")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default


def is_elastic_bands_enabled() -> bool:
    return _flag("COE_ELASTIC_BAND_ENABLED", False)


DEFAULT_HIGH_WATER = 50
DEFAULT_LOAN_MAX_PCT = 0.5   # cap loan at 50% of donor reservation


@dataclass
class ElasticBandPlan:
    """One redistribution snapshot.

    Attributes:
        active: True iff the plan modifies reservations.
        donor: Class name that is loaning capacity ("mutation").
        receiver: Class name receiving capacity ("backtest").
        donor_reservation_before: Original reservation for the donor.
        donor_reservation_after: Effective reservation after loan.
        receiver_reservation_before / after: same for receiver.
        loan_amount: How much reservation was moved.
        reason: Free-form.
    """
    active:                       bool = False
    donor:                        str  = ""
    receiver:                     str  = ""
    donor_reservation_before:     int  = 0
    donor_reservation_after:      int  = 0
    receiver_reservation_before:  int  = 0
    receiver_reservation_after:   int  = 0
    loan_amount:                  int  = 0
    reason:                       str  = "flag_off"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ElasticBandRedistributor:
    """Computes the current BACKTEST ↔ MUTATION loan plan.

    Args:
        get_queue_depth: `(class) → int` returning the queue depth.
        get_reservation: `(class) → int` returning the static reservation.
    """

    def __init__(
        self,
        *,
        get_queue_depth,
        get_reservation,
    ) -> None:
        self._depth = get_queue_depth
        self._reservation = get_reservation

    def compute_plan(self) -> ElasticBandPlan:
        if not is_elastic_bands_enabled():
            return ElasticBandPlan(reason="flag_off")
        try:
            bt_depth = int(self._depth("backtest"))
            mu_depth = int(self._depth("mutation"))
            bt_res   = int(self._reservation("backtest"))
            mu_res   = int(self._reservation("mutation"))
        except Exception:                                       # noqa: BLE001
            return ElasticBandPlan(reason="lookup_failed")

        high_water = _int_env("ELASTIC_HIGH_WATER", DEFAULT_HIGH_WATER)
        if bt_depth < high_water:
            return ElasticBandPlan(reason="below_high_water",
                                    donor_reservation_before=mu_res,
                                    donor_reservation_after=mu_res,
                                    receiver_reservation_before=bt_res,
                                    receiver_reservation_after=bt_res)
        if mu_depth > 0:
            return ElasticBandPlan(reason="donor_busy",
                                    donor_reservation_before=mu_res,
                                    donor_reservation_after=mu_res,
                                    receiver_reservation_before=bt_res,
                                    receiver_reservation_after=bt_res)

        # Loan up to 50% of the donor's reservation
        loan = max(0, int(mu_res * DEFAULT_LOAN_MAX_PCT))
        if loan <= 0:
            return ElasticBandPlan(reason="loan_zero",
                                    donor_reservation_before=mu_res,
                                    donor_reservation_after=mu_res,
                                    receiver_reservation_before=bt_res,
                                    receiver_reservation_after=bt_res)
        return ElasticBandPlan(
            active=True,
            donor="mutation",
            receiver="backtest",
            donor_reservation_before=mu_res,
            donor_reservation_after=mu_res - loan,
            receiver_reservation_before=bt_res,
            receiver_reservation_after=bt_res + loan,
            loan_amount=loan,
            reason="active_loan",
        )
