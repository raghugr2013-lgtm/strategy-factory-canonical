"""
Paper Execution → Alerts Bridge (additive).

Fires an alert when a paper-execution strategy's live profit factor
deviates from its backtest profit factor by more than a configurable
threshold AND the deviation persists for N consecutive samples.

Design mirrors `monitoring_alert_bridge.py`:
    • pure bridge — no alert logic duplicated; delegates to
      `alert_engine.send_alert` for delivery + channel handling
    • dedup key: (run_id, strategy_hash) — one alert per deviating
      strategy per paper run. Stored in `paper_deviation_alert_log`.
    • fully fail-safe — every entrypoint is try/except wrapped so a
      transient alert failure never breaks the paper execution loop.

Event type: PAPER_DEVIATION
Config keys (all live on `auto_factory_config`):
    alerts_enabled              — global alerts kill switch (existing)
    alert_on_paper_deviation    — per-event toggle (new, default True)
    deviation_threshold         — fractional, e.g. 0.20 = 20% (new)
    deviation_persistence       — consecutive samples required (new)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

BRIDGE_LOG_COLLECTION = "paper_deviation_alert_log"
EVENT_TYPE = "PAPER_DEVIATION"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────
# Deviation math (pure, testable)
# ──────────────────────────────────────────────────────────────────────
def deviation_ratio(running_pf: float, backtest_pf: float) -> Optional[float]:
    """Return |running − backtest| / backtest as a fraction. None when
    backtest PF is missing or non-positive (cannot form a ratio)."""
    try:
        bt = float(backtest_pf or 0.0)
        lp = float(running_pf or 0.0)
    except Exception:
        return None
    if bt <= 0:
        return None
    return abs(lp - bt) / bt


def exceeds_threshold(
    running_pf: float, backtest_pf: float, threshold: float,
) -> bool:
    """True iff deviation_ratio(…) > threshold. False when ratio is None
    (insufficient data to decide) — fail-safe."""
    r = deviation_ratio(running_pf, backtest_pf)
    if r is None:
        return False
    return r > float(threshold)


# ──────────────────────────────────────────────────────────────────────
# Dedup
# ──────────────────────────────────────────────────────────────────────
async def _already_alerted(run_id: str, strategy_hash: str) -> bool:
    try:
        db = get_db()
        doc = await db[BRIDGE_LOG_COLLECTION].find_one(
            {"run_id": run_id, "strategy_hash": strategy_hash}, {"_id": 1},
        )
        return bool(doc)
    except Exception:
        # Fail-open (don't block alerts on dedup lookup failure) but log
        # so operators can see real Mongo outages rather than silent dupes.
        logger.exception("paper-deviation dedup lookup failed — failing open")
        return False


async def _record(
    run_id: str, strategy_hash: str, payload: Dict[str, Any],
    result: Dict[str, Any],
) -> None:
    try:
        db = get_db()
        await db[BRIDGE_LOG_COLLECTION].insert_one({
            "run_id": run_id,
            "strategy_hash": strategy_hash,
            "event_type": EVENT_TYPE,
            "sent_at": _now_iso(),
            "payload": payload,
            "result": result,
        })
    except Exception:
        logger.exception("paper-deviation alert log insert failed")


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────
def build_deviation_payload(
    *,
    run_id: str,
    strategy: Dict[str, Any],
    running_pf: float,
    backtest_pf: float,
    streak: int,
    threshold: float,
) -> Dict[str, Any]:
    """Rich payload shipped to webhook / Telegram consumers."""
    r = deviation_ratio(running_pf, backtest_pf)
    return {
        "type": EVENT_TYPE,
        "run_id": run_id,
        "strategy": strategy.get("strategy_name") or strategy.get("strategy_hash"),
        "strategy_hash": strategy.get("strategy_hash"),
        "pair": strategy.get("pair") or "—",
        "timeframe": strategy.get("timeframe") or "—",
        "style": strategy.get("style") or "—",
        "backtest_pf": round(float(backtest_pf or 0.0), 3),
        "live_pf": round(float(running_pf or 0.0), 3),
        "deviation_pct": round((r * 100.0) if r is not None else 0.0, 2),
        "deviation_direction": "below" if (running_pf or 0) < (backtest_pf or 0) else "above",
        "streak": int(streak),
        "threshold_pct": round(float(threshold) * 100.0, 2),
        "timestamp": _now_iso(),
    }


async def trigger_deviation_alert(
    *,
    run_id: str,
    strategy: Dict[str, Any],
    running_pf: float,
    backtest_pf: float,
    streak: int,
    config: Dict[str, Any],
    force: bool = False,
) -> Dict[str, Any]:
    """Fire a PAPER_DEVIATION alert for one strategy. Reuses
    `alert_engine.send_alert` for delivery. Never raises.

    Returns `{sent, reason?, payload?, channels?}`.
    """
    result: Dict[str, Any] = {"event_type": EVENT_TYPE, "sent": False,
                             "run_id": run_id,
                             "strategy_hash": strategy.get("strategy_hash")}
    try:
        # Gating (respect existing global + per-event toggles)
        if not config.get("alerts_enabled"):
            result["reason"] = "alerts_disabled"
            return result
        if not config.get("alert_on_paper_deviation", True):
            result["reason"] = "event_type_disabled"
            return result

        threshold = float(config.get("deviation_threshold", 0.20))
        if not exceeds_threshold(running_pf, backtest_pf, threshold):
            result["reason"] = "below_threshold"
            return result

        s_hash = str(strategy.get("strategy_hash") or "")
        if not s_hash:
            result["reason"] = "missing_strategy_hash"
            return result

        if not force and await _already_alerted(run_id, s_hash):
            result["reason"] = "duplicate"
            return result

        payload = build_deviation_payload(
            run_id=run_id, strategy=strategy,
            running_pf=running_pf, backtest_pf=backtest_pf,
            streak=streak, threshold=threshold,
        )

        # Delegate to the existing alert engine. We feed a synthetic
        # strategy dict so `alert_engine.build_payload` has enough to
        # shape its base record; the monitoring-bridge pattern. The
        # actual delivery (webhook/telegram), logging, and channel
        # routing all stay in `alert_engine` — zero duplication.
        from engines import alert_engine as alerts
        synthetic = {
            "strategy_text": (
                f"[PAPER_DEVIATION] {strategy.get('strategy_name') or s_hash}: "
                f"live PF {payload['live_pf']} vs backtest PF {payload['backtest_pf']} "
                f"({payload['deviation_pct']}% {payload['deviation_direction']}, "
                f"streak {streak})"
            ),
            "pair": strategy.get("pair") or "—",
            "timeframe": strategy.get("timeframe") or "—",
            "profit_factor": running_pf,
            "max_drawdown": 0,
            "pass_probability": 0,
            "metrics": {"total_trades": strategy.get("trades", 0)},
            "firm": strategy.get("firm_slug") or "—",
            "strategy_hash": f"paper_dev:{run_id}:{s_hash}",
        }
        # `force=True` — dedup lives in THIS bridge, not in alert_engine.
        send_result = await alerts.send_alert(
            synthetic, config, run_id=run_id, force=True,
        )

        # Overlay the richer deviation fields on the engine's payload so
        # webhook / telegram consumers see the full deviation shape.
        if send_result.get("payload") is not None:
            send_result["payload"] = {**send_result["payload"], **payload}

        result["sent"] = bool(send_result.get("sent"))
        result["reason"] = send_result.get("reason")
        result["channels"] = send_result.get("channels", [])
        result["payload"] = send_result.get("payload") or payload

        if result["sent"]:
            await _record(run_id, s_hash, result["payload"], send_result)
    except Exception as e:
        logger.exception("trigger_deviation_alert failed")
        result["reason"] = f"exception: {str(e)[:200]}"
    return result


async def recent_log(limit: int = 25) -> List[Dict[str, Any]]:
    try:
        db = get_db()
        cur = db[BRIDGE_LOG_COLLECTION].find({}, {"_id": 0}).sort("sent_at", -1).limit(
            max(1, min(limit, 200)),
        )
        return await cur.to_list(length=None)
    except Exception:
        return []
