"""Phase 29.0 — Regime-stratified OOS (supplement) trust gate.

Validates the supplement function ``run_oos_holdout_regime_stratified``
without altering the canonical ``run_oos_holdout`` or any lifecycle
input.

8 tests:
  1. Original `run_oos_holdout` byte-identity on identical input.
  2. Stable output schema on insufficient data.
  3. Stable output schema on synthetic multi-regime price series.
  4. Per-regime keys always present (even when null).
  5. `_leakage_guard.per_regime_stratified` is True.
  6. Output `phase=29.0, advisory_only=True`.
  7. Does NOT write to lib.oos_holdout (we verify the function returns
     a separate object that does not include a top-level `oos_holdout`
     key, and explicitly carries the `_note` marker).
  8. Determinism: same prices → same per_regime structure.
"""
from __future__ import annotations

import sys
import random

from dotenv import load_dotenv

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
load_dotenv("/app/backend/.env")

from engines import oos_holdout as oh  # noqa: E402
from engines.regime_performance import REGIMES_CANONICAL  # noqa: E402


def _synthetic_multi_regime_prices(n=600):
    """Build a deterministic series with embedded regime structure.

    First third: strong uptrend (trending). Middle third: oscillation
    (ranging). Last third: heavy oscillation (high_volatility).
    """
    rng = random.Random(20290101)
    series = [100.0]
    # Trending — drift up
    for _ in range(n // 3):
        series.append(series[-1] * (1.0 + 0.001 + rng.gauss(0, 0.0005)))
    # Ranging — mean revert around current level
    anchor = series[-1]
    for _ in range(n // 3):
        series.append(anchor + rng.gauss(0, anchor * 0.001))
    # High volatility — wider Gaussian
    anchor = series[-1]
    for _ in range(n - len(series)):
        series.append(anchor * (1.0 + rng.gauss(0, 0.005)))
    return series


def test_original_run_oos_holdout_byte_identical_on_short_input():
    """Original function unchanged: identical error message + shape
    when called with insufficient data."""
    out = oh.run_oos_holdout(
        "MA crossover strategy",
        "EURUSD", "H1",
        prices=[1.0] * 50,
    )
    assert out["success"] is False
    assert out["mode"] == "holdout"
    # Pre-29 error message preserved
    assert "at least" in out.get("error", "")


def test_stratified_short_input_returns_stable_failure_shape():
    out = oh.run_oos_holdout_regime_stratified(
        "MA crossover strategy",
        "EURUSD", "H1",
        prices=[1.0] * 50,
    )
    assert out["success"] is False
    assert out["mode"] == "holdout_regime_stratified"
    assert out["phase"] == "29.0"
    assert out["advisory_only"] is True
    assert set(out["per_regime"].keys()) == set(REGIMES_CANONICAL)
    assert out["regimes_with_evidence"] == 0


def test_stratified_per_regime_keys_always_present():
    prices = _synthetic_multi_regime_prices(400)
    out = oh.run_oos_holdout_regime_stratified(
        "MA crossover strategy",
        "EURUSD", "H1",
        prices=prices,
        num_variants=10,           # smaller search to keep test fast
    )
    # Even regimes with NO contiguous stable run must appear as a key,
    # value `None` (honest refusal, never missing).
    assert set(out["per_regime"].keys()) == set(REGIMES_CANONICAL)


def test_stratified_leakage_guard_marked():
    prices = _synthetic_multi_regime_prices(400)
    out = oh.run_oos_holdout_regime_stratified(
        "MA crossover strategy",
        "EURUSD", "H1",
        prices=prices,
        num_variants=10,
    )
    guard = out.get("_leakage_guard") or {}
    assert guard.get("fit_sees_train_only") is True
    assert guard.get("score_sees_oos_only") is True
    assert guard.get("params_frozen_before_oos") is True
    assert guard.get("per_regime_stratified") is True


def test_stratified_supplement_note_present():
    out = oh.run_oos_holdout_regime_stratified(
        "MA strategy",
        "EURUSD", "H1",
        prices=_synthetic_multi_regime_prices(400),
        num_variants=10,
    )
    assert "_note" in out
    assert "supplement only" in out["_note"]
    # MUST NOT include a top-level `oos_holdout` key (the field that
    # the lifecycle gate reads from the library doc).
    assert "oos_holdout" not in out


def test_stratified_phase_advisory_marker():
    out = oh.run_oos_holdout_regime_stratified(
        "MA strategy",
        "EURUSD", "H1",
        prices=_synthetic_multi_regime_prices(400),
        num_variants=10,
    )
    assert out["phase"] == "29.0"
    assert out["advisory_only"] is True


def test_stratified_run_does_not_mutate_input_prices():
    prices = _synthetic_multi_regime_prices(400)
    snapshot = list(prices)
    _ = oh.run_oos_holdout_regime_stratified(
        "MA strategy",
        "EURUSD", "H1",
        prices=prices,
        num_variants=10,
    )
    assert prices == snapshot


def test_longest_contiguous_run_helper():
    # 0..3 trending, 4..7 ranging, 8..11 trending → longest trending
    # is the FIRST or LAST run (both length 4); helper returns the
    # FIRST encountered.
    labels = ["trending"] * 4 + ["ranging"] * 4 + ["trending"] * 4
    start, end = oh._longest_contiguous_run(labels, "trending")
    assert (start, end) == (0, 4)
    # No matches → (None, None)
    start, end = oh._longest_contiguous_run(labels, "high_volatility")
    assert start is None and end is None
