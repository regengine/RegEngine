"""One-call tenant onboarding: pods, agents, inboxes, scoped keys.

See ``DESIGN_agent-org.md`` section 5 for the full design and section 8
for deviations called out up front — in particular:

* ``onboard_tenant_agent_org`` is ``async def`` mixing a synchronous
  ``Session`` (matching ``services/ingestion/app/remediation/service.py``'s
  raw-``text()``, ``set_tenant_guc``-first style for pod/agent/inbox
  writes) with an *awaited* async ``DatabaseAPIKeyStore`` (there is no
  sync key-minting path to call instead). This is a deliberate,
  documented deviation, not an established pattern elsewhere in this
  codebase.
* Idempotency is enforced at the DB layer via ``INSERT ... ON CONFLICT
  DO NOTHING RETURNING id``, falling back to a plain ``SELECT`` when the
  insert affects zero rows — the same "claim-or-read" shape
  ``delivery.py``'s ``_claim()`` uses for outbox rows.
* Raw secrets are never returned or logged: ``OnboardingResult.key_ids``
  holds only ``key_id`` strings. Each ``APIKeyCreateResponse.raw_key``
  minted here is discarded immediately after use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from shared.tenant_context import set_tenant_guc
from sqlalchemy import text

from .keys import AGENT_KEY_CAPABILITIES, mint_agent_scoped_key
from .providers import InboxProvider, agent_slug, get_inbox_provider

if TYPE_CHECKING:
    from shared.api_key_store import DatabaseAPIKeyStore

#: Departments a pod may declare — mirrors the migration's CHECK
#: constraint on ``agent_org.agent_pods.department``.
POD_DEPARTMENTS = frozenset({"research", "outreach", "ops", "legal_review"})

#: Capabilities granted to a key minted during onboarding. Onboarding
#: mints a working automation key by default; capabilities can be
#: narrowed later via the ordinary key-management surface
#: (out of scope here — see DatabaseAPIKeyStore.change_scopes).
DEFAULT_ONBOARDING_AGENT_CAPABILITIES: tuple[str, ...] = tuple(sorted(AGENT_KEY_CAPABILITIES))


@dataclass(frozen=True)
class PodSpec:
    """Caller-supplied spec for one pod to create/find during onboarding."""

    name: str
    department: str  # one of POD_DEPARTMENTS
    agent_count: int

    def __post_init__(self) -> None:
        if self.department not in POD_DEPARTMENTS:
            raise ValueError(f"Unknown department {self.department!r}; must be one of {sorted(POD_DEPARTMENTS)}")
        if self.agent_count <= 0:
            raise ValueError(f"agent_count must be positive; got {self.agent_count!r}")


@dataclass(frozen=True)
class OnboardingResult:
    """Summary of one onboarding call — never carries raw key material."""

    tenant_id: str
    pods_created: int
    agents_created: int
    inboxes_created: int
    keys_created: int
    inbox_addresses: list[str] = field(default_factory=list)
    key_ids: list[str] = field(default_factory=list)  # key_id only — never raw_key


def _get_tenant_slug(db: Any, tenant_id: str) -> str:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text("SELECT slug FROM tenants WHERE id = CAST(:tenant_id AS uuid)"),
        {"tenant_id": tenant_id},
    ).fetchone()
    if not row or not row[0]:
        raise ValueError(f"Tenant {tenant_id!r} has no slug; cannot derive inbox addresses")
    return row[0]


def _get_or_create_pod(db: Any, *, tenant_id: str, pod: PodSpec) -> tuple[str, bool]:
    """Return ``(pod_id, created)``. Idempotent on ``(tenant_id, name)``."""
    inserted = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO agent_org.agent_pods (tenant_id, name, department)
            VALUES (CAST(:tenant_id AS uuid), :name, :department)
            ON CONFLICT (tenant_id, name) DO NOTHING
            RETURNING id
            """
        ),
        {"tenant_id": tenant_id, "name": pod.name, "department": pod.department},
    ).fetchone()
    if inserted:
        return str(inserted[0]), True

    existing = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id FROM agent_org.agent_pods
            WHERE tenant_id = CAST(:tenant_id AS uuid) AND name = :name
            """
        ),
        {"tenant_id": tenant_id, "name": pod.name},
    ).fetchone()
    if not existing:
        raise RuntimeError(f"agent_pods claim-or-read race: pod {pod.name!r} neither inserted nor found")
    return str(existing[0]), False


def _get_or_create_agent(
    db: Any, *, tenant_id: str, pod_id: str, name: str, role: str
) -> tuple[str, bool]:
    """Return ``(agent_id, created)``. Idempotent on ``(tenant_id, pod_id, name)``."""
    inserted = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO agent_org.agent_identities (pod_id, tenant_id, name, role)
            VALUES (CAST(:pod_id AS uuid), CAST(:tenant_id AS uuid), :name, :role)
            ON CONFLICT (tenant_id, pod_id, name) DO NOTHING
            RETURNING id
            """
        ),
        {"pod_id": pod_id, "tenant_id": tenant_id, "name": name, "role": role},
    ).fetchone()
    if inserted:
        return str(inserted[0]), True

    existing = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT id FROM agent_org.agent_identities
            WHERE tenant_id = CAST(:tenant_id AS uuid)
              AND pod_id = CAST(:pod_id AS uuid)
              AND name = :name
            """
        ),
        {"tenant_id": tenant_id, "pod_id": pod_id, "name": name},
    ).fetchone()
    if not existing:
        raise RuntimeError(f"agent_identities claim-or-read race: agent {name!r} neither inserted nor found")
    return str(existing[0]), False


def _get_or_create_inbox(
    db: Any,
    *,
    tenant_id: str,
    agent_id: str,
    tenant_slug: str,
    agent_name: str,
    inbox_provider: InboxProvider,
) -> tuple[str, bool]:
    """Return ``(email_address, created)``. Idempotent per ``agent_id``."""
    existing = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT email_address FROM agent_org.agent_inboxes
            WHERE agent_id = CAST(:agent_id AS uuid) AND tenant_id = CAST(:tenant_id AS uuid)
            """
        ),
        {"agent_id": agent_id, "tenant_id": tenant_id},
    ).fetchone()
    if existing:
        return existing[0], False

    provisioned = inbox_provider.provision(
        tenant_slug=tenant_slug,
        agent_slug=agent_slug(agent_name),
        tenant_id=tenant_id,
        agent_id=agent_id,
    )
    inserted = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            INSERT INTO agent_org.agent_inboxes
                (agent_id, tenant_id, email_address, provider, provider_ref)
            VALUES
                (CAST(:agent_id AS uuid), CAST(:tenant_id AS uuid), :email_address, :provider, :provider_ref)
            ON CONFLICT (email_address) DO NOTHING
            RETURNING email_address
            """
        ),
        {
            "agent_id": agent_id,
            "tenant_id": tenant_id,
            "email_address": provisioned.email_address,
            "provider": provisioned.provider,
            "provider_ref": provisioned.provider_ref,
        },
    ).fetchone()
    if not inserted:
        # email_address is globally UNIQUE — this agent has no existing
        # inbox row (checked above) yet the provider-derived address is
        # already claimed by a *different* agent/tenant. That should be
        # unreachable given tenant-slug + pod/agent-name uniqueness, so
        # surface it loudly instead of silently mislabeling this as
        # "created" or attributing another agent's address to this one.
        raise RuntimeError(
            f"agent_inboxes address collision: {provisioned.email_address!r} "
            f"is already assigned to a different agent"
        )
    db.flush()
    return provisioned.email_address, True


def _existing_agent_key_id(db: Any, *, tenant_id: str, agent_id: str) -> Optional[str]:
    row = db.execute(
        # nosemgrep: avoid-sqlalchemy-text — parameterized with :param
        text(
            """
            SELECT key_id FROM api_keys
            WHERE agent_id = CAST(:agent_id AS uuid)
              AND tenant_id = CAST(:tenant_id AS uuid)
              AND enabled = true
            ORDER BY created_at ASC
            LIMIT 1
            """
        ),
        {"agent_id": agent_id, "tenant_id": tenant_id},
    ).fetchone()
    return row[0] if row else None


async def onboard_tenant_agent_org(
    db: Any,
    tenant_id: str,
    pods: list[PodSpec],
    *,
    key_store: Optional["DatabaseAPIKeyStore"] = None,
    inbox_provider: Optional[InboxProvider] = None,
) -> OnboardingResult:
    """Create pods, agents, inboxes and scoped keys for a tenant in one call.

    Idempotent: re-calling with the same ``tenant_id`` + ``pods`` (matched
    by ``(tenant_id, pod.name)`` and, within a pod, by a deterministic
    per-index agent name ``"<pod.name>-agent-<n>"``) creates zero
    additional rows and mints zero additional keys — it returns the
    counts/addresses/key_ids of the *existing* rows instead. Growing a
    pod's ``agent_count`` on a later call is treated as intentional
    incremental onboarding: it creates only the newly-numbered agents,
    not a duplicate of the whole pod.

    ``db`` is expected to already be scoped to ``tenant_id`` by the
    caller's tenant-resolution funnel (the RLS begin-hook applies
    ``app.tenant_id`` from the request/job's tenant scope); this function
    additionally calls ``set_tenant_guc`` itself so it is also safe to
    call directly, e.g. from a script or test, without a surrounding
    request context.
    """
    if key_store is None:
        from shared.api_key_store import get_db_key_store  # noqa: PLC0415

        key_store = await get_db_key_store()
    if inbox_provider is None:
        inbox_provider = get_inbox_provider()

    set_tenant_guc(db, tenant_id)
    tenant_slug = _get_tenant_slug(db, tenant_id)

    pods_created = 0
    agents_created = 0
    inboxes_created = 0
    keys_created = 0
    inbox_addresses: list[str] = []
    key_ids: list[str] = []

    for pod in pods:
        pod_id, pod_was_created = _get_or_create_pod(db, tenant_id=tenant_id, pod=pod)
        if pod_was_created:
            pods_created += 1
        db.flush()

        for i in range(1, pod.agent_count + 1):
            agent_name = f"{pod.name}-agent-{i}"
            # PodSpec carries no per-agent role; role is free text with no
            # authorization meaning at v1 (authorization runs on API-key
            # scopes, not this column) — default it to the pod's
            # department so it is at least descriptive.
            agent_id, agent_was_created = _get_or_create_agent(
                db, tenant_id=tenant_id, pod_id=pod_id, name=agent_name, role=pod.department
            )
            if agent_was_created:
                agents_created += 1
            db.flush()

            email_address, inbox_was_created = _get_or_create_inbox(
                db,
                tenant_id=tenant_id,
                agent_id=agent_id,
                tenant_slug=tenant_slug,
                agent_name=agent_name,
                inbox_provider=inbox_provider,
            )
            if inbox_was_created:
                inboxes_created += 1
            inbox_addresses.append(email_address)

            # Key minting happens after the DB writes for this agent are
            # flushed, so a key is never minted for an agent row that
            # didn't actually get committed. A crash between "agent row
            # committed" and "key minted" is recovered by simply
            # re-calling onboarding: idempotent per the check below, it
            # mints the missing key on retry.
            existing_key_id = _existing_agent_key_id(db, tenant_id=tenant_id, agent_id=agent_id)
            if existing_key_id:
                key_ids.append(existing_key_id)
            else:
                minted = await mint_agent_scoped_key(
                    key_store,
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    name=f"{agent_name} key",
                    capabilities=DEFAULT_ONBOARDING_AGENT_CAPABILITIES,
                    created_by="agent_org.onboarding",
                )
                keys_created += 1
                key_ids.append(minted.key_id)
                # raw_key (minted.raw_key) is discarded here — never
                # stored, logged, or returned by this function.

    return OnboardingResult(
        tenant_id=tenant_id,
        pods_created=pods_created,
        agents_created=agents_created,
        inboxes_created=inboxes_created,
        keys_created=keys_created,
        inbox_addresses=inbox_addresses,
        key_ids=key_ids,
    )
