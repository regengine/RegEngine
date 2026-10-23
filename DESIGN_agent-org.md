# Agent Organization (pods, inboxes, scoped keys, suppression) — v1 Design

Status: proposed. Scope: v1, honestly bounded. This document is the basis for
implementation in this worktree (`feature/agent-org-pods`).

## 0. What this is honestly building

RegEngine's marketing describes "an agent organization... 17 inboxes across 4
isolated pods, onboarded per tenant in one function call." Today none of that
exists — no pods table, no agent identities, no inboxes, no scoped agent
keys, no suppression list. This design builds a real, minimal v1 of the
underlying primitives:

- Real DB-backed pods/agents/inboxes with tenant isolation (RLS), created by
  a single idempotent function call.
- API keys scoped to a single agent (not just a tenant), with a restricted
  capability set, provably unable to reach another agent's or tenant's data.
- A suppression list enforced as a hard gate in front of the *existing*
  outbound remediation email path (`services/ingestion/app/remediation/delivery.py`).
- A pluggable inbox-provisioning interface with exactly one real
  implementation: `DevInboxProvider`, which deterministically derives an
  address string and records it. **It does not create an internet-routable
  mailbox and does not talk to any external email provider.** No live email
  provider credentials (e.g. Postmark) exist in this environment. The
  interface is shaped so a real provider could be added later without
  touching the onboarding/DB layer, but that provider does not exist in this
  change and must not be claimed to.
- "17 inboxes across 4 pods" is a *capacity* the schema and onboarding call
  support for any tenant that configures 4 pods with a combined 17 agents —
  it is not a fixed, pre-seeded number this change creates for every tenant.
  Nothing in this change hardcodes "17" or "4"; those are caller-supplied
  `pods: list[PodSpec]` at onboarding time.

## 1. New schema: `agent_org`

New Postgres schema `agent_org`, mirroring the `fsma` schema's own-schema
convention (see `alembic/versions/20260716_c7a1e5f2b9d4_v095_supplier_remediation_slice.py`).
All tables get `tenant_id UUID NOT NULL` + `ENABLE/FORCE ROW LEVEL SECURITY`
using the existing `_tenant_rls()` helper pattern (predicate
`tenant_id = get_tenant_context()`, from `public.get_tenant_context()`,
pinned fail-hard by v097 — `alembic/versions/20260721_e4d7b2a9c561_v097_pin_get_tenant_context_fail_hard.py`).

### 1.1 `agent_org.agent_pods`

```sql
CREATE TABLE IF NOT EXISTS agent_org.agent_pods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    department TEXT NOT NULL
        CHECK (department IN ('research', 'outreach', 'ops', 'legal_review')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, name)
);
CREATE INDEX IF NOT EXISTS idx_agent_pods_tenant ON agent_org.agent_pods (tenant_id);
```

`UNIQUE (tenant_id, name)` is what makes onboarding idempotent at the pod
level: re-running onboarding for the same `(tenant_id, pod.name)` finds the
existing row (`ON CONFLICT (tenant_id, name) DO NOTHING RETURNING id`, else a
`SELECT`) instead of creating a duplicate. `department` is a `CHECK`
constraint, not a native Postgres `ENUM` type — consistent with how
`fsma.remediation_cases.status` and `fsma.manifest_records.validation_status`
are declared as `TEXT ... CHECK (...)` in the v095 migration (`ALTER TYPE ...
ADD VALUE` on real enums is the harder, less-used path in this codebase; the
CHECK-constraint convention wins for a first cut and is trivially
migratable later).

`tenants(id)` is `services/admin/app/sqlalchemy_models.py::TenantModel` (table
`tenants`, `id` a `GUID()`/UUID primary key, `slug` unique — `slug` is reused
below as the "tenant-subdomain" component of inbox addresses).

### 1.2 `agent_org.agent_identities`

```sql
CREATE TABLE IF NOT EXISTS agent_org.agent_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pod_id UUID NOT NULL REFERENCES agent_org.agent_pods(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, pod_id, name)
);
CREATE INDEX IF NOT EXISTS idx_agent_identities_tenant_pod
    ON agent_org.agent_identities (tenant_id, pod_id);
```

`tenant_id` is denormalized onto this table (not derived only via `pod_id`)
so the RLS predicate and every downstream query can filter on
`agent_identities.tenant_id` directly without a join — same denormalization
choice v095 makes for `manifest_records.tenant_id` alongside its
`ingestion_run_id` FK. `role` is free text at v1 (e.g. `"researcher"`,
`"outreach_lead"`) — not constrained to an enum, since role naming is
expected to vary per pod/department and isn't yet an authorization input
(authorization runs on API-key `scopes`, not on this column).

### 1.3 `agent_org.agent_inboxes`

```sql
CREATE TABLE IF NOT EXISTS agent_org.agent_inboxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID NOT NULL REFERENCES agent_org.agent_identities(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email_address TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    provider_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agent_inboxes_tenant_agent
    ON agent_org.agent_inboxes (tenant_id, agent_id);
```

`email_address UNIQUE` is global (not per-tenant) because addresses are
derived from the tenant's own slug (`{agent-slug}@agents.{tenant-slug}.regengine.dev`)
and are meant to be globally addressable mail endpoints — two tenants must
never be able to collide on the same address. `provider` is the provider key
(`"dev"` for v1's only implementation); `provider_ref` is an opaque
provider-side identifier (`None` for `DevInboxProvider`, which has no
external side to reference — reserved for a future real provider's mailbox/
stream id).

### 1.4 `agent_org.email_suppressions`

```sql
CREATE TABLE IF NOT EXISTS agent_org.email_suppressions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email_address TEXT NOT NULL,
    reason TEXT NOT NULL
        CHECK (reason IN ('bounce', 'complaint', 'manual_unsubscribe')),
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_email_suppressions_tenant_email
    ON agent_org.email_suppressions (tenant_id, email_address);
```

`email_address` is stored and matched lower-cased and trimmed at the
application layer (see `_normalize_email` below) rather than via a
`CITEXT` column, since no other table in this codebase uses `CITEXT` for
email columns (`fsma.remediation_tokens.supplier_email` is plain `TEXT`
too) — consistent with existing convention rather than introducing a new
column type. No `UNIQUE` constraint on `(tenant_id, email_address)`: an
address can be re-suppressed for a new reason (e.g. bounce, then later a
manual unsubscribe) and both rows are kept for audit; `is_suppressed()`
only cares whether *any* row matches.

`is_suppressed(tenant_id, email) -> bool` helper (module-level function, not
a Postgres function — matching how `fsma` helpers like
`tokens._token_skip_reason` live in Python next to their table, not as
plpgsql):

```python
def is_suppressed(session: Any, *, tenant_id: str, email_address: str) -> bool:
    """True iff email_address has an active suppression row for tenant_id.

    Caller must already have the tenant GUC set (set_tenant_guc) — this
    function adds tenant_id as a belt-and-suspenders predicate on top of
    RLS, matching remediation.delivery's own query style.
    """
```

Implementation: one parameterized `SELECT 1 FROM agent_org.email_suppressions
WHERE tenant_id = CAST(:tenant_id AS uuid) AND email_address = :email LIMIT 1`
via `sqlalchemy.text`, normalizing `email_address` with
`_normalize_email(s) = s.strip().lower()` on both write and read paths.

### 1.5 Migration file

New file: `alembic/versions/20260912_bd0c6549153a_v121_agent_org_pods.py`
(date stamped for today; revision id generated the same way existing ones
are — a random 12-hex-char alembic revision id). `down_revision =
"c6a120b4e901"` <!-- pragma: allowlist secret --> (the current head, `20260904_..._v120_rule_citations.py`).
Structure mirrors `20260716_c7a1e5f2b9d4_v095_supplier_remediation_slice.py`
exactly: `op.execute("CREATE SCHEMA IF NOT EXISTS agent_org")`, one
`_create_tables()` using `CREATE TABLE IF NOT EXISTS` + inline indexes, then
`_tenant_rls(...)` calls for all four tables reusing the same `_tenant_rls`
helper function body (copied into the new migration file, since each
migration file in this repo is self-contained rather than importing from a
shared migrations-lib module — matches existing precedent, e.g. v051 and
v095 each define their own RLS-application logic rather than sharing it).
`downgrade()` drops the four tables in FK-safe order
(`agent_inboxes`, `agent_identities`, `agent_pods`, `email_suppressions`)
then `DROP SCHEMA IF EXISTS agent_org` only if empty (skip the schema drop
entirely to be safe — other migrations don't drop their schema either, e.g.
`downgrade()` in v095 never does `DROP SCHEMA fsma`).

### 1.6 `api_keys.agent_id` column (extends existing table, not a new one)

Migration also adds one nullable column to the existing `api_keys` table
(same file, same migration, since it's one logical change):

```sql
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS agent_id UUID;
CREATE INDEX IF NOT EXISTS ix_api_keys_agent_id ON api_keys (agent_id);
```

This follows the exact precedent of the existing `partner_id` column on
`APIKeyModel` (`services/shared/api_key_store.py:180-187`): "NULL for
non-partner keys... populated for keys issued to partners." `agent_id` is
the same shape: NULL for ordinary tenant keys, populated for keys minted
via `mint_agent_scoped_key()`. No FK constraint to `agent_org.agent_identities`
is added — `api_keys` lives in the `public` schema and is looked up
*before* any tenant/agent context is established (see
`set_api_key_lookup_context` in `api_key_store.py`), so keeping it a plain
UUID column (like `partner_id` is a plain string, not FK'd either) avoids
adding a cross-schema FK to a pre-auth-path table. The application layer
enforces the reference at mint time and at validation time instead
(`extra_data` is explicitly documented as *not* to be used for
authorization decisions — `api_key_store.py:1049-1055` — so a real column is
required here, not a metadata field).

## 2. Scoped agent API keys

### 2.1 `APIKeyModel` / `APIKeyResponse` change

`services/shared/api_key_store.py`:

- `APIKeyModel.agent_id = Column(TenantUUIDText(), nullable=True, index=True)`
  — reuse the existing `TenantUUIDText` type decorator (already handles the
  uuid-on-Postgres / text-on-SQLite split that `tenant_id` and `partner_id`
  need; `agent_id` needs the identical treatment since it's also a
  cross-dialect UUID FK-shaped column, and SQLite-backed unit tests are the
  primary place this matters, per `TenantUUIDText`'s own docstring).
- `APIKeyResponse.agent_id: Optional[str] = None`, with the same
  `@field_validator("agent_id", mode="before")` `str(v) if v is not None else
  None` coercion already applied to `tenant_id` (same asyncpg-returns-UUID
  problem — `api_key_store.py:258-265`).
- `DatabaseAPIKeyStore.create_key(..., agent_id: Optional[str] = None)` — one
  new keyword-only parameter threaded through to `APIKeyModel(agent_id=...)`
  and into the returned `APIKeyCreateResponse`.

### 2.2 Minting: `mint_agent_scoped_key`

New function in `services/shared/agent_org/keys.py`:

```python
AGENT_SCOPE_PREFIX = "agent."

# The only capabilities an agent-scoped key may ever carry. Anything outside
# this set cannot be granted via mint_agent_scoped_key, regardless of caller
# input — the allowlist is enforced in code, not left to caller discipline.
AGENT_KEY_CAPABILITIES: frozenset[str] = frozenset({
    "agent.inbox.read",
    "agent.inbox.send",
    "agent.suppression.read",
})

async def mint_agent_scoped_key(
    key_store: DatabaseAPIKeyStore,
    *,
    tenant_id: str,
    agent_id: str,
    name: str,
    capabilities: Sequence[str],
    created_by: Optional[str] = None,
) -> APIKeyCreateResponse:
    """Mint an API key scoped to exactly one agent.

    Raises ValueError if any capability is outside AGENT_KEY_CAPABILITIES.
    The resulting key's `.tenant_id` and `.agent_id` are both set; scopes
    are stored as `agent.<capability>` (already namespaced — capabilities
    are passed in already-prefixed, e.g. "agent.inbox.read") plus no
    wildcard/tenant-wide scope is ever added. Rate limits default lower
    than a tenant key's (agent keys are meant for narrow automation, not
    bulk API usage): rate_limit_per_minute=30 unless overridden.
    """
```

This is a thin, validating wrapper around the *existing*
`DatabaseAPIKeyStore.create_key`, not a parallel key system — it calls
`key_store.create_key(name=..., tenant_id=tenant_id, agent_id=agent_id,
scopes=list(capabilities), rate_limit_per_minute=30, ...)`. Capability
validation (the `frozenset` check) happens here because
`DatabaseAPIKeyStore.create_key` itself is intentionally generic and
doesn't know about the agent-org capability model, the same way
`change_scopes()` is the dedicated privilege-sensitive wrapper for scope
mutation rather than folding validation into `update_key()`
(`api_key_store.py:1019-1027`'s own comment explains that split).

### 2.3 Enforcement: cross-agent / cross-tenant isolation

New dependency factory in `services/shared/agent_org/authz.py`, following
`services/ingestion/app/authz.py`'s `require_permission()` shape:

```python
class AgentPrincipal(BaseModel):
    key_id: str
    tenant_id: str
    agent_id: str
    scopes: list[str] = Field(default_factory=list)


def require_agent_key(required_capability: str):
    """FastAPI dependency: authenticate + require an agent-scoped key whose
    agent_id matches the path's {agent_id}, and whose scopes grant
    required_capability. Reuses shared.auth.require_api_key for the actual
    credential validation (hash check, enabled/expiry/revocation, rate
    limiting) — this only adds the agent-scope layer on top, exactly as
    services/ingestion/app/authz.require_permission layers tenant-scope
    checks on top of the same require_api_key.
    """
    async def _dependency(
        request: Request,
        agent_id: str,  # bound from the route's path param of the same name
        api_key: APIKeyResponse = Depends(require_api_key),
    ) -> AgentPrincipal:
        key_agent_id = getattr(api_key, "agent_id", None)
        if not key_agent_id:
            raise HTTPException(403, "Key is not agent-scoped")
        if str(key_agent_id) != str(agent_id):
            # Cross-agent: the key is valid but for a *different* agent.
            raise HTTPException(403, "Key is not scoped to this agent")
        if not has_permission(api_key.scopes or [], required_capability):
            raise HTTPException(403, "Missing capability")
        return AgentPrincipal(
            key_id=api_key.key_id,
            tenant_id=str(api_key.tenant_id),
            agent_id=str(key_agent_id),
            scopes=list(api_key.scopes or []),
        )
    return _dependency
```

Cross-tenant isolation falls out of `require_api_key` itself: it already
407/403s any key whose `tenant_id` doesn't match the resolved tenant
context (`reconcile_tenant_scope`, `services/shared/auth.py:498-554`) and
rejects tenantless/workload keys on tenant APIs
(`services/shared/auth.py:370-384`). `require_agent_key` adds the
*additional* agent-level narrowing that doesn't exist today: a valid
tenant-scoped key for tenant A, agent 1 must not be usable against agent
2's resources even within the same tenant. That's the isolation property
this whole scoped-key feature exists to prove, and it's a pure Python
equality check (`key_agent_id != agent_id`) plus the capability allowlist
— no new DB round trip.

### 2.4 Tests: `services/shared/tests/test_agent_org_keys.py`

Using the in-memory SQLite path already exercised by
`test_api_key_store_set_context.py` / `test_change_scopes.py` (no live DB
required):

- `test_mint_agent_scoped_key_rejects_unknown_capability` — capability
  outside `AGENT_KEY_CAPABILITIES` raises `ValueError`.
- `test_agent_key_cannot_access_different_agent` — mint two agent-scoped
  keys under the *same* tenant for two different `agent_id`s; call
  `require_agent_key("agent.inbox.read")`'s inner dependency directly with
  agent A's key but agent B's `agent_id` path param; assert `HTTPException`
  403.
- `test_agent_key_cannot_access_different_tenant` — mint an agent key under
  tenant A; simulate a request resolved to tenant B's context; assert
  `require_api_key`'s existing tenant-mismatch path (or the agent
  dependency layered on top) rejects it — proving the *combination* still
  holds, not just the new check in isolation.
- `test_agent_key_missing_capability_rejected` — a key scoped to
  `agent.inbox.read` only is rejected by
  `require_agent_key("agent.inbox.send")`.
- `test_tenant_key_without_agent_id_rejected_by_agent_dependency` — an
  ordinary tenant-wide key (`agent_id is None`) is rejected by
  `require_agent_key`, proving agent-only routes can't be reached with a
  regular tenant key.

## 3. Inbox provisioning: `services/shared/agent_org/providers.py`

```python
class InboxProvider(Protocol):
    """Provisions one mailbox-shaped inbox for one agent.

    Implementations own address generation and any external provider call;
    onboarding only records what they return. A real implementation (e.g.
    Postmark's server + inbound-webhook API) would create genuine routable
    mail infrastructure here — DevInboxProvider, the only implementation in
    this change, does not.
    """

    def provision(
        self, *, tenant_slug: str, agent_slug: str, tenant_id: str, agent_id: str
    ) -> ProvisionedInbox: ...


@dataclass(frozen=True)
class ProvisionedInbox:
    email_address: str
    provider: str
    provider_ref: Optional[str]


class DevInboxProvider:
    """Deterministic, local-only inbox address generator.

    HONEST LIMITATION: this does not create a real, internet-routable
    mailbox. It does not talk to any external email service. No inbound
    mail sent to the address it returns will ever be received anywhere —
    there is no MX record, no mailbox, no webhook target behind
    "agents.<tenant-slug>.regengine.dev". It exists so agent_org has a
    working, testable provisioning path in an environment with no live
    email-provider credentials. A real provider (e.g. PostmarkInboxProvider
    using Postmark's server + inbound-message-stream API to create a real
    inbound address and webhook) can implement this same InboxProvider
    protocol later without any change to onboarding.py or the DB schema.
    """

    provider_name = "dev"

    def provision(self, *, tenant_slug, agent_slug, tenant_id, agent_id) -> ProvisionedInbox:
        address = f"{agent_slug}@agents.{tenant_slug}.regengine.dev"
        return ProvisionedInbox(email_address=address, provider=self.provider_name, provider_ref=None)
```

`agent_slug` is derived the same way tenant slugs are:
`re.sub(r"[^a-z0-9]+", "-", agent_name.strip().lower()).strip("-") or
"agent"`, reusing the exact regex from
`services/admin/app/tenant_slug_helpers.py::_slugify_tenant_name` (extracted
into `services/shared/agent_org/slugs.py::slugify(name: str, *, fallback:
str) -> str` so both admin's tenant slugging and agent_org's agent/pod
slugging share one implementation instead of two copies of the same regex —
this is a small shared-code extraction, not new tenant-slug behavior).
`tenant_slug` for address generation is read from `tenants.slug` (already
unique per tenant).

Provider selection: `get_inbox_provider() -> InboxProvider` reads
`os.environ.get("AGENT_ORG_INBOX_PROVIDER", "dev")` and returns
`DevInboxProvider()` for `"dev"` (the only registered value); any other
value raises `RuntimeError(f"Unknown inbox provider: {value!r}")` rather
than silently falling back, so a future real provider must be explicitly
wired in `providers.py`'s registry, never guessed.

## 4. Suppression enforcement in the outbound path

Target: `services/ingestion/app/remediation/delivery.py`,
`NotificationOutboxDrainer._drain_one` (currently at
`services/ingestion/app/remediation/delivery.py:229` in this worktree,
right before `provider_id = self._send(row["recipient"], ...)`).

Change: insert one gate immediately before the `self._send(...)` call:

```python
from shared.agent_org.suppression import is_suppressed

...

def _drain_one(self, tenant_id: str, row: Dict[str, Any]) -> str:
    if not row["recipient"]:
        return self._finish_skipped(tenant_id, row, reason="no_recipient")

    if is_suppressed(self._session, tenant_id=tenant_id, email_address=row["recipient"]):
        return self._finish_skipped(tenant_id, row, reason="recipient_suppressed")

    token_id = (row["payload"] or {}).get("token_id")
    ...
```

This is a hard gate: it runs unconditionally, before any token
reminting/network call, for every row this drainer would otherwise send —
so a suppressed address can never receive mail via this path regardless of
`payload`/token state. `_finish_skipped` already exists
(`services/ingestion/app/remediation/delivery.py`, used today for
`no_recipient`) and records the row as terminally skipped with a `reason`
column value — `"recipient_suppressed"` is a new reason string alongside
the existing ones, no schema change needed since `reason` is already a free
`TEXT` column on `fsma.notification_outbox` (verified: no `CHECK` constraint
on that column restricts values, unlike `status`).

`is_suppressed` itself lives in `services/shared/agent_org/suppression.py`
(not `delivery.py`) so it's the same function agent-org routes and any
future outbound path can call — a second call site (e.g. a future
agent-inbox outbound send) reuses it instead of re-querying
`agent_org.email_suppressions` ad hoc.

### 4.1 Test: `services/ingestion/tests/remediation/test_suppression_gate.py`

Unit-level, no live DB (per the "avoid live DB in unit tests" instruction) —
uses a stub session object (the test needs no live database):

```python
class _StubSession:
    """Fakes just enough of Session.execute for is_suppressed()'s one query."""
    def __init__(self, suppressed_emails: set[str]):
        self._suppressed = suppressed_emails

    def execute(self, stmt, params=None):
        email = (params or {}).get("email_address")
        hit = email in self._suppressed
        return _StubResult(hit)


def test_drain_one_skips_suppressed_recipient(monkeypatch):
    session = _StubSession({"blocked@example.com"})
    drainer = NotificationOutboxDrainer(session, email_sender=lambda *a: pytest.fail("must not send"))
    row = {"id": "...", "recipient": "blocked@example.com", "subject": "s", "body": "b", "payload": {}, "attempts": 0}
    outcome = drainer._drain_one("tenant-1", row)
    assert outcome == "skipped"
    # and the recorded skip reason == "recipient_suppressed" (assert via the
    # _finish_skipped call — stub session records the UPDATE statement/params
    # and the test asserts params["reason"] == "recipient_suppressed").
```

The `email_sender=lambda *a: pytest.fail(...)` is the actual proof required
by the spec ("a suppressed address must never receive mail from that path")
— if the gate is ever removed or reordered after the send call, this test
fails immediately because the stub sender is invoked.

## 5. One-call onboarding: `services/shared/agent_org/onboarding.py`

```python
@dataclass(frozen=True)
class PodSpec:
    name: str
    department: str  # one of the four CHECK-constrained values
    agent_count: int


@dataclass(frozen=True)
class OnboardingResult:
    tenant_id: str
    pods_created: int
    agents_created: int
    inboxes_created: int
    keys_created: int
    inbox_addresses: list[str]
    key_ids: list[str]  # key_id only — never raw_key


async def onboard_tenant_agent_org(
    db: Session,
    tenant_id: str,
    pods: list[PodSpec],
    *,
    key_store: Optional[DatabaseAPIKeyStore] = None,
    inbox_provider: Optional[InboxProvider] = None,
) -> OnboardingResult:
    """Create pods, agents, inboxes and scoped keys for a tenant in one call.

    Idempotent: re-calling with the same tenant_id + pods (matched by
    (tenant_id, pod.name) and, within a pod, by a deterministic per-index
    agent name "<pod.name>-agent-<n>") creates zero additional rows and
    mints zero additional keys — it returns the counts/addresses/key_ids
    of the *existing* rows instead. Idempotency is enforced at the DB layer
    (UNIQUE (tenant_id, name) on both agent_pods and, scoped by pod_id, on
    agent_identities) via INSERT ... ON CONFLICT DO NOTHING RETURNING id,
    falling back to SELECT when the INSERT affects 0 rows — the same
    "claim-or-read" shape delivery.py's _claim() uses for outbox rows.
    """
```

Key design decisions:

- **`db` is a synchronous `Session`** (matching
  `services/shared/database.py::get_db_session` and every function in
  `services/ingestion/app/remediation/service.py`, which takes a sync `db`
  first positional arg and issues raw parameterized `text()` SQL) — pod,
  agent and inbox row writes use that same raw-SQL, `set_tenant_guc`-first
  style, not the ORM. **The function itself is `async def`** only because it
  must `await key_store.create_key(...)` once per agent — `DatabaseAPIKeyStore`
  is fully async with no sync counterpart (`services/shared/api_key_store.py`).
  This mixes a sync `Session` and an async key store inside one `async def`,
  which is a deviation worth flagging explicitly (see §7) — it is not an
  established pattern elsewhere in this codebase, but no sync key-minting
  path exists to call instead, and rewriting `DatabaseAPIKeyStore` to be
  dual sync/async is out of scope for this feature.
- **Agent naming for idempotency**: since the spec's `PodSpec` only carries
  `agent_count` (not per-agent names), agents are named deterministically
  as `f"{pod.name}-agent-{i}"` for `i in range(1, agent_count + 1)`, which
  is what makes `UNIQUE (tenant_id, pod_id, name)` double as the
  idempotency key at the agent level, exactly mirroring the pod level.
  Calling `onboard_tenant_agent_org` twice with `agent_count=3` then later
  `agent_count=5` for the same pod is **not** idempotent-as-a-no-op in the
  strict sense — it correctly creates the two new agents (`-agent-4`,
  `-agent-5`) since those names don't yet exist. The spec's idempotency
  requirement ("calling it twice for the same tenant+pod config must not
  duplicate rows") is satisfied for identical repeated input; growing the
  config is treated as an intentional incremental onboarding, not a bug.
- **Inbox/key idempotency**: for each agent, before provisioning inbox
  or minting a key, the function checks
  `SELECT id FROM agent_org.agent_inboxes WHERE agent_id = :aid` and
  `SELECT key_id FROM api_keys WHERE agent_id = :aid AND enabled = true`
  respectively; only provisions/mints when absent. This means a second
  onboarding call for an existing agent creates zero inboxes, zero keys —
  it reads back the existing `email_address` / `key_id` into the returned
  `OnboardingResult` instead.
- **Never logs or returns raw secrets**: `OnboardingResult.key_ids` holds
  only `key_id` strings; `mint_agent_scoped_key`'s `APIKeyCreateResponse.raw_key`
  is discarded by `onboard_tenant_agent_org` after minting (not stored, not
  logged) — the caller of the onboarding function never receives raw keys
  for agents created on a *second* call anyway, and the design deliberately
  does not add a "return raw keys once at onboarding" feature, since the
  spec explicitly says "never raw secrets in the return value/logs" with no
  carve-out. A tenant admin who needs an agent's raw key uses the existing
  key-rotation/creation admin surface per-agent afterward, out of scope
  here.
- **Transactional shape (revised during self-review)**: pods/agents/inboxes
  are written under one `set_tenant_guc(db, tenant_id)` call per commit
  boundary, on `db`. Key minting runs on `DatabaseAPIKeyStore`'s own,
  separate async engine/connection, which commits immediately and
  independently of `db`. Because of that, `onboard_tenant_agent_org`
  deviates from the usual "the router's `db_session` dependency owns
  commit/rollback, not the service function" rule
  (`service.ingest_manifest`'s style): it calls `db.commit()` itself,
  once per agent, immediately before minting that agent's key — followed
  by re-applying `set_tenant_guc` (transaction-scoped, so it doesn't
  survive a commit). A first draft of this function only called
  `db.flush()` before minting, which does **not** give the "a key is
  never minted for an agent row that didn't actually get committed"
  guarantee this design claims: a flush is visible only inside the same,
  still-open transaction, so a later exception in the same onboarding
  call (a different pod/agent, or the key-store call itself) would roll
  back this agent's pod/agent/inbox rows while its already-committed key
  survived — an orphaned, still-valid agent-scoped credential pointing at
  an agent that no longer exists, with no FK to catch it. Committing per
  agent before minting closes that gap; a crash between "agent row
  committed" and "key minted" is still recovered by simply re-calling
  onboarding, which is idempotent per the inbox/key check above and will
  mint the missing key on retry.

## 6. API route: `POST /agent-org/onboard`

New router: `services/shared/agent_org/router.py`

```python
router = APIRouter(prefix="/agent-org", tags=["Agent Organization"])

class PodSpecRequest(BaseModel):
    name: str
    department: Literal["research", "outreach", "ops", "legal_review"]
    agent_count: int = Field(gt=0, le=50)

class OnboardRequest(BaseModel):
    pods: list[PodSpecRequest]

@router.post("/onboard", response_model=OnboardingResultResponse)
async def onboard(
    body: OnboardRequest,
    principal: IngestionPrincipal = Depends(require_permission("agent_org.admin")),
    db_session=Depends(get_db_session),
):
    tid = resolve_tenant(None, principal)
    result = await onboard_tenant_agent_org(
        db_session, tid, [PodSpec(**p.model_dump()) for p in body.pods]
    )
    return OnboardingResultResponse(**asdict(result))
```

Mounted in `server/main.py` following the exact
`_router_enabled(...)` / `include_owned_router(...)` pattern used for every
other domain router (`server/main.py:701-706` for remediation is the direct
template):

```python
if _router_enabled("agent_org"):
    from services.shared.agent_org.router import router as agent_org_router

    include_owned_router(app, agent_org_router, owner="agent_org", tags=["Agent Organization"])
```

placed in the same file, in its own new section comment block (e.g. after
the "DOMAIN: COMPLIANCE CONTROL PLANE" block), so it participates in
`_router_enabled`'s existing env-var-gated rollout mechanism
(`server/main.py:406`) the same as every other domain.

New permission scope: `agent_org.admin` (tenant admin/owner capability to
run onboarding), following `has_permission`'s dot-namespace convention
(`services/shared/permissions.py`) — distinct from the `agent.*` capability
namespace used by agent-scoped keys themselves (§2.1), since onboarding is
performed with a full tenant key, never an agent-scoped one.

## 7. Files created / edited (summary)

Created:
- `services/shared/agent_org/__init__.py`
- `services/shared/agent_org/slugs.py`
- `services/shared/agent_org/providers.py`
- `services/shared/agent_org/suppression.py`
- `services/shared/agent_org/keys.py`
- `services/shared/agent_org/authz.py`
- `services/shared/agent_org/onboarding.py`
- `services/shared/agent_org/router.py`
- `alembic/versions/20260912_bd0c6549153a_v121_agent_org_pods.py`
- `services/shared/tests/test_agent_org_onboarding.py`
- `services/shared/tests/test_agent_org_keys.py`
- `services/shared/tests/test_agent_org_providers.py`
- `services/ingestion/tests/remediation/test_suppression_gate.py`

Edited:
- `services/shared/api_key_store.py` — add `agent_id` column/field/coercion
  (§2.1).
- `services/ingestion/app/remediation/delivery.py` — suppression gate in
  `_drain_one` (§4).
- `server/main.py` — mount the new router (§6).
- `services/admin/app/tenant_slug_helpers.py` — extract `_slugify_tenant_name`'s
  regex into the new shared `services/shared/agent_org/slugs.py::slugify`
  and have `_slugify_tenant_name` delegate to it (kept as a thin wrapper so
  its existing call sites/tests are untouched).

## 8. Deviations from a literal reading of the spec (to call out up front)

1. **"17 inboxes across 4 isolated pods"** is not hardcoded anywhere — it's
   a capacity the schema/onboarding call supports for a caller-chosen
   `pods` config that happens to sum to 17 agents across 4 pods. No seed
   data ships 17 inboxes for any tenant automatically.
2. **`DevInboxProvider` provisions nothing externally.** It generates and
   records a deterministic address string only. This is stated as a hard
   limitation in the provider's own docstring, in this design doc, and must
   be stated the same way in the final report — never described as "real
   inbound email."
3. **`onboard_tenant_agent_org` is `async def` mixing a sync `db.Session`
   with an awaited async `DatabaseAPIKeyStore`** — there is no existing
   sync/async-mixed precedent exactly like this elsewhere in the codebase;
   it's the necessary consequence of `DatabaseAPIKeyStore` being async-only
   while the remediation-style row-write helpers this module's DB code is
   modeled on are sync. Flagged here rather than silently introduced.
4. **`agent_id` is a plain nullable UUID column on `api_keys`, not
   FK-constrained** to `agent_org.agent_identities` — deliberately matching
   `partner_id`'s existing precedent of an unconstrained scoping column on
   this specific pre-auth-path table (§1.6).
5. **No Postgres native `ENUM` types** — `department` and
   `email_suppressions.reason` are `TEXT` + `CHECK`, matching the
   established convention in `fsma.*` tables rather than the spec's literal
   phrase "department enum" being read as a native `CREATE TYPE ... AS
   ENUM`.
