"""Unit tests for webhook v2 rate limiting."""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_router_v2 as webhook_router_v2


def test_check_rate_limit_uses_tenant_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def _allow(**kwargs):
        captured.update(kwargs)
        return True, 19

    monkeypatch.setattr(webhook_router_v2, "consume_tenant_rate_limit", _allow)

    webhook_router_v2._check_rate_limit("tenant-123")

    assert captured["tenant_id"] == "tenant-123"
    assert captured["bucket_suffix"] == "webhooks.ingest"
    assert captured["limit"] > 0
    assert captured["window"] > 0


def test_check_rate_limit_blocks_with_429(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        webhook_router_v2,
        "consume_tenant_rate_limit",
        lambda **_kwargs: (False, 0),
    )

    with pytest.raises(HTTPException) as exc_info:
        webhook_router_v2._check_rate_limit("tenant-123")

    assert exc_info.value.status_code == 429
    assert "Rate limit exceeded" in str(exc_info.value.detail)
