"""POST /api/v1/ingest/csv with a Jev suggestion for a file that declares no CTE.

The upload UI never sends ``cte_type`` and RegEngine's own templates have no
CTE column, so a filled-in template uploaded from the UI has every row
rejected with "No CTE type". Contract pinned here:

* Not configured: byte-for-byte the old behaviour; the 400 body has no
  ``cte_type_suggestion`` and nothing leaves the process.
* Configured (advisory default): one question about the header row; the
  answer comes back in the 400 body (so the uploader can re-upload with it)
  and on the response, and rows are parsed exactly as before.
* ``REGENGINE_JEV_APPLY_FILE_CTE_TYPE``: an AUTO_APPLY-band answer naming
  one CTE becomes the file's fallback CTE, unless a row names another CTE,
  and is recorded as a reviewed ``field_mapping_suggestion`` artifact.
* A declared ``cte_type`` or a per-row CTE column means the question is not
  asked. Provider and evidence failures never change the upload's outcome.
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
from shared.jev.cte_classification import (
    CTE_NAMES,
    MIXED_OR_UNCLEAR,
    QUESTION_ID,
    QUESTIONS_VERSION,
    REVERSED_QUESTION_ID,
)
from shared.jev.header_mapping import NO_MATCH

TENANT = str(uuid.uuid4())
RUN_ID = str(uuid.uuid4())

# RegEngine's own receiving template, filled in: every column is one the
# parser reads, and there is no CTE column.
RECEIVING_TEMPLATE = ct._generate_csv_template("receiving").encode()


def _receiving_with(extra_header: str, value: str) -> bytes:
    """The receiving template with one unrecognised column appended to the header and example rows."""
    header, example, comment = ct._generate_csv_template("receiving").splitlines()[:3]
    return f"{header},{extra_header}\n{example},{value}\n{comment},\n".encode()


def _choice(choice: str, confidence: float, **others: float) -> dict:
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": {choice: confidence, **others},
    }


def _transport(
    file_cte: Optional[dict],
    columns: Optional[dict[str, dict]] = None,
    seen: Optional[dict] = None,
    status: int = 200,
) -> httpx2.MockTransport:
    """Answer the file-CTE question with ``file_cte`` and header questions from ``columns``."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if seen is not None:
            seen.setdefault("bodies", []).append(body)
        if status != 200:
            return httpx2.Response(status, text="down")
        answered = {}
        for question_id in body["questions"]:
            if question_id in (QUESTION_ID, REVERSED_QUESTION_ID):
                answered[question_id] = file_cte
            else:
                index = int(question_id.split("_")[1])
                answered[question_id] = (columns or {})[body["state"]["columns_to_map"][index]["header"]]
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_file_cte"},
            json={"model": "jev-1.14.0", "answers": answered, "usage": {"input_tokens": 90, "output_tokens": 1}},
        )

    return httpx2.MockTransport(handler)


def _decider(transport, **settings) -> JevDecider:
    base = {"api_key": "k", "max_retries": 0, "timeout_seconds": 1.0}
    base.update(settings)
    return JevDecider(JevSettings(**base), transport=transport)


def _cte_questions(seen: dict) -> list[dict]:
    return [body for body in seen.get("bodies", []) if QUESTION_ID in body["questions"]]


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


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_verify_api_key] = lambda: None
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="key-1", scopes=["*"], tenant_id=TENANT
    )
    return TestClient(app)


def _post(body: bytes = RECEIVING_TEMPLATE, data: Optional[dict] = None):
    # No cte_type form field unless a test adds one: what the upload UI sends.
    return _client().post(
        "/api/v1/ingest/csv",
        files={"file": ("receiving.csv", body, "text/csv")},
        data=data or {},
    )


# ---------------------------------------------------------------------------
# The gap, and not configured
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cte", sorted(CTE_NAMES))
def test_every_template_without_a_declared_cte_is_rejected_today(cte):
    events, errors, _ = ct.parse_csv_rows(ct._generate_csv_template(cte), None)
    assert events == []
    assert errors == ["Row 2: No CTE type — add cte_type column or pass cte_type param"]


def test_every_cte_jev_can_answer_is_one_the_parser_accepts():
    # Applying an answer the parser cannot resolve would reject every row.
    for name in CTE_NAMES:
        assert ct._CTE_TYPE_ALIASES[name] == name


def test_not_configured_changes_nothing_and_sends_nothing(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.99), seen=seen), api_key=None))

    resp = _post()

    assert resp.status_code == 400
    assert resp.json()["detail"] == {
        "message": "No valid rows found",
        "errors": ["Row 2: No CTE type — add cte_type column or pass cte_type param"],
    }
    assert "bodies" not in seen
    assert harness["payloads"] == [] and harness["artifacts"] == []


# ---------------------------------------------------------------------------
# Advisory (default when configured)
# ---------------------------------------------------------------------------


def test_advisory_answer_rides_the_400_so_the_uploader_can_re_upload_with_it(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.97, shipping=0.02), seen=seen)))

    resp = _post()

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["message"] == "No valid rows found"
    assert detail["errors"] == ["Row 2: No CTE type — add cte_type column or pass cte_type param"]
    assert detail["cte_type_suggestion"] == {
        "provider": "typesafe",
        "status": "ok",
        "cte_type": "receiving",
        "confidence": 0.97,
        "band": "auto_apply",
        "applied": False,
        "blocked_reason": "apply_disabled",
        "model": "jev-1.14.0",
        "request_id": "req_file_cte",
        "questions_version": QUESTIONS_VERSION,
        "apply_enabled": False,
        "artifacts_recorded": 0,
    }
    # Only the header row left the process: every template column is one the
    # parser knows, so the header mapping asked nothing.
    (sent,) = seen["bodies"]
    assert list(sent["questions"]) == [QUESTION_ID, REVERSED_QUESTION_ID]
    assert sent["state"] == {"csv_headers": RECEIVING_TEMPLATE.decode().splitlines()[0].split(",")}
    assert "TOM-0226-F3-001" not in json.dumps(sent)
    assert harness["payloads"] == [] and harness["artifacts"] == []


def test_re_uploading_with_the_suggested_cte_ingests_every_row(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.97), seen=seen)))

    resp = _post(data={"cte_type": "receiving"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 1 and body["rejected"] == 0
    # The uploader decided: nothing to ask and nothing to report.
    assert body["cte_type_suggestion"] is None
    assert _cte_questions(seen) == []


def test_advisory_answer_is_reported_on_a_partly_accepted_upload(harness):
    # "Activity" gives rows their own CTE once the header mapping applies it;
    # the file-CTE answer stays advisory and is reported with its artifact.
    columns = {"Activity": _choice("cte_type", 0.97, no_match=0.03)}
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.93), columns), apply_header_mappings=True))

    resp = _post(_receiving_with("Activity", "receiving"))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 1
    suggestion = body["cte_type_suggestion"]
    assert suggestion["cte_type"] == "receiving" and suggestion["applied"] is False
    assert suggestion["blocked_reason"] == "apply_disabled"
    assert suggestion["artifacts_recorded"] == 1
    cte_artifacts = [a for a in harness["artifacts"] if a.payload.source_field == "csv_file"]
    (artifact,) = cte_artifacts
    assert artifact.requires_human_review is True
    assert artifact.payload.target_canonical_field == "cte_type"
    assert artifact.payload.normalized_value == "receiving"


# ---------------------------------------------------------------------------
# Apply mode
# ---------------------------------------------------------------------------


def test_apply_mode_ingests_the_template_as_the_suggested_cte(harness):
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.97)), apply_file_cte_type=True))

    resp = _post()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 1 and body["rejected"] == 0
    (payload,) = harness["payloads"]
    assert [event.cte_type.value for event in payload.events] == ["receiving"]
    suggestion = body["cte_type_suggestion"]
    assert suggestion["applied"] is True and suggestion["blocked_reason"] is None
    assert suggestion["apply_enabled"] is True
    assert suggestion["artifacts_recorded"] == 1

    (artifact,) = harness["artifacts"]
    assert artifact.artifact_type == "field_mapping_suggestion"
    assert artifact.requires_human_review is False
    assert str(artifact.tenant_id) == TENANT
    assert str(artifact.context.ingestion_run_id) == RUN_ID
    assert artifact.payload.source_field == "csv_file"
    assert artifact.payload.target_canonical_field == "cte_type"
    assert artifact.payload.normalized_value == "receiving"
    assert harness["sessions"][-1].committed and harness["sessions"][-1].closed


@pytest.mark.parametrize(
    "answer,blocked",
    [
        (_choice("receiving", 0.80), "below_auto_apply_threshold"),
        (_choice(MIXED_OR_UNCLEAR, 0.95), MIXED_OR_UNCLEAR),
    ],
)
def test_apply_mode_leaves_uncertain_answers_advisory(harness, answer, blocked):
    harness["use_decider"](_decider(_transport(answer), apply_file_cte_type=True))

    resp = _post()

    assert resp.status_code == 400
    suggestion = resp.json()["detail"]["cte_type_suggestion"]
    assert suggestion["applied"] is False
    assert suggestion["blocked_reason"] == blocked
    assert harness["payloads"] == []


def test_apply_mode_never_overrides_a_cte_a_row_names(harness):
    # "Activity" holds a per-row CTE value that contradicts the answer: the
    # file CTE would be a fallback the rows argue with, so it is not applied.
    columns = {"Activity": _choice(NO_MATCH, 0.90, cte_type=0.10)}
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.97), columns), apply_file_cte_type=True))

    resp = _post(_receiving_with("Activity", "ship"))

    assert resp.status_code == 400
    suggestion = resp.json()["detail"]["cte_type_suggestion"]
    assert suggestion["cte_type"] == "receiving"
    assert suggestion["applied"] is False
    assert suggestion["blocked_reason"] == "row_values_contradict"
    assert harness["payloads"] == []


def test_apply_mode_keeps_a_cte_rows_agree_with(harness):
    columns = {"Activity": _choice(NO_MATCH, 0.90, cte_type=0.10)}
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.97), columns), apply_file_cte_type=True))

    resp = _post(_receiving_with("Activity", "receipt"))

    assert resp.status_code == 200, resp.text
    assert resp.json()["cte_type_suggestion"]["applied"] is True


def test_both_questions_are_asked_at_once_and_both_can_apply(harness):
    # "Lot #" hides the lot code from the parser and there is no CTE: only
    # with both answers applied does the row parse.
    header, example, _ = ct._generate_csv_template("receiving").splitlines()[:3]
    body = (header.replace("traceability_lot_code", "Lot #") + "\n" + example + "\n").encode()
    seen: dict = {}
    columns = {"Lot #": _choice("traceability_lot_code", 0.97, no_match=0.03)}
    harness["use_decider"](
        _decider(
            _transport(_choice("receiving", 0.97), columns, seen),
            apply_file_cte_type=True,
            apply_header_mappings=True,
        )
    )

    resp = _post(body)

    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["accepted"] == 1
    assert result["cte_type_suggestion"]["applied"] is True
    (mapping,) = result["header_mapping_suggestions"]
    assert mapping["applied"] is True
    # Three requests: the header mapping, its reversed-order check (the
    # mapping is about to change rows) and the file CTE with its twin.
    assert sorted(list(b["questions"]) for b in seen["bodies"]) == [
        ["col_0"],
        ["col_0"],
        [QUESTION_ID, REVERSED_QUESTION_ID],
    ]
    (payload,) = harness["payloads"]
    assert payload.events[0].traceability_lot_code == "TOM-0226-F3-001"
    assert payload.events[0].cte_type.value == "receiving"


# ---------------------------------------------------------------------------
# When the question is not asked
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("declared", ["receiving", "Receiving", " receive "])
def test_a_declared_cte_is_never_second_guessed(harness, declared):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(_choice("shipping", 0.99), seen=seen), apply_file_cte_type=True))

    resp = _post(data={"cte_type": declared})

    assert resp.status_code == 200, resp.text
    assert resp.json()["cte_type_suggestion"] is None
    assert _cte_questions(seen) == []
    (payload,) = harness["payloads"]
    assert payload.events[0].cte_type.value == "receiving"


@pytest.mark.parametrize("cte_header", ["cte_type", "Event Type", "CTE"])
def test_a_per_row_cte_column_is_not_asked_about(harness, cte_header):
    header, example, _ = ct._generate_csv_template("receiving").splitlines()[:3]
    body = f"{cte_header},{header}\nreceiving,{example}\n".encode()
    seen: dict = {}
    harness["use_decider"](_decider(_transport(_choice("shipping", 0.99), seen=seen), apply_file_cte_type=True))

    resp = _post(body)

    assert resp.status_code == 200, resp.text
    suggestion = resp.json()["cte_type_suggestion"]
    assert suggestion["status"] == "per_row_cte_column"
    assert suggestion["cte_type"] is None and suggestion["applied"] is False
    assert _cte_questions(seen) == []
    (payload,) = harness["payloads"]
    assert payload.events[0].cte_type.value == "receiving"


def test_an_over_long_header_is_never_sent_and_says_why(harness):
    # One header is longer than any real column name: probably row data.
    seen: dict = {}
    harness["use_decider"](_decider(_transport(_choice("shipping", 0.99), seen=seen), apply_file_cte_type=True))
    header, example, _ = ct._generate_csv_template("receiving").splitlines()[:3]

    resp = _post(f"{header},{'x' * 200}\n{example},\n".encode())

    assert resp.status_code == 400
    assert "bodies" not in seen
    suggestion = resp.json()["detail"]["cte_type_suggestion"]
    assert suggestion["status"] == "malformed_header"
    assert suggestion["cte_type"] is None and suggestion["applied"] is False


def test_a_header_row_that_swallows_rows_is_never_sent(harness):
    # An unterminated quote makes the "header" run into the rows below it.
    seen: dict = {}
    harness["use_decider"](_decider(_transport(_choice("shipping", 0.99), seen=seen), apply_file_cte_type=True))

    resp = _post(b'Lot,"Qty\nTLC-1,5,Farm\n')

    assert resp.status_code == 400
    assert resp.json()["detail"] == "CSV contained no data rows"
    assert "bodies" not in seen


# ---------------------------------------------------------------------------
# Failures never change the outcome
# ---------------------------------------------------------------------------


def test_provider_failure_leaves_the_upload_exactly_as_before(harness):
    harness["use_decider"](_decider(_transport(None, status=503), apply_file_cte_type=True))

    resp = _post()

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["errors"] == ["Row 2: No CTE type — add cte_type column or pass cte_type param"]
    suggestion = detail["cte_type_suggestion"]
    assert suggestion["status"] == "unavailable:server_error"
    assert suggestion["cte_type"] is None and suggestion["applied"] is False


def test_an_unexpected_error_is_contained(harness, monkeypatch):
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.99)), apply_file_cte_type=True))

    def explode(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(ct, "suggest_file_cte_type", explode)

    resp = _post()

    assert resp.status_code == 400
    assert resp.json()["detail"]["cte_type_suggestion"]["status"] == "error"


def test_evidence_failure_does_not_fail_an_applied_upload(harness):
    harness["queue_fails"] = True
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.97)), apply_file_cte_type=True))

    resp = _post()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 1
    assert body["cte_type_suggestion"]["applied"] is True
    assert body["cte_type_suggestion"]["artifacts_recorded"] == 0
    assert harness["sessions"][-1].rolled_back and harness["sessions"][-1].closed


def test_openapi_advertises_the_suggestion_as_optional():
    schema = _client().get("/openapi.json").json()["components"]["schemas"]
    response = schema["CsvIngestResponse"]
    assert "cte_type_suggestion" in response["properties"]
    assert "cte_type_suggestion" not in response.get("required", [])
    assert set(schema["CteTypeSuggestionResult"]["required"]) == {"status"}


def test_confidence_float_noise_never_turns_the_response_into_a_500(harness):
    # The SDK does not bound confidence; the response model does.
    harness["use_decider"](_decider(_transport(_choice("receiving", 1.0000001)), apply_file_cte_type=True))

    resp = _post()

    assert resp.status_code == 200, resp.text
    suggestion = resp.json()["cte_type_suggestion"]
    assert suggestion["confidence"] == 1.0
    assert suggestion["applied"] is True


def test_column_suggestions_ride_the_400_too(harness):
    # "Lot #" hides the lot code from the parser: the uploader needs to know
    # which column Jev thinks it is, as well as which CTE the file records.
    header, example, _ = ct._generate_csv_template("receiving").splitlines()[:3]
    body = (header.replace("traceability_lot_code", "Lot #") + "\n" + example + "\n").encode()
    columns = {"Lot #": _choice("traceability_lot_code", 0.97, no_match=0.03)}
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.97), columns)))

    resp = _post(body, data={"cte_type": "receiving"})

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "cte_type_suggestion" not in detail
    (suggestion,) = detail["header_mapping_suggestions"]
    assert suggestion["source_header"] == "Lot #"
    assert suggestion["canonical_field"] == "traceability_lot_code"
    assert suggestion["band"] == "auto_apply"
    assert suggestion["applied"] is False and suggestion["blocked_reason"] == "apply_disabled"


def test_no_column_suggestions_key_without_jev(harness):
    header, example, _ = ct._generate_csv_template("receiving").splitlines()[:3]
    body = (header.replace("traceability_lot_code", "Lot #") + "\n" + example + "\n").encode()
    harness["use_decider"](_decider(_transport(_choice("receiving", 0.97)), api_key=None))

    resp = _post(body, data={"cte_type": "receiving"})

    assert resp.status_code == 400
    assert "header_mapping_suggestions" not in resp.json()["detail"]
