-- V057: Remove cottage cheese from FTL Fresh Soft Cheese category
--
-- FDA finalized the cottage cheese exemption (April 2026).
-- Cottage cheese is on the IMS List and exempt per §1.1305(d).
-- This updates the seed data inserted by V036.

UPDATE food_traceability_list
SET examples   = array_remove(examples, 'cottage cheese'),
    exclusions = CASE
        WHEN exclusions IS NULL THEN ARRAY['hard cheeses', 'cottage cheese (exempt per §1.1305(d), IMS List, finalized April 2026)']
        ELSE array_append(exclusions, 'cottage cheese (exempt per §1.1305(d), IMS List, finalized April 2026)')
    END
WHERE food_name = 'Fresh Soft Cheese (pasteurized milk)';
