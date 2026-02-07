"""
Tests for Framework Arbitrage API
"""

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.fixture
def client():
    """Test client fixture"""
    return AsyncClient(app=app, base_url="http://test")


class TestArbitrageEndpoint:
    """Test /graph/arbitrage endpoint"""

    @pytest.mark.asyncio
    async def test_arbitrage_soc2_to_iso27001(self, client):
        """Test arbitrage detection between SOC2 and ISO27001"""
        response = await client.get(
            "/graph/arbitrage",
            params={"framework_from": "SOC2", "framework_to": "ISO27001"}
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

    @pytest.mark.asyncio
    async def test_arbitrage_missing_framework(self, client):
        """Test arbitrage with non-existent framework"""
        response = await client.get(
            "/graph/arbitrage",
            params={"framework_from": "NONEXISTENT", "framework_to": "ISO27001"}
        )
        
        # Should return 200 with empty opportunities or 404
        assert response.status_code in [200, 404]
        
        if response.status_code == 200:
            data = response.json()
            assert data["opportunities"] == []

    @pytest.mark.asyncio
    async def test_arbitrage_missing_params(self, client):
        """Test arbitrage without required parameters"""
        response = await client.get("/graph/arbitrage")
        
        # FastAPI should return 422 for missing query params
        assert response.status_code == 422


class TestGapAnalysisEndpoint:
    """Test /graph/gaps endpoint"""

    @pytest.mark.asyncio
    async def test_gaps_soc2_to_hipaa(self, client):
        """Test gap analysis from SOC2 to HIPAA"""
        response = await client.get(
            "/graph/gaps",
            params={"current_framework": "SOC2", "target_framework": "HIPAA"}
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

    @pytest.mark.asyncio
    async def test_gaps_response_structure(self, client):
        """Test gap analysis response has correct structure"""
        response = await client.get(
            "/graph/gaps",
            params={"current_framework": "SOC2", "target_framework": "HIPAA"}
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

    @pytest.mark.asyncio
    async def test_relationships_soc2(self, client):
        """Test framework relationships for SOC2"""
        response = await client.get("/graph/frameworks/SOC2/relationships")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "framework" in data
        assert "related_frameworks" in data
        assert data["framework"] == "SOC2"
        assert isinstance(data["related_frameworks"], list)

    @pytest.mark.asyncio
    async def test_relationships_structure(self, client):
        """Test relationship response structure"""
        response = await client.get("/graph/frameworks/SOC2/relationships")
        
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

    @pytest.mark.asyncio
    async def test_list_frameworks(self, client):
        """Test listing all frameworks"""
        response = await client.get("/graph/frameworks")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "count" in data
        assert "frameworks" in data
        assert isinstance(data["frameworks"], list)
        assert data["count"] == len(data["frameworks"])

    @pytest.mark.asyncio
    async def test_frameworks_structure(self, client):
        """Test framework list structure"""
        response = await client.get("/graph/frameworks")
        
        assert response.status_code == 200
        data = response.json()
        
        if data["frameworks"]:
            framework = data["frameworks"][0]
            assert "name" in framework
            assert "version" in framework
            assert "category" in framework


class TestHealthEndpoint:
    """Test health endpoint"""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """Test health check endpoint"""
        response = await client.get("/health")
        
        # May fail if Neo4j not available, but should return proper structure
        assert response.status_code in [200, 503]
        
        data = response.json()
        assert "status" in data or "detail" in data


class TestRootEndpoint:
    """Test root endpoint"""

    @pytest.mark.asyncio
    async def test_root(self, client):
        """Test root endpoint returns service info"""
        response = await client.get("/")
        
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

    @pytest.mark.asyncio
    async def test_full_arbitrage_workflow(self, client):
        """Test complete arbitrage workflow"""
        # 1. List frameworks
        response = await client.get("/graph/frameworks")
        assert response.status_code == 200
        frameworks = response.json()["frameworks"]
        
        if len(frameworks) >= 2:
            f1 = frameworks[0]["name"]
            f2 = frameworks[1]["name"]
            
            # 2. Find arbitrage
            response = await client.get(
                "/graph/arbitrage",
                params={"framework_from": f1, "framework_to": f2}
            )
            assert response.status_code == 200
            
            # 3. Find gaps
            response = await client.get(
                "/graph/gaps",
                params={"current_framework": f1, "target_framework": f2}
            )
            assert response.status_code == 200
            
            # 4. Get relationships
            response = await client.get(f"/graph/frameworks/{f1}/relationships")
            assert response.status_code == 200


# Run with: pytest tests/test_arbitrage_api.py -v
# Run integration tests: pytest tests/test_arbitrage_api.py -v --integration
