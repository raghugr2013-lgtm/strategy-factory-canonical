"""
Test suite for Random Search Optimization Engine (Phase 1).
Tests the /api/optimize-random endpoint with various scenarios.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Sample strategy text for testing
SAMPLE_STRATEGY = """
Buy when fast EMA crosses above slow EMA and RSI is below 70.
Sell when fast EMA crosses below slow EMA or RSI is above 80.
Use 20 pip stop loss and 40 pip take profit.
"""


class TestRandomSearchEndpoint:
    """Tests for POST /api/optimize-random endpoint"""

    def test_endpoint_exists_and_accepts_requests(self):
        """Verify endpoint exists and accepts POST requests"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        # Should return 200 (success) or 400 (no data) - not 404/405
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code}"

    def test_rejects_request_when_no_real_data(self):
        """Endpoint should return 400 when no real data exists for pair/timeframe"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "GBPUSD",  # No data for this pair
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "real historical data" in data["detail"].lower() or "download data" in data["detail"].lower()

    def test_success_with_real_data_eurusd_h1(self):
        """Endpoint returns success with train/test split metrics when real data exists"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "optimization" in data
        opt = data["optimization"]
        assert opt.get("success") == True
        assert opt.get("method") == "random_search"

    def test_response_includes_top_10_array(self):
        """Response should include top_10 array with at least 1 entry"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        assert "top_10" in opt
        assert isinstance(opt["top_10"], list)
        assert len(opt["top_10"]) >= 1

    def test_top_10_entry_structure(self):
        """Each top_10 entry should have required fields"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        # Check first entry has all required fields
        entry = opt["top_10"][0]
        required_fields = ["rank", "parameters", "fitness", "sharpe_ratio", "overfit_score", "train", "test", "fitness_breakdown"]
        for field in required_fields:
            assert field in entry, f"Missing field: {field}"

    def test_train_metrics_structure(self):
        """Train metrics should include required fields"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        train = opt["top_10"][0]["train"]
        required_train_fields = ["net_profit", "sharpe_ratio", "max_drawdown_pct", "total_trades", "total_costs"]
        for field in required_train_fields:
            assert field in train, f"Missing train field: {field}"

    def test_test_metrics_structure(self):
        """Test metrics should include required fields"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        test = opt["top_10"][0]["test"]
        required_test_fields = ["net_profit", "sharpe_ratio", "max_drawdown_pct"]
        for field in required_test_fields:
            assert field in test, f"Missing test field: {field}"

    def test_train_test_split_info(self):
        """train_test_split should show correct train/test candle counts"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        assert "train_test_split" in opt
        split = opt["train_test_split"]
        assert "train_candles" in split
        assert "test_candles" in split
        assert "train_ratio" in split
        assert "total_candles" in split
        
        # Verify split is approximately 70/30
        total = split["total_candles"]
        train = split["train_candles"]
        test = split["test_candles"]
        assert train + test == total
        assert abs(train / total - 0.70) < 0.01  # Within 1% of 70%

    def test_population_stats_structure(self):
        """population_stats should include required fields"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        assert "population_stats" in opt
        stats = opt["population_stats"]
        required_stats = ["mean_fitness", "profitable_on_train", "profitable_on_test", "avg_overfit_score"]
        for field in required_stats:
            assert field in stats, f"Missing population_stats field: {field}"

    def test_scoring_weights_returned(self):
        """scoring_weights should be returned with correct values"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        assert "scoring_weights" in opt
        weights = opt["scoring_weights"]
        assert weights.get("net_profit") == 0.25
        assert weights.get("sharpe_ratio") == 0.30
        assert weights.get("max_drawdown") == 0.25
        assert weights.get("trade_frequency") == 0.20

    def test_warnings_array_exists(self):
        """warnings array should exist in response"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        assert "warnings" in opt
        assert isinstance(opt["warnings"], list)

    def test_search_space_returned(self):
        """search_space should be returned with min/max/step for each parameter"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        assert "search_space" in opt
        space = opt["search_space"]
        assert len(space) > 0
        
        # Check structure of first parameter
        first_param = list(space.values())[0]
        assert "min" in first_param
        assert "max" in first_param
        assert "step" in first_param


class TestOldOptimizeEndpointBackwardCompatibility:
    """Tests for backward compatibility of /api/optimize-strategy endpoint"""

    def test_old_endpoint_still_works(self):
        """Old /api/optimize-strategy endpoint should still work"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-strategy",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "optimization" in data
        opt = data["optimization"]
        assert "best" in opt
        assert "top_5" in opt


class TestRandomSearchVariantOptions:
    """Tests for different variant and train ratio options"""

    def test_different_train_ratios(self):
        """Test with different train ratios (60%, 70%, 80%)"""
        for ratio in [0.60, 0.70, 0.80]:
            response = requests.post(
                f"{BASE_URL}/api/optimize-random",
                json={
                    "strategy_text": SAMPLE_STRATEGY,
                    "pair": "EURUSD",
                    "timeframe": "H1",
                    "num_variants": 20,
                    "train_ratio": ratio
                }
            )
            assert response.status_code == 200
            opt = response.json()["optimization"]
            actual_ratio = opt["train_test_split"]["train_ratio"]
            assert abs(actual_ratio - ratio) < 0.01, f"Expected ratio {ratio}, got {actual_ratio}"

    def test_variant_count_respected(self):
        """Test that num_variants is respected"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        assert opt["num_variants"] == 20


class TestFitnessBreakdown:
    """Tests for fitness breakdown structure"""

    def test_fitness_breakdown_components(self):
        """Fitness breakdown should have profit, sharpe, drawdown, frequency"""
        response = requests.post(
            f"{BASE_URL}/api/optimize-random",
            json={
                "strategy_text": SAMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "num_variants": 20,
                "train_ratio": 0.70
            }
        )
        assert response.status_code == 200
        opt = response.json()["optimization"]
        
        breakdown = opt["top_10"][0]["fitness_breakdown"]
        assert "profit" in breakdown
        assert "sharpe" in breakdown
        assert "drawdown" in breakdown
        assert "frequency" in breakdown


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
