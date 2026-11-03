"""Synthetic strict-response, evidence policy and diagnostic preview tests."""

from __future__ import annotations

import asyncio
import copy
import json

import httpx2
import pytest
from shared.jev import JevDecider, JevSettings, JevUnavailable
from shared.jev.review_policy import (
    QUESTION_SETS,
    adjudicate_evidence,
    review_pilot_diagnostic,
    summarize_diagnostic,
)
from shared.jev.review_validation import ReviewContractError, validate_review_answers


def _choice(question, selected=None, probability=0.9):
    keys = list(question["criteria"])
    selected = selected or keys[0]
    return {
        "type": "choice",
        "choice": selected,
        "confidence": 0.99,
        "probabilities": {key: probability if key == selected else (1 - probability) / (len(keys) - 1) for key in keys},
    }


def _answers(mode="mode_b"):
    result = {}
    for key, question in QUESTION_SETS[mode].items():
        if question["type"] == "choice":
            result[key] = _choice(question)
        elif question["type"] == "noul":
            result[key] = {"type": "noul", "noul": 0.9}
        else:
            result[key] = {
                "type": "score",
                "score": 0,
                "confidence": 1,
                "probabilities": {str(i): int(i == 0) for i in range(len(question["criteria"]))},
                "legend": {str(i): text for i, text in enumerate(question["criteria"])},
            }
    if mode == "mode_b":
        result["q2_cross_source_conflict"]["noul"] = 0.1
    return result


def _decider(answers, *, model="jev-1.14.0", status=200, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx2.Response(
            status,
            headers={"x-typesafe-request-id": "req_synthetic_review"},
            json={
                "model": model,
                "answers": answers,
                "usage": {"input_tokens": 100, "output_tokens": 20},
            },
        )

    transport = httpx2.MockTransport(handler)
    return JevDecider(
        JevSettings(api_key="test-key", max_retries=0, timeout_seconds=1),  # pragma: allowlist secret
        transport=transport,
        async_transport=transport,
    )


@pytest.mark.parametrize("mode", ["mode_a", "mode_b"])
def test_valid_question_contract(mode):
    validate_review_answers(_answers(mode), QUESTION_SETS[mode])


@pytest.mark.parametrize("value", [None, True, False, "0.9", float("nan"), float("inf"), -0.1, 1.1, 10**400])
def test_invalid_noul_and_confidence_are_rejected(value):
    for key, field in [("q1_topic_presence", "noul"), ("q3_evidence_polarity", "confidence")]:
        answers = _answers()
        answers[key][field] = value
        with pytest.raises(ReviewContractError):
            adjudicate_evidence(answers, authoritative_scope_verified=True)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda a: a.pop("q1_topic_presence"),
        lambda a: a.update(extra={"type": "noul", "noul": 0.9}),
        lambda a: a["q1_topic_presence"].update(type="choice"),
        lambda a: a["q3_evidence_polarity"].update(choice="invented"),
        lambda a: a["q3_evidence_polarity"].update(choice="explicitly_contradicted"),
        lambda a: a["q3_evidence_polarity"]["probabilities"].pop("topic_not_in_state"),
        lambda a: a["q3_evidence_polarity"]["probabilities"].update(invented=0),
        lambda a: a["q3_evidence_polarity"]["probabilities"].update(explicitly_supported=0.5),
    ],
)
def test_answer_shape_and_distribution_failures(mutation):
    answers = _answers()
    mutation(answers)
    with pytest.raises(ReviewContractError):
        validate_review_answers(answers, QUESTION_SETS["mode_b"])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda a: a.update(score=1),
        lambda a: a.update(score=True),
        lambda a: a.update(score=float("nan")),
        lambda a: a.update(legend={"0": "invented", "1": "other", "2": "other"}),
        lambda a: a.update(probabilities={"1": 1, "2": 0, "3": 0}),
    ],
)
def test_score_mean_numbering_and_legend_are_checked(mutation):
    answers = _answers("mode_a")
    mutation(answers["customer_review_effort"])
    with pytest.raises(ReviewContractError):
        summarize_diagnostic(answers)


@pytest.mark.parametrize("value", [True, "0.9", 1.1])
def test_strict_transport_rejects_original_values_before_conversion(value):
    answers = _answers()
    answers["q1_topic_presence"]["noul"] = value
    decider = _decider(answers)
    with pytest.raises(JevUnavailable, match="invalid_response"):
        decider.ask({}, QUESTION_SETS["mode_b"], purpose="evidence_review", strict_answers=True)
    decider.close()


def test_legacy_advisory_clamping_is_unchanged():
    answers = _answers()
    answers["q1_topic_presence"]["noul"] = 1.1
    decider = _decider(answers)
    assert decider.ask({}, QUESTION_SETS["mode_b"], purpose="legacy").nouls["q1_topic_presence"].probability == 1
    decider.close()


@pytest.mark.parametrize(
    "polarity,expected",
    [
        ("explicitly_supported", "supported"),
        ("explicitly_contradicted", "contradicted"),
        ("missing_required_proof", "insufficient"),
        ("topic_not_in_state", "insufficient"),
    ],
)
def test_conflict_is_preserved_independently_of_polarity(polarity, expected):
    answers = _answers()
    answers["q3_evidence_polarity"] = _choice(QUESTION_SETS["mode_b"]["q3_evidence_polarity"], polarity)
    assert adjudicate_evidence(answers, authoritative_scope_verified=True)["label"] == expected
    answers["q2_cross_source_conflict"]["noul"] = 0.99
    result = adjudicate_evidence(answers, authoritative_scope_verified=True)
    assert result["label"] == "conflicting"
    assert result["claim_verdict"] == expected
    assert result["source_conflict"] == "present"


@pytest.mark.parametrize("flag", [False, None, "true", 1])
def test_scope_must_be_explicitly_verified(flag):
    assert adjudicate_evidence(_answers(), authoritative_scope_verified=flag)["claim_verdict"] == "insufficient"


@pytest.mark.parametrize("presence,expected", [(0.3, "insufficient"), (0.699999, "insufficient"), (0.7, "supported")])
def test_presence_boundary(presence, expected):
    answers = _answers()
    answers["q1_topic_presence"]["noul"] = presence
    assert adjudicate_evidence(answers, authoritative_scope_verified=True)["label"] == expected


@pytest.mark.parametrize("conflict,expected", [(0.3, "supported"), (0.300001, "insufficient"), (0.7, "conflicting")])
def test_conflict_boundary(conflict, expected):
    answers = _answers()
    answers["q2_cross_source_conflict"]["noul"] = conflict
    assert adjudicate_evidence(answers, authoritative_scope_verified=True)["label"] == expected


@pytest.mark.parametrize("probability,expected", [(0.749999, "insufficient"), (0.75, "supported")])
def test_polarity_boundary(probability, expected):
    answers = _answers()
    answers["q3_evidence_polarity"] = _choice(QUESTION_SETS["mode_b"]["q3_evidence_polarity"], probability=probability)
    assert adjudicate_evidence(answers, authoritative_scope_verified=True)["label"] == expected


def test_unknown_evidence_and_arbitrary_calibration_never_assign():
    flags = {"approvedCalibrationId": "pretend", "ownership": {"role": "upstream_supplier_or_grower_rep"}}
    result = summarize_diagnostic(_answers("mode_a"), evidence_flags=flags)
    assert result["tlc_source_suggestion"] == "requires_confirmation"
    assert result["data_gap_origin_suggestion"] == "ambiguous_requires_customer_confirmation"
    assert result["external_followup"] == "uncertain"
    assert result["effort"] == {"status": "unknown"}
    assert result["correction_owner"]["status"] == "triage"
    assert result["correction_owner"]["owner_role"] is None
    assert sum(c["probability"] for c in result["correction_owner"]["candidates"]) < 1


def test_manual_owner_is_not_a_candidate_assignment():
    answers = _answers("mode_a")
    answers["correction_owner_role"] = _choice(
        QUESTION_SETS["mode_a"]["correction_owner_role"], "needs_founder_manual_triage", 1
    )
    assert summarize_diagnostic(answers)["correction_owner"]["candidates"] == []


def test_evidence_flags_are_independent_and_strict_booleans():
    answers = _answers("mode_a")
    result = summarize_diagnostic(
        answers, evidence_flags={"tlc_source_verified": True, "effort_basis_verified": "true"}
    )
    assert result["tlc_source_suggestion"] == "suspected_mismatch"
    assert result["data_gap_origin_suggestion"] == "ambiguous_requires_customer_confirmation"
    assert result["effort"] == {"status": "unknown"}


def test_bimodal_effort_is_not_reported_as_medium():
    answers = _answers("mode_a")
    assert (
        summarize_diagnostic(answers, evidence_flags={"effort_basis_verified": True})["effort"]["status"]
        == "provisional"
    )
    answers["customer_review_effort"].update(score=1, probabilities={"0": 0.5, "1": 0, "2": 0.5})
    assert summarize_diagnostic(answers, evidence_flags={"effort_basis_verified": True})["effort"] == {
        "status": "unknown"
    }


@pytest.mark.parametrize("malformed", [False, True])
def test_async_preview_uses_strict_transport_and_metadata_only(malformed, caplog):
    answers = _answers("mode_a")
    if malformed:
        answers["external_followup_required"]["noul"] = 2
    seen = []
    decider = _decider(answers, seen=seen)

    async def run():
        try:
            return await review_pilot_diagnostic({"synthetic_marker": "DO_NOT_LOG_THIS_STATE"}, decider)
        finally:
            await decider.aclose()

    result = asyncio.run(run())
    assert result["automatic_assignment_enabled"] is False
    assert len(seen) == 1
    assert "DO_NOT_LOG_THIS_STATE" not in caplog.text
    if malformed:
        assert result["status"] == "unavailable"
        assert result["reason"] == "invalid_response"
        assert result["suggestions"] is None
    else:
        assert result["status"] == "review"
        assert result["evidence"]["request_id"] == "req_synthetic_review"
        assert result["suggestions"]["correction_owner"]["owner_role"] is None


def test_disabled_preview_makes_no_request():
    result = asyncio.run(review_pilot_diagnostic({}, JevDecider(JevSettings(api_key=None))))
    assert result["status"] == "unavailable"
    assert result["reason"] == "disabled"


def test_model_mismatch_is_processing_failure():
    decider = _decider(_answers(), model="jev-1.13.0")
    with pytest.raises(JevUnavailable, match="invalid_response"):
        decider.ask({}, QUESTION_SETS["mode_b"], purpose="evidence", strict_answers=True)
    decider.close()
