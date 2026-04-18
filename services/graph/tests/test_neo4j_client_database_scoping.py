"""Unit tests for ``Neo4jClient`` per-tenant database selection.

Regression coverage for #1229: the constructor used to silently override the
``database=`` argument with ``DB_GLOBAL`` on every call, defeating the
per-tenant DB isolation that callers believed they were configuring via
``Neo4jClient(database=get_tenant_database_name(tenant_id))``.

The fix: honor the argument when ``settings.neo4j_enterprise`` is True; pin
to DB_GLOBAL on Community (the default), but make the choice explicit rather
than silent.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import UUID


def _mk_client_with_fake_driver(enterprise: bool, database):
    """Construct a Neo4jClient with the AsyncGraphDatabase.driver mocked, and
    ``settings.neo4j_enterprise`` patched to ``enterprise``. Returns the
    client instance.
    """
    with patch("app.neo4j_utils.AsyncGraphDatabase") as mock_gdb, patch(
        "app.neo4j_utils.settings"
    ) as mock_settings:
        mock_settings.neo4j_uri = "bolt://localhost:7687"
        mock_settings.neo4j_user = "neo4j"
        mock_settings.neo4j_password = "x"
        mock_settings.neo4j_max_lifetime = 3600
        mock_settings.neo4j_pool_size = 10
        mock_settings.neo4j_pool_timeout = 60.0
        mock_settings.neo4j_encrypted = False
        mock_settings.neo4j_enterprise = enterprise

        mock_gdb.driver.return_value = MagicMock()

        from app.neo4j_utils import Neo4jClient

        if database is None:
            return Neo4jClient()
        return Neo4jClient(database=database)


def test_client_pins_to_global_db_on_community():
    """On Community (neo4j_enterprise=False), a non-None database argument
    is ignored and the client pins to DB_GLOBAL. This is intentional because
    Community cannot actually serve multiple user databases — but it must be
    an explicit (not silent) decision so that reviewers and callers don't
    believe DB-level isolation exists when it does not.
    """
    from app.neo4j_utils import Neo4jClient

    client = _mk_client_with_fake_driver(
        enterprise=False, database="reg_tenant_" + "a" * 32
    )
    assert client.database == Neo4jClient.DB_GLOBAL


def test_client_honors_database_arg_on_enterprise():
    """On Enterprise, the constructor must route the session to the tenant
    database the caller asked for. This is the contract #1229 was silently
    violating before the fix.
    """
    tenant_db = "reg_tenant_" + "a" * 32
    client = _mk_client_with_fake_driver(enterprise=True, database=tenant_db)
    assert client.database == tenant_db


def test_client_falls_back_to_global_when_no_database_on_enterprise():
    """Enterprise + no database= argument => DB_GLOBAL. Preserves the existing
    behavior of unannotated callers (e.g. regulatory/global reads).
    """
    from app.neo4j_utils import Neo4jClient

    client = _mk_client_with_fake_driver(enterprise=True, database=None)
    assert client.database == Neo4jClient.DB_GLOBAL


def test_get_tenant_database_name_format_is_stable():
    """The naming convention is part of the isolation contract; callers build
    DB names via this static method."""
    from app.neo4j_utils import Neo4jClient

    tid = UUID("12345678-1234-5678-1234-567812345678")
    assert (
        Neo4jClient.get_tenant_database_name(tid)
        == f"reg_tenant_{tid}"
    )


def test_session_uses_configured_database_on_enterprise():
    """Session factory must forward the configured database to the driver.
    This is the actual isolation boundary — if the driver sees a different
    DB name than what the client was constructed with, the isolation is a
    lie.
    """
    tenant_db = "reg_tenant_" + "b" * 32
    with patch("app.neo4j_utils.AsyncGraphDatabase") as mock_gdb, patch(
        "app.neo4j_utils.settings"
    ) as mock_settings:
        mock_settings.neo4j_uri = "bolt://localhost:7687"
        mock_settings.neo4j_user = "neo4j"
        mock_settings.neo4j_password = "x"
        mock_settings.neo4j_max_lifetime = 3600
        mock_settings.neo4j_pool_size = 10
        mock_settings.neo4j_pool_timeout = 60.0
        mock_settings.neo4j_encrypted = False
        mock_settings.neo4j_enterprise = True

        fake_driver = MagicMock()
        mock_gdb.driver.return_value = fake_driver

        from app.neo4j_utils import Neo4jClient

        client = Neo4jClient(database=tenant_db)
        client.session()

        fake_driver.session.assert_called_once()
        _, kwargs = fake_driver.session.call_args
        assert kwargs["database"] == tenant_db
