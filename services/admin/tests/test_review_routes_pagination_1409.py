"""Regression tests for #1409 -- list_hallucinations pagination discipline.

The endpoint ``GET /v1/admin/review/hallucinations`` previously allowed
``limit=1000`` and returned the full ``text_raw`` (OCR output, 10MB+
per row) in every list row. A single request could produce a multi-GB
response; no rate limit existed. This module pins:

1. The ``limit`` Query cap at 100 (422 on ``limit=101``).
2. List items expose ``text_preview`` (<= 200 chars) and NOT
   ``text_raw`` / ``source_text``.
3. The endpoint carries ``@limiter.limit("30/minute")``.
4. The tracker's ``list_hallucinations`` projection (metrics.py lines
   365-425) also excludes the full ``text_raw`` so megabytes never
   leave the SQLAlchemy row buffer on a list request, even for
   non-HTTP callers of the tracker API.

The matching index on
``review_hallucinations(tenant_id, status, created_at desc, id desc)``
is intentionally out of scope here; it lands in a separate migration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


TENANT_ID = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# Test fixtures -- minimal FastAPI app around just review_routes so we
# don't need a live Postgres. Follows the pattern in
# ``tests/test_funnel_endpoint.py``.
# ---------------------------------------------------------------------------


def _fake_api_key(tenant_id: Optional[str] = TENANT_ID):
    from shared.auth import APIKey

    return APIKey(
        key_id="rge_test_list_hallucinations",
        key_hash="x",
        name="test-key",
        tenant_id=tenant_id,
        created_at=datetime.now(timezone.utc),
    )


class _FakeTracker:
    """Stand-in for ``HallucinationTracker.list_hallucinations`` output.

    We inject a long ``text_preview`` directly so the tests exercise
    the HTTP-layer projection without pulling in the SQLAlchemy
    serializer. (A separate test --
    ``test_tracker_list_projection_excludes_text_raw`` --
    covers the tracker layer end-to-end.)
    """

    def __init__(self, items: List[Dict[str, Any]]):
        self._items = items
        self.calls: List[Dict[str, Any]] = []

    def list_hallucinations(self, *, status, tenant_id, limit, cursor):
        self.calls.append(
            {
                "status": status,
                "tenant_id": tenant_id,
                "limit": limit,
                "cursor": cursor,
            }
        )
        return {
            "items": self._items[:limit],
            "next_cursor": None,
            "has_more": False,
        }


@pytest.fixture
def app_and_tracker(monkeypatch):
    """Build a FastAPI app with review_routes mounted, override auth,
    and swap the tracker getter for a fake."""
    from app import review_routes as review_mod
    from shared.auth import require_api_key

    app = FastAPI()
    app.include_router(review_mod.router)

    # SlowAPI needs the limiter registered on app.state for the
    # decorator to resolve at request time.
    from shared.rate_limit import add_rate_limiting

    add_rate_limiting(app)

    # A 400-char payload exercises both the truncation path and the
    # "preview must not include full text_raw" invariant. 400 > 200
    # (the preview cap) and 400 > 100 * N is irrelevant -- we only
    # care that the wire payload drops the long string.
    long_text = "abcde" * 80  # 400 chars
    now = datetime.now(timezone.utc)

    fake_items = [
        {
            "review_id": f"00000000-0000-0000-0000-00000000000{i}",
            "doc_hash": f"hash-{i}",
            "confidence_score": 0.42,
            # Intentionally: the tracker layer already drops text_raw
            # from list projections (#1409) and returns text_preview.
            # We feed a 400-char preview so the HTTP layer's truncate-
            # to-200 is exercised too.
            "text_preview": long_text,
            "extraction": {"source_text": "extracted"},
            "created_at": now,
            "status": "PENDING",
        }
        for i in range(3)
    ]

    tracker = _FakeTracker(fake_items)
    monkeypatch.setattr(review_mod, "_get_tracker", lambda: tracker)

    app.dependency_overrides[require_api_key] = lambda: _fake_api_key()

    return app, tracker, long_text


# =========================================================================
# 1. limit=101 -> 422 (Query ``le=100``)
# =========================================================================


def test_list_hallucinations_limit_above_100_rejected(app_and_tracker):
    app, _tracker, _ = app_and_tracker
    with TestClient(app) as client:
        response = client.get("/v1/admin/review/hallucinations?limit=101")
    assert response.status_code == 422, response.text


def test_list_hallucinations_limit_100_allowed(app_and_tracker):
    app, _tracker, _ = app_and_tracker
    with TestClient(app) as client:
        response = client.get("/v1/admin/review/hallucinations?limit=100")
    assert response.status_code == 200, response.text


def test_list_hallucinations_limit_1000_rejected_matches_issue_1409(app_and_tracker):
    """The original bug: ``limit=1000`` was accepted and returned
    multi-GB responses. Must now 422."""
    app, _tracker, _ = app_and_tracker
    with TestClient(app) as client:
        response = client.get("/v1/admin/review/hallucinations?limit=1000")
    assert response.status_code == 422


# =========================================================================
# 2. List items exclude text_raw / source_text; include text_preview
# =========================================================================


def test_list_items_exclude_text_raw_field(app_and_tracker):
    app, _tracker, _ = app_and_tracker
    with TestClient(app) as client:
        response = client.get("/v1/admin/review/hallucinations")
    assert response.status_code == 200
    body = response.json()
    assert body["items"], "fixture must produce at least one item"
    for item in body["items"]:
        assert "text_raw" not in item
        # The legacy ``source_text`` field was the full sanitized OCR
        # text and is removed from the list shape in #1409.
        assert "source_text" not in item


def test_list_items_include_text_preview(app_and_tracker):
    app, _tracker, _ = app_and_tracker
    with TestClient(app) as client:
        response = client.get("/v1/admin/review/hallucinations")
    assert response.status_code == 200
    body = response.json()
    for item in body["items"]:
        assert "text_preview" in item
        assert isinstance(item["text_preview"], str)


def test_text_preview_capped_at_200_chars(app_and_tracker):
    """Fixture feeds a 400-char string; wire payload must <= 200."""
    app, _tracker, long_text = app_and_tracker
    assert len(long_text) > 200  # sanity

    with TestClient(app) as client:
        response = client.get("/v1/admin/review/hallucinations")

    assert response.status_code == 200
    body = response.json()
    for item in body["items"]:
        assert len(item["text_preview"]) <= 200


# =========================================================================
# 3. Rate limit: @limiter.limit("30/minute") applied to the endpoint
# =========================================================================


def test_rate_limit_decorator_present_on_endpoint():
    """Pin the decorator at import time. A TestClient-based load-test
    for 429 is brittle across environments (SlowAPI storage backends,
    reset between tests), so we assert the decorator statically
    instead. The slowapi library records decorated endpoints on
    ``limiter._route_limits``."""
    from app import review_routes as review_mod
    from shared.rate_limit import limiter

    # slowapi exposes the per-endpoint limits through a private attr;
    # we probe both the common names it has used.
    registry = getattr(limiter, "_route_limits", None) or getattr(
        limiter, "limits", None
    )

    # Fallback: assert the function's attached limits directly. SlowAPI
    # sticks the Limit objects onto the decorated function via a
    # ``__wrapped__``-like attribute.
    endpoint = review_mod.get_review_queue
    attached = getattr(endpoint, "_rate_limit", None) or getattr(
        endpoint, "__limits__", None
    )

    # At least one probe must come back non-empty. If both are empty,
    # the decorator is not wired and the test fails loudly.
    wired = bool(registry) or bool(attached)
    assert wired, (
        "expected @limiter.limit('30/minute') to be registered on "
        "get_review_queue -- neither limiter._route_limits nor the "
        "endpoint's __limits__ attr surfaced the limit"
    )


def test_rate_limit_value_is_30_per_minute():
    """Inspect the endpoint's docstring and source for the
    ``30/minute`` setting. The source-level check is blunt but
    deliberately so -- the alternative (spinning the limiter with a
    fake clock) is fragile and the value is load-bearing for #1409."""
    import inspect

    from app import review_routes as review_mod

    # Walk up through wrappers to find the source.
    source = inspect.getsource(review_mod.get_review_queue)
    # The decorator lives on the function definition right above.
    module_src = inspect.getsource(review_mod)
    assert '@limiter.limit("30/minute")' in module_src, (
        "expected @limiter.limit(\"30/minute\") literal on the endpoint"
    )
    # And the endpoint body references the cap-at-100 rationale.
    assert "100" in source


# =========================================================================
# 4. Tracker-layer projection excludes text_raw from list aggregates
#    (metrics.py:365-425 parallel fix)
# =========================================================================


def test_tracker_list_projection_excludes_text_raw():
    """Direct unit test on ``HallucinationTracker._serialize_list_item``.

    The tracker's list projection must not include ``text_raw`` in the
    serialized dict; it must include ``text_preview`` bounded at 200
    chars. This closes the ``metrics.py:365-425`` parallel hole called
    out in issue #1409.
    """
    from app.metrics import HallucinationTracker

    # Build a stub ReviewItemModel-shaped object. The tracker calls
    # ``item.text_raw`` / ``item.reviewer_id`` / etc., so a duck-typed
    # SimpleNamespace is sufficient.
    long_raw = "x" * 15_000  # 15k chars -- simulates OCR output
    item = SimpleNamespace(
        id="11111111-2222-3333-4444-555555555555",
        tenant_id=None,
        doc_hash="hash-abc",
        confidence_score=0.5,
        status="PENDING",
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        extraction={"attributes": {}},
        provenance=None,
        reviewer_id=None,
        text_raw=long_raw,
    )

    tracker = HallucinationTracker(session_factory=lambda: None)
    result = tracker._serialize_list_item(item)

    # The full raw text MUST NOT appear in the list projection. This
    # is the megabyte-saver; a regression here reopens the original
    # multi-GB response hole.
    assert "text_raw" not in result
    assert "text_preview" in result
    assert len(result["text_preview"]) <= 200
    assert result["text_preview"] == long_raw[:200]


def test_tracker_detail_projection_still_includes_text_raw():
    """Negative control: the DETAIL path must still expose full
    ``text_raw`` so the single-item view / audit exports keep working.
    This pins that we didn't accidentally strip ``text_raw`` from
    ``get_hallucination``'s projection too."""
    from app.metrics import HallucinationTracker

    long_raw = "y" * 5_000
    item = SimpleNamespace(
        id="22222222-3333-4444-5555-666666666666",
        tenant_id=None,
        doc_hash="hash-def",
        confidence_score=0.7,
        status="PENDING",
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        extraction={"attributes": {}},
        provenance=None,
        reviewer_id="some-reviewer",
        text_raw=long_raw,
    )

    tracker = HallucinationTracker(session_factory=lambda: None)
    result = tracker._serialize(item)

    assert "text_raw" in result
    assert result["text_raw"] == long_raw


# =========================================================================
# 5. Tenant-scope / 403 path preserved (regression guard on #1389)
# =========================================================================


def test_legacy_key_without_tenant_still_rejected(app_and_tracker, monkeypatch):
    """The existing #1389 guard (no-tenant keys are 403) must survive
    the #1409 refactor."""
    from app import review_routes as review_mod
    from shared.auth import require_api_key

    app, _tracker, _ = app_and_tracker
    app.dependency_overrides[require_api_key] = lambda: _fake_api_key(tenant_id=None)

    with TestClient(app) as client:
        response = client.get("/v1/admin/review/hallucinations")
    assert response.status_code == 403
