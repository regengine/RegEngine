"""Data-free checks for the EPCIS XML ingest route.

No EPCIS event documents, GS1 identifiers, or lot codes. Malformed bytes,
an empty body, a non-XML body, and an empty document shell are the only
payloads.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"
_XML_PATH = "/api/v1/epcis/events/xml"


@pytest.fixture
def client() -> TestClient:
    """Same pattern as ``test_epcis_ingestion_api.py`` -- override the
    api-key dep so the tests focus on XML rejection behavior."""
    from app.epcis.router import router
    from app.webhook_compat import _verify_api_key

    from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant=TEST_TENANT_ID)
    return TestClient(app)


def _malformed_xml() -> bytes:
    """Broken XML -- lxml will raise. Not an event document."""
    return b'<?xml version="1.0"?><EPCISDocument><unclosed>'


def _empty_xml_document() -> bytes:
    """Well-formed document shell with no events."""
    return b"""<?xml version="1.0"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:2">
  <EPCISBody><EventList></EventList></EPCISBody>
</epcis:EPCISDocument>"""


def _assert_no_traceback(response) -> None:
    text = response.text
    assert "Traceback" not in text
    assert 'File "' not in text


def _xml_headers(**extra: str) -> dict[str, str]:
    headers = {
        "X-Tenant-ID": TEST_TENANT_ID,
        "Content-Type": "application/xml",
    }
    headers.update(extra)
    return headers


class TestXmlPayloadShape_Issue1151:
    def test_empty_body_rejected(self, client):
        resp = client.post(_XML_PATH, headers=_xml_headers(), content=b"")
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert isinstance(detail, str)
        assert "Empty XML payload" in detail
        _assert_no_traceback(resp)

    def test_non_xml_content_rejected(self, client):
        """Payload that doesn't start with ``<`` or ``<?xml`` must be
        refused before we hand it to lxml."""
        resp = client.post(
            _XML_PATH,
            headers=_xml_headers(),
            content=b"not xml at all, just junk",
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert isinstance(detail, str)
        assert "does not appear to be XML" in detail
        _assert_no_traceback(resp)

    def test_wrong_content_type_rejected(self, client):
        resp = client.post(
            _XML_PATH,
            headers=_xml_headers(**{"Content-Type": "text/plain"}),
            content=b"not xml",
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert isinstance(detail, str)
        assert "does not appear to be XML" in detail
        _assert_no_traceback(resp)


class TestXmlParseStrictness_Issue1151:
    def test_malformed_xml_returns_400(self, client):
        """Unparseable XML is a client error, not an empty document."""
        resp = client.post(
            _XML_PATH,
            headers=_xml_headers(),
            content=_malformed_xml(),
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert isinstance(detail, str)
        assert "malformed XML" in detail
        _assert_no_traceback(resp)

    def test_well_formed_but_empty_document_returns_422(self, client):
        resp = client.post(
            _XML_PATH,
            headers=_xml_headers(),
            content=_empty_xml_document(),
        )
        assert resp.status_code == 422
        detail = resp.json().get("detail", "")
        assert isinstance(detail, str)
        assert "No EPCIS events found" in detail
        _assert_no_traceback(resp)


class TestXmlPartialModeEscapeHatch_Issue1151:
    def test_invalid_mode_value_rejected(self, client):
        """Mode is checked before the body is read, so an empty body is enough."""
        resp = client.post(
            _XML_PATH,
            params={"mode": "lenient"},
            headers=_xml_headers(),
            content=b"",
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert isinstance(detail, str)
        assert "mode" in detail.lower()
        _assert_no_traceback(resp)


class TestParseXmlUnit_Issue1151:
    """Direct exercise of ``_parse_epcis_xml`` -- no router, no DB."""

    def test_parse_raises_400_on_malformed_xml(self):
        from app.epcis.xml_parser import _parse_epcis_xml

        with pytest.raises(HTTPException) as caught:
            _parse_epcis_xml(_malformed_xml())
        assert caught.value.status_code == 400
        detail = str(caught.value.detail)
        assert "malformed XML" in detail
        assert "Traceback" not in detail
        assert 'File "' not in detail

    def test_parse_empty_document_returns_empty_list(self):
        from app.epcis.xml_parser import _parse_epcis_xml

        events = _parse_epcis_xml(_empty_xml_document())
        assert events == []
