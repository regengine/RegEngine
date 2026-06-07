"""v079 -- append-only ingestion run receipt ledger.

Revision ID: c1d2e3f4a5b6
Revises: 8a9b0c1d2e3f
Create Date: 2026-05-13

Extends the existing ``fsma.ingestion_runs`` spine with a tenant-scoped,
append-only receipt table. Each receipt records one state transition and is
hash-linked to the previous receipt for the same ingestion run.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c1d2e3f4a5b6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "8a9b0c1d2e3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INGESTION_RUN_RECEIPTS_SQL = """
CREATE SCHEMA IF NOT EXISTS fsma;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE UNIQUE INDEX IF NOT EXISTS ux_ingestion_runs_id_tenant
    ON fsma.ingestion_runs (id, tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_traceability_events_event_tenant
    ON fsma.traceability_events (event_id, tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_evidence_attachments_id_tenant
    ON fsma.evidence_attachments (id, tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_rule_evaluations_id_tenant
    ON fsma.rule_evaluations (evaluation_id, tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fda_export_log_id_tenant
    ON fsma.fda_export_log (id, tenant_id);

CREATE OR REPLACE FUNCTION fsma.compute_ingestion_run_receipt_payload_hash(
    p_metadata JSONB
) RETURNS TEXT
LANGUAGE SQL
AS $$
    SELECT encode(digest(COALESCE(p_metadata, '{}'::jsonb)::text, 'sha256'), 'hex')
$$;

CREATE OR REPLACE FUNCTION fsma.compute_ingestion_run_receipt_hash(
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
$$;

CREATE TABLE IF NOT EXISTS fsma.ingestion_run_receipts (
    receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    ingestion_run_id UUID NOT NULL,

    sequence_num BIGINT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'received',
        'validated',
        'canonicalized',
        'evidence_persisted',
        'rule_evaluated',
        'export_ready',
        'export_generated',
        'failed',
        'needs_review'
    )),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor TEXT NOT NULL DEFAULT 'system',
    request_id TEXT,

    canonical_event_id UUID,
    evidence_attachment_id UUID,
    rule_evaluation_id UUID,
    export_log_id UUID,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_hash TEXT NOT NULL CHECK (payload_hash ~ '^[A-Fa-f0-9]{64}$'),
    previous_receipt_hash TEXT CHECK (
        previous_receipt_hash IS NULL
        OR previous_receipt_hash ~ '^[A-Fa-f0-9]{64}$'
    ),
    receipt_hash TEXT NOT NULL CHECK (receipt_hash ~ '^[A-Fa-f0-9]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_ingestion_run_receipts_run_tenant
        FOREIGN KEY (ingestion_run_id, tenant_id)
        REFERENCES fsma.ingestion_runs (id, tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_ingestion_run_receipts_event_tenant
        FOREIGN KEY (canonical_event_id, tenant_id)
        REFERENCES fsma.traceability_events (event_id, tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_ingestion_run_receipts_evidence_tenant
        FOREIGN KEY (evidence_attachment_id, tenant_id)
        REFERENCES fsma.evidence_attachments (id, tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_ingestion_run_receipts_rule_eval_tenant
        FOREIGN KEY (rule_evaluation_id, tenant_id)
        REFERENCES fsma.rule_evaluations (evaluation_id, tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_ingestion_run_receipts_export_tenant
        FOREIGN KEY (export_log_id, tenant_id)
        REFERENCES fsma.fda_export_log (id, tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT ux_ingestion_run_receipts_run_sequence
        UNIQUE (tenant_id, ingestion_run_id, sequence_num),
    CONSTRAINT ux_ingestion_run_receipts_hash
        UNIQUE (tenant_id, receipt_hash)
);

CREATE INDEX IF NOT EXISTS idx_ingestion_run_receipts_tenant_run
    ON fsma.ingestion_run_receipts (tenant_id, ingestion_run_id, sequence_num);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_receipts_tenant_state
    ON fsma.ingestion_run_receipts (tenant_id, state, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_run_receipts_event
    ON fsma.ingestion_run_receipts (tenant_id, canonical_event_id)
    WHERE canonical_event_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ingestion_run_receipts_evidence
    ON fsma.ingestion_run_receipts (tenant_id, evidence_attachment_id)
    WHERE evidence_attachment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ingestion_run_receipts_rule_eval
    ON fsma.ingestion_run_receipts (tenant_id, rule_evaluation_id)
    WHERE rule_evaluation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ingestion_run_receipts_export
    ON fsma.ingestion_run_receipts (tenant_id, export_log_id)
    WHERE export_log_id IS NOT NULL;

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

DROP TRIGGER IF EXISTS ingestion_run_receipts_prepare
    ON fsma.ingestion_run_receipts;
CREATE TRIGGER ingestion_run_receipts_prepare
    BEFORE INSERT ON fsma.ingestion_run_receipts
    FOR EACH ROW EXECUTE FUNCTION fsma.prepare_ingestion_run_receipt();

CREATE OR REPLACE FUNCTION fsma.prevent_ingestion_run_receipt_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'ingestion_run_receipts is append-only. Operation % rejected.',
        TG_OP
        USING ERRCODE = 'check_violation';
END;
$$;

DROP TRIGGER IF EXISTS ingestion_run_receipts_append_only
    ON fsma.ingestion_run_receipts;
CREATE TRIGGER ingestion_run_receipts_append_only
    BEFORE UPDATE OR DELETE ON fsma.ingestion_run_receipts
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_ingestion_run_receipt_mutation();

ALTER TABLE fsma.ingestion_run_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.ingestion_run_receipts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_ingestion_run_receipts
    ON fsma.ingestion_run_receipts;
CREATE POLICY tenant_isolation_ingestion_run_receipts
    ON fsma.ingestion_run_receipts
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context())
    WITH CHECK (tenant_id = get_tenant_context());

REVOKE UPDATE, DELETE, TRUNCATE ON fsma.ingestion_run_receipts FROM PUBLIC;

COMMENT ON TABLE fsma.ingestion_run_receipts IS
    'Tenant-scoped append-only state receipt ledger for ingestion runs.';
COMMENT ON COLUMN fsma.ingestion_run_receipts.previous_receipt_hash IS
    'Hash of the previous receipt for the same ingestion run; NULL for sequence 1.';
COMMENT ON COLUMN fsma.ingestion_run_receipts.receipt_hash IS
    'SHA-256 hash over receipt identity, state, links, payload hash, and previous receipt hash.';
COMMENT ON COLUMN fsma.ingestion_run_receipts.payload_hash IS
    'SHA-256 hash of the receipt metadata JSONB payload.';
"""


def upgrade() -> None:
    op.execute(_INGESTION_RUN_RECEIPTS_SQL)


def downgrade() -> None:
    """Non-destructive ledger migration; preserve receipts once created."""
    pass
