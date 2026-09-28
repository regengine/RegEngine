"""Offline tests for ``shared.jev.header_mapping``.

The policy under test, in one place:

* only unrecognised, non-blank, non-duplicate headers are asked about;
* one Choice question per column over the canonical vocabulary plus
  ``no_match``;
* an answer is applied only when apply is enabled, the band is AUTO_APPLY,
  the confidence clears the agent-artifact human-review threshold, the
  target column is absent from the file and no other column competes;
* every actionable answer becomes a strict ``field_mapping_suggestion``
  artifact anchored to the upload hash (and run id when it is a UUID);
* any provider failure yields a status, never an exception.
"""

from __future__ import annotations

import json
import uuid

import httpx2
import pytest
from shared.agent_artifacts import HUMAN_REVIEW_CONFIDENCE_THRESHOLD, AgentArtifact
from shared.jev import ConfidenceBand, JevDecider, JevSettings
from shared.jev.header_mapping import (
    AGENT_NAME,
    CANONICAL_FIELD_NAMES,
    CANONICAL_FIELDS,
    MAX_COLUMNS_PER_UPLOAD,
    NO_MATCH,
    PURPOSE,
    QUESTIONS_VERSION,
    HeaderMappingResult,
    build_field_mapping_artifacts,
    build_questions,
    build_state,
    collect_sample_values,
    normalize_csv_header,
    outranked_columns,
    suggest_header_mappings,
    unrecognized_headers,
)

RECOGNIZED = {"traceability_lot_code", "product_description", "quantity", "unit_of_measure", "location_name"}
HEADERS = ["Lot #", "product_description", "quantity", "unit_of_measure", "Ship Dt", "Notes", "location_name"]
SOURCE_HASH = "b" * 64


def _choice(choice: str, confidence: float, **others: float) -> dict:
    probabilities = {choice: confidence, **others}
    return {"type": "choice", "choice": choice, "confidence": confidence, "probabilities": probabilities}


def _transport(answer_for: dict[str, dict], seen: dict | None = None) -> httpx2.MockTransport:
    """Answer each ``col_<i>`` question by looking up the column header it asks about."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if seen is not None:
            seen["body"] = body
        answers = {}
        for question_id in body["questions"]:
            index = int(question_id.split("_")[1])
            header = body["state"]["columns_to_map"][index]["header"]
            answers[question_id] = answer_for[header]
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_hm"},
            json={"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 200, "output_tokens": 4}},
        )

    return httpx2.MockTransport(handler)


def _decider(transport, **settings) -> JevDecider:
    base = {"api_key": "k", "max_retries": 0, "timeout_seconds": 1.0}
    base.update(settings)
    return JevDecider(JevSettings(**base), transport=transport)


DEFAULT_ANSWERS = {
    "Lot #": _choice("traceability_lot_code", 0.97, no_match=0.03),
    "Ship Dt": _choice("ship_date", 0.70, event_date=0.30),
    "Notes": _choice(NO_MATCH, 0.99, carrier=0.01),
}


# ---------------------------------------------------------------------------
# Vocabulary and question construction
# ---------------------------------------------------------------------------


def test_vocabulary_has_no_match_and_structured_descriptions():
    assert NO_MATCH in CANONICAL_FIELDS
    assert NO_MATCH not in CANONICAL_FIELD_NAMES
    assert len(CANONICAL_FIELDS) <= 255  # Choice option cap
    for name, description in CANONICAL_FIELDS.items():
        assert name == normalize_csv_header(name), f"{name!r} is not a normalised column key"
        assert description["what"]
        assert description["examples"]


def test_unrecognized_headers_drops_blank_known_and_duplicate_columns():
    headers = [" Lot # ", "quantity", "", None, "LOT #", "Ship Dt", "ship dt", "Notes"]
    assert unrecognized_headers(headers, RECOGNIZED) == ["Lot #", "Ship Dt", "Notes"]


def test_build_questions_one_choice_per_column_over_the_vocabulary():
    questions = build_questions(["Lot #", "Ship Dt"])
    assert list(questions) == ["col_0", "col_1"]
    for index, header in enumerate(["Lot #", "Ship Dt"]):
        question = questions[f"col_{index}"]
        assert question["type"] == "choice"
        assert question["criteria"] is CANONICAL_FIELDS
        assert question["instructions"]["column"] == {"path": f"columns_to_map[{index}]", "header": header}


def test_build_state_only_includes_samples_when_present():
    state = build_state(["Lot #", "quantity"], ["Lot #"], {"Lot #": ["L1", "L2"]})
    assert state == {
        "csv_headers": ["Lot #", "quantity"],
        "columns_to_map": [{"index": 0, "header": "Lot #", "sample_values": ["L1", "L2"]}],
    }
    assert build_state(["Lot #"], ["Lot #"], None)["columns_to_map"] == [{"index": 0, "header": "Lot #"}]


def test_build_state_without_cte_type_is_the_v1_shape_byte_for_byte():
    # A file without a declared CTE must send exactly what it sent before
    # ``file_cte_type`` existed: no key, not a null.
    expected = {
        "csv_headers": ["Lot #", "quantity"],
        "columns_to_map": [{"index": 0, "header": "Lot #", "sample_values": ["L1"]}],
    }
    for state in (
        build_state([" Lot # ", "quantity"], ["Lot #"], {"Lot #": ["L1"]}),
        build_state([" Lot # ", "quantity"], ["Lot #"], {"Lot #": ["L1"]}, cte_type=None),
    ):
        assert state == expected
        assert "file_cte_type" not in state
        assert json.dumps(state) == (
            '{"csv_headers": ["Lot #", "quantity"], '
            '"columns_to_map": [{"index": 0, "header": "Lot #", "sample_values": ["L1"]}]}'
        )


def test_build_state_with_cte_type_names_the_file_cte():
    state = build_state(["Ship Dt", "quantity"], ["Ship Dt"], None, cte_type="shipping")
    assert state == {
        "csv_headers": ["Ship Dt", "quantity"],
        "columns_to_map": [{"index": 0, "header": "Ship Dt"}],
        "file_cte_type": "shipping",
    }


def test_questions_explain_file_cte_type_and_the_version_says_so():
    # The task text is what auditors read back from QUESTIONS_VERSION: a
    # change to it must come with a new version.
    assert QUESTIONS_VERSION == "csv-header-mapping.v2"
    task = build_questions(["Ship Dt"])["col_0"]["instructions"]["task"]
    assert task == (
        "Decide which canonical FSMA 204 traceability field the CSV column described in "
        "`column` represents. Use `csv_headers` in the state for context about the file. "
        "When the state has `file_cte_type`, it names the FSMA 204 critical tracking event "
        "that every row in the file records."
    )


# ---------------------------------------------------------------------------
# suggest_header_mappings: request shape and policy
# ---------------------------------------------------------------------------


def test_request_sends_header_row_and_only_unrecognized_columns():
    seen: dict = {}
    result = suggest_header_mappings(
        HEADERS, recognized=RECOGNIZED, decider=_decider(_transport(DEFAULT_ANSWERS, seen))
    )

    assert result.ok
    body = seen["body"]
    assert body["state"]["csv_headers"] == HEADERS
    assert [column["header"] for column in body["state"]["columns_to_map"]] == ["Lot #", "Ship Dt", "Notes"]
    assert set(body["questions"]) == {"col_0", "col_1", "col_2"}
    assert body["model"] == "jev-1.13.0"
    assert result.evidence is not None
    assert result.evidence.purpose == PURPOSE
    assert result.evidence.questions_version == QUESTIONS_VERSION
    assert result.evidence.request_id == "req_hm"
    assert set(body["state"]) == {"csv_headers", "columns_to_map"}


def test_declared_cte_type_reaches_the_request_state():
    seen: dict = {}
    result = suggest_header_mappings(
        HEADERS, recognized=RECOGNIZED, decider=_decider(_transport(DEFAULT_ANSWERS, seen)), cte_type="shipping"
    )

    assert result.ok
    assert seen["body"]["state"]["file_cte_type"] == "shipping"
    assert seen["body"]["state"]["csv_headers"] == HEADERS
    assert result.evidence.questions_version == "csv-header-mapping.v2"


def test_advisory_mode_never_applies_even_at_full_confidence():
    result = suggest_header_mappings(HEADERS, recognized=RECOGNIZED, decider=_decider(_transport(DEFAULT_ANSWERS)))

    by_header = {s.source_header: s for s in result.suggestions}
    lot = by_header["Lot #"]
    assert lot.canonical_field == "traceability_lot_code"
    assert lot.band is ConfidenceBand.AUTO_APPLY
    assert lot.applied is False
    assert lot.blocked_reason == "apply_disabled"
    assert lot.source_key == "lot_#"
    assert by_header["Ship Dt"].band is ConfidenceBand.REVIEW
    assert by_header["Ship Dt"].blocked_reason == "below_auto_apply_threshold"
    assert by_header["Notes"].canonical_field is None
    assert by_header["Notes"].blocked_reason == "no_match"
    assert result.applied_mapping == {}


def test_apply_mode_applies_only_auto_apply_band():
    decider = _decider(_transport(DEFAULT_ANSWERS), apply_header_mappings=True)
    result = suggest_header_mappings(HEADERS, recognized=RECOGNIZED, decider=decider)

    assert result.applied_mapping == {"lot_#": "traceability_lot_code"}
    by_header = {s.source_header: s for s in result.suggestions}
    assert by_header["Lot #"].applied is True and by_header["Lot #"].blocked_reason is None
    assert by_header["Ship Dt"].applied is False


def test_apply_respects_operator_thresholds_but_never_below_artifact_threshold():
    answers = {"Lot #": _choice("traceability_lot_code", 0.80, no_match=0.20)}
    headers = ["Lot #", "quantity"]

    lenient = _decider(
        _transport(answers), apply_header_mappings=True, auto_apply_confidence=0.70, review_confidence=0.30
    )
    result = suggest_header_mappings(headers, recognized=RECOGNIZED, decider=lenient)
    suggestion = result.suggestions[0]
    assert suggestion.band is ConfidenceBand.AUTO_APPLY
    assert suggestion.applied is False
    assert suggestion.blocked_reason == "below_human_review_threshold"
    assert suggestion.confidence < HUMAN_REVIEW_CONFIDENCE_THRESHOLD


def test_conflicting_columns_are_not_applied():
    answers = {
        "Lot #": _choice("traceability_lot_code", 0.95, no_match=0.05),
        "Batch": _choice("traceability_lot_code", 0.93, no_match=0.07),
    }
    decider = _decider(_transport(answers), apply_header_mappings=True)
    result = suggest_header_mappings(["Lot #", "Batch", "quantity"], recognized=RECOGNIZED, decider=decider)

    assert result.applied_mapping == {}
    assert {s.blocked_reason for s in result.suggestions} == {"conflict"}


def test_target_already_present_in_file_is_not_applied():
    answers = {"Lot #": _choice("traceability_lot_code", 0.99)}
    decider = _decider(_transport(answers), apply_header_mappings=True)
    result = suggest_header_mappings(
        ["Lot #", "traceability_lot_code", "quantity"], recognized=RECOGNIZED, decider=decider
    )

    assert result.applied_mapping == {}
    assert result.suggestions[0].blocked_reason == "target_present"


LOT_PRECEDENCE = (("traceability_lot_code", "tlc", "lot_code"),)
LOCATION_PRECEDENCE = (("location_name", "ship_from_location", "receiving_location", "location"),)


def test_outranked_columns_follow_parser_precedence():
    dates = ("event_date", "harvest_date", "ship_date")
    assert outranked_columns("event_date", (dates,)) == ("harvest_date", "ship_date")
    assert outranked_columns("harvest_date", (dates,)) == ("ship_date",)
    assert outranked_columns("ship_date", (dates,)) == ()
    assert outranked_columns("traceability_lot_code", LOT_PRECEDENCE) == ("tlc", "lot_code")
    assert outranked_columns("quantity", LOT_PRECEDENCE) == ()


def test_mapping_that_would_outrank_a_column_the_file_carries_is_not_applied():
    # The parser reads traceability_lot_code before tlc, so applying "Lot #"
    # under the canonical key would replace the tlc values the file provides.
    answers = {"Lot #": _choice("traceability_lot_code", 0.99)}
    decider = _decider(_transport(answers), apply_header_mappings=True)
    result = suggest_header_mappings(
        ["Lot #", "tlc", "quantity"], recognized=RECOGNIZED | {"tlc"}, decider=decider, precedence=LOT_PRECEDENCE
    )

    assert result.applied_mapping == {}
    (suggestion,) = result.suggestions
    assert suggestion.band is ConfidenceBand.AUTO_APPLY
    assert suggestion.applied is False
    assert suggestion.blocked_reason == "shadows_existing_column"
    assert suggestion.shadowed_columns == ("tlc",)
    assert suggestion.to_dict()["shadowed_columns"] == ["tlc"]

    (artifact,) = build_field_mapping_artifacts(
        result, tenant_id="00000000-0000-0000-0000-000000000001", source_hash=SOURCE_HASH
    )
    assert artifact.requires_human_review is True
    assert "already carries tlc" in artifact.payload.rationale


def test_mapping_onto_a_lower_precedence_key_is_still_applied():
    # location_name outranks ship_from_location, so a mapped ship_from_location
    # can never replace the file's location_name: it only fills the shipping KDE.
    answers = {"Origin": _choice("ship_from_location", 0.96)}
    decider = _decider(_transport(answers), apply_header_mappings=True)
    result = suggest_header_mappings(
        ["Origin", "location_name", "quantity"], recognized=RECOGNIZED, decider=decider, precedence=LOCATION_PRECEDENCE
    )

    assert result.applied_mapping == {"origin": "ship_from_location"}
    assert result.suggestions[0].shadowed_columns == ()


def test_unknown_choice_label_is_treated_as_no_match():
    answers = {"Lot #": _choice("something_new", 0.9)}
    result = suggest_header_mappings(
        ["Lot #", "quantity"], recognized=RECOGNIZED, decider=_decider(_transport(answers))
    )
    assert result.suggestions[0].canonical_field is None
    assert result.suggestions[0].blocked_reason == "no_match"


def test_disabled_and_nothing_to_map_short_circuit_without_a_request():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(500)

    disabled = _decider(httpx2.MockTransport(handler), api_key=None)
    assert suggest_header_mappings(HEADERS, recognized=RECOGNIZED, decider=disabled).status == "disabled"

    enabled = _decider(httpx2.MockTransport(handler))
    result = suggest_header_mappings(["quantity", "location_name"], recognized=RECOGNIZED, decider=enabled)
    assert result.status == "no_unrecognized_headers"
    assert calls == []


@pytest.mark.parametrize(
    "response,expected",
    [
        (lambda r: httpx2.Response(503, text="down"), "unavailable:server_error"),
        (lambda r: httpx2.Response(429, json={"error": "slow"}), "unavailable:rate_limited"),
        (lambda r: httpx2.Response(401, json={"error": "nope"}), "unavailable:auth"),
        (lambda r: httpx2.Response(200, json={"model": "m"}), "unavailable:invalid_response"),
    ],
)
def test_provider_failures_become_statuses(response, expected):
    result = suggest_header_mappings(HEADERS, recognized=RECOGNIZED, decider=_decider(httpx2.MockTransport(response)))
    assert result.status == expected
    assert result.suggestions == ()
    assert result.evidence is None
    assert result.applied_mapping == {}


def test_transport_exceptions_become_statuses():
    def boom(request):
        raise httpx2.ConnectError("refused")

    result = suggest_header_mappings(HEADERS, recognized=RECOGNIZED, decider=_decider(httpx2.MockTransport(boom)))
    assert result.status == "unavailable:connection"


def test_too_many_columns_are_truncated_not_rejected():
    headers = [f"Unknown {i}" for i in range(MAX_COLUMNS_PER_UPLOAD + 5)]
    answers = {header: _choice(NO_MATCH, 0.9) for header in headers}
    seen: dict = {}
    result = suggest_header_mappings(headers, recognized=RECOGNIZED, decider=_decider(_transport(answers, seen)))

    assert result.ok
    assert result.truncated_columns == 5
    assert len(seen["body"]["questions"]) == MAX_COLUMNS_PER_UPLOAD
    assert len(result.suggestions) == MAX_COLUMNS_PER_UPLOAD


# ---------------------------------------------------------------------------
# Sample values
# ---------------------------------------------------------------------------


def test_collect_sample_values_redacts_truncates_and_limits():
    rows = [
        {"Lot #": "L1", "Notes": "call 555-123-4567 re jane.doe@example.com", "quantity": "1"},
        {"Lot #": "L1", "Notes": "x" * 200, "quantity": "2"},
        {"Lot #": "L2", "Notes": "", "quantity": "3"},
        {"Lot #": "L3", "Notes": "late", "quantity": "4"},
    ]
    samples = collect_sample_values(rows, ["Lot #", "Notes"], 2)

    assert samples["Lot #"] == ["L1", "L2"]  # distinct, capped at the limit
    assert samples["Notes"][0] == "call [PHONE_REDACTED] re [EMAIL_REDACTED]"
    assert len(samples["Notes"][1]) == 64
    assert "quantity" not in samples
    assert collect_sample_values(rows, ["Lot #"], 0) == {}


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


def test_artifacts_cover_actionable_suggestions_and_validate_the_contract():
    decider = _decider(_transport(DEFAULT_ANSWERS), apply_header_mappings=True)
    result = suggest_header_mappings(HEADERS, recognized=RECOGNIZED, decider=decider)
    tenant_id = uuid.uuid4()
    run_id = uuid.uuid4()

    artifacts = build_field_mapping_artifacts(
        result, tenant_id=str(tenant_id), source_hash=SOURCE_HASH, ingestion_run_id=str(run_id)
    )

    assert [a.payload.target_canonical_field for a in artifacts] == ["traceability_lot_code", "ship_date"]
    applied, advisory = artifacts
    assert all(isinstance(a, AgentArtifact) for a in artifacts)
    assert applied.requires_human_review is False and applied.confidence == pytest.approx(0.97)
    assert advisory.requires_human_review is True and advisory.confidence == pytest.approx(0.70)
    for artifact in artifacts:
        assert artifact.artifact_type == "field_mapping_suggestion"
        assert artifact.tenant_id == tenant_id
        assert artifact.agent_name == AGENT_NAME
        assert artifact.agent_version == QUESTIONS_VERSION
        assert artifact.model_name == "typesafe/jev-1.13.0"
        assert artifact.context.ingestion_run_id == run_id
        assert artifact.context.source_hashes == [SOURCE_HASH]
        assert artifact.context.request_id == "req_hm"
        assert "probabilities" in artifact.payload.rationale.lower()
        assert artifact.payload.normalized_value is None
    assert "applied" in applied.suggestion and "advisory" in advisory.suggestion
    assert "Not applied" in advisory.payload.rationale


def test_artifacts_fall_back_to_hash_anchor_when_run_id_is_not_a_uuid():
    result = suggest_header_mappings(HEADERS, recognized=RECOGNIZED, decider=_decider(_transport(DEFAULT_ANSWERS)))
    artifacts = build_field_mapping_artifacts(
        result, tenant_id=str(uuid.uuid4()), source_hash=SOURCE_HASH, ingestion_run_id="run-abc"
    )
    assert artifacts and all(a.context.ingestion_run_id is None for a in artifacts)
    assert all(a.context.source_hashes == [SOURCE_HASH] for a in artifacts)


def test_no_artifacts_for_failed_calls_or_rejected_answers():
    assert (
        build_field_mapping_artifacts(
            HeaderMappingResult(status="unavailable:timeout"), tenant_id=str(uuid.uuid4()), source_hash=SOURCE_HASH
        )
        == []
    )

    answers = {"Ref": _choice("reference_document", 0.30, no_match=0.30, tlc_source_reference=0.40)}
    result = suggest_header_mappings(["Ref", "quantity"], recognized=RECOGNIZED, decider=_decider(_transport(answers)))
    assert result.suggestions[0].band is ConfidenceBand.REJECT
    assert build_field_mapping_artifacts(result, tenant_id=str(uuid.uuid4()), source_hash=SOURCE_HASH) == []


def test_non_uuid_tenant_raises_value_error_for_the_caller_to_handle():
    result = suggest_header_mappings(HEADERS, recognized=RECOGNIZED, decider=_decider(_transport(DEFAULT_ANSWERS)))
    with pytest.raises(ValueError):
        build_field_mapping_artifacts(result, tenant_id="t1", source_hash=SOURCE_HASH)
