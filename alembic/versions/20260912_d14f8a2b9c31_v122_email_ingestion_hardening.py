"""v122 — inbound email ingestion hardening: sender allowlist + claim-then-act audit.

Revision ID: d14f8a2b9c31
Revises: ccaa01e4fd7c
Create Date: 2026-09-12

Closes two gaps in v121 (``ccaa01e4fd7c``) found in security review, before
this feature has shipped to any real tenant:

1. **No sender authentication.** v121's ``fsma.get_tenant_by_inbound_address``
   resolved a tenant from the recipient address alone. Postmark's Basic-Auth
   webhook credential only proves "this HTTP call came from Postmark" -- it
   forwards *any* internet sender's mail addressed to a configured inbound
   address using that same shared credential. Combined with v121's own
   admission (``DESIGN_email-ingestion.md`` section 14) that inbound
   addresses are "seeded directly ... e.g. via a one-off INSERT" with no
   stated entropy requirement, the entire cross-tenant authorization
   boundary collapsed to "knows/guesses one string".

   Fix: ``fsma.tenant_inbound_addresses`` gains ``allowed_senders TEXT[]``,
   and ``fsma.get_tenant_by_inbound_address`` takes the email's ``From``
   address as a second argument and only resolves a tenant when the sender
   matches an allowlist entry -- either a full address or an ``@domain``
   suffix. A row with an empty allowlist (the v121 default state for any
   already-seeded row) now authorizes **no** sender at all -- fail closed,
   not fail open -- so provisioning always requires an explicit decision
   about who may submit data on the tenant's behalf, in addition to guessing
   the address.

2. **Read-then-act idempotency race**, documented as a known residual gap in
   ``DESIGN_email-ingestion.md`` section 13 item 4: two concurrent
   deliveries of the same Postmark ``MessageID`` could both observe "no
   audit row yet" and both run CSV ingestion, double-persisting CTE events
   through ``CTEPersistence`` (``ON CONFLICT (message_id) DO NOTHING`` on
   the old ``record_inbound_email_audit`` only deduplicated the *audit* row,
   after the fact).

   Fix: claim-then-act, mirroring the ``NotificationOutboxDrainer._claim()``
   pattern already used in ``app/remediation/delivery.py`` for the same
   "make double-processing structurally impossible, not just unlikely"
   problem. ``status`` gains a ``'processing'`` value; a new
   ``fsma.claim_inbound_email_audit`` inserts the audit row with
   ``status='processing'`` *before* any attachment touches CSV ingestion
   (``ON CONFLICT (message_id) DO NOTHING`` -- the loser of the race gets no
   row back and must not proceed), and a new
   ``fsma.finalize_inbound_email_audit`` updates that same row to its final
   status afterward (only while it is still ``'processing'``, so a stray
   double-finalize is a no-op). ``fsma.record_inbound_email_audit`` (the
   single-statement write) is dropped -- nothing else in the codebase calls
   it after this revision.

Both v121 functions this migration replaces are dropped and recreated with
new signatures/bodies rather than left in place, since neither has shipped
to a real deployment yet (this whole feature is still on
``feature/inbound-email-ingestion``).

Downgrade restores the v121 shape: the single-argument
``get_tenant_by_inbound_address(TEXT)``, ``record_inbound_email_audit``, the
three-value status vocabulary, and drops ``allowed_senders`` plus the two
claim/finalize functions.
"""

from alembic import op

revision = "d14f8a2b9c31"  # pragma: allowlist secret
down_revision = "ccaa01e4fd7c"  # pragma: allowlist secret
branch_labels = None
depends_on = None

_STATUSES_NEW = "('processing', 'accepted', 'partial', 'rejected')"
_STATUSES_OLD = "('accepted', 'partial', 'rejected')"


def _add_sender_allowlist() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.tenant_inbound_addresses') IS NULL THEN
                RETURN;
            END IF;
            ALTER TABLE fsma.tenant_inbound_addresses
                ADD COLUMN IF NOT EXISTS allowed_senders TEXT[] NOT NULL DEFAULT '{}';
        END $$;
        """
    )


def _replace_tenant_lookup_function() -> None:
    """Sender-checked replacement for the v121 bootstrap lookup.

    Still runs before any tenant context exists (same RLS bootstrap shape as
    v121/v095), but a row now only matches when ``p_sender`` is present in
    that row's ``allowed_senders`` -- either verbatim, or via an ``@domain``
    suffix entry. Suffix matching uses ``right(...) = pattern`` (not
    ``LIKE``) so a stored allowlist value is never interpreted as a wildcard
    pattern.
    """
    op.execute("DROP FUNCTION IF EXISTS fsma.get_tenant_by_inbound_address(TEXT)")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.get_tenant_by_inbound_address(p_address TEXT, p_sender TEXT)
        RETURNS UUID
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = fsma, public, pg_temp
        AS $fn$
        DECLARE
            v_tenant UUID;
            v_sender TEXT := lower(trim(coalesce(p_sender, '')));
        BEGIN
            PERFORM set_config('app.inbound_lookup_address', lower(p_address), true);
            IF NULLIF(current_setting('app.tenant_id', true), '') IS NULL THEN
                PERFORM set_config('app.tenant_id', '00000000-0000-0000-0000-000000000000', true);
            END IF;

            SELECT tenant_id INTO v_tenant
            FROM fsma.tenant_inbound_addresses
            WHERE inbound_address = lower(p_address)
              AND is_active
              -- Fail closed: a row with no configured allowlist authorizes
              -- no sender (avoids the v121 "any sender who guesses the
              -- address" gap for every already-seeded row).
              AND EXISTS (
                  SELECT 1
                  FROM unnest(allowed_senders) AS pattern
                  WHERE (pattern LIKE '@%' AND right(v_sender, length(pattern)) = pattern)
                     OR (pattern NOT LIKE '@%' AND pattern = v_sender)
              )
            LIMIT 1;

            RETURN v_tenant;
        END;
        $fn$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION fsma.get_tenant_by_inbound_address(TEXT, TEXT) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION fsma.get_tenant_by_inbound_address(TEXT, TEXT) TO regengine")


def _restore_v121_tenant_lookup_function() -> None:
    op.execute("DROP FUNCTION IF EXISTS fsma.get_tenant_by_inbound_address(TEXT, TEXT)")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.get_tenant_by_inbound_address(p_address TEXT)
        RETURNS UUID
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = fsma, public, pg_temp
        AS $fn$
        DECLARE
            v_tenant UUID;
        BEGIN
            PERFORM set_config('app.inbound_lookup_address', lower(p_address), true);
            IF NULLIF(current_setting('app.tenant_id', true), '') IS NULL THEN
                PERFORM set_config('app.tenant_id', '00000000-0000-0000-0000-000000000000', true);
            END IF;
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


def _widen_status_check() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.inbound_email_audit') IS NULL THEN
                RETURN;
            END IF;
            ALTER TABLE fsma.inbound_email_audit
                DROP CONSTRAINT IF EXISTS inbound_email_audit_status_check;
            ALTER TABLE fsma.inbound_email_audit
                ADD CONSTRAINT inbound_email_audit_status_check
                CHECK (status IN {statuses});
        END $$;
        """.format(statuses=_STATUSES_NEW)
    )


def _restore_status_check() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.inbound_email_audit') IS NULL THEN
                RETURN;
            END IF;
            -- Any row left mid-flight ('processing') at downgrade time would
            -- violate the v121 vocabulary; this feature has not shipped to a
            -- real deployment yet, so unlike the v101 notification_outbox
            -- precedent this does not need a NOT VALID + preserve-existing-
            -- rows dance -- fail loudly instead of silently reinterpreting
            -- an in-flight row's status.
            UPDATE fsma.inbound_email_audit SET status = 'rejected' WHERE status = 'processing';
            ALTER TABLE fsma.inbound_email_audit
                DROP CONSTRAINT IF EXISTS inbound_email_audit_status_check;
            ALTER TABLE fsma.inbound_email_audit
                ADD CONSTRAINT inbound_email_audit_status_check
                CHECK (status IN {statuses});
        END $$;
        """.format(statuses=_STATUSES_OLD)
    )


def _claim_and_finalize_functions() -> None:
    """Claim-then-act replacement for the v121 single-statement write.

    ``claim_inbound_email_audit`` is the ONLY insert path now: it writes the
    row as ``status='processing'`` before any attachment is touched.
    ``ON CONFLICT (message_id) DO NOTHING`` means the loser of a concurrent-
    delivery race gets no row back from ``RETURNING`` and must not proceed
    with CSV ingestion (see ``service.process_inbound_email``).
    ``finalize_inbound_email_audit`` then updates that same row to its real
    outcome -- guarded by ``status = 'processing'`` so it only ever applies
    to the row its own claim produced.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.claim_inbound_email_audit(
            p_tenant_id UUID, p_message_id TEXT, p_sender TEXT, p_recipient TEXT,
            p_subject TEXT, p_attachment_count INT
        ) RETURNS TABLE (id UUID, message_id TEXT, status TEXT)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = fsma, public, pg_temp
        AS $fn$
        BEGIN
            RETURN QUERY
            INSERT INTO fsma.inbound_email_audit AS a
                (tenant_id, message_id, sender, recipient, subject, status, attachment_count)
            VALUES (p_tenant_id, p_message_id, p_sender, p_recipient, p_subject, 'processing', p_attachment_count)
            ON CONFLICT (message_id) DO NOTHING
            RETURNING a.id, a.message_id, a.status;
        END;
        $fn$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION fsma.claim_inbound_email_audit"
        "(UUID, TEXT, TEXT, TEXT, TEXT, INT) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION fsma.claim_inbound_email_audit"
        "(UUID, TEXT, TEXT, TEXT, TEXT, INT) TO regengine"
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.finalize_inbound_email_audit(
            p_message_id TEXT, p_tenant_id UUID, p_status TEXT, p_rejection_reason TEXT,
            p_attachment_count INT, p_accepted_count INT, p_rejected_count INT, p_details JSONB
        ) RETURNS TABLE (id UUID, message_id TEXT, status TEXT, attachment_count INT,
                          accepted_attachment_count INT, rejected_attachment_count INT)
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = fsma, public, pg_temp
        AS $fn$
        BEGIN
            RETURN QUERY
            UPDATE fsma.inbound_email_audit AS a
            SET tenant_id = COALESCE(p_tenant_id, a.tenant_id),
                status = p_status,
                rejection_reason = p_rejection_reason,
                attachment_count = p_attachment_count,
                accepted_attachment_count = p_accepted_count,
                rejected_attachment_count = p_rejected_count,
                details = p_details
            WHERE a.message_id = p_message_id
              AND a.status = 'processing'
            RETURNING a.id, a.message_id, a.status, a.attachment_count,
                      a.accepted_attachment_count, a.rejected_attachment_count;
        END;
        $fn$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION fsma.finalize_inbound_email_audit"
        "(TEXT, UUID, TEXT, TEXT, INT, INT, INT, JSONB) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION fsma.finalize_inbound_email_audit"
        "(TEXT, UUID, TEXT, TEXT, INT, INT, INT, JSONB) TO regengine"
    )


def _drop_claim_and_finalize_functions() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS fsma.finalize_inbound_email_audit"
        "(TEXT, UUID, TEXT, TEXT, INT, INT, INT, JSONB)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS fsma.claim_inbound_email_audit"
        "(UUID, TEXT, TEXT, TEXT, TEXT, INT)"
    )


def _restore_record_function() -> None:
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


def _drop_record_function() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS fsma.record_inbound_email_audit"
        "(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INT, INT, INT, JSONB)"
    )


def upgrade() -> None:
    _add_sender_allowlist()
    _replace_tenant_lookup_function()
    _widen_status_check()
    _claim_and_finalize_functions()
    _drop_record_function()


def downgrade() -> None:
    _restore_record_function()
    _drop_claim_and_finalize_functions()
    _restore_status_check()
    _restore_v121_tenant_lookup_function()
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.tenant_inbound_addresses') IS NULL THEN
                RETURN;
            END IF;
            ALTER TABLE fsma.tenant_inbound_addresses DROP COLUMN IF EXISTS allowed_senders;
        END $$;
        """
    )
