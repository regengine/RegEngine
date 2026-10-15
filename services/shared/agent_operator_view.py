"""Read-model service for the first agent operator view.

This module assembles persisted advisory artifacts, operator review state,
ingestion run context, advisory ledger receipts, and deterministic risk
evaluation into the API-facing ``AgentReviewItem`` contract.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field
from shared.agent_risk_engine import ComplianceGap, RiskScoreBreakdown, evaluate_agent_risk
from shared.run_ledger import IngestionRunTimeline, fetch_ingestion_run_timeline, verify_receipt_chain
from sqlalchemy import text

ReviewStatus = Literal["pending", "accepted", "rejected", "needs_more_evidence"]
ReviewDecisionStatus = Literal["accepted", "rejected", "needs_more_evidence"]
ArtifactType = Literal[
    "field_mapping_suggestion",
    "identity_match_suggestion",
    "validation_explanation",
    "review_routing_suggestion",
    "export_readiness_summary",
]


class StrictOperatorViewModel(BaseModel):
    """Base model for operator-view contracts."""

    model_config = ConfigDict(extra="forbid")


class AgentReviewItem(StrictOperatorViewModel):
    """Single row for the operator Agent Review queue."""

    artifact_id: str
    tenant_id: str
    artifact_type: ArtifactType
    created_at: datetime
    agent_name: str
    suggestion: str
    confidence: float
    requires_human_review: bool

    review_id: Optional[str] = None
    review_status: ReviewStatus
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    risk_score: float
    risk_breakdown: RiskScoreBreakdown
    compliance_gap_count: int
    compliance_gaps: list[ComplianceGap]

    ingestion_run_id: Optional[str] = None
    ingestion_run_status: Optional[str] = None
    source_system: Optional[str] = None
    source_file_name: Optional[str] = None

    advisory_receipt_id: Optional[str] = None
    advisory_receipt_state: Optional[str] = None
    receipt_hash: Optional[str] = None
    chain_valid: Optional[bool] = None

    evidence_ids: list[str] = Field(default_factory=list)
    canonical_event_ids: list[str] = Field(default_factory=list)
    source_hashes: list[str] = Field(default_factory=list)
    rule_id: Optional[str] = None
    rule_version: Optional[int] = None


class AgentReviewListResponse(StrictOperatorViewModel):
    """Paginated response for operator review items."""

    items: list[AgentReviewItem]
    total: int
    limit: int
    offset: int


class AgentReviewDecisionRequest(StrictOperatorViewModel):
    """Operator decision payload for one advisory artifact."""

    status: ReviewDecisionStatus
    notes: Optional[str] = Field(default=None, max_length=4000)
    review_reason: Optional[str] = Field(default=None, max_length=500)
    operator_notes: Optional[str] = Field(default=None, max_length=4000)
    decision_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentReviewDecisionResponse(StrictOperatorViewModel):
    """Persisted operator decision for one advisory artifact."""

    review_id: str
    artifact_id: str
    tenant_id: str
    status: ReviewDecisionStatus
    reviewed_by: str
    reviewed_at: datetime
    ingestion_run_id: Optional[str] = None
    advisory_receipt_id: Optional[str] = None


class AgentArtifactTimelineResponse(StrictOperatorViewModel):
    """Artifact detail plus the linked ingestion-run receipt timeline."""

    item: AgentReviewItem
    timeline: Optional[IngestionRunTimeline] = None
    chain_valid: Optional[bool] = None


# Every tenant table behind the operator view, narrowed to the caller's
# tenant before it is joined. The outer queries read these CTEs, so no
# joined row (review, run, receipt) can come from another tenant even where
# the join keys alone would allow it.
_TENANT_SCOPED_REVIEW_CTES = """
    WITH aa AS (
        SELECT aa.* FROM fsma.agent_artifacts aa WHERE aa.tenant_id = :tenant_id
    ),
    ar AS (
        SELECT r.* FROM fsma.agent_artifact_reviews r WHERE r.tenant_id = :tenant_id
    ),
    ir AS (
        SELECT i.* FROM fsma.ingestion_runs i WHERE i.tenant_id = :tenant_id
    ),
    receipt_scope AS (
        SELECT x.* FROM fsma.ingestion_run_receipts x WHERE x.tenant_id = :tenant_id
    )
"""


def fetch_agent_review_items(
    db_session: Any,
    *,
    tenant_id: str,
    artifact_id: Optional[str] = None,
    ingestion_run_id: Optional[str] = None,
    review_status: Optional[ReviewStatus] = None,
    artifact_type: Optional[ArtifactType] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> AgentReviewListResponse:
    """Fetch operator review rows and enrich them with deterministic risk."""

    if limit < 1 or limit > 200:
        raise ValueError("limit must be between 1 and 200")
    if offset < 0:
        raise ValueError("offset must be greater than or equal to 0")

    where_sql, params = _build_filters(
        tenant_id=tenant_id,
        artifact_id=artifact_id,
        ingestion_run_id=ingestion_run_id,
        review_status=review_status,
        artifact_type=artifact_type,
        created_after=created_after,
        created_before=created_before,
    )
    total = int(
        db_session.execute(
            text(
                f"""{_TENANT_SCOPED_REVIEW_CTES}
                SELECT COUNT(*)
                FROM aa
                LEFT JOIN ar
                  ON ar.tenant_id = aa.tenant_id
                 AND ar.artifact_id = aa.artifact_id
                WHERE {where_sql}
                """
            ),
            params,
        ).scalar_one()
        or 0
    )

    rows = (
        db_session.execute(
            text(
                f"""{_TENANT_SCOPED_REVIEW_CTES}
                SELECT
                    aa.artifact_id,
                    aa.tenant_id,
                    aa.artifact_type,
                    aa.created_at,
                    aa.agent_name,
                    aa.suggestion,
                    aa.confidence,
                    aa.requires_human_review,
                    ar.review_id,
                    COALESCE(ar.status, 'pending') AS review_status,
                    ar.reviewed_by,
                    ar.reviewed_at,
                    aa.ingestion_run_id,
                    ir.status AS ingestion_run_status,
                    ir.source_system,
                    ir.source_file_name,
                    advisory.receipt_id AS advisory_receipt_id,
                    advisory.state AS advisory_receipt_state,
                    advisory.receipt_hash,
                    aa.evidence_ids,
                    aa.canonical_event_ids,
                    aa.source_hashes,
                    aa.rule_id,
                    aa.rule_version,
                    aa.artifact
                FROM aa
                LEFT JOIN ar
                  ON ar.tenant_id = aa.tenant_id
                 AND ar.artifact_id = aa.artifact_id
                LEFT JOIN ir
                  ON ir.tenant_id = aa.tenant_id
                 AND ir.id = aa.ingestion_run_id
                LEFT JOIN LATERAL (
                    SELECT receipt_id, state, receipt_hash
                    FROM receipt_scope receipt
                    WHERE receipt.tenant_id = aa.tenant_id
                      AND receipt.ingestion_run_id = aa.ingestion_run_id
                      AND receipt.metadata->'agent_artifact'->>'artifact_id' = aa.artifact_id::text
                    ORDER BY receipt.sequence_num DESC
                    LIMIT 1
                ) advisory ON TRUE
                WHERE {where_sql}
                ORDER BY aa.created_at DESC, aa.artifact_id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {**params, "limit": limit, "offset": offset},
        )
        .mappings()
        .all()
    )

    chain_valid_by_run = _fetch_chain_valid_by_run(
        db_session,
        tenant_id=tenant_id,
        run_ids=[
            str(row["ingestion_run_id"])
            for row in rows
            if row.get("ingestion_run_id") is not None and row.get("advisory_receipt_id") is not None
        ],
    )

    return AgentReviewListResponse(
        items=[_item_from_row(row, chain_valid_by_run=chain_valid_by_run) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def upsert_agent_artifact_review(
    db_session: Any,
    *,
    tenant_id: str,
    artifact_id: str,
    status: ReviewDecisionStatus,
    reviewed_by: str,
    notes: Optional[str] = None,
    review_reason: Optional[str] = None,
    operator_notes: Optional[str] = None,
    decision_metadata: Optional[Mapping[str, Any]] = None,
) -> AgentReviewDecisionResponse:
    """Record the operator's advisory artifact decision.

    The artifact remains append-only. This writes only the mutable operator
    outcome row, linked back to the artifact, run, and advisory receipt.
    """

    if status not in ("accepted", "rejected", "needs_more_evidence"):
        raise ValueError("status must be one of accepted, rejected, needs_more_evidence")
    if not str(reviewed_by).strip():
        raise ValueError("reviewed_by is required")

    anchor = _fetch_artifact_review_anchor(
        db_session,
        tenant_id=tenant_id,
        artifact_id=artifact_id,
    )
    if anchor is None:
        raise LookupError(f"agent artifact {artifact_id} not found for tenant {tenant_id}")

    resolved_operator_notes = operator_notes if operator_notes is not None else notes
    row = (
        db_session.execute(
            text(
                """
                INSERT INTO fsma.agent_artifact_reviews (
                    tenant_id, artifact_id, ingestion_run_id, advisory_receipt_id,
                    status, reviewed_by, reviewed_at, review_reason, operator_notes,
                    decision_metadata
                )
                VALUES (
                    :tenant_id, :artifact_id, :ingestion_run_id, :advisory_receipt_id,
                    :status, :reviewed_by, now(), :review_reason, :notes,
                    CAST(:decision_metadata AS jsonb)
                )
                ON CONFLICT (tenant_id, artifact_id) DO UPDATE SET
                    ingestion_run_id = EXCLUDED.ingestion_run_id,
                    advisory_receipt_id = EXCLUDED.advisory_receipt_id,
                    status = EXCLUDED.status,
                    reviewed_by = EXCLUDED.reviewed_by,
                    reviewed_at = EXCLUDED.reviewed_at,
                    review_reason = EXCLUDED.review_reason,
                    operator_notes = EXCLUDED.operator_notes,
                    decision_metadata = EXCLUDED.decision_metadata
                RETURNING
                    review_id::text AS review_id,
                    artifact_id::text AS artifact_id,
                    tenant_id::text AS tenant_id,
                    status,
                    reviewed_by::text AS reviewed_by,
                    reviewed_at,
                    ingestion_run_id::text AS ingestion_run_id,
                    advisory_receipt_id::text AS advisory_receipt_id
                """
            ),
            {
                "tenant_id": tenant_id,
                "artifact_id": artifact_id,
                "ingestion_run_id": _string_or_none(anchor.get("ingestion_run_id")),
                "advisory_receipt_id": _string_or_none(anchor.get("advisory_receipt_id")),
                "status": status,
                "reviewed_by": str(reviewed_by),
                "review_reason": review_reason,
                "notes": resolved_operator_notes,
                "decision_metadata": json.dumps(dict(decision_metadata or {}), sort_keys=True),
            },
        )
        .mappings()
        .one_or_none()
    )

    if row is None:
        raise RuntimeError("agent artifact review upsert did not return a row")

    return AgentReviewDecisionResponse(
        review_id=str(row["review_id"]),
        artifact_id=str(row["artifact_id"]),
        tenant_id=str(row["tenant_id"]),
        status=row["status"],
        reviewed_by=str(row["reviewed_by"]),
        reviewed_at=row["reviewed_at"],
        ingestion_run_id=_string_or_none(row.get("ingestion_run_id")),
        advisory_receipt_id=_string_or_none(row.get("advisory_receipt_id")),
    )


def fetch_agent_artifact_timeline(
    db_session: Any,
    *,
    tenant_id: str,
    artifact_id: str,
) -> AgentArtifactTimelineResponse:
    """Fetch one artifact review item and the linked run ledger timeline."""

    row = _fetch_agent_review_item_row(
        db_session,
        tenant_id=tenant_id,
        artifact_id=artifact_id,
    )
    if row is None:
        raise LookupError(f"agent artifact {artifact_id} not found for tenant {tenant_id}")

    ingestion_run_id = _string_or_none(row.get("ingestion_run_id"))
    timeline = fetch_ingestion_run_timeline(db_session, tenant_id, ingestion_run_id) if ingestion_run_id else None
    if ingestion_run_id and timeline is None:
        raise LookupError(f"ingestion run {ingestion_run_id} not found for artifact {artifact_id}")

    chain_valid = timeline.verification.valid if timeline is not None else None
    item = _item_from_row(
        row,
        chain_valid_by_run=(
            {ingestion_run_id: chain_valid} if ingestion_run_id is not None and chain_valid is not None else {}
        ),
    )
    return AgentArtifactTimelineResponse(
        item=item,
        timeline=timeline,
        chain_valid=chain_valid,
    )


def _build_filters(
    *,
    tenant_id: str,
    artifact_id: Optional[str],
    ingestion_run_id: Optional[str],
    review_status: Optional[ReviewStatus],
    artifact_type: Optional[ArtifactType],
    created_after: Optional[datetime],
    created_before: Optional[datetime],
) -> tuple[str, dict[str, Any]]:
    clauses = ["aa.tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": tenant_id}

    if artifact_id is not None:
        clauses.append("aa.artifact_id = :artifact_id")
        params["artifact_id"] = artifact_id
    if ingestion_run_id is not None:
        clauses.append("aa.ingestion_run_id = :ingestion_run_id")
        params["ingestion_run_id"] = ingestion_run_id
    if review_status is not None:
        clauses.append("COALESCE(ar.status, 'pending') = :review_status")
        params["review_status"] = review_status
    if artifact_type is not None:
        clauses.append("aa.artifact_type = :artifact_type")
        params["artifact_type"] = artifact_type
    if created_after is not None:
        clauses.append("aa.created_at >= :created_after")
        params["created_after"] = created_after
    if created_before is not None:
        clauses.append("aa.created_at <= :created_before")
        params["created_before"] = created_before

    return " AND ".join(clauses), params


def _fetch_agent_review_item_row(
    db_session: Any,
    *,
    tenant_id: str,
    artifact_id: str,
) -> Optional[Mapping[str, Any]]:
    return (
        db_session.execute(
            text(
                f"""{_TENANT_SCOPED_REVIEW_CTES}
                SELECT
                    aa.artifact_id,
                    aa.tenant_id,
                    aa.artifact_type,
                    aa.created_at,
                    aa.agent_name,
                    aa.suggestion,
                    aa.confidence,
                    aa.requires_human_review,
                    ar.review_id,
                    COALESCE(ar.status, 'pending') AS review_status,
                    ar.reviewed_by,
                    ar.reviewed_at,
                    aa.ingestion_run_id,
                    ir.status AS ingestion_run_status,
                    ir.source_system,
                    ir.source_file_name,
                    advisory.receipt_id AS advisory_receipt_id,
                    advisory.state AS advisory_receipt_state,
                    advisory.receipt_hash,
                    aa.evidence_ids,
                    aa.canonical_event_ids,
                    aa.source_hashes,
                    aa.rule_id,
                    aa.rule_version,
                    aa.artifact
                FROM aa
                LEFT JOIN ar
                  ON ar.tenant_id = aa.tenant_id
                 AND ar.artifact_id = aa.artifact_id
                LEFT JOIN ir
                  ON ir.tenant_id = aa.tenant_id
                 AND ir.id = aa.ingestion_run_id
                LEFT JOIN LATERAL (
                    SELECT receipt_id, state, receipt_hash
                    FROM receipt_scope receipt
                    WHERE receipt.tenant_id = aa.tenant_id
                      AND receipt.ingestion_run_id = aa.ingestion_run_id
                      AND receipt.metadata->'agent_artifact'->>'artifact_id' = aa.artifact_id::text
                    ORDER BY receipt.sequence_num DESC
                    LIMIT 1
                ) advisory ON TRUE
                WHERE aa.tenant_id = :tenant_id
                  AND aa.artifact_id = :artifact_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "artifact_id": artifact_id},
        )
        .mappings()
        .one_or_none()
    )


def _fetch_artifact_review_anchor(
    db_session: Any,
    *,
    tenant_id: str,
    artifact_id: str,
) -> Optional[Mapping[str, Any]]:
    rows = (
        db_session.execute(
            text(
                f"""{_TENANT_SCOPED_REVIEW_CTES}
                SELECT
                    aa.artifact_id::text AS artifact_id,
                    aa.tenant_id::text AS tenant_id,
                    aa.ingestion_run_id::text AS ingestion_run_id,
                    advisory.receipt_id::text AS advisory_receipt_id
                FROM aa
                LEFT JOIN LATERAL (
                    SELECT receipt_id
                    FROM receipt_scope receipt
                    WHERE receipt.tenant_id = aa.tenant_id
                      AND receipt.ingestion_run_id = aa.ingestion_run_id
                      AND receipt.metadata->'agent_artifact'->>'artifact_id' = aa.artifact_id::text
                    ORDER BY receipt.sequence_num DESC
                    LIMIT 1
                ) advisory ON TRUE
                WHERE aa.tenant_id = :tenant_id
                  AND aa.artifact_id = :artifact_id
                LIMIT 1
                """
            ),
            {"tenant_id": tenant_id, "artifact_id": artifact_id},
        )
        .mappings()
        .all()
    )
    return rows[0] if rows else None


def _fetch_chain_valid_by_run(
    db_session: Any,
    *,
    tenant_id: str,
    run_ids: list[str],
) -> dict[str, bool]:
    unique_run_ids = sorted(set(run_ids))
    if not unique_run_ids:
        return {}

    placeholders = ", ".join(f":run_id_{idx}" for idx in range(len(unique_run_ids)))
    params = {"tenant_id": tenant_id}
    params.update({f"run_id_{idx}": run_id for idx, run_id in enumerate(unique_run_ids)})
    rows = (
        db_session.execute(
            text(
                f"""
                SELECT
                    ingestion_run_id,
                    receipt_id,
                    sequence_num,
                    state,
                    occurred_at,
                    actor,
                    request_id,
                    canonical_event_id,
                    evidence_attachment_id,
                    rule_evaluation_id,
                    export_log_id,
                    metadata,
                    payload_hash,
                    previous_receipt_hash,
                    receipt_hash,
                    created_at
                FROM fsma.ingestion_run_receipts
                WHERE tenant_id = :tenant_id
                  AND ingestion_run_id::text IN ({placeholders})
                ORDER BY ingestion_run_id, sequence_num
                """
            ),
            params,
        )
        .mappings()
        .all()
    )

    grouped: dict[str, list[dict[str, Any]]] = {run_id: [] for run_id in unique_run_ids}
    for row in rows:
        run_id = str(row["ingestion_run_id"])
        grouped.setdefault(run_id, []).append(_receipt_for_verification(row))

    return {run_id: verify_receipt_chain(receipts).valid for run_id, receipts in grouped.items() if receipts}


def _item_from_row(
    row: Mapping[str, Any],
    *,
    chain_valid_by_run: dict[str, bool],
) -> AgentReviewItem:
    artifact = _coerce_json_object(row["artifact"])
    ingestion_run_id = _string_or_none(row.get("ingestion_run_id"))
    advisory_receipt_id = _string_or_none(row.get("advisory_receipt_id"))
    chain_valid = (
        chain_valid_by_run.get(ingestion_run_id)
        if ingestion_run_id is not None and advisory_receipt_id is not None
        else None
    )
    risk = evaluate_agent_risk(
        artifact,
        ledger_receipt_found=advisory_receipt_id is not None,
        chain_valid=chain_valid,
    )

    return AgentReviewItem(
        artifact_id=str(row["artifact_id"]),
        tenant_id=str(row["tenant_id"]),
        artifact_type=row["artifact_type"],
        created_at=row["created_at"],
        agent_name=row["agent_name"],
        suggestion=row["suggestion"],
        confidence=float(row["confidence"]),
        requires_human_review=bool(row["requires_human_review"]),
        review_id=_string_or_none(row.get("review_id")),
        review_status=row["review_status"],
        reviewed_by=_string_or_none(row.get("reviewed_by")),
        reviewed_at=row.get("reviewed_at"),
        risk_score=risk.risk_score.score,
        risk_breakdown=risk.risk_score,
        compliance_gap_count=risk.compliance_gap_count,
        compliance_gaps=risk.compliance_gaps,
        ingestion_run_id=ingestion_run_id,
        ingestion_run_status=row.get("ingestion_run_status"),
        source_system=row.get("source_system"),
        source_file_name=row.get("source_file_name"),
        advisory_receipt_id=advisory_receipt_id,
        advisory_receipt_state=row.get("advisory_receipt_state"),
        receipt_hash=row.get("receipt_hash"),
        chain_valid=chain_valid,
        evidence_ids=_string_list(row.get("evidence_ids")),
        canonical_event_ids=_string_list(row.get("canonical_event_ids")),
        source_hashes=_string_list(row.get("source_hashes")),
        rule_id=row.get("rule_id"),
        rule_version=row.get("rule_version"),
    )


def _receipt_for_verification(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "receipt_id": str(row["receipt_id"]),
        "sequence_num": row["sequence_num"],
        "state": row["state"],
        "occurred_at": row.get("occurred_at"),
        "actor": row.get("actor"),
        "request_id": row.get("request_id"),
        "canonical_event_id": _string_or_none(row.get("canonical_event_id")),
        "evidence_attachment_id": _string_or_none(row.get("evidence_attachment_id")),
        "rule_evaluation_id": _string_or_none(row.get("rule_evaluation_id")),
        "export_log_id": _string_or_none(row.get("export_log_id")),
        "metadata": _coerce_json_object(row.get("metadata")),
        "payload_hash": row["payload_hash"],
        "previous_receipt_hash": row.get("previous_receipt_hash"),
        "receipt_hash": row["receipt_hash"],
        "created_at": row.get("created_at"),
    }


def _coerce_json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return dict(value)


def _string_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(item) for item in value]


__all__ = [
    "AgentArtifactTimelineResponse",
    "AgentReviewDecisionRequest",
    "AgentReviewDecisionResponse",
    "AgentReviewItem",
    "AgentReviewListResponse",
    "ArtifactType",
    "ReviewDecisionStatus",
    "ReviewStatus",
    "fetch_agent_artifact_timeline",
    "fetch_agent_review_items",
    "upsert_agent_artifact_review",
]
