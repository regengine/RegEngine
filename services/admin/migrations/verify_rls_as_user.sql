-- Verification as app_user
SET ROLE app_user;

-- 1. Switch to Tenant A
SELECT set_tenant_context('11111111-1111-1111-1111-111111111111');

-- 2. Insert item for Tenant A
INSERT INTO review_items (doc_hash, text_raw, extraction, confidence_score)
VALUES ('hash_a_user', 'Data for A from User', '{}', 0.8);

-- 3. Verify visibility for A (Should see the item we just added, plus previous if they belonged to A)
SELECT count(*) as count_for_a FROM review_items;

-- 4. Switch to Tenant B
SELECT set_tenant_context('22222222-2222-2222-2222-222222222222');

-- 5. Insert item for Tenant B
INSERT INTO review_items (doc_hash, text_raw, extraction, confidence_score)
VALUES ('hash_b_user', 'Data for B from User', '{}', 0.9);

-- 6. Verify visibility for B (Should see 1 item, hash_b_user)
SELECT count(*) as count_for_b FROM review_items;

-- 7. Switch back to A
SELECT set_tenant_context('11111111-1111-1111-1111-111111111111');

-- 8. Verify visibility for A (Should be >= 1, and NOT see B's item)
SELECT count(*) as count_for_a_again FROM review_items;
