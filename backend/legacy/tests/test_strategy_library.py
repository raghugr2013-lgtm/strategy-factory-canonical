"""
Phase 11 — Strategy Library tests.
Uses mongomock/mocked db unavailable here; we verify pure helpers.
For DB paths we rely on the real Mongo service (same approach as Phase 10).
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from engines.strategy_library import (
    save_strategy, list_saved, delete_saved,
    _fingerprint, _is_eligible, _extract_core,
    RISKY_MIN_SCORE, COLLECTION,
)
from engines.db import get_db


def _card(verdict="TRADE", status="SAFE", score=60.0, pair="EURUSD",
          tf="H1", style="trend-following", sl=20, tp=35):
    return {
        "strategy_id": "cand_1",
        "pair": pair, "timeframe": tf, "style": style,
        "score": score,
        "verdict": verdict,
        "status": status,
        "pass_probability": 65,
        "confidence": 70,
        "reason": "test",
        "parameters": {"sl_pips": sl, "tp_pips": tp, "fast_period": 8},
        "strategy_text": f"EMA crossover {pair} {tf} sl={sl} tp={tp}",
        "prop_firm_panel": {
            "status": status, "pass_probability": 65,
            "max_drawdown": 3.5, "daily_drawdown": 1.2,
            "consistency_score": 70, "recommendation": "OK",
            "violations": {"daily_dd": 0, "max_dd": 0, "consistency": 0,
                           "profit_target": 0, "min_days": 0},
        },
        "decision": {"verdict": verdict, "confidence": 70, "reason": "ok"},
        "backtest": {"total_return_pct": 5.0, "profit_factor": 1.4,
                      "win_rate": 52.0, "total_trades": 40,
                      "max_drawdown_pct": 3.5},
    }


# ── Pure helper tests ─────────────────────────────────────────────────

def test_eligible_trade():
    allowed, _ = _is_eligible("TRADE", 10, "SAFE")
    assert allowed is True


def test_eligible_strong_risky_via_pass_prob():
    # score>=45 AND pass_probability>=50
    allowed, reason = _is_eligible(
        "RISKY", 50, "RISKY", pass_probability=60, stability_score=40,
    )
    assert allowed is True, reason


def test_eligible_strong_risky_via_stability():
    # score>=45 AND stability_score>=50
    allowed, reason = _is_eligible(
        "RISKY", 50, "RISKY", pass_probability=30, stability_score=55,
    )
    assert allowed is True, reason


def test_not_eligible_risky_both_unstable():
    # score>=45 but BOTH pp<50 AND stab<50
    allowed, reason = _is_eligible(
        "RISKY", 50, "RISKY", pass_probability=30, stability_score=40,
    )
    assert allowed is False
    assert "unstable" in reason.lower()


def test_not_eligible_weak_risky():
    allowed, reason = _is_eligible(
        "RISKY", RISKY_MIN_SCORE - 1, "RISKY",
        pass_probability=90, stability_score=90,
    )
    assert allowed is False
    assert "weak" in reason.lower()


def test_not_eligible_reject():
    allowed, _ = _is_eligible("REJECT", 90, "SAFE",
                                pass_probability=90, stability_score=90)
    assert allowed is False


def test_not_eligible_prop_fail():
    allowed, reason = _is_eligible(
        "TRADE", 90, "FAIL", pass_probability=80, stability_score=80,
    )
    assert allowed is False
    assert "FAIL" in reason


def test_eligible_risky_missing_probability_but_stable():
    """Missing pass_probability defaults to 0 — stability alone saves."""
    allowed, _ = _is_eligible(
        "RISKY", 50, "RISKY", pass_probability=None, stability_score=60,
    )
    assert allowed is True


def test_not_eligible_risky_missing_both_signals():
    """Missing both → default 0 → reject."""
    allowed, _ = _is_eligible(
        "RISKY", 50, "RISKY", pass_probability=None, stability_score=None,
    )
    assert allowed is False


def test_fingerprint_stable():
    fp1 = _fingerprint("EURUSD", "H1", "trend", {"sl_pips": 20, "tp_pips": 35},
                       "EMA crossover text")
    fp2 = _fingerprint("eurusd", "h1", "TREND", {"sl_pips": 20, "tp_pips": 35},
                       "EMA crossover text")
    assert fp1 == fp2


def test_fingerprint_near_duplicate_collapse():
    """±10% param changes collapse to the same fingerprint."""
    fp1 = _fingerprint("EURUSD", "H1", "trend", {"sl_pips": 20}, "text")
    fp2 = _fingerprint("EURUSD", "H1", "trend", {"sl_pips": 21}, "text")
    # 20 and 21 bucketed at 10% band → same bucket
    assert fp1 == fp2


def test_fingerprint_different_pair_differs():
    fp1 = _fingerprint("EURUSD", "H1", "trend", {"sl": 20}, "text")
    fp2 = _fingerprint("GBPUSD", "H1", "trend", {"sl": 20}, "text")
    assert fp1 != fp2


def test_extract_core_from_dashboard_card():
    core = _extract_core(_card())
    assert core["pair"] == "EURUSD"
    assert core["verdict"] == "TRADE"
    assert core["prop_status"] == "SAFE"
    assert core["pass_probability"] == 65
    assert core["max_drawdown_pct"] == 3.5


def test_extract_core_pulls_stability_from_walk_forward():
    """stability_score must come from validation_report.walk_forward.aggregate."""
    from engines.strategy_library import _extract_core
    payload = {
        **_card(),
        "validation_report": {
            "walk_forward": {
                "success": True,
                "aggregate": {"stability_score": 67.5,
                              "oos_avg_return_pct": 2.1,
                              "oos_profitable_ratio": 0.8,
                              "mean_degradation_pct": 12.0},
            },
        },
    }
    core = _extract_core(payload)
    assert core["stability_score"] == 67.5


def test_extract_core_stability_falls_back_to_composed_report():
    payload = {
        **_card(),
        "validation_report": {"stability_score": {"score": 58.0}},
    }
    core = _extract_core(payload)
    assert core["stability_score"] == 58.0


def test_extract_core_stability_defaults_none_when_missing():
    payload = {**_card(), "validation_report": None}
    core = _extract_core(payload)
    # _card() has consistency_score=70 in prop_firm_panel which becomes final fallback
    assert core["stability_score"] == 70.0


# ── Integration: save() honours the refined rule end-to-end ──────────

def test_save_risky_with_pass_prob_and_weak_stability_passes():
    import asyncio
    async def _run():
        payload = _card(verdict="RISKY", status="RISKY", score=55)
        payload["prop_firm_panel"] = {
            "status": "RISKY", "pass_probability": 62, "consistency_score": 40,
            "max_drawdown": 4.0, "daily_drawdown": 1.5,
            "violations": {"daily_dd": 0, "max_dd": 0, "consistency": 0,
                           "profit_target": 0, "min_days": 0},
        }
        res = await save_strategy(payload, source="test")
        assert res["status"] == "saved", res
    asyncio.get_event_loop().run_until_complete(_run())


def test_save_risky_with_weak_both_signals_rejected():
    import asyncio
    async def _run():
        payload = _card(verdict="RISKY", status="RISKY", score=55)
        payload["prop_firm_panel"] = {
            "status": "RISKY", "pass_probability": 25, "consistency_score": 30,
            "max_drawdown": 4.0, "daily_drawdown": 1.5,
            "violations": {"daily_dd": 0, "max_dd": 0, "consistency": 0,
                           "profit_target": 0, "min_days": 0},
        }
        res = await save_strategy(payload, source="test")
        assert res["status"] == "rejected", res
        assert "unstable" in res["reason"].lower()
    asyncio.get_event_loop().run_until_complete(_run())


# ── DB round-trip tests ───────────────────────────────────────────────

def _clean():
    async def _run():
        db = get_db()
        await db[COLLECTION].delete_many({"source": {"$in": ["test"]}})
    asyncio.get_event_loop().run_until_complete(_run())


def test_db_save_and_list_and_delete():
    _clean()

    async def _run():
        # Save one TRADE
        card = _card()
        res1 = await save_strategy(card, source="test")
        assert res1["status"] == "saved"
        assert res1["strategy_id"]

        # Save same fingerprint → duplicate
        res2 = await save_strategy(card, source="test")
        assert res2["status"] == "duplicate"
        assert res2["strategy_id"] == res1["strategy_id"]

        # Save near-duplicate (param within bucket)
        card2 = _card(sl=21)
        res3 = await save_strategy(card2, source="test")
        assert res3["status"] == "duplicate"

        # Save a REJECT → rejected
        bad = _card(verdict="REJECT", status="FAIL")
        res4 = await save_strategy(bad, source="test")
        assert res4["status"] == "rejected"

        # List should contain 1 saved
        items = await list_saved(pair="EURUSD", limit=50)
        test_items = [i for i in items if i.get("source") == "test"]
        assert len(test_items) == 1

        # Delete
        ok = await delete_saved(res1["strategy_id"])
        assert ok is True

    asyncio.get_event_loop().run_until_complete(_run())


if __name__ == "__main__":
    test_eligible_trade()
    test_eligible_strong_risky()
    test_not_eligible_weak_risky()
    test_not_eligible_reject()
    test_not_eligible_prop_fail()
    test_fingerprint_stable()
    test_fingerprint_near_duplicate_collapse()
    test_fingerprint_different_pair_differs()
    test_extract_core_from_dashboard_card()
    test_db_save_and_list_and_delete()
    print("strategy_library: ALL TESTS PASSED")
