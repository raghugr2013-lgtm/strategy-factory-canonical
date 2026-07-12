"""
Prop Firm Challenge Simulator Tests (Phase 1)

Tests for:
- GET /api/challenge-firms - List firm presets
- POST /api/simulate-challenge - Simulate challenge with trades

Test scenarios:
1. PASS case: 10 trades across 5 days with >10% profit (FTMO)
2. FAIL daily_dd: Trade with floating_pnl causing >5% intraday DD
3. FAIL total_dd: Gradual losses exceeding 8% trailing DD (PipFarm)
4. Edge cases: empty trades, 1-2 trades, large gap loss, min days not met
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestChallengeFirmsEndpoint:
    """Tests for GET /api/challenge-firms"""

    def test_endpoint_returns_200(self):
        """Endpoint exists and returns 200"""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✓ GET /api/challenge-firms returns 200")

    def test_returns_all_three_firms(self):
        """Returns all 3 firm presets: ftmo, fundednext, pipfarm"""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        data = response.json()
        assert "firms" in data, "Response missing 'firms' key"
        firms = data["firms"]
        assert "ftmo" in firms, "Missing 'ftmo' preset"
        assert "fundednext" in firms, "Missing 'fundednext' preset"
        assert "pipfarm" in firms, "Missing 'pipfarm' preset"
        print(f"✓ All 3 firms present: {list(firms.keys())}")

    def test_firm_preset_required_fields(self):
        """Each firm preset has required fields"""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        firms = response.json()["firms"]
        
        required_fields = [
            "profit_target_pct",
            "max_daily_dd_pct",
            "max_total_dd_pct",
            "min_trading_days",
            "drawdown_type"
        ]
        
        for firm_name, preset in firms.items():
            for field in required_fields:
                assert field in preset, f"Firm '{firm_name}' missing field '{field}'"
            print(f"✓ {firm_name}: {preset['profit_target_pct']}% target, {preset['max_daily_dd_pct']}% daily DD, {preset['drawdown_type']} DD type")

    def test_ftmo_preset_values(self):
        """FTMO preset has correct values"""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        ftmo = response.json()["firms"]["ftmo"]
        
        assert ftmo["profit_target_pct"] == 10.0, f"FTMO profit target should be 10%, got {ftmo['profit_target_pct']}"
        assert ftmo["max_daily_dd_pct"] == 5.0, f"FTMO daily DD should be 5%, got {ftmo['max_daily_dd_pct']}"
        assert ftmo["max_total_dd_pct"] == 10.0, f"FTMO total DD should be 10%, got {ftmo['max_total_dd_pct']}"
        assert ftmo["min_trading_days"] == 4, f"FTMO min days should be 4, got {ftmo['min_trading_days']}"
        assert ftmo["drawdown_type"] == "static", f"FTMO DD type should be static, got {ftmo['drawdown_type']}"
        print("✓ FTMO preset values correct")

    def test_pipfarm_trailing_drawdown(self):
        """PipFarm uses trailing drawdown"""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        pipfarm = response.json()["firms"]["pipfarm"]
        
        assert pipfarm["drawdown_type"] == "trailing", f"PipFarm should use trailing DD, got {pipfarm['drawdown_type']}"
        assert pipfarm["max_total_dd_pct"] == 8.0, f"PipFarm total DD should be 8%, got {pipfarm['max_total_dd_pct']}"
        print("✓ PipFarm uses trailing drawdown (8%)")


class TestSimulateChallengePassCase:
    """Test Case 1: PASS - 10 trades across 5 days with >10% profit"""

    def test_pass_with_profitable_trades(self):
        """Strategy with 10 trades, 5 days, >$10k profit passes FTMO"""
        # 10 trades across 5 days, each day has 2 trades
        # Total profit: $12,000 (12% of $100k) > 10% target
        trades = [
            # Day 1 - 2 trades, +$2000
            {"net_pnl": 1200, "floating_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 800, "floating_pnl": -100, "timestamp": "2024-01-01T14:00:00"},
            # Day 2 - 2 trades, +$2500
            {"net_pnl": 1500, "floating_pnl": -300, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 1000, "floating_pnl": -200, "timestamp": "2024-01-02T14:00:00"},
            # Day 3 - 2 trades, +$2000
            {"net_pnl": 1100, "floating_pnl": -150, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 900, "floating_pnl": -100, "timestamp": "2024-01-03T14:00:00"},
            # Day 4 - 2 trades, +$2500
            {"net_pnl": 1300, "floating_pnl": -200, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 1200, "floating_pnl": -150, "timestamp": "2024-01-04T14:00:00"},
            # Day 5 - 2 trades, +$3000
            {"net_pnl": 1800, "floating_pnl": -250, "timestamp": "2024-01-05T10:00:00"},
            {"net_pnl": 1200, "floating_pnl": -100, "timestamp": "2024-01-05T14:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "simulation" in data, "Response missing 'simulation' key"
        
        sim = data["simulation"]
        assert sim["status"] == "pass", f"Expected status=pass, got {sim['status']}, reason: {sim.get('failure_reason')}"
        assert sim["trading_days"] >= 4, f"Expected >=4 trading days, got {sim['trading_days']}"
        assert sim["profit_pct"] >= 10.0, f"Expected >=10% profit, got {sim['profit_pct']}%"
        print(f"✓ PASS case: status={sim['status']}, profit={sim['profit_pct']}%, days={sim['trading_days']}")


class TestSimulateChallengeFailDailyDD:
    """Test Case 2: FAIL daily_dd - Floating PnL causes >5% intraday DD"""

    def test_fail_daily_dd_via_floating_pnl(self):
        """Trade with floating_pnl=-5500 causes >5% intraday DD breach"""
        # Day 1: Normal trades
        # Day 2: Trade with large floating loss (-5500 = 5.5% of $100k)
        trades = [
            # Day 1 - normal
            {"net_pnl": 1000, "floating_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "floating_pnl": -100, "timestamp": "2024-01-01T14:00:00"},
            # Day 2 - large floating loss triggers daily DD breach
            {"net_pnl": 200, "floating_pnl": -5500, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        
        assert sim["status"] == "fail", f"Expected status=fail, got {sim['status']}"
        assert sim["failure_reason"] == "daily_dd", f"Expected failure_reason=daily_dd, got {sim['failure_reason']}"
        assert sim["max_daily_drawdown_pct"] >= 5.0, f"Expected daily DD >= 5%, got {sim['max_daily_drawdown_pct']}%"
        print(f"✓ FAIL daily_dd: status={sim['status']}, reason={sim['failure_reason']}, daily_dd={sim['max_daily_drawdown_pct']}%")

    def test_daily_dd_detected_via_floating_not_closed(self):
        """Daily DD is detected via floating_pnl (intraday equity drop), not just closed PnL"""
        # Trade closes positive but had large floating loss during trade
        trades = [
            # Day 1: Trade closes +$500 but had -$6000 floating (6% DD)
            {"net_pnl": 500, "floating_pnl": -6000, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        # Should fail because floating_pnl caused >5% intraday DD
        assert sim["status"] == "fail", f"Expected fail due to floating DD, got {sim['status']}"
        assert sim["failure_reason"] == "daily_dd", f"Expected daily_dd, got {sim['failure_reason']}"
        print(f"✓ Daily DD detected via floating_pnl: {sim['max_daily_drawdown_pct']}%")


class TestSimulateChallengeFailTotalDD:
    """Test Case 3: FAIL total_dd - Gradual losses exceed 8% trailing DD (PipFarm)"""

    def test_fail_trailing_dd_gradual_losses(self):
        """Gradual losses across 6 days, each under 4% daily DD but total trailing DD exceeds 8%"""
        # PipFarm: 4% daily DD, 8% trailing total DD
        # Each day loses ~1.5% (under 4% daily limit)
        # After 6 days: ~9% total loss from peak (exceeds 8% trailing DD)
        trades = [
            # Day 1: -$1500 (1.5%)
            {"net_pnl": -1500, "floating_pnl": -500, "timestamp": "2024-01-01T10:00:00"},
            # Day 2: -$1500 (cumulative: -3%)
            {"net_pnl": -1500, "floating_pnl": -500, "timestamp": "2024-01-02T10:00:00"},
            # Day 3: -$1500 (cumulative: -4.5%)
            {"net_pnl": -1500, "floating_pnl": -500, "timestamp": "2024-01-03T10:00:00"},
            # Day 4: -$1500 (cumulative: -6%)
            {"net_pnl": -1500, "floating_pnl": -500, "timestamp": "2024-01-04T10:00:00"},
            # Day 5: -$1500 (cumulative: -7.5%)
            {"net_pnl": -1500, "floating_pnl": -500, "timestamp": "2024-01-05T10:00:00"},
            # Day 6: -$1500 (cumulative: -9%) - exceeds 8% trailing DD
            {"net_pnl": -1500, "floating_pnl": -500, "timestamp": "2024-01-06T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "pipfarm"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        
        assert sim["status"] == "fail", f"Expected status=fail, got {sim['status']}"
        assert sim["failure_reason"] == "total_dd", f"Expected failure_reason=total_dd, got {sim['failure_reason']}"
        assert sim["max_drawdown_pct"] >= 8.0, f"Expected total DD >= 8%, got {sim['max_drawdown_pct']}%"
        print(f"✓ FAIL total_dd (trailing): status={sim['status']}, reason={sim['failure_reason']}, total_dd={sim['max_drawdown_pct']}%")

    def test_trailing_dd_tracks_from_peak_equity(self):
        """Trailing drawdown tracks from all-time peak equity, not initial balance"""
        # First make profit (peak equity = $105k), then lose from peak
        # Each day's loss must stay under 4% daily DD limit (PipFarm)
        # But cumulative trailing DD from peak should exceed 8%
        trades = [
            # Day 1: +$5000 (balance = $105k, peak = $105k)
            {"net_pnl": 5000, "floating_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Day 2: -$2500 (balance = $102.5k, daily DD = 2.5%, trailing DD from peak = 2.5%)
            {"net_pnl": -2500, "floating_pnl": -300, "timestamp": "2024-01-02T10:00:00"},
            # Day 3: -$2500 (balance = $100k, daily DD = 2.5%, trailing DD from peak = 5%)
            {"net_pnl": -2500, "floating_pnl": -300, "timestamp": "2024-01-03T10:00:00"},
            # Day 4: -$2500 (balance = $97.5k, daily DD = 2.5%, trailing DD from peak = 7.5%)
            {"net_pnl": -2500, "floating_pnl": -300, "timestamp": "2024-01-04T10:00:00"},
            # Day 5: -$1500 (balance = $96k, daily DD = 1.5%, trailing DD from peak = 9% > 8%)
            {"net_pnl": -1500, "floating_pnl": -300, "timestamp": "2024-01-05T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "pipfarm"}
        )
        
        sim = response.json()["simulation"]
        # Should fail because trailing DD from peak ($105k) exceeds 8%
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "total_dd", f"Expected total_dd, got {sim['failure_reason']}"
        assert sim["peak_equity"] >= 105000, f"Peak equity should be >= $105k, got ${sim['peak_equity']}"
        assert sim["max_drawdown_pct"] >= 8.0, f"Trailing DD should be >= 8%, got {sim['max_drawdown_pct']}%"
        print(f"✓ Trailing DD from peak: peak=${sim['peak_equity']}, final=${sim['final_balance']}, DD={sim['max_drawdown_pct']}%")


class TestSimulateChallengeEdgeCases:
    """Edge cases: empty trades, few trades, large gap loss, min days not met"""

    def test_empty_trades_returns_fail_no_trades(self):
        """Empty trades array returns status=fail, failure_reason=no_trades"""
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": [], "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        
        assert sim["status"] == "fail", f"Expected status=fail, got {sim['status']}"
        assert sim["failure_reason"] == "no_trades", f"Expected failure_reason=no_trades, got {sim['failure_reason']}"
        print(f"✓ Empty trades: status={sim['status']}, reason={sim['failure_reason']}")

    def test_single_trade_handled_without_crash(self):
        """Very few trades (1) handled without crash"""
        trades = [
            {"net_pnl": 500, "floating_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        assert "status" in sim, "Response should have status"
        assert sim["total_trades"] == 1, f"Expected 1 trade, got {sim['total_trades']}"
        print(f"✓ Single trade handled: status={sim['status']}, trades={sim['total_trades']}")

    def test_two_trades_handled_without_crash(self):
        """Very few trades (2) handled without crash"""
        trades = [
            {"net_pnl": 500, "floating_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 300, "floating_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        assert sim["total_trades"] == 2, f"Expected 2 trades, got {sim['total_trades']}"
        print(f"✓ Two trades handled: status={sim['status']}, trades={sim['total_trades']}")

    def test_large_gap_loss_detected(self):
        """Large gap loss (-$12000 in single trade) detected correctly"""
        trades = [
            # Single trade with massive loss (12% of $100k)
            {"net_pnl": -12000, "floating_pnl": -12000, "timestamp": "2024-01-01T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        # Should fail on either daily_dd (12% > 5%) or total_dd (12% > 10%)
        assert sim["failure_reason"] in ["daily_dd", "total_dd"], f"Expected daily_dd or total_dd, got {sim['failure_reason']}"
        print(f"✓ Large gap loss detected: status={sim['status']}, reason={sim['failure_reason']}, DD={sim['max_drawdown_pct']}%")

    def test_profit_target_hit_but_min_days_not_met(self):
        """Profit target reached but min_trading_days not met returns fail with reason min_days_not_met"""
        # FTMO requires 4 min trading days
        # Make >10% profit in just 2 days
        trades = [
            # Day 1: +$6000
            {"net_pnl": 6000, "floating_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
            # Day 2: +$5000 (total: $11k = 11% > 10% target)
            {"net_pnl": 5000, "floating_pnl": -200, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        assert sim["status"] == "fail", f"Expected fail, got {sim['status']}"
        assert sim["failure_reason"] == "min_days_not_met", f"Expected min_days_not_met, got {sim['failure_reason']}"
        assert sim["profit_pct"] >= 10.0, f"Profit should be >= 10%, got {sim['profit_pct']}%"
        assert sim["trading_days"] < 4, f"Trading days should be < 4, got {sim['trading_days']}"
        print(f"✓ Min days not met: profit={sim['profit_pct']}%, days={sim['trading_days']}, reason={sim['failure_reason']}")

    def test_high_frequency_20_trades_in_one_day(self):
        """High-frequency: 20 trades in 1 day handled correctly"""
        trades = [
            {"net_pnl": 100, "floating_pnl": -50, "timestamp": f"2024-01-01T{10+i//2}:{(i%2)*30:02d}:00"}
            for i in range(20)
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        assert sim["total_trades"] == 20, f"Expected 20 trades, got {sim['total_trades']}"
        assert sim["trading_days"] == 1, f"Expected 1 trading day, got {sim['trading_days']}"
        print(f"✓ High-frequency handled: {sim['total_trades']} trades in {sim['trading_days']} day")


class TestSimulateChallengeValidation:
    """Input validation tests"""

    def test_no_strategy_id_or_trades_returns_400(self):
        """No strategy_id or strategy_trades returns 400 error"""
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"firm": "ftmo"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Missing trades/strategy_id returns 400")

    def test_unknown_firm_returns_400_with_available_list(self):
        """Unknown firm name returns 400 with available firms list"""
        trades = [{"net_pnl": 100, "floating_pnl": -10, "timestamp": "2024-01-01T10:00:00"}]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "unknown_firm"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        error_detail = response.json().get("detail", "")
        assert "unknown_firm" in error_detail.lower() or "available" in error_detail.lower(), \
            f"Error should mention unknown firm or available firms: {error_detail}"
        print(f"✓ Unknown firm returns 400: {error_detail}")

    def test_custom_rules_config_works(self):
        """Custom rules_config works (no firm preset needed)"""
        trades = [
            {"net_pnl": 1000, "floating_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 1000, "floating_pnl": -100, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 1000, "floating_pnl": -100, "timestamp": "2024-01-03T10:00:00"},
        ]
        
        custom_rules = {
            "initial_balance": 50000,
            "profit_target_pct": 5.0,  # 5% of $50k = $2500
            "max_daily_dd_pct": 3.0,
            "max_total_dd_pct": 6.0,
            "min_trading_days": 2,
            "drawdown_type": "static"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "rules_config": custom_rules}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        sim = response.json()["simulation"]
        assert sim["rules_used"]["initial_balance"] == 50000, "Custom initial_balance not applied"
        assert sim["rules_used"]["profit_target_pct"] == 5.0, "Custom profit_target not applied"
        print(f"✓ Custom rules_config works: balance=${sim['rules_used']['initial_balance']}, target={sim['rules_used']['profit_target_pct']}%")


class TestSimulateChallengeResponseStructure:
    """Response structure validation"""

    def test_response_includes_required_fields(self):
        """Response includes all required fields"""
        trades = [
            {"net_pnl": 1000, "floating_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "floating_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        
        required_fields = [
            "status", "failure_reason", "days_taken", "trading_days",
            "final_balance", "final_equity", "max_drawdown_pct",
            "max_daily_drawdown_pct", "equity_curve", "daily_summary", "rules_used"
        ]
        
        for field in required_fields:
            assert field in sim, f"Response missing required field: {field}"
        
        print(f"✓ All required fields present: {required_fields}")

    def test_daily_summary_structure(self):
        """daily_summary includes required fields"""
        trades = [
            {"net_pnl": 1000, "floating_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "floating_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        assert len(sim["daily_summary"]) > 0, "daily_summary should not be empty"
        
        day = sim["daily_summary"][0]
        required_day_fields = [
            "day", "trades", "pnl", "balance", "equity",
            "day_peak_equity", "day_low_equity", "daily_dd_pct"
        ]
        
        for field in required_day_fields:
            assert field in day, f"daily_summary missing field: {field}"
        
        print(f"✓ daily_summary structure correct: {list(day.keys())}")

    def test_equity_curve_tracks_balance_progression(self):
        """equity_curve tracks balance progression through trades"""
        trades = [
            {"net_pnl": 1000, "floating_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 500, "floating_pnl": -50, "timestamp": "2024-01-01T14:00:00"},
            {"net_pnl": -200, "floating_pnl": -300, "timestamp": "2024-01-02T10:00:00"},
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        curve = sim["equity_curve"]
        
        assert len(curve) >= 2, f"equity_curve should have multiple points, got {len(curve)}"
        assert curve[0] == 100000, f"equity_curve should start at initial balance, got {curve[0]}"
        print(f"✓ equity_curve: {curve[:5]}... (length={len(curve)})")

    def test_rules_used_field_shows_applied_rules(self):
        """rules_used field shows the rules that were applied"""
        trades = [{"net_pnl": 100, "floating_pnl": -10, "timestamp": "2024-01-01T10:00:00"}]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_trades": trades, "firm": "ftmo"}
        )
        
        sim = response.json()["simulation"]
        rules = sim["rules_used"]
        
        assert "initial_balance" in rules, "rules_used missing initial_balance"
        assert "profit_target_pct" in rules, "rules_used missing profit_target_pct"
        assert "max_daily_dd_pct" in rules, "rules_used missing max_daily_dd_pct"
        assert "max_total_dd_pct" in rules, "rules_used missing max_total_dd_pct"
        assert "drawdown_type" in rules, "rules_used missing drawdown_type"
        assert rules["firm_name"] == "FTMO", f"Expected firm_name=FTMO, got {rules['firm_name']}"
        print(f"✓ rules_used: {rules}")


class TestSimulateChallengeWithStrategyId:
    """Test using strategy_id to load trades from MongoDB"""

    def test_strategy_id_parameter_loads_trades(self):
        """strategy_id parameter loads trades from MongoDB strategy document"""
        # First, get a strategy from the library
        response = requests.get(f"{BASE_URL}/api/strategies")
        if response.status_code != 200:
            pytest.skip("Could not fetch strategies")
        
        strategies = response.json().get("strategies", [])
        if not strategies:
            pytest.skip("No strategies in library to test with")
        
        # Find a strategy with backtest trades
        strategy_with_trades = None
        for s in strategies:
            bt = s.get("backtest_results", {})
            if bt and bt.get("trades"):
                strategy_with_trades = s
                break
        
        if not strategy_with_trades:
            pytest.skip("No strategy with backtest trades found")
        
        strategy_id = strategy_with_trades["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_id": strategy_id, "firm": "ftmo"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        sim = response.json()["simulation"]
        assert "status" in sim, "Response should have status"
        assert "strategy" in sim, "Response should include strategy metadata"
        assert sim["strategy"]["id"] == strategy_id, "Strategy ID should match"
        print(f"✓ strategy_id loads trades: {sim['total_trades']} trades, status={sim['status']}")

    def test_invalid_strategy_id_returns_400(self):
        """Invalid strategy_id returns 400"""
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_id": "invalid_id", "firm": "ftmo"}
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Invalid strategy_id returns 400")

    def test_nonexistent_strategy_id_returns_404(self):
        """Non-existent strategy_id returns 404"""
        # Valid ObjectId format but doesn't exist
        response = requests.post(
            f"{BASE_URL}/api/simulate-challenge",
            json={"strategy_id": "507f1f77bcf86cd799439011", "firm": "ftmo"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent strategy_id returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
