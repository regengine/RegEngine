-- V039 — Hash chain immutability trigger
-- ========================================
-- The fsma.hash_chain table is designed as append-only, but there are no
-- database-level protections preventing UPDATE or DELETE.  Any SQL injection
-- or admin console access could modify the chain and destroy audit integrity.
--
-- This trigger rejects all UPDATE and DELETE operations at the DB level.

BEGIN;

CREATE OR REPLACE FUNCTION fsma.prevent_chain_mutation() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'hash_chain is append-only — modifications are prohibited';
END;
$$ LANGUAGE plpgsql;

-- Drop if exists to make migration idempotent
DROP TRIGGER IF EXISTS chain_immutability ON fsma.hash_chain;

CREATE TRIGGER chain_immutability
    BEFORE UPDATE OR DELETE ON fsma.hash_chain
    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_chain_mutation();

COMMENT ON TRIGGER chain_immutability ON fsma.hash_chain IS
    'Enforces append-only semantics — no row may be updated or deleted (V039)';

COMMIT;
