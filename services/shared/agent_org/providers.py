"""Inbox provisioning for agent-org agents.

One protocol (:class:`InboxProvider`) and exactly one real implementation
(:class:`DevInboxProvider`). See the class docstring below for the
honest limitation this ships with: no real, internet-routable mailbox is
ever created by this change. A future real provider (e.g. Postmark) would
implement the same protocol without touching onboarding.py or the DB
schema — see ``DESIGN_agent-org.md`` section 3.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Protocol

from .slugs import slugify

#: Environment variable selecting the registered inbox provider.
AGENT_ORG_INBOX_PROVIDER_ENV = "AGENT_ORG_INBOX_PROVIDER"

#: Fallback agent slug when a name slugifies to empty.
_AGENT_SLUG_FALLBACK = "agent"


@dataclass(frozen=True)
class ProvisionedInbox:
    """What a provider returns after provisioning one agent's inbox."""

    email_address: str
    provider: str
    provider_ref: Optional[str]


class InboxProvider(Protocol):
    """Provisions one mailbox-shaped inbox for one agent.

    Implementations own address generation and any external provider
    call; onboarding only records what they return. A real
    implementation (e.g. Postmark's server + inbound-webhook API) would
    create genuine routable mail infrastructure here —
    :class:`DevInboxProvider`, the only implementation in this change,
    does not.
    """

    def provision(
        self, *, tenant_slug: str, agent_slug: str, tenant_id: str, agent_id: str
    ) -> ProvisionedInbox: ...


class DevInboxProvider:
    """Deterministic, local-only inbox address generator.

    HONEST LIMITATION: this does not create a real, internet-routable
    mailbox. It does not talk to any external email service. No inbound
    mail sent to the address it returns will ever be received anywhere
    — there is no MX record, no mailbox, no webhook target behind
    ``agents.<tenant-slug>.regengine.dev``. It exists so agent_org has a
    working, testable provisioning path in an environment with no live
    email-provider credentials. A real provider (e.g. a
    ``PostmarkInboxProvider`` using Postmark's server + inbound-message-
    stream API to create a real inbound address and webhook) can
    implement this same :class:`InboxProvider` protocol later without
    any change to ``onboarding.py`` or the DB schema.
    """

    provider_name = "dev"

    def provision(
        self, *, tenant_slug: str, agent_slug: str, tenant_id: str, agent_id: str
    ) -> ProvisionedInbox:
        address = f"{agent_slug}@agents.{tenant_slug}.regengine.dev"
        return ProvisionedInbox(email_address=address, provider=self.provider_name, provider_ref=None)


def agent_slug(agent_name: str) -> str:
    """Slugify an agent (or pod) display name for use in an inbox address."""
    return slugify(agent_name, fallback=_AGENT_SLUG_FALLBACK)


def get_inbox_provider() -> InboxProvider:
    """Return the configured :class:`InboxProvider`.

    Reads ``AGENT_ORG_INBOX_PROVIDER`` (default ``"dev"``). Any value
    other than ``"dev"`` raises ``RuntimeError`` rather than silently
    falling back — a future real provider must be explicitly wired into
    this registry, never guessed.
    """
    value = os.environ.get(AGENT_ORG_INBOX_PROVIDER_ENV, "dev").strip().lower()
    if value == "dev":
        return DevInboxProvider()
    raise RuntimeError(f"Unknown inbox provider: {value!r}")
