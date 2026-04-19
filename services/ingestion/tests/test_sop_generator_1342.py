"""
Regression coverage for ``app/sop_generator.py``.

The SOP generator emits an FSMA 204 Traceability Plan as markdown —
it's customer-facing content used by small growers / co-packers to
pass their first FDA audit. Coverage has been at 46%. These tests
lock in:

* every branch of ``_generate_cte_procedures`` (company-type-specific
  sections, IoT-toggled lines)
* the ``/generate`` endpoint wiring (auth dep override, response
  shape, section list, page estimate)
* retailer-specific content (Walmart / Kroger / Costco — case-insensitive)
* integration section (ERP + IoT toggles)

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.sop_generator import (
    SOPRequest,
    SOPResponse,
    _generate_cte_procedures,
    generate_sop,
    router,
)
from app.webhook_compat import _verify_api_key


# ===========================================================================
# App fixture with auth bypass
# ===========================================================================


@pytest.fixture
def client():
    """Router-only app; no-op auth dep so tests don't depend on a key."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    with TestClient(app) as c:
        yield c


def _minimal_payload(**overrides):
    base = {
        "company_name": "Acme Produce",
        "company_type": "manufacturer",
        "products": ["Romaine Lettuce"],
        "facilities": ["Salinas, CA"],
        "primary_contact": "Jane Roe",
    }
    base.update(overrides)
    return base


# ===========================================================================
# _generate_cte_procedures — company-type-specific sections
# ===========================================================================


class TestGenerateCteProceduresByCompanyType:

    def test_grower_includes_harvesting_cooling(self):
        out = _generate_cte_procedures("grower", ["Tomatoes"], has_iot=False)
        assert "Harvesting CTE" in out
        assert "§1.1325(a)" in out
        assert "Cooling CTE" in out
        assert "§1.1325(b)" in out
        # Grower does NOT get transformation.
        assert "Transformation CTE" not in out

    def test_manufacturer_gets_harvest_cool_and_transformation(self):
        out = _generate_cte_procedures("manufacturer", ["Salsa"], has_iot=False)
        assert "Harvesting CTE" in out
        assert "Cooling CTE" in out
        assert "Transformation CTE" in out
        assert "§1.1350" in out

    def test_distributor_gets_flbr_not_harvest(self):
        out = _generate_cte_procedures("distributor", ["Leafy Greens"], has_iot=False)
        assert "First Land-Based Receiving CTE" in out
        assert "§1.1325(c)" in out
        # Distributor does NOT assign new TLCs at harvest.
        assert "Harvesting CTE" not in out
        assert "Transformation CTE" not in out

    def test_importer_gets_flbr_not_harvest(self):
        out = _generate_cte_procedures("importer", ["Mangoes"], has_iot=False)
        assert "First Land-Based Receiving CTE" in out
        # Importer does NOT assign new TLCs at harvest.
        assert "Harvesting CTE" not in out
        assert "Transformation CTE" not in out

    def test_retailer_gets_only_ship_and_receive(self):
        """Retailer has no harvest/cool/transform/FLBR — just ship/receive."""
        out = _generate_cte_procedures("retailer", ["Salad Mix"], has_iot=False)
        assert "Shipping CTE" in out
        assert "Receiving CTE" in out
        assert "Harvesting CTE" not in out
        assert "Cooling CTE" not in out
        assert "Transformation CTE" not in out
        assert "First Land-Based Receiving CTE" not in out

    def test_shipping_and_receiving_always_included(self):
        """Every company type gets ship/receive sections."""
        for company_type in ("grower", "manufacturer", "distributor", "importer", "retailer"):
            out = _generate_cte_procedures(company_type, ["P"], has_iot=False)
            assert "Shipping CTE" in out
            assert "Receiving CTE" in out


class TestGenerateCteProceduresIotToggle:

    def test_iot_on_cooling_mentions_sensitech(self):
        out = _generate_cte_procedures("manufacturer", ["Tomatoes"], has_iot=True)
        assert "Sensitech" in out or "IoT temperature logger" in out

    def test_iot_off_cooling_mentions_manual_temp(self):
        out = _generate_cte_procedures("manufacturer", ["Tomatoes"], has_iot=False)
        assert "manual temperature check" in out

    def test_iot_on_shipping_mentions_attach_logger(self):
        out = _generate_cte_procedures("manufacturer", ["P"], has_iot=True)
        assert "Attach IoT temperature logger" in out

    def test_iot_off_shipping_mentions_loading_dock_record(self):
        out = _generate_cte_procedures("manufacturer", ["P"], has_iot=False)
        assert "Record temperature at loading dock" in out

    def test_iot_on_receiving_mentions_download_log(self):
        out = _generate_cte_procedures("manufacturer", ["P"], has_iot=True)
        assert "Download IoT temperature log" in out

    def test_iot_off_receiving_mentions_receiving_dock_record(self):
        out = _generate_cte_procedures("manufacturer", ["P"], has_iot=False)
        assert "Record temperature at receiving dock" in out


class TestGenerateCteProceduresProductList:

    def test_first_five_products_listed(self):
        products = ["A", "B", "C", "D", "E", "F", "G"]
        out = _generate_cte_procedures("manufacturer", products, has_iot=False)
        # Only first 5 products are named in the CTE preamble.
        for p in ["A", "B", "C", "D", "E"]:
            assert p in out
        # 6th and 7th intentionally truncated.
        # (They may still appear in other places, but the 'Scope' line should
        # have only the first 5.)

    def test_empty_products_still_produces_shipping_section(self):
        """Even with 0 products, ship/receive sections still render."""
        out = _generate_cte_procedures("retailer", [], has_iot=False)
        assert "Shipping CTE" in out


# ===========================================================================
# /generate endpoint — minimal happy path
# ===========================================================================


class TestGenerateEndpointHappyPath:

    def test_minimal_request_returns_valid_sop(self, client):
        resp = client.post("/api/v1/sop/generate", json=_minimal_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["company_name"] == "Acme Produce"
        assert "FSMA 204 Traceability Plan" in body["document_title"]
        assert "Acme Produce" in body["markdown_content"]
        assert isinstance(body["sections"], list)
        assert body["page_estimate"] >= 8  # minimum is 8

    def test_response_includes_regulatory_citations(self, client):
        resp = client.post("/api/v1/sop/generate", json=_minimal_payload())
        body = resp.json()
        cites = body["compliance_citations"]
        assert "21 CFR Part 1, Subpart S" in cites
        assert any("1.1325" in c for c in cites)
        assert any("1.1340" in c for c in cites)
        assert any("1.1345" in c for c in cites)
        assert any("1.1350" in c for c in cites)
        assert any("1.1455" in c for c in cites)

    def test_response_has_iso_generated_at(self, client):
        resp = client.post("/api/v1/sop/generate", json=_minimal_payload())
        body = resp.json()
        assert "T" in body["generated_at"]
        assert body["generated_at"].endswith("+00:00") or body["generated_at"].endswith("Z")

    def test_markdown_includes_facilities(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(facilities=["Salinas, CA", "Yuma, AZ"]),
        )
        body = resp.json()
        assert "Salinas, CA" in body["markdown_content"]
        assert "Yuma, AZ" in body["markdown_content"]

    def test_markdown_includes_primary_contact(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(primary_contact="Sam Compliance"),
        )
        body = resp.json()
        assert "Sam Compliance" in body["markdown_content"]


# ===========================================================================
# /generate endpoint — validation errors
# ===========================================================================


class TestGenerateEndpointValidation:

    def test_empty_products_rejected(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(products=[]),
        )
        # Pydantic rejects — min_length=1 on products.
        assert resp.status_code == 422

    def test_empty_facilities_rejected(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(facilities=[]),
        )
        assert resp.status_code == 422

    def test_missing_company_name_rejected(self, client):
        payload = _minimal_payload()
        del payload["company_name"]
        resp = client.post("/api/v1/sop/generate", json=payload)
        assert resp.status_code == 422


# ===========================================================================
# /generate endpoint — contact optional fields
# ===========================================================================


class TestGenerateEndpointOptionalContactFields:

    def test_contact_title_appended_when_present(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(
                primary_contact="Jane Roe", contact_title="VP Compliance"
            ),
        )
        body = resp.json()
        assert "VP Compliance" in body["markdown_content"]

    def test_contact_email_rendered_when_present(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(contact_email="jane@acme.example"),
        )
        body = resp.json()
        assert "jane@acme.example" in body["markdown_content"]

    def test_no_optional_contact_fields_no_blank_lines(self, client):
        resp = client.post("/api/v1/sop/generate", json=_minimal_payload())
        body = resp.json()
        # No crash, still renders.
        assert "**Compliance Contact**" in body["markdown_content"]


# ===========================================================================
# /generate endpoint — retailer-specific content
# ===========================================================================


class TestGenerateEndpointRetailerSections:

    def test_no_target_retailers_omits_retailer_section(self, client):
        resp = client.post("/api/v1/sop/generate", json=_minimal_payload())
        body = resp.json()
        assert "Retailer-Specific Requirements" not in body["sections"]

    def test_target_retailers_adds_section_entry(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(target_retailers=["Walmart"]),
        )
        body = resp.json()
        assert "Retailer-Specific Requirements" in body["sections"]

    def test_walmart_retailer_section_rendered(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(target_retailers=["Walmart"]),
        )
        body = resp.json()
        md = body["markdown_content"]
        assert "Walmart" in md
        assert "GS1-128" in md

    def test_walmart_case_insensitive(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(target_retailers=["walmart"]),
        )
        body = resp.json()
        assert "GS1-128" in body["markdown_content"]

    def test_kroger_retailer_section_rendered(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(target_retailers=["Kroger"]),
        )
        body = resp.json()
        md = body["markdown_content"]
        assert "Kroger" in md
        assert "GLN" in md

    def test_costco_retailer_section_rendered(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(target_retailers=["Costco"]),
        )
        body = resp.json()
        md = body["markdown_content"]
        assert "Costco" in md
        assert "EPCIS" in md

    def test_multiple_retailers_all_rendered(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(
                target_retailers=["Walmart", "Kroger", "Costco"]
            ),
        )
        body = resp.json()
        md = body["markdown_content"]
        assert "Walmart" in md
        assert "Kroger" in md
        assert "Costco" in md


# ===========================================================================
# /generate endpoint — integration section toggles
# ===========================================================================


class TestGenerateEndpointIntegrationSection:

    def test_no_integration_omits_section(self, client):
        resp = client.post("/api/v1/sop/generate", json=_minimal_payload())
        body = resp.json()
        assert "Technology Integration" not in body["sections"]
        assert "## 7. Technology Integration" not in body["markdown_content"]

    def test_erp_only_includes_erp_subsection(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(has_erp_integration=True),
        )
        body = resp.json()
        assert "Technology Integration" in body["sections"]
        md = body["markdown_content"]
        assert "ERP/WMS Integration" in md
        assert "webhooks/ingest" in md
        # API integration line is reached in section 5.1.
        assert "API integration" in md

    def test_iot_only_includes_iot_subsection(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(has_iot_monitoring=True),
        )
        body = resp.json()
        assert "Technology Integration" in body["sections"]
        md = body["markdown_content"]
        assert "IoT Temperature Monitoring" in md
        assert "Sensitech TempTale" in md

    def test_both_erp_and_iot_include_both_subsections(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(
                has_erp_integration=True, has_iot_monitoring=True
            ),
        )
        body = resp.json()
        md = body["markdown_content"]
        assert "ERP/WMS Integration" in md
        assert "IoT Temperature Monitoring" in md


# ===========================================================================
# /generate endpoint — section ordering & page estimate
# ===========================================================================


class TestSectionListOrdering:

    def test_default_sections_in_order(self, client):
        resp = client.post("/api/v1/sop/generate", json=_minimal_payload())
        sections = resp.json()["sections"]
        assert sections == [
            "Purpose & Scope",
            "Regulatory Background",
            "TLC Assignment",
            "CTE Procedures",
            "Record Keeping & Data Management",
            "Corrective Actions",
            "Training",
            "Document Control",
        ]

    def test_integration_inserted_before_training(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(has_erp_integration=True),
        )
        sections = resp.json()["sections"]
        idx = sections.index("Technology Integration")
        assert sections[idx + 1] == "Training"

    def test_retailer_appended_last(self, client):
        resp = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(target_retailers=["Walmart"]),
        )
        sections = resp.json()["sections"]
        assert sections[-1] == "Retailer-Specific Requirements"

    def test_page_estimate_is_int_and_at_least_8(self, client):
        resp = client.post("/api/v1/sop/generate", json=_minimal_payload())
        body = resp.json()
        assert isinstance(body["page_estimate"], int)
        assert body["page_estimate"] >= 8

    def test_page_estimate_scales_with_content(self, client):
        """Longer inputs → larger document → bigger page_estimate."""
        small = client.post("/api/v1/sop/generate", json=_minimal_payload()).json()
        big = client.post(
            "/api/v1/sop/generate",
            json=_minimal_payload(
                products=[f"P{i}" for i in range(50)],
                facilities=[f"Facility {i}" for i in range(20)],
                has_erp_integration=True,
                has_iot_monitoring=True,
                target_retailers=["Walmart", "Kroger", "Costco"],
            ),
        ).json()
        assert big["page_estimate"] >= small["page_estimate"]


# ===========================================================================
# Pydantic model surface
# ===========================================================================


class TestPydanticModels:

    def test_sop_request_defaults(self):
        r = SOPRequest(
            company_name="X",
            products=["P"],
            facilities=["F"],
            primary_contact="C",
        )
        assert r.company_type == "manufacturer"
        assert r.has_iot_monitoring is False
        assert r.has_erp_integration is False
        assert r.target_retailers == []

    def test_sop_response_required_fields(self):
        r = SOPResponse(
            company_name="X",
            generated_at="2026-01-01T00:00:00+00:00",
            document_title="T",
            markdown_content="# X",
            sections=["a"],
            page_estimate=8,
            compliance_citations=["21 CFR Part 1, Subpart S"],
        )
        assert r.page_estimate == 8
