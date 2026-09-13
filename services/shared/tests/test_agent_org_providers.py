"""Unit tests for ``shared.agent_org.providers``.

No DB, no network: ``DevInboxProvider`` is a pure address generator and
``get_inbox_provider`` only reads an env var — both are exercised directly
with monkeypatch, matching ``test_stripe_plans_1342.py``'s
``monkeypatch.setenv``/``delenv`` style.
"""

from __future__ import annotations

import pytest
from shared.agent_org.providers import (
    AGENT_ORG_INBOX_PROVIDER_ENV,
    DevInboxProvider,
    ProvisionedInbox,
    agent_slug,
    get_inbox_provider,
)


class TestAgentSlug:
    def test_slugifies_agent_name(self):
        assert agent_slug("Outreach Pod-1-agent-1") == "outreach-pod-1-agent-1"

    def test_empty_name_falls_back_to_agent(self):
        assert agent_slug("") == "agent"

    def test_all_punctuation_name_falls_back_to_agent(self):
        assert agent_slug("!!!") == "agent"


class TestDevInboxProvider:
    def test_provision_returns_deterministic_address(self):
        provider = DevInboxProvider()
        result = provider.provision(
            tenant_slug="acme",
            agent_slug="outreach-pod-1-agent-1",
            tenant_id="tenant-1",
            agent_id="agent-1",
        )
        assert isinstance(result, ProvisionedInbox)
        assert result.email_address == "outreach-pod-1-agent-1@agents.acme.regengine.dev"
        assert result.provider == "dev"
        assert result.provider_ref is None

    def test_provider_name_is_dev(self):
        assert DevInboxProvider.provider_name == "dev"

    def test_different_tenant_slugs_produce_different_addresses(self):
        provider = DevInboxProvider()
        a = provider.provision(tenant_slug="acme", agent_slug="bot", tenant_id="t1", agent_id="a1")
        b = provider.provision(tenant_slug="globex", agent_slug="bot", tenant_id="t2", agent_id="a2")
        assert a.email_address != b.email_address

    def test_provision_ignores_tenant_id_and_agent_id_in_the_address(self):
        # The address is derived only from the slugs — tenant_id/agent_id
        # are accepted for a future provider's use (e.g. a webhook target
        # keyed by agent_id) but DevInboxProvider itself never embeds them.
        provider = DevInboxProvider()
        result = provider.provision(
            tenant_slug="acme", agent_slug="bot", tenant_id="totally-different", agent_id="also-different"
        )
        assert result.email_address == "bot@agents.acme.regengine.dev"


class TestGetInboxProvider:
    def test_default_returns_dev_provider(self, monkeypatch):
        monkeypatch.delenv(AGENT_ORG_INBOX_PROVIDER_ENV, raising=False)
        provider = get_inbox_provider()
        assert isinstance(provider, DevInboxProvider)

    def test_explicit_dev_returns_dev_provider(self, monkeypatch):
        monkeypatch.setenv(AGENT_ORG_INBOX_PROVIDER_ENV, "dev")
        assert isinstance(get_inbox_provider(), DevInboxProvider)

    def test_value_is_case_and_whitespace_insensitive(self, monkeypatch):
        monkeypatch.setenv(AGENT_ORG_INBOX_PROVIDER_ENV, "  DEV  ")
        assert isinstance(get_inbox_provider(), DevInboxProvider)

    def test_unknown_provider_raises_runtime_error_not_silent_fallback(self, monkeypatch):
        monkeypatch.setenv(AGENT_ORG_INBOX_PROVIDER_ENV, "postmark")
        with pytest.raises(RuntimeError) as ei:
            get_inbox_provider()
        assert "postmark" in str(ei.value)
