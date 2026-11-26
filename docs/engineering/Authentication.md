# Authentication and API keys

Authentication depends on the route. Ingestion APIs support tenant-scoped API
keys; the primary browser login uses email one-time codes and passkeys with
cookie sessions. Some legacy Supabase-session code remains in the frontend.
A local API key does not create a browser user or sign in a browser. Check the
route's dependencies and the [router policy](../../server/router_policy.py)
for availability rather than assuming all routes share one auth mechanism.

## API keys

The shared API-key authentication scheme uses `X-RegEngine-API-Key`. Keys
carry tenant and scope information; tenant authority comes from the
authenticated principal, not a caller-provided tenant ID. Protected routes can
also apply entitlement and rate limits. See [shared auth](../../services/shared/auth.py),
[tenant context](../../services/shared/tenant_context.py), and the
[tenant-route inventory](../security/tenant-route-inventory.md).

For an isolated development stack, follow the [local setup guide](../guides/LOCAL_SETUP_GUIDE.md#create-a-local-api-key).
The helper creates a test key through the database store and writes its raw
value once to a permission-restricted file. Set `ENABLE_DB_API_KEYS=true` in
the development server when using DB-backed keys. Keep raw keys out of shell
history, logs, source control, and browser-exposed environment variables.

The database key store persists a digest, not the raw key. It uses HMAC-SHA256
when `REGENGINE_API_KEY_HASH_PEPPER` is configured and supports legacy SHA-256
hashes; see [api_key_store.py](../../services/shared/api_key_store.py). Do not
manually insert hashes into `api_keys`: use supported key-management paths so
scope, tenant, audit, and storage behavior remain consistent.

The admin routes `POST /v1/admin/keys` and `DELETE /v1/admin/keys/{key_id}`
create and revoke keys for an authenticated high-assurance sysadmin. They are
implemented in [admin routes](../../services/admin/app/routes.py); use the
route's current request schema and access checks. Store a newly issued raw key
securely, update authorized clients when rotating it, and revoke the old key
when it is no longer needed. These code paths do not prove the status of any
deployed credential or endpoint.

## Browser login

The passwordless flow and session implementation are in
[auth challenges](../../services/admin/app/auth/challenges_router.py) and the
[frontend passwordless client](../../frontend/src/lib/passwordless-auth.ts).
A code is dispatched only for an eligible provisioned identity; the challenge
response does not disclose whether an address is eligible. Outside the guarded
local E2E outbox mode, delivery requires the configured Resend integration.
An accepted challenge response alone therefore does not confirm delivery or
that an account is eligible. See the [root README](../../README.md#security-and-tenant-boundaries)
for the current identity and session caveats.

For local development and frontend routing, start with the
[local setup guide](../guides/LOCAL_SETUP_GUIDE.md) and
[frontend README](../../frontend/README.md). Do not use production credentials
or customer data to test a local stack.
