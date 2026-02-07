import pytest
import requests
import time
import os
import uuid
from typing import Dict, Any, List

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8400")
INGEST_SERVICE_URL = os.getenv("INGEST_SERVICE_URL", "http://localhost:8002")
ADMIN_MASTER_KEY = os.getenv("ADMIN_MASTER_KEY", "admin-master-key-dev")

# Test Data
TENANT_ID = "11111111-1111-1111-1111-111111111111"
API_KEY = "rge_phase2b.testsecret123"

HEADERS = {
    "X-RegEngine-API-Key": API_KEY,
    "X-Admin-Key": ADMIN_MASTER_KEY,
    "X-Tenant-ID": TENANT_ID,
    "Content-Type": "application/json"
}

class TestFSMA204ExtractionPhase3a:
    """
    Phase 3a: Fact Extraction Verification.
    
    Verifies that the system extracts specific "Key Data Elements" (KDEs)
    and "Critical Tracking Events" (CTEs) from the FSMA 204 Golden Corpus.
    """
    
    def test_fact_extraction_quality(self):
        """
        Verify presence of critical FSMA 204 obligations:
        1. Ingest FDA Rule (idempotent, effectively re-trigger or find existing)
        2. Poll for Facts
        3. Assert specific facts exist
        """
        
        # 1. Trigger Ingestion (Idempotent: will return existing if handled, or update)
        payload = {
            "url": "https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods",
            "source_system": "fda",
            "document_type": "regulation"
        }
        
        print(f"\n[Phase 3a] Ensuring Document Ingestion...")
        response = requests.post(f"{INGEST_SERVICE_URL}/v1/ingest/url", json=payload, headers=HEADERS)
        assert response.status_code in [200, 202], f"Ingestion failed: {response.text}"
        
        # 2. Find Authority Document
        found_authority = None
        # We need to reuse the polling logic or assume it exists from Phase 2b
        print("[Phase 3a] Locating Authority Document...")
        auth_resp = requests.get(f"{API_BASE_URL}/pcos/authorities", headers=HEADERS)
        if auth_resp.status_code == 200:
            authorities = auth_resp.json()
            found_authority = next((a for a in authorities if "FDA" in str(a.get("issuer_name", "")).upper()), None)
            
        assert found_authority, "Authority Document not found. Phase 2b must pass first."
        print(f"Found Authority: {found_authority['id']}")
        
        # 3. Poll for Facts
        # Logic: Worker might take a moment to extract facts after document creation
        print("[Phase 3a] Polling for Extracted Facts...")
        found_facts = []
        start_time = time.time()
        timeout = 30
        
        while time.time() - start_time < timeout:
            facts_resp = requests.get(f"{API_BASE_URL}/pcos/authorities/{found_authority['id']}/facts", headers=HEADERS)
            if facts_resp.status_code == 200:
                found_facts = facts_resp.json()
                if len(found_facts) > 0:
                    break
            time.sleep(2)
            
        if not found_facts:
            # If empty, we fail, but print helpful debug
            print("No facts found yet.")
            
        # 4. Assert Specific "Golden" Facts
        # These are the FSMA 204 "Must Haves"
        expected_terms = [
            "Traceability Lot Code",
            "24 hours", # Retention/turnaround time
            "Key Data Elements",
            "Critical Tracking Events"
        ]
        
        print(f"[Phase 3a] Verifying {len(found_facts)} facts against {len(expected_terms)} expected terms...")
        
        matched_terms = []
        for term in expected_terms:
            # Check if any fact contains this term in name, description, or value
            match = next((f for f in found_facts if 
                          term.lower() in str(f.get("fact_name", "")).lower() or 
                          term.lower() in str(f.get("fact_description", "")).lower() or
                          term.lower() in str(f.get("value", "")).lower()), None)
            if match:
                matched_terms.append(term)
                print(f"✅ Found term '{term}' in fact: {match.get('fact_name')}")
            else:
                print(f"❌ Missing term '{term}'")
                
        # Assertion: We want at least SOME facts to match to prove extraction logic works
        assert len(matched_terms) == len(expected_terms), f"Missing critical facts: {set(expected_terms) - set(matched_terms)}"
