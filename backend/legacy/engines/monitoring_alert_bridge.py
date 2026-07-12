"""
Monitoring → Alerts Bridge (Phase 6 × Phase 5.5 add-on, fully additive).

Pure bridge layer:
  * reads events from a Phase-6 monitoring snapshot
  * translates them into the alert payload format
  * delegates actual delivery to `alert_engine.send_alert()`
    — no alert logic duplicated

Supported event types:
  • DAILY_DD_BREACH        (daily DD ≥ threshold)
  • TOTAL_DD_BREACH        (total DD ≥ threshold)
  • UNDERPERFORMANCE       (last-N PF < threshold)
  • LOSS_STREAK            (consecutive losses ≥ threshold)

Dedup:
  Each (event_type, subject_id, UTC date) pair is recorded in
  `monitoring_alert_log` — the same breach on the same subject on the
  same day will not be re-emitted. Resets naturally at UTC midnight.

Safety:
  • never raises (try/except around every public entrypoint)
  • if `monitoring_alerts_enabled` is false OR the per-type toggle is
    off, emits nothing
  • if alerts_enabled (Phase 5.5 global switch) is false, nothing fires
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

BRIDGE_LOG_COLLECTION = "monitoring_alert_log"

# Event keys ↔ config toggle
_EVENT_TOGGLES = {
    "DAILY_DD_BREACH":   "alert_on_daily_dd",
    "TOTAL_DD_BREACH":   "alert_on_total_dd",
    "UNDERPERFORMANCE":  "alert_on_underperformance",
    "LOSS_STREAK":       "alert_on_loss_streak",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ──────────────────────────────────────────────────────────────────────
# Dedup
# ──────────────────────────────────────────────────────────────────────
async def _already_sent(event_type: str, subject_id: str, date: str) -> bool:
    try:
        db = get_db()
        doc = await db[BRIDGE_LOG_COLLECTION].find_one(
            {"event_type": event_type, "subject_id": subject_id, "date": date},
            {"_id": 1},
        )
        return bool(doc)
    except Exception:
        return False


async def _record(event_type: str, subject_id: str, payload: Dict[str, Any],
                  result: Dict[str, Any]) -> None:
    try:
        db = get_db()
        await db[BRIDGE_LOG_COLLECTION].insert_one({
            "event_type": event_type,
            "subject_id": subject_id,
            "date": _utc_date(),
            "sent_at": _now_iso(),
            "payload": payload,
            "result": result,
        })
    except Exception:
        logger.exception("bridge log insert failed")


# ──────────────────────────────────────────────────────────────────────
# Payload builder
# ──────────────────────────────────────────────────────────────────────
def _dd_fraction(value: Any) -> float:
    """Normalise DD to fraction (0.11) regardless of input form (%, 0-1)."""
    try:
        n = float(value or 0)
    except Exception:
        return 0.0
    return n / 100.0 if n > 1.0 else n


def build_event_payload(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a monitoring breach/strategy event into the alert payload."""
    payload: Dict[str, Any] = {
        "type": event_type,
        "strategy": data.get("strategy") or data.get("strategy_id") or "",
        "pair": data.get("pair") or "—",
        "timeframe": data.get("timeframe") or "—",
        "state": data.get("state"),
        "timestamp": _now_iso(),
    }

    if event_type == "TOTAL_DD_BREACH":
        payload["dd"] = round(_dd_fraction(data.get("total_dd_pct")), 4)
        payload["threshold"] = round(_dd_fraction(data.get("total_dd_threshold_pct")), 4)
    elif event_type == "DAILY_DD_BREACH":
        payload["dd"] = round(_dd_fraction(data.get("daily_dd_pct")), 4)
        payload["threshold"] = round(_dd_fraction(data.get("daily_dd_threshold_pct")), 4)
    elif event_type == "UNDERPERFORMANCE":
        payload["pf_last_n"] = round(float(data.get("pf_last_n") or 0), 3)
        payload["threshold_pf"] = float(data.get("underperform_pf_threshold") or 1.0)
        payload["window"] = int(data.get("underperform_window") or 20)
    elif event_type == "LOSS_STREAK":
        payload["loss_streak"] = int(data.get("loss_streak") or 0)
        payload["threshold"] = int(data.get("loss_streak_threshold") or 5)

    return payload


# ──────────────────────────────────────────────────────────────────────
# Core bridge entrypoint
# ──────────────────────────────────────────────────────────────────────
async def trigger_monitoring_alert(
    event_type: str,
    payload: Dict[str, Any],
    config: Dict[str, Any],
    *,
    subject_id: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Emit a single monitoring alert. Reuses alert_engine.send_alert.

    Returns a structured summary {sent: bool, reason?, ...}. Never raises.
    """
    result: Dict[str, Any] = {"event_type": event_type, "sent": False}

    try:
        if event_type not in _EVENT_TOGGLES:
            result["reason"] = "unknown_event_type"
            return result

        if not config.get("alerts_enabled"):
            result["reason"] = "alerts_disabled"
            return result
        if not config.get("monitoring_alerts_enabled"):
            result["reason"] = "monitoring_alerts_disabled"
            return result
        if not config.get(_EVENT_TOGGLES[event_type], True):
            result["reason"] = "event_type_disabled"
            return result

        # Dedup key — portfolio events key by 'portfolio', strategy events by strategy_id
        sid = str(subject_id or payload.get("strategy") or "portfolio")
        date = _utc_date()
        result["subject_id"] = sid
        result["date"] = date

        if not force and await _already_sent(event_type, sid, date):
            result["reason"] = "duplicate"
            return result

        # Delegate to existing Phase 5.5 alert engine — NO alert logic
        # duplicated here. We wrap the payload in the shape alert_engine
        # expects (it accepts arbitrary extra keys).
        from engines import alert_engine as alerts

        # Build a monitoring-style payload directly via send_alert with
        # force=True (dedup is handled by THIS bridge, not by alert_engine).
        # We fabricate a synthetic "strategy" dict so alert_engine can
        # construct its payload — then merge the monitoring fields.
        synthetic = {
            "strategy_text": payload.get("strategy") or event_type,
            "pair": payload.get("pair") or "—",
            "timeframe": payload.get("timeframe") or "—",
            "profit_factor": payload.get("pf_last_n") or 0,
            "max_drawdown": payload.get("dd") or 0,
            "pass_probability": 0,
            "metrics": {"total_trades": payload.get("window") or 0},
            "firm": config.get("firm") or "—",
            "strategy_hash": f"{event_type}:{sid}:{date}",
        }
        send_result = await alerts.send_alert(synthetic, config, run_id=None, force=True)

        # Overlay the richer monitoring payload on what alert_engine built,
        # so webhook/telegram consumers see the full event shape.
        if send_result.get("payload") is not None:
            merged = {**send_result["payload"], **payload}
            send_result["payload"] = merged

        result["sent"] = bool(send_result.get("sent"))
        result["reason"] = send_result.get("reason")
        result["channels"] = send_result.get("channels", [])
        result["payload"] = send_result.get("payload")

        if result["sent"]:
            await _record(event_type, sid, result.get("payload") or payload, send_result)
    except Exception as e:
        logger.exception("trigger_monitoring_alert failed")
        result["reason"] = f"exception: {str(e)[:200]}"

    return result


# ──────────────────────────────────────────────────────────────────────
# High-level hook used by monitoring_engine after a tick
# ──────────────────────────────────────────────────────────────────────
async def emit_from_snapshot(snapshot: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Walk a Phase-6 snapshot, emit alerts for every qualifying event.

    The bridge re-reads `config` rather than the snapshot's thresholds
    because alert toggles live on auto_factory_config (Phase 5.5).
    """
    out: Dict[str, Any] = {"emitted": 0, "skipped": 0, "results": []}

    try:
        if not config.get("alerts_enabled") or not config.get("monitoring_alerts_enabled"):
            out["skipped_reason"] = "bridge_disabled"
            return out

        metrics = snapshot.get("metrics") or {}
        thresholds = snapshot.get("thresholds") or {}
        breaches: List[Dict[str, Any]] = snapshot.get("breaches") or []
        strategies: List[Dict[str, Any]] = snapshot.get("strategies") or []

        # Portfolio-level breaches
        for b in breaches:
            kind = b.get("kind")
            if kind == "total_dd":
                p = build_event_payload("TOTAL_DD_BREACH", {
                    "strategy": "portfolio",
                    "state": snapshot.get("state"),
                    "total_dd_pct": metrics.get("portfolio_total_dd_pct"),
                    "total_dd_threshold_pct": thresholds.get("total_dd_threshold_pct"),
                })
                r = await trigger_monitoring_alert("TOTAL_DD_BREACH", p, config, subject_id="portfolio")
                out["results"].append(r)
                out["emitted" if r.get("sent") else "skipped"] += 1
            elif kind == "daily_dd":
                p = build_event_payload("DAILY_DD_BREACH", {
                    "strategy": "portfolio",
                    "state": snapshot.get("state"),
                    "daily_dd_pct": metrics.get("portfolio_daily_dd_pct"),
                    "daily_dd_threshold_pct": thresholds.get("daily_dd_threshold_pct"),
                })
                r = await trigger_monitoring_alert("DAILY_DD_BREACH", p, config, subject_id="portfolio")
                out["results"].append(r)
                out["emitted" if r.get("sent") else "skipped"] += 1

        # Strategy-level events
        for s in strategies:
            state = s.get("state")
            sid = s.get("strategy_id") or s.get("run_id")
            m = s.get("metrics") or {}
            if state == "UNDER_REVIEW":
                p = build_event_payload("UNDERPERFORMANCE", {
                    "strategy": sid,
                    "pair": s.get("pair"),
                    "timeframe": s.get("timeframe"),
                    "state": state,
                    "pf_last_n": m.get("pf_last_n"),
                    "underperform_pf_threshold": thresholds.get("underperform_pf_threshold"),
                    "underperform_window": thresholds.get("underperform_window"),
                })
                r = await trigger_monitoring_alert("UNDERPERFORMANCE", p, config, subject_id=sid)
                out["results"].append(r)
                out["emitted" if r.get("sent") else "skipped"] += 1
            elif state == "PAUSED_STREAK":
                p = build_event_payload("LOSS_STREAK", {
                    "strategy": sid,
                    "pair": s.get("pair"),
                    "timeframe": s.get("timeframe"),
                    "state": state,
                    "loss_streak": m.get("loss_streak"),
                    "loss_streak_threshold": thresholds.get("loss_streak_threshold"),
                })
                r = await trigger_monitoring_alert("LOSS_STREAK", p, config, subject_id=sid)
                out["results"].append(r)
                out["emitted" if r.get("sent") else "skipped"] += 1
    except Exception:
        logger.exception("emit_from_snapshot failed")
    return out


async def recent_log(limit: int = 25) -> List[Dict[str, Any]]:
    try:
        db = get_db()
        cur = db[BRIDGE_LOG_COLLECTION].find({}, {"_id": 0}).sort("sent_at", -1).limit(max(1, min(limit, 200)))
        return await cur.to_list(length=None)
    except Exception:
        return []
