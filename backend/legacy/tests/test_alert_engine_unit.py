"""Direct engine-level tests for alert_engine: qualifies() + dedup."""
import asyncio
import os
import time
import pytest
from dotenv import load_dotenv

# Load backend .env so DB_NAME/MONGO_URL are set for direct engine calls
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from engines import alert_engine  # noqa: E402


CFG_BASE = {
    "alerts_enabled": True,
    "webhook_url": "https://httpbin.org/post",
    "min_pf": 1.2, "min_runs": 3, "max_drawdown": 0.12,
    "alert_min_pass_probability": 0.6,
    "alert_min_env_confidence": 0.6,
}


def test_qualifies_pass():
    s = {"profit_factor": 1.5, "runs": 5, "max_drawdown_pct": 8.0,
         "pass_probability": 0.7, "environment_confidence": 0.7}
    assert alert_engine.qualifies(s, CFG_BASE) is True


def test_qualifies_fail_on_pf():
    s = {"profit_factor": 1.0, "runs": 5, "max_drawdown_pct": 8.0,
         "pass_probability": 0.7, "environment_confidence": 0.7}
    assert alert_engine.qualifies(s, CFG_BASE) is False


def test_qualifies_fail_on_pass_prob():
    s = {"profit_factor": 1.5, "runs": 5, "max_drawdown_pct": 8.0,
         "pass_probability": 0.5, "environment_confidence": 0.7}
    assert alert_engine.qualifies(s, CFG_BASE) is False


def test_qualifies_fail_on_env_conf():
    s = {"profit_factor": 1.5, "runs": 5, "max_drawdown_pct": 8.0,
         "pass_probability": 0.7, "environment_confidence": 0.5}
    assert alert_engine.qualifies(s, CFG_BASE) is False


def test_qualifies_fail_on_drawdown():
    s = {"profit_factor": 1.5, "runs": 5, "max_drawdown_pct": 20.0,
         "pass_probability": 0.7, "environment_confidence": 0.7}
    assert alert_engine.qualifies(s, CFG_BASE) is False


def test_dedup_skips_second_with_same_hash_and_run():
    """Second send_alert with same strategy_hash + run_id must return
    reason='duplicate' when force=False."""
    unique_hash = f"TEST-dedup-{int(time.time()*1000)}"
    run_id = f"TEST-run-{int(time.time()*1000)}"
    strat = {
        "strategy_hash": unique_hash,
        "strategy_text": "test strat",
        "pair": "EURUSD", "timeframe": "H1",
        "profit_factor": 1.5, "max_drawdown_pct": 8.0,
        "pass_probability": 0.7, "environment_confidence": 0.7,
    }

    async def _go():
        r1 = await alert_engine.send_alert(strat, CFG_BASE, run_id=run_id, force=False)
        r2 = await alert_engine.send_alert(strat, CFG_BASE, run_id=run_id, force=False)
        return r1, r2

    r1, r2 = asyncio.run(_go())
    assert r1.get("sent") is True, f"first send expected success: {r1}"
    assert r2.get("sent") is False
    assert r2.get("reason") == "duplicate", f"expected duplicate, got {r2}"


def test_build_payload_shape():
    strat = {
        "strategy_text": "foo", "pair": "GBPUSD", "timeframe": "H4",
        "profit_factor": 1.52, "max_drawdown_pct": 8.0,
        "pass_probability": 0.72, "safe_risk": 0.5, "firm": "FTMO",
        "metrics": {"total_trades": 42}, "environment_confidence": 0.75,
    }
    p = alert_engine.build_payload(strat)
    for k in ["strategy", "pair", "timeframe", "pf", "dd",
              "pass_probability", "safe_risk", "environment", "firm"]:
        assert k in p
    assert p["pair"] == "GBPUSD"
    assert p["pf"] == pytest.approx(1.52, rel=1e-3)
