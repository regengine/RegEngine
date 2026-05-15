"""v080 -- agent artifact operator persistence.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-05-13

Adds tenant-scoped persistence for advisory agent artifacts and operator
review outcomes. Existing ingestion run and receipt tables remain the ledger
source of truth; these tables link agent activity back to that spine without
allowing agents to mutate canonical evidence.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d2e3f4a5b6c7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_AGENT_ARTIFACT_OPERATOR_PERSISTENCE_SQL = """
CREATE SCHEMA IF NOT EXISTS fsma;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE UNIQUE INDEX IF NOT EXISTS ux_ingestion_run_receipts_id_tenant
    ON fsma.ingestion_run_receipts (receipt_id, tenant_id);

CREATE OR REPLACE FUNCTION fsma.sha256_text_array_is_valid(
    p_values TEXT[]
) RETURNS BOOLEAN
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT COALESCE(
        (
            SELECT bool_and(value ~ '^[A-Fa-f0-9]{64}$')
            FROM unnest(COALESCE(p_values, ARRAY[]::text[])) AS value
        ),
        TRUE
    )
$$;

CREATE OR REPLACE FUNCTION fsma.compute_agent_artifact_hash(
    p_artifact JSONB
) RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT encode(digest(COALESCE(p_artifact, '{}'::jsonb)::text, 'sha256'), 'hex')
$$;

CREATE TABLE IF NOT EXISTS fsma.agent_artifacts (
    artifact_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,

    artifact_version TEXT NOT NULL CHECK (artifact_version = 'agent-artifact.v1'),
    artifact_type TEXT NOT NULL CHECK (artifact_type IN (
        'field_mapping_suggestion',
        'identity_match_suggestion',
        'validation_explanation',
        'review_routing_suggestion',
        'export_readiness_summary'
    )),
    created_at TIMESTAMPTZ NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    agent_name TEXT NOT NULL CHECK (length(agent_name) > 0),
    agent_version TEXT NOT NULL CHECK (length(agent_version) > 0),
    model_name TEXT,
    suggestion TEXT NOT NULL CHECK (length(suggestion) > 0),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
    requires_human_review BOOLEAN NOT NULL,

    evidence_ids UUID[] NOT NULL DEFAULT ARRAY[]::uuid[],
    canonical_event_ids UUID[] NOT NULL DEFAULT ARRAY[]::uuid[],
    ingestion_run_id UUID,
    source_hashes TEXT[] NOT NULL DEFAULT ARRAY[]::text[],
    rule_id TEXT,
    rule_version INTEGER CHECK (rule_version >= 1),
    citation_reference TEXT,
    request_id TEXT,

    artifact JSONB NOT NULL CHECK (jsonb_typeof(artifact) = 'object'),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    artifact_hash TEXT NOT NULL CHECK (artifact_hash ~ '^[A-Fa-f0-9]{64}$'),

    CONSTRAINT ux_agent_artifacts_artifact_tenant
        UNIQUE (artifact_id, tenant_id),
    CONSTRAINT fk_agent_artifacts_run_tenant
        FOREIGN KEY (ingestion_run_id, tenant_id)
        REFERENCES fsma.ingestion_runs (id, tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_agent_artifacts_traceability_anchor
        CHECK (
            cardinality(evidence_ids) > 0
            OR cardinality(canonical_event_ids) > 0
            OR ingestion_run_id IS NOT NULL
            OR cardinality(source_hashes) > 0
        ),
    CONSTRAINT ck_agent_artifacts_source_hashes
        CHECK (fsma.sha256_text_array_is_valid(source_hashes)),
    CONSTRAINT ck_agent_artifacts_rule_pair
        CHECK ((rule_id IS NULL AND rule_version IS NULL) OR (rule_id IS NOT NULL AND rule_version IS NOT NULL)),
    CONSTRAINT ck_agent_artifacts_json_identity
        CHECK (
            artifact ? 'artifact_id'
            AND artifact ? 'tenant_id'
            AND artifact ? 'artifact_type'
            AND artifact ? 'artifact_version'
            AND artifact->>'artifact_id' = artifact_id::text
            AND artifact->>'tenant_id' = tenant_id::text
            AND artifact->>'artifact_type' = artifact_type
            AND artifact->>'artifact_version' = artifact_version
        )
);

CREATE INDEX IF NOT EXISTS idx_agent_artifacts_tenant_created
    ON fsma.agent_artifacts (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_tenant_type
    ON fsma.agent_artifacts (tenant_id, artifact_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_tenant_run
    ON fsma.agent_artifacts (tenant_id, ingestion_run_id, created_at DESC)
    WHERE ingestion_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_tenant_review_required
    ON fsma.agent_artifacts (tenant_id, requires_human_review, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_evidence_ids
    ON fsma.agent_artifacts USING GIN (evidence_ids);
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_canonical_event_ids
    ON fsma.agent_artifacts USING GIN (canonical_event_ids);
CREATE INDEX IF NOT EXISTS idx_agent_artifacts_source_hashes
    ON fsma.agent_artifacts USING GIN (source_hashes);

CREATE OR REPLACE FUNCTION fsma.prepare_agent_artifact()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.artifact_hash := fsma.compute_agent_artifact_hash(NEW.artifact);
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agent_artifacts_prepare
    ON fsma.agent_artifacts;
CREATE TRIGGER agent_artifacts_prepare
    BEFORE INSERT ON fsma.agent_artifacts
    FOR EACH ROW EXECUTE FUNCTION fsma.prepare_agent_artifact();

CREATE OR REPLACE FUNCTION fsma.prevent_agent_artifact_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'agent_artifacts is append-only. Operation % rejected.',
        TG_OP
        USING ERRCODE = 'check_violation';
END;
$$;

DROP TRIGGER IF EXISTS agent_artifacts_append_only
    ON fsma.agent_artifacts;
CREATE TRIGGER agent_artifacts_append_only
    BEFORE UPDATE OR DELETE ON fsma.agent_artifacts
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_agent_artifact_mutation();

CREATE TABLE IF NOT EXISTS fsma.agent_artifact_reviews (
    review_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    artifact_id UUID NOT NULL,
    ingestion_run_id UUID,
    advisory_receipt_id UUID,

    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',
        'accepted',
        'rejected',
        'needs_more_evidence'
    )),
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    review_reason TEXT,
    operator_notes TEXT,
    decision_metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (
        jsonb_typeof(decision_metadata) = 'object'
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ux_agent_artifact_reviews_tenant_artifact
        UNIQUE (tenant_id, artifact_id),
    CONSTRAINT fk_agent_reviews_artifact_tenant
        FOREIGN KEY (artifact_id, tenant_id)
        REFERENCES fsma.agent_artifacts (artifact_id, tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_agent_reviews_run_tenant
        FOREIGN KEY (ingestion_run_id, tenant_id)
        REFERENCES fsma.ingestion_runs (id, tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_agent_reviews_receipt_tenant
        FOREIGN KEY (advisory_receipt_id, tenant_id)
        REFERENCES fsma.ingestion_run_receipts (receipt_id, tenant_id)
        ON DELETE RESTRICT,
    CONSTRAINT ck_agent_reviews_terminal_metadata
        CHECK (
            (
                status = 'pending'
                AND reviewed_by IS NULL
                AND reviewed_at IS NULL
            )
            OR (
                status <> 'pending'
                AND reviewed_by IS NOT NULL
                AND reviewed_at IS NOT NULL
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_agent_reviews_tenant_status
    ON fsma.agent_artifact_reviews (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_reviews_tenant_artifact
    ON fsma.agent_artifact_reviews (tenant_id, artifact_id);
CREATE INDEX IF NOT EXISTS idx_agent_reviews_tenant_run
    ON fsma.agent_artifact_reviews (tenant_id, ingestion_run_id)
    WHERE ingestion_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agent_reviews_tenant_receipt
    ON fsma.agent_artifact_reviews (tenant_id, advisory_receipt_id)
    WHERE advisory_receipt_id IS NOT NULL;

CREATE OR REPLACE FUNCTION fsma.touch_agent_artifact_review_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agent_artifact_reviews_touch_updated_at
    ON fsma.agent_artifact_reviews;
CREATE TRIGGER agent_artifact_reviews_touch_updated_at
    BEFORE UPDATE ON fsma.agent_artifact_reviews
    FOR EACH ROW EXECUTE FUNCTION fsma.touch_agent_artifact_review_updated_at();

CREATE OR REPLACE FUNCTION fsma.prevent_agent_artifact_review_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'agent_artifact_reviews cannot be deleted. Operation % rejected.',
        TG_OP
        USING ERRCODE = 'check_violation';
END;
$$;

DROP TRIGGER IF EXISTS agent_artifact_reviews_no_delete
    ON fsma.agent_artifact_reviews;
CREATE TRIGGER agent_artifact_reviews_no_delete
    BEFORE DELETE ON fsma.agent_artifact_reviews
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_agent_artifact_review_delete();

ALTER TABLE fsma.agent_artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.agent_artifacts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_agent_artifacts
    ON fsma.agent_artifacts;
CREATE POLICY tenant_isolation_agent_artifacts
    ON fsma.agent_artifacts
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context())
    WITH CHECK (tenant_id = get_tenant_context());

ALTER TABLE fsma.agent_artifact_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.agent_artifact_reviews FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_agent_artifact_reviews
    ON fsma.agent_artifact_reviews;
CREATE POLICY tenant_isolation_agent_artifact_reviews
    ON fsma.agent_artifact_reviews
    FOR ALL TO regengine
    USING (tenant_id = get_tenant_context())
    WITH CHECK (tenant_id = get_tenant_context());

REVOKE UPDATE, DELETE, TRUNCATE ON fsma.agent_artifacts FROM PUBLIC;
REVOKE DELETE, TRUNCATE ON fsma.agent_artifact_reviews FROM PUBLIC;

COMMENT ON TABLE fsma.agent_artifacts IS
    'Tenant-scoped append-only storage for validated advisory agent artifacts.';
COMMENT ON TABLE fsma.agent_artifact_reviews IS
    'Tenant-scoped operator review outcomes for advisory agent artifacts.';
COMMENT ON COLUMN fsma.agent_artifacts.artifact_hash IS
    'SHA-256 hash of the persisted artifact JSONB payload.';
COMMENT ON COLUMN fsma.agent_artifact_reviews.status IS
    'Operator review status: pending, accepted, rejected, or needs_more_evidence.';
"""


def upgrade() -> None:
    op.execute(_AGENT_ARTIFACT_OPERATOR_PERSISTENCE_SQL)


def downgrade() -> None:
    """Non-destructive operator persistence migration; preserve review history."""
    pass
