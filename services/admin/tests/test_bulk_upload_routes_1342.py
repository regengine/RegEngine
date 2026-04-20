"""
Regression coverage for ``app/bulk_upload/routes.py`` — closes the 89% gap.

Missing branches targeted:
* Line 111  — _coerce_commit_summary else branch (non-dict input)
* Line 117  — _coerce_validation_preview else branch (non-dict input)
* Line 123  — _tenant_and_user: no tenant → 400
* Line 178  — validate: session not found → 404
* Line 226  — commit: fast idempotency session not found → 404
* Line 257  — commit CAS fail + refreshed None → 404
* Line 262  — commit CAS fail + refreshed completed → 200 (race path)
* Lines 284-289 — execute_bulk_commit raises → 400, session set to failed
* Line 313  — status: session not found → 404
* Lines 334-336 — GET /template happy path

Tracks GitHub issue #1342.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bulk_upload.routes import (
    BulkUploadCommitSummary,
    _coerce_commit_summary,
    _coerce_validation_preview,
    router,
)
from app.sqlalchemy_models import (
    SupplierCTEEventModel,
    SupplierFacilityFTLCategoryModel,
    SupplierFacilityModel,
    SupplierTraceabilityLotModel,
    TenantModel,
    UserModel,
)

TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _SessionStore:
    """In-memory session store for route tests."""

    def __init__(self):
        self._store: dict[str, dict] = {}
        self._counter = 0

    async def create_session(self, tenant_id, user_id, payload):
        self._counter += 1
        sid = f"session-{self._counter:08d}"
        self._store[f"{tenant_id}:{user_id}:{sid}"] = payload
        return sid

    async def get_session(self, tenant_id, user_id, session_id):
        return self._store.get(f"{tenant_id}:{user_id}:{session_id}")

    async def update_session(self, tenant_id, user_id, session_id, payload):
        self._store[f"{tenant_id}:{user_id}:{session_id}"] = payload

    async def try_claim_commit(self, tenant_id, user_id, session_id, *,
                               from_status="validated", to_status="processing",
                               mutations=None):
        key = f"{tenant_id}:{user_id}:{session_id}"
        payload = self._store.get(key)
        if payload is None or payload.get("status") != from_status:
            return None
        payload["status"] = to_status
        if mutations:
            payload.update(mutations)
        self._store[key] = payload
        return payload


# ---------------------------------------------------------------------------
# DB fixture
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
    for t in tables:
        t.create(bind=engine)
    SM = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                      expire_on_commit=False, future=True)
    session = SM()
    session.add(TenantModel(id=TEST_TENANT_ID, name="T", slug="t", status="active", settings={}))
    session.add(UserModel(id=TEST_USER_ID, email="u@example.com",
                          password_hash="x", status="active", is_sysadmin=False))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        for t in reversed(tables):
            t.drop(bind=engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------


def _make_client(db_session, monkeypatch, *, tenant=TEST_TENANT_ID,
                 store=None):
    import app.bulk_upload.routes as bulk_routes

    app = FastAPI()
    app.include_router(router, prefix="/v1/supplier/bulk-upload")

    current_user = db_session.get(UserModel, TEST_USER_ID)

    def _get_session():
        yield db_session

    def _get_user():
        return current_user

    app.dependency_overrides[bulk_routes.get_session] = _get_session
    app.dependency_overrides[bulk_routes.get_current_user] = _get_user

    monkeypatch.setattr(bulk_routes.TenantContext, "get_tenant_context",
                        lambda _db: tenant)
    if store is not None:
        monkeypatch.setattr(bulk_routes, "session_store", store)

    return TestClient(app)


@pytest.fixture
def store():
    return _SessionStore()


@pytest.fixture
def client(db_session, monkeypatch, store):
    with _make_client(db_session, monkeypatch, store=store) as c:
        yield c


@pytest.fixture
def client_no_tenant(db_session, monkeypatch):
    with _make_client(db_session, monkeypatch, tenant=None) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper function unit tests — lines 111, 117
# ---------------------------------------------------------------------------


class TestCoerceHelpers:

    def test_coerce_commit_summary_non_dict_returns_default(self):
        """Line 111: non-dict value → empty BulkUploadCommitSummary."""
        result = _coerce_commit_summary(None)
        assert isinstance(result, BulkUploadCommitSummary)
        assert result.events_chained == 0

    def test_coerce_commit_summary_string_returns_default(self):
        """Line 111: string value is not a dict → default summary."""
        result = _coerce_commit_summary("not-a-dict")
        assert isinstance(result, BulkUploadCommitSummary)

    def test_coerce_validation_preview_non_dict_returns_none(self):
        """Line 117: non-dict value → None."""
        from app.bulk_upload.routes import _coerce_validation_preview
        assert _coerce_validation_preview(None) is None
        assert _coerce_validation_preview("oops") is None
        assert _coerce_validation_preview(42) is None


# ---------------------------------------------------------------------------
# _tenant_and_user — line 123
# ---------------------------------------------------------------------------


class TestTenantAndUserGuard:

    def test_parse_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 123: any endpoint that calls _tenant_and_user raises 400 on missing tenant."""
        resp = client_no_tenant.post(
            "/v1/supplier/bulk-upload/parse",
            files={"file": ("test.csv", b"record_type\nfacility", "text/csv")},
        )
        assert resp.status_code == 400
        assert "Tenant context required" in resp.json()["detail"]

    def test_validate_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 123: validate also uses _tenant_and_user."""
        resp = client_no_tenant.post(
            "/v1/supplier/bulk-upload/validate?session_id=session-00000001"
        )
        assert resp.status_code == 400

    def test_commit_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 123: commit also uses _tenant_and_user."""
        resp = client_no_tenant.post(
            "/v1/supplier/bulk-upload/commit?session_id=session-00000001"
        )
        assert resp.status_code == 400

    def test_status_no_tenant_returns_400(self, client_no_tenant: TestClient):
        """Line 123: status also uses _tenant_and_user."""
        resp = client_no_tenant.get("/v1/supplier/bulk-upload/status/session-00000001")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# validate: session not found — line 178
# ---------------------------------------------------------------------------


class TestValidateSessionNotFound:

    def test_missing_session_returns_404(self, client: TestClient):
        """Line 178: session_id not in store → 404."""
        resp = client.post(
            "/v1/supplier/bulk-upload/validate?session_id=session-99999999"
        )
        assert resp.status_code == 404
        assert "Session expired or not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# commit: fast idempotency not found — line 226
# ---------------------------------------------------------------------------


class TestCommitSessionNotFound:

    def test_missing_session_returns_404(self, client: TestClient):
        """Line 226: get_session returns None → 404 on fast idempotency check."""
        resp = client.post(
            "/v1/supplier/bulk-upload/commit?session_id=session-99999999"
        )
        assert resp.status_code == 404
        assert "Session expired or not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# commit CAS race paths — lines 257, 262
# ---------------------------------------------------------------------------


class TestCommitCASRace:

    def test_cas_fail_and_refreshed_none_returns_404(
        self, db_session, monkeypatch, store
    ):
        """Line 257: CAS returns None AND re-read also returns None → 404.

        This simulates: session was found on first read (status=parsed),
        CAS fails (wrong status), and then the session disappears (TTL'd out)
        before the re-read.
        """
        import app.bulk_upload.routes as bulk_routes

        # Prime store with a parsed (not validated) session
        import asyncio
        loop = asyncio.new_event_loop()
        tenant_key = str(TEST_TENANT_ID)
        user_key = str(TEST_USER_ID)
        sid = loop.run_until_complete(
            store.create_session(tenant_key, user_key, {"status": "parsed"})
        )
        loop.close()

        app = FastAPI()
        app.include_router(router, prefix="/v1/supplier/bulk-upload")
        current_user = db_session.get(UserModel, TEST_USER_ID)

        def _get_session():
            yield db_session

        def _get_user():
            return current_user

        app.dependency_overrides[bulk_routes.get_session] = _get_session
        app.dependency_overrides[bulk_routes.get_current_user] = _get_user
        monkeypatch.setattr(bulk_routes.TenantContext, "get_tenant_context",
                            lambda _db: TEST_TENANT_ID)

        # try_claim_commit returns None (status != validated),
        # then get_session also returns None (simulate expiry)
        vanishing_store = _SessionStore()

        async def _cas_none(*_a, **_kw):
            return None

        async def _get_none(*_a, **_kw):
            # First call (fast idempotency) returns parsed session;
            # second call (re-read after CAS fail) returns None.
            return None

        call_count = [0]

        async def _get_session_side_effect(tenant_id, user_id, session_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"status": "parsed"}
            return None

        vanishing_store.get_session = _get_session_side_effect
        vanishing_store.try_claim_commit = _cas_none
        monkeypatch.setattr(bulk_routes, "session_store", vanishing_store)

        with TestClient(app) as c:
            resp = c.post(f"/v1/supplier/bulk-upload/commit?session_id={sid}")

        assert resp.status_code == 404

    def _race_client(self, db_session, monkeypatch, first_status, second_status,
                     summary=None):
        """Helper: builds a TestClient where first get returns first_status,
        CAS fails, re-read returns second_status."""
        import app.bulk_upload.routes as bulk_routes

        call_count = [0]

        async def _get_side_effect(tenant_id, user_id, session_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"status": first_status}
            payload = {"status": second_status}
            if summary:
                payload["commit_summary"] = summary
            return payload

        async def _cas_none(*_a, **_kw):
            return None

        race_store = _SessionStore()
        race_store.get_session = _get_side_effect
        race_store.try_claim_commit = _cas_none

        app = FastAPI()
        app.include_router(router, prefix="/v1/supplier/bulk-upload")
        current_user = db_session.get(UserModel, TEST_USER_ID)

        app.dependency_overrides[bulk_routes.get_session] = lambda: (yield db_session)
        app.dependency_overrides[bulk_routes.get_current_user] = lambda: current_user
        monkeypatch.setattr(bulk_routes.TenantContext, "get_tenant_context",
                            lambda _db: TEST_TENANT_ID)
        monkeypatch.setattr(bulk_routes, "session_store", race_store)
        return TestClient(app)

    def test_cas_fail_refreshed_processing_returns_409(self, db_session, monkeypatch):
        """Line 267-271: CAS fails, re-read shows processing → 409."""
        c = self._race_client(db_session, monkeypatch, "validated", "processing")
        with c:
            resp = c.post("/v1/supplier/bulk-upload/commit?session_id=session-00000001")
        assert resp.status_code == 409
        assert "in progress" in resp.json()["detail"]

    def test_cas_fail_refreshed_not_validated_returns_400(self, db_session, monkeypatch):
        """Lines 272-275: CAS fails, re-read shows parsed (not validated) → 400."""
        c = self._race_client(db_session, monkeypatch, "validated", "parsed")
        with c:
            resp = c.post("/v1/supplier/bulk-upload/commit?session_id=session-00000001")
        assert resp.status_code == 400
        assert "must be validated" in resp.json()["detail"]

    def test_cas_fail_and_refreshed_completed_returns_200(
        self, db_session, monkeypatch
    ):
        """Line 262: CAS returns None but re-read shows completed → return summary.

        Simulates a race where a concurrent commit finished between the
        initial idempotency check and the CAS attempt.
        """
        import app.bulk_upload.routes as bulk_routes

        summary_payload = {
            "events_chained": 3, "facilities_created": 1,
            "facilities_updated": 0, "ftl_scopes_upserted": 0,
            "tlcs_created": 1, "tlcs_updated": 0, "last_merkle_hash": "abc",
            "sync_warning_count": 0, "sync_warnings": [],
        }

        call_count = [0]

        async def _get_side_effect(tenant_id, user_id, session_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"status": "validated"}
            return {"status": "completed", "commit_summary": summary_payload}

        async def _cas_none(*_a, **_kw):
            return None

        race_store = _SessionStore()
        race_store.get_session = _get_side_effect
        race_store.try_claim_commit = _cas_none

        app = FastAPI()
        app.include_router(router, prefix="/v1/supplier/bulk-upload")
        current_user = db_session.get(UserModel, TEST_USER_ID)

        def _get_session():
            yield db_session

        def _get_user():
            return current_user

        app.dependency_overrides[bulk_routes.get_session] = _get_session
        app.dependency_overrides[bulk_routes.get_current_user] = _get_user
        monkeypatch.setattr(bulk_routes.TenantContext, "get_tenant_context",
                            lambda _db: TEST_TENANT_ID)
        monkeypatch.setattr(bulk_routes, "session_store", race_store)

        with TestClient(app) as c:
            resp = c.post("/v1/supplier/bulk-upload/commit?session_id=session-00000001")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["summary"]["events_chained"] == 3


# ---------------------------------------------------------------------------
# commit exception handler — lines 284-289
# ---------------------------------------------------------------------------


class TestCommitExceptionHandler:

    def test_execute_bulk_commit_raises_sets_failed_status(
        self, db_session, monkeypatch, store
    ):
        """Lines 284-289: if execute_bulk_commit raises, session set to 'failed'
        and HTTP 400 returned. The exception message is surfaced in the detail."""
        import asyncio
        import app.bulk_upload.routes as bulk_routes

        tenant_key = str(TEST_TENANT_ID)
        user_key = str(TEST_USER_ID)

        loop = asyncio.new_event_loop()
        validated_payload = {
            "status": "validated",
            "normalized_data": {},
            "error": None,
        }
        sid = loop.run_until_complete(
            store.create_session(tenant_key, user_key, validated_payload)
        )
        loop.close()

        app = FastAPI()
        app.include_router(router, prefix="/v1/supplier/bulk-upload")
        current_user = db_session.get(UserModel, TEST_USER_ID)

        def _get_session():
            yield db_session

        def _get_user():
            return current_user

        app.dependency_overrides[bulk_routes.get_session] = _get_session
        app.dependency_overrides[bulk_routes.get_current_user] = _get_user
        monkeypatch.setattr(bulk_routes.TenantContext, "get_tenant_context",
                            lambda _db: TEST_TENANT_ID)
        monkeypatch.setattr(bulk_routes, "session_store", store)
        monkeypatch.setattr(
            bulk_routes, "execute_bulk_commit",
            lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("DB exploded"))
        )

        with TestClient(app) as c:
            resp = c.post(f"/v1/supplier/bulk-upload/commit?session_id={sid}")

        assert resp.status_code == 400
        assert "DB exploded" in resp.json()["detail"]

        # Verify session was transitioned to "failed"
        import asyncio
        loop2 = asyncio.new_event_loop()
        session_after = loop2.run_until_complete(
            store.get_session(tenant_key, user_key, sid)
        )
        loop2.close()
        assert session_after["status"] == "failed"
        assert "DB exploded" in session_after["error"]


# ---------------------------------------------------------------------------
# status: session not found — line 313
# ---------------------------------------------------------------------------


class TestStatusSessionNotFound:

    def test_missing_session_returns_404(self, client: TestClient):
        """Line 313: get_session returns None → 404."""
        resp = client.get("/v1/supplier/bulk-upload/status/session-99999999")
        assert resp.status_code == 404
        assert "Session expired or not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /template — lines 334-336
# ---------------------------------------------------------------------------


class TestDownloadTemplate:

    def test_csv_template_downloads(self, client: TestClient):
        """Lines 334-336: GET /template?format=csv returns streaming CSV."""
        resp = client.get("/v1/supplier/bulk-upload/template?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert len(resp.content) > 0

    def test_xlsx_template_downloads(self, client: TestClient):
        """Lines 334-336: GET /template?format=xlsx returns xlsx binary."""
        resp = client.get("/v1/supplier/bulk-upload/template?format=xlsx")
        assert resp.status_code == 200
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_invalid_format_returns_422(self, client: TestClient):
        """Pattern validation on format param rejects unknown values."""
        resp = client.get("/v1/supplier/bulk-upload/template?format=pdf")
        assert resp.status_code == 422
