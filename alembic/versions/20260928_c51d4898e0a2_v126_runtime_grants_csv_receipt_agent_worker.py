"""v126 — grant the runtime role what CSV ingest and the artifact worker write.

Two release-enabled paths run as the restricted ``regengine`` role and fail
at 22a278f6dc78:

1. ``POST /api/v1/ingest/csv`` (#3122) retains every upload in
   ``fsma.manifest_blobs`` inside the ingest transaction
   (``services/ingestion/app/webhook_compat.py::_open_ingestion_run``).
   v111's closed inventory grants that table nothing, so every upload is
   rolled back with ``permission denied for table manifest_blobs`` (HTTP 500).
2. The ``agent_artifact_review`` TaskWorker handler
   (``shared.agent_task_bridge.handle_agent_artifact_task``) writes
   ``fsma.agent_artifacts`` and a ledger receipt in
   ``fsma.ingestion_run_receipts``. v111 granted bare INSERT on both, but
   the statements also need: SELECT on the ``ON CONFLICT (artifact_id)``
   arbiter; EXECUTE on the hash helpers the SECURITY INVOKER triggers call
   and on the ``source_hashes`` CHECK helper; SELECT for the receipt
   trigger's chain-head lookup and the bridge's ``RETURNING``; and UPDATE,
   because that lookup was ``SELECT ... FOR UPDATE``. The receipt hashes
   also called ``digest()`` unqualified, which fails from the application's
   default search_path when pgcrypto lives in ``fsma`` or ``extensions``.

Privilege design — least privilege, invoker rights, policies unchanged:

* ``fsma.manifest_blobs``: INSERT only. The route's INSERT has no
  RETURNING, ON CONFLICT or sub-select; reads, updates and deletes stay
  denied, so the disabled remediation surface keeps its contract. The
  table's FORCE RLS tenant policy governs the write.
* ``fsma.agent_artifacts``: column SELECT (``artifact_id``) — the arbiter
  column only.
* ``fsma.ingestion_run_receipts``: column SELECT on the five columns the
  trigger lookup and ``RETURNING`` read. Metadata and actor stay unreadable.
* EXECUTE on four pure hash/validation helpers. They read no table, have
  no side effects and cannot arm tenant or admin context.
* No UPDATE on the append-only ledger. The receipt trigger now serialises
  appends by locking the parent ``fsma.ingestion_runs`` row
  (``FOR NO KEY UPDATE``), which the runtime role may already update under
  its tenant policy. Locking the latest receipt could not serialise the
  first append of a run (there is no row to lock); the parent lock can,
  and the lookup that follows it sees any append committed while it waited.
* The trigger functions stay SECURITY INVOKER. A definer trigger would run
  as the FORCE-RLS table owner, which has no policy (the chain-head lookup
  would see nothing), and would read another tenant's chain head before
  the WITH CHECK policy rejects a forged ``tenant_id`` — its
  sequence/previous-hash errors would leak that hash.
* ``digest()`` is qualified with pgcrypto's catalog namespace, resolved at
  migration time (the v111 precedent for ``compute_agent_artifact_hash``).
  Hash inputs and output are unchanged, so existing receipts still verify.

Every deploy reruns ``scripts/apply_runtime_role_cutover.py`` after Alembic
(``scripts/run-migrations.sh``). It revokes all runtime privileges and
rebuilds them from v111's inventory, so a grant that lived only here would
be revoked on the next deploy. The grants are therefore registered in
v111's ``REGENGINE_TABLE_GRANTS`` / ``REGENGINE_COLUMN_GRANTS`` /
``_FUNCTION_GRANTS`` (as v113 and v121 did); this revision applies the same
grants so a plain ``alembic upgrade head`` converges without the cutover.

Downgrade revokes exactly these grants and restores the v079 function
bodies verbatim.

Revision ID: c51d4898e0a2
Revises: 22a278f6dc78
Create Date: 2026-09-28
"""

from alembic import op

revision = "c51d4898e0a2"  # pragma: allowlist secret
down_revision = "22a278f6dc78"  # pragma: allowlist secret
branch_labels = None
depends_on = None


_RECEIPT_HASH_SIGNATURE = (
    "fsma.compute_ingestion_run_receipt_hash("
    "uuid, uuid, bigint, text, timestamptz, text, text, uuid, uuid, uuid, uuid, text, text)"
)
_RECEIPT_SELECT_COLUMNS = "receipt_id, tenant_id, ingestion_run_id, sequence_num, receipt_hash"

# (grant, matching revoke). Keep in lockstep with v111's inventory; the
# direct-role CI gate compares the live ACLs against that inventory.
_RUNTIME_GRANTS = (
    (
        "GRANT INSERT ON TABLE fsma.manifest_blobs TO regengine",
        "REVOKE INSERT ON TABLE fsma.manifest_blobs FROM regengine",
    ),
    (
        "GRANT SELECT (artifact_id) ON TABLE fsma.agent_artifacts TO regengine",
        "REVOKE SELECT (artifact_id) ON TABLE fsma.agent_artifacts FROM regengine",
    ),
    (
        f"GRANT SELECT ({_RECEIPT_SELECT_COLUMNS}) ON TABLE fsma.ingestion_run_receipts TO regengine",
        f"REVOKE SELECT ({_RECEIPT_SELECT_COLUMNS}) ON TABLE fsma.ingestion_run_receipts FROM regengine",
    ),
    (
        "GRANT EXECUTE ON FUNCTION fsma.compute_agent_artifact_hash(jsonb) TO regengine",
        "REVOKE EXECUTE ON FUNCTION fsma.compute_agent_artifact_hash(jsonb) FROM regengine",
    ),
    (
        "GRANT EXECUTE ON FUNCTION fsma.sha256_text_array_is_valid(text[]) TO regengine",
        "REVOKE EXECUTE ON FUNCTION fsma.sha256_text_array_is_valid(text[]) FROM regengine",
    ),
    (
        "GRANT EXECUTE ON FUNCTION fsma.compute_ingestion_run_receipt_payload_hash(jsonb) TO regengine",
        "REVOKE EXECUTE ON FUNCTION fsma.compute_ingestion_run_receipt_payload_hash(jsonb) FROM regengine",
    ),
    (
        f"GRANT EXECUTE ON FUNCTION {_RECEIPT_HASH_SIGNATURE} TO regengine",
        f"REVOKE EXECUTE ON FUNCTION {_RECEIPT_HASH_SIGNATURE} FROM regengine",
    ),
)


# Same inputs, same canonical JSON, same SHA-256 as v079; only name
# resolution changes (pgcrypto's namespace and pg_catalog are explicit).
_QUALIFIED_RECEIPT_HASHES = """
DO $receipt_hashes$
DECLARE
    pgcrypto_schema name;
BEGIN
    SELECT n.nspname
      INTO STRICT pgcrypto_schema
      FROM pg_extension AS e
      JOIN pg_namespace AS n ON n.oid = e.extnamespace
     WHERE e.extname = 'pgcrypto';

    EXECUTE format(
        $ddl$
        CREATE OR REPLACE FUNCTION fsma.compute_ingestion_run_receipt_payload_hash(
            p_metadata jsonb
        ) RETURNS text
        LANGUAGE sql
        AS $function$
            SELECT pg_catalog.encode(
                %I.digest(
                    COALESCE(p_metadata, '{}'::jsonb)::text,
                    'sha256'::text
                ),
                'hex'::text
            )
        $function$
        $ddl$,
        pgcrypto_schema
    );

    EXECUTE format(
        $ddl$
        CREATE OR REPLACE FUNCTION fsma.compute_ingestion_run_receipt_hash(
            p_tenant_id uuid,
            p_ingestion_run_id uuid,
            p_sequence_num bigint,
            p_state text,
            p_occurred_at timestamptz,
            p_actor text,
            p_request_id text,
            p_canonical_event_id uuid,
            p_evidence_attachment_id uuid,
            p_rule_evaluation_id uuid,
            p_export_log_id uuid,
            p_payload_hash text,
            p_previous_receipt_hash text
        ) RETURNS text
        LANGUAGE sql
        AS $function$
            SELECT pg_catalog.encode(
                %I.digest(
                    pg_catalog.jsonb_build_object(
                        'tenant_id', p_tenant_id::text,
                        'ingestion_run_id', p_ingestion_run_id::text,
                        'sequence_num', p_sequence_num,
                        'state', p_state,
                        'occurred_at_utc',
                            pg_catalog.to_char(
                                p_occurred_at AT TIME ZONE 'UTC',
                                'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                            ),
                        'actor', p_actor,
                        'request_id', p_request_id,
                        'canonical_event_id', p_canonical_event_id::text,
                        'evidence_attachment_id', p_evidence_attachment_id::text,
                        'rule_evaluation_id', p_rule_evaluation_id::text,
                        'export_log_id', p_export_log_id::text,
                        'payload_hash', p_payload_hash,
                        'previous_receipt_hash', p_previous_receipt_hash
                    )::text,
                    'sha256'::text
                ),
                'hex'::text
            )
        $function$
        $ddl$,
        pgcrypto_schema
    );
END
$receipt_hashes$;
"""


# The body after the chain-head lookup is v079's, unchanged.
_PARENT_LOCKED_RECEIPT_TRIGGER = """
CREATE OR REPLACE FUNCTION fsma.prepare_ingestion_run_receipt()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    expected_previous_hash TEXT;
    expected_sequence BIGINT;
BEGIN
    -- Serialise appends per run on the parent run row. This takes the
    -- caller's UPDATE privilege and tenant policy on fsma.ingestion_runs
    -- (never on the append-only ledger), and it also covers the first
    -- append of a run, when there is no receipt row to lock. Under the
    -- caller's RLS another tenant's run is invisible and nothing is locked;
    -- that insert is then rejected by the WITH CHECK policy or the
    -- (ingestion_run_id, tenant_id) foreign key.
    PERFORM 1
       FROM fsma.ingestion_runs
      WHERE id = NEW.ingestion_run_id
        AND tenant_id = NEW.tenant_id
      FOR NO KEY UPDATE;

    -- A fresh statement snapshot: sees any append that committed while
    -- this transaction waited for the run lock.
    SELECT receipt_hash, sequence_num + 1
    INTO expected_previous_hash, expected_sequence
    FROM fsma.ingestion_run_receipts
    WHERE tenant_id = NEW.tenant_id
      AND ingestion_run_id = NEW.ingestion_run_id
    ORDER BY sequence_num DESC
    LIMIT 1;

    expected_sequence := COALESCE(expected_sequence, 1);

    IF NEW.sequence_num IS NULL THEN
        NEW.sequence_num := expected_sequence;
    END IF;

    IF NEW.sequence_num <> expected_sequence THEN
        RAISE EXCEPTION
            'ingestion_run_receipts sequence gap for run %, expected %, got %',
            NEW.ingestion_run_id, expected_sequence, NEW.sequence_num
            USING ERRCODE = 'check_violation';
    END IF;

    IF expected_previous_hash IS NULL AND NEW.previous_receipt_hash IS NOT NULL THEN
        RAISE EXCEPTION
            'first ingestion_run_receipt for run % must not provide previous_receipt_hash',
            NEW.ingestion_run_id
            USING ERRCODE = 'check_violation';
    END IF;

    IF expected_previous_hash IS NOT NULL
       AND NEW.previous_receipt_hash IS NOT NULL
       AND NEW.previous_receipt_hash <> expected_previous_hash THEN
        RAISE EXCEPTION
            'previous_receipt_hash mismatch for run %, expected %, got %',
            NEW.ingestion_run_id, expected_previous_hash, NEW.previous_receipt_hash
            USING ERRCODE = 'check_violation';
    END IF;

    NEW.previous_receipt_hash := expected_previous_hash;
    NEW.payload_hash := fsma.compute_ingestion_run_receipt_payload_hash(NEW.metadata);
    NEW.receipt_hash := fsma.compute_ingestion_run_receipt_hash(
        NEW.tenant_id,
        NEW.ingestion_run_id,
        NEW.sequence_num,
        NEW.state,
        NEW.occurred_at,
        NEW.actor,
        NEW.request_id,
        NEW.canonical_event_id,
        NEW.evidence_attachment_id,
        NEW.rule_evaluation_id,
        NEW.export_log_id,
        NEW.payload_hash,
        NEW.previous_receipt_hash
    );

    RETURN NEW;
END;
$$;
"""


# Verbatim v079 (c1d2e3f4a5b6) definitions, byte-for-byte, so a downgrade
# leaves the exact prior function bodies.
_V079_RECEIPT_PAYLOAD_HASH = """CREATE OR REPLACE FUNCTION fsma.compute_ingestion_run_receipt_payload_hash(
    p_metadata JSONB
) RETURNS TEXT
LANGUAGE SQL
AS $$
    SELECT encode(digest(COALESCE(p_metadata, '{}'::jsonb)::text, 'sha256'), 'hex')
$$"""

_V079_RECEIPT_HASH = """CREATE OR REPLACE FUNCTION fsma.compute_ingestion_run_receipt_hash(
    p_tenant_id UUID,
    p_ingestion_run_id UUID,
    p_sequence_num BIGINT,
    p_state TEXT,
    p_occurred_at TIMESTAMPTZ,
    p_actor TEXT,
    p_request_id TEXT,
    p_canonical_event_id UUID,
    p_evidence_attachment_id UUID,
    p_rule_evaluation_id UUID,
    p_export_log_id UUID,
    p_payload_hash TEXT,
    p_previous_receipt_hash TEXT
) RETURNS TEXT
LANGUAGE SQL
AS $$
    SELECT encode(
        digest(
            jsonb_build_object(
                'tenant_id', p_tenant_id::text,
                'ingestion_run_id', p_ingestion_run_id::text,
                'sequence_num', p_sequence_num,
                'state', p_state,
                'occurred_at_utc',
                    to_char(
                        p_occurred_at AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                    ),
                'actor', p_actor,
                'request_id', p_request_id,
                'canonical_event_id', p_canonical_event_id::text,
                'evidence_attachment_id', p_evidence_attachment_id::text,
                'rule_evaluation_id', p_rule_evaluation_id::text,
                'export_log_id', p_export_log_id::text,
                'payload_hash', p_payload_hash,
                'previous_receipt_hash', p_previous_receipt_hash
            )::text,
            'sha256'
        ),
        'hex'
    )
$$"""


def _without_body_check(ddl: str) -> str:
    """Recreate an unqualified-digest() body without resolving it now.

    The v079 bodies call digest() unqualified; with check_function_bodies on,
    CREATE would fail whenever pgcrypto's schema is not on the downgrade
    session's search_path. The setting is restored in the same block.
    """
    return f"""
DO $restore_v079$
DECLARE
    previous_check text := current_setting('check_function_bodies');
BEGIN
    PERFORM set_config('check_function_bodies', 'off', true);
    EXECUTE $v079_ddl${ddl}$v079_ddl$;
    PERFORM set_config('check_function_bodies', previous_check, true);
END
$restore_v079$;
"""


_V079_FUNCTIONS = (
    _without_body_check(_V079_RECEIPT_PAYLOAD_HASH)
    + _without_body_check(_V079_RECEIPT_HASH)
    + """
CREATE OR REPLACE FUNCTION fsma.prepare_ingestion_run_receipt()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    expected_previous_hash TEXT;
    expected_sequence BIGINT;
BEGIN
    SELECT receipt_hash, sequence_num + 1
    INTO expected_previous_hash, expected_sequence
    FROM fsma.ingestion_run_receipts
    WHERE tenant_id = NEW.tenant_id
      AND ingestion_run_id = NEW.ingestion_run_id
    ORDER BY sequence_num DESC
    LIMIT 1
    FOR UPDATE;

    expected_sequence := COALESCE(expected_sequence, 1);

    IF NEW.sequence_num IS NULL THEN
        NEW.sequence_num := expected_sequence;
    END IF;

    IF NEW.sequence_num <> expected_sequence THEN
        RAISE EXCEPTION
            'ingestion_run_receipts sequence gap for run %, expected %, got %',
            NEW.ingestion_run_id, expected_sequence, NEW.sequence_num
            USING ERRCODE = 'check_violation';
    END IF;

    IF expected_previous_hash IS NULL AND NEW.previous_receipt_hash IS NOT NULL THEN
        RAISE EXCEPTION
            'first ingestion_run_receipt for run % must not provide previous_receipt_hash',
            NEW.ingestion_run_id
            USING ERRCODE = 'check_violation';
    END IF;

    IF expected_previous_hash IS NOT NULL
       AND NEW.previous_receipt_hash IS NOT NULL
       AND NEW.previous_receipt_hash <> expected_previous_hash THEN
        RAISE EXCEPTION
            'previous_receipt_hash mismatch for run %, expected %, got %',
            NEW.ingestion_run_id, expected_previous_hash, NEW.previous_receipt_hash
            USING ERRCODE = 'check_violation';
    END IF;

    NEW.previous_receipt_hash := expected_previous_hash;
    NEW.payload_hash := fsma.compute_ingestion_run_receipt_payload_hash(NEW.metadata);
    NEW.receipt_hash := fsma.compute_ingestion_run_receipt_hash(
        NEW.tenant_id,
        NEW.ingestion_run_id,
        NEW.sequence_num,
        NEW.state,
        NEW.occurred_at,
        NEW.actor,
        NEW.request_id,
        NEW.canonical_event_id,
        NEW.evidence_attachment_id,
        NEW.rule_evaluation_id,
        NEW.export_log_id,
        NEW.payload_hash,
        NEW.previous_receipt_hash
    );

    RETURN NEW;
END;
$$;
"""
)


def upgrade() -> None:
    # CREATE OR REPLACE keeps each function's owner and ACL, and every
    # statement is convergent, so a rerun after partial drift is safe.
    op.execute(_QUALIFIED_RECEIPT_HASHES)
    op.execute(_PARENT_LOCKED_RECEIPT_TRIGGER)
    for grant, _revoke in _RUNTIME_GRANTS:
        op.execute(grant)


def downgrade() -> None:
    for _grant, revoke in reversed(_RUNTIME_GRANTS):
        op.execute(revoke)
    op.execute(_V079_FUNCTIONS)
