# RLS deployment

The previous copy of this page told operators to run `./scripts/deploy_rls.sh` against local, staging, and production, then optionally disable row level security on every table in `public`. That procedure is retired.

`scripts/deploy_rls.sh` now prints that direct RLS SQL deployment is retired (service-level Flyway SQL was removed in #2004) and exits 2. It does not apply migrations. Do not follow the old V27/V28 `pcos_*` steps, and do not disable row level security as a rollback.

Current database changes, including RLS policies, go through the Alembic chain as `regengine_migrator`. The blocking procedure is [Runtime Database Role Cutover](DATABASE_ROLE_CUTOVER.md). Production hard-requires RLS (`REGENGINE_REQUIRE_RLS_ENFORCEMENT=1`). A bypass-RLS credential is not an acceptable rollback.

## v144 client reads (`d8f3a1c6b902`)

Revision v144 (`alembic/versions/20261119_d8f3a1c6b902_v144_anon_tenant_catalog_rls.py`, mirrored at `supabase/migrations/20261119120000_v144_anon_tenant_catalog_rls.sql`) removes anonymous and public SELECT on live tenant metadata and the product catalog. The migration header states it is **not applied to production** and must not be applied without an explicit yes from C.Lee. Merging the revision into `main` is not a production apply.

Once the revision is applied on a database that has the Supabase client roles and `auth.uid()`:

| Surface | Who can SELECT | Notes |
|---|---|---|
| `public.memberships` | `authenticated`, only rows where `user_id = auth.uid()` (`memberships_authenticated_self_read`) | Created only when the `authenticated` role and `auth.uid()` exist. `tenant_isolation_memberships` is narrowed to `regengine` and `regengine_sysadmin`. Membership writes are not broadened. |
| `public.tenants` | `authenticated` members (`tenants_authenticated_member_read`: `id` is in the caller's memberships) | `tenants_read_all` is dropped. `anon` loses SELECT, INSERT, UPDATE, DELETE, TRUNCATE, TRIGGER, and REFERENCES. `authenticated` keeps SELECT only; the other six privileges, including TRUNCATE, are revoked. |
| `public.tenants` | `regengine` / `regengine_sysadmin` (`tenants_backend_context_read`) | A sysadmin read requires `current_user = regengine_sysadmin` and `regengine.is_sysadmin = true`. Otherwise the row id must equal `get_tenant_context()`. |
| `public.tenants` writes | backend roles only (`tenants_write_own`, UPDATE) | The sysadmin-flag branch of this policy is false, so v111's separate sysadmin policy remains the global write path. Other backend writes require `id = get_tenant_context()`. |
| `public.product_catalog` | `authenticated` members | `tenant_id` (text) is compared to `memberships.tenant_id::text`. `FORCE ROW LEVEL SECURITY` is enabled. `public_read_product_catalog` is dropped and `anon` SELECT is revoked. `service_role_full_access` and service-role grants are left unchanged. |

App-only databases that lack `product_catalog`, the `anon` or `authenticated` roles, or `auth.uid()` skip the client policies that need those objects. Dropping `tenants_read_all` still happens. Missing client objects fail closed: the member policies are not created without `auth.uid()`.

Authenticated catalog and tenant reads depend on existing SELECT on `memberships.user_id` and `memberships.tenant_id`. v144 does not grant those columns. A missing grant fails with permission denied.

A `regengine` session with no tenant selected now fails inside `get_tenant_context()` (`app.tenant_id not set`) instead of returning an empty tenant list. `regengine_sysadmin` with `regengine.is_sysadmin=true` does not take that branch.

The supported migration runner reapplies v111 after upgrading to head. That reapply drops `tenants_write_own` only when `tenants_backend_context_read` is absent, so a later v144 policy is preserved. Startup pins the resulting tenant policy tuples in `services/shared/database.py` (`_EXPECTED_RUNTIME_POLICY_MANIFEST_SHA256` for `regengine` and `regengine_sysadmin`). Boot with `REGENGINE_REQUIRE_RLS_ENFORCEMENT=1` refuses policy-manifest drift. Do not copy those digests into this page; they change when the catalog changes.

Downgrade restores the previous public and anonymous exposure and the excess client grants, including TRUNCATE. It is not a security-preserving rollback. Do not paste the commented downgrade block from the SQL mirror into a hosted session.

### Checks before an approved apply

Run the structural tests, then the disposable-PostgreSQL cases. A machine without PostgreSQL skips the database cases; CI must run them with `--require-db` before anyone applies v144.

```bash
python3 -m pytest tests/migrations/test_v144_anon_tenant_catalog_rls.py tests/migrations/test_v144_runtime_policy_manifest.py tests/migrations/test_v111_runtime_role_grants.py -q --no-cov -o addopts=''
```

On a disposable database after apply, `tenants_read_all` and `public_read_product_catalog` must be gone. On a Supabase database that has `auth.uid()`, these policy names must exist: `memberships_authenticated_self_read`, `tenants_authenticated_member_read`, `tenants_backend_context_read`, `tenants_write_own`, and `product_catalog_authenticated_member_read`. An app-only database that skipped the client policies will not have the `authenticated` policies.

```sql
SELECT tablename, policyname, roles
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN ('tenants', 'memberships', 'product_catalog')
ORDER BY 1, 2;
```

## Invite acceptance under FORCE RLS (SEL-612)

`POST /v1/auth/accept-invite` is unauthenticated and rate-limited to 10 requests per minute. The handler is `accept_invite` in `services/admin/app/invite_routes.py`. The consolidated app mounts that router at `/v1` only when the `admin` router is enabled (`server/routers_mount.py`). The legacy admin entrypoint uses the same prefix. `public.invites` is FORCE RLS. Reading it with no tenant context raises, because `get_tenant_context()` raises when `app.tenant_id` is unset (v097). The handler does not broaden policies or grants.

On PostgreSQL it:

1. Hashes the token with SHA-256 and calls `get_invite_tenant_by_token_hash`. A token that matches no still-usable invite returns no tenant. The handler then returns HTTP 400 with detail `Invite is not usable` and does not read `invites` without context.
2. Sets that tenant with `TenantContext.set_tenant_context`, so later statements use the ordinary tenant policies.
3. Arms global identity context only around two blocks, and disarms in `finally` even when the block fails. `tests/security/test_global_admin_context_allowlist.py` classifies `accept_invite` as `auth-bootstrap` with exactly two `arm_global_admin_context` calls.
   - First arm: case-insensitive global user lookup or create. New users are `is_sysadmin=False` and `status=active`. A user whose `status` or `global_status` is not `active` is not reinstated. The user insert is flushed before disarm.
   - Second arm: `ensure_passwordless_identity` for the invited mailbox and the invite's organization, then `flush` while the context is still armed.
4. Attaches the membership from the invite's tenant and role, writes the `invite.accept` audit event, and commits. An audit-chain write failure rolls back and returns HTTP 500 with error `audit_write_failed`. Duplicate-user, duplicate-membership, and email-ownership races roll back and return the same 400 as an unusable invite.

SQLite and other non-PostgreSQL binds skip `get_invite_tenant_by_token_hash`. They still use the same handler. An existing membership marks the invite accepted and then returns 400 so the token cannot be reused.

The invite link puts the one-time token in the URL fragment (`/accept-invite#token=...`), so the secret is not sent to servers or proxies. Creating an invite is the authenticated route `POST /v1/admin/invites` (`users.invite`).

### Pitfalls

- A uniform 400 hides expired, revoked, accepted, unknown, inactive-user, ambiguous case-variant user, and ownership-conflict cases. Do not add distinct client errors for those.
- Leaving global admin context armed past the `finally` would let later statements on that session bypass tenant RLS. Both arms stay inside `try`/`finally`.
- v144 and SEL-612 solve different problems. v144 closes anonymous PostgREST reads of `tenants` and `product_catalog`. SEL-612 lets pre-auth invite acceptance write global identity rows under FORCE RLS without a standing admin context.
- Applying v144 without the membership SELECT grants makes authenticated client reads fail closed. Applying the v144 downgrade reopens anonymous reads.
