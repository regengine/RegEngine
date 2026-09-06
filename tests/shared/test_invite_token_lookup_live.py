"""Live-DB regression: the public accept-invite path can read its invite (#2899).

``POST /auth/accept-invite`` is unauthenticated. Its first act is to look up
``public.invites`` by the SHA-256 of the token the invitee was mailed — before
any tenant is known, because the invite row is what *names* the tenant.

``public.invites`` is ENABLE + FORCE ROW LEVEL SECURITY with exactly one
policy, v078's ``tenant_isolation_invites`` (``tenant_id =
get_tenant_context()``, ``FOR ALL``, no ``TO`` clause, no sysadmin arm), and
v097 pinned ``get_tenant_context()`` to RAISE when ``app.tenant_id`` is unset.
The admin pool's checkout listener clears ``app.tenant_id`` on every checkout.
So under the #2461 least-privilege posture the lookup raised
``app.tenant_id not set - tenant context required for RLS`` for BOTH
``regengine`` and ``regengine_sysadmin`` — every invite acceptance 500'd.

This is the same mechanism as the 2026-07-27 production incident that v100
fixed for ``public.memberships`` (see
``tests/shared/test_auth_pretenant_membership_lookup_live.py``); v100 was
scoped to one table, so ``invites`` kept the defect.

v113's fix is deliberately narrower than v100's: instead of an
``USING (true)`` policy arm that would expose every invite row of every
tenant to the admin role, it adds a SECURITY DEFINER function keyed on the
token hash which returns nothing but the ``tenant_id`` of an invite that is
unaccepted, unrevoked and unexpired. Possession of the mailed token is the
authorisation; the handler then binds that tenant context and every
subsequent statement is authorised by the ordinary tenant policies.

The assertions below therefore cover both halves: the pre-tenant lookup now
works, AND ``public.invites`` itself is no more readable than it was.

Only a real Postgres evaluates RLS policies, which is why the SQLite-backed
``accept_invite`` unit tests never caught this.
"""

from __future__ import annotations

import uuid

import pytest

from tests.migrations.rls_db import guarded_live_database_url

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason=(
        "no designated live test DB (CI DATABASE_URL or REGENGINE_MIGRATION_TEST_DB) — "
        "skipping live invite token lookup test"
    ),
)

_LOOKUP = "public.get_invite_tenant_by_token_hash"


def _engine():
    from sqlalchemy import create_engine

    # Raw engine on purpose: shared.database's begin-hook must not be
    # involved — the point is a connection with NO app.tenant_id GUC at all.
    return create_engine(DATABASE_URL)


def _seed(conn, *, token_hash: str, accepted: bool = False, revoked: bool = False, expired: bool = False):
    """Insert a tenant/inviter/role/invite quadruple. Caller rolls back."""
    from sqlalchemy import text

    tenant_id = uuid.uuid4()
    inviter_id = uuid.uuid4()
    role_id = uuid.uuid4()
    suffix = uuid.uuid4().hex[:12]

    conn.execute(
        text("INSERT INTO public.tenants (id, name, slug) VALUES (:id, :name, :slug)"),
        {"id": str(tenant_id), "name": f"t-{suffix}", "slug": f"t-{suffix}"},
    )
    conn.execute(
        text("INSERT INTO public.users (id, email, status) VALUES (:id, :email, 'active')"),
        {"id": str(inviter_id), "email": f"inviter-{suffix}@example.test"},
    )
    conn.execute(
        text("INSERT INTO public.roles (id, tenant_id, name) VALUES (:id, :tid, 'Member')"),
        {"id": str(role_id), "tid": str(tenant_id)},
    )
    conn.execute(
        text(
            """
            INSERT INTO public.invites
                (id, tenant_id, email, role_id, token_hash, expires_at,
                 revoked_at, accepted_at, created_by)
            VALUES
                (:id, :tid, :email, :rid, :hash,
                 now() + (CASE WHEN :expired THEN interval '-1 day' ELSE interval '7 days' END),
                 CASE WHEN :revoked THEN now() ELSE NULL END,
                 CASE WHEN :accepted THEN now() ELSE NULL END,
                 :cby)
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "tid": str(tenant_id),
            "email": f"invitee-{suffix}@example.test",
            "rid": str(role_id),
            "hash": token_hash,
            "expired": expired,
            "revoked": revoked,
            "accepted": accepted,
            "cby": str(inviter_id),
        },
    )
    return tenant_id


@pytest.mark.parametrize("role", ["regengine_sysadmin"])
def test_token_lookup_resolves_tenant_without_tenant_context(role: str) -> None:
    """The acceptance criterion: works as the admin route credential, no tenant GUC set.

    Pre-v113 this raised ``app.tenant_id not set`` for either role.
    """
    from sqlalchemy import text

    engine = _engine()
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar():
                    pytest.fail(f"{role} role not present — this database is not prod-shaped")

                token_hash = uuid.uuid4().hex
                tenant_id = _seed(conn, token_hash=token_hash)

                conn.execute(text(f"SET LOCAL ROLE {role}"))
                # Belt and braces: prove the GUC really is unset on this
                # connection, so the assertion below cannot pass by accident.
                assert conn.execute(text("SELECT current_setting('app.tenant_id', true)")).scalar() in (None, "")

                resolved = conn.execute(text(f"SELECT {_LOOKUP}(:h)"), {"h": token_hash}).scalar()
                assert resolved is not None, (
                    f"{_LOOKUP} returned NULL for a valid unconsumed invite as {role}; "
                    "the public accept-invite route cannot resolve its tenant and will 400/500"
                )
                assert str(resolved) == str(tenant_id)
            finally:
                trans.rollback()
    finally:
        engine.dispose()


def test_token_lookup_is_fail_closed_for_unusable_invites() -> None:
    """Accepted / revoked / expired / unknown tokens resolve to NULL, not a tenant.

    The function is the only pre-tenant window into ``invites``; if it served
    consumed tokens it would be a replayable cross-tenant entry point.
    """
    from sqlalchemy import text

    engine = _engine()
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                cases = {
                    "accepted": {"accepted": True},
                    "revoked": {"revoked": True},
                    "expired": {"expired": True},
                }
                hashes = {}
                for label, kwargs in cases.items():
                    h = uuid.uuid4().hex
                    _seed(conn, token_hash=h, **kwargs)
                    hashes[label] = h

                conn.execute(text("SET LOCAL ROLE regengine_sysadmin"))
                for label, h in hashes.items():
                    resolved = conn.execute(text(f"SELECT {_LOOKUP}(:h)"), {"h": h}).scalar()
                    assert resolved is None, f"{label} invite must not resolve a tenant, got {resolved!r}"

                unknown = conn.execute(text(f"SELECT {_LOOKUP}(:h)"), {"h": uuid.uuid4().hex}).scalar()
                assert unknown is None, "an unknown token hash must resolve to NULL"
            finally:
                trans.rollback()
    finally:
        engine.dispose()


def test_invites_table_is_no_more_readable_than_before() -> None:
    """The fix must not widen ``tenant_isolation_invites``.

    Two properties, both of which a policy-relaxing "fix" would break:
      * with no tenant context, a direct read of ``public.invites`` still
        raises — the table was not opened up, only the token-keyed function
        was added;
      * with tenant B's context bound, tenant A's invite is invisible.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    engine = _engine()
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                token_hash = uuid.uuid4().hex
                tenant_a = _seed(conn, token_hash=token_hash)
                other_tenant = uuid.uuid4()

                conn.execute(text("SET LOCAL ROLE regengine_sysadmin"))

                sp = conn.begin_nested()
                try:
                    conn.execute(
                        text("SELECT id FROM public.invites WHERE token_hash = :h"),
                        {"h": token_hash},
                    ).fetchall()
                    raised = False
                except DBAPIError as exc:
                    raised = "app.tenant_id not set" in str(exc)
                finally:
                    sp.rollback()
                assert raised, (
                    "a direct read of public.invites with no tenant context no longer fails closed — "
                    "tenant_isolation_invites has been widened, which is not what #2899 asked for"
                )

                conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(other_tenant)})
                cross = conn.execute(
                    text("SELECT id FROM public.invites WHERE token_hash = :h"),
                    {"h": token_hash},
                ).fetchall()
                assert cross == [], f"tenant {other_tenant} can read tenant {tenant_a}'s invite row — cross-tenant leak"
            finally:
                trans.rollback()
    finally:
        engine.dispose()


def test_lookup_function_is_invoker_pinned_and_not_world_executable() -> None:
    """The lookup must NOT be a privilege escalation.

    Authorisation comes from the ``invites_token_lookup`` policy, evaluated
    against the real calling role. A SECURITY DEFINER here would be both
    useless (``invites`` is FORCE RLS, so the owner is subject to the same
    policy — v112 records that trap) and a standing read primitive.
    """
    from sqlalchemy import text

    engine = _engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT p.prosecdef, p.proconfig, p.proacl::text
                    FROM pg_proc p
                    JOIN pg_namespace n ON n.oid = p.pronamespace
                    WHERE n.nspname = 'public'
                      AND p.proname = 'get_invite_tenant_by_token_hash'
                    """
                )
            ).fetchone()
            assert row is not None, "public.get_invite_tenant_by_token_hash is missing — v113 not applied"
            prosecdef, proconfig, proacl = row

            assert prosecdef is False, (
                "the lookup must stay SECURITY INVOKER — the token-keyed policy arm is the "
                "authorisation, and definer rights would not bypass FORCE RLS anyway"
            )
            assert proconfig and any(c.startswith("search_path=") for c in proconfig), (
                "search_path must be pinned so a caller cannot re-point the function's relations"
            )
            assert proacl is not None, "EXECUTE must be revoked from PUBLIC (a NULL acl means world-executable)"
            # A PUBLIC grant is the acl entry with an EMPTY grantee: "=X/owner".
            assert "{=" not in proacl and ",=" not in proacl, f"EXECUTE must not be granted to PUBLIC, got {proacl!r}"
            assert "regengine=X/" not in proacl and "regengine_sysadmin=X/" in proacl, (
                f"only the admin route credential needs EXECUTE, got {proacl!r}"
            )
    finally:
        engine.dispose()


def test_token_lookup_arm_is_scoped_to_a_single_unconsumed_row() -> None:
    """The policy arm must not be a back door onto the whole table.

    Arming the GUC by hand exposes exactly the row whose token hash was
    supplied — nothing else, and nothing already consumed.
    """
    from sqlalchemy import text

    engine = _engine()
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            try:
                wanted = uuid.uuid4().hex
                other = uuid.uuid4().hex
                _seed(conn, token_hash=wanted)
                _seed(conn, token_hash=other)

                conn.execute(text("SET LOCAL ROLE regengine_sysadmin"))
                # Mirror what get_invite_tenant_by_token_hash does internally:
                # an unmatchable tenant id (so the fail-hard arm evaluates to
                # false rather than raising) plus the token hash.
                conn.execute(text("SELECT set_config('app.tenant_id', gen_random_uuid()::text, true)"))
                conn.execute(
                    text("SELECT set_config('regengine.invite_token_hash', :h, true)"),
                    {"h": wanted},
                )
                rows = conn.execute(text("SELECT token_hash FROM public.invites")).fetchall()
                assert [r[0] for r in rows] == [wanted], (
                    f"the token-keyed arm exposed more than the one invite it was armed for: {[r[0] for r in rows]!r}"
                )
            finally:
                trans.rollback()
    finally:
        engine.dispose()


def test_ordinary_runtime_cannot_read_invites_or_invoke_lookup():
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    engine = _engine()
    try:
        with engine.connect() as conn:
            transaction = conn.begin()
            try:
                conn.execute(text("SET LOCAL ROLE regengine"))
                assert not conn.execute(
                    text("SELECT has_table_privilege(current_user, 'public.invites', 'SELECT')")
                ).scalar()
                for sql in (
                    "SELECT public.get_invite_tenant_by_token_hash('unknown')",
                    "SELECT token_hash FROM public.invites",
                ):
                    with (
                        pytest.raises(DBAPIError, match="permission denied|app.tenant_id not set"),
                        conn.begin_nested(),
                    ):
                        conn.execute(text(sql))
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
