"""Typed advisory artifacts emitted by RegEngine intelligence agents.

The evidence layer is deterministic and append-only. These models define the
small, typed language agents may use to make FSMA-specific suggestions without
mutating canonical evidence directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

AGENT_ARTIFACT_VERSION = "agent-artifact.v1"
HUMAN_REVIEW_CONFIDENCE_THRESHOLD = 0.85

SHA256_HEX_PATTERN = r"^[A-Fa-f0-9]{64}$"
SHA256Hex = Annotated[str, StringConstraints(pattern=SHA256_HEX_PATTERN)]

ArtifactType = Literal[
    "field_mapping_suggestion",
    "identity_match_suggestion",
    "validation_explanation",
    "review_routing_suggestion",
    "export_readiness_summary",
]


class StrictArtifactModel(BaseModel):
    """Base model for artifact contracts; unexpected fields are contract drift."""

    model_config = ConfigDict(extra="forbid")


class AgentArtifactContext(StrictArtifactModel):
    """Traceability context required for every advisory artifact."""

    evidence_ids: list[UUID] = Field(default_factory=list)
    canonical_event_ids: list[UUID] = Field(default_factory=list)
    ingestion_run_id: Optional[UUID] = None
    source_hashes: list[SHA256Hex] = Field(default_factory=list)
    rule_id: Optional[str] = Field(default=None, min_length=1)
    rule_version: Optional[int] = Field(default=None, ge=1)
    citation_reference: Optional[str] = None
    request_id: Optional[str] = None

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "anyOf": [
                {
                    "required": ["evidence_ids"],
                    "properties": {"evidence_ids": {"minItems": 1}},
                },
                {
                    "required": ["canonical_event_ids"],
                    "properties": {"canonical_event_ids": {"minItems": 1}},
                },
                {
                    "required": ["ingestion_run_id"],
                    "properties": {"ingestion_run_id": {"type": "string", "format": "uuid"}},
                },
                {
                    "required": ["source_hashes"],
                    "properties": {"source_hashes": {"minItems": 1}},
                },
            ],
            "allOf": [
                {
                    "if": {
                        "required": ["rule_id"],
                        "properties": {"rule_id": {"type": "string"}},
                    },
                    "then": {
                        "required": ["rule_version"],
                        "properties": {"rule_version": {"type": "integer", "minimum": 1}},
                    },
                },
                {
                    "if": {
                        "required": ["rule_version"],
                        "properties": {"rule_version": {"type": "integer"}},
                    },
                    "then": {
                        "required": ["rule_id"],
                        "properties": {"rule_id": {"type": "string", "minLength": 1}},
                    },
                },
            ],
        },
    )

    @model_validator(mode="after")
    def validate_traceability_context(self) -> "AgentArtifactContext":
        """Require a real evidence anchor and coherent rule version metadata."""

        has_anchor = bool(self.evidence_ids or self.canonical_event_ids or self.ingestion_run_id or self.source_hashes)
        if not has_anchor:
            raise ValueError(
                "agent artifact context must include at least one traceability anchor: "
                "evidence_ids, canonical_event_ids, ingestion_run_id, or source_hashes"
            )

        if (self.rule_id is None) != (self.rule_version is None):
            raise ValueError("rule_id and rule_version must be provided together")

        return self


class FieldMappingSuggestionPayload(StrictArtifactModel):
    """Suggested mapping from a supplier/source field to a canonical FSMA field."""

    source_field: str = Field(..., min_length=1)
    source_value: Any
    target_canonical_field: str = Field(..., min_length=1)
    normalized_value: Any
    rationale: str = Field(..., min_length=1)


class IdentityMatchSuggestionPayload(StrictArtifactModel):
    """Suggested identity match that must be reviewed or applied by deterministic code."""

    candidate_entity_ids: list[UUID] = Field(..., min_length=1)
    match_type: Literal["exact", "likely", "ambiguous", "unresolved"]
    matching_fields: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str = Field(..., min_length=1)


class ValidationExplanationPayload(StrictArtifactModel):
    """Agent-readable explanation of a deterministic rule evaluation."""

    rule_result: Literal["pass", "fail", "warn", "skip", "not_ftl_scoped", "error"]
    inspected_fields: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str = Field(..., min_length=1)
    remediation_suggestion: Optional[str] = None


class ReviewRoutingSuggestionPayload(StrictArtifactModel):
    """Suggested routing for human review queues."""

    review_queue_name: str = Field(..., min_length=1)
    priority: int = Field(..., ge=0, le=100)
    review_reason: str = Field(..., min_length=1)


class ExportReadinessSummaryPayload(StrictArtifactModel):
    """Advisory export-readiness summary derived from existing evidence and rules."""

    exportable: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    referenced_rule_versions: dict[str, int] = Field(default_factory=dict)


AgentArtifactPayload = Union[
    FieldMappingSuggestionPayload,
    IdentityMatchSuggestionPayload,
    ValidationExplanationPayload,
    ReviewRoutingSuggestionPayload,
    ExportReadinessSummaryPayload,
]

_PAYLOAD_TYPE_BY_ARTIFACT_TYPE = {
    "field_mapping_suggestion": FieldMappingSuggestionPayload,
    "identity_match_suggestion": IdentityMatchSuggestionPayload,
    "validation_explanation": ValidationExplanationPayload,
    "review_routing_suggestion": ReviewRoutingSuggestionPayload,
    "export_readiness_summary": ExportReadinessSummaryPayload,
}


def _agent_artifact_schema_extra(schema: dict[str, Any]) -> None:
    """Add cross-field contract rules that Pydantic validators also enforce."""

    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://schemas.regengine.co/events/agent.artifact.schema.json"
    schema.setdefault("allOf", [])
    schema["allOf"].extend(
        [
            {
                "if": {
                    "required": ["confidence"],
                    "properties": {"confidence": {"exclusiveMaximum": HUMAN_REVIEW_CONFIDENCE_THRESHOLD}},
                },
                "then": {
                    "required": ["requires_human_review"],
                    "properties": {"requires_human_review": {"const": True}},
                },
            },
            {
                "if": {
                    "required": ["artifact_type"],
                    "properties": {"artifact_type": {"const": "field_mapping_suggestion"}},
                },
                "then": {
                    "properties": {
                        "payload": {
                            "required": [
                                "source_field",
                                "source_value",
                                "target_canonical_field",
                                "normalized_value",
                                "rationale",
                            ]
                        }
                    }
                },
            },
            {
                "if": {
                    "required": ["artifact_type"],
                    "properties": {"artifact_type": {"const": "identity_match_suggestion"}},
                },
                "then": {"properties": {"payload": {"required": ["candidate_entity_ids", "match_type", "rationale"]}}},
            },
            {
                "if": {
                    "required": ["artifact_type"],
                    "properties": {"artifact_type": {"const": "validation_explanation"}},
                },
                "then": {"properties": {"payload": {"required": ["rule_result", "explanation"]}}},
            },
            {
                "if": {
                    "required": ["artifact_type"],
                    "properties": {"artifact_type": {"const": "review_routing_suggestion"}},
                },
                "then": {"properties": {"payload": {"required": ["review_queue_name", "priority", "review_reason"]}}},
            },
            {
                "if": {
                    "required": ["artifact_type"],
                    "properties": {"artifact_type": {"const": "export_readiness_summary"}},
                },
                "then": {"properties": {"payload": {"required": ["exportable"]}}},
            },
        ]
    )


class AgentArtifact(StrictArtifactModel):
    """Envelope for advisory agent output touching the FSMA evidence system."""

    artifact_id: UUID
    artifact_version: Literal["agent-artifact.v1"]
    artifact_type: ArtifactType
    tenant_id: UUID
    created_at: datetime
    agent_name: str = Field(..., min_length=1)
    agent_version: str = Field(..., min_length=1)
    model_name: Optional[str]
    suggestion: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    requires_human_review: bool
    context: AgentArtifactContext
    payload: AgentArtifactPayload

    model_config = ConfigDict(extra="forbid", json_schema_extra=_agent_artifact_schema_extra)

    @model_validator(mode="after")
    def validate_artifact_contract(self) -> "AgentArtifact":
        """Enforce advisory gating and payload/envelope consistency."""

        if self.confidence < HUMAN_REVIEW_CONFIDENCE_THRESHOLD and not self.requires_human_review:
            raise ValueError(
                "agent artifacts below the human-review confidence threshold "
                f"({HUMAN_REVIEW_CONFIDENCE_THRESHOLD}) must require human review"
            )

        expected_payload_type = _PAYLOAD_TYPE_BY_ARTIFACT_TYPE[self.artifact_type]
        if not isinstance(self.payload, expected_payload_type):
            raise ValueError(
                f"payload for artifact_type={self.artifact_type!r} must be {expected_payload_type.__name__}"
            )

        return self
