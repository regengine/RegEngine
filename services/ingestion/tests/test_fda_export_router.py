"""API tests for hardened FDA export router."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import types
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import shared.cte_persistence as shared_cte_persistence
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.fda_export.router import router as fda_router
from app.fda_export_service import _generate_csv


class _FakeChainVerification:
    def __init__(self, valid: bool = True):
        self.valid = valid
        self.chain_length = 7
        self.errors: list[str] = []
        self.checked_at = "2026-03-10T10:00:00+00:00"


class _Result:
    def __init__(self, *, row: Any = None, rows: Optional[list[Any]] = None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeSession:
    def __init__(self, export_log_row: Any = None):
        self._export_log_row = export_log_row

    def execute(self, *_args, **_kwargs):
        return _Result(row=self._export_log_row)

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


class _FakePersistence:
    def __init__(self, _session):
        self._by_tlc = {
            "TLC-2026-001": [
                {
                    "id": "evt-1",
                    "event_type": "shipping",
                    "traceability_lot_code": "TLC-2026-001",
                    "product_description": "Romaine Hearts",
                    "quantity": 120.0,
                    "unit_of_measure": "cases",
                    "location_gln": "0614141000005",
                    "location_name": "Valley Fresh Farms",
                    "event_timestamp": "2026-03-10T09:00:00+00:00",
                    "sha256_hash": "a" * 64,
                    "chain_hash": "b" * 64,
                    "source": "webhook",
                    # Missing ship_to_location on purpose to exercise completeness warnings.
                    "kdes": {
                        "ship_date": "2026-03-10",
                        "ship_from_location": "Valley Fresh Farms",
                    },
                }
            ],
            "TLC-2026-002": [
                {
                    "id": "evt-2",
                    "event_type": "receiving",
                    "traceability_lot_code": "TLC-2026-002",
                    "product_description": "Baby Spinach",
                    "quantity": 80.0,
                    "unit_of_measure": "cases",
                    "location_gln": "0614141000006",
                    "location_name": "Metro Distribution Center",
                    "event_timestamp": "2026-03-10T10:00:00+00:00",
                    "sha256_hash": "c" * 64,
                    "chain_hash": "d" * 64,
                    "source": "webhook",
                    "kdes": {
                        "receive_date": "2026-03-10",
                        "receiving_location": "Metro Distribution Center",
                    },
                }
            ],
        }

    def query_events_by_tlc(
        self,
        tenant_id: str,
        tlc: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[dict]:
        _ = tenant_id, start_date, end_date
        return list(self._by_tlc.get(tlc, []))

    def query_all_events(
        self,
        tenant_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ):
        _ = tenant_id, start_date, end_date, event_type, limit, offset
        return (
            [
                {"traceability_lot_code": "TLC-2026-001"},
                {"traceability_lot_code": "TLC-2026-002"},
            ],
            2,
        )

    def verify_chain(self, tenant_id: str):
        _ = tenant_id
        return _FakeChainVerification(valid=True)

    def log_export(self, **_kwargs):
        return "export-log-id"


def _install_fake_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    session_factory,
    persistence_cls,
) -> None:
    fake_db_module = types.ModuleType("shared.database")
    fake_db_module.SessionLocal = session_factory
    monkeypatch.setitem(sys.modules, "shared.database", fake_db_module)
    monkeypatch.setattr(shared_cte_persistence, "CTEPersistence", persistence_cls)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from app.subscription_gate import require_active_subscription

    app = FastAPI()
    app.include_router(fda_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        auth_mode="test",
    )
    # #1182: the subscription gate is now fail-closed; override it in tests so
    # we don't need a Redis stand-in just to exercise export logic.
    app.dependency_overrides[require_active_subscription] = lambda: None

    _install_fake_dependencies(
        monkeypatch,
        session_factory=lambda: _FakeSession(),
        persistence_cls=_FakePersistence,
    )

    with TestClient(app) as test_client:
        yield test_client


def test_export_default_returns_verifiable_zip_package(client: TestClient) -> None:
    # The fixture event has KDE coverage ~67%, which trips the #1222
    # gate. Pass ``allow_incomplete=true`` to exercise the happy path.
    response = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-2026-001",
            "allow_incomplete": "true",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert response.headers["x-export-hash"]
    assert response.headers["x-package-hash"]
    assert response.headers["x-chain-integrity"] == "VERIFIED"

    with zipfile.ZipFile(io.BytesIO(response.content)) as package:
        names = set(package.namelist())
        assert "manifest.json" in names
        assert "README.txt" in names
        chain_file = next(name for name in names if name.startswith("chain_verification_"))
        csv_file = next(name for name in names if name.startswith("fda_spreadsheet_"))

        manifest = json.loads(package.read("manifest.json").decode("utf-8"))
        chain_payload = json.loads(package.read(chain_file).decode("utf-8"))
        manifest_hashes = {entry["name"]: entry["sha256"] for entry in manifest["files"]}

        assert manifest["export_type"] == "fda_traceability_package"
        assert manifest["summary"]["record_count"] == 1
        assert manifest["verification"]["chain_valid"] is True
        assert manifest["completeness"]["events_with_missing_required_fields"] == 1
        assert chain_payload["verification_status"] == "VERIFIED"
        assert chain_payload["content_hash"] == response.headers["x-export-hash"]
        assert chain_payload["record_count"] == 1

        csv_text = package.read(csv_file).decode("utf-8")
        assert "Traceability Lot Code (TLC)" in csv_text
        assert "TLC-2026-001" in csv_text
        for name, expected_digest in manifest_hashes.items():
            actual_digest = hashlib.sha256(package.read(name)).hexdigest()
            assert actual_digest == expected_digest


def test_export_csv_format_still_supported(client: TestClient) -> None:
    response = client.get(
        "/api/v1/fda/export",
        params={
            "tenant_id": "00000000-0000-0000-0000-000000000111",
            "tlc": "TLC-2026-001",
            "format": "csv",
            # Bypass the #1222 KDE coverage gate for this legacy test.
            "allow_incomplete": "true",
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "X-Package-Hash" not in response.headers
    assert response.headers["x-kde-coverage"] == "0.6667"
    assert "Traceability Lot Code (TLC)" in response.text


def test_verify_export_recomputes_hash_for_full_export(monkeypatch: pytest.MonkeyPatch) -> None:
    persistence = _FakePersistence(None)
    events = persistence.query_events_by_tlc("", "TLC-2026-001") + persistence.query_events_by_tlc("", "TLC-2026-002")
    original_hash = hashlib.sha256(_generate_csv(events).encode("utf-8")).hexdigest()
    export_log_row = (
        "fda_spreadsheet",
        None,  # query_tlc
        None,  # query_start_date
        None,  # query_end_date
        len(events),
        original_hash,
        datetime.now(timezone.utc),
    )

    from app.subscription_gate import require_active_subscription

    app = FastAPI()
    app.include_router(fda_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        auth_mode="test",
    )
    # #1182: bypass fail-closed subscription gate in tests.
    app.dependency_overrides[require_active_subscription] = lambda: None

    _install_fake_dependencies(
        monkeypatch,
        session_factory=lambda: _FakeSession(export_log_row=export_log_row),
        persistence_cls=_FakePersistence,
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/v1/fda/export/verify",
            params={
                "export_id": "00000000-0000-0000-0000-00000000fda1",
                "tenant_id": "00000000-0000-0000-0000-000000000111",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["hashes_match"] is True
    assert payload["data_integrity"] == "VERIFIED"
    assert payload["current_record_count"] == 2


def test_export_denied_without_fda_export_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(fda_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="limited-key",
        scopes=["fda.read"],
        auth_mode="test",
    )

    _install_fake_dependencies(
        monkeypatch,
        session_factory=lambda: _FakeSession(),
        persistence_cls=_FakePersistence,
    )

    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/v1/fda/export",
            params={
                "tenant_id": "00000000-0000-0000-0000-000000000111",
                "tlc": "TLC-2026-001",
            },
        )

    assert response.status_code == 403
    assert "requires 'fda.export'" in response.json()["detail"]


def test_export_denied_cross_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: a principal scoped to tenant A MUST NOT be able to
    export tenant B's traceability data by passing ``?tenant_id=B``.

    The cross-tenant check lives in ``require_permission`` (authz.py) and
    compares ``principal.tenant_id`` to the tenant context derived from
    the query/header. FDA export is the highest-value endpoint guarded by
    that check — a cross-tenant bypass here would let any authenticated
    customer pull another customer's full FSMA traceability graph, which
    is a P0 multi-tenant data-leak.

    The wildcard-scope carve-out (``"*" in principal.scopes``) intentionally
    does NOT apply to this test — we're asserting the default, non-sysadmin
    path. A sibling test elsewhere in the suite covers the wildcard case.
    """
    app = FastAPI()
    app.include_router(fda_router)

    # Principal scoped to tenant A with fda.export permission.
    tenant_a = "00000000-0000-0000-0000-00000000000a"
    tenant_b = "00000000-0000-0000-0000-00000000000b"
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="tenant-a-key",
        scopes=["fda.export"],  # valid scope, but no wildcard
        tenant_id=tenant_a,
        auth_mode="test",
    )

    # Bypass subscription gate (test-only; mirrors the ``client`` fixture).
    from app.subscription_gate import require_active_subscription
    app.dependency_overrides[require_active_subscription] = lambda: None

    _install_fake_dependencies(
        monkeypatch,
        session_factory=lambda: _FakeSession(),
        persistence_cls=_FakePersistence,
    )

    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/v1/fda/export",
            params={
                "tenant_id": tenant_b,  # <-- mismatch with principal.tenant_id
                "tlc": "TLC-2026-001",
            },
        )

    assert response.status_code == 403, (
        f"Cross-tenant FDA export must 403 but got {response.status_code}: {response.text}"
    )
    assert "Tenant mismatch" in response.json()["detail"]


def test_export_denied_cross_tenant_via_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sibling to test_export_denied_cross_tenant covering the ``X-Tenant-ID``
    header as the tenant-carrier instead of the query param.

    ``_requested_tenant_context`` in authz.py accepts either source; the
    cross-tenant check must fire on either. Without this test, a caller
    could circumvent the query-param check by switching to a header.
    """
    app = FastAPI()
    app.include_router(fda_router)

    tenant_a = "00000000-0000-0000-0000-00000000000a"
    tenant_b = "00000000-0000-0000-0000-00000000000b"
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="tenant-a-key",
        scopes=["fda.export"],
        tenant_id=tenant_a,
        auth_mode="test",
    )
    from app.subscription_gate import require_active_subscription
    app.dependency_overrides[require_active_subscription] = lambda: None

    _install_fake_dependencies(
        monkeypatch,
        session_factory=lambda: _FakeSession(),
        persistence_cls=_FakePersistence,
    )

    with TestClient(app) as test_client:
        response = test_client.get(
            "/api/v1/fda/export",
            params={
                # Query and header disagree — _requested_tenant_context
                # rejects the conflict before even reaching the tenant check.
                "tenant_id": tenant_a,
                "tlc": "TLC-2026-001",
            },
            headers={"X-Tenant-ID": tenant_b},
        )

    # Either 400 (conflicting tenant context) or 403 (tenant mismatch) is
    # acceptable — both refuse cross-tenant access. The important negative
    # is that the request MUST NOT produce a 200 with tenant B's data.
    assert response.status_code in (400, 403), (
        f"Conflicting tenant context must be rejected but got {response.status_code}: "
        f"{response.text}"
    )
