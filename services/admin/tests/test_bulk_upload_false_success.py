"""False-success fixes for bulk upload.

* Autofill warnings used to live in a module-global list cleared per run,
  so concurrent validations stole or duplicated each other's warnings.
* Invalid rows (bad ISO dates, unknown FTL categories) were reported as
  warnings and dropped while the commit reported success.
* Commit responses hid non-blocking warnings entirely.
"""

from __future__ import annotations

import asyncio
import sys
import threading
from uuid import UUID

import pytest
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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

TEST_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


class _InMemorySessionStore:
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

    async def try_claim_commit(
        self, tenant_id, user_id, session_id, *, from_status="validated", to_status="processing", mutations=None
    ):
        key = f"{tenant_id}:{user_id}:{session_id}"
        payload = self._store.get(key)
        if payload is None or payload.get("status") != from_status:
            return None
        payload["status"] = to_status
        if mutations:
            payload.update(mutations)
        self._store[key] = payload
        return payload


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
    from sqlalchemy import text as _ddl_text

    with engine.begin() as _conn:
        _conn.execute(
            _ddl_text("""
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
        """)
        )
    SM = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    session = SM()
    session.add(TenantModel(id=TEST_TENANT_ID, name="T", slug="t", status="active", settings={}))
    session.add(UserModel(id=TEST_USER_ID, email="u@example.com", status="active", is_sysadmin=False))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        for t in reversed(tables):
            t.drop(bind=engine)
        engine.dispose()


@pytest.fixture
def client_and_store(db_session, monkeypatch):
    import app.bulk_upload.routes as bulk_routes
    import app.bulk_upload.transaction_manager as tx_manager

    app = FastAPI()
    app.include_router(bulk_routes.router, prefix="/v1/supplier/bulk-upload")
    current_user = db_session.get(UserModel, TEST_USER_ID)

    def _get_session():
        yield db_session

    def _get_user():
        return current_user

    app.dependency_overrides[bulk_routes.get_session] = _get_session
    app.dependency_overrides[bulk_routes.get_current_user] = _get_user
    monkeypatch.setattr(bulk_routes.TenantContext, "get_tenant_context", lambda _db: TEST_TENANT_ID)
    monkeypatch.setattr(tx_manager.supplier_graph_sync, "record_facility_ftl_scoping", lambda **_kw: None)
    monkeypatch.setattr(tx_manager.supplier_graph_sync, "record_cte_event", lambda **_kw: None)
    store = _InMemorySessionStore()
    monkeypatch.setattr(bulk_routes, "session_store", store)
    with TestClient(app) as c:
        yield c, store


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── Per-request warnings ──────────────────────────────────────────


def test_concurrent_validations_do_not_share_autofill_warnings():
    """Each concurrent validation sees exactly its own warnings.

    Threads validate payloads with distinct facility counts under a tiny
    GIL switch interval to force interleaving. With the old module-global
    list, runs observed each other's warnings (wrong counts).
    """
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    mismatches: list[tuple[int, int, int]] = []
    lock = threading.Lock()
    try:

        def worker(idx: int):
            expect = 30 + idx * 10
            payload = {
                "facilities": [
                    {"name": "", "street": "s", "city": "c", "state": "st", "postal_code": "p"} for _ in range(expect)
                ],
                "ftl_scopes": [],
                "tlcs": [],
                "events": [],
            }
            for _ in range(20):
                _, errors = validate_and_normalize_payload(
                    payload,
                    supported_cte_types={"shipping"},
                    valid_ftl_category_ids={"1"},
                )
                got = len([e for e in errors if e.get("section") == "autofill"])
                if got != expect:
                    with lock:
                        mismatches.append((idx, expect, got))
                    return

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        sys.setswitchinterval(old_interval)

    assert mismatches == [], f"warnings crossed request boundaries: {mismatches[:5]}"


def test_concurrent_validations_isolated_with_forced_interleave(monkeypatch):
    """Two validations running inside each other never share a collector.

    The thread-stress test above can pass on the old module-global list
    when the GIL never interleaves the clear and the later read. This
    test forces the interleave with a barrier inside the warning
    collector: both threads must be mid-validation at the same moment.
    With the old shared list each run would then report 2 warnings
    instead of its own 1.
    """
    import app.bulk_upload.validators as validators_mod

    barrier = threading.Barrier(2)
    original_collector = validators_mod._warning_collector
    arrivals: list[int] = []
    arrivals_lock = threading.Lock()

    def hooked_collector():
        collector = original_collector()
        # Rendezvous only the first two collector calls overall (one per
        # thread): later calls pass straight through so the barrier can
        # never strand a thread whose peer already finished.
        with arrivals_lock:
            arrivals.append(1)
            rendezvous = len(arrivals) <= 2
        if rendezvous:
            barrier.wait(timeout=15)
        return collector

    monkeypatch.setattr(validators_mod, "_warning_collector", hooked_collector)

    facility_payload = {
        "facilities": [{"name": "", "street": "s", "city": "c", "state": "st", "postal_code": "p"}],
        "ftl_scopes": [],
        "tlcs": [],
        "events": [],
    }
    tlc_payload = {
        "facilities": [],
        "ftl_scopes": [],
        "tlcs": [{"tlc_code": "", "facility_name": "Salinas Packhouse"}],
        "events": [],
    }
    results: dict[str, list] = {}

    def worker(name, payload):
        _, errors = validate_and_normalize_payload(
            payload,
            supported_cte_types={"shipping"},
            valid_ftl_category_ids={"1"},
        )
        results[name] = [e for e in errors if e.get("section") == "autofill"]

    threads = [
        threading.Thread(target=worker, args=("facility", facility_payload)),
        threading.Thread(target=worker, args=("tlc", tlc_payload)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results["facility"]) == 1, results
    assert "facility_name" in results["facility"][0]["message"], results
    assert len(results["tlc"]) == 1, results
    assert "tlc_code" in results["tlc"][0]["message"], results


def test_sequential_validations_do_not_carry_warnings_over():
    """A clean upload after a messy one reports zero autofill warnings."""
    messy = {
        "facilities": [{"name": "", "street": "s", "city": "c", "state": "st", "postal_code": "p"}],
        "ftl_scopes": [],
        "tlcs": [],
        "events": [],
    }
    _, messy_errors = validate_and_normalize_payload(
        messy, supported_cte_types={"shipping"}, valid_ftl_category_ids={"1"}
    )
    assert any(e.get("section") == "autofill" for e in messy_errors)

    clean = {
        "facilities": [
            {
                "name": "Salinas Packhouse",
                "street": "s",
                "city": "c",
                "state": "st",
                "postal_code": "p",
            }
        ],
        "ftl_scopes": [],
        "tlcs": [],
        "events": [],
    }
    _, clean_errors = validate_and_normalize_payload(
        clean, supported_cte_types={"shipping"}, valid_ftl_category_ids={"1"}
    )
    assert [e for e in clean_errors if e.get("section") == "autofill"] == []


# ── Honest commit reporting ───────────────────────────────────────


def test_commit_rejects_upload_with_dropped_invalid_row(client_and_store, db_session):
    """A dropped invalid row blocks commit instead of silent success."""
    client, store = client_and_store
    tenant_key = str(TEST_TENANT_ID)
    user_key = str(TEST_USER_ID)
    sid = _run(
        store.create_session(
            tenant_key,
            user_key,
            {
                "status": "validated",
                "parsed_data": {
                    "facilities": [
                        {
                            "name": "Salinas Packhouse",
                            "street": "s",
                            "city": "c",
                            "state": "st",
                            "postal_code": "p",
                        }
                    ],
                    "ftl_scopes": [],
                    "tlcs": [],
                    "events": [
                        {
                            "facility_name": "Salinas Packhouse",
                            "tlc_code": "TLC-1",
                            "cte_type": "shipping",
                            "event_time": "not-iso",
                        }
                    ],
                },
            },
        )
    )

    resp = client.post(f"/v1/supplier/bulk-upload/commit?session_id={sid}")
    assert resp.status_code == 400, resp.text
    # The failure names the blocking row so the caller knows what to fix,
    # instead of a bare "invalid rows" sentence.
    detail = resp.json().get("detail", "")
    assert "invalid row" in detail
    assert "event row 1" in detail
    session_data = _run(store.get_session(tenant_key, user_key, sid))
    assert session_data["status"] == "failed"
    assert "event row 1" in (session_data.get("error") or "")
    # Nothing from the rejected payload was persisted.
    assert db_session.query(SupplierFacilityModel).count() == 0
    assert db_session.query(SupplierCTEEventModel).count() == 0


def test_commit_summary_carries_autofill_warnings(client_and_store):
    """Autofill substitutions travel with a completed commit response."""
    client, store = client_and_store
    tenant_key = str(TEST_TENANT_ID)
    user_key = str(TEST_USER_ID)
    sid = _run(
        store.create_session(
            tenant_key,
            user_key,
            {
                "status": "validated",
                "parsed_data": {
                    "facilities": [
                        {"name": "", "street": "s", "city": "c", "state": "st", "postal_code": "p"},
                    ],
                    "ftl_scopes": [],
                    "tlcs": [],
                    "events": [],
                },
            },
        )
    )

    resp = client.post(f"/v1/supplier/bulk-upload/commit?session_id={sid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["summary"]["validation_warning_count"] >= 1
    assert any("Auto-filled" in w for w in body["summary"]["validation_warnings"])
