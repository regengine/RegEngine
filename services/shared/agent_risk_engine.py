"""Deterministic V1 risk scoring for advisory agent artifacts.

This module is intentionally pure: no database reads, no clocks, no network
calls. Operator views and API endpoints can reuse it safely because every
score is a direct function of the supplied artifact and ledger flags.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field
from shared.agent_artifacts import (
    HUMAN_REVIEW_CONFIDENCE_THRESHOLD,
    AgentArtifact,
    ExportReadinessSummaryPayload,
)

ArtifactGapCode = Literal[
    "low_confidence",
    "human_review_required",
    "missing_evidence_anchor",
    "missing_rule_reference",
    "export_blocker",
    "ledger_unlinked",
    "chain_unverified",
]


class StrictRiskModel(BaseModel):
    """Base model for risk-engine outputs."""

    model_config = ConfigDict(extra="forbid")


class RiskScoreBreakdown(StrictRiskModel):
    """Auditable V1 risk-score components."""

    score: float = Field(..., ge=0.0, le=100.0)
    uncapped_score: float = Field(..., ge=0.0)
    confidence_risk: float = Field(..., ge=0.0)
    review_risk: float = Field(..., ge=0.0)
    artifact_type_risk: float = Field(..., ge=0.0)
    evidence_gap_risk: float = Field(..., ge=0.0)
    rule_gap_risk: float = Field(..., ge=0.0)


class ComplianceGap(StrictRiskModel):
    """One deterministic reason an artifact needs operator attention."""

    code: ArtifactGapCode
    message: str


class AgentRiskEvaluation(StrictRiskModel):
    """Combined risk score and compliance gaps for an operator row."""

    risk_score: RiskScoreBreakdown
    compliance_gaps: list[ComplianceGap]
    compliance_gap_count: int


def calculate_risk_score(artifact_data: AgentArtifact | Mapping[str, Any]) -> RiskScoreBreakdown:
    """Calculate the V1 risk score.

    Formula:
        min(100, confidence_risk + review_risk + artifact_type_risk
             + evidence_gap_risk + rule_gap_risk)
    """

    artifact = _coerce_artifact(artifact_data)
    confidence_risk = (1.0 - artifact.confidence) * 40.0
    review_risk = 25.0 if artifact.requires_human_review else 0.0
    artifact_type_risk = _artifact_type_risk(artifact)
    evidence_gap_risk = 15.0 if _missing_evidence_anchor(artifact) else 0.0
    rule_gap_risk = 10.0 if _missing_rule_reference(artifact) else 0.0
    uncapped = confidence_risk + review_risk + artifact_type_risk + evidence_gap_risk + rule_gap_risk
    return RiskScoreBreakdown(
        score=_round_score(min(100.0, uncapped)),
        uncapped_score=_round_score(uncapped),
        confidence_risk=_round_score(confidence_risk),
        review_risk=review_risk,
        artifact_type_risk=artifact_type_risk,
        evidence_gap_risk=evidence_gap_risk,
        rule_gap_risk=rule_gap_risk,
    )


def calculate_compliance_gaps(
    artifact_data: AgentArtifact | Mapping[str, Any],
    *,
    ledger_receipt_found: Optional[bool] = None,
    chain_valid: Optional[bool] = None,
) -> list[ComplianceGap]:
    """Return all V1 compliance gaps determinable from the supplied data."""

    artifact = _coerce_artifact(artifact_data)
    gaps: list[ComplianceGap] = []

    if artifact.confidence < HUMAN_REVIEW_CONFIDENCE_THRESHOLD:
        gaps.append(
            ComplianceGap(
                code="low_confidence",
                message=(
                    f"Artifact confidence is below the human-review threshold ({HUMAN_REVIEW_CONFIDENCE_THRESHOLD})."
                ),
            )
        )
    if artifact.requires_human_review:
        gaps.append(
            ComplianceGap(
                code="human_review_required",
                message="Artifact explicitly requires human review.",
            )
        )
    if _missing_evidence_anchor(artifact):
        gaps.append(
            ComplianceGap(
                code="missing_evidence_anchor",
                message="Artifact has no evidence_ids or canonical_event_ids.",
            )
        )
    if _missing_rule_reference(artifact):
        gaps.append(
            ComplianceGap(
                code="missing_rule_reference",
                message="Artifact has no rule_id/rule_version reference.",
            )
        )
    if _has_export_blocker(artifact):
        gaps.append(
            ComplianceGap(
                code="export_blocker",
                message="Export readiness summary marks the run as not exportable.",
            )
        )
    if ledger_receipt_found is False:
        gaps.append(
            ComplianceGap(
                code="ledger_unlinked",
                message="No advisory ledger receipt is linked to this artifact.",
            )
        )
    if chain_valid is False:
        gaps.append(
            ComplianceGap(
                code="chain_unverified",
                message="Linked run ledger chain verification failed.",
            )
        )

    return gaps


def evaluate_agent_risk(
    artifact_data: AgentArtifact | Mapping[str, Any],
    *,
    ledger_receipt_found: Optional[bool] = None,
    chain_valid: Optional[bool] = None,
) -> AgentRiskEvaluation:
    """Return score, gap list, and gap count for an operator view row."""

    gaps = calculate_compliance_gaps(
        artifact_data,
        ledger_receipt_found=ledger_receipt_found,
        chain_valid=chain_valid,
    )
    return AgentRiskEvaluation(
        risk_score=calculate_risk_score(artifact_data),
        compliance_gaps=gaps,
        compliance_gap_count=len(gaps),
    )


def _coerce_artifact(artifact_data: AgentArtifact | Mapping[str, Any]) -> AgentArtifact:
    if isinstance(artifact_data, AgentArtifact):
        return artifact_data
    if hasattr(artifact_data, "model_dump"):
        return AgentArtifact.model_validate(artifact_data.model_dump(mode="json"))
    return AgentArtifact.model_validate(artifact_data)


def _artifact_type_risk(artifact: AgentArtifact) -> float:
    if artifact.artifact_type == "identity_match_suggestion":
        return 20.0
    if artifact.artifact_type == "field_mapping_suggestion":
        return 15.0
    if artifact.artifact_type == "validation_explanation":
        return 15.0
    if artifact.artifact_type == "review_routing_suggestion":
        return 10.0
    if artifact.artifact_type == "export_readiness_summary":
        return 25.0 if _has_export_blocker(artifact) else 5.0
    raise ValueError(f"unsupported artifact_type: {artifact.artifact_type!r}")


def _missing_evidence_anchor(artifact: AgentArtifact) -> bool:
    return not (artifact.context.evidence_ids or artifact.context.canonical_event_ids)


def _missing_rule_reference(artifact: AgentArtifact) -> bool:
    return artifact.context.rule_id is None or artifact.context.rule_version is None


def _has_export_blocker(artifact: AgentArtifact) -> bool:
    return (
        artifact.artifact_type == "export_readiness_summary"
        and isinstance(artifact.payload, ExportReadinessSummaryPayload)
        and not artifact.payload.exportable
    )


def _round_score(value: float) -> float:
    return round(value, 4)


__all__ = [
    "AgentRiskEvaluation",
    "ComplianceGap",
    "RiskScoreBreakdown",
    "calculate_compliance_gaps",
    "calculate_risk_score",
    "evaluate_agent_risk",
]
