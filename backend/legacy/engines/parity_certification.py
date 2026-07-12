"""
P1.5 — Dormant parity-certification aggregator and hard-gate primitive.

Status
------
* DORMANT BY DEFAULT. Gated by ``ENABLE_TRADE_PARITY_HARD_GATE``
  and ``ENABLE_HTF_PARITY_HARD_GATE`` (both default ``False``).
  Even when one or both are ON, **no production code path consults
  this module**. Activation requires BOTH flag flips AND a deliberate
  future single-file change in ``engines/cbot_parity.py`` that
  replaces (or augments) the existing ``is_passed(signoff)`` helper
  with the hardened ``would_pass_hard_gate(...)`` defined here.
* Pure functions. No I/O on import. Read-only against Mongo
  (one query against ``cbot_parity_signoff``) when the aggregator
  is invoked. Never writes to any collection.

Why this exists
---------------
The institutional roadmap (PRD §13) makes the P1.5 promotion of
trade-parity and HTF-parity from ADVISORY to HARD-GATE conditional
on soak evidence. The previous passes (P1.3, P1.4) made each
parity verdict observable per sign-off document. What was missing
is the aggregator that synthesises those rows into a single
operator-facing verdict:

  "Across the last N sign-offs, would promoting these advisories
   to hard gates have passed the institutional pass-rate threshold?"

Without that aggregator, P1.5 is a guess. With it, P1.5 is an
evidence-based, reversible operator decision.

Determinism
-----------
Every public function in this module is a pure function of its
inputs. The aggregator does ONE Mongo find (read-only); the
``would_pass_hard_gate`` predicate is pure. No randomness, no clock
reads (except ``now`` for windowing), no LLM, no network.

Wiring policy
-------------
* ``engines/cbot_parity.py`` is NOT modified by this pass. Its
  existing ``is_passed(signoff)`` helper continues to drive every
  caller (export gates, lifecycle promotions, audit checks).
* When operators are ready to put P1.5 into authority, the wiring
  point is a single-file change in ``engines/cbot_parity.py``:
  add a new ``is_passed_hard(signoff, *, require_trade=..., require_htf=...)``
  helper that delegates to ``would_pass_hard_gate``. The dormancy
  test below must be updated in the same PR to whitelist the new
  importer — institutional gate against drive-by activation.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


SIGNOFF_COLL = "cbot_parity_signoff"


# ─────────────────────────────────────────────────────────────────────
# Public flag accessors (dormant by default)
# ─────────────────────────────────────────────────────────────────────
def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def is_hard_gate_trade_enabled() -> bool:
    """True iff ``ENABLE_TRADE_PARITY_HARD_GATE`` is set to a truthy
    env value. Mirrors the discipline used by other dormant primitives:
    feature_flags is the canonical registry, but ``os.environ`` is
    the authoritative runtime source.
    """
    return _truthy("ENABLE_TRADE_PARITY_HARD_GATE")


def is_hard_gate_htf_enabled() -> bool:
    """True iff ``ENABLE_HTF_PARITY_HARD_GATE`` is set to a truthy
    env value.
    """
    return _truthy("ENABLE_HTF_PARITY_HARD_GATE")


def min_samples_default() -> int:
    """Operator-tunable minimum sign-off sample size before the
    promotion-readiness verdict can leave ``NEEDS_MORE_EVIDENCE``.
    Defaults to 30.
    """
    try:
        return max(1, int(os.environ.get("PARITY_CERTIFICATION_MIN_SAMPLES", "30")))
    except (TypeError, ValueError):
        return 30


def min_pass_rate_default() -> float:
    """Operator-tunable minimum would-pass-hard-gate rate before the
    promotion-readiness verdict can return ``PROMOTABLE``. Defaults
    to 0.95 (95%).
    """
    try:
        v = float(os.environ.get("PARITY_CERTIFICATION_MIN_PASS_RATE", "0.95"))
        return max(0.0, min(1.0, v))
    except (TypeError, ValueError):
        return 0.95


# ─────────────────────────────────────────────────────────────────────
# Pure hard-gate predicate
# ─────────────────────────────────────────────────────────────────────
def would_pass_hard_gate(
    signoff: Optional[Dict[str, Any]],
    *,
    require_trade_parity: bool = False,
    require_htf_parity: bool = False,
) -> bool:
    """Pure predicate — would this sign-off document satisfy a
    hardened parity gate?

    The CURRENT production gate (``engines.cbot_parity.is_passed``)
    is: ``signoff.status == "PASSED"`` — signal parity only.

    The future hardened gate would additionally require:
      * trade-parity verdict OK (when ``require_trade_parity=True``):
        ``signoff.trade_parity_passed is True``. A missing field
        means trade-parity was not run for this row — the predicate
        returns False (honest refusal: cannot certify without
        evidence).
      * HTF-parity verdict OK (when ``require_htf_parity=True``):
        ``signoff.htf_parity_verdict in ("EXACT", "WITHIN_TOLERANCE",
        "NOT_APPLICABLE")``. A missing field means HTF-parity was
        not run — same honest-refusal discipline.

    Parameters
    ----------
    signoff : dict | None
        The ``cbot_parity_signoff`` document. ``None`` returns
        ``False`` (no document, no certification).
    require_trade_parity : bool
        Require the advisory trade-parity field to be ``True``.
        When this caller is itself dormant (``require_*=False`` by
        default), the predicate degenerates to the existing
        signal-only ``is_passed`` semantics.
    require_htf_parity : bool
        Require the advisory HTF-parity field to be in the
        passing band.

    Returns
    -------
    bool
        ``True`` iff every requested dimension verifies.
    """
    if not signoff:
        return False
    # Signal parity — the existing production semantic.
    if signoff.get("status") != "PASSED":
        return False
    # Trade-parity (P1.3 advisory field) — honest refusal when absent.
    if require_trade_parity:
        if signoff.get("trade_parity_passed") is not True:
            return False
    # HTF-parity (P1.4 advisory field) — honest refusal when absent.
    if require_htf_parity:
        verdict = signoff.get("htf_parity_verdict")
        if verdict not in ("EXACT", "WITHIN_TOLERANCE", "NOT_APPLICABLE"):
            return False
    return True


# ─────────────────────────────────────────────────────────────────────
# Aggregator: certify a batch of sign-offs
# ─────────────────────────────────────────────────────────────────────
def summarize_signoffs(
    rows: Iterable[Dict[str, Any]],
    *,
    require_trade_parity: bool = True,
    require_htf_parity: bool = True,
) -> Dict[str, Any]:
    """Pure aggregator. Walks a list of sign-off documents and
    computes the distribution of statuses + advisory verdicts + the
    would-pass-hard-gate rate for the requested dimensions.

    Returns
    -------
    dict
        ``{
            "total":             int,
            "status_counts":     {PASSED: int, NO_IR: int, ...},
            "trade_parity":      {present: int, passed: int,
                                  rate: float | None},
            "htf_parity":        {present: int, verdicts:
                                  {EXACT: int, WITHIN_TOLERANCE: int,
                                   DIVERGENT: int, NOT_APPLICABLE: int,
                                   ERROR: int},
                                  passing: int, rate: float | None},
            "hard_gate":         {would_pass: int, rate: float | None,
                                  require_trade_parity: bool,
                                  require_htf_parity: bool},
          }``
    """
    rows_list = list(rows)
    n = len(rows_list)

    status_counts: Dict[str, int] = {}
    tp_present = 0
    tp_passed = 0
    htf_present = 0
    htf_verdicts: Dict[str, int] = {
        "EXACT": 0, "WITHIN_TOLERANCE": 0, "DIVERGENT": 0,
        "NOT_APPLICABLE": 0, "ERROR": 0,
    }
    htf_passing = 0
    would_pass = 0

    for row in rows_list:
        st = str(row.get("status") or "UNKNOWN")
        status_counts[st] = status_counts.get(st, 0) + 1

        if "trade_parity_passed" in row:
            tp_present += 1
            if row.get("trade_parity_passed") is True:
                tp_passed += 1

        if "htf_parity_verdict" in row:
            htf_present += 1
            v = row.get("htf_parity_verdict") or "UNKNOWN"
            htf_verdicts[v] = htf_verdicts.get(v, 0) + 1
            if v in ("EXACT", "WITHIN_TOLERANCE", "NOT_APPLICABLE"):
                htf_passing += 1

        if would_pass_hard_gate(
            row,
            require_trade_parity=require_trade_parity,
            require_htf_parity=require_htf_parity,
        ):
            would_pass += 1

    return {
        "total":         n,
        "status_counts": status_counts,
        "trade_parity": {
            "present": tp_present,
            "passed":  tp_passed,
            "rate":    (tp_passed / tp_present) if tp_present > 0 else None,
        },
        "htf_parity": {
            "present":  htf_present,
            "verdicts": htf_verdicts,
            "passing":  htf_passing,
            "rate":     (htf_passing / htf_present) if htf_present > 0 else None,
        },
        "hard_gate": {
            "would_pass":           would_pass,
            "rate":                 (would_pass / n) if n > 0 else None,
            "require_trade_parity": require_trade_parity,
            "require_htf_parity":   require_htf_parity,
        },
    }


# ─────────────────────────────────────────────────────────────────────
# Promotion-readiness verdict
# ─────────────────────────────────────────────────────────────────────
def evaluate_promotion_readiness(
    summary: Dict[str, Any],
    *,
    min_samples: Optional[int] = None,
    min_pass_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """Operator-facing verdict over a ``summarize_signoffs(...)``
    summary. Vocabulary:

      * ``PROMOTABLE``           — enough samples AND pass-rate ≥ min
      * ``NEEDS_MORE_EVIDENCE``  — sample size below the configured
                                   minimum (NEEDS soak)
      * ``NOT_READY``            — samples sufficient BUT pass-rate
                                   below the configured threshold
      * ``UNCERTIFIED``          — no advisory fields present at all
                                   (P1.3 / P1.4 never ran)

    Returns
    -------
    dict
        ``{
            "verdict":         str,
            "rationale":       str,
            "min_samples":     int,
            "min_pass_rate":   float,
            "observed_pass_rate": float | None,
            "advisory_only":   True,
            "operator_authority": "final",
        }``
    """
    ms = min_samples if min_samples is not None else min_samples_default()
    mr = min_pass_rate if min_pass_rate is not None else min_pass_rate_default()

    total = int(summary.get("total") or 0)
    hard = summary.get("hard_gate") or {}
    rate = hard.get("rate")  # may be None on empty samples
    tp = summary.get("trade_parity") or {}
    htf = summary.get("htf_parity") or {}

    advisory_present = (
        int(tp.get("present") or 0) > 0
        or int(htf.get("present") or 0) > 0
    )

    if not advisory_present:
        return {
            "verdict":             "UNCERTIFIED",
            "rationale":           (
                f"No advisory parity fields present in {total} sign-offs. "
                "Set ENABLE_CBOT_TRADE_PARITY=true and "
                "ENABLE_HTF_PARITY_VALIDATION=true, then run sign-offs."
            ),
            "min_samples":         ms,
            "min_pass_rate":       mr,
            "observed_pass_rate":  rate,
            "advisory_only":       True,
            "operator_authority":  "final",
        }

    if total < ms:
        return {
            "verdict":             "NEEDS_MORE_EVIDENCE",
            "rationale":           (
                f"Sample size {total} < min_samples {ms}. Continue soak."
            ),
            "min_samples":         ms,
            "min_pass_rate":       mr,
            "observed_pass_rate":  rate,
            "advisory_only":       True,
            "operator_authority":  "final",
        }

    if rate is None or rate < mr:
        return {
            "verdict":             "NOT_READY",
            "rationale":           (
                f"Pass-rate {rate:.3f} < min_pass_rate {mr:.3f} across "
                f"{total} sign-offs. Diagnose divergent rows before "
                "promoting to hard gate."
                if rate is not None else
                f"Pass-rate undefined across {total} sign-offs."
            ),
            "min_samples":         ms,
            "min_pass_rate":       mr,
            "observed_pass_rate":  rate,
            "advisory_only":       True,
            "operator_authority":  "final",
        }

    return {
        "verdict":             "PROMOTABLE",
        "rationale":           (
            f"Pass-rate {rate:.3f} ≥ {mr:.3f} across {total} sign-offs. "
            "Hard-gate promotion is institutionally admissible — "
            "operator may flip ENABLE_TRADE_PARITY_HARD_GATE and/or "
            "ENABLE_HTF_PARITY_HARD_GATE and update is_passed() to "
            "delegate to would_pass_hard_gate()."
        ),
        "min_samples":         ms,
        "min_pass_rate":       mr,
        "observed_pass_rate":  rate,
        "advisory_only":       True,
        "operator_authority":  "final",
    }


# ─────────────────────────────────────────────────────────────────────
# Live aggregator (Mongo) — used by the latent endpoint
# ─────────────────────────────────────────────────────────────────────
async def certify_window(
    *,
    window_days: int = 30,
    require_trade_parity: Optional[bool] = None,
    require_htf_parity: Optional[bool] = None,
    min_samples: Optional[int] = None,
    min_pass_rate: Optional[float] = None,
    limit: int = 5000,
) -> Dict[str, Any]:
    """One-shot live aggregator. Reads ``cbot_parity_signoff`` over
    the last ``window_days`` days (or up to ``limit`` rows, whichever
    is smaller), computes the summary + verdict, and returns the
    institutional snapshot.

    The function reads ONLY. Never writes. Honest-refusal verdict on
    empty/unreachable collection: ``verdict="UNCERTIFIED"`` with a
    rationale that names the missing prerequisite.

    Parameters mirror ``summarize_signoffs`` / ``evaluate_promotion_readiness``.
    When ``require_trade_parity`` / ``require_htf_parity`` are
    ``None``, the function reads the current flag state — so the
    aggregator reflects what the hard gate WOULD look like under the
    operator's current activation intent.
    """
    rtp = (
        require_trade_parity
        if require_trade_parity is not None
        else is_hard_gate_trade_enabled()
    )
    rhf = (
        require_htf_parity
        if require_htf_parity is not None
        else is_hard_gate_htf_enabled()
    )

    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(days=max(1, int(window_days)))
    ).isoformat()
    limit = max(1, min(int(limit), 50000))

    rows: List[Dict[str, Any]] = []
    err: Optional[str] = None
    try:
        from engines.db import get_db
        db = get_db()
        cur = db[SIGNOFF_COLL].find(
            {"signed_at": {"$gte": cutoff_iso}},
            {"_id": 0},
        ).sort("signed_at", -1).limit(limit)
        rows = [d async for d in cur]
    except Exception as e:                                  # pragma: no cover
        logger.debug("[parity_certification] read failed: %s", e)
        err = str(e)[:300]

    summary = summarize_signoffs(
        rows,
        require_trade_parity=rtp,
        require_htf_parity=rhf,
    )
    verdict = evaluate_promotion_readiness(
        summary,
        min_samples=min_samples,
        min_pass_rate=min_pass_rate,
    )

    return {
        "window_days":         max(1, int(window_days)),
        "cutoff_signed_at":    cutoff_iso,
        "row_count":           len(rows),
        "summary":             summary,
        "verdict":             verdict,
        "flags_at_read_time": {
            "ENABLE_TRADE_PARITY_HARD_GATE": is_hard_gate_trade_enabled(),
            "ENABLE_HTF_PARITY_HARD_GATE":   is_hard_gate_htf_enabled(),
            "PARITY_CERTIFICATION_MIN_SAMPLES":   min_samples_default(),
            "PARITY_CERTIFICATION_MIN_PASS_RATE": min_pass_rate_default(),
        },
        "read_only":          True,
        "advisory_only":      True,
        "governance_authority": False,
        "operator_authority": "final",
        "dormant":            not (
            is_hard_gate_trade_enabled() or is_hard_gate_htf_enabled()
        ),
        "read_error":         err,
    }


__all__ = [
    "is_hard_gate_trade_enabled",
    "is_hard_gate_htf_enabled",
    "min_samples_default",
    "min_pass_rate_default",
    "would_pass_hard_gate",
    "summarize_signoffs",
    "evaluate_promotion_readiness",
    "certify_window",
]


# ── MB-10 — Export-time parity gate (opt-in, admin-overridable) ────
#
# `assert_pass(revision_id)` is consumed by the Master Bot cBot
# exporter to hard-block any export whose enabled members lack a
# PASSED parity sign-off. This is the primitive the
# `master_bot_export.export_master_bot()` flow consults; it does NOT
# replace `cbot_parity.is_passed(signoff)`.
#
# Default behaviour: the gate is **OPT-IN**. Set the env flag
# `MB_PARITY_GATE_ENABLED=1` (or pass `enforce=True` at the call site)
# to turn it on. When OFF, every call to `assert_pass` returns
# `{enforced: false, would_block: <bool>, …}` so operators can preview
# what a future activation would look like WITHOUT yet enforcing.
#
# Honest refusal: when the gate is ON and a member has NO sign-off,
# that counts as a FAILURE (verdict: "missing_signoff"). No
# fabrication.

PARITY_GATE_ENV = "MB_PARITY_GATE_ENABLED"


class ParityGateError(RuntimeError):
    """Raised by `assert_pass` when the parity gate is enforced AND
    at least one enabled member fails. Carries the structured
    verdict so the API layer can render it back to the operator."""

    def __init__(self, verdict: Dict[str, Any]):
        self.verdict = verdict
        passed   = verdict.get("passed_count", 0)
        failed   = verdict.get("failed_count", 0)
        missing  = verdict.get("missing_count", 0)
        total    = verdict.get("total_enabled", 0)
        super().__init__(
            f"parity gate blocked export: {failed} FAILED + {missing} MISSING / "
            f"{total} enabled members ({passed} PASSED). Operator override: "
            f"POST /api/master-bot/{{id}}/export?force_parity=true (admin)."
        )


def is_parity_gate_enabled() -> bool:
    """Env-driven activation. OFF by default."""
    return _truthy(PARITY_GATE_ENV)


async def assert_pass(
    revision_id: str,
    *,
    enforce: Optional[bool] = None,
) -> Dict[str, Any]:
    """Evaluate the parity status of every enabled member of a
    Master Bot revision. Returns a structured verdict:

        {
          "revision_id":   "...",
          "enforced":      True|False,        # whether this call would block
          "would_block":   True|False,        # the verdict's pass/fail
          "total_enabled": N,
          "passed_count":  N,                  # has PASSED sign-off
          "failed_count":  N,                  # has non-PASSED sign-off
          "missing_count": N,                  # has no sign-off at all
          "per_member": [
            { "strategy_hash": "...", "tier": "tier1",
              "verdict": "PASSED" | "FAILED" | "MISSING",
              "signed_at": "...", "fixtures_passed": N, "details": "..." },
            ...
          ],
          "checked_at":    "ISO",
          "policy":        "enforce_on_missing | advisory",
        }

    When `enforce=True` is passed (or `MB_PARITY_GATE_ENABLED=1` env)
    AND `would_block` is True, this function raises
    `ParityGateError(verdict)`. Otherwise it returns the verdict
    object so callers can decide.
    """
    # Late imports — avoid touching cbot_parity / master_bot_definition
    # at module-import time so the dormancy guarantee is preserved.
    from engines import cbot_parity as cp
    from engines import master_bot_definition as mbd

    revision = await mbd.get_definition(revision_id=revision_id)
    if not revision:
        raise ValueError("revision not found")

    payload = revision.get("payload") or {}
    per_member: List[Dict[str, Any]] = []
    passed = failed = missing = 0
    total_enabled = 0

    for tier in payload.get("tiers") or []:
        tk = tier.get("tier_key")
        for m in tier.get("members") or []:
            if not m.get("enabled"):
                continue
            total_enabled += 1
            h = m.get("strategy_hash")
            signoff = await cp.get_signoff(h) if h else None
            if signoff is None:
                missing += 1
                verdict = "MISSING"
                details = "no parity sign-off on record for this strategy"
                signed_at = None
                fixtures = 0
            elif cp.is_passed(signoff):
                passed += 1
                verdict = "PASSED"
                details = signoff.get("notes") or ""
                signed_at = signoff.get("signed_at")
                fixtures = int(signoff.get("fixtures_passed") or 0)
            else:
                failed += 1
                verdict = "FAILED"
                details = (
                    signoff.get("status") or "non-PASSED"
                ) + " : " + (signoff.get("notes") or "")
                signed_at = signoff.get("signed_at")
                fixtures = int(signoff.get("fixtures_passed") or 0)
            per_member.append({
                "strategy_hash": h, "tier": tk,
                "verdict":       verdict,
                "signed_at":     signed_at,
                "fixtures_passed": fixtures,
                "details":       details,
            })

    would_block = (failed + missing) > 0
    enforced = bool(enforce) if enforce is not None else is_parity_gate_enabled()

    verdict_doc = {
        "revision_id":   revision_id,
        "enforced":      enforced,
        "would_block":   would_block,
        "total_enabled": total_enabled,
        "passed_count":  passed,
        "failed_count":  failed,
        "missing_count": missing,
        "per_member":    per_member,
        "checked_at":    datetime.now(timezone.utc).isoformat(),
        "policy":        "enforce_on_missing" if enforced else "advisory",
    }

    if enforced and would_block:
        raise ParityGateError(verdict_doc)
    return verdict_doc
