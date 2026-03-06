import pytest
import httpx
import os
from pathlib import Path

# Target the ingestion service running in Docker (map to 8002 locally)
BASE_URL = os.getenv("INGESTION_SERVICE_URL", "http://localhost:8002")
API_KEY = os.getenv("API_KEY", "") # Default is blank as seen in config

@pytest.mark.asyncio
async def test_compliance_golden_path():
    """
    E2E Test: 
    1. Upload Harvest CSV 
    2. Check Compliance Score
    3. Verify Chain Integrity
    """
    # Use a real UUID as expected by some middleware components
    tenant_id = "123e4567-e89b-12d3-a456-426614174000"
    headers = {
        "X-RegEngine-API-Key": "regengine-universal-test-key-2026",
        "X-RegEngine-Tenant-ID": tenant_id,
        "X-RegEngine-Internal-Secret": "trusted-internal-v1"
    }
    
    # 1. Upload FSMA 204 Harvest CSV
    csv_path = Path(__file__).parent / "data" / "fsma_harvest_sample.csv"
    with open(csv_path, "rb") as f:
        files = {"file": ("fsma_harvest.csv", f, "text/csv")}
        data = {
            "cte_type": "harvesting",
            "source": "e2e_integration_test",
            "tenant_id": tenant_id
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/v1/ingest/csv",
                data=data,
                files=files,
                headers=headers,
                timeout=30.0
            )
            
            assert response.status_code == 200, f"CSV upload failed: {response.text}"
            resp_json = response.json()
            assert resp_json["accepted"] > 0, "No rows were accepted"
            
            # Capture the last chain hash
            last_event = resp_json["events"][-1]
            last_chain_hash = last_event["chain_hash"]
            assert last_chain_hash is not None
            
            # 2. Fetch Compliance Score
            score_response = await client.get(
                f"{BASE_URL}/api/v1/compliance/score/{tenant_id}",
                headers=headers
            )
            
            assert score_response.status_code == 200, f"Score fetch failed: {score_response.text}"
            score_json = score_response.json()
            
            assert score_json["overall_score"] > 0, f"Score should be > 0 after ingestion. Got {score_json['overall_score']}"
            assert score_json["last_chain_hash"] == last_chain_hash, "Chain hash mismatch in score"
            assert len(score_json["next_actions"]) > 0, "Should have next actions"
            
            # 3. Verify Breakdown
            breakdown = score_json["breakdown"]
            assert "chain_integrity" in breakdown
            assert breakdown["chain_integrity"]["score"] == 100
            
            print(f"\n✅ E2E Compliance Path Verified for Tenant: {tenant_id}")
            print(f"✅ Final Chain Hash: {last_chain_hash}")
            print(f"✅ Overall Score: {score_json['overall_score']} (Grade: {score_json['grade']})")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_compliance_golden_path())
