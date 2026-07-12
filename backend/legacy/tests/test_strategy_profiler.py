"""
Phase 3: Strategy Profiler (DNA Layer) Tests

Tests the POST /api/profile-strategy endpoint which computes:
- Risk metrics (max_drawdown, avg_drawdown, daily_dd distribution)
- Trade behavior (trades_per_day, win_rate, avg_win/loss, risk_reward)
- Consistency (profit_distribution, largest_winning_day, consecutive wins/losses)
- Time metrics (avg_holding_time, intraday vs swing)
- Performance stability (Sharpe, profit_factor, equity_curve_smoothness)
- Classification (type, risk_level, consistency_level, speed, tags)
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


# ═══════════════════════════════════════════════════════
# Test Data Generators
# ═══════════════════════════════════════════════════════

def generate_intraday_trades(num_days=10, trades_per_day=2):
    """
    Generate intraday trades: ~2 trades/day, 60-120min hold, 70% WR, positive Sharpe.
    """
    trades = []
    base_date = datetime(2025, 1, 1, 9, 0, 0)
    trade_id = 0
    
    for day in range(num_days):
        day_start = base_date + timedelta(days=day)
        for t in range(trades_per_day):
            trade_id += 1
            entry_time = day_start + timedelta(hours=t * 3)
            hold_minutes = 60 + (trade_id % 60)  # 60-120 min hold
            close_time = entry_time + timedelta(minutes=hold_minutes)
            
            # 70% win rate
            is_win = (trade_id % 10) < 7
            pnl = 150 + (trade_id % 50) if is_win else -(80 + (trade_id % 30))
            
            trades.append({
                "trade_id": trade_id,
                "entry_time": entry_time.isoformat(),
                "close_time": close_time.isoformat(),
                "net_pnl": pnl,
                "symbol": "EURUSD",
            })
    
    return trades


def generate_scalping_trades(num_days=5, trades_per_day=12):
    """
    Generate scalping trades: ~10+ trades/day, <10min hold, 50% WR, low RR.
    """
    trades = []
    base_date = datetime(2025, 1, 1, 9, 0, 0)
    trade_id = 0
    
    for day in range(num_days):
        day_start = base_date + timedelta(days=day)
        for t in range(trades_per_day):
            trade_id += 1
            entry_time = day_start + timedelta(minutes=t * 30)
            hold_minutes = 3 + (trade_id % 7)  # 3-10 min hold
            close_time = entry_time + timedelta(minutes=hold_minutes)
            
            # 50% win rate
            is_win = (trade_id % 2) == 0
            pnl = 30 + (trade_id % 20) if is_win else -(35 + (trade_id % 15))
            
            trades.append({
                "trade_id": trade_id,
                "entry_time": entry_time.isoformat(),
                "close_time": close_time.isoformat(),
                "net_pnl": pnl,
                "symbol": "EURUSD",
            })
    
    return trades


def generate_swing_trades(num_weeks=4, trades_per_week=1):
    """
    Generate swing trades: ~1 trade/week, multi-day hold (2-6 days), 60% WR.
    """
    trades = []
    base_date = datetime(2025, 1, 1, 9, 0, 0)
    trade_id = 0
    
    for week in range(num_weeks):
        for t in range(trades_per_week):
            trade_id += 1
            entry_time = base_date + timedelta(weeks=week, days=t)
            hold_days = 2 + (trade_id % 5)  # 2-6 days hold
            close_time = entry_time + timedelta(days=hold_days)
            
            # 60% win rate
            is_win = (trade_id % 5) < 3
            pnl = 500 + (trade_id % 200) if is_win else -(300 + (trade_id % 100))
            
            trades.append({
                "trade_id": trade_id,
                "entry_time": entry_time.isoformat(),
                "close_time": close_time.isoformat(),
                "net_pnl": pnl,
                "symbol": "EURUSD",
            })
    
    return trades


def generate_high_risk_trades(num_trades=20):
    """
    Generate high-risk trades with large drawdowns.
    """
    trades = []
    base_date = datetime(2025, 1, 1, 9, 0, 0)
    
    for i in range(num_trades):
        entry_time = base_date + timedelta(days=i)
        close_time = entry_time + timedelta(hours=2)
        
        # Create large losses to trigger high drawdown
        if i % 3 == 0:
            pnl = -2000 - (i * 50)  # Large losses
        else:
            pnl = 300 + (i * 10)  # Moderate wins
        
        trades.append({
            "trade_id": i + 1,
            "entry_time": entry_time.isoformat(),
            "close_time": close_time.isoformat(),
            "net_pnl": pnl,
            "symbol": "EURUSD",
        })
    
    return trades


def generate_low_risk_trades(num_trades=30):
    """
    Generate low-risk trades with small, consistent gains and minimal drawdown.
    """
    trades = []
    base_date = datetime(2025, 1, 1, 9, 0, 0)
    
    for i in range(num_trades):
        entry_time = base_date + timedelta(days=i // 3)
        close_time = entry_time + timedelta(hours=1)
        
        # Small consistent gains with occasional small losses
        if i % 5 == 0:
            pnl = -50  # Small loss
        else:
            pnl = 100 + (i % 30)  # Consistent small wins
        
        trades.append({
            "trade_id": i + 1,
            "entry_time": entry_time.isoformat(),
            "close_time": close_time.isoformat(),
            "net_pnl": pnl,
            "symbol": "EURUSD",
        })
    
    return trades


def generate_trades_without_timestamps(num_trades=10):
    """
    Generate trades without entry_time/close_time fields.
    """
    trades = []
    for i in range(num_trades):
        is_win = i % 3 != 0
        pnl = 100 if is_win else -80
        trades.append({
            "trade_id": i + 1,
            "net_pnl": pnl,
            "symbol": "EURUSD",
        })
    return trades


# ═══════════════════════════════════════════════════════
# Test Classes
# ═══════════════════════════════════════════════════════

class TestProfileStrategyEndpoint:
    """Test basic endpoint functionality."""
    
    def test_endpoint_exists_and_returns_200(self):
        """POST /api/profile-strategy endpoint exists and returns 200."""
        trades = generate_intraday_trades(num_days=5)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "profile" in data, "Response should contain 'profile' key"
        print("PASSED: Endpoint exists and returns 200")
    
    def test_error_when_no_trades_or_strategy_id(self):
        """Error returned when neither strategy_id nor strategy_trades provided."""
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"initial_balance": 10000}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASSED: Error returned when no trades or strategy_id provided")


class TestResponseStructure:
    """Test that response has all required sections and fields."""
    
    def test_response_has_all_6_top_level_sections(self):
        """Response has all 6 top-level sections: risk, behavior, consistency, time, stability, classification."""
        trades = generate_intraday_trades(num_days=5)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        
        required_sections = ["risk", "behavior", "consistency", "time", "stability", "classification"]
        for section in required_sections:
            assert section in profile, f"Missing section: {section}"
        
        print(f"PASSED: All 6 sections present: {required_sections}")
    
    def test_risk_section_structure(self):
        """risk section has: max_drawdown_pct, avg_drawdown_pct, daily_dd_distribution with p50/p75/p90/p95/max."""
        trades = generate_intraday_trades(num_days=5)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        risk = response.json()["profile"]["risk"]
        
        assert "max_drawdown_pct" in risk, "Missing max_drawdown_pct"
        assert "avg_drawdown_pct" in risk, "Missing avg_drawdown_pct"
        assert "daily_dd_distribution" in risk, "Missing daily_dd_distribution"
        
        dd_dist = risk["daily_dd_distribution"]
        for key in ["p50", "p75", "p90", "p95", "max"]:
            assert key in dd_dist, f"Missing daily_dd_distribution.{key}"
        
        print("PASSED: risk section has all required fields")
    
    def test_behavior_section_structure(self):
        """behavior section has: total_trades, trades_per_day, win_rate, avg_win, avg_loss, risk_reward_ratio, largest_win, largest_loss."""
        trades = generate_intraday_trades(num_days=5)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        behavior = response.json()["profile"]["behavior"]
        
        required_fields = ["total_trades", "trades_per_day", "win_rate", "avg_win", "avg_loss", 
                          "risk_reward_ratio", "largest_win", "largest_loss"]
        for field in required_fields:
            assert field in behavior, f"Missing behavior.{field}"
        
        print("PASSED: behavior section has all required fields")
    
    def test_consistency_section_structure(self):
        """consistency section has: profit_distribution (top_day_pct, top_3_days_pct), largest_winning_day_pct, max_consecutive_wins, max_consecutive_losses."""
        trades = generate_intraday_trades(num_days=5)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        consistency = response.json()["profile"]["consistency"]
        
        assert "profit_distribution" in consistency, "Missing profit_distribution"
        pd = consistency["profit_distribution"]
        assert "top_day_pct" in pd, "Missing profit_distribution.top_day_pct"
        assert "top_3_days_pct" in pd, "Missing profit_distribution.top_3_days_pct"
        
        assert "largest_winning_day_pct" in consistency, "Missing largest_winning_day_pct"
        assert "max_consecutive_wins" in consistency, "Missing max_consecutive_wins"
        assert "max_consecutive_losses" in consistency, "Missing max_consecutive_losses"
        
        print("PASSED: consistency section has all required fields")
    
    def test_time_section_structure(self):
        """time section has: avg_holding_minutes, estimated_type, intraday_pct, swing_pct."""
        trades = generate_intraday_trades(num_days=5)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        time_metrics = response.json()["profile"]["time"]
        
        required_fields = ["avg_holding_minutes", "estimated_type", "intraday_pct", "swing_pct"]
        for field in required_fields:
            assert field in time_metrics, f"Missing time.{field}"
        
        print("PASSED: time section has all required fields")
    
    def test_stability_section_structure(self):
        """stability section has: sharpe_ratio, profit_factor, equity_curve_smoothness, net_profit, total_return_pct."""
        trades = generate_intraday_trades(num_days=5)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        stability = response.json()["profile"]["stability"]
        
        required_fields = ["sharpe_ratio", "profit_factor", "equity_curve_smoothness", "net_profit", "total_return_pct"]
        for field in required_fields:
            assert field in stability, f"Missing stability.{field}"
        
        print("PASSED: stability section has all required fields")
    
    def test_classification_section_structure(self):
        """classification section has: type, risk_level, consistency_level, speed, tags."""
        trades = generate_intraday_trades(num_days=5)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        classification = response.json()["profile"]["classification"]
        
        required_fields = ["type", "risk_level", "consistency_level", "speed", "tags"]
        for field in required_fields:
            assert field in classification, f"Missing classification.{field}"
        
        assert isinstance(classification["tags"], list), "tags should be a list"
        
        print("PASSED: classification section has all required fields")


class TestStrategyTypeClassification:
    """Test strategy type classification (scalping/intraday/swing)."""
    
    def test_intraday_classification(self):
        """Profile of intraday trades returns classification.type='intraday'."""
        trades = generate_intraday_trades(num_days=10, trades_per_day=2)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        
        classification = profile["classification"]
        time_metrics = profile["time"]
        
        print(f"  avg_holding_minutes: {time_metrics.get('avg_holding_minutes')}")
        print(f"  trades_per_day: {profile['behavior'].get('trades_per_day')}")
        print(f"  estimated_type: {time_metrics.get('estimated_type')}")
        print(f"  classification.type: {classification.get('type')}")
        
        assert classification["type"] == "intraday", f"Expected 'intraday', got '{classification['type']}'"
        print("PASSED: Intraday trades classified as 'intraday'")
    
    def test_scalping_classification(self):
        """Profile of scalping trades (5min avg hold, >8 trades/day) returns classification.type='scalping'."""
        trades = generate_scalping_trades(num_days=5, trades_per_day=12)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        
        classification = profile["classification"]
        time_metrics = profile["time"]
        behavior = profile["behavior"]
        
        print(f"  avg_holding_minutes: {time_metrics.get('avg_holding_minutes')}")
        print(f"  trades_per_day: {behavior.get('trades_per_day')}")
        print(f"  estimated_type: {time_metrics.get('estimated_type')}")
        print(f"  classification.type: {classification.get('type')}")
        
        assert classification["type"] == "scalping", f"Expected 'scalping', got '{classification['type']}'"
        print("PASSED: Scalping trades classified as 'scalping'")
    
    def test_swing_classification(self):
        """Profile of swing trades (multi-day holds) returns classification.type='swing'."""
        trades = generate_swing_trades(num_weeks=4, trades_per_week=1)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        
        classification = profile["classification"]
        time_metrics = profile["time"]
        behavior = profile["behavior"]
        
        print(f"  avg_holding_minutes: {time_metrics.get('avg_holding_minutes')}")
        print(f"  trades_per_day: {behavior.get('trades_per_day')}")
        print(f"  estimated_type: {time_metrics.get('estimated_type')}")
        print(f"  classification.type: {classification.get('type')}")
        
        assert classification["type"] == "swing", f"Expected 'swing', got '{classification['type']}'"
        print("PASSED: Swing trades classified as 'swing'")


class TestRiskLevelClassification:
    """Test risk level classification (high/medium/low)."""
    
    def test_high_risk_classification(self):
        """High-risk strategy (large DD) returns classification.risk_level='high'."""
        trades = generate_high_risk_trades(num_trades=20)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        
        risk = profile["risk"]
        classification = profile["classification"]
        
        print(f"  max_drawdown_pct: {risk.get('max_drawdown_pct')}")
        print(f"  daily_dd_distribution.p90: {risk.get('daily_dd_distribution', {}).get('p90')}")
        print(f"  classification.risk_level: {classification.get('risk_level')}")
        
        assert classification["risk_level"] == "high", f"Expected 'high', got '{classification['risk_level']}'"
        print("PASSED: High-risk strategy classified as 'high' risk")
    
    def test_low_risk_classification(self):
        """Low-risk strategy (small DD) returns classification.risk_level='low'."""
        trades = generate_low_risk_trades(num_trades=30)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        
        risk = profile["risk"]
        classification = profile["classification"]
        
        print(f"  max_drawdown_pct: {risk.get('max_drawdown_pct')}")
        print(f"  daily_dd_distribution.p90: {risk.get('daily_dd_distribution', {}).get('p90')}")
        print(f"  classification.risk_level: {classification.get('risk_level')}")
        
        assert classification["risk_level"] == "low", f"Expected 'low', got '{classification['risk_level']}'"
        print("PASSED: Low-risk strategy classified as 'low' risk")


class TestEdgeCases:
    """Test edge cases and special scenarios."""
    
    def test_empty_trades_returns_valid_profile(self):
        """Empty trades array returns valid profile with all zeroes and type='unknown'."""
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": [], "initial_balance": 10000}
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        
        # Check classification is 'unknown'
        assert profile["classification"]["type"] == "unknown", "Empty trades should have type='unknown'"
        assert profile["classification"]["risk_level"] == "unknown", "Empty trades should have risk_level='unknown'"
        
        # Check zeroes in key fields
        assert profile["behavior"]["total_trades"] == 0
        assert profile["risk"]["max_drawdown_pct"] == 0
        assert profile["stability"]["net_profit"] == 0
        
        print("PASSED: Empty trades returns valid profile with zeroes and type='unknown'")
    
    def test_no_nan_values_in_response(self):
        """No NaN values in any response field."""
        trades = generate_intraday_trades(num_days=5)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        
        # Check for NaN in JSON response text
        response_text = response.text
        assert "NaN" not in response_text, "Response contains NaN values"
        assert "nan" not in response_text.lower().replace('"', ''), "Response contains nan values"
        
        print("PASSED: No NaN values in response")
    
    def test_trades_without_timestamps_produces_valid_profile(self):
        """strategy_trades with no timestamps still produces valid profile."""
        trades = generate_trades_without_timestamps(num_trades=10)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        
        # Should still have all sections
        assert "risk" in profile
        assert "behavior" in profile
        assert "classification" in profile
        
        # Time metrics should indicate no holding data available
        time_metrics = profile["time"]
        assert "holding_data_available" in time_metrics
        
        print(f"  holding_data_available: {time_metrics.get('holding_data_available')}")
        print(f"  estimated_type: {time_metrics.get('estimated_type')}")
        
        print("PASSED: Trades without timestamps produce valid profile")
    
    def test_equity_curve_smoothness_between_0_and_100(self):
        """Equity curve smoothness is between 0 and 100."""
        trades = generate_intraday_trades(num_days=10)
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        
        smoothness = response.json()["profile"]["stability"]["equity_curve_smoothness"]
        assert 0 <= smoothness <= 100, f"Smoothness {smoothness} not in range [0, 100]"
        
        print(f"PASSED: equity_curve_smoothness={smoothness} is in range [0, 100]")


class TestHoldingTimeCalculation:
    """Test holding time calculations."""
    
    def test_holding_time_calculation_with_timestamps(self):
        """Holding time calculation correct when entry_time and close_time provided."""
        # Create trades with known holding times
        trades = [
            {
                "trade_id": 1,
                "entry_time": "2025-01-01T09:00:00",
                "close_time": "2025-01-01T10:30:00",  # 90 minutes
                "net_pnl": 100,
            },
            {
                "trade_id": 2,
                "entry_time": "2025-01-01T11:00:00",
                "close_time": "2025-01-01T12:00:00",  # 60 minutes
                "net_pnl": 50,
            },
            {
                "trade_id": 3,
                "entry_time": "2025-01-02T09:00:00",
                "close_time": "2025-01-02T10:00:00",  # 60 minutes
                "net_pnl": 75,
            },
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        
        time_metrics = response.json()["profile"]["time"]
        avg_holding = time_metrics["avg_holding_minutes"]
        
        # Expected average: (90 + 60 + 60) / 3 = 70 minutes
        expected_avg = 70.0
        assert abs(avg_holding - expected_avg) < 1, f"Expected ~{expected_avg}, got {avg_holding}"
        
        print(f"PASSED: avg_holding_minutes={avg_holding} (expected ~{expected_avg})")


class TestTagsGeneration:
    """Test that tags are generated based on metrics."""
    
    def test_tags_include_relevant_tags(self):
        """Tags array includes relevant tags like 'high_winrate', 'strong_sharpe', 'tight_dd' based on metrics."""
        # Generate trades with high win rate
        trades = []
        base_date = datetime(2025, 1, 1, 9, 0, 0)
        for i in range(30):
            entry_time = base_date + timedelta(days=i // 3)
            close_time = entry_time + timedelta(hours=1)
            # 80% win rate with consistent small wins
            is_win = i % 5 != 0
            pnl = 150 if is_win else -50
            trades.append({
                "trade_id": i + 1,
                "entry_time": entry_time.isoformat(),
                "close_time": close_time.isoformat(),
                "net_pnl": pnl,
            })
        
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        profile = response.json()["profile"]
        
        tags = profile["classification"]["tags"]
        behavior = profile["behavior"]
        stability = profile["stability"]
        risk = profile["risk"]
        
        print(f"  win_rate: {behavior.get('win_rate')}")
        print(f"  sharpe_ratio: {stability.get('sharpe_ratio')}")
        print(f"  max_drawdown_pct: {risk.get('max_drawdown_pct')}")
        print(f"  tags: {tags}")
        
        assert isinstance(tags, list), "tags should be a list"
        assert len(tags) > 0, "tags should not be empty"
        
        # Check that strategy type is in tags
        strategy_type = profile["classification"]["type"]
        assert strategy_type in tags, f"Strategy type '{strategy_type}' should be in tags"
        
        # Check risk level tag
        risk_level = profile["classification"]["risk_level"]
        risk_tag = f"{risk_level}_risk"
        assert risk_tag in tags, f"Risk tag '{risk_tag}' should be in tags"
        
        print("PASSED: Tags include relevant tags based on metrics")


class TestDataValidation:
    """Test data validation and numeric accuracy."""
    
    def test_win_rate_calculation(self):
        """Win rate is calculated correctly."""
        # 7 wins, 3 losses = 70% win rate
        trades = []
        for i in range(10):
            is_win = i < 7
            trades.append({
                "trade_id": i + 1,
                "entry_time": f"2025-01-0{(i % 9) + 1}T09:00:00",
                "close_time": f"2025-01-0{(i % 9) + 1}T10:00:00",
                "net_pnl": 100 if is_win else -80,
            })
        
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        
        win_rate = response.json()["profile"]["behavior"]["win_rate"]
        assert win_rate == 70.0, f"Expected win_rate=70.0, got {win_rate}"
        
        print(f"PASSED: win_rate={win_rate} calculated correctly")
    
    def test_trades_per_day_calculation(self):
        """Trades per day is calculated correctly."""
        # 10 trades over 5 days = 2 trades/day
        trades = []
        for i in range(10):
            day = (i // 2) + 1
            trades.append({
                "trade_id": i + 1,
                "entry_time": f"2025-01-0{day}T09:00:00",
                "close_time": f"2025-01-0{day}T10:00:00",
                "net_pnl": 100 if i % 2 == 0 else -50,
            })
        
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        
        tpd = response.json()["profile"]["behavior"]["trades_per_day"]
        assert tpd == 2.0, f"Expected trades_per_day=2.0, got {tpd}"
        
        print(f"PASSED: trades_per_day={tpd} calculated correctly")
    
    def test_net_profit_calculation(self):
        """Net profit is calculated correctly."""
        # 5 wins of $100 each, 2 losses of $50 each = $400 net
        trades = []
        for i in range(7):
            is_win = i < 5
            trades.append({
                "trade_id": i + 1,
                "entry_time": f"2025-01-0{i + 1}T09:00:00",
                "close_time": f"2025-01-0{i + 1}T10:00:00",
                "net_pnl": 100 if is_win else -50,
            })
        
        response = requests.post(
            f"{BASE_URL}/api/profile-strategy",
            json={"strategy_trades": trades, "initial_balance": 10000}
        )
        assert response.status_code == 200
        
        net_profit = response.json()["profile"]["stability"]["net_profit"]
        expected = (5 * 100) + (2 * -50)  # 500 - 100 = 400
        assert net_profit == expected, f"Expected net_profit={expected}, got {net_profit}"
        
        print(f"PASSED: net_profit={net_profit} calculated correctly")


# ═══════════════════════════════════════════════════════
# Run tests
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
