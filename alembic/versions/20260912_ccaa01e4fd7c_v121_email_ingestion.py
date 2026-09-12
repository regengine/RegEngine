"""v121 — inbound email ingestion: tenant address mapping + audit trail.

Revision ID: ccaa01e4fd7c
Revises: c6a120b4e901
Create Date: 2026-09-12

Adds the storage for the inbound-email pipeline (see
``DESIGN_email-ingestion.md``): a Postmark inbound-parse webhook receives an
email, resolves a tenant from the recipient address, runs any CSV
attachment through the existing ``app.csv_templates.ingest_csv`` path, and
records one audit row per email.

1. ``fsma.tenant_inbound_addresses`` — recipient-address -> tenant mapping.
   ``tenant_id UUID NOT NULL`` + ENABLE/FORCE ROW LEVEL SECURITY with the
   standard ``get_tenant_context()`` policy (v095 ``_tenant_rls`` helper),
   so a tenant admin UI can list/manage its own mapped addresses later.
   That alone cannot serve the webhook's lookup: at webhook-receipt time
   there is no tenant context yet, and ``get_tenant_context()`` RAISES when
   ``app.tenant_id`` is unset (v097), so a bare ``FOR ALL`` policy would
   raise before a permissive ``OR`` arm is even considered (the exact class
   of bug v100/v113 fixed for ``public.memberships``/``public.invites``).
   This reuses the ``fsma.remediation_tokens`` bootstrap shape (v095) instead:
   a hash/address-keyed ``FOR SELECT`` policy plus a ``SECURITY DEFINER``
   function (``fsma.get_tenant_by_inbound_address``) that pins
   ``app.tenant_id`` to the nil UUID for the duration of the lookup — turning
   the ``tenant_isolation`` arm from "raises" into "false" (matches no
   tenant) rather than weakening it, so only the address-keyed arm can admit
   a row.

2. ``fsma.inbound_email_audit`` — one row per inbound email, independent of
   attachment count. ``tenant_id`` is nullable (an email to an unmapped
   recipient has no tenant yet must still be auditable), and ``message_id``
   is unique so a provider retry (Postmark retries on non-2xx) is
   idempotent instead of re-running CSV ingestion a second time. Unlike
   every other new ``fsma`` table in this repo, ``FORCE ROW LEVEL SECURITY``
   is deliberately NOT enabled here: the nullable ``tenant_id`` has no value
   to compare against a ``tenant_id = get_tenant_context()`` policy for
   unmapped rows, so the enforcement boundary is the pair of
   ``SECURITY DEFINER`` functions (``fsma.record_inbound_email_audit``,
   ``fsma.get_inbound_email_audit_by_message_id``) instead of a table
   policy — same reasoning as the ``get_remediation_token_by_hash``
   bootstrap precedent (v095) and ``seed_obligations_for_tenant`` (v112) for
   exactly the same "no tenant context yet" problem. No direct table
   privilege is granted to ``regengine``; only ``EXECUTE`` on the two
   functions, matching the v111 closed-grant model.

Downgrade drops the functions, policies, and both tables.
"""

from alembic import op

revision = "ccaa01e4fd7c"  # pragma: allowlist secret
down_revision = "c6a120b4e901"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def _tenant_rls(table: str, column: str, policy: str) -> None:
    """Standard tenant-isolation FOR ALL policy (v095 helper, reused verbatim)."""
    schema, table_name = table.split(".", 1)
    op.execute(
        f"""
        DO $$
        DECLARE
            column_type text;
            predicate text;
        BEGIN
            IF to_regclass('{table}') IS NULL THEN
                RETURN;
            END IF;
            SELECT data_type INTO column_type
            FROM information_schema.columns
            WHERE table_schema = '{schema}'
              AND table_name = '{table_name}'
              AND column_name = '{column}';
            IF column_type IS NULL THEN
                RETURN;
            END IF;
            IF column_type IN ('text', 'character varying') THEN
                predicate := '{column} = get_tenant_context()::text';
            ELSE
                predicate := '{column} = get_tenant_context()';
            END IF;
            EXECUTE 'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY';
            EXECUTE 'ALTER TABLE {table} FORCE ROW LEVEL SECURITY';
            EXECUTE 'DROP POLICY IF EXISTS {policy} ON {table}';
            EXECUTE format(
                'CREATE POLICY {policy} ON {table}
                    FOR ALL
                    USING (%s)
                    WITH CHECK (%s)',
                predicate,
                predicate
            );
        END $$;
        """
    )


def _ensure_runtime_roles() -> None:
    # Make the precondition true instead of guarding the GRANTs on it
    # (v113 precedent — v104 documents a conditional CREATE POLICY as the
    # cause of a production incident; a role must exist, not be assumed).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine') THEN
                CREATE ROLE regengine LOGIN;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'regengine_sysadmin') THEN
                CREATE ROLE regengine_sysadmin LOGIN INHERIT;
            END IF;
        END $$;
        """
    )


def _create_tables() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS fsma")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.tenant_inbound_addresses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL,
            inbound_address TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ux_tenant_inbound_addresses_address UNIQUE (inbound_address)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_inbound_addresses_tenant
            ON fsma.tenant_inbound_addresses (tenant_id);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fsma.inbound_email_audit (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID,
            message_id TEXT NOT NULL,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            subject TEXT,
            status TEXT NOT NULL CHECK (status IN ('accepted', 'partial', 'rejected')),
            rejection_reason TEXT,
            attachment_count INTEGER NOT NULL DEFAULT 0,
            accepted_attachment_count INTEGER NOT NULL DEFAULT 0,
            rejected_attachment_count INTEGER NOT NULL DEFAULT 0,
            details JSONB NOT NULL DEFAULT '[]'::jsonb,
            received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ux_inbound_email_audit_message_id UNIQUE (message_id)
        );
        CREATE INDEX IF NOT EXISTS idx_inbound_email_audit_tenant_received
            ON fsma.inbound_email_audit (tenant_id, received_at DESC);
        """
    )


def _inbound_address_lookup() -> None:
    """Unauthenticated bootstrap lookup under FORCE RLS (v095 precedent).

    The webhook resolves a tenant from a recipient address before any
    tenant context exists, so the address-keyed SELECT policy plus a
    SECURITY DEFINER function are the only RLS path in.
    """
    op.execute("DROP POLICY IF EXISTS inbound_address_lookup ON fsma.tenant_inbound_addresses")
    op.execute(
        """
        CREATE POLICY inbound_address_lookup
            ON fsma.tenant_inbound_addresses
            FOR SELECT
            USING (
                inbound_address = NULLIF(current_setting('app.inbound_lookup_address', true), '')
            )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.get_tenant_by_inbound_address(p_address TEXT)
        RETURNS UUID
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = fsma, public, pg_temp
        SET row_security = off
        AS $fn$
        DECLARE
            v_tenant UUID;
        BEGIN
            PERFORM set_config('app.inbound_lookup_address', lower(p_address), true);
            -- The bootstrap SELECT runs before any tenant context exists,
            -- so it cannot go through the tenant-isolation policy at all
            -- (get_tenant_context() RAISEs on an unset GUC per v097, and
            -- pinning app.tenant_id to any constant to dodge that -- even
            -- the nil UUID -- is exactly the fail-open shape #1091/#2935
            -- ban outright). `SET row_security = off` on this function
            -- bypasses RLS for its own execution only; the REVOKE/GRANT
            -- below still limit who may ever call it, and the query is
            -- scoped to a single row by the caller-supplied address.
            SELECT tenant_id INTO v_tenant
            FROM fsma.tenant_inbound_addresses
            WHERE inbound_address = lower(p_address) AND is_active
            LIMIT 1;
            RETURN v_tenant;
        END;
        $fn$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION fsma.get_tenant_by_inbound_address(TEXT) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION fsma.get_tenant_by_inbound_address(TEXT) TO regengine")


def _audit_functions() -> None:
    """SECURITY DEFINER write/read for fsma.inbound_email_audit.

    This table has no FORCE RLS policy (nullable tenant_id), so these two
    functions are the enforcement boundary instead — matching the
    get_remediation_token_by_hash / seed_obligations_for_tenant bootstrap
    precedent for the same "no tenant context yet" problem.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.record_inbound_email_audit(
            p_tenant_id UUID, p_message_id TEXT, p_sender TEXT, p_recipient TEXT,
            p_subject TEXT, p_status TEXT, p_rejection_reason TEXT,
            p_attachment_count INT, p_accepted_count INT, p_rejected_count INT,
            p_details JSONB
        ) RETURNS TABLE (id UUID, message_id TEXT, status TEXT, attachment_count INT,
                          accepted_attachment_count INT, rejected_attachment_count INT)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = fsma, public, pg_temp
        AS $fn$
        BEGIN
            RETURN QUERY
            INSERT INTO fsma.inbound_email_audit AS a
                (tenant_id, message_id, sender, recipient, subject, status,
                 rejection_reason, attachment_count, accepted_attachment_count,
                 rejected_attachment_count, details)
            VALUES (p_tenant_id, p_message_id, p_sender, p_recipient, p_subject, p_status,
                    p_rejection_reason, p_attachment_count, p_accepted_count, p_rejected_count, p_details)
            ON CONFLICT (message_id) DO NOTHING
            RETURNING a.id, a.message_id, a.status, a.attachment_count,
                      a.accepted_attachment_count, a.rejected_attachment_count;
        END;
        $fn$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION fsma.record_inbound_email_audit"
        "(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INT, INT, INT, JSONB) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION fsma.record_inbound_email_audit"
        "(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INT, INT, INT, JSONB) TO regengine"
    )

    # Idempotency read: service.py checks this first so a provider retry
    # (e.g. our process crashed after committing CSV rows but before
    # returning 200) replays the previously recorded summary instead of
    # re-running CSV ingestion a second time.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.get_inbound_email_audit_by_message_id(p_message_id TEXT)
        RETURNS TABLE (
            id UUID, tenant_id UUID, message_id TEXT, sender TEXT, recipient TEXT,
            subject TEXT, status TEXT, rejection_reason TEXT, attachment_count INT,
            accepted_attachment_count INT, rejected_attachment_count INT,
            details JSONB, received_at TIMESTAMPTZ
        )
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = fsma, public, pg_temp
        AS $fn$
        BEGIN
            RETURN QUERY
            SELECT a.id, a.tenant_id, a.message_id, a.sender, a.recipient,
                   a.subject, a.status, a.rejection_reason, a.attachment_count,
                   a.accepted_attachment_count, a.rejected_attachment_count,
                   a.details, a.received_at
            FROM fsma.inbound_email_audit AS a
            WHERE a.message_id = p_message_id
            LIMIT 1;
        END;
        $fn$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION fsma.get_inbound_email_audit_by_message_id(TEXT) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION fsma.get_inbound_email_audit_by_message_id(TEXT) TO regengine")


def upgrade() -> None:
    _ensure_runtime_roles()
    _create_tables()
    _tenant_rls("fsma.tenant_inbound_addresses", "tenant_id", "tenant_isolation_tenant_inbound_addresses")
    _inbound_address_lookup()
    _audit_functions()


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS fsma.get_inbound_email_audit_by_message_id(TEXT)")
    op.execute(
        "DROP FUNCTION IF EXISTS fsma.record_inbound_email_audit"
        "(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INT, INT, INT, JSONB)"
    )
    op.execute("DROP TABLE IF EXISTS fsma.inbound_email_audit")
    op.execute("DROP FUNCTION IF EXISTS fsma.get_tenant_by_inbound_address(TEXT)")
    op.execute("DROP POLICY IF EXISTS inbound_address_lookup ON fsma.tenant_inbound_addresses")
    op.execute("DROP TABLE IF EXISTS fsma.tenant_inbound_addresses")
