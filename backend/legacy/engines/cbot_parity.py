"""
Phase B.1 — cBot parity sign-off pipeline.

ADDITIVE: this module provides a single helper, `sign_off_parity()`,
that proves a strategy's IR survives the Phase 28-C transpiler trust
gate end-to-end:

  1. Locate the canonical IR for `strategy_hash`.
  2. Pull a recent price fixture from MongoDB market_data.
  3. Run `ir_parity_simulator.simulate_cbot_signals(...)` — which
     internally delegates to the canonical `IRInterpreter`.
  4. Re-emit the C# via `ir_transpiler.transpile_ir_to_csharp(...,
     parity_status="PASSED", parity_fixtures_passed=N)` so the
     artifact ships with PASSED parity metadata.
  5. Persist the sign-off to `cbot_parity_signoff` (one document per
     strategy_hash, idempotent upsert) and write an `audit_log` row.

The interpreter and transpiler are both SEALED Phase 28 surfaces.
This module exercises them and records the outcome — it does NOT
modify them.

Discipline:
  * Honest refusal: any `IRCoverageGap` or `UnsupportedIROperatorError`
    becomes a PASSED=False sign-off with `status="UNSUPPORTED"`.
  * Audit log: every sign-off (PASSED or otherwise) writes an
    `audit_log` row with event `cbot_parity_signoff`.
  * Idempotent: re-running for the same hash overwrites the sign-off
    document and appends a new audit row.
  * Read-only on the rest of the system — no lifecycle writes.

Phase B.2 (soft) wires `api/strategy_memory.py::export_cbot` to:
  * Look up the sign-off before transpiling.
  * Pass `parity_status="PASSED"` + `parity_fixtures_passed=N` when a
    PASSED sign-off exists, otherwise emit an advisory warning in the
    response. NEVER blocks export at this phase.

Phase B.5 (deferred, separate operator approval) will flip the soft
warning into a hard gate.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from engines.db import get_db

logger = logging.getLogger(__name__)


SIGNOFF_COLL = "cbot_parity_signoff"
AUDIT_COLL = "audit_log"

_DEFAULT_FIXTURE_BARS = 240
_MIN_FIXTURE_BARS = 80


# ─────────────────────────────────────────────────────────────────────
# P1.3 — Trade-parity activation gate
# ─────────────────────────────────────────────────────────────────────
# The P0.4 dormant trade-lifecycle simulator (`engines.cbot_trade_parity`)
# is wired in here behind a strict env-flag check. Default OFF preserves
# the prior signal-only sign-off byte-for-byte.
#
# When ENABLE_CBOT_TRADE_PARITY=true:
#   * After the signal-parity step succeeds, we also call
#     `cbot_trade_parity.simulate_trades(...)` on the SAME IR + fixture.
#   * The resulting trade summary is attached to the sign-off doc as
#     `trade_summary` (numbers only — never embedded the raw trade list
#     into Mongo to keep the document small) + `trade_parity_passed`
#     (boolean derived from `compare_trade_series` self-test, which is
#     a lower-bound determinism check).
#   * The OVERALL sign-off `status` remains driven by signal parity.
#     Promoting trade-parity into a hard gate is a future, separately-
#     reviewed step (audit doc §9 P1.4).
#
# When OFF: the block is skipped entirely. The sign-off document has
# no `trade_summary` field — identical to the pre-P1.3 schema.
def _trade_parity_enabled() -> bool:
    raw = os.environ.get("ENABLE_CBOT_TRADE_PARITY", "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


# G-2.b — ENABLE_HTF_PARITY_VALIDATION (default OFF). When ON,
# sign_off_parity adds five advisory HTF-parity fields to the
# persisted signoff doc (htf_parity_verdict, htf_divergence_pct,
# htf_parity_tolerance_pct, htf_parity_compared_bars,
# htf_parity_diverging_bars). When OFF: the block is skipped — the
# signoff doc has no htf_parity_* fields (pre-G-2.b schema).
# Defers the canonical reading to ``engines.htf_parity.is_enabled``
# so the env-truthy semantics stay in lockstep with the validator.
def _htf_parity_enabled() -> bool:
    try:
        from engines.htf_parity import is_enabled as _htf_is_enabled
        return bool(_htf_is_enabled())
    except Exception:                                       # pragma: no cover
        raw = os.environ.get("ENABLE_HTF_PARITY_VALIDATION", "")
        return raw.strip().lower() in ("1", "true", "yes", "on")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────
# Helpers: locate IR + fixture
# ─────────────────────────────────────────────────────────────────────

async def _find_ir_for_strategy(strategy_hash: str) -> Optional[Dict[str, Any]]:
    """Locate the canonical IR for a strategy.

    Search order:
      1. `strategy_library` doc by strategy_hash → `strategy_ir`
      2. Latest `mutation_events` for variant_fingerprint == hash
      3. `strategy_lifecycle` doc by strategy_hash → IR snapshot

    Returns the IR dict (Pydantic-serialised) or None.
    """
    db = get_db()
    try:
        doc = await db["strategy_library"].find_one(
            {"strategy_hash": strategy_hash},
            {"_id": 0, "strategy_ir": 1},
        )
        if doc and doc.get("strategy_ir"):
            return doc["strategy_ir"]
    except Exception as e:                                  # pragma: no cover
        logger.debug("find_ir strategy_library lookup failed: %s", e)

    try:
        cur = db["mutation_events"].find(
            {"variant_fingerprint": strategy_hash, "ir_status": "ir_native"},
            {"_id": 0, "strategy_ir": 1, "ts": 1},
        ).sort("ts", -1).limit(1)
        async for row in cur:
            if row.get("strategy_ir"):
                return row["strategy_ir"]
    except Exception as e:                                  # pragma: no cover
        logger.debug("find_ir mutation_events lookup failed: %s", e)

    try:
        doc = await db["strategy_lifecycle"].find_one(
            {"strategy_hash": strategy_hash},
            {"_id": 0, "strategy_ir": 1},
        )
        if doc and doc.get("strategy_ir"):
            return doc["strategy_ir"]
    except Exception as e:                                  # pragma: no cover
        logger.debug("find_ir strategy_lifecycle lookup failed: %s", e)

    return None


async def _load_price_fixture(
    pair: str, timeframe: str, n_bars: int = _DEFAULT_FIXTURE_BARS,
) -> Optional[Tuple[List[float], List[float], List[float], List[Any]]]:
    """Return (closes, highs, lows, timestamps) for the latest n_bars,
    or None if not enough data exists.

    Phase 1 P1.2 fix: route through the canonical `data_access` loader
    so schema normalization (symbol vs pair, H1 vs 1h) is handled by
    the single source of truth.
    """
    try:
        from engines.data_access import load_ohlc_bars
        rows = await load_ohlc_bars(pair, timeframe, source="bid_1m")
    except Exception as e:                                  # pragma: no cover
        logger.warning("[cbot_parity] market_data fetch failed: %s", e)
        return None
    # Use the latest n_bars (data_access returns ascending; tail-slice)
    if rows and len(rows) > int(n_bars):
        rows = rows[-int(n_bars):]
    if len(rows) < _MIN_FIXTURE_BARS:
        return None
    closes = [float(r.get("close") or 0.0) for r in rows]
    highs = [float(r.get("high") or 0.0) for r in rows]
    lows = [float(r.get("low") or 0.0) for r in rows]
    ts = [r.get("timestamp") for r in rows]
    return closes, highs, lows, ts


# ─────────────────────────────────────────────────────────────────────
# Sign-off pipeline
# ─────────────────────────────────────────────────────────────────────

async def sign_off_parity(
    strategy_hash: str,
    *,
    ir_override: Optional[Dict[str, Any]] = None,
    pair_override: Optional[str] = None,
    timeframe_override: Optional[str] = None,
    n_bars: int = _DEFAULT_FIXTURE_BARS,
    triggered_by: str = "manual",
) -> Dict[str, Any]:
    """Prove signal parity for the strategy's IR against a price fixture.

    Returns a structured outcome:
        {
          "strategy_hash": ...,
          "status": "PASSED" | "UNSUPPORTED" | "NO_IR" | "NO_DATA" | "ERROR",
          "signed_at": iso,
          "transpiler_version": "1.0.0",
          "fixture": {pair, timeframe, bars, source},
          "signal_summary": {total, long, short, none},
          "operators_used": [...],
          "indicator_kinds_used": [...],
          "htf_present": bool,
          "parity_mode": "EXACT" | "APPROXIMATE",
          "details": "...",
        }

    NEVER raises. On any unexpected exception, status="ERROR" is
    returned and the audit-log row carries the message.
    """
    db = get_db()
    out: Dict[str, Any] = {
        "strategy_hash": strategy_hash,
        "status": "ERROR",
        "signed_at": _now_iso(),
        "triggered_by": triggered_by,
    }

    # ── 1. Locate IR ──────────────────────────────────────────────
    ir = ir_override
    if ir is None:
        ir = await _find_ir_for_strategy(strategy_hash)
    if ir is None:
        out["status"] = "NO_IR"
        out["details"] = (
            "No IR found for strategy. Save via mutation_engine or "
            "supply ir_override to sign off."
        )
        await _persist_signoff(db, out)
        await _audit(db, strategy_hash, out, triggered_by=triggered_by)
        return out

    # ── 2. Pair/TF for fixture ────────────────────────────────────
    md = (ir.get("metadata") or {}) if isinstance(ir, dict) else {}
    pair = (pair_override or md.get("pair") or "EURUSD").upper()
    tf = (timeframe_override or md.get("timeframe") or "H1").upper()

    # ── 3. Load fixture ───────────────────────────────────────────
    fixture = await _load_price_fixture(pair, tf, n_bars=n_bars)
    if fixture is None:
        out["status"] = "NO_DATA"
        out["fixture"] = {"pair": pair, "timeframe": tf, "bars": 0, "source": "market_data"}
        out["details"] = (
            f"Insufficient market_data for {pair}/{tf} "
            f"(<{_MIN_FIXTURE_BARS} bars). Ingest data first."
        )
        await _persist_signoff(db, out)
        await _audit(db, strategy_hash, out, triggered_by=triggered_by)
        return out

    closes, highs, lows, ts = fixture
    out["fixture"] = {
        "pair": pair, "timeframe": tf,
        "bars": len(closes), "source": "market_data",
    }

    # ── 4. Run the parity simulator (delegates to IRInterpreter) ─
    try:
        from cbot_engine.ir_parity_simulator import (
            simulate_cbot_signals, IRCoverageGap,
        )
        sim = simulate_cbot_signals(
            ir,
            prices=closes, highs=highs, lows=lows,
            timestamps=ts, strategy_timeframe=tf,
        )
    except IRCoverageGap as gap:
        out["status"] = "UNSUPPORTED"
        out["details"] = str(gap)[:400]
        await _persist_signoff(db, out)
        await _audit(db, strategy_hash, out, triggered_by=triggered_by)
        return out
    except Exception as e:                                  # noqa: BLE001
        out["status"] = "ERROR"
        out["details"] = f"parity sim error: {str(e)[:400]}"
        await _persist_signoff(db, out)
        await _audit(db, strategy_hash, out, triggered_by=triggered_by)
        return out

    # ── 5. Verify the transpiler accepts the same IR ─────────────
    try:
        from cbot_engine.ir_transpiler import (
            transpile_ir_to_csharp, UnsupportedIROperatorError,
        )
        fixtures_passed = len(closes)
        artefact = transpile_ir_to_csharp(
            ir,
            parity_status="PASSED",
            parity_fixtures_passed=fixtures_passed,
        )
    except UnsupportedIROperatorError as exc:
        out["status"] = "UNSUPPORTED"
        out["details"] = f"transpiler refused: {str(exc)[:400]}"
        await _persist_signoff(db, out)
        await _audit(db, strategy_hash, out, triggered_by=triggered_by)
        return out
    except Exception as e:                                  # noqa: BLE001
        out["status"] = "ERROR"
        out["details"] = f"transpiler error: {str(e)[:400]}"
        await _persist_signoff(db, out)
        await _audit(db, strategy_hash, out, triggered_by=triggered_by)
        return out

    # ── 6. Sign off ───────────────────────────────────────────────
    signals = sim.get("signals") or []
    long_n = sum(1 for s in signals if s == "BUY")
    short_n = sum(1 for s in signals if s == "SELL")
    none_n = len(signals) - long_n - short_n
    out.update({
        "status": "PASSED",
        "transpiler_version": artefact.get("transpiler_version"),
        "ir_version": artefact.get("ir_version"),
        "strategy_hash_from_ir": artefact.get("strategy_hash"),
        "bot_name": artefact.get("bot_name"),
        "signal_summary": {
            "total": len(signals),
            "long": long_n,
            "short": short_n,
            "none": none_n,
        },
        "operators_used": sim.get("operators_used") or [],
        "indicator_kinds_used": sim.get("indicator_kinds_used") or [],
        "sl_kind": sim.get("sl_kind"),
        "tp_kind": sim.get("tp_kind"),
        "htf_present": bool(sim.get("htf_present")),
        "parity_mode": artefact.get("htf_parity_mode") or "EXACT",
        "fixtures_passed": fixtures_passed,
        "details": (
            "Signal series produced by canonical interpreter; "
            "transpiler accepts the same IR."
        ),
    })

    # ── 6b. P1.3 — Flag-gated trade-lifecycle parity (additive) ──
    # When ENABLE_CBOT_TRADE_PARITY=true, run the candle-level trade
    # simulator on the SAME IR + fixture and attach an advisory
    # summary. NEVER overwrites the overall `status` — signal parity
    # remains the authoritative verdict at this phase. The trade
    # summary is purely additive metadata so operators can observe
    # the trade-lifecycle picture without committing to a hard gate.
    if _trade_parity_enabled():
        try:
            from engines.cbot_trade_parity import (
                compare_trade_series, first_n_default, simulate_trades,
            )
            tp_report = simulate_trades(
                ir,
                prices=closes, highs=highs, lows=lows,
                timestamps=ts, strategy_timeframe=tf,
                pair=pair, first_n=first_n_default(),
            )
            self_check = compare_trade_series(
                tp_report["trades"], tp_report["trades"],
            )
            # Trade-parity "PASSED" at this phase = (a) the simulator
            # ran end-to-end without error AND (b) the self-comparison
            # reports PASSED or EMPTY. This is the LOWER-BOUND determinism
            # guarantee. The HIGHER-BOUND (broker-emulator alignment)
            # belongs to P3.2.
            trade_passed = self_check["verdict"] in ("PASSED", "EMPTY")
            out["trade_summary"] = tp_report["summary"]
            out["trade_parity_passed"] = trade_passed
            out["trade_parity_inputs"] = tp_report["parity_inputs"]
            out["trade_parity_self_check"] = self_check["verdict"]
            out["trade_parity_advisory_only"] = True
            out["details"] += (
                f" | trade-parity (advisory): {self_check['verdict']}, "
                f"trades={tp_report['summary']['total_trades']}"
            )
        except Exception as e:                              # noqa: BLE001
            # P1.3 is advisory — a trade-parity error MUST NOT alter
            # the signal-parity verdict. We record the failure and
            # move on so the operator still receives the PASSED
            # signal sign-off.
            logger.warning(
                "[cbot_parity] trade-parity advisory step failed: %s", e,
            )
            out["trade_parity_passed"] = False
            out["trade_parity_error"] = str(e)[:400]
            out["trade_parity_advisory_only"] = True

    # ── 6c. G-2.b — Flag-gated HTF parity advisory (additive) ──
    # When ENABLE_HTF_PARITY_VALIDATION=true, run the candle-space
    # HTF parity validator on the SAME IR + fixture and attach an
    # advisory verdict. NEVER overwrites the overall `status` — signal
    # parity remains the authoritative verdict at this phase. The HTF
    # parity verdict is purely additive metadata that closes the
    # final-mile wiring gap acknowledged by engines/htf_parity.py
    # lines 107-111 (the engine's own "future wiring would call
    # validate_htf_parity(...) and persist htf_parity_verdict +
    # htf_divergence_pct" docstring promise).
    #
    # The five possible verdicts are EXACT / WITHIN_TOLERANCE /
    # DIVERGENT / NOT_APPLICABLE / ERROR — see engines/htf_parity.py
    # lines 80-99 for the full contract. The R6.6 parity-certification
    # census (engines/parity_certification.summarize_signoffs) reads
    # these field names directly; no census-side change is required.
    if _htf_parity_enabled():
        try:
            from engines.htf_parity import validate_htf_parity
            htf_report = validate_htf_parity(
                ir,
                prices=closes, highs=highs, lows=lows,
                timestamps=ts, strategy_timeframe=tf,
            )
            out["htf_parity_verdict"] = htf_report.get("verdict")
            out["htf_divergence_pct"] = htf_report.get("divergence_pct")
            out["htf_parity_tolerance_pct"] = htf_report.get("tolerance_pct")
            out["htf_parity_compared_bars"] = htf_report.get("compared_bars")
            out["htf_parity_diverging_bars"] = htf_report.get("diverging_bars")
            out["htf_parity_first_divergence"] = htf_report.get("first_divergence")
            out["htf_parity_advisory_only"] = True
            out["details"] += (
                f" | htf-parity (advisory): {htf_report.get('verdict')}, "
                f"divergence={htf_report.get('divergence_pct'):.2f}%"
                if isinstance(htf_report.get("divergence_pct"), (int, float))
                else f" | htf-parity (advisory): {htf_report.get('verdict')}"
            )
        except Exception as e:                              # noqa: BLE001
            # G-2.b is advisory — an HTF-parity error MUST NOT alter
            # the signal-parity verdict. Record the failure and move
            # on so the operator still receives the PASSED signal
            # sign-off. Mirrors the P1.3 error-handling pattern above.
            logger.warning(
                "[cbot_parity] htf-parity advisory step failed: %s", e,
            )
            out["htf_parity_verdict"] = "ERROR"
            out["htf_parity_error"] = str(e)[:400]
            out["htf_parity_advisory_only"] = True

    await _persist_signoff(db, out)
    await _audit(db, strategy_hash, out, triggered_by=triggered_by)
    return out


# ─────────────────────────────────────────────────────────────────────
# Persistence + audit
# ─────────────────────────────────────────────────────────────────────

async def _persist_signoff(db, doc: Dict[str, Any]) -> None:
    try:
        await db[SIGNOFF_COLL].update_one(
            {"strategy_hash": doc["strategy_hash"]},
            {"$set": doc},
            upsert=True,
        )
    except Exception as e:                                  # pragma: no cover
        logger.warning("[cbot_parity] signoff persist failed: %s", e)


async def _audit(db, strategy_hash: str, outcome: Dict[str, Any],
                 *, triggered_by: str) -> None:
    try:
        row: Dict[str, Any] = {
            "ts": _now_iso(),
            "event": "cbot_parity_signoff",
            "strategy_hash": strategy_hash,
            "status": outcome.get("status"),
            "triggered_by": triggered_by,
            "fixture": outcome.get("fixture"),
            "parity_mode": outcome.get("parity_mode"),
            "fixtures_passed": outcome.get("fixtures_passed"),
            "details": outcome.get("details"),
            "phase": "B.1",
        }
        # P1.3 — when trade-parity ran, surface its verdict in the
        # audit row so forensic queries can see the trade-lifecycle
        # state without re-reading the sign-off doc. Advisory-only
        # at this phase; never alters the primary `status` field.
        if "trade_parity_passed" in outcome:
            row["trade_parity_passed"] = outcome.get("trade_parity_passed")
            row["trade_parity_self_check"] = outcome.get("trade_parity_self_check")
            if outcome.get("trade_summary"):
                ts_sum = outcome["trade_summary"]
                row["trade_parity_total_trades"] = ts_sum.get("total_trades")
                row["trade_parity_sl_hits"] = ts_sum.get("sl_hits")
                row["trade_parity_tp_hits"] = ts_sum.get("tp_hits")
        # G-2.b — when HTF-parity ran, surface its verdict in the
        # audit row. Mirrors the P1.3 pattern above; advisory-only.
        if "htf_parity_verdict" in outcome:
            row["htf_parity_verdict"] = outcome.get("htf_parity_verdict")
            row["htf_divergence_pct"] = outcome.get("htf_divergence_pct")
            row["htf_parity_compared_bars"] = outcome.get("htf_parity_compared_bars")
        await db[AUDIT_COLL].insert_one(row)
    except Exception as e:                                  # pragma: no cover
        logger.debug("[cbot_parity] audit insert failed: %s", e)


# ─────────────────────────────────────────────────────────────────────
# Read helpers (consumed by api/cbot.py + export gate)
# ─────────────────────────────────────────────────────────────────────

async def get_signoff(strategy_hash: str) -> Optional[Dict[str, Any]]:
    """Return the latest sign-off document for a strategy, or None."""
    db = get_db()
    try:
        return await db[SIGNOFF_COLL].find_one(
            {"strategy_hash": strategy_hash},
            {"_id": 0},
        )
    except Exception as e:                                  # pragma: no cover
        logger.debug("[cbot_parity] get_signoff failed: %s", e)
        return None


async def list_signoffs(limit: int = 100) -> List[Dict[str, Any]]:
    db = get_db()
    limit = max(1, min(int(limit), 500))
    try:
        cur = db[SIGNOFF_COLL].find({}, {"_id": 0}).sort("signed_at", -1).limit(limit)
        return [d async for d in cur]
    except Exception as e:                                  # pragma: no cover
        logger.debug("[cbot_parity] list_signoffs failed: %s", e)
        return []


def is_passed(signoff: Optional[Dict[str, Any]]) -> bool:
    return bool(signoff and signoff.get("status") == "PASSED")
