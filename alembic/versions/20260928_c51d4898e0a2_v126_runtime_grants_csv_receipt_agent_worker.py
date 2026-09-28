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
   the statements also need: SELECT on the ON CONFLICT arbiter; EXECUTE on
   the hash helpers the SECURITY INVOKER triggers call and on the
   ``source_hashes`` CHECK helper; SELECT for the receipt trigger's
   chain-head lookup and the bridge's RETURNING; and UPDATE, because that
   lookup was ``SELECT ... FOR UPDATE``. The helpers also called
   ``digest()`` unqualified, and production keeps pgcrypto in a
   provider-owned ``extensions`` schema the runtime role cannot use.

Privilege design — least privilege, RLS policies unchanged:

* ``fsma.manifest_blobs``: column INSERT on exactly the seven columns the
  route writes, so ``storage_url`` and ``created_at`` cannot be forged; no
  SELECT, UPDATE or DELETE (the disabled remediation surface keeps its
  contract). The single-column run foreign key is replaced by a composite
  ``(ingestion_run_id, tenant_id)`` key: a blob can only attach to its own
  tenant's run, even though the tenant policy only checks ``tenant_id``.
* ``fsma.agent_artifacts``: column SELECT (``artifact_id``, ``tenant_id``)
  for the tenant-scoped ``ON CONFLICT (artifact_id, tenant_id)`` arbiter and
  ``RETURNING artifact_id``. Nothing else is readable.
* ``fsma.ingestion_run_receipts``: column SELECT on the five columns the
  trigger lookup and ``RETURNING`` read. Metadata and actor stay unreadable.
* EXECUTE on four pure hash/validation helpers. The three that call
  ``digest()`` become SECURITY DEFINER, owned by the migration owner, with
  ``search_path = pg_catalog, pg_temp`` and a schema-qualified ``digest()``.
  They read no table and have no side effects, so definer rights widen no
  data access; they only reach pgcrypto without giving the runtime role
  USAGE on the extension schema and every other function in it.
  ``sha256_text_array_is_valid`` calls no extension and stays INVOKER.
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
  sequence/previous-hash errors would leak that hash. The definer hash
  helpers are safe because they receive only the row being written.
* Hash inputs and outputs are unchanged, so existing receipts and
  artifacts still verify.

Every deploy reruns ``scripts/apply_runtime_role_cutover.py`` after Alembic
(``scripts/run-migrations.sh``). It revokes all runtime privileges and
rebuilds them from v111's inventory, and it re-creates the hash helpers from
v111's ``_HASH_HELPER_REPAIR`` — so both are registered there (as v113 and
v121 did for grants). This revision applies the same repair and grants so a
plain ``alembic upgrade head`` converges without the cutover.

The foreign key is validated as the NOBYPASSRLS owner with the v116/v120
pattern: FORCE RLS would apply the tenant policies to the owner, whose
``get_tenant_context()`` raises without a tenant. Rows that would violate
the new key abort the migration with their count; nothing is deleted.
``runbooks/predeploy-v126-misattached-blobs.sql`` lists them beforehand from
a provider superuser/BYPASSRLS session.

Downgrade restores the single-column foreign key, revokes exactly these
grants, and restores the prior function definitions byte-for-byte (v079
receipt helpers and trigger, v111's invoker ``compute_agent_artifact_hash``).

Revision ID: c51d4898e0a2
Revises: 22a278f6dc78
Create Date: 2026-09-28
"""

import importlib.util
from contextlib import contextmanager
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision = "c51d4898e0a2"  # pragma: allowlist secret
down_revision = "22a278f6dc78"  # pragma: allowlist secret
branch_labels = None
depends_on = None


_RECEIPT_HASH_SIGNATURE = (
    "fsma.compute_ingestion_run_receipt_hash("
    "uuid, uuid, bigint, text, timestamptz, text, text, uuid, uuid, uuid, uuid, text, text)"
)
# The digest() callers; v111's _HASH_HELPER_REPAIR makes them pinned definers.
_DEFINER_HASH_HELPERS = (
    "fsma.compute_agent_artifact_hash(jsonb)",
    "fsma.compute_ingestion_run_receipt_payload_hash(jsonb)",
    _RECEIPT_HASH_SIGNATURE,
)
# Exactly the columns webhook_compat._open_ingestion_run inserts.
_BLOB_INSERT_COLUMNS = "ingestion_run_id, tenant_id, raw_bytes, sha256, original_filename, content_type, uploaded_by"
_ARTIFACT_SELECT_COLUMNS = "artifact_id, tenant_id"
_RECEIPT_SELECT_COLUMNS = "receipt_id, tenant_id, ingestion_run_id, sequence_num, receipt_hash"

# (grant, matching revoke). Keep in lockstep with v111's inventory; the
# direct-role CI gate compares the live ACLs against that inventory.
_RUNTIME_GRANTS = (
    (
        f"GRANT INSERT ({_BLOB_INSERT_COLUMNS}) ON TABLE fsma.manifest_blobs TO regengine",
        f"REVOKE INSERT ({_BLOB_INSERT_COLUMNS}) ON TABLE fsma.manifest_blobs FROM regengine",
    ),
    (
        f"GRANT SELECT ({_ARTIFACT_SELECT_COLUMNS}) ON TABLE fsma.agent_artifacts TO regengine",
        f"REVOKE SELECT ({_ARTIFACT_SELECT_COLUMNS}) ON TABLE fsma.agent_artifacts FROM regengine",
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

_BLOB_RUN_TENANT_FK = "fk_manifest_blobs_run_tenant"
_LEGACY_BLOB_RUN_FK = "manifest_blobs_ingestion_run_id_fkey"
# Bounds how long the ingestion tables can queue behind the ALTER TABLE
# locks; a busy deploy fails fast and is retried instead of stalling ingest.
_LOCK_TIMEOUT = "10s"

_BLOBS_OFF_THEIR_TENANT_RUN = """
SELECT pg_catalog.count(*)
  FROM fsma.manifest_blobs AS blob
 WHERE NOT EXISTS (
       SELECT 1
         FROM fsma.ingestion_runs AS run
        WHERE run.id = blob.ingestion_run_id
          AND run.tenant_id = blob.tenant_id
 )
"""

_SINGLE_COLUMN_BLOB_RUN_FKS = """
SELECT pg_catalog.quote_ident(con.conname)
  FROM pg_catalog.pg_constraint AS con
 WHERE con.conrelid = 'fsma.manifest_blobs'::regclass
   AND con.contype = 'f'
   AND con.confrelid = 'fsma.ingestion_runs'::regclass
   AND con.conkey = ARRAY[(
       SELECT attnum
         FROM pg_catalog.pg_attribute
        WHERE attrelid = 'fsma.manifest_blobs'::regclass
          AND attname = 'ingestion_run_id'
   )]
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


# Verbatim 22a278f6dc78 definition of compute_agent_artifact_hash (v111's
# former invoker repair), so a downgrade restores the exact prior body.
_V111_AGENT_ARTIFACT_HASH = """
DO $repair$
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
        CREATE OR REPLACE FUNCTION fsma.compute_agent_artifact_hash(
            p_artifact jsonb
        ) RETURNS text
        LANGUAGE sql
        IMMUTABLE
        AS $function$
            SELECT pg_catalog.encode(
                %I.digest(
                    COALESCE(p_artifact, '{}'::jsonb)::text,
                    'sha256'::text
                ),
                'hex'::text
            )
        $function$
        $ddl$,
        pgcrypto_schema
    );
END
$repair$;
"""


def _hash_helper_repair() -> str:
    """The helper DDL the per-deploy cutover reapplies (single source of truth).

    ``scripts/apply_runtime_role_cutover.py`` loads v111 the same way and
    replays ``_HASH_HELPER_REPAIR`` after every migration run, so applying it
    here keeps a plain ``alembic upgrade head`` identical to a deploy.
    """
    path = Path(__file__).with_name("20260803_b71d9e4c2a60_v111_runtime_role_grants.py")
    spec = importlib.util.spec_from_file_location("regengine_v111_cutover_for_v126", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the v111 cutover from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._HASH_HELPER_REPAIR


@contextmanager
def _owner_validates_blob_runs():
    """Let the NOBYPASSRLS owner see manifest_blobs/ingestion_runs rows.

    FORCE RLS applies the tenant policies to the table owner too, and their
    get_tenant_context() raises without app.tenant_id, so a foreign-key
    validation fails as the dedicated owner. As in v116/v120, NO FORCE is
    scoped to this transaction: ALTER TABLE holds its lock until commit, so
    no other session can observe it, and a failure rolls everything back.
    """
    conn = op.get_bind()
    previous_lock_timeout = conn.execute(sa.text("SELECT pg_catalog.current_setting('lock_timeout')")).scalar_one()
    conn.execute(sa.text("SELECT pg_catalog.set_config('lock_timeout', :value, true)"), {"value": _LOCK_TIMEOUT})
    forced = (
        conn.execute(
            sa.text(
                """SELECT pg_catalog.format('%I.%I', n.nspname, c.relname)
                     FROM pg_catalog.pg_class AS c
                     JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE c.oid IN ('fsma.ingestion_runs'::regclass,
                                    'fsma.manifest_blobs'::regclass)
                      AND c.relforcerowsecurity
                    ORDER BY 1"""
            )
        )
        .scalars()
        .all()
    )
    for table in forced:
        # Names come only from the two fixed regclass values above.
        conn.execute(sa.text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
    yield conn
    for table in forced:
        conn.execute(sa.text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
    conn.execute(
        sa.text("SELECT pg_catalog.set_config('lock_timeout', :value, true)"),
        {"value": previous_lock_timeout},
    )


def _constraint_exists(conn, name: str) -> bool:
    return conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint "
            "WHERE conrelid = 'fsma.manifest_blobs'::regclass AND conname = :name)"
        ),
        {"name": name},
    ).scalar_one()


_PREDEPLOY_RUNBOOK = "runbooks/predeploy-v126-misattached-blobs.sql"


def _misattached_blobs_refusal(count: int) -> str:
    """Operator guidance when existing rows would violate the new key.

    A plain schema-owner session cannot review them: under FORCE RLS it
    errors without app.tenant_id, and with a tenant it sees no
    ingestion_runs rows (those policies are TO the runtime roles), so every
    blob of that tenant would look misattached.
    """
    return (
        f"v126: {count} fsma.manifest_blobs row(s) are not attached to an ingestion run of "
        "their own tenant; refusing to add the (ingestion_run_id, tenant_id) foreign key. "
        "Nothing was changed or deleted. List them with "
        f"{_PREDEPLOY_RUNBOOK} from a provider superuser or BYPASSRLS session, or as "
        "the schema owner only after ALTER TABLE fsma.ingestion_runs / fsma.manifest_blobs "
        "NO FORCE ROW LEVEL SECURITY inside a transaction that is rolled back. A plain "
        "schema-owner session gives wrong per-tenant results under FORCE RLS (it sees no "
        "ingestion runs and flags every blob of the tenant) -- do not delete evidence on "
        "that basis."
    )


def _pin_blobs_to_their_tenant_run() -> None:
    with _owner_validates_blob_runs() as conn:
        misattached = conn.execute(sa.text(_BLOBS_OFF_THEIR_TENANT_RUN)).scalar_one()
        if misattached:
            raise RuntimeError(_misattached_blobs_refusal(misattached))
        for quoted_name in conn.execute(sa.text(_SINGLE_COLUMN_BLOB_RUN_FKS)).scalars().all():
            conn.execute(sa.text(f"ALTER TABLE fsma.manifest_blobs DROP CONSTRAINT {quoted_name}"))
        if not _constraint_exists(conn, _BLOB_RUN_TENANT_FK):
            conn.execute(
                sa.text(
                    f"""ALTER TABLE fsma.manifest_blobs
                        ADD CONSTRAINT {_BLOB_RUN_TENANT_FK}
                        FOREIGN KEY (ingestion_run_id, tenant_id)
                        REFERENCES fsma.ingestion_runs (id, tenant_id)
                        ON DELETE CASCADE"""
                )
            )


def _restore_single_column_blob_fk() -> None:
    with _owner_validates_blob_runs() as conn:
        conn.execute(sa.text(f"ALTER TABLE fsma.manifest_blobs DROP CONSTRAINT IF EXISTS {_BLOB_RUN_TENANT_FK}"))
        if not conn.execute(sa.text(_SINGLE_COLUMN_BLOB_RUN_FKS)).scalars().all():
            conn.execute(
                sa.text(
                    f"""ALTER TABLE fsma.manifest_blobs
                        ADD CONSTRAINT {_LEGACY_BLOB_RUN_FK}
                        FOREIGN KEY (ingestion_run_id)
                        REFERENCES fsma.ingestion_runs (id)
                        ON DELETE CASCADE"""
                )
            )


def upgrade() -> None:
    # CREATE OR REPLACE keeps each function's owner and ACL, and every
    # statement is convergent, so a rerun after partial drift is safe.
    op.execute(_hash_helper_repair())
    op.execute(_PARENT_LOCKED_RECEIPT_TRIGGER)
    for signature in _DEFINER_HASH_HELPERS:
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
    for grant, _revoke in _RUNTIME_GRANTS:
        op.execute(grant)
    _pin_blobs_to_their_tenant_run()


def downgrade() -> None:
    _restore_single_column_blob_fk()
    for _grant, revoke in reversed(_RUNTIME_GRANTS):
        op.execute(revoke)
    op.execute(_V079_FUNCTIONS)
    op.execute(_V111_AGENT_ARTIFACT_HASH)
