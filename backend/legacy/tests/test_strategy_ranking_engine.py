"""
Phase 8.6 — Strategy Ranking Engine tests.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engines.strategy_ranking_engine import rank_strategies, rank_summary


def _make(
    sid: str,
    verdict: str,
    stability: float = 60,
    overfit: float = 20,
    ev: float = 200,
    prob: float = 60,
) -> dict:
    return {
        "strategy_id": sid,
        "decision": {"verdict": verdict, "confidence": 70, "reason": ""},
        "validation_report": {
            "stability_score": {"score": stability},
            "overfit_score": {"score": overfit},
        },
        "expected_value": {"expected_value": ev, "ev_grade": "good" if ev > 0 else "negative"},
        "pass_probability": prob,
    }


def test_trade_outranks_risky_outranks_reject():
    strategies = [
        _make("risky_mid", "RISKY", stability=55, overfit=30, ev=100, prob=55),
        _make("trade_best", "TRADE", stability=75, overfit=15, ev=400, prob=70),
        _make("reject_bad", "REJECT", stability=10, overfit=90, ev=-200, prob=20),
    ]
    ranked = rank_strategies(strategies, top_n=5)
    # REJECT excluded by default
    ids = [r["strategy_id"] for r in ranked]
    assert "reject_bad" not in ids
    assert ranked[0]["strategy_id"] == "trade_best"
    assert ranked[1]["strategy_id"] == "risky_mid"
    assert all(r["rank"] == i + 1 for i, r in enumerate(ranked))


def test_rejects_can_be_included_explicitly():
    strategies = [
        _make("a", "TRADE", ev=300),
        _make("b", "REJECT", overfit=90, ev=-100),
    ]
    ranked = rank_strategies(strategies, include_rejects=True)
    ids = [r["strategy_id"] for r in ranked]
    assert "b" in ids


def test_top_n_is_respected():
    pool = [_make(f"s{i}", "TRADE", stability=60 + i, ev=100 + 10 * i) for i in range(10)]
    ranked = rank_strategies(pool, top_n=3)
    assert len(ranked) == 3
    # Sorted descending
    scores = [r["score"] for r in ranked]
    assert scores == sorted(scores, reverse=True)


def test_score_range_and_breakdown():
    ranked = rank_strategies([_make("x", "TRADE", stability=80, overfit=10, ev=500, prob=70)])
    r = ranked[0]
    assert 0 <= r["score"] <= 100
    assert set(r["breakdown"].keys()) == {"verdict", "stability", "probability", "ev", "overfit_penalty"}
    assert r["breakdown"]["verdict"] == 35.0  # TRADE * 0.35
    assert r["breakdown"]["overfit_penalty"] <= 0


def test_tolerant_to_missing_fields():
    sparse = [
        {"strategy_id": "minimal"},                   # nothing known
        {"strategy_id": "only_id", "pass_probability": 75},
        {"id": "alt_key", "decision": "TRADE"},       # string verdict + alt id
    ]
    ranked = rank_strategies(sparse, top_n=5)
    ids = {r["strategy_id"] for r in ranked}
    # 'minimal' and 'only_id' default to RISKY (included), 'alt_key' is TRADE
    assert ids == {"minimal", "only_id", "alt_key"}
    # TRADE should rank first even without other signals
    assert ranked[0]["strategy_id"] == "alt_key"


def test_rank_summary_counts_verdicts():
    pool = [
        _make("a", "TRADE"), _make("b", "TRADE"),
        _make("c", "RISKY"),
        _make("d", "REJECT"),
    ]
    s = rank_summary(pool, top_n=5)
    assert s["total_candidates"] == 4
    assert s["verdict_counts"] == {"TRADE": 2, "RISKY": 1, "REJECT": 1}
    # REJECT excluded from ranked by default
    assert all(r["verdict"] != "REJECT" for r in s["ranked"])


def test_empty_input_returns_empty_list():
    assert rank_strategies([]) == []


if __name__ == "__main__":
    test_trade_outranks_risky_outranks_reject()
    test_rejects_can_be_included_explicitly()
    test_top_n_is_respected()
    test_score_range_and_breakdown()
    test_tolerant_to_missing_fields()
    test_rank_summary_counts_verdicts()
    test_empty_input_returns_empty_list()
    print("strategy_ranking_engine: ALL TESTS PASSED")
