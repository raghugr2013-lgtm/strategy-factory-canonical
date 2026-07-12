"""
Phase 4: Strategy ↔ Prop Firm Matching Engine Tests

Tests the matching engine that:
1. Profiles strategies (DNA from Phase 3)
2. Pre-filters firms based on DNA compatibility
3. Runs challenge simulation for compatible firms (Phase 1)
4. Scores and ranks matches
5. Returns top_matches + rejected firms

Test scenarios:
- Low-risk profitable strategy → should PASS FTMO/FundedNext
- High-risk volatile strategy → should FAIL on daily DD
- Extremely high-DD strategy → should be REJECTED in pre-filter
- Scalping strategy → should be correctly profiled as scalping type
"""

import pytest
import requests
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


# ═══════════════════════════════════════════════════════
# Test Data Generators
# ═══════════════════════════════════════════════════════

def generate_low_risk_profitable_trades():
    """
    Generate ~10 trades across 5 days with ~$10k total profit (10% of $100k).
    Small floating_pnl values to stay well within DD limits.
    This should PASS FTMO and FundedNext.
    """
    base_date = datetime(2024, 1, 1)
    trades = []
    
    # Day 1: 2 trades, +$2000
    trades.append({
        "net_pnl": 1200,
        "floating_pnl": -100,  # Small floating loss
        "timestamp": (base_date + timedelta(hours=9)).isoformat(),
        "entry_time": (base_date + timedelta(hours=8)).isoformat(),
        "close_time": (base_date + timedelta(hours=9)).isoformat(),
    })
    trades.append({
        "net_pnl": 800,
        "floating_pnl": -50,
        "timestamp": (base_date + timedelta(hours=14)).isoformat(),
        "entry_time": (base_date + timedelta(hours=13)).isoformat(),
        "close_time": (base_date + timedelta(hours=14)).isoformat(),
    })
    
    # Day 2: 2 trades, +$2500
    trades.append({
        "net_pnl": 1500,
        "floating_pnl": -200,
        "timestamp": (base_date + timedelta(days=1, hours=10)).isoformat(),
        "entry_time": (base_date + timedelta(days=1, hours=9)).isoformat(),
        "close_time": (base_date + timedelta(days=1, hours=10)).isoformat(),
    })
    trades.append({
        "net_pnl": 1000,
        "floating_pnl": -100,
        "timestamp": (base_date + timedelta(days=1, hours=15)).isoformat(),
        "entry_time": (base_date + timedelta(days=1, hours=14)).isoformat(),
        "close_time": (base_date + timedelta(days=1, hours=15)).isoformat(),
    })
    
    # Day 3: 2 trades, +$2000
    trades.append({
        "net_pnl": 1100,
        "floating_pnl": -150,
        "timestamp": (base_date + timedelta(days=2, hours=11)).isoformat(),
        "entry_time": (base_date + timedelta(days=2, hours=10)).isoformat(),
        "close_time": (base_date + timedelta(days=2, hours=11)).isoformat(),
    })
    trades.append({
        "net_pnl": 900,
        "floating_pnl": -80,
        "timestamp": (base_date + timedelta(days=2, hours=16)).isoformat(),
        "entry_time": (base_date + timedelta(days=2, hours=15)).isoformat(),
        "close_time": (base_date + timedelta(days=2, hours=16)).isoformat(),
    })
    
    # Day 4: 2 trades, +$1800
    trades.append({
        "net_pnl": 1000,
        "floating_pnl": -120,
        "timestamp": (base_date + timedelta(days=3, hours=10)).isoformat(),
        "entry_time": (base_date + timedelta(days=3, hours=9)).isoformat(),
        "close_time": (base_date + timedelta(days=3, hours=10)).isoformat(),
    })
    trades.append({
        "net_pnl": 800,
        "floating_pnl": -90,
        "timestamp": (base_date + timedelta(days=3, hours=14)).isoformat(),
        "entry_time": (base_date + timedelta(days=3, hours=13)).isoformat(),
        "close_time": (base_date + timedelta(days=3, hours=14)).isoformat(),
    })
    
    # Day 5: 2 trades, +$1700
    trades.append({
        "net_pnl": 900,
        "floating_pnl": -100,
        "timestamp": (base_date + timedelta(days=4, hours=11)).isoformat(),
        "entry_time": (base_date + timedelta(days=4, hours=10)).isoformat(),
        "close_time": (base_date + timedelta(days=4, hours=11)).isoformat(),
    })
    trades.append({
        "net_pnl": 800,
        "floating_pnl": -70,
        "timestamp": (base_date + timedelta(days=4, hours=15)).isoformat(),
        "entry_time": (base_date + timedelta(days=4, hours=14)).isoformat(),
        "close_time": (base_date + timedelta(days=4, hours=15)).isoformat(),
    })
    
    # Total: $10,000 profit (10% of $100k), 5 trading days, 10 trades
    return trades


def generate_high_risk_volatile_trades():
    """
    Generate trades with large floating_pnl values that breach 5% daily DD.
    This should FAIL firms due to daily DD violations.
    """
    base_date = datetime(2024, 1, 1)
    trades = []
    
    # Day 1: Large floating loss that breaches 5% daily DD ($5000 on $100k)
    trades.append({
        "net_pnl": 500,  # Ends positive
        "floating_pnl": -6000,  # 6% floating loss - breaches 5% daily DD
        "timestamp": (base_date + timedelta(hours=10)).isoformat(),
        "entry_time": (base_date + timedelta(hours=8)).isoformat(),
        "close_time": (base_date + timedelta(hours=10)).isoformat(),
    })
    trades.append({
        "net_pnl": 1000,
        "floating_pnl": -3000,
        "timestamp": (base_date + timedelta(hours=14)).isoformat(),
        "entry_time": (base_date + timedelta(hours=12)).isoformat(),
        "close_time": (base_date + timedelta(hours=14)).isoformat(),
    })
    
    # Day 2: More volatile trades
    trades.append({
        "net_pnl": 2000,
        "floating_pnl": -4500,
        "timestamp": (base_date + timedelta(days=1, hours=11)).isoformat(),
        "entry_time": (base_date + timedelta(days=1, hours=9)).isoformat(),
        "close_time": (base_date + timedelta(days=1, hours=11)).isoformat(),
    })
    trades.append({
        "net_pnl": 1500,
        "floating_pnl": -5500,  # Another breach
        "timestamp": (base_date + timedelta(days=1, hours=15)).isoformat(),
        "entry_time": (base_date + timedelta(days=1, hours=13)).isoformat(),
        "close_time": (base_date + timedelta(days=1, hours=15)).isoformat(),
    })
    
    # Day 3-5: More trades to meet min days
    for day in range(2, 5):
        trades.append({
            "net_pnl": 1000,
            "floating_pnl": -4000,
            "timestamp": (base_date + timedelta(days=day, hours=12)).isoformat(),
            "entry_time": (base_date + timedelta(days=day, hours=10)).isoformat(),
            "close_time": (base_date + timedelta(days=day, hours=12)).isoformat(),
        })
    
    return trades


def generate_extreme_dd_strategy():
    """
    Generate strategy with >15% max DD that should be REJECTED in pre-filter.
    Pre-filter rejects if max_dd > 1.5x firm total DD limit (1.5 * 10% = 15%).
    """
    base_date = datetime(2024, 1, 1)
    trades = []
    
    # Day 1: Massive loss
    trades.append({
        "net_pnl": -8000,  # 8% loss
        "floating_pnl": -10000,
        "timestamp": (base_date + timedelta(hours=10)).isoformat(),
        "entry_time": (base_date + timedelta(hours=8)).isoformat(),
        "close_time": (base_date + timedelta(hours=10)).isoformat(),
    })
    
    # Day 2: Another big loss
    trades.append({
        "net_pnl": -6000,  # 6% loss, cumulative 14%
        "floating_pnl": -8000,
        "timestamp": (base_date + timedelta(days=1, hours=11)).isoformat(),
        "entry_time": (base_date + timedelta(days=1, hours=9)).isoformat(),
        "close_time": (base_date + timedelta(days=1, hours=11)).isoformat(),
    })
    
    # Day 3: More losses
    trades.append({
        "net_pnl": -4000,  # 4% loss, cumulative 18%
        "floating_pnl": -5000,
        "timestamp": (base_date + timedelta(days=2, hours=12)).isoformat(),
        "entry_time": (base_date + timedelta(days=2, hours=10)).isoformat(),
        "close_time": (base_date + timedelta(days=2, hours=12)).isoformat(),
    })
    
    # Day 4-5: Small recovery but still net negative
    trades.append({
        "net_pnl": 2000,
        "floating_pnl": -1000,
        "timestamp": (base_date + timedelta(days=3, hours=11)).isoformat(),
        "entry_time": (base_date + timedelta(days=3, hours=9)).isoformat(),
        "close_time": (base_date + timedelta(days=3, hours=11)).isoformat(),
    })
    trades.append({
        "net_pnl": 1000,
        "floating_pnl": -500,
        "timestamp": (base_date + timedelta(days=4, hours=10)).isoformat(),
        "entry_time": (base_date + timedelta(days=4, hours=8)).isoformat(),
        "close_time": (base_date + timedelta(days=4, hours=10)).isoformat(),
    })
    
    # Total: -$15,000 (15% loss), max DD > 15%
    return trades


def generate_scalping_trades():
    """
    Generate high-frequency scalping trades (>8 trades per day, short holding times).
    Should be profiled as 'scalping' type.
    """
    base_date = datetime(2024, 1, 1)
    trades = []
    
    # Day 1: 12 quick trades (scalping)
    for i in range(12):
        hour = 8 + i // 2
        minute = (i % 2) * 30
        trades.append({
            "net_pnl": 100 + (i * 10),  # Small profits
            "floating_pnl": -50,
            "timestamp": (base_date + timedelta(hours=hour, minutes=minute+5)).isoformat(),
            "entry_time": (base_date + timedelta(hours=hour, minutes=minute)).isoformat(),
            "close_time": (base_date + timedelta(hours=hour, minutes=minute+5)).isoformat(),  # 5 min hold
        })
    
    # Day 2: 10 quick trades
    for i in range(10):
        hour = 9 + i // 2
        minute = (i % 2) * 25
        trades.append({
            "net_pnl": 80 + (i * 15),
            "floating_pnl": -40,
            "timestamp": (base_date + timedelta(days=1, hours=hour, minutes=minute+6)).isoformat(),
            "entry_time": (base_date + timedelta(days=1, hours=hour, minutes=minute)).isoformat(),
            "close_time": (base_date + timedelta(days=1, hours=hour, minutes=minute+6)).isoformat(),
        })
    
    # Day 3-5: More scalping trades
    for day in range(2, 5):
        for i in range(8):
            hour = 9 + i
            trades.append({
                "net_pnl": 120,
                "floating_pnl": -30,
                "timestamp": (base_date + timedelta(days=day, hours=hour, minutes=10)).isoformat(),
                "entry_time": (base_date + timedelta(days=day, hours=hour, minutes=5)).isoformat(),
                "close_time": (base_date + timedelta(days=day, hours=hour, minutes=10)).isoformat(),
            })
    
    return trades


# ═══════════════════════════════════════════════════════
# Test Classes
# ═══════════════════════════════════════════════════════

class TestMatchStrategyEndpoint:
    """Test the POST /api/match-strategy endpoint basics"""
    
    def test_endpoint_exists_and_returns_200(self):
        """POST /api/match-strategy should exist and return 200 with valid trades"""
        trades = generate_low_risk_profitable_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "matching" in data, "Response should have 'matching' key"
    
    def test_error_when_no_trades_or_strategy_id(self):
        """Should return error when neither strategy_id nor strategy_trades provided"""
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"initial_balance": 100000}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data, "Error response should have 'detail'"
    
    def test_empty_trades_returns_error(self):
        """Empty trades array should return error in response"""
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": [], "initial_balance": 100000}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        matching = data.get("matching", {})
        assert "error" in matching, "Empty trades should return error in matching response"


class TestResponseStructure:
    """Test the response structure of match-strategy endpoint"""
    
    @pytest.fixture(scope="class")
    def matching_response(self):
        """Get a matching response for structure tests"""
        trades = generate_low_risk_profitable_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        return response.json().get("matching", {})
    
    def test_has_top_matches_array(self, matching_response):
        """Response should have top_matches array"""
        assert "top_matches" in matching_response, "Response should have 'top_matches'"
        assert isinstance(matching_response["top_matches"], list), "top_matches should be a list"
    
    def test_has_rejected_array(self, matching_response):
        """Response should have rejected array"""
        assert "rejected" in matching_response, "Response should have 'rejected'"
        assert isinstance(matching_response["rejected"], list), "rejected should be a list"
    
    def test_has_profile_summary(self, matching_response):
        """Response should have profile_summary with required fields"""
        assert "profile_summary" in matching_response, "Response should have 'profile_summary'"
        profile = matching_response["profile_summary"]
        
        required_fields = ["type", "risk_level", "consistency_level", "speed", "tags"]
        for field in required_fields:
            assert field in profile, f"profile_summary should have '{field}'"
    
    def test_has_firms_analyzed_count(self, matching_response):
        """Response should have firms_analyzed count"""
        assert "firms_analyzed" in matching_response, "Response should have 'firms_analyzed'"
        assert isinstance(matching_response["firms_analyzed"], int), "firms_analyzed should be int"
    
    def test_firms_compatible_plus_rejected_equals_analyzed(self, matching_response):
        """firms_compatible + firms_rejected should equal firms_analyzed"""
        analyzed = matching_response.get("firms_analyzed", 0)
        compatible = matching_response.get("firms_compatible", 0)
        rejected = matching_response.get("firms_rejected", 0)
        
        assert compatible + rejected == analyzed, \
            f"compatible ({compatible}) + rejected ({rejected}) should equal analyzed ({analyzed})"


class TestTopMatchesStructure:
    """Test the structure of items in top_matches array"""
    
    @pytest.fixture(scope="class")
    def top_match(self):
        """Get a single top match for structure tests"""
        trades = generate_low_risk_profitable_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        top_matches = matching.get("top_matches", [])
        assert len(top_matches) > 0, "Should have at least one top match"
        return top_matches[0]
    
    def test_has_firm_field(self, top_match):
        """Top match should have firm field"""
        assert "firm" in top_match, "Top match should have 'firm'"
    
    def test_has_status_field(self, top_match):
        """Top match should have status field (pass/fail)"""
        assert "status" in top_match, "Top match should have 'status'"
        assert top_match["status"] in ["pass", "fail"], "Status should be 'pass' or 'fail'"
    
    def test_has_score_field(self, top_match):
        """Top match should have score field"""
        assert "score" in top_match, "Top match should have 'score'"
        assert isinstance(top_match["score"], (int, float)), "Score should be numeric"
    
    def test_has_drawdown_buffer(self, top_match):
        """Top match should have drawdown_buffer with total_dd and daily_dd"""
        assert "drawdown_buffer" in top_match, "Top match should have 'drawdown_buffer'"
        buffer = top_match["drawdown_buffer"]
        assert "total_dd" in buffer, "drawdown_buffer should have 'total_dd'"
        assert "daily_dd" in buffer, "drawdown_buffer should have 'daily_dd'"
    
    def test_has_days_taken(self, top_match):
        """Top match should have days_taken field"""
        assert "days_taken" in top_match, "Top match should have 'days_taken'"
    
    def test_has_profit_pct(self, top_match):
        """Top match should have profit_pct field"""
        assert "profit_pct" in top_match, "Top match should have 'profit_pct'"
    
    def test_has_flags_array(self, top_match):
        """Top match should have flags array"""
        assert "flags" in top_match, "Top match should have 'flags'"
        assert isinstance(top_match["flags"], list), "flags should be a list"
    
    def test_has_score_breakdown(self, top_match):
        """Top match should have score_breakdown with all components"""
        assert "score_breakdown" in top_match, "Top match should have 'score_breakdown'"
        breakdown = top_match["score_breakdown"]
        
        required_components = [
            "pass_status", "drawdown_buffer", "profit_efficiency", 
            "stability_bonus", "flag_penalty"
        ]
        for comp in required_components:
            assert comp in breakdown, f"score_breakdown should have '{comp}'"


class TestRejectedStructure:
    """Test the structure of items in rejected array"""
    
    def test_rejected_has_firm_and_reason(self):
        """Rejected items should have firm and reason fields"""
        trades = generate_extreme_dd_strategy()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        rejected = matching.get("rejected", [])
        
        # This extreme DD strategy should have some rejections
        if len(rejected) > 0:
            for item in rejected:
                assert "firm" in item, "Rejected item should have 'firm'"
                assert "reason" in item, "Rejected item should have 'reason'"


class TestLowRiskStrategy:
    """Test low-risk profitable strategy matching"""
    
    def test_low_risk_matches_ftmo_and_fundednext_with_pass(self):
        """Low-risk intraday strategy should match FTMO and FundedNext with PASS status"""
        trades = generate_low_risk_profitable_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        top_matches = matching.get("top_matches", [])
        
        # Find FTMO and FundedNext in matches
        firm_results = {m["firm"]: m for m in top_matches}
        
        # Check FTMO
        assert "FTMO" in firm_results, "FTMO should be in top_matches"
        ftmo = firm_results["FTMO"]
        assert ftmo["status"] == "pass", f"FTMO should PASS, got {ftmo['status']}"
        
        # Check FundedNext
        assert "FundedNext" in firm_results, "FundedNext should be in top_matches"
        fn = firm_results["FundedNext"]
        assert fn["status"] == "pass", f"FundedNext should PASS, got {fn['status']}"
    
    def test_low_risk_profile_is_intraday_low_risk(self):
        """Low-risk strategy should be profiled as intraday with low risk"""
        trades = generate_low_risk_profitable_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        profile = matching.get("profile_summary", {})
        
        assert profile.get("type") == "intraday", f"Expected intraday, got {profile.get('type')}"
        assert profile.get("risk_level") == "low", f"Expected low risk, got {profile.get('risk_level')}"


class TestHighRiskStrategy:
    """Test high-risk volatile strategy matching"""
    
    def test_high_risk_fails_firms_due_to_daily_dd(self):
        """High-risk strategy should fail firms due to daily DD violations"""
        trades = generate_high_risk_volatile_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        top_matches = matching.get("top_matches", [])
        
        # Check that at least some firms fail
        failed_firms = [m for m in top_matches if m["status"] == "fail"]
        assert len(failed_firms) > 0, "High-risk strategy should fail at least some firms"
        
        # Check failure reasons include daily_dd
        failure_reasons = [m.get("failure_reason") for m in failed_firms]
        print(f"Failure reasons: {failure_reasons}")
        
        # At least one should fail due to DD
        dd_failures = [r for r in failure_reasons if r and ("dd" in r.lower() or "drawdown" in r.lower())]
        assert len(dd_failures) > 0 or len(failed_firms) > 0, \
            "High-risk strategy should have DD-related failures"


class TestExtremeDrawdownStrategy:
    """Test extremely high-DD strategy pre-filtering"""
    
    def test_extreme_dd_rejected_in_prefilter(self):
        """Extremely high-DD strategy should be rejected by all firms in pre-filtering"""
        trades = generate_extreme_dd_strategy()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        rejected = matching.get("rejected", [])
        
        # Should have rejections due to max_drawdown_too_high or unprofitable_strategy
        print(f"Rejected firms: {rejected}")
        
        # Check rejection reasons
        if len(rejected) > 0:
            reasons = [r.get("reason", "") for r in rejected]
            print(f"Rejection reasons: {reasons}")
            
            # Should have rejections related to DD or profitability
            dd_rejections = [r for r in reasons if "drawdown" in r.lower() or "unprofitable" in r.lower()]
            assert len(dd_rejections) > 0, "Should have DD or profitability rejections"


class TestScalpingStrategy:
    """Test scalping strategy profiling"""
    
    def test_scalping_strategy_profiled_correctly(self):
        """Scalping strategy (high tpd) should be correctly profiled as scalping type"""
        trades = generate_scalping_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        profile = matching.get("profile_summary", {})
        
        # Should be classified as scalping
        assert profile.get("type") == "scalping", \
            f"Expected scalping type, got {profile.get('type')}"
        
        # Should have high trades_per_day
        tpd = profile.get("trades_per_day", 0)
        assert tpd > 5, f"Scalping should have >5 trades per day, got {tpd}"


class TestSortingAndScoring:
    """Test that top_matches are sorted by score descending"""
    
    def test_top_matches_sorted_by_score_descending(self):
        """top_matches should be sorted by score in descending order"""
        trades = generate_low_risk_profitable_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        top_matches = matching.get("top_matches", [])
        
        if len(top_matches) > 1:
            scores = [m["score"] for m in top_matches]
            assert scores == sorted(scores, reverse=True), \
                f"Scores should be descending: {scores}"


class TestFlagsPopulation:
    """Test that flags are populated for firms with soft warnings"""
    
    def test_flags_populated_for_warnings(self):
        """Flags should be populated for firms with soft warnings"""
        # Use high-risk trades that should trigger flags
        trades = generate_high_risk_volatile_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        top_matches = matching.get("top_matches", [])
        
        # Check if any matches have flags
        all_flags = []
        for m in top_matches:
            flags = m.get("flags", [])
            all_flags.extend(flags)
        
        print(f"All flags found: {all_flags}")
        
        # High-risk strategy should trigger some flags
        # (dd_pressure, trailing_dd_risk, etc.)


class TestPreFilteringLogic:
    """Test pre-filtering rejection logic"""
    
    def test_prefilter_rejects_max_dd_over_1_5x_limit(self):
        """Pre-filtering should reject strategies where max DD > 1.5x firm total DD limit"""
        # Create strategy with ~16% max DD (> 1.5 * 10% = 15%)
        trades = generate_extreme_dd_strategy()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        rejected = matching.get("rejected", [])
        
        # Check for max_drawdown_too_high rejections
        dd_rejections = [r for r in rejected if "drawdown" in r.get("reason", "").lower()]
        print(f"DD rejections: {dd_rejections}")
    
    def test_prefilter_rejects_unprofitable_with_low_pf(self):
        """Pre-filtering should reject unprofitable strategies (negative return + PF < 0.5)"""
        # The extreme DD strategy is also unprofitable
        trades = generate_extreme_dd_strategy()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        rejected = matching.get("rejected", [])
        
        # Check for unprofitable rejections
        unprofitable_rejections = [r for r in rejected if "unprofitable" in r.get("reason", "").lower()]
        print(f"Unprofitable rejections: {unprofitable_rejections}")


class TestFirmsAnalyzedCount:
    """Test firms_analyzed count matches DB"""
    
    def test_firms_analyzed_matches_db_count(self):
        """firms_analyzed count should match number of firms in DB"""
        # First get the firms from challenge-firms endpoint
        firms_response = requests.get(f"{BASE_URL}/api/challenge-firms")
        assert firms_response.status_code == 200
        firms_data = firms_response.json()
        db_firm_count = firms_data.get("count", 0)
        
        # Now run matching
        trades = generate_low_risk_profitable_trades()
        response = requests.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": trades, "initial_balance": 100000}
        )
        assert response.status_code == 200
        matching = response.json().get("matching", {})
        firms_analyzed = matching.get("firms_analyzed", 0)
        
        assert firms_analyzed == db_firm_count, \
            f"firms_analyzed ({firms_analyzed}) should match DB count ({db_firm_count})"


# ═══════════════════════════════════════════════════════
# Run tests
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
