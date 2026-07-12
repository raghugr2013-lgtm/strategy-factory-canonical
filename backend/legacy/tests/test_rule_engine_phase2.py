"""
Phase 2: Rule Engine + Versioning Tests for Prop Firm Challenge Simulator.

Tests:
- GET /api/challenge-firms (DB-backed, source='database')
- GET /api/challenge-rules (all rules with full schema)
- GET /api/challenge-rules/{firm_slug} (single firm's complete rule schema)
- POST /api/challenge-rules (create new rule set with version=1)
- PUT /api/challenge-rules/{firm_slug} (update + version bump)
- DELETE /api/challenge-rules/{firm_slug}
- POST /api/challenge-rules/{firm_slug}/validate
- POST /api/challenge-rules/{firm_slug}/override
- GET /api/challenge-rules/{firm_slug}/changelog
- POST /api/simulate-challenge (now uses DB rules, returns rule_source field)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test firm slug for CRUD operations (will be cleaned up after tests)
TEST_FIRM_SLUG = "test_firm_phase2"


class TestChallengeFirmsFromDB:
    """Test GET /api/challenge-firms returns firms from DB with source='database'."""

    def test_endpoint_returns_200(self):
        """Verify endpoint is accessible."""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASSED: GET /api/challenge-firms returns 200")

    def test_source_is_database(self):
        """Verify source field is 'database' (not hardcoded)."""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        data = response.json()
        assert data.get("source") == "database", f"Expected source='database', got {data.get('source')}"
        print("PASSED: source='database' confirms DB-backed rules")

    def test_returns_seeded_firms(self):
        """Verify 3 seed firms are present: ftmo, fundednext, pipfarm."""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        data = response.json()
        firms = data.get("firms", {})
        expected_firms = ["ftmo", "fundednext", "pipfarm"]
        for firm in expected_firms:
            assert firm in firms, f"Missing seeded firm: {firm}"
        print(f"PASSED: All 3 seeded firms present: {expected_firms}")

    def test_firm_has_rules_structure(self):
        """Verify each firm has the full rules structure."""
        response = requests.get(f"{BASE_URL}/api/challenge-firms")
        data = response.json()
        firms = data.get("firms", {})
        for slug, firm in firms.items():
            assert "rules" in firm, f"Firm {slug} missing 'rules' field"
            assert "version" in firm, f"Firm {slug} missing 'version' field"
            assert "confidence_score" in firm, f"Firm {slug} missing 'confidence_score' field"
            assert "validated" in firm, f"Firm {slug} missing 'validated' field"
        print("PASSED: All firms have rules, version, confidence_score, validated fields")


class TestChallengeRulesListAll:
    """Test GET /api/challenge-rules returns all rule sets with full schema."""

    def test_endpoint_returns_200(self):
        """Verify endpoint is accessible."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("PASSED: GET /api/challenge-rules returns 200")

    def test_returns_rules_array(self):
        """Verify response contains rules array."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules")
        data = response.json()
        assert "rules" in data, "Missing 'rules' field in response"
        assert isinstance(data["rules"], list), "rules should be a list"
        assert "count" in data, "Missing 'count' field"
        print(f"PASSED: Returns {data['count']} rules")

    def test_rule_has_full_schema(self):
        """Verify each rule has the complete structured schema."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules")
        data = response.json()
        rules = data.get("rules", [])
        assert len(rules) >= 3, f"Expected at least 3 seeded rules, got {len(rules)}"
        
        required_fields = [
            "firm_slug", "firm_name", "phase", "version", "initial_balance",
            "rules", "confidence_score", "validated", "changelog"
        ]
        for rule in rules:
            for field in required_fields:
                assert field in rule, f"Rule {rule.get('firm_slug')} missing field: {field}"
        print("PASSED: All rules have complete schema")


class TestChallengeRulesGetSingle:
    """Test GET /api/challenge-rules/{firm_slug} returns single firm's complete rule schema."""

    def test_get_ftmo_rules(self):
        """Verify FTMO rules can be fetched."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/ftmo")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "rule" in data, "Missing 'rule' field"
        rule = data["rule"]
        assert rule["firm_slug"] == "ftmo"
        assert rule["firm_name"] == "FTMO"
        print("PASSED: GET /api/challenge-rules/ftmo returns FTMO rules")

    def test_nonexistent_firm_returns_404(self):
        """Verify 404 for non-existent firm."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/nonexistent_firm_xyz")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASSED: Non-existent firm returns 404")


class TestRuleSubRulesStructure:
    """Test that rules have structured sub-rules: daily_dd, total_dd, consistency, restrictions."""

    def test_daily_dd_structure(self):
        """Verify daily_dd has type (equity/balance) and max_pct."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/ftmo")
        data = response.json()
        rules = data["rule"]["rules"]
        daily_dd = rules.get("daily_dd", {})
        assert "type" in daily_dd, "daily_dd missing 'type' field"
        assert daily_dd["type"] in ["equity", "balance"], f"Invalid daily_dd type: {daily_dd['type']}"
        assert "max_pct" in daily_dd, "daily_dd missing 'max_pct' field"
        assert "enabled" in daily_dd, "daily_dd missing 'enabled' field"
        print(f"PASSED: daily_dd has type={daily_dd['type']}, max_pct={daily_dd['max_pct']}")

    def test_total_dd_structure(self):
        """Verify total_dd has type (static/trailing) and max_pct."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/pipfarm")
        data = response.json()
        rules = data["rule"]["rules"]
        total_dd = rules.get("total_dd", {})
        assert "type" in total_dd, "total_dd missing 'type' field"
        assert total_dd["type"] in ["static", "trailing"], f"Invalid total_dd type: {total_dd['type']}"
        assert "max_pct" in total_dd, "total_dd missing 'max_pct' field"
        # PipFarm should have trailing DD
        assert total_dd["type"] == "trailing", f"PipFarm should have trailing DD, got {total_dd['type']}"
        print(f"PASSED: total_dd has type={total_dd['type']}, max_pct={total_dd['max_pct']}")

    def test_consistency_structure(self):
        """Verify consistency rule has enabled/min_lots_per_day/max_daily_profit_pct."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/ftmo")
        data = response.json()
        rules = data["rule"]["rules"]
        consistency = rules.get("consistency", {})
        assert "enabled" in consistency, "consistency missing 'enabled' field"
        assert "min_lots_per_day" in consistency, "consistency missing 'min_lots_per_day' field"
        assert "max_daily_profit_pct" in consistency, "consistency missing 'max_daily_profit_pct' field"
        print("PASSED: consistency rule has correct structure")

    def test_restrictions_structure(self):
        """Verify restrictions rule has news_blackout_minutes/max_overnight_lots/weekend_hold_allowed."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/ftmo")
        data = response.json()
        rules = data["rule"]["rules"]
        restrictions = rules.get("restrictions", {})
        assert "news_blackout_minutes" in restrictions, "restrictions missing 'news_blackout_minutes'"
        assert "max_overnight_lots" in restrictions, "restrictions missing 'max_overnight_lots'"
        assert "weekend_hold_allowed" in restrictions, "restrictions missing 'weekend_hold_allowed'"
        print("PASSED: restrictions rule has correct structure")

    def test_profit_target_structure(self):
        """Verify profit_target rule exists."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/ftmo")
        data = response.json()
        rules = data["rule"]["rules"]
        profit_target = rules.get("profit_target", {})
        assert "enabled" in profit_target, "profit_target missing 'enabled'"
        assert "target_pct" in profit_target, "profit_target missing 'target_pct'"
        print(f"PASSED: profit_target has target_pct={profit_target['target_pct']}")

    def test_min_trading_days_structure(self):
        """Verify min_trading_days rule exists."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/ftmo")
        data = response.json()
        rules = data["rule"]["rules"]
        min_days = rules.get("min_trading_days", {})
        assert "enabled" in min_days, "min_trading_days missing 'enabled'"
        assert "days" in min_days, "min_trading_days missing 'days'"
        print(f"PASSED: min_trading_days has days={min_days['days']}")

    def test_time_limit_structure(self):
        """Verify time_limit rule exists."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/ftmo")
        data = response.json()
        rules = data["rule"]["rules"]
        time_limit = rules.get("time_limit", {})
        assert "enabled" in time_limit, "time_limit missing 'enabled'"
        assert "calendar_days" in time_limit, "time_limit missing 'calendar_days'"
        print(f"PASSED: time_limit has calendar_days={time_limit['calendar_days']}")


class TestRuleEngineCRUD:
    """Test CRUD operations for rule engine."""

    def test_create_rule_with_version_1(self):
        """Test POST /api/challenge-rules creates new rule set with version=1."""
        # First, ensure test firm doesn't exist (cleanup from previous runs)
        requests.delete(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}")
        
        payload = {
            "firm_slug": TEST_FIRM_SLUG,
            "firm_name": "Test Firm Phase 2",
            "phase": "Test Challenge",
            "initial_balance": 50000,
            "rules": {
                "daily_dd": {"enabled": True, "type": "equity", "max_pct": 4.0},
                "total_dd": {"enabled": True, "type": "static", "max_pct": 8.0},
                "profit_target": {"enabled": True, "target_pct": 8.0},
                "min_trading_days": {"enabled": True, "days": 3},
                "time_limit": {"enabled": False, "calendar_days": 0},
                "consistency": {"enabled": False, "min_lots_per_day": None, "max_daily_profit_pct": None},
                "restrictions": {"news_blackout_minutes": None, "max_overnight_lots": None, "weekend_hold_allowed": True}
            },
            "confidence_score": 70,
            "confidence_notes": "Test rule for Phase 2 testing"
        }
        response = requests.post(f"{BASE_URL}/api/challenge-rules", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "rule" in data, "Missing 'rule' in response"
        rule = data["rule"]
        assert rule["version"] == 1, f"Expected version=1, got {rule['version']}"
        assert rule["firm_slug"] == TEST_FIRM_SLUG
        print(f"PASSED: Created rule set with version=1 for {TEST_FIRM_SLUG}")

    def test_duplicate_firm_slug_returns_400(self):
        """Test that creating duplicate firm_slug returns 400."""
        payload = {
            "firm_slug": TEST_FIRM_SLUG,
            "firm_name": "Duplicate Test",
            "rules": {}
        }
        response = requests.post(f"{BASE_URL}/api/challenge-rules", json=payload)
        assert response.status_code == 400, f"Expected 400 for duplicate, got {response.status_code}"
        print("PASSED: Duplicate firm_slug returns 400")

    def test_update_rule_increments_version(self):
        """Test PUT /api/challenge-rules/{firm_slug} updates rules and increments version."""
        # Get current version
        get_response = requests.get(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}")
        assert get_response.status_code == 200
        current_version = get_response.json()["rule"]["version"]
        
        # Update
        update_payload = {
            "rules": {
                "daily_dd": {"enabled": True, "type": "balance", "max_pct": 5.0},
                "total_dd": {"enabled": True, "type": "trailing", "max_pct": 10.0},
                "profit_target": {"enabled": True, "target_pct": 10.0},
                "min_trading_days": {"enabled": True, "days": 5},
                "time_limit": {"enabled": True, "calendar_days": 30},
                "consistency": {"enabled": False, "min_lots_per_day": None, "max_daily_profit_pct": None},
                "restrictions": {"news_blackout_minutes": 15, "max_overnight_lots": 5, "weekend_hold_allowed": False}
            },
            "change_note": "Updated rules for testing version increment"
        }
        response = requests.put(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}", json=update_payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        new_version = data["rule"]["version"]
        assert new_version == current_version + 1, f"Expected version {current_version + 1}, got {new_version}"
        print(f"PASSED: Update incremented version from {current_version} to {new_version}")

    def test_update_nonexistent_returns_404(self):
        """Test PUT on non-existent firm returns 404."""
        response = requests.put(f"{BASE_URL}/api/challenge-rules/nonexistent_xyz", json={"rules": {}})
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASSED: Update non-existent firm returns 404")


class TestRuleVersioningAndChangelog:
    """Test versioning and changelog functionality."""

    def test_changelog_tracks_changes(self):
        """Test GET /api/challenge-rules/{firm_slug}/changelog returns version history."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}/changelog")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "changelog" in data, "Missing 'changelog' field"
        assert "current_version" in data, "Missing 'current_version' field"
        changelog = data["changelog"]
        assert len(changelog) >= 2, f"Expected at least 2 changelog entries, got {len(changelog)}"
        # Verify changelog entries have required fields
        for entry in changelog:
            assert "version" in entry, "Changelog entry missing 'version'"
            assert "date" in entry, "Changelog entry missing 'date'"
            assert "changes" in entry, "Changelog entry missing 'changes'"
        print(f"PASSED: Changelog has {len(changelog)} entries with version/date/changes")

    def test_changelog_nonexistent_returns_404(self):
        """Test changelog for non-existent firm returns 404."""
        response = requests.get(f"{BASE_URL}/api/challenge-rules/nonexistent_xyz/changelog")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASSED: Changelog for non-existent firm returns 404")


class TestRuleValidation:
    """Test rule validation endpoint."""

    def test_validate_rule_sets_confidence_and_validated(self):
        """Test POST /api/challenge-rules/{firm_slug}/validate sets confidence_score and validated=true."""
        payload = {
            "confidence_score": 95,
            "notes": "Validated during Phase 2 testing"
        }
        response = requests.post(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}/validate", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        rule = data["rule"]
        assert rule["validated"] == True, "Expected validated=True"
        assert rule["confidence_score"] == 95, f"Expected confidence_score=95, got {rule['confidence_score']}"
        assert rule["validated_at"] is not None, "Expected validated_at to be set"
        print("PASSED: Validate sets confidence_score=95 and validated=True")

    def test_validate_nonexistent_returns_404(self):
        """Test validate on non-existent firm returns 404."""
        response = requests.post(f"{BASE_URL}/api/challenge-rules/nonexistent_xyz/validate", json={"confidence_score": 50})
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASSED: Validate non-existent firm returns 404")


class TestRuleOverride:
    """Test rule override endpoint."""

    def test_override_sets_flag_and_bumps_version(self):
        """Test POST /api/challenge-rules/{firm_slug}/override sets manual_override and bumps version."""
        # Get current version
        get_response = requests.get(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}")
        current_version = get_response.json()["rule"]["version"]
        
        payload = {
            "override": True,
            "note": "Manual override for testing"
        }
        response = requests.post(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}/override", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        rule = data["rule"]
        assert rule["manual_override"] == True, "Expected manual_override=True"
        assert rule["version"] == current_version + 1, f"Expected version {current_version + 1}, got {rule['version']}"
        print(f"PASSED: Override sets manual_override=True and bumps version to {rule['version']}")

    def test_override_nonexistent_returns_404(self):
        """Test override on non-existent firm returns 404."""
        response = requests.post(f"{BASE_URL}/api/challenge-rules/nonexistent_xyz/override", json={"override": True})
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASSED: Override non-existent firm returns 404")


class TestSimulateChallengeWithDBRules:
    """Test POST /api/simulate-challenge uses DB rules and returns rule_source field."""

    def test_simulate_with_ftmo_loads_from_db(self):
        """Test simulation with firm=ftmo loads rules from DB (rule_source=database)."""
        trades = [
            {"net_pnl": 500, "floating_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 300, "floating_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
            {"net_pnl": 400, "floating_pnl": -80, "timestamp": "2024-01-03T10:00:00"},
            {"net_pnl": 600, "floating_pnl": -120, "timestamp": "2024-01-04T10:00:00"},
            {"net_pnl": 500, "floating_pnl": -100, "timestamp": "2024-01-05T10:00:00"},
        ]
        payload = {
            "strategy_trades": trades,
            "firm": "ftmo"
        }
        response = requests.post(f"{BASE_URL}/api/simulate-challenge", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        simulation = data["simulation"]
        assert "rule_source" in simulation, "Missing 'rule_source' field"
        assert simulation["rule_source"] == "database", f"Expected rule_source='database', got {simulation['rule_source']}"
        print("PASSED: Simulation with firm=ftmo uses rule_source='database'")

    def test_simulate_with_custom_rules_still_works(self):
        """Test simulation with custom rules_config still works (backward compatible)."""
        trades = [
            {"net_pnl": 500, "floating_pnl": -100, "timestamp": "2024-01-01T10:00:00"},
            {"net_pnl": 300, "floating_pnl": -50, "timestamp": "2024-01-02T10:00:00"},
        ]
        custom_rules = {
            "initial_balance": 50000,
            "profit_target_pct": 5.0,
            "max_daily_dd_pct": 3.0,
            "max_total_dd_pct": 6.0,
            "min_trading_days": 2,
            "time_limit_days": 0,
            "drawdown_type": "static"
        }
        payload = {
            "strategy_trades": trades,
            "rules_config": custom_rules
        }
        response = requests.post(f"{BASE_URL}/api/simulate-challenge", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        simulation = data["simulation"]
        assert simulation["rule_source"] == "custom", f"Expected rule_source='custom', got {simulation['rule_source']}"
        print("PASSED: Simulation with custom rules_config works (rule_source='custom')")

    def test_simulate_result_includes_rule_source(self):
        """Verify simulation result always includes rule_source field."""
        trades = [{"net_pnl": 100, "timestamp": "2024-01-01T10:00:00"}]
        payload = {"strategy_trades": trades, "firm": "fundednext"}
        response = requests.post(f"{BASE_URL}/api/simulate-challenge", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "rule_source" in data["simulation"], "Missing rule_source in simulation result"
        print(f"PASSED: Simulation result includes rule_source={data['simulation']['rule_source']}")


class TestDeleteRule:
    """Test DELETE /api/challenge-rules/{firm_slug}."""

    def test_delete_rule(self):
        """Test DELETE removes rule set."""
        response = requests.delete(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify it's gone
        get_response = requests.get(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}")
        assert get_response.status_code == 404, "Rule should be deleted"
        print(f"PASSED: Deleted rule set '{TEST_FIRM_SLUG}'")

    def test_delete_nonexistent_returns_404(self):
        """Test DELETE on non-existent firm returns 404."""
        response = requests.delete(f"{BASE_URL}/api/challenge-rules/nonexistent_xyz")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASSED: Delete non-existent firm returns 404")


class TestCleanup:
    """Cleanup test data after all tests."""

    def test_cleanup_test_firm(self):
        """Ensure test firm is deleted (cleanup)."""
        response = requests.delete(f"{BASE_URL}/api/challenge-rules/{TEST_FIRM_SLUG}")
        # Don't assert - it may already be deleted
        print(f"CLEANUP: Attempted to delete {TEST_FIRM_SLUG} (status: {response.status_code})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
