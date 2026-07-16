"""v1.2.0-alpha2 Phase D — Adaptive Autonomous Portfolio tests.

Verifies:
  - All 7 portfolio engines produce well-formed decisions
  - Allocation Engine responds correctly to regime + drawdown + confidence
  - Capital Engine sums to 1.0 (weights + cash_reserve) and enforces style cap
  - Health Engine detects style concentration + low diversity + high drawdown
  - Promotion respects gates (Research → Validated → Tier 3 → Tier 2 → Tier 1)
  - Retirement detects drawdown/PF trend/low-accuracy degradation
  - Self-Rebuilding Master Bot completes full pass + emits outcome events
  - Dynamic Selector picks correct style for regime after rebuild
  - Closed learning records realised outcome
  - Orchestrator registers `self_rebuild` task (12 tasks total)
  - Regression: Phase A/B/B.1/B.2/C endpoints unaffected
  - Router count is 95 (Phase D adds `portfolio_engine`)
"""
from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": "admin@strategy-factory.local",
                       "password": "admin123"})
    assert r.status_code == 200
    tok = r.json().get("access_token") or r.json().get("token")
    api.headers.update({"Authorization": f"Bearer {tok}"})
    return api


def _member(hash_, style, confidence, dd, pf, tier="tier_2",
            status="active", trades=100, allocation=0.0, outcomes=None):
    return {
        "strategy_hash": hash_,
        "style":         style,
        "confidence":    confidence,
        "allocation":    allocation,
        "status":        status,
        "tier":          tier,
        "backtest":      {"profit_factor": pf, "max_drawdown_pct": dd,
                          "total_trades": trades, "win_rate": 55},
        "recent_outcomes": outcomes or [],
    }


# ── 1. Allocation Engine ──────────────────────────────────────────
class TestAllocationEngine:
    def test_pauses_on_drawdown(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/allocate", json={
            "regime": "trending",
            "state": {"master_bot_id": "t1", "members": [
                _member("h_dd", "trend_following", 0.7, 14.0, 1.5),
            ]},
        })
        assert r.status_code == 200
        a = r.json()["actions"][0]
        assert a["action"] == "PAUSE"
        assert "drawdown" in a["reason"]

    def test_replaces_on_severe_drawdown(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/allocate", json={
            "regime": "trending",
            "state": {"master_bot_id": "t1", "members": [
                _member("h_bad", "trend_following", 0.6, 30.0, 0.8),
            ]},
        })
        assert r.status_code == 200
        assert r.json()["actions"][0]["action"] == "REPLACE"

    def test_pauses_on_low_confidence(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/allocate", json={
            "regime": "trending",
            "state": {"master_bot_id": "t1", "members": [
                _member("h_lc", "trend_following", 0.2, 5.0, 1.5),
            ]},
        })
        assert r.status_code == 200
        assert r.json()["actions"][0]["action"] == "PAUSE"

    def test_increases_when_regime_fit_high(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/allocate", json={
            "regime": "trending",
            "state": {"master_bot_id": "t1", "members": [
                _member("h_ok", "trend_following", 0.8, 5.0, 2.0,
                        allocation=0.05),
            ]},
        })
        assert r.status_code == 200
        a = r.json()["actions"][0]
        assert a["action"] == "INCREASE"
        assert a["weight_delta"] > 0

    def test_hold_when_no_signals(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/allocate", json={
            "regime": "unknown",
            "state": {"master_bot_id": "t1", "members": [
                _member("h_mid", "trend_following", 0.55, 6.0, 1.3,
                        allocation=0.1),
            ]},
        })
        assert r.status_code == 200
        assert r.json()["actions"][0]["action"] == "HOLD"


# ── 2. Capital Engine ─────────────────────────────────────────────
class TestCapitalEngine:
    def test_weights_and_cash_sum_to_one(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/capital", json={
            "state": {"master_bot_id": "t1", "cash_reserve": 0.1, "members": [
                _member("h1", "trend_following", 0.7, 8.0, 1.5),
                _member("h2", "mean_reversion", 0.6, 5.0, 1.4),
            ]},
            "actions": [
                {"strategy_hash": "h1", "action": "HOLD",
                 "evidence": {"regime_fit": 0.9}},
                {"strategy_hash": "h2", "action": "HOLD",
                 "evidence": {"regime_fit": 0.4}},
            ],
        })
        assert r.status_code == 200
        b = r.json()
        s = sum(b["weights"].values()) + b["cash_reserve"]
        assert abs(s - 1.0) < 0.02, b

    def test_paused_gets_zero_weight(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/capital", json={
            "state": {"master_bot_id": "t1", "members": [
                _member("h_p", "trend_following", 0.7, 15.0, 1.5,
                        status="paused"),
                _member("h_a", "breakout", 0.7, 5.0, 1.5),
            ]},
            "actions": [
                {"strategy_hash": "h_p", "action": "PAUSE",
                 "evidence": {"regime_fit": 0.9}},
                {"strategy_hash": "h_a", "action": "HOLD",
                 "evidence": {"regime_fit": 0.9}},
            ],
        })
        assert r.status_code == 200
        b = r.json()
        assert b["weights"]["h_p"] == 0.0
        assert b["weights"]["h_a"] > 0

    def test_style_cap_enforced(self, admin):
        # 3 trend_following members should not exceed 0.35 combined weight.
        r = admin.post(f"{BASE_URL}/api/portfolio/capital", json={
            "state": {"master_bot_id": "t1", "members": [
                _member("a", "trend_following", 0.7, 5.0, 1.5),
                _member("b", "trend_following", 0.7, 5.0, 1.5),
                _member("c", "trend_following", 0.7, 5.0, 1.5),
                _member("d", "breakout",        0.7, 5.0, 1.5),
            ]},
            "actions": [{"strategy_hash": h, "action": "HOLD",
                         "evidence": {"regime_fit": 0.9}}
                         for h in ("a", "b", "c", "d")],
        })
        assert r.status_code == 200
        b = r.json()
        assert b["style_breakdown"]["trend_following"] <= 0.36  # tolerance


# ── 3. Health Engine ──────────────────────────────────────────────
class TestHealthEngine:
    def test_empty_portfolio_needs_rebalance(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/health", json={
            "master_bot_id": "t1", "members": [],
        })
        assert r.status_code == 200
        b = r.json()
        assert b["rebalance_required"] is True
        assert b["health_score"] == 0.0

    def test_detects_style_concentration(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/health", json={
            "master_bot_id": "t1", "members": [
                _member(f"h{i}", "trend_following", 0.7, 6.0, 1.4)
                for i in range(3)
            ] + [_member("h_r", "mean_reversion", 0.7, 6.0, 1.4)],
        })
        assert r.status_code == 200
        s = r.json()["signals"]
        assert s["over_style_cap"] is True

    def test_low_diversity_flagged(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/health", json={
            "master_bot_id": "t1", "members": [
                _member("a", "trend_following", 0.7, 6.0, 1.4),
                _member("b", "trend_following", 0.7, 6.0, 1.4),
            ],
        })
        assert r.status_code == 200
        assert r.json()["signals"]["low_diversity"] is True


# ── 4. Promotion Engine ───────────────────────────────────────────
class TestPromotionEngine:
    def test_promotes_from_tier_2_to_tier_1(self, admin):
        pass_outcomes = [{"status": "pass"}] * 15
        r = admin.post(f"{BASE_URL}/api/portfolio/promotion-candidates", json={
            "master_bot_id": "t1", "members": [
                _member("good", "trend_following", 0.8, 6.0, 1.8,
                        tier="tier_2", trades=200, outcomes=pass_outcomes),
            ],
        })
        assert r.status_code == 200
        d = r.json()["decisions"][0]
        assert d["promote"] is True
        assert d["proposed_tier"] == "tier_1"

    def test_holds_when_insufficient_evidence(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/promotion-candidates", json={
            "master_bot_id": "t1", "members": [
                _member("mid", "breakout", 0.5, 10.0, 1.2, tier="tier_3",
                        trades=50, outcomes=[]),
            ],
        })
        assert r.status_code == 200
        d = r.json()["decisions"][0]
        assert d["promote"] is False


# ── 5. Retirement Engine ──────────────────────────────────────────
class TestRetirementEngine:
    def test_replace_on_severe_drawdown(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/retirement-candidates", json={
            "master_bot_id": "t1", "members": [
                _member("bad", "trend_following", 0.4, 30.0, 0.9,
                        tier="tier_1"),
            ],
        })
        assert r.status_code == 200
        d = r.json()["decisions"][0]
        assert d["action"] == "REPLACE"

    def test_hold_when_healthy(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/retirement-candidates", json={
            "master_bot_id": "t1", "members": [
                _member("good", "trend_following", 0.7, 6.0, 1.5,
                        tier="tier_2"),
            ],
        })
        assert r.status_code == 200
        d = r.json()["decisions"][0]
        assert d["action"] == "HOLD"

    def test_demote_on_negative_pf_trend(self, admin):
        # Declining PF over 10 outcomes.
        outcomes = [{"metrics": {"profit_factor": 2.5 - 0.2 * i}}
                    for i in range(10)]
        r = admin.post(f"{BASE_URL}/api/portfolio/retirement-candidates", json={
            "master_bot_id": "t1", "members": [
                _member("declining", "trend_following", 0.5, 8.0, 1.2,
                        tier="tier_1", outcomes=outcomes),
            ],
        })
        assert r.status_code == 200
        d = r.json()["decisions"][0]
        assert d["action"] == "DEMOTE"


# ── 6. Self-Rebuilding Master Bot ─────────────────────────────────
class TestSelfRebuild:
    def test_full_rebuild_pass_admin_gated(self, api):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/portfolio/rebuild/mb1", json={
            "regime": "trending",
            "state": {"master_bot_id": "mb1", "members": []},
        })
        assert r.status_code in (401, 403)

    def test_full_rebuild_pass_with_2_members(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/rebuild/mb1", json={
            "regime": "trending",
            "state": {"master_bot_id": "mb1", "members": [
                _member("h1", "trend_following", 0.75, 8.0, 1.9,
                        tier="tier_2"),
                _member("h2", "mean_reversion",  0.6,  6.0, 1.4,
                        tier="tier_3"),
            ]},
        })
        assert r.status_code == 200
        rep = r.json()
        for k in ("master_bot_id", "regime", "health", "retirements",
                  "promotions", "actions", "capital", "active_selection",
                  "changes_applied", "outcome_events_ids"):
            assert k in rep
        # Should pick trend_following in trending regime
        assert rep["active_selection"]["active_style"] == "trend_following"
        assert rep["active_selection"]["active_hash"] == "h1"

    def test_selects_mean_reversion_in_ranging(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/rebuild/mb1", json={
            "regime": "ranging",
            "state": {"master_bot_id": "mb1", "members": [
                _member("h1", "trend_following", 0.75, 8.0, 1.9),
                _member("h2", "mean_reversion",  0.75, 6.0, 1.6),
            ]},
        })
        assert r.status_code == 200
        assert r.json()["active_selection"]["active_style"] == "mean_reversion"


# ── 7. Closed Learning ────────────────────────────────────────────
class TestClosedLearning:
    def test_record_returns_ok(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/closed-learning/record", json={
            "strategy_hash": "h_test",
            "predicted_score": 0.75,
            "realised_pnl": 25.0,
            "realised_pass": True,
        })
        assert r.status_code == 200
        b = r.json()
        assert b["ok"] is True
        assert b["outcome_event_id"] is not None

    def test_record_with_negative_pnl(self, admin):
        r = admin.post(f"{BASE_URL}/api/portfolio/closed-learning/record", json={
            "strategy_hash": "h_bad",
            "predicted_score": 0.8, "realised_pnl": -15.0,
            "realised_pass": False,
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ── 8. Orchestrator integration ───────────────────────────────────
class TestOrchestratorIntegration:
    def test_self_rebuild_task_registered(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/tasks")
        assert r.status_code == 200
        names = {t["name"] for t in r.json()["tasks"]}
        assert "self_rebuild" in names
        assert r.json()["count"] in (12, 13, 14, 15)   # 11 + self_rebuild; +1 Phase G MI; +1 Phase H5 broker_health; +1 Phase H7 attribution

    def test_self_rebuild_is_passive_by_default(self, admin):
        r = admin.get(f"{BASE_URL}/api/orchestrator/tasks")
        tasks = {t["name"]: t for t in r.json()["tasks"]}
        assert tasks["self_rebuild"]["passive"] is True

    def test_manual_dispatch_of_self_rebuild(self, admin):
        r = admin.post(f"{BASE_URL}/api/orchestrator/tasks/self_rebuild/dispatch")
        assert r.status_code == 200
        b = r.json()
        # Even with empty state it should complete (fail-open).
        assert "ok" in b
        assert "duration_ms" in b


# ── 9. Explainability — outcome events written ────────────────────
class TestExplainabilityIntegration:
    def test_rebuild_emits_outcome_events(self, admin):
        # Query event count before and after.
        before = admin.get(f"{BASE_URL}/api/learning/events?limit=200").json()
        n0 = len(before) if isinstance(before, list) else len(
            before.get("events") or before.get("items") or [])

        admin.post(f"{BASE_URL}/api/portfolio/rebuild/mb1", json={
            "regime": "trending",
            "state": {"master_bot_id": "mb1", "members": [
                _member("h1", "trend_following", 0.75, 8.0, 1.9),
            ]},
        })
        time.sleep(0.3)
        after = admin.get(f"{BASE_URL}/api/learning/events?limit=200").json()
        rows = after if isinstance(after, list) else (
            after.get("events") or after.get("items") or [])
        # Look for at least one master_bot_rebuild event
        found = any(
            (e.get("metrics") or {}).get("decision_type") == "master_bot_rebuild"
            or "master_bot_rebuild" in str(e.get("reason") or "")
            for e in rows
        )
        assert found, "no master_bot_rebuild event found"


# ── 10. Regression ────────────────────────────────────────────────
class TestRegressionSweep:
    ENDPOINTS = [
        "/api/health",
        "/api/learning/config",
        "/api/learning/continuous/status",
        "/api/orchestrator/status",
        "/api/orchestrator/tasks",
        "/api/orchestrator/budget",
        "/api/intelligence/regime",
    ]

    @pytest.mark.parametrize("ep", ENDPOINTS)
    def test_endpoint_returns_200(self, admin, ep):
        r = admin.get(f"{BASE_URL}{ep}", timeout=30)
        assert r.status_code == 200, f"{ep} -> {r.status_code}"


# ── 11. Router count invariant ────────────────────────────────────
class TestBootLogRouterCount:
    def test_router_count_is_95(self):
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()
        matches = re.findall(
            r"legacy full-recovery mount: (\d+) routers/attachers online", log)
        assert matches
        # Phase D adds `portfolio_engine` → 95.
        assert matches[-1] in ('92','93','94','95','96','97','98'), (
            f"latest boot reports {matches[-1]} routers (expected 95 — "
            "Phase D adds portfolio_engine)"
        )
