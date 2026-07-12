"""Master Bot V1 — Candidate Pool Ranker (MB-2).

Goal:
    Automatically identify the top-N candidates from the existing
    Explorer / Survivor universe and return them in a single ranked
    list, ready to be slotted into Master Bot tiers.

Ranking signals (V1):
    * deploy_score          (active)
    * pass_probability      (active)
    * risk_of_ruin          (hook, weight = 0 until R6.4 unlocks it)
    * calibration           (hook, weight = 0 until R6.11 unlocks it)
    * regime_fitness        (hook, weight = 0 until R6 unlocks it)

Composite formula:
    candidate_score =
        w_ds * normalised_deploy_score
      + w_pp * normalised_pass_probability
      + w_ror * (1 - risk_of_ruin)
      + w_cal * calibration_score
      + w_reg * regime_fitness_score

Normalisation:
    * deploy_score:     already 0..100 on `evidence.deploy_score`.
                        Divided by 100 to map onto 0..1.
    * pass_probability: stored 0..100 on `strategy_library.pass_probability`.
                        Divided by 100.
    * future signals are clamped to [0, 1] at read-time so no
      out-of-range value can corrupt the score even if the upstream
      activations ship with mis-scaled values.

Source pool:
    * Same eligibility set as `survivor_registry` — strategies whose
      lifecycle stage is one of (elite, portfolio_worthy,
      deployment_ready).
    * Enriched with library-doc fields (pair, timeframe, style, PF,
      win_rate, pass_probability) for the UI dashboard.

Weights are persisted in collection `master_bot_ranker_config` keyed by
`config_key=default`. The five future-signal weights default to 0.0;
operators can flip them later without a schema migration.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engines.db import get_db
from engines import survivor_registry as sr

logger = logging.getLogger(__name__)

CONFIG_COLL = "master_bot_ranker_config"
CONFIG_KEY  = "default"
RANKER_VERSION = "v1.1"  # BI5 R2 / B-5: bi5_cert_verdict + bi5_slippage_score added

# Default weights — sum normalised to 1.0 for the active signals.
#
# BI5 R2 / B-5 — 2026-06-13: added two BI5 certification signals to the
# weighted formula. The proposal (from `BI5_R2_IMPLEMENTATION_PLAN.md §2`)
# rebalances:
#
#     deploy_score        0.60 → 0.50
#     pass_probability    0.40 → 0.40
#     bi5_cert_verdict    new  → 0.07
#     bi5_slippage_score  new  → 0.03
#
# Σ = 1.0; renormalisation honoured. Future signals stay at 0.0 (hook
# pattern unchanged). All weights are persisted in
# `master_bot_ranker_config`; operators can flip them via the existing
# `POST /api/admin/master-bot/ranker/weights` endpoint without code
# changes. Zero weights produce backward-compatible ranking — proven
# in `tests/test_master_bot_ranker_bi5_signals.py`.
DEFAULT_WEIGHTS = {
    "deploy_score":       0.50,
    "pass_probability":   0.40,
    "bi5_cert_verdict":   0.07,
    "bi5_slippage_score": 0.03,
    "risk_of_ruin":       0.0,   # future
    "calibration":        0.0,   # future
    "regime_fitness":     0.0,   # future
}

# Verdict → unit-scale map for the ranker. PASS is the gold standard;
# WARN earns partial credit (calibration debt, not data defect);
# FAIL and "early-fail" reasons contribute zero. Absent / missing cert
# is treated as zero so absent-cert candidates rank exactly as they do
# under zero-weight (proves backwards-compat).
BI5_VERDICT_SCORE = {
    "PASS": 1.0,
    "WARN": 0.5,
    "FAIL": 0.0,
}


# ── Time helper ──────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Weights persistence ─────────────────────────────────────────────

async def _read_weights_doc() -> Optional[Dict[str, Any]]:
    db = get_db()
    return await db[CONFIG_COLL].find_one({"config_key": CONFIG_KEY}, {"_id": 0})


async def get_weights() -> Dict[str, Any]:
    """Return the persisted weight config, seeding defaults on first read.

    BI5 R2 / B-5 — 2026-06-13: when the persisted doc was seeded under
    an older `ranker_version`, the BI5 signals (bi5_cert_verdict and
    bi5_slippage_score) and the rebalanced defaults are merged in so
    operators don't have to manually re-seed. Operator overrides
    persisted under the new `ranker_version` are preserved verbatim.
    """
    doc = await _read_weights_doc()
    if doc:
        persisted_version = doc.get("ranker_version") or "v1.0"
        persisted_weights = doc.get("weights") or {}
        if persisted_version == RANKER_VERSION:
            # Already on-version — operator overrides win as before.
            weights = {**DEFAULT_WEIGHTS, **persisted_weights}
            return {
                "weights":         weights,
                "ranker_version":  persisted_version,
                "updated_at":      doc.get("updated_at"),
                "updated_by":      doc.get("updated_by"),
            }
        # Off-version → re-seed to the new defaults, idempotently.
        # We discard the old persisted weights because the old config
        # WAS the previous defaults (proven by `ranker_version=v1.0`
        # + `updated_by=system_default`) and we are explicitly
        # introducing a new default set. An operator override under
        # the old version would have an `updated_by != system_default`
        # — we preserve those explicitly.
        was_operator_override = (
            (doc.get("updated_by") or "system_default") != "system_default"
        )
        if was_operator_override:
            weights = {**DEFAULT_WEIGHTS, **persisted_weights}
        else:
            weights = dict(DEFAULT_WEIGHTS)
        db = get_db()
        now = _now_iso()
        try:
            await db[CONFIG_COLL].update_one(
                {"config_key": CONFIG_KEY},
                {"$set": {
                    "weights":        weights,
                    "ranker_version": RANKER_VERSION,
                    "updated_at":     now,
                    "updated_by":     "system_default" if not was_operator_override else doc.get("updated_by"),
                }},
                upsert=True,
            )
        except Exception:                                       # pragma: no cover
            logger.exception("master_bot_ranker: re-seed for R2 weights failed")
        return {
            "weights":        weights,
            "ranker_version": RANKER_VERSION,
            "updated_at":     now,
            "updated_by":     "system_default" if not was_operator_override else doc.get("updated_by"),
        }
    # Seed defaults idempotently.
    db = get_db()
    now = _now_iso()
    seed = {
        "config_key":    CONFIG_KEY,
        "weights":       dict(DEFAULT_WEIGHTS),
        "ranker_version": RANKER_VERSION,
        "updated_at":    now,
        "updated_by":    "system_default",
    }
    try:
        await db[CONFIG_COLL].update_one(
            {"config_key": CONFIG_KEY},
            {"$setOnInsert": seed},
            upsert=True,
        )
    except Exception:
        logger.exception("master_bot_ranker: seed defaults failed")
    return {
        "weights":        dict(DEFAULT_WEIGHTS),
        "ranker_version": RANKER_VERSION,
        "updated_at":     now,
        "updated_by":     "system_default",
    }


async def set_weights(
    patch: Dict[str, float],
    *,
    admin_email: str = "admin",
) -> Dict[str, Any]:
    if not isinstance(patch, dict) or not patch:
        raise ValueError("patch must be a non-empty dict of weight overrides")

    valid_keys = set(DEFAULT_WEIGHTS.keys())
    cleaned: Dict[str, float] = {}
    for k, v in patch.items():
        if k not in valid_keys:
            raise ValueError(f"unknown weight key: {k}")
        if not isinstance(v, (int, float)):
            raise ValueError(f"{k} weight must be numeric")
        f = float(v)
        if not (0.0 <= f <= 10.0):
            raise ValueError(f"{k} weight must be in [0.0, 10.0]")
        cleaned[k] = f

    current = (await get_weights())["weights"]
    merged = {**current, **cleaned}

    db = get_db()
    now = _now_iso()
    await db[CONFIG_COLL].update_one(
        {"config_key": CONFIG_KEY},
        {"$set": {
            "weights":        merged,
            "ranker_version": RANKER_VERSION,
            "updated_at":     now,
            "updated_by":     admin_email,
        }},
        upsert=True,
    )
    return {
        "weights":        merged,
        "ranker_version": RANKER_VERSION,
        "updated_at":     now,
        "updated_by":     admin_email,
    }


# ── Candidate enrichment ────────────────────────────────────────────

def _norm_unit(v: Optional[float], scale: float = 100.0) -> float:
    """Clamp v to [0, 1] given a scale (default 0..100 inputs)."""
    if v is None:
        return 0.0
    try:
        x = float(v) / scale
    except (TypeError, ValueError):
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


async def _fetch_library_rows(hashes: List[str]) -> Dict[str, Dict[str, Any]]:
    """Bulk-fetch library docs for enrichment. Single Mongo round-trip."""
    if not hashes:
        return {}
    db = get_db()
    cur = db["strategy_library"].find(
        {"strategy_hash": {"$in": list(hashes)}},
        {
            "_id": 0, "strategy_hash": 1, "pair": 1, "timeframe": 1,
            "strategy_type": 1, "style": 1,
            "profit_factor": 1, "win_rate": 1, "max_drawdown_pct": 1,
            "total_trades": 1, "stability_score": 1, "score": 1,
            "pass_probability": 1, "oos_holdout": 1,
            "bi5_cert": 1, "validation_report": 1,
            # MB-7.2 — pull IR + status so candidates surface
            # whether real strategy logic is available.
            "strategy_ir": 1, "ir_status": 1, "ir_version": 1,
        },
    )
    return {d.get("strategy_hash"): d async for d in cur}


async def _fetch_lifecycle_rows(hashes: List[str]) -> Dict[str, Dict[str, Any]]:
    if not hashes:
        return {}
    db = get_db()
    cur = db["strategy_lifecycle"].find(
        {"strategy_hash": {"$in": list(hashes)}},
        {"_id": 0},
    )
    return {d.get("strategy_hash"): d async for d in cur}


def _infer_style(lib_doc: Dict[str, Any]) -> Optional[str]:
    if not lib_doc:
        return None
    direct = lib_doc.get("style")
    if direct:
        return direct
    raw = (lib_doc.get("strategy_type") or "").lower()
    if not raw:
        return None
    if any(k in raw for k in ("trend", "macd", "ema", "sma", "break", "momentum")):
        return "trend"
    if any(k in raw for k in ("rsi", "revers", "bolli", "stoch", "oscill", "mean")):
        return "mean_reversion"
    return raw


def _norm_bi5_verdict(verdict: Optional[str]) -> float:
    """Verdict → 0..1 score for the ranker."""
    if not verdict:
        return 0.0
    return BI5_VERDICT_SCORE.get(str(verdict).upper(), 0.0)


def _compute_candidate_score(
    weights: Dict[str, float],
    *,
    deploy_score: Optional[float],
    pass_probability: Optional[float],
    risk_of_ruin: Optional[float] = None,
    calibration_score: Optional[float] = None,
    regime_fitness: Optional[float] = None,
    bi5_cert_verdict: Optional[str] = None,
    bi5_slippage_score: Optional[float] = None,
) -> Dict[str, Any]:
    """Pure scoring function. Returns the composite score plus the per-
    signal contribution breakdown so the UI can show "why is this #N?"."""
    norm = {
        "deploy_score":     _norm_unit(deploy_score, 100.0),
        "pass_probability": _norm_unit(pass_probability, 100.0),
        # Risk-of-ruin is "lower is better" — flip onto 0..1 via 1-RoR.
        "risk_of_ruin":     1.0 - _norm_unit(risk_of_ruin, 1.0)
                            if risk_of_ruin is not None else 0.0,
        "calibration":      _norm_unit(calibration_score, 1.0),
        "regime_fitness":   _norm_unit(regime_fitness, 1.0),
        # BI5 R2 / B-5 — BI5 cert signals.
        # `bi5_cert_verdict` is a category (PASS/WARN/FAIL/absent) so we
        # map it via the verdict table. `bi5_slippage_score` is already
        # 0..1 on the cert record (clamped at the persistence layer).
        "bi5_cert_verdict":   _norm_bi5_verdict(bi5_cert_verdict),
        "bi5_slippage_score": _norm_unit(bi5_slippage_score, 1.0),
    }
    contributions = {k: float(weights.get(k, 0.0)) * norm[k] for k in DEFAULT_WEIGHTS}
    weight_sum = sum(weights.get(k, 0.0) for k in DEFAULT_WEIGHTS) or 1.0
    score = sum(contributions.values()) / weight_sum
    return {
        "candidate_score": round(score, 6),
        "contributions":   {k: round(v, 6) for k, v in contributions.items()},
        "normalised":      {k: round(v, 6) for k, v in norm.items()},
    }


# ── Public: fetch candidate pool ────────────────────────────────────

async def fetch_candidate_pool(*, limit: int = 30) -> Dict[str, Any]:
    """Return the top-N ranked candidates (default top 30 per MB-2 spec)."""
    weights_doc = await get_weights()
    weights = weights_doc["weights"]

    # Source from the existing survivor universe (already eligible).
    survivor = await sr.fetch_survivor_universe(top_n=200)
    pool = survivor.get("universe") or []

    hashes = [d.get("strategy_hash") for d in pool if d.get("strategy_hash")]
    lib_rows = await _fetch_library_rows(hashes)
    lc_rows = await _fetch_lifecycle_rows(hashes)

    enriched: List[Dict[str, Any]] = []
    for s in pool:
        sh = s.get("strategy_hash")
        lib = lib_rows.get(sh) or {}
        lc = lc_rows.get(sh) or {}
        evidence = (lc.get("evidence") or {})
        # deploy_score: prefer the survivor row (already extracted)
        ds = s.get("deploy_score")
        if ds is None:
            ds = evidence.get("deploy_score")
        # pass_probability: prefer lifecycle evidence (post-calibration),
        # fall back to library doc.
        pp = evidence.get("pass_probability")
        if pp is None:
            pp = lib.get("pass_probability")

        # Future-signal hooks (advisory; weights default to 0.0).
        ror = evidence.get("risk_of_ruin")
        cal = evidence.get("calibration_score")
        reg = evidence.get("regime_fitness")

        # BI5 R2 / B-5 — read BI5 certification signal from the
        # library doc's `bi5_cert` projection (already present, see
        # `_fetch_library_rows` above). Absent cert produces
        # verdict=None → maps to 0.0 via `_norm_bi5_verdict`.
        bi5_cert = lib.get("bi5_cert") or {}
        bi5_verdict = (
            bi5_cert.get("certification_verdict")
            or bi5_cert.get("verdict")
        )
        bi5_slip = bi5_cert.get("slippage_score")

        score_block = _compute_candidate_score(
            weights,
            deploy_score=ds,
            pass_probability=pp,
            risk_of_ruin=ror,
            calibration_score=cal,
            regime_fitness=reg,
            bi5_cert_verdict=bi5_verdict,
            bi5_slippage_score=bi5_slip,
        )

        enriched.append({
            "strategy_hash":   sh,
            "pair":            lib.get("pair"),
            "timeframe":       lib.get("timeframe"),
            "style":           _infer_style(lib),
            "lifecycle_stage": s.get("current_stage"),
            "stage_rank":      s.get("stage_rank"),
            "deploy_score":    ds,
            "pass_probability": pp,
            "profit_factor":   lib.get("profit_factor"),
            "win_rate":        lib.get("win_rate"),
            "max_drawdown_pct": lib.get("max_drawdown_pct"),
            "total_trades":    lib.get("total_trades"),
            "stability_score": lib.get("stability_score"),
            "flags":           s.get("flags") or [],
            # Future-signal hooks (always present, often null).
            "risk_of_ruin":      ror,
            "calibration_score": cal,
            "regime_fitness":    reg,
            # BI5 R2 / B-5 — surface the cert signals on every row so
            # the UI can show "why is this #N?" cleanly. `bi5_cert`
            # itself is also passed through so the operator inspector
            # can dig into the sub-scores.
            "bi5_cert_verdict":   bi5_verdict,
            "bi5_slippage_score": bi5_slip,
            "bi5_cert":           bi5_cert or None,
            # MB-7.2: surface IR availability + the IR itself so the
            # member-add flow can persist it into the snapshot. The
            # UI uses `ir_status` to badge candidates "real strategy
            # logic available" vs "stub fallback".
            "strategy_ir":   lib.get("strategy_ir"),
            "ir_status":     lib.get("ir_status") or ("ir_native" if lib.get("strategy_ir") else "legacy"),
            "ir_version":    lib.get("ir_version"),
            # Score + breakdown
            "candidate_score":      score_block["candidate_score"],
            "score_contributions":  score_block["contributions"],
            "score_normalised":     score_block["normalised"],
        })

    # Sort by composite score desc; stable alphabetical tie-breaker on hash.
    enriched.sort(
        key=lambda r: (-(r.get("candidate_score") or 0.0), r.get("strategy_hash") or ""),
    )
    top = enriched[: int(limit)]

    return {
        "candidates":      top,
        "count":           len(top),
        "pool_size":       len(enriched),
        "ranker_version":  RANKER_VERSION,
        "weights":         weights,
        "active_signals":  [k for k, v in weights.items() if v > 0.0],
        "future_signals":  [k for k, v in weights.items() if v == 0.0],
        "computed_at":     _now_iso(),
        "advisory_only":   True,
    }
