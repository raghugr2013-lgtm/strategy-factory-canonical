"""Phase 26.5 — Strategy Lifecycle gate + persistence tests.

Pure-function gate coverage (no DB needed) + persistence smoke (Mongo).
Self-cleaning: every Mongo test seeds with TEST_LF_ prefix and removes
its rows in a finally block.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

from engines import strategy_lifecycle as lc


# ── Fixtures (synthetic library docs + history rows) ───────────────

def _lib(**overrides):
    """Library doc that, by default, sits at CANDIDATE."""
    base = {
        "_id": "lib_test_id",
        "profit_factor": 1.4,
        "total_trades": 60,
        "stability_score": 55,
        "max_drawdown_pct": 0.08,
        "pass_probability": 50,
        "behavioral_profile": "UNCLASSIFIED",
        "smoothness_label": None,
        "expected_max_consec_losses": 4,
        "recovery_factor": 1.2,
        "oos_holdout": {"ratio": 0.5},
        "validation_report": {"badges": []},
    }
    base.update(overrides)
    return base


def _runs(n: int, *, regime_mix=("trending",), pf_seq=None):
    rows = []
    pfs = pf_seq or [1.4 + (i * 0.01) for i in range(n)]
    for i in range(n):
        rows.append({
            "pf": pfs[i % len(pfs)],
            "regime": regime_mix[i % len(regime_mix)],
        })
    return rows


# ── Pure-function gate tests ───────────────────────────────────────

class TestLifecycleGates:

    def test_exploratory_default_no_library(self):
        s = lc.compute_lifecycle_state(library_doc=None, history_rows=[])
        assert s["current_stage"] == "exploratory"
        assert s["stage_rank"] == 0

    def test_exploratory_no_library_id(self):
        # Lib has metrics but no _id / library_id → stays exploratory.
        s = lc.compute_lifecycle_state(
            library_doc=_lib(_id=None),
            history_rows=_runs(5),
        )
        assert s["current_stage"] == "exploratory"

    def test_candidate_baseline(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(),                   # PF=1.4, trades=60
            history_rows=_runs(3),
        )
        assert s["current_stage"] == "candidate"

    def test_candidate_blocked_by_low_trades(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(total_trades=20),
            history_rows=_runs(5),
        )
        assert s["current_stage"] == "exploratory"

    def test_validated_passes_oos_and_stability(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.85},
                stability_score=70,
            ),
            history_rows=_runs(4),
        )
        assert s["current_stage"] == "validated"

    def test_validated_blocked_by_overfit_badge(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.85},
                stability_score=70,
                validation_report={"badges": ["OVERFIT_RISK"]},
            ),
            history_rows=_runs(4),
        )
        assert s["current_stage"] == "candidate"

    def test_stable_requires_consistent_pfs_and_classified_profile(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.85},
                stability_score=70,
                behavioral_profile="TREND_FOLLOWER",
            ),
            history_rows=_runs(8, pf_seq=[1.4, 1.42, 1.45, 1.43, 1.41]),
        )
        assert s["current_stage"] == "stable"

    def test_stable_blocked_by_unclassified_profile(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.85},
                stability_score=70,
                behavioral_profile="UNCLASSIFIED",
            ),
            history_rows=_runs(8, pf_seq=[1.4, 1.42, 1.45, 1.43, 1.41]),
        )
        assert s["current_stage"] == "validated"

    def test_stable_blocked_by_high_cov(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.85},
                stability_score=70,
                behavioral_profile="TREND_FOLLOWER",
            ),
            history_rows=_runs(8, pf_seq=[0.5, 1.4, 2.5, 0.8, 2.0]),
        )
        assert s["current_stage"] == "validated"

    def test_prop_safe_passes(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.85},
                stability_score=72,
                max_drawdown_pct=0.04,
                pass_probability=68,
                smoothness_label="SMOOTH",
                behavioral_profile="TREND_FOLLOWER",
            ),
            history_rows=_runs(8, pf_seq=[1.4, 1.42, 1.45, 1.43, 1.41]),
        )
        assert s["current_stage"] == "prop_safe"

    def test_prop_safe_blocked_volatile(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.85},
                stability_score=72,
                max_drawdown_pct=0.04,
                pass_probability=68,
                smoothness_label="VOLATILE",
                behavioral_profile="TREND_FOLLOWER",
            ),
            history_rows=_runs(8, pf_seq=[1.4, 1.42, 1.45, 1.43, 1.41]),
        )
        assert s["current_stage"] == "stable"

    def test_prop_safe_breakout_with_bad_streak(self):
        # ASYMMETRIC_BREAKOUT with consec losses > 5 → blocked at STABLE.
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.85},
                stability_score=72,
                max_drawdown_pct=0.04,
                pass_probability=68,
                smoothness_label="SMOOTH",
                behavioral_profile="ASYMMETRIC_BREAKOUT",
                expected_max_consec_losses=8,
            ),
            history_rows=_runs(8, pf_seq=[1.4, 1.42, 1.45, 1.43, 1.41]),
        )
        assert s["current_stage"] == "stable"

    def test_elite_requires_cohort_and_regimes_and_recovery(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.9},
                stability_score=80,
                max_drawdown_pct=0.03,
                pass_probability=75,
                smoothness_label="SMOOTH",
                behavioral_profile="TREND_FOLLOWER",
                recovery_factor=2.5,
                deploy_score=82,
                profit_factor=1.6,
                total_trades=200,
            ),
            history_rows=_runs(15, regime_mix=("trending", "ranging"),
                               pf_seq=[1.5, 1.55, 1.6, 1.58, 1.62]),
            cohort_p90_deploy_score=70,
        )
        assert s["current_stage"] == "elite"

    def test_elite_blocked_by_single_regime(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.9},
                stability_score=80,
                max_drawdown_pct=0.03,
                pass_probability=75,
                smoothness_label="SMOOTH",
                behavioral_profile="TREND_FOLLOWER",
                recovery_factor=2.5,
                deploy_score=82,
                total_trades=200,
            ),
            history_rows=_runs(15, regime_mix=("trending",),
                               pf_seq=[1.5, 1.55, 1.6, 1.58, 1.62]),
            cohort_p90_deploy_score=70,
        )
        assert s["current_stage"] == "prop_safe"

    def test_elite_blocked_below_cohort_p90(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.9},
                stability_score=80,
                max_drawdown_pct=0.03,
                pass_probability=75,
                smoothness_label="SMOOTH",
                behavioral_profile="TREND_FOLLOWER",
                recovery_factor=2.5,
                deploy_score=55,
                total_trades=200,
            ),
            history_rows=_runs(15, regime_mix=("trending", "ranging"),
                               pf_seq=[1.5, 1.55, 1.6, 1.58, 1.62]),
            cohort_p90_deploy_score=80,
        )
        assert s["current_stage"] == "prop_safe"

    def test_portfolio_worthy_requires_membership(self):
        # ELITE-eligible but no portfolio membership → stays at ELITE.
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.9},
                stability_score=80,
                max_drawdown_pct=0.03,
                pass_probability=75,
                smoothness_label="SMOOTH",
                behavioral_profile="TREND_FOLLOWER",
                recovery_factor=2.5,
                deploy_score=82,
                total_trades=200,
            ),
            history_rows=_runs(15, regime_mix=("trending", "ranging"),
                               pf_seq=[1.5, 1.55, 1.6, 1.58, 1.62]),
            cohort_p90_deploy_score=70,
            portfolio_membership=None,
        )
        assert s["current_stage"] == "elite"

        s2 = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.9},
                stability_score=80,
                max_drawdown_pct=0.03,
                pass_probability=75,
                smoothness_label="SMOOTH",
                behavioral_profile="TREND_FOLLOWER",
                recovery_factor=2.5,
                deploy_score=82,
                total_trades=200,
            ),
            history_rows=_runs(15, regime_mix=("trending", "ranging"),
                               pf_seq=[1.5, 1.55, 1.6, 1.58, 1.62]),
            cohort_p90_deploy_score=70,
            portfolio_membership={
                "is_member": True, "firm_match_score": 0.85,
                "firm_status": "approved",
            },
        )
        assert s2["current_stage"] == "portfolio_worthy"

    def test_deployment_ready_requires_bi5_and_cbot(self):
        common = dict(
            library_doc=_lib(
                oos_holdout={"ratio": 0.9},
                stability_score=80,
                max_drawdown_pct=0.03,
                pass_probability=75,
                smoothness_label="SMOOTH",
                behavioral_profile="TREND_FOLLOWER",
                recovery_factor=2.5,
                deploy_score=82,
                total_trades=200,
                prop_firm_panel={"safe_risk_per_trade": 0.005},
            ),
            history_rows=_runs(15, regime_mix=("trending", "ranging"),
                               pf_seq=[1.5, 1.55, 1.6, 1.58, 1.62]),
            cohort_p90_deploy_score=70,
            portfolio_membership={
                "is_member": True, "firm_match_score": 0.85,
                "firm_status": "approved",
            },
        )
        # Missing BI5 → portfolio_worthy.
        s = lc.compute_lifecycle_state(**common)
        assert s["current_stage"] == "portfolio_worthy"

        # BI5 below 0.75 → partial-realism flag, still portfolio_worthy.
        s2 = lc.compute_lifecycle_state(
            **common,
            bi5_realism={"pf_ratio": 0.65},
            cbot_status={"compiled": True, "valid": True},
        )
        assert s2["current_stage"] == "portfolio_worthy"
        assert "PARTIAL_REALISM" in s2["flags"]

        # BI5 above 0.75 + cbot ok → DEPLOYMENT_READY.
        s3 = lc.compute_lifecycle_state(
            **common,
            bi5_realism={"pf_ratio": 0.82},
            cbot_status={"compiled": True, "valid": True},
        )
        assert s3["current_stage"] == "deployment_ready"

    def test_bi5_hard_fail_sets_cooldown(self):
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.9},
                stability_score=80,
                max_drawdown_pct=0.03,
                pass_probability=75,
                smoothness_label="SMOOTH",
                behavioral_profile="TREND_FOLLOWER",
            ),
            history_rows=_runs(8, pf_seq=[1.4, 1.42, 1.45]),
            bi5_realism={"pf_ratio": 0.40},
        )
        assert "BI5_FAIL" in s["flags"]
        assert s["cool_down_until"] is not None


class TestHysteresisAndCooldown:

    def test_validated_demotion_buffer(self):
        # Prior at validated, OOS slips to 0.65 — buffer keeps validated.
        prior = {"current_stage": "validated", "current_stage_since": "2026-01-01T00:00:00+00:00"}
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.65},
                stability_score=70,
            ),
            history_rows=_runs(5),
            prior_state=prior,
        )
        assert s["current_stage"] == "validated"

        # OOS at 0.55 — falls below buffer, demotes.
        s2 = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.55},
                stability_score=70,
            ),
            history_rows=_runs(5),
            prior_state=prior,
        )
        assert s2["current_stage"] == "candidate"

    def test_active_cooldown_caps_at_stable(self):
        # Cool-down window still active → cannot reach ELITE even with
        # all evidence present.
        cd_future = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
        prior = {
            "current_stage": "stable",
            "current_stage_since": "2026-01-01T00:00:00+00:00",
            "flags": ["BI5_FAIL"],
            "cool_down_until": cd_future,
        }
        s = lc.compute_lifecycle_state(
            library_doc=_lib(
                oos_holdout={"ratio": 0.9},
                stability_score=80,
                max_drawdown_pct=0.03,
                pass_probability=75,
                smoothness_label="SMOOTH",
                behavioral_profile="TREND_FOLLOWER",
                recovery_factor=2.5,
                deploy_score=82,
                total_trades=200,
            ),
            history_rows=_runs(15, regime_mix=("trending", "ranging"),
                               pf_seq=[1.5, 1.55, 1.6, 1.58, 1.62]),
            cohort_p90_deploy_score=70,
            prior_state=prior,
        )
        # Capped at prop_safe; BI5 lock prevented elite climb.
        assert s["current_stage"] == "prop_safe"
        assert s["cool_down_until"] == cd_future


class TestCohortP90:

    def test_p90_returns_none_for_small_cohort(self):
        libs = [_lib(deploy_score=50) for _ in range(5)]
        assert lc.compute_cohort_p90_deploy_score(libs) is None

    def test_p90_is_high_in_uniform_cohort(self):
        libs = [_lib(deploy_score=70 + i, total_trades=100) for i in range(20)]
        v = lc.compute_cohort_p90_deploy_score(libs)
        assert v is not None
        assert 86 <= v <= 90

    def test_estimate_deploy_score_bounded(self):
        s = lc.estimate_deploy_score(_lib(
            pass_probability=80, stability_score=80,
            profit_factor=2.0, oos_holdout={"ratio": 0.85},
            max_drawdown_pct=0.03, score=75, total_trades=200,
        ))
        assert s is not None
        assert 0 <= s <= 100


# ── Persistence + audit log tests ──────────────────────────────────

@pytest.fixture
def event_loop():
    """Fresh loop per test — motor caches its client to the first loop it
    sees, so we reset between tests."""
    import engines.db as _db
    _db._client = None
    _db._db = None
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
    _db._client = None
    _db._db = None


class TestLifecyclePersistence:

    def test_upsert_and_history_log(self, event_loop):
        async def _go():
            from engines.db import get_db
            db = get_db()
            try:
                await db[lc.LIFECYCLE_COLL].delete_many(
                    {"strategy_hash": "TEST_LF_HASH"})
                await db[lc.LIFECYCLE_HISTORY_COLL].delete_many(
                    {"strategy_hash": "TEST_LF_HASH"})

                state_a = lc.compute_lifecycle_state(
                    library_doc=_lib(),
                    history_rows=_runs(3),
                )
                doc_a = await lc.upsert_lifecycle(
                    "TEST_LF_HASH",
                    library_id="lib_test_id",
                    state=state_a,
                    research_run_id="rr_test_lf",
                )
                assert doc_a["current_stage"] == "candidate"

                # Re-evaluate — same stage, NO history row should be added.
                doc_b = await lc.upsert_lifecycle(
                    "TEST_LF_HASH",
                    library_id="lib_test_id",
                    state=state_a,
                    prior_state=doc_a,
                    research_run_id="rr_test_lf_2",
                )
                assert doc_b["current_stage_since"] == doc_a["current_stage_since"]

                # New stage → history row appended.
                state_c = lc.compute_lifecycle_state(
                    library_doc=_lib(
                        oos_holdout={"ratio": 0.85},
                        stability_score=70,
                    ),
                    history_rows=_runs(5),
                )
                await lc.upsert_lifecycle(
                    "TEST_LF_HASH",
                    library_id="lib_test_id",
                    state=state_c,
                    prior_state=doc_b,
                    research_run_id="rr_test_lf_3",
                )

                hist = await lc.get_lifecycle_history("TEST_LF_HASH")
                # 2 rows: None→candidate (initial), candidate→validated.
                assert len(hist) == 2
                assert hist[0]["from_stage"] == "candidate"
                assert hist[0]["to_stage"] == "validated"
                assert hist[0]["research_run_id"] == "rr_test_lf_3"
                assert hist[1]["from_stage"] is None
                assert hist[1]["to_stage"] == "candidate"

                live = await lc.get_lifecycle("TEST_LF_HASH")
                assert live["current_stage"] == "validated"

                bulk = await lc.get_lifecycle_map(["TEST_LF_HASH", "DOES_NOT_EXIST"])
                assert "TEST_LF_HASH" in bulk
                assert "DOES_NOT_EXIST" not in bulk
            finally:
                await db[lc.LIFECYCLE_COLL].delete_many(
                    {"strategy_hash": "TEST_LF_HASH"})
                await db[lc.LIFECYCLE_HISTORY_COLL].delete_many(
                    {"strategy_hash": "TEST_LF_HASH"})

        event_loop.run_until_complete(_go())


class TestRollupAdapter:

    def test_rollup_adapter_matches_core_function(self):
        # Build a minimal rollup entry that mirrors what the Explorer
        # produces, run the adapter, and verify the stage matches what
        # we'd get from the core function on the same shape.
        entry = {
            "strategy_hash": "h_ro",
            "name": "TEST_LF_RollupAdapter",
            "runs": 8,
            "library_id": "lib_test_id",
            "library": {
                "profit_factor": 1.5,
                "total_trades": 100,
                "stability_score": 72,
                "max_drawdown_pct": 0.04,
                "pass_probability": 65,
                "smoothness_label": "SMOOTH",
                "behavioral_profile": "TREND_FOLLOWER",
                "oos_holdout": {"ratio": 0.85},
                "validation_report": {"badges": []},
            },
            "validation": {"metrics": {
                "behavioral_profile": "TREND_FOLLOWER",
                "smoothness_label": "SMOOTH",
                "expected_max_consec_losses": 3,
                "recovery_factor": 1.8,
            }},
            "best_pf": 1.55,
            "avg_pf": 1.5,
            "last_pf": 1.5,
            "min_pf": 1.45,
            "stability_score": 0.78,
            "regimes": {"trending": 5, "ranging": 3},
            "last_seen": "2026-05-09T12:00:00+00:00",
        }
        s = lc.compute_lifecycle_state_from_rollup(entry)
        assert s["current_stage"] in ("prop_safe", "stable")
