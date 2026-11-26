# runbooks/

Operator SQL files that live docs and tests name by this path:

| File | Named by |
|---|---|
| `prod-least-privilege-db-role.sql` | `docs/operations/DATABASE_ROLE_CUTOVER.md`, `alembic/versions/20260725_8b2f4e6a9c31_v098_runtime_ddl_into_migrations.py` |
| `prod-revoke-create-after-v098.sql` | `docs/operations/DISASTER_RECOVERY.md`, the v098 revision |
| `predeploy-v126-misattached-blobs.sql` | the v126 revision's operator message, `tests/scripts/test_v126_operator_guidance.py` |
| `verify-v126-runtime-grants.sql` | `docs/operations/DATABASE_ROLE_CUTOVER.md`, `tests/migrations/test_v111_runtime_role_grants.py` |
| `supabase-anon-lead-capture-lockdown.sql` | `tests/supabase/test_assessment_lead_abuse_guard.py` |
| `supabase-assessment-lead-abuse-guard.sql` | `tests/supabase/test_assessment_lead_abuse_guard.py` |

The five narrative runbooks that carried a `LEGACY:` banner (deploy security
hardening, monitoring alerts, Neo4j disaster recovery, rollback procedure,
scaling guide) describe the retired six-service topology and moved to
`docs/runbooks/legacy/` on 2026-11-04 (tech-debt WI-07). Current runbooks are
under `docs/runbooks/`.
