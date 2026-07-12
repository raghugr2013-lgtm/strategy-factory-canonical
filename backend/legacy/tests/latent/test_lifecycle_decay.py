"""Unit tests for engines.lifecycle_decay (latent — Phase 4 P4.15)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from engines import lifecycle_decay as decay

pytestmark = pytest.mark.latent


def _iso_n_days_ago(days: float) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).isoformat()


# ─────────────────────────────────────────────────────────────────────
# Penalty math
# ─────────────────────────────────────────────────────────────────────

def test_penalty_missing_revalidation_is_zero():
    assert decay.compute_aging_penalty(None) == 0.0
    assert decay.compute_aging_penalty("") == 0.0


def test_penalty_invalid_iso_is_zero():
    assert decay.compute_aging_penalty("not-a-date") == 0.0


def test_penalty_fresh_is_near_zero():
    p = decay.compute_aging_penalty(_iso_n_days_ago(0.1), tau_days=60.0)
    assert 0.0 <= p < 0.01


def test_penalty_at_tau_is_approximately_one_minus_e_inverse():
    # 1 - exp(-1) ≈ 0.6321
    p = decay.compute_aging_penalty(_iso_n_days_ago(60), tau_days=60.0)
    assert 0.62 < p < 0.64


def test_penalty_far_past_approaches_one():
    p = decay.compute_aging_penalty(_iso_n_days_ago(365), tau_days=60.0)
    assert p > 0.99


def test_penalty_future_timestamp_is_zero():
    future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    assert decay.compute_aging_penalty(future) == 0.0


# ─────────────────────────────────────────────────────────────────────
# Staleness gate (P4.15 demotion criterion mirror)
# ─────────────────────────────────────────────────────────────────────

def test_is_stale_requires_both_threshold_and_age():
    # Penalty above threshold BUT not old enough → not stale.
    assert not decay.is_stale(0.7, _iso_n_days_ago(30), min_age_days=90.0)
    # Penalty BELOW threshold even if very old → not stale.
    assert not decay.is_stale(0.4, _iso_n_days_ago(200), min_age_days=90.0)
    # Both conditions met → stale.
    assert decay.is_stale(0.7, _iso_n_days_ago(200), min_age_days=90.0)


def test_is_stale_handles_missing_revalidation():
    assert not decay.is_stale(0.9, None)


# ─────────────────────────────────────────────────────────────────────
# Activation contract
# ─────────────────────────────────────────────────────────────────────

def test_default_dormant():
    """CRITICAL — must remain False until operator explicitly enables."""
    assert decay.is_active() is False
