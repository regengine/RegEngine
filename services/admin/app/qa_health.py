"""Sysadmin QA health artifact reader.

The dashboard consumes a normalized JSON artifact instead of raw CI logs so
operator views can stay useful without exposing secrets, stack traces, or
test-result internals to tenant-facing surfaces.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

QA_HEALTH_SCHEMA_VERSION = "1.0"
QA_HEALTH_MAX_BYTES = 256 * 1024

# How old the artifact may be before the dashboard refuses to present it as
# current. ``qa-health.yml`` rebuilds on every push to main and develop, so a
# healthy artifact is hours old; anything measured in days means the pipeline
# that produces it is not reaching this deployment. Seven days is deliberately
# generous — this must catch "nothing has refreshed this in weeks", not flag a
# quiet weekend.
QA_HEALTH_MAX_AGE_DAYS = float(os.getenv("QA_HEALTH_MAX_AGE_DAYS", "7"))

QAHealthStatus = Literal["passing", "failing", "degraded", "unavailable", "invalid_artifact"]
QASuiteStatus = Literal["passed", "failed", "degraded", "skipped", "unavailable"]
QASeverity = Literal["critical", "high", "medium", "low", "info"]
QADecisionStatus = Literal["blocking", "advisory", "passed", "unavailable"]

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\b(?:sk_live|sk_test)_[A-Za-z0-9_]+\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
)


class QAHealthSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["ci_artifact", "local_artifact", "unavailable"] = "ci_artifact"
    path: str | None = None
    workflow: str | None = None
    run_id: str | None = None
    commit: str | None = None
    branch: str | None = None
    note: str | None = None


class QAHealthOverall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: QAHealthStatus
    ready_percent: int = Field(ge=0, le=100)
    blocking_count: int = Field(ge=0)
    advisory_count: int = Field(ge=0)


class QAHealthSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    command: str
    status: QASuiteStatus
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    errors: int = Field(ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    blocking: bool


class QAHealthCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    severity: QASeverity
    affected_suites: list[str] = Field(default_factory=list)
    owner_lane: str
    impact: str
    next_action: str


class QAHealthDecisionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    status: QADecisionStatus
    detail: str | None = None


class QAHealthArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    path: str
    type: str

    @field_validator("path")
    @classmethod
    def path_must_be_relative(cls, value: str) -> str:
        if "\\" in value:
            raise ValueError("artifact path must use forward slashes")
        if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
            raise ValueError("artifact path must be relative")
        parts = PurePosixPath(value).parts
        if ".." in parts:
            raise ValueError("artifact path must not traverse directories")
        if not value.strip():
            raise ValueError("artifact path is required")
        return value


class QAHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    generated_at: str
    source: QAHealthSource
    overall: QAHealthOverall
    suites: list[QAHealthSuite] = Field(default_factory=list)
    clusters: list[QAHealthCluster] = Field(default_factory=list)
    decision_checks: list[QAHealthDecisionCheck] = Field(default_factory=list)
    artifact_refs: list[QAHealthArtifactRef] = Field(default_factory=list)


def default_qa_health_summary_path() -> Path:
    configured = os.getenv("QA_HEALTH_SUMMARY_PATH")
    if configured:
        return Path(configured)

    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "qa" / "qa-health" / "latest.json"


def load_qa_health_summary(path: Path | None = None) -> QAHealthResponse:
    summary_path = path or default_qa_health_summary_path()

    try:
        stat = summary_path.stat()
    except FileNotFoundError:
        return _fallback_summary(
            status="unavailable",
            note="QA health summary artifact is not available.",
            path=summary_path,
        )
    except OSError:
        return _fallback_summary(
            status="unavailable",
            note="QA health summary artifact could not be inspected.",
            path=summary_path,
        )

    if stat.st_size > QA_HEALTH_MAX_BYTES:
        return _fallback_summary(
            status="invalid_artifact",
            note="QA health summary artifact exceeded the size limit.",
            path=summary_path,
        )

    try:
        raw = json.loads(summary_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return _fallback_summary(
            status="invalid_artifact",
            note="QA health summary artifact is not valid JSON.",
            path=summary_path,
        )

    try:
        summary = QAHealthResponse.model_validate(raw)
    except ValidationError:
        return _fallback_summary(
            status="invalid_artifact",
            note="QA health summary artifact did not match the expected schema.",
            path=summary_path,
        )

    stale_note = _staleness_note(summary.generated_at)
    if stale_note:
        # A snapshot that nothing has refreshed is not "the latest CI
        # artifact", and presenting one as current is worse than presenting
        # nothing: the numbers look authoritative and are simply old. This
        # deployment shipped a build-time copy frozen at 2026-07-23 for weeks,
        # labelled "Latest CI artifact", because the only freshness check on
        # the file was a size cap.
        #
        # ``unavailable`` rather than a new status value on purpose. It is
        # already in ``QAHealthStatus`` and already handled by every consumer,
        # so the honest answer needs no contract change to be understood — and
        # the note carries the age for whoever is looking.
        return _fallback_summary(
            status="unavailable",
            note=stale_note,
            path=summary_path,
        )

    sanitized = _scrub_value(summary.model_dump(mode="json"))
    return QAHealthResponse.model_validate(sanitized)


def _staleness_note(generated_at: str) -> str | None:
    """Return an explanatory note when ``generated_at`` is too old, else None.

    An unparseable timestamp is treated as stale. The alternative — trusting a
    value we could not read — is how a frozen artifact passes for a fresh one.
    """
    if QA_HEALTH_MAX_AGE_DAYS <= 0:
        return None

    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return "QA health summary artifact has an unreadable generated_at timestamp."

    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)

    age_days = (datetime.now(timezone.utc) - generated).total_seconds() / 86400
    if age_days <= QA_HEALTH_MAX_AGE_DAYS:
        return None

    return (
        f"QA health summary artifact is stale — generated {age_days:.0f} days ago "
        f"({generated_at}), past the {QA_HEALTH_MAX_AGE_DAYS:.0f}-day limit. "
        "Nothing has refreshed it, so its results are not reported."
    )


def _fallback_summary(*, status: QAHealthStatus, note: str, path: Path) -> QAHealthResponse:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    return QAHealthResponse(
        schema_version=QA_HEALTH_SCHEMA_VERSION,
        generated_at=now,
        source=QAHealthSource(
            kind="unavailable",
            path=_safe_source_path(path),
            note=note,
        ),
        overall=QAHealthOverall(
            status=status,
            ready_percent=0,
            blocking_count=0,
            advisory_count=0,
        ),
        suites=[],
        clusters=[],
        decision_checks=[
            QAHealthDecisionCheck(
                label="QA artifact",
                status="unavailable",
                detail=note,
            )
        ],
        artifact_refs=[],
    )


def _safe_source_path(path: Path) -> str:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except (OSError, ValueError):
        return path.name


def _scrub_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _scrub_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_scrub_value(child) for child in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _redact_string(value: str) -> str:
    scrubbed = value
    for pattern in _SECRET_PATTERNS:
        scrubbed = pattern.sub(
            lambda match: f"{match.group(1)}[redacted]" if match.lastindex else "[redacted]",
            scrubbed,
        )
    if len(scrubbed) > 500:
        return f"{scrubbed[:497]}..."
    return scrubbed
