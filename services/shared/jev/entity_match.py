"""Which existing entity, if any, an incoming name refers to, answered by Jev.

Why this exists
---------------
``IdentityResolutionService.find_potential_matches`` ranks candidate entities
by a lexical ratio (``difflib.SequenceMatcher``) over the pg_trgm pre-filtered
alias pool (#1208). A lexical ratio cannot tell that "ACME Foods Inc." and
"Acme Food Company" are one supplier while "Acme Farms" and "Acme Foods" are
two, and its 0.6 cutoff behaves differently per tenant. One ``Choice``
question asks Jev which candidate (or none) is the same real-world business.

Scope: shadow only
------------------
This module **never changes a resolution outcome**. It takes the candidates
``find_potential_matches`` already returned, asks one question, and reports
Jev's pick, its confidence band, and whether it agrees with the lexical top
match. Callers log/count the result so the agreement rate can be measured on
real traffic before any decision is handed to the model. Nothing here writes
to ``fsma.*``.

What leaves the process: the incoming name, the requested entity type, and
for each candidate its canonical name, matched alias, entity type and lexical
score. No GLN/GTIN/FDA registration values, no addresses or contacts, and only
candidates the caller already scoped to one tenant.

Policy
------
* No candidates: no call (``status == "no_candidates"``).
* Candidates beyond :data:`MAX_CANDIDATES` are dropped (lexical order kept).
* Jev may answer :data:`NO_MATCH`; that is a first-class outcome.
* Any provider failure yields a status (``unavailable:<reason>``), never an
  exception, so the deterministic path is untouched.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

from .client import JevDecider, JevEvidence, JevUnavailable, get_jev_decider
from .routing import ConfidenceBand, ConfidenceThresholds, band_for_confidence

logger = structlog.get_logger("jev.entity_match")

# Bump whenever question text, option meaning or a state key changes.
QUESTIONS_VERSION = "entity-match.v1"
PURPOSE = "identity_entity_match"
QUESTION_ID = "same_entity"
NO_MATCH = "none_of_these"
MAX_CANDIDATES = 10
_OPTION_PREFIX = "candidate_"


def _option_key(index: int) -> str:
    return f"{_OPTION_PREFIX}{index + 1}"


def _candidates(candidates: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Unique entity ids, lexical order kept, capped at :data:`MAX_CANDIDATES`."""
    seen: set[str] = set()
    kept: list[Mapping[str, Any]] = []
    for candidate in candidates:
        entity_id = str(candidate.get("entity_id") or "")
        if not entity_id or entity_id in seen:
            continue
        seen.add(entity_id)
        kept.append(candidate)
        if len(kept) == MAX_CANDIDATES:
            break
    return kept


def build_state(
    search_name: str,
    candidates: Sequence[Mapping[str, Any]],
    *,
    entity_type: Optional[str] = None,
) -> dict[str, Any]:
    """Names and types only; identifiers and contact data never leave the process."""
    state: dict[str, Any] = {
        "incoming_name": (search_name or "").strip(),
        "candidates": [
            {
                "option": _option_key(index),
                "canonical_name": candidate.get("canonical_name") or "",
                "matched_alias": candidate.get("matched_alias") or "",
                "entity_type": candidate.get("entity_type") or "",
                "lexical_similarity": candidate.get("confidence"),
            }
            for index, candidate in enumerate(candidates)
        ],
    }
    if entity_type:
        state["incoming_entity_type"] = entity_type
    return state


def build_questions(candidate_count: int) -> dict[str, dict[str, Any]]:
    """One Choice: a candidate option per row, plus :data:`NO_MATCH`."""
    criteria: dict[str, dict[str, Any]] = {
        _option_key(index): {
            "what": (
                f"The incoming name refers to the same real-world business or location as the candidate "
                f"whose `option` is {_option_key(index)}."
            ),
        }
        for index in range(candidate_count)
    }
    criteria[NO_MATCH] = {
        "what": "The incoming name refers to a business or location that none of the candidates are.",
        "examples": [
            "Same leading word but a different business: 'Acme Farms' vs 'Acme Foods'.",
            "A different site or division named separately: 'Sysco Houston' vs 'Sysco Dallas'.",
        ],
    }
    return {
        QUESTION_ID: {
            "type": "choice",
            "instructions": {
                "task": (
                    "Decide which candidate in `candidates`, if any, is the same real-world supply-chain "
                    "business or location as `incoming_name`."
                ),
                "guidance": (
                    "Treat legal suffixes (Inc, LLC, Co, Corp), punctuation, case and common abbreviations as "
                    "insignificant. `lexical_similarity` is a spelling hint only; a high value does not make "
                    f"two different businesses the same. Choose {NO_MATCH} when no candidate is clearly the "
                    "same business."
                ),
            },
            "criteria": criteria,
        }
    }


@dataclass(frozen=True)
class EntityMatchSuggestion:
    """Jev's pick, mapped back to an entity id (``None`` for :data:`NO_MATCH`)."""

    entity_id: Optional[str]
    confidence: float
    band: ConfidenceBand
    probabilities: dict[str, float] = field(default_factory=dict)  # entity_id or NO_MATCH -> p

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "confidence": self.confidence,
            "band": self.band.value,
            "probabilities": dict(self.probabilities),
        }


@dataclass(frozen=True)
class EntityMatchResult:
    """Shadow comparison for one lookup. Never applied to resolution."""

    status: str
    lexical_top_entity_id: Optional[str] = None
    suggestion: Optional[EntityMatchSuggestion] = None
    evidence: Optional[JevEvidence] = None
    candidate_count: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def agrees(self) -> Optional[bool]:
        """Jev's pick equals the lexical top match; ``None`` when there is no answer."""
        if self.suggestion is None:
            return None
        return self.suggestion.entity_id == self.lexical_top_entity_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "lexical_top_entity_id": self.lexical_top_entity_id,
            "suggestion": self.suggestion.to_dict() if self.suggestion else None,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "candidate_count": self.candidate_count,
            "agrees": self.agrees,
        }


def shadow_match_entity(
    search_name: str,
    candidates: Sequence[Mapping[str, Any]],
    *,
    entity_type: Optional[str] = None,
    decider: Optional[JevDecider] = None,
    thresholds: Optional[ConfidenceThresholds] = None,
) -> EntityMatchResult:
    """Ask Jev which of ``candidates`` (the output of ``find_potential_matches``) is ``search_name``.

    Returns a result for logging and evaluation only. Never raises on provider
    failure and never mutates state.
    """
    kept = _candidates(candidates)
    lexical_top = str(kept[0]["entity_id"]) if kept else None
    if not kept:
        return EntityMatchResult(status="no_candidates")

    decider = decider if decider is not None else get_jev_decider()
    thresholds = thresholds if thresholds is not None else ConfidenceThresholds()
    try:
        answers = decider.ask(
            build_state(search_name, kept, entity_type=entity_type),
            build_questions(len(kept)),
            purpose=PURPOSE,
            questions_version=QUESTIONS_VERSION,
        )
    except JevUnavailable as exc:
        return EntityMatchResult(
            status=f"unavailable:{exc.reason}", lexical_top_entity_id=lexical_top, candidate_count=len(kept)
        )

    answer = answers.choices.get(QUESTION_ID)
    by_option = {_option_key(index): str(candidate["entity_id"]) for index, candidate in enumerate(kept)}
    if answer is None or (answer.choice != NO_MATCH and answer.choice not in by_option):
        logger.warning("jev.entity_match.unusable_answer", request_id=answers.evidence.request_id)
        return EntityMatchResult(
            status="invalid_answer",
            lexical_top_entity_id=lexical_top,
            evidence=answers.evidence,
            candidate_count=len(kept),
        )

    probabilities = {
        (NO_MATCH if option == NO_MATCH else by_option[option]): p
        for option, p in answer.probabilities.items()
        if option == NO_MATCH or option in by_option
    }
    suggestion = EntityMatchSuggestion(
        entity_id=None if answer.choice == NO_MATCH else by_option[answer.choice],
        confidence=answer.confidence,
        band=band_for_confidence(answer.confidence, thresholds),
        probabilities=probabilities,
    )
    result = EntityMatchResult(
        status="ok",
        lexical_top_entity_id=lexical_top,
        suggestion=suggestion,
        evidence=answers.evidence,
        candidate_count=len(kept),
    )
    logger.info(
        "jev.entity_match.shadow",
        request_id=answers.evidence.request_id,
        candidate_count=len(kept),
        band=suggestion.band.value,
        no_match=suggestion.entity_id is None,
        agrees=result.agrees,
    )
    return result
