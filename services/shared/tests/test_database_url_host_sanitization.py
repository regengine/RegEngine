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
]

# Hostname is NOT a Supabase pooler; the literal only appears in userinfo,
# path, query, or a lookalike domain. These must all be treated as non-pooler.
_SPOOFED_URLS = [
    "postgresql://pooler.supabase.com@db.internal:5432/postgres",
    "postgresql://u:p@db.internal/pooler.supabase.com",
    "postgresql://u:p@db.internal/postgres?host=pooler.supabase.com",
    "postgresql://u:p@pooler.supabase.com.evil.test:5432/postgres",
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
