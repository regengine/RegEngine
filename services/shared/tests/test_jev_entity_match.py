"""Offline tests for ``shared.jev.entity_match`` (shadow-only entity matching).

Policy under test:

* one Choice question: one option per candidate plus ``none_of_these``;
* state carries names/types/lexical score only -- never GLN/GTIN/contacts;
* candidates are de-duplicated by entity id and capped;
* answers map back to entity ids; ``none_of_these`` maps to ``None``;
* no candidates -> no call; provider failure -> status, never an exception.
"""

from __future__ import annotations

import json

import httpx2
from shared.jev import ConfidenceBand, JevDecider, JevSettings
from shared.jev.entity_match import (
    MAX_CANDIDATES,
    NO_MATCH,
    PURPOSE,
    QUESTION_ID,
    QUESTIONS_VERSION,
    build_questions,
    build_state,
    shadow_match_entity,
)

CANDIDATES = [
    {
        "entity_id": "e-acme-foods",
        "entity_type": "firm",
        "canonical_name": "Acme Foods Inc.",
        "gln": "0614141000005",
        "gtin": None,
        "verification_status": "verified",
        "entity_confidence": 1.0,
        "confidence": 0.82,
        "matched_alias": "ACME FOODS",
    },
    {
        "entity_id": "e-acme-farms",
        "entity_type": "firm",
        "canonical_name": "Acme Farms LLC",
        "gln": "0614141000012",
        "confidence": 0.71,
        "matched_alias": "Acme Farms",
    },
]


def _answer(choice: str, confidence: float, **others: float) -> dict:
    return {
        "type": "choice",
        "choice": choice,
        "confidence": confidence,
        "probabilities": {choice: confidence, **others},
    }


def _transport(answer: dict | None, seen: dict | None = None, status: int = 200) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if seen is not None:
            seen.setdefault("bodies", []).append(json.loads(request.content))
        if status != 200:
            return httpx2.Response(status, text="down")
        answers = {} if answer is None else {QUESTION_ID: answer}
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_match"},
            json={"model": "jev-1.14.0", "answers": answers, "usage": {"input_tokens": 80, "output_tokens": 1}},
        )

    return httpx2.MockTransport(handler)


def _decider(transport) -> JevDecider:
    return JevDecider(JevSettings(api_key="k", max_retries=0, timeout_seconds=1.0), transport=transport)


def test_question_has_one_option_per_candidate_plus_no_match():
    question = build_questions(2)[QUESTION_ID]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"candidate_1", "candidate_2", NO_MATCH}


def test_state_never_carries_identifiers_or_contacts():
    state = build_state(" Acme Food Co ", CANDIDATES, entity_type="firm")
    assert state["incoming_name"] == "Acme Food Co"
    assert state["incoming_entity_type"] == "firm"
    flat = json.dumps(state)
    for secret in ("0614141000005", "0614141000012", "verified", "e-acme-foods"):
        assert secret not in flat
    assert [c["option"] for c in state["candidates"]] == ["candidate_1", "candidate_2"]


def test_no_candidates_makes_no_call():
    seen: dict = {}
    result = shadow_match_entity("Acme", [], decider=_decider(_transport(None, seen)))
    assert result.status == "no_candidates"
    assert "bodies" not in seen


def test_candidates_are_deduplicated_and_capped():
    many = [{"entity_id": f"e{i}", "canonical_name": f"N{i}", "confidence": 0.9} for i in range(MAX_CANDIDATES + 5)]
    many.insert(1, dict(many[0]))  # duplicate entity id
    seen: dict = {}
    result = shadow_match_entity("N0", many, decider=_decider(_transport(_answer("candidate_1", 0.95), seen)))
    assert result.candidate_count == MAX_CANDIDATES
    body = seen["bodies"][0]
    sent = body["state"]["candidates"]
    assert len(sent) == MAX_CANDIDATES
    assert [c["canonical_name"] for c in sent[:2]] == ["N0", "N1"]  # duplicate dropped, order kept
    assert set(body["questions"][QUESTION_ID]["criteria"]) == {f"candidate_{i}" for i in range(1, 11)} | {NO_MATCH}


def test_pick_maps_back_to_entity_id_and_agreement():
    result = shadow_match_entity(
        "Acme Food Company",
        CANDIDATES,
        decider=_decider(_transport(_answer("candidate_1", 0.93, candidate_2=0.05, none_of_these=0.02))),
    )
    assert result.ok
    assert result.suggestion.entity_id == "e-acme-foods"
    assert result.suggestion.band is ConfidenceBand.AUTO_APPLY
    assert result.suggestion.probabilities == {"e-acme-foods": 0.93, "e-acme-farms": 0.05, NO_MATCH: 0.02}
    assert result.agrees is True
    assert result.evidence.purpose == PURPOSE
    assert result.evidence.questions_version == QUESTIONS_VERSION


def test_disagreement_is_reported():
    result = shadow_match_entity("Acme Farms", CANDIDATES, decider=_decider(_transport(_answer("candidate_2", 0.7))))
    assert result.suggestion.entity_id == "e-acme-farms"
    assert result.suggestion.band is ConfidenceBand.REVIEW
    assert result.agrees is False


def test_no_match_maps_to_none():
    result = shadow_match_entity("Acme Logistics", CANDIDATES, decider=_decider(_transport(_answer(NO_MATCH, 0.88))))
    assert result.ok
    assert result.suggestion.entity_id is None
    assert result.agrees is False


def test_unknown_option_is_invalid_answer():
    result = shadow_match_entity("Acme", CANDIDATES, decider=_decider(_transport(_answer("candidate_9", 0.99))))
    assert result.status == "invalid_answer"
    assert result.suggestion is None
    assert result.agrees is None


def test_provider_failure_is_a_status_not_an_exception():
    result = shadow_match_entity("Acme", CANDIDATES, decider=_decider(_transport(None, status=503)))
    assert result.status.startswith("unavailable:")
    assert result.lexical_top_entity_id == "e-acme-foods"


def test_disabled_decider_is_unavailable():
    decider = JevDecider(JevSettings(api_key=""))
    result = shadow_match_entity("Acme", CANDIDATES, decider=decider)
    assert result.status == "unavailable:disabled"
