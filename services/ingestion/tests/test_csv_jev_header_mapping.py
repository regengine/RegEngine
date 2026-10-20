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

import asyncio
import collections
import csv
import json
import threading
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
from shared.jev.header_mapping import CANONICAL_FIELD_NAMES, NO_MATCH, normalize_csv_header, outranked_columns

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

# The same upload without the ``tlc`` column: nothing in the file competes
# with a mapped lot code, so apply mode may act on every row.
CSV_BODY_NO_ALIAS = (
    "Lot #,product_description,quantity,unit_of_measure,harvest_date,location_name,reference_document,Notes\n"
    "TLC-001,Kale,10,lbs,2026-04-17,Farm A,REF-1,call 555-123-4567\n"
    "TLC-002,Chard,5,lbs,2026-04-17,Farm A,REF-2,\n"
    "TLC-003,Beet,7,lbs,2026-04-17,Farm A,REF-3,\n"
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
            json={"model": "jev-1.14.0", "answers": answered, "usage": {"input_tokens": 100, "output_tokens": 2}},
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


def _post(client: TestClient, body: bytes = CSV_BODY, data: Optional[dict] = None):
    return client.post(
        "/api/v1/ingest/csv",
        files={"file": ("supplier.csv", body, "text/csv")},
        data={"cte_type": "harvesting"} if data is None else data,
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
    assert engine["model"] == "jev-1.14.0"
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
# Declared CTE as context
# ---------------------------------------------------------------------------

# A single-type shipping file whose extra headers only make sense once you
# know every row is a shipment.
SHIPPING_CSV_BODY = (
    "traceability_lot_code,product_description,quantity,unit_of_measure,ship_date,"
    "ship_from_location,ship_to_location,reference_document,tlc_source_reference,Ship Dt,Qty Shpd\n"
    "TLC-S1,Romaine,120,cases,2026-09-21,Packhouse A,DC B,BOL-1,PACK-1,09/21/2026,120\n"
).encode()

SHIPPING_ANSWERS = {
    "Ship Dt": _choice("ship_date", 0.95, event_date=0.05),
    "Qty Shpd": _choice("quantity", 0.93, no_match=0.07),
}

# No form field: each row names its own CTE.
MIXED_CSV_BODY = (
    "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,event_date,location_name,Notes\n"
    "harvesting,TLC-H1,Kale,10,lbs,2026-04-17,Farm A,\n"
    "shipping,TLC-S1,Kale,10,lbs,2026-04-18,Farm A,\n"
).encode()


@pytest.mark.parametrize("declared", ["Shipping", " ship ", "SHIPPING"])
def test_declared_cte_type_is_sent_to_jev_normalised(harness, declared):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(SHIPPING_ANSWERS, seen)))

    resp = _post(_client(), SHIPPING_CSV_BODY, data={"cte_type": declared})

    assert resp.status_code == 200, resp.text
    (sent,) = seen["bodies"]
    assert sent["state"]["file_cte_type"] == "shipping"
    assert [c["header"] for c in sent["state"]["columns_to_map"]] == ["Ship Dt", "Qty Shpd"]
    assert resp.json()["header_mapping_engine"]["questions_version"] == "csv-header-mapping.v3"
    # The evidence records what Jev was told, next to the question-set version.
    assert len(harness["artifacts"]) == 2
    for artifact in harness["artifacts"]:
        assert "(csv-header-mapping.v3)" in artifact.payload.rationale
        assert "State file_cte_type: shipping." in artifact.payload.rationale


def _per_row_cte_body(cte_header: str) -> bytes:
    """A shipping upload that also names each row's CTE in ``cte_header``.

    Row 1 says ``receiving``; row 2 leaves it blank and falls back to the
    declared CTE. The declared CTE is therefore false for row 1.
    """
    return (
        f"{cte_header},traceability_lot_code,product_description,quantity,unit_of_measure,ship_date,"
        "ship_from_location,ship_to_location,reference_document,tlc_source_reference,Ship Dt,Qty Shpd\n"
        "receiving,TLC-R1,Romaine,120,cases,2026-09-21,Packhouse A,DC B,BOL-1,PACK-1,09/21/2026,120\n"
        ",TLC-S1,Romaine,120,cases,2026-09-21,Packhouse A,DC B,BOL-2,PACK-2,09/21/2026,120\n"
    ).encode()


@pytest.mark.parametrize("cte_header", ["cte_type", "Event Type", "CTE", " Type "])
def test_declared_cte_type_is_withheld_when_rows_carry_their_own(harness, cte_header):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(SHIPPING_ANSWERS, seen)))

    resp = _post(_client(), _per_row_cte_body(cte_header), data={"cte_type": "Shipping"})

    assert resp.status_code == 200, resp.text
    (sent,) = seen["bodies"]
    assert set(sent["state"]) == {"csv_headers", "columns_to_map"}
    # Why it was withheld: the parser really does let the row win.
    (payload,) = harness["payloads"]
    assert [e.cte_type.value for e in payload.events] == ["receiving", "shipping"]
    assert harness["artifacts"]
    reason = f"file has a per-row CTE column: {cte_header.strip()}"
    for artifact in harness["artifacts"]:
        assert f"State file_cte_type: none (declared CTE withheld: {reason})." in artifact.payload.rationale


# ---------------------------------------------------------------------------
# A row's own CTE beats the declared file CTE (parser precedence)
# ---------------------------------------------------------------------------

_SHIP_COLUMNS = (
    "traceability_lot_code,product_description,quantity,unit_of_measure,ship_date,"
    "ship_from_location,ship_to_location,reference_document,tlc_source_reference"
)


def _extra_column_body(header: str, *values: str) -> bytes:
    """A shipping upload with one unrecognised ``header`` column holding ``values``, one per row."""
    rows = "".join(
        f"{value},TLC-A{index},Romaine,120,cases,2026-09-21,Packhouse A,DC B,BOL-{index},PACK-{index}\n"
        for index, value in enumerate(values, start=1)
    )
    return f"{header},{_SHIP_COLUMNS}\n{rows}".encode()


# The worst case for the invariant: Jev maps every column it is asked about
# onto cte_type with auto-apply confidence.
EVERYTHING_IS_CTE = collections.defaultdict(lambda: _choice("cte_type", 0.97, no_match=0.03))

FALLBACK_NOTE = "remains the fallback for rows where this column is blank or not a known CTE; per-row values"


@pytest.mark.parametrize("header", ["Activity", "Event Kind", "Event-Type", "Transaction Type"])
def test_other_cte_values_in_an_unrecognised_column_withhold_the_declared_cte(harness, header):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(EVERYTHING_IS_CTE, seen), apply_header_mappings=True))

    resp = _post(_client(), _extra_column_body(header, "receiving", "shipping"), data={"cte_type": "Shipping"})

    assert resp.status_code == 200, resp.text
    assert "file_cte_type" not in seen["bodies"][0]["state"]
    # The mapping applies exactly as it does without a declared CTE: each
    # row's own CTE wins, as it would under an "Event Type" header.
    (suggestion,) = resp.json()["header_mapping_suggestions"]
    assert suggestion["canonical_field"] == "cte_type"
    assert suggestion["applied"] is True and suggestion["blocked_reason"] is None
    (payload,) = harness["payloads"]
    assert [e.cte_type.value for e in payload.events] == ["receiving", "shipping"]
    (artifact,) = harness["artifacts"]
    rationale = artifact.payload.rationale
    assert f"declared CTE withheld: column {header} holds per-row CTE values" in rationale
    assert f"The declared file CTE {FALLBACK_NOTE} from this column override it." in rationale


def test_unrecognised_column_agreeing_with_the_declared_cte_keeps_it(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(EVERYTHING_IS_CTE, seen), apply_header_mappings=True))

    resp = _post(_client(), _extra_column_body("Activity", "shipping", "S", "Ship"), data={"cte_type": "Shipping"})

    assert resp.status_code == 200, resp.text
    assert seen["bodies"][0]["state"]["file_cte_type"] == "shipping"
    (suggestion,) = resp.json()["header_mapping_suggestions"]
    assert suggestion["applied"] is True
    (payload,) = harness["payloads"]
    assert [e.cte_type.value for e in payload.events] == ["shipping", "shipping", "shipping"]
    (artifact,) = harness["artifacts"]
    assert "State file_cte_type: shipping." in artifact.payload.rationale
    assert f"The declared file CTE shipping {FALLBACK_NOTE} from this column override it." in artifact.payload.rationale


def test_free_text_in_an_unrecognised_column_keeps_the_declared_cte_as_fallback(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(EVERYTHING_IS_CTE, seen), apply_header_mappings=True))

    resp = _post(_client(), _extra_column_body("Activity", "load dock 4", ""), data={"cte_type": "Shipping"})

    assert resp.status_code == 200, resp.text
    assert seen["bodies"][0]["state"]["file_cte_type"] == "shipping"
    (suggestion,) = resp.json()["header_mapping_suggestions"]
    assert suggestion["applied"] is True
    # "load dock 4" is copied under cte_type but is not a known CTE, so the
    # parser falls back to the declared one; the source column stays in kdes.
    (payload,) = harness["payloads"]
    assert [e.cte_type.value for e in payload.events] == ["shipping", "shipping"]
    assert payload.events[0].kdes["activity"] == "load dock 4"


def test_single_letter_aliases_withhold_the_declared_cte_conservatively(harness):
    # "R" is an alias of receiving in _CTE_TYPE_ALIASES, so a "Grade" column of
    # S and R could become per-row CTEs if Jev mapped it. Withholding costs Jev
    # only a hint, so the scan errs that way.
    seen: dict = {}
    harness["use_decider"](_decider(_transport({"Grade": _choice(NO_MATCH, 0.95)}, seen)))

    resp = _post(_client(), _extra_column_body("Grade", "S", "R"), data={"cte_type": "Shipping"})

    assert resp.status_code == 200, resp.text
    assert "file_cte_type" not in seen["bodies"][0]["state"]
    (payload,) = harness["payloads"]
    assert [e.cte_type.value for e in payload.events] == ["shipping", "shipping"]


def test_without_a_declared_cte_the_cte_mapping_applies_as_before(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(EVERYTHING_IS_CTE, seen), apply_header_mappings=True))

    resp = _post(_client(), _extra_column_body("Activity", "receiving", "shipping"), data={})

    assert resp.status_code == 200, resp.text
    assert "file_cte_type" not in seen["bodies"][0]["state"]
    (suggestion,) = resp.json()["header_mapping_suggestions"]
    assert suggestion["applied"] is True and suggestion["blocked_reason"] is None
    (payload,) = harness["payloads"]
    assert [e.cte_type.value for e in payload.events] == ["receiving", "shipping"]
    (artifact,) = harness["artifacts"]
    assert artifact.requires_human_review is False
    assert "remains the fallback" not in artifact.payload.rationale


# A comment row (first value starts with "#") is skipped by the parser, so
# its "receiving" can never become a row's CTE and must not withhold.
COMMENT_ROW_BODY = (
    f"{_SHIP_COLUMNS},Activity\n"
    "# example,Romaine,1,cases,2026-09-21,Packhouse A,DC B,BOL-0,PACK-0,receiving\n"
    "TLC-A1,Romaine,120,cases,2026-09-21,Packhouse A,DC B,BOL-1,PACK-1,shipping\n"
).encode()

INVARIANT_CASES = {
    "mixed": (_extra_column_body("Activity", "receiving", "shipping"), False),
    "event-kind-alias": (_extra_column_body("Event Kind", "Receipt", ""), False),
    "grade-letters": (_extra_column_body("Grade", "S", "R"), False),
    "agreeing-aliases": (_extra_column_body("Activity", "shipping", "S", "Ship"), True),
    "free-text": (_extra_column_body("Activity", "load dock 4", ""), True),
    "blank": (_extra_column_body("Activity", "", ""), True),
    "comment-row": (COMMENT_ROW_BODY, True),
}


@pytest.mark.parametrize("apply", [True, False], ids=["apply-on", "apply-off"])
@pytest.mark.parametrize("case", sorted(INVARIANT_CASES))
def test_a_sent_file_cte_is_the_cte_of_every_parsed_row(harness, case, apply):
    """Invariant: whenever file_cte_type=X is sent, every row the parser produces has CTE X."""
    body, expect_sent = INVARIANT_CASES[case]
    seen: dict = {}
    harness["use_decider"](_decider(_transport(EVERYTHING_IS_CTE, seen), apply_header_mappings=apply))

    resp = _post(_client(), body, data={"cte_type": "Shipping"})

    assert resp.status_code == 200, resp.text
    state = seen["bodies"][0]["state"]
    assert ("file_cte_type" in state) is expect_sent
    (payload,) = harness["payloads"]
    if "file_cte_type" in state:
        assert {e.cte_type.value for e in payload.events} == {state["file_cte_type"]}


@pytest.mark.parametrize(
    "text,expected",
    [
        # Recognised columns are never sent to Jev, so they cannot be mapped.
        (f"{_SHIP_COLUMNS},location_name\nT1,R,1,cases,2026-09-21,A,B,C,D,receiving\n", ("shipping", None)),
        ("Activity,quantity\nS,1\nship,2\n,3\n", ("shipping", None)),
        ("Activity,quantity\nS,1\nH,2\n", (None, "column Activity holds per-row CTE values")),
        (" Activity ,quantity\nreceiving,1\n", (None, "column Activity holds per-row CTE values")),
        # Duplicate headers: every raw column is scanned, not just the one the parser keeps.
        ("Activity,activity,quantity\nreceiving,shipping,1\n", (None, "column Activity holds per-row CTE values")),
        ("Activity,quantity\n# receiving,1\nshipping,2\n", ("shipping", None)),
        (
            "Activity,quantity\n" + '"' + "x" * 200_000 + '",1\n',
            (None, "rows could not be read to rule out per-row CTE values"),
        ),
    ],
    ids=["recognised", "agreeing", "letter-alias", "padded-header", "duplicate-header", "comment", "unreadable"],
)
def test_file_cte_type_for_jev_value_scan(text, expected):
    assert ct._file_cte_type_for_jev(text, "shipping") == expected
    assert ct._file_cte_type_for_jev(text, None) == (None, None)


# ---------------------------------------------------------------------------
# The scan reads exactly the rows the parser reads, off the event loop
# ---------------------------------------------------------------------------


def _row_limit_body(position: int, *, comments: int = 0, blanks: int = 0, empties: int = 0) -> str:
    """502 DictReader rows; the one at ``position`` (1-based) says receiving, every data row shipping.

    Comment rows (which also say receiving) and all-empty rows count towards
    the parser's row limit; blank lines are skipped by DictReader and do not.
    They all come first, so they shift where the limit falls.
    """
    rows: list[str] = ["\n"] * blanks
    rows += ["# note,,,,,,,,,receiving\n"] * comments
    rows += [",,,,,,,,,\n"] * empties
    for index in range(comments + empties + 1, ct.MAX_CSV_ROWS + 3):
        activity = "receiving" if index == position else "shipping"
        rows.append(f"TLC-{index},Romaine,1,cases,2026-09-21,Packhouse A,DC B,BOL-{index},PACK-{index},{activity}\n")
    return f"{_SHIP_COLUMNS},Activity\n" + "".join(rows)


@pytest.mark.parametrize(
    "position,comments,blanks,empties,withheld",
    [
        (ct.MAX_CSV_ROWS, 0, 0, 0, True),
        (ct.MAX_CSV_ROWS + 1, 0, 0, 0, False),
        (ct.MAX_CSV_ROWS, 3, 0, 0, True),
        (ct.MAX_CSV_ROWS + 1, 3, 0, 0, False),
        (ct.MAX_CSV_ROWS, 0, 5, 0, True),
        (ct.MAX_CSV_ROWS + 1, 0, 5, 0, False),
        (ct.MAX_CSV_ROWS, 0, 0, 2, True),
        (ct.MAX_CSV_ROWS + 1, 0, 0, 2, False),
    ],
    ids=["500", "501", "500-comments", "501-comments", "500-blanks", "501-blanks", "500-empties", "501-empties"],
)
def test_scan_stops_exactly_where_the_parser_stops(position, comments, blanks, empties, withheld):
    text = _row_limit_body(position, comments=comments, blanks=blanks, empties=empties)

    file_cte_type, reason = ct._file_cte_type_for_jev(text, "shipping")

    # Ground truth: does the parser, with Jev's mapping applied, ingest a receiving row?
    events, errors, _ = ct.parse_csv_rows(text, "shipping", header_mapping={"activity": "cte_type"})
    parser_ingests_receiving = any(event.cte_type.value == "receiving" for event in events)
    assert errors[-1].endswith(f"CSV exceeds maximum row limit of {ct.MAX_CSV_ROWS}")
    assert (file_cte_type is None) is parser_ingests_receiving is withheld
    assert reason == ("column Activity holds per-row CTE values" if withheld else None)


def test_scan_reads_at_most_max_csv_rows(monkeypatch):
    pulled = collections.Counter()

    class CountingDictReader(csv.DictReader):
        def __next__(self):
            row = super().__next__()
            pulled["rows"] += 1
            return row

    monkeypatch.setattr(ct.csv, "DictReader", CountingDictReader)
    text = f"{_SHIP_COLUMNS},Activity\n" + "T1,Romaine,1,cases,2026-09-21,A,B,C,D,shipping\n" * (ct.MAX_CSV_ROWS * 4)

    assert ct._file_cte_type_for_jev(text, "shipping") == ("shipping", None)
    assert pulled["rows"] == ct.MAX_CSV_ROWS


@pytest.mark.parametrize(
    "text,withheld",
    [
        # Only the first column marks a comment; a later hash-prefixed
        # value must not hide a data row from either the scan or parser.
        ("Lot,Notes,Activity\nTLC-1,# x,receiving\n", True),
        ("Lot,Notes,Activity\n# x,TLC-1,receiving\n", False),
    ],
    ids=["first-column-is-data", "first-column-is-comment"],
)
def test_comment_rows_are_the_ones_the_parser_skips(text, withheld):
    events, errors, _ = ct.parse_csv_rows(text, "shipping")
    parser_skipped_it = not events and not errors
    assert parser_skipped_it is not withheld
    assert (ct._file_cte_type_for_jev(text, "shipping")[0] is None) is withheld


def test_reading_the_upload_happens_in_the_threadpool(monkeypatch):
    on_loop_thread: dict[str, bool] = {}
    for name in ("_csv_headers_and_samples", "_file_cte_type_for_jev"):

        def wrapper(*args, _original=getattr(ct, name), _name=name, **kwargs):
            on_loop_thread[_name] = threading.current_thread() is threading.main_thread()
            return _original(*args, **kwargs)

        monkeypatch.setattr(ct, name, wrapper)
    seen: dict = {}
    decider = _decider(_transport(SHIPPING_ANSWERS, seen), header_sample_values=2)

    # asyncio.run drives the loop on this (main) thread.
    assert threading.current_thread() is threading.main_thread()
    result = asyncio.run(
        ct._suggest_header_mappings_for_upload(SHIPPING_CSV_BODY.decode(), decider=decider, cte_type="shipping")
    )

    assert result.ok and seen["bodies"][0]["state"]["file_cte_type"] == "shipping"
    assert on_loop_thread == {"_csv_headers_and_samples": False, "_file_cte_type_for_jev": False}


def test_reading_the_upload_never_raises_into_the_route(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(ct, "_file_cte_type_for_jev", boom)
    seen: dict = {}
    decider = _decider(_transport(SHIPPING_ANSWERS, seen))

    result = asyncio.run(
        ct._suggest_header_mappings_for_upload(SHIPPING_CSV_BODY.decode(), decider=decider, cte_type="shipping")
    )

    assert result.status == "error"
    assert "bodies" not in seen


@pytest.mark.parametrize(
    "header,parser_reads_it",
    [
        ("cte_type", True),
        ("CTE", True),
        ("Event Type", True),
        (" type ", True),
        ("EVENT_TYPE", True),
        ("cte type", True),
        ("Event-Type", False),
        ("event  type", False),
        ("Transaction Type", False),
        ("cte_type_code", False),
    ],
)
def test_per_row_cte_column_matches_exactly_what_the_parser_reads(header, parser_reads_it):
    text = (
        f"{header},traceability_lot_code,product_description,quantity,unit_of_measure,ship_date,location_name\n"
        "receiving,TLC-1,Kale,1,cases,2026-09-21,Farm A\n"
    )
    (event,), errors, _ = ct.parse_csv_rows(text, "shipping")
    assert errors == []
    assert (event.cte_type.value == "receiving") is parser_reads_it
    assert (ct._per_row_cte_column([header, "quantity"]) is not None) is parser_reads_it
    # Either way the declared CTE is withheld: by the header rule when the
    # parser reads the column, by the value scan when only Jev could map it.
    reason = (
        f"file has a per-row CTE column: {header.strip()}"
        if parser_reads_it
        else f"column {header.strip()} holds per-row CTE values"
    )
    assert ct._file_cte_type_for_jev(text, "shipping") == (None, reason)
    assert ct._file_cte_type_for_jev(text, None) == (None, None)
    if not parser_reads_it:
        # ...and if Jev maps it, the row's own value wins over the declared CTE.
        (mapped,), _, _ = ct.parse_csv_rows(text, "shipping", header_mapping={normalize_csv_header(header): "cte_type"})
        assert mapped.cte_type.value == "receiving"


def test_mixed_type_upload_without_the_form_field_sends_no_file_cte_type(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS, seen)))

    resp = _post(_client(), MIXED_CSV_BODY, data={})

    assert resp.status_code == 200, resp.text
    (sent,) = seen["bodies"]
    # Exactly the pre-v2 state shape: the key is absent, not null.
    assert set(sent["state"]) == {"csv_headers", "columns_to_map"}
    assert [c["header"] for c in sent["state"]["columns_to_map"]] == ["Notes"]
    (payload,) = harness["payloads"]
    assert [e.cte_type.value for e in payload.events] == ["harvesting", "shipping"]


def test_unknown_declared_cte_type_is_rejected_before_jev_is_asked(harness):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(SHIPPING_ANSWERS, seen)))

    resp = _post(_client(), SHIPPING_CSV_BODY, data={"cte_type": "teleporting"})

    assert resp.status_code == 400
    assert "bodies" not in seen


# ---------------------------------------------------------------------------
# Apply mode
# ---------------------------------------------------------------------------


def test_apply_mode_maps_the_column_and_records_reviewed_evidence(harness):
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS), apply_header_mappings=True))

    resp = _post(_client(), CSV_BODY_NO_ALIAS)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["accepted"] == 3 and body["rejected"] == 0
    (payload,) = harness["payloads"]
    assert [e.traceability_lot_code for e in payload.events] == ["TLC-001", "TLC-002", "TLC-003"]
    # The source column still reaches the KDEs: nothing is dropped from the evidence trail.
    assert payload.events[0].kdes["lot_#"] == "TLC-001"
    assert payload.events[0].kdes["traceability_lot_code"] == "TLC-001"

    suggestion = next(s for s in body["header_mapping_suggestions"] if s["source_header"] == "Lot #")
    assert suggestion["applied"] is True and suggestion["blocked_reason"] is None
    assert body["header_mapping_engine"]["apply_enabled"] is True

    (artifact,) = harness["artifacts"]
    assert artifact.requires_human_review is False
    assert "applied" in artifact.suggestion


def test_apply_mode_never_outranks_a_column_the_file_carries(harness):
    # CSV_BODY carries ``tlc``, which the parser reads right after
    # traceability_lot_code: applying "Lot #" would replace TLC-003 on the row
    # that provides it through ``tlc``. The suggestion is recorded for review
    # instead, and the rows parse exactly as they do without Jev.
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS), apply_header_mappings=True))

    resp = _post(_client())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    suggestion = next(s for s in body["header_mapping_suggestions"] if s["source_header"] == "Lot #")
    assert suggestion["band"] == "auto_apply"
    assert suggestion["applied"] is False
    assert suggestion["blocked_reason"] == "shadows_existing_column"
    assert body["accepted"] == 1 and body["rejected"] == 2
    (payload,) = harness["payloads"]
    assert [e.traceability_lot_code for e in payload.events] == ["TLC-003"]
    assert (
        "traceability_lot_code" not in payload.events[0].kdes
        or payload.events[0].kdes["traceability_lot_code"] == "TLC-003"
    )

    (artifact,) = harness["artifacts"]
    assert artifact.requires_human_review is True
    assert "already carries tlc" in artifact.payload.rationale


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
# Malformed header row: row data never leaves as a "header"
# ---------------------------------------------------------------------------

# The review's reproduction: an unterminated quote makes the reader take the
# rest of the file, PII included, as a single "header".
OPEN_QUOTE_TEXT = '"Lot #,product_description,Notes\nTLC-1,Kale,call 555-123-4567 jane@example.com\nTLC-2,Chard,x\n'

# One ordinary line whose last header is far longer than any column name.
LONG_HEADER_TEXT = (
    "traceability_lot_code,product_description,quantity,unit_of_measure,harvest_date,location_name,"
    "reference_document,Notes " + "x" * 200 + "\n"
    "TLC-001,Kale,10,lbs,2026-04-17,Farm A,REF-1,call 555-123-4567\n"
)


def test_unterminated_quote_in_the_header_row_sends_nothing(harness, caplog):
    seen: dict = {}
    harness["use_decider"](_decider(_transport(DEFAULT_ANSWERS, seen), header_sample_values=2))

    with caplog.at_level("WARNING", logger="csv-templates"):
        resp = _post(_client(), OPEN_QUOTE_TEXT.encode(), data={"cte_type": "harvesting"})

    assert "bodies" not in seen  # zero requests reached the transport
    assert resp.status_code == 400  # no data rows, exactly as without Jev
    assert harness["artifacts"] == [] and harness["payloads"] == []
    logged = caplog.text
    assert "csv_header_mapping_malformed_header reason=the header row spans 3 lines" in logged
    assert "555-123-4567" not in logged and "jane@example.com" not in logged


def test_malformed_header_row_is_reported_on_the_response_with_no_evidence(harness):
    seen: dict = {}
    harness["use_decider"](
        _decider(_transport(DEFAULT_ANSWERS, seen), apply_header_mappings=True, header_sample_values=2)
    )

    resp = _post(_client(), LONG_HEADER_TEXT.encode())

    assert "bodies" not in seen
    assert resp.status_code == 200, resp.text
    body = resp.json()
    engine = body["header_mapping_engine"]
    assert engine["status"] == "malformed_header"
    assert engine["model"] is None and engine["request_id"] is None and engine["questions_version"] is None
    assert engine["artifacts_recorded"] == 0
    assert body["header_mapping_suggestions"] == []
    assert harness["artifacts"] == []
    # The rows themselves are unaffected: the file ingests as it would without Jev.
    assert body["accepted"] == 1


@pytest.mark.parametrize(
    "text,reason",
    [
        (OPEN_QUOTE_TEXT, "the header row spans 3 lines"),
        ('"Ship\nDate",quantity\nA,1\n', "the header row spans 2 lines"),
        ('"Ship\rDate",quantity\nA,1\n', "a header contains a line break"),
        (LONG_HEADER_TEXT, "a header is 206 characters long (limit 128)"),
    ],
    ids=["unterminated-quote", "quoted-newline", "quoted-carriage-return", "over-cap"],
)
def test_malformed_header_row_stops_every_reader_of_the_file(text, reason):
    headers, samples, malformed = ct._csv_headers_and_samples(text, 5)
    assert malformed == reason
    assert samples == {}  # no sample values are even collected
    # The CTE value scan neither scans nor names the "headers".
    assert ct._file_cte_type_for_jev(text, "shipping") == (None, "the header row is malformed")

    seen: dict = {}
    decider = _decider(_transport(DEFAULT_ANSWERS, seen), header_sample_values=5)
    result = asyncio.run(ct._suggest_header_mappings_for_upload(text, decider=decider, cte_type="shipping"))
    assert result.status == "malformed_header"
    assert "bodies" not in seen


def test_well_formed_header_rows_are_unchanged():
    quoted = '"Lot #","Notes, internal",quantity\nA,B,1\n'  # properly closed quotes on one line
    for text in (CSV_BODY.decode(), CSV_BODY.decode().replace("\n", "\r\n"), quoted):
        headers, samples, malformed = ct._csv_headers_and_samples(text, 2)
        assert malformed is None and headers
    assert ct._csv_headers_and_samples(quoted, 2)[0] == ["Lot #", "Notes, internal", "quantity"]


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


def test_parse_csv_rows_mapping_never_replaces_a_value_the_row_provides():
    # Row 2 provides its lot code through ``tlc``; the mapped "Lot #" must not
    # outrank it. Row 3 has no lot code of its own, so the mapping fills it in.
    text = (
        "Lot #,tlc,product_description,quantity,unit_of_measure,harvest_date,location_name\n"
        "MAPPED-1,FILE-1,Kale,10,lbs,2026-04-17,Farm A\n"
        "MAPPED-2,,Chard,5,lbs,2026-04-17,Farm A\n"
    )
    events, errors, _ = ct.parse_csv_rows(text, "harvesting", header_mapping={"lot_#": "traceability_lot_code"})

    assert errors == []
    assert [e.traceability_lot_code for e in events] == ["FILE-1", "MAPPED-2"]


def test_precedence_chains_pin_the_parser_order_the_policy_relies_on():
    for chain in ct._COLUMN_PRECEDENCE:
        assert len(chain) == len(set(chain))
        assert set(chain) <= ct._RECOGNIZED_COLUMNS
    assert outranked_columns("traceability_lot_code", ct._COLUMN_PRECEDENCE) == ("tlc", "lot_code")
    assert outranked_columns("quantity", ct._COLUMN_PRECEDENCE) == ("qty",)
    assert outranked_columns("location_name", ct._COLUMN_PRECEDENCE) == (
        "ship_from_location",
        "receiving_location",
        "location_identifier",
        "facility_name",
        "location",
    )
    # event_date is read before every CTE-specific date column.
    assert set(outranked_columns("event_date", ct._COLUMN_PRECEDENCE)) == set(ct._DATE_FIELDS) - {"event_date"}
    assert outranked_columns("landing_date", ct._COLUMN_PRECEDENCE) == ()


def test_upload_ui_labels_every_field_jev_can_name_with_a_header_the_parser_reads():
    # The upload pages tell uploaders to rename a column to the label in
    # frontend/src/lib/column-suggestions.ts. That only works if the labels
    # cover Jev's vocabulary exactly and each normalises to a parser column.
    import re
    from pathlib import Path

    source = (Path(__file__).resolve().parents[3] / "frontend" / "src" / "lib" / "column-suggestions.ts").read_text()
    block = source.split("FIELD_LABELS", 1)[1].split("};", 1)[0]
    labels = dict(re.findall(r"^\s+([a-z_]+): '([^']+)',$", block, flags=re.MULTILINE))

    assert set(labels) == set(CANONICAL_FIELD_NAMES)
    for field, label in labels.items():
        assert normalize_csv_header(label) == field
        assert field in ct._RECOGNIZED_COLUMNS
