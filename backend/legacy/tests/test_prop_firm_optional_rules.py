"""Regression tests for the optional-rules + scaling_rule implementation.

Covers:
  - `_build_challenge_rules_doc` honours core-required + toggle-based optional.
  - `_build_rules_doc` (intelligence path) defaults all optionals to disabled.
  - `rules_to_sim_config` exposes scaling_rule + news_restriction + reset_time.
  - `simulate_challenge` enforces scaling_rule (PnL scaled by risk_multiplier
    once cumulative DD crosses threshold).
  - Disabled scaling_rule → no behaviour change (bit-identical result).
  - News_restriction is stored but NOT enforced (enforced flag = false).
  - Existing SEED_RULES carry the new scaling_rule subsection (migration-safe).
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")

import pytest  # noqa: E402
from engines.challenge_simulator import simulate_challenge  # noqa: E402
from engines.prop_firm_config_engine import _build_challenge_rules_doc  # noqa: E402
from engines.prop_firm_intelligence import _build_rules_doc  # noqa: E402
from engines.rule_engine import SEED_RULES, rules_to_sim_config  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────
# Schema build — core + optional toggles
# ─────────────────────────────────────────────────────────────────────
class TestBuildChallengeRulesDoc:
    def test_core_rules_always_enabled(self):
        doc = _build_challenge_rules_doc(
            firm_slug="test", firm_name="Test", challenge_size=100000.0,
            rules={"max_total_drawdown": 10, "max_daily_drawdown": 5, "profit_target": 10},
            now=_now(),
        )
        r = doc["rules"]
        assert r["daily_dd"]["enabled"] is True
        assert r["total_dd"]["enabled"] is True
        assert r["profit_target"]["enabled"] is True
        assert r["daily_dd"]["max_pct"] == 5.0
        assert r["total_dd"]["max_pct"] == 10.0
        assert r["profit_target"]["target_pct"] == 10.0

    def test_optional_rules_default_disabled(self):
        doc = _build_challenge_rules_doc(
            firm_slug="test", firm_name="Test", challenge_size=100000.0,
            rules={"max_total_drawdown": 10, "max_daily_drawdown": 5, "profit_target": 10},
            now=_now(),
        )
        r = doc["rules"]
        for key in ("min_trading_days", "consistency", "news_restriction",
                    "position_sizing", "scaling_rule"):
            assert r[key]["enabled"] is False, f"{key} must default-disabled"

    def test_optional_scaling_rule_respects_toggle_on(self):
        doc = _build_challenge_rules_doc(
            firm_slug="test", firm_name="Test", challenge_size=100000.0,
            rules={
                "max_total_drawdown": 10, "max_daily_drawdown": 5, "profit_target": 10,
                "scaling_rule": {"enabled": True, "threshold_dd_pct": 6.0, "risk_multiplier": 0.25},
            },
            now=_now(),
        )
        sr = doc["rules"]["scaling_rule"]
        assert sr["enabled"] is True
        assert sr["threshold_dd_pct"] == 6.0
        assert sr["risk_multiplier"] == 0.25

    def test_news_restriction_stored_with_enforced_false(self):
        doc = _build_challenge_rules_doc(
            firm_slug="test", firm_name="Test", challenge_size=100000.0,
            rules={
                "max_total_drawdown": 10, "max_daily_drawdown": 5, "profit_target": 10,
                "news_restriction": {"enabled": True, "blackout_minutes": 5},
            },
            now=_now(),
        )
        nr = doc["rules"]["news_restriction"]
        assert nr["enabled"] is True
        assert nr["blackout_minutes"] == 5
        assert nr["enforced"] is False

    def test_lot_size_limit_toggle(self):
        doc = _build_challenge_rules_doc(
            firm_slug="test", firm_name="Test", challenge_size=100000.0,
            rules={
                "max_total_drawdown": 10, "max_daily_drawdown": 5, "profit_target": 10,
                "lot_size_limit": {"enabled": True, "max_lot_per_trade": 5.0, "max_total_exposure": 10.0},
            },
            now=_now(),
        )
        ps = doc["rules"]["position_sizing"]
        assert ps["enabled"] is True
        assert ps["max_lot_per_trade"] == 5.0
        assert ps["max_total_exposure"] == 10.0

    def test_legacy_min_trading_days_int_form(self):
        """Old callers may still pass `min_trading_days: 4` (an int).
        Normaliser should treat that as enabled with days=4."""
        doc = _build_challenge_rules_doc(
            firm_slug="test", firm_name="Test", challenge_size=100000.0,
            rules={
                "max_total_drawdown": 10, "max_daily_drawdown": 5, "profit_target": 10,
                "min_trading_days": 4,
            },
            now=_now(),
        )
        mtd = doc["rules"]["min_trading_days"]
        assert mtd["enabled"] is True
        assert mtd["days"] == 4


# ─────────────────────────────────────────────────────────────────────
# Intelligence path
# ─────────────────────────────────────────────────────────────────────
class TestBuildRulesDocIntelligence:
    def test_multi_plan_defaults_all_optionals_off(self):
        doc = _build_rules_doc(
            firm_slug="ft", firm_name="FirmX",
            challenge=dict(account_size=100000, type="2-step",
                           rules=dict(max_total_drawdown=10, max_daily_drawdown=5,
                                      profit_target=10),
                           source="pdf", confidence=90),
            now=_now(),
        )
        r = doc["rules"]
        assert r["scaling_rule"]["enabled"] is False
        assert r["news_restriction"]["enabled"] is False
        assert r["news_restriction"]["enforced"] is False
        assert r["position_sizing"]["enabled"] is False
        assert r["consistency"]["enabled"] is False
        assert r["min_trading_days"]["enabled"] is False


# ─────────────────────────────────────────────────────────────────────
# rules_to_sim_config — plumbs scaling_rule + news + reset_time
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
class TestRulesToSimConfig:
    async def test_reset_time_surfaced_as_core(self):
        rule_doc = dict(SEED_RULES[0])
        cfg = await rules_to_sim_config(rule_doc)
        assert cfg["reset_time"] == {"timezone": "America/New_York", "hour": 17}

    async def test_scaling_disabled_by_default(self):
        rule_doc = dict(SEED_RULES[0])
        cfg = await rules_to_sim_config(rule_doc)
        assert cfg["scaling_rule"]["enabled"] is False

    async def test_scaling_enabled_passes_threshold_and_multiplier(self):
        rule_doc = dict(SEED_RULES[0])
        rule_doc = {**rule_doc, "rules": {
            **rule_doc["rules"],
            "scaling_rule": {
                "enabled": True, "type": "risk_reduction",
                "threshold_dd_pct": 4.5, "risk_multiplier": 0.3,
            },
        }}
        cfg = await rules_to_sim_config(rule_doc)
        sr = cfg["scaling_rule"]
        assert sr["enabled"] is True
        assert sr["threshold_dd_pct"] == 4.5
        assert sr["risk_multiplier"] == 0.3

    async def test_news_restriction_store_only(self):
        rule_doc = dict(SEED_RULES[0])
        rule_doc = {**rule_doc, "rules": {
            **rule_doc["rules"],
            "news_restriction": {"enabled": True, "blackout_minutes": 3},
        }}
        cfg = await rules_to_sim_config(rule_doc)
        assert cfg["news_restriction"] == {
            "enabled": True, "enforced": False, "blackout_minutes": 3,
        }


# ─────────────────────────────────────────────────────────────────────
# Simulator — scaling rule enforcement
# ─────────────────────────────────────────────────────────────────────

def _synth_trades(n_loss_first: int = 3, n_later: int = 5):
    """Build a trade series that puts the account ~6% under water after
    the first N trades, then has `n_later` break-even wins/losses. Lets us
    prove that scaling DOES / DOES NOT fire based on config."""
    trades = []
    # First block — big losses to push DD past threshold
    for i in range(n_loss_first):
        trades.append({
            "net_pnl": -2500.0,
            "floating_min_pnl": -2500.0,
            "timestamp": f"2026-01-{i+1:02d}T15:00:00+00:00",
            "lot_size": 1.0,
        })
    # Later block — +1000 wins (so we can see if they got scaled)
    for j in range(n_later):
        trades.append({
            "net_pnl": 1000.0,
            "floating_min_pnl": -200.0,
            "timestamp": f"2026-01-{n_loss_first + j + 1:02d}T15:00:00+00:00",
            "lot_size": 1.0,
        })
    return trades


BASE_CONFIG = {
    "initial_balance": 100000,
    "profit_target_pct": 10.0,
    "max_daily_dd_pct": 100.0,   # effectively disabled — we want DD to accumulate
    "max_total_dd_pct": 100.0,   # same — we're testing scaling, not DD breaches
    "min_trading_days": 0,
    "drawdown_type": "static",
    "consistency": {"enabled": False},
    "position_sizing": {"enabled": False},
    "execution": {"enabled": False},
    "reset_time": {"timezone": "America/New_York", "hour": 17},
}


class TestScalingRuleEnforcement:
    def test_disabled_scaling_is_noop(self):
        cfg = {**BASE_CONFIG, "scaling_rule": {"enabled": False}}
        res = simulate_challenge(_synth_trades(), cfg)
        # 3 × -2500 + 5 × 1000 = -2500 final PnL
        assert res["scaling_rule"]["enabled"] is False
        assert res["scaling_rule"]["triggered"] is False
        assert res["scaling_rule"]["scaled_trades"] == 0
        assert round(res["final_balance"], 0) == 97500.0

    def test_enabled_scaling_halves_later_trades(self):
        cfg = {**BASE_CONFIG, "scaling_rule": {
            "enabled": True, "threshold_dd_pct": 5.0, "risk_multiplier": 0.5,
        }}
        res = simulate_challenge(_synth_trades(), cfg)
        # Expected trace (threshold=5%, multiplier=0.5):
        #   t1: -2500 not scaled → bal 97500, max_dd 2.5%
        #   t2: -2500 not scaled → bal 95000, max_dd 5.0%  (threshold hit)
        #   t3: -2500 × 0.5 = -1250 scaled → bal 93750, max_dd 6.25%
        #   t4-t8: +1000 × 0.5 = +500 each → 93750 + 5×500 = 96250
        # Scaled trades total: 6 (1 loss + 5 wins)
        assert res["scaling_rule"]["enabled"] is True
        assert res["scaling_rule"]["triggered"] is True
        assert res["scaling_rule"]["scaled_trades"] == 6
        assert round(res["final_balance"], 0) == 96250.0

    def test_scaling_below_threshold_not_triggered(self):
        cfg = {**BASE_CONFIG, "scaling_rule": {
            "enabled": True, "threshold_dd_pct": 20.0, "risk_multiplier": 0.5,
        }}
        res = simulate_challenge(_synth_trades(), cfg)
        assert res["scaling_rule"]["enabled"] is True
        # Max DD is ~7.5% < 20% threshold → should never fire
        assert res["scaling_rule"]["triggered"] is False
        assert res["scaling_rule"]["scaled_trades"] == 0

    def test_scaling_config_preserved_in_rules_used(self):
        cfg = {**BASE_CONFIG, "scaling_rule": {
            "enabled": True, "threshold_dd_pct": 5.0, "risk_multiplier": 0.25,
        }}
        res = simulate_challenge(_synth_trades(), cfg)
        rules_used = res["rules_used"]
        assert rules_used["scaling_rule_enabled"] is True
        assert rules_used["scaling_threshold_dd_pct"] == 5.0
        assert rules_used["scaling_risk_multiplier"] == 0.25
        assert rules_used["reset_time"] == {"timezone": "America/New_York", "hour": 17}


# ─────────────────────────────────────────────────────────────────────
# Seed data migration safety
# ─────────────────────────────────────────────────────────────────────
class TestSeedRulesMigration:
    def test_all_seed_firms_carry_scaling_rule_disabled(self):
        for firm in SEED_RULES:
            r = firm["rules"]
            assert "scaling_rule" in r, f"{firm['firm_slug']} missing scaling_rule"
            assert r["scaling_rule"]["enabled"] is False
