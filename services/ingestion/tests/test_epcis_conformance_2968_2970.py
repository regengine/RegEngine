"""Regression tests for EPCIS 2.0 conformance defects #2968 and #2970.

#2968 — ``_normalize_epcis_to_cte`` read ``quantityList`` only from the
EPCIS 1.x ``extension`` wrapper, so a GS1-conformant EPCIS 2.0 JSON
event (``quantityList`` as a direct member) normalized to
``quantity = None`` and was hard-rejected with 422 ``missing_quantity``
— the exact KDE the sender had supplied.

#2970 — ``_validate_epcis`` required ``action`` on every event type.
EPCIS 2.0 defines no ``action`` member on TransformationEvent (it
carries ``transformationID`` and input/output lists), so the FSMA 204
transformation CTE could not be ingested on any route, and in XML
strict mode one conformant TransformationEvent aborted the whole
document.

Both defects are exercised at the unit level (normalizer / validator)
and end-to-end through the ingest router so a future refactor cannot
reintroduce them behind a passing unit test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.epcis.normalization import _normalize_epcis_to_cte  # noqa: E402
from app.epcis.persistence import (  # noqa: E402
    _epcis_idempotency_index,
    _epcis_store,
    _parse_epcis_document,
)
from app.epcis.router import router as epcis_ingestion_router  # noqa: E402
from app.epcis.validation import _validate_epcis  # noqa: E402
from app.webhook_compat import _verify_api_key  # noqa: E402

from services.ingestion.tests.tenant_context_overrides import install_tenant_context_override  # noqa: E402

TEST_TENANT_ID = "00000000-0000-0000-0000-000000000123"


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(epcis_ingestion_router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    install_tenant_context_override(app, default_tenant=TEST_TENANT_ID)
    _epcis_store.clear()
    _epcis_idempotency_index.clear()
    with TestClient(app) as test_client:
        yield test_client


def _quantity_element() -> dict:
    return {"epcClass": "urn:epc:class:lgtin:0614141.107346.ROM0042", "quantity": 12.0, "uom": "KGM"}


def _object_event(tlc: str) -> dict:
    """A GS1 EPCIS 2.0 JSON ObjectEvent — ``quantityList`` at the top
    level, no EPCIS 1.x ``extension`` wrapper anywhere."""
    return {
        "@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
        "type": "ObjectEvent",
        "eventTime": "2026-02-28T09:30:00.000-05:00",
        "eventTimeZoneOffset": "-05:00",
        "action": "OBSERVE",
        "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
        "bizLocation": {"id": "urn:epc:id:sgln:0614141.00002.0"},
        "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
        "quantityList": [_quantity_element()],
        "ilmd": {"cbvmda:lotNumber": "ROM-0042", "fsma:traceabilityLotCode": tlc},
    }


def _transformation_event(tlc: str) -> dict:
    """A GS1 EPCIS 2.0 JSON TransformationEvent — ``transformationID``
    plus output lists and NO ``action`` member, which the standard does
    not define for this type."""
    return {
        "@context": ["https://ref.gs1.org/standards/epcis/2.0.0/epcis-context.jsonld"],
        "type": "TransformationEvent",
        "eventTime": "2026-02-28T11:00:00.000-05:00",
        "eventTimeZoneOffset": "-05:00",
        "bizStep": "urn:epcglobal:cbv:bizstep:transforming",
        "bizLocation": {"id": "urn:epc:id:sgln:0614141.00002.0"},
        "transformationID": "urn:uuid:8b4c2f1e-0f4b-4f8c-9a3e-3f0d2c1b7a55",
        "inputEPCList": ["urn:epc:id:sgtin:0614141.107346.2017"],
        "outputEPCList": ["urn:epc:id:sgtin:0614141.107777.9001"],
        "outputQuantityList": [
            {"epcClass": "urn:epc:class:lgtin:0614141.107777.CHOP01", "quantity": 250.0, "uom": "KGM"}
        ],
        "ilmd": {"cbvmda:lotNumber": "CHOP-01", "fsma:traceabilityLotCode": tlc},
    }


# ---------------------------------------------------------------------------
# #2968 — top-level quantityList
# ---------------------------------------------------------------------------


class TestTopLevelQuantityList2968:
    def test_top_level_quantity_list_is_read(self):
        # Pre-fix this returned (None, None) because only
        # ``extension.quantityList`` was consulted.
        out = _normalize_epcis_to_cte(_object_event("00012345678901-ROM0042"))
        assert out["quantity"] == 12.0
        assert out["unit_of_measure"] == "KGM"

    def test_top_level_and_extension_shapes_agree(self):
        top_level = _object_event("00012345678901-ROM0042")
        nested = _object_event("00012345678901-ROM0042")
        nested["extension"] = {"quantityList": [nested.pop("quantityList")[0]]}

        top_out = _normalize_epcis_to_cte(top_level)
        nested_out = _normalize_epcis_to_cte(nested)
        assert (top_out["quantity"], top_out["unit_of_measure"]) == (
            nested_out["quantity"],
            nested_out["unit_of_measure"],
        )

    def test_legacy_and_canonical_writers_agree(self):
        # The canonical writer already read both shapes; the legacy CTE
        # normalizer did not, so the two disagreed about whether the very
        # same event had a quantity at all.
        import shared.canonical_event as canonical_mod

        top_level = _object_event("00012345678901-ROM0042")
        nested = _object_event("00012345678901-ROM0042")
        nested["extension"] = {"quantityList": [nested.pop("quantityList")[0]]}

        for event in (top_level, nested):
            normalized = _normalize_epcis_to_cte(event)
            canon_qty, canon_uom = canonical_mod._extract_epcis_quantity(event)
            assert canon_qty is not None
            assert float(normalized["quantity"]) == canon_qty
            assert normalized["unit_of_measure"] == canon_uom

    def test_extension_shape_still_wins_when_both_present(self):
        # Precedence is pinned to ``canonical_event._extract_epcis_quantity``
        # so a malformed event carrying both shapes cannot make the two
        # writers drift apart again.
        import shared.canonical_event as canonical_mod

        event = _object_event("00012345678901-ROM0042")
        event["extension"] = {"quantityList": [{"quantity": 99.0, "uom": "CS"}]}

        normalized = _normalize_epcis_to_cte(event)
        canon_qty, canon_uom = canonical_mod._extract_epcis_quantity(event)
        assert (float(normalized["quantity"]), normalized["unit_of_measure"]) == (canon_qty, canon_uom)

    def test_conformant_event_ingests_without_missing_quantity_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/epcis/events",
            headers={"X-Tenant-ID": TEST_TENANT_ID},
            json=_object_event("00012345678901-TOPLEVEL01"),
        )
        assert response.status_code == 201, response.text
        event_id = response.json()["cte_id"]
        assert event_id

        fetched = client.get(
            f"/api/v1/epcis/events/{event_id}",
            headers={"X-Tenant-ID": TEST_TENANT_ID},
        )
        assert fetched.status_code == 200, fetched.text
        normalized = fetched.json()["normalized_cte"]
        assert normalized["quantity"] == 12.0
        assert normalized["unit_of_measure"] == "KGM"


# ---------------------------------------------------------------------------
# #2970 — action is not a TransformationEvent member
# ---------------------------------------------------------------------------


class TestTransformationEventAction2970:
    def test_action_less_transformation_event_is_valid(self):
        # Pre-fix: ["Missing required EPCIS field 'action'"].
        assert _validate_epcis(_transformation_event("00012345678901-CHOP01")) == []

    def test_transformation_identified_by_output_lists_only(self):
        event = _transformation_event("00012345678901-CHOP01")
        event.pop("transformationID")
        assert _validate_epcis(event) == []

    def test_transformation_without_identity_fields_flagged(self):
        event = _transformation_event("00012345678901-CHOP01")
        for field in ("transformationID", "inputEPCList", "outputEPCList", "outputQuantityList"):
            event.pop(field, None)
        errors = _validate_epcis(event)
        assert any("transformationID" in e for e in errors)
        # The rejection must be about the transformation identity, not
        # about a field EPCIS 2.0 never defined for this type.
        assert not any("'action'" in e for e in errors)

    def test_object_event_without_action_still_rejected(self):
        event = _object_event("00012345678901-ROM0042")
        event.pop("action")
        errors = _validate_epcis(event)
        assert any("Missing required EPCIS field 'action'" in e for e in errors)

    def test_conformant_transformation_event_ingests(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/epcis/events",
            headers={"X-Tenant-ID": TEST_TENANT_ID},
            json=_transformation_event("00012345678901-CHOP01"),
        )
        assert response.status_code == 201, response.text
        assert response.json()["cte_id"]

    def test_rebuilt_transformation_event_has_no_fabricated_action(self):
        normalized = {
            "epcis_event_type": "TransformationEvent",
            "event_time": "2026-02-28T11:00:00+00:00",
            "epcis_action": None,
            "epcis_biz_step": "urn:epcglobal:cbv:bizstep:transforming",
            "lot_code": "CHOP-01",
            "tlc": "00012345678901-CHOP01",
        }
        rebuilt = _parse_epcis_document({}, normalized)
        assert rebuilt["type"] == "TransformationEvent"
        assert "action" not in rebuilt

        # Types that DO define ``action`` keep the existing default.
        object_rebuilt = _parse_epcis_document({}, {"epcis_event_type": "ObjectEvent"})
        assert object_rebuilt["action"] == "OBSERVE"


# ---------------------------------------------------------------------------
# #2970 — XML strict mode must not abort a mixed document
# ---------------------------------------------------------------------------


_MIXED_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<epcis:EPCISDocument xmlns:epcis="urn:epcglobal:epcis:xsd:2"
                     schemaVersion="2.0" creationDate="2026-02-28T09:30:00Z">
  <EPCISBody>
    <EventList>
      <ObjectEvent>
        <eventTime>2026-02-28T09:30:00.000-05:00</eventTime>
        <eventTimeZoneOffset>-05:00</eventTimeZoneOffset>
        <action>OBSERVE</action>
        <bizStep>urn:epcglobal:cbv:bizstep:receiving</bizStep>
        <bizLocation><id>urn:epc:id:sgln:0614141.00002.0</id></bizLocation>
        <epcList><epc>urn:epc:id:sgtin:0614141.107346.2017</epc></epcList>
        <extension>
          <quantityList>
            <quantityElement>
              <epcClass>urn:epc:class:lgtin:0614141.107346.ROM0042</epcClass>
              <quantity>12.0</quantity>
              <uom>KGM</uom>
            </quantityElement>
          </quantityList>
        </extension>
        <ilmd>
          <cbvmda:lotNumber xmlns:cbvmda="urn:epcglobal:cbv:mda">ROM-0042</cbvmda:lotNumber>
          <fsma:traceabilityLotCode xmlns:fsma="urn:fsma:food:traceability">00012345678901-ROM0042</fsma:traceabilityLotCode>
        </ilmd>
      </ObjectEvent>
      <TransformationEvent>
        <eventTime>2026-02-28T11:00:00.000-05:00</eventTime>
        <eventTimeZoneOffset>-05:00</eventTimeZoneOffset>
        <bizStep>urn:epcglobal:cbv:bizstep:transforming</bizStep>
        <bizLocation><id>urn:epc:id:sgln:0614141.00002.0</id></bizLocation>
        <transformationID>urn:uuid:8b4c2f1e-0f4b-4f8c-9a3e-3f0d2c1b7a55</transformationID>
        <outputEPCList><epc>urn:epc:id:sgtin:0614141.107777.9001</epc></outputEPCList>
        <outputQuantityList>
          <quantityElement>
            <epcClass>urn:epc:class:lgtin:0614141.107777.CHOP01</epcClass>
            <quantity>250.0</quantity>
            <uom>KGM</uom>
          </quantityElement>
        </outputQuantityList>
        <ilmd>
          <cbvmda:lotNumber xmlns:cbvmda="urn:epcglobal:cbv:mda">CHOP-01</cbvmda:lotNumber>
          <fsma:traceabilityLotCode xmlns:fsma="urn:fsma:food:traceability">00012345678901-CHOP01</fsma:traceabilityLotCode>
        </ilmd>
      </TransformationEvent>
    </EventList>
  </EPCISBody>
</epcis:EPCISDocument>"""


class TestXmlMixedDocument2970:
    def test_strict_mode_keeps_both_events(self, monkeypatch):
        # Pre-fix the action-less TransformationEvent failed
        # ``_validate_epcis`` and strict mode raised a whole-document
        # 422, so the valid ObjectEvent was lost with it.
        pytest.importorskip("lxml")
        monkeypatch.delenv("STRICT_FSMA_VALIDATION", raising=False)
        monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)

        from app.epcis.xml_parser import _parse_epcis_xml

        events = _parse_epcis_xml(_MIXED_XML)
        assert [e["type"] for e in events] == ["ObjectEvent", "TransformationEvent"]

        transformation = events[1]
        assert "action" not in transformation
        assert transformation["transformationID"] == "urn:uuid:8b4c2f1e-0f4b-4f8c-9a3e-3f0d2c1b7a55"
        assert _normalize_epcis_to_cte(transformation)["quantity"] == 250.0

    def test_xml_route_ingests_both_events(self, client: TestClient, monkeypatch):
        pytest.importorskip("lxml")
        monkeypatch.delenv("STRICT_FSMA_VALIDATION", raising=False)
        monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)

        # Stub the DB batch orchestrator (same pattern as
        # test_epcis_xml_strict_validation_1151) so the assertion is
        # about the strict-mode parse gate, not about Postgres.
        import app.epcis.router as router_mod

        forwarded: list[dict] = []

        def _fake_batch(tenant_id, events):
            forwarded.extend(events)
            return [
                (
                    {
                        "cte_id": f"fake-{i}",
                        "validation_status": "valid",
                        "kde_completeness": 1.0,
                        "alerts": [],
                        "idempotent": False,
                    },
                    201,
                )
                for i, _ in enumerate(events)
            ]

        monkeypatch.setattr(router_mod, "_ingest_batch_events_db_atomic", _fake_batch)

        response = client.post(
            "/api/v1/epcis/events/xml",
            headers={"X-Tenant-ID": TEST_TENANT_ID, "Content-Type": "application/xml"},
            content=_MIXED_XML,
        )
        assert response.status_code in (200, 201), response.text
        body = response.json()
        assert body.get("total") == 2
        assert body.get("created") == 2
        assert body.get("failed") == 0
        assert [e["type"] for e in forwarded] == ["ObjectEvent", "TransformationEvent"]
