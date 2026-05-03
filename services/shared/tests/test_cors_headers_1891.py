"""CORS header allow-list regression tests for #1891."""

from __future__ import annotations

import pytest

from shared.cors import get_allowed_headers


def test_default_cors_headers_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_HEADERS", raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "production")

    headers = get_allowed_headers()

    assert "*" not in headers
    assert "Authorization" in headers
    assert "Content-Type" in headers
    assert "X-RegEngine-API-Key" in headers
    assert "X-RegEngine-Partner-Key" in headers
    assert "X-Tenant-ID" in headers
    assert "X-RegEngine-Tenant-ID" in headers
    assert "X-Request-ID" in headers
    assert "X-Correlation-ID" in headers
    assert "X-API-Version" in headers


def test_wildcard_cors_headers_rejected_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("CORS_ALLOWED_HEADERS", "Authorization,*")

    with pytest.raises(ValueError, match=r"wildcard .* headers not allowed"):
        get_allowed_headers()


def test_wildcard_cors_headers_allowed_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setenv("CORS_ALLOWED_HEADERS", "Authorization,*")

    assert get_allowed_headers() == ["Authorization", "*"]
