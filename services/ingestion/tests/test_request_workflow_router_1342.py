"""Coverage-sweep tests for ``app.request_workflow_router`` (#1342).

The existing ``tests/test_request_workflow_router.py`` mocks
``_get_service`` wholesale and skips several endpoints entirely
(``/collect``, ``/gap-analysis``, ``/amend``, ``/packages``), plus
the non-blocking-defect branch of ``/submit``. That leaves 21
statements uncovered (baseline 84%).

This file closes those gaps:
    48-51    — ``_get_service(None)`` and happy path
    231-234  — ``POST /{id}/collect``
    251-254  — ``POST /{id}/gap-analysis``
    335      — ``POST /{id}/submit`` when ValueError is NOT a blocking
               defect (re-raised, surfaces as 500)
    355-358  — ``POST /{id}/amend``
    377-380  — ``GET /{id}/packages``
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

import app.authz as authz  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app import request_workflow_router  # noqa: E402
from app.request_workflow_router import _get_service  # noqa: E402


TENANT = "tenant-rw-1342"


def _make_principal() -> IngestionPrincipal:
    return IngestionPrincipal(
        key_id="test-key",
        tenant_id=TENANT,
        scopes=["requests.read", "requests.write"],
        auth_mode="test",
    )


@pytest.fixture(autouse=True)
def _patch_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))


@pytest.fixture(autouse=True)
def _restore_get_service():
    original = request_workflow_router._get_service
    yield
    request_workflow_router._get_service = original


def _build_client(mock_svc: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(request_workflow_router.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: _make_principal()
    app.dependency_overrides[request_workflow_router._get_db_session] = lambda: MagicMock()
    request_workflow_router._get_service = lambda _db: mock_svc  # type: ignore[assignment]
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Lines 48-51: _get_service direct tests
# --------------------------------------------------------------------------- #


class TestGetService:
    def test_raises_503_when_db_none(self) -> None:
        # Line 49: db_session=None -> 503.
        with pytest.raises(HTTPException) as exc:
            _get_service(None)
        assert exc.value.status_code == 503
        assert exc.value.detail == "Database unavailable"

    def test_constructs_request_workflow_when_db_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Lines 50-51: lazy import + wrap.
        captured: dict[str, object] = {}

        class _FakeRequestWorkflow:
            def __init__(self, db_session: object) -> None:
                captured["db_session"] = db_session

        fake_module = types.ModuleType("shared.request_workflow")
        fake_module.RequestWorkflow = _FakeRequestWorkflow  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "shared.request_workflow", fake_module)

        session = MagicMock()
        svc = _get_service(session)
        assert isinstance(svc, _FakeRequestWorkflow)
        assert captured["db_session"] is session


# --------------------------------------------------------------------------- #
# Lines 231-234: POST /{id}/collect
# --------------------------------------------------------------------------- #


class TestCollectRecords:
    def test_returns_records_collected_count(self) -> None:
        mock_svc = MagicMock()
        mock_svc.collect_records.return_value = [{"record_id": f"r-{i}"} for i in range(5)]
        client = _build_client(mock_svc)

        response = client.post("/api/v1/requests/rc-42/collect")
        assert response.status_code == 200
        payload = response.json()
        assert payload["request_case_id"] == "rc-42"
        assert payload["records_collected"] == 5
        assert payload["status"] == "collecting"
        mock_svc.collect_records.assert_called_once_with(TENANT, "rc-42")


# --------------------------------------------------------------------------- #
# Lines 251-254: POST /{id}/gap-analysis
# --------------------------------------------------------------------------- #


class TestRunGapAnalysis:
    def test_returns_gap_analysis_from_service(self) -> None:
        gap_result = {
            "missing_kdes": ["ship_date"],
            "coverage_percentage": 87.5,
        }
        mock_svc = MagicMock()
        mock_svc.run_gap_analysis.return_value = gap_result
        client = _build_client(mock_svc)

        response = client.post("/api/v1/requests/rc-gap/gap-analysis")
        assert response.status_code == 200
        payload = response.json()
        assert payload["request_case_id"] == "rc-gap"
        assert payload["gap_analysis"] == gap_result
        assert payload["status"] == "gap_analysis"
        mock_svc.run_gap_analysis.assert_called_once_with(TENANT, "rc-gap")


# --------------------------------------------------------------------------- #
# Line 335: POST /{id}/submit — non-blocking ValueError re-raises
# --------------------------------------------------------------------------- #


class TestSubmitNonBlockingValueError:
    def test_value_error_without_blocking_defect_reraises(self) -> None:
        # Line 335: raise (unhandled ValueError). FastAPI surfaces
        # unhandled ValueError as 500.
        mock_svc = MagicMock()
        mock_svc.submit_package.side_effect = ValueError(
            "something else entirely went wrong"
        )
        client = _build_client(mock_svc)

        with pytest.raises(ValueError, match="something else entirely"):
            client.post(
                "/api/v1/requests/rc-boom/submit",
                json={
                    "submitted_by": "auditor@acme.test",
                    "submission_method": "export",
                },
            )

    def test_value_error_with_blocking_defect_returns_422(self) -> None:
        # Sibling branch (line 333-334) — already covered by existing
        # tests, but pinning it here alongside the 335 test makes the
        # intent obvious when reviewing the diff.
        mock_svc = MagicMock()
        mock_svc.submit_package.side_effect = ValueError(
            "cannot submit: blocking defect present on rc-blk"
        )
        client = _build_client(mock_svc)

        response = client.post(
            "/api/v1/requests/rc-blk/submit",
            json={
                "submitted_by": "auditor@acme.test",
                "submission_method": "export",
            },
        )
        assert response.status_code == 422
        assert "blocking defect" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Lines 355-358: POST /{id}/amend
# --------------------------------------------------------------------------- #


class TestCreateAmendment:
    def test_returns_package_metadata_from_service(self) -> None:
        mock_svc = MagicMock()
        mock_svc.create_amendment.return_value = {
            "package_id": "pkg-99",
            "version_number": 2,
            "diff_from_previous": {"added": ["lot-X"], "removed": []},
        }
        client = _build_client(mock_svc)

        response = client.post(
            "/api/v1/requests/rc-am/amend",
            json={"generated_by": "compliance@acme.test",
                  "amendment_reason": "scope expansion"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["request_case_id"] == "rc-am"
        assert payload["package_id"] == "pkg-99"
        assert payload["version_number"] == 2
        assert payload["diff_from_previous"]["added"] == ["lot-X"]
        assert payload["status"] == "amended"
        mock_svc.create_amendment.assert_called_once_with(
            TENANT, "rc-am", "compliance@acme.test"
        )


# --------------------------------------------------------------------------- #
# Lines 377-380: GET /{id}/packages
# --------------------------------------------------------------------------- #


class TestPackageHistory:
    def test_returns_packages_list(self) -> None:
        mock_svc = MagicMock()
        mock_svc.get_package_history.return_value = [
            {"package_id": "pkg-1", "version_number": 1},
            {"package_id": "pkg-2", "version_number": 2},
            {"package_id": "pkg-3", "version_number": 3},
        ]
        client = _build_client(mock_svc)

        response = client.get("/api/v1/requests/rc-hist/packages")
        assert response.status_code == 200
        payload = response.json()
        assert payload["request_case_id"] == "rc-hist"
        assert payload["total"] == 3
        assert [p["version_number"] for p in payload["packages"]] == [1, 2, 3]
        mock_svc.get_package_history.assert_called_once_with(TENANT, "rc-hist")

    def test_empty_history_returns_empty_list(self) -> None:
        mock_svc = MagicMock()
        mock_svc.get_package_history.return_value = []
        client = _build_client(mock_svc)

        response = client.get("/api/v1/requests/rc-empty/packages")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 0
        assert payload["packages"] == []
