"""
Integration Tests: Service-to-Service Communication
Tests complete workflows across multiple RegEngine services
"""

import pytest
import httpx
from datetime import datetime, timedelta

# Service URLs (can be overridden with env vars)
ADMIN_URL = "http://localhost:8000"
ENERGY_URL = "http://localhost:8001"
OPPORTUNITY_URL = "http://localhost:8002"
GRAPH_URL = "http://localhost:8003"

@pytest.fixture
async def auth_token():
    """Get authentication token from admin service"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ADMIN_URL}/auth/login",
            json={"email": "integration@test.com", "password": "testpass123"}
        )
        assert response.status_code == 200
        return response.json()["access_token"]

@pytest.fixture
async def tenant_id(auth_token):
    """Get tenant ID for testing"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ADMIN_URL}/v1/tenants/current",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        return response.json()["tenant_id"]


class TestAdminToEnergyFlow:
    """Test authentication and snapshot creation flow"""
    
    @pytest.mark.asyncio
    async def test_authenticated_snapshot_creation(self, auth_token, tenant_id):
        """Create snapshot with proper authentication"""
        async with httpx.AsyncClient() as client:
            # Create snapshot via Energy service
            snapshot_data = {
                "substation_id": "SUB-INT-001",
                "facility_name": "Integration Test Facility",
                "voltage_kv": 138,
                "firmware_versions": {
                    "pmu": "2.1.0",
                    "rtu": "3.0.1"
                }
            }
            
            response = await client.post(
                f"{ENERGY_URL}/energy/snapshots",
                json=snapshot_data,
                headers={
                    "Authorization": f"Bearer {auth_token}",
                    "X-Tenant-ID": tenant_id
                }
            )
            
            assert response.status_code == 201
            snapshot = response.json()
            assert snapshot["snapshot_id"]
            assert snapshot["substation_id"] == "SUB-INT-001"
            assert snapshot["created_by"]  # Should have user attribution
            
            # Verify we can retrieve it
            snapshot_id = snapshot["snapshot_id"]
            response = await client.get(
                f"{ENERGY_URL}/energy/snapshots/{snapshot_id}",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            
            assert response.status_code == 200
            retrieved = response.json()
            assert retrieved["snapshot_id"] == snapshot_id


class TestEnergyToOpportunityFlow:
    """Test compliance data flow to opportunity detection"""
    
    @pytest.mark.asyncio
    async def test_snapshot_triggers_opportunity_analysis(self, auth_token):
        """Creating compliant snapshot should enable arbitrage detection"""
        async with httpx.AsyncClient() as client:
            # Create compliant snapshot
            snapshot_data = {
                "substation_id": "SUB-OPP-001",
                "compliance_data": {
                    "cip_013": {
                        "patch_management": True,
                        "access_controls": True,
                        "supply_chain_risk": True
                    }
                }
            }
            
            response = await client.post(
                f"{ENERGY_URL}/energy/snapshots",
                json=snapshot_data,
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            
            assert response.status_code == 201
            
            # Check if opportunities are available
            # (Assuming opportunity service analyzes compliance data)
            response = await client.get(
                f"{OPPORTUNITY_URL}/opportunities/arbitrage?framework=NERC_CIP",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            
            assert response.status_code == 200
            opportunities = response.json()
            assert "items" in opportunities


class TestGraphToOpportunityFlow:
    """Test graph analytics feeding opportunity detection"""
    
    @pytest.mark.asyncio
    async def test_framework_mapping_to_arbitrage(self, auth_token):
        """Graph relationships should inform arbitrage opportunities"""
        async with httpx.AsyncClient() as client:
            # Get framework relationships from Graph service
            response = await client.get(
                f"{GRAPH_URL}/graph/frameworks/SOC2/relationships",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            
            assert response.status_code == 200
            relationships = response.json()
            assert "related_frameworks" in relationships
            
            # Use those relationships to find arbitrage
            for related in relationships["related_frameworks"][:1]:
                framework_id = related["framework_id"]
                
                response = await client.get(
                    f"{OPPORTUNITY_URL}/opportunities/arbitrage",
                    params={
                        "framework_from": "SOC2",
                        "framework_to": framework_id
                    },
                    headers={"Authorization": f"Bearer {auth_token}"}
                )
                
                assert response.status_code == 200
                arbitrage = response.json()
                assert "items" in arbitrage


class TestMultiTenantIsolation:
    """Test tenant data isolation across services"""
    
    @pytest.mark.asyncio
    async def test_tenant_data_isolation(self):
        """Ensure tenants can't access each other's data"""
        async with httpx.AsyncClient() as client:
            # Login as tenant A
            response = await client.post(
                f"{ADMIN_URL}/auth/login",
                json={"email": "tenant-a@test.com", "password": "testpass"}
            )
            token_a = response.json()["access_token"]
            
            # Create snapshot as tenant A
            response = await client.post(
                f"{ENERGY_URL}/energy/snapshots",
                json={"substation_id": "TENANT-A-001"},
                headers={"Authorization": f"Bearer {token_a}"}
            )
            snapshot_a_id = response.json()["snapshot_id"]
            
            # Login as tenant B
            response = await client.post(
                f"{ADMIN_URL}/auth/login",
                json={"email": "tenant-b@test.com", "password": "testpass"}
            )
            token_b = response.json()["access_token"]
            
            # Try to access tenant A's snapshot as tenant B
            response = await client.get(
                f"{ENERGY_URL}/energy/snapshots/{snapshot_a_id}",
                headers={"Authorization": f"Bearer {token_b}"}
            )
            
            # Should be 404 (not found) or 403 (forbidden)
            assert response.status_code in [403, 404]


class TestEndToEndUserJourney:
    """Test complete user journey across all services"""
    
    @pytest.mark.asyncio
    async def test_complete_compliance_workflow(self, auth_token):
        """
        Complete workflow:
        1. Login (Admin)
        2. Create snapshot (Energy)
        3. Detect mismatches (Energy)
        4. Find opportunities (Opportunity + Graph)
        5. Review and approve (Admin)
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. Verify auth (already done via fixture)
            assert auth_token
            
            # 2. Create snapshot
            snapshot_response = await client.post(
                f"{ENERGY_URL}/energy/snapshots",
                json={
                    "substation_id": "E2E-001",
                    "compliance_data": {"cip_013": {"patch_management": False}}
                },
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert snapshot_response.status_code == 201
            snapshot_id = snapshot_response.json()["snapshot_id"]
            
            # 3. Check for mismatches
            mismatches_response = await client.get(
                f"{ENERGY_URL}/energy/snapshots/{snapshot_id}/mismatches",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert mismatches_response.status_code == 200
            
            # 4. Find compliance gaps (opportunities)
            gaps_response = await client.get(
                f"{OPPORTUNITY_URL}/opportunities/gaps?framework=NERC_CIP",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert gaps_response.status_code == 200
            
            # 5. Check review queue (if applicable)
            review_response = await client.get(
                f"{ADMIN_URL}/v1/review-queue",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert review_response.status_code in [200, 404]  # May not have review items


class TestPerformanceUnderLoad:
    """Test service performance with multiple concurrent requests"""
    
    @pytest.mark.asyncio
    async def test_concurrent_snapshot_creation(self, auth_token):
        """Create multiple snapshots concurrently"""
        import asyncio
        
        async def create_snapshot(index):
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{ENERGY_URL}/energy/snapshots",
                    json={"substation_id": f"LOAD-{index:03d}"},
                    headers={"Authorization": f"Bearer {auth_token}"}
                )
                return response.status_code
        
        # Create 10 snapshots concurrently
        tasks = [create_snapshot(i) for i in range(10)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed
        assert all(status == 201 for status in results)


# Run tests with: pytest tests/integration/ -v
