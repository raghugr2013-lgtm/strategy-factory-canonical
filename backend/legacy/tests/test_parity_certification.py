"""
P1.5 — Tests for engines.parity_certification (dormant hard-gate primitive).

Five tiers, mirroring the discipline used by P0.4 / P1.2 / P1.4 / P1.6:

  Tier 1 — Dormancy contract: no engine consumes the module.
  Tier 2 — Pure helpers (flag accessors + tuning defaults).
  Tier 3 — would_pass_hard_gate predicate (signal-only vs trade vs HTF).
  Tier 4 — Aggregator + promotion-readiness verdict bands.
  Tier 5 — Feature-flag manifest integration.

Discipline:
  * Pure tests; no Mongo writes, no LLM, no network.
  * Synthetic sign-off documents only — deterministic, repeatable.
  * The dormancy test (Tier 1) is the institutional gate that
    prevents drive-by activation.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import pytest


def _passed_signal_only() -> Dict[str, Any]:
    return {"strategy_hash": "abc", "status": "PASSED"}


def _passed_with_trade() -> Dict[str, Any]:
    return {
        "strategy_hash": "abc",
        "status": "PASSED",
        "trade_parity_passed": True,
    }


def _passed_with_htf_exact() -> Dict[str, Any]:
    return {
        "strategy_hash": "abc",
        "status": "PASSED",
        "htf_parity_verdict": "EXACT",
    }


def _passed_full() -> Dict[str, Any]:
    return {
        "strategy_hash": "abc",
        "status": "PASSED",
        "trade_parity_passed": True,
        "htf_parity_verdict": "WITHIN_TOLERANCE",
    }


def _failed_signal() -> Dict[str, Any]:
    return {"strategy_hash": "x", "status": "UNSUPPORTED"}


def _passed_signal_failing_trade() -> Dict[str, Any]:
    return {
        "strategy_hash": "y",
        "status": "PASSED",
        "trade_parity_passed": False,
        "htf_parity_verdict": "EXACT",
    }


def _passed_signal_divergent_htf() -> Dict[str, Any]:
    return {
        "strategy_hash": "z",
        "status": "PASSED",
        "trade_parity_passed": True,
        "htf_parity_verdict": "DIVERGENT",
    }


# ─────────────────────────────────────────────────────────────────────
# Tier 1 — Dormancy contract
# ─────────────────────────────────────────────────────────────────────
class TestDormancy:
    """Institutional invariant: no module under ``backend/engines/``
    may import ``engines.parity_certification`` until a separately-
    reviewed wiring pass updates the whitelist below.
    """

    _AUTHORIZED_IMPORTERS: set = set()  # empty: P1.5 is fully dormant

    def test_no_engine_consumer(self):
        backend = Path(__file__).resolve().parent.parent
        engines_dir = backend / "engines"
        offenders: List[str] = []
        for py in engines_dir.rglob("*.py"):
            if py.name == "parity_certification.py":
                continue
            try:
                src = py.read_text(encoding="utf-8")
            except Exception:
                continue
            for line in src.splitlines():
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if (
                    "from engines.parity_certification" in stripped
                    or "import engines.parity_certification" in stripped
                ):
                    rel = str(py.relative_to(backend))
                    if rel not in self._AUTHORIZED_IMPORTERS:
                        offenders.append(rel)
                        break
        assert not offenders, (
            f"P1.5 dormancy violated — engines/ imports parity_certification "
            f"in: {offenders}. Update _AUTHORIZED_IMPORTERS only via a "
            "reviewed wiring pass."
        )

    def test_cbot_parity_does_not_consult_module(self):
        """``engines.cbot_parity.is_passed`` MUST remain the production
        semantic; it MUST NOT delegate to ``would_pass_hard_gate``
        until P1.5 is wired in.
        """
        from engines import cbot_parity
        src = Path(cbot_parity.__file__).read_text(encoding="utf-8")
        assert "parity_certification" not in src, (
            "engines.cbot_parity imports parity_certification — that is "
            "the P1.5 wiring change and must update the whitelist."
        )


class TestFlagAccessors:
    def test_defaults_off(self):
        for var in (
            "ENABLE_TRADE_PARITY_HARD_GATE",
            "ENABLE_HTF_PARITY_HARD_GATE",
        ):
            os.environ.pop(var, None)
        from engines.parity_certification import (
            is_hard_gate_trade_enabled, is_hard_gate_htf_enabled,
        )
        assert is_hard_gate_trade_enabled() is False
        assert is_hard_gate_htf_enabled() is False

    def test_truthy_values(self):
        from engines.parity_certification import (
            is_hard_gate_trade_enabled, is_hard_gate_htf_enabled,
        )
        for v in ("true", "1", "yes", "on", "TRUE"):
            os.environ["ENABLE_TRADE_PARITY_HARD_GATE"] = v
            try:
                assert is_hard_gate_trade_enabled() is True
            finally:
                os.environ.pop("ENABLE_TRADE_PARITY_HARD_GATE", None)
            os.environ["ENABLE_HTF_PARITY_HARD_GATE"] = v
            try:
                assert is_hard_gate_htf_enabled() is True
            finally:
                os.environ.pop("ENABLE_HTF_PARITY_HARD_GATE", None)

    def test_tuning_defaults(self):
        from engines.parity_certification import (
            min_samples_default, min_pass_rate_default,
        )
        os.environ.pop("PARITY_CERTIFICATION_MIN_SAMPLES", None)
        os.environ.pop("PARITY_CERTIFICATION_MIN_PASS_RATE", None)
        assert min_samples_default() == 30
        assert abs(min_pass_rate_default() - 0.95) < 1e-9

    def test_tuning_malformed_falls_back(self):
        from engines.parity_certification import (
            min_samples_default, min_pass_rate_default,
        )
        os.environ["PARITY_CERTIFICATION_MIN_SAMPLES"] = "not-an-int"
        os.environ["PARITY_CERTIFICATION_MIN_PASS_RATE"] = "garbage"
        try:
            assert min_samples_default() == 30
            assert abs(min_pass_rate_default() - 0.95) < 1e-9
        finally:
            os.environ.pop("PARITY_CERTIFICATION_MIN_SAMPLES", None)
            os.environ.pop("PARITY_CERTIFICATION_MIN_PASS_RATE", None)

    def test_pass_rate_clamped(self):
        from engines.parity_certification import min_pass_rate_default
        os.environ["PARITY_CERTIFICATION_MIN_PASS_RATE"] = "2.5"
        try:
            assert min_pass_rate_default() == 1.0
        finally:
            os.environ.pop("PARITY_CERTIFICATION_MIN_PASS_RATE", None)
        os.environ["PARITY_CERTIFICATION_MIN_PASS_RATE"] = "-1.0"
        try:
            assert min_pass_rate_default() == 0.0
        finally:
            os.environ.pop("PARITY_CERTIFICATION_MIN_PASS_RATE", None)


# ─────────────────────────────────────────────────────────────────────
# Tier 3 — would_pass_hard_gate predicate
# ─────────────────────────────────────────────────────────────────────
class TestHardGatePredicate:
    def test_none_signoff_returns_false(self):
        from engines.parity_certification import would_pass_hard_gate
        assert would_pass_hard_gate(None) is False

    def test_signal_only_default_semantic_matches_is_passed(self):
        """Default ``require_*=False`` makes the predicate identical
        to today's ``engines.cbot_parity.is_passed`` semantic."""
        from engines.parity_certification import would_pass_hard_gate
        assert would_pass_hard_gate(_passed_signal_only()) is True
        assert would_pass_hard_gate(_failed_signal()) is False

    def test_trade_parity_required_honest_refusal_on_missing(self):
        from engines.parity_certification import would_pass_hard_gate
        # Sign-off without the advisory field — honest refusal.
        assert would_pass_hard_gate(
            _passed_signal_only(), require_trade_parity=True,
        ) is False
        # Sign-off WITH the advisory field, passing.
        assert would_pass_hard_gate(
            _passed_with_trade(), require_trade_parity=True,
        ) is True
        # Sign-off WITH the advisory field, failing.
        assert would_pass_hard_gate(
            _passed_signal_failing_trade(), require_trade_parity=True,
        ) is False

    def test_htf_parity_required_band_semantics(self):
        from engines.parity_certification import would_pass_hard_gate
        # EXACT and WITHIN_TOLERANCE both pass. NOT_APPLICABLE is
        # explicitly in the passing band (an IR with no HTF use is
        # trivially HTF-correct).
        for verdict in ("EXACT", "WITHIN_TOLERANCE", "NOT_APPLICABLE"):
            r = dict(_passed_with_htf_exact())
            r["htf_parity_verdict"] = verdict
            assert would_pass_hard_gate(r, require_htf_parity=True) is True
        # DIVERGENT and ERROR both fail.
        for verdict in ("DIVERGENT", "ERROR"):
            r = dict(_passed_with_htf_exact())
            r["htf_parity_verdict"] = verdict
            assert would_pass_hard_gate(r, require_htf_parity=True) is False
        # Missing field — honest refusal.
        assert would_pass_hard_gate(
            _passed_signal_only(), require_htf_parity=True,
        ) is False

    def test_both_dimensions_required(self):
        from engines.parity_certification import would_pass_hard_gate
        # All three dimensions OK.
        assert would_pass_hard_gate(
            _passed_full(),
            require_trade_parity=True,
            require_htf_parity=True,
        ) is True
        # Trade-parity fails → False.
        assert would_pass_hard_gate(
            _passed_signal_failing_trade(),
            require_trade_parity=True,
            require_htf_parity=True,
        ) is False
        # HTF-parity divergent → False.
        assert would_pass_hard_gate(
            _passed_signal_divergent_htf(),
            require_trade_parity=True,
            require_htf_parity=True,
        ) is False


# ─────────────────────────────────────────────────────────────────────
# Tier 4 — Aggregator + promotion-readiness verdict bands
# ─────────────────────────────────────────────────────────────────────
class TestAggregator:
    def test_empty_rows_summary(self):
        from engines.parity_certification import summarize_signoffs
        s = summarize_signoffs([])
        assert s["total"] == 0
        assert s["status_counts"] == {}
        assert s["trade_parity"]["present"] == 0
        assert s["trade_parity"]["rate"] is None
        assert s["htf_parity"]["rate"] is None
        assert s["hard_gate"]["rate"] is None

    def test_summary_status_counts(self):
        from engines.parity_certification import summarize_signoffs
        rows = [
            _passed_signal_only(),
            _passed_full(),
            _failed_signal(),
            {"status": "NO_DATA"},
        ]
        s = summarize_signoffs(rows, require_trade_parity=False,
                                require_htf_parity=False)
        assert s["total"] == 4
        assert s["status_counts"].get("PASSED") == 2
        assert s["status_counts"].get("UNSUPPORTED") == 1
        assert s["status_counts"].get("NO_DATA") == 1
        # Default require_*=False → signal-only semantic.
        # PASSED rows = 2, hard_gate would_pass = 2, rate = 0.5
        assert s["hard_gate"]["would_pass"] == 2
        assert s["hard_gate"]["rate"] == 0.5

    def test_summary_advisory_aware(self):
        from engines.parity_certification import summarize_signoffs
        rows = [
            _passed_full(),                       # both advisories OK
            _passed_signal_failing_trade(),       # trade fails
            _passed_signal_divergent_htf(),       # htf fails
            _passed_signal_only(),                # advisories absent
        ]
        s = summarize_signoffs(
            rows, require_trade_parity=True, require_htf_parity=True,
        )
        # Only _passed_full satisfies BOTH advisories.
        assert s["hard_gate"]["would_pass"] == 1
        assert s["hard_gate"]["rate"] == 0.25
        # 3 of 4 rows have trade_parity_passed; 1 of those 3 is True.
        assert s["trade_parity"]["present"] == 3
        assert s["trade_parity"]["passed"] == 2
        # 3 of 4 rows have htf_parity_verdict; 2 are in passing band.
        assert s["htf_parity"]["present"] == 3
        assert s["htf_parity"]["passing"] == 2
        assert s["htf_parity"]["verdicts"].get("DIVERGENT") == 1


class TestPromotionVerdict:
    def test_uncertified_when_no_advisories(self):
        from engines.parity_certification import (
            evaluate_promotion_readiness, summarize_signoffs,
        )
        s = summarize_signoffs([_passed_signal_only()] * 100)
        v = evaluate_promotion_readiness(s)
        assert v["verdict"] == "UNCERTIFIED"
        assert "ENABLE_CBOT_TRADE_PARITY" in v["rationale"]

    def test_needs_more_evidence_when_low_sample_count(self):
        from engines.parity_certification import (
            evaluate_promotion_readiness, summarize_signoffs,
        )
        # 5 rows with all advisories passing — below min_samples=30.
        s = summarize_signoffs(
            [_passed_full()] * 5,
            require_trade_parity=True, require_htf_parity=True,
        )
        v = evaluate_promotion_readiness(s, min_samples=30, min_pass_rate=0.95)
        assert v["verdict"] == "NEEDS_MORE_EVIDENCE"
        assert "5" in v["rationale"] and "30" in v["rationale"]

    def test_not_ready_when_pass_rate_below_threshold(self):
        from engines.parity_certification import (
            evaluate_promotion_readiness, summarize_signoffs,
        )
        rows = ([_passed_full()] * 50) + ([_passed_signal_divergent_htf()] * 50)
        s = summarize_signoffs(
            rows, require_trade_parity=True, require_htf_parity=True,
        )
        v = evaluate_promotion_readiness(s, min_samples=30, min_pass_rate=0.95)
        assert v["verdict"] == "NOT_READY"
        assert v["observed_pass_rate"] == 0.5

    def test_promotable_when_evidence_meets_thresholds(self):
        from engines.parity_certification import (
            evaluate_promotion_readiness, summarize_signoffs,
        )
        # 50 perfect rows.
        s = summarize_signoffs(
            [_passed_full()] * 50,
            require_trade_parity=True, require_htf_parity=True,
        )
        v = evaluate_promotion_readiness(s, min_samples=30, min_pass_rate=0.95)
        assert v["verdict"] == "PROMOTABLE"
        assert v["observed_pass_rate"] == 1.0
        assert "ENABLE_TRADE_PARITY_HARD_GATE" in v["rationale"]

    def test_verdict_envelope(self):
        """Verdict payload must always carry the institutional envelope:
        advisory_only, operator_authority, thresholds.
        """
        from engines.parity_certification import (
            evaluate_promotion_readiness, summarize_signoffs,
        )
        s = summarize_signoffs([_passed_full()] * 50,
                                require_trade_parity=True,
                                require_htf_parity=True)
        v = evaluate_promotion_readiness(s)
        assert v["advisory_only"] is True
        assert v["operator_authority"] == "final"
        assert "min_samples" in v and "min_pass_rate" in v


# ─────────────────────────────────────────────────────────────────────
# Tier 5 — Feature-flag manifest integration
# ─────────────────────────────────────────────────────────────────────
class TestFeatureFlagManifest:
    def test_flags_registered(self):
        from engines.feature_flags import all_flags
        snap = all_flags()
        for name in (
            "ENABLE_TRADE_PARITY_HARD_GATE",
            "ENABLE_HTF_PARITY_HARD_GATE",
            "PARITY_CERTIFICATION_MIN_SAMPLES",
            "PARITY_CERTIFICATION_MIN_PASS_RATE",
        ):
            assert name in snap, f"missing flag: {name}"

    def test_flags_in_cbot_parity_scope(self):
        from engines.feature_flags import scope_index
        idx = scope_index()
        assert "cbot_parity" in idx
        for name in (
            "ENABLE_TRADE_PARITY_HARD_GATE",
            "ENABLE_HTF_PARITY_HARD_GATE",
            "PARITY_CERTIFICATION_MIN_SAMPLES",
            "PARITY_CERTIFICATION_MIN_PASS_RATE",
        ):
            assert name in idx["cbot_parity"]

    def test_defaults_are_dormant(self):
        from engines.feature_flags import all_flags
        snap = all_flags()
        assert snap["ENABLE_TRADE_PARITY_HARD_GATE"]["default"] is False
        assert snap["ENABLE_HTF_PARITY_HARD_GATE"]["default"] is False
        assert snap["ENABLE_TRADE_PARITY_HARD_GATE"]["is_dormant"] is True
        assert snap["ENABLE_HTF_PARITY_HARD_GATE"]["is_dormant"] is True


if __name__ == "__main__":   # pragma: no cover
    pytest.main([__file__, "-v"])
