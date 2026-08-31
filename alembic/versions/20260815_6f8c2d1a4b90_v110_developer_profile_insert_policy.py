"""v110 -- allow authenticated users to create their own developer profile.

Revision ID: 6f8c2d1a4b90
Revises: 51701aedee57
Create Date: 2026-08-15

The developer portal requires a one-to-one ``developer_profiles`` row before
users can create sandbox API keys. Existing RLS policies permit users to read
and update their own row but do not permit the initial insert.

#2880 — this revision is Supabase-only, and now says so explicitly
--------------------------------------------------------------------
As first written, ``upgrade()`` wrapped the ``CREATE POLICY`` in a block that
``RETURN``ed silently when ``to_regclass('public.developer_profiles')`` was
NULL or when the ``authenticated`` role was missing. Both are false on the
Alembic-managed database, so the revision was a guaranteed double no-op —
the same shape v104's docstring calls out as the cause of a production
incident ("A conditional CREATE POLICY is what caused this incident").

The evidence that the developer portal is a Supabase surface, not an
Alembic-managed one:

* ``developer_profiles`` is created by no migration in this tree. v058 only
  COMMENTs on it, and even that is wrapped in
  ``EXCEPTION WHEN undefined_table THEN NULL``. Its documented shape is
  "1:1 with auth.users via auth_user_id" — ``auth.users`` is the Supabase
  auth schema.
* Its only consumers are Next.js route handlers going through a Supabase
  client (``frontend/src/app/api/developer/portal/_utils.ts`` and
  ``frontend/src/proxy.ts``: ``client.supabase.from('developer_profiles')``),
  i.e. PostgREST against the Supabase project — never the backend's
  ``DATABASE_URL``.
* ``authenticated`` and ``auth.uid()`` are Supabase constructs that do not
  exist on the Railway database (v104 documents this at length).

So neither of the other two options fits. Creating the table here (option a)
would put dead schema on the Alembic database that nothing reads, keyed on an
``auth.uid()`` function that does not exist there. Raising unconditionally
(option b) would abort ``alembic upgrade head``, which is the production
container entrypoint (``Dockerfile`` line 101) — every Railway deploy would
fail on a policy that database has no use for.

Option (c), implemented below: gate on an explicit environment marker,
``REGENGINE_SUPABASE_PORTAL_MIGRATIONS=1``, set only when the migration
target IS the Supabase project that hosts the developer portal. The
difference from the original guard is that the decision is now made by the
operator rather than inferred from the schema, and it is loud in both
directions:

* marker unset (the Railway/Alembic path) — a deliberate, logged no-op. The
  skip is a documented property of this revision, not an accident of a
  precondition that silently failed.
* marker set — the DDL runs with NO ``to_regclass`` / ``pg_roles`` guard, and
  an explicit ``RAISE EXCEPTION`` fires if the table or role is missing. A
  Supabase target that cannot host this policy fails the migration instead of
  quietly shipping without it.

Editing an already-released revision in place is safe here precisely because
it was a guaranteed no-op: no database anywhere applied anything under
6f8c2d1a4b90, so re-defining what it does cannot diverge from what any
database already has.
"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "6f8c2d1a4b90"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "51701aedee57"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Set to "1" only when this migration run targets the Supabase project that
# hosts the developer portal (the one carrying auth.users / auth.uid() and the
# anon+authenticated roles). Unset everywhere else, including Railway.
_MARKER_ENV = "REGENGINE_SUPABASE_PORTAL_MIGRATIONS"


def _targets_supabase_portal() -> bool:
    return os.environ.get(_MARKER_ENV, "0") == "1"


def upgrade() -> None:
    if not _targets_supabase_portal():
        # Deliberate no-op, announced in the migration log so a deploy that
        # SHOULD have applied it is visible rather than silent.
        op.execute(
            f"""
            DO $$
            BEGIN
                RAISE NOTICE
                    'v110: developer_profiles insert policy not applied - '
                    '{_MARKER_ENV} is not set, so this run does not target the '
                    'Supabase developer-portal project. This is the expected '
                    'outcome on the Alembic-managed database (see #2880).';
            END
            $$;
            """
        )
        return

    op.execute(
        f"""
        DO $$
        BEGIN
            -- Preconditions are asserted, not guarded: {_MARKER_ENV}=1 is the
            -- operator asserting this IS the portal database, so a missing
            -- table or role is a broken target, not a reason to skip (#2880).
            IF to_regclass('public.developer_profiles') IS NULL THEN
                RAISE EXCEPTION
                    'v110: {_MARKER_ENV}=1 but public.developer_profiles does not '
                    'exist - this database does not host the developer portal';
            END IF;

            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                RAISE EXCEPTION
                    'v110: {_MARKER_ENV}=1 but the authenticated role does not '
                    'exist - this database is not a Supabase project';
            END IF;

            DROP POLICY IF EXISTS developers_insert_own_profile
                ON public.developer_profiles;

            CREATE POLICY developers_insert_own_profile
                ON public.developer_profiles
                FOR INSERT
                TO authenticated
                WITH CHECK ((SELECT auth.uid()) = auth_user_id);
        END
        $$;
        """
    )


def downgrade() -> None:
    if not _targets_supabase_portal():
        op.execute(
            f"""
            DO $$
            BEGIN
                RAISE NOTICE
                    'v110 downgrade: nothing to remove - {_MARKER_ENV} is not set, '
                    'so the insert policy was never applied here (#2880).';
            END
            $$;
            """
        )
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('public.developer_profiles') IS NULL THEN
                RETURN;
            END IF;

            DROP POLICY IF EXISTS developers_insert_own_profile
                ON public.developer_profiles;
        END
        $$;
        """
    )
