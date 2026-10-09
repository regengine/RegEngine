import os
import time
import uuid
from typing import Any, Dict, List

import pytest
import requests

# Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8400")
INGEST_SERVICE_URL = os.getenv("INGEST_SERVICE_URL", "http://localhost:8002")

# Test Data
TENANT_ID = "11111111-1111-1111-1111-111111111111"
# No default: the caller must provide a test-only key via the environment.
# This keeps even test credentials out of source control.
API_KEY = os.getenv("REGENGINE_TEST_API_KEY")

# Explicit opt-in gate for the live external FDA fetch below. The test
# skips unless the operator sets REGENGINE_ALLOW_LIVE_FDA_FETCH=1.
LIVE_FDA_FETCH_ENABLED = os.getenv("REGENGINE_ALLOW_LIVE_FDA_FETCH", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

FDA_RULE_URL = (
    "https://www.fda.gov/food/food-safety-modernization-act-fsma/"
    "fsma-final-rule-requirements-additional-traceability-records-certain-foods"
)


def _auth_headers(api_key: str) -> Dict[str, str]:
    return {
        "X-RegEngine-API-Key": api_key,
        "X-Tenant-ID": TENANT_ID,
        "Content-Type": "application/json",
    }


def _service_available(base_url: str) -> bool:
    try:
        response = requests.get(f"{base_url}/health", timeout=2)
        return response.status_code < 500
    except requests.RequestException:
        return False


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
        api_key = os.getenv("REGENGINE_TEST_API_KEY")
        if not api_key:
            pytest.skip("REGENGINE_TEST_API_KEY is not set; refusing to use a default key")
        live_enabled = os.getenv("REGENGINE_ALLOW_LIVE_FDA_FETCH", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not live_enabled:
            pytest.skip("live FDA fetch not enabled; set REGENGINE_ALLOW_LIVE_FDA_FETCH=1 to opt in")
        headers = _auth_headers(api_key)
        if not _service_available(INGEST_SERVICE_URL):
            pytest.skip("ingestion service not running")
        if not _service_available(API_BASE_URL):
            pytest.skip("admin service not running")

        # 1. Trigger Ingestion (Idempotent: will return existing if handled, or update)
        payload = {
            "url": FDA_RULE_URL,
            "source_system": "fda",
            "document_type": "regulation",
        }

        print(f"\n[Phase 3a] Ensuring Document Ingestion...")
        response = requests.post(f"{INGEST_SERVICE_URL}/v1/ingest/url", json=payload, headers=headers)
        assert response.status_code in [200, 202], f"Ingestion failed: {response.text}"

        # 2. Find Authority Document
        found_authority = None
        # We need to reuse the polling logic or assume it exists from Phase 2b
        print("[Phase 3a] Locating Authority Document...")
        auth_resp = requests.get(f"{API_BASE_URL}/pcos/authorities", headers=headers)
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
            facts_resp = requests.get(f"{API_BASE_URL}/pcos/authorities/{found_authority['id']}/facts", headers=headers)
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
            "24 hours",  # Retention/turnaround time
            "Key Data Elements",
            "Critical Tracking Events",
        ]

        print(f"[Phase 3a] Verifying {len(found_facts)} facts against {len(expected_terms)} expected terms...")

        matched_terms = []
        for term in expected_terms:
            # Check if any fact contains this term in name, description, or value
            match = next(
                (
                    f
                    for f in found_facts
                    if term.lower() in str(f.get("fact_name", "")).lower()
                    or term.lower() in str(f.get("fact_description", "")).lower()
                    or term.lower() in str(f.get("value", "")).lower()
                ),
                None,
            )
            if match:
                matched_terms.append(term)
                print(f"✅ Found term '{term}' in fact: {match.get('fact_name')}")
            else:
                print(f"❌ Missing term '{term}'")

        # Assertion: We want at least SOME facts to match to prove extraction logic works
        assert len(matched_terms) == len(expected_terms), (
            f"Missing critical facts: {set(expected_terms) - set(matched_terms)}"
        )
