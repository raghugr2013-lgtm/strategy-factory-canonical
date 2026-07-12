"""BI5 R2 / B-5 — Master Bot ranker BI5 signal integration tests.

Covers:

1. PASS-cert candidate outranks an identical no-cert candidate.
2. WARN-cert candidate outranks an identical no-cert candidate but
   ranks below an identical PASS-cert candidate.
3. With both BI5 weights set to 0.0, ranking with or without a cert
   is identical (backward-compatibility proof — proves the additive
   nature of the change).
4. Out-of-range slippage values are clamped at scoring time.
5. Unknown / "early-fail" verdicts score 0.0.

All tests exercise the pure `_compute_candidate_score` function — they
do not require Mongo. The full `fetch_candidate_pool` end-to-end is
covered separately by the bigger ranker integration test suite.
"""
from __future__ import annotations

import pytest

from engines.master_bot_ranker import (
    DEFAULT_WEIGHTS,
    _compute_candidate_score,
    _norm_bi5_verdict,
)


# Common evidence row used by all PASS-vs-no-cert comparisons.
_BASE = dict(
    deploy_score=80.0,        # 0.80 normalised
    pass_probability=70.0,    # 0.70 normalised
)


def _score(extra: dict, weights: dict = None) -> float:
    w = weights or DEFAULT_WEIGHTS
    return _compute_candidate_score(w, **_BASE, **extra)["candidate_score"]


def test_pass_cert_outranks_no_cert():
    pass_score = _score({"bi5_cert_verdict": "PASS", "bi5_slippage_score": 0.9})
    no_score   = _score({"bi5_cert_verdict": None,  "bi5_slippage_score": None})
    assert pass_score > no_score, (pass_score, no_score)


def test_warn_cert_outranks_no_cert_but_below_pass():
    pass_score = _score({"bi5_cert_verdict": "PASS", "bi5_slippage_score": 0.9})
    warn_score = _score({"bi5_cert_verdict": "WARN", "bi5_slippage_score": 0.9})
    no_score   = _score({"bi5_cert_verdict": None,  "bi5_slippage_score": None})
    assert warn_score > no_score
    assert warn_score < pass_score


def test_fail_cert_scores_as_no_cert():
    fail_score = _score({"bi5_cert_verdict": "FAIL", "bi5_slippage_score": 0.0})
    no_score   = _score({"bi5_cert_verdict": None,  "bi5_slippage_score": None})
    # Equal because FAIL → 0 and absent slippage → 0; both signals contribute 0.
    assert fail_score == pytest.approx(no_score)


def test_unknown_verdict_treated_as_zero():
    weird_score = _score({"bi5_cert_verdict": "PARTIAL", "bi5_slippage_score": None})
    no_score    = _score({"bi5_cert_verdict": None,      "bi5_slippage_score": None})
    assert weird_score == pytest.approx(no_score)


def test_zero_weight_backwards_compat():
    """With BI5 weights = 0, cert presence must not move the score."""
    zero_w = {
        **DEFAULT_WEIGHTS,
        "bi5_cert_verdict": 0.0,
        "bi5_slippage_score": 0.0,
        # also zero the future signals so the sum is just deploy+pp.
    }
    with_cert    = _score({"bi5_cert_verdict": "PASS", "bi5_slippage_score": 1.0},
                          weights=zero_w)
    without_cert = _score({"bi5_cert_verdict": None,  "bi5_slippage_score": None},
                          weights=zero_w)
    assert with_cert == pytest.approx(without_cert)


def test_slippage_value_clamped():
    """Out-of-range slippage_score values cannot corrupt the score."""
    big   = _score({"bi5_cert_verdict": "PASS", "bi5_slippage_score": 5.0})   # >1
    legit = _score({"bi5_cert_verdict": "PASS", "bi5_slippage_score": 1.0})
    assert big == pytest.approx(legit)


def test_norm_bi5_verdict_table():
    assert _norm_bi5_verdict("PASS") == 1.0
    assert _norm_bi5_verdict("pass") == 1.0
    assert _norm_bi5_verdict("WARN") == 0.5
    assert _norm_bi5_verdict("FAIL") == 0.0
    assert _norm_bi5_verdict(None) == 0.0
    assert _norm_bi5_verdict("") == 0.0
    assert _norm_bi5_verdict("PARTIAL") == 0.0


def test_default_weights_sum_to_one_for_active_signals():
    """Σ of active (non-future) weights must equal 1.0 exactly."""
    active = sum(
        v for k, v in DEFAULT_WEIGHTS.items()
        if k not in ("risk_of_ruin", "calibration", "regime_fitness")
    )
    assert active == pytest.approx(1.0)


def test_bi5_weight_split_matches_plan():
    """The R2 spec calls for 0.07 + 0.03 across the BI5 signals."""
    assert DEFAULT_WEIGHTS["bi5_cert_verdict"]   == pytest.approx(0.07)
    assert DEFAULT_WEIGHTS["bi5_slippage_score"] == pytest.approx(0.03)
    assert DEFAULT_WEIGHTS["deploy_score"]       == pytest.approx(0.50)
    assert DEFAULT_WEIGHTS["pass_probability"]   == pytest.approx(0.40)
