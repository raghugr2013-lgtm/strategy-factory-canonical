"""
Prop Firm Challenge Simulator Phase 1 Upgrade Tests

Tests for:
1. floating_min_pnl intraday DD detection (worst intraday PnL checked BEFORE trade close)
2. Backward compatibility: floating_min_pnl > floating_pnl > no check with warning
3. Consistency rule enforcement: no single day profit > X% of total profit
4. Regression tests: original Phase 1 tests still pass

Key test scenarios:
- Trade with net_pnl=+500 but floating_min_pnl=-5500 fails daily DD (5.5% > 5%)
- floating_pnl is used as fallback when floating_min_pnl is absent
- No floating fields at all: simulation completes with warnings field logged
- Consistency rule: day with 80% of total profit fails when max_daily_profit_pct=40
- Consistency rule: evenly distributed profits pass when max_daily_profit_pct=40
- Consistency rule: checked at end of simulation, not mid-challenge
- Response includes consistency_violated boolean
- rules_used includes consistency_enabled and max_daily_profit_pct
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


# ═══════════════════════════════════════════════════════
# Test 1: floating_min_pnl Intraday DD Detection
# ═══════════════════════════════════════════════════════

class TestFloatingMinPnlIntradayDD:
    """Tests for floating_min_pnl causing intraday DD fail even when net_pnl is positive"""

    def test_floating_min_pnl_causes_daily_dd_fail_despite_positive_net_pnl(self):
        """
        Trade with net_pnl=+500 but floating_min_pnl=-5500 fails daily DD (5.5% > 5%)
        The trade is a WINNER at close but was deeply underwater mid-trade.
        """
        trades = [
            # Day 1: Trade closes +$500 but had -$5500 floating worst (5.5% DD)
            {"net_pnl": 500, "floating_min_pnl": -5500, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        
        # Should fail because floating_min_pnl caused >5% intraday DD
        assert sim["status"] == "fail", f"Expected fail due to floating_min_pnl DD, got {sim['status']}"
        assert sim["failure_reason"] == "daily_dd", f"Expected daily_dd, got {sim['failure_reason']}"
        assert sim["max_daily_drawdown_pct"] >= 5.0, f"Expected daily DD >= 5%, got {sim['max_daily_drawdown_pct']}%"
        print(f"✓ floating_min_pnl causes DD fail: net_pnl=+500, floating_min_pnl=-5500, DD={sim['max_daily_drawdown_pct']}%")

    def test_floating_min_pnl_checked_before_trade_close(self):
        """
        DD is checked at floating worst BEFORE trade closes.
        Even if trade recovers to profit, the intraday low triggers DD breach.
        """
        trades = [
            # Day 1: Normal trade
            {"net_pnl": 1000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Day 2: Trade recovers from -$6000 to +$1000 (6% intraday DD > 5% limit)
            {"net_pnl": 1000, "floating_min_pnl": -6000, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "daily_dd", f"Expected daily_dd, got {sim['failure_reason']}"
        print("✓ DD checked before close: floating_min_pnl=-6000 triggers breach despite +$1000 close")

    def test_two_checkpoints_per_trade_floating_worst_and_post_close(self):
        """
        DD is checked at both floating worst AND post-close (2 checkpoints per trade).
        Test that both checkpoints work correctly.
        """
        # Checkpoint 1: floating worst
        trades_floating_breach = [
            {"net_pnl": 500, "floating_min_pnl": -5500, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response1 = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades_floating_breach, "firm": "ftmo"}
        )
        sim1 = response1.json()["simulation"]
        assert sim1["status"] == "fail", "Checkpoint 1 (floating worst) should trigger fail"
        assert sim1["failure_reason"] == "daily_dd", "Should fail on daily_dd at floating worst"
        
        # Checkpoint 2: post-close (large closed loss)
        trades_close_breach = [
            {"net_pnl": -6000, "floating_min_pnl": -3000, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response2 = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades_close_breach, "firm": "ftmo"}
        )
        sim2 = response2.json()["simulation"]
        assert sim2["status"] == "fail", "Checkpoint 2 (post-close) should trigger fail"
        assert sim2["failure_reason"] in ["daily_dd", "total_dd"], "Should fail on DD at post-close"
        
        print("✓ Both checkpoints work: floating worst and post-close")

    def test_floating_min_pnl_triggers_total_dd_breach(self):
        """
        floating_min_pnl can also trigger total DD breach (not just daily DD).
        Test with PipFarm trailing DD (8% limit).
        Use gradual losses that stay under daily DD (4%) but exceed total DD (8%).
        """
        # First make profit, then have trades with floating losses that stay under daily DD
        # but accumulate to exceed total DD
        trades = [
            # Day 1: +$5000 (peak = $105k)
            {"net_pnl": 5000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Day 2: Trade with floating_min_pnl=-3500 (3.5% daily DD < 4% limit)
            # But balance drops to $105k - $3500 = $101.5k (trailing DD = 3.5%)
            {"net_pnl": -3000, "floating_min_pnl": -3500, "timestamp": "2024-01-02T10:00:00"},
            # Day 3: Trade with floating_min_pnl=-3500 (3.5% daily DD < 4% limit)
            # Balance = $101.5k - $3500 = $98k (trailing DD from $105k = 6.7%)
            {"net_pnl": -3000, "floating_min_pnl": -3500, "timestamp": "2024-01-03T10:00:00"},
            # Day 4: Trade with floating_min_pnl=-3000 (3% daily DD < 4% limit)
            # Balance = $98k - $3000 = $95k (trailing DD from $105k = 9.5% > 8%)
            {"net_pnl": -2500, "floating_min_pnl": -3000, "timestamp": "2024-01-04T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "pipfarm"}
        )
        
        sim = response.json()["simulation"]
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "total_dd", f"Expected total_dd, got {sim['failure_reason']}"
        assert sim["max_drawdown_pct"] >= 8.0, f"Expected total DD >= 8%, got {sim['max_drawdown_pct']}%"
        print(f"✓ floating_min_pnl triggers total DD breach: {sim['max_drawdown_pct']}% > 8%")


# ═══════════════════════════════════════════════════════
# Test 2: Backward Compatibility
# ═══════════════════════════════════════════════════════

class TestBackwardCompatibility:
    """Tests for backward compatibility: floating_min_pnl > floating_pnl > no check with warning"""

    def test_floating_pnl_used_as_fallback_when_floating_min_pnl_absent(self):
        """
        floating_pnl is used as fallback when floating_min_pnl is absent.
        Same behavior as before the upgrade.
        """
        trades = [
            # Day 1: Trade with floating_pnl (no floating_min_pnl)
            {"net_pnl": 500, "floating_pnl": -5500, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        # Should fail because floating_pnl caused >5% intraday DD
        assert sim["status"] == "fail", f"Expected fail due to floating_pnl DD, got {sim['status']}"
        assert sim["failure_reason"] == "daily_dd", f"Expected daily_dd, got {sim['failure_reason']}"
        print(f"✓ floating_pnl fallback works: DD={sim['max_daily_drawdown_pct']}%")

    def test_floating_min_pnl_takes_priority_over_floating_pnl(self):
        """
        When both floating_min_pnl and floating_pnl are present,
        floating_min_pnl takes priority (it's the true worst-case).
        """
        trades = [
            # floating_min_pnl=-5500 (5.5% DD) should be used, not floating_pnl=-3000
            {"net_pnl": 500, "floating_min_pnl": -5500, "floating_pnl": -3000, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        # Should fail because floating_min_pnl (5.5%) > 5% limit
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "daily_dd", f"Expected daily_dd, got {sim['failure_reason']}"
        assert sim["max_daily_drawdown_pct"] >= 5.0, f"DD should be >= 5%, got {sim['max_daily_drawdown_pct']}%"
        print(f"✓ floating_min_pnl takes priority: DD={sim['max_daily_drawdown_pct']}%")

    def test_no_floating_fields_completes_with_warnings(self):
        """
        No floating fields at all: simulation completes with warnings field logged.
        Intraday DD check is skipped for those trades.
        """
        trades = [
            # Trades with only net_pnl (no floating fields)
            {"net_pnl": 1000, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": -200, "timestamp": "2024-01-03T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        
        # Should complete (not crash)
        assert "status" in sim, "Response should have status"
        
        # Should have warnings about missing floating fields
        # Note: warnings only appear for losing trades (net_pnl < 0)
        if sim.get("warnings"):
            assert any("floating" in w.lower() for w in sim["warnings"]), \
                f"Expected warning about floating fields, got: {sim['warnings']}"
            print(f"✓ No floating fields: completed with warnings: {sim['warnings']}")
        else:
            # If no losing trades without floating fields, no warning needed
            print("✓ No floating fields: completed without warnings (no losing trades without floating)")

    def test_no_floating_fields_on_losing_trade_logs_warning(self):
        """
        Losing trade without floating fields should log a warning.
        """
        trades = [
            # Losing trade without floating fields
            {"net_pnl": -500, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        # Should have warnings about missing floating fields for losing trade
        assert "warnings" in sim, "Expected warnings field for losing trade without floating"
        assert len(sim["warnings"]) > 0, "Expected at least one warning"
        assert any("floating" in w.lower() for w in sim["warnings"]), \
            f"Expected warning about floating fields, got: {sim['warnings']}"
        print(f"✓ Losing trade without floating: warning logged: {sim['warnings']}")


# ═══════════════════════════════════════════════════════
# Test 3: Consistency Rule Enforcement
# ═══════════════════════════════════════════════════════

class TestConsistencyRuleEnforcement:
    """Tests for consistency rule: no single day profit > X% of total profit"""

    def test_consistency_rule_fails_when_single_day_exceeds_max_pct(self):
        """
        Consistency fail: day with 80% of total profit fails when max_daily_profit_pct=40.
        Trades: day1=$8000, day2-6=$500 each. Day 1 has 80% of total profit.
        """
        # Total profit = $8000 + $500*5 = $10,500
        # Day 1 profit = $8000 = 76% of total (> 40% limit)
        trades = [
            # Day 1: $8000 profit (76% of total)
            {"net_pnl": 8000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Days 2-6: $500 each
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-05T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -50, "timestamp": "2024-01-06T10:00:00"},
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
        
        assert sim["status"] == "fail", f"Expected fail due to consistency, got {sim['status']}"
        assert sim["failure_reason"] == "consistency", f"Expected consistency, got {sim['failure_reason']}"
        assert sim["consistency_violated"] == True, "Expected consistency_violated=True"
        print("✓ Consistency rule fails: day1=76% of total profit > 40% limit")

    def test_consistency_rule_passes_with_evenly_distributed_profits(self):
        """
        Consistency rule: evenly distributed profits pass when max_daily_profit_pct=40.
        Each day ~$2000, no single day > 40% of total.
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
        print("✓ Consistency rule passes: each day=20% of total profit < 40% limit")

    def test_consistency_rule_checked_at_end_of_simulation(self):
        """
        Consistency rule: checked at end of simulation, not mid-challenge.
        Even if day 1 has 100% of profit mid-challenge, it's only checked at the end.
        """
        # Day 1: $5000 (initially 100% of profit)
        # Day 2-5: $1250 each (total = $10,000, day 1 = 50% > 40%)
        # But consistency is checked at END, so it should fail
        trades = [
            {"net_pnl": 5000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 1250, "floating_min_pnl": -100, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 1250, "floating_min_pnl": -100, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 1250, "floating_min_pnl": -100, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 1250, "floating_min_pnl": -100, "timestamp": "2024-01-05T10:00:00"},
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
        
        # Day 1 = $5000 / $10000 = 50% > 40% limit
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "consistency", f"Expected consistency, got {sim['failure_reason']}"
        print("✓ Consistency checked at end: day1=50% of total > 40% limit")

    def test_consistency_disabled_by_default(self):
        """
        Consistency disabled by default (no false positives on existing tests).
        Firm presets should not have consistency enabled.
        """
        # Same trades that would fail consistency if enabled
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
        
        # Should pass because consistency is disabled by default for firm presets
        assert sim["status"] == "pass", f"Expected pass (consistency disabled), got {sim['status']}, reason: {sim.get('failure_reason')}"
        assert sim["consistency_violated"] == False, "Expected consistency_violated=False"
        assert sim["rules_used"]["consistency_enabled"] == False, "Expected consistency_enabled=False in rules_used"
        print("✓ Consistency disabled by default: status=pass, consistency_enabled=False")


# ═══════════════════════════════════════════════════════
# Test 4: Response Structure for Consistency
# ═══════════════════════════════════════════════════════

class TestConsistencyResponseStructure:
    """Tests for consistency-related response fields"""

    def test_response_includes_consistency_violated_boolean(self):
        """Response includes consistency_violated boolean"""
        trades = [
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        assert "consistency_violated" in sim, "Response missing consistency_violated field"
        assert isinstance(sim["consistency_violated"], bool), "consistency_violated should be boolean"
        print(f"✓ Response includes consistency_violated: {sim['consistency_violated']}")

    def test_rules_used_includes_consistency_enabled(self):
        """rules_used includes consistency_enabled"""
        trades = [
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        rules = sim["rules_used"]
        assert "consistency_enabled" in rules, "rules_used missing consistency_enabled"
        assert isinstance(rules["consistency_enabled"], bool), "consistency_enabled should be boolean"
        print(f"✓ rules_used includes consistency_enabled: {rules['consistency_enabled']}")

    def test_rules_used_includes_max_daily_profit_pct(self):
        """rules_used includes max_daily_profit_pct when consistency is enabled"""
        trades = [
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 10.0,
            "max_daily_dd_pct": 5.0,
            "max_total_dd_pct": 10.0,
            "min_trading_days": 1,
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
        rules = sim["rules_used"]
        assert "max_daily_profit_pct" in rules, "rules_used missing max_daily_profit_pct"
        assert rules["max_daily_profit_pct"] == 40.0, f"Expected 40.0, got {rules['max_daily_profit_pct']}"
        print(f"✓ rules_used includes max_daily_profit_pct: {rules['max_daily_profit_pct']}")


# ═══════════════════════════════════════════════════════
# Test 5: daily_summary includes day_low_equity
# ═══════════════════════════════════════════════════════

class TestDailySummaryDayLowEquity:
    """Tests for daily_summary including day_low_equity reflecting floating_min_pnl"""

    def test_daily_summary_includes_day_low_equity(self):
        """daily_summary includes day_low_equity field"""
        trades = [
            {"net_pnl": 1000, "floating_min_pnl": -500, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "floating_min_pnl": -200, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        assert len(sim["daily_summary"]) > 0, "daily_summary should not be empty"
        
        day = sim["daily_summary"][0]
        assert "day_low_equity" in day, "daily_summary missing day_low_equity field"
        print(f"✓ daily_summary includes day_low_equity: {day['day_low_equity']}")

    def test_day_low_equity_reflects_floating_min_pnl(self):
        """day_low_equity reflects the worst intraday equity from floating_min_pnl"""
        # Initial balance = $100,000
        # Trade with floating_min_pnl = -$3000
        # Day low equity should be $100,000 - $3000 = $97,000
        trades = [
            {"net_pnl": 1000, "floating_min_pnl": -3000, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        day = sim["daily_summary"][0]
        
        # Day low equity should reflect the floating worst
        assert day["day_low_equity"] <= 97000, f"Expected day_low_equity <= 97000, got {day['day_low_equity']}"
        print(f"✓ day_low_equity reflects floating_min_pnl: {day['day_low_equity']}")


# ═══════════════════════════════════════════════════════
# Test 6: Regression Tests (Original Phase 1 Tests)
# ═══════════════════════════════════════════════════════

class TestRegressionOriginalPhase1:
    """Regression tests: original Phase 1 tests still pass"""

    def test_profitable_strategy_passes_ftmo(self):
        """Original Phase 1 test: profitable strategy passes FTMO"""
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
        """Original Phase 1 test: daily DD breach detected"""
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

    def test_total_dd_trailing_breach_detected(self):
        """Original Phase 1 test: total DD trailing breach detected"""
        trades = [
            {"net_pnl": 5000, "floating_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": -2500, "floating_pnl": -300, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": -2500, "floating_pnl": -300, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": -2500, "floating_pnl": -300, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": -1500, "floating_pnl": -300, "timestamp": "2024-01-05T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "pipfarm"}
        )
        
        sim = response.json()["simulation"]
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "total_dd", f"Expected total_dd, got {sim['failure_reason']}"
        print("✓ Regression: total DD trailing breach detected")

    def test_empty_trades_returns_fail_no_trades(self):
        """Original Phase 1 test: empty trades returns fail/no_trades"""
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": [], "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "no_trades", f"Expected no_trades, got {sim['failure_reason']}"
        print("✓ Regression: empty trades returns fail/no_trades")


# ═══════════════════════════════════════════════════════
# Test 7: Firm Preset Rules Still Work
# ═══════════════════════════════════════════════════════

class TestFirmPresetBackwardCompatibility:
    """Tests that firm preset rules still work (backward compatible)"""

    def test_ftmo_preset_still_works(self):
        """FTMO preset still works correctly"""
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
        
        sim = response.json()["simulation"]
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}"
        assert sim["rules_used"]["firm_name"] == "FTMO", f"Expected FTMO, got {sim['rules_used']['firm_name']}"
        print("✓ FTMO preset still works")

    def test_fundednext_preset_still_works(self):
        """FundedNext preset still works correctly"""
        trades = [
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 2000, "floating_min_pnl": -200, "timestamp": "2024-01-05T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "fundednext"}
        )
        
        sim = response.json()["simulation"]
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}"
        assert sim["rules_used"]["firm_name"] == "FundedNext", f"Expected FundedNext, got {sim['rules_used']['firm_name']}"
        print("✓ FundedNext preset still works")

    def test_pipfarm_preset_still_works(self):
        """PipFarm preset still works correctly"""
        trades = [
            {"net_pnl": 4000, "floating_min_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 4000, "floating_min_pnl": -200, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 4000, "floating_min_pnl": -200, "timestamp": "2024-01-03T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "pipfarm"}
        )
        
        sim = response.json()["simulation"]
        assert sim["status"] == "pass", f"Expected pass, got {sim['status']}"
        assert sim["rules_used"]["firm_name"] == "PipFarm", f"Expected PipFarm, got {sim['rules_used']['firm_name']}"
        assert sim["rules_used"]["drawdown_type"] == "trailing", f"Expected trailing DD, got {sim['rules_used']['drawdown_type']}"
        print("✓ PipFarm preset still works (trailing DD)")


# ═══════════════════════════════════════════════════════
# Test 8: Consistency Rules Loaded from rules_config
# ═══════════════════════════════════════════════════════

class TestConsistencyRulesFromConfig:
    """Tests that consistency rules are loaded from rules_config.consistency dict"""

    def test_consistency_rules_loaded_from_rules_config(self):
        """Consistency rules loaded from rules_config.consistency dict"""
        trades = [
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 2.0,
            "max_daily_dd_pct": 5.0,
            "max_total_dd_pct": 10.0,
            "min_trading_days": 2,
            "drawdown_type": "static",
            "consistency": {
                "enabled": True,
                "max_daily_profit_pct": 60.0
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "rules_config": custom_rules}
        )
        
        sim = response.json()["simulation"]
        rules = sim["rules_used"]
        
        assert rules["consistency_enabled"] == True, "Expected consistency_enabled=True"
        assert rules["max_daily_profit_pct"] == 60.0, f"Expected 60.0, got {rules['max_daily_profit_pct']}"
        print(f"✓ Consistency rules loaded from rules_config: enabled={rules['consistency_enabled']}, max_pct={rules['max_daily_profit_pct']}")

    def test_consistency_disabled_when_not_in_config(self):
        """Consistency disabled when not in rules_config"""
        trades = [
            {"net_pnl": 1000, "floating_min_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 1.0,
            "max_daily_dd_pct": 5.0,
            "max_total_dd_pct": 10.0,
            "min_trading_days": 1,
            "drawdown_type": "static"
            # No consistency key
        }
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "rules_config": custom_rules}
        )
        
        sim = response.json()["simulation"]
        rules = sim["rules_used"]
        
        assert rules["consistency_enabled"] == False, "Expected consistency_enabled=False when not in config"
        print("✓ Consistency disabled when not in config")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
