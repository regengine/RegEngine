
-- Seed obligation_cte_rules mapping FSMA 204 obligations to CTE types and KDE keys
-- These rules power real-time compliance checking on ingest

BEGIN;

DO $$ 
DECLARE 
  tid TEXT := 'a0000000-0000-4000-8000-000000000001';
  obl_id UUID;
BEGIN

-- Clear existing rules for this tenant's obligations
DELETE FROM obligation_cte_rules WHERE obligation_id IN (SELECT id FROM obligations WHERE tenant_id = tid);

-- SHIPPING rules
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'SHIPPING: Record traceability lot code' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'shipping', 'traceability_lot_code', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'SHIPPING: Record quantity%' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'shipping', 'quantity', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'SHIPPING: Record product description' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'shipping', 'product_description', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'SHIPPING: Record recipient%' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'shipping', 'ship_to_location', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'SHIPPING: Record shipping origin' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'shipping', 'ship_from_location', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'SHIPPING: Record ship date' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'shipping', 'ship_date', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'SHIPPING: Record TLC source%' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'shipping', 'tlc_source_reference', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'SHIPPING: Record reference document' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'shipping', 'reference_document', 'present');
END LOOP;

-- RECEIVING rules
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECEIVING: Record traceability lot code' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'receiving', 'traceability_lot_code', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECEIVING: Record quantity%' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'receiving', 'quantity', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECEIVING: Record product description' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'receiving', 'product_description', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECEIVING: Record previous source' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'receiving', 'ship_from_location', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECEIVING: Record receiving location' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'receiving', 'receiving_location', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECEIVING: Record receive date' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'receiving', 'receive_date', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECEIVING: Record TLC source%' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'receiving', 'tlc_source_reference', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECEIVING: Record reference document' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'receiving', 'reference_document', 'present');
END LOOP;

-- HARVESTING rules
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'HARVESTING: Record commodity%' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'harvesting', 'product_description', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'HARVESTING: Record quantity%' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'harvesting', 'quantity', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'HARVESTING: Record farm location' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'harvesting', 'location_name', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'HARVESTING: Record harvest date' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'harvesting', 'harvest_date', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'HARVESTING: Record reference document' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'harvesting', 'reference_document', 'present');
END LOOP;

-- COOLING rules
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'COOLING: Record cooling location' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'cooling', 'location_name', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'COOLING: Record cooling date' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'cooling', 'cooling_date', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'COOLING: Record reference document' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'cooling', 'reference_document', 'present');
END LOOP;

-- INITIAL PACKING rules
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'INITIAL PACKING: Assign TLC' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'initial_packing', 'traceability_lot_code', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'INITIAL PACKING: Record product description' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'initial_packing', 'product_description', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'INITIAL PACKING: Record packing date' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'initial_packing', 'packing_date', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'INITIAL PACKING: Record reference document' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'initial_packing', 'reference_document', 'present');
END LOOP;

-- FIRST LAND-BASED RECEIVER rules
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'FIRST LAND-BASED RECEIVER: Assign TLC' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'first_land_based_receiving', 'traceability_lot_code', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'FIRST LAND-BASED RECEIVER: Record landing date' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'first_land_based_receiving', 'landing_date', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'FIRST LAND-BASED RECEIVER: Record reference document' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'first_land_based_receiving', 'reference_document', 'present');
END LOOP;

-- TRANSFORMATION rules
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'TRANSFORMATION OUTPUT: Assign new TLC' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'transformation', 'traceability_lot_code', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'TRANSFORMATION OUTPUT: Record completion date' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'transformation', 'transformation_date', 'present');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'TRANSFORMATION OUTPUT: Record reference document' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'transformation', 'reference_document', 'present');
END LOOP;

-- Cross-CTE rules (apply to all CTE types)
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECORDS: Retain for 2 years' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'all', NULL, 'policy');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECORDS: Available within 24 hours' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'all', NULL, 'policy');
END LOOP;
FOR obl_id IN SELECT id FROM obligations WHERE tenant_id = tid AND title LIKE 'RECORDS: Electronic sortable format' LOOP
  INSERT INTO obligation_cte_rules (id, obligation_id, cte_type, required_kde_key, validation_rule) VALUES (gen_random_uuid(), obl_id, 'all', NULL, 'policy');
END LOOP;

END $$;

COMMIT;
;
