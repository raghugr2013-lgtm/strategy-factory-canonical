"""ASF calibration snapshot — receiver-side builder.

For the 1-vCPU migration package, the source pod never ran the BI5
cert engine, so the package itself carries no calibration data. The
receiving pod synthesises its own snapshot (current `tick_validator`
version + post-R2 Step-0 density table + thresholds + ranker version)
and treats the import as zero-drift.

See `ASF_PACKAGE_V1_SPEC.md §9` and `ASF_BACKEND_ARCHITECTURE.md §3.4`.
"""
from __future__ import annotations

import logging

from engines.asf.schema import CalibrationSnapshot

logger = logging.getLogger(__name__)


# Receiver-pod canonical versions. Source of truth lives in the
# tick_validator / master_bot_ranker modules; we mirror the constants
# here as the snapshot manifest values. If those modules change the
# constants, this snapshot follows automatically via import.

def _current_tick_validator_version() -> str:
    try:
        from engines import tick_validator as tv
        v = getattr(tv, "VERSION", None) or getattr(tv, "EVALUATOR_VERSION", None)
        if v:
            return str(v)
    except Exception:
        pass
    # Post-R2 Step-0 Option A baseline.
    return "tick_validator@P0B-v2"


def _current_density_table() -> dict:
    try:
        from engines import tick_validator as tv
        dt = getattr(tv, "DENSITY_TABLE", None)
        if isinstance(dt, dict):
            return dict(dt)
    except Exception:
        pass
    return {}


def _current_ranker_version() -> str:
    try:
        from engines import master_bot_ranker as mr
        v = getattr(mr, "RANKER_VERSION", None) or getattr(mr, "VERSION", None)
        if v:
            return str(v)
    except Exception:
        pass
    return "master_bot_ranker@v1.1"


def build_receiver_snapshot(
    *,
    pass_threshold: float = 0.85,
    warn_threshold: float = 0.70,
) -> CalibrationSnapshot:
    """Materialise the calibration block from the receiving pod's
    live state. Pure read; no side effects."""
    return CalibrationSnapshot(
        tick_validator_version=_current_tick_validator_version(),
        density_table_snapshot=_current_density_table(),
        pass_threshold=pass_threshold,
        warn_threshold=warn_threshold,
        ranker_version=_current_ranker_version(),
    )


def compare_calibration(
    *,
    package: CalibrationSnapshot,
    receiver: CalibrationSnapshot,
) -> dict:
    """Compare a package's calibration to the receiver's. Returns a
    drift summary; empty drift_keys means clean import."""
    drift_keys = []
    if package.tick_validator_version != receiver.tick_validator_version:
        drift_keys.append("tick_validator_version")
    if package.ranker_version != receiver.ranker_version:
        drift_keys.append("ranker_version")
    if abs(package.pass_threshold - receiver.pass_threshold) > 1e-6:
        drift_keys.append("pass_threshold")
    if abs(package.warn_threshold - receiver.warn_threshold) > 1e-6:
        drift_keys.append("warn_threshold")
    return {
        "drift_detected": len(drift_keys) > 0,
        "drift_keys": drift_keys,
        "package_tick_validator": package.tick_validator_version,
        "receiver_tick_validator": receiver.tick_validator_version,
        "package_ranker_version": package.ranker_version,
        "receiver_ranker_version": receiver.ranker_version,
    }
