"""POST /api/v1/ingest/csv with TypeSafe Jev header-mapping suggestions.

Contract pinned here:

* Not configured: the route is byte-for-byte the old behaviour apart from
  an empty ``header_mapping_suggestions`` list and a null
  ``header_mapping_engine``; nothing leaves the process.
* Configured (advisory default): unrecognised headers are sent once per
  upload, suggestions come back on the response, each actionable one is
  queued as a ``field_mapping_suggestion`` artifact requiring review, and
  rows are parsed exactly as before.
* ``REGENGINE_JEV_APPLY_HEADER_MAPPINGS``: AUTO_APPLY-band mappings are
  copied onto rows before parsing, and their artifacts are recorded as
  reviewed.
* Provider or evidence failures never reject an upload.
* Every canonical field Jev can name is a column the parser reads.
"""

from __future__ import annotations

import json
import uuid
from typing import Optional

import httpx2
import pytest
from app import csv_templates as ct
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.csv_templates import router
from app.webhook_compat import _verify_api_key
from app.webhook_models import EventResult, IngestResponse
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.jev import JevDecider, JevSettings
from shared.jev.header_mapping import CANONICAL_FIELD_NAMES, NO_MATCH

TENANT = str(uuid.uuid4())
RUN_ID = str(uuid.uuid4())

# "Lot #" is not a column the parser knows, so without a mapping rows 2-3
# have no traceability lot code and are rejected by the IngestEvent schema.
# Row 4 carries its lot code in the recognised ``tlc`` alias and parses on
# its own, which keeps the upload from being rejected outright.
CSV_BODY = (
    "Lot #,tlc,product_description,quantity,unit_of_measure,harvest_date,location_name,reference_document,Notes\n"
    "TLC-001,,Kale,10,lbs,2026-04-17,Farm A,REF-1,call 555-123-4567\n"
    "TLC-002,,Chard,5,lbs,2026-04-17,Farm A,REF-2,\n"
    ",TLC-003,Beet,7,lbs,2026-04-17,Farm A,REF-3,\n"
).encode()


def _choice(choice: str, confidence: float, **others: float) -> dict:
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": {choice: confidence, **others},
    }


DEFAULT_ANSWERS = {
    "Lot #": _choice("traceability_lot_code", 0.97, no_match=0.03),
    "Notes": _choice(NO_MATCH, 0.98, carrier=0.02),
}


def _transport(answers: dict[str, dict], seen: Optional[dict] = None, status: int = 200) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if seen is not None:
            seen.setdefault("bodies", []).append(body)
        if status != 200:
            return httpx2.Response(status, text="down")
        answered = {}
        for question_id in body["questions"]:
            index = int(question_id.split("_")[1])
            answered[question_id] = answers[body["state"]["columns_to_map"][index]["header"]]
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_csv"},
            json={"model": "jev-1.13.0", "answers": answered, "usage": {"input_tokens": 100, "output_tokens": 2}},
        )

    return httpx2.MockTransport(handler)


class _FakeSession:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


@pytest.fixture
def harness(monkeypatch):
    """Route harness with faked ingestion, evidence queue, and a pluggable Jev decider."""
    state: dict = {"payloads": [], "artifacts": [], "sessions": []}

    async def _fake_ingest(payload, **kwargs):
        state["payloads"].append(payload)
        return IngestResponse(
            accepted=len(payload.events),
            rejected=0,
            total=len(payload.events),
            events=[
                EventResult(traceability_lot_code=e.traceability_lot_code, cte_type=e.cte_type.value, status="accepted")
                for e in payload.events
            ],
            ingestion_run_id=RUN_ID,
        )

    def _fake_enqueue(session, artifact, **kwargs):
        if getattr(session, "fail", False):
            raise RuntimeError("queue down")
        state["artifacts"].append(artifact)
        return len(state["artifacts"])

    def _fake_session_factory():
        session = _FakeSession(fail=state.get("queue_fails", False))
        state["sessions"].append(session)
        return session

    monkeypatch.setattr(ct, "ingest_events", _fake_ingest)
    monkeypatch.setattr(ct, "enqueue_agent_artifact_task", _fake_enqueue)
    monkeypatch.setattr(ct, "SessionLocal", _fake_session_factory)
    monkeypatch.setattr(ct, "set_tenant_guc", lambda session, tenant_id: None)

    def use_decider(decider: JevDecider) -> None:
        monkeypatch.setattr(ct, "get_jev_decider", lambda: decider)

    state["use_decider"] = use_decider
    return state


def _client(tenant: Optional[str] = TENANT) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="key-1", scopes=["*"], tenant_id=tenant
    )
    return TestClient(app)


def _post(client: TestClient, body: bytes = CSV_BODY):
    return client.post(
        "/api/v1/ingest/csv",
        files={"file": ("supplier.csv", body, "text/csv")},
        data={"cte_type": "harvesting"},
    )


def _decider(transport, **settings) -> JevDecider:
    base = {"api_key": "k", "max_retries": 0, "timeout_seconds": 1.0}
    base.update(settings)
    return JevDecider(JevSettings(**base), transport=transport)


# ---------------------------------------------------------------------------
# Not configured
# ---------------------------------------------------------------------------


def test_not_configured_changes_nothing_and_sends_nothing(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS, seen), api_key=None))

    resp = _post(_client())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["header_mapping_suggestions"] == []
    assert body["header_mapping_engine"] is None
    assert "bodies" not in seen
    assert harness["artifacts"] == []
    # Without a mapping only the ``tlc`` row parses; the "Lot #" rows are rejected as before.
    assert body["accepted"] == 1 and body["rejected"] == 2
    (payload,) = harness["payloads"]
    assert [e.traceability_lot_code for e in payload.events] == ["TLC-003"]


# ---------------------------------------------------------------------------
# Advisory (default when configured)
# ---------------------------------------------------------------------------


def test_advisory_mode_suggests_records_and_leaves_rows_alone(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS, seen)))

    resp = _post(_client())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Only the header row left the process, and only unrecognised columns were asked about.
    assert len(seen["bodies"]) == 1
    sent = seen["bodies"][0]
    assert [c["header"] for c in sent["state"]["columns_to_map"]] == ["Lot #", "Notes"]
    assert all("sample_values" not in c for c in sent["state"]["columns_to_map"])
    assert "TLC-001" not in json.dumps(sent)

    suggestions = {s["source_header"]: s for s in body["header_mapping_suggestions"]}
    assert suggestions["Lot #"]["canonical_field"] == "traceability_lot_code"
    assert suggestions["Lot #"]["band"] == "auto_apply"
    assert suggestions["Lot #"]["applied"] is False
    assert suggestions["Lot #"]["blocked_reason"] == "apply_disabled"
    assert suggestions["Notes"]["canonical_field"] is None

    engine = body["header_mapping_engine"]
    assert engine["provider"] == "typesafe"
    assert engine["status"] == "ok"
    assert engine["model"] == "jev-1.13.0"
    assert engine["request_id"] == "req_csv"
    assert engine["apply_enabled"] is False
    assert engine["artifacts_recorded"] == 1

    # Evidence: one advisory artifact, anchored to the run and the upload hash, requiring review.
    (artifact,) = harness["artifacts"]
    assert artifact.artifact_type == "field_mapping_suggestion"
    assert str(artifact.tenant_id) == TENANT
    assert artifact.requires_human_review is True
    assert str(artifact.context.ingestion_run_id) == RUN_ID
    assert len(artifact.context.source_hashes) == 1
    assert harness["sessions"][0].committed and harness["sessions"][0].closed

    # Rows were parsed exactly as before: the "Lot #" rows still have no lot code.
    assert body["accepted"] == 1 and body["rejected"] == 2
    (payload,) = harness["payloads"]
    assert [e.traceability_lot_code for e in payload.events] == ["TLC-003"]


# ---------------------------------------------------------------------------
# Apply mode
# ---------------------------------------------------------------------------


def test_apply_mode_maps_the_column_and_records_reviewed_evidence(harness):
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS), apply_header_mappings=True))

    resp = _post(_client())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 3 and body["rejected"] == 0
    (payload,) = harness["payloads"]
    assert [e.traceability_lot_code for e in payload.events] == ["TLC-001", "TLC-002", "TLC-003"]
    # The source column still reaches the KDEs: nothing is dropped from the evidence trail.
    assert payload.events[0].kdes["lot_#"] == "TLC-001"
    assert payload.events[0].kdes["traceability_lot_code"] == "TLC-001"
    # The row that already had a lot code is untouched by the mapping.
    assert "lot_#" not in payload.events[2].kdes

    suggestion = next(s for s in body["header_mapping_suggestions"] if s["source_header"] == "Lot #")
    assert suggestion["applied"] is True and suggestion["blocked_reason"] is None
    assert body["header_mapping_engine"]["apply_enabled"] is True

    (artifact,) = harness["artifacts"]
    assert artifact.requires_human_review is False
    assert "applied" in artifact.suggestion


def test_sample_values_are_sent_only_when_configured_and_are_redacted(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS, seen), header_sample_values=2))

    resp = _post(_client())

    assert resp.status_code == 200, resp.text
    columns = {c["header"]: c for c in seen["bodies"][0]["state"]["columns_to_map"]}
    assert columns["Lot #"]["sample_values"] == ["TLC-001", "TLC-002"]
    assert columns["Notes"]["sample_values"] == ["call [PHONE_REDACTED]"]
    assert "555-123-4567" not in json.dumps(seen["bodies"][0])


# ---------------------------------------------------------------------------
# Failure isolation
# ---------------------------------------------------------------------------


def test_provider_outage_does_not_affect_the_upload(harness):
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS, status=503), apply_header_mappings=True))

    resp = _post(_client())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["header_mapping_suggestions"] == []
    assert body["header_mapping_engine"]["status"] == "unavailable:server_error"
    assert body["header_mapping_engine"]["artifacts_recorded"] == 0
    assert harness["artifacts"] == []
    assert body["accepted"] == 1 and body["rejected"] == 2


def test_evidence_queue_failure_is_logged_not_raised(harness, caplog):
    harness["queue_fails"] = True
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS)))

    with caplog.at_level("ERROR", logger="csv-templates"):
        resp = _post(_client())

    assert resp.status_code == 200, resp.text
    assert resp.json()["header_mapping_engine"]["artifacts_recorded"] == 0
    assert harness["sessions"][0].rolled_back and harness["sessions"][0].closed
    assert any("csv_header_mapping_evidence_failed" in record.getMessage() for record in caplog.records)


def test_non_uuid_tenant_skips_evidence_gracefully(harness):
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS)))

    resp = _post(_client(tenant="t1"))

    assert resp.status_code == 200, resp.text
    assert resp.json()["header_mapping_engine"]["artifacts_recorded"] == 0
    assert harness["artifacts"] == []


def test_no_unrecognized_headers_makes_no_request(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS, seen)))
    clean = (
        "traceability_lot_code,product_description,quantity,unit_of_measure,harvest_date,location_name,reference_document\n"
        "TLC-001,Kale,10,lbs,2026-04-17,Farm A,REF-1\n"
    ).encode()

    resp = _post(_client(), clean)

    assert resp.status_code == 200, resp.text
    assert "bodies" not in seen
    assert resp.json()["header_mapping_engine"]["status"] == "no_unrecognized_headers"
    assert resp.json()["accepted"] == 1


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_schema_documents_the_new_fields_as_optional():
    spec = _client().app.openapi()
    content = spec["paths"]["/api/v1/ingest/csv"]["post"]["responses"]["200"]["content"]
    ref = content["application/json"]["schema"]["$ref"]
    schema = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    assert "header_mapping_suggestions" in schema["properties"]
    assert "header_mapping_engine" in schema["properties"]
    assert "header_mapping_suggestions" not in schema.get("required", [])
    assert "header_mapping_engine" not in schema.get("required", [])


def test_every_canonical_field_is_a_column_the_parser_reads():
    """Applying a mapping to a column nobody reads would be theatre."""
    assert CANONICAL_FIELD_NAMES <= ct._RECOGNIZED_COLUMNS


def test_parse_csv_rows_default_is_unchanged():
    text = CSV_BODY.decode()
    events, errors, _ = ct.parse_csv_rows(text, "harvesting")
    assert [e.traceability_lot_code for e in events] == ["TLC-003"] and len(errors) == 2
    mapped_events, mapped_errors, _ = ct.parse_csv_rows(
        text, "harvesting", header_mapping={"lot_#": "traceability_lot_code"}
    )
    assert [e.traceability_lot_code for e in mapped_events] == ["TLC-001", "TLC-002", "TLC-003"]
    assert mapped_errors == []
