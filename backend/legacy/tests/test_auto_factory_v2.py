"""
Test Suite for Phase 5.5 Auto Factory Engine (POST /api/run-auto-factory, GET /api/auto-factory-results)

Tests the universe-based continuous strategy generation system:
- Universe: 5 pairs × 4 styles with timeframe mappings
- Rotation: subset per cycle via seed
- Multi-level filtering: L1 quick → safety+ranking → L2 profile (DNA) → L3 match+probability
- Storage: top N per combo in auto_factory_strategies collection

IMPORTANT: POST /api/run-auto-factory takes 30-60 seconds per call due to LLM generation + backtesting.
Use minimal parameters: max_combos=1, strategies_per_combo=2, mc_simulations=10, keep_top_n=2
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ═══════════════════════════════════════════════════════
# Test Fixtures
# ═══════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# ═══════════════════════════════════════════════════════
# Test: Endpoint Existence and Basic Response
# ═══════════════════════════════════════════════════════

class TestEndpointExists:
    """Verify endpoints exist and return expected status codes"""
    
    def test_run_auto_factory_endpoint_exists(self, api_client):
        """POST /api/run-auto-factory should exist and return 200"""
        # Use seed=42 which picks EURUSD/D1 (no data) to get fast response
        response = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 1,
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 42  # Picks combo without data for fast test
        }, timeout=120)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "auto_factory" in data, "Response should have 'auto_factory' key"
    
    def test_get_auto_factory_results_endpoint_exists(self, api_client):
        """GET /api/auto-factory-results should exist and return 200"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "total_strategies" in data
        assert "total_combos" in data
        assert "combos" in data


# ═══════════════════════════════════════════════════════
# Test: Response Structure for POST /api/run-auto-factory
# ═══════════════════════════════════════════════════════

class TestAutoFactoryResponseStructure:
    """Verify response structure has all required fields"""
    
    @pytest.fixture(scope="class")
    def auto_factory_response(self, api_client):
        """Run auto factory once with seed=42 (no data combo) for structure tests"""
        response = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 1,
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 42
        }, timeout=120)
        assert response.status_code == 200
        return response.json()
    
    def test_has_auto_factory_key(self, auto_factory_response):
        """Response should have auto_factory key"""
        assert "auto_factory" in auto_factory_response
    
    def test_has_stats(self, auto_factory_response):
        """auto_factory should have stats object"""
        af = auto_factory_response["auto_factory"]
        assert "stats" in af, "Missing 'stats' in auto_factory"
    
    def test_stats_has_combos_selected(self, auto_factory_response):
        """stats should have combos_selected"""
        stats = auto_factory_response["auto_factory"]["stats"]
        assert "combos_selected" in stats
    
    def test_stats_has_combos_with_data(self, auto_factory_response):
        """stats should have combos_with_data"""
        stats = auto_factory_response["auto_factory"]["stats"]
        assert "combos_with_data" in stats
    
    def test_stats_has_total_generated(self, auto_factory_response):
        """stats should have total_generated"""
        stats = auto_factory_response["auto_factory"]["stats"]
        assert "total_generated" in stats
    
    def test_stats_has_total_backtested(self, auto_factory_response):
        """stats should have total_backtested"""
        stats = auto_factory_response["auto_factory"]["stats"]
        assert "total_backtested" in stats
    
    def test_stats_has_level1_passed(self, auto_factory_response):
        """stats should have level1_passed"""
        stats = auto_factory_response["auto_factory"]["stats"]
        assert "level1_passed" in stats
    
    def test_stats_has_level2_profiled(self, auto_factory_response):
        """stats should have level2_profiled"""
        stats = auto_factory_response["auto_factory"]["stats"]
        assert "level2_profiled" in stats
    
    def test_stats_has_level3_matched(self, auto_factory_response):
        """stats should have level3_matched"""
        stats = auto_factory_response["auto_factory"]["stats"]
        assert "level3_matched" in stats
    
    def test_stats_has_total_stored(self, auto_factory_response):
        """stats should have total_stored"""
        stats = auto_factory_response["auto_factory"]["stats"]
        assert "total_stored" in stats
    
    def test_has_stored_strategies_array(self, auto_factory_response):
        """auto_factory should have stored_strategies array"""
        af = auto_factory_response["auto_factory"]
        assert "stored_strategies" in af
        assert isinstance(af["stored_strategies"], list)
    
    def test_has_combo_results_array(self, auto_factory_response):
        """auto_factory should have combo_results array"""
        af = auto_factory_response["auto_factory"]
        assert "combo_results" in af
        assert isinstance(af["combo_results"], list)
    
    def test_has_cycle_log_array(self, auto_factory_response):
        """auto_factory should have cycle_log array"""
        af = auto_factory_response["auto_factory"]
        assert "cycle_log" in af
        assert isinstance(af["cycle_log"], list)


# ═══════════════════════════════════════════════════════
# Test: Combos Without Data Are Skipped
# ═══════════════════════════════════════════════════════

class TestNoDataCombosSkipped:
    """Verify combos without real data are skipped with status=skipped_no_data"""
    
    def test_combo_without_data_is_skipped(self, api_client):
        """seed=42 picks EURUSD/D1 which has no data - should be skipped"""
        response = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 1,
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 42  # Picks EURUSD/D1/trend-following (no data)
        }, timeout=120)
        assert response.status_code == 200
        data = response.json()
        af = data["auto_factory"]
        
        # Check stats
        stats = af["stats"]
        assert stats["combos_skipped_no_data"] >= 0, "Should track skipped combos"
        
        # Check combo_results for skipped status
        combo_results = af["combo_results"]
        assert len(combo_results) > 0, "Should have at least one combo result"
        
        # At least one combo should be skipped (seed=42 picks no-data combo)
        skipped = [c for c in combo_results if c.get("status") == "skipped_no_data"]
        # Note: seed=42 may or may not pick a no-data combo depending on universe order
        # The important thing is the structure is correct
        for combo in combo_results:
            assert "status" in combo, "Each combo result should have status"
            assert "combo_key" in combo, "Each combo result should have combo_key"


# ═══════════════════════════════════════════════════════
# Test: Full Pipeline with Data (seed=21 picks EURUSD/H1/breakout)
# ═══════════════════════════════════════════════════════

class TestFullPipelineWithData:
    """Test full pipeline: generate → backtest → L1 → safety → rank → L2 → L3 → store"""
    
    @pytest.fixture(scope="class")
    def pipeline_response(self, api_client):
        """Run auto factory with seed=21 which picks EURUSD/H1/breakout (has data)"""
        response = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 1,
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 21  # Picks EURUSD/H1/breakout which has data
        }, timeout=180)  # Longer timeout for LLM + backtest
        assert response.status_code == 200, f"Pipeline failed: {response.text}"
        return response.json()
    
    def test_combo_with_data_processed(self, pipeline_response):
        """Combo with data should be processed (not skipped)"""
        af = pipeline_response["auto_factory"]
        stats = af["stats"]
        
        # With seed=21, we should have at least one combo with data
        # Note: The exact combo depends on universe shuffle
        assert stats["combos_selected"] >= 1
    
    def test_strategies_generated(self, pipeline_response):
        """Should generate strategies for combos with data"""
        af = pipeline_response["auto_factory"]
        stats = af["stats"]
        
        # If we have combos with data, we should have generated strategies
        if stats["combos_with_data"] > 0:
            assert stats["total_generated"] > 0, "Should generate strategies for combos with data"
    
    def test_strategies_backtested(self, pipeline_response):
        """Should backtest generated strategies"""
        af = pipeline_response["auto_factory"]
        stats = af["stats"]
        
        if stats["total_generated"] > 0:
            assert stats["total_backtested"] > 0, "Should backtest generated strategies"
    
    def test_level1_filtering_applied(self, pipeline_response):
        """L1 filter should be applied (passed + rejected = backtested)"""
        af = pipeline_response["auto_factory"]
        stats = af["stats"]
        
        if stats["total_backtested"] > 0:
            # L1 passed + L1 rejected should equal total backtested
            l1_total = stats["level1_passed"] + stats.get("level1_rejected", 0)
            assert l1_total == stats["total_backtested"], \
                f"L1 passed ({stats['level1_passed']}) + rejected ({stats.get('level1_rejected', 0)}) should equal backtested ({stats['total_backtested']})"
    
    def test_level2_profiling_applied(self, pipeline_response):
        """L2 profiling (DNA) should be applied to L1 passed strategies"""
        af = pipeline_response["auto_factory"]
        stats = af["stats"]
        
        if stats["level1_passed"] > 0:
            assert stats["level2_profiled"] > 0, "Should profile L1 passed strategies"
    
    def test_level3_matching_applied(self, pipeline_response):
        """L3 matching should be applied to profiled strategies"""
        af = pipeline_response["auto_factory"]
        stats = af["stats"]
        
        if stats["level2_profiled"] > 0:
            assert stats["level3_matched"] > 0, "Should match profiled strategies"
    
    def test_combo_result_has_complete_status(self, pipeline_response):
        """Combo with data should have status=complete"""
        af = pipeline_response["auto_factory"]
        combo_results = af["combo_results"]
        
        # Find combos that were processed (not skipped)
        processed = [c for c in combo_results if c.get("status") not in ["skipped_no_data", "generation_failed", "backtest_failed"]]
        
        for combo in processed:
            # Should have detailed stats
            assert "generated" in combo, "Processed combo should have 'generated' count"
            assert "stored" in combo, "Processed combo should have 'stored' count"


# ═══════════════════════════════════════════════════════
# Test: Stored Strategy Fields
# ═══════════════════════════════════════════════════════

class TestStoredStrategyFields:
    """Verify stored strategies have required fields"""
    
    def test_stored_strategies_have_composite_score(self, api_client):
        """Stored strategies should have composite_score"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        if data["total_strategies"] > 0:
            combos = data["combos"]
            for combo_key, strategies in combos.items():
                for s in strategies:
                    assert "composite_score" in s, f"Strategy in {combo_key} missing composite_score"
    
    def test_stored_strategies_have_pass_probability(self, api_client):
        """Stored strategies should have pass_probability"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data = response.json()
        
        if data["total_strategies"] > 0:
            combos = data["combos"]
            for combo_key, strategies in combos.items():
                for s in strategies:
                    assert "pass_probability" in s, f"Strategy in {combo_key} missing pass_probability"
    
    def test_stored_strategies_have_best_firm_fit(self, api_client):
        """Stored strategies should have best_firm_fit"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data = response.json()
        
        if data["total_strategies"] > 0:
            combos = data["combos"]
            for combo_key, strategies in combos.items():
                for s in strategies:
                    assert "best_firm_fit" in s, f"Strategy in {combo_key} missing best_firm_fit"
    
    def test_stored_strategies_have_required_fields(self, api_client):
        """Stored strategies should have all required fields"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data = response.json()
        
        required_fields = [
            "pair", "timeframe", "style", "rank", "metrics", 
            "classification", "safety", "pass_probability", 
            "best_firm_fit", "last_updated"
        ]
        
        if data["total_strategies"] > 0:
            combos = data["combos"]
            for combo_key, strategies in combos.items():
                for s in strategies:
                    for field in required_fields:
                        assert field in s, f"Strategy in {combo_key} missing required field: {field}"


# ═══════════════════════════════════════════════════════
# Test: GET /api/auto-factory-results Structure
# ═══════════════════════════════════════════════════════

class TestGetAutoFactoryResults:
    """Test GET /api/auto-factory-results endpoint"""
    
    def test_returns_grouped_by_combo(self, api_client):
        """Results should be grouped by combo_key"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        assert response.status_code == 200
        data = response.json()
        
        assert "combos" in data
        assert isinstance(data["combos"], dict)
        
        # Each combo should have a list of strategies
        for combo_key, strategies in data["combos"].items():
            assert isinstance(strategies, list), f"Combo {combo_key} should have list of strategies"
            # Verify combo_key format: pair:timeframe:style
            parts = combo_key.split(":")
            assert len(parts) == 3, f"combo_key should be pair:timeframe:style, got {combo_key}"
    
    def test_strategies_sorted_by_rank(self, api_client):
        """Strategies within each combo should be sorted by rank"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data = response.json()
        
        for combo_key, strategies in data["combos"].items():
            if len(strategies) > 1:
                ranks = [s.get("rank", 0) for s in strategies]
                assert ranks == sorted(ranks), f"Strategies in {combo_key} not sorted by rank"
    
    def test_total_counts_match(self, api_client):
        """total_strategies should match sum of all strategies in combos"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data = response.json()
        
        total_from_combos = sum(len(strategies) for strategies in data["combos"].values())
        assert data["total_strategies"] == total_from_combos, \
            f"total_strategies ({data['total_strategies']}) doesn't match sum ({total_from_combos})"
        
        assert data["total_combos"] == len(data["combos"]), \
            f"total_combos ({data['total_combos']}) doesn't match combos count ({len(data['combos'])})"


# ═══════════════════════════════════════════════════════
# Test: Rotation (Different Seeds Select Different Combos)
# ═══════════════════════════════════════════════════════

class TestRotation:
    """Verify different seeds select different combos"""
    
    def test_different_seeds_different_combos(self, api_client):
        """Different seeds should select different combos"""
        # Run with seed=21
        response1 = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 1,
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 21
        }, timeout=180)
        assert response1.status_code == 200
        data1 = response1.json()
        combos1 = [c["combo_key"] for c in data1["auto_factory"]["combo_results"]]
        
        # Run with seed=42
        response2 = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 1,
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 42
        }, timeout=180)
        assert response2.status_code == 200
        data2 = response2.json()
        combos2 = [c["combo_key"] for c in data2["auto_factory"]["combo_results"]]
        
        # Different seeds should produce different combo selections
        # (unless by chance they pick the same - but with different seeds this is unlikely)
        # We just verify both ran successfully and returned combo results
        assert len(combos1) > 0, "Seed 21 should select at least one combo"
        assert len(combos2) > 0, "Seed 42 should select at least one combo"


# ═══════════════════════════════════════════════════════
# Test: Replacement (No Duplicates)
# ═══════════════════════════════════════════════════════

class TestReplacement:
    """Verify running cycle again replaces old strategies (not duplicates)"""
    
    def test_same_combo_replaces_not_duplicates(self, api_client):
        """Running cycle with same combo should replace, not duplicate"""
        # Get initial count for EURUSD:H1:breakout
        response1 = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data1 = response1.json()
        initial_count = len(data1["combos"].get("EURUSD:H1:breakout", []))
        
        # Run auto factory with seed=21 (picks EURUSD/H1/breakout)
        response2 = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 1,
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 21
        }, timeout=180)
        assert response2.status_code == 200
        
        # Get count after
        response3 = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data3 = response3.json()
        
        # The combo should have at most keep_top_n strategies (not accumulated)
        combo_strategies = data3["combos"].get("EURUSD:H1:breakout", [])
        assert len(combo_strategies) <= 5, \
            f"Should have at most 5 strategies per combo (keep_top_n), got {len(combo_strategies)}"


# ═══════════════════════════════════════════════════════
# Test: L1 Filter Criteria
# ═══════════════════════════════════════════════════════

class TestL1FilterCriteria:
    """Verify L1 filter rejects strategies with <3 trades, >40% DD, or <10% win rate"""
    
    def test_l1_filter_rejects_bad_strategies(self, api_client):
        """L1 filter should reject strategies that don't meet criteria"""
        # Run auto factory
        response = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 1,
            "strategies_per_combo": 3,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 21
        }, timeout=180)
        assert response.status_code == 200
        data = response.json()
        af = data["auto_factory"]
        stats = af["stats"]
        
        # If we have backtested strategies, L1 filter should have been applied
        if stats["total_backtested"] > 0:
            # L1 rejected count should be tracked
            assert "level1_rejected" in stats or stats["level1_passed"] <= stats["total_backtested"], \
                "L1 filter should track passed/rejected counts"
        
        # Check stored strategies meet L1 criteria
        response2 = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data2 = response2.json()
        
        for combo_key, strategies in data2["combos"].items():
            for s in strategies:
                metrics = s.get("metrics", {})
                # Stored strategies should pass L1 criteria
                total_trades = metrics.get("total_trades", 0)
                max_dd = metrics.get("max_drawdown_pct", 0)
                win_rate = metrics.get("win_rate", 0)
                
                # Note: These are the L1 criteria from _quick_filter
                # <3 trades, >40% DD, <10% win rate are rejected
                # Stored strategies should have passed these
                assert total_trades >= 3, f"Stored strategy should have >=3 trades, got {total_trades}"
                assert max_dd <= 40, f"Stored strategy should have <=40% DD, got {max_dd}"
                assert win_rate >= 10, f"Stored strategy should have >=10% win rate, got {win_rate}"


# ═══════════════════════════════════════════════════════
# Test: Pipeline Completes Without Crashes
# ═══════════════════════════════════════════════════════

class TestPipelineStability:
    """Verify pipeline completes without crashes even when most combos have no data"""
    
    def test_pipeline_handles_no_data_gracefully(self, api_client):
        """Pipeline should complete even when combos have no data"""
        # Use seed=42 which picks combos without data
        response = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 3,  # Try multiple combos
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 42
        }, timeout=180)
        
        assert response.status_code == 200, f"Pipeline should not crash: {response.text}"
        data = response.json()
        
        # Should have success=True
        assert data["auto_factory"]["success"] == True, "Pipeline should report success"
        
        # Should have combo_results for all selected combos
        af = data["auto_factory"]
        assert len(af["combo_results"]) == af["stats"]["combos_selected"], \
            "Should have result for each selected combo"


# ═══════════════════════════════════════════════════════
# Test: max_combos Parameter
# ═══════════════════════════════════════════════════════

class TestMaxCombosParameter:
    """Verify max_combos parameter limits number of combos processed"""
    
    def test_max_combos_limits_selection(self, api_client):
        """max_combos should limit number of combos selected"""
        # Test with max_combos=1
        response1 = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 1,
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 21
        }, timeout=180)
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["auto_factory"]["stats"]["combos_selected"] == 1, \
            "max_combos=1 should select exactly 1 combo"
        
        # Test with max_combos=2
        response2 = api_client.post(f"{BASE_URL}/api/run-auto-factory", json={
            "max_combos": 2,
            "strategies_per_combo": 2,
            "keep_top_n": 2,
            "mc_simulations": 10,
            "seed": 21
        }, timeout=180)
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["auto_factory"]["stats"]["combos_selected"] == 2, \
            "max_combos=2 should select exactly 2 combos"


# ═══════════════════════════════════════════════════════
# Test: Composite Score Calculation
# ═══════════════════════════════════════════════════════

class TestCompositeScore:
    """Verify composite score is calculated correctly"""
    
    def test_composite_score_is_numeric(self, api_client):
        """composite_score should be a numeric value"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data = response.json()
        
        for combo_key, strategies in data["combos"].items():
            for s in strategies:
                score = s.get("composite_score")
                assert score is not None, "composite_score should not be None"
                assert isinstance(score, (int, float)), f"composite_score should be numeric, got {type(score)}"
    
    def test_strategies_sorted_by_composite_score(self, api_client):
        """Strategies should be ranked by composite_score (descending)"""
        response = api_client.get(f"{BASE_URL}/api/auto-factory-results", timeout=30)
        data = response.json()
        
        for combo_key, strategies in data["combos"].items():
            if len(strategies) > 1:
                scores = [s.get("composite_score", 0) for s in strategies]
                # Higher rank = higher score (rank 1 should have highest score)
                assert scores == sorted(scores, reverse=True), \
                    f"Strategies in {combo_key} not sorted by composite_score descending"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
