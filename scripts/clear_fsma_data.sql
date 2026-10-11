-- Clear FSMA demo data for the zero-UUID tenant only.
-- Dev and test helper. Never run against production.
-- Table triggers stay enabled so audit and immutability protections apply
-- to these deletes, and both deletes run in a single transaction so a
-- failure partway through rolls back instead of leaving a half-cleared tenant.

BEGIN;

DELETE FROM pcos_extracted_facts
WHERE tenant_id = '00000000-0000-0000-0000-000000000000';

DELETE FROM pcos_authority_documents
WHERE tenant_id = '00000000-0000-0000-0000-000000000000';

COMMIT;
