"""
Alert Engine — Phase 5.5 add-on (fully additive).

Fires alerts when the Auto Factory stores a strategy that meets all
qualification thresholds. Safe to call from the `store` step — all
failures are swallowed and logged so the orchestrator never breaks
because of a 3rd-party outage.

Channels (driven by auto_factory_config):
  • webhook_url      — simple HTTP POST with JSON payload
  • telegram_*       — bot API sendMessage

Deduplication:
  • One alert per (strategy_hash, run_id) is persisted in
    `auto_factory_alert_log`. Re-submissions are skipped silently.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from engines.db import get_db

logger = logging.getLogger(__name__)

ALERT_LOG_COLLECTION = "auto_factory_alert_log"

# Default gating (overridable via config keys of the same name).
DEFAULT_ALERT_MIN_PASS_PROB = 0.6
DEFAULT_ALERT_MIN_ENV_CONF = 0.6


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────────
# Payload construction
# ──────────────────────────────────────────────────────────────────────
def _num(d: Dict[str, Any], *keys, default=None):
    for k in keys:
        if d is None:
            return default
        v = d.get(k)
        if v is not None:
            return v
    return default


def build_payload(strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Map a stored strategy doc into the user-specified alert payload."""
    metrics = strategy.get("metrics") or {}
    pair = strategy.get("pair") or metrics.get("pair") or "—"
    tf = strategy.get("timeframe") or metrics.get("timeframe") or "—"
    pf = _num(strategy, "profit_factor", "pf") or _num(metrics, "profit_factor", "pf") or 0.0
    dd_raw = (
        _num(strategy, "max_drawdown", "max_drawdown_pct", "drawdown")
        or _num(metrics, "max_drawdown", "max_drawdown_pct", "drawdown")
        or 0.0
    )
    try:
        dd_val = float(dd_raw)
    except Exception:
        dd_val = 0.0
    dd = dd_val / 100.0 if dd_val > 1.0 else dd_val

    pass_prob = _num(strategy, "pass_probability") or _num(metrics, "pass_probability") or 0.0
    safe_risk = _num(strategy, "safe_risk", "safe_risk_pct") or 0.0
    firm = strategy.get("firm") or strategy.get("best_firm_fit") or strategy.get("firm_slug") or "—"

    return {
        "strategy": strategy.get("strategy_text") or strategy.get("name") or strategy.get("strategy_id") or "",
        "pair": pair,
        "timeframe": tf,
        "pf": round(float(pf or 0), 3),
        "dd": round(float(dd or 0), 4),
        "pass_probability": round(float(pass_prob or 0), 3),
        "safe_risk": round(float(safe_risk or 0), 3),
        "environment": f"{pair} {tf}",
        "firm": firm,
    }


# ──────────────────────────────────────────────────────────────────────
# Qualification
# ──────────────────────────────────────────────────────────────────────
def _to_fraction(v: Any) -> float:
    try:
        n = float(v)
    except Exception:
        return 0.0
    return n / 100.0 if n > 1.0 else n


def qualifies(strategy: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    """PF≥min_pf, DD≤max_drawdown, runs≥min_runs, pass_prob≥0.6, env_conf≥0.6."""
    metrics = strategy.get("metrics") or {}
    try:
        pf = float(_num(strategy, "profit_factor", "pf") or _num(metrics, "profit_factor", "pf") or 0.0)
        runs = int(_num(strategy, "runs", "total_trades", "trades") or _num(metrics, "total_trades") or 0)
        dd = _to_fraction(
            _num(strategy, "max_drawdown", "max_drawdown_pct", "drawdown")
            or _num(metrics, "max_drawdown_pct", "max_drawdown")
            or 0.0
        )
        pass_prob = float(_num(strategy, "pass_probability") or _num(metrics, "pass_probability") or 0.0)
        env_conf = float(
            _num(strategy, "environment_confidence", "env_confidence")
            or _num(metrics, "environment_confidence", "env_confidence")
            or 0.0
        )
    except Exception:
        return False

    min_pf = float(cfg.get("min_pf", 1.2))
    min_runs = int(cfg.get("min_runs", 3))
    max_dd = float(cfg.get("max_drawdown", 0.12))
    min_pp = float(cfg.get("alert_min_pass_probability", DEFAULT_ALERT_MIN_PASS_PROB))
    min_ec = float(cfg.get("alert_min_env_confidence", DEFAULT_ALERT_MIN_ENV_CONF))

    return (
        pf >= min_pf
        and runs >= min_runs
        and dd <= max_dd
        and pass_prob >= min_pp
        and env_conf >= min_ec
    )


# ──────────────────────────────────────────────────────────────────────
# Dedup
# ──────────────────────────────────────────────────────────────────────
def _strategy_hash(strategy: Dict[str, Any]) -> str:
    explicit = strategy.get("strategy_hash") or strategy.get("hash") or strategy.get("strategy_id")
    if explicit:
        return str(explicit)
    # Fingerprint pair+tf+style+first 200 chars of strategy_text
    base = "|".join([
        str(strategy.get("pair") or ""),
        str(strategy.get("timeframe") or ""),
        str(strategy.get("style") or ""),
        str(strategy.get("strategy_text") or "")[:200],
    ])
    return hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()[:16]


async def _already_alerted(strategy_hash: str, run_id: Optional[str]) -> bool:
    if not strategy_hash:
        return False
    db = get_db()
    q = {"strategy_hash": strategy_hash}
    if run_id:
        q["run_id"] = run_id
    doc = await db[ALERT_LOG_COLLECTION].find_one(q, {"_id": 1})
    return bool(doc)


async def _record_alert(strategy_hash: str, run_id: Optional[str],
                        payload: Dict[str, Any], channels: Dict[str, Any]):
    db = get_db()
    try:
        await db[ALERT_LOG_COLLECTION].insert_one({
            "strategy_hash": strategy_hash,
            "run_id": run_id,
            "sent_at": _now_iso(),
            "payload": payload,
            "channels": channels,
        })
    except Exception:
        logger.exception("alert log insert failed")


# ──────────────────────────────────────────────────────────────────────
# Channels
# ──────────────────────────────────────────────────────────────────────
async def _send_webhook(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"channel": "webhook", "url": url[:120], "ok": False}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=payload)
            out["status_code"] = r.status_code
            out["ok"] = 200 <= r.status_code < 300
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


async def _send_telegram(token: str, chat_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {"channel": "telegram", "ok": False}
    text = (
        "🚀 *Auto Factory — Qualified Strategy*\n"
        f"*{payload.get('pair')} {payload.get('timeframe')}*  ·  firm: `{payload.get('firm')}`\n"
        f"PF `{payload.get('pf')}`  ·  DD `{payload.get('dd')}`  ·  "
        f"pass `{payload.get('pass_probability')}`\n"
        f"safe risk `{payload.get('safe_risk')}`\n"
        f"```\n{(payload.get('strategy') or '')[:500]}\n```"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            )
            out["status_code"] = r.status_code
            out["ok"] = 200 <= r.status_code < 300
            if not out["ok"]:
                out["error"] = r.text[:200]
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────
async def send_alert(
    strategy_data: Dict[str, Any],
    config: Dict[str, Any],
    *,
    run_id: Optional[str] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Fire an alert for one qualified strategy. Fails silently.

    Returns a structured summary {sent: bool, reason?, channels:[...]}.
    """
    result: Dict[str, Any] = {"sent": False, "channels": []}

    try:
        if not config.get("alerts_enabled"):
            result["reason"] = "alerts_disabled"
            return result

        payload = build_payload(strategy_data)
        result["payload"] = payload
        s_hash = _strategy_hash(strategy_data)
        result["strategy_hash"] = s_hash

        if not force and await _already_alerted(s_hash, run_id):
            result["reason"] = "duplicate"
            return result

        channels: list = []
        if config.get("webhook_url"):
            channels.append(await _send_webhook(str(config["webhook_url"]), payload))
        if config.get("telegram_enabled") and config.get("telegram_bot_token") and config.get("telegram_chat_id"):
            channels.append(await _send_telegram(
                str(config["telegram_bot_token"]),
                str(config["telegram_chat_id"]),
                payload,
            ))

        if not channels:
            result["reason"] = "no_channels_configured"
            return result

        result["channels"] = channels
        result["sent"] = any(c.get("ok") for c in channels)
        if result["sent"]:
            await _record_alert(s_hash, run_id, payload, channels)
    except Exception as e:
        logger.exception("send_alert failed")
        result["reason"] = f"exception: {str(e)[:200]}"

    return result


async def process_stored_strategies(
    stored: list,
    config: Dict[str, Any],
    *,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Iterate stored strategies; fire alerts for each that qualifies.

    Designed for Phase 5.5's store step. NEVER raises — every error is
    contained so the orchestrator keeps running.
    """
    summary: Dict[str, Any] = {
        "evaluated": 0,
        "qualified": 0,
        "alerts_sent": 0,
        "duplicates": 0,
        "failures": 0,
        "details": [],
    }
    try:
        if not config.get("alerts_enabled"):
            summary["skipped"] = "alerts_disabled"
            return summary

        for s in stored or []:
            summary["evaluated"] += 1
            try:
                if not qualifies(s, config):
                    continue
                summary["qualified"] += 1
                r = await send_alert(s, config, run_id=run_id)
                summary["details"].append({
                    "strategy_hash": r.get("strategy_hash"),
                    "sent": r.get("sent"),
                    "reason": r.get("reason"),
                })
                if r.get("sent"):
                    summary["alerts_sent"] += 1
                elif r.get("reason") == "duplicate":
                    summary["duplicates"] += 1
                else:
                    summary["failures"] += 1
            except Exception:
                logger.exception("alert processing failed for strategy")
                summary["failures"] += 1
    except Exception:
        logger.exception("process_stored_strategies outer failure")
    return summary


# Test-alert convenience — hits configured channels with a fake payload
async def send_test_alert(config: Dict[str, Any]) -> Dict[str, Any]:
    sample = {
        "strategy_text": "TEST — RSI(14)<30 BUY, RSI(14)>70 SELL · SL 1.0R TP 1.8R",
        "pair": "GBPUSD",
        "timeframe": "H4",
        "profit_factor": 1.52,
        "max_drawdown_pct": 8.0,
        "pass_probability": 0.72,
        "safe_risk": 0.5,
        "firm": "FTMO Aggressive",
        "metrics": {"total_trades": 42},
        "environment_confidence": 0.75,
        "strategy_hash": f"test-{int(datetime.now(timezone.utc).timestamp())}",
    }
    return await send_alert(sample, config, run_id=None, force=True)


# Small helper so the API layer can expose a text dump when debugging.
def payload_preview(strategy: Dict[str, Any]) -> str:
    return json.dumps(build_payload(strategy), indent=2)



# ══════════════════════════════════════════════════════════════════════
# Phase 30.1 — Δ2 · Institutional Event Notifications (subordinate-only).
# ══════════════════════════════════════════════════════════════════════
#
# Operator constraint:
#   This layer is strictly subordinate to governance truth. Alert
#   failures must NEVER:
#     • block lifecycle writes
#     • affect orchestrator execution
#     • alter governance state
#     • change promotion timing
#
# Channel policy:
#   • If `auto_factory_config.alerts_enabled` + a configured channel
#     (webhook / telegram) → fire to that channel.
#   • Otherwise (or on channel failure) → fall back to `audit_log`
#     collection ONLY. No other side effects.
#
# Dedup:
#   • One row per (strategy_hash, event_type, optional run_id) in
#     `auto_factory_alert_log`.
# ══════════════════════════════════════════════════════════════════════

# Closed taxonomy — only these 7 event types are allowed. Adding more
# requires explicit operator decree (anti-drift).
INSTITUTIONAL_EVENT_TYPES = (
    "LIFECYCLE_DEPLOYMENT_READY",
    "LIFECYCLE_ELITE_PROMOTION",
    "SURVIVOR_ADMITTED",
    "SURVIVOR_DEMOTED",
    "REPLACEMENT_EXECUTED",
    "REGIME_FRAGILE_FLAG",
    "DEPLOYMENT_EXPORTED",
    # MB-9 Phase 2.C — parity-drift surveillance.
    # Emitted by api/master_bot.py::deployments_parity_drift_scan_and_alert
    # for every live deployment whose drift verdict is non-OK.
    "PARITY_DRIFT_DETECTED",
)

AUDIT_LOG_COLLECTION = "audit_log"


async def _load_alert_config() -> Dict[str, Any]:
    """Best-effort read of auto_factory_config. Never raises."""
    try:
        db = get_db()
        doc = await db["auto_factory_config"].find_one({}, {"_id": 0})
        return doc or {}
    except Exception:
        return {}


async def _audit_log_event(
    event_type: str,
    strategy_hash: str,
    details: Dict[str, Any],
    *,
    fallback_reason: str,
) -> Dict[str, Any]:
    """Write a row to `audit_log`. Permanent retention. Never raises."""
    try:
        db = get_db()
        await db[AUDIT_LOG_COLLECTION].insert_one({
            "event":         f"phase30_1_event:{event_type}",
            "event_type":    event_type,
            "strategy_hash": strategy_hash,
            "details":       details or {},
            "fallback":      fallback_reason,
            "phase":         "30.1",
            "ts":            _now_iso(),
        })
        return {"channel": "audit_log", "ok": True, "reason": fallback_reason}
    except Exception as e:                                      # pragma: no cover
        logger.debug("audit_log fallback write failed: %s", e)
        return {"channel": "audit_log", "ok": False, "error": str(e)[:200]}


async def emit_event(
    event_type: str,
    strategy_hash: str,
    details: Optional[Dict[str, Any]] = None,
    *,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Emit one institutional event. Subordinate-only — NEVER raises.

    Order of attempts:
      1. Reject unknown event_type silently (caller bug, do not crash).
      2. Dedup via `auto_factory_alert_log`.
      3. If channel(s) configured → fire webhook / telegram with a
         compact payload. Record success in alert_log.
      4. Always (success or failure) → also write to `audit_log` so
         every event is permanently traceable, even when channels
         are not configured. This is the operator-decreed fallback.
    """
    result: Dict[str, Any] = {
        "emitted":      False,
        "event_type":   event_type,
        "strategy_hash": strategy_hash,
        "channels":     [],
    }
    try:
        if event_type not in INSTITUTIONAL_EVENT_TYPES:
            result["reason"] = "unknown_event_type"
            return result

        details = details or {}
        # Dedup first — one record per (hash, event_type, run_id).
        try:
            db = get_db()
            q: Dict[str, Any] = {
                "strategy_hash": strategy_hash,
                "event_type":    event_type,
            }
            if run_id:
                q["run_id"] = run_id
            existing = await db[ALERT_LOG_COLLECTION].find_one(q, {"_id": 1})
            if existing:
                result["reason"] = "duplicate"
                return result
        except Exception:                                       # pragma: no cover
            # dedup-read failure is non-fatal; fall through.
            pass

        payload = {
            "event_type":    event_type,
            "strategy_hash": strategy_hash,
            "phase":         "30.1",
            "ts":            _now_iso(),
            "details":       details,
        }

        cfg = await _load_alert_config()
        channels: list = []
        if cfg.get("alerts_enabled"):
            if cfg.get("webhook_url"):
                channels.append(await _send_webhook(
                    str(cfg["webhook_url"]), payload,
                ))
            if (cfg.get("telegram_enabled")
                    and cfg.get("telegram_bot_token")
                    and cfg.get("telegram_chat_id")):
                # Reuse the existing telegram sender with a minimal
                # synthetic payload so the formatter doesn't crash.
                synth = {
                    "strategy":        f"[{event_type}] {strategy_hash}",
                    "pair":            details.get("pair") or "—",
                    "timeframe":       details.get("timeframe") or "—",
                    "pf":              details.get("deploy_score") or 0.0,
                    "dd":              0.0,
                    "pass_probability": 0.0,
                    "safe_risk":       0.0,
                    "firm":            "—",
                }
                channels.append(await _send_telegram(
                    str(cfg["telegram_bot_token"]),
                    str(cfg["telegram_chat_id"]),
                    synth,
                ))

        channel_ok = any(c.get("ok") for c in channels) if channels else False

        # Operator-decreed: audit_log is the canonical fallback AND a
        # permanent receipt for every institutional event. Write it
        # regardless of channel outcome so trace remains complete.
        fallback_reason = (
            "no_channels_configured" if not channels
            else ("primary_send_ok" if channel_ok else "primary_send_failed")
        )
        audit_outcome = await _audit_log_event(
            event_type, strategy_hash, payload, fallback_reason=fallback_reason,
        )
        channels.append(audit_outcome)

        # Persist dedup row — independent of channel success.
        try:
            db = get_db()
            await db[ALERT_LOG_COLLECTION].insert_one({
                "strategy_hash":  strategy_hash,
                "run_id":         run_id,
                "event_type":     event_type,
                "sent_at":        _now_iso(),
                "payload":        payload,
                "channels":       channels,
            })
        except Exception:                                       # pragma: no cover
            logger.debug("alert log dedup insert failed")

        result["channels"] = channels
        result["emitted"]  = channel_ok or audit_outcome.get("ok", False)
        return result
    except Exception as e:                                      # pragma: no cover
        # Subordinate-only — never bubble up. Log and return.
        logger.debug("emit_event swallowed exception: %s", e)
        result["reason"] = f"swallowed:{str(e)[:200]}"
        return result
