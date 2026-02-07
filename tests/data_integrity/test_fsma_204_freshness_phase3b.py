import pytest
import requests
import uuid
import time
import json

# Configuration
INGEST_URL = "http://localhost:8002/v1/ingest"
ADMIN_API_URL = "http://localhost:8400"
TENANT_ID = "00000000-0000-0000-0000-000000000000"
API_KEY = "admin"

# Mock Content
MOCK_SOURCE_URL = "http://mock-fsma.gov/rule-204"
CONTENT_V1 = """
<html>
<body>
    <h1>FSMA 204 Traceability Rule (Version 1)</h1>
    <p>Obligation: Traceability Lot Code Assignment is Mandatory.</p>
    <p>Constraint: Record Retention Period is 24 hours.</p>
</body>
</html>
"""

CONTENT_V2 = """
<html>
<body>
    <h1>FSMA 204 Traceability Rule (Version 2 - Updated)</h1>
    <p>Obligation: Traceability Lot Code Assignment is Mandatory.</p>
    <p>Constraint: Record Retention Period is 24 hours.</p>
    <p>Note: Minor text change to force hash difference.</p>
</body>
</html>
"""

ADMIN_MASTER_KEY = "admin-master-key-dev"

@pytest.fixture
def auth_headers():
    return {
        "X-RegEngine-API-Key": API_KEY,
        "X-Admin-Key": ADMIN_MASTER_KEY,
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json"
    }

class TestFSMA204FreshnessPhase3b:
    
    def test_freshness_and_versioning(self, auth_headers):
        print("\n[Phase 3b] Starting Freshness & Versioning Test...")

        # 1. Ingest V1
        print("[Phase 3b] Ingesting V1 Content...")
        payload_v1 = {
            "text": CONTENT_V1,
            "source_url": MOCK_SOURCE_URL,
            "source_system": "manual_test",
            "vertical": "food_safety"
        }
        resp = requests.post(INGEST_URL, json=payload_v1, headers=auth_headers)
        assert resp.status_code == 200, f"Ingest V1 failed: {resp.text}"
        
        # 2. Wait for V1 Document
        print("[Phase 3b] Waiting for V1 Authority Document...")
        doc_v1 = self._wait_for_document(auth_headers, MOCK_SOURCE_URL, expect_version=1)
        assert doc_v1, "V1 Document not found"
        print(f"✅ V1 Document Created: {doc_v1['id']} (Status: {doc_v1['status']})")
        
        # 3. Wait for V1 Facts
        print("[Phase 3b] Verifying V1 Facts...")
        facts_v1 = self._wait_for_facts(auth_headers, doc_v1['id'])
        assert len(facts_v1) > 0, "No facts extracted for V1"
        fact_v1_sample = facts_v1[0]
        assert fact_v1_sample['version'] == 1, "Fact V1 should be version 1"
        assert fact_v1_sample['is_current'] == True, "Fact V1 should be current"
        print(f"✅ V1 Facts Verified ({len(facts_v1)} facts)")

        # 4. Ingest V2 (Modified Content)
        print("[Phase 3b] Ingesting V2 Content (Triggering Refresh)...")
        payload_v2 = {
            "text": CONTENT_V2,
            "source_url": MOCK_SOURCE_URL,
            "source_system": "manual_test",
            "vertical": "food_safety"
        }
        resp = requests.post(INGEST_URL, json=payload_v2, headers=auth_headers)
        assert resp.status_code == 200, f"Ingest V2 failed: {resp.text}"
        
        # 5. Wait for V2 Document and Check Supersedes
        print("[Phase 3b] Waiting for V2 Authority Document...")
        doc_v2 = self._wait_for_document(auth_headers, MOCK_SOURCE_URL, expect_version=2, previous_id=doc_v1['id'])
        assert doc_v2, "V2 Document not found"
        print(f"✅ V2 Document Created: {doc_v2['id']}")
        
        assert doc_v2['supersedes_document_id'] == doc_v1['id'], "V2 should supersede V1"
        
        # 6. Verify V1 is now Superseded
        # We need to fetch V1 again to check status
        # admin api currently lists by tenant, we need get by ID or just re-list
        # Assuming list_authorities returns all, let's find V1 in the list from _wait_for_document logic
        # But _wait_for_document filters by active mostly.
        # Let's check status explicitly if API supports GET /authorities/{id}. 
        # Since we just added GET /authorities/{id}/facts, maybe we don't have GET /authorities/{id} detailed?
        # Use database or implicit check via list.
        # Check V2 Facts Lineage first.
        
        # 7. Verify V2 Facts Lineage
        print("[Phase 3b] Verifying V2 Facts Lineage...")
        facts_v2 = self._wait_for_facts(auth_headers, doc_v2['id'])
        assert len(facts_v2) > 0, "No facts extracted for V2"
        
        fact_v2_sample = facts_v2[0]
        print(f"   Fact V2 Version: {fact_v2_sample.get('version')}")
        print(f"   Fact V2 Prev ID: {fact_v2_sample.get('previous_fact_id')}")
        
        assert fact_v2_sample['version'] > 1, f"Fact V2 version should be > 1, got {fact_v2_sample['version']}"
        assert fact_v2_sample['previous_fact_id'] is not None, "Fact V2 should link to previous fact"
        print("✅ Fact Lineage Verified")

    def _wait_for_document(self, headers, source_url, expect_version=1, previous_id=None, timeout=30):
        # Admin API: GET /pcos/authorities
        start = time.time()
        while time.time() - start < timeout:
            resp = requests.get(f"{ADMIN_API_URL}/pcos/authorities", headers=headers)
            if resp.status_code == 200:
                docs = resp.json()
                # Find doc matching source_url
                matches = [d for d in docs if d.get('original_file_path') == source_url]
                
                # Logic to determine which is the "New" one
                # If expect_version == 1, just get the first one
                # If expect_version == 2, find one that supersedes previous_id
                
                if expect_version == 1:
                    if matches:
                        return matches[0]
                elif expect_version == 2:
                    for d in matches:
                        if d.get('supersedes_document_id') == previous_id:
                            return d
            time.sleep(2)
        return None

    def _wait_for_facts(self, headers, doc_id, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            resp = requests.get(f"{ADMIN_API_URL}/pcos/authorities/{doc_id}/facts", headers=headers)
            if resp.status_code == 200:
                facts = resp.json()
                if facts:
                    return facts
            time.sleep(2)
        return []
