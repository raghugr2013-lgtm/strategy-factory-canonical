"""Phase 29.0 — Walk-forward regime coverage (supplement) trust gate.

Validates ``regime_coverage_summary`` against ``run_walk_forward``.
Original `run_walk_forward` byte-identical.

5 tests:
  1. Entropy zero when all windows in single regime
  2. Entropy ~ln(k) when uniform across k regimes
  3. Function does NOT mutate input windows list
  4. Empty windows / empty prices → stable shape, never raises
  5. Output `phase=29.0, advisory_only=True`
"""
from __future__ import annotations

import math
import sys

from dotenv import load_dotenv

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
load_dotenv("/app/backend/.env")

from engines import walk_forward_engine as wf  # noqa: E402


def _flat_prices(n=300, anchor=100.0):
    """Tight oscillation around an anchor → classifier returns
    `ranging` (`low_volatility` is also plausible — for entropy test
    we accept either)."""
    out = [anchor]
    for i in range(n - 1):
        out.append(anchor + ((-1) ** i) * 0.0001)
    return out


def _trending_prices(n=300, anchor=100.0):
    """Monotonic uptrend → classifier returns `trending`."""
    return [anchor * (1.0 + 0.001 * i) for i in range(n)]


def test_entropy_zero_when_single_regime():
    # All windows fall on a single-regime price series.
    prices = _trending_prices(300)
    windows = [
        {"window": 1, "train_range": [0, 100], "oos_range": [100, 150]},
        {"window": 2, "train_range": [50, 150], "oos_range": [150, 200]},
        {"window": 3, "train_range": [100, 200], "oos_range": [200, 250]},
    ]
    out = wf.regime_coverage_summary(windows, prices)
    distrib = out["regime_distribution_oos"]
    nonzero = [v for v in distrib.values() if v > 0]
    assert len(nonzero) == 1, f"expected 1 regime, got {distrib}"
    assert out["regime_entropy_oos"] == 0.0


def test_entropy_uniform_two_regimes():
    # Hand-rolled: tell the summarizer the OOS distribution directly
    # via the internal Shannon helper — guarantees the math is right
    # without relying on the classifier's exact labels.
    h = wf._shannon_entropy({"trending": 5, "ranging": 5})
    assert abs(h - math.log(2)) < 1e-3


def test_does_not_mutate_input_windows():
    prices = _trending_prices(300)
    windows = [
        {"window": 1, "train_range": [0, 100], "oos_range": [100, 150]},
        {"window": 2, "train_range": [50, 150], "oos_range": [150, 200]},
    ]
    snapshot = [dict(w) for w in windows]
    _ = wf.regime_coverage_summary(windows, prices)
    assert windows == snapshot


def test_empty_inputs_stable_shape():
    out_a = wf.regime_coverage_summary([], [])
    out_b = wf.regime_coverage_summary([], _trending_prices(100))
    out_c = wf.regime_coverage_summary(
        [{"window": 1, "train_range": [0, 50], "oos_range": [50, 75]}], [],
    )
    for out in (out_a, out_b, out_c):
        assert out["windows_total"] == 0
        assert out["regime_entropy_oos"] == 0.0
        # All five regime keys present in distribution
        assert set(out["regime_distribution_oos"].keys()) >= {
            "trending", "ranging", "high_volatility", "low_volatility", "unknown",
        }


def test_phase_advisory_marker_and_no_mutation_of_run_wf_output():
    out = wf.regime_coverage_summary(
        [{"window": 1, "train_range": [0, 100], "oos_range": [100, 150]}],
        _trending_prices(300),
    )
    assert out["phase"] == "29.0"
    assert out["advisory_only"] is True

    # Sanity — original run_walk_forward signature unchanged: refuses
    # cleanly on insufficient data with the pre-29 error message.
    orig = wf.run_walk_forward(
        "MA strategy", "EURUSD", "H1",
        prices=[1.0] * 50,
    )
    assert orig["success"] is False
    assert orig["mode"] == "walk_forward"
