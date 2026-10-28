
-- Seed FSMA 204 obligations for production tenant
-- 82 actionable requirements from 21 CFR Part 1 Subpart S

BEGIN;

-- Production tenant
DO $$ DECLARE tid TEXT := 'a0000000-0000-4000-8000-000000000001'; BEGIN

-- Clear any previous seed (idempotent)
DELETE FROM obligation_cte_rules WHERE obligation_id IN (SELECT id FROM obligations WHERE tenant_id = tid);
DELETE FROM obligations WHERE tenant_id = tid;

-- SHIPPING obligations (§1.1340)
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'SHIPPING: Record traceability lot code', '21 CFR §1.1340(a)(1)', 'Record the traceability lot code for the food when shipping', 'active'),
  (gen_random_uuid(), tid, 'SHIPPING: Record quantity and unit of measure', '21 CFR §1.1340(a)(2)', 'Record quantity and unit of measure of the food shipped', 'active'),
  (gen_random_uuid(), tid, 'SHIPPING: Record product description', '21 CFR §1.1340(a)(3)', 'Record product description for the food shipped', 'active'),
  (gen_random_uuid(), tid, 'SHIPPING: Record recipient location', '21 CFR §1.1340(a)(4)', 'Record location description for the immediate subsequent recipient', 'active'),
  (gen_random_uuid(), tid, 'SHIPPING: Record shipping origin', '21 CFR §1.1340(a)(5)', 'Record location description for the location from which you shipped', 'active'),
  (gen_random_uuid(), tid, 'SHIPPING: Record ship date', '21 CFR §1.1340(a)(6)', 'Record the date you shipped the food', 'active'),
  (gen_random_uuid(), tid, 'SHIPPING: Record TLC source reference', '21 CFR §1.1340(a)(7)', 'Record location description for TLC source or TLC source reference', 'active'),
  (gen_random_uuid(), tid, 'SHIPPING: Record reference document', '21 CFR §1.1340(a)(8)', 'Record reference document type and number', 'active'),
  (gen_random_uuid(), tid, 'SHIPPING: Provide KDEs to recipient', '21 CFR §1.1340(b)', 'Provide items (1)-(7) to immediate subsequent recipient in written form', 'active');

-- RECEIVING obligations (§1.1345)
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'RECEIVING: Record traceability lot code', '21 CFR §1.1345(a)(1)', 'Record the traceability lot code for the food received', 'active'),
  (gen_random_uuid(), tid, 'RECEIVING: Record quantity and unit of measure', '21 CFR §1.1345(a)(2)', 'Record quantity and unit of measure of the food received', 'active'),
  (gen_random_uuid(), tid, 'RECEIVING: Record product description', '21 CFR §1.1345(a)(3)', 'Record product description for the food received', 'active'),
  (gen_random_uuid(), tid, 'RECEIVING: Record previous source', '21 CFR §1.1345(a)(4)', 'Record location description for the immediate previous source', 'active'),
  (gen_random_uuid(), tid, 'RECEIVING: Record receiving location', '21 CFR §1.1345(a)(5)', 'Record location description for where the food was received', 'active'),
  (gen_random_uuid(), tid, 'RECEIVING: Record receive date', '21 CFR §1.1345(a)(6)', 'Record the date you received the food', 'active'),
  (gen_random_uuid(), tid, 'RECEIVING: Record TLC source reference', '21 CFR §1.1345(a)(7)', 'Record TLC source location or TLC source reference', 'active'),
  (gen_random_uuid(), tid, 'RECEIVING: Record reference document', '21 CFR §1.1345(a)(8)', 'Record reference document type and number', 'active');

-- HARVESTING obligations (§1.1325)
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'HARVESTING: Record recipient location', '21 CFR §1.1325(a)(1)(i)', 'Record location description for immediate subsequent recipient', 'active'),
  (gen_random_uuid(), tid, 'HARVESTING: Record commodity and variety', '21 CFR §1.1325(a)(1)(ii)', 'Record commodity and variety of the food', 'active'),
  (gen_random_uuid(), tid, 'HARVESTING: Record quantity and unit of measure', '21 CFR §1.1325(a)(1)(iii)', 'Record quantity and unit of measure of the food', 'active'),
  (gen_random_uuid(), tid, 'HARVESTING: Record farm location', '21 CFR §1.1325(a)(1)(iv)', 'Record location description for the farm where food was harvested', 'active'),
  (gen_random_uuid(), tid, 'HARVESTING: Record field/growing area', '21 CFR §1.1325(a)(1)(v)', 'Record name of field or growing area from which food was harvested', 'active'),
  (gen_random_uuid(), tid, 'HARVESTING: Record harvest date', '21 CFR §1.1325(a)(1)(vi)', 'Record the date of harvesting', 'active'),
  (gen_random_uuid(), tid, 'HARVESTING: Record reference document', '21 CFR §1.1325(a)(1)(vii)', 'Record reference document type and number', 'active'),
  (gen_random_uuid(), tid, 'HARVESTING: Provide KDEs to initial packer', '21 CFR §1.1325(a)(2)', 'Provide all KDEs except reference docs to initial packer or cooler', 'active');

-- COOLING obligations (§1.1325(b))
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'COOLING: Record recipient location', '21 CFR §1.1325(b)(1)(i)', 'Record location description for immediate subsequent recipient', 'active'),
  (gen_random_uuid(), tid, 'COOLING: Record commodity and variety', '21 CFR §1.1325(b)(1)(ii)', 'Record commodity and variety of the food', 'active'),
  (gen_random_uuid(), tid, 'COOLING: Record quantity and unit of measure', '21 CFR §1.1325(b)(1)(iii)', 'Record quantity and unit of measure', 'active'),
  (gen_random_uuid(), tid, 'COOLING: Record cooling location', '21 CFR §1.1325(b)(1)(iv)', 'Record location description for the cooling location', 'active'),
  (gen_random_uuid(), tid, 'COOLING: Record cooling date', '21 CFR §1.1325(b)(1)(v)', 'Record the date of cooling', 'active'),
  (gen_random_uuid(), tid, 'COOLING: Record farm location', '21 CFR §1.1325(b)(1)(vi)', 'Record location description for the farm where food was harvested', 'active'),
  (gen_random_uuid(), tid, 'COOLING: Record reference document', '21 CFR §1.1325(b)(1)(vii)', 'Record reference document type and number', 'active'),
  (gen_random_uuid(), tid, 'COOLING: Provide KDEs to initial packer', '21 CFR §1.1325(b)(2)', 'Provide KDEs (except reference docs) to initial packer', 'active');

-- INITIAL PACKING obligations (§1.1330)
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record commodity received', '21 CFR §1.1330(a)(1)', 'Record commodity and variety of food received', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record date received', '21 CFR §1.1330(a)(2)', 'Record date food was received', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record quantity received', '21 CFR §1.1330(a)(3)', 'Record quantity and unit of measure received', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record farm location', '21 CFR §1.1330(a)(4)', 'Record location description for farm where harvested', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record field/growing area', '21 CFR §1.1330(a)(5)', 'Record name of field/growing area or container', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record harvester info', '21 CFR §1.1330(a)(6)', 'Record business name and phone number of harvester', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record harvest date', '21 CFR §1.1330(a)(7)', 'Record date of harvesting', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record cooling info', '21 CFR §1.1330(a)(8-9)', 'Record cooling location and date if applicable', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Assign TLC', '21 CFR §1.1330(a)(10)', 'Assign and record traceability lot code', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record product description', '21 CFR §1.1330(a)(11)', 'Record product description for the packed food', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record quantity packed', '21 CFR §1.1330(a)(12)', 'Record quantity and unit of measure of packed food', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record packing location', '21 CFR §1.1330(a)(13)', 'Record location description for initial packing and TLC source reference', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record packing date', '21 CFR §1.1330(a)(14)', 'Record date of initial packing', 'active'),
  (gen_random_uuid(), tid, 'INITIAL PACKING: Record reference document', '21 CFR §1.1330(a)(15)', 'Record reference document type and number', 'active');

-- FIRST LAND-BASED RECEIVER (§1.1335)
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'FIRST LAND-BASED RECEIVER: Assign TLC', '21 CFR §1.1335(1)', 'Assign and record traceability lot code', 'active'),
  (gen_random_uuid(), tid, 'FIRST LAND-BASED RECEIVER: Record species/product', '21 CFR §1.1335(2)', 'Record species/market name for unpackaged or product description for packaged food', 'active'),
  (gen_random_uuid(), tid, 'FIRST LAND-BASED RECEIVER: Record quantity', '21 CFR §1.1335(3)', 'Record quantity and unit of measure', 'active'),
  (gen_random_uuid(), tid, 'FIRST LAND-BASED RECEIVER: Record harvest info', '21 CFR §1.1335(4)', 'Record harvest date range and locations for the fishing trip', 'active'),
  (gen_random_uuid(), tid, 'FIRST LAND-BASED RECEIVER: Record receiving location', '21 CFR §1.1335(5)', 'Record location description for where you received the food', 'active'),
  (gen_random_uuid(), tid, 'FIRST LAND-BASED RECEIVER: Record landing date', '21 CFR §1.1335(6)', 'Record the date you received the food (landing date)', 'active'),
  (gen_random_uuid(), tid, 'FIRST LAND-BASED RECEIVER: Record reference document', '21 CFR §1.1335(7)', 'Record reference document type and number', 'active');

-- TRANSFORMATION obligations (§1.1350)
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'TRANSFORMATION INPUT: Record TLC', '21 CFR §1.1350(1)', 'Record traceability lot code for each input food', 'active'),
  (gen_random_uuid(), tid, 'TRANSFORMATION INPUT: Record product description', '21 CFR §1.1350(2)', 'Record product description for each input food', 'active'),
  (gen_random_uuid(), tid, 'TRANSFORMATION INPUT: Record quantity used', '21 CFR §1.1350(3)', 'Record quantity and unit of measure used from each lot', 'active'),
  (gen_random_uuid(), tid, 'TRANSFORMATION OUTPUT: Assign new TLC', '21 CFR §1.1350(4)', 'Assign and record new traceability lot code', 'active'),
  (gen_random_uuid(), tid, 'TRANSFORMATION OUTPUT: Record location', '21 CFR §1.1350(5)', 'Record location description for transformation location', 'active'),
  (gen_random_uuid(), tid, 'TRANSFORMATION OUTPUT: Record completion date', '21 CFR §1.1350(6)', 'Record date transformation was completed', 'active'),
  (gen_random_uuid(), tid, 'TRANSFORMATION OUTPUT: Record product description', '21 CFR §1.1350(7)', 'Record product description for the new food', 'active'),
  (gen_random_uuid(), tid, 'TRANSFORMATION OUTPUT: Record quantity', '21 CFR §1.1350(8)', 'Record quantity and unit of measure of the new food', 'active'),
  (gen_random_uuid(), tid, 'TRANSFORMATION OUTPUT: Record reference document', '21 CFR §1.1350(9)', 'Record reference document type and number', 'active');

-- TLC ASSIGNMENT (§1.1320)
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'TLC: Assign when initially packing RAC', '21 CFR §1.1320(a)(1)', 'Assign TLC when initially packing a raw agricultural commodity', 'active'),
  (gen_random_uuid(), tid, 'TLC: Assign when first land-based receiving', '21 CFR §1.1320(a)(2)', 'Assign TLC when receiving food as first land-based receiver', 'active'),
  (gen_random_uuid(), tid, 'TLC: Assign when transforming food', '21 CFR §1.1320(a)(3)', 'Assign TLC when transforming food', 'active'),
  (gen_random_uuid(), tid, 'TLC: Do not reassign for shipping', '21 CFR §1.1320(b)', 'Do NOT assign new TLC for shipping or other activities', 'active');

-- TRACEABILITY PLAN (§1.1315)
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'PLAN: Document record procedures', '21 CFR §1.1315(a)(1)', 'Describe procedures for maintaining required records including format and location', 'active'),
  (gen_random_uuid(), tid, 'PLAN: FTL identification procedures', '21 CFR §1.1315(a)(2)', 'Describe procedures for identifying FTL foods you handle', 'active'),
  (gen_random_uuid(), tid, 'PLAN: TLC assignment methods', '21 CFR §1.1315(a)(3)', 'Describe how traceability lot codes are assigned', 'active'),
  (gen_random_uuid(), tid, 'PLAN: Point of contact', '21 CFR §1.1315(a)(4)', 'Identify point of contact for traceability questions', 'active'),
  (gen_random_uuid(), tid, 'PLAN: Farm/aquaculture maps', '21 CFR §1.1315(a)(5)', 'Provide maps showing fields/growing areas with coordinates', 'active'),
  (gen_random_uuid(), tid, 'PLAN: Keep plan current', '21 CFR §1.1315(b)', 'Update traceability plan to reflect current practices; retain previous versions 2 years', 'active');

-- RECORDS (§1.1455)
INSERT INTO obligations (id, tenant_id, title, regulation_ref, description, status) VALUES
  (gen_random_uuid(), tid, 'RECORDS: Maintain as originals or true copies', '21 CFR §1.1455(a)', 'Maintain records as original paper/electronic records or true copies, legible and protected', 'active'),
  (gen_random_uuid(), tid, 'RECORDS: Available within 24 hours', '21 CFR §1.1455(c)', 'Make all records available to FDA within 24 hours of request', 'active'),
  (gen_random_uuid(), tid, 'RECORDS: Electronic sortable format', '21 CFR §1.1455(f)', 'Provide records in electronic sortable spreadsheet format upon FDA request', 'active'),
  (gen_random_uuid(), tid, 'RECORDS: Retain for 2 years', '21 CFR §1.1455(h)', 'Retain all required records for 2 years from creation/receipt date', 'active'),
  (gen_random_uuid(), tid, 'RECORDS: 24-hour outbreak response', '21 CFR §1.1455(e)', 'In outbreak/recall situations provide information within 24 hours', 'active');

END $$;

COMMIT;
;
