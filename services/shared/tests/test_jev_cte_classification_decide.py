"""Direct unit tests for ``decide`` and the result containers in ``shared.jev.cte_classification``.

The request-level behavior (transport, statuses, artifacts) is covered by
``test_jev_cte_classification.py``. These tests pin the pure policy function
and the small serialization helpers: every blocked reason, the top-3
probability summary, and the ``to_dict``/``ok``/``applied_cte_type`` surface.
"""

from __future__ import annotations

import json

import httpx2
import pytest
from shared.jev import ConfidenceBand, JevDecider, JevSettings
from shared.jev.client import ChoiceResult
from shared.jev.cte_classification import (
    MIXED_OR_UNCLEAR,
    QUESTION_ID,
    REVERSED_QUESTION_ID,
    CteClassificationResult,
    CteTypeSuggestion,
    build_state,
    decide,
    suggest_file_cte_type,
)
from shared.jev.routing import ConfidenceThresholds

THRESHOLDS = ConfidenceThresholds()
HEADERS = ["Ship Date", "Customer", "Carrier"]


def _choice(choice: str, confidence: float, **others: float) -> ChoiceResult:
    return ChoiceResult(choice=choice, confidence=confidence, probabilities={choice: confidence, **others})


def _twin(choice: str = "shipping", confidence: float = 0.9) -> ChoiceResult:
    return ChoiceResult(choice=choice, confidence=confidence, probabilities={choice: confidence})


def test_decide_applies_when_orders_agree():
    suggestion = decide(
        _choice("shipping", 0.95, receiving=0.04),
        thresholds=THRESHOLDS,
        apply_enabled=True,
        reversed_answer=_twin("shipping", 0.8),
    )

    assert suggestion.cte_type == "shipping"
    assert suggestion.confidence == pytest.approx(0.95)
    assert suggestion.band is ConfidenceBand.AUTO_APPLY
    assert suggestion.applied is True
    assert suggestion.blocked_reason is None


@pytest.mark.parametrize(
    "answer,apply_enabled,reversed_answer,blocked",
    [
        (_choice(MIXED_OR_UNCLEAR, 0.95), True, None, MIXED_OR_UNCLEAR),
        (_choice("growing", 0.99), True, None, MIXED_OR_UNCLEAR),
        (_choice("shipping", 0.70), True, _twin(), "below_auto_apply_threshold"),
        (_choice("shipping", 0.30), True, _twin(), "below_auto_apply_threshold"),
        (_choice("shipping", 0.95), False, _twin(), "apply_disabled"),
        (_choice("shipping", 0.95), True, None, "order_check_unavailable"),
        (_choice("shipping", 0.95), True, _twin("receiving"), "order_inconsistent"),
        (_choice("shipping", 0.95), True, _twin(MIXED_OR_UNCLEAR), "order_inconsistent"),
    ],
)
def test_decide_blocked_reasons(answer, apply_enabled, reversed_answer, blocked):
    suggestion = decide(answer, thresholds=THRESHOLDS, apply_enabled=apply_enabled, reversed_answer=reversed_answer)

    assert suggestion.applied is False
    assert suggestion.blocked_reason == blocked


def test_decide_blocks_auto_apply_band_below_artifact_review_threshold():
    loose = ConfidenceThresholds(auto_apply=0.70, review=0.30)
    suggestion = decide(
        _choice("receiving", 0.75), thresholds=loose, apply_enabled=True, reversed_answer=_twin("receiving")
    )

    assert suggestion.band is ConfidenceBand.AUTO_APPLY
    assert suggestion.applied is False
    assert suggestion.blocked_reason == "below_human_review_threshold"


def test_decide_keeps_top_three_probabilities_rounded_and_ordered():
    answer = ChoiceResult(
        choice="shipping",
        confidence=0.9,
        probabilities={"shipping": 0.90005, "receiving": 0.05, "cooling": 0.03, "harvesting": 0.0199},
    )
    suggestion = decide(answer, thresholds=THRESHOLDS, apply_enabled=True, reversed_answer=_twin())

    assert suggestion.probabilities == {"shipping": 0.9001, "receiving": 0.05, "cooling": 0.03}
    assert list(suggestion.probabilities) == ["shipping", "receiving", "cooling"]


def test_suggestion_to_dict_round_trip():
    suggestion = decide(
        _choice("receiving", 0.96, shipping=0.03),
        thresholds=THRESHOLDS,
        apply_enabled=True,
        reversed_answer=_twin("receiving"),
    )

    assert suggestion.to_dict() == {
        "cte_type": "receiving",
        "confidence": pytest.approx(0.96),
        "band": "auto_apply",
        "probabilities": {"receiving": 0.96, "shipping": 0.03},
        "applied": True,
        "blocked_reason": None,
    }


def test_empty_result_is_not_ok_and_applies_nothing():
    result = CteClassificationResult(status="unavailable:timeout")

    assert result.ok is False
    assert result.suggestion is None
    assert result.applied_cte_type is None


def test_samples_reach_the_request_state_only_when_given():
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        seen.setdefault("bodies", []).append(body)
        payload = {
            QUESTION_ID: {
                "type": "choice",
                "choice": "shipping",
                "confidence": 0.97,
                "probabilities": {"shipping": 0.97},
            },
            REVERSED_QUESTION_ID: {
                "type": "choice",
                "choice": "shipping",
                "confidence": 0.97,
                "probabilities": {"shipping": 0.97},
            },
        }
        return httpx2.Response(
            200,
            headers={"x-typesafe-request-id": "req_decide"},
            json={"model": "jev-1.13.0", "answers": payload, "usage": {"input_tokens": 90, "output_tokens": 2}},
        )

    decider = JevDecider(
        JevSettings(api_key="k", max_retries=0, timeout_seconds=1.0), transport=httpx2.MockTransport(handler)
    )
    result = suggest_file_cte_type(HEADERS, samples={"Customer": ["ACME"]}, decider=decider)

    assert result.ok
    assert seen["bodies"][0]["state"] == build_state(HEADERS, {"Customer": ["ACME"]})
    assert result.applied_cte_type is None
