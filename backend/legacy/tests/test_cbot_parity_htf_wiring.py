"""G-2.b HTF-parity wiring tests for ``engines.cbot_parity.sign_off_parity``.

Constraint envelope (operator-imposed):
    * No certification math changes
    * No threshold changes
    * No density table changes
    * No verdict overrides
    * Advisory only — must NEVER alter the primary ``status`` verdict

These tests cover the five-case matrix proposed in
``H1_IMPLEMENTATION_AND_G2B_PROPOSAL.md`` §B.4:

    1. flag OFF  → no htf_parity_* fields on the persisted signoff
    2. flag ON, HTF-bearing IR  → htf_parity_verdict ∈ valid set
    3. flag ON, non-HTF IR      → htf_parity_verdict == "NOT_APPLICABLE"
    4. flag ON, validator raises → status untouched, htf_parity_error set
    5. audit row surfaces htf_parity_verdict

All tests stub ``engines.htf_parity.validate_htf_parity`` at the
module boundary so they stay hermetic and fast. The native interpreter
path is exercised in ``test_htf_parity.py``.
"""
from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

import pytest


# -----------------------------------------------------------------------------
# Shared fixture — a minimal sign-off invocation built around mocks for every
# heavy seam in ``sign_off_parity``. This isolates the G-2.b branch and lets
# each test assert on the persisted outcome ``out`` directly.
# -----------------------------------------------------------------------------
async def _run_signoff_with_stubs(
    *,
    htf_flag: bool,
    htf_report: Dict[str, Any] = None,
    raise_in_htf: bool = False,
) -> Dict[str, Any]:
    """Run ``sign_off_parity`` against a stub IR/fixture/db. Returns the
    sign-off doc that would have been persisted (no real Mongo writes).

    Heavy in-function imports (`cbot_engine.ir_parity_simulator`,
    `cbot_engine.ir_transpiler`) are patched at their source modules
    so the test exercises only the G-2.b wiring branch.
    """
    from engines import cbot_parity

    # Stub IR + fixture
    stub_ir = {
        "version": "v1",
        "indicators": [], "operators": [],
        "metadata": {"primary_timeframe": "H1"},
    }
    stub_fixture_tuple = (
        [1.0, 1.01, 1.02, 1.03] * 30,  # closes
        [1.01, 1.02, 1.03, 1.04] * 30, # highs
        [0.99, 1.00, 1.01, 1.02] * 30, # lows
        list(range(120)),               # timestamps
    )
    stub_signals = [{"action": "long"} for _ in range(50)]
    stub_sim = {
        "signals": stub_signals,
        "operators_used": ["GT", "LT"],
        "indicator_kinds_used": ["EMA"],
        "sl_kind": "atr_multiple", "tp_kind": "atr_multiple",
        "htf_present": False,
    }
    stub_artefact = {
        "csharp": "/* stubbed */",
        "ir_version": "v1",
        "strategy_hash": "stub_hash",
        "bot_name": "StubBot",
        "htf_parity_mode": "EXACT",
    }

    captured: Dict[str, Any] = {}

    async def fake_persist(db, doc):
        captured["signoff"] = dict(doc)

    async def fake_audit(db, sh, outcome, *, triggered_by):
        captured["audit"] = dict(outcome)

    async def fake_find_ir(sh):
        return stub_ir

    async def fake_load_fixture(pair, tf, *, n_bars=None):
        return stub_fixture_tuple

    if raise_in_htf:
        def fake_validate(*args, **kwargs):
            raise RuntimeError("synthetic validator failure")
    else:
        default_report = htf_report or {
            "verdict": "NOT_APPLICABLE",
            "htf_present": False,
            "divergence_pct": 0.0,
            "tolerance_pct": 5.0,
            "compared_bars": 0,
            "diverging_bars": 0,
            "first_divergence": None,
        }
        def fake_validate(*args, **kwargs):
            return default_report

    import cbot_engine.ir_parity_simulator as ips
    import cbot_engine.ir_transpiler as ipt
    import engines.htf_parity as hp

    with patch.object(cbot_parity, "_find_ir_for_strategy", fake_find_ir), \
         patch.object(cbot_parity, "_load_price_fixture", fake_load_fixture), \
         patch.object(cbot_parity, "_persist_signoff", fake_persist), \
         patch.object(cbot_parity, "_audit", fake_audit), \
         patch.object(cbot_parity, "_htf_parity_enabled",
                      lambda: htf_flag), \
         patch.object(cbot_parity, "_trade_parity_enabled",
                      lambda: False), \
         patch.object(ips, "simulate_cbot_signals",
                      lambda ir, **kw: stub_sim), \
         patch.object(ipt, "transpile_ir_to_csharp",
                      lambda ir, **kw: stub_artefact), \
         patch.object(hp, "validate_htf_parity", fake_validate):
        # The validator is also resolved via the `from engines.htf_parity
        # import validate_htf_parity` line inside the G-2.b try-block. The
        # patch on `hp.validate_htf_parity` covers that import path.
        result = await cbot_parity.sign_off_parity(
            strategy_hash="stub_hash",
            pair_override="EURUSD",
            timeframe_override="H1",
        )

    return {"result": result, "captured": captured}


# -----------------------------------------------------------------------------
# Test 1 — Flag OFF: no htf_parity_* fields on the persisted signoff
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signoff_omits_htf_when_flag_off():
    """With ``ENABLE_HTF_PARITY_VALIDATION`` off (default), the
    persisted signoff doc has NO htf_parity_* advisory fields —
    preserves the pre-G-2.b schema for downstream consumers."""
    out = await _run_signoff_with_stubs(htf_flag=False)
    signoff = out["captured"]["signoff"]
    assert "htf_parity_verdict" not in signoff
    assert "htf_divergence_pct" not in signoff
    assert "htf_parity_advisory_only" not in signoff
    # Sanity — primary status unchanged
    assert signoff["status"] == "PASSED"


# -----------------------------------------------------------------------------
# Test 2 — Flag ON, HTF-bearing IR: signoff carries verdict + fields
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signoff_attaches_htf_verdict_when_flag_on():
    """With the flag on and a non-error validator result, the persisted
    signoff doc carries the five proposed advisory fields and an
    advisory-only marker."""
    htf_report = {
        "verdict": "WITHIN_TOLERANCE",
        "htf_present": True,
        "divergence_pct": 2.4,
        "tolerance_pct": 5.0,
        "compared_bars": 100,
        "diverging_bars": 2,
        "first_divergence": 17,
    }
    out = await _run_signoff_with_stubs(htf_flag=True, htf_report=htf_report)
    signoff = out["captured"]["signoff"]
    assert signoff["htf_parity_verdict"] == "WITHIN_TOLERANCE"
    assert signoff["htf_divergence_pct"] == 2.4
    assert signoff["htf_parity_tolerance_pct"] == 5.0
    assert signoff["htf_parity_compared_bars"] == 100
    assert signoff["htf_parity_diverging_bars"] == 2
    assert signoff["htf_parity_first_divergence"] == 17
    assert signoff["htf_parity_advisory_only"] is True
    # Primary status unchanged (advisory-only contract)
    assert signoff["status"] == "PASSED"


# -----------------------------------------------------------------------------
# Test 3 — Flag ON, non-HTF IR: NOT_APPLICABLE
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signoff_htf_verdict_not_applicable_when_no_htf():
    """For an IR with no HTF indicator, the engine returns
    NOT_APPLICABLE. The wiring must persist that verdict unchanged."""
    htf_report = {
        "verdict": "NOT_APPLICABLE",
        "htf_present": False,
        "divergence_pct": 0.0,
        "tolerance_pct": 5.0,
        "compared_bars": 0,
        "diverging_bars": 0,
        "first_divergence": None,
    }
    out = await _run_signoff_with_stubs(htf_flag=True, htf_report=htf_report)
    signoff = out["captured"]["signoff"]
    assert signoff["htf_parity_verdict"] == "NOT_APPLICABLE"
    assert signoff["htf_parity_advisory_only"] is True


# -----------------------------------------------------------------------------
# Test 4 — Flag ON, validator raises: status untouched, error captured
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signoff_htf_error_does_not_alter_signal_verdict():
    """An exception inside validate_htf_parity must NOT alter the
    primary ``status`` field. Mirrors the existing P1.3 advisory
    error-handling pattern."""
    out = await _run_signoff_with_stubs(htf_flag=True, raise_in_htf=True)
    signoff = out["captured"]["signoff"]
    # Primary status survives the advisory failure
    assert signoff["status"] == "PASSED"
    # Failure captured advisory-side
    assert signoff["htf_parity_verdict"] == "ERROR"
    assert "synthetic validator failure" in signoff["htf_parity_error"]
    assert signoff["htf_parity_advisory_only"] is True


# -----------------------------------------------------------------------------
# Test 5 — Audit row surfaces htf_parity_verdict
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signoff_audit_row_surfaces_htf_verdict():
    """The audit insert receives htf_parity_verdict so forensic
    queries can see the verdict without re-reading the signoff doc."""
    htf_report = {
        "verdict": "EXACT",
        "htf_present": True,
        "divergence_pct": 0.0,
        "tolerance_pct": 5.0,
        "compared_bars": 100,
        "diverging_bars": 0,
        "first_divergence": None,
    }
    out = await _run_signoff_with_stubs(htf_flag=True, htf_report=htf_report)
    audit = out["captured"]["audit"]
    # The captured outcome is what flows into _audit
    assert audit.get("htf_parity_verdict") == "EXACT"
    assert audit.get("htf_divergence_pct") == 0.0
    assert audit.get("htf_parity_compared_bars") == 100
