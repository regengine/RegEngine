"""Deep QA coverage for services/admin/app/bulk_upload/.

Covers real behavior gaps found during the QA pass:

* ``parsers._classify_row`` had an unreachable TLC fallback: any row without
  an explicit ``record_type`` that carried a ``tlc_code`` (but no
  ``cte_type``) was classified as an *event*, so valid TLC data in
  record-type-less CSV/JSON uploads was rejected as a bad ``cte_type``.
* ``transaction_manager.execute_bulk_commit`` crashed with a raw DB
  ``IntegrityError`` on duplicate TLC codes or duplicate FTL scopes inside
  one upload (unique constraints are per tenant / per facility).
* ``execute_bulk_commit`` only rolled back on ``SQLAlchemyError``; a
  ``ValueError`` mid-commit (unknown facility, bad category) left flushed
  rows visible in the session.
* An upload with zero rows validated cleanly and committed as a silent
  no-op "success".
* Tenant/user session isolation and parse guards had no direct tests.
"""

from __future__ import annotations

import asyncio
import io
from uuid import UUID

import pytest
from app.bulk_upload.parsers import parse_incoming_file
from app.bulk_upload.session_store import BulkUploadSessionStore
from app.bulk_upload.templates import generate_template
from app.bulk_upload.transaction_manager import (
    build_validation_preview,
    execute_bulk_commit,
)
from app.bulk_upload.validators import validate_and_normalize_payload
from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierTraceabilityLotModel,
    TenantModel,
    UserModel,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import UploadFile

TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_TENANT_B_ID = UUID("00000000-0000-0000-0000-000000000009")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")
TEST_USER_2_ID = UUID("00000000-0000-0000-0000-000000000003")

SUPPORTED_CTE_TYPES = {
    "shipping",
    "receiving",
    "transforming",
    "harvesting",
    "cooling",
    "initial_packing",
    "first_receiver",
}
VALID_FTL_CATEGORIES = {"1", "2"}


def _make_upload_file(filename: str, content: bytes) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers={"content-type": "application/octet-stream"},
    )


def _parse(filename: str, content: bytes) -> dict:
    return asyncio.new_event_loop().run_until_complete(
        parse_incoming_file(_make_upload_file(filename, content))
    )


def _validate(parsed: dict):
    return validate_and_normalize_payload(
        parsed,
        supported_cte_types=set(SUPPORTED_CTE_TYPES),
        valid_ftl_category_ids=set(VALID_FTL_CATEGORIES),
    )


# ---------------------------------------------------------------------------
# Parser classification
# ---------------------------------------------------------------------------


class TestRecordTypelessClassification:
    def test_tlc_rows_without_record_type_classify_as_tlcs(self):
        """TLC data in a record-type-less CSV must land in ``tlcs``.

        Before the fix the second ``if row.get("tlc_code")`` branch in
        ``_classify_row`` was unreachable, so these rows became events with
        an empty ``cte_type`` and validation rejected the whole upload.
        """
        parsed = _parse(
            "supplier.csv",
            b"facility_name,tlc_code,product_description,status\n"
            b"Acme Packing,TLC-001,Spinach,active\n"
            b"Acme Packing,TLC-002,Kale,active\n",
        )
        assert len(parsed["tlcs"]) == 2
        assert parsed["events"] == []
        # Scaffolded facility keeps the commit path viable.
        assert len(parsed["facilities"]) == 1

        normalized, errors = _validate(parsed)
        assert len(normalized["tlcs"]) == 2
        assert not [e for e in errors if e.get("severity") != "warning"]

    def test_bare_json_object_tlc_classifies_as_tlc(self):
        parsed = _parse(
            "supplier.json",
            b'{"tlc_code": "TLC-9", "facility_name": "Acme Packing"}',
        )
        assert len(parsed["tlcs"]) == 1
        assert parsed["events"] == []

    def test_row_with_event_signals_but_no_cte_type_stays_an_event(self):
        """An event row missing ``cte_type`` must fail loudly, not mint a lot.

        Rows carrying ``event_time``/``kde_data`` stay events so validation
        reports the missing ``cte_type`` as a blocking error.
        """
        parsed = _parse(
            "supplier.csv",
            b"facility_name,tlc_code,cte_type,event_time\n"
            b"Acme Packing,TLC-001,,2026-03-03T12:00:00Z\n",
        )
        assert len(parsed["events"]) == 1
        assert parsed["tlcs"] == []

        _normalized, errors = _validate(parsed)
        assert any(
            e.get("severity") == "error" and "cte_type" in e["message"]
            for e in errors
        )


# ---------------------------------------------------------------------------
# Parse guards and templates
# ---------------------------------------------------------------------------


class TestParseGuards:
    def test_unsupported_extension_rejected(self):
        import asyncio

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                parse_incoming_file(_make_upload_file("supplier.exe", b"data"))
            )
        assert exc_info.value.status_code == 400

    def test_empty_file_rejected(self):
        import asyncio

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            asyncio.new_event_loop().run_until_complete(
                parse_incoming_file(_make_upload_file("supplier.csv", b""))
            )
        assert exc_info.value.status_code == 400

    def test_csv_template_round_trip(self):
        payload, media_type, filename = generate_template("csv")
        assert media_type == "text/csv"
        assert filename.endswith(".csv")
        parsed = _parse("supplier.csv", payload)
        assert len(parsed["facilities"]) == 1
        assert len(parsed["ftl_scopes"]) == 1
        assert len(parsed["tlcs"]) == 1
        assert len(parsed["events"]) == 1

    def test_xlsx_template_round_trip(self):
        pytest.importorskip("openpyxl")
        payload, media_type, filename = generate_template("xlsx")
        assert filename.endswith(".xlsx")
        assert "spreadsheet" in media_type
        parsed = _parse("supplier.xlsx", payload)
        assert len(parsed["facilities"]) == 1
        assert len(parsed["ftl_scopes"]) == 1
        assert len(parsed["tlcs"]) == 1
        assert len(parsed["events"]) == 1

    def test_bad_template_format_rejected(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            generate_template("pdf")
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# Commit-level fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    tables = [
        TenantModel.__table__,
        UserModel.__table__,
        SupplierFacilityModel.__table__,
        SupplierFacilityFTLCategoryModel.__table__,
        SupplierTraceabilityLotModel.__table__,
        SupplierCTEEventModel.__table__,
    ]
    for table in tables:
        table.create(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS graph_outbox (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       TEXT NULL,
                operation       TEXT NOT NULL,
                cypher          TEXT NOT NULL,
                params          TEXT NOT NULL DEFAULT '{}',
                status          TEXT NOT NULL DEFAULT 'pending',
                attempts        INTEGER NOT NULL DEFAULT 0,
                max_attempts    INTEGER NOT NULL DEFAULT 10,
                last_error      TEXT NULL,
                enqueued_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                drained_at      TEXT NULL,
                next_attempt_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                dedupe_key      TEXT NULL
            )
            """
            )
        )
    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )
    session = session_local()
    session.add(
        TenantModel(
            id=TEST_TENANT_ID,
            name="Test Tenant",
            slug="test-tenant",
            status="active",
            settings={},
        )
    )
    session.add(
        UserModel(
            id=TEST_USER_ID,
            email="supplier@example.com",
            status="active",
            is_sysadmin=False,
        )
    )
    session.add(
        UserModel(
            id=TEST_USER_2_ID,
            email="second@example.com",
            status="active",
            is_sysadmin=False,
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        for table in reversed(tables):
            table.drop(bind=engine)
        engine.dispose()


@pytest.fixture
def no_graph(monkeypatch: pytest.MonkeyPatch):
    import app.bulk_upload.transaction_manager as tx_manager

    monkeypatch.setattr(
        tx_manager.supplier_graph_sync, "record_facility_ftl_scoping", lambda **_kw: None
    )
    monkeypatch.setattr(
        tx_manager.supplier_graph_sync, "record_cte_event", lambda **_kw: None
    )


def _facility_row(name: str = "Acme Packing") -> dict:
    return {
        "name": name,
        "street": "1 Main St",
        "city": "Salinas",
        "state": "CA",
        "postal_code": "93901",
        "fda_registration_number": None,
        "roles": ["Packer"],
    }


# ---------------------------------------------------------------------------
# Duplicate rows inside one upload
# ---------------------------------------------------------------------------


class TestIntraUploadDuplicates:
    def test_duplicate_tlc_codes_fold_into_one_lot(
        self, db_session: Session, no_graph
    ):
        """Two rows with the same TLC code must not raise IntegrityError."""
        user = db_session.get(UserModel, TEST_USER_ID)
        summary = execute_bulk_commit(
            db_session,
            tenant_id=TEST_TENANT_ID,
            current_user=user,
            normalized_payload={
                "facilities": [_facility_row()],
                "ftl_scopes": [
                    {"facility_name": "Acme Packing", "category_id": "2"}
                ],
                "tlcs": [
                    {
                        "tlc_code": "TLC-DUP",
                        "facility_name": "Acme Packing",
                        "product_description": "Spinach",
                        "status": "active",
                    },
                    {
                        "tlc_code": "TLC-DUP",
                        "facility_name": "Acme Packing",
                        "product_description": "Spinach v2",
                        "status": "active",
                    },
                ],
                "events": [],
            },
        )
        assert summary["tlcs_created"] == 1
        assert summary["tlcs_updated"] == 1
        lots = db_session.execute(select(SupplierTraceabilityLotModel)).scalars().all()
        assert len(lots) == 1
        assert lots[0].product_description == "Spinach v2"

    def test_duplicate_scopes_upsert_once(self, db_session: Session, no_graph):
        user = db_session.get(UserModel, TEST_USER_ID)
        summary = execute_bulk_commit(
            db_session,
            tenant_id=TEST_TENANT_ID,
            current_user=user,
            normalized_payload={
                "facilities": [_facility_row()],
                "ftl_scopes": [
                    {"facility_name": "Acme Packing", "category_id": "2"},
                    {"facility_name": "Acme Packing", "category_id": "2"},
                ],
                "tlcs": [],
                "events": [],
            },
        )
        assert summary["ftl_scopes_upserted"] == 1
        scopes = db_session.execute(
            select(SupplierFacilityFTLCategoryModel)
        ).scalars().all()
        assert len(scopes) == 1

    def test_preview_counts_duplicate_tlc_as_create_plus_update(
        self, db_session: Session
    ):
        preview = build_validation_preview(
            db_session,
            tenant_id=TEST_TENANT_ID,
            supplier_user_id=TEST_USER_ID,
            normalized_payload={
                "facilities": [_facility_row()],
                "ftl_scopes": [],
                "tlcs": [
                    {
                        "tlc_code": "TLC-DUP",
                        "facility_name": "Acme Packing",
                        "product_description": "Spinach",
                        "status": "active",
                    },
                    {
                        "tlc_code": "TLC-DUP",
                        "facility_name": "Acme Packing",
                        "product_description": "Spinach v2",
                        "status": "active",
                    },
                ],
                "events": [],
            },
            validation_errors=[],
        )
        assert preview["tlcs_to_create"] == 1
        assert preview["tlcs_to_update"] == 1
        assert preview["can_commit"] is True


# ---------------------------------------------------------------------------
# Failed commits must roll back
# ---------------------------------------------------------------------------


class TestFailedCommitRollback:
    def test_value_error_mid_commit_leaves_no_phantom_rows(
        self, db_session: Session, no_graph
    ):
        """A ValueError after facility flush must roll back, not linger.

        Before the fix only ``SQLAlchemyError`` triggered ``db.rollback()``,
        so the flushed facility row stayed visible in the session after the
        failed commit.
        """
        user = db_session.get(UserModel, TEST_USER_ID)
        with pytest.raises(ValueError, match="Unknown facility_name"):
            execute_bulk_commit(
                db_session,
                tenant_id=TEST_TENANT_ID,
                current_user=user,
                normalized_payload={
                    "facilities": [_facility_row()],
                    "ftl_scopes": [],
                    "tlcs": [
                        {
                            "tlc_code": "TLC-X",
                            "facility_name": "Ghost Warehouse",
                            "product_description": None,
                            "status": "active",
                        }
                    ],
                    "events": [],
                },
            )
        assert db_session.execute(select(SupplierFacilityModel)).scalars().all() == []
        assert (
            db_session.execute(select(SupplierTraceabilityLotModel)).scalars().all()
            == []
        )


# ---------------------------------------------------------------------------
# Empty uploads must not "succeed"
# ---------------------------------------------------------------------------


class TestEmptyUploadBlocked:
    def test_empty_payload_preview_blocks_commit(self, db_session: Session):
        preview = build_validation_preview(
            db_session,
            tenant_id=TEST_TENANT_ID,
            supplier_user_id=TEST_USER_ID,
            normalized_payload={
                "facilities": [],
                "ftl_scopes": [],
                "tlcs": [],
                "events": [],
            },
            validation_errors=[],
        )
        assert preview["can_commit"] is False
        assert any(
            e.get("severity") == "error" and "no rows" in e["message"].lower()
            for e in preview["errors"]
        )


# ---------------------------------------------------------------------------
# Tenant and user session boundaries (route level)
# ---------------------------------------------------------------------------


def _route_client(db_session, monkeypatch, *, user_id, tenant_id, store):
    import app.bulk_upload.routes as bulk_routes

    test_app = FastAPI()
    test_app.include_router(bulk_routes.router, prefix="/v1/supplier/bulk-upload")
    current_user = db_session.get(UserModel, user_id)
    assert current_user is not None

    def override_get_session():
        yield db_session

    def override_get_current_user():
        return current_user

    test_app.dependency_overrides[bulk_routes.get_session] = override_get_session
    test_app.dependency_overrides[
        bulk_routes.get_current_user
    ] = override_get_current_user
    monkeypatch.setattr(
        bulk_routes.TenantContext, "get_tenant_context", lambda _db: tenant_id
    )
    monkeypatch.setattr(bulk_routes, "session_store", store)
    return TestClient(test_app)


class TestSessionIsolation:
    def test_session_invisible_across_tenants_and_users(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ):
        store = BulkUploadSessionStore()
        store._redis_available = False  # type: ignore[attr-defined]
        loop = asyncio.new_event_loop()
        session_id = loop.run_until_complete(
            store.create_session(
                str(TEST_TENANT_ID),
                str(TEST_USER_ID),
                {"status": "parsed", "parsed_data": {}},
            )
        )
        loop.close()

        owner = _route_client(
            db_session,
            monkeypatch,
            user_id=TEST_USER_ID,
            tenant_id=TEST_TENANT_ID,
            store=store,
        )
        with owner as client:
            assert (
                client.get(f"/v1/supplier/bulk-upload/status/{session_id}").status_code
                == 200
            )

        other_tenant = _route_client(
            db_session,
            monkeypatch,
            user_id=TEST_USER_ID,
            tenant_id=TEST_TENANT_B_ID,
            store=store,
        )
        with other_tenant as client:
            assert (
                client.get(f"/v1/supplier/bulk-upload/status/{session_id}").status_code
                == 404
            )

        other_user = _route_client(
            db_session,
            monkeypatch,
            user_id=TEST_USER_2_ID,
            tenant_id=TEST_TENANT_ID,
            store=store,
        )
        with other_user as client:
            assert (
                client.get(f"/v1/supplier/bulk-upload/status/{session_id}").status_code
                == 404
            )
