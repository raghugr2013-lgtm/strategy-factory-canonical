"""
Backend API Tests for AI Strategy Factory
Tests all major endpoints: health, strategies, backtest, optimization, safety, monte carlo, 
market data, live tracking, portfolio, and rebalance config.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestHealthEndpoint:
    """Health check endpoint tests"""
    
    def test_health_returns_ok(self):
        """Test /api/health returns status ok"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "service" in data
        print(f"Health check passed: {data}")


class TestStrategyGeneration:
    """Strategy generation endpoint tests"""
    
    def test_generate_strategy_basic(self):
        """Test /api/generate-strategy with default params"""
        response = requests.post(f"{BASE_URL}/api/generate-strategy", json={
            "pair": "EURUSD",
            "timeframe": "H1",
            "style": "trend-following"
        }, timeout=60)  # LLM calls can take time
        assert response.status_code == 200
        data = response.json()
        assert "strategy" in data
        assert isinstance(data["strategy"], str)
        assert len(data["strategy"]) > 50  # Should have meaningful content
        print(f"Strategy generated: {len(data['strategy'])} chars")
        return data["strategy"]
    
    def test_generate_strategy_different_styles(self):
        """Test strategy generation with different styles"""
        styles = ["mean-reversion", "breakout"]
        for style in styles:
            response = requests.post(f"{BASE_URL}/api/generate-strategy", json={
                "pair": "BTCUSD",
                "timeframe": "H4",
                "style": style
            }, timeout=60)
            assert response.status_code == 200
            data = response.json()
            assert "strategy" in data
            print(f"Generated {style} strategy: {len(data['strategy'])} chars")


class TestBacktestEndpoint:
    """Backtest endpoint tests"""
    
    def test_run_backtest_with_sample_strategy(self):
        """Test /api/run-backtest with a sample strategy text"""
        sample_strategy = """
        Strategy: EMA Crossover
        Entry: Buy when 10 EMA crosses above 20 EMA
        Exit: Sell when 10 EMA crosses below 20 EMA
        Stop Loss: 50 pips
        Take Profit: 100 pips
        """
        response = requests.post(f"{BASE_URL}/api/run-backtest", json={
            "strategy_text": sample_strategy,
            "pair": "EURUSD",
            "timeframe": "H1",
            "risk_percent": 1.0
        }, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        results = data["results"]
        # Verify backtest result structure
        assert "total_trades" in results
        assert "net_profit" in results
        assert "win_rate" in results
        assert "max_drawdown_pct" in results
        print(f"Backtest results: {results.get('total_trades')} trades, PnL: ${results.get('net_profit')}")
    
    def test_run_backtest_with_spread(self):
        """Test backtest with custom spread"""
        sample_strategy = "Buy when RSI < 30, Sell when RSI > 70. SL: 30 pips, TP: 60 pips"
        response = requests.post(f"{BASE_URL}/api/run-backtest", json={
            "strategy_text": sample_strategy,
            "pair": "GBPUSD",
            "timeframe": "M30",
            "spread_pips": 2.0,
            "risk_percent": 2.0
        }, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        print(f"Backtest with spread: {data['results'].get('total_trades')} trades")


class TestStrategyCRUD:
    """Strategy save/list/delete CRUD tests"""
    
    @pytest.fixture
    def saved_strategy_id(self):
        """Create a strategy and return its ID for testing"""
        response = requests.post(f"{BASE_URL}/api/save-strategy", json={
            "strategy_text": "TEST_CRUD_Strategy: Buy when price > SMA20, Sell when price < SMA20",
            "pair": "EURUSD",
            "timeframe": "H1",
            "backtest_results": {
                "total_trades": 10,
                "net_profit": 500,
                "win_rate": 60,
                "max_drawdown_pct": 5
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        return data["id"]
    
    def test_save_strategy(self):
        """Test /api/save-strategy"""
        response = requests.post(f"{BASE_URL}/api/save-strategy", json={
            "strategy_text": "TEST_Save_Strategy: Simple moving average crossover",
            "pair": "BTCUSD",
            "timeframe": "H4",
            "backtest_results": {
                "total_trades": 25,
                "net_profit": 1200,
                "win_rate": 55,
                "profit_factor": 1.8,
                "max_drawdown_pct": 8
            }
        })
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "status" in data
        print(f"Strategy saved with ID: {data['id']}, status: {data['status']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/strategies/{data['id']}")
    
    def test_get_strategies_list(self):
        """Test /api/strategies returns list"""
        response = requests.get(f"{BASE_URL}/api/strategies")
        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data
        assert isinstance(data["strategies"], list)
        print(f"Found {len(data['strategies'])} strategies in library")
    
    def test_get_strategies_with_filters(self):
        """Test /api/strategies with query filters"""
        response = requests.get(f"{BASE_URL}/api/strategies?symbol=EURUSD&sort_by=score&sort_dir=desc")
        assert response.status_code == 200
        data = response.json()
        assert "strategies" in data
        print(f"Filtered strategies: {len(data['strategies'])}")
    
    def test_delete_strategy(self, saved_strategy_id):
        """Test /api/strategies/{id} DELETE"""
        response = requests.delete(f"{BASE_URL}/api/strategies/{saved_strategy_id}")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"Deleted strategy: {saved_strategy_id}")
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/strategies/{saved_strategy_id}")
        assert get_response.status_code == 404


class TestOptimizationEndpoint:
    """Optimization endpoint tests"""
    
    def test_optimize_strategy(self):
        """Test /api/optimize-strategy"""
        sample_strategy = "EMA crossover: Buy when 10 EMA > 20 EMA, SL 40 pips, TP 80 pips"
        response = requests.post(f"{BASE_URL}/api/optimize-strategy", json={
            "strategy_text": sample_strategy,
            "pair": "EURUSD",
            "timeframe": "H1",
            "risk_percent": 1.0
        }, timeout=60)
        assert response.status_code == 200
        data = response.json()
        assert "optimization" in data
        opt = data["optimization"]
        assert "best_params" in opt or "iterations" in opt or "data_source" in opt
        print(f"Optimization completed: {opt.get('data_source', 'N/A')}")


class TestSafetyCheckEndpoint:
    """Safety check endpoint tests"""
    
    def test_safety_check(self):
        """Test /api/safety-check"""
        sample_strategy = "RSI strategy: Buy RSI<30, Sell RSI>70, SL 25 pips, TP 50 pips"
        response = requests.post(f"{BASE_URL}/api/safety-check", json={
            "strategy_text": sample_strategy,
            "pair": "EURUSD",
            "timeframe": "H1",
            "risk_percent": 1.0
        }, timeout=30)
        assert response.status_code == 200
        data = response.json()
        assert "safety" in data
        safety = data["safety"]
        assert "safety_score" in safety
        assert "is_safe" in safety
        assert "grade" in safety
        print(f"Safety check: score={safety['safety_score']}, grade={safety['grade']}, safe={safety['is_safe']}")


class TestMonteCarloEndpoint:
    """Monte Carlo simulation endpoint tests"""
    
    def test_monte_carlo(self):
        """Test /api/monte-carlo"""
        sample_strategy = "Bollinger Bands: Buy at lower band, Sell at upper band, SL 30 pips, TP 60 pips"
        response = requests.post(f"{BASE_URL}/api/monte-carlo", json={
            "strategy_text": sample_strategy,
            "pair": "EURUSD",
            "timeframe": "H1",
            "num_simulations": 50,
            "risk_percent": 1.0
        }, timeout=60)
        assert response.status_code == 200
        data = response.json()
        assert "monte_carlo" in data
        mc = data["monte_carlo"]
        # Monte Carlo may fail if not enough trades
        if mc.get("success") is False:
            print(f"Monte Carlo: Not enough trades - {mc.get('error', 'N/A')}")
        else:
            print(f"Monte Carlo completed: {mc.get('num_simulations', 'N/A')} simulations")


class TestMarketDataEndpoints:
    """Market data endpoint tests"""
    
    def test_get_market_data(self):
        """Test /api/market-data returns datasets list"""
        response = requests.get(f"{BASE_URL}/api/market-data")
        assert response.status_code == 200
        data = response.json()
        assert "datasets" in data
        assert isinstance(data["datasets"], list)
        print(f"Market data: {len(data['datasets'])} datasets available")
    
    def test_get_server_files(self):
        """Test /api/server-files returns file list"""
        response = requests.get(f"{BASE_URL}/api/server-files")
        assert response.status_code == 200
        data = response.json()
        assert "files" in data
        assert "import_directory" in data
        print(f"Server files: {len(data['files'])} files in {data['import_directory']}")


class TestLiveTrackingEndpoints:
    """Live tracking endpoint tests"""
    
    def test_get_tracked_strategies(self):
        """Test /api/live/strategies returns tracked list"""
        response = requests.get(f"{BASE_URL}/api/live/strategies")
        assert response.status_code == 200
        data = response.json()
        assert "tracked" in data
        assert isinstance(data["tracked"], list)
        print(f"Live tracking: {len(data['tracked'])} strategies being tracked")
    
    def test_start_stop_tracking_flow(self):
        """Test start/stop tracking flow (requires existing strategy)"""
        # First get a strategy ID
        strats_response = requests.get(f"{BASE_URL}/api/strategies")
        if strats_response.status_code != 200:
            pytest.skip("No strategies available for tracking test")
        
        strats = strats_response.json().get("strategies", [])
        if not strats:
            # Create a test strategy first
            save_response = requests.post(f"{BASE_URL}/api/save-strategy", json={
                "strategy_text": "TEST_Tracking_Strategy",
                "pair": "EURUSD",
                "timeframe": "H1",
                "backtest_results": {"total_trades": 5, "net_profit": 100}
            })
            if save_response.status_code == 200:
                strategy_id = save_response.json()["id"]
            else:
                pytest.skip("Could not create test strategy")
        else:
            strategy_id = strats[0]["id"]
        
        # Start tracking
        start_response = requests.post(f"{BASE_URL}/api/live/start", json={
            "strategy_id": strategy_id,
            "failure_threshold": 3,
            "auto_disable": True
        })
        assert start_response.status_code == 200
        print(f"Started tracking: {strategy_id}")
        
        # Stop tracking
        stop_response = requests.post(f"{BASE_URL}/api/live/stop", json={
            "strategy_id": strategy_id
        })
        assert stop_response.status_code == 200
        print(f"Stopped tracking: {strategy_id}")


class TestPortfolioEndpoints:
    """Portfolio analysis endpoint tests"""
    
    def test_portfolio_analyze_requires_strategies(self):
        """Test /api/portfolio-analyze with no strategies returns error"""
        response = requests.post(f"{BASE_URL}/api/portfolio-analyze", json={
            "strategy_ids": []
        })
        # Should return 400 for empty list
        assert response.status_code == 400
        print("Portfolio analyze correctly rejects empty strategy list")
    
    def test_portfolio_auto_build(self):
        """Test /api/portfolio-auto-build"""
        response = requests.post(f"{BASE_URL}/api/portfolio-auto-build", json={
            "target_size": 3,
            "max_pair_corr": 0.6,
            "min_score": 0,
            "min_safety": 0
        })
        # May return 400 if no strategies in library
        if response.status_code == 400:
            data = response.json()
            print(f"Auto build: {data.get('detail', 'No strategies')}")
        else:
            assert response.status_code == 200
            data = response.json()
            print(f"Auto build: {data.get('success', False)}")


class TestRebalanceEndpoints:
    """Rebalance configuration endpoint tests"""
    
    def test_get_rebalance_config(self):
        """Test /api/rebalance/config GET"""
        response = requests.get(f"{BASE_URL}/api/rebalance/config")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "interval_minutes" in data
        print(f"Rebalance config: enabled={data['enabled']}, interval={data['interval_minutes']}min")
    
    def test_save_rebalance_config(self):
        """Test /api/rebalance/config POST"""
        response = requests.post(f"{BASE_URL}/api/rebalance/config", json={
            "enabled": False,
            "strategy_ids": [],
            "interval_minutes": 120,
            "max_allocation_pct": 40.0,
            "deviation_threshold_pct": 15.0
        })
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"Rebalance config saved: {data['message']}")
    
    def test_get_rebalance_status(self):
        """Test /api/rebalance/status"""
        response = requests.get(f"{BASE_URL}/api/rebalance/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "strategy_count" in data
        print(f"Rebalance status: enabled={data['enabled']}, strategies={data['strategy_count']}")


class TestPipelineEndpoints:
    """Pipeline and Auto Factory endpoint tests"""
    
    def test_run_pipeline(self):
        """Test /api/run-pipeline"""
        response = requests.post(f"{BASE_URL}/api/run-pipeline", json={
            "pair": "EURUSD",
            "timeframe": "H1",
            "count": 2,
            "risk_percent": 1.0
        }, timeout=120)  # Pipeline can take time
        assert response.status_code == 200
        data = response.json()
        assert "ranked_strategies" in data
        assert "best_strategy" in data
        assert "steps_log" in data
        print(f"Pipeline: {data.get('total_generated', 0)} generated, {data.get('total_backtested', 0)} backtested")
    
    def test_auto_factory(self):
        """Test /api/auto-factory"""
        response = requests.post(f"{BASE_URL}/api/auto-factory", json={
            "symbols": ["EURUSD"],
            "timeframes": ["H1"],
            "strategies_per_pair": 2,
            "keep_top_n": 1,
            "risk_percent": 1.0,
            "min_trades": 1,
            "min_win_rate": 0,
            "min_score": 0,
            "min_safety_score": 0
        }, timeout=180)  # Auto factory can take longer
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "summary" in data
        print(f"Auto Factory: {data['summary'].get('total_saved', 0)} strategies saved")


class TestAllocationHistory:
    """Allocation history endpoint tests"""
    
    def test_get_allocation_history(self):
        """Test /api/allocation-history"""
        response = requests.get(f"{BASE_URL}/api/allocation-history?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "history" in data
        assert "total" in data
        print(f"Allocation history: {data['total']} records")


# Cleanup test data after all tests
@pytest.fixture(scope="session", autouse=True)
def cleanup_test_strategies():
    """Cleanup TEST_ prefixed strategies after test session"""
    yield
    # Cleanup
    try:
        response = requests.get(f"{BASE_URL}/api/strategies")
        if response.status_code == 200:
            strategies = response.json().get("strategies", [])
            for s in strategies:
                if s.get("strategy_text", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/strategies/{s['id']}")
                    print(f"Cleaned up test strategy: {s['id']}")
    except Exception as e:
        print(f"Cleanup error: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
