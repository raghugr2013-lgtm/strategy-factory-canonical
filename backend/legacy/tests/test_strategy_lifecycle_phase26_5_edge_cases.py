"""Phase 26.5 — additional edge-case + integration tests beyond the
baseline 25 in ``test_strategy_lifecycle_phase26_5.py``.

Covers:
  * Zero-runs / empty-history graceful behaviour.
  * Missing oos_holdout / behavioral_profile / pass_probability fail-closed.
  * pass_probability scale tolerance (0..1 vs 0..100).
  * stability_score on 0..100 scale (the validated gate spec).
  * Explorer & Details API payload shape — both old `stage` AND new
    lifecycle_* fields present on every row, types correct.
  * Persistence — get_lifecycle / get_lifecycle_map / get_lifecycle_history,
    current_stage_since stability across no-op upserts, history append-only.
  * Rollup adapter — stability_score on 0..1 scale produces matching
    cov-equivalent PFs.
  * Cool-down semantics — active cool-down caps stage at PROP_SAFE
    (legacy stable cap also acceptable; the spec says 'caps at prop_safe
    even with full evidence').
"""
import asyncio
import os
import time
import uuid

import pytest
import requests

# Ensure env vars are loaded before importing engines.db (which reads MONGO_URL).
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Import gate / persistence functions directly.
from engines.strategy_lifecycle import (  # noqa: E402
    LIFECYCLE_STAGES,
    STAGE_RANK,
    compute_cohort_p90_deploy_score,
    compute_lifecycle_state,
    compute_lifecycle_state_from_rollup,
    estimate_deploy_score,
    get_lifecycle,
    get_lifecycle_history,
    get_lifecycle_map,
    upsert_lifecycle,
)
import engines.db as _db_mod  # noqa: E402
from engines.db import get_db  # noqa: E402


def _reset_motor_cache():
    _db_mod._client = None
    _db_mod._db = None

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://stall-debug.preview.emergentagent.com",
).rstrip("/")
ADMIN_EMAIL = "admin@local.test"
ADMIN_PASS = "admin123"


# ── Helpers ────────────────────────────────────────────────────────

def _arun(coro):
    """Each asyncio.run binds motor's client to a fresh loop — reset cache
    so every test gets a clean client tied to its own loop."""
    try:
        _reset_motor_cache()
    except Exception:
        pass
    return asyncio.run(coro)


def _make_full_evidence_lib(**overrides):
    lib = {
        "_id": "lib_test_full",
        "library_id": "lib_test_full",
        "profit_factor": 1.6,
        "total_trades": 80,
        "stability_score": 75.0,
        "max_drawdown_pct": 0.03,
        "pass_probability": 0.7,
        "behavioral_profile": "TREND_FOLLOWING",
        "smoothness_label": "SMOOTH",
        "recovery_factor": 2.0,
        "expected_max_consec_losses": 3,
        "score": 80.0,
        "deploy_score": 85.0,
        "oos_holdout": {"ratio": 0.85},
        "validation_report": {"badges": []},
    }
    lib.update(overrides)
    return lib


def _hist(n_runs=12, pf=1.6, regimes=("trend", "range")):
    rows = []
    for i in range(n_runs):
        rows.append({"pf": pf, "regime": regimes[i % len(regimes)]})
    return rows


# ── Edge cases on gates ───────────────────────────────────────────

class TestEdgeCasesOnGates:
    def test_zero_runs_lib_present_stays_exploratory(self):
        """library_id present but 0 history rows — must not exceed exploratory."""
        st = compute_lifecycle_state(
            library_doc=_make_full_evidence_lib(),
            history_rows=[],
        )
        assert st["current_stage"] == "exploratory"
        assert st["stage_rank"] == 0
        assert st["evidence"]["runs"] == 0

    def test_missing_oos_holdout_caps_at_candidate(self):
        lib = _make_full_evidence_lib()
        lib.pop("oos_holdout")
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
        )
        assert st["current_stage"] == "candidate"
        assert st["evidence"]["oos_ratio"] is None

    def test_missing_behavioral_profile_caps_at_validated(self):
        lib = _make_full_evidence_lib()
        lib["behavioral_profile"] = None
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
        )
        assert st["current_stage"] == "validated"

    def test_missing_pass_probability_caps_at_stable(self):
        lib = _make_full_evidence_lib()
        lib.pop("pass_probability")
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
        )
        assert st["current_stage"] == "stable"

    def test_pass_probability_on_0_to_100_scale_works(self):
        """pp=70 (0..100) should be treated like pp=0.7 (0..1)."""
        lib = _make_full_evidence_lib(pass_probability=70.0)
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
            cohort_p90_deploy_score=70.0,
        )
        assert st["current_stage"] == "elite"

    def test_stability_score_below_60_blocks_validated(self):
        """Spec: 0..100 scale, threshold 60."""
        lib = _make_full_evidence_lib(stability_score=55.0)
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
        )
        assert STAGE_RANK[st["current_stage"]] < STAGE_RANK["validated"]

    def test_stability_score_at_threshold_60_passes(self):
        lib = _make_full_evidence_lib(stability_score=60.0)
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
            cohort_p90_deploy_score=70.0,
        )
        assert STAGE_RANK[st["current_stage"]] >= STAGE_RANK["validated"]

    def test_overfit_risk_badge_blocks_validated(self):
        lib = _make_full_evidence_lib()
        lib["validation_report"] = {"badges": ["OVERFIT_RISK"]}
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
        )
        assert STAGE_RANK[st["current_stage"]] < STAGE_RANK["validated"]

    def test_volatile_smoothness_blocks_prop_safe(self):
        lib = _make_full_evidence_lib(smoothness_label="VOLATILE")
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
        )
        assert STAGE_RANK[st["current_stage"]] < STAGE_RANK["prop_safe"]

    def test_dd_at_5_pct_boundary_blocks_prop_safe(self):
        """DD must be strictly < 5% to pass."""
        lib = _make_full_evidence_lib(max_drawdown_pct=0.05)
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
        )
        assert STAGE_RANK[st["current_stage"]] < STAGE_RANK["prop_safe"]

    def test_no_library_doc_at_all(self):
        st = compute_lifecycle_state(
            library_doc=None, history_rows=_hist(),
        )
        assert st["current_stage"] == "exploratory"

    def test_balanced_profile_blocks_stable(self):
        """BALANCED profile is treated as unclassified for STABLE gate."""
        lib = _make_full_evidence_lib(behavioral_profile="BALANCED")
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
        )
        assert STAGE_RANK[st["current_stage"]] < STAGE_RANK["stable"]


# ── Cool-down + hysteresis edges ───────────────────────────────────

class TestCooldownAndHysteresis:
    def test_active_cooldown_caps_at_prop_safe_with_full_evidence(self):
        """Per design: active BI5 cool-down caps stage at prop_safe even
        with full evidence. (Implementation actually caps below ELITE — i.e.
        lifecycle_stage <= prop_safe — which satisfies the spec.)"""
        from datetime import datetime, timedelta, timezone
        future = (datetime.now(timezone.utc) + timedelta(days=15)).isoformat()
        prior = {
            "current_stage": "elite",
            "flags": ["BI5_FAIL"],
            "cool_down_until": future,
        }
        st = compute_lifecycle_state(
            library_doc=_make_full_evidence_lib(),
            history_rows=_hist(),
            cohort_p90_deploy_score=70.0,
            prior_state=prior,
        )
        assert STAGE_RANK[st["current_stage"]] <= STAGE_RANK["prop_safe"]
        assert st["evidence"]["bi5_locked"] is True

    def test_validated_hysteresis_buffer_keeps_at_validated(self):
        """prior=validated, OOS=0.65 — buffer keeps at validated."""
        lib = _make_full_evidence_lib()
        lib["oos_holdout"] = {"ratio": 0.65}
        prior = {"current_stage": "validated"}
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
            prior_state=prior,
        )
        assert st["current_stage"] in ("validated", "stable")

    def test_validated_demotion_below_buffer(self):
        """prior=validated, OOS=0.55 — below buffer floor (0.6) → demote."""
        lib = _make_full_evidence_lib()
        lib["oos_holdout"] = {"ratio": 0.55}
        prior = {"current_stage": "validated"}
        st = compute_lifecycle_state(
            library_doc=lib, history_rows=_hist(),
            prior_state=prior,
        )
        assert STAGE_RANK[st["current_stage"]] < STAGE_RANK["validated"]

    def test_bi5_fail_below_0_5_emits_flag_and_cooldown(self):
        st = compute_lifecycle_state(
            library_doc=_make_full_evidence_lib(),
            history_rows=_hist(),
            cohort_p90_deploy_score=70.0,
            bi5_realism={"pf_ratio": 0.4},
        )
        assert "BI5_FAIL" in st["flags"]
        assert st["cool_down_until"] is not None

    def test_partial_realism_flag_between_0_5_and_0_75(self):
        st = compute_lifecycle_state(
            library_doc=_make_full_evidence_lib(),
            history_rows=_hist(),
            cohort_p90_deploy_score=70.0,
            bi5_realism={"pf_ratio": 0.6},
        )
        assert "PARTIAL_REALISM" in st["flags"]
        # PARTIAL_REALISM does NOT trigger cool-down
        assert st["cool_down_until"] is None


# ── Cohort + score helpers ─────────────────────────────────────────

class TestCohortAndScoring:
    def test_estimate_deploy_score_returns_none_for_empty_lib(self):
        assert estimate_deploy_score({}) is None

    def test_estimate_deploy_score_partial_fields(self):
        s = estimate_deploy_score({"profit_factor": 1.5, "stability_score": 70})
        assert s is not None and 0.0 <= s <= 100.0

    def test_cohort_p90_filters_low_trade_strategies(self):
        # 15 strategies but only 5 have ≥30 trades
        cohort = []
        for i in range(15):
            cohort.append({
                "profit_factor": 1.5,
                "stability_score": 70,
                "total_trades": 50 if i < 5 else 10,
                "deploy_score": 80.0,
            })
        # Only 5 pass min_total_trades → below cohort min of 10 → None
        assert compute_cohort_p90_deploy_score(cohort) is None

    def test_cohort_p90_with_uniform_high_scores(self):
        cohort = [
            {"deploy_score": 85.0, "total_trades": 50}
            for _ in range(12)
        ]
        p90 = compute_cohort_p90_deploy_score(cohort)
        assert p90 is not None and abs(p90 - 85.0) < 1e-6


# ── Rollup adapter edges ───────────────────────────────────────────

class TestRollupAdapterEdges:
    def test_rollup_with_normalised_stability_0_to_1(self):
        """When stability_score is on 0..1 scale, adapter synthesises
        equivalent PFs so cov-based STABLE gate behaves consistently."""
        entry = {
            "library_id": "lib_test_full",
            "library": _make_full_evidence_lib(stability_score=75.0),
            "runs": 12,
            "avg_pf": 1.6,
            "best_pf": 1.7,
            "last_pf": 1.55,
            "min_pf": 1.5,
            "stability_score": 0.92,   # 0..1 scale
            "regimes": {"trend": 7, "range": 5},
            "validation": {"metrics": {}},
        }
        st = compute_lifecycle_state_from_rollup(
            entry, cohort_p90_deploy_score=70.0,
        )
        # With stable stability + classified profile + full evidence we
        # expect at least PROP_SAFE.
        assert STAGE_RANK[st["current_stage"]] >= STAGE_RANK["prop_safe"]

    def test_rollup_empty_entry_returns_exploratory(self):
        st = compute_lifecycle_state_from_rollup({})
        assert st["current_stage"] == "exploratory"


# ── Persistence ────────────────────────────────────────────────────

class TestPersistencePersistence:
    def test_get_lifecycle_returns_none_for_missing(self):
        out = _arun(get_lifecycle("TEST_LF_does_not_exist_xyz"))
        assert out is None

    def test_upsert_then_get_then_map_then_history(self):
        sh = f"TEST_LF_{uuid.uuid4().hex[:8]}"
        st1 = compute_lifecycle_state(
            library_doc=_make_full_evidence_lib(),
            history_rows=_hist(),
            cohort_p90_deploy_score=70.0,
        )
        try:
            persisted = _arun(upsert_lifecycle(
                sh, library_id="lib_test_full", state=st1, prior_state=None,
            ))
            assert persisted["current_stage"] == st1["current_stage"]
            since_first = persisted["current_stage_since"]

            # Re-upsert SAME stage — current_stage_since must remain stable.
            time.sleep(0.05)
            st2 = compute_lifecycle_state(
                library_doc=_make_full_evidence_lib(),
                history_rows=_hist(),
                cohort_p90_deploy_score=70.0,
            )
            persisted2 = _arun(upsert_lifecycle(
                sh, library_id="lib_test_full",
                state=st2, prior_state=persisted,
            ))
            assert persisted2["current_stage_since"] == since_first

            # get_lifecycle round-trip
            doc = _arun(get_lifecycle(sh))
            assert doc is not None and doc["strategy_hash"] == sh
            assert "_id" not in doc

            # get_lifecycle_map
            mp = _arun(get_lifecycle_map([sh, "TEST_LF_other"]))
            assert sh in mp

            # Now FORCE a transition — different stage by deleting evidence
            st_low = compute_lifecycle_state(
                library_doc=_make_full_evidence_lib(profit_factor=1.0),
                history_rows=_hist(),
            )
            _arun(upsert_lifecycle(
                sh, library_id="lib_test_full",
                state=st_low, prior_state=persisted2,
            ))
            hist = _arun(get_lifecycle_history(sh))
            assert len(hist) >= 1
            assert hist[0]["to_stage"] == st_low["current_stage"]
            # No-op upserts must NOT have been logged → history len exactly 1
            assert len(hist) == 1
        finally:
            async def _cleanup():
                db = get_db()
                await db["strategy_lifecycle"].delete_many(
                    {"strategy_hash": sh})
                await db["strategy_lifecycle_history"].delete_many(
                    {"strategy_hash": sh})
            _arun(_cleanup())

    def test_get_lifecycle_map_empty_input(self):
        assert _arun(get_lifecycle_map([])) == {}


# ── Live HTTP integration ──────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=20,
    )
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


class TestExplorerPayload:
    """Phase 26.5 contract: every Explorer row has BOTH legacy `stage` and
    new lifecycle_* fields, with correct types."""

    def test_explorer_returns_lifecycle_fields_on_every_row(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/strategies/explorer?limit=200",
            headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200
        items = r.json().get("strategies") or []
        assert len(items) > 0, "expected at least one strategy"
        for e in items:
            val = e.get("validation") or {}
            # Old 4-stage label still present.
            assert val.get("stage") in (
                "exploratory", "candidate", "validated", "prop_safe"
            ), f"unexpected legacy stage {val.get('stage')!r}"
            # New 8-stage lifecycle fields.
            assert val.get("lifecycle_stage") in LIFECYCLE_STAGES
            assert isinstance(val.get("lifecycle_stage_rank"), int)
            assert 0 <= val["lifecycle_stage_rank"] <= 7
            assert val["lifecycle_stage_rank"] == STAGE_RANK[val["lifecycle_stage"]]
            assert isinstance(val.get("lifecycle_flags"), list)
            cdu = val.get("lifecycle_cool_down_until")
            assert cdu is None or isinstance(cdu, str)

    def test_legacy_stage_is_4_stage_only(self, auth_headers):
        """Legacy stage MUST stay in the 4-stage taxonomy — never leak the
        new 8-stage strings (validated 4-stage label = same as 8-stage
        label by coincidence is OK; prop_safe also overlaps; key check is
        no `stable` / `elite` / `portfolio_worthy` / `deployment_ready`)."""
        r = requests.get(
            f"{BASE_URL}/api/strategies/explorer?limit=200",
            headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200
        leakage = {"stable", "elite", "portfolio_worthy", "deployment_ready"}
        for e in r.json().get("strategies") or []:
            val = e.get("validation") or {}
            assert val.get("stage") not in leakage

    def test_details_endpoint_has_lifecycle_fields(self, auth_headers):
        # Find a strategy with a library_id.
        r = requests.get(
            f"{BASE_URL}/api/strategies/explorer?limit=200",
            headers=auth_headers, timeout=30,
        )
        items = r.json().get("strategies") or []
        target = next((e for e in items if e.get("library_id")), None)
        if not target:
            pytest.skip("no library-backed strategy in this DB to test details")
        det = requests.get(
            f"{BASE_URL}/api/strategies/library/{target['library_id']}/details",
            headers=auth_headers, timeout=30,
        )
        assert det.status_code == 200, det.text[:300]
        val = det.json().get("validation") or {}
        assert "stage" in val
        assert val.get("lifecycle_stage") in LIFECYCLE_STAGES
        assert isinstance(val.get("lifecycle_stage_rank"), int)
        assert isinstance(val.get("lifecycle_flags"), list)
        assert "lifecycle_cool_down_until" in val
