"""Phase 26.5 — Strategy Lifecycle State Machine.

Single source of truth for the 8-stage strategy lifecycle:

    EXPLORATORY → CANDIDATE → VALIDATED → STABLE → PROP_SAFE
                → ELITE → PORTFOLIO_WORTHY → DEPLOYMENT_READY

Each gate is a **pure function over already-cached fields** — no backtest
re-run, no LLM call, no expensive I/O. Cohort percentiles for ELITE come
from the caller (one cheap pass over the rollup, reused for the whole
batch). BI5 realism / portfolio membership / cBot validation are not
yet computed (the gates fail safely until those modules land in later
phases) — the lifecycle module already models all 8 states so callers
see a coherent ladder today, with PORTFOLIO_WORTHY / DEPLOYMENT_READY
unreachable until G6 / BI5 / G7 close their loops.

Design tenets:
    * **Additive.** Old 4-stage `stage` label remains untouched in
      ``strategy_memory._attach_validation_view``. The new fields
      (``lifecycle_stage`` / ``lifecycle_stage_rank`` /
      ``lifecycle_flags`` / ``lifecycle_cool_down_until``) are appended.
    * **Cached only.** Inputs are: a library doc, the history rows for
      the same hash, and a cohort percentile passed by the caller.
    * **Hysteresis-aware.** When a prior lifecycle doc is supplied, the
      "stay" thresholds are slightly tighter than the "enter" thresholds
      to prevent flip-flop on tick-to-tick metric jitter.
    * **Graceful degradation.** Missing fields → gate fails closed.
      Strategies stay at the highest stage their evidence supports.
    * **Pure function — no I/O.** Persistence lives in the helper
      ``upsert_lifecycle`` and is opt-in (Explorer rollup never writes).

Public surface:
    * compute_lifecycle_state(library_doc, history_rows, *, ...) -> dict
    * compute_lifecycle_state_from_rollup(entry, *, ...) -> dict
    * upsert_lifecycle(strategy_hash, *, library_id, state, prior_state,
                       research_run_id) -> dict
    * get_lifecycle(strategy_hash) -> dict | None
    * get_lifecycle_map(strategy_hashes) -> dict[hash, doc]
    * compute_cohort_p90_deploy_score(rollup_entries) -> float | None
    * estimate_deploy_score(library_doc) -> float | None

Exposed constants:
    * LIFECYCLE_STAGES — ordered tuple of stage strings
    * STAGE_RANK — dict {stage: int}
    * LIFECYCLE_FLAGS — closed taxonomy
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from engines.db import get_db

logger = logging.getLogger(__name__)

LIFECYCLE_COLL = "strategy_lifecycle"
LIFECYCLE_HISTORY_COLL = "strategy_lifecycle_history"

# ── Taxonomy ────────────────────────────────────────────────────────

LIFECYCLE_STAGES = (
    "exploratory",
    "candidate",
    "validated",
    "stable",
    "prop_safe",
    "elite",
    "portfolio_worthy",
    "deployment_ready",
)
STAGE_RANK: Dict[str, int] = {s: i for i, s in enumerate(LIFECYCLE_STAGES)}

# Closed flag taxonomy (UI tones key off these strings)
LIFECYCLE_FLAGS = {
    "PARTIAL_REALISM",     # 0.50 ≤ realism_pf < 0.75
    "BI5_FAIL",            # realism_pf < 0.50 — 30-day cool-down
    "STALE",               # no new run in ≥30 days
    "MANUALLY_OVERRIDDEN", # operator force-promoted/demoted
    # Phase 27.3 / BI5 — flag-and-allow when BI5 ticks aren't loaded.
    # Strategy stays at PORTFOLIO_WORTHY without demotion; UI shows
    # "BI5 not verified" pill so operator knows to upload BI5 chunks.
    "BI5_DATA_MISSING",
    # Phase 29.0 — REGIME_FRAGILE is reserved in the closed taxonomy
    # for advisory regime-evidence. Per operator decisions:
    #   • 29.0 is observational only. This flag is NOT emitted to
    #     persisted lifecycle docs in 29.0. It exists in the taxonomy
    #     so consumers (UI, API) can declare it as a recognised flag
    #     value, and so the 29.1 operator-decision (whether to emit
    #     and/or cap promotion) is a single field flip — audit-loud,
    #     not a schema change.
    #   • Evidence is surfaced live by `api/regime.py` endpoints
    #     (on-read only — operator decision #4) without writing to
    #     `strategy_lifecycle`.
    #   • `unknown` regime is a refusal state, NEVER negative evidence
    #     (operator guarantee #2).
    "REGIME_FRAGILE",
}

# Demotion buffers — entry threshold + buffer = "stay" threshold.
# Encoded directly inside the gate functions when relevant.
_BI5_FAIL_COOLDOWN_DAYS = 30
_STALE_DAYS = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _safe_num(v: Any) -> Optional[float]:
    if isinstance(v, (int, float)) and v == v:
        return float(v)
    return None


def _safe_int(v: Any) -> Optional[int]:
    n = _safe_num(v)
    return int(n) if n is not None else None


# ── Gate functions (pure, deterministic) ──────────────────────────

def _gate_candidate(lib: Dict[str, Any], runs: int) -> bool:
    """Has library_id, ≥3 runs, IS_PF≥1.2, total_trades≥30."""
    if not lib:
        return False
    if runs < 3:
        return False
    pf = _safe_num(lib.get("profit_factor"))
    if pf is None or pf < 1.2:
        return False
    trades = _safe_num(lib.get("total_trades"))
    if trades is None or trades < 30:
        return False
    return True


def _gate_validated(lib: Dict[str, Any], oos_ratio_buffer: float = 0.0) -> bool:
    """OOS_ratio ≥ 0.7, stability ≥ 60, no OVERFIT_RISK."""
    if not lib:
        return False
    oos = lib.get("oos_holdout") or {}
    ratio = _safe_num(oos.get("ratio"))
    if ratio is None or ratio < (0.7 - oos_ratio_buffer):
        return False
    stab = _safe_num(lib.get("stability_score"))
    if stab is None or stab < 60.0:
        return False
    badges = ((lib.get("validation_report") or {}).get("badges") or [])
    if "OVERFIT_RISK" in badges:
        return False
    return True


def _cross_run_cov(pfs: List[float]) -> Optional[float]:
    """Coefficient of variation = std/|mean|. None if insufficient data."""
    if len(pfs) < 2:
        return None
    mean = sum(pfs) / len(pfs)
    if abs(mean) < 1e-9:
        return None
    var = sum((p - mean) ** 2 for p in pfs) / len(pfs)
    return math.sqrt(var) / abs(mean)


def _gate_stable(
    lib: Dict[str, Any],
    history_pfs: List[float],
    cov_buffer: float = 0.0,
) -> bool:
    """≥5 runs with PF, cross-run CoV ≤ 0.25, behavioral profile classified."""
    if len(history_pfs) < 5:
        return False
    cov = _cross_run_cov(history_pfs[-10:])    # last 10 runs at most
    if cov is None or cov > (0.25 + cov_buffer):
        return False
    profile = (lib.get("behavioral_profile") or "").upper()
    if profile in ("", "UNCLASSIFIED", "BALANCED"):
        return False
    return True


def _gate_prop_safe(lib: Dict[str, Any], dd_buffer: float = 0.0) -> bool:
    """DD<5%, pass_prob≥60%, smoothness∈{SMOOTH,null}, asymm-breakout DD-aware."""
    dd = _safe_num(lib.get("max_drawdown_pct"))    # 0..1 fraction
    if dd is None or dd >= (0.05 + dd_buffer):
        return False
    # pass_probability sometimes stored as 0..1, sometimes 0..100 — normalize
    pp = _safe_num(lib.get("pass_probability"))
    if pp is None:
        return False
    pp_pct = pp * 100.0 if pp <= 1.0 else pp
    if pp_pct < 60.0:
        return False
    smooth = (lib.get("smoothness_label") or "").upper()
    if smooth == "VOLATILE":
        return False
    profile = (lib.get("behavioral_profile") or "").upper()
    if profile == "ASYMMETRIC_BREAKOUT":
        # Only passes if losing streaks fit inside daily-loss limits.
        consec = _safe_num(lib.get("expected_max_consec_losses"))
        if consec is None or consec > 5:
            return False
    return True


def _gate_elite(
    lib: Dict[str, Any],
    runs: int,
    distinct_regimes: int,
    cohort_p90_deploy_score: Optional[float],
    pre_computed_deploy_score: Optional[float] = None,
) -> bool:
    """deploy_score≥p90 of cohort, ≥10 runs, ≥2 regimes, recovery_factor≥1.5."""
    if cohort_p90_deploy_score is None:
        return False
    if runs < 10:
        return False
    if distinct_regimes < 2:
        return False
    rec = _safe_num(lib.get("recovery_factor"))
    if rec is None or rec < 1.5:
        return False
    score = pre_computed_deploy_score
    if score is None:
        score = estimate_deploy_score(lib)
    if score is None or score < cohort_p90_deploy_score:
        return False
    return True


def _gate_portfolio_worthy(portfolio_membership: Optional[Dict[str, Any]]) -> bool:
    """Member of an active portfolio + verified-firm match_score ≥ 0.8."""
    if not portfolio_membership:
        return False
    if not portfolio_membership.get("is_member"):
        return False
    score = _safe_num(portfolio_membership.get("firm_match_score"))
    if score is None or score < 0.8:
        return False
    if (portfolio_membership.get("firm_status") or "").lower() != "approved":
        return False
    return True


def _gate_deployment_ready(
    lib: Dict[str, Any],
    bi5_realism: Optional[Dict[str, Any]],
    cbot_status: Optional[Dict[str, Any]],
    bi5_buffer: float = 0.0,
) -> bool:
    """BI5 realism PF ratio≥0.75, cBot compiles, safe risk per trade≤1%."""
    if not bi5_realism:
        return False
    pf_ratio = _safe_num(bi5_realism.get("pf_ratio"))
    if pf_ratio is None or pf_ratio < (0.75 - bi5_buffer):
        return False
    if not (cbot_status and cbot_status.get("compiled")
            and cbot_status.get("valid", True)):
        return False
    safe_risk = _safe_num((lib.get("prop_firm_panel") or {}).get("safe_risk_per_trade"))
    if safe_risk is None or safe_risk <= 0 or safe_risk > 0.01:
        return False
    return True


# ── Cohort + score helpers ─────────────────────────────────────────

def estimate_deploy_score(lib: Dict[str, Any]) -> Optional[float]:
    """When ``deploy_score`` is not pre-computed on the library doc, build a
    blended 0..100 estimate from cached fields. Mirrors
    ``auto_selection_engine._compute_deploy_score`` but inlined to avoid a
    cross-engine import on a pure-function path.

    Weights: pass_prob 25 % · stability 20 % · pf_capped 15 % ·
    oos_ratio 15 % · dd_inv 10 % · score 10 % · trades_adequacy 5 %.
    """
    if not lib:
        return None
    pp = _safe_num(lib.get("pass_probability"))
    if pp is not None and pp <= 1.0:
        pp = pp * 100.0
    stab = _safe_num(lib.get("stability_score"))         # 0..100
    pf = _safe_num(lib.get("profit_factor"))
    oos = _safe_num((lib.get("oos_holdout") or {}).get("ratio"))
    dd = _safe_num(lib.get("max_drawdown_pct"))
    score_field = _safe_num(lib.get("score"))            # 0..100
    trades = _safe_num(lib.get("total_trades"))

    parts: List[float] = []
    weight_total = 0.0
    if pp is not None:
        parts.append(min(100.0, max(0.0, pp)) * 0.25)
        weight_total += 0.25
    if stab is not None:
        parts.append(min(100.0, max(0.0, stab)) * 0.20)
        weight_total += 0.20
    if pf is not None:
        # Cap PF at 3.0 to avoid over-weighting overfit outliers (>5 already
        # tagged OVERFIT_RISK by Phase 24 badges).
        parts.append(min(100.0, (min(pf, 3.0) / 3.0) * 100.0) * 0.15)
        weight_total += 0.15
    if oos is not None:
        parts.append(min(100.0, max(0.0, oos * 100.0)) * 0.15)
        weight_total += 0.15
    if dd is not None:
        # 0% DD → 100; 20% DD → 0
        dd_score = max(0.0, min(100.0, (1.0 - (dd / 0.20)) * 100.0))
        parts.append(dd_score * 0.10)
        weight_total += 0.10
    if score_field is not None:
        parts.append(min(100.0, max(0.0, score_field)) * 0.10)
        weight_total += 0.10
    if trades is not None:
        # Saturating trade-count credit: 30 trades → 50, 100 trades → 100
        adequacy = (
            min(100.0, max(0.0, (trades - 30) * 100.0 / 70.0))
            if trades >= 30 else 0.0
        )
        parts.append(adequacy * 0.05)
        weight_total += 0.05
    if not parts or weight_total < 1e-6:
        return None
    return round(sum(parts) / weight_total, 2)


def _percentile(values: List[float], pct: float) -> Optional[float]:
    """Linear-interpolation percentile. Returns None on empty."""
    if not values:
        return None
    sv = sorted(values)
    if len(sv) == 1:
        return sv[0]
    rank = (pct / 100.0) * (len(sv) - 1)
    lo, hi = math.floor(rank), math.ceil(rank)
    if lo == hi:
        return sv[lo]
    return sv[lo] + (sv[hi] - sv[lo]) * (rank - lo)


def compute_cohort_p90_deploy_score(
    library_docs: Iterable[Dict[str, Any]],
    *,
    min_cohort_size: int = 10,
    min_total_trades: int = 30,
) -> Optional[float]:
    """One-shot p90 cutoff over the prop-safe-eligible cohort.

    Caller should pass the already-filtered cohort (PROP_SAFE candidates
    in the last 30 days). Returns None when cohort < ``min_cohort_size``.
    """
    scores: List[float] = []
    for d in library_docs:
        if (_safe_num(d.get("total_trades")) or 0) < min_total_trades:
            continue
        s = _safe_num(d.get("deploy_score")) or estimate_deploy_score(d)
        if s is not None:
            scores.append(s)
    if len(scores) < min_cohort_size:
        return None
    return _percentile(scores, 90)


# ── Core compute ───────────────────────────────────────────────────

def compute_lifecycle_state(
    *,
    library_doc: Optional[Dict[str, Any]],
    history_rows: List[Dict[str, Any]],
    cohort_p90_deploy_score: Optional[float] = None,
    bi5_realism: Optional[Dict[str, Any]] = None,
    cbot_status: Optional[Dict[str, Any]] = None,
    portfolio_membership: Optional[Dict[str, Any]] = None,
    prior_state: Optional[Dict[str, Any]] = None,
    last_run_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Determine the current lifecycle state. Pure function — no I/O.

    Returns:
        {
          "current_stage":      str,   # one of LIFECYCLE_STAGES
          "stage_rank":         int,   # 0..7
          "evidence":           dict,  # the inputs that decided each gate
          "flags":              list,  # subset of LIFECYCLE_FLAGS
          "cool_down_until":    iso str | None,
          "computed_at":        iso str,
        }
    """
    lib = library_doc or {}
    runs = len(history_rows)
    history_pfs = [
        float(r["pf"]) for r in history_rows
        if isinstance(r.get("pf"), (int, float))
    ]
    distinct_regimes = len(
        {r.get("regime") for r in history_rows if r.get("regime")}
    )

    # ── Hysteresis buffers ────────────────────────────────────────
    # If we were already at this stage, apply the slightly stricter
    # "stay" threshold to prevent flip-flop. Otherwise no buffer.
    prior_stage = (prior_state or {}).get("current_stage")
    bufs = {"oos_ratio": 0.0, "cov": 0.0, "dd": 0.0, "bi5": 0.0}
    if prior_stage == "validated":
        bufs["oos_ratio"] = 0.10                # demote at <0.6 (entry 0.7)
    elif prior_stage == "stable":
        bufs["cov"] = 0.10                      # demote at >0.35 (entry 0.25)
    elif prior_stage == "prop_safe":
        bufs["dd"] = 0.02                       # demote at ≥0.07 (entry 0.05)
    elif prior_stage == "deployment_ready":
        bufs["bi5"] = 0.10                      # demote at <0.65 (entry 0.75)

    # ── Cool-down ──────────────────────────────────────────────────
    # If a prior BI5_FAIL is still cooling down, cap stage at "stable".
    flags_in: List[str] = list((prior_state or {}).get("flags") or [])
    cool_down_until = (prior_state or {}).get("cool_down_until")
    bi5_locked = False
    if cool_down_until:
        try:
            cd = datetime.fromisoformat(cool_down_until.replace("Z", "+00:00"))
            if cd > _now():
                bi5_locked = True
        except Exception:                               # pragma: no cover
            cool_down_until = None
    flags_out: List[str] = []

    # ── Walk the ladder upward; highest passing gate wins ─────────
    stage = "exploratory"
    has_lib_id = bool(lib.get("_id") or lib.get("library_id"))
    if has_lib_id and _gate_candidate(lib, runs):
        stage = "candidate"
        if _gate_validated(lib, oos_ratio_buffer=bufs["oos_ratio"]):
            stage = "validated"
            if _gate_stable(lib, history_pfs, cov_buffer=bufs["cov"]):
                stage = "stable"
                if _gate_prop_safe(lib, dd_buffer=bufs["dd"]):
                    stage = "prop_safe"
                    if not bi5_locked and _gate_elite(
                        lib, runs, distinct_regimes,
                        cohort_p90_deploy_score,
                    ):
                        stage = "elite"
                        if _gate_portfolio_worthy(portfolio_membership):
                            stage = "portfolio_worthy"
                            if _gate_deployment_ready(
                                lib, bi5_realism, cbot_status,
                                bi5_buffer=bufs["bi5"],
                            ):
                                stage = "deployment_ready"

    # ── Flags ─────────────────────────────────────────────────────
    if bi5_realism:
        # Phase 27.3 — surface BI5_DATA_MISSING when the realism gate
        # could not run because BI5 ticks aren't loaded yet. This is
        # the design's "flag-and-allow" path: no demotion, no
        # cool-down, but the operator UI shows a clear "not verified"
        # pill so they know to upload BI5 chunks.
        if (bi5_realism.get("status") == "data_missing"
                and "BI5_DATA_MISSING" not in flags_out):
            flags_out.append("BI5_DATA_MISSING")
        pfr = _safe_num(bi5_realism.get("pf_ratio"))
        if pfr is not None:
            if pfr < 0.50:
                flags_out.append("BI5_FAIL")
                cool_down_until = (_now() + timedelta(
                    days=_BI5_FAIL_COOLDOWN_DAYS)).isoformat()
            elif pfr < 0.75:
                flags_out.append("PARTIAL_REALISM")
    if "MANUALLY_OVERRIDDEN" in flags_in:
        flags_out.append("MANUALLY_OVERRIDDEN")
    if last_run_at:
        try:
            ts = datetime.fromisoformat(last_run_at.replace("Z", "+00:00"))
            if (_now() - ts).days >= _STALE_DAYS and STAGE_RANK[stage] >= STAGE_RANK["stable"]:
                flags_out.append("STALE")
        except Exception:                               # pragma: no cover
            pass

    return {
        "current_stage": stage,
        "stage_rank":    STAGE_RANK[stage],
        "evidence": {
            "runs":                runs,
            "is_pf":               _safe_num(lib.get("profit_factor")),
            "total_trades":        _safe_int(lib.get("total_trades")),
            "oos_ratio":           _safe_num((lib.get("oos_holdout") or {}).get("ratio")),
            "stability_score":     _safe_num(lib.get("stability_score")),
            "max_drawdown_pct":    _safe_num(lib.get("max_drawdown_pct")),
            "pass_probability":    _safe_num(lib.get("pass_probability")),
            "behavioral_profile":  lib.get("behavioral_profile"),
            "smoothness_label":    lib.get("smoothness_label"),
            "expected_max_consec_losses":
                _safe_num(lib.get("expected_max_consec_losses")),
            "recovery_factor":     _safe_num(lib.get("recovery_factor")),
            "cross_run_cov":       (
                round(_cross_run_cov(history_pfs[-10:]) or 0.0, 4)
                if history_pfs else None
            ),
            "distinct_regimes":    distinct_regimes,
            "deploy_score":        _safe_num(lib.get("deploy_score"))
                                    or estimate_deploy_score(lib),
            "cohort_p90":          cohort_p90_deploy_score,
            "bi5_pf_ratio":        _safe_num((bi5_realism or {}).get("pf_ratio")),
            "bi5_locked":          bi5_locked,
            "applied_buffers":     bufs,
        },
        "flags":           flags_out,
        "cool_down_until": cool_down_until,
        "computed_at":     _now_iso(),
    }


def compute_lifecycle_state_from_rollup(
    entry: Dict[str, Any],
    *,
    cohort_p90_deploy_score: Optional[float] = None,
    bi5_realism: Optional[Dict[str, Any]] = None,
    cbot_status: Optional[Dict[str, Any]] = None,
    portfolio_membership: Optional[Dict[str, Any]] = None,
    prior_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Adapter for the Explorer rollup case. The rollup carries already
    aggregated fields (``runs`` / ``stability_score`` / ``regimes`` count
    map / ``library`` snapshot) — feed those into a synthetic library_doc
    + history_rows shape and reuse the core function so the gates are
    identical."""
    lib_snap = dict(entry.get("library") or {})
    # The rollup carries library_id at the entry level; promote it so
    # _gate_candidate sees a truthy id even when the library snapshot
    # itself only has metric fields.
    if entry.get("library_id"):
        lib_snap["library_id"] = entry["library_id"]
    # Behavioral metrics live on validation.metrics in the rollup view —
    # mirror them onto the library snapshot so gates can read uniformly.
    val = (entry.get("validation") or {}).get("metrics") or {}
    for k in (
        "behavioral_profile", "smoothness_label", "expected_max_consec_losses",
        "recovery_factor",
    ):
        if k not in lib_snap and val.get(k) is not None:
            lib_snap[k] = val.get(k)
    runs = int(entry.get("runs") or 0)

    # Build a synthetic history slice — only PF + regime are gate-relevant.
    # The rollup collapses regime counts so we reconstruct one row per
    # distinct regime with the avg_pf so the cov / regime gates still get
    # representative inputs without scanning the full history collection.
    pfs_repr: List[float] = []
    avg_pf = _safe_num(entry.get("avg_pf"))
    best_pf = _safe_num(entry.get("best_pf"))
    last_pf = _safe_num(entry.get("last_pf"))
    min_pf = _safe_num(entry.get("min_pf"))
    for pf in (best_pf, last_pf, avg_pf, min_pf):
        if pf is not None:
            pfs_repr.append(pf)
    # If the rollup gave us the per-run "stability_score" (0..1), prefer
    # that signal: convert to an equivalent set of PFs that yields the
    # same cov so _gate_stable behaves identically without raw history.
    stab_norm = _safe_num(entry.get("stability_score"))
    if stab_norm is not None and 0.0 <= stab_norm <= 1.0 and avg_pf:
        # cov ≈ 1 - stability. Synthesise pfs so std/|mean| ≈ cov.
        cov = max(0.0, min(1.0, 1.0 - stab_norm))
        spread = avg_pf * cov
        pfs_repr = [avg_pf - spread, avg_pf, avg_pf + spread] * max(2, runs // 3)

    regimes = entry.get("regimes") or {}
    history_rows: List[Dict[str, Any]] = []
    for r, count in regimes.items():
        # one row per regime, repeated `count` times — only `pf` + `regime`
        # are read by gates, so a tiny synthetic stand-in is enough.
        for _ in range(min(count, 50)):                  # cap fan-out
            history_rows.append({"regime": r, "pf": avg_pf})

    if len(history_rows) < runs and pfs_repr:
        # Fill missing rows so len(history_rows) ≈ runs for STABLE/ELITE.
        i = 0
        while len(history_rows) < runs:
            history_rows.append({"pf": pfs_repr[i % len(pfs_repr)],
                                 "regime": None})
            i += 1

    return compute_lifecycle_state(
        library_doc=lib_snap,
        history_rows=history_rows,
        cohort_p90_deploy_score=cohort_p90_deploy_score,
        bi5_realism=bi5_realism,
        cbot_status=cbot_status,
        portfolio_membership=portfolio_membership,
        prior_state=prior_state,
        last_run_at=entry.get("last_seen"),
    )


# ── Persistence (opt-in, never called from Explorer rollup) ───────

async def upsert_lifecycle(
    strategy_hash: str,
    *,
    library_id: Optional[str],
    state: Dict[str, Any],
    prior_state: Optional[Dict[str, Any]] = None,
    research_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist current lifecycle state for a strategy. Logs every stage
    transition into ``strategy_lifecycle_history`` for audit.

    Returns the persisted doc (without ``_id``).
    """
    if not strategy_hash:
        raise ValueError("strategy_hash required")
    db = get_db()
    now = _now_iso()
    new_stage = state["current_stage"]
    prior_stage = (prior_state or {}).get("current_stage")
    same_stage = prior_stage == new_stage

    doc = {
        "strategy_hash":        strategy_hash,
        "library_id":           library_id,
        "current_stage":        new_stage,
        "stage_rank":           state["stage_rank"],
        "current_stage_since":  (
            (prior_state or {}).get("current_stage_since") or now
            if same_stage else now
        ),
        "evidence":             state.get("evidence") or {},
        "flags":                list(state.get("flags") or []),
        "cool_down_until":      state.get("cool_down_until"),
        "last_evaluated_at":    now,
        "research_run_id":      research_run_id
                                or (prior_state or {}).get("research_run_id"),
    }

    # ── Phase 30.1 · Δ4 — First-time `elite` admission marker ──────
    # Stamp `phase30_universe_member=True` ONLY on the FIRST transition
    # into `elite`. Idempotent: once stamped, neither this code path
    # nor any later evaluator may rewrite the marker. Historically
    # additive: a strategy that demotes out of `elite` keeps the
    # marker (it records "ever admitted", not "currently admitted").
    prior_marker = bool((prior_state or {}).get("phase30_universe_member"))
    if prior_marker:
        # Persist forward so the marker stays alive across upserts.
        doc["phase30_universe_member"] = True
        if (prior_state or {}).get("phase30_universe_joined_at"):
            doc["phase30_universe_joined_at"] = (
                (prior_state or {}).get("phase30_universe_joined_at")
            )
    elif (
        new_stage == "elite"
        and prior_stage != "elite"
    ):
        doc["phase30_universe_member"]    = True
        doc["phase30_universe_joined_at"] = now

    try:
        await db[LIFECYCLE_COLL].update_one(
            {"strategy_hash": strategy_hash},
            {"$set": doc},
            upsert=True,
        )
    except Exception as e:
        logger.warning("[lifecycle] upsert failed: %s", e)

    # Audit log — append-only on transitions.
    if not same_stage:
        try:
            await db[LIFECYCLE_HISTORY_COLL].insert_one({
                "strategy_hash":     strategy_hash,
                "library_id":        library_id,
                "from_stage":        prior_stage,
                "from_stage_rank":   STAGE_RANK.get(prior_stage) if prior_stage else None,
                "to_stage":          new_stage,
                "to_stage_rank":     state["stage_rank"],
                "transition_at":     now,
                "evidence_snapshot": state.get("evidence") or {},
                "flags":             list(state.get("flags") or []),
                "research_run_id":   research_run_id,            })
        except Exception as e:                          # pragma: no cover
            logger.warning("[lifecycle] history append failed: %s", e)

    # ── Phase 30.1 · Δ2 — Institutional Event Notifications ───────
    # Subordinate-only. Wrapped in broad try/except: alert failures
    # MUST NEVER block lifecycle writes, alter governance state, or
    # change promotion timing (operator decree).
    if not same_stage:
        try:
            from engines.alert_engine import emit_event as _emit
            from_rank = STAGE_RANK.get(prior_stage, 0)
            to_rank   = STAGE_RANK.get(new_stage, 0)
            is_promotion = to_rank > from_rank
            event_details = {
                "from_stage":   prior_stage,
                "to_stage":     new_stage,
                "deploy_score": (state.get("evidence") or {}).get("deploy_score"),
                "research_run_id": research_run_id,
            }
            if new_stage == "deployment_ready" and is_promotion:
                await _emit(
                    "LIFECYCLE_DEPLOYMENT_READY", strategy_hash,
                    event_details, run_id=research_run_id,
                )
            if new_stage == "elite" and is_promotion:
                await _emit(
                    "LIFECYCLE_ELITE_PROMOTION", strategy_hash,
                    event_details, run_id=research_run_id,
                )
                # First-time admission to the Phase 30 universe — only
                # emit when the Δ4 marker was just stamped on THIS
                # upsert (i.e. prior_marker was False).
                if not prior_marker:
                    await _emit(
                        "SURVIVOR_ADMITTED", strategy_hash,
                        event_details, run_id=research_run_id,
                    )
            # Demotion out of the survivor universe.
            if (
                prior_stage in ("elite", "portfolio_worthy", "deployment_ready")
                and new_stage not in ("elite", "portfolio_worthy", "deployment_ready")
                and to_rank < from_rank
            ):
                await _emit(
                    "SURVIVOR_DEMOTED", strategy_hash,
                    event_details, run_id=research_run_id,
                )
        except Exception as e:                                  # pragma: no cover
            logger.debug("[lifecycle] event emit swallowed: %s", e)
    return doc


async def get_lifecycle(strategy_hash: str) -> Optional[Dict[str, Any]]:
    if not strategy_hash:
        return None
    db = get_db()
    return await db[LIFECYCLE_COLL].find_one(
        {"strategy_hash": strategy_hash}, {"_id": 0},
    )


async def get_lifecycle_map(
    strategy_hashes: Iterable[str],
) -> Dict[str, Dict[str, Any]]:
    """Bulk lookup — returns {hash: doc} for the given hashes."""
    hashes = [h for h in strategy_hashes if h]
    if not hashes:
        return {}
    db = get_db()
    out: Dict[str, Dict[str, Any]] = {}
    async for d in db[LIFECYCLE_COLL].find(
        {"strategy_hash": {"$in": hashes}}, {"_id": 0},
    ):
        out[d["strategy_hash"]] = d
    return out


async def get_lifecycle_history(
    strategy_hash: str, *, limit: int = 50,
) -> List[Dict[str, Any]]:
    if not strategy_hash:
        return []
    db = get_db()
    cur = (
        db[LIFECYCLE_HISTORY_COLL]
        .find({"strategy_hash": strategy_hash}, {"_id": 0})
        .sort("transition_at", -1)
        .limit(max(1, min(int(limit), 500)))
    )
    return [d async for d in cur]


# ── Phase 27.2 / G6 — autonomous progression ──────────────────────

async def recent_transitions(
    *,
    since_iso: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Read recent stage transitions across all strategies.

    The orchestrator's ``observe_state`` calls this on every tick to
    aggregate promotion/demotion counters; the lifecycle API also
    surfaces it for ops visibility. Read-only, no I/O outside Mongo.

    ``since_iso`` filters by ``transition_at >= since_iso`` (string
    comparison works because ISO 8601 sorts lexically when timezones
    are normalised — all our writes use ``datetime.now(timezone.utc)``
    so this assumption holds).
    """
    db = get_db()
    q: Dict[str, Any] = {}
    if since_iso:
        q["transition_at"] = {"$gte": since_iso}
    cur = (
        db[LIFECYCLE_HISTORY_COLL]
        .find(q, {"_id": 0})
        .sort("transition_at", -1)
        .limit(max(1, min(int(limit), 500)))
    )
    return [d async for d in cur]


async def cohort_stage_counts() -> Dict[str, int]:
    """Distribution of strategies across the 8 lifecycle stages.

    Cheap aggregation over the persisted ``strategy_lifecycle``
    collection (one document per strategy_hash). Missing stages report
    as 0 so callers can render a stable shape.
    """
    db = get_db()
    counts: Dict[str, int] = {s: 0 for s in LIFECYCLE_STAGES}
    pipeline = [
        {"$group": {"_id": "$current_stage", "n": {"$sum": 1}}},
    ]
    try:
        async for row in db[LIFECYCLE_COLL].aggregate(pipeline):
            stage = row.get("_id")
            if stage in counts:
                counts[stage] = int(row.get("n") or 0)
    except Exception as e:                                   # pragma: no cover
        logger.debug("[lifecycle] cohort_stage_counts failed: %s", e)
    return counts


async def evaluate_cohort(
    *,
    persist: bool = True,
    limit: int = 500,
    research_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """One autonomous lifecycle pass over the eligible cohort.

    Steps (all over already-cached fields — no backtest re-run):
      1. Pull the Explorer rollup (which already attaches the live
         ``validation.lifecycle_stage`` view).
      2. Fetch any prior persisted lifecycle docs in one bulk lookup.
      3. For each row, recompute the lifecycle state with the prior
         state supplied for hysteresis, then upsert when ``persist`` is
         True (and the stage actually changed OR the persisted row is
         missing — first-touch rows always upsert so we have a baseline).
      4. Log each stage flip into ``strategy_lifecycle_history`` via
         ``upsert_lifecycle`` (it handles the audit append).

    Returns a summary suitable for the orchestrator + the API:
        {
          "evaluated":        int,
          "transitions":      [ {strategy_hash, from, to, at, evidence, flags}, ... ],
          "promotions":       int,
          "demotions":        int,
          "first_touch":      int,    # previously unknown → new baseline
          "stage_counts":     { stage: int, ... },   # post-eval distribution
          "cohort_p90_deploy_score": float | None,
          "evaluated_at":     iso,
        }
    """
    # Lazy import to avoid a circular module reference at import time
    # (strategy_memory imports strategy_lifecycle at function level).
    from engines import strategy_memory

    rollup = await strategy_memory.get_explorer_rollup(limit=limit)

    # Cohort p90 already attached by the rollup view, but we recompute
    # it here so the response carries the canonical number for the API.
    cohort_libs = [r.get("library") or {} for r in rollup if r.get("library")]
    p90 = compute_cohort_p90_deploy_score(cohort_libs)

    # Bulk fetch prior persisted state for every hash in the rollup.
    hashes = [r.get("strategy_hash") for r in rollup if r.get("strategy_hash")]
    prior_map = await get_lifecycle_map(hashes)

    transitions: List[Dict[str, Any]] = []
    promotions = 0
    demotions = 0
    first_touch = 0
    upserted = 0

    for row in rollup:
        h = row.get("strategy_hash")
        if not h:
            continue
        prior = prior_map.get(h)
        prior_stage = (prior or {}).get("current_stage")
        # Phase 27.3 — pull persisted BI5 realism block onto the gate
        # input. Stored on the lifecycle doc by `engines.bi5_realism`,
        # consumed via the existing `bi5_realism` kwarg of
        # `compute_lifecycle_state_from_rollup`. Keeps responsibilities
        # crisp: lifecycle owns the gates; bi5_realism owns the
        # evidence; this evaluator just stitches them together.
        bi5_block = (prior or {}).get("bi5_realism")
        # Recompute with prior_state so the gate functions apply the
        # documented hysteresis buffers (validated 0.10 OOS, stable
        # 0.10 CoV, prop_safe 0.02 DD, deployment_ready 0.10 BI5).
        try:
            state = compute_lifecycle_state_from_rollup(
                row,
                cohort_p90_deploy_score=p90,
                bi5_realism=bi5_block,
                prior_state=prior,
            )
        except Exception as e:                              # pragma: no cover
            logger.debug("[lifecycle] compute failed for %s: %s", h, e)
            continue
        new_stage = state["current_stage"]
        is_first_touch = prior is None
        is_transition = (not is_first_touch) and (prior_stage != new_stage)

        if persist and (is_first_touch or is_transition):
            try:
                await upsert_lifecycle(
                    h,
                    library_id=row.get("library_id"),
                    state=state,
                    prior_state=prior,
                    research_run_id=research_run_id,
                )
                upserted += 1
            except Exception as e:                          # pragma: no cover
                logger.debug("[lifecycle] upsert failed for %s: %s", h, e)

        if is_first_touch:
            first_touch += 1
            # First-touch is recorded but not counted as a transition
            # for orchestrator advisory rules — it's a baseline write.
        elif is_transition:
            from_rank = STAGE_RANK.get(prior_stage, 0)
            to_rank = STAGE_RANK.get(new_stage, 0)
            direction = "promotion" if to_rank > from_rank else "demotion"
            if direction == "promotion":
                promotions += 1
            else:
                demotions += 1
            transitions.append({
                "strategy_hash": h,
                "library_id":    row.get("library_id"),
                "from_stage":    prior_stage,
                "to_stage":      new_stage,
                "from_rank":     from_rank,
                "to_rank":       to_rank,
                "direction":     direction,
                "evidence":      state.get("evidence") or {},
                "flags":         state.get("flags") or [],
                "at":            state.get("computed_at"),
            })

    stage_counts = await cohort_stage_counts() if persist else {
        s: 0 for s in LIFECYCLE_STAGES
    }

    return {
        "evaluated":              len(rollup),
        "transitions":            transitions,
        "promotions":             promotions,
        "demotions":              demotions,
        "first_touch":            first_touch,
        "upserted":               upserted,
        "stage_counts":           stage_counts,
        "cohort_p90_deploy_score": p90,
        "evaluated_at":           _now_iso(),
        "research_run_id":        research_run_id,
    }
