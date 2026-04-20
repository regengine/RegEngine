from __future__ import annotations

import re
from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Reviewer hint character class — ASCII alphanumerics plus the subset
# of punctuation that legitimately appears in names and email addresses.
# Anything outside this set is rejected to prevent stored-XSS / CKG
# node-key poisoning when the hint is rendered in an admin UI or
# written as a graph node key (issue #1125 / EPIC-L).
_REVIEWER_HINT_RE = re.compile(r"^[A-Za-z0-9 .,'_@\-]{2,120}$")


# ---------------------------------------------------------------------------
# FSMA 204 Models
# ---------------------------------------------------------------------------

ModelStatus = Literal["active", "deprecated"]
ValidationType = Literal["fairness", "performance", "conceptual_soundness"]
ChangeType = Literal["feature_added", "threshold_change", "retrain"]


class ModelRegistrationRequest(BaseModel):
    id: str = Field(..., min_length=2)
    name: str = Field(..., min_length=2)
    version: str = Field(..., min_length=1)
    owner: str = Field(..., min_length=2)
    deployment_date: date
    status: ModelStatus = "active"


class ValidationRequest(BaseModel):
    validation_type: ValidationType
    validator: str = Field(..., min_length=2)
    date: date
    status: Literal["passed", "failed"]
    notes: Optional[str] = None


class ModelChangeRequest(BaseModel):
    change_type: ChangeType
    description: str = Field(..., min_length=4)
    date: date


class ModelRecordResponse(BaseModel):
    id: str
    name: str
    version: str
    owner: str
    deployment_date: date
    status: ModelStatus
    deployment_locked: bool
    lock_reason: Optional[str]
    last_fairness_result_at: Optional[datetime] = None


AuditOutputType = Literal[
    "regulator_examination_package",
    "model_validation_dossier",
]


class AuditExportRequest(BaseModel):
    """Request body for an audit-artifact export.

    ``reviewer`` is a **hint only** — it is never used as the
    authoritative attestation identity. The route handler derives the
    reviewer sign-off from the authenticated principal (api_key.key_id
    or a signed reviewer-identity JWT) and ignores any attempt to
    assert a different reviewer via the request body.

    The hint is still accepted so auditors can annotate who they
    *intend* the reviewer to be, but it's validated against a narrow
    character class so stored-XSS or CKG node-key poisoning attempts
    can't land even if a future handler accidentally echoes it (issue
    #1125 / EPIC-L).
    """

    model_id: str = Field(..., min_length=2, max_length=120)
    output_type: AuditOutputType
    reviewer: str = Field(
        ...,
        min_length=2,
        max_length=120,
        description=(
            "Advisory reviewer label only — the authoritative reviewer "
            "sign-off is derived server-side from the authenticated "
            "principal. Must match ^[A-Za-z0-9 .,'_@-]{2,120}$."
        ),
    )

    @field_validator("reviewer")
    @classmethod
    def _validate_reviewer(cls, value: str) -> str:
        if not _REVIEWER_HINT_RE.match(value):
            raise ValueError(
                "reviewer must match ^[A-Za-z0-9 .,'_@-]{2,120}$; "
                "tokens containing HTML, quotes, or control characters "
                "are rejected to prevent audit-trail pollution"
            )
        return value


class AuditExportResponse(BaseModel):
    artifact_id: str
    model_id: str
    output_type: AuditOutputType
    version: int
    immutable: bool
    hash_sha256: str
    generated_at: datetime
    metadata: Dict[str, str]


class RiskSummaryResponse(BaseModel):
    overall_risk: Literal["Low", "Medium", "High"]
    drift_status: Literal["Green", "Yellow", "Red"]
    last_tested: date
    exposure_score: float


class CKGSummaryResponse(BaseModel):
    nodes_by_type: Dict[str, int]
    edge_count: int
    latest_evidence_id: Optional[str]
