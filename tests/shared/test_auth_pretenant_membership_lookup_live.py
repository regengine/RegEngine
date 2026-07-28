"""Live-DB regression: pre-tenant memberships lookup works for the auth path.

Prod incident 2026-07-27: after the #2461 least-privilege cutover every
authenticated dashboard route returned 500. ``GET /auth/me`` and
``get_current_user`` select the user's active ``public.memberships`` rows to
DERIVE the tenant — before any tenant context exists. The table is FORCE-RLS
with only ``tenant_id = get_tenant_context()``, and v097's fail-hard
``get_tenant_context()`` raises ``app.tenant_id not set`` when the GUC is
unset. The old role's BYPASSRLS masked this; ``regengine_sysadmin`` (the
admin engine's role) is NOBYPASSRLS, so the auth bootstrap raised on its
first query and the frontend's auth hydration looped on the 500s.

v100 adds a SELECT-only policy arm TO ``regengine_sysadmin``. This test runs
that exact pre-tenant query as ``regengine_sysadmin`` on a live database with
NO tenant GUC set and asserts it completes. A mocked-session test cannot
catch this (only a real Postgres evaluates RLS policies), which is how it
shipped. Requires DATABASE_URL and skips without it (same pattern as
tests/shared/test_data_archival_job_live.py); also skips when the
``regengine_sysadmin`` role does not exist (plain local databases).
"""

from __future__ import annotations

import os
import uuid

import pytest

DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("ADMIN_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping live pre-tenant membership lookup test",
)


def test_sysadmin_reads_memberships_without_tenant_context() -> None:
    from sqlalchemy import create_engine, text

    # Raw engine on purpose: shared.database's Engine begin-hook must not be
    # involved — the point is a connection with NO app.tenant_id GUC at all.
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as conn:
            role_exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin'")).scalar()
            if not role_exists:
                pytest.skip("regengine_sysadmin role not present in this database")

            policy_exists = conn.execute(
                text(
                    "SELECT 1 FROM pg_policies WHERE schemaname = 'public' "
                    "AND tablename = 'memberships' "
                    "AND policyname = 'memberships_sysadmin_read'"
                )
            ).scalar()
            assert policy_exists, (
                "memberships_sysadmin_read policy missing — v100 not applied; "
                "the /auth/me pre-tenant lookup would 500 under least privilege"
            )

            trans = conn.begin()
            try:
                conn.execute(text("SET LOCAL ROLE regengine_sysadmin"))
                # The exact shape of _resolve_session_tenant_id /
                # get_current_user's derivation: active memberships by
                # user_id, no tenant GUC set. Pre-v100 this raises
                # "app.tenant_id not set - tenant context required for RLS".
                rows = conn.execute(
                    text("SELECT tenant_id FROM public.memberships WHERE user_id = :uid AND is_active = true"),
                    {"uid": str(uuid.uuid4())},
                ).fetchall()
                assert rows == []
            finally:
                trans.rollback()
    finally:
        engine.dispose()
