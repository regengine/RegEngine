ALTER TABLE pcos_extracted_facts DISABLE TRIGGER ALL;
ALTER TABLE pcos_authority_documents DISABLE TRIGGER ALL;

DELETE FROM pcos_extracted_facts 
WHERE tenant_id = '00000000-0000-0000-0000-000000000000';

DELETE FROM pcos_authority_documents 
WHERE tenant_id = '00000000-0000-0000-0000-000000000000';

ALTER TABLE pcos_authority_documents ENABLE TRIGGER ALL;
ALTER TABLE pcos_extracted_facts ENABLE TRIGGER ALL;
