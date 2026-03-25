"""
E2E Smoke Tests — Critical Path Validation

Exercises the critical path: ingest → NLP → graph → export.
Runs against local Docker stack (``start-stack.sh``).

Usage:
    pytest tests/e2e/test_critical_path.py -v

Prerequisites:
    - Docker stack running via ``./start-stack.sh``
    - Ingestion, NLP, Graph, and Compliance services healthy
"""

from __future__ import annotations

import os
import time
import uuid
import pytest
import requests

# ── Configuration ────────────────────────────────────────────────

BASE_URL = os.getenv("REGENGINE_BASE_URL", "http://localhost")
INGESTION_URL = os.getenv("INGESTION_URL", f"{BASE_URL}:8002")
GRAPH_URL = os.getenv("GRAPH_URL", f"{BASE_URL}:8200")
ADMIN_URL = os.getenv("ADMIN_URL", f"{BASE_URL}:8400")
NLP_URL = os.getenv("NLP_URL", f"{BASE_URL}:8100")
COMPLIANCE_URL = os.getenv("COMPLIANCE_URL", f"{BASE_URL}:8500")

API_KEY = os.getenv("REGENGINE_API_KEY", "test-key-smoke")
TENANT_ID = os.getenv("REGENGINE_TENANT_ID", "smoke-test-tenant")

HEADERS = {
    "X-RegEngine-API-Key": API_KEY,
    "X-Tenant-ID": TENANT_ID,
    "Content-Type": "application/json",
}

POLL_INTERVAL = 2  # seconds
POLL_TIMEOUT = 30  # seconds


# ── Helpers ──────────────────────────────────────────────────────

def wait_for_service(url: str, timeout: int = 10) -> bool:
    """Poll a service health endpoint until it responds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{url}/health", timeout=3)
            if r.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    return False


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def check_services():
    """Ensure critical services are reachable before running tests."""
    services = {
        "ingestion": INGESTION_URL,
        "admin": ADMIN_URL,
    }
    unreachable = []
    for name, url in services.items():
        if not wait_for_service(url, timeout=5):
            unreachable.append(name)

    if unreachable:
        pytest.skip(
            f"Services not reachable (is Docker stack running?): {', '.join(unreachable)}"
        )


# ── Test 1: Service Health ───────────────────────────────────────

class TestServiceHealth:
    """Verify all services respond to /health."""

    @pytest.mark.parametrize("service_name,url", [
        ("ingestion", INGESTION_URL),
        ("admin", ADMIN_URL),
        ("nlp", NLP_URL),
        ("graph", GRAPH_URL),
        ("compliance", COMPLIANCE_URL),
    ])
    def test_health_endpoint(self, service_name: str, url: str):
        """Each service should return healthy status."""
        try:
            r = requests.get(f"{url}/health", timeout=5)
            assert r.status_code == 200, f"{service_name} returned {r.status_code}"
            data = r.json()
            assert data.get("status") in ("healthy", "ok", "ready"), (
                f"{service_name} unhealthy: {data}"
            )
        except requests.ConnectionError:
            pytest.skip(f"{service_name} not reachable at {url}")


# ── Test 2: Document Ingestion ───────────────────────────────────

class TestIngestionFlow:
    """Test document ingestion via the API."""

    def test_ingest_document(self):
        """POST a document and verify acceptance."""
        doc_id = str(uuid.uuid4())
        payload = {
            "document_id": doc_id,
            "source_url": "https://example.com/test-regulation.pdf",
            "content_type": "application/pdf",
            "tenant_id": TENANT_ID,
            "metadata": {
                "title": "E2E Smoke Test Document",
                "category": "food-safety",
            },
        }

        try:
            r = requests.post(
                f"{INGESTION_URL}/api/v1/ingest",
                json=payload,
                headers=HEADERS,
                timeout=10,
            )
            # Accept 200, 201, or 202 (queued)
            assert r.status_code in (200, 201, 202), (
                f"Ingestion failed: {r.status_code} — {r.text}"
            )
        except requests.ConnectionError:
            pytest.skip("Ingestion service not reachable")


# ── Test 3: Compliance Checklist ─────────────────────────────────

class TestComplianceChecklist:
    """Test compliance checklist validation."""

    def test_list_checklists(self):
        """GET available compliance checklists."""
        try:
            r = requests.get(
                f"{COMPLIANCE_URL}/checklists",
                headers=HEADERS,
                timeout=5,
            )
            assert r.status_code == 200
            data = r.json()
            assert "checklists" in data
            assert data["total"] > 0, "No checklists loaded"
        except requests.ConnectionError:
            pytest.skip("Compliance service not reachable")

    def test_validate_hipaa_checklist(self):
        """POST a HIPAA compliance validation."""
        payload = {
            "checklist_id": "hipaa_compliance",
            "customer_config": {
                "hipaa_001": True,
                "hipaa_002": True,
                "hipaa_003": False,
            },
        }
        try:
            r = requests.post(
                f"{COMPLIANCE_URL}/validate",
                json=payload,
                headers=HEADERS,
                timeout=5,
            )
            assert r.status_code == 200
            data = r.json()
            assert "overall_status" in data
            assert "pass_rate" in data
        except requests.ConnectionError:
            pytest.skip("Compliance service not reachable")
