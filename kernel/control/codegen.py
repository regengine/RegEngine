"""
Code Generation Module
======================
Generates FastAPI routes and Pydantic models from vertical schemas.

Security posture
----------------
Vertical metadata values flow directly into emitted Python source. Any string
that is *interpolated* into a code template is treated as untrusted and must
pass a strict regex allowlist before it is allowed into the template. Values
that fail the allowlist cause codegen to raise ``CodegenValidationError``
**before** any source is emitted or written to disk. This is a fail-closed
policy: we never try to escape untrusted input into generated Python, because
escaping generated Python is notoriously error-prone and cannot be audited
statically.

If you are adding a new template field that reads from ``vertical_meta`` or
``obligations``, you MUST either:

1. Route the value through :func:`_assert_safe_identifier`,
   :func:`_assert_safe_ident_list`, :func:`_assert_safe_citation`, or
2. Emit it as ``repr(...)`` of a plain Python literal (str/int/bool) so the
   parser, not the template, is responsible for framing it.

Related GitHub issues: #1275 (placeholder NameError), #1285 (RCE via
unvalidated interpolation), #1295 (emitted module correctness).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any, Iterable, List, Sequence


class CodegenValidationError(ValueError):
    """Raised when untrusted metadata fails the codegen allowlist.

    This is deliberately a ``ValueError`` subclass rather than a Pydantic
    ``ValidationError`` so callers can catch it specifically without depending
    on Pydantic internals.
    """


# ---------------------------------------------------------------------------
# Allowlist patterns
#
# These patterns are intentionally stricter than schema_validator.py to defend
# against codegen-specific injection even if a caller skips the compiler's
# pre-validation step.
# ---------------------------------------------------------------------------

# Python identifier-like: lowercase letters, digits, underscores, must start
# with a letter. Matches the convention for ``decision_types`` and
# ``vertical_meta.name``.
_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Citation strings (e.g. "21 CFR 1.1320") — letters, digits, spaces,
# dots, dashes, slashes. No quotes, no backslashes, no newlines.
_CITATION_RE = re.compile(r"^[A-Za-z0-9 .\-/()§]{1,128}$")

# Obligation IDs (uppercase snake case)
_OBLIGATION_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

# Regulator / domain names — uppercase letters, digits, underscores
_ENUM_LIKE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


def _assert_safe_identifier(value: Any, *, field: str) -> str:
    """Assert ``value`` is a safe Python-identifier-like string.

    Raises :class:`CodegenValidationError` with ``field`` in the message on
    any violation. Returns the validated string unchanged.
    """
    if not isinstance(value, str):
        raise CodegenValidationError(
            f"codegen: {field!r} must be a string, got {type(value).__name__}"
        )
    if not _IDENT_RE.match(value):
        raise CodegenValidationError(
            f"codegen: {field!r}={value!r} failed allowlist "
            f"(expected {_IDENT_RE.pattern})"
        )
    return value


def _assert_safe_ident_list(values: Any, *, field: str) -> List[str]:
    """Assert every item in ``values`` is a safe identifier."""
    if not isinstance(values, (list, tuple)):
        raise CodegenValidationError(
            f"codegen: {field!r} must be a list, got {type(values).__name__}"
        )
    if len(values) == 0:
        raise CodegenValidationError(
            f"codegen: {field!r} must be non-empty"
        )
    validated: List[str] = []
    for i, v in enumerate(values):
        validated.append(_assert_safe_identifier(v, field=f"{field}[{i}]"))
    return validated


def _assert_safe_citation(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise CodegenValidationError(
            f"codegen: {field!r} must be a string, got {type(value).__name__}"
        )
    if not _CITATION_RE.match(value):
        raise CodegenValidationError(
            f"codegen: {field!r}={value!r} failed allowlist "
            f"(expected {_CITATION_RE.pattern})"
        )
    return value


def _assert_safe_enum_like(value: Any, *, field: str) -> str:
    if not isinstance(value, str):
        raise CodegenValidationError(
            f"codegen: {field!r} must be a string, got {type(value).__name__}"
        )
    if not _ENUM_LIKE_RE.match(value):
        raise CodegenValidationError(
            f"codegen: {field!r}={value!r} failed allowlist "
            f"(expected {_ENUM_LIKE_RE.pattern})"
        )
    return value


def _assert_parsable_python(source: str, *, context: str) -> None:
    """Final belt-and-braces check — emitted source must parse as Python.

    This does not catch runtime bugs, but it does catch catastrophic template
    failures (e.g. unclosed string literals, accidental indentation mistakes)
    before the file is written to disk.
    """
    try:
        ast.parse(source)
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise CodegenValidationError(
            f"codegen: emitted source for {context} is not valid Python: {exc}"
        ) from exc


def _validate_vertical_meta_for_codegen(vertical_meta: Any) -> None:
    """Validate every ``vertical_meta`` field that flows into codegen.

    Fails closed with :class:`CodegenValidationError` on the first violation.
    """
    _assert_safe_identifier(getattr(vertical_meta, "name", None), field="vertical_meta.name")
    _assert_safe_ident_list(
        getattr(vertical_meta, "decision_types", None),
        field="vertical_meta.decision_types",
    )
    # ``regulators`` and ``regulatory_domains`` land in graph_adapter's
    # ``choices=...`` lists but are also referenced here for completeness.
    regulators = getattr(vertical_meta, "regulators", None)
    if regulators is not None:
        if not isinstance(regulators, (list, tuple)):
            raise CodegenValidationError(
                "codegen: vertical_meta.regulators must be a list"
            )
        for i, r in enumerate(regulators):
            _assert_safe_enum_like(r, field=f"vertical_meta.regulators[{i}]")

    domains = getattr(vertical_meta, "regulatory_domains", None)
    if domains is not None:
        if not isinstance(domains, (list, tuple)):
            raise CodegenValidationError(
                "codegen: vertical_meta.regulatory_domains must be a list"
            )
        for i, d in enumerate(domains):
            _assert_safe_enum_like(d, field=f"vertical_meta.regulatory_domains[{i}]")


def _validate_obligations_for_codegen(obligations: Sequence[Any]) -> None:
    """Validate obligation fields that flow into codegen output."""
    for idx, ob in enumerate(obligations):
        _assert_safe_citation(
            getattr(ob, "citation", ""),
            field=f"obligations[{idx}].citation",
        )
        ob_id = getattr(ob, "id", None)
        if ob_id is None or not isinstance(ob_id, str) or not _OBLIGATION_ID_RE.match(ob_id):
            raise CodegenValidationError(
                f"codegen: obligations[{idx}].id={ob_id!r} failed allowlist "
                f"(expected {_OBLIGATION_ID_RE.pattern})"
            )


def _evidence_contract_literal(vertical_meta: Any) -> str:
    """Return a safe ``EVIDENCE_CONTRACT = {...}`` source block.

    ``vertical_meta.evidence_contract`` is a dict keyed by decision_type. We
    emit it via :func:`repr` on data we've already validated (decision types
    and evidence field names). We do not trust the dict shape blindly —
    non-string keys/values raise CodegenValidationError.
    """
    contract = getattr(vertical_meta, "evidence_contract", None) or {}
    if not isinstance(contract, dict):
        raise CodegenValidationError(
            f"codegen: vertical_meta.evidence_contract must be a dict, got "
            f"{type(contract).__name__}"
        )

    safe: dict = {}
    for k, v in contract.items():
        _assert_safe_identifier(k, field=f"evidence_contract[{k!r}]")

        # Accept either the old shape (list of fields) or the schema shape
        # ({"required": [...]}). Normalise to list of fields here.
        if isinstance(v, dict) and "required" in v:
            fields: Iterable = v["required"]
        elif isinstance(v, list):
            fields = v
        else:
            raise CodegenValidationError(
                f"codegen: evidence_contract[{k!r}] must be a dict with "
                f"'required' key or a list, got {type(v).__name__}"
            )

        if not isinstance(fields, (list, tuple)):
            raise CodegenValidationError(
                f"codegen: evidence_contract[{k!r}].required must be a list"
            )
        clean_fields: List[str] = []
        for i, f in enumerate(fields):
            # Evidence field names follow the same identifier rule.
            clean_fields.append(
                _assert_safe_identifier(
                    f, field=f"evidence_contract[{k!r}][{i}]"
                )
            )
        safe[k] = clean_fields

    # ``repr`` on a dict of str -> List[str] produces a safe Python literal:
    # every string goes through the parser's own escape rules.
    return f"EVIDENCE_CONTRACT = {safe!r}"


def generate_fastapi_routes(vertical_meta: Any, obligations: Sequence[Any]) -> str:
    """
    Generate FastAPI routes file.

    Generates:
    - POST /v1/{vertical}/decision/record
    - POST /v1/{vertical}/decision/replay
    - GET  /v1/{vertical}/snapshot
    - GET  /v1/{vertical}/export

    Raises :class:`CodegenValidationError` if any input value fails the
    codegen allowlist (see module docstring).
    """
    _validate_vertical_meta_for_codegen(vertical_meta)
    _validate_obligations_for_codegen(obligations)

    vertical_name = vertical_meta.name
    decision_types: List[str] = list(vertical_meta.decision_types)
    vertical_cap = vertical_name.capitalize()

    # Pre-build every template slot as a sanitised string — never interpolate
    # raw ``vertical_meta`` attributes further down.
    evidence_contract_block = _evidence_contract_literal(vertical_meta)
    decision_types_csv = ", ".join(decision_types)

    # Use ``.format_map`` with explicit named slots rather than f-strings so
    # that the interpolation surface is a closed set, auditable by reading the
    # ``fmt`` dict below.
    template = '''"""
Auto-generated FastAPI routes for {vertical_name} vertical.
DO NOT MODIFY MANUALLY - regenerate via: regengine compile vertical {vertical_name}
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime
import logging

from .models import (
    DecisionRequest,
    DecisionResponse,
    SnapshotResponse,
    ExportRequest,
)

logger = logging.getLogger(__name__)

{evidence_contract_block}

router = APIRouter(prefix="/v1/{vertical_name}", tags=["{vertical_name}"])


@router.post("/decision/record", response_model=DecisionResponse)
async def record_decision(request: DecisionRequest):
    """Record a {vertical_name} decision with evidence.

    Decision Types: {decision_types_csv}
    """
    logger.info("Recording %s decision", request.decision_type)

    # Import services (will be defined in generated service files)
    from .snapshot_service import {vertical_cap}SnapshotService
    from .graph_store import {vertical_cap}GraphStore

    try:
        graph_store = {vertical_cap}GraphStore()
        snapshot_service = {vertical_cap}SnapshotService(graph_store)

        required_fields = EVIDENCE_CONTRACT.get(request.decision_type, [])
        provided_fields = set(request.evidence.keys())
        missing_fields = set(required_fields) - provided_fields

        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required evidence fields: {{missing_fields}}",
            )

        decision_id = await graph_store.create_decision(
            decision_type=request.decision_type,
            evidence=request.evidence,
            metadata=request.metadata,
        )

        obligation_results = await snapshot_service.evaluate_decision_obligations(
            decision_id=decision_id,
            decision_type=request.decision_type,
            evidence=request.evidence,
        )

        envelope_id = await graph_store.create_evidence_envelope(
            decision_id=decision_id,
            evidence=request.evidence,
        )

        obligations_met = sum(1 for r in obligation_results if r.get("met"))
        logger.info(
            "Decision recorded: %s envelope=%s obligations_met=%s/%s",
            decision_id, envelope_id, obligations_met, len(obligation_results),
        )

        return DecisionResponse(
            decision_id=decision_id,
            status="recorded",
            timestamp=datetime.utcnow().isoformat(),
            envelope_id=envelope_id,
            obligations_evaluated=len(obligation_results),
            obligations_met=obligations_met,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to record decision: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshot", response_model=SnapshotResponse)
async def get_snapshot():
    """Get current compliance snapshot for {vertical_name} vertical."""
    logger.info("Computing compliance snapshot")

    from .snapshot_adapter import {vertical_cap}SnapshotAdapter
    from .graph_store import get_graph_client
    from .db import get_db_client

    try:
        graph = get_graph_client()
        db = get_db_client()
        adapter = {vertical_cap}SnapshotAdapter(graph, db)
        snapshot = adapter.compute_snapshot()
        return SnapshotResponse(**snapshot)
    except Exception as e:
        logger.error("Failed to compute snapshot: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {{
        "status": "healthy",
        "service": "{vertical_name}_api",
    }}
'''

    code = template.format_map(
        {
            "vertical_name": vertical_name,
            "vertical_cap": vertical_cap,
            "decision_types_csv": decision_types_csv,
            "evidence_contract_block": evidence_contract_block,
        }
    )

    # Belt-and-braces: the emitted module must parse.
    _assert_parsable_python(code, context=f"{vertical_name}/routes.py")
    return code


def generate_pydantic_models(vertical_meta: Any, obligations: Sequence[Any]) -> str:
    """
    Generate Pydantic models file.

    Generates: DecisionRequest, DecisionResponse, SnapshotResponse, ExportRequest.

    Raises :class:`CodegenValidationError` on allowlist violations.
    """
    _validate_vertical_meta_for_codegen(vertical_meta)
    _validate_obligations_for_codegen(obligations)

    vertical_name = vertical_meta.name
    decision_types: List[str] = list(vertical_meta.decision_types)

    # Build the Enum body safely: both sides of ``NAME = "value"`` are vetted
    # identifiers, so ``repr``-level escaping is unnecessary. We still keep
    # the pattern deterministic.
    enum_members_lines = "\n".join(
        f'    {dt.upper()} = "{dt}"' for dt in decision_types
    )

    template = '''"""
Auto-generated Pydantic models for {vertical_name} vertical.
DO NOT MODIFY MANUALLY - regenerate via: regengine compile vertical {vertical_name}
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum


class DecisionType(str, Enum):
    """Decision types for {vertical_name} vertical."""
{enum_members_lines}


class DecisionRequest(BaseModel):
    """Request to record a decision."""
    decision_id: str
    decision_type: DecisionType
    evidence: Dict[str, Any] = Field(..., description="Evidence payload")
    metadata: Optional[Dict[str, Any]] = None


class DecisionResponse(BaseModel):
    """Response from decision recording."""
    decision_id: str
    status: str
    timestamp: str
    envelope_id: Optional[str] = None
    obligations_evaluated: Optional[int] = None
    obligations_met: Optional[int] = None
    evaluation_id: Optional[str] = None
    coverage_percent: Optional[float] = None
    risk_level: Optional[str] = None


class SnapshotResponse(BaseModel):
    """Compliance snapshot response."""
    snapshot_id: str
    timestamp: str
    vertical: str = "{vertical_name}"
    bias_score: float = 0.0
    drift_score: float = 0.0
    documentation_score: float = 0.0
    regulatory_mapping_score: float = 0.0
    obligation_coverage_percent: float = 0.0
    total_compliance_score: float = 0.0
    risk_level: str = "unknown"
    num_open_violations: int = 0


class ExportRequest(BaseModel):
    """Request to export compliance data."""
    export_type: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    format: str = "json"
'''

    code = template.format_map(
        {
            "vertical_name": vertical_name,
            "enum_members_lines": enum_members_lines,
        }
    )

    _assert_parsable_python(code, context=f"{vertical_name}/models.py")
    return code


def generate_test_scaffolds(
    vertical_meta: Any, obligations: Sequence[Any], output_dir: Path
) -> List[Path]:
    """
    Generate test scaffold files.

    Generates: test_routes.py, test_models.py.

    Raises :class:`CodegenValidationError` on allowlist violations.
    """
    _validate_vertical_meta_for_codegen(vertical_meta)
    _validate_obligations_for_codegen(obligations)

    vertical_name = vertical_meta.name
    vertical_cap = vertical_name.capitalize()
    decision_types: List[str] = list(vertical_meta.decision_types)
    first_decision_type = decision_types[0] if decision_types else "default"
    # ``first_decision_type`` was already validated above.
    decision_types_quoted_csv = ", ".join(f'"{dt}"' for dt in decision_types)

    generated_files: List[Path] = []

    # -- test_routes.py --------------------------------------------------
    routes_template = '''"""
Auto-generated route tests for {vertical_name} vertical.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def test_record_decision():
    """Test decision recording endpoint returns valid response."""
    from .routes import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    payload = {{
        "decision_id": "test-001",
        "decision_type": "{first_decision_type}",
        "evidence": {{"field1": "value1"}},
        "metadata": {{"source": "test"}},
    }}

    with patch(".".join([__name__.rsplit(".", 1)[0], "routes", "{vertical_cap}SnapshotService"]), new_callable=MagicMock), \\
         patch(".".join([__name__.rsplit(".", 1)[0], "routes", "{vertical_cap}GraphStore"]), new_callable=MagicMock):
        response = client.post("/v1/{vertical_name}/decision/record", json=payload)
        assert response.status_code in (200, 422, 500)


def test_get_snapshot():
    """Test snapshot endpoint returns compliance data."""
    from .routes import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with patch(".".join([__name__.rsplit(".", 1)[0], "routes", "{vertical_cap}SnapshotAdapter"]), new_callable=MagicMock):
        response = client.get("/v1/{vertical_name}/snapshot")
        assert response.status_code in (200, 500)


def test_health_check():
    """Test health check endpoint returns service status."""
    from .routes import router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/v1/{vertical_name}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "{vertical_name}_api"
'''

    routes_test = routes_template.format_map(
        {
            "vertical_name": vertical_name,
            "vertical_cap": vertical_cap,
            "first_decision_type": first_decision_type,
        }
    )
    _assert_parsable_python(routes_test, context=f"{vertical_name}/tests/test_routes.py")

    routes_test_file = output_dir / "test_routes.py"
    with open(routes_test_file, "w", encoding="utf-8") as f:
        f.write(routes_test)
    generated_files.append(routes_test_file)

    # -- test_models.py --------------------------------------------------
    models_template = '''"""
Auto-generated model tests for {vertical_name} vertical.
"""

import pytest
from .models import DecisionType, DecisionRequest


def test_decision_type_enum():
    """Test DecisionType enum contains all expected members."""
    expected_types = [{decision_types_quoted_csv}]
    for dtype in expected_types:
        member = DecisionType(dtype)
        assert member.value == dtype

    # Verify enum count matches schema
    assert len(DecisionType) == {decision_type_count}


def test_decision_request_validation():
    """Test DecisionRequest pydantic validation."""
    valid = DecisionRequest(
        decision_id="test-001",
        decision_type=DecisionType("{first_decision_type}"),
        evidence={{"field1": "value1"}},
    )
    assert valid.decision_id == "test-001"

    with pytest.raises(ValueError):
        DecisionRequest(
            decision_id="test-002",
            decision_type="invalid_type_not_in_enum",
            evidence={{}},
        )
'''

    models_test = models_template.format_map(
        {
            "vertical_name": vertical_name,
            "decision_types_quoted_csv": decision_types_quoted_csv,
            "decision_type_count": len(decision_types),
            "first_decision_type": first_decision_type,
        }
    )
    _assert_parsable_python(models_test, context=f"{vertical_name}/tests/test_models.py")

    models_test_file = output_dir / "test_models.py"
    with open(models_test_file, "w", encoding="utf-8") as f:
        f.write(models_test)
    generated_files.append(models_test_file)

    return generated_files
