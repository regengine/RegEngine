"""A deterministic, offline stand-in for TypeSafe Jev. Its answers are not Jev's.

It speaks the same wire format as ``api.typesafe.ai`` so the real
:class:`shared.jev.JevDecider` (and the TypeSafe SDK under it) can talk to it
through an ``httpx2.MockTransport``. Nothing leaves the process. Jev Lab uses
it for ``--fake`` runs and the tests use it to drive the loop end to end.

How it answers:

* ``choice``: bag-of-words overlap between the subject (the column header a
  header-mapping question points at, the header row of a file question, or the
  state text of an ad-hoc question) and each option's description. Tokens in
  ``what`` and ``examples`` count for an option, tokens in ``not_for`` count
  against it, each weighted by how few options use it (a word every date
  field shares says little), and a subject that equals one of an option's
  examples gets a bonus. A softmax turns the scores into probabilities; ``confidence`` is
  ``1 - entropy / log(options)``, how concentrated they are, which is what
  Jev's confidence describes. With no overlap at all the probabilities are
  flat, confidence is 0 and a "nothing fits" option wins the tie.
* ``noul``: p(yes) rises with the overlap between the question and the state.
* ``score``: a distribution over the levels centred where the overlap points.

It does not expand abbreviations, so "Dte" does not read as "date" until a
description mentions it. That is the gap the offline proposer closes, which
lets the loop show real accept and reject decisions without any key.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

import httpx2

MODEL = "fake-jev-offline"
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_STOPWORDS = frozenset(
    "a an and any are as at be by each for from has have in is it its of on or that the their this to was were "
    "which with when where who whose what does do not no".split()
)
_NONE_OPTIONS = ("no_match", "mixed_or_unclear", "unclear", "none_of_these", "none")
_TEMPERATURE = 0.35
_EXAMPLE_BONUS = 3.0
_NOT_FOR_WEIGHT = 0.6


def tokens(text: Any) -> list[str]:
    """Lower-case word tokens, split at camelCase and punctuation, without stopwords."""
    if text is None:
        return []
    if not isinstance(text, str):
        text = json.dumps(text, sort_keys=True)
    text = _CAMEL_RE.sub(" ", text.replace("_", " "))
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS]


def _normalized(text: str) -> str:
    return " ".join(tokens(text))


def _option_texts(name: str, description: Any) -> tuple[set[str], set[str], set[str]]:
    """``(for_tokens, against_tokens, example_phrases)`` for one option."""
    positive = set(tokens(name))
    negative: set[str] = set()
    examples: set[str] = set()
    if isinstance(description, Mapping):
        positive |= set(tokens(description.get("what")))
        negative |= set(tokens(description.get("not_for")))
        for example in description.get("examples") or ():
            positive |= set(tokens(example))
            examples.add(_normalized(str(example)))
    elif description is not None:
        positive |= set(tokens(description))
    return positive, negative - positive, examples


def _options(criteria: Any) -> list[tuple[str, Any]]:
    if isinstance(criteria, Mapping):
        return [(str(name), description) for name, description in criteria.items()]
    if isinstance(criteria, Iterable) and not isinstance(criteria, (str, bytes)):
        return [(str(name), None) for name in criteria]
    return []


def _softmax(scores: list[float]) -> list[float]:
    top = max(scores)
    weights = [math.exp((score - top) / _TEMPERATURE) for score in scores]
    total = sum(weights)
    return [weight / total for weight in weights]


def _concentration(probabilities: list[float]) -> float:
    if len(probabilities) < 2:
        return 1.0
    entropy = -sum(p * math.log(p) for p in probabilities if p > 0)
    return max(0.0, min(1.0, 1.0 - entropy / math.log(len(probabilities))))


def _subject(state: Any, question: Mapping[str, Any]) -> tuple[list[str], str | None]:
    """The tokens a question is about, and the whole subject phrase when it is one header."""
    instructions = question.get("instructions")
    if isinstance(instructions, Mapping):
        column = instructions.get("column")
        if isinstance(column, Mapping) and isinstance(column.get("header"), str):
            return tokens(column["header"]), _normalized(column["header"])
    if isinstance(state, Mapping) and isinstance(state.get("csv_headers"), list):
        return tokens(" ".join(str(h) for h in state["csv_headers"])), None
    words = tokens(state)
    if isinstance(instructions, str):
        words += tokens(instructions)
    return words, None


def answer_choice(state: Any, question: Mapping[str, Any]) -> dict[str, Any]:
    options = _options(question.get("criteria"))
    if not options:
        return {"type": "choice", "choice": "", "confidence": 0.0, "probabilities": {}}
    subject, phrase = _subject(state, question)
    subject_set = set(subject)
    texts = [_option_texts(name, description) for name, description in options]
    frequency: dict[str, int] = {}
    for positive, _, _ in texts:
        for token in positive:
            frequency[token] = frequency.get(token, 0) + 1

    def weight(token: str) -> float:
        return math.log(1.0 + len(options) / frequency.get(token, 1))

    scores = []
    for positive, negative, examples in texts:
        score = sum(weight(t) for t in subject_set & positive) - _NOT_FOR_WEIGHT * sum(
            weight(t) for t in subject_set & negative
        )
        if phrase and phrase in examples:
            score += _EXAMPLE_BONUS
        scores.append(float(score))
    probabilities = _softmax(scores)
    best = max(probabilities)
    tied = [name for (name, _), p in zip(options, probabilities) if math.isclose(p, best, rel_tol=1e-9)]
    choice = next((name for name in tied if name in _NONE_OPTIONS), tied[0])
    return {
        "type": "choice",
        "choice": choice,
        "confidence": round(_concentration(probabilities), 6),
        "probabilities": {name: round(p, 6) for (name, _), p in zip(options, probabilities)},
    }


def answer_noul(state: Any, question: Mapping[str, Any]) -> dict[str, Any]:
    asked = set(tokens(question.get("instructions")))
    overlap = len(asked & set(tokens(state)))
    return {"type": "noul", "noul": round(1.0 / (1.0 + math.exp(-(overlap - 1.5))), 6)}


def answer_score(state: Any, question: Mapping[str, Any]) -> dict[str, Any]:
    levels = [str(level) for level in (question.get("criteria") or [])] or ["low", "high"]
    asked = set(tokens(question.get("instructions")))
    overlap = len(asked & set(tokens(state)))
    centre = min(len(levels) - 1, overlap)
    raw = [math.exp(-((index - centre) ** 2)) for index in range(len(levels))]
    total = sum(raw)
    probabilities = [value / total for value in raw]
    expected = sum(index * p for index, p in enumerate(probabilities))
    return {
        "type": "score",
        "score": round(expected, 6),
        "confidence": round(_concentration(probabilities), 6),
        "probabilities": {str(index): round(p, 6) for index, p in enumerate(probabilities)},
        "legend": {str(index): level for index, level in enumerate(levels)},
    }


_ANSWERERS = {"choice": answer_choice, "noul": answer_noul, "score": answer_score}


def answer(state: Any, questions: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """The response body for one request."""
    answers = {}
    for question_id, question in questions.items():
        answerer = _ANSWERERS.get(str(question.get("type", "choice")))
        if answerer is not None:
            answers[question_id] = answerer(state, question)
    return {
        "model": MODEL,
        "answers": answers,
        "usage": {"input_tokens": len(json.dumps({"state": state, "questions": questions})) // 3, "output_tokens": 1},
    }


def handler(request: httpx2.Request) -> httpx2.Response:
    body = json.loads(request.content or b"{}")
    digest = hashlib.sha256(request.content or b"").hexdigest()[:16]
    return httpx2.Response(
        200,
        headers={"x-typesafe-request-id": f"fake_{digest}"},
        json=answer(body.get("state"), body.get("questions") or {}),
    )


def transport() -> httpx2.MockTransport:
    """An ``httpx2`` transport that answers every request with :func:`answer`."""
    return httpx2.MockTransport(handler)
