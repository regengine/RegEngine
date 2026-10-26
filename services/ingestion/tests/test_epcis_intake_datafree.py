"""Data-free EPCIS intake checks.

No EPCIS documents, events, GS1 identifiers, or lot codes. BizStep names
are the CBV vocabulary tokens already stored on ``_EVENT_TYPE_MAP``.
The XML node test builds an empty element and appends an lxml comment
and a processing instruction.
"""

from __future__ import annotations

import pytest
from app.epcis.normalization import _EVENT_TYPE_MAP, _canonical_bizstep
from app.epcis.router import router as epcis_ingestion_router
from app.epcis.xml_parser import _xml_child_text, _xml_elements
from app.webhook_compat import _verify_api_key
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override

TEST_TENANT_ID = "t"
_XML_PATH = "/api/v1/epcis/events/xml"
_CBV_PREFIX = "urn:epcglobal:cbv:bizstep:"
_CBV_NAMES = tuple(sorted(key[len(_CBV_PREFIX) :] for key in _EVENT_TYPE_MAP if key.startswith(_CBV_PREFIX)))


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(epcis_ingestion_router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant=TEST_TENANT_ID)
    with TestClient(app) as test_client:
        yield test_client


def _assert_no_parser_internals(response) -> None:
    text = response.text
    assert "Traceback" not in text
    assert 'File "' not in text


@pytest.mark.parametrize("name", _CBV_NAMES)
def test_bare_and_web_vocabulary_bizstep_normalise(name: str) -> None:
    expected = _CBV_PREFIX + name
    assert expected in _EVENT_TYPE_MAP
    assert _canonical_bizstep(name) == expected
    assert _canonical_bizstep(f"https://ref.gs1.org/cbv/BizStep-{name}") == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("not-a-bizstep", "not-a-bizstep"),
        (None, ""),
        ("", ""),
        ("   ", ""),
    ],
)
def test_unknown_bizstep_stays_unmapped(value: object, expected: str) -> None:
    assert _canonical_bizstep(value) == expected
    assert expected not in _EVENT_TYPE_MAP


def test_xml_child_iteration_skips_comments_and_processing_instructions() -> None:
    etree = pytest.importorskip("lxml.etree")
    parent = etree.Element("empty")
    comment = etree.Comment("note")
    instruction = etree.ProcessingInstruction("target", "data")
    parent.append(comment)
    parent.append(instruction)

    assert len(parent) == 2
    assert list(parent) == [comment, instruction]
    assert list(_xml_elements(parent)) == []
    assert _xml_child_text(parent, "child") is None


def test_malformed_xml_bytes_return_400(client: TestClient) -> None:
    response = client.post(
        _XML_PATH,
        headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/xml"},
        content=b"<a>",
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert isinstance(detail, str)
    assert "malformed XML" in detail
    _assert_no_parser_internals(response)


def test_non_parse_exception_propagates_as_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """A parser failure that is not malformed XML is not relabelled as HTTP 400."""

    def _boom(_raw: object) -> list[dict]:
        raise RuntimeError("parser helper failed")

    monkeypatch.setattr("app.epcis.router._parse_epcis_xml", _boom)
    app = FastAPI()
    app.include_router(epcis_ingestion_router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant=TEST_TENANT_ID)
    with TestClient(app, raise_server_exceptions=False) as local_client:
        response = local_client.post(
            _XML_PATH,
            headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/xml"},
            content=b"<a/>",
        )
    assert response.status_code == 500
    _assert_no_parser_internals(response)


def test_empty_xml_body_returns_400(client: TestClient) -> None:
    response = client.post(
        _XML_PATH,
        headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/xml"},
        content=b"",
    )
    assert response.status_code == 400
    detail = response.json().get("detail", "")
    assert isinstance(detail, str)
    assert "Empty XML payload" in detail
    _assert_no_parser_internals(response)
