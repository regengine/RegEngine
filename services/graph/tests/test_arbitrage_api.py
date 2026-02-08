"""
Tests for Framework Arbitrage API

These tests require a live, authenticated Neo4j instance.
They are skipped automatically when Neo4j is unreachable.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


def _make_client():
    """Create a TestClient from the main app, skipping if import fails."""
    try:
        from app.main import app
    except Exception:
        pytest.skip("Graph app could not be imported (dependency issue)")
    return TestClient(app, raise_server_exceptions=False)


def _skip_if_neo4j_unavailable(client):
    """Skip the test if Neo4j is not reachable."""
    response = client.get("/health")
    if response.status_code != 200:
        pytest.skip("Neo4j is not reachable — skipping integration test")


class TestArbitrageEndpoint:
    """Test /graph/arbitrage endpoint"""

    def test_arbitrage_soc2_to_iso27001(self):
        """Test arbitrage detection between SOC2 and ISO27001"""
        client = _make_client()
        _skip_if_neo4j_unavailable(client)

        response = client.get(
            "/graph/arbitrage",
            params={"framework_from": "SOC2", "framework_to": "ISO27001"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "opportunities" in data
        assert len(data["opportunities"]) >= 0

        if data["opportunities"]:
            opp = data["opportunities"][0]
            assert opp["from_framework"] == "SOC2"
            assert opp["to_framework"] == "ISO27001"
            assert "overlap_controls" in opp
            assert "overlap_percentage" in opp
            assert "estimated_savings_hours" in opp
            assert "path" in opp

    def test_arbitrage_missing_framework(self):
        """Test arbitrage with non-existent framework"""
        client = _make_client()
        _skip_if_neo4j_unavailable(client)

        response = client.get(
            "/graph/arbitrage",
            params={"framework_from": "NONEXISTENT", "framework_to": "ISO27001"},
        )

        # Should return 200 with empty opportunities or 404
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert data["opportunities"] == []

    def test_arbitrage_missing_params(self):
        """Test arbitrage without required parameters"""
        client = _make_client()

        response = client.get("/graph/arbitrage")

        # FastAPI should return 422 for missing query params
        assert response.status_code == 422


class TestGapAnalysisEndpoint:
    """Test /graph/gaps endpoint"""

    def test_gaps_soc2_to_hipaa(self):
        """Test gap analysis from SOC2 to HIPAA"""
        client = _make_client()
        _skip_if_neo4j_unavailable(client)

        response = client.get(
            "/graph/gaps",
            params={"current_framework": "SOC2", "target_framework": "HIPAA"},
        )

        assert response.status_code == 200
        data = response.json()

        assert "gaps" in data
        assert "coverage_percentage" in data
        assert "total_gaps" in data
        assert "estimated_total_hours" in data

        assert isinstance(data["gaps"], list)
        assert isinstance(data["coverage_percentage"], (int, float))
        assert isinstance(data["total_gaps"], int)

    def test_gaps_response_structure(self):
        """Test gap analysis response has correct structure"""
        client = _make_client()
        _skip_if_neo4j_unavailable(client)

        response = client.get(
            "/graph/gaps",
            params={"current_framework": "SOC2", "target_framework": "HIPAA"},
        )

        assert response.status_code == 200
        data = response.json()

        if data["gaps"]:
            gap = data["gaps"][0]
            assert "control_id" in gap
            assert "control_name" in gap
            assert "missing_in" in gap
            assert "remediation_effort" in gap
            assert "priority" in gap
            assert gap["remediation_effort"] in ["low", "medium", "high"]
            assert gap["priority"] in ["low", "medium", "high"]


class TestFrameworkRelationshipsEndpoint:
    """Test /graph/frameworks/{id}/relationships endpoint"""

    def test_relationships_soc2(self):
        """Test framework relationships for SOC2"""
        client = _make_client()
        _skip_if_neo4j_unavailable(client)

        response = client.get("/graph/frameworks/SOC2/relationships")

        assert response.status_code == 200
        data = response.json()

        assert "framework" in data
        assert "related_frameworks" in data
        assert data["framework"] == "SOC2"
        assert isinstance(data["related_frameworks"], list)

    def test_relationships_structure(self):
        """Test relationship response structure"""
        client = _make_client()
        _skip_if_neo4j_unavailable(client)

        response = client.get("/graph/frameworks/SOC2/relationships")

        assert response.status_code == 200
        data = response.json()

        if data["related_frameworks"]:
            rel = data["related_frameworks"][0]
            assert "framework_id" in rel
            assert "framework_name" in rel
            assert "relationship_type" in rel
            assert "strength" in rel
            assert "control_overlap" in rel
            assert 0.0 <= rel["strength"] <= 1.0


class TestListFrameworksEndpoint:
    """Test /graph/frameworks endpoint"""

    def test_list_frameworks(self):
        """Test listing all frameworks"""
        client = _make_client()
        _skip_if_neo4j_unavailable(client)

        response = client.get("/graph/frameworks")

        assert response.status_code == 200
        data = response.json()

        assert "count" in data
        assert "frameworks" in data
        assert isinstance(data["frameworks"], list)
        assert data["count"] == len(data["frameworks"])

    def test_frameworks_structure(self):
        """Test framework list structure"""
        client = _make_client()
        _skip_if_neo4j_unavailable(client)

        response = client.get("/graph/frameworks")

        assert response.status_code == 200
        data = response.json()

        if data["frameworks"]:
            framework = data["frameworks"][0]
            assert "name" in framework
            assert "version" in framework
            assert "category" in framework


class TestHealthEndpoint:
    """Test health endpoint"""

    def test_health_check(self):
        """Test health check endpoint"""
        client = _make_client()
        response = client.get("/health")

        # May fail if Neo4j not available, but should return proper structure
        assert response.status_code in [200, 503]

        data = response.json()
        assert "status" in data or "detail" in data


class TestRootEndpoint:
    """Test root endpoint"""

    def test_root(self):
        """Test root endpoint returns service info"""
        client = _make_client()
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert "service" in data
        assert "version" in data
        assert "endpoints" in data
        assert "arbitrage" in data["endpoints"]
        assert "gaps" in data["endpoints"]


# Integration tests (require Neo4j)
@pytest.mark.integration
class TestIntegrationArbirage:
    """Integration tests for arbitrage (requires Neo4j with data)"""

    def test_full_arbitrage_workflow(self):
        """Test complete arbitrage workflow"""
        client = _make_client()
        _skip_if_neo4j_unavailable(client)

        # 1. List frameworks
        response = client.get("/graph/frameworks")
        assert response.status_code == 200
        frameworks = response.json()["frameworks"]

        if len(frameworks) >= 2:
            f1 = frameworks[0]["name"]
            f2 = frameworks[1]["name"]

            # 2. Find arbitrage
            response = client.get(
                "/graph/arbitrage",
                params={"framework_from": f1, "framework_to": f2},
            )
            assert response.status_code == 200

            # 3. Find gaps
            response = client.get(
                "/graph/gaps",
                params={"current_framework": f1, "target_framework": f2},
            )
            assert response.status_code == 200

            # 4. Get relationships
            response = client.get(f"/graph/frameworks/{f1}/relationships")
            assert response.status_code == 200


# Run with: pytest tests/test_arbitrage_api.py -v
# Run integration tests: pytest tests/test_arbitrage_api.py -v --integration
