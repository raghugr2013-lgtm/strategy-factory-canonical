"""MB-9 Phase 2.A — Runner Router tests.

Pure-function decision tests (no Mongo). The router's async wrapper
is exercised in Phase 2.B integration tests.

Discipline: every alive runner row carries ``verdict="alive"`` to
satisfy the policy contract; rows with other verdicts are unreachable.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from engines import runner_router as rr


def _runner(
    *, rid: str, verdict: str = "alive",
    age_seconds: int = 10, queue_depth: int = 0,
    pair_filters=None, timeframe_filters=None,
    name: str = "",
) -> Dict[str, Any]:
    return {
        "runner_id":         rid,
        "name":              name or f"runner-{rid}",
        "verdict":           verdict,
        "age_seconds":       age_seconds,
        "pair_filters":      list(pair_filters or []),
        "timeframe_filters": list(timeframe_filters or []),
        "last_snapshot":     {"queue_depth": queue_depth},
    }


@pytest.fixture(autouse=True)
def _reset_env_and_rr_cursor(monkeypatch):
    # Clear env policy override on each test for determinism.
    monkeypatch.delenv("RUNNER_AFFINITY_POLICY", raising=False)
    rr._RR_CURSOR["i"] = 0
    yield


# ── Refusal cases ─────────────────────────────────────────────────────
def test_empty_fleet_refuses_no_runners():
    d = rr.decide("EURUSD", "H1", [])
    assert d["runner_id"] is None
    assert d["reason"] == rr.REASON_NO_RUNNERS
    assert d["candidates_considered"] == 0


def test_no_alive_runners_refuses():
    fleet = [_runner(rid="r1", verdict="stale"),
             _runner(rid="r2", verdict="dead")]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] is None
    assert d["reason"] == rr.REASON_NO_ALIVE_RUNNERS
    assert d["candidates_considered"] == 2


def test_sticky_with_no_affinity_match_refuses():
    fleet = [_runner(rid="r1", pair_filters=["BTCUSD"], timeframe_filters=["M15"])]
    # single-runner shortcut bypasses sticky; bring a second alive
    fleet.append(_runner(rid="r2", pair_filters=["GBPUSD"], timeframe_filters=["D1"]))
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] is None
    assert d["reason"] == rr.REASON_NO_AFFINITY_MATCH


# ── Single-runner = byte-identical to Phase 1 ─────────────────────────
def test_single_alive_runner_always_routes_regardless_of_policy(monkeypatch):
    fleet = [_runner(rid="r1", pair_filters=["BTCUSD"])]
    for p in rr.VALID_POLICIES:
        monkeypatch.setenv("RUNNER_AFFINITY_POLICY", p)
        d = rr.decide("EURUSD", "H1", fleet)
        assert d["runner_id"] == "r1", f"policy {p} failed"
        assert d["candidates_considered"] == 1


# ── Sticky_pair_tf policy ────────────────────────────────────────────
def test_sticky_pair_tf_picks_matching_filter():
    fleet = [
        _runner(rid="r1", pair_filters=["BTCUSD"], timeframe_filters=["H1"]),
        _runner(rid="r2", pair_filters=["EURUSD"], timeframe_filters=["H1"]),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] == "r2"
    assert d["policy_used"] == rr.POLICY_STICKY_PAIR_TF


def test_sticky_empty_filters_match_everything():
    fleet = [
        _runner(rid="r1", pair_filters=[], timeframe_filters=[]),
        _runner(rid="r2", pair_filters=["BTCUSD"], timeframe_filters=["H1"]),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    # r1 matches (empty=wildcard); r2 does not match EURUSD; r1 wins
    assert d["runner_id"] == "r1"


def test_sticky_tie_break_freshest_heartbeat():
    fleet = [
        _runner(rid="r-old", pair_filters=["EURUSD"], timeframe_filters=["H1"], age_seconds=500),
        _runner(rid="r-new", pair_filters=["EURUSD"], timeframe_filters=["H1"], age_seconds=10),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] == "r-new"


def test_sticky_tie_break_then_queue_depth():
    fleet = [
        _runner(rid="r-busy", pair_filters=["EURUSD"], timeframe_filters=["H1"], age_seconds=10, queue_depth=10),
        _runner(rid="r-idle", pair_filters=["EURUSD"], timeframe_filters=["H1"], age_seconds=10, queue_depth=1),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] == "r-idle"


def test_sticky_case_insensitive_pair():
    fleet = [
        _runner(rid="r1", pair_filters=["eurusd"], timeframe_filters=["h1"]),
        _runner(rid="r2", pair_filters=["gbpusd"], timeframe_filters=["h1"]),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] == "r1"


# ── Least_busy policy ────────────────────────────────────────────────
def test_least_busy_ignores_filters():
    fleet = [
        _runner(rid="r1", pair_filters=["GBPUSD"], queue_depth=20),
        _runner(rid="r2", pair_filters=["BTCUSD"], queue_depth=5),
        _runner(rid="r3", pair_filters=["EURUSD"], queue_depth=2),
    ]
    d = rr.decide("EURUSD", "H1", fleet, policy=rr.POLICY_LEAST_BUSY)
    # r3 (queue=2) tied break with age — equal ages → queue depth picks r3
    assert d["runner_id"] == "r3"
    assert d["policy_used"] == rr.POLICY_LEAST_BUSY


# ── Round_robin policy ───────────────────────────────────────────────
def test_round_robin_cycles_deterministically():
    fleet = [_runner(rid=x) for x in ("a", "b", "c")]
    picks = [rr.decide("EURUSD", "H1", fleet, policy=rr.POLICY_ROUND_ROBIN)["runner_id"]
             for _ in range(7)]
    assert picks == ["a", "b", "c", "a", "b", "c", "a"]


def test_round_robin_skips_dead_runners():
    fleet = [
        _runner(rid="a", verdict="dead"),
        _runner(rid="b"),
        _runner(rid="c", verdict="stale"),
        _runner(rid="d"),
    ]
    picks = [rr.decide("EURUSD", "H1", fleet, policy=rr.POLICY_ROUND_ROBIN)["runner_id"]
             for _ in range(4)]
    # alive set = {b, d}; sorted by id = [b, d]; cycle: b, d, b, d
    assert picks == ["b", "d", "b", "d"]


# ── local_only policy ────────────────────────────────────────────────
def test_local_only_returns_first_alive():
    fleet = [_runner(rid="z"), _runner(rid="a")]
    d = rr.decide("EURUSD", "H1", fleet, policy=rr.POLICY_LOCAL_ONLY)
    assert d["runner_id"] in {"a", "z"}
    assert d["policy_used"] == rr.POLICY_LOCAL_ONLY


# ── Env override + invalid policy ─────────────────────────────────────
def test_env_policy_override(monkeypatch):
    monkeypatch.setenv("RUNNER_AFFINITY_POLICY", rr.POLICY_LEAST_BUSY)
    fleet = [
        _runner(rid="r1", queue_depth=10),
        _runner(rid="r2", queue_depth=1),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["policy_used"] == rr.POLICY_LEAST_BUSY
    assert d["runner_id"] == "r2"


def test_unknown_policy_in_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("RUNNER_AFFINITY_POLICY", "nonsense_policy")
    fleet = [
        _runner(rid="r1", pair_filters=["EURUSD"], timeframe_filters=["H1"]),
        _runner(rid="r2", pair_filters=["BTCUSD"], timeframe_filters=["H1"]),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["policy_used"] == rr.DEFAULT_POLICY  # sticky_pair_tf
    assert d["runner_id"] == "r1"


def test_unknown_policy_in_override_falls_back():
    fleet = [_runner(rid="r1"), _runner(rid="r2")]
    d = rr.decide("EURUSD", "H1", fleet, policy="totally_made_up")
    assert d["policy_used"] == rr.DEFAULT_POLICY


# ── Determinism / no hidden state ─────────────────────────────────────
def test_pure_function_no_side_effects():
    fleet = [_runner(rid="r1", pair_filters=["EURUSD"], timeframe_filters=["H1"]),
             _runner(rid="r2", pair_filters=["EURUSD"], timeframe_filters=["H1"], age_seconds=5)]
    d1 = rr.decide("EURUSD", "H1", fleet)
    d2 = rr.decide("EURUSD", "H1", fleet)
    assert d1["runner_id"] == d2["runner_id"]  # repeatable


def test_age_none_demoted_to_last():
    fleet = [
        _runner(rid="never", age_seconds=None, pair_filters=["EURUSD"], timeframe_filters=["H1"]),
        _runner(rid="fresh", age_seconds=2,   pair_filters=["EURUSD"], timeframe_filters=["H1"]),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] == "fresh"


# ── Stale/dead never picked ───────────────────────────────────────────
@pytest.mark.parametrize("v", ["stale", "dead", "disabled", "unknown", "never_seen"])
def test_only_alive_is_routable(v):
    fleet = [_runner(rid="bad", verdict=v),
             _runner(rid="ok",  verdict="alive")]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] == "ok"


# ── Defensive: filter case-insensitivity + whitespace tolerance ───────
def test_pair_filter_whitespace_tolerant():
    fleet = [
        _runner(rid="r1", pair_filters=[" EURUSD "], timeframe_filters=[" H1 "]),
        _runner(rid="r2", pair_filters=["BTCUSD"], timeframe_filters=["H1"]),
    ]
    d = rr.decide("eurusd", "h1", fleet)
    assert d["runner_id"] == "r1"


# ── Coverage: queue_depth missing / malformed ────────────────────────
def test_queue_depth_missing_treated_as_zero():
    fleet = [
        {"runner_id": "r1", "verdict": "alive", "age_seconds": 10,
         "pair_filters": [], "timeframe_filters": []},
        {"runner_id": "r2", "verdict": "alive", "age_seconds": 10,
         "pair_filters": [], "timeframe_filters": [],
         "last_snapshot": {"queue_depth": "bogus"}},
    ]
    d = rr.decide("EURUSD", "H1", fleet, policy=rr.POLICY_LEAST_BUSY)
    # Both treated as queue=0; tiebreaker is runner_id ascending → r1
    assert d["runner_id"] == "r1"


def test_decide_returns_dict_with_required_keys():
    fleet = [_runner(rid="r1")]
    d = rr.decide("EURUSD", "H1", fleet)
    for k in ("runner_id", "policy_used", "candidates_considered", "reason"):
        assert k in d


# ── Sticky picks matched fresh > matched stale ───────────────────────
def test_sticky_only_considers_filter_matches_then_tiebreaks():
    fleet = [
        _runner(rid="match-old", pair_filters=["EURUSD"], timeframe_filters=["H1"], age_seconds=900),
        _runner(rid="match-new", pair_filters=["EURUSD"], timeframe_filters=["H1"], age_seconds=10),
        _runner(rid="nomatch-fresh", pair_filters=["BTCUSD"], timeframe_filters=["H1"], age_seconds=1),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] == "match-new"
    assert d["candidates_considered"] == 2


# ── Tie-break determinism on equal age + queue → runner_id ascending ──
def test_full_tiebreak_on_runner_id():
    fleet = [
        _runner(rid="z1", pair_filters=["EURUSD"], timeframe_filters=["H1"]),
        _runner(rid="a1", pair_filters=["EURUSD"], timeframe_filters=["H1"]),
        _runner(rid="m1", pair_filters=["EURUSD"], timeframe_filters=["H1"]),
    ]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_id"] == "a1"


# ── Acceptance shape: matched returns runner_name + verdict ──────────
def test_acceptance_shape_includes_name_and_verdict():
    fleet = [_runner(rid="r1", name="winrunner-01")]
    d = rr.decide("EURUSD", "H1", fleet)
    assert d["runner_name"] == "winrunner-01"
    assert d["verdict"] == "alive"
    assert d["reason"] == "matched"


# ── Reasons exposed as constants — guard against accidental rename ──
def test_reason_constants_stable():
    assert rr.REASON_NO_RUNNERS         == "no_runners_registered"
    assert rr.REASON_NO_ALIVE_RUNNERS   == "no_alive_runner_in_fleet"
    assert rr.REASON_NO_AFFINITY_MATCH  == "no_runner_matches_pair_timeframe"
    assert rr.DEFAULT_POLICY            == rr.POLICY_STICKY_PAIR_TF


# ── Multiple candidate counts surfaced honestly ───────────────────────
def test_candidates_considered_reflects_alive_count_in_least_busy():
    fleet = [
        _runner(rid="a", queue_depth=5),
        _runner(rid="b", queue_depth=2),
        _runner(rid="c", verdict="dead"),
    ]
    d = rr.decide("EURUSD", "H1", fleet, policy=rr.POLICY_LEAST_BUSY)
    assert d["candidates_considered"] == 2
    assert d["runner_id"] == "b"
