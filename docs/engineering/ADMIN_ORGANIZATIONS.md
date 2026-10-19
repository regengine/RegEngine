# Organization administration

Sysadmin routes for the passwordless-auth organization that shares its id
with a tenant. Mounted from `services/admin/app/admin/organizations_router.py`
on the consolidated app when the `admin` router is enabled. The path prefix
is `/admin/organizations`.

Both writes require a browser session for a user with `is_sysadmin` and a
high-assurance method: `webauthn` or `sso`. An email-OTP session is HTTP 403
`requires_step_up`. A missing session is HTTP 401. `X-Admin-Key` is rejected
with HTTP 401 even when a valid session cookie is also present. Each call
audits `attempted`, then `succeeded` or `failed`.

## Rename

`PATCH /admin/organizations/{org_id}` sets the organization display name.
The body is `{ "name": "..." }`. The name is stripped. An empty name, a
whitespace-only name, or a name longer than 255 characters is HTTP 422 and
does not touch the database.

```bash
curl -X PATCH "$BASE/admin/organizations/$ORG_ID" \
  -H "Content-Type: application/json" \
  -H "Cookie: __Host-regengine_session=$ADMIN_SESSION" \
  -d '{"name":"Renamed Foods"}'
```

The browser calls the same route through the Next.js admin proxy. That
proxy's base is `/api/admin`, and this path already starts with `/admin`,
so the dashboard request is `PATCH /api/admin/admin/organizations/{org_id}`.
The proxy forwards the `__Host-regengine_session` cookie.

The response is `{ "id", "name" }` after commit.

The organization id is the tenant id (`organizations.id == tenants.id`).
When a `tenants` row exists with that id, its `name` is updated in the same
transaction. The tenant `slug` is left as it is. When no tenant row shares
the id, the organization rename still commits.

Alembic v133 (`c4d8f1a2b6e7`) grants `regengine_sysadmin` `UPDATE (name)` on
`public.tenants`. v111 had granted that role update on `settings` and
`updated_at` only, so a rename deployed before v133 fails the commit. The
route then rolls back and returns HTTP 503 `Organization update temporarily
unavailable`. Neither name changes. An unknown organization is HTTP 404.

Audit action: `organization.update`. A missing organization is recorded as
`failed` with reason `organization_not_found`. A database error is
`database_unavailable`.

## SSO policy

`PUT /admin/organizations/{org_id}/sso-policy` is the sibling route on the
same router. The body is `domain_name`, `domain_verified`, and
`enforced_auth_policy` (`standard` or `sso_only`). `domain_name` must be a
bare DNS domain: it is stripped, lowercased, and a trailing dot is removed.
An email address, scheme, port, space, or empty label is HTTP 422. A domain
that another organization already claims is HTTP 409. Storing `sso_only`
with `domain_verified` false is accepted. Passwordless enforcement uses the
policy only after the domain is verified.

Audit action: `organization.sso_policy.update`.

## Tests

```bash
python3 -m pytest services/admin/tests/test_admin_organizations_router.py -q --no-cov
python3 -m pytest tests/migrations/test_v133_sysadmin_tenant_name_update.py -q --no-cov
```
