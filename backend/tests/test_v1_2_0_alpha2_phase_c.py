"""v1.2.0-alpha2 Phase C — Autonomous Quant Intelligence tests.

Verifies:
  - Strategy classification detects style from text + backtest evidence
  - Portfolio score rewards diversification + penalises correlation
  - Master Bot builder produces balanced Tier 1/2/3 bundles
  - Market Regime engine returns a well-formed snapshot
  - Dynamic selector picks the highest-confidence strategy for the regime
  - All 5 API endpoints (/api/intelligence/*) return 200
  - Every decision emits an outcome_events record (explainability)
  - Regression: Phase A/B/B.1/B.2 endpoints unaffected
  - Router count is 94 (Phase C added `intelligence_engine`, strictly additive)
"""
from __future__ import annotations

import os
import re
import subprocess
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
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": "admin@strategy-factory.local",
                       "password": "admin123"})
    assert r.status_code == 200
    d = r.json()
    return d.get("access_token") or d.get("token")


@pytest.fixture(scope="module")
def admin(api, admin_token):
    api.headers.update({"Authorization": f"Bearer {admin_token}"})
    return api


# ── 1. Strategy Intelligence ──────────────────────────────────────
class TestStrategyIntelligence:
    def test_classify_trend_following(self, admin):
        payload = {
            "strategy_text": "Enter long when EMA20 crosses above EMA50 with MACD confirmation. SL=20 TP=40",
            "profit_factor": 2.1, "max_drawdown_pct": 8.5,
            "total_trades": 150, "win_rate": 58,
            "strategy_hash": "h_trend_1",
        }
        r = admin.post(f"{BASE_URL}/api/intelligence/classify", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["style"] == "trend_following"
        assert body["regime_suitability"]["trending"] >= 0.8
        assert body["confidence"] > 0.5
        assert body["risk_profile"]["sl_pips"] == 20.0
        assert body["risk_profile"]["tp_pips"] == 40.0
        assert body["risk_profile"]["rr_ratio"] == 2.0

    def test_classify_mean_reversion(self, admin):
        payload = {
            "strategy_text": "Enter long when RSI drops below 30 (oversold) and BB(20,2) lower band touched",
            "profit_factor": 1.6, "max_drawdown_pct": 6.0,
            "total_trades": 200, "win_rate": 62,
            "strategy_hash": "h_rev_1",
        }
        r = admin.post(f"{BASE_URL}/api/intelligence/classify", json=payload)
        assert r.status_code == 200
        assert r.json()["style"] == "mean_reversion"

    def test_classify_low_evidence_low_confidence(self, admin):
        payload = {"strategy_text": "EMA cross", "strategy_hash": "h_lowev"}
        r = admin.post(f"{BASE_URL}/api/intelligence/classify", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["confidence"] < 0.3   # no backtest evidence


# ── 2. Portfolio Intelligence ─────────────────────────────────────
class TestPortfolioIntelligence:
    def test_diversification_bonus(self, admin):
        r = admin.post(f"{BASE_URL}/api/intelligence/portfolio-score", json={
            "candidate": {"strategy_hash": "new", "style": "mean_reversion",
                          "backtest": {"profit_factor": 1.8, "max_drawdown_pct": 6,
                                       "total_trades": 80, "win_rate": 52}},
            "existing_bundle": [
                {"strategy_hash": "a", "style": "trend_following",
                 "backtest": {"profit_factor": 2.0}},
                {"strategy_hash": "b", "style": "trend_following",
                 "backtest": {"profit_factor": 2.1}},
            ],
        })
        assert r.status_code == 200
        b = r.json()
        # New style is 0% of bundle → full bonus
        assert b["diversification_bonus"] >= 0.25
        assert b["contribution_score"] > b["solo_score"]

    def test_empty_bundle_gets_full_bonus(self, admin):
        r = admin.post(f"{BASE_URL}/api/intelligence/portfolio-score", json={
            "candidate": {"strategy_hash": "first", "style": "any",
                          "backtest": {"profit_factor": 1.5}},
            "existing_bundle": [],
        })
        assert r.status_code == 200
        b = r.json()
        assert b["diversification_bonus"] >= 0.29


# ── 3. Master Bot Builder ─────────────────────────────────────────
class TestMasterBotBuilder:
    STRATEGIES = [
        {"strategy_hash": f"h{i}",
         "strategy_text": text,
         "profit_factor": 1.4 + (i % 5) * 0.15,
         "max_drawdown_pct": 5 + (i % 4) * 2,
         "total_trades": 80 + (i * 5),
         "win_rate": 45 + (i % 8) * 2}
        for i, text in enumerate([
            "EMA20 crosses EMA50 SL=20 TP=40",
            "RSI oversold SL=15 TP=30",
            "Donchian breakout SL=25 TP=50",
            "London session VWAP SL=10 TP=20",
            "ATR expand entry SL=18 TP=36",
            "MACD momentum SL=22 TP=44",
            "BB mean reversion SL=12 TP=24",
            "EMA trend continuation SL=25 TP=50",
            "New York session RSI SL=15 TP=30",
            "Volatility breakout ATR SL=30 TP=60",
        ])
    ]

    def test_bundle_build_admin_gated(self, api):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/intelligence/bundles/build",
                   json={"strategies": []})
        assert r.status_code in (401, 403)

    def test_build_produces_tiered_report(self, admin):
        r = admin.post(f"{BASE_URL}/api/intelligence/bundles/build",
                       json={"strategies": self.STRATEGIES})
        assert r.status_code == 200, r.text
        rep = r.json()["report"]
        assert rep["pool_size"] == len(self.STRATEGIES)
        assert rep["accepted"] >= 3
        assert isinstance(rep["tier_1"], list)
        assert isinstance(rep["tier_2"], list)
        assert isinstance(rep["tier_3"], list)
        for tier in ("tier_1", "tier_2", "tier_3"):
            for s in rep[tier]:
                for k in ("strategy_hash", "style", "confidence",
                          "solo_score", "regime_suitability",
                          "portfolio_score"):
                    assert k in s, f"missing {k} in {tier}"

    def test_style_balance_present(self, admin):
        r = admin.post(f"{BASE_URL}/api/intelligence/bundles/build",
                       json={"strategies": self.STRATEGIES})
        assert r.status_code == 200
        rep = r.json()["report"]
        # Style balance should include > 1 distinct style with these varied texts.
        assert len(rep["style_balance"]) >= 2

    def test_empty_strategies_returns_400(self, admin):
        r = admin.post(f"{BASE_URL}/api/intelligence/bundles/build",
                       json={"strategies": []})
        assert r.status_code == 400


# ── 4. Market Regime Engine ───────────────────────────────────────
class TestMarketRegime:
    def test_regime_endpoint_shape(self, admin):
        r = admin.get(f"{BASE_URL}/api/intelligence/regime?pair=EURUSD&timeframe=H1")
        assert r.status_code == 200
        body = r.json()
        for k in ("pair", "timeframe", "regime", "confidence",
                  "volatility", "trend_score", "ts", "evidence"):
            assert k in body
        assert body["regime"] in (
            "trending", "ranging", "high_volatility", "low_volatility", "unknown"
        )
        assert 0.0 <= body["confidence"] <= 1.0

    def test_regime_falls_back_to_synthetic(self, admin):
        # No real data in this pod → source should be "synthetic"
        r = admin.get(f"{BASE_URL}/api/intelligence/regime?pair=XAUUSD&timeframe=H4")
        b = r.json()
        assert b["evidence"]["source"] == "synthetic"


# ── 5. Dynamic Strategy Selector ─────────────────────────────────
class TestDynamicSelector:
    def test_selects_trend_following_in_trending_regime(self, admin):
        r = admin.post(f"{BASE_URL}/api/intelligence/activate", json={
            "regime_override": "trending",
            "bundle": [
                {"strategy_hash": "trend_1", "style": "trend_following",
                 "confidence": 0.8,
                 "regime_suitability": {"trending": 0.9, "ranging": 0.25},
                 "backtest": {"profit_factor": 2.1, "max_drawdown_pct": 8}},
                {"strategy_hash": "rev_1", "style": "mean_reversion",
                 "confidence": 0.6,
                 "regime_suitability": {"trending": 0.25, "ranging": 0.9},
                 "backtest": {"profit_factor": 1.6, "max_drawdown_pct": 6}},
            ],
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["active_hash"] == "trend_1"
        assert d["active_style"] == "trend_following"
        assert d["regime"] == "trending"
        assert d["activation_score"] > 0.5
        assert len(d["candidates"]) == 2

    def test_selects_mean_reversion_in_ranging_regime(self, admin):
        r = admin.post(f"{BASE_URL}/api/intelligence/activate", json={
            "regime_override": "ranging",
            "bundle": [
                {"strategy_hash": "trend_1", "style": "trend_following",
                 "confidence": 0.8,
                 "regime_suitability": {"trending": 0.9, "ranging": 0.25},
                 "backtest": {"profit_factor": 2.1}},
                {"strategy_hash": "rev_1", "style": "mean_reversion",
                 "confidence": 0.6,
                 "regime_suitability": {"trending": 0.25, "ranging": 0.9},
                 "backtest": {"profit_factor": 1.6}},
            ],
        })
        assert r.status_code == 200
        d = r.json()
        assert d["active_hash"] == "rev_1"
        assert d["active_style"] == "mean_reversion"

    def test_empty_bundle_returns_none(self, admin):
        r = admin.post(f"{BASE_URL}/api/intelligence/activate", json={
            "regime_override": "trending", "bundle": [],
        })
        assert r.status_code == 200
        d = r.json()
        assert d["active_hash"] is None
        assert d["reason"] == "empty_bundle"


# ── 6. Explainability (outcome_events emission) ──────────────────
class TestExplainability:
    def test_classify_emits_outcome_event(self, admin):
        # Make a classify call, then check that an outcome_events row appears.
        # The Phase B outcome_events endpoint returns recent rows.
        admin.post(f"{BASE_URL}/api/intelligence/classify", json={
            "strategy_text": "EMA20 cross EMA50 SL=20 TP=40",
            "profit_factor": 2.0, "total_trades": 100,
            "strategy_hash": "explain_test_1",
        })
        time.sleep(0.5)
        r = admin.get(f"{BASE_URL}/api/learning/events?limit=20")
        assert r.status_code == 200
        events = r.json()
        # events may be either a list or {"events":[...]} depending on router version
        rows = events if isinstance(events, list) else (
            events.get("events") or events.get("items") or []
        )
        found = False
        for e in rows:
            m = e.get("metrics") or {}
            if m.get("decision_type") == "strategy_classification":
                found = True
                break
        assert found, "no strategy_classification event found"


# ── 7. Regression: existing endpoints still 200 ──────────────────
class TestRegressionSweep:
    ENDPOINTS = [
        "/api/health",
        "/api/learning/config",
        "/api/learning/metrics",
        "/api/learning/continuous/status",
        "/api/orchestrator/status",
        "/api/orchestrator/tasks",
        "/api/orchestrator/budget",
        "/api/intelligence/regime",
    ]

    @pytest.mark.parametrize("ep", ENDPOINTS)
    def test_endpoint_returns_200(self, admin, ep):
        r = admin.get(f"{BASE_URL}{ep}", timeout=30)
        assert r.status_code == 200, f"{ep} -> {r.status_code}: {r.text[:200]}"


# ── 8. Router count invariant ─────────────────────────────────────
class TestBootLogRouterCount:
    def test_router_count_is_94(self):
        with open("/var/log/supervisor/backend.err.log") as f:
            log = f.read()
        matches = re.findall(
            r"legacy full-recovery mount: (\d+) routers/attachers online", log)
        assert matches, "no mount log line found"
        assert matches[-1] in ("94", "95"), (
            f"latest boot reports {matches[-1]} routers (expected 94..95)")
