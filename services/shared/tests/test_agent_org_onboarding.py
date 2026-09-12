"""Unit tests for ``shared.agent_org.onboarding``.

No live DB. Two layers of fakes, both matching the stub-session style
``test_rules_rejection_audit.py`` uses for text()-based SQL helpers under
SQLite-incompatible Postgres syntax (``CAST(... AS uuid)`` can't run
against SQLite):

* ``_QueueSession`` — a bare, order-based fetchone() queue used to unit
  test each private claim-or-read helper (``_get_or_create_pod`` etc.) in
  isolation, including their race-condition ``RuntimeError`` branches.
* ``_RelationalFakeDB`` — a tiny in-memory simulation of the four tables
  this module writes (keyed the same way the real UNIQUE constraints are),
  used to exercise ``onboard_tenant_agent_org`` end-to-end: idempotency,
  incremental pod growth, and the key-recovery path.

``mint_agent_scoped_key`` is monkeypatched at the module level (the same
"patch the direct collaborator" technique ``test_stripe_plans_1342.py``
uses via ``monkeypatch.setattr``/``setenv``) so no real ``DatabaseAPIKeyStore``
or DB-backed key store is ever constructed. ``DevInboxProvider`` is used for
real — it is a pure, deterministic function with no I/O.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from shared.agent_org import onboarding as mod
from shared.agent_org.onboarding import (
    DEFAULT_ONBOARDING_AGENT_CAPABILITIES,
    PodSpec,
    _existing_agent_key_id,
    _get_or_create_agent,
    _get_or_create_inbox,
    _get_or_create_pod,
    _get_tenant_slug,
    onboard_tenant_agent_org,
)
from shared.agent_org.providers import DevInboxProvider


def _uuid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# PodSpec validation
# ---------------------------------------------------------------------------


class TestPodSpec:
    def test_valid_spec_constructs(self):
        spec = PodSpec(name="outreach-pod-1", department="outreach", agent_count=3)
        assert spec.agent_count == 3

    def test_unknown_department_raises_value_error(self):
        with pytest.raises(ValueError) as ei:
            PodSpec(name="x", department="marketing", agent_count=1)
        assert "marketing" in str(ei.value)

    @pytest.mark.parametrize("bad_count", [0, -1, -50])
    def test_non_positive_agent_count_raises_value_error(self, bad_count):
        with pytest.raises(ValueError):
            PodSpec(name="x", department="ops", agent_count=bad_count)


# ---------------------------------------------------------------------------
# Private helpers — isolated, order-based fake session
# ---------------------------------------------------------------------------


class _QueueSession:
    """Order-based ``fetchone()`` queue; records rendered SQL + params."""

    def __init__(self, fetchone_results):
        self._results = list(fetchone_results)
        self.calls: list[tuple[str, dict]] = []

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        self.calls.append((sql, dict(params or {})))
        result = MagicMock()
        result.fetchone.return_value = self._results.pop(0) if self._results else None
        return result

    def flush(self):
        pass


class TestGetTenantSlug:
    def test_returns_slug_from_row(self):
        db = _QueueSession([("acme",)])
        tid = _uuid()
        assert _get_tenant_slug(db, tid) == "acme"
        _, params = db.calls[0]
        assert params["tenant_id"] == tid

    def test_no_row_raises_value_error(self):
        db = _QueueSession([None])
        with pytest.raises(ValueError):
            _get_tenant_slug(db, _uuid())

    def test_falsy_slug_raises_value_error(self):
        db = _QueueSession([("",)])
        with pytest.raises(ValueError):
            _get_tenant_slug(db, _uuid())


class TestGetOrCreatePod:
    def test_insert_succeeds_returns_created_true(self):
        pod_id = _uuid()
        db = _QueueSession([(pod_id,)])
        spec = PodSpec(name="outreach-pod-1", department="outreach", agent_count=1)
        result_id, created = _get_or_create_pod(db, tenant_id=_uuid(), pod=spec)
        assert result_id == pod_id
        assert created is True
        assert len(db.calls) == 1  # only the INSERT — no fallback SELECT needed

    def test_conflict_then_select_returns_created_false(self):
        pod_id = _uuid()
        db = _QueueSession([None, (pod_id,)])
        spec = PodSpec(name="outreach-pod-1", department="outreach", agent_count=1)
        result_id, created = _get_or_create_pod(db, tenant_id=_uuid(), pod=spec)
        assert result_id == pod_id
        assert created is False
        assert len(db.calls) == 2

    def test_conflict_then_missing_row_raises_runtime_error(self):
        # Neither the INSERT nor the fallback SELECT found a row — an
        # unreachable-in-practice race the code refuses to paper over.
        db = _QueueSession([None, None])
        spec = PodSpec(name="outreach-pod-1", department="outreach", agent_count=1)
        with pytest.raises(RuntimeError) as ei:
            _get_or_create_pod(db, tenant_id=_uuid(), pod=spec)
        assert "outreach-pod-1" in str(ei.value)


class TestGetOrCreateAgent:
    def test_insert_succeeds_returns_created_true(self):
        agent_id = _uuid()
        db = _QueueSession([(agent_id,)])
        result_id, created = _get_or_create_agent(
            db, tenant_id=_uuid(), pod_id=_uuid(), name="outreach-pod-1-agent-1", role="outreach"
        )
        assert result_id == agent_id
        assert created is True

    def test_conflict_then_select_returns_created_false(self):
        agent_id = _uuid()
        db = _QueueSession([None, (agent_id,)])
        result_id, created = _get_or_create_agent(
            db, tenant_id=_uuid(), pod_id=_uuid(), name="outreach-pod-1-agent-1", role="outreach"
        )
        assert result_id == agent_id
        assert created is False

    def test_conflict_then_missing_row_raises_runtime_error(self):
        db = _QueueSession([None, None])
        with pytest.raises(RuntimeError) as ei:
            _get_or_create_agent(db, tenant_id=_uuid(), pod_id=_uuid(), name="agent-x", role="ops")
        assert "agent-x" in str(ei.value)


class TestGetOrCreateInbox:
    def test_existing_inbox_returns_created_false_and_never_calls_provider(self):
        email = "bot@agents.acme.regengine.dev"
        db = _QueueSession([(email,)])
        provider = MagicMock()
        result_email, created = _get_or_create_inbox(
            db,
            tenant_id=_uuid(),
            agent_id=_uuid(),
            tenant_slug="acme",
            agent_name="bot",
            inbox_provider=provider,
        )
        assert result_email == email
        assert created is False
        provider.provision.assert_not_called()
        assert len(db.calls) == 1

    def test_no_existing_inbox_provisions_and_inserts(self):
        db = _QueueSession([None, ("bot@agents.acme.regengine.dev",)])
        provider = DevInboxProvider()
        result_email, created = _get_or_create_inbox(
            db,
            tenant_id=_uuid(),
            agent_id=_uuid(),
            tenant_slug="acme",
            agent_name="bot",
            inbox_provider=provider,
        )
        assert result_email == "bot@agents.acme.regengine.dev"
        assert created is True
        assert len(db.calls) == 2

    def test_address_collision_on_insert_raises_runtime_error(self):
        # No existing row for THIS agent, but the address is already
        # claimed by a different agent/tenant (email_address is globally
        # UNIQUE) — must be surfaced loudly, never silently mislabeled.
        db = _QueueSession([None, None])
        provider = DevInboxProvider()
        with pytest.raises(RuntimeError) as ei:
            _get_or_create_inbox(
                db,
                tenant_id=_uuid(),
                agent_id=_uuid(),
                tenant_slug="acme",
                agent_name="bot",
                inbox_provider=provider,
            )
        assert "collision" in str(ei.value)
        assert "bot@agents.acme.regengine.dev" in str(ei.value)


class TestExistingAgentKeyId:
    def test_returns_key_id_when_present(self):
        db = _QueueSession([("key-1",)])
        assert _existing_agent_key_id(db, tenant_id=_uuid(), agent_id=_uuid()) == "key-1"

    def test_returns_none_when_absent(self):
        db = _QueueSession([None])
        assert _existing_agent_key_id(db, tenant_id=_uuid(), agent_id=_uuid()) is None


# ---------------------------------------------------------------------------
# onboard_tenant_agent_org — end-to-end with an in-memory relational fake
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _RelationalFakeDB:
    """Minimal in-memory stand-in for the tables ``onboarding.py`` writes.

    Keyed exactly like the real UNIQUE constraints (see the v121 migration):
    pods on (tenant_id, name), agents on (tenant_id, pod_id, name), inboxes
    on a globally-unique email_address, keys on (tenant_id, agent_id).
    """

    def __init__(self, tenant_slugs: dict[str, str]):
        self.tenant_slugs = tenant_slugs
        self.pods: dict[tuple, str] = {}
        self.agents: dict[tuple, str] = {}
        self.agent_roles: dict[str, str] = {}
        self.inbox_by_agent: dict[str, str] = {}
        self.inbox_addresses_taken: set[str] = set()
        self.keys_by_agent: dict[tuple, str] = {}
        self.guc_calls: list[str] = []
        self.flush_count = 0
        self.commit_count = 0
        self.executed: list[tuple[str, dict]] = []
        self.events: list[str] = []  # ordered "commit" / "mint:<agent_id>" trail

    def flush(self):
        self.flush_count += 1

    def commit(self):
        self.commit_count += 1
        self.events.append("commit")

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        params = params or {}
        self.executed.append((sql, params))

        if "set_config" in sql:
            self.guc_calls.append(params.get("tid"))
            return _Result(None)

        if "SELECT slug FROM tenants" in sql:
            slug = self.tenant_slugs.get(params["tenant_id"])
            return _Result((slug,) if slug else None)

        if "INSERT INTO agent_org.agent_pods" in sql:
            key = (params["tenant_id"], params["name"])
            if key in self.pods:
                return _Result(None)
            new_id = _uuid()
            self.pods[key] = new_id
            return _Result((new_id,))

        if sql.lstrip().startswith("SELECT id FROM agent_org.agent_pods"):
            key = (params["tenant_id"], params["name"])
            pod_id = self.pods.get(key)
            return _Result((pod_id,) if pod_id else None)

        if "INSERT INTO agent_org.agent_identities" in sql:
            key = (params["tenant_id"], params["pod_id"], params["name"])
            if key in self.agents:
                return _Result(None)
            new_id = _uuid()
            self.agents[key] = new_id
            self.agent_roles[new_id] = params["role"]
            return _Result((new_id,))

        if sql.lstrip().startswith("SELECT id FROM agent_org.agent_identities"):
            key = (params["tenant_id"], params["pod_id"], params["name"])
            agent_id = self.agents.get(key)
            return _Result((agent_id,) if agent_id else None)

        if sql.lstrip().startswith("SELECT email_address FROM agent_org.agent_inboxes"):
            email = self.inbox_by_agent.get(params["agent_id"])
            return _Result((email,) if email else None)

        if "INSERT INTO agent_org.agent_inboxes" in sql:
            email = params["email_address"]
            if email in self.inbox_addresses_taken:
                return _Result(None)
            self.inbox_addresses_taken.add(email)
            self.inbox_by_agent[params["agent_id"]] = email
            return _Result((email,))

        if sql.lstrip().startswith("SELECT key_id FROM api_keys"):
            key_id = self.keys_by_agent.get((params["tenant_id"], params["agent_id"]))
            return _Result((key_id,) if key_id else None)

        raise AssertionError(f"_RelationalFakeDB got unexpected SQL:\n{sql}\nparams={params}")


def _install_fake_key_minting(monkeypatch, db: _RelationalFakeDB):
    """Deterministic key minting keyed by agent_id; records every call."""
    calls: list[dict] = []

    async def _fake_mint(key_store, *, tenant_id, agent_id, name, capabilities, created_by=None, rate_limit_per_minute=30):
        calls.append(
            dict(
                tenant_id=tenant_id,
                agent_id=agent_id,
                name=name,
                capabilities=list(capabilities),
                created_by=created_by,
            )
        )
        db.events.append(f"mint:{agent_id}")
        key_id = _uuid()
        db.keys_by_agent[(tenant_id, agent_id)] = key_id
        return SimpleNamespace(key_id=key_id, raw_key="raw-secret-must-never-leak")

    monkeypatch.setattr(mod, "mint_agent_scoped_key", _fake_mint)
    return calls


@pytest.fixture
def tenant_id():
    return _uuid()


class TestOnboardTenantAgentOrgFreshTenant:
    @pytest.mark.asyncio
    async def test_creates_pods_agents_inboxes_and_keys(self, monkeypatch, tenant_id):
        db = _RelationalFakeDB({tenant_id: "acme"})
        mint_calls = _install_fake_key_minting(monkeypatch, db)
        pods = [PodSpec(name="outreach-pod-1", department="outreach", agent_count=2)]

        result = await onboard_tenant_agent_org(
            db, tenant_id, pods, key_store=AsyncMock(), inbox_provider=DevInboxProvider()
        )

        assert result.tenant_id == tenant_id
        assert result.pods_created == 1
        assert result.agents_created == 2
        assert result.inboxes_created == 2
        assert result.keys_created == 2
        assert result.inbox_addresses == [
            "outreach-pod-1-agent-1@agents.acme.regengine.dev",
            "outreach-pod-1-agent-2@agents.acme.regengine.dev",
        ]
        assert len(result.key_ids) == 2
        assert len(set(result.key_ids)) == 2  # distinct keys per agent
        assert not hasattr(result, "raw_key")
        # set_tenant_guc is called once up front, then re-applied after
        # every per-agent commit (transaction-scoped GUC does not survive
        # a commit) — one initial call plus one per agent processed.
        assert db.guc_calls == [tenant_id] * 3
        assert db.commit_count == 2  # one commit per agent, before minting its key

        # Every minted key carries exactly the default onboarding
        # capabilities — never a wildcard, never empty.
        for call in mint_calls:
            assert call["capabilities"] == list(DEFAULT_ONBOARDING_AGENT_CAPABILITIES)
            assert call["tenant_id"] == tenant_id

    @pytest.mark.asyncio
    async def test_agent_role_defaults_to_pod_department(self, monkeypatch, tenant_id):
        db = _RelationalFakeDB({tenant_id: "acme"})
        _install_fake_key_minting(monkeypatch, db)
        pods = [PodSpec(name="legal-pod", department="legal_review", agent_count=1)]

        await onboard_tenant_agent_org(db, tenant_id, pods, key_store=AsyncMock(), inbox_provider=DevInboxProvider())

        (agent_id,) = db.agents.values()
        assert db.agent_roles[agent_id] == "legal_review"

    @pytest.mark.asyncio
    async def test_missing_tenant_slug_raises_value_error(self, monkeypatch, tenant_id):
        db = _RelationalFakeDB({})  # tenant not registered
        _install_fake_key_minting(monkeypatch, db)
        pods = [PodSpec(name="p", department="ops", agent_count=1)]

        with pytest.raises(ValueError):
            await onboard_tenant_agent_org(db, tenant_id, pods, key_store=AsyncMock(), inbox_provider=DevInboxProvider())

    @pytest.mark.asyncio
    async def test_multiple_pods_produce_independent_agents(self, monkeypatch, tenant_id):
        db = _RelationalFakeDB({tenant_id: "acme"})
        _install_fake_key_minting(monkeypatch, db)
        pods = [
            PodSpec(name="outreach-pod-1", department="outreach", agent_count=1),
            PodSpec(name="research-pod-1", department="research", agent_count=1),
        ]

        result = await onboard_tenant_agent_org(db, tenant_id, pods, key_store=AsyncMock(), inbox_provider=DevInboxProvider())

        assert result.pods_created == 2
        assert result.agents_created == 2
        assert result.inbox_addresses == [
            "outreach-pod-1-agent-1@agents.acme.regengine.dev",
            "research-pod-1-agent-1@agents.acme.regengine.dev",
        ]


class TestOnboardTenantAgentOrgIdempotency:
    @pytest.mark.asyncio
    async def test_second_identical_call_creates_nothing_new(self, monkeypatch, tenant_id):
        db = _RelationalFakeDB({tenant_id: "acme"})
        _install_fake_key_minting(monkeypatch, db)
        pods = [PodSpec(name="outreach-pod-1", department="outreach", agent_count=2)]

        first = await onboard_tenant_agent_org(db, tenant_id, pods, key_store=AsyncMock(), inbox_provider=DevInboxProvider())
        second = await onboard_tenant_agent_org(db, tenant_id, pods, key_store=AsyncMock(), inbox_provider=DevInboxProvider())

        assert second.pods_created == 0
        assert second.agents_created == 0
        assert second.inboxes_created == 0
        assert second.keys_created == 0
        # Same existing rows are reported back, not fresh ones.
        assert second.inbox_addresses == first.inbox_addresses
        assert second.key_ids == first.key_ids

    @pytest.mark.asyncio
    async def test_growing_agent_count_only_creates_the_new_agents(self, monkeypatch, tenant_id):
        db = _RelationalFakeDB({tenant_id: "acme"})
        _install_fake_key_minting(monkeypatch, db)
        pod = PodSpec(name="outreach-pod-1", department="outreach", agent_count=2)

        first = await onboard_tenant_agent_org(db, tenant_id, [pod], key_store=AsyncMock(), inbox_provider=DevInboxProvider())

        grown_pod = PodSpec(name="outreach-pod-1", department="outreach", agent_count=3)
        second = await onboard_tenant_agent_org(
            db, tenant_id, [grown_pod], key_store=AsyncMock(), inbox_provider=DevInboxProvider()
        )

        assert second.pods_created == 0  # pod already existed
        assert second.agents_created == 1  # only agent-3 is new
        assert second.inboxes_created == 1
        assert second.keys_created == 1
        assert second.inbox_addresses == [
            "outreach-pod-1-agent-1@agents.acme.regengine.dev",
            "outreach-pod-1-agent-2@agents.acme.regengine.dev",
            "outreach-pod-1-agent-3@agents.acme.regengine.dev",
        ]
        # The first two keys are carried over unchanged; only one new key.
        assert second.key_ids[:2] == first.key_ids
        assert len(second.key_ids) == 3

    @pytest.mark.asyncio
    async def test_recovers_a_missing_key_without_recreating_rows(self, monkeypatch, tenant_id):
        # Simulates a crash between "agent/inbox rows committed" and "key
        # minted": pre-populate everything except the key, then re-run
        # onboarding and confirm only the key gets minted.
        db = _RelationalFakeDB({tenant_id: "acme"})
        mint_calls = _install_fake_key_minting(monkeypatch, db)
        pod = PodSpec(name="outreach-pod-1", department="outreach", agent_count=1)

        pod_id = _uuid()
        db.pods[(tenant_id, "outreach-pod-1")] = pod_id
        agent_id = _uuid()
        db.agents[(tenant_id, pod_id, "outreach-pod-1-agent-1")] = agent_id
        db.agent_roles[agent_id] = "outreach"
        email = "outreach-pod-1-agent-1@agents.acme.regengine.dev"
        db.inbox_by_agent[agent_id] = email
        db.inbox_addresses_taken.add(email)
        # Deliberately no entry in db.keys_by_agent.

        result = await onboard_tenant_agent_org(
            db, tenant_id, [pod], key_store=AsyncMock(), inbox_provider=DevInboxProvider()
        )

        assert result.pods_created == 0
        assert result.agents_created == 0
        assert result.inboxes_created == 0
        assert result.keys_created == 1
        assert len(mint_calls) == 1
        assert mint_calls[0]["agent_id"] == agent_id


class TestOnboardTenantAgentOrgInboxCollision:
    @pytest.mark.asyncio
    async def test_address_already_claimed_by_a_different_agent_raises_runtime_error(self, monkeypatch, tenant_id):
        db = _RelationalFakeDB({tenant_id: "acme"})
        _install_fake_key_minting(monkeypatch, db)
        # Pre-claim the address this onboarding call will derive, but
        # attribute it to a different agent — an unreachable-in-practice
        # state given the uniqueness of (tenant_slug, agent_slug), but the
        # code must refuse to mislabel it if it ever happens.
        db.inbox_addresses_taken.add("outreach-pod-1-agent-1@agents.acme.regengine.dev")
        pod = PodSpec(name="outreach-pod-1", department="outreach", agent_count=1)

        with pytest.raises(RuntimeError):
            await onboard_tenant_agent_org(db, tenant_id, [pod], key_store=AsyncMock(), inbox_provider=DevInboxProvider())


class TestOnboardTenantAgentOrgCommitOrdering:
    """Regression coverage for the self-review fix: a key must never be
    minted for an agent row that is only flushed, not committed.

    ``mint_agent_scoped_key`` runs on ``DatabaseAPIKeyStore``'s own,
    separate async engine, which commits immediately and independently of
    ``db``. If ``db`` only flushed (never committed) before minting, an
    exception raised for a *later* agent in the same call would roll back
    an *earlier* agent's already-flushed pod/agent/inbox rows while its
    already-minted-and-committed key survived — an orphaned credential
    pointing at a row that no longer exists. These tests assert the fix's
    actual mechanism: ``db.commit()`` (and re-applying the transaction-
    scoped tenant GUC) happens for each agent strictly before that agent's
    key is minted.
    """

    @pytest.mark.asyncio
    async def test_commit_happens_before_each_agents_key_is_minted(self, monkeypatch, tenant_id):
        db = _RelationalFakeDB({tenant_id: "acme"})
        _install_fake_key_minting(monkeypatch, db)
        pods = [PodSpec(name="outreach-pod-1", department="outreach", agent_count=2)]

        await onboard_tenant_agent_org(db, tenant_id, pods, key_store=AsyncMock(), inbox_provider=DevInboxProvider())

        # Exactly one commit precedes each mint — never a mint with no
        # preceding commit, and never two mints sharing one commit.
        assert db.events == [
            "commit",
            "mint:" + [aid for (t, p, n), aid in db.agents.items() if n.endswith("agent-1")][0],
            "commit",
            "mint:" + [aid for (t, p, n), aid in db.agents.items() if n.endswith("agent-2")][0],
        ]

    @pytest.mark.asyncio
    async def test_tenant_guc_is_reapplied_after_every_commit(self, monkeypatch, tenant_id):
        # set_tenant_guc uses set_config(..., true) — transaction-scoped,
        # so it does not survive a commit. Every commit must be followed
        # by another set_tenant_guc call before the next statement runs.
        db = _RelationalFakeDB({tenant_id: "acme"})
        _install_fake_key_minting(monkeypatch, db)
        pods = [PodSpec(name="outreach-pod-1", department="outreach", agent_count=3)]

        await onboard_tenant_agent_org(db, tenant_id, pods, key_store=AsyncMock(), inbox_provider=DevInboxProvider())

        # One initial set_tenant_guc, plus one per agent (after its commit).
        assert db.guc_calls == [tenant_id] * 4
        assert db.commit_count == 3
