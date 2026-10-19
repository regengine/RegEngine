"""QA5: review-queue ``offset``/``total`` contract.

``GET /v1/admin/review/hallucinations`` accepted ``offset`` but never
passed it to the tracker, and ``total`` fell back to the page size
because the tracker never returned one. Every page showed the first N
rows while echoing the requested offset. These tests pin the fixed
contract at both layers:

* tracker: ``offset`` skips rows, ``total`` counts pre-pagination rows.
* route: ``offset`` is forwarded and ``total`` comes from the tracker.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

pytest.importorskip("sqlalchemy")

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


def _tracker_db():
    from app.sqlalchemy_models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def _seed_review_items(n: int, tenant_id: str) -> Any:
    from app.metrics import HallucinationTracker  # noqa: E402

    engine = _tracker_db()
    factory = sessionmaker(bind=engine)
    tracker = HallucinationTracker(session_factory=factory, redis_client=None)
    for i in range(n):
        tracker.record_hallucination(
            tenant_id=tenant_id,
            document_id=f"doc-{i}",
            doc_hash=f"hash-{i}",
            extractor="GENERIC",
            confidence_score=0.5,
            extraction={"attributes": {}},
            text_raw=f"source text {i}",
        )
    return tracker


TENANT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class TestTrackerOffsetAndTotal:
    def test_offset_skips_rows(self):
        tracker = _seed_review_items(5, TENANT)
        page1 = tracker.list_hallucinations(tenant_id=TENANT, limit=2)
        page2 = tracker.list_hallucinations(tenant_id=TENANT, limit=2, offset=2)
        page3 = tracker.list_hallucinations(tenant_id=TENANT, limit=2, offset=4)

        assert [i["doc_hash"] for i in page1["items"]] != [i["doc_hash"] for i in page2["items"]]
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 2
        assert len(page3["items"]) == 1
        assert page1["total"] == 5
        assert page2["total"] == 5
        assert page3["total"] == 5

    def test_total_counts_all_matches_not_page_size(self):
        tracker = _seed_review_items(5, TENANT)
        result = tracker.list_hallucinations(tenant_id=TENANT, limit=2)
        assert result["total"] == 5
        assert result["has_more"] is True

    def test_offset_past_end_returns_empty_page_with_total(self):
        tracker = _seed_review_items(3, TENANT)
        result = tracker.list_hallucinations(tenant_id=TENANT, limit=2, offset=10)
        assert result["items"] == []
        assert result["total"] == 3

    def test_negative_offset_clamped_to_zero(self):
        tracker = _seed_review_items(3, TENANT)
        result = tracker.list_hallucinations(tenant_id=TENANT, limit=2, offset=-5)
        assert len(result["items"]) == 2
        assert result["total"] == 3


# ---------------------------------------------------------------------------
# Route layer: offset forwarded, total honored
# ---------------------------------------------------------------------------


def _reset_route_limiter(limiter) -> None:
    reset = getattr(limiter, "reset", None)
    if callable(reset):
        reset()
    storage = getattr(limiter, "_storage", None)
    if storage is None:
        return
    storage_reset = getattr(storage, "reset", None)
    if callable(storage_reset):
        storage_reset()


class _OffsetAwareFakeTracker:
    """Mimics the fixed tracker contract over an in-memory row list."""

    def __init__(self, count: int):
        now = datetime.now(timezone.utc)
        self._rows = [
            {
                "review_id": f"00000000-0000-0000-0000-{i:012d}",
                "doc_hash": f"hash-{i}",
                "confidence_score": 0.42,
                "text_preview": f"preview {i}",
                "extraction": {},
                "created_at": now,
                "status": "PENDING",
            }
            for i in range(count)
        ]
        self.calls: List[Dict[str, Any]] = []

    def list_hallucinations(self, *, status, tenant_id, limit, cursor, offset=0):
        self.calls.append(
            {"status": status, "tenant_id": tenant_id, "limit": limit, "cursor": cursor, "offset": offset}
        )
        page = self._rows[offset : offset + limit]
        return {
            "items": page,
            "next_cursor": None,
            "has_more": offset + limit < len(self._rows),
            "total": len(self._rows),
        }


@pytest.fixture
def routed_app(monkeypatch):
    from app import review_routes as review_mod
    from app.privileged_auth import PrivilegedActor
    from fastapi import FastAPI
    from shared.rate_limit import add_rate_limiting

    _reset_route_limiter(review_mod.limiter)
    app = FastAPI()
    app.include_router(review_mod.router)
    add_rate_limiting(app)

    tracker = _OffsetAwareFakeTracker(5)
    monkeypatch.setattr(review_mod, "_get_tracker", lambda: tracker)
    actor = PrivilegedActor(
        actor_type="tenant_user",
        actor_id="22222222-2222-2222-2222-222222222222",
        session_id="33333333-3333-3333-3333-333333333333",
        auth_method="webauthn",
        tenant_id=TENANT,
        permissions=("review.read",),
    )
    app.dependency_overrides[review_mod.require_review_read] = lambda: actor
    try:
        yield app, tracker
    finally:
        _reset_route_limiter(review_mod.limiter)


def test_route_forwards_offset_and_reports_total(routed_app):
    from fastapi.testclient import TestClient

    app, tracker = routed_app
    with TestClient(app) as client:
        page2 = client.get("/v1/admin/review/hallucinations?limit=2&offset=2")
        page1 = client.get("/v1/admin/review/hallucinations?limit=2&offset=0")

    assert page2.status_code == 200, page2.text
    body2 = page2.json()
    body1 = page1.json()
    assert tracker.calls[-1]["offset"] == 0
    assert tracker.calls[-2]["offset"] == 2
    assert body2["offset"] == 2
    assert body2["total"] == 5
    assert body1["total"] == 5
    hashes1 = [i["doc_hash"] for i in body1["items"]]
    hashes2 = [i["doc_hash"] for i in body2["items"]]
    assert hashes1 != hashes2
    assert hashes2 == ["hash-2", "hash-3"]


def test_route_second_page_contents(routed_app):
    from fastapi.testclient import TestClient

    app, _ = routed_app
    with TestClient(app) as client:
        response = client.get("/v1/admin/review/hallucinations?limit=2&offset=4")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [i["doc_hash"] for i in body["items"]] == ["hash-4"]
    assert body["total"] == 5
