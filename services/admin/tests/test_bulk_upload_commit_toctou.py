"""Regression tests for #1074 — bulk-upload /commit TOCTOU race.

Two concurrent ``POST /v1/supplier/bulk-upload/commit`` requests for the
same session must never both succeed. Before the fix at
``services/admin/app/bulk_upload/routes.py``, the status guard

    current_status = session_data["status"]         # read
    if current_status == "processing": raise 409    # check
    session_data["status"] = "processing"           # mutate
    await session_store.update_session(...)         # set

was not atomic. Two concurrent callers could both observe
``status == "validated"``, both pass the guard, and both call
``execute_bulk_commit`` — producing duplicate FSMA rows and Merkle-hash
divergence in the audit chain.

The fix replaces the check-then-set with an atomic CAS on
:class:`BulkUploadSessionStore.try_claim_commit`.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.bulk_upload.routes import router
from app.bulk_upload.session_store import BulkUploadSessionStore
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


# ─────────────────────────────────────────────────────────────────────
# Direct unit tests for BulkUploadSessionStore.try_claim_commit
# (exercises the in-memory fallback path — Redis path is symmetric
# but unit-testable only with a real Redis.)
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def store() -> BulkUploadSessionStore:
    """Force the in-memory fallback by pre-flagging Redis as unavailable."""
    s = BulkUploadSessionStore()
    s._redis_available = False  # type: ignore[attr-defined]
    return s


@pytest.mark.asyncio
async def test_try_claim_commit_succeeds_when_status_matches(store):
    session_id = await store.create_session(
        "t1", "u1", {"status": "validated", "normalized_data": {"x": 1}}
    )
    result = await store.try_claim_commit("t1", "u1", session_id)
    assert result is not None
    assert result["status"] == "processing"
    assert result["normalized_data"] == {"x": 1}

    # The persisted payload reflects the transition.
    persisted = await store.get_session("t1", "u1", session_id)
    assert persisted is not None
    assert persisted["status"] == "processing"


@pytest.mark.asyncio
async def test_try_claim_commit_applies_mutations(store):
    session_id = await store.create_session(
        "t1", "u1", {"status": "validated", "error": "stale-error"}
    )
    result = await store.try_claim_commit(
        "t1", "u1", session_id, mutations={"error": None, "updated_at": "2026-04-18T00:00:00+00:00"}
    )
    assert result is not None
    assert result["status"] == "processing"
    assert result["error"] is None
    assert result["updated_at"] == "2026-04-18T00:00:00+00:00"


@pytest.mark.asyncio
async def test_try_claim_commit_returns_none_when_already_processing(store):
    session_id = await store.create_session(
        "t1", "u1", {"status": "processing"}
    )
    result = await store.try_claim_commit("t1", "u1", session_id)
    assert result is None


@pytest.mark.asyncio
async def test_try_claim_commit_returns_none_when_completed(store):
    session_id = await store.create_session(
        "t1", "u1", {"status": "completed", "commit_summary": {"events_chained": 1}}
    )
    result = await store.try_claim_commit("t1", "u1", session_id)
    assert result is None


@pytest.mark.asyncio
async def test_try_claim_commit_returns_none_when_parsed(store):
    """A session that hasn't been validated yet should not be claimable."""
    session_id = await store.create_session(
        "t1", "u1", {"status": "parsed"}
    )
    result = await store.try_claim_commit("t1", "u1", session_id)
    assert result is None


@pytest.mark.asyncio
async def test_try_claim_commit_returns_none_when_session_missing(store):
    result = await store.try_claim_commit("t1", "u1", "nonexistent-session")
    assert result is None


@pytest.mark.asyncio
async def test_try_claim_commit_is_mutually_exclusive_under_concurrency(store):
    """The canonical TOCTOU test: N concurrent claims ⇒ exactly 1 wins.

    This is the core invariant the fix guarantees. Prior to the
    ``try_claim_commit`` CAS, this test would routinely show 2+ winners
    because every claimant could observe ``status=validated`` between
    the first check and the first write.
    """
    session_id = await store.create_session(
        "t1", "u1", {"status": "validated", "normalized_data": {"x": 1}}
    )

    async def _claim() -> dict[str, Any] | None:
        return await store.try_claim_commit("t1", "u1", session_id)

    # Fire many concurrent claims on the same session.
    results = await asyncio.gather(*[_claim() for _ in range(25)])
    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]

    assert len(winners) == 1, (
        f"Exactly one claim must win; got {len(winners)} winners "
        f"(all others must return None)"
    )
    assert len(losers) == 24
    assert winners[0]["status"] == "processing"


@pytest.mark.asyncio
async def test_try_claim_commit_isolates_distinct_sessions(store):
    """Concurrency on different session ids must not serialize each other."""
    sid_a = await store.create_session("t1", "u1", {"status": "validated"})
    sid_b = await store.create_session("t1", "u1", {"status": "validated"})

    # Both should succeed — they're different sessions.
    a, b = await asyncio.gather(
        store.try_claim_commit("t1", "u1", sid_a),
        store.try_claim_commit("t1", "u1", sid_b),
    )
    assert a is not None
    assert b is not None
    assert a["status"] == "processing"
    assert b["status"] == "processing"


@pytest.mark.asyncio
async def test_try_claim_commit_rejects_corrupt_payload(store):
    """A session blob with a non-dict payload is unclaimable, not a crash."""
    # Simulate a corrupted in-memory entry. The store's own methods
    # guarantee dicts, but the defensive path matters for Redis where
    # the blob comes from JSON deserialization.
    import time as _time
    key = store._session_key("t1", "u1", "corrupt-session")
    store._memory_store[key] = (_time.time() + 3600, "not-a-dict")  # type: ignore[assignment]
    result = await store.try_claim_commit("t1", "u1", "corrupt-session")
    assert result is None


# ─────────────────────────────────────────────────────────────────────
# End-to-end route-level regression: two concurrent POSTs to /commit
# ─────────────────────────────────────────────────────────────────────


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    table_bindings = [
        TenantModel.__table__,
        UserModel.__table__,
        SupplierFacilityModel.__table__,
        SupplierFacilityFTLCategoryModel.__table__,
        SupplierTraceabilityLotModel.__table__,
        SupplierCTEEventModel.__table__,
    ]
    for table in table_bindings:
        table.create(bind=engine)

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
            password_hash="hashed-password",
            status="active",
            is_sysadmin=False,
        )
    )
    session.commit()

    try:
        yield session
    finally:
        session.close()
        for table in reversed(table_bindings):
            table.drop(bind=engine)
        engine.dispose()


def test_concurrent_commits_route_level_only_one_succeeds(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """Two concurrent POST /commit calls → exactly one 200, one 409.

    ``execute_bulk_commit`` must be invoked at most once regardless of
    how many duplicate commits arrive. This is the FSMA-audit-integrity
    invariant: duplicated CTE events would produce duplicate
    ``sequence_number`` rows and Merkle-hash divergence.
    """
    import app.bulk_upload.routes as bulk_routes
    import app.bulk_upload.transaction_manager as tx_manager

    # Use the real BulkUploadSessionStore (in-memory fallback path)
    # — that's the code under test. The e2e helper store is a simpler
    # stub; the asyncio.Lock lives in the real store.
    real_store = BulkUploadSessionStore()
    real_store._redis_available = False  # type: ignore[attr-defined]
    monkeypatch.setattr(bulk_routes, "session_store", real_store)

    call_count = {"n": 0}

    def _counting_execute(*_args, **_kwargs) -> dict:
        call_count["n"] += 1
        # Mimic a slow commit so the other request has time to arrive.
        import time as _time
        _time.sleep(0.05)
        return {
            "facilities_created": 0,
            "facilities_updated": 0,
            "ftl_scopes_upserted": 0,
            "tlcs_created": 0,
            "tlcs_updated": 0,
            "events_chained": 1,
            "last_merkle_hash": "deadbeef",
            "sync_warning_count": 0,
            "sync_warnings": [],
        }

    monkeypatch.setattr(bulk_routes, "execute_bulk_commit", _counting_execute)

    test_app = FastAPI()
    test_app.include_router(router, prefix="/v1/supplier/bulk-upload")

    current_user = db_session.get(UserModel, TEST_USER_ID)
    assert current_user is not None

    def override_get_session():
        yield db_session

    def override_get_current_user() -> UserModel:
        return current_user

    test_app.dependency_overrides[bulk_routes.get_session] = override_get_session
    test_app.dependency_overrides[bulk_routes.get_current_user] = override_get_current_user
    monkeypatch.setattr(
        bulk_routes.TenantContext, "get_tenant_context", lambda _db: TEST_TENANT_ID
    )

    # Seed a validated session directly in the real store so we don't
    # depend on parse/validate to make it testable.
    session_id = asyncio.get_event_loop().run_until_complete(
        real_store.create_session(
            str(TEST_TENANT_ID),
            str(TEST_USER_ID),
            {
                "status": "validated",
                "normalized_data": {"facilities": [], "ftl_scopes": [], "tlcs": [], "events": []},
                "parsed_data": {},
                "validation_preview": None,
                "commit_summary": None,
                "error": None,
                "updated_at": "2026-04-18T00:00:00+00:00",
            },
        )
    )

    # Fire two concurrent commits from separate threads. TestClient is
    # sync; we use threads to force real concurrency on the async
    # route. Because our fixture uses a StaticPool SQLite engine, the
    # DB connection is shared safely.
    import threading

    results: list[tuple[int, dict]] = []
    results_lock = threading.Lock()

    def _fire():
        with TestClient(test_app) as client:
            resp = client.post(f"/v1/supplier/bulk-upload/commit?session_id={session_id}")
            with results_lock:
                results.append((resp.status_code, resp.json()))

    t1 = threading.Thread(target=_fire)
    t2 = threading.Thread(target=_fire)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one execute_bulk_commit call — the canonical FSMA invariant.
    assert call_count["n"] == 1, (
        f"execute_bulk_commit must run exactly once; ran {call_count['n']} times. "
        "Each duplicate run would produce a duplicate Merkle-chain event."
    )

    # Exactly one 200 response; the other is either 409 "in progress" or
    # 200 with the cached completed summary (whichever lost the race).
    status_codes = sorted(r[0] for r in results)
    assert status_codes in ([200, 200], [200, 409]), (
        f"Expected one success + one 409 or two idempotent 200s; got {status_codes}"
    )
    # At least one response must report completed status.
    assert any(r[1].get("status") == "completed" for r in results)


def test_commit_after_completed_is_idempotent_not_409(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """A commit on an already-completed session returns the cached summary.

    This is the ``completed`` short-circuit path — without it, the CAS
    would reject a retry and a successfully-completed export would look
    like an error to a client that re-POSTs after a network flap.
    """
    import app.bulk_upload.routes as bulk_routes

    real_store = BulkUploadSessionStore()
    real_store._redis_available = False  # type: ignore[attr-defined]
    monkeypatch.setattr(bulk_routes, "session_store", real_store)

    session_id = asyncio.get_event_loop().run_until_complete(
        real_store.create_session(
            str(TEST_TENANT_ID),
            str(TEST_USER_ID),
            {
                "status": "completed",
                "commit_summary": {
                    "facilities_created": 0,
                    "facilities_updated": 0,
                    "ftl_scopes_upserted": 0,
                    "tlcs_created": 0,
                    "tlcs_updated": 0,
                    "events_chained": 7,
                    "last_merkle_hash": "cafef00d",
                    "sync_warning_count": 0,
                    "sync_warnings": [],
                },
            },
        )
    )

    test_app = FastAPI()
    test_app.include_router(router, prefix="/v1/supplier/bulk-upload")

    current_user = db_session.get(UserModel, TEST_USER_ID)
    assert current_user is not None

    def override_get_session():
        yield db_session

    def override_get_current_user() -> UserModel:
        return current_user

    test_app.dependency_overrides[bulk_routes.get_session] = override_get_session
    test_app.dependency_overrides[bulk_routes.get_current_user] = override_get_current_user
    monkeypatch.setattr(
        bulk_routes.TenantContext, "get_tenant_context", lambda _db: TEST_TENANT_ID
    )

    with TestClient(test_app) as client:
        resp = client.post(f"/v1/supplier/bulk-upload/commit?session_id={session_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["summary"]["events_chained"] == 7


def test_commit_when_session_is_parsed_returns_400(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """A commit without a prior successful validate must be rejected with 400."""
    import app.bulk_upload.routes as bulk_routes

    real_store = BulkUploadSessionStore()
    real_store._redis_available = False  # type: ignore[attr-defined]
    monkeypatch.setattr(bulk_routes, "session_store", real_store)

    session_id = asyncio.get_event_loop().run_until_complete(
        real_store.create_session(
            str(TEST_TENANT_ID),
            str(TEST_USER_ID),
            {"status": "parsed"},
        )
    )

    test_app = FastAPI()
    test_app.include_router(router, prefix="/v1/supplier/bulk-upload")

    current_user = db_session.get(UserModel, TEST_USER_ID)
    assert current_user is not None

    def override_get_session():
        yield db_session

    def override_get_current_user() -> UserModel:
        return current_user

    test_app.dependency_overrides[bulk_routes.get_session] = override_get_session
    test_app.dependency_overrides[bulk_routes.get_current_user] = override_get_current_user
    monkeypatch.setattr(
        bulk_routes.TenantContext, "get_tenant_context", lambda _db: TEST_TENANT_ID
    )

    with TestClient(test_app) as client:
        resp = client.post(f"/v1/supplier/bulk-upload/commit?session_id={session_id}")

    assert resp.status_code == 400
    assert "validated" in resp.json()["detail"].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
