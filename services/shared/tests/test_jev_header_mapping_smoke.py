"""Focused smoke tests for ``shared.jev.header_mapping``.

Complements the exhaustive ``test_jev_header_mapping.py`` with one fast
file that walks the main public path end to end: header normalisation,
unrecognised column selection, malformed header refusal, question and state
shape, an offline suggestion round trip, and provider failure handling.
All provider traffic uses ``httpx2.MockTransport`` so no network is needed.
"""

from __future__ import annotations

import json

import httpx2
from shared.jev import ConfidenceBand, JevDecider, JevSettings
from shared.jev.header_mapping import (
    CANONICAL_FIELDS,
    MAX_HEADER_CHARS,
    NO_MATCH,
    HeaderMappingResult,
    HeaderMappingSuggestion,
    build_questions,
    build_state,
    collect_sample_values,
    malformed_header_reason,
    normalize_csv_header,
    outranked_columns,
    reversed_criteria,
    suggest_header_mappings,
    unrecognized_headers,
)

RECOGNIZED = {"quantity", "unit_of_measure"}


def test_normalize_csv_header_matches_parser_rules():
    assert normalize_csv_header(" Lot # ") == "lot_#"
    assert normalize_csv_header("Ship Dt") == "ship_dt"
    assert normalize_csv_header(None) == ""
    assert normalize_csv_header("  ") == ""


def test_unrecognized_headers_keeps_first_spelling_only():
    headers = ["Lot #", "quantity", "", None, "LOT #", "Ship Dt"]
    assert unrecognized_headers(headers, RECOGNIZED) == ["Lot #", "Ship Dt"]


def test_malformed_header_reason_refuses_long_and_broken_rows():
    assert malformed_header_reason(["quantity", "Lot #"]) is None
    assert malformed_header_reason(["quantity", "x" * MAX_HEADER_CHARS]) is None
    over = malformed_header_reason(["quantity", "x" * (MAX_HEADER_CHARS + 1)])
    assert over is not None and str(MAX_HEADER_CHARS) in over
    assert malformed_header_reason(["quantity", "Ship\nDate"]) == "a header contains a line break"


def test_build_state_and_questions_cover_each_column_once():
    state = build_state(["Lot #", "quantity"], ["Lot #"], None)
    assert state["csv_headers"] == ["Lot #", "quantity"]
    assert state["columns_to_map"] == [{"index": 0, "header": "Lot #"}]
    assert "file_cte_type" not in state

    questions = build_questions(["Lot #", "Ship Dt"])
    assert list(questions) == ["col_0", "col_1"]
    for index, header in enumerate(["Lot #", "Ship Dt"]):
        question = questions[f"col_{index}"]
        assert question["type"] == "choice"
        assert question["criteria"] is CANONICAL_FIELDS
        assert question["instructions"]["column"] == {"path": f"columns_to_map[{index}]", "header": header}


def test_reversed_criteria_and_outranked_columns():
    flipped = reversed_criteria(CANONICAL_FIELDS)
    assert list(flipped) == list(reversed(list(CANONICAL_FIELDS)))
    assert outranked_columns("event_date", (("event_date", "ship_date"),)) == ("ship_date",)
    assert outranked_columns("ship_date", (("event_date", "ship_date"),)) == ()


def test_collect_sample_values_caps_distinct_values_per_column():
    rows = [{"Lot #": "L1"}, {"Lot #": "L1"}, {"Lot #": "L2"}, {"Lot #": "L3"}]
    assert collect_sample_values(rows, ["Lot #"], 2) == {"Lot #": ["L1", "L2"]}
    assert collect_sample_values(rows, ["Lot #"], 0) == {}


def _decider(handler, **settings) -> JevDecider:
    base = {"api_key": "k", "max_retries": 0, "timeout_seconds": 1.0}
    base.update(settings)
    return JevDecider(JevSettings(**base), transport=httpx2.MockTransport(handler))


def test_suggest_header_mappings_names_the_canonical_field_offline():
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        assert body["state"]["csv_headers"] == ["Lot #", "quantity"]
        answers = {
            "col_0": {
                "type": "choice",
                "choice": "traceability_lot_code",
                "confidence": 0.97,
                "probabilities": {"traceability_lot_code": 0.97, NO_MATCH: 0.03},
            }
        }
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_smoke"},
            json={"model": "jev-1.13.0", "answers": answers, "usage": {}},
        )

    result = suggest_header_mappings(["Lot #", "quantity"], recognized=RECOGNIZED, decider=_decider(handler))

    assert result.ok
    (suggestion,) = result.suggestions
    assert suggestion.source_header == "Lot #"
    assert suggestion.source_key == "lot_#"
    assert suggestion.canonical_field == "traceability_lot_code"
    assert suggestion.band is ConfidenceBand.AUTO_APPLY
    assert suggestion.applied is False
    assert suggestion.blocked_reason == "apply_disabled"
    assert result.applied_mapping == {}


def test_provider_failure_becomes_a_status_and_never_raises():
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(503, text="down")

    result = suggest_header_mappings(["Lot #", "quantity"], recognized=RECOGNIZED, decider=_decider(handler))

    assert not result.ok
    assert result.status.startswith("unavailable:")
    assert result.suggestions == ()
    assert result.evidence is None
    assert result.applied_mapping == {}


def test_suggestion_to_dict_uses_plain_json_types():
    suggestion = HeaderMappingSuggestion(
        source_header="Lot #",
        source_key="lot_#",
        canonical_field="traceability_lot_code",
        confidence=0.97,
        band=ConfidenceBand.AUTO_APPLY,
        probabilities={"traceability_lot_code": 0.97},
        applied=True,
        shadowed_columns=("tlc",),
    )
    assert suggestion.to_dict()["band"] == "auto_apply"
    assert suggestion.to_dict()["shadowed_columns"] == ["tlc"]
    assert HeaderMappingResult(status="ok", suggestions=(suggestion,)).applied_mapping == {
        "lot_#": "traceability_lot_code"
    }
    assert HeaderMappingResult(status="error").ok is False
