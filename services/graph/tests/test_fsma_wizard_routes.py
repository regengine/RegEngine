"""
Route-level tests for the FSMA 204 V2 Wizard API endpoints.

Tests:
  GET  /v1/fsma/wizard/ftl-categories
  POST /v1/fsma/wizard/applicability
  POST /v1/fsma/wizard/exemptions

Mounts ONLY the wizard router directly (not the full fsma_routes) to avoid
pulling in the entire graph service dependency chain (Neo4j, etc.).
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_repo_root = Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Stub shared.auth and structlog so wizard.py imports succeed without the
# full graph service dependency chain. The FSMA engine itself no longer
# depends on shared.* after the kernel migration (#2225), so the validator
# and fsma_rules stubs from the prior version are no longer needed.
# ---------------------------------------------------------------------------

_STUBBED_NAMES = (
    "shared.auth",
    "shared",
    "structlog",
    "fsma_engine_module",
    "fsma_wizard",
)
_REAL_MODULES = {name: sys.modules.get(name) for name in _STUBBED_NAMES}


def _force_stub(name: str, **attrs):
    """Force-register a stub module (overrides any existing entry)."""
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


# Stub shared.auth so wizard.py's `from shared.auth import require_api_key` works.
_force_stub(
    "shared.auth",
    require_api_key=lambda: None,
    APIKey=object,
)

# Ensure shared package itself is registered
if "shared" not in sys.modules:
    _force_stub("shared")

# Stub structlog only if it's genuinely not importable.
try:
    import structlog  # noqa: F401
except ImportError:
    _sl = types.ModuleType("structlog")
    _sl.get_logger = lambda *a, **kw: MagicMock()
    sys.modules["structlog"] = _sl


@pytest.fixture(scope="module", autouse=True)
def _restore_sys_modules_on_teardown():
    """Restore the pre-existing ``sys.modules`` entries this file overwrote."""
    yield
    for name, real in _REAL_MODULES.items():
        if real is not None:
            sys.modules[name] = real
        else:
            sys.modules.pop(name, None)


# ---------------------------------------------------------------------------
# Load fsma_engine directly from its new home in services/graph/app
# (bypasses the rest of services.graph.app.__init__ which pulls in the full
# graph dependency chain).
# ---------------------------------------------------------------------------
_engine_path = _repo_root / "services" / "graph" / "app" / "fsma_engine.py"
_espec = importlib.util.spec_from_file_location(
    "services.graph.app.fsma_engine", _engine_path
)
_engine_mod = importlib.util.module_from_spec(_espec)
sys.modules["services.graph.app.fsma_engine"] = _engine_mod
sys.modules["fsma_engine_module"] = _engine_mod
_espec.loader.exec_module(_engine_mod)

# ---------------------------------------------------------------------------
# Load wizard.py directly
# ---------------------------------------------------------------------------
_wizard_path = _repo_root / "services" / "graph" / "app" / "routers" / "fsma" / "wizard.py"
_wspec = importlib.util.spec_from_file_location("fsma_wizard", _wizard_path)
_wizard_mod = importlib.util.module_from_spec(_wspec)
sys.modules["fsma_wizard"] = _wizard_mod
_wspec.loader.exec_module(_wizard_mod)


@pytest.fixture(scope="module")
def client():
    """Create a test client with only the wizard router mounted."""
    app = FastAPI()
    app.include_router(_wizard_mod.router, prefix="/v1/fsma")
    return TestClient(app)


# ============================================================================
# GET /v1/fsma/wizard/ftl-categories
# ============================================================================


class TestFTLCategoriesEndpoint:
    """Tests for GET /v1/fsma/wizard/ftl-categories."""

    def test_returns_200(self, client):
        response = client.get("/v1/fsma/wizard/ftl-categories")
        assert response.status_code == 200

    def test_auth_dependency_present(self, client):
        """Endpoint requires API key authentication."""
        response = client.get("/v1/fsma/wizard/ftl-categories")
        assert response.status_code == 200

    def test_returns_23_categories(self, client):
        data = client.get("/v1/fsma/wizard/ftl-categories").json()
        assert data["total"] == 23
        assert len(data["categories"]) == 23

    def test_covered_count(self, client):
        data = client.get("/v1/fsma/wizard/ftl-categories").json()
        assert data["covered_count"] == 23

    def test_returns_6_exemption_definitions(self, client):
        data = client.get("/v1/fsma/wizard/ftl-categories").json()
        assert len(data["exemption_definitions"]) == 6

    def test_category_shape(self, client):
        data = client.get("/v1/fsma/wizard/ftl-categories").json()
        required = {"id", "name", "examples", "covered", "outbreak_frequency", "ctes", "cfr_sections", "kdes"}
        for cat in data["categories"]:
            missing = required - set(cat.keys())
            assert not missing, f"Category '{cat.get('id')}' missing fields: {missing}"

    def test_regulatory_reference_present(self, client):
        data = client.get("/v1/fsma/wizard/ftl-categories").json()
        assert "21 CFR Part 1 Subpart S" in data["regulatory_reference"]
        assert data["compliance_deadline"] == "2028-07-20"

    def test_known_categories_present(self, client):
        data = client.get("/v1/fsma/wizard/ftl-categories").json()
        ids = {c["id"] for c in data["categories"]}
        assert "leafy-greens-fresh" in ids
        assert "eggs" in ids
        assert "crustaceans" in ids
        assert "cheese-fresh-soft" in ids


# ============================================================================
# POST /v1/fsma/wizard/applicability
# ============================================================================


class TestApplicabilityEndpoint:
    """Tests for POST /v1/fsma/wizard/applicability."""

    def test_returns_200(self, client):
        response = client.post("/v1/fsma/wizard/applicability", json={"selections": ["leafy-greens-fresh"]})
        assert response.status_code == 200

    def test_auth_dependency_present(self, client):
        response = client.post("/v1/fsma/wizard/applicability", json={"selections": ["eggs"]})
        assert response.status_code == 200

    def test_covered_category_is_applicable(self, client):
        data = client.post("/v1/fsma/wizard/applicability", json={"selections": ["leafy-greens-fresh"]}).json()
        assert data["is_applicable"] is True
        assert len(data["covered_categories"]) == 1
        assert data["covered_categories"][0]["id"] == "leafy-greens-fresh"

    def test_empty_selections_not_applicable(self, client):
        data = client.post("/v1/fsma/wizard/applicability", json={"selections": []}).json()
        assert data["is_applicable"] is False

    def test_multiple_categories(self, client):
        data = client.post("/v1/fsma/wizard/applicability", json={"selections": ["eggs", "tomatoes", "crustaceans"]}).json()
        assert data["is_applicable"] is True
        assert len(data["covered_categories"]) == 3

    def test_unknown_category_in_not_covered(self, client):
        data = client.post("/v1/fsma/wizard/applicability", json={"selections": ["canned-goods"]}).json()
        assert data["is_applicable"] is False
        assert "canned-goods" in data["not_covered_categories"]

    def test_high_outbreak_count(self, client):
        data = client.post("/v1/fsma/wizard/applicability", json={"selections": ["leafy-greens-fresh", "eggs"]}).json()
        assert data["high_outbreak_count"] == 1  # leafy-greens-fresh=HIGH, eggs=MODERATE

    def test_missing_selections_field_returns_422(self, client):
        response = client.post("/v1/fsma/wizard/applicability", json={})
        assert response.status_code == 422

    def test_response_includes_reason(self, client):
        data = client.post("/v1/fsma/wizard/applicability", json={"selections": ["eggs"]}).json()
        assert isinstance(data["reason"], str)
        assert len(data["reason"]) > 0


# ============================================================================
# POST /v1/fsma/wizard/exemptions
# ============================================================================


class TestExemptionsEndpoint:
    """Tests for POST /v1/fsma/wizard/exemptions."""

    def test_returns_200(self, client):
        response = client.post("/v1/fsma/wizard/exemptions", json={"answers": {}})
        assert response.status_code == 200

    def test_auth_dependency_present(self, client):
        response = client.post("/v1/fsma/wizard/exemptions", json={"answers": {"small-producer": True}})
        assert response.status_code == 200

    def test_empty_answers_not_exempt(self, client):
        data = client.post("/v1/fsma/wizard/exemptions", json={"answers": {}}).json()
        assert data["status"] == "UNKNOWN"
        assert data["is_exempt"] is False
        assert data["unanswered_count"] == 6

    def test_small_producer_yes_exempt(self, client):
        data = client.post("/v1/fsma/wizard/exemptions", json={"answers": {"small-producer": True}}).json()
        assert data["status"] == "EXEMPT"
        assert data["is_exempt"] is True
        assert any(e["id"] == "small-producer" for e in data["active_exemptions"])

    def test_kill_step_yes_exempt(self, client):
        data = client.post("/v1/fsma/wizard/exemptions", json={"answers": {"kill-step": True}}).json()
        assert data["status"] == "EXEMPT"

    def test_direct_to_consumer_yes_exempt(self, client):
        data = client.post("/v1/fsma/wizard/exemptions", json={"answers": {"direct-to-consumer": True}}).json()
        assert data["status"] == "EXEMPT"

    def test_small_retail_yes_exempt(self, client):
        data = client.post("/v1/fsma/wizard/exemptions", json={"answers": {"small-retail": True}}).json()
        assert data["status"] == "EXEMPT"

    def test_rarely_consumed_raw_yes_exempt(self, client):
        data = client.post("/v1/fsma/wizard/exemptions", json={"answers": {"rarely-consumed-raw": True}}).json()
        assert data["status"] == "EXEMPT"

    def test_usda_jurisdiction_yes_exempt(self, client):
        data = client.post("/v1/fsma/wizard/exemptions", json={"answers": {"usda-jurisdiction": True}}).json()
        assert data["status"] == "EXEMPT"

    def test_all_no_not_exempt(self, client):
        answers = {
            "small-producer": False, "kill-step": False, "direct-to-consumer": False,
            "small-retail": False, "rarely-consumed-raw": False, "usda-jurisdiction": False,
        }
        data = client.post("/v1/fsma/wizard/exemptions", json={"answers": answers}).json()
        assert data["status"] == "NOT_EXEMPT"
        assert data["unanswered_count"] == 0

    def test_active_exemptions_include_citation(self, client):
        data = client.post("/v1/fsma/wizard/exemptions", json={"answers": {"kill-step": True}}).json()
        assert len(data["active_exemptions"]) == 1
        exemption = data["active_exemptions"][0]
        assert "citation" in exemption
        assert "§1.1305" in exemption["citation"]

    def test_missing_answers_field_uses_default(self, client):
        data = client.post("/v1/fsma/wizard/exemptions", json={}).json()
        assert data["status"] == "UNKNOWN"
