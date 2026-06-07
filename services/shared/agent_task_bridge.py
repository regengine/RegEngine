"""Operational bridge from advisory agent artifacts to durable queue tasks.

Agents propose; deterministic services decide. This module turns a validated
``AgentArtifact`` into a tenant-scoped task payload and, when the artifact is
anchored to an ingestion run, records an advisory receipt in the append-only
run ledger. It does not mutate canonical evidence records.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal, Mapping, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from shared.agent_artifacts import (
    AGENT_ARTIFACT_VERSION,
    AgentArtifact,
    ArtifactType,
    SHA256Hex,
)
from shared.task_queue import enqueue_task, register_task_handler
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text

logger = logging.getLogger("agent_task_bridge")

AGENT_ARTIFACT_TASK_VERSION = "agent-artifact-task.v1"
AGENT_ARTIFACT_TASK_TYPE = "agent_artifact_review"
AGENT_ARTIFACT_TASK_VISIBILITY_TIMEOUT_SECONDS = 120
AGENT_ARTIFACT_DEFAULT_PRIORITY = 50
AGENT_ARTIFACT_HUMAN_REVIEW_PRIORITY = 80


class StrictAgentTaskModel(BaseModel):
    """Base model for agent-task contracts; extra fields are drift."""

    model_config = ConfigDict(extra="forbid")


def _agent_task_schema_extra(schema: dict[str, Any]) -> None:
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://schemas.regengine.co/events/agent.task.schema.json"


class AgentArtifactTaskPayload(StrictAgentTaskModel):
    """Queue payload for processing an advisory agent artifact."""

    task_version: Literal["agent-artifact-task.v1"]
    task_type: Literal["agent_artifact_review"]
    artifact_id: UUID
    artifact_version: Literal["agent-artifact.v1"]
    artifact_type: ArtifactType
    tenant_id: UUID
    created_at: datetime
    requires_human_review: bool
    confidence: float = Field(..., ge=0.0, le=1.0)

    evidence_ids: list[UUID] = Field(default_factory=list)
    canonical_event_ids: list[UUID] = Field(default_factory=list)
    ingestion_run_id: Optional[UUID] = None
    source_hashes: list[SHA256Hex] = Field(default_factory=list)
    rule_id: Optional[str] = None
    rule_version: Optional[int] = None
    citation_reference: Optional[str] = None
    request_id: Optional[str] = None

    artifact: AgentArtifact

    model_config = ConfigDict(extra="forbid", json_schema_extra=_agent_task_schema_extra)

    @classmethod
    def model_json_schema(cls, *args: Any, **kwargs: Any) -> dict[str, Any]:
        schema = super().model_json_schema(*args, **kwargs)
        _strip_embedded_agent_artifact_schema_ids(schema)
        return schema

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        schema = handler(core_schema)
        _strip_embedded_agent_artifact_schema_ids(schema)
        return schema

    @model_validator(mode="after")
    def validate_payload_matches_embedded_artifact(self) -> "AgentArtifactTaskPayload":
        """Ensure flattened queue routing fields match the full artifact."""

        artifact = self.artifact
        mismatches: list[str] = []
        for field_name in (
            "artifact_id",
            "artifact_version",
            "artifact_type",
            "tenant_id",
            "created_at",
            "requires_human_review",
            "confidence",
        ):
            if getattr(self, field_name) != getattr(artifact, field_name):
                mismatches.append(field_name)

        context = artifact.context
        context_checks = {
            "evidence_ids": context.evidence_ids,
            "canonical_event_ids": context.canonical_event_ids,
            "ingestion_run_id": context.ingestion_run_id,
            "source_hashes": context.source_hashes,
            "rule_id": context.rule_id,
            "rule_version": context.rule_version,
            "citation_reference": context.citation_reference,
            "request_id": context.request_id,
        }
        for field_name, expected in context_checks.items():
            if getattr(self, field_name) != expected:
                mismatches.append(field_name)

        if mismatches:
            raise ValueError(
                "agent artifact task payload does not match embedded artifact: " + ", ".join(sorted(mismatches))
            )

        return self


class AgentLedgerBridgeResult(StrictAgentTaskModel):
    """Result from recording an advisory artifact receipt."""

    artifact_id: UUID
    tenant_id: UUID
    ledger_receipt_appended: bool
    ledger_state: Optional[Literal["needs_review", "rule_evaluated"]] = None
    receipt_id: Optional[str] = None
    receipt_hash: Optional[str] = None
    skip_reason: Optional[Literal["missing_ingestion_run_id"]] = None


def build_agent_artifact_task_payload(
    artifact: AgentArtifact | Mapping[str, Any],
) -> AgentArtifactTaskPayload:
    """Build the durable task payload for a validated advisory artifact."""

    parsed = artifact if isinstance(artifact, AgentArtifact) else AgentArtifact.model_validate(artifact)
    return AgentArtifactTaskPayload(
        task_version=AGENT_ARTIFACT_TASK_VERSION,
        task_type=AGENT_ARTIFACT_TASK_TYPE,
        artifact_id=parsed.artifact_id,
        artifact_version=parsed.artifact_version,
        artifact_type=parsed.artifact_type,
        tenant_id=parsed.tenant_id,
        created_at=parsed.created_at,
        requires_human_review=parsed.requires_human_review,
        confidence=parsed.confidence,
        evidence_ids=parsed.context.evidence_ids,
        canonical_event_ids=parsed.context.canonical_event_ids,
        ingestion_run_id=parsed.context.ingestion_run_id,
        source_hashes=parsed.context.source_hashes,
        rule_id=parsed.context.rule_id,
        rule_version=parsed.context.rule_version,
        citation_reference=parsed.context.citation_reference,
        request_id=parsed.context.request_id,
        artifact=parsed,
    )


def agent_artifact_idempotency_key(artifact: AgentArtifact | AgentArtifactTaskPayload) -> str:
    """Return the tenant-scoped queue idempotency key for an artifact task."""

    return f"{AGENT_ARTIFACT_TASK_TYPE}:{artifact.tenant_id}:{artifact.artifact_id}:{AGENT_ARTIFACT_VERSION}"


def enqueue_agent_artifact_task(
    db_session: Any,
    artifact: AgentArtifact | Mapping[str, Any],
    *,
    scheduled_at: Optional[datetime] = None,
    priority: Optional[int] = None,
    visibility_timeout_seconds: int = AGENT_ARTIFACT_TASK_VISIBILITY_TIMEOUT_SECONDS,
) -> int:
    """Enqueue an advisory artifact for reliable bridge processing."""

    payload = build_agent_artifact_task_payload(artifact)
    resolved_priority = (
        priority
        if priority is not None
        else (
            AGENT_ARTIFACT_HUMAN_REVIEW_PRIORITY if payload.requires_human_review else AGENT_ARTIFACT_DEFAULT_PRIORITY
        )
    )
    return enqueue_task(
        db_session,
        task_type=AGENT_ARTIFACT_TASK_TYPE,
        payload=payload.model_dump(mode="json"),
        tenant_id=str(payload.tenant_id),
        priority=resolved_priority,
        idempotency_key=agent_artifact_idempotency_key(payload),
        scheduled_at=scheduled_at,
        visibility_timeout_seconds=visibility_timeout_seconds,
    )


def persist_agent_artifact(
    db_session: Any,
    payload: AgentArtifactTaskPayload | Mapping[str, Any],
) -> None:
    """Persist the validated advisory artifact for operator review."""

    parsed = (
        payload if isinstance(payload, AgentArtifactTaskPayload) else AgentArtifactTaskPayload.model_validate(payload)
    )
    artifact = parsed.artifact
    db_session.execute(
        text(
            """
            INSERT INTO fsma.agent_artifacts (
                artifact_id, tenant_id, artifact_version, artifact_type,
                created_at, agent_name, agent_version, model_name, suggestion,
                confidence, requires_human_review, evidence_ids,
                canonical_event_ids, ingestion_run_id, source_hashes, rule_id,
                rule_version, citation_reference, request_id, artifact, payload
            )
            VALUES (
                :artifact_id, :tenant_id, :artifact_version, :artifact_type,
                :created_at, :agent_name, :agent_version, :model_name,
                :suggestion, :confidence, :requires_human_review,
                CAST(:evidence_ids AS uuid[]),
                CAST(:canonical_event_ids AS uuid[]),
                :ingestion_run_id,
                CAST(:source_hashes AS text[]),
                :rule_id, :rule_version, :citation_reference, :request_id,
                CAST(:artifact AS jsonb), CAST(:payload AS jsonb)
            )
            ON CONFLICT (artifact_id) DO NOTHING
            """
        ),
        {
            "artifact_id": str(parsed.artifact_id),
            "tenant_id": str(parsed.tenant_id),
            "artifact_version": parsed.artifact_version,
            "artifact_type": parsed.artifact_type,
            "created_at": parsed.created_at,
            "agent_name": artifact.agent_name,
            "agent_version": artifact.agent_version,
            "model_name": artifact.model_name,
            "suggestion": artifact.suggestion,
            "confidence": parsed.confidence,
            "requires_human_review": parsed.requires_human_review,
            "evidence_ids": [str(value) for value in parsed.evidence_ids],
            "canonical_event_ids": [str(value) for value in parsed.canonical_event_ids],
            "ingestion_run_id": str(parsed.ingestion_run_id) if parsed.ingestion_run_id else None,
            "source_hashes": list(parsed.source_hashes),
            "rule_id": parsed.rule_id,
            "rule_version": parsed.rule_version,
            "citation_reference": parsed.citation_reference,
            "request_id": parsed.request_id,
            "artifact": json.dumps(artifact.model_dump(mode="json"), sort_keys=True),
            "payload": json.dumps(artifact.payload.model_dump(mode="json"), sort_keys=True),
        },
    )


def append_agent_artifact_receipt(
    db_session: Any,
    payload: AgentArtifactTaskPayload | Mapping[str, Any],
) -> AgentLedgerBridgeResult:
    """Append an advisory receipt to the ingestion-run ledger when possible."""

    parsed = (
        payload if isinstance(payload, AgentArtifactTaskPayload) else AgentArtifactTaskPayload.model_validate(payload)
    )
    if parsed.ingestion_run_id is None:
        return AgentLedgerBridgeResult(
            artifact_id=parsed.artifact_id,
            tenant_id=parsed.tenant_id,
            ledger_receipt_appended=False,
            skip_reason="missing_ingestion_run_id",
        )

    ledger_state: Literal["needs_review", "rule_evaluated"] = (
        "needs_review" if parsed.requires_human_review else "rule_evaluated"
    )
    row = db_session.execute(
        text(
            """
            INSERT INTO fsma.ingestion_run_receipts (
                tenant_id, ingestion_run_id, state, actor, request_id, metadata
            )
            VALUES (
                :tenant_id, :ingestion_run_id, :state, :actor, :request_id,
                CAST(:metadata AS jsonb)
            )
            RETURNING receipt_id::text, receipt_hash
            """
        ),
        {
            "tenant_id": str(parsed.tenant_id),
            "ingestion_run_id": str(parsed.ingestion_run_id),
            "state": ledger_state,
            "actor": f"agent:{parsed.artifact.agent_name}",
            "request_id": parsed.request_id,
            "metadata": json.dumps(_receipt_metadata(parsed), sort_keys=True),
        },
    ).fetchone()

    return AgentLedgerBridgeResult(
        artifact_id=parsed.artifact_id,
        tenant_id=parsed.tenant_id,
        ledger_receipt_appended=True,
        ledger_state=ledger_state,
        receipt_id=str(row[0]) if row else None,
        receipt_hash=str(row[1]) if row else None,
    )


def handle_agent_artifact_task(**payload: Any) -> None:
    """TaskWorker handler for ``agent_artifact_review`` queue rows."""

    parsed = AgentArtifactTaskPayload.model_validate(payload)
    db_session = _get_session()
    try:
        set_tenant_guc(db_session, str(parsed.tenant_id))
        persist_agent_artifact(db_session, parsed)
        result = append_agent_artifact_receipt(db_session, parsed)
        db_session.commit()
        logger.info(
            "agent_artifact_task_processed",
            extra={
                "artifact_id": str(parsed.artifact_id),
                "tenant_id": str(parsed.tenant_id),
                "ledger_receipt_appended": result.ledger_receipt_appended,
                "ledger_state": result.ledger_state,
                "receipt_id": result.receipt_id,
            },
        )
    except Exception:
        db_session.rollback()
        logger.exception(
            "agent_artifact_task_failed",
            extra={
                "artifact_id": str(parsed.artifact_id),
                "tenant_id": str(parsed.tenant_id),
            },
        )
        raise
    finally:
        db_session.close()


def register_agent_bridge_handlers() -> None:
    """Register agent bridge task handlers with the shared TaskWorker."""

    register_task_handler(AGENT_ARTIFACT_TASK_TYPE, handle_agent_artifact_task)


def _receipt_metadata(payload: AgentArtifactTaskPayload) -> dict[str, Any]:
    artifact = payload.artifact
    return {
        "advisory_contract": "propose_never_decide",
        "agent_artifact": {
            "artifact_id": str(payload.artifact_id),
            "artifact_version": payload.artifact_version,
            "artifact_type": payload.artifact_type,
            "agent_name": artifact.agent_name,
            "agent_version": artifact.agent_version,
            "model_name": artifact.model_name,
            "confidence": payload.confidence,
            "requires_human_review": payload.requires_human_review,
            "suggestion": artifact.suggestion,
        },
        "traceability": {
            "evidence_ids": [str(value) for value in payload.evidence_ids],
            "canonical_event_ids": [str(value) for value in payload.canonical_event_ids],
            "ingestion_run_id": (str(payload.ingestion_run_id) if payload.ingestion_run_id else None),
            "source_hashes": list(payload.source_hashes),
            "rule_id": payload.rule_id,
            "rule_version": payload.rule_version,
            "citation_reference": payload.citation_reference,
            "request_id": payload.request_id,
        },
        "task": {
            "task_version": payload.task_version,
            "task_type": payload.task_type,
        },
        "artifact_payload": artifact.payload.model_dump(mode="json"),
    }


def _strip_embedded_agent_artifact_schema_ids(schema: dict[str, Any]) -> None:
    agent_artifact_schema = schema.get("$defs", {}).get("AgentArtifact")
    if isinstance(agent_artifact_schema, dict):
        # AgentArtifact is embedded here, so its standalone schema ID would
        # make local $refs resolve against the wrong document.
        agent_artifact_schema.pop("$id", None)
        agent_artifact_schema.pop("$schema", None)


def _get_session() -> Any:
    from shared.database import SessionLocal

    return SessionLocal()


__all__ = [
    "AGENT_ARTIFACT_TASK_TYPE",
    "AGENT_ARTIFACT_TASK_VERSION",
    "AgentArtifactTaskPayload",
    "AgentLedgerBridgeResult",
    "agent_artifact_idempotency_key",
    "append_agent_artifact_receipt",
    "build_agent_artifact_task_payload",
    "enqueue_agent_artifact_task",
    "handle_agent_artifact_task",
    "persist_agent_artifact",
    "register_agent_bridge_handlers",
]
