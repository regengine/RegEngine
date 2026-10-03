"""Which FSMA 204 critical tracking event a CSV upload records, answered by Jev.

Why this exists
---------------
The upload UI never sends ``cte_type`` (``frontend/src/lib/api-client.ts``
calls ``ingestFile`` without it), so the CSV parser reads each row's CTE
from a ``cte_type``/``event_type`` column (``_detect_row_cte_type`` in
``services/ingestion/app/csv_templates.py``). A supplier export without such
a column -- the usual shape of an ERP shipping or receiving log -- has every
row rejected with "No CTE type". One ``Choice`` question asks Jev which CTE
the whole file records, from its header row.

When it is asked
----------------
Only when the uploader declared no CTE and no column carries per-row CTE
values (the route checks both). Anything else already gives the parser each
row's CTE, and the answer could at best repeat it.

Policy
------
The answer is always reported (the upload response, and the 400 body when no
row parses), so the uploader can re-upload with that CTE in one step. It
becomes the file's fallback CTE only when all of the following hold:

* the operator enabled ``REGENGINE_JEV_APPLY_FILE_CTE_TYPE``;
* the answer names one CTE, not ``mixed_or_unclear``;
* its confidence is in the AUTO_APPLY band and clears the agent-artifact
  human-review threshold.

A row's own CTE value still wins wherever it exists: the parser reads the
row first and falls back to the file CTE. Every actionable answer is recorded
as an advisory ``field_mapping_suggestion`` artifact targeting ``cte_type``,
anchored to the upload's SHA-256 and ingestion run.

What leaves the process: the CSV header row and, only when
``REGENGINE_JEV_HEADER_SAMPLE_VALUES`` is set, the same PII-redacted sample
values the header mapping sends for unrecognised columns. Never rows. A
header row that fails :func:`shared.jev.header_mapping.malformed_header_reason`
is refused and nothing is sent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import structlog
from shared.agent_artifacts import (
    AGENT_ARTIFACT_VERSION,
    HUMAN_REVIEW_CONFIDENCE_THRESHOLD,
    AgentArtifact,
    AgentArtifactContext,
    FieldMappingSuggestionPayload,
)

from .client import JevDecider, JevEvidence, JevUnavailable, get_jev_decider
from .header_mapping import MALFORMED_HEADER, malformed_header_reason
from .routing import ConfidenceBand, ConfidenceThresholds, band_for_confidence

logger = structlog.get_logger("jev.cte_classification")

# Recorded with every answer and artifact. Bump it whenever the question
# text, the vocabulary or the meaning of a state key changes.
# v2: the same question is also asked with the options reversed, in the same
# request, and an answer is applied only when both orders agree.
QUESTIONS_VERSION = "csv-file-cte.v2"
AGENT_NAME = "jev-csv-cte-classifier"
PURPOSE = "csv_file_cte_type"
QUESTION_ID = "file_cte"
# Jev 1.13 leans toward the first option of a Choice (TypeSafe's published
# model jaggedness, item 8). The vendor's remedy is to reorder the options and
# check the answer holds; the reversed copy rides in the same request, which
# runs questions in parallel, so it costs ~700 input tokens and no latency.
REVERSED_QUESTION_ID = "file_cte_reversed"
MIXED_OR_UNCLEAR = "mixed_or_unclear"
# The artifact's ``source_field``: the answer is about the file, not a column.
FILE_SOURCE_FIELD = "csv_file"
TARGET_FIELD = "cte_type"

# The FDA-defined CTEs the parser accepts, with descriptions that follow the
# vendor guidance for confusable options: what it is, what it is not, and
# headers that typically identify it. ``growing`` is RegEngine-internal and
# not an FDA CTE, so it is never suggested.
CTE_CRITERIA: dict[str, dict[str, Any]] = {
    "harvesting": {
        "what": "Harvesting a raw agricultural commodity from the field or growing area where it grew.",
        "not_for": "Cooling, packing, shipping or receiving of product that was already harvested.",
        "examples": ["Harvest Date", "Field", "Field ID", "Ranch", "Block", "Harvester", "Crew", "Growing Area"],
    },
    "cooling": {
        "what": "Cooling a raw agricultural commodity before its initial packing, such as hydrocooling or "
        "forced-air cooling after harvest.",
        "not_for": "Storage or transit temperatures recorded while shipping or receiving.",
        "examples": ["Cooling Date", "Cooler", "Cooling Location", "Precool", "Hydrocooler", "Pulp Temp"],
    },
    "initial_packing": {
        "what": "The first packing of a raw agricultural commodity after harvest, usually at a packinghouse.",
        "not_for": "Repacking or relabeling product that was already packed, which is transformation.",
        "examples": ["Pack Date", "Packed Date", "Packinghouse", "Harvest Lot", "Harvester Business Name", "Packer"],
    },
    "first_land_based_receiving": {
        "what": "Taking possession on land, for the first time, of food caught by a fishing vessel.",
        "not_for": "Receiving food from another land-based business.",
        "examples": ["Landing Date", "Vessel", "Vessel Name", "Harvest Area", "Dock", "Catch Date"],
    },
    "shipping": {
        "what": "Sending food to another location or business: every row is an outbound shipment.",
        "not_for": "Inbound deliveries received from a supplier; production or inventory records.",
        "examples": ["Ship Date", "Ship To", "Destination", "Consignee", "Customer", "Carrier", "BOL", "Shipped Qty"],
    },
    "receiving": {
        "what": "Receiving food from another location or business: every row is an inbound delivery.",
        "not_for": "Outbound shipments to customers; the first receipt of food from a fishing vessel.",
        "examples": ["Receive Date", "Received Date", "Receiving Location", "Received From", "Supplier", "Vendor"],
    },
    "transformation": {
        "what": "Manufacturing, processing, commingling, repacking or relabeling that turns input lots into a "
        "new product lot.",
        "not_for": "Moving or storing a lot without changing it.",
        "examples": ["Production Date", "Input Lot", "Ingredient Lot", "Output Lot", "Batch Record", "Work Order"],
    },
    MIXED_OR_UNCLEAR: {
        "what": "The rows record more than one kind of event, or the headers do not show which event they record.",
        "examples": ["Transaction Type", "Activity", "Movement", "Date", "Location"],
    },
}

CTE_NAMES: frozenset[str] = frozenset(name for name in CTE_CRITERIA if name != MIXED_OR_UNCLEAR)


def build_state(headers: Sequence[str], samples: Mapping[str, Sequence[str]] | None = None) -> dict[str, Any]:
    """The whole header row, plus redacted sample values only when the operator allows them."""
    state: dict[str, Any] = {"csv_headers": [(header or "").strip() for header in headers]}
    values = {header: list(found) for header, found in (samples or {}).items() if found}
    if values:
        state["sample_values"] = values
    return state


def build_questions() -> dict[str, dict[str, Any]]:
    """The Choice question over the CTE vocabulary, keyed :data:`QUESTION_ID`, and its
    reversed-order twin, keyed :data:`REVERSED_QUESTION_ID`."""
    question = _question(CTE_CRITERIA)
    return {
        QUESTION_ID: question,
        REVERSED_QUESTION_ID: {**question, "criteria": dict(reversed(list(CTE_CRITERIA.items())))},
    }


def _question(criteria: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": {
            "task": (
                "Decide which FSMA 204 critical tracking event (CTE) every row of this CSV file records. "
                "Use the column headers in `csv_headers`, and `sample_values` when the state has them."
            ),
            "guidance": (
                "Choose a CTE only when the headers show that every row records that one event. "
                f"Choose {MIXED_OR_UNCLEAR} when rows could record different events or the headers do "
                "not show which event. Do not guess from the product or the file's other columns alone."
            ),
        },
        "criteria": criteria,
    }


@dataclass(frozen=True)
class CteTypeSuggestion:
    """Jev's read on the file's CTE and what code did with it."""

    cte_type: Optional[str]
    confidence: float
    band: ConfidenceBand
    probabilities: dict[str, float] = field(default_factory=dict)
    applied: bool = False
    blocked_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cte_type": self.cte_type,
            "confidence": self.confidence,
            "band": self.band.value,
            "probabilities": dict(self.probabilities),
            "applied": self.applied,
            "blocked_reason": self.blocked_reason,
        }


@dataclass(frozen=True)
class CteClassificationResult:
    """The suggestion for one upload plus the evidence for the Jev call."""

    status: str
    suggestion: Optional[CteTypeSuggestion] = None
    evidence: Optional[JevEvidence] = None
    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    apply_enabled: bool = False
    headers: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def applied_cte_type(self) -> Optional[str]:
        """The CTE the parser must use as the file's fallback, or ``None``."""
        if self.suggestion is not None and self.suggestion.applied:
            return self.suggestion.cte_type
        return None


def _top_probabilities(probabilities: Mapping[str, float], limit: int = 3) -> dict[str, float]:
    ordered = sorted(probabilities.items(), key=lambda item: (-item[1], item[0]))
    return {label: round(float(p), 4) for label, p in ordered[:limit]}


def _cte_of(answer: Any) -> Optional[str]:
    return answer.choice if answer.choice in CTE_NAMES else None


def decide(
    answer: Any,
    *,
    thresholds: ConfidenceThresholds,
    apply_enabled: bool,
    reversed_answer: Any | None = None,
) -> CteTypeSuggestion:
    """Turn the Choice answer into a suggestion and apply the policy deterministically.

    ``reversed_answer`` is the same question with the options in reverse
    order. An answer that would be applied is applied only when it names the
    same CTE; a missing twin blocks it too.
    """
    cte_type = _cte_of(answer)
    confidence = float(answer.confidence)
    band = band_for_confidence(confidence, thresholds)
    blocked: Optional[str] = None
    if cte_type is None:
        blocked = MIXED_OR_UNCLEAR
    elif band is not ConfidenceBand.AUTO_APPLY:
        blocked = "below_auto_apply_threshold"
    elif confidence < HUMAN_REVIEW_CONFIDENCE_THRESHOLD:
        blocked = "below_human_review_threshold"
    elif not apply_enabled:
        blocked = "apply_disabled"
    elif reversed_answer is None:
        blocked = "order_check_unavailable"
    elif _cte_of(reversed_answer) != cte_type:
        blocked = "order_inconsistent"
    return CteTypeSuggestion(
        cte_type=cte_type,
        confidence=confidence,
        band=band,
        probabilities=_top_probabilities(answer.probabilities),
        applied=blocked is None,
        blocked_reason=blocked,
    )


def suggest_file_cte_type(
    headers: Sequence[str | None],
    *,
    samples: Mapping[str, Sequence[str]] | None = None,
    decider: JevDecider | None = None,
) -> CteClassificationResult:
    """Ask Jev which CTE the file records. Never raises.

    The caller decides *whether* to ask (no declared CTE, no per-row CTE
    column); this function only asks and applies the policy. The decider's
    settings supply the thresholds and the apply switch.
    """
    decider = decider if decider is not None else get_jev_decider()
    settings = decider.settings
    thresholds = settings.thresholds
    apply_enabled = settings.apply_file_cte_type

    if not decider.enabled:
        return CteClassificationResult(status="disabled", thresholds=thresholds, apply_enabled=apply_enabled)
    if malformed_header_reason(headers):
        return CteClassificationResult(status=MALFORMED_HEADER, thresholds=thresholds, apply_enabled=apply_enabled)
    cleaned = tuple((header or "").strip() for header in headers)
    if not any(cleaned):
        return CteClassificationResult(status="no_headers", thresholds=thresholds, apply_enabled=apply_enabled)

    try:
        answers = decider.ask(
            build_state(cleaned, samples),
            build_questions(),
            purpose=PURPOSE,
            questions_version=QUESTIONS_VERSION,
        )
    except JevUnavailable as exc:
        return CteClassificationResult(
            status=f"unavailable:{exc.reason}", thresholds=thresholds, apply_enabled=apply_enabled, headers=cleaned
        )
    except Exception:  # noqa: BLE001 - the upload must not fail because a suggestion did.
        logger.exception("jev.cte_classification.error", column_count=len(cleaned))
        return CteClassificationResult(
            status="error", thresholds=thresholds, apply_enabled=apply_enabled, headers=cleaned
        )

    answer = answers.choices.get(QUESTION_ID)
    if answer is None:
        return CteClassificationResult(
            status="no_answer",
            evidence=answers.evidence,
            thresholds=thresholds,
            apply_enabled=apply_enabled,
            headers=cleaned,
        )
    suggestion = decide(
        answer,
        thresholds=thresholds,
        apply_enabled=apply_enabled,
        reversed_answer=answers.choices.get(REVERSED_QUESTION_ID),
    )
    logger.info(
        "jev.cte_classification.suggested",
        cte_type=suggestion.cte_type,
        confidence=round(suggestion.confidence, 4),
        band=suggestion.band.value,
        applied=suggestion.applied,
        blocked_reason=suggestion.blocked_reason,
        request_id=answers.evidence.request_id,
    )
    return CteClassificationResult(
        status="ok",
        suggestion=suggestion,
        evidence=answers.evidence,
        thresholds=thresholds,
        apply_enabled=apply_enabled,
        headers=cleaned,
    )


def _rationale(suggestion: CteTypeSuggestion, result: CteClassificationResult) -> str:
    parts = [
        f"TypeSafe Jev Choice question ({QUESTIONS_VERSION}) over the FSMA 204 CTE vocabulary, "
        "asked because the upload declared no CTE and has no per-row CTE column.",
        f"Top probabilities: {suggestion.probabilities}.",
        f"Confidence {suggestion.confidence:.3f} falls in band '{suggestion.band.value}' "
        f"(auto_apply >= {result.thresholds.auto_apply}, review >= {result.thresholds.review}).",
        "Applied as the file's fallback CTE by deterministic code; a row's own CTE value still wins. "
        "The answer held with the options in reverse order."
        if suggestion.applied
        else f"Not applied (reason: {suggestion.blocked_reason}); rows without a CTE were rejected.",
    ]
    if result.evidence is not None:
        parts.append(
            f"Model {result.evidence.model}, request {result.evidence.request_id or 'n/a'}, "
            f"latency {result.evidence.latency_ms} ms."
        )
    return " ".join(parts)


def build_cte_type_artifacts(
    result: CteClassificationResult,
    *,
    tenant_id: str | UUID,
    source_hash: str,
    ingestion_run_id: str | UUID | None = None,
    now: datetime | None = None,
) -> list[AgentArtifact]:
    """An advisory ``field_mapping_suggestion`` artifact targeting ``cte_type``.

    ``mixed_or_unclear`` and ``REJECT``-band answers produce none: there is
    nothing for a reviewer to accept. An applied answer is recorded with
    ``requires_human_review=False`` (its confidence cleared the artifact
    threshold); anything else asks for review.
    """
    suggestion = result.suggestion
    if not result.ok or suggestion is None or suggestion.cte_type is None or suggestion.band is ConfidenceBand.REJECT:
        return []
    run_uuid: Optional[UUID] = None
    if ingestion_run_id:
        try:
            run_uuid = UUID(str(ingestion_run_id))
        except ValueError:
            run_uuid = None
    model_name = f"typesafe/{result.evidence.model}" if result.evidence else "typesafe/jev"
    return [
        AgentArtifact(
            artifact_id=uuid4(),
            artifact_version=AGENT_ARTIFACT_VERSION,
            artifact_type="field_mapping_suggestion",
            tenant_id=UUID(str(tenant_id)),
            created_at=now or datetime.now(timezone.utc),
            agent_name=AGENT_NAME,
            agent_version=QUESTIONS_VERSION,
            model_name=model_name,
            suggestion=(
                f"Treat every row of this CSV file as a {suggestion.cte_type} event "
                f"({'applied' if suggestion.applied else 'advisory'}, confidence {suggestion.confidence:.2f})."
            ),
            confidence=suggestion.confidence,
            requires_human_review=not suggestion.applied,
            context=AgentArtifactContext(
                ingestion_run_id=run_uuid,
                source_hashes=[source_hash],
                request_id=result.evidence.request_id if result.evidence else None,
            ),
            payload=FieldMappingSuggestionPayload(
                source_field=FILE_SOURCE_FIELD,
                source_value=list(result.headers),
                target_canonical_field=TARGET_FIELD,
                normalized_value=suggestion.cte_type,
                rationale=_rationale(suggestion, result),
            ),
        )
    ]
