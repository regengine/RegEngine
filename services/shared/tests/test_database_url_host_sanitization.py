"""Focused tests for Supabase pooler DATABASE_URL detection.

Regression for CodeQL py/incomplete-url-substring-sanitization in
``services/shared/env.py`` and ``services/shared/cors.py``. The pooler host
must be detected by parsing the URL and comparing the hostname (exact host or
subdomain), not by a substring check on the raw connection string.
"""

from __future__ import annotations

import pytest

from shared import cors, env

_POOLER_URLS = [
    "postgresql://u:p@aws-0-us-east-1.pooler.supabase.com:5432/postgres",
    "postgres://u:p@pooler.supabase.com/db",
    # libpq ?host= overrides the URI host, so a pooler reached this way is a
    # real production connection and must fail closed into pooler detection.
    "postgresql://u:p@db.internal/postgres?host=pooler.supabase.com",
    "postgresql://u:p@db.internal/postgres?host=aws-0-us-east-1.pooler.supabase.com",
    # Comma-separated libpq host list where one entry is the pooler.
    "postgresql://u:p@db.internal/postgres?host=db.internal,pooler.supabase.com",
]

# Hostname is NOT a Supabase pooler; the literal only appears in userinfo,
# path, a lookalike domain, a non-host query key, or a lookalike ?host=.
# These must all be treated as non-pooler.
_SPOOFED_URLS = [
    "postgresql://pooler.supabase.com@db.internal:5432/postgres",
    "postgresql://u:p@db.internal/pooler.supabase.com",
    "postgresql://u:p@pooler.supabase.com.evil.test:5432/postgres",
    # Literal appears only in a non-host query parameter.
    "postgresql://u:p@db.internal/postgres?sslhost=pooler.supabase.com",
    # ?host= points at a lookalike domain, not the real pooler.
    "postgresql://u:p@db.internal/postgres?host=pooler.supabase.com.evil.test",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("DATABASE_URL", "REGENGINE_ENV", "ENV"):
        monkeypatch.delenv(name, raising=False)
    yield


@pytest.mark.parametrize("url", _POOLER_URLS)
def test_pooler_host_detected(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    assert env._is_supabase_pooler_database() is True
    assert cors._is_supabase_pooler_database() is True
    # is_production falls back to the pooler heuristic when no env name is set.
    assert env.is_production() is True


@pytest.mark.parametrize("url", _SPOOFED_URLS)
def test_spoofed_pooler_url_rejected(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    assert env._is_supabase_pooler_database() is False
    assert cors._is_supabase_pooler_database() is False
    assert env.is_production() is False


def test_missing_database_url_is_not_pooler(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert env._is_supabase_pooler_database() is False
    assert cors._is_supabase_pooler_database() is False
