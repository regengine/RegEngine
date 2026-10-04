"""Offline tests for ``shared.jev.cte_classification``.

The policy under test, in one place:

* one Choice question over the seven FDA CTEs plus ``mixed_or_unclear``;
  ``growing`` (RegEngine-internal) is never an option;
* the state is the header row, plus redacted samples only when given;
* an answer becomes the file's fallback CTE only when apply is enabled, it
  names one CTE, its band is AUTO_APPLY and its confidence clears the
  agent-artifact human-review threshold;
* every actionable answer becomes a strict ``field_mapping_suggestion``
  artifact targeting ``cte_type``, anchored to the upload hash;
* a malformed header row is never sent, and any provider failure yields a
  status, never an exception.
"""

from __future__ import annotations

import json
import uuid

import httpx2
import pytest
from shared.agent_artifacts import HUMAN_REVIEW_CONFIDENCE_THRESHOLD, AgentArtifact
from shared.jev import ConfidenceBand, JevDecider, JevSettings
from shared.jev.cte_classification import (
    AGENT_NAME,
    CTE_CRITERIA,
    CTE_NAMES,
    FILE_SOURCE_FIELD,
    MIXED_OR_UNCLEAR,
    PURPOSE,
    QUESTION_ID,
    QUESTIONS_VERSION,
    REVERSED_QUESTION_ID,
    TARGET_FIELD,
    CteClassificationResult,
    build_cte_type_artifacts,
    build_questions,
    build_state,
    suggest_file_cte_type,
)
from shared.jev.header_mapping import MALFORMED_HEADER, MAX_HEADER_CHARS

# A RegEngine receiving template: every column is one the parser knows, but
# there is no cte_type column, so without a declared CTE every row fails.
RECEIVING_HEADERS = [
    "traceability_lot_code",
    "product_description",
    "quantity",
    "unit_of_measure",
    "receive_date",
    "receiving_location",
    "immediate_previous_source",
    "reference_document",
]
SOURCE_HASH = "c" * 64
FDA_CTES = {
    "harvesting",
    "cooling",
    "initial_packing",
    "first_land_based_receiving",
    "shipping",
    "receiving",
    "transformation",
}


def _answer(choice: str, confidence: float, **others: float) -> dict:
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": {choice: confidence, **others},
    }


def _transport(answer: dict | None, seen: dict | None = None, status: int = 200) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        if seen is not None:
            seen.setdefault("bodies", []).append(body)
        if status != 200:
            return httpx2.Response(status, text="down")
        answers = {} if answer is None else {QUESTION_ID: answer, REVERSED_QUESTION_ID: answer}
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_cte"},
            json={"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 90, "output_tokens": 1}},
        )

    return httpx2.MockTransport(handler)


def _decider(transport, **settings) -> JevDecider:
    base = {"api_key": "k", "max_retries": 0, "timeout_seconds": 1.0}
    base.update(settings)
    return JevDecider(JevSettings(**base), transport=transport)


# ---------------------------------------------------------------------------
# Vocabulary, state and question
# ---------------------------------------------------------------------------


def test_vocabulary_is_the_fda_ctes_plus_mixed_or_unclear():
    assert CTE_NAMES == FDA_CTES
    assert set(CTE_CRITERIA) == FDA_CTES | {MIXED_OR_UNCLEAR}
    assert "growing" not in CTE_CRITERIA
    for name, criteria in CTE_CRITERIA.items():
        assert criteria["what"], name
        assert criteria["examples"], name
        if name != MIXED_OR_UNCLEAR:
            assert criteria["not_for"], name


def test_one_choice_question_over_the_vocabulary():
    questions = build_questions()
    assert list(questions) == [QUESTION_ID, REVERSED_QUESTION_ID]
    question = questions[QUESTION_ID]
    assert question["type"] == "choice"
    assert question["criteria"] is CTE_CRITERIA
    assert "csv_headers" in question["instructions"]["task"]
    assert MIXED_OR_UNCLEAR in question["instructions"]["guidance"]


def test_state_is_the_header_row_and_samples_only_when_given():
    assert build_state([" Ship Date ", "Customer", None]) == {"csv_headers": ["Ship Date", "Customer", ""]}
    state = build_state(["Activity"], {"Activity": ["SHIP", "SHIP"], "Empty": []})
    assert state == {"csv_headers": ["Activity"], "sample_values": {"Activity": ["SHIP", "SHIP"]}}


def test_request_carries_the_header_row_purpose_and_version():
    seen: dict = {}
    decider = _decider(_transport(_answer("receiving", 0.97), seen))
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=decider)

    assert result.ok
    (body,) = seen["bodies"]
    assert body["state"] == {"csv_headers": RECEIVING_HEADERS}
    assert list(body["questions"]) == [QUESTION_ID, REVERSED_QUESTION_ID]
    assert body["questions"][QUESTION_ID]["criteria"].keys() == CTE_CRITERIA.keys()
    assert result.evidence.purpose == PURPOSE
    assert result.evidence.questions_version == QUESTIONS_VERSION


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


def test_advisory_default_never_applies_even_at_full_confidence():
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=_decider(_transport(_answer("receiving", 1.0))))

    assert result.suggestion.cte_type == "receiving"
    assert result.suggestion.band is ConfidenceBand.AUTO_APPLY
    assert result.suggestion.applied is False
    assert result.suggestion.blocked_reason == "apply_disabled"
    assert result.applied_cte_type is None


def test_apply_mode_applies_an_auto_apply_band_answer():
    decider = _decider(_transport(_answer("receiving", 0.96, shipping=0.03)), apply_file_cte_type=True)
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=decider)

    assert result.apply_enabled is True
    assert result.suggestion.applied is True
    assert result.suggestion.blocked_reason is None
    assert result.applied_cte_type == "receiving"
    assert result.suggestion.probabilities == {"receiving": 0.96, "shipping": 0.03}


def test_header_mapping_apply_switch_does_not_apply_the_file_cte():
    decider = _decider(_transport(_answer("receiving", 0.99)), apply_header_mappings=True)
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=decider)
    assert result.applied_cte_type is None
    assert result.suggestion.blocked_reason == "apply_disabled"


@pytest.mark.parametrize(
    "confidence,band,blocked",
    [
        (0.80, ConfidenceBand.REVIEW, "below_auto_apply_threshold"),
        (0.40, ConfidenceBand.REJECT, "below_auto_apply_threshold"),
    ],
)
def test_below_the_auto_apply_band_is_never_applied(confidence, band, blocked):
    decider = _decider(_transport(_answer("shipping", confidence)), apply_file_cte_type=True)
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=decider)
    assert result.suggestion.band is band
    assert result.suggestion.blocked_reason == blocked
    assert result.applied_cte_type is None


def test_operator_thresholds_never_go_below_the_artifact_review_threshold():
    confidence = HUMAN_REVIEW_CONFIDENCE_THRESHOLD - 0.05
    decider = _decider(
        _transport(_answer("shipping", confidence)),
        apply_file_cte_type=True,
        auto_apply_confidence=0.70,
        review_confidence=0.30,
    )
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=decider)
    assert result.suggestion.band is ConfidenceBand.AUTO_APPLY
    assert result.suggestion.blocked_reason == "below_human_review_threshold"
    assert result.applied_cte_type is None


def test_mixed_or_unclear_is_reported_but_never_applied():
    decider = _decider(_transport(_answer(MIXED_OR_UNCLEAR, 0.95, shipping=0.05)), apply_file_cte_type=True)
    result = suggest_file_cte_type(["Date", "Activity", "Lot"], decider=decider)
    assert result.suggestion.cte_type is None
    assert result.suggestion.blocked_reason == MIXED_OR_UNCLEAR
    assert result.applied_cte_type is None


@pytest.mark.parametrize("label", ["growing", "creation", "not_a_cte"])
def test_labels_outside_the_vocabulary_are_treated_as_mixed_or_unclear(label):
    decider = _decider(_transport(_answer(label, 0.99)), apply_file_cte_type=True)
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=decider)
    assert result.suggestion.cte_type is None
    assert result.suggestion.blocked_reason == MIXED_OR_UNCLEAR
    assert result.applied_cte_type is None


# ---------------------------------------------------------------------------
# What is never sent, and failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        ["Lot", "Qty\nTLC-1,5"],
        ["Lot", "x" * (MAX_HEADER_CHARS + 1)],
    ],
)
def test_malformed_header_row_is_never_sent(headers):
    seen: dict = {}
    result = suggest_file_cte_type(headers, decider=_decider(_transport(_answer("shipping", 0.99), seen)))
    assert result.status == MALFORMED_HEADER
    assert "bodies" not in seen


def test_disabled_and_blank_header_rows_short_circuit_without_a_request():
    seen: dict = {}
    disabled = _decider(_transport(_answer("shipping", 0.99), seen), api_key=None)
    assert suggest_file_cte_type(RECEIVING_HEADERS, decider=disabled).status == "disabled"

    enabled = _decider(_transport(_answer("shipping", 0.99), seen))
    assert suggest_file_cte_type(["", "  ", None], decider=enabled).status == "no_headers"
    assert "bodies" not in seen


@pytest.mark.parametrize(
    "status,expected",
    [
        (503, "unavailable:server_error"),
        (429, "unavailable:rate_limited"),
        (401, "unavailable:auth"),
    ],
)
def test_provider_failures_become_statuses(status, expected):
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=_decider(_transport(None, status=status)))
    assert result.status == expected
    assert result.suggestion is None
    assert result.applied_cte_type is None


def test_transport_exceptions_become_statuses():
    def boom(request):
        raise httpx2.ConnectError("refused")

    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=_decider(httpx2.MockTransport(boom)))
    assert result.status == "unavailable:connection"


def test_a_response_without_the_question_is_no_answer():
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=_decider(_transport(None)))
    assert result.status == "no_answer"
    assert result.suggestion is None
    assert result.evidence is not None and result.evidence.request_id == "req_cte"


def test_unexpected_errors_are_contained(monkeypatch):
    decider = _decider(_transport(_answer("shipping", 0.99)))

    def explode(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr(decider, "ask", explode)
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=decider)
    assert result.status == "error"
    assert result.headers == tuple(RECEIVING_HEADERS)


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def test_applied_answer_becomes_a_reviewed_cte_type_artifact():
    decider = _decider(_transport(_answer("receiving", 0.96)), apply_file_cte_type=True)
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=decider)
    tenant_id, run_id = uuid.uuid4(), uuid.uuid4()

    (artifact,) = build_cte_type_artifacts(
        result, tenant_id=str(tenant_id), source_hash=SOURCE_HASH, ingestion_run_id=str(run_id)
    )

    assert isinstance(artifact, AgentArtifact)
    assert artifact.artifact_type == "field_mapping_suggestion"
    assert artifact.tenant_id == tenant_id
    assert artifact.agent_name == AGENT_NAME
    assert artifact.agent_version == QUESTIONS_VERSION
    assert artifact.model_name == "typesafe/jev-1.13.0"
    assert artifact.requires_human_review is False
    assert artifact.confidence == pytest.approx(0.96)
    assert artifact.context.ingestion_run_id == run_id
    assert artifact.context.source_hashes == [SOURCE_HASH]
    assert artifact.context.request_id == "req_cte"
    assert artifact.payload.source_field == FILE_SOURCE_FIELD
    assert artifact.payload.source_value == RECEIVING_HEADERS
    assert artifact.payload.target_canonical_field == TARGET_FIELD
    assert artifact.payload.normalized_value == "receiving"
    assert "Applied as the file's fallback CTE" in artifact.payload.rationale
    assert "applied" in artifact.suggestion


def test_advisory_answer_asks_for_review():
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=_decider(_transport(_answer("receiving", 0.70))))
    (artifact,) = build_cte_type_artifacts(result, tenant_id=str(uuid.uuid4()), source_hash=SOURCE_HASH)
    assert artifact.requires_human_review is True
    assert artifact.context.ingestion_run_id is None
    assert "Not applied (reason: below_auto_apply_threshold)" in artifact.payload.rationale
    assert "advisory" in artifact.suggestion


def test_no_artifact_for_mixed_rejected_or_failed_answers():
    tenant = str(uuid.uuid4())
    mixed = suggest_file_cte_type(RECEIVING_HEADERS, decider=_decider(_transport(_answer(MIXED_OR_UNCLEAR, 0.9))))
    rejected = suggest_file_cte_type(RECEIVING_HEADERS, decider=_decider(_transport(_answer("shipping", 0.3))))
    assert rejected.suggestion.band is ConfidenceBand.REJECT
    for result in (mixed, rejected, CteClassificationResult(status="unavailable:timeout")):
        assert build_cte_type_artifacts(result, tenant_id=tenant, source_hash=SOURCE_HASH) == []


def test_non_uuid_run_id_falls_back_to_the_hash_anchor():
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=_decider(_transport(_answer("receiving", 0.7))))
    (artifact,) = build_cte_type_artifacts(
        result, tenant_id=str(uuid.uuid4()), source_hash=SOURCE_HASH, ingestion_run_id="run-abc"
    )
    assert artifact.context.ingestion_run_id is None
    assert artifact.context.source_hashes == [SOURCE_HASH]


def test_non_uuid_tenant_raises_value_error_for_the_caller_to_handle():
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=_decider(_transport(_answer("receiving", 0.7))))
    with pytest.raises(ValueError):
        build_cte_type_artifacts(result, tenant_id="t1", source_hash=SOURCE_HASH)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [(None, False), ("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("maybe", False)],
)
def test_apply_switch_is_opt_in(raw, expected):
    env = {} if raw is None else {"REGENGINE_JEV_APPLY_FILE_CTE_TYPE": raw}
    assert JevSettings.from_env(env).apply_file_cte_type is expected
    # Independent of the header-mapping switch in both directions.
    assert JevSettings.from_env({**env, "REGENGINE_JEV_APPLY_HEADER_MAPPINGS": "1"}).apply_file_cte_type is expected
    assert JevSettings.from_env(env).apply_header_mappings is False


# ---------------------------------------------------------------------------
# Option-order consistency (questions v2)
# ---------------------------------------------------------------------------


def test_reversed_twin_asks_the_same_question_with_the_options_reversed():
    questions = build_questions()
    forward, flipped = questions[QUESTION_ID], questions[REVERSED_QUESTION_ID]
    assert flipped["instructions"] == forward["instructions"]
    assert list(flipped["criteria"]) == list(reversed(list(forward["criteria"])))
    assert flipped["criteria"] == forward["criteria"] == CTE_CRITERIA


def _twin_transport(forward: dict, reverse: dict | None) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        answers = {QUESTION_ID: forward}
        if reverse is not None:
            answers[REVERSED_QUESTION_ID] = reverse
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_cte"},
            json={"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 90, "output_tokens": 2}},
        )

    return httpx2.MockTransport(handler)


@pytest.mark.parametrize(
    "reverse, reason",
    [
        (_answer("shipping", 0.55, receiving=0.45), "order_inconsistent"),
        (_answer(MIXED_OR_UNCLEAR, 0.6, receiving=0.4), "order_inconsistent"),
        (None, "order_check_unavailable"),
    ],
)
def test_answer_is_applied_only_when_both_orders_agree(reverse, reason):
    decider = JevDecider(
        JevSettings(api_key="k", max_retries=0, timeout_seconds=1.0, apply_file_cte_type=True),
        transport=_twin_transport(_answer("receiving", 0.97), reverse),
    )
    result = suggest_file_cte_type(RECEIVING_HEADERS, decider=decider)
    assert result.ok
    assert result.suggestion.cte_type == "receiving"
    assert result.suggestion.applied is False
    assert result.suggestion.blocked_reason == reason
    assert result.applied_cte_type is None
