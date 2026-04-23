"""DatabaseAPIKeyStore must be pgbouncer-transaction-mode compatible.

Regression test for #1874. Prod `DATABASE_URL` points at Supabase's
transaction-pool pgbouncer endpoint. asyncpg's default prepared-statement
cache is incompatible with `pool_mode=transaction` because pgbouncer
rotates the backend per transaction and cached statement handles from
one transaction are invalid in the next.

The fix: pass ``statement_cache_size=0`` and
``prepared_statement_cache_size=0`` via ``connect_args`` when the URL
uses the asyncpg driver. This test pins that behavior.
"""
from unittest.mock import patch


def _make_store_with_url(url: str):
    """Build a DatabaseAPIKeyStore without opening a real connection.

    Patches ``create_async_engine`` so we can inspect the kwargs the
    store would have used, without touching a network or running a
    real engine.
    """
    from shared import api_key_store

    captured: dict = {}

    def _fake_create_async_engine(database_url, **kwargs):
        captured["database_url"] = database_url
        captured["kwargs"] = kwargs
        return object()  # Engine stand-in; store only needs it for attribute assignment.

    with patch.object(api_key_store, "create_async_engine", _fake_create_async_engine), patch.object(
        api_key_store, "sessionmaker", lambda *a, **kw: None
    ):
        api_key_store.DatabaseAPIKeyStore(database_url=url)
    return captured


def test_asyncpg_url_disables_statement_cache_for_pgbouncer():
    """Supabase pooler URL → cache-disabling connect_args are injected."""
    cap = _make_store_with_url(
        "postgresql://postgres.abc:pw@aws-0-us-east-1.pooler.supabase.com:6543/postgres"  # pragma: allowlist secret
    )
    ca = cap["kwargs"].get("connect_args", {})
    assert ca.get("statement_cache_size") == 0
    assert ca.get("prepared_statement_cache_size") == 0
    # The URL rewrite upgrades to asyncpg driver.
    assert "+asyncpg" in cap["database_url"]


def test_explicit_asyncpg_url_also_gets_cache_disabled():
    """URL that already declares +asyncpg still gets the connect_args."""
    cap = _make_store_with_url(
        "postgresql+asyncpg://postgres.abc:pw@aws-0.pooler.supabase.com:6543/postgres"  # pragma: allowlist secret
    )
    ca = cap["kwargs"].get("connect_args", {})
    assert ca.get("statement_cache_size") == 0
    assert ca.get("prepared_statement_cache_size") == 0


def test_sqlite_url_untouched_by_pgbouncer_fix():
    """Non-postgres URLs do not get asyncpg-specific connect_args."""
    cap = _make_store_with_url("sqlite+aiosqlite:///:memory:")
    ca = cap["kwargs"].get("connect_args", {})
    assert "statement_cache_size" not in ca
    assert "prepared_statement_cache_size" not in ca


def test_existing_connect_args_preserved():
    """If SSL injection already set connect_args, cache-size keys merge in."""
    cap = _make_store_with_url(
        "postgresql://postgres.abc:pw@aws-0.pooler.supabase.com:6543/postgres?sslmode=require"  # pragma: allowlist secret
    )
    ca = cap["kwargs"].get("connect_args", {})
    # SSL fix still applied …
    assert ca.get("ssl") == "require"
    # … alongside the cache-disabling settings.
    assert ca.get("statement_cache_size") == 0
    assert ca.get("prepared_statement_cache_size") == 0
