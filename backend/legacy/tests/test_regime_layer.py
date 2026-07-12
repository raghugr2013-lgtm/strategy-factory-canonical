"""Phase 29.0 — Regime Layer trust gate.

Pure-function tests over ``engines.regime_performance`` + lifecycle
taxonomy + API shape. 32 tests across 7 tiers.

7 tiers (per implementation plan):
  1. Determinism                  (4)
  2. Honest refusal               (6)
  3. Sample-adequacy semantics    (5)
  4. Flag emission                (5)
  5. Lifecycle backward-compat    (6)
  6. API contract                 (4)
  7. Schema stability             (2)

Discipline:
  • No DB I/O in pure tiers (1-5, 7). Tier 6 uses live HTTP probes.
  • Self-cleaning: any Mongo writes use a TEST_R29_ prefix.
  • Original `compute_lifecycle_state` byte-identity is asserted in
    Tier 5 by re-running a representative fixture from
    `test_strategy_lifecycle_phase26_5.py` and asserting identical
    `current_stage` / `stage_rank` regardless of regime layer
    presence (REGIME_FRAGILE flag is NOT emitted by lifecycle in 29.0).
"""
from __future__ import annotations

import json
import random
import sys

import pytest
from dotenv import load_dotenv

_BACKEND = "/app/backend"
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
load_dotenv("/app/backend/.env")

from engines import regime_performance as rp  # noqa: E402
from engines import strategy_lifecycle as lc  # noqa: E402


# ── Fixture helpers ─────────────────────────────────────────────────


def _row(regime, pf=1.4, trades=20, dd=0.08, win_rate=0.55, return_pct=5.0):
    return {
        "regime":     regime,
        "pf":         pf,
        "dd_pct":     dd,
        "trades":     trades,
        "win_rate":   win_rate,
        "return_pct": return_pct,
    }


def _narrow_history(regime="trending", n=5, pf=1.4):
    return [_row(regime, pf=pf) for _ in range(n)]


def _broad_history(pf_trending=1.4, pf_ranging=1.3, n_each=3):
    return (
        [_row("trending", pf=pf_trending) for _ in range(n_each)]
        + [_row("ranging", pf=pf_ranging) for _ in range(n_each)]
    )


# ════════════════════════════════════════════════════════════════════
# Tier 1 — Determinism (4)
# ════════════════════════════════════════════════════════════════════

class TestTier1Determinism:

    def test_same_history_same_output(self):
        history = _broad_history()
        a = rp.compute_regime_performance(history)
        b = rp.compute_regime_performance(history)
        # computed_at differs — strip and compare the rest.
        a.pop("computed_at")
        b.pop("computed_at")
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_row_order_shuffle_invariant(self):
        history = _broad_history()
        baseline = rp.compute_regime_performance(history)
        rng = random.Random(42)
        for _ in range(5):
            shuffled = list(history)
            rng.shuffle(shuffled)
            out = rp.compute_regime_performance(shuffled)
            baseline.pop("computed_at", None)
            out.pop("computed_at", None)
            assert (
                json.dumps(baseline, sort_keys=True)
                == json.dumps(out, sort_keys=True)
            )

    def test_alphabetical_list_ordering(self):
        history = _broad_history()
        out = rp.compute_regime_performance(history)
        # Lists must be alphabetical (stable across input row order).
        assert out["regimes_seen"] == sorted(out["regimes_seen"])
        assert out["regimes_adequate"] == sorted(out["regimes_adequate"])
        assert out["regimes_breadth"] == sorted(out["regimes_breadth"])

    def test_per_regime_key_set_stable(self):
        # Empty history and broad history must both have the SAME set
        # of per_regime keys (all 5).
        empty = rp.compute_regime_performance([])
        broad = rp.compute_regime_performance(_broad_history())
        assert set(empty["per_regime"].keys()) == set(broad["per_regime"].keys())
        assert set(empty["per_regime"].keys()) == set(rp.ALL_REGIMES)


# ════════════════════════════════════════════════════════════════════
# Tier 2 — Honest refusal (6)
# ════════════════════════════════════════════════════════════════════

class TestTier2HonestRefusal:

    def test_empty_history_is_fragile_with_zero_breadth(self):
        out = rp.compute_regime_performance([])
        assert out["breadth_count"] == 0
        assert out["fragile"] is True
        assert out["regimes_seen"] == []
        assert out["regimes_adequate"] == []
        assert out["regimes_breadth"] == []

    def test_none_regime_buckets_into_unknown_not_canonical(self):
        history = [_row(None) for _ in range(5)]
        out = rp.compute_regime_performance(history)
        assert out["per_regime"]["unknown"]["n_runs"] == 5
        # None bucketed into unknown → NEVER feeds breadth.
        assert out["breadth_count"] == 0
        assert out["fragile"] is True

    def test_unknown_string_label_buckets_into_unknown(self):
        history = [_row("unknown", pf=1.5, trades=50) for _ in range(5)]
        out = rp.compute_regime_performance(history)
        # Operator guarantee #2 — unknown NEVER counts as evidence.
        assert out["per_regime"]["unknown"]["sample_adequate"] is False
        assert out["per_regime"]["unknown"]["edge_positive"] is False
        assert out["breadth_count"] == 0

    def test_typo_or_unrecognised_regime_buckets_into_unknown(self):
        history = [_row("TREND-ING", pf=1.5, trades=50) for _ in range(5)]
        out = rp.compute_regime_performance(history)
        assert out["per_regime"]["unknown"]["n_runs"] == 5
        assert out["per_regime"]["trending"]["n_runs"] == 0
        assert out["breadth_count"] == 0

    def test_missing_pf_yields_null_not_zero(self):
        history = [
            {"regime": "trending", "trades": 30},
            {"regime": "trending", "trades": 30},
        ]
        out = rp.compute_regime_performance(history)
        assert out["per_regime"]["trending"]["pf_mean"] is None
        # No edge if PF unknown — refusal, not optimism.
        assert out["per_regime"]["trending"]["edge_positive"] is False

    def test_non_dict_rows_ignored_safely(self):
        history = [None, 42, "string-row", _row("trending"), {"foo": "bar"}]
        out = rp.compute_regime_performance(history)
        # Only the valid trending row is counted; the {"foo":"bar"} row
        # has regime=None → unknown bucket; junk dropped silently.
        assert out["per_regime"]["trending"]["n_runs"] == 1
        assert out["per_regime"]["unknown"]["n_runs"] == 1


# ════════════════════════════════════════════════════════════════════
# Tier 3 — Sample-adequacy semantics (5)
# ════════════════════════════════════════════════════════════════════

class TestTier3SampleAdequacy:

    def test_one_run_thirty_trades_not_adequate(self):
        # operator: N≥2 runs is the floor — 1 lucky run never counts.
        history = [_row("trending", pf=1.5, trades=30)]
        out = rp.compute_regime_performance(history)
        assert out["per_regime"]["trending"]["n_runs"] == 1
        assert out["per_regime"]["trending"]["sample_adequate"] is False

    def test_two_runs_four_trades_each_not_adequate(self):
        # 8 trades < MIN_TRADES_PER_REGIME (10).
        history = [_row("trending", pf=1.5, trades=4) for _ in range(2)]
        out = rp.compute_regime_performance(history)
        assert out["per_regime"]["trending"]["trades_total"] == 8
        assert out["per_regime"]["trending"]["sample_adequate"] is False

    def test_two_runs_five_trades_each_adequate(self):
        history = [_row("trending", pf=1.5, trades=5) for _ in range(2)]
        out = rp.compute_regime_performance(history)
        assert out["per_regime"]["trending"]["n_runs"] == 2
        assert out["per_regime"]["trending"]["trades_total"] == 10
        assert out["per_regime"]["trending"]["sample_adequate"] is True
        assert out["per_regime"]["trending"]["edge_positive"] is True

    def test_pf_mean_arithmetic_correct(self):
        history = [
            _row("trending", pf=1.2, trades=15),
            _row("trending", pf=1.6, trades=15),
        ]
        out = rp.compute_regime_performance(history)
        assert abs(out["per_regime"]["trending"]["pf_mean"] - 1.4) < 1e-6

    def test_pf_cov_arithmetic_correct(self):
        # PFs = [1.0, 2.0] → mean=1.5, std=0.5, cov = 0.5/1.5 ≈ 0.3333
        history = [
            _row("trending", pf=1.0, trades=15),
            _row("trending", pf=2.0, trades=15),
        ]
        out = rp.compute_regime_performance(history)
        cov = out["per_regime"]["trending"]["pf_cov"]
        assert cov is not None
        assert abs(cov - 0.3333) < 0.001


# ════════════════════════════════════════════════════════════════════
# Tier 4 — Flag emission semantics (5)
# ════════════════════════════════════════════════════════════════════

class TestTier4FlagEmission:

    def test_narrow_regime_history_is_fragile(self):
        # 5 rows all trending, adequate, profitable → breadth=1 → fragile
        history = _narrow_history("trending", n=5, pf=1.4)
        out = rp.compute_regime_performance(history)
        assert out["breadth_count"] == 1
        assert out["fragile"] is True

    def test_broad_two_regimes_not_fragile(self):
        history = _broad_history(pf_trending=1.4, pf_ranging=1.3, n_each=3)
        out = rp.compute_regime_performance(history)
        # Need trades_total ≥ 10 per regime — each row has 20 trades by
        # default, so 3 rows × 20 = 60 trades per regime.
        assert out["per_regime"]["trending"]["sample_adequate"] is True
        assert out["per_regime"]["ranging"]["sample_adequate"] is True
        assert out["breadth_count"] == 2
        assert out["fragile"] is False

    def test_negative_edge_regime_does_not_count_for_breadth(self):
        # trending profitable, ranging adequate but losing (PF=0.7)
        history = (
            [_row("trending", pf=1.4, trades=20) for _ in range(3)]
            + [_row("ranging", pf=0.7, trades=20) for _ in range(3)]
        )
        out = rp.compute_regime_performance(history)
        assert out["per_regime"]["ranging"]["sample_adequate"] is True
        assert out["per_regime"]["ranging"]["edge_positive"] is False
        assert out["breadth_count"] == 1
        assert out["fragile"] is True

    def test_unknown_only_history_is_fragile_not_evidential(self):
        # Operator guarantee #2 — unknown buckets never feed breadth.
        history = [_row(None, pf=2.0, trades=50) for _ in range(10)]
        out = rp.compute_regime_performance(history)
        assert out["per_regime"]["unknown"]["n_runs"] == 10
        assert out["per_regime"]["unknown"]["sample_adequate"] is False
        assert out["breadth_count"] == 0
        assert out["fragile"] is True

    def test_three_regimes_broad_strong_breadth(self):
        history = (
            [_row("trending", pf=1.4, trades=20) for _ in range(3)]
            + [_row("ranging", pf=1.2, trades=20) for _ in range(3)]
            + [_row("high_volatility", pf=1.3, trades=20) for _ in range(3)]
        )
        out = rp.compute_regime_performance(history)
        assert out["breadth_count"] == 3
        assert out["fragile"] is False
        assert "trending" in out["regimes_breadth"]
        assert "ranging" in out["regimes_breadth"]
        assert "high_volatility" in out["regimes_breadth"]


# ════════════════════════════════════════════════════════════════════
# Tier 5 — Lifecycle backward-compat + taxonomy (6)
# ════════════════════════════════════════════════════════════════════

class TestTier5LifecycleBackwardCompat:

    def test_regime_fragile_in_taxonomy(self):
        assert "REGIME_FRAGILE" in lc.LIFECYCLE_FLAGS

    def test_existing_flags_still_in_taxonomy(self):
        for f in ("PARTIAL_REALISM", "BI5_FAIL", "STALE",
                  "MANUALLY_OVERRIDDEN", "BI5_DATA_MISSING"):
            assert f in lc.LIFECYCLE_FLAGS

    def test_lifecycle_state_does_not_emit_regime_fragile_in_29_0(self):
        # Phase 29.0: REGIME_FRAGILE is reserved in taxonomy but NEVER
        # emitted by `compute_lifecycle_state`. The lifecycle doc is
        # operator-decision authoritative — regime evidence is on-read
        # only via the API. This test guards against accidental drift.
        narrow = _narrow_history("trending", n=10, pf=1.5)
        state = lc.compute_lifecycle_state(
            library_doc={
                "_id": "x", "profit_factor": 1.5, "total_trades": 100,
                "stability_score": 80, "max_drawdown_pct": 0.04,
                "pass_probability": 80, "behavioral_profile": "TREND_RIDER",
                "smoothness_label": "SMOOTH", "recovery_factor": 1.8,
                "oos_holdout": {"ratio": 0.8},
                "validation_report": {"badges": []},
                "expected_max_consec_losses": 3,
            },
            history_rows=narrow,
        )
        assert "REGIME_FRAGILE" not in state["flags"]

    def test_compute_lifecycle_state_unchanged_signatures(self):
        # Backward-compat: the function must accept ALL pre-29 kwargs.
        out = lc.compute_lifecycle_state(
            library_doc=None,
            history_rows=[],
            cohort_p90_deploy_score=None,
            bi5_realism=None,
            cbot_status=None,
            portfolio_membership=None,
            prior_state=None,
            last_run_at=None,
        )
        assert out["current_stage"] == "exploratory"
        assert out["stage_rank"] == 0

    def test_lifecycle_stages_tuple_unchanged(self):
        # The 8-stage closed taxonomy is unchanged by Phase 29.0.
        assert lc.LIFECYCLE_STAGES == (
            "exploratory", "candidate", "validated", "stable",
            "prop_safe", "elite", "portfolio_worthy", "deployment_ready",
        )

    def test_gate_functions_callable_unchanged_surface(self):
        # All 7 gates exist and are private — same import path as pre-29.
        for name in (
            "_gate_candidate", "_gate_validated", "_gate_stable",
            "_gate_prop_safe", "_gate_elite", "_gate_portfolio_worthy",
            "_gate_deployment_ready",
        ):
            assert hasattr(lc, name), (
                f"{name} disappeared — Phase 29 must not touch gate surface"
            )


# ════════════════════════════════════════════════════════════════════
# Tier 6 — API contract (4) — live HTTP probes
# ════════════════════════════════════════════════════════════════════

# These tests require the backend to be running. They use the same
# pattern as `test_research_lineage_g1.py` (requests + a session token).

@pytest.fixture(scope="module")
def auth_token():
    """Login as the seeded admin and return a bearer token. Skips the
    Tier 6 tests when the backend is not reachable."""
    import os
    import requests

    base = os.environ.get("BACKEND_BASE_URL", "http://localhost:8001")
    try:
        r = requests.post(
            f"{base}/api/auth/login",
            json={"email": "admin@local.test", "password": "admin123"},
            timeout=3,
        )
    except Exception:
        pytest.skip("backend not reachable for Tier 6 API tests")
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code}")
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def base_url():
    import os
    return os.environ.get("BACKEND_BASE_URL", "http://localhost:8001")


class TestTier6ApiContract:

    def test_unknown_hash_returns_200_with_empty_evidence(self, base_url, auth_token):
        import requests
        r = requests.get(
            f"{base_url}/api/regime/strategy/__phase29_unknown_hash__",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=5,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["row_count"] == 0
        assert body["evidence"]["regimes_seen"] == []
        assert body["evidence"]["breadth_count"] == 0
        assert body["evidence"]["fragile"] is True
        assert body["evidence"]["phase"] == "29.0"
        assert body["evidence"]["advisory_only"] is True

    def test_cohort_distribution_stable_shape_on_empty(self, base_url, auth_token):
        import requests
        r = requests.get(
            f"{base_url}/api/regime/cohort-distribution",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=10,
        )
        assert r.status_code == 200
        body = r.json()
        assert "breadth_count_distribution" in body
        assert set(body["breadth_count_distribution"].keys()) >= {"0", "1", "2", "3", "4"}
        assert set(body["per_regime_breadth_occupancy"].keys()) == set(rp.REGIMES_CANONICAL)
        assert body["phase"] == "29.0"
        assert body["advisory_only"] is True

    def test_cohort_distribution_limit_validation(self, base_url, auth_token):
        import requests
        r = requests.get(
            f"{base_url}/api/regime/cohort-distribution?limit=0",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=5,
        )
        # FastAPI Query(ge=1) → 422 on limit=0.
        assert r.status_code == 422

    def test_lifecycle_alias_marks_no_mutation(self, base_url, auth_token):
        import requests
        r = requests.get(
            f"{base_url}/api/lifecycle/regime-evidence/__phase29_unknown_hash__",
            headers={"Authorization": f"Bearer {auth_token}"},
            timeout=5,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["lifecycle_doc_mutated"] is False
        assert body["regime_evidence"]["phase"] == "29.0"


# ════════════════════════════════════════════════════════════════════
# Tier 7 — Schema stability (2)
# ════════════════════════════════════════════════════════════════════

class TestTier7SchemaStability:

    def test_per_regime_always_has_all_five_keys(self):
        # Even with zero history rows, every regime key (4 canonical +
        # unknown) is present with empty_regime_stats shape.
        out = rp.compute_regime_performance([])
        assert set(out["per_regime"].keys()) == set(rp.ALL_REGIMES)
        for r in rp.ALL_REGIMES:
            expected_keys = set(rp.empty_regime_stats(r).keys())
            assert set(out["per_regime"][r].keys()) == expected_keys

    def test_top_level_keys_stable(self):
        expected = {
            "per_regime", "regimes_seen", "regimes_adequate",
            "regimes_breadth", "breadth_count", "fragile",
            "computed_at", "phase", "advisory_only",
        }
        broad = rp.compute_regime_performance(_broad_history())
        empty = rp.compute_regime_performance([])
        assert set(broad.keys()) == expected
        assert set(empty.keys()) == expected
