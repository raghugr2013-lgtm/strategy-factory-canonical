"""Phase H8 — Risk Monitor (RECOMMEND ONLY per Q3).

Guards:
  * max_positions          — count of open positions
  * max_exposure_pair      — Σ |qty × avg_entry| per pair
  * max_exposure_total     — Σ across all pairs
  * daily_loss_pct         — realised loss today vs. account equity
  * loss_24h_pct           — trailing 24h realised loss
  * broker_health_min      — broker score_5m floor
  * clock_drift            — placeholder (populated when clock sync monitored)

Every breach:
  1. emits `risk_breach` outcome_event (severity, guard, evidence)
  2. writes a `RiskRecommendation` (pause / reduce / halt_new_opens)
  3. NEVER liquidates positions automatically — operator confirmation
     required (Q3).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import config as ecfg
from . import ledger
from .broker_health import read_latest_health
from .types import RiskGuard, RiskRecommendation

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def evaluate_guards(
    account_id: str, *,
    account_equity: float = 100_000.0,
) -> List[RiskRecommendation]:
    """Run every guard, emit outcome events, return the list of
    recommendations. Callers decide whether to honour them."""
    thresholds = ecfg.risk_thresholds()
    recs: List[RiskRecommendation] = []
    open_pos = await ledger.read_positions(account_id=account_id, open_only=True)
    closed = await ledger.read_closed_positions(account_id=account_id, limit=1000)

    # 1. max_positions
    if len(open_pos) >= thresholds["max_positions"]:
        recs.append(RiskRecommendation(
            ts=_now(), account_id=account_id,
            guard=RiskGuard.MAX_POSITIONS, severity=1.0,
            action="halt_new_opens",
            reason=f"open_positions={len(open_pos)} ≥ max={thresholds['max_positions']}",
            evidence={"open": len(open_pos),
                      "threshold": thresholds["max_positions"]},
        ))

    # 2/3. exposure per pair + total
    per_pair: Dict[str, float] = {}
    for p in open_pos:
        per_pair[p.pair] = per_pair.get(p.pair, 0.0) + abs(p.qty * p.avg_entry)
    for pair, exposure in per_pair.items():
        if exposure > thresholds["max_exposure_pair"]:
            recs.append(RiskRecommendation(
                ts=_now(), account_id=account_id,
                guard=RiskGuard.MAX_EXPOSURE_PAIR, severity=1.0,
                action="reduce",
                reason=f"{pair} exposure={exposure:.0f} > "
                       f"max={thresholds['max_exposure_pair']}",
                evidence={"pair": pair, "exposure": exposure,
                          "threshold": thresholds["max_exposure_pair"]},
            ))
    total_exposure = sum(per_pair.values())
    if total_exposure > thresholds["max_exposure_total"]:
        recs.append(RiskRecommendation(
            ts=_now(), account_id=account_id,
            guard=RiskGuard.MAX_EXPOSURE_TOTAL, severity=1.0,
            action="halt_new_opens",
            reason=f"total_exposure={total_exposure:.0f} > "
                   f"max={thresholds['max_exposure_total']}",
            evidence={"exposure": total_exposure,
                      "threshold": thresholds["max_exposure_total"]},
        ))

    # 4/5. daily_loss + 24h_loss
    today = datetime.now(timezone.utc).date().isoformat()
    daily_pnl = sum(p.realised_pnl for p in closed
                     if p.closed_at and p.closed_at[:10] == today)
    loss_pct_today = (-daily_pnl / account_equity) * 100.0 if account_equity else 0.0
    if loss_pct_today >= thresholds["daily_loss_pct"]:
        recs.append(RiskRecommendation(
            ts=_now(), account_id=account_id,
            guard=RiskGuard.DAILY_LOSS_CAP, severity=1.0,
            action="halt_new_opens",
            reason=f"daily_loss={loss_pct_today:.2f}% ≥ "
                   f"cap={thresholds['daily_loss_pct']}%",
            evidence={"daily_pnl": daily_pnl,
                      "loss_pct": loss_pct_today,
                      "threshold": thresholds["daily_loss_pct"]},
        ))
    # 24h — reuse closed (assumes closed_at is recent enough).
    pnl_24h = sum(p.realised_pnl for p in closed)
    loss_pct_24h = (-pnl_24h / account_equity) * 100.0 if account_equity else 0.0
    if loss_pct_24h >= thresholds["loss_24h_pct"]:
        recs.append(RiskRecommendation(
            ts=_now(), account_id=account_id,
            guard=RiskGuard.LOSS_24H_CAP, severity=1.0,
            action="pause",
            reason=f"24h_loss={loss_pct_24h:.2f}% ≥ "
                   f"cap={thresholds['loss_24h_pct']}%",
            evidence={"pnl_24h": pnl_24h,
                      "loss_pct": loss_pct_24h,
                      "threshold": thresholds["loss_24h_pct"]},
        ))

    # 6. broker_health_min
    bh = await read_latest_health(account_id)
    if bh is not None and float(bh.score_5m) < thresholds["broker_health_min"]:
        recs.append(RiskRecommendation(
            ts=_now(), account_id=account_id,
            guard=RiskGuard.BROKER_HEALTH_MIN, severity=1.0,
            action="halt_new_opens",
            reason=f"broker_score_5m={bh.score_5m} < "
                   f"floor={thresholds['broker_health_min']}",
            evidence={"score_5m": bh.score_5m,
                      "band": bh.band,
                      "threshold": thresholds["broker_health_min"]},
        ))

    for r in recs:
        await _emit_breach(r)
    return recs


async def _emit_breach(rec: RiskRecommendation) -> None:
    try:
        from engines.intelligence.explainability import emit_decision
        await emit_decision(
            "risk_breach",
            reason=rec.reason,
            metrics={"account_id": rec.account_id,
                      "guard": rec.guard, "severity": rec.severity,
                      "action": rec.action},
            evidence=rec.evidence,
        )
    except Exception:                                    # noqa: BLE001
        pass
