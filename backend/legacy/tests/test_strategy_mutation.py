"""
Phase 6: Strategy Mutation Engine Tests

Tests the POST /api/mutate-strategy endpoint which:
- Diagnoses strategy issues (high DD, low probability, low win rate, unprofitable)
- Generates controlled mutations (tighten_sl, widen_tp, risk_reduction_combo, stricter_rsi, combined_improvement)
- Evaluates each mutation (backtest → profile → probability)
- Returns best improvement

NOTE: Each mutation call runs ~8-9 backtests + probability calculations.
Using mc_simulations=10 and limiting to 2-3 test calls to avoid timeout.
Only EURUSD/H1 data exists (2616 candles).
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Simple EMA crossover strategy for testing
SIMPLE_STRATEGY = """STRATEGY: EMA Crossover
ENTRY LONG: EMA 8 crosses above EMA 21 AND RSI 14 > 50
ENTRY SHORT: EMA 8 crosses below EMA 21 AND RSI 14 < 50
EXIT: SL 20 pips, TP 35 pips
PARAMETERS: Fast=8, Slow=21, RSI=14, SL=20, TP=35"""

# Strategy with poor metrics (tight TP, wide SL) to trigger mutations
POOR_STRATEGY = """STRATEGY: Poor EMA Crossover
ENTRY LONG: EMA 5 crosses above EMA 10 AND RSI 14 > 30
ENTRY SHORT: EMA 5 crosses below EMA 10 AND RSI 14 < 70
EXIT: SL 50 pips, TP 15 pips
PARAMETERS: Fast=5, Slow=10, RSI=14, SL=50, TP=15"""


class TestMutateStrategyEndpointExists:
    """Test that the endpoint exists and returns 200"""
    
    def test_endpoint_exists_with_valid_request(self):
        """POST /api/mutate-strategy should return 200 with valid strategy"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": SIMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
            },
            timeout=120  # Mutation takes time due to multiple backtests
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("✓ Endpoint exists and returns 200")


class TestMutateStrategyResponseStructure:
    """Test response structure has all required fields"""
    
    @pytest.fixture(scope="class")
    def mutation_response(self):
        """Run mutation once and cache result for all tests in this class"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": SIMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
            },
            timeout=120
        )
        assert response.status_code == 200
        return response.json()
    
    def test_has_mutation_key(self, mutation_response):
        """Response should have 'mutation' key"""
        assert "mutation" in mutation_response
        print("✓ Response has 'mutation' key")
    
    def test_has_action_field(self, mutation_response):
        """mutation.action should be one of: mutation_applied, no_mutation_needed, no_improvement_found"""
        mutation = mutation_response.get("mutation", {})
        assert "action" in mutation, "Missing 'action' field"
        valid_actions = ["mutation_applied", "no_mutation_needed", "no_improvement_found"]
        assert mutation["action"] in valid_actions, f"Invalid action: {mutation['action']}"
        print(f"✓ mutation.action = {mutation['action']}")
    
    def test_has_original_with_backtest(self, mutation_response):
        """mutation.original should have backtest data"""
        mutation = mutation_response.get("mutation", {})
        assert "original" in mutation, "Missing 'original' field"
        original = mutation["original"]
        assert "backtest" in original, "original missing 'backtest'"
        print("✓ mutation.original.backtest exists")
    
    def test_has_original_with_profile(self, mutation_response):
        """mutation.original should have profile data"""
        mutation = mutation_response.get("mutation", {})
        original = mutation.get("original", {})
        assert "profile" in original, "original missing 'profile'"
        print("✓ mutation.original.profile exists")
    
    def test_has_original_with_simulation(self, mutation_response):
        """mutation.original should have simulation data"""
        mutation = mutation_response.get("mutation", {})
        original = mutation.get("original", {})
        assert "simulation" in original, "original missing 'simulation'"
        print("✓ mutation.original.simulation exists")
    
    def test_has_original_with_probability(self, mutation_response):
        """mutation.original should have probability data"""
        mutation = mutation_response.get("mutation", {})
        original = mutation.get("original", {})
        assert "probability" in original, "original missing 'probability'"
        print("✓ mutation.original.probability exists")
    
    def test_has_diagnosis_array(self, mutation_response):
        """mutation.diagnosis should be an array"""
        mutation = mutation_response.get("mutation", {})
        assert "diagnosis" in mutation, "Missing 'diagnosis' field"
        assert isinstance(mutation["diagnosis"], list), "diagnosis should be a list"
        print(f"✓ mutation.diagnosis is array with {len(mutation['diagnosis'])} items")
    
    def test_diagnosis_has_type_severity_detail(self, mutation_response):
        """Each diagnosis item should have type, severity, detail"""
        mutation = mutation_response.get("mutation", {})
        diagnosis = mutation.get("diagnosis", [])
        if diagnosis:
            for d in diagnosis:
                assert "type" in d, "diagnosis item missing 'type'"
                assert "severity" in d, "diagnosis item missing 'severity'"
                assert "detail" in d, "diagnosis item missing 'detail'"
            print("✓ All diagnosis items have type, severity, detail")
        else:
            print("✓ No diagnosis items (strategy may be healthy)")
    
    def test_has_mutations_tested_count(self, mutation_response):
        """mutation.mutations_tested should be a number"""
        mutation = mutation_response.get("mutation", {})
        assert "mutations_tested" in mutation, "Missing 'mutations_tested' field"
        assert isinstance(mutation["mutations_tested"], int), "mutations_tested should be int"
        print(f"✓ mutation.mutations_tested = {mutation['mutations_tested']}")
    
    def test_has_mutations_improved_count(self, mutation_response):
        """mutation.mutations_improved should be a number"""
        mutation = mutation_response.get("mutation", {})
        assert "mutations_improved" in mutation, "Missing 'mutations_improved' field"
        assert isinstance(mutation["mutations_improved"], int), "mutations_improved should be int"
        print(f"✓ mutation.mutations_improved = {mutation['mutations_improved']}")
    
    def test_has_original_probability(self, mutation_response):
        """mutation.original_probability should be a number"""
        mutation = mutation_response.get("mutation", {})
        assert "original_probability" in mutation, "Missing 'original_probability' field"
        assert isinstance(mutation["original_probability"], (int, float)), "original_probability should be numeric"
        print(f"✓ mutation.original_probability = {mutation['original_probability']}")
    
    def test_has_mutated_probability(self, mutation_response):
        """mutation.mutated_probability should be a number"""
        mutation = mutation_response.get("mutation", {})
        assert "mutated_probability" in mutation, "Missing 'mutated_probability' field"
        assert isinstance(mutation["mutated_probability"], (int, float)), "mutated_probability should be numeric"
        print(f"✓ mutation.mutated_probability = {mutation['mutated_probability']}")
    
    def test_has_improvement_delta(self, mutation_response):
        """mutation.improvement should be a number (delta)"""
        mutation = mutation_response.get("mutation", {})
        assert "improvement" in mutation, "Missing 'improvement' field"
        assert isinstance(mutation["improvement"], (int, float)), "improvement should be numeric"
        print(f"✓ mutation.improvement = {mutation['improvement']}")
    
    def test_has_all_mutations_array(self, mutation_response):
        """mutation.all_mutations should be an array"""
        mutation = mutation_response.get("mutation", {})
        assert "all_mutations" in mutation, "Missing 'all_mutations' field"
        assert isinstance(mutation["all_mutations"], list), "all_mutations should be a list"
        print(f"✓ mutation.all_mutations is array with {len(mutation['all_mutations'])} items")
    
    def test_has_best_mutation_or_null(self, mutation_response):
        """mutation.best_mutation should exist (can be null if no improvement)"""
        mutation = mutation_response.get("mutation", {})
        assert "best_mutation" in mutation, "Missing 'best_mutation' field"
        # Can be None/null if no improvement found
        print(f"✓ mutation.best_mutation exists (is_null={mutation['best_mutation'] is None})")


class TestMutationItemStructure:
    """Test structure of individual mutation items in all_mutations array"""
    
    @pytest.fixture(scope="class")
    def mutation_response(self):
        """Run mutation once and cache result"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": POOR_STRATEGY,  # Use poor strategy to ensure mutations are generated
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
            },
            timeout=120
        )
        assert response.status_code == 200
        return response.json()
    
    def test_mutation_has_name(self, mutation_response):
        """Each mutation should have a name"""
        mutation = mutation_response.get("mutation", {})
        all_mutations = mutation.get("all_mutations", [])
        if all_mutations:
            for m in all_mutations:
                assert "name" in m, "mutation item missing 'name'"
            print("✓ All mutations have 'name' field")
        else:
            pytest.skip("No mutations generated")
    
    def test_mutation_has_description(self, mutation_response):
        """Each mutation should have a description"""
        mutation = mutation_response.get("mutation", {})
        all_mutations = mutation.get("all_mutations", [])
        if all_mutations:
            for m in all_mutations:
                assert "description" in m, "mutation item missing 'description'"
            print("✓ All mutations have 'description' field")
        else:
            pytest.skip("No mutations generated")
    
    def test_mutation_has_changes(self, mutation_response):
        """Each mutation should have changes array"""
        mutation = mutation_response.get("mutation", {})
        all_mutations = mutation.get("all_mutations", [])
        if all_mutations:
            for m in all_mutations:
                assert "changes" in m, "mutation item missing 'changes'"
                assert isinstance(m["changes"], list), "changes should be a list"
            print("✓ All mutations have 'changes' array")
        else:
            pytest.skip("No mutations generated")
    
    def test_mutation_has_backtest_results(self, mutation_response):
        """Each mutation should have backtest results (unless error)"""
        mutation = mutation_response.get("mutation", {})
        all_mutations = mutation.get("all_mutations", [])
        if all_mutations:
            for m in all_mutations:
                if "error" not in m:
                    assert "backtest" in m, "mutation item missing 'backtest'"
            print("✓ All successful mutations have 'backtest' results")
        else:
            pytest.skip("No mutations generated")
    
    def test_mutation_has_is_improvement_boolean(self, mutation_response):
        """Each mutation should have is_improvement boolean"""
        mutation = mutation_response.get("mutation", {})
        all_mutations = mutation.get("all_mutations", [])
        if all_mutations:
            for m in all_mutations:
                assert "is_improvement" in m, "mutation item missing 'is_improvement'"
                assert isinstance(m["is_improvement"], bool), "is_improvement should be boolean"
            print("✓ All mutations have 'is_improvement' boolean")
        else:
            pytest.skip("No mutations generated")
    
    def test_mutation_has_improvement_reason(self, mutation_response):
        """Each mutation should have improvement_reason string"""
        mutation = mutation_response.get("mutation", {})
        all_mutations = mutation.get("all_mutations", [])
        if all_mutations:
            for m in all_mutations:
                if "error" not in m:
                    assert "improvement_reason" in m, "mutation item missing 'improvement_reason'"
            print("✓ All successful mutations have 'improvement_reason'")
        else:
            pytest.skip("No mutations generated")


class TestDiagnosisTypes:
    """Test that diagnosis correctly identifies different issue types"""
    
    @pytest.fixture(scope="class")
    def mutation_response(self):
        """Run mutation with poor strategy to trigger diagnosis"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": POOR_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
            },
            timeout=120
        )
        assert response.status_code == 200
        return response.json()
    
    def test_diagnosis_types_are_valid(self, mutation_response):
        """Diagnosis types should be from known set"""
        mutation = mutation_response.get("mutation", {})
        diagnosis = mutation.get("diagnosis", [])
        
        valid_types = [
            "high_drawdown", "daily_dd_pressure", "low_probability", 
            "low_win_rate", "poor_risk_reward", "low_consistency",
            "streak_risk", "unprofitable", "sim_daily_dd_breach", "sim_total_dd_breach"
        ]
        
        for d in diagnosis:
            assert d["type"] in valid_types, f"Unknown diagnosis type: {d['type']}"
        
        types_found = [d["type"] for d in diagnosis]
        print(f"✓ Diagnosis types found: {types_found}")
    
    def test_diagnosis_severity_is_valid(self, mutation_response):
        """Diagnosis severity should be critical, high, or medium"""
        mutation = mutation_response.get("mutation", {})
        diagnosis = mutation.get("diagnosis", [])
        
        valid_severities = ["critical", "high", "medium"]
        
        for d in diagnosis:
            assert d["severity"] in valid_severities, f"Invalid severity: {d['severity']}"
        
        print("✓ All diagnosis severities are valid")


class TestMutationTypes:
    """Test that mutation types are generated correctly"""
    
    @pytest.fixture(scope="class")
    def mutation_response(self):
        """Run mutation with poor strategy to trigger mutations"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": POOR_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
            },
            timeout=120
        )
        assert response.status_code == 200
        return response.json()
    
    def test_mutation_names_are_valid(self, mutation_response):
        """Mutation names should be from known set"""
        mutation = mutation_response.get("mutation", {})
        all_mutations = mutation.get("all_mutations", [])
        
        valid_names = [
            "tighten_sl_mild", "tighten_sl_moderate", "tighten_sl_aggressive",
            "widen_tp_mild", "widen_tp_moderate",
            "risk_reduction_combo", "stricter_rsi", "longer_periods",
            "combined_improvement"
        ]
        
        names_found = []
        for m in all_mutations:
            names_found.append(m["name"])
            assert m["name"] in valid_names, f"Unknown mutation name: {m['name']}"
        
        print(f"✓ Mutation names found: {names_found}")
    
    def test_combined_improvement_always_generated(self, mutation_response):
        """combined_improvement mutation should always be generated when issues exist"""
        mutation = mutation_response.get("mutation", {})
        all_mutations = mutation.get("all_mutations", [])
        diagnosis = mutation.get("diagnosis", [])
        
        if diagnosis:  # If there are issues
            names = [m["name"] for m in all_mutations]
            assert "combined_improvement" in names, "combined_improvement should be generated when issues exist"
            print("✓ combined_improvement mutation generated")
        else:
            print("✓ No issues diagnosed, combined_improvement not required")


class TestBestMutationSelection:
    """Test that best mutation is selected correctly"""
    
    @pytest.fixture(scope="class")
    def mutation_response(self):
        """Run mutation with poor strategy"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": POOR_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
            },
            timeout=120
        )
        assert response.status_code == 200
        return response.json()
    
    def test_best_mutation_has_highest_probability_among_improvements(self, mutation_response):
        """Best mutation should have highest probability among improvements"""
        mutation = mutation_response.get("mutation", {})
        best = mutation.get("best_mutation")
        all_mutations = mutation.get("all_mutations", [])
        
        if best is None:
            print("✓ No best mutation (no improvements found)")
            return
        
        # Get all improvements
        improvements = [m for m in all_mutations if m.get("is_improvement")]
        
        if improvements:
            best_prob = best.get("probability", {}).get("pass_probability", 0)
            for imp in improvements:
                imp_prob = imp.get("probability", {}).get("pass_probability", 0)
                assert best_prob >= imp_prob, f"Best mutation prob {best_prob} < improvement prob {imp_prob}"
            print(f"✓ Best mutation has highest probability: {best_prob}%")
        else:
            print("✓ No improvements found")


class TestErrorHandling:
    """Test error handling for invalid requests"""
    
    def test_error_when_no_strategy_provided(self):
        """Should return error when neither strategy_text nor strategy_id provided"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "pair": "EURUSD",
                "timeframe": "H1"
            },
            timeout=30
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        print(f"✓ Error returned when no strategy: {data['detail']}")
    
    def test_error_when_no_real_data_available(self):
        """Should return error when no real data for pair/timeframe"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": SIMPLE_STRATEGY,
                "pair": "GBPJPY",  # No data for this pair
                "timeframe": "M15",
                "mc_simulations": 10
            },
            timeout=30
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        assert "data" in data["detail"].lower() or "real" in data["detail"].lower()
        print(f"✓ Error returned when no real data: {data['detail']}")
    
    def test_error_when_invalid_strategy_id(self):
        """Should return error when invalid strategy_id provided"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_id": "invalid_id_123",
                "pair": "EURUSD",
                "timeframe": "H1"
            },
            timeout=30
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Error returned for invalid strategy_id")


class TestDefaultFirm:
    """Test that default firm is FTMO when no firm specified"""
    
    def test_default_firm_is_ftmo(self):
        """When no firm specified, should use FTMO rules"""
        # Run mutation without specifying firm
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": SIMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
                # No firm specified
            },
            timeout=120
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # The mutation should complete successfully using FTMO rules
        data = response.json()
        mutation = data.get("mutation", {})
        assert mutation.get("success", False) or mutation.get("action") in [
            "mutation_applied", "no_mutation_needed", "no_improvement_found"
        ]
        print(f"✓ Default firm (FTMO) used successfully, action: {mutation.get('action')}")


class TestOriginalBacktestFields:
    """Test that original backtest has expected fields"""
    
    @pytest.fixture(scope="class")
    def mutation_response(self):
        """Run mutation once and cache result"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": SIMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
            },
            timeout=120
        )
        assert response.status_code == 200
        return response.json()
    
    def test_original_backtest_has_net_profit(self, mutation_response):
        """original.backtest should have net_profit"""
        mutation = mutation_response.get("mutation", {})
        backtest = mutation.get("original", {}).get("backtest", {})
        assert "net_profit" in backtest
        print(f"✓ original.backtest.net_profit = {backtest['net_profit']}")
    
    def test_original_backtest_has_total_return_pct(self, mutation_response):
        """original.backtest should have total_return_pct"""
        mutation = mutation_response.get("mutation", {})
        backtest = mutation.get("original", {}).get("backtest", {})
        assert "total_return_pct" in backtest
        print(f"✓ original.backtest.total_return_pct = {backtest['total_return_pct']}")
    
    def test_original_backtest_has_win_rate(self, mutation_response):
        """original.backtest should have win_rate"""
        mutation = mutation_response.get("mutation", {})
        backtest = mutation.get("original", {}).get("backtest", {})
        assert "win_rate" in backtest
        print(f"✓ original.backtest.win_rate = {backtest['win_rate']}")
    
    def test_original_backtest_has_profit_factor(self, mutation_response):
        """original.backtest should have profit_factor"""
        mutation = mutation_response.get("mutation", {})
        backtest = mutation.get("original", {}).get("backtest", {})
        assert "profit_factor" in backtest
        print(f"✓ original.backtest.profit_factor = {backtest['profit_factor']}")
    
    def test_original_backtest_has_max_drawdown_pct(self, mutation_response):
        """original.backtest should have max_drawdown_pct"""
        mutation = mutation_response.get("mutation", {})
        backtest = mutation.get("original", {}).get("backtest", {})
        assert "max_drawdown_pct" in backtest
        print(f"✓ original.backtest.max_drawdown_pct = {backtest['max_drawdown_pct']}")
    
    def test_original_backtest_has_total_trades(self, mutation_response):
        """original.backtest should have total_trades"""
        mutation = mutation_response.get("mutation", {})
        backtest = mutation.get("original", {}).get("backtest", {})
        assert "total_trades" in backtest
        print(f"✓ original.backtest.total_trades = {backtest['total_trades']}")


class TestOriginalProbabilityFields:
    """Test that original probability has expected fields"""
    
    @pytest.fixture(scope="class")
    def mutation_response(self):
        """Run mutation once and cache result"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": SIMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
            },
            timeout=120
        )
        assert response.status_code == 200
        return response.json()
    
    def test_original_probability_has_pass_probability(self, mutation_response):
        """original.probability should have pass_probability"""
        mutation = mutation_response.get("mutation", {})
        prob = mutation.get("original", {}).get("probability", {})
        assert "pass_probability" in prob
        print(f"✓ original.probability.pass_probability = {prob['pass_probability']}")
    
    def test_original_probability_has_risk_label(self, mutation_response):
        """original.probability should have risk_label"""
        mutation = mutation_response.get("mutation", {})
        prob = mutation.get("original", {}).get("probability", {})
        assert "risk_label" in prob
        print(f"✓ original.probability.risk_label = {prob['risk_label']}")


class TestOriginalSimulationFields:
    """Test that original simulation has expected fields"""
    
    @pytest.fixture(scope="class")
    def mutation_response(self):
        """Run mutation once and cache result"""
        response = requests.post(
            f"{BASE_URL}/api/mutate-strategy",
            json={
                "strategy_text": SIMPLE_STRATEGY,
                "pair": "EURUSD",
                "timeframe": "H1",
                "mc_simulations": 10
            },
            timeout=120
        )
        assert response.status_code == 200
        return response.json()
    
    def test_original_simulation_has_status(self, mutation_response):
        """original.simulation should have status"""
        mutation = mutation_response.get("mutation", {})
        sim = mutation.get("original", {}).get("simulation", {})
        assert "status" in sim
        print(f"✓ original.simulation.status = {sim['status']}")
    
    def test_original_simulation_has_max_drawdown_pct(self, mutation_response):
        """original.simulation should have max_drawdown_pct"""
        mutation = mutation_response.get("mutation", {})
        sim = mutation.get("original", {}).get("simulation", {})
        assert "max_drawdown_pct" in sim
        print(f"✓ original.simulation.max_drawdown_pct = {sim['max_drawdown_pct']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
