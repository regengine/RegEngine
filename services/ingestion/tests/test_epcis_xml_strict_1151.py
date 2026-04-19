"""Regression tests for issue #1151 -- EPCIS XML parser strict validation.

Before the fix, ``_parse_epcis_xml()`` returned a list of extracted events
without running EPCIS structural validation or FSMA schema validation on
each one. Combined with the legacy per-event loop in the XML endpoint,
this meant:

- An XML document with a structurally invalid EPCIS event was silently
  accepted -- the malformed event flowed through as 201 with only a
  compliance alert.
- An XML document that failed FSMA schema validation was persisted with
  ``fsma_validated=None`` and never returned a 422.
- A document with completely unparseable XML returned an empty event
  list with no error -- the client had no signal something was wrong.

The fix (landed on main):

1. ``router.py`` now routes the XML endpoint through
   ``_ingest_batch_events_db_atomic`` by default (same atomic phase-1
   pre-validation used by the JSON batch endpoint for #1156).
2. ``_prepare_event_for_persistence`` calls ``_validate_epcis`` + the
   FSMA strict-mode gate (#1239), raising 400/422 before any DB work.
3. Unmapped bizStep URIs raise 400 ``unmapped_bizstep`` (#1153) --
   integrated through the same pipeline for XML events.
4. ``?mode=partial`` is retained as an explicit opt-in for the legacy
   per-event 207 behavior.

These tests lock in the strict-by-default contract. A regression that
re-introduces the silent-accept path would fail ``test_xml_ingest_*``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"


@pytest.fixture
def client() -> TestClient:
    """Same pattern as ``test_epcis_ingestion_api.py`` -- override the
    api-key dep so the tests focus on XML + validation behavior."""
    from app.epcis.router import router
    from app.webhook_compat import _verify_api_key

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return TestClient(app)


# ── XML sample fixtures ─────────────────────────────────────────────────────


def _valid_epcis_xml() -> bytes:
    """A full, FSMA-valid ObjectEvent in EPCIS 2.0 XML."""
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:2"
                     schemaVersion="2.0" creationDate="2026-04-18T09:30:00Z">
  <EPCISBody>
    <EventList>
      <ObjectEvent>
        <eventTime>2026-04-18T09:30:00.000-05:00</eventTime>
        <eventTimeZoneOffset>-05:00</eventTimeZoneOffset>
        <action>OBSERVE</action>
        <bizStep>urn:epcglobal:cbv:bizstep:receiving</bizStep>
        <bizLocation><id>urn:epc:id:sgln:0614141.00002.0</id></bizLocation>
        <epcList><epc>urn:epc:id:sgtin:0614141.107346.1</epc></epcList>
        <extension>
          <quantityList>
            <quantityElement>
              <epcClass>urn:epc:class:lgtin:0614141.107346.ROM0042</epcClass>
              <quantity>10.0</quantity>
              <uom>CS</uom>
            </quantityElement>
          </quantityList>
        </extension>
        <ilmd>
          <cbvmda:lotNumber xmlns:cbvmda="urn:epcglobal:cbv:mda">ROM-0042</cbvmda:lotNumber>
          <fsma:traceabilityLotCode xmlns:fsma="urn:fsma:food:traceability">00012345678901-ROM0042</fsma:traceabilityLotCode>
        </ilmd>
      </ObjectEvent>
    </EventList>
  </EPCISBody>
</epcis:EPCISDocument>"""


def _xml_with_missing_required_fields() -> bytes:
    """ObjectEvent missing ``bizStep`` -- fails validation.

    NOTE: XML comments cannot contain double-hyphens, so we simply omit
    bizStep without an inline explanatory comment.
    """
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:2"
                     schemaVersion="2.0" creationDate="2026-04-18T09:30:00Z">
  <EPCISBody>
    <EventList>
      <ObjectEvent>
        <eventTime>2026-04-18T09:30:00.000-05:00</eventTime>
        <action>OBSERVE</action>
      </ObjectEvent>
    </EventList>
  </EPCISBody>
</epcis:EPCISDocument>"""


def _xml_with_unmapped_bizstep() -> bytes:
    """EPCIS/FSMA-complete event but with an unknown bizStep URI.

    Includes TLC/lotNumber so the unmapped-bizStep check (#1153) fires
    before any FSMA ILMD completeness check. Exercises the #1153 guard
    from the XML ingestion path -- pre-fix this would silently default
    to 'receiving'.
    """
    return b"""<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:2"
                     schemaVersion="2.0" creationDate="2026-04-18T09:30:00Z">
  <EPCISBody>
    <EventList>
      <ObjectEvent>
        <eventTime>2026-04-18T09:30:00.000-05:00</eventTime>
        <eventTimeZoneOffset>-05:00</eventTimeZoneOffset>
        <action>OBSERVE</action>
        <bizStep>urn:epcglobal:cbv:bizstep:fabricated-step</bizStep>
        <bizLocation><id>urn:epc:id:sgln:0614141.00002.0</id></bizLocation>
        <epcList><epc>urn:epc:id:sgtin:0614141.107346.1</epc></epcList>
        <extension>
          <quantityList>
            <quantityElement>
              <epcClass>urn:epc:class:lgtin:0614141.107346.ROM0042</epcClass>
              <quantity>10.0</quantity>
              <uom>CS</uom>
            </quantityElement>
          </quantityList>
        </extension>
        <ilmd>
          <cbvmda:lotNumber xmlns:cbvmda="urn:epcglobal:cbv:mda">ROM-BOGUS</cbvmda:lotNumber>
          <fsma:traceabilityLotCode xmlns:fsma="urn:fsma:food:traceability">00012345678901-ROMBOGUS</fsma:traceabilityLotCode>
        </ilmd>
      </ObjectEvent>
    </EventList>
  </EPCISBody>
</epcis:EPCISDocument>"""


def _malformed_xml() -> bytes:
    """Broken XML -- lxml will raise. Pre-fix path returned [] silently."""
    return b"<?xml version=\"1.0\"?><EPCISDocument><unclosed>"


def _empty_xml_document() -> bytes:
    """Well-formed but contains no events -- should 422, not 201."""
    return b"""<?xml version="1.0"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:2">
  <EPCISBody><EventList></EventList></EPCISBody>
</epcis:EPCISDocument>"""


# ── Pre-parse payload-shape rejections ──────────────────────────────────────


class TestXmlPayloadShape_Issue1151:
    def test_empty_body_rejected(self, client):
        resp = client.post(
            "/api/v1/epcis/events/xml",
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=b"",
        )
        assert resp.status_code == 400
        assert "Empty XML payload" in resp.json().get("detail", "")

    def test_non_xml_content_rejected(self, client):
        """Payload that doesn't start with ``<`` or ``<?xml`` must be
        refused before we hand it to lxml -- closes a DoS-ish path too."""
        resp = client.post(
            "/api/v1/epcis/events/xml",
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=b"not xml at all, just junk",
        )
        assert resp.status_code == 400


# ── Parse-level strictness ──────────────────────────────────────────────────


class TestXmlParseStrictness_Issue1151:
    def test_malformed_xml_returns_422_not_201(self, client):
        """Pre-fix: parser returned [] and router happily reported an
        empty-batch success. Post-fix: router must signal '0 events'
        with 422 -- the parse failure itself surfaces to the client."""
        resp = client.post(
            "/api/v1/epcis/events/xml",
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=_malformed_xml(),
        )
        assert resp.status_code == 422
        detail = resp.json().get("detail", "")
        assert "No EPCIS events" in detail or "no events" in detail.lower()

    def test_well_formed_but_empty_document_returns_422(self, client):
        resp = client.post(
            "/api/v1/epcis/events/xml",
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=_empty_xml_document(),
        )
        assert resp.status_code == 422


# ── Atomic-mode pre-DB validation rejects invalid events ────────────────────


class TestXmlAtomicValidation_Issue1151:
    """The core defect: XML events that fail EPCIS structural validation
    or FSMA schema validation MUST be rejected with 400/422 -- not
    silently stored with a compliance alert."""

    def test_missing_required_field_returns_400(self, client):
        """Pre-fix: the missing-bizStep event would flow through with an
        'incomplete_route' alert and be stored as 201. Post-fix: atomic
        batch pre-validation raises 400 ``batch_validation_failed``."""
        resp = client.post(
            "/api/v1/epcis/events/xml",
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=_xml_with_missing_required_fields(),
        )
        assert resp.status_code == 400
        payload = resp.json()
        detail = payload.get("detail", payload)
        # Atomic mode must be the default for the XML endpoint.
        assert detail.get("mode") == "atomic"
        assert detail.get("error") == "batch_validation_failed"
        # Per-index error surfaces the inner validation failure.
        errors = detail.get("errors", [])
        assert len(errors) >= 1
        assert errors[0]["index"] == 0

    def test_unmapped_bizstep_in_xml_returns_400(self, client):
        """Integration with #1153 -- XML path must not silently default
        an unmapped bizStep to 'receiving'."""
        resp = client.post(
            "/api/v1/epcis/events/xml",
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=_xml_with_unmapped_bizstep(),
        )
        assert resp.status_code == 400
        payload = resp.json()
        detail = payload.get("detail", payload)
        assert detail.get("error") == "batch_validation_failed"
        # The inner error from #1153 should be captured per index.
        errors = detail.get("errors", [])
        assert len(errors) >= 1
        inner = errors[0]
        # The inner detail is itself a dict with error='unmapped_bizstep'.
        inner_detail = inner.get("detail", inner)
        if isinstance(inner_detail, dict):
            assert inner_detail.get("error") == "unmapped_bizstep"

    def test_atomic_is_the_default_xml_mode(self, client):
        """No ``mode`` query param → atomic behavior. Pre-fix, the XML
        endpoint only had one mode and it was the silently-accepting
        per-event loop."""
        resp = client.post(
            "/api/v1/epcis/events/xml",
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=_xml_with_missing_required_fields(),
        )
        # Atomic-mode rejection = 400, not 207 (per-event partial).
        assert resp.status_code == 400
        assert resp.status_code != 207
        detail = resp.json().get("detail", {})
        if isinstance(detail, dict):
            assert detail.get("mode") == "atomic"


# ── Partial mode escape hatch still available ───────────────────────────────


class TestXmlPartialModeEscapeHatch_Issue1151:
    """Partial mode is explicit opt-in. We lock in that it's available
    (for migration / legacy clients) but NOT the default."""

    def test_explicit_partial_mode_accepts_mixed_batch(self, client):
        """With ``?mode=partial`` an invalid event produces a per-index
        failure but does not 400 the whole request. This preserves the
        legacy 207 semantics for clients that need them."""
        resp = client.post(
            "/api/v1/epcis/events/xml",
            params={"mode": "partial"},
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=_xml_with_missing_required_fields(),
        )
        # Partial mode with only-invalid events = 400 (no successes);
        # mixed invalid+valid would be 207. Either is acceptable -- what
        # we lock in is that ``mode`` was recognized.
        assert resp.status_code in (400, 207)
        payload = resp.json()
        assert payload.get("mode") == "partial" or (
            isinstance(payload.get("detail"), dict)
            and payload["detail"].get("mode") == "partial"
        )

    def test_invalid_mode_value_rejected(self, client):
        resp = client.post(
            "/api/v1/epcis/events/xml",
            params={"mode": "lenient"},
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=_valid_epcis_xml(),
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert "mode" in detail.lower() or "invalid" in detail.lower()


# ── Parse function unit checks ──────────────────────────────────────────────


class TestParseXmlUnit_Issue1151:
    """Direct exercise of ``_parse_epcis_xml`` -- no router, no DB. These
    lock in that the parser itself doesn't crash on bad input and produces
    dicts that flow cleanly into the validation pipeline downstream."""

    def test_parse_returns_empty_on_malformed_xml(self):
        """The parser's own contract: return [] rather than raise. The
        router is responsible for turning [] into a 422."""
        from app.epcis.xml_parser import _parse_epcis_xml
        events = _parse_epcis_xml(_malformed_xml())
        assert events == []

    def test_parse_valid_xml_extracts_biz_step(self):
        """Round-trip check: a valid ObjectEvent comes out with bizStep
        populated so ``_normalize_epcis_to_cte`` can map it to a CTE."""
        from app.epcis.xml_parser import _parse_epcis_xml
        events = _parse_epcis_xml(_valid_epcis_xml())
        assert len(events) == 1
        assert events[0]["type"] == "ObjectEvent"
        assert events[0].get("bizStep") == "urn:epcglobal:cbv:bizstep:receiving"
        assert events[0].get("action") == "OBSERVE"

    def test_parse_empty_document_returns_empty_list(self):
        from app.epcis.xml_parser import _parse_epcis_xml
        events = _parse_epcis_xml(_empty_xml_document())
        assert events == []
