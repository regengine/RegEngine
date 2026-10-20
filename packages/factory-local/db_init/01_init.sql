-- factory-local schema. Runs once when the postgres volume is first created,
-- and again (idempotently) from pipeline.ensure_schema.

CREATE TABLE IF NOT EXISTS bill_versions (
    version_uid     text PRIMARY KEY,
    bill_id         text NOT NULL,
    jurisdiction    text NOT NULL,
    title           text NOT NULL,
    statutory_text  text NOT NULL,
    source_uri      text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS extracted_rules (
    rule_uid           text PRIMARY KEY,
    version_uid        text NOT NULL REFERENCES bill_versions (version_uid),
    ir_json            jsonb NOT NULL,
    rego               text NOT NULL,
    z3_result          jsonb NOT NULL,
    human_verified     boolean NOT NULL DEFAULT false,
    extraction_source  text,
    approved_at        timestamptz,
    updated_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS compliance_audit_ledger (
    execution_id        uuid PRIMARY KEY,
    tenant_id           text NOT NULL,
    rule_uid            text NOT NULL,
    version_uid         text NOT NULL,
    input_payload_hash  char(64) NOT NULL,
    evaluated_decision  text NOT NULL,
    citation_uri        text NOT NULL,
    previous_leaf_hash  char(64) NOT NULL,
    leaf_hash           char(64) NOT NULL,
    ed25519_signature   text NOT NULL,
    evaluated_at        timestamptz NOT NULL,
    seq                 bigserial NOT NULL UNIQUE
);

CREATE INDEX IF NOT EXISTS compliance_audit_ledger_tenant_seq
    ON compliance_audit_ledger (tenant_id, seq);

-- Append only. A superuser can still disable this trigger, which is why
-- verify_chain recomputes every hash and signature instead of trusting rows.
CREATE OR REPLACE FUNCTION compliance_audit_ledger_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'compliance_audit_ledger is append only';
END;
$$;

DROP TRIGGER IF EXISTS compliance_audit_ledger_no_mutation ON compliance_audit_ledger;
CREATE TRIGGER compliance_audit_ledger_no_mutation
    BEFORE UPDATE OR DELETE ON compliance_audit_ledger
    FOR EACH ROW EXECUTE FUNCTION compliance_audit_ledger_append_only();
