"""Data-free FDA export coverage-gate and route-shape checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.authz import IngestionPrincipal  # noqa: E402
from app.fda_export.coverage import _enforce_kde_coverage_gate  # noqa: E402
from app.fda_export.router import _authorize_pii_access, router  # noqa: E402
from app.fda_export_service import _build_completeness_summary  # noqa: E402


def test_include_pii_without_permission_returns_403() -> None:
    with pytest.raises(HTTPException) as exc:
        _authorize_pii_access(
            include_pii=True,
            principal=IngestionPrincipal(key_id="", scopes=[]),
            identity={"user_id": "", "request_id": ""},
            tenant_id="",
            export_scope="",
        )
    assert exc.value.status_code == 403


def test_coverage_above_threshold_passes_silently() -> None:
    _enforce_kde_coverage_gate(
        completeness_summary=_build_completeness_summary([]),
        allow_incomplete=False,
        identity={},
        tenant_id="",
        export_scope="",
    )


def test_unchecked_empty_event_requires_acknowledgement() -> None:
    summary = _build_completeness_summary([{}])
    with pytest.raises(HTTPException) as exc:
        _enforce_kde_coverage_gate(
            completeness_summary=summary,
            allow_incomplete=False,
            identity={},
            tenant_id="",
            export_scope="",
        )
    assert exc.value.status_code == 409


def test_history_and_verification_routes_are_registered() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    assert "/api/v1/fda/export/history" in paths
    assert "/api/v1/fda/export/verify" in paths
    assert "/api/v1/fda/export/v2" in paths
    assert "/api/v1/fda/export/merkle-root" in paths
