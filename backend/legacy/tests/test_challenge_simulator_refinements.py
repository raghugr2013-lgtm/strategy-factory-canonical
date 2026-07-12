"""
Challenge Simulator Refinements Tests (Iteration 12)

Tests for two targeted refinements:
1. FIX 1: Consistency rule checked after EACH DAY (not end of challenge), with min-days guard
   - min_days_for_check = ceil(100/max_daily_profit_pct)
   - For 40% threshold: ceil(100/40) = 3 days minimum before consistency check starts
   - Consistency violation detected MID-CHALLENGE (after day 3, not at end)

2. FIX 2: Missing floating_min_pnl estimated conservatively
   - Losers (net_pnl < 0): floating_worst = net_pnl * 2.0 (assumes went 2x deeper)
   - Winners (net_pnl > 0): floating_worst = -abs(net_pnl) * 0.5 (small adverse excursion)
   - Zero pnl: floating_worst = 0
   - Response includes floating_estimated_count and warnings array

Key test scenarios:
- Consistency fails MID-CHALLENGE after 3 trading days (40% threshold)
- Consistency check only starts after ceil(100/T) trading days
- Evenly distributed profits pass consistency check
- Missing floating_min_pnl: losers estimated as 2x net_pnl → triggers DD
- Missing floating_min_pnl: winners estimated as -0.5x net_pnl
- Response includes floating_estimated_count when estimation used
- Response includes warnings array describing estimation method
- With explicit floating_min_pnl: no estimation (floating_estimated_count=0)
- floating_pnl fallback still works (backward compat)
- Firm presets (FTMO, FundedNext, PipFarm) still work (consistency disabled by default)
- Regression: profitable strategy passes FTMO
- Regression: daily DD breach detected
- Regression: empty trades returns fail/no_trades
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


# ═══════════════════════════════════════════════════════
# FIX 1: Consistency Rule Mid-Challenge Detection
# ═══════════════════════════════════════════════════════

class TestConsistencyMidChallengeDetection:
    """Tests for consistency rule checked after EACH DAY with min-days guard"""

    def test_consistency_fails_mid_challenge_after_3_trading_days(self):
        """
        Consistency rule fails MID-CHALLENGE: day with 92% of total profit detected after 3 trading days.
        With 40% threshold: ceil(100/40) = 3 days minimum.
        Day 1: $8000, Day 2: $200, Day 3: $500 → total = $8700
        Day 1 share = 8000/8700 = 92% > 40% → FAIL after day 3
        """
        trades = [
            # Day 1: $8000 profit (will be 92% of total after day 3)
            {"net_pnl": 8000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Day 2: $200 profit
            {"net_pnl": 200, "floating_min_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
            # Day 3: $500 profit → total = $8700, day1 = 92% > 40%
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-03T10:00:00"},
            # Day 4: Should NOT be reached (fail happens after day 3)
            {"net_pnl": 1000, "floating_min_pnl": -50, "timestamp": "2024-01-04T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 10.0,
            "max_daily_dd_pct": 5.0,
            "max_total_dd_pct": 10.0,
            "min_trading_days": 4,
            "drawdown_type": "static",
            "consistency": {
                "enabled": True,
                "max_daily_profit_pct": 40.0
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "rules_config": custom_rules}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        
        # Should fail due to consistency violation
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "consistency", f"Expected consistency, got {sim['failure_reason']}"
        assert sim["consistency_violated"] == True, "Expected consistency_violated=True"
        
        # Should fail after day 3 (not process day 4)
        assert sim["trading_days"] == 3, f"Expected 3 trading days (fail mid-challenge), got {sim['trading_days']}"
        
        print("✓ Consistency fails MID-CHALLENGE after 3 days: day1=92% > 40% limit")

    def test_consistency_check_starts_after_min_days_for_40_pct_threshold(self):
        """
        Consistency check only starts after ceil(100/40) = 3 trading days.
        With only 2 trading days, consistency should NOT be checked even if day1 has 100% profit.
        """
        trades = [
            # Day 1: $5000 profit (100% of total after day 1, 83% after day 2)
            {"net_pnl": 5000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Day 2: $1000 profit → total = $6000, day1 = 83% > 40%
            # But only 2 trading days < ceil(100/40) = 3, so no consistency check yet
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 6.0,  # Target = $6000 (exactly met)
            "max_daily_dd_pct": 5.0,
            "max_total_dd_pct": 10.0,
            "min_trading_days": 2,
            "drawdown_type": "static",
            "consistency": {
                "enabled": True,
                "max_daily_profit_pct": 40.0
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "rules_config": custom_rules}
        )
        
        sim = response.json()["simulation"]
        
        # Should pass because consistency check hasn't started yet (only 2 days < 3 required)
        assert sim["status"] == "pass", f"Expected pass (consistency check not started), got {sim['status']}, reason: {sim.get('failure_reason')}"
        assert sim["consistency_violated"] == False, "Expected consistency_violated=False"
        assert sim["trading_days"] == 2, f"Expected 2 trading days, got {sim['trading_days']}"
        
        print("✓ Consistency check NOT started with only 2 days (need 3 for 40% threshold)")

    def test_consistency_check_starts_after_min_days_for_50_pct_threshold(self):
        """
        With 50% threshold: ceil(100/50) = 2 days minimum.
        After 2 trading days, consistency should be checked.
        """
        trades = [
            # Day 1: $5000 profit (83% of total after day 2)
            {"net_pnl": 5000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Day 2: $1000 profit → total = $6000, day1 = 83% > 50%
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 10.0,
            "max_daily_dd_pct": 5.0,
            "max_total_dd_pct": 10.0,
            "min_trading_days": 2,
            "drawdown_type": "static",
            "consistency": {
                "enabled": True,
                "max_daily_profit_pct": 50.0  # ceil(100/50) = 2 days
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "rules_config": custom_rules}
        )
        
        sim = response.json()["simulation"]
        
        # Should fail because consistency check starts at 2 days for 50% threshold
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "consistency", f"Expected consistency, got {sim['failure_reason']}"
        assert sim["consistency_violated"] == True, "Expected consistency_violated=True"
        
        print("✓ Consistency check starts at 2 days for 50% threshold: day1=83% > 50%")

    def test_consistency_check_starts_after_min_days_for_30_pct_threshold(self):
        """
        With 30% threshold: ceil(100/30) = 4 days minimum.
        After 3 trading days, consistency should NOT be checked yet.
        """
        trades = [
            # Day 1: $5000 profit
            {"net_pnl": 5000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Day 2: $500 profit
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
            # Day 3: $500 profit → total = $6000, day1 = 83% > 30%
            # But only 3 trading days < ceil(100/30) = 4, so no consistency check yet
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-03T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 6.0,  # Target = $6000 (exactly met)
            "max_daily_dd_pct": 5.0,
            "max_total_dd_pct": 10.0,
            "min_trading_days": 3,
            "drawdown_type": "static",
            "consistency": {
                "enabled": True,
                "max_daily_profit_pct": 30.0  # ceil(100/30) = 4 days
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "rules_config": custom_rules}
        )
        
        sim = response.json()["simulation"]
        
        # Should pass because consistency check hasn't started yet (only 3 days < 4 required)
        assert sim["status"] == "pass", f"Expected pass (consistency check not started), got {sim['status']}, reason: {sim.get('failure_reason')}"
        assert sim["consistency_violated"] == False, "Expected consistency_violated=False"
        
        print("✓ Consistency check NOT started with only 3 days (need 4 for 30% threshold)")

    def test_evenly_distributed_profits_pass_consistency_check(self):
        """
        Evenly distributed profits pass consistency check (each day ~20% with 40% limit).
        """
        # Total profit = $2000 * 5 = $10,000
        # Each day = 20% of total (< 40% limit)
        trades = [
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-05T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 10.0,
            "max_daily_dd_pct": 5.0,
            "max_total_dd_pct": 10.0,
            "min_trading_days": 4,
            "drawdown_type": "static",
            "consistency": {
                "enabled": True,
                "max_daily_profit_pct": 40.0
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "rules_config": custom_rules}
        )
        
        sim = response.json()["simulation"]
        
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}, reason: {sim.get('failure_reason')}"
        assert sim["consistency_violated"] == False, "Expected consistency_violated=False"
        
        print("✓ Evenly distributed profits pass: each day=20% < 40% limit")


# ═══════════════════════════════════════════════════════
# FIX 2: Missing floating_min_pnl Estimation
# ═══════════════════════════════════════════════════════

class TestFloatingMinPnlEstimation:
    """Tests for conservative estimation of missing floating_min_pnl"""

    def test_losing_trade_estimated_as_2x_net_pnl_triggers_dd(self):
        """
        Missing floating_min_pnl: losers estimated as net_pnl×2.
        Trade with net_pnl=-3000 estimates floating=-6000 → 6% DD > 5% limit → fail.
        """
        trades = [
            # Losing trade without floating_min_pnl
            # net_pnl=-3000 → estimated floating_worst = -3000 * 2 = -6000 (6% DD > 5%)
            {"net_pnl": -3000, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        
        # Should fail because estimated floating_worst = -6000 (6% DD > 5% limit)
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "daily_dd", f"Expected daily_dd, got {sim['failure_reason']}"
        assert sim["max_daily_drawdown_pct"] >= 5.0, f"Expected DD >= 5%, got {sim['max_daily_drawdown_pct']}%"
        
        # Should have floating_estimated_count
        assert "floating_estimated_count" in sim, "Expected floating_estimated_count in response"
        assert sim["floating_estimated_count"] >= 1, f"Expected floating_estimated_count >= 1, got {sim.get('floating_estimated_count')}"
        
        # Should have warnings
        assert "warnings" in sim, "Expected warnings in response"
        assert len(sim["warnings"]) > 0, "Expected at least one warning"
        
        print(f"✓ Losing trade estimated as 2x: net_pnl=-3000 → floating=-6000 → DD={sim['max_daily_drawdown_pct']}%")

    def test_winning_trade_estimated_as_minus_half_net_pnl(self):
        """
        Missing floating_min_pnl: winning trades estimated as -0.5×net_pnl.
        Trade with net_pnl=+2000 estimates floating_worst = -1000 (small adverse excursion).
        """
        trades = [
            # Winning trade without floating_min_pnl
            # net_pnl=+2000 → estimated floating_worst = -abs(2000) * 0.5 = -1000
            {"net_pnl": 2000, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 2000, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 2000, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 2000, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 2000, "timestamp": "2024-01-05T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        # Should pass (estimated floating_worst = -1000 per trade = 1% DD < 5% limit)
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}, reason: {sim.get('failure_reason')}"
        
        # Should have floating_estimated_count = 5 (all trades estimated)
        assert "floating_estimated_count" in sim, "Expected floating_estimated_count in response"
        assert sim["floating_estimated_count"] == 5, f"Expected floating_estimated_count=5, got {sim.get('floating_estimated_count')}"
        
        # Should have warnings
        assert "warnings" in sim, "Expected warnings in response"
        
        print("✓ Winning trades estimated as -0.5x: net_pnl=+2000 → floating=-1000, status=pass")

    def test_zero_pnl_trade_estimated_as_zero_floating(self):
        """
        Zero pnl trade: floating_worst = 0.
        """
        trades = [
            # Zero pnl trade
            {"net_pnl": 0, "timestamp": "2024-01-01T10:00:00"},
            # Profitable trades to meet target
            {"net_pnl": 2500, "floating_min_pnl": -200, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 2500, "floating_min_pnl": -200, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 2500, "floating_min_pnl": -200, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 2500, "floating_min_pnl": -200, "timestamp": "2024-01-05T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        # Should pass (zero pnl trade doesn't cause DD)
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}, reason: {sim.get('failure_reason')}"
        
        # Should have floating_estimated_count = 1 (only the zero pnl trade)
        assert "floating_estimated_count" in sim, "Expected floating_estimated_count in response"
        assert sim["floating_estimated_count"] == 1, f"Expected floating_estimated_count=1, got {sim.get('floating_estimated_count')}"
        
        print("✓ Zero pnl trade estimated as floating=0, status=pass")

    def test_response_includes_floating_estimated_count(self):
        """
        Response includes floating_estimated_count when estimation was used.
        """
        trades = [
            # Trade without floating fields
            {"net_pnl": 500, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        assert "floating_estimated_count" in sim, "Expected floating_estimated_count in response"
        assert sim["floating_estimated_count"] == 2, f"Expected 2, got {sim['floating_estimated_count']}"
        
        print(f"✓ Response includes floating_estimated_count: {sim['floating_estimated_count']}")

    def test_response_includes_warnings_array(self):
        """
        Response includes warnings array describing estimation method.
        """
        trades = [
            {"net_pnl": -500, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        assert "warnings" in sim, "Expected warnings in response"
        assert isinstance(sim["warnings"], list), "warnings should be a list"
        assert len(sim["warnings"]) > 0, "Expected at least one warning"
        
        # Check warning content mentions estimation method
        warning_text = " ".join(sim["warnings"]).lower()
        assert "estimated" in warning_text or "floating" in warning_text, \
            f"Warning should mention estimation: {sim['warnings']}"
        
        print(f"✓ Response includes warnings: {sim['warnings']}")

    def test_explicit_floating_min_pnl_no_estimation(self):
        """
        With explicit floating_min_pnl provided: no estimation occurs (floating_estimated_count=0).
        """
        trades = [
            {"net_pnl": 1000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 1000, "floating_min_pnl": -200, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        # Should NOT have floating_estimated_count (or it should be 0)
        if "floating_estimated_count" in sim:
            assert sim["floating_estimated_count"] == 0, f"Expected 0, got {sim['floating_estimated_count']}"
        
        # Should NOT have warnings
        assert "warnings" not in sim or len(sim.get("warnings", [])) == 0, \
            f"Expected no warnings, got {sim.get('warnings')}"
        
        print("✓ Explicit floating_min_pnl: no estimation, no warnings")

    def test_floating_pnl_fallback_still_works(self):
        """
        floating_pnl field still works as fallback (backward compat).
        """
        trades = [
            # Trade with floating_pnl (no floating_min_pnl)
            {"net_pnl": 500, "floating_pnl": -5500, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        # Should fail because floating_pnl=-5500 (5.5% DD > 5% limit)
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "daily_dd", f"Expected daily_dd, got {sim['failure_reason']}"
        
        # Should NOT have floating_estimated_count (floating_pnl was used, not estimated)
        if "floating_estimated_count" in sim:
            assert sim["floating_estimated_count"] == 0, f"Expected 0 (floating_pnl used), got {sim['floating_estimated_count']}"
        
        print(f"✓ floating_pnl fallback works: DD={sim['max_daily_drawdown_pct']}%")


# ═══════════════════════════════════════════════════════
# Regression Tests: Firm Presets & Original Behavior
# ═══════════════════════════════════════════════════════

class TestFirmPresetNoFalsePositives:
    """Tests that firm presets have consistency disabled by default (no false positives)"""

    def test_ftmo_consistency_disabled_by_default(self):
        """
        FTMO preset: consistency disabled by default.
        Trades that would fail consistency if enabled should pass.
        """
        # Trades with uneven distribution (would fail 40% consistency)
        trades = [
            {"net_pnl": 8000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-05T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        assert sim["status"] == "pass", f"Expected pass (consistency disabled), got {sim['status']}, reason: {sim.get('failure_reason')}"
        assert sim["consistency_violated"] == False, "Expected consistency_violated=False"
        assert sim["rules_used"]["consistency_enabled"] == False, "Expected consistency_enabled=False"
        
        print("✓ FTMO: consistency disabled by default, no false positives")

    def test_fundednext_consistency_disabled_by_default(self):
        """FundedNext preset: consistency disabled by default."""
        trades = [
            {"net_pnl": 8000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-05T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "fundednext"}
        )
        
        sim = response.json()["simulation"]
        
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}, reason: {sim.get('failure_reason')}"
        assert sim["rules_used"]["consistency_enabled"] == False, "Expected consistency_enabled=False"
        
        print("✓ FundedNext: consistency disabled by default")

    def test_pipfarm_consistency_disabled_by_default(self):
        """PipFarm preset: consistency disabled by default."""
        trades = [
            {"net_pnl": 10000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-03T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "pipfarm"}
        )
        
        sim = response.json()["simulation"]
        
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}, reason: {sim.get('failure_reason')}"
        assert sim["rules_used"]["consistency_enabled"] == False, "Expected consistency_enabled=False"
        
        print("✓ PipFarm: consistency disabled by default")


class TestRegressionOriginalBehavior:
    """Regression tests: original behavior still works"""

    def test_profitable_strategy_passes_ftmo(self):
        """Original profitable strategy still passes FTMO."""
        trades = [
            {"net_pnl": 1200, "floating_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 800, "floating_pnl": -100, "timestamp": "2024-01-01T14:00:00"},
            {"net_pnl": 1500, "floating_pnl": -300, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 1000, "floating_pnl": -200, "timestamp": "2024-01-02T14:00:00"},
            {"net_pnl": 1100, "floating_pnl": -150, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 900, "floating_pnl": -100, "timestamp": "2024-01-03T14:00:00"},
            {"net_pnl": 1300, "floating_pnl": -200, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 1200, "floating_pnl": -150, "timestamp": "2024-01-04T14:00:00"},
            {"net_pnl": 1800, "floating_pnl": -250, "timestamp": "2024-01-05T10:00:00"},
            {"net_pnl": 1200, "floating_pnl": -100, "timestamp": "2024-01-05T14:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}, reason: {sim.get('failure_reason')}"
        assert sim["trading_days"] >= 4, f"Expected >=4 trading days, got {sim['trading_days']}"
        assert sim["profit_pct"] >= 10.0, f"Expected >=10% profit, got {sim['profit_pct']}%"
        
        print("✓ Regression: profitable strategy passes FTMO")

    def test_daily_dd_breach_detected(self):
        """Original daily DD breach still detected."""
        trades = [
            {"net_pnl": 1000, "floating_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "floating_pnl": -100, "timestamp": "2024-01-01T14:00:00"},
            {"net_pnl": 200, "floating_pnl": -5500, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "daily_dd", f"Expected daily_dd, got {sim['failure_reason']}"
        
        print("✓ Regression: daily DD breach detected")

    def test_empty_trades_returns_fail_no_trades(self):
        """Empty trades still returns fail/no_trades."""
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": [], "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "no_trades", f"Expected no_trades, got {sim['failure_reason']}"
        
        print("✓ Regression: empty trades returns fail/no_trades")

    def test_firm_preset_simulation_still_works(self):
        """Firm preset simulation (firm='ftmo') still works (backward compat)."""
        trades = [
            {"net_pnl": 2500, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 2500, "floating_min_pnl": -200, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 2500, "floating_min_pnl": -200, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 2500, "floating_min_pnl": -200, "timestamp": "2024-01-04T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}"
        assert sim["rules_used"]["firm_name"] == "FTMO", f"Expected FTMO, got {sim['rules_used']['firm_name']}"
        
        print("✓ Firm preset simulation (firm='ftmo') still works")


# ═══════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge case tests for the refinements"""

    def test_consistency_with_negative_total_profit_not_checked(self):
        """
        Consistency rule only checked when total_profit > 0.
        With negative total profit, consistency should not be checked.
        """
        trades = [
            {"net_pnl": -500, "floating_min_pnl": -600, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": -500, "floating_min_pnl": -600, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": -500, "floating_min_pnl": -600, "timestamp": "2024-01-03T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 10.0,
            "max_daily_dd_pct": 5.0,
            "max_total_dd_pct": 10.0,
            "min_trading_days": 3,
            "drawdown_type": "static",
            "consistency": {
                "enabled": True,
                "max_daily_profit_pct": 40.0
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "rules_config": custom_rules}
        )
        
        sim = response.json()["simulation"]
        
        # Should fail due to profit target not reached, NOT consistency
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] != "consistency", "Should not fail on consistency with negative profit"
        assert sim["consistency_violated"] == False, "Expected consistency_violated=False"
        
        print("✓ Consistency not checked with negative total profit")

    def test_mixed_trades_with_and_without_floating(self):
        """
        Mixed trades: some with floating_min_pnl, some without.
        Only trades without floating fields should be estimated.
        """
        trades = [
            # Trade with floating_min_pnl (not estimated)
            {"net_pnl": 1000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Trade without floating fields (estimated)
            {"net_pnl": 1000, "timestamp": "2024-01-02T10:00:00"},
            # Trade with floating_pnl (not estimated)
            {"net_pnl": 1000, "floating_pnl": -200, "timestamp": "2024-01-03T10:00:00"},
            # Trade without floating fields (estimated)
            {"net_pnl": 1000, "timestamp": "2024-01-04T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        # Should have floating_estimated_count = 2 (only trades without floating fields)
        assert "floating_estimated_count" in sim, "Expected floating_estimated_count in response"
        assert sim["floating_estimated_count"] == 2, f"Expected 2, got {sim['floating_estimated_count']}"
        
        print(f"✓ Mixed trades: floating_estimated_count={sim['floating_estimated_count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
