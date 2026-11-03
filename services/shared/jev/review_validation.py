"""Strict review-answer checks, applied before the advisory client's coercion."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

TOLERANCE = 0.001


class ReviewContractError(ValueError):
    """A malformed response, never an evidence verdict. Messages omit input data."""


def _mapping(value: Any) -> Mapping:
    if not isinstance(value, Mapping):
        raise ReviewContractError("Expected an object")
    return value


def _number(value: Any, maximum: float = 1) -> float:
    if type(value) not in (int, float) or not 0 <= value <= maximum or not math.isfinite(value):
        raise ReviewContractError("Missing, non-finite, or out-of-range number")
    return value


def validate_review_answers(answers: Any, questions: Mapping[str, Any]) -> None:
    """Validate raw JSON without repairing probabilities or accepting numeric strings."""
    answers = _mapping(answers)
    if set(answers) != set(questions):
        raise ReviewContractError("Answer keys differ from requested questions")
    for question_id, question in questions.items():
        if not isinstance(question, Mapping):
            question = question.model_dump(mode="json")
        answer = _mapping(answers[question_id])
        kind = question.get("type")
        if kind not in {"choice", "score", "noul"} or answer.get("type") != kind:
            raise ReviewContractError("Wrong answer type")
        if kind == "noul":
            _number(answer.get("noul"))
            continue
        criteria = question["criteria"]
        keys = set(criteria) if kind == "choice" else {str(i) for i in range(len(criteria))}
        probabilities = _mapping(answer.get("probabilities"))
        if set(probabilities) != keys:
            raise ReviewContractError("Probability keys differ from criteria")
        values = [_number(p) for p in probabilities.values()]
        if abs(sum(values) - 1) > TOLERANCE:
            raise ReviewContractError("Probabilities do not sum to one")
        _number(answer.get("confidence"))
        if kind == "choice":
            choice = answer.get("choice")
            if not isinstance(choice, str) or choice not in keys:
                raise ReviewContractError("Unknown choice")
            if probabilities[choice] + TOLERANCE < max(values):
                raise ReviewContractError("Choice is not a maximum-probability option")
        else:
            score = _number(answer.get("score"), len(criteria) - 1)
            expected = sum(int(key) * value for key, value in probabilities.items())
            if abs(score - expected) > TOLERANCE * len(criteria):
                raise ReviewContractError("Score disagrees with distribution")
            legend = _mapping(answer.get("legend"))
            if dict(legend) != {str(i): text for i, text in enumerate(criteria)}:
                raise ReviewContractError("Score legend differs from criteria")
