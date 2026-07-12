"""Unit tests for engines.calibration_framework (latent — Phase 4 P4.16)."""
from __future__ import annotations

import pytest

from engines import calibration_framework as cf

pytestmark = pytest.mark.latent


# ─────────────────────────────────────────────────────────────────────
# apply_calibration — identity-transform contract
# ─────────────────────────────────────────────────────────────────────

def test_apply_returns_raw_when_flag_off():
    res = cf.apply_calibration(0.42, table=None)
    assert res["raw"] == pytest.approx(0.42)
    assert res["calibrated"] == pytest.approx(0.42)
    assert res["source"] == "identity_flag_off"


def test_apply_clamps_to_unit_interval():
    res = cf.apply_calibration(1.5, table=None)
    assert res["raw"] == 1.0
    res = cf.apply_calibration(-0.1, table=None)
    assert res["raw"] == 0.0


def test_apply_sparse_bin_returns_raw(monkeypatch):
    # Force the feature flag ON via env override.
    monkeypatch.setenv("ENABLE_CALIBRATION", "true")
    # Reload the flag module mid-test by re-importing — but flag()
    # always reads os.environ so this is enough.
    table = {
        "bins": [
            {"bin_lo": 0.0, "bin_hi": 0.5, "pass_rate": 0.5,
             "is_calibrated": False, "n": 3},
            {"bin_lo": 0.5, "bin_hi": 1.0, "pass_rate": 0.8,
             "is_calibrated": True, "n": 200},
        ]
    }
    sparse = cf.apply_calibration(0.25, table=table)
    assert sparse["source"] == "identity_sparse_bin"
    assert sparse["calibrated"] == pytest.approx(0.25)


def test_apply_calibrated_bin_returns_table_value(monkeypatch):
    monkeypatch.setenv("ENABLE_CALIBRATION", "true")
    table = {
        "bins": [
            {"bin_lo": 0.0, "bin_hi": 0.5, "pass_rate": 0.5,
             "is_calibrated": False, "n": 3},
            {"bin_lo": 0.5, "bin_hi": 1.0, "pass_rate": 0.8,
             "is_calibrated": True, "n": 200},
        ]
    }
    calibrated = cf.apply_calibration(0.75, table=table)
    assert calibrated["source"] == "calibrated"
    assert calibrated["calibrated"] == pytest.approx(0.8)


def test_apply_when_flag_off_with_table_present_still_identity(monkeypatch):
    monkeypatch.delenv("ENABLE_CALIBRATION", raising=False)
    table = {
        "bins": [
            {"bin_lo": 0.0, "bin_hi": 1.0, "pass_rate": 0.9,
             "is_calibrated": True, "n": 500},
        ]
    }
    res = cf.apply_calibration(0.3, table=table)
    # Flag off → identity transform even when table would calibrate.
    assert res["source"] == "identity_flag_off"
    assert res["calibrated"] == pytest.approx(0.3)
