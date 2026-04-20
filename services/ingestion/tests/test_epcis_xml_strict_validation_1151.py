"""Regression tests for #1151 — EPCIS XML strict FSMA validation gate.

Locks in the contract established by the fix:

* ``_parse_epcis_xml`` now invokes ``_validate_epcis`` on every extracted
  event and, when ``STRICT_FSMA_VALIDATION`` is truthy (default), raises
  ``HTTPException(422)`` with a per-index error map. Lenient mode
  (``STRICT_FSMA_VALIDATION=false``) logs a WARNING per invalid event
  and preserves the pre-fix advisory flow so FDA/SMB tenants can still
  onboard.
* ``_ingest_single_event_db`` refuses to persist an event whose
  FSMAEvent validation is missing. In strict mode it raises
  ``ValueError("E_EPCIS_UNVALIDATED")`` — a code-level sentinel that the
  HTTP edge translates to 422.

The four tests below correspond one-to-one with the acceptance checklist
on the issue:

1. ``test_invalid_event_rejected_in_strict_mode``
2. ``test_all_valid_events_still_accepted``
3. ``test_lenient_mode_still_persists_with_warning``
4. ``test_persistence_refuses_unvalidated_in_strict_mode``
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


TEST_TENANT_ID = "00000000-0000-0000-0000-000000000abc"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """Same pattern as the other EPCIS test modules: mount the router on a
    fresh FastAPI app and short-circuit the api-key dependency so the
    tests can focus on validation behaviour."""
    from app.epcis.router import router
    from app.webhook_compat import _verify_api_key

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    return TestClient(app)


def _valid_epcis_xml() -> bytes:
    """A full, FSMA-valid ObjectEvent in EPCIS 2.0 XML.

    Has all four structurally required fields (``type``, ``eventTime``,
    ``action``, ``bizStep``) plus an ILMD block with a TLC — satisfies
    ``_validate_epcis`` + downstream FSMA / quantity gates.
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


def _xml_missing_required_field() -> bytes:
    """ObjectEvent missing ``bizStep`` — fails ``_validate_epcis``.

    NOTE: XML comments cannot contain double-hyphens, so we simply omit
    the field without an inline explanatory comment.
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


# ---------------------------------------------------------------------------
# 1. Invalid event rejected in strict mode (default)
# ---------------------------------------------------------------------------


def test_invalid_event_rejected_in_strict_mode(client, monkeypatch):
    """Strict mode (default) — a missing FSMA field MUST surface as 422
    with a per-event error keyed by index. Pre-fix, the event was
    silently persisted with a compliance alert."""
    monkeypatch.delenv("STRICT_FSMA_VALIDATION", raising=False)
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)

    resp = client.post(
        "/api/v1/epcis/events/xml",
        headers={
            "X-Tenant-ID": TEST_TENANT_ID,
            "Content-Type": "application/xml",
        },
        content=_xml_missing_required_field(),
    )
    assert resp.status_code == 422
    payload = resp.json()
    detail = payload.get("detail", payload)
    assert detail.get("error") == "epcis_xml_validation_failed"
    errors = detail.get("errors", [])
    assert len(errors) == 1, "Expected a per-index error entry"
    assert errors[0]["index"] == 0
    per_event_errors = errors[0].get("errors", [])
    # The specific missing field should appear in the per-event error list.
    assert any("bizStep" in msg for msg in per_event_errors), (
        f"Expected 'bizStep' in per-event errors, got {per_event_errors}"
    )


# ---------------------------------------------------------------------------
# 2. Baseline — valid events still accepted
# ---------------------------------------------------------------------------


def test_all_valid_events_still_accepted(client, monkeypatch):
    """A well-formed, FSMA-complete XML document MUST still succeed.
    The strict-validation gate is surgical — it only blocks malformed
    events, not happy-path traffic."""
    monkeypatch.delenv("STRICT_FSMA_VALIDATION", raising=False)
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)

    # Short-circuit downstream DB work so this test is self-contained
    # (no Postgres needed). We stub the atomic batch orchestrator to
    # return a plain success envelope, which is what it would return
    # for a valid event once persistence commits.
    import app.epcis.router as router_mod

    def _fake_batch(tenant_id, events):
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

    monkeypatch.setattr(
        router_mod, "_ingest_batch_events_db_atomic", _fake_batch
    )

    resp = client.post(
        "/api/v1/epcis/events/xml",
        headers={
            "X-Tenant-ID": TEST_TENANT_ID,
            "Content-Type": "application/xml",
        },
        content=_valid_epcis_xml(),
    )
    assert resp.status_code in (200, 201), (
        f"Expected 200/201 on all-valid payload, got {resp.status_code}: "
        f"{resp.text}"
    )
    body = resp.json()
    assert body.get("total") == 1
    assert body.get("created") == 1
    assert body.get("failed") == 0


# ---------------------------------------------------------------------------
# 3. Lenient mode — persists with warning
# ---------------------------------------------------------------------------


def test_lenient_mode_still_persists_with_warning(client, monkeypatch, caplog):
    """With ``STRICT_FSMA_VALIDATION=false`` an event that would fail
    validation in strict mode is still threaded through to persistence.
    A WARNING is emitted per invalid event so operators see the defect
    in their logs / Sentry without losing the inbound data."""
    monkeypatch.setenv("STRICT_FSMA_VALIDATION", "false")
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)

    # Stub the persistence layer so we don't need a real DB. In lenient
    # mode the batch orchestrator is still invoked on the extracted
    # events; we assert the parse did NOT raise 422.
    import app.epcis.router as router_mod

    captured_events: list[dict] = []

    def _fake_batch(tenant_id, events):
        captured_events.extend(events)
        return [
            (
                {
                    "cte_id": f"fake-{i}",
                    "validation_status": "warning",
                    "kde_completeness": 0.5,
                    "alerts": [
                        {
                            "severity": "warning",
                            "alert_type": "fsma_validation",
                            "message": "lenient-mode passthrough",
                        }
                    ],
                    "idempotent": False,
                },
                201,
            )
            for i, _ in enumerate(events)
        ]

    monkeypatch.setattr(
        router_mod, "_ingest_batch_events_db_atomic", _fake_batch
    )

    with caplog.at_level(logging.WARNING, logger="epcis-ingestion"):
        resp = client.post(
            "/api/v1/epcis/events/xml",
            headers={
                "X-Tenant-ID": TEST_TENANT_ID,
                "Content-Type": "application/xml",
            },
            content=_xml_missing_required_field(),
        )

    # Lenient mode does NOT 422 at parse — the event is passed to the
    # downstream orchestrator so the legacy onboarding flow still works.
    assert resp.status_code != 422, (
        "Lenient mode should not 422 at parse time"
    )
    # A WARNING must have been emitted per invalid event.
    warning_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    assert any(
        "epcis_xml_event_validation_failed_lenient" in msg
        for msg in warning_messages
    ), (
        "Expected a 'lenient' warning log per invalid event. "
        f"Got warnings: {warning_messages}"
    )
    # The event was forwarded to the persistence layer (not silently
    # dropped from the event list).
    assert len(captured_events) == 1, (
        "Lenient mode must still forward the event to persistence"
    )


# ---------------------------------------------------------------------------
# 4. Persistence-layer guard — refuse unvalidated in strict mode
# ---------------------------------------------------------------------------


def test_persistence_refuses_unvalidated_in_strict_mode(monkeypatch):
    """``_ingest_single_event_db`` must raise ``ValueError`` with the
    sentinel code ``E_EPCIS_UNVALIDATED`` when ``_validate_as_fsma_event``
    returns ``None`` and strict mode is on (or unset → default strict).
    This is the last-line defence against a caller that bypasses the
    parse gate but still hits the DB path."""
    import app.epcis.persistence as persistence_mod

    # Ensure strict mode is on (default when both env vars unset).
    monkeypatch.delenv("STRICT_FSMA_VALIDATION", raising=False)
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)

    # Force FSMAEvent validation to fail so ``fsma_validated`` is None.
    monkeypatch.setattr(
        persistence_mod, "_validate_as_fsma_event", lambda normalized, tenant: None
    )

    valid_event = {
        "type": "ObjectEvent",
        "eventTime": "2026-04-18T09:30:00Z",
        "action": "OBSERVE",
        "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
        "epcList": ["urn:epc:id:sgtin:0614141.107346.1"],
        "ilmd": {
            "fsma:traceabilityLotCode": "00012345678901-ROM0042",
            "cbvmda:lotNumber": "ROM-0042",
        },
        "extension": {
            "quantityList": [
                {
                    "epcClass": "urn:epc:class:lgtin:0614141.107346.ROM0042",
                    "quantity": 10.0,
                    "uom": "CS",
                }
            ]
        },
    }

    with pytest.raises(ValueError) as exc_info:
        persistence_mod._ingest_single_event_db(TEST_TENANT_ID, valid_event)
    assert str(exc_info.value) == "E_EPCIS_UNVALIDATED"


def test_persistence_refuses_unvalidated_also_with_strict_validation_env(
    monkeypatch,
):
    """Dual-alias coverage: the new ``STRICT_FSMA_VALIDATION`` env var
    alone (without ``FSMA_STRICT_MODE``) must also enable the guard."""
    import app.epcis.persistence as persistence_mod

    monkeypatch.setenv("STRICT_FSMA_VALIDATION", "true")
    monkeypatch.delenv("FSMA_STRICT_MODE", raising=False)
    monkeypatch.setattr(
        persistence_mod, "_validate_as_fsma_event", lambda normalized, tenant: None
    )

    valid_event = {
        "type": "ObjectEvent",
        "eventTime": "2026-04-18T09:30:00Z",
        "action": "OBSERVE",
        "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
        "epcList": ["urn:epc:id:sgtin:0614141.107346.1"],
        "ilmd": {
            "fsma:traceabilityLotCode": "00012345678901-ROM0042",
            "cbvmda:lotNumber": "ROM-0042",
        },
        "extension": {
            "quantityList": [
                {
                    "epcClass": "urn:epc:class:lgtin:0614141.107346.ROM0042",
                    "quantity": 10.0,
                    "uom": "CS",
                }
            ]
        },
    }

    with pytest.raises(ValueError, match="E_EPCIS_UNVALIDATED"):
        persistence_mod._ingest_single_event_db(TEST_TENANT_ID, valid_event)
