"""
Phase 11 — Strategy Library.

Persists dashboard-approved strategies (validated + decision + prop firm
readiness) into a dedicated MongoDB collection `strategy_library`, with
deterministic duplicate detection.

Save eligibility:
    * verdict == "TRADE"                                    — always saveable
    * verdict == "RISKY" AND score >= RISKY_MIN_SCORE       — strong-RISKY only
    * verdict == "REJECT"                                   — never
    * prop_status == "FAIL"                                 — never

Duplicate detection:
    A stable SHA1 fingerprint over (pair | timeframe | style | normalised
    parameters | normalised strategy_text). Near-duplicates collapse to the
    same fingerprint because parameters are bucketed (see `_fingerprint`).
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from bson import ObjectId

from engines.db import get_db

logger = logging.getLogger(__name__)

COLLECTION = "strategy_library"
RISKY_MIN_SCORE = 35.0            # threshold for "strong" RISKY saves
                                  # (dev: lowered 45 → 35 to surface improving
                                  # strategies during optimisation phase. Does
                                  # NOT change verdict logic or pass/fail
                                  # evaluation — only the visibility floor for
                                  # which RISKY rows reach strategy_library.)
PARAM_BUCKET_PCT = 0.10           # ±10% bucketing for near-dup collapse


# ── Fingerprint (dedup key) ───────────────────────────────────────────

_WS_RE = re.compile(r"\s+")


def _normalize_text(txt: str) -> str:
    if not txt:
        return ""
    t = txt.strip().lower()
    t = _WS_RE.sub(" ", t)
    # Strip numeric values so small param edits don't break fingerprint
    t = re.sub(r"\b\d+(?:\.\d+)?\b", "N", t)
    return t


def _bucket_param(v):
    """Bucket a numeric param to the nearest PARAM_BUCKET_PCT band."""
    if not isinstance(v, (int, float)) or v == 0:
        return v
    band = max(1, round(abs(v) * PARAM_BUCKET_PCT))
    return round(v / band) * band


def _canon_params(params: dict | None) -> str:
    if not params:
        return ""
    items = []
    for k in sorted(params.keys()):
        v = params[k]
        if isinstance(v, (int, float)):
            v = _bucket_param(v)
        items.append(f"{k}={v}")
    return "|".join(items)


def _fingerprint(pair, timeframe, style, params, strategy_text) -> str:
    raw = "||".join([
        (pair or "").upper(),
        (timeframe or "").upper(),
        (style or "").lower(),
        _canon_params(params),
        _normalize_text(strategy_text),
    ])
    return hashlib.sha1(raw.encode()).hexdigest()



# ── Index management ──────────────────────────────────────────────────

async def ensure_unique_fingerprint_index() -> None:
    """Pre-create the unique-fingerprint index. Called by bulk-import
    paths (e.g. ASF migration importer) BEFORE bulk insert to avoid
    racey lazy-create under load. Idempotent / no-op when already
    present (Mongo dedups equivalent index specs)."""
    db = get_db()
    try:
        await db[COLLECTION].create_index(
            "fingerprint", unique=True, background=True,
        )
    except Exception:
        logger.exception("ensure_unique_fingerprint_index failed (non-fatal)")


# ── Eligibility ───────────────────────────────────────────────────────

def _is_eligible(
    verdict: str | None,
    score,
    prop_status: str | None,
    pass_probability=None,
    stability_score=None,
) -> tuple[bool, str]:
    """
    Return (allowed, reason).

    Rules (Phase 11 refinement):
      1. TRADE + prop_status != FAIL                              → SAVE
      2. RISKY + prop_status != FAIL + score >= RISKY_MIN_SCORE
         AND (pass_probability >= 50 OR stability_score >= 50)   → SAVE
      3. Otherwise                                                → REJECT
    """
    if (prop_status or "").upper() == "FAIL":
        return False, "prop_firm_panel status is FAIL"

    if verdict == "TRADE":
        return True, "TRADE verdict"

    if verdict == "RISKY":
        try:
            s = float(score) if score is not None else 0.0
        except (TypeError, ValueError):
            s = 0.0
        if s < RISKY_MIN_SCORE:
            return False, f"weak RISKY (score {s:.1f} < {RISKY_MIN_SCORE})"
        try:
            pp = float(pass_probability) if pass_probability is not None else 0.0
        except (TypeError, ValueError):
            pp = 0.0
        try:
            stab = float(stability_score) if stability_score is not None else 0.0
        except (TypeError, ValueError):
            stab = 0.0
        if pp >= 50.0 or stab >= 50.0:
            return True, (
                f"strong RISKY (score {s:.1f}, "
                f"pass_prob {pp:.0f}, stability {stab:.0f})"
            )
        return False, (
            f"RISKY too unstable (pass_prob {pp:.0f} < 50 AND "
            f"stability {stab:.0f} < 50)"
        )

    return False, f"verdict={verdict!r} not saveable"


# ── Extractors (tolerant to dashboard-card or engine-native shapes) ───

def _get(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def _extract_stability(validation_report: dict | None) -> float | None:
    """
    Pull stability_score, preferring walk_forward.aggregate.stability_score,
    then the composed validation_report.stability_score.
    """
    if not isinstance(validation_report, dict):
        return None
    # Preferred: walk-forward aggregate
    wf = validation_report.get("walk_forward")
    if isinstance(wf, dict):
        agg = wf.get("aggregate")
        if isinstance(agg, dict) and isinstance(agg.get("stability_score"), (int, float)):
            return float(agg["stability_score"])
    # Composed report
    st = validation_report.get("stability_score")
    if isinstance(st, dict) and isinstance(st.get("score"), (int, float)):
        return float(st["score"])
    if isinstance(st, (int, float)):
        return float(st)
    # Basic segment fallback
    basic = validation_report.get("basic") or {}
    if isinstance(basic.get("stability"), dict) and isinstance(
        basic["stability"].get("score"), (int, float)
    ):
        return float(basic["stability"]["score"])
    return None


def _extract_core(payload: dict) -> dict:
    """Pull the common card/strategy fields into a flat shape."""
    panel = payload.get("prop_firm_panel") or {}
    backtest = payload.get("backtest") or payload.get("backtest_results") or {}
    decision = payload.get("decision") or {}
    if isinstance(decision.get("decision"), dict):
        decision_inner = decision["decision"]
    else:
        decision_inner = decision
    verdict = payload.get("verdict") or _get(decision_inner, "verdict")
    prop_status = payload.get("status") or panel.get("status")

    # Phase 11 refinement — pass_probability & stability_score extraction.
    pass_prob = (
        panel.get("pass_probability") if panel else None
    )
    if pass_prob is None:
        pass_prob = payload.get("pass_probability")
    if pass_prob is None:
        # Sometimes the dashboard card puts it inside decision.scores
        scores = payload.get("scores") or {}
        if isinstance(scores, dict) and isinstance(
            scores.get("pass_probability"), (int, float)
        ):
            pass_prob = scores["pass_probability"]

    stability = _extract_stability(payload.get("validation_report"))
    if stability is None:
        # Card may carry stability flat
        if isinstance(payload.get("stability_score"), (int, float)):
            stability = float(payload["stability_score"])
        elif isinstance(payload.get("consistency_score"), (int, float)):
            # Final fallback — panel consistency mirrors walk-forward stability
            stability = float(payload["consistency_score"])
        elif panel and isinstance(panel.get("consistency_score"), (int, float)):
            stability = float(panel["consistency_score"])

    return {
        "pair": payload.get("pair") or "UNKNOWN",
        "timeframe": payload.get("timeframe") or "UNKNOWN",
        "style": payload.get("style") or "unknown",
        "strategy_text": payload.get("strategy_text") or "",
        "parameters": payload.get("parameters") or payload.get("param_overrides") or {},
        "score": payload.get("score"),
        "verdict": verdict,
        "prop_status": prop_status,
        "pass_probability": pass_prob,
        "stability_score": stability,
        "max_drawdown_pct": panel.get("max_drawdown")
                            if panel else backtest.get("max_drawdown_pct"),
        "daily_drawdown_pct": panel.get("daily_drawdown") if panel else None,
        "profit_factor": backtest.get("profit_factor"),
        "total_return_pct": backtest.get("total_return_pct"),
        "win_rate": backtest.get("win_rate"),
        "total_trades": backtest.get("total_trades"),
        # Phase 25 — win/loss breakdown (cache from backtest_results so
        # subsequent Explorer reads stay free of recompute).
        "winning_trades": backtest.get("winning_trades"),
        "losing_trades": backtest.get("losing_trades"),
        "avg_win_usd": backtest.get("avg_win_usd"),
        "avg_loss_usd": backtest.get("avg_loss_usd"),
        "avg_win_pips": backtest.get("avg_win_pips"),
        "avg_loss_pips": backtest.get("avg_loss_pips"),
        "consistency_score": panel.get("consistency_score") if panel else None,
        "confidence": _get(decision_inner, "confidence"),
        "reason": payload.get("reason") or _get(decision_inner, "reason"),
        "recommendation": panel.get("recommendation") if panel else None,
        # ── Additive: TASK 1 / TASK 3 evaluation fields ──
        # Persisted directly on the saved doc so the prop-firm matcher
        # and the dashboard can consume them without reaching into
        # nested validation_report / decision payloads.
        "expected_value": payload.get("expected_value"),
        "oos_holdout": payload.get("oos_holdout"),
        # ── H-1 (IR persistence fix): whitelist passthrough ──
        # When the mutation engine builds an IR-bearing variant, it now
        # includes ``strategy_ir`` and ``strategy_hash`` in the auto-save
        # card. ``_extract_core`` is the field gate; without this
        # passthrough the fields would be silently dropped (the
        # pre-existing wiring gap discovered in Path α′).
        "strategy_ir": payload.get("strategy_ir"),
        "strategy_hash": payload.get("strategy_hash"),
    }


# ── Public API ────────────────────────────────────────────────────────

async def save_strategy(
    payload: dict,
    *,
    source: str = "dashboard",
    force: bool = False,
) -> dict:
    """
    Persist a dashboard strategy into `strategy_library`.

    Args:
        payload: dashboard card shape OR full engine strategy dict.
        source:  origin tag ("dashboard" / "auto_save" / "manual").
        force:   skip the eligibility rule (still respects dedup). Used by
                 user-override manual saves; default False.

    Returns:
        {"success": bool, "status": "saved|duplicate|rejected",
         "strategy_id": str|None, "reason": str, "fingerprint": str}
    """
    core = _extract_core(payload)

    allowed, reason = _is_eligible(
        core["verdict"], core["score"], core["prop_status"],
        pass_probability=core.get("pass_probability"),
        stability_score=core.get("stability_score"),
    )
    if not allowed and not force:
        return {
            "success": False,
            "status": "rejected",
            "strategy_id": None,
            "reason": f"Not eligible: {reason}",
            "fingerprint": None,
        }

    fp = _fingerprint(
        core["pair"], core["timeframe"], core["style"],
        core["parameters"], core["strategy_text"],
    )

    db = get_db()
    existing = await db[COLLECTION].find_one({"fingerprint": fp}, {"_id": 1})
    if existing:
        return {
            "success": True,
            "status": "duplicate",
            "strategy_id": str(existing["_id"]),
            "reason": "Identical or near-duplicate already in library.",
            "fingerprint": fp,
        }

    now = datetime.now(timezone.utc).isoformat()
    doc = {
        **core,
        "fingerprint": fp,
        "source": source,
        "force_saved": bool(force and not allowed),
        "validation_report": payload.get("validation_report"),
        "decision": payload.get("decision"),
        "prop_firm_panel": payload.get("prop_firm_panel"),
        "created_at": now,
    }
    # Ensure fingerprint uniqueness (best-effort; ok to race, dedup handles it)
    try:
        await db[COLLECTION].create_index("fingerprint", unique=True, background=True)
    except Exception:
        pass

    try:
        res = await db[COLLECTION].insert_one(doc)
    except Exception as e:
        # Race: another coroutine inserted the same fingerprint first.
        existing2 = await db[COLLECTION].find_one({"fingerprint": fp}, {"_id": 1})
        if existing2:
            return {
                "success": True, "status": "duplicate",
                "strategy_id": str(existing2["_id"]),
                "reason": "Raced with parallel save; existing doc kept.",
                "fingerprint": fp,
            }
        raise e

    # Store the stable string id on the doc itself so downstream
    # consumers (Phase 11 sweep / Phase 12 events) can join by
    # strategy_id without touching raw ObjectId.
    try:
        await db[COLLECTION].update_one(
            {"_id": res.inserted_id},
            {"$set": {"strategy_id": str(res.inserted_id)}},
        )
    except Exception:
        pass

    return {
        "success": True,
        "status": "saved",
        "strategy_id": str(res.inserted_id),
        "reason": reason,
        "fingerprint": fp,
    }


async def auto_save_top(
    top_strategies: list,
    *,
    source: str = "auto_save",
) -> dict:
    """
    Save every eligible entry from a ranked top-N list. Used by the
    dashboard's "Save Top" one-click action.
    """
    saved, duplicates, rejected = [], [], []
    for s in top_strategies or []:
        res = await save_strategy(s, source=source)
        if res["status"] == "saved":
            saved.append(res["strategy_id"])
        elif res["status"] == "duplicate":
            duplicates.append(res["strategy_id"])
        else:
            rejected.append(res["reason"])
    return {
        "success": True,
        "saved": saved,
        "duplicates": duplicates,
        "rejected": rejected,
        "counts": {
            "saved": len(saved),
            "duplicates": len(duplicates),
            "rejected": len(rejected),
        },
    }


async def list_saved(
    pair: str | None = None,
    timeframe: str | None = None,
    verdict: str | None = None,
    limit: int = 100,
) -> list[dict]:
    db = get_db()
    q: dict = {}
    if pair:
        q["pair"] = pair.upper()
    if timeframe:
        q["timeframe"] = timeframe.upper()
    if verdict:
        q["verdict"] = verdict.upper()
    cursor = db[COLLECTION].find(q).sort("created_at", -1) \
        .limit(max(1, min(int(limit), 500)))
    items = []
    async for doc in cursor:
        doc["strategy_id"] = str(doc.pop("_id"))
        items.append(doc)
    return items


async def delete_saved(strategy_id: str) -> bool:
    db = get_db()
    try:
        res = await db[COLLECTION].delete_one({"_id": ObjectId(strategy_id)})
        return res.deleted_count > 0
    except Exception as e:
        logger.warning(f"delete_saved failed: {e}")
        return False
