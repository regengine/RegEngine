"""Data-free checks for the supplier form and request rate limit."""

from __future__ import annotations

import pytest
from app.remediation import supplier_router
from fastapi import HTTPException
from starlette.requests import Request


@pytest.mark.asyncio
async def test_form_page_is_static_and_tokenless():
    response = await supplier_router.correction_form()
    assert response.status_code == 200
    assert response.media_type == "text/html"
    assert b"location.hash" in response.body


def test_rate_limit_trips(monkeypatch):
    calls = 0

    def limiter(**_kwargs):
        nonlocal calls
        calls += 1
        return calls < 2, 0

    monkeypatch.setattr(supplier_router, "_consume_rate_limit", limiter)
    request = Request({"type": "http", "headers": [], "client": ("testclient", 0)})
    supplier_router._rate_limit(request, "preview", 1)
    with pytest.raises(HTTPException) as excinfo:
        supplier_router._rate_limit(request, "preview", 1)
    assert excinfo.value.status_code == 429
