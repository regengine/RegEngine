"""Minting API keys scoped to exactly one agent_org agent.

Thin, validating wrapper around the existing
``shared.api_key_store.DatabaseAPIKeyStore.create_key`` — not a parallel
key system. Capability validation (the frozenset check below) happens
here because ``create_key`` itself is intentionally generic and doesn't
know about the agent-org capability model, the same reasoning
``DatabaseAPIKeyStore.change_scopes`` gives for being the dedicated
privilege-sensitive wrapper around scope mutation rather than folding
that validation into ``update_key``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    from shared.api_key_store import APIKeyCreateResponse, DatabaseAPIKeyStore

#: Namespace prefix for every agent-scoped capability.
AGENT_SCOPE_PREFIX = "agent."

#: The only capabilities an agent-scoped key may ever carry. Anything
#: outside this set cannot be granted via mint_agent_scoped_key,
#: regardless of caller input — the allowlist is enforced in code, not
#: left to caller discipline.
AGENT_KEY_CAPABILITIES: frozenset[str] = frozenset(
    {
        "agent.inbox.read",
        "agent.inbox.send",
        "agent.suppression.read",
    }
)

#: Agent keys are meant for narrow automation, not bulk API usage —
#: default rate limit is lower than a tenant key's default (60/min).
DEFAULT_AGENT_KEY_RATE_LIMIT_PER_MINUTE = 30


def _validate_capabilities(capabilities: Sequence[str]) -> list[str]:
    capability_list = list(capabilities)
    unknown = sorted(set(capability_list) - AGENT_KEY_CAPABILITIES)
    if unknown:
        raise ValueError(
            f"Unknown agent capability(ies): {unknown}; "
            f"must be a subset of {sorted(AGENT_KEY_CAPABILITIES)}"
        )
    return capability_list


async def mint_agent_scoped_key(
    key_store: "DatabaseAPIKeyStore",
    *,
    tenant_id: str,
    agent_id: str,
    name: str,
    capabilities: Sequence[str],
    created_by: Optional[str] = None,
    rate_limit_per_minute: int = DEFAULT_AGENT_KEY_RATE_LIMIT_PER_MINUTE,
) -> "APIKeyCreateResponse":
    """Mint an API key scoped to exactly one agent.

    Raises ``ValueError`` if any capability is outside
    :data:`AGENT_KEY_CAPABILITIES`. The resulting key's ``.tenant_id``
    and ``.agent_id`` are both set; scopes are stored exactly as passed
    (capabilities are already namespaced, e.g. ``"agent.inbox.read"``) —
    no wildcard or tenant-wide scope is ever added. Rate limits default
    lower than a tenant key's, since agent keys are meant for narrow
    automation, not bulk API usage.
    """
    validated_capabilities = _validate_capabilities(capabilities)

    return await key_store.create_key(
        name=name,
        tenant_id=tenant_id,
        agent_id=agent_id,
        scopes=validated_capabilities,
        rate_limit_per_minute=rate_limit_per_minute,
        created_by=created_by,
    )
