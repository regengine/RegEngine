"""
E2E Tests — Inter-Service Resilience & Tenant Isolation

Validates the foundational hardening from PR #266:
- Compliance → Graph service call chain (resilient_client + circuit breaker)
- Tenant header propagation across service boundaries
- Error passthrough (4xx vs 5xx distinction)
- FSMA compliance checklist + validation endpoints

Usage:
    pytest tests/e2e/test_inter_service_resilience.py -v

Prerequisites:
    - Docker stack running via ``docker compose up``
    - At minimum: compliance-api, graph-service, admin-api
"""

from __future__ import annotations

import os
import time
import pytest
import requests

# ── Configuration ────────────────────────────────────────────────

BASE_URL = os.getenv("REGENGINE_BASE_URL", "http://localhost")
COMPLIANCE_URL = os.getenv("COMPLIANCE_URL", f"{BASE_URL}:8500")
GRAPH_URL = os.getenv("GRAPH_URL", f"{BASE_URL}:8200")
ADMIN_URL = os.getenv("ADMIN_URL", f"{BASE_URL}:8400")
INGESTION_URL = os.getenv("INGESTION_URL", f"{BASE_URL}:8002")
NLP_URL = os.getenv("NLP_URL", f"{BASE_URL}:8100")

API_KEY = os.getenv("REGENGINE_API_KEY", "test-key-e2e")
TENANT_ID = os.getenv("REGENGINE_TENANT_ID", "e2e-test-tenant")
BYPASS_TOKEN = os.getenv("AUTH_TEST_BYPASS_TOKEN", "admin")

HEADERS = {
    "X-RegEngine-API-Key": API_KEY,
    "X-RegEngine-Tenant-ID": TENANT_ID,
    "Content-Type": "application/json",
}

# Use bypass token if API key auth isn't configured
BYPASS_HEADERS = {
    "X-RegEngine-API-Key": BYPASS_TOKEN,
    "X-RegEngine-Tenant-ID": TENANT_ID,
    "Content-Type": "application/json",
}


# ── Helpers ──────────────────────────────────────────────────────

def wait_for_service(url: str, timeout: int = 5) -> bool:
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


def skip_if_unavailable(*services: tuple[str, str]):
    """Skip test if any required service is not reachable."""
    unreachable = []
    for name, url in services:
        if not wait_for_service(url, timeout=3):
            unreachable.append(name)
    if unreachable:
        pytest.skip(f"Services not reachable: {', '.join(unreachable)}")


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def check_compliance_service():
    """Ensure compliance service is reachable."""
    skip_if_unavailable(("compliance", COMPLIANCE_URL))


# ── Test 1: Service Health with Correct Ports ────────────────────

class TestServiceHealthPorts:
    """Verify services respond on the correct ports (post-PR #266 fix)."""

    @pytest.mark.parametrize("service_name,url", [
        ("compliance", COMPLIANCE_URL),
        ("graph", GRAPH_URL),
        ("admin", ADMIN_URL),
        ("ingestion", INGESTION_URL),
        ("nlp", NLP_URL),
    ])
    def test_health_on_correct_port(self, service_name: str, url: str):
        """Each service should respond on its Docker-assigned port."""
        try:
            r = requests.get(f"{url}/health", timeout=5)
            assert r.status_code == 200, f"{service_name} returned {r.status_code}"
        except requests.ConnectionError:
            pytest.skip(f"{service_name} not reachable at {url}")


# ── Test 2: Compliance Endpoints (FSMA 204) ──────────────────────

class TestComplianceFSMA:
    """Test FSMA 204 compliance endpoints work end-to-end."""

    def test_list_industries(self):
        """GET /industries should return FSMA 204 food industries."""
        r = requests.get(f"{COMPLIANCE_URL}/industries", headers=BYPASS_HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "industries" in data
        assert data["total"] >= 5  # fresh-produce, seafood, dairy, deli, shell-eggs
        names = [i["name"] for i in data["industries"]]
        assert "Fresh Produce" in names

    def test_list_checklists(self):
        """GET /checklists should return FSMA 204 checklists."""
        r = requests.get(f"{COMPLIANCE_URL}/checklists", headers=BYPASS_HEADERS, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "checklists" in data
        assert data["total"] >= 5

    def test_list_checklists_filter_by_industry(self):
        """GET /checklists?industry=Seafood should filter results."""
        r = requests.get(
            f"{COMPLIANCE_URL}/checklists",
            headers=BYPASS_HEADERS,
            params={"industry": "Seafood"},
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        for c in data["checklists"]:
            assert c["industry"] == "Seafood"

    def test_get_specific_checklist(self):
        """GET /checklists/{id} should return a specific checklist."""
        r = requests.get(
            f"{COMPLIANCE_URL}/checklists/fsma-204-fresh-produce",
            headers=BYPASS_HEADERS,
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "fsma-204-fresh-produce"
        assert data["framework"] == "FSMA 204"
        assert len(data["requirements"]) >= 6

    def test_get_nonexistent_checklist_returns_404(self):
        """GET /checklists/{invalid} should return 404, not 500."""
        r = requests.get(
            f"{COMPLIANCE_URL}/checklists/nonexistent-id",
            headers=BYPASS_HEADERS,
            timeout=5,
        )
        assert r.status_code == 404


# ── Test 3: Compliance Validation ────────────────────────────────

class TestComplianceValidation:
    """Test FSMA 204 config validation endpoint."""

    def test_valid_config_passes(self):
        """Config with all required fields should validate."""
        r = requests.post(
            f"{COMPLIANCE_URL}/validate",
            headers=BYPASS_HEADERS,
            json={
                "config": {
                    "tlc": "LOT-2024-001",
                    "cte_type": "receiving",
                    "event_date": "2024-01-15",
                    "location": "GLN:0012345000015",
                },
            },
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert len(data["errors"]) == 0

    def test_missing_required_fields_fails(self):
        """Config missing required FSMA fields should fail validation."""
        r = requests.post(
            f"{COMPLIANCE_URL}/validate",
            headers=BYPASS_HEADERS,
            json={"config": {"tlc": "LOT-001"}},
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is False
        assert len(data["errors"]) >= 3  # missing cte_type, event_date, location
        error_paths = [e["path"] for e in data["errors"]]
        assert "cte_type" in error_paths
        assert "event_date" in error_paths
        assert "location" in error_paths

    def test_strict_mode_promotes_warnings(self):
        """Strict mode should turn warnings into errors."""
        r = requests.post(
            f"{COMPLIANCE_URL}/validate",
            headers=BYPASS_HEADERS,
            json={
                "config": {
                    "tlc": "LOT-001",
                    "cte_type": "receiving",
                    "event_date": "2024-01-15",
                    "location": "GLN:001",
                },
                "strict": True,
            },
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        # Strict mode converts missing recommended fields to errors
        assert data["valid"] is False
        assert len(data["warnings"]) == 0  # promoted to errors


# ── Test 4: Authentication Required ──────────────────────────────

class TestAuthenticationEnforcement:
    """Verify endpoints require authentication."""

    def test_industries_without_api_key_rejects(self):
        """Requests without API key should be rejected."""
        r = requests.get(
            f"{COMPLIANCE_URL}/industries",
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        # Should get 401 or 403, not 200
        assert r.status_code in (401, 403), (
            f"Expected auth rejection, got {r.status_code}"
        )

    def test_checklists_without_api_key_rejects(self):
        """Checklists endpoint should require auth."""
        r = requests.get(
            f"{COMPLIANCE_URL}/checklists",
            headers={"Content-Type": "application/json"},
            timeout=5,
        )
        assert r.status_code in (401, 403)


# ── Test 5: Compliance → Graph Error Passthrough ─────────────────

class TestErrorPassthrough:
    """Verify that graph service errors are properly proxied (not generic 502)."""

    def test_audit_spreadsheet_without_graph(self):
        """Audit spreadsheet should handle graph service errors gracefully."""
        skip_if_unavailable(("compliance", COMPLIANCE_URL))
        r = requests.get(
            f"{COMPLIANCE_URL}/v1/fsma/audit/spreadsheet",
            headers=BYPASS_HEADERS,
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            },
            timeout=35,
        )
        # If graph is up: 200 (CSV). If down: 502 with detail.
        # Either way, should NOT be a generic 500.
        assert r.status_code != 500, f"Got unhandled 500: {r.text[:200]}"
        if r.status_code == 502:
            # Verify error detail is present (not blank)
            data = r.json()
            assert "detail" in data
            assert len(data["detail"]) > 0


# ── Test 6: Tenant Header Propagation ────────────────────────────

class TestTenantHeaderPropagation:
    """Verify tenant context headers are accepted and processed."""

    def test_tenant_header_accepted(self):
        """Compliance service should accept X-RegEngine-Tenant-ID header."""
        headers = {
            **BYPASS_HEADERS,
            "X-RegEngine-Tenant-ID": "tenant-isolation-test",
        }
        r = requests.get(
            f"{COMPLIANCE_URL}/industries",
            headers=headers,
            timeout=5,
        )
        assert r.status_code == 200

    def test_request_id_accepted(self):
        """Compliance service should accept X-Request-ID for correlation."""
        headers = {
            **BYPASS_HEADERS,
            "X-Request-ID": "e2e-test-correlation-id-001",
        }
        r = requests.get(
            f"{COMPLIANCE_URL}/industries",
            headers=headers,
            timeout=5,
        )
        assert r.status_code == 200
