"""Production keeps the unpromoted remediation surface inaccessible.

Positive supplier-remediation tests remain under services/ingestion/tests/
remediation, but their historical grants conflict with v111's current closed
inventory. This gate proves the release contract without adding those grants.
"""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from server.router_policy import PRODUCTION_ENABLED_ROUTERS, RouterPolicy
from tests.migrations.rls_db import guarded_live_database_url

PROHIBITED_TABLE_PRIVILEGES = {
    "fsma.manifest_blobs": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "fsma.manifest_records": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "fsma.remediation_cases": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    # Existing background token/outbox work has narrower positive grants.
    # Those do not authorize creating manifests, cases, or notifications.
    "fsma.remediation_tokens": ("DELETE",),
    "fsma.notification_outbox": ("INSERT", "DELETE"),
}
FUNCTIONS = (
    "fsma.get_remediation_token_by_hash",
    "fsma.get_remediation_token_by_session_hash",
)


def test_production_rejects_remediation_enablement():
    assert "remediation" not in PRODUCTION_ENABLED_ROUTERS
    approved = ",".join(sorted(PRODUCTION_ENABLED_ROUTERS))
    policy = RouterPolicy.from_environment(production=True, environ={"ENABLED_ROUTERS": approved})
    assert not policy.is_enabled("remediation")
    with pytest.raises(RuntimeError, match="extra=.*remediation"):
        RouterPolicy.from_environment(production=True, environ={"ENABLED_ROUTERS": approved + ",remediation"})


@pytest.fixture
def runtime_connection():
    designated = guarded_live_database_url()
    if not designated:
        pytest.fail("a designated migrated scratch database is required for direct-role proof")
    raw = os.getenv("REMEDIATION_TEST_APP_DSN")
    if not raw:
        pytest.fail("REMEDIATION_TEST_APP_DSN is required for direct-role proof")
    target, runtime = make_url(designated), make_url(raw)
    assert (target.host, target.port, target.database) == (runtime.host, runtime.port, runtime.database)
    engine = create_engine(raw)
    try:
        with engine.connect() as conn:
            assert conn.execute(
                text("SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
            ).one() == ("regengine", False, False)
            yield conn
    finally:
        engine.dispose()


@pytest.mark.parametrize("table", PROHIBITED_TABLE_PRIVILEGES)
def test_runtime_cannot_exceed_remediation_grant_inventory(runtime_connection, table):
    conn = runtime_connection
    for privilege in PROHIBITED_TABLE_PRIVILEGES[table]:
        assert not conn.execute(
            text("SELECT has_table_privilege(current_user,:table,:privilege)"), {"table": table, "privilege": privilege}
        ).scalar_one()
    with pytest.raises(DBAPIError), conn.begin_nested():
        conn.execute(text(f"DELETE FROM {table} WHERE false"))


@pytest.mark.parametrize("function", FUNCTIONS)
def test_runtime_cannot_invoke_remediation_token_lookup(runtime_connection, function):
    conn = runtime_connection
    assert not conn.execute(
        text("SELECT has_function_privilege(current_user,:signature,'EXECUTE')"), {"signature": function + "(text)"}
    ).scalar_one()
    with pytest.raises(DBAPIError), conn.begin_nested():
        conn.execute(text(f"SELECT {function}(:token)"), {"token": "unknown-synthetic-token"})
