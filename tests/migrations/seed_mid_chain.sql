-- Representative dataset applied at MID_CHAIN_REVISION (v089 / 38e02636e340)
-- by test_seeded_mid_chain_upgrade.py, before running `alembic upgrade head`.
--
-- Purpose (#2588 follow-up): every other migration gate upgrades an EMPTY
-- database, so row-dependent migration bugs never fire in CI. The v090
-- sequence_num backfill UPDATE on audit_logs was rejected by the v066
-- audit_append_only trigger on any populated database — both production
-- deploys on 2026-07-15 failed there while CI stayed green. This seed makes
-- the post-v089 chain run against populated tables so that class of failure
-- surfaces pre-merge.
--
-- Written against the v089 schema. It always executes at exactly that
-- revision, so later schema changes never invalidate it. Two tenants so
-- per-tenant partitioned backfills (PARTITION BY tenant_id) are exercised
-- across more than one partition. All ids are fixed so the test can assert
-- on them after the upgrade.
--
-- Executed as the superuser CI connection: RLS does not apply, and the
-- append-only triggers (v053 fsma, v066 audit_logs) only block
-- UPDATE/DELETE, not INSERT.

BEGIN;

INSERT INTO public.tenants (id, name, slug, status)
VALUES
    ('00000000-0000-4000-8000-00000000000a', 'Seed Tenant A', 'seed-tenant-a', 'active'),
    ('00000000-0000-4000-8000-00000000000b', 'Seed Tenant B', 'seed-tenant-b', 'active');

INSERT INTO public.users (id, email, is_sysadmin)
VALUES
    ('00000000-0000-4000-8000-0000000000aa', 'seed-admin@example.test', true),
    ('00000000-0000-4000-8000-0000000000ab', 'seed-user@example.test', false);

-- Rows in audit_logs are what arm the v066 audit_append_only trigger path:
-- any later migration that UPDATEs/DELETEs audit rows fails here exactly as
-- it would in production. Hash-chain values are synthetic; no migration
-- recomputes them.
INSERT INTO public.audit_logs
    (tenant_id, actor_id, actor_email, event_type, event_category, action,
     severity, resource_type, resource_id, prev_hash, integrity_hash)
VALUES
    ('00000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000aa',
     'seed-admin@example.test', 'auth.login', 'auth', 'login',
     'info', 'session', 'seed-1', NULL, 'seedhash-a1'),
    ('00000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000aa',
     'seed-admin@example.test', 'tenant.update', 'admin', 'update',
     'info', 'tenant', 'seed-2', 'seedhash-a1', 'seedhash-a2'),
    ('00000000-0000-4000-8000-00000000000a', '00000000-0000-4000-8000-0000000000ab',
     'seed-user@example.test', 'auth.login', 'auth', 'login',
     'info', 'session', 'seed-3', 'seedhash-a2', 'seedhash-a3'),
    ('00000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000ab',
     'seed-user@example.test', 'auth.login', 'auth', 'login',
     'info', 'session', 'seed-4', NULL, 'seedhash-b1'),
    ('00000000-0000-4000-8000-00000000000b', '00000000-0000-4000-8000-0000000000ab',
     'seed-user@example.test', 'export.create', 'compliance', 'create',
     'info', 'export', 'seed-5', 'seedhash-b1', 'seedhash-b2');

INSERT INTO fsma.cte_events
    (id, tenant_id, event_type, traceability_lot_code, product_description,
     quantity, unit_of_measure, event_timestamp, sha256_hash, chain_hash)
VALUES
    ('00000000-0000-4000-8000-0000000000c1', '00000000-0000-4000-8000-00000000000a',
     'harvesting', 'LOT-SEED-001', 'Romaine lettuce',
     120.5, 'kg', '2026-06-01T08:00:00Z', 'seedsha-c1', 'seedchain-c1'),
    ('00000000-0000-4000-8000-0000000000c2', '00000000-0000-4000-8000-00000000000a',
     'shipping', 'LOT-SEED-001', 'Romaine lettuce',
     120.5, 'kg', '2026-06-02T09:30:00Z', 'seedsha-c2', 'seedchain-c2'),
    ('00000000-0000-4000-8000-0000000000c3', '00000000-0000-4000-8000-00000000000b',
     'receiving', 'LOT-SEED-002', 'Fresh-cut mango',
     40.0, 'kg', '2026-06-03T14:00:00Z', 'seedsha-c3', 'seedchain-c3');

INSERT INTO fsma.request_cases
    (request_case_id, tenant_id, response_due_at, requesting_party, scope_type)
VALUES
    ('00000000-0000-4000-8000-0000000000d1', '00000000-0000-4000-8000-00000000000a',
     '2026-06-25T00:00:00Z', 'FDA District Office', 'tlc_trace');

INSERT INTO fsma.request_signoffs
    (id, tenant_id, request_case_id, signoff_type, signed_by)
VALUES
    ('00000000-0000-4000-8000-0000000000e1', '00000000-0000-4000-8000-00000000000a',
     '00000000-0000-4000-8000-0000000000d1', 'scope_approval', 'seed-admin@example.test'),
    ('00000000-0000-4000-8000-0000000000e2', '00000000-0000-4000-8000-00000000000a',
     '00000000-0000-4000-8000-0000000000d1', 'final_approval', 'seed-admin@example.test');

COMMIT;
