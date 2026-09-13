# Agent organization — pods, inboxes, scoped keys, suppression (v1)

Status date: 2026-09-12. Verified against `feature/agent-org-pods` in this
tree. Full design rationale and every convention decision behind this
implementation lives in [DESIGN_agent-org.md](../../DESIGN_agent-org.md) —
this page is the shorter, "what's actually true today" companion to that
design doc, kept in `docs/` per this repo's own doc-location convention
(see `docs/persistence/dual-write-cutover.md` for the same style of page).

## What this is

A minimal, real v1 of the primitives behind "an agent organization ...
onboarded per tenant in one function call": DB-backed pods and agent
identities with tenant isolation, one inbox address per agent, API keys
scoped to a single agent (not just a tenant), and a hard suppression gate
in front of the existing supplier-remediation outbound email path.

It does **not** stand up real inbound email, and it is **not yet reachable
in production**. Both limitations are load-bearing — see below before
citing this feature as live or customer-facing.

## Schema

New Postgres schema `agent_org`, added by
[alembic/versions/20260912_bd0c6549153a_v121_agent_org_pods.py](../../alembic/versions/20260912_bd0c6549153a_v121_agent_org_pods.py).
All four tables carry `tenant_id UUID NOT NULL` with ENABLE/FORCE row-level
security, mirroring the `fsma` schema's own-schema RLS convention.

| Table | Purpose |
| --- | --- |
| `agent_org.agent_pods` | One row per pod. `department` is `research`, `outreach`, `ops`, or `legal_review` (`TEXT` + `CHECK`, not a native enum). `UNIQUE (tenant_id, name)` is the pod-level idempotency key. |
| `agent_org.agent_identities` | One row per agent, belonging to exactly one pod. `UNIQUE (tenant_id, pod_id, name)` is the agent-level idempotency key. |
| `agent_org.agent_inboxes` | One inbox per agent. `email_address` is globally unique (derived from the tenant's own slug). `provider` is `"dev"` for every row created today (see Inbox provisioning below). |
| `agent_org.email_suppressions` | Hard-suppression rows (`reason` one of `bounce`, `complaint`, `manual_unsubscribe`). No uniqueness constraint — an address can be suppressed more than once, for audit. |

`api_keys` also gained a nullable `agent_id UUID` column (indexed, not
FK-constrained — the same unconstrained-scoping-column precedent as the
existing `partner_id`), populated only for keys minted through
`mint_agent_scoped_key`.

`docs/schema/expected_schema.json` (the schema-parity CI contract used by
[scripts/schema_parity_audit.py](../../scripts/schema_parity_audit.py))
has **not** been regenerated against this migration in this worktree —
regenerating it against a migrated database is the standard step that
still needs to happen before/at merge, or the schema-parity CI gate will
fail.

## One-call onboarding: `POST /agent-org/onboard`

Implemented in
[services/shared/agent_org/onboarding.py](../../services/shared/agent_org/onboarding.py)
and mounted by
[services/shared/agent_org/router.py](../../services/shared/agent_org/router.py).
Request body is a list of pods (`name`, `department`,
`agent_count` ≤ 50 each); the request is capped at 20 pods and 200 total
agents per call. Requires a tenant-scoped API key carrying the
`agent_org.admin` permission scope — never an agent-scoped key.

- **Idempotent**: re-posting the same tenant + pod config creates zero
  additional rows and mints zero additional keys (enforced via `INSERT ...
  ON CONFLICT DO NOTHING` at the DB layer, plus a partial unique index on
  `api_keys(tenant_id, agent_id) WHERE enabled` so two concurrent calls
  can't mint two keys for the same agent). Growing a pod's `agent_count`
  on a later call correctly adds only the new agents; it is not a no-op in
  that case, by design.
- **Never returns or logs raw key material.** The response
  (`OnboardingResultResponse`) carries `key_ids` only; each minted key's
  raw secret is discarded immediately after use.
- **"17 inboxes across 4 pods" is a capacity, not a seed.** Nothing in
  this change hardcodes those numbers — they're whatever a caller's
  `pods` list sums to. No tenant gets inboxes provisioned automatically.

## Inbox provisioning — dev-only, stated plainly

[services/shared/agent_org/providers.py](../../services/shared/agent_org/providers.py)
defines an `InboxProvider` protocol with exactly one implementation,
`DevInboxProvider`. It deterministically derives an address string
(`{agent-slug}@agents.{tenant-slug}.regengine.dev`) and records it.

**It does not create an internet-routable mailbox and does not talk to any
external email provider.** There is no MX record, no mailbox, no inbound
webhook behind that domain. No mail sent to an address this feature
returns will ever be received anywhere. No live email-provider
credentials (e.g. Postmark) exist in this environment. The protocol is
shaped so a real provider could implement it later without touching the
onboarding or DB layers, but that provider does not exist in this change.

Provider selection reads `AGENT_ORG_INBOX_PROVIDER` (default `"dev"`); any
other value raises rather than silently falling back.

## Scoped agent API keys

`mint_agent_scoped_key`
([services/shared/agent_org/keys.py](../../services/shared/agent_org/keys.py))
is a thin, validating wrapper around the existing
`DatabaseAPIKeyStore.create_key`. Capabilities are restricted to a fixed
allowlist — `agent.inbox.read`, `agent.inbox.send`,
`agent.suppression.read` — enforced in code, not left to caller input.
`require_agent_key`
([services/shared/agent_org/authz.py](../../services/shared/agent_org/authz.py))
is a FastAPI dependency factory that layers agent-level isolation on top
of the existing `require_api_key`: a key valid for tenant A / agent 1 is
rejected against agent 2's resources even within the same tenant, and
cross-tenant isolation falls out of the existing tenant-key auth stack
underneath it.

**No mounted route calls `require_agent_key` yet.** It is fully unit
tested as a dependency (cross-agent rejection, cross-tenant rejection,
missing-capability rejection, non-agent-key rejection), but the only HTTP
surface this feature exposes today is the onboarding endpoint, which is
authenticated with a full tenant key, not an agent-scoped one. Minted
agent keys are real, valid, and correctly isolated — there is simply
nothing for an agent to call with one yet (no inbox-read, inbox-send, or
suppression-read endpoint is mounted). That is intentionally scoped out
of this v1, not an oversight to paper over.

## Suppression enforcement

`is_suppressed`
([services/shared/agent_org/suppression.py](../../services/shared/agent_org/suppression.py))
is wired as a hard, unconditional gate in
`NotificationOutboxDrainer._drain_one`
([services/ingestion/app/remediation/delivery.py](../../services/ingestion/app/remediation/delivery.py)),
immediately before the existing outbound email send call. A suppressed
address is recorded as skipped (`reason="recipient_suppressed"`) and the
send is never attempted — proven by a unit test whose stub email sender
calls `pytest.fail` if it is ever invoked for a suppressed row.

`record_suppression` (same module) inserts a suppression row and is
covered by unit tests, but **no HTTP or admin-UI surface calls it today.**
The only way to populate `agent_org.email_suppressions` right now is
directly, e.g. from a script or a future admin route — there is no
`POST` endpoint to suppress an address yet.

## Production rollout status

The router is registered in
[server/router_policy.py](../../server/router_policy.py) as `"agent_org"`,
listed under `EXPERIMENTAL_ROUTERS`, and is **not** in
`PRODUCTION_ENABLED_ROUTERS`. Production requires `ENABLED_ROUTERS` to
match the release-approved set exactly, so `/agent-org/onboard` cannot be
reached in production today without a deliberate code change adding
`agent_org` to `PRODUCTION_ENABLED_ROUTERS` (a release decision, not a
config flip) — plus regenerating the schema-parity snapshot above. In
local development, tests, and any non-production environment without an
explicit `DISABLED_ROUTERS=agent_org`, the router mounts by default.

## Test coverage

Over 100 unit tests across
[services/shared/tests/test_agent_org_*.py](../../services/shared/tests/)
and
[services/ingestion/tests/remediation/test_suppression_gate.py](../../services/ingestion/tests/remediation/test_suppression_gate.py),
all passing against the in-memory SQLite path / stub sessions this
repo's other unit-level API-key and remediation tests already use — **no
live database, live Stripe call, or live email-provider call is required
or made** by any of this feature's tests. There is no live-DB integration
test for the `agent_org` schema's RLS policies themselves yet (compare to
`tests/migrations/test_seeded_mid_chain_upgrade.py` for the pattern this
would eventually follow).

## Known deviations, called out on purpose

- `onboard_tenant_agent_org` is `async def` but mixes a synchronous
  `Session` for pod/agent/inbox row writes with an *awaited* async
  `DatabaseAPIKeyStore` call for key minting — there is no sync
  key-minting path to call instead. See DESIGN_agent-org.md §8 for the
  full reasoning and the commit-before-mint ordering this requires to
  avoid orphaning a live key for a rolled-back agent row.
- `department` and `email_suppressions.reason` are `TEXT` + `CHECK`
  constraints, not native Postgres `ENUM` types, matching this
  codebase's existing `fsma.*` convention.
