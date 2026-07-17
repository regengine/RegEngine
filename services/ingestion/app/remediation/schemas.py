"""Pydantic request/response models for the remediation slice.

Supplier-facing request models deliberately define NO tenant_id field —
tenant context comes only from the token row (see supplier_router.py).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

MAX_FIELD_VALUE_CHARS = 4096


class RuleFailureOut(BaseModel):
    issue_id: str
    rule_id: str
    rule_version: int
    rule_title: str
    severity: str
    category: str
    result: str  # fail | warn
    why_failed: str
    remediation: Optional[str] = None
    source: str  # kde | rule | service
    field: Optional[str] = None
    source_column: Optional[str] = None
    remediation_owner: str = "supplier"
    auto_resolvable: bool = False


class RecordSummaryOut(BaseModel):
    record_id: str
    row_number: int
    validation_status: str
    release_status: str
    blocking: bool
    failures: List[RuleFailureOut] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    remediation_case_id: Optional[str] = None
    released_event_id: Optional[str] = None


class ManifestUploadResponse(BaseModel):
    ingestion_run_id: str
    source_sha256: str
    original_filename: str
    ruleset_hash: str
    total_rows: int
    passed: int
    failed: int
    records: List[RecordSummaryOut]


class ReleaseRequest(BaseModel):
    record_ids: Optional[List[str]] = None


class ReleaseResponse(BaseModel):
    released: List[Dict[str, str]]
    skipped: List[Dict[str, str]]


class CreateLinkRequest(BaseModel):
    authorized_fields: Optional[List[str]] = Field(
        default=None,
        description="Field paths the supplier may correct; defaults to the case's failing fields.",
    )
    supplier_email: Optional[str] = Field(default=None, max_length=320)
    expires_hours: int = Field(default=24, ge=1, le=168)


class CreateLinkResponse(BaseModel):
    token_id: str
    case_id: str
    correction_url: str
    token: str  # returned exactly once; only its hash is stored
    expires_at: str
    authorized_fields: List[Dict[str, Any]]


class ExchangeRequest(BaseModel):
    token: str = Field(min_length=16, max_length=128)


class AttestationIn(BaseModel):
    text: str = Field(min_length=10, max_length=2000)
    accepted: bool


class CorrectionRequest(BaseModel):
    changes: Dict[str, str] = Field(min_length=1, max_length=10)
    actor_name: str = Field(min_length=1, max_length=200)
    actor_role: str = Field(min_length=1, max_length=200)
    correcting_org: Optional[str] = Field(default=None, max_length=300)
    reason: str = Field(min_length=3, max_length=2000)
    attestation: AttestationIn
    evidence_ref: Optional[str] = Field(default=None, max_length=500)
