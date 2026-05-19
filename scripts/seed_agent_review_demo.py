#!/usr/bin/env python3
"""Seed deterministic synthetic FSMA agent-review artifacts.

This script populates the agent operator-review tables without touching the
legacy DORA ``review_items`` path. It uses the shared ``AgentArtifact``
contracts and the agent task bridge persistence helpers so demo rows also get
advisory ingestion-run receipts.

Usage:
    PYTHONPATH=services python3 scripts/seed_agent_review_demo.py --dry-run
    PYTHONPATH=services python3 scripts/seed_agent_review_demo.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from uuid import UUID, uuid5

from sqlalchemy import text


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = REPO_ROOT / "services"
if str(SERVICES_DIR) in sys.path:
    sys.path.remove(str(SERVICES_DIR))
sys.path.insert(0, str(SERVICES_DIR))

from shared.agent_artifacts import (  # noqa: E402
    AGENT_ARTIFACT_VERSION,
    AgentArtifact,
    AgentArtifactContext,
    ExportReadinessSummaryPayload,
    FieldMappingSuggestionPayload,
    IdentityMatchSuggestionPayload,
    ReviewRoutingSuggestionPayload,
    ValidationExplanationPayload,
)
from shared.agent_task_bridge import (  # noqa: E402
    append_agent_artifact_receipt,
    build_agent_artifact_task_payload,
    persist_agent_artifact,
)
from shared.tenant_context import set_tenant_guc  # noqa: E402


DEFAULT_TENANT_ID = UUID("00000000-de00-4000-8000-000000000001")
DEFAULT_INGESTION_RUN_ID = UUID("00000000-de00-4000-8000-0000000000a1")
DEMO_NAMESPACE = UUID("15597ebc-1b76-50d3-861d-80f61a570eb8")
DEMO_CREATED_AT = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
DEMO_REQUEST_ID = "synthetic-agent-review-demo"
DEMO_AGENT_NAME = "fsma-agent-review-demo-seeder"
DEMO_AGENT_VERSION = "2026.05.19"
DEMO_MODEL_NAME = "synthetic-deterministic-fixture"
DEFAULT_DEV_DATABASE_URL = "postgresql://regengine:regengine@postgres:5432/regengine"

ARTIFACT_TYPES = (
    "field_mapping_suggestion",
    "identity_match_suggestion",
    "validation_explanation",
    "review_routing_suggestion",
    "export_readiness_summary",
)


@dataclass(frozen=True)
class SeedResult:
    artifacts_created: int = 0
    artifacts_skipped: int = 0
    receipts_created: int = 0
    receipts_skipped: int = 0


def build_demo_artifacts(
    *,
    tenant_id: UUID | str = DEFAULT_TENANT_ID,
    ingestion_run_id: UUID | str = DEFAULT_INGESTION_RUN_ID,
) -> list[AgentArtifact]:
    """Return deterministic, Pydantic-validated synthetic demo artifacts."""

    tenant_uuid = _coerce_uuid(tenant_id, "tenant_id")
    run_uuid = _coerce_uuid(ingestion_run_id, "ingestion_run_id")

    return [
        _artifact(
            tenant_uuid,
            run_uuid,
            artifact_type="field_mapping_suggestion",
            artifact_key="field-map-supplier-tlc",
            suggestion=(
                "Synthetic FSMA agent-review demo: map supplier field "
                "`Supplier Lot / TLC` to the canonical traceability lot code."
            ),
            confidence=0.93,
            requires_human_review=False,
            rule_id="fsma-204-field-mapping-tlc",
            rule_version=1,
            citation_reference="21 CFR 1.1345(b)(3)",
            evidence_keys=["supplier-csv-row-17"],
            canonical_event_keys=["receiving-romaine-a23"],
            source_keys=["supplier-upload-romaine-a23"],
            payload=FieldMappingSuggestionPayload(
                source_field="Supplier Lot / TLC",
                source_value="Romaine-Lot A23",
                target_canonical_field="traceability_lot_code",
                normalized_value="ROM-2026-05-19-A23",
                rationale=(
                    "The supplier column contains the lot value required for "
                    "FSMA traceability-lot-code export fields."
                ),
            ),
        ),
        _artifact(
            tenant_uuid,
            run_uuid,
            artifact_type="identity_match_suggestion",
            artifact_key="identity-match-sunshine-packing",
            suggestion=(
                "Synthetic FSMA agent-review demo: review an ambiguous facility "
                "identity match before applying it to canonical events."
            ),
            confidence=0.74,
            requires_human_review=True,
            rule_id="fsma-204-identity-gln-resolution",
            rule_version=2,
            citation_reference="21 CFR 1.1315",
            evidence_keys=["supplier-master-row-04"],
            canonical_event_keys=["shipping-romaine-a23"],
            source_keys=["supplier-master-sunshine-packing"],
            payload=IdentityMatchSuggestionPayload(
                candidate_entity_ids=[
                    _stable_uuid(tenant_uuid, run_uuid, "entity", "sunshine-packing-co"),
                    _stable_uuid(tenant_uuid, run_uuid, "entity", "sunshine-packing-company"),
                ],
                match_type="ambiguous",
                matching_fields=[
                    {
                        "field": "gln",
                        "source_value": "0061414100020",
                        "candidate_value": "0061414100020",
                    },
                    {
                        "field": "facility_name",
                        "source_value": "Sunshine Packing",
                        "candidate_value": "Sunshine Packing Co",
                    },
                ],
                rationale=(
                    "The GLN matches exactly, but the source name is abbreviated "
                    "and should be reviewed before the identity edge is accepted."
                ),
            ),
        ),
        _artifact(
            tenant_uuid,
            run_uuid,
            artifact_type="validation_explanation",
            artifact_key="validation-missing-previous-source",
            suggestion=(
                "Synthetic FSMA agent-review demo: explain a failed receiving "
                "KDE validation in reviewer-readable language."
            ),
            confidence=0.82,
            requires_human_review=True,
            rule_id="fsma-204-receiving-previous-source",
            rule_version=3,
            citation_reference="21 CFR 1.1345(b)(2)",
            evidence_keys=["receiver-spreadsheet-row-22"],
            canonical_event_keys=["receiving-spinach-b11"],
            source_keys=["receiver-upload-spinach-b11"],
            payload=ValidationExplanationPayload(
                rule_result="fail",
                inspected_fields=[
                    {
                        "field": "immediate_previous_source",
                        "value": None,
                        "required": True,
                    },
                    {
                        "field": "traceability_lot_code",
                        "value": "SPN-2026-05-18-B11",
                        "required": True,
                    },
                ],
                explanation=(
                    "The receiving event has a traceability lot code but does not "
                    "identify the immediate previous source."
                ),
                remediation_suggestion=(
                    "Ask the receiving operator to attach the bill of lading or "
                    "supplier ASN that names the previous source."
                ),
            ),
        ),
        _artifact(
            tenant_uuid,
            run_uuid,
            artifact_type="review_routing_suggestion",
            artifact_key="routing-high-priority-identity-kde",
            suggestion=(
                "Synthetic FSMA agent-review demo: route the ambiguous identity "
                "match and failed KDE validation to the operator queue."
            ),
            confidence=0.79,
            requires_human_review=True,
            rule_id="fsma-204-review-routing-priority",
            rule_version=1,
            citation_reference="FSMA 204 operator review policy v1",
            evidence_keys=["receiver-spreadsheet-row-22", "supplier-master-row-04"],
            canonical_event_keys=["receiving-spinach-b11"],
            source_keys=["routing-bundle-spinach-b11"],
            payload=ReviewRoutingSuggestionPayload(
                review_queue_name="FSMA Exceptions - Identity and KDE",
                priority=88,
                review_reason=(
                    "The ingestion run contains both an ambiguous facility match "
                    "and a failed receiving KDE that block confident export."
                ),
            ),
        ),
        _artifact(
            tenant_uuid,
            run_uuid,
            artifact_type="export_readiness_summary",
            artifact_key="export-readiness-summary",
            suggestion=(
                "Synthetic FSMA agent-review demo: summarize export readiness "
                "for the operator before FDA-response package generation."
            ),
            confidence=0.91,
            requires_human_review=True,
            rule_id="fsma-204-export-readiness",
            rule_version=4,
            citation_reference="21 CFR 1.1455",
            evidence_keys=["export-readiness-snapshot"],
            canonical_event_keys=["receiving-romaine-a23", "receiving-spinach-b11"],
            source_keys=["export-readiness-snapshot"],
            payload=ExportReadinessSummaryPayload(
                exportable=False,
                blockers=[
                    "Receiving event SPN-2026-05-18-B11 is missing immediate_previous_source.",
                    "Sunshine Packing facility identity match is ambiguous.",
                ],
                warnings=[
                    "Romaine lot ROM-2026-05-19-A23 is exportable but includes an agent-suggested field mapping.",
                ],
                referenced_rule_versions={
                    "fsma-204-field-mapping-tlc": 1,
                    "fsma-204-identity-gln-resolution": 2,
                    "fsma-204-receiving-previous-source": 3,
                    "fsma-204-review-routing-priority": 1,
                    "fsma-204-export-readiness": 4,
                },
            ),
        ),
    ]


def seed_agent_review_demo(db_session, artifacts: Iterable[AgentArtifact]) -> SeedResult:
    """Persist demo artifacts and advisory receipts idempotently."""

    created = 0
    skipped = 0
    receipts_created = 0
    receipts_skipped = 0

    artifacts = list(artifacts)
    if not artifacts:
        return SeedResult()

    tenant_ids = {artifact.tenant_id for artifact in artifacts}
    if len(tenant_ids) != 1:
        raise ValueError("agent-review demo seed artifacts must belong to one tenant")

    tenant_id = str(next(iter(tenant_ids)))
    set_tenant_guc(db_session, tenant_id)
    _ensure_ingestion_run(db_session, artifacts[0])

    for artifact in artifacts:
        payload = build_agent_artifact_task_payload(artifact)
        if _artifact_exists(db_session, artifact):
            skipped += 1
        else:
            persist_agent_artifact(db_session, payload)
            created += 1

        if _receipt_exists(db_session, payload):
            receipts_skipped += 1
        else:
            append_agent_artifact_receipt(db_session, payload)
            receipts_created += 1

    return SeedResult(
        artifacts_created=created,
        artifacts_skipped=skipped,
        receipts_created=receipts_created,
        receipts_skipped=receipts_skipped,
    )


def is_safe_database_url_for_demo_seed(database_url: str | None) -> bool:
    """Return whether a URL looks local/dev enough for synthetic seeding."""

    if not database_url:
        return False

    lowered = database_url.lower()
    if lowered.startswith("sqlite:"):
        return True

    parsed = urlparse(database_url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False

    production_markers = (
        "supabase.co",
        "pooler.supabase.com",
        "railway",
        "render.com",
        "amazonaws.com",
        "rds.amazonaws.com",
        "neon.tech",
        "herokuapp.com",
        "fly.dev",
        "azure.com",
    )
    if any(marker in host for marker in production_markers):
        return False

    local_hosts = {"localhost", "127.0.0.1", "::1", "postgres", "host.docker.internal"}
    return host in local_hosts or host.endswith(".local") or host.endswith(".test")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed deterministic synthetic FSMA agent-review demo artifacts."
    )
    parser.add_argument(
        "--tenant-id",
        type=UUID,
        default=DEFAULT_TENANT_ID,
        help=f"Tenant UUID to seed. Defaults to {DEFAULT_TENANT_ID}.",
    )
    parser.add_argument(
        "--ingestion-run-id",
        type=UUID,
        default=DEFAULT_INGESTION_RUN_ID,
        help=f"Ingestion run UUID to anchor artifacts. Defaults to {DEFAULT_INGESTION_RUN_ID}.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print artifacts without opening a database connection.",
    )
    parser.add_argument(
        "--allow-production-demo-seed",
        action="store_true",
        help="Allow seeding when environment or DATABASE_URL looks production.",
    )
    args = parser.parse_args(argv)

    artifacts = build_demo_artifacts(
        tenant_id=args.tenant_id,
        ingestion_run_id=args.ingestion_run_id,
    )

    if args.dry_run:
        _print_dry_run(artifacts)
        return 0

    database_url = os.environ.get("DATABASE_URL") or DEFAULT_DEV_DATABASE_URL
    if not args.allow_production_demo_seed and (
        _environment_looks_production() or not is_safe_database_url_for_demo_seed(database_url)
    ):
        print(
            "Refusing to seed synthetic agent-review demo data because the "
            "environment or DATABASE_URL does not look local/dev. Re-run with "
            "--allow-production-demo-seed only if you intentionally want demo "
            "fixtures in that database.",
            file=sys.stderr,
        )
        return 2

    try:
        from shared.database import SessionLocal

        db_session = SessionLocal()
        try:
            result = seed_agent_review_demo(db_session, artifacts)
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()
    except Exception as exc:
        print(f"Failed to seed FSMA agent-review demo artifacts: {exc}", file=sys.stderr)
        return 1

    print(
        "Seeded FSMA agent-review demo artifacts: "
        f"{result.artifacts_created} created, {result.artifacts_skipped} already present; "
        f"{result.receipts_created} receipts created, {result.receipts_skipped} already present."
    )
    return 0


def _artifact(
    tenant_id: UUID,
    ingestion_run_id: UUID,
    *,
    artifact_type: str,
    artifact_key: str,
    suggestion: str,
    confidence: float,
    requires_human_review: bool,
    rule_id: str,
    rule_version: int,
    citation_reference: str,
    evidence_keys: list[str],
    canonical_event_keys: list[str],
    source_keys: list[str],
    payload,
) -> AgentArtifact:
    return AgentArtifact(
        artifact_id=_stable_uuid(tenant_id, ingestion_run_id, "artifact", artifact_key),
        artifact_version=AGENT_ARTIFACT_VERSION,
        artifact_type=artifact_type,
        tenant_id=tenant_id,
        created_at=DEMO_CREATED_AT,
        agent_name=DEMO_AGENT_NAME,
        agent_version=DEMO_AGENT_VERSION,
        model_name=DEMO_MODEL_NAME,
        suggestion=suggestion,
        confidence=confidence,
        requires_human_review=requires_human_review,
        context=AgentArtifactContext(
            evidence_ids=[
                _stable_uuid(tenant_id, ingestion_run_id, "evidence", key)
                for key in evidence_keys
            ],
            canonical_event_ids=[
                _stable_uuid(tenant_id, ingestion_run_id, "canonical-event", key)
                for key in canonical_event_keys
            ],
            ingestion_run_id=ingestion_run_id,
            source_hashes=[_source_hash(key) for key in source_keys],
            rule_id=rule_id,
            rule_version=rule_version,
            citation_reference=citation_reference,
            request_id=DEMO_REQUEST_ID,
        ),
        payload=payload,
    )


def _coerce_uuid(value: UUID | str, field_name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a UUID") from exc


def _stable_uuid(tenant_id: UUID, ingestion_run_id: UUID, kind: str, key: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, f"{tenant_id}:{ingestion_run_id}:{kind}:{key}")


def _source_hash(key: str) -> str:
    return hashlib.sha256(f"synthetic-fsma-agent-review-demo:{key}".encode("utf-8")).hexdigest()


def _ensure_ingestion_run(db_session, artifact: AgentArtifact) -> None:
    db_session.execute(
        text(
            """
            INSERT INTO fsma.ingestion_runs (
                id, tenant_id, source_system, source_file_name,
                source_file_hash, source_file_size, record_count,
                accepted_count, rejected_count, mapper_version, schema_version,
                status, initiated_by, started_at, completed_at, errors
            )
            VALUES (
                :id, :tenant_id, :source_system, :source_file_name,
                :source_file_hash, :source_file_size, :record_count,
                :accepted_count, :rejected_count, :mapper_version, :schema_version,
                :status, :initiated_by, :started_at, :completed_at,
                CAST(:errors AS jsonb)
            )
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {
            "id": str(artifact.context.ingestion_run_id),
            "tenant_id": str(artifact.tenant_id),
            "source_system": "manual",
            "source_file_name": "synthetic_agent_review_demo.csv",
            "source_file_hash": _source_hash("synthetic-agent-review-demo-ingestion-run"),
            "source_file_size": 0,
            "record_count": len(ARTIFACT_TYPES),
            "accepted_count": len(ARTIFACT_TYPES),
            "rejected_count": 0,
            "mapper_version": "agent-review-demo-seed.v1",
            "schema_version": AGENT_ARTIFACT_VERSION,
            "status": "completed",
            "initiated_by": "script:seed_agent_review_demo.py",
            "started_at": DEMO_CREATED_AT,
            "completed_at": DEMO_CREATED_AT,
            "errors": "[]",
        },
    )


def _artifact_exists(db_session, artifact: AgentArtifact) -> bool:
    row = db_session.execute(
        text(
            """
            SELECT 1
            FROM fsma.agent_artifacts
            WHERE artifact_id = :artifact_id
              AND tenant_id = :tenant_id
            LIMIT 1
            """
        ),
        {
            "artifact_id": str(artifact.artifact_id),
            "tenant_id": str(artifact.tenant_id),
        },
    ).first()
    return row is not None


def _receipt_exists(db_session, payload) -> bool:
    if payload.ingestion_run_id is None:
        return True

    row = db_session.execute(
        text(
            """
            SELECT 1
            FROM fsma.ingestion_run_receipts
            WHERE tenant_id = :tenant_id
              AND ingestion_run_id = :ingestion_run_id
              AND metadata -> 'agent_artifact' ->> 'artifact_id' = :artifact_id
            LIMIT 1
            """
        ),
        {
            "tenant_id": str(payload.tenant_id),
            "ingestion_run_id": str(payload.ingestion_run_id),
            "artifact_id": str(payload.artifact_id),
        },
    ).first()
    return row is not None


def _environment_looks_production() -> bool:
    regengine_env = os.environ.get("REGENGINE_ENV", "").lower()
    env = os.environ.get("ENV", "").lower()
    if regengine_env == "production" or env == "production":
        return True
    cloud_markers = ("RAILWAY_ENVIRONMENT", "RAILWAY_SERVICE_NAME", "VERCEL_ENV", "VERCEL_URL")
    return any(os.environ.get(marker) for marker in cloud_markers)


def _print_dry_run(artifacts: list[AgentArtifact]) -> None:
    print(json.dumps([artifact.model_dump(mode="json") for artifact in artifacts], indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
