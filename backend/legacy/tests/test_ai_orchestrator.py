"""Phase 22 — unit tests for the rule-based AI orchestrator.

Pure decide() testing — no DB, no network. Verifies every rule with
synthetic state fixtures so adding/removing a rule is a one-line diff.
"""
from engines.ai_orchestrator import decide, ACTION_TYPES


def _base_state(**overrides):
    """Reasonable baseline state with no rules firing."""
    st = {
        "live": {"status": "idle"},
        "recent_runs": [],
        "saves_per_run": [],
        "pfs_per_run": [],
        "avg_pf_recent": None,
        "total_saves_recent": 0,
        "rejection_breakdown": {"counts": {}, "total": 0, "top_reason": None},
        "library": {"total": 0, "new_last_hour": 0},
        "best_candidate": None,
    }
    st.update(overrides)
    return st


def test_no_recommendations_on_fresh_empty_state():
    recs = decide(_base_state())
    # Phase 27.2 added RULE 8 (LIFECYCLE_EVALUATE) and Phase 30.1 added
    # RULE 12 (AUTONOMOUS_DISCOVERY_TICK) — both are observational /
    # advisory rules that fire every tick by design. The honest invariant
    # for an empty fresh state is therefore: NO execution-authority
    # actions fire (no multi-cycle trigger/stop) and no `promote_best_strategy`.
    forbidden = {"trigger_multi_cycle", "stop_multi_cycle", "promote_best_strategy"}
    assert not any(r["action"] in forbidden for r in recs), (
        f"Unexpected execution-authority action on empty state: "
        f"{[r['rule_id'] for r in recs if r['action'] in forbidden]}"
    )


def test_run_active_emits_advisory_and_gates_triggers():
    st = _base_state(
        live={"status": "running", "run_id": "abc"},
        recent_runs=[{"run_id": f"r{i}"} for i in range(3)],
        total_saves_recent=0,
    )
    recs = decide(st)
    ids = [r["rule_id"] for r in recs]
    assert "RUN_ACTIVE" in ids
    # NO_SAVES should NOT trigger a multi-cycle while a run is active.
    assert not any(r["action"] == "trigger_multi_cycle" for r in recs)


def test_no_saves_across_window_boosts_diversity():
    st = _base_state(
        live={"status": "idle"},
        recent_runs=[{"run_id": f"r{i}"} for i in range(3)],
        total_saves_recent=0,
    )
    recs = decide(st)
    boost = [r for r in recs if r["rule_id"] == "NO_SAVES_BOOST_DIVERSITY"]
    assert len(boost) == 1
    assert boost[0]["action"] == "trigger_multi_cycle"
    assert boost[0]["params"]["batch_size"] >= 5
    assert len(boost[0]["params"]["scan"]) >= 6  # broadened scan


def test_insufficient_trades_rule_advisory_only():
    st = _base_state(
        rejection_breakdown={
            "counts": {"insufficient_trades": 12, "other": 3},
            "total": 15, "top_reason": "insufficient_trades",
        },
    )
    recs = decide(st)
    matched = [r for r in recs if r["rule_id"] == "HIGH_INSUFFICIENT_TRADES"]
    assert matched
    assert matched[0]["action"] == "log_recommendation"
    assert matched[0]["params"]["hint"] == "generation_style=high_frequency_preferred"


def test_low_pf_triggers_diversity_cycle():
    st = _base_state(
        live={"status": "idle"},
        recent_runs=[{"run_id": "a"}, {"run_id": "b"}],
        avg_pf_recent=0.72,
    )
    recs = decide(st)
    low_pf = [r for r in recs if r["rule_id"] == "LOW_PF_DIVERSITY"]
    assert len(low_pf) == 1
    assert low_pf[0]["action"] == "trigger_multi_cycle"
    # Diversity scan should include more than the 4 default pairs
    assert len(low_pf[0]["params"]["scan"]) >= 6


def test_low_pf_does_not_trigger_when_run_active():
    st = _base_state(
        live={"status": "running"},
        recent_runs=[{"run_id": "a"}, {"run_id": "b"}],
        avg_pf_recent=0.72,
    )
    recs = decide(st)
    assert not any(r["rule_id"] == "LOW_PF_DIVERSITY" for r in recs)


def test_prop_fail_dominant_advisory():
    st = _base_state(
        rejection_breakdown={
            "counts": {"prop_status_fail": 9, "other": 1},
            "total": 10, "top_reason": "prop_status_fail",
        },
    )
    recs = decide(st)
    pf = [r for r in recs if r["rule_id"] == "PROP_STATUS_FAIL_DOMINANT"]
    assert pf and pf[0]["action"] == "log_recommendation"
    assert pf[0]["params"]["hint"] == "prefer_H4_timeframes"


def test_promote_best_when_high_score_candidate_exists():
    st = _base_state(
        best_candidate={
            "strategy_id": "xyz", "pair": "EURUSD", "timeframe": "H1",
            "score": 72.5, "pass_probability": 58.0, "stability_score": 81.0,
        },
    )
    recs = decide(st)
    pr = [r for r in recs if r["rule_id"] == "PROMOTE_BEST"]
    assert pr and pr[0]["action"] == "promote_best_strategy"
    assert pr[0]["params"]["strategy_id"] == "xyz"
    assert pr[0]["params"]["score"] == 72.5


def test_healthy_trajectory_no_intervention():
    st = _base_state(
        total_saves_recent=3, avg_pf_recent=1.55,
        recent_runs=[{"run_id": "a"}, {"run_id": "b"}],
    )
    recs = decide(st)
    hp = [r for r in recs if r["rule_id"] == "HEALTHY_TRAJECTORY"]
    assert hp and hp[0]["action"] == "log_recommendation"
    # No trigger_multi_cycle when healthy
    assert not any(r["action"] == "trigger_multi_cycle" for r in recs)


def test_all_recommendations_have_valid_action_types():
    # Worst-case state: many rules fire simultaneously.
    st = _base_state(
        live={"status": "idle"},
        recent_runs=[{"run_id": f"r{i}"} for i in range(3)],
        total_saves_recent=0,
        avg_pf_recent=0.5,
        rejection_breakdown={
            "counts": {"insufficient_trades": 4, "prop_status_fail": 6, "oos_gate_failed": 5},
            "total": 15, "top_reason": "prop_status_fail",
        },
        best_candidate={
            "strategy_id": "x", "pair": "XAUUSD", "timeframe": "H4",
            "score": 68.0, "pass_probability": 50.0, "stability_score": 75.0,
        },
    )
    recs = decide(st)
    assert len(recs) >= 4
    for r in recs:
        assert r["action"] in ACTION_TYPES
        assert r["severity"] in ("info", "warn", "critical")
        assert r["rule_id"] and r["reason"]
