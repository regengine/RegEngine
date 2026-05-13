"""Tests for the advisory agent artifact contract."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, ValidationError as JsonSchemaValidationError
from pydantic import ValidationError

from shared.agent_artifacts import (
    AgentArtifact,
    AgentArtifactContext,
    ExportReadinessSummaryPayload,
    FieldMappingSuggestionPayload,
    IdentityMatchSuggestionPayload,
    ReviewRoutingSuggestionPayload,
    ValidationExplanationPayload,
)


SCHEMA_PATH = Path("data-schemas/events/agent.artifact.schema.json")
SHA256 = "a" * 64


def _context(**overrides) -> AgentArtifactContext:
    defaults = {
        "source_hashes": [SHA256],
        "rule_id": "fsma-receiving-tlc-source",
        "rule_version": 1,
        "citation_reference": "21 CFR 1.1345(b)(3)",
        "request_id": "req-test-001",
    }
    defaults.update(overrides)
    return AgentArtifactContext(**defaults)


def _artifact(artifact_type: str, payload, **overrides) -> AgentArtifact:
    defaults = {
        "artifact_id": uuid4(),
        "artifact_version": "agent-artifact.v1",
        "artifact_type": artifact_type,
        "tenant_id": uuid4(),
        "created_at": datetime(2026, 5, 13, 12, 0, tzinfo=timezone.utc),
        "agent_name": "fsma-contract-agent",
        "agent_version": "1.0.0",
        "model_name": "gpt-5",
        "suggestion": "Review the suggested FSMA evidence interpretation.",
        "confidence": 0.92,
        "requires_human_review": False,
        "context": _context(),
        "payload": payload,
    }
    defaults.update(overrides)
    return AgentArtifact(**defaults)


@pytest.mark.parametrize(
    ("artifact_type", "payload"),
    [
        (
            "field_mapping_suggestion",
            FieldMappingSuggestionPayload(
                source_field="Supplier TLC",
                source_value="LOT-123",
                target_canonical_field="traceability_lot_code",
                normalized_value="LOT-123",
                rationale="The supplier column carries the traceability lot code.",
            ),
        ),
        (
            "identity_match_suggestion",
            IdentityMatchSuggestionPayload(
                candidate_entity_ids=[uuid4(), uuid4()],
                match_type="likely",
                matching_fields=[{"field": "gln", "similarity": 0.97}],
                rationale="Both facility records share the same GLN.",
            ),
        ),
        (
            "validation_explanation",
            ValidationExplanationPayload(
                rule_result="fail",
                inspected_fields=[
                    {
                        "field": "kdes.tlc_source_reference",
                        "value": None,
                        "expected": "not_empty",
                    }
                ],
                explanation="The receiving event is missing a TLC source reference.",
                remediation_suggestion="Request the TLC source reference from the immediate supplier.",
            ),
        ),
        (
            "review_routing_suggestion",
            ReviewRoutingSuggestionPayload(
                review_queue_name="fsma_identity_review",
                priority=75,
                review_reason="The identity match is high value but not deterministic.",
            ),
        ),
        (
            "export_readiness_summary",
            ExportReadinessSummaryPayload(
                exportable=False,
                blockers=["Missing TLC source reference"],
                warnings=["One identity match remains pending"],
                referenced_rule_versions={"fsma-receiving-tlc-source": 1},
            ),
        ),
    ],
)
def test_valid_artifact_passes_for_each_payload_type(artifact_type, payload):
    artifact = _artifact(artifact_type, payload)

    assert artifact.artifact_type == artifact_type
    assert artifact.payload == payload
    assert artifact.context.source_hashes == [SHA256]


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_invalid_confidence_bounds_fail(confidence):
    payload = ExportReadinessSummaryPayload(exportable=True)

    with pytest.raises(ValidationError):
        _artifact("export_readiness_summary", payload, confidence=confidence)


def test_missing_traceability_anchors_fail():
    with pytest.raises(ValidationError, match="traceability anchor"):
        AgentArtifactContext(
            evidence_ids=[],
            canonical_event_ids=[],
            ingestion_run_id=None,
            source_hashes=[],
        )


def test_source_hashes_must_be_sha256_hex_strings():
    with pytest.raises(ValidationError):
        _context(source_hashes=["not-a-sha"])


@pytest.mark.parametrize(
    "context_kwargs",
    [
        {"rule_id": "fsma-rule", "rule_version": None},
        {"rule_id": None, "rule_version": 1},
    ],
)
def test_rule_id_and_rule_version_must_be_provided_together(context_kwargs):
    with pytest.raises(ValidationError, match="provided together"):
        _context(**context_kwargs)


def test_low_confidence_requires_human_review():
    payload = ExportReadinessSummaryPayload(exportable=False)

    with pytest.raises(ValidationError, match="must require human review"):
        _artifact(
            "export_readiness_summary",
            payload,
            confidence=0.84,
            requires_human_review=False,
        )

    artifact = _artifact(
        "export_readiness_summary",
        payload,
        confidence=0.84,
        requires_human_review=True,
    )
    assert artifact.requires_human_review is True


def test_unknown_fields_are_rejected_on_envelope_context_and_payload():
    payload = ExportReadinessSummaryPayload(exportable=True)

    with pytest.raises(ValidationError):
        _artifact("export_readiness_summary", payload, unexpected="field")

    with pytest.raises(ValidationError):
        AgentArtifactContext(source_hashes=[SHA256], unexpected="field")

    with pytest.raises(ValidationError):
        ExportReadinessSummaryPayload(exportable=True, unexpected="field")


def test_mismatched_artifact_type_and_payload_fail():
    payload = ExportReadinessSummaryPayload(exportable=True)

    with pytest.raises(ValidationError, match="payload for artifact_type"):
        _artifact("field_mapping_suggestion", payload)


def _checked_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_checked_schema())


def _json_artifact() -> dict:
    artifact = _artifact(
        "field_mapping_suggestion",
        FieldMappingSuggestionPayload(
            source_field="Supplier TLC",
            source_value="LOT-123",
            target_canonical_field="traceability_lot_code",
            normalized_value="LOT-123",
            rationale="The supplier column carries the traceability lot code.",
        ),
    )
    return artifact.model_dump(mode="json")


def test_checked_json_schema_validates_good_artifact_examples():
    validator = _validator()

    for artifact_type, payload in [
        (
            "field_mapping_suggestion",
            FieldMappingSuggestionPayload(
                source_field="Supplier TLC",
                source_value="LOT-123",
                target_canonical_field="traceability_lot_code",
                normalized_value="LOT-123",
                rationale="The supplier column carries the traceability lot code.",
            ),
        ),
        (
            "identity_match_suggestion",
            IdentityMatchSuggestionPayload(
                candidate_entity_ids=[uuid4(), uuid4()],
                match_type="likely",
                matching_fields=[{"field": "gln", "similarity": 0.97}],
                rationale="Both facility records share the same GLN.",
            ),
        ),
        (
            "validation_explanation",
            ValidationExplanationPayload(
                rule_result="fail",
                inspected_fields=[{"field": "kdes.tlc_source_reference", "value": None}],
                explanation="The receiving event is missing a TLC source reference.",
                remediation_suggestion="Request the TLC source reference.",
            ),
        ),
        (
            "review_routing_suggestion",
            ReviewRoutingSuggestionPayload(
                review_queue_name="fsma_identity_review",
                priority=75,
                review_reason="The identity match is not deterministic.",
            ),
        ),
        (
            "export_readiness_summary",
            ExportReadinessSummaryPayload(
                exportable=False,
                blockers=["Missing TLC source reference"],
                warnings=[],
                referenced_rule_versions={"fsma-receiving-tlc-source": 1},
            ),
        ),
    ]:
        validator.validate(_artifact(artifact_type, payload).model_dump(mode="json"))


def test_checked_json_schema_rejects_missing_anchors_bad_confidence_and_extra_fields():
    validator = _validator()
    artifact = _json_artifact()

    missing_anchor = deepcopy(artifact)
    missing_anchor["context"]["evidence_ids"] = []
    missing_anchor["context"]["canonical_event_ids"] = []
    missing_anchor["context"]["ingestion_run_id"] = None
    missing_anchor["context"]["source_hashes"] = []
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(missing_anchor)

    bad_confidence = deepcopy(artifact)
    bad_confidence["confidence"] = 1.2
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(bad_confidence)

    extra_field = deepcopy(artifact)
    extra_field["unexpected"] = "contract drift"
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(extra_field)


def test_checked_json_schema_rejects_mismatched_artifact_type_and_payload():
    validator = _validator()
    artifact = _json_artifact()
    artifact["artifact_type"] = "export_readiness_summary"

    with pytest.raises(JsonSchemaValidationError):
        validator.validate(artifact)


def _normalize_schema(value):
    if isinstance(value, dict):
        return {key: _normalize_schema(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize_schema(item) for item in value]
    return value


def test_checked_json_schema_matches_generated_pydantic_schema():
    generated = AgentArtifact.model_json_schema(ref_template="#/$defs/{model}")

    assert _normalize_schema(_checked_schema()) == _normalize_schema(generated)
