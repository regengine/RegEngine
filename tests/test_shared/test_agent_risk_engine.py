"""Tests for deterministic agent operator risk scoring."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import BaseModel

from shared.agent_artifacts import (
    AgentArtifact,
    AgentArtifactContext,
    ExportReadinessSummaryPayload,
    FieldMappingSuggestionPayload,
    IdentityMatchSuggestionPayload,
)
from shared.agent_risk_engine import (
    ComplianceGap,
    RiskScoreBreakdown,
    calculate_compliance_gaps,
    calculate_risk_score,
    evaluate_agent_risk,
)


SHA256 = "c" * 64


def _artifact(
    *,
    artifact_type: str = "field_mapping_suggestion",
    confidence: float = 0.9,
    requires_human_review: bool = False,
    context: AgentArtifactContext | None = None,
    payload=None,
) -> AgentArtifact:
    if payload is None:
        if artifact_type == "identity_match_suggestion":
            payload = IdentityMatchSuggestionPayload(
                candidate_entity_ids=[uuid4()],
                match_type="likely",
                matching_fields=[{"field": "gln", "similarity": 0.91}],
                rationale="The candidate shares the same GLN.",
            )
        elif artifact_type == "export_readiness_summary":
            payload = ExportReadinessSummaryPayload(exportable=True)
        else:
            payload = FieldMappingSuggestionPayload(
                source_field="Supplier TLC",
                source_value="LOT-123",
                target_canonical_field="traceability_lot_code",
                normalized_value="LOT-123",
                rationale="The supplier column carries the traceability lot code.",
            )

    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json")

    return AgentArtifact(
        artifact_id=uuid4(),
        artifact_version="agent-artifact.v1",
        artifact_type=artifact_type,
        tenant_id=uuid4(),
        created_at=datetime(2026, 5, 13, 15, 0, tzinfo=timezone.utc),
        agent_name="fsma-risk-agent",
        agent_version="1.0.0",
        model_name="gpt-5",
        suggestion="Review this advisory finding.",
        confidence=confidence,
        requires_human_review=requires_human_review,
        context=context
        or AgentArtifactContext(
            evidence_ids=[uuid4()],
            canonical_event_ids=[],
            ingestion_run_id=uuid4(),
            source_hashes=[SHA256],
            rule_id="fsma-receiving-tlc-source",
            rule_version=1,
        ),
        payload=payload,
    )


def test_calculate_risk_score_uses_exact_v1_weights_for_field_mapping():
    artifact = _artifact(confidence=0.5, requires_human_review=True)

    result = calculate_risk_score(artifact)

    assert isinstance(result, RiskScoreBreakdown)
    assert result.confidence_risk == 20.0
    assert result.review_risk == 25.0
    assert result.artifact_type_risk == 15.0
    assert result.evidence_gap_risk == 0.0
    assert result.rule_gap_risk == 0.0
    assert result.score == 60.0


def test_calculate_risk_score_caps_at_100():
    artifact = _artifact(
        artifact_type="export_readiness_summary",
        confidence=0.0,
        requires_human_review=True,
        context=AgentArtifactContext(source_hashes=[SHA256]),
        payload=ExportReadinessSummaryPayload(exportable=False),
    )

    result = calculate_risk_score(artifact)

    assert result.score == 100.0
    assert result.uncapped_score == 115.0


@pytest.mark.parametrize(
    ("artifact_type", "payload", "expected_artifact_type_risk"),
    [
        ("identity_match_suggestion", None, 20.0),
        ("field_mapping_suggestion", None, 15.0),
        ("review_routing_suggestion", None, 10.0),
        (
            "export_readiness_summary",
            ExportReadinessSummaryPayload(exportable=True),
            5.0,
        ),
        (
            "export_readiness_summary",
            ExportReadinessSummaryPayload(exportable=False),
            25.0,
        ),
    ],
)
def test_artifact_type_risk_weights_are_deterministic(
    artifact_type,
    payload,
    expected_artifact_type_risk,
):
    if artifact_type == "review_routing_suggestion":
        from shared.agent_artifacts import ReviewRoutingSuggestionPayload

        payload = ReviewRoutingSuggestionPayload(
            review_queue_name="fsma_review",
            priority=50,
            review_reason="Needs operator review.",
        )
    artifact = _artifact(artifact_type=artifact_type, payload=payload)

    assert calculate_risk_score(artifact).artifact_type_risk == expected_artifact_type_risk


def test_calculate_compliance_gaps_returns_all_determinable_gap_names():
    artifact = _artifact(
        artifact_type="export_readiness_summary",
        confidence=0.7,
        requires_human_review=True,
        context=AgentArtifactContext(source_hashes=[SHA256]),
        payload=ExportReadinessSummaryPayload(exportable=False),
    )

    gaps = calculate_compliance_gaps(
        artifact,
        ledger_receipt_found=False,
        chain_valid=False,
    )

    assert [gap.code for gap in gaps] == [
        "low_confidence",
        "human_review_required",
        "missing_evidence_anchor",
        "missing_rule_reference",
        "export_blocker",
        "ledger_unlinked",
        "chain_unverified",
    ]
    assert all(isinstance(gap, ComplianceGap) for gap in gaps)


def test_calculate_compliance_gaps_omits_unknown_ledger_state_when_not_supplied():
    artifact = _artifact()

    gaps = calculate_compliance_gaps(artifact)

    assert gaps == []


def test_evaluate_agent_risk_returns_score_gaps_and_count():
    artifact = _artifact(confidence=0.84, requires_human_review=True)

    result = evaluate_agent_risk(artifact, ledger_receipt_found=True, chain_valid=True)

    assert result.risk_score.score == pytest.approx(46.4)
    assert result.compliance_gap_count == 2
    assert [gap.code for gap in result.compliance_gaps] == [
        "low_confidence",
        "human_review_required",
    ]


def test_risk_engine_accepts_dict_artifact_data():
    artifact_dict = _artifact(confidence=1.0).model_dump(mode="json")

    result = calculate_risk_score(artifact_dict)

    assert result.confidence_risk == 0.0
    assert result.score == 15.0
