"""Unit tests for ``shared.agent_org.keys.mint_agent_scoped_key``.

No live DB: ``DatabaseAPIKeyStore.create_key`` is replaced with an
``AsyncMock`` (matching ``test_agent_org_router.py``'s ``AsyncMock``-based
style for the async collaborator this module calls) so we only exercise
``mint_agent_scoped_key``'s own capability-allowlist validation and its
argument plumbing into ``create_key`` — never a real key store.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from shared.agent_org.keys import (
    AGENT_KEY_CAPABILITIES,
    AGENT_SCOPE_PREFIX,
    DEFAULT_AGENT_KEY_RATE_LIMIT_PER_MINUTE,
    mint_agent_scoped_key,
)


def _fake_key_store(return_value="sentinel-response"):
    store = AsyncMock()
    store.create_key = AsyncMock(return_value=return_value)
    return store


class TestCapabilityAllowlist:
    def test_every_declared_capability_is_namespaced(self):
        # The allowlist itself must live inside the declared namespace —
        # otherwise AGENT_SCOPE_PREFIX documents a convention nothing
        # enforces.
        for capability in AGENT_KEY_CAPABILITIES:
            assert capability.startswith(AGENT_SCOPE_PREFIX)

    @pytest.mark.asyncio
    async def test_unknown_capability_raises_value_error_before_any_store_call(self):
        store = _fake_key_store()
        with pytest.raises(ValueError) as ei:
            await mint_agent_scoped_key(
                store,
                tenant_id="tenant-1",
                agent_id="agent-1",
                name="test key",
                capabilities=["agent.inbox.read", "agent.super_admin"],
            )
        assert "agent.super_admin" in str(ei.value)
        store.create_key.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tenant_wide_wildcard_capability_is_rejected(self):
        # A caller passing "*" or "admin.*" must not slip an unscoped
        # capability onto a key that is supposed to be agent-narrow.
        store = _fake_key_store()
        with pytest.raises(ValueError):
            await mint_agent_scoped_key(
                store,
                tenant_id="tenant-1",
                agent_id="agent-1",
                name="test key",
                capabilities=["*"],
            )
        store.create_key.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_capabilities_is_allowed(self):
        # An empty subset of AGENT_KEY_CAPABILITIES is still a valid
        # subset — a key with zero capabilities is unusual but not
        # something this validator should block.
        store = _fake_key_store()
        await mint_agent_scoped_key(
            store, tenant_id="tenant-1", agent_id="agent-1", name="test key", capabilities=[]
        )
        store.create_key.assert_awaited_once()
        _, kwargs = store.create_key.call_args
        assert kwargs["scopes"] == []

    @pytest.mark.asyncio
    async def test_every_allowlisted_capability_individually_accepted(self):
        for capability in sorted(AGENT_KEY_CAPABILITIES):
            store = _fake_key_store()
            await mint_agent_scoped_key(
                store,
                tenant_id="tenant-1",
                agent_id="agent-1",
                name="test key",
                capabilities=[capability],
            )
            store.create_key.assert_awaited_once()


class TestArgumentPlumbing:
    @pytest.mark.asyncio
    async def test_calls_create_key_with_agent_id_and_scopes_unmodified(self):
        store = _fake_key_store()
        capabilities = ["agent.inbox.send", "agent.inbox.read"]
        await mint_agent_scoped_key(
            store,
            tenant_id="tenant-42",
            agent_id="agent-99",
            name="outreach-pod-1-agent-1 key",
            capabilities=capabilities,
            created_by="agent_org.onboarding",
        )
        store.create_key.assert_awaited_once()
        _, kwargs = store.create_key.call_args
        assert kwargs["tenant_id"] == "tenant-42"
        assert kwargs["agent_id"] == "agent-99"
        assert kwargs["name"] == "outreach-pod-1-agent-1 key"
        # Scopes are stored exactly as passed — no wildcard/tenant-wide
        # scope is ever injected alongside the requested capabilities.
        assert kwargs["scopes"] == capabilities
        assert kwargs["created_by"] == "agent_org.onboarding"

    @pytest.mark.asyncio
    async def test_default_rate_limit_is_lower_than_tenant_key_default(self):
        store = _fake_key_store()
        await mint_agent_scoped_key(
            store, tenant_id="tenant-1", agent_id="agent-1", name="k", capabilities=["agent.inbox.read"]
        )
        _, kwargs = store.create_key.call_args
        assert kwargs["rate_limit_per_minute"] == DEFAULT_AGENT_KEY_RATE_LIMIT_PER_MINUTE
        assert DEFAULT_AGENT_KEY_RATE_LIMIT_PER_MINUTE < 60  # the tenant-key default in api_key_store.create_key

    @pytest.mark.asyncio
    async def test_explicit_rate_limit_overrides_default(self):
        store = _fake_key_store()
        await mint_agent_scoped_key(
            store,
            tenant_id="tenant-1",
            agent_id="agent-1",
            name="k",
            capabilities=["agent.inbox.read"],
            rate_limit_per_minute=5,
        )
        _, kwargs = store.create_key.call_args
        assert kwargs["rate_limit_per_minute"] == 5

    @pytest.mark.asyncio
    async def test_created_by_defaults_to_none(self):
        store = _fake_key_store()
        await mint_agent_scoped_key(
            store, tenant_id="tenant-1", agent_id="agent-1", name="k", capabilities=[]
        )
        _, kwargs = store.create_key.call_args
        assert kwargs["created_by"] is None

    @pytest.mark.asyncio
    async def test_returns_create_key_response_unmodified(self):
        sentinel = object()
        store = _fake_key_store(return_value=sentinel)
        result = await mint_agent_scoped_key(
            store, tenant_id="tenant-1", agent_id="agent-1", name="k", capabilities=[]
        )
        assert result is sentinel
