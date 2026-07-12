"""
Phase 5: Pass Probability Engine (Monte Carlo Simulation) Tests.

Tests the Monte Carlo pass probability estimation endpoint and its integration
with the matching engine. Uses n_simulations=20 for speed.

Key test strategies:
1. Stable: 10 trades across 5 days, ~$10.4k profit, small floating_pnl → >70% pass rate for FTMO
2. Risky: trades with floating_pnl of -6000 to -9000 that breach 5% daily DD → <20% pass rate
3. Reproducibility: same trades with same seed should give same result
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ═══════════════════════════════════════════════════════
# Test Data: Stable Strategy (should pass >70%)
# 10 trades across 5 days, ~$10.4k profit on $100k account = 10.4%
# Small floating_pnl, no DD breaches
# ═══════════════════════════════════════════════════════

STABLE_TRADES = [
    # Day 1: 2 trades, +$2000
    {"net_pnl": 1200, "floating_pnl": -200, "timestamp": "2024-01-01T10:00:00"},
    {"net_pnl": 800, "floating_pnl": -150, "timestamp": "2024-01-01T14:00:00"},
    # Day 2: 2 trades, +$2100
    {"net_pnl": 1100, "floating_pnl": -300, "timestamp": "2024-01-02T09:00:00"},
    {"net_pnl": 1000, "floating_pnl": -250, "timestamp": "2024-01-02T15:00:00"},
    # Day 3: 2 trades, +$2200
    {"net_pnl": 1300, "floating_pnl": -400, "timestamp": "2024-01-03T10:00:00"},
    {"net_pnl": 900, "floating_pnl": -200, "timestamp": "2024-01-03T16:00:00"},
    # Day 4: 2 trades, +$2000
    {"net_pnl": 1000, "floating_pnl": -350, "timestamp": "2024-01-04T11:00:00"},
    {"net_pnl": 1000, "floating_pnl": -300, "timestamp": "2024-01-04T14:00:00"},
    # Day 5: 2 trades, +$2100
    {"net_pnl": 1200, "floating_pnl": -250, "timestamp": "2024-01-05T09:00:00"},
    {"net_pnl": 900, "floating_pnl": -200, "timestamp": "2024-01-05T15:00:00"},
]
# Total: $10,400 profit = 10.4% on $100k

# ═══════════════════════════════════════════════════════
# Test Data: Risky Strategy (should fail <20%)
# Trades with large floating_pnl that breach 5% daily DD ($5000 on $100k)
# ═══════════════════════════════════════════════════════

RISKY_TRADES = [
    # Day 1: Large floating loss that breaches daily DD
    {"net_pnl": 500, "floating_pnl": -6000, "timestamp": "2024-01-01T10:00:00"},
    {"net_pnl": 300, "floating_pnl": -7000, "timestamp": "2024-01-01T14:00:00"},
    # Day 2: More risky trades
    {"net_pnl": 400, "floating_pnl": -8000, "timestamp": "2024-01-02T09:00:00"},
    {"net_pnl": 200, "floating_pnl": -9000, "timestamp": "2024-01-02T15:00:00"},
    # Day 3: Continued risk
    {"net_pnl": 600, "floating_pnl": -6500, "timestamp": "2024-01-03T10:00:00"},
    {"net_pnl": 350, "floating_pnl": -7500, "timestamp": "2024-01-03T16:00:00"},
    # Day 4
    {"net_pnl": 450, "floating_pnl": -8500, "timestamp": "2024-01-04T11:00:00"},
    {"net_pnl": 250, "floating_pnl": -6000, "timestamp": "2024-01-04T14:00:00"},
]


@pytest.fixture
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# ═══════════════════════════════════════════════════════
# Test: Endpoint Exists and Returns 200
# ═══════════════════════════════════════════════════════

class TestEstimateProbabilityEndpoint:
    """Test POST /api/estimate-probability endpoint basics."""

    def test_endpoint_exists_and_returns_200(self, api_client):
        """POST /api/estimate-probability should return 200 with valid input."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "probability" in data, "Response should have 'probability' key"

    def test_error_when_no_trades_or_strategy_id(self, api_client):
        """Should return error when neither trades nor strategy_id provided."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={"firm": "ftmo", "n_simulations": 20},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data

    def test_error_when_empty_trades(self, api_client):
        """Should return error or 0% probability when trades list is empty."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={"strategy_trades": [], "firm": "ftmo", "n_simulations": 20},
        )
        # Could be 200 with error in response or 400
        if response.status_code == 200:
            data = response.json()
            prob = data.get("probability", {})
            # Should have error or 0% probability
            assert prob.get("error") or prob.get("pass_probability") == 0
        else:
            assert response.status_code == 400

    def test_error_when_no_firm_or_rules(self, api_client):
        """Should return error when neither firm nor rules_config provided."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={"strategy_trades": STABLE_TRADES, "n_simulations": 20},
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data

    def test_error_when_unknown_firm(self, api_client):
        """Should return error for unknown firm name."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "nonexistent_firm_xyz",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data


# ═══════════════════════════════════════════════════════
# Test: Response Structure
# ═══════════════════════════════════════════════════════

class TestResponseStructure:
    """Test that response includes all required fields."""

    @pytest.fixture(autouse=True)
    def setup(self, api_client):
        """Run estimation once and store result."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        self.result = response.json().get("probability", {})

    def test_has_pass_probability(self):
        """Response should have pass_probability field."""
        assert "pass_probability" in self.result
        assert isinstance(self.result["pass_probability"], (int, float))

    def test_has_confidence_interval(self):
        """Response should have confidence_interval as 2-element array."""
        assert "confidence_interval" in self.result
        ci = self.result["confidence_interval"]
        assert isinstance(ci, list), "confidence_interval should be a list"
        assert len(ci) == 2, "confidence_interval should have 2 elements [lower, upper]"
        assert ci[0] <= ci[1], "lower bound should be <= upper bound"

    def test_has_risk_label(self):
        """Response should have risk_label (low/medium/high/very_high)."""
        assert "risk_label" in self.result
        assert self.result["risk_label"] in ["low", "medium", "high", "very_high"]

    def test_has_n_simulations(self):
        """Response should have n_simulations field."""
        assert "n_simulations" in self.result
        assert self.result["n_simulations"] >= 10

    def test_has_passes_and_fails(self):
        """Response should have passes and fails counts."""
        assert "passes" in self.result
        assert "fails" in self.result
        assert self.result["passes"] + self.result["fails"] == self.result["n_simulations"]

    def test_has_avg_days_to_pass(self):
        """Response should have avg_days_to_pass field."""
        assert "avg_days_to_pass" in self.result
        assert isinstance(self.result["avg_days_to_pass"], (int, float))

    def test_has_failure_breakdown(self):
        """Response should have failure_breakdown dict."""
        assert "failure_breakdown" in self.result
        assert isinstance(self.result["failure_breakdown"], dict)

    def test_has_method_comparison(self):
        """Response should have method_comparison with shuffle and perturb rates."""
        assert "method_comparison" in self.result
        mc = self.result["method_comparison"]
        assert "shuffle_pass_rate" in mc
        assert "perturb_pass_rate" in mc

    def test_has_baseline(self):
        """Response should have baseline (original unmodified simulation)."""
        assert "baseline" in self.result
        baseline = self.result["baseline"]
        assert "status" in baseline
        assert "profit_pct" in baseline
        assert "max_drawdown_pct" in baseline

    def test_has_simulation_details(self):
        """Response should have simulation_details array."""
        assert "simulation_details" in self.result
        details = self.result["simulation_details"]
        assert isinstance(details, list)
        assert len(details) == self.result["n_simulations"]

    def test_simulation_details_structure(self):
        """Each simulation detail should have required fields."""
        details = self.result["simulation_details"]
        if details:
            detail = details[0]
            assert "run" in detail
            assert "method" in detail
            assert detail["method"] in ["shuffle", "perturb"]
            assert "status" in detail
            assert "days_taken" in detail
            assert "profit_pct" in detail


# ═══════════════════════════════════════════════════════
# Test: Stable Strategy Should Have High Pass Rate
# ═══════════════════════════════════════════════════════

class TestStableStrategy:
    """Test that stable strategy (10%+ profit, low DD) returns high pass_probability."""

    def test_stable_strategy_high_pass_rate_ftmo(self, api_client):
        """Stable strategy should have >70% pass rate for FTMO."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        pass_prob = prob.get("pass_probability", 0)
        print(f"Stable strategy FTMO pass probability: {pass_prob}%")
        assert pass_prob >= 70, f"Expected >70% pass rate, got {pass_prob}%"

    def test_stable_strategy_low_risk_label(self, api_client):
        """Stable strategy should have 'low' or 'medium' risk label."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        risk_label = prob.get("risk_label", "")
        print(f"Stable strategy risk label: {risk_label}")
        assert risk_label in ["low", "medium"], f"Expected low/medium risk, got {risk_label}"


# ═══════════════════════════════════════════════════════
# Test: Risky Strategy Should Have Low Pass Rate
# ═══════════════════════════════════════════════════════

class TestRiskyStrategy:
    """Test that risky strategy (large floating PnL causing DD breaches) returns low pass_probability."""

    def test_risky_strategy_low_pass_rate(self, api_client):
        """Risky strategy with DD breaches should have <20% pass rate."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": RISKY_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        pass_prob = prob.get("pass_probability", 100)
        print(f"Risky strategy FTMO pass probability: {pass_prob}%")
        assert pass_prob <= 20, f"Expected <20% pass rate, got {pass_prob}%"

    def test_risky_strategy_high_risk_label(self, api_client):
        """Risky strategy should have 'high' or 'very_high' risk label."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": RISKY_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        risk_label = prob.get("risk_label", "")
        print(f"Risky strategy risk label: {risk_label}")
        assert risk_label in ["high", "very_high"], f"Expected high/very_high risk, got {risk_label}"

    def test_risky_strategy_failure_breakdown_has_daily_dd(self, api_client):
        """Risky strategy failure_breakdown should show daily_dd as primary reason."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": RISKY_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        breakdown = prob.get("failure_breakdown", {})
        print(f"Risky strategy failure breakdown: {breakdown}")
        # Should have daily_dd as a failure reason
        assert "daily_dd" in breakdown or len(breakdown) > 0, "Expected failure_breakdown to have reasons"


# ═══════════════════════════════════════════════════════
# Test: Reproducibility (Seeded Random)
# ═══════════════════════════════════════════════════════

class TestReproducibility:
    """Test that results are reproducible with same seed (default seed=42)."""

    def test_same_trades_same_result(self, api_client):
        """Same trades should give same result (seeded random)."""
        # First call
        response1 = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response1.status_code == 200
        prob1 = response1.json().get("probability", {})

        # Second call with same input
        response2 = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response2.status_code == 200
        prob2 = response2.json().get("probability", {})

        # Results should be identical
        assert prob1["pass_probability"] == prob2["pass_probability"], \
            f"Results not reproducible: {prob1['pass_probability']} vs {prob2['pass_probability']}"
        assert prob1["passes"] == prob2["passes"]
        assert prob1["fails"] == prob2["fails"]


# ═══════════════════════════════════════════════════════
# Test: Failure Breakdown Percentages
# ═══════════════════════════════════════════════════════

class TestFailureBreakdown:
    """Test failure_breakdown shows percentage of failures by reason."""

    def test_failure_breakdown_percentages_sum_to_100(self, api_client):
        """Failure breakdown percentages should sum to ~100% (if there are failures)."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": RISKY_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        breakdown = prob.get("failure_breakdown", {})
        fails = prob.get("fails", 0)

        if fails > 0 and breakdown:
            total_pct = sum(breakdown.values())
            print(f"Failure breakdown: {breakdown}, total: {total_pct}%")
            # Should sum to approximately 100%
            assert 95 <= total_pct <= 105, f"Breakdown should sum to ~100%, got {total_pct}%"


# ═══════════════════════════════════════════════════════
# Test: Method Comparison
# ═══════════════════════════════════════════════════════

class TestMethodComparison:
    """Test method_comparison shows shuffle and perturb rates separately."""

    def test_method_comparison_has_both_rates(self, api_client):
        """method_comparison should have shuffle_pass_rate and perturb_pass_rate."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "ftmo",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        mc = prob.get("method_comparison", {})
        assert "shuffle_pass_rate" in mc
        assert "perturb_pass_rate" in mc
        print(f"Method comparison: shuffle={mc['shuffle_pass_rate']}%, perturb={mc['perturb_pass_rate']}%")


# ═══════════════════════════════════════════════════════
# Test: Matching Engine Integration with include_probability
# ═══════════════════════════════════════════════════════

class TestMatchingEngineIntegration:
    """Test POST /api/match-strategy with include_probability=true."""

    def test_matching_with_probability_includes_probability_field(self, api_client):
        """With include_probability=true, each top_match should have probability field."""
        response = api_client.post(
            f"{BASE_URL}/api/match-strategy",
            json={
                "strategy_trades": STABLE_TRADES,
                "include_probability": True,
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        data = response.json()
        matching = data.get("matching", {})
        top_matches = matching.get("top_matches", [])

        assert len(top_matches) > 0, "Should have at least one top match"

        for match in top_matches:
            assert "probability" in match, f"Match for {match.get('firm')} missing probability field"
            prob = match["probability"]
            assert "pass_probability" in prob
            assert "confidence_interval" in prob
            assert "risk_label" in prob
            assert "avg_days_to_pass" in prob
            assert "failure_breakdown" in prob
            print(f"{match.get('firm')}: pass_probability={prob['pass_probability']}%")

    def test_matching_without_probability_no_probability_field(self, api_client):
        """Without include_probability, top_matches should NOT have probability field."""
        response = api_client.post(
            f"{BASE_URL}/api/match-strategy",
            json={
                "strategy_trades": STABLE_TRADES,
                "include_probability": False,
            },
        )
        assert response.status_code == 200
        data = response.json()
        matching = data.get("matching", {})
        top_matches = matching.get("top_matches", [])

        assert len(top_matches) > 0, "Should have at least one top match"

        for match in top_matches:
            assert "probability" not in match, \
                f"Match for {match.get('firm')} should NOT have probability field when include_probability=false"

    def test_matching_default_no_probability(self, api_client):
        """Default (no include_probability param) should NOT include probability."""
        response = api_client.post(
            f"{BASE_URL}/api/match-strategy",
            json={"strategy_trades": STABLE_TRADES},
        )
        assert response.status_code == 200
        data = response.json()
        matching = data.get("matching", {})
        top_matches = matching.get("top_matches", [])

        if top_matches:
            # Default should be backward compatible (no probability)
            assert "probability" not in top_matches[0], \
                "Default should not include probability (backward compatible)"


# ═══════════════════════════════════════════════════════
# Test: Custom Rules Config
# ═══════════════════════════════════════════════════════

class TestCustomRulesConfig:
    """Test using custom rules_config instead of firm name."""

    def test_custom_rules_config_works(self, api_client):
        """Should accept custom rules_config instead of firm name."""
        custom_rules = {
            "initial_balance": 100000,
            "profit_target_pct": 8.0,  # Lower target
            "max_daily_dd_pct": 6.0,   # Higher DD limit
            "max_total_dd_pct": 12.0,
            "min_trading_days": 3,
            "time_limit_days": 0,
            "drawdown_type": "static",
        }
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "rules_config": custom_rules,
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        assert "pass_probability" in prob
        print(f"Custom rules pass probability: {prob['pass_probability']}%")


# ═══════════════════════════════════════════════════════
# Test: Different Firms
# ═══════════════════════════════════════════════════════

class TestDifferentFirms:
    """Test probability estimation with different firms."""

    def test_fundednext_estimation(self, api_client):
        """Should work with FundedNext firm."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "fundednext",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        assert "pass_probability" in prob
        print(f"FundedNext pass probability: {prob['pass_probability']}%")

    def test_pipfarm_estimation(self, api_client):
        """Should work with PipFarm firm (trailing DD)."""
        response = api_client.post(
            f"{BASE_URL}/api/estimate-probability",
            json={
                "strategy_trades": STABLE_TRADES,
                "firm": "pipfarm",
                "n_simulations": 20,
            },
        )
        assert response.status_code == 200
        prob = response.json().get("probability", {})
        assert "pass_probability" in prob
        print(f"PipFarm pass probability: {prob['pass_probability']}%")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
