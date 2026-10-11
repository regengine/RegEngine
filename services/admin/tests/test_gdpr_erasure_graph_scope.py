"""GDPR erasure graph scope: delete identity nodes, anonymize shared records.

Regression tests for the finding that erasure deleted any graph node where
``actor_id`` equaled the user, wiping trace events that are other parties'
FSMA 204 compliance evidence. The fixed behavior is two steps:

1. DETACH DELETE only identity nodes (User, Account, TeamMember,
   SupplierContact) belonging to the erased user and tenant.
2. Anonymize the actor reference on shared records (trace events, CTEs,
   lots, facilities) with a stable ``erased-user-<hash>`` token instead of
   deleting the record.

Tenant scoping is preserved throughout, and another user's records are
untouched.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from services.admin.app import erasure_routes as mod
from services.admin.app.sqlalchemy_models import (
    Base,
    MembershipModel,
    RoleModel,
    TenantModel,
    UserModel,
)

TENANT = "tenant-aaaa-0001"
OTHER_TENANT = "tenant-bbbb-0002"
USER = "user-1111-0001"
OTHER_USER = "user-2222-0002"


def _nodes_fixture() -> list[dict]:
    """Small in-memory property graph covering the cases that matter."""
    return [
        # 0: erased user's identity node, must be deleted.
        {"labels": ["SupplierContact"], "tenant_id": TENANT, "user_id": USER},
        # 1: erased user's identity node matched by id, must be deleted.
        {"labels": ["User"], "tenant_id": TENANT, "id": USER},
        # 2: shared trace event referencing the user, must be kept + anonymized.
        {"labels": ["CTEEvent"], "tenant_id": TENANT, "actor_id": USER, "cte_type": "shipping"},
        # 3: shared lot node referencing the user, must be kept + anonymized.
        {"labels": ["TLC"], "tenant_id": TENANT, "user_id": USER, "status": "active"},
        # 4/5: another user's identity and trace nodes, must be untouched.
        {"labels": ["SupplierContact"], "tenant_id": TENANT, "user_id": OTHER_USER},
        {"labels": ["CTEEvent"], "tenant_id": TENANT, "actor_id": OTHER_USER, "cte_type": "receiving"},
        # 6/7: erased user's nodes under another tenant, must be untouched.
        {"labels": ["SupplierContact"], "tenant_id": OTHER_TENANT, "user_id": USER},
        {"labels": ["CTEEvent"], "tenant_id": OTHER_TENANT, "actor_id": USER, "cte_type": "shipping"},
    ]


def _apply_fixed_semantics(nodes: list[dict], tenant_id: str, user_id: str, token: str) -> list[dict]:
    """Mirror the two fixed Cypher queries over the in-memory fixture.

    The predicates below are bound to the module under test: the identity
    label set comes from ``mod._ERASURE_IDENTITY_LABELS``, and companion
    string assertions pin the actual Cypher text to the same rules (delete
    query carries every identity label and no actor_id match; anonymize
    query carries the token SET and excludes identity labels).
    """
    identity = set(mod._ERASURE_IDENTITY_LABELS)

    def is_identity(node: dict) -> bool:
        return bool(identity.intersection(node["labels"]))

    # Step 1: _CYPHER_DELETE_IDENTITY_NODES.
    surviving = [
        node
        for node in nodes
        if not (
            node["tenant_id"] == tenant_id
            and is_identity(node)
            and (node.get("user_id") == user_id or node.get("id") == user_id)
        )
    ]
    # Step 2: _CYPHER_ANONYMIZE_SHARED_ACTOR_REFS.
    for node in surviving:
        if node["tenant_id"] != tenant_id or is_identity(node):
            continue
        if node.get("actor_id") == user_id:
            node["actor_id"] = token
        if node.get("user_id") == user_id:
            node["user_id"] = token
    return surviving


def test_erased_actor_token_is_stable_and_opaque():
    token_a = mod._erased_actor_token(USER)
    assert token_a == mod._erased_actor_token(USER)
    assert token_a.startswith("erased-user-")
    assert USER not in token_a
    assert mod._erased_actor_token(OTHER_USER) != token_a


def test_delete_query_targets_only_identity_nodes():
    cypher = mod._CYPHER_DELETE_IDENTITY_NODES
    for label in mod._ERASURE_IDENTITY_LABELS:
        assert f"'{label}'" in cypher
    assert "$tenant_id" in cypher
    assert "$user_id" in cypher
    assert USER not in cypher and TENANT not in cypher
    assert "DETACH DELETE" in cypher
    # The bug: shared records matched via actor_id were deleted. The delete
    # step must not reference actor_id at all.
    assert "actor_id" not in cypher
    assert "MATCH (n {tenant_id: $tenant_id}) DETACH DELETE n" not in cypher


def test_anonymize_query_preserves_records_and_rewrites_actor():
    cypher = mod._CYPHER_ANONYMIZE_SHARED_ACTOR_REFS
    assert "$tenant_id" in cypher
    assert "$user_id" in cypher
    assert "$erased_actor_id" in cypher
    assert "DETACH DELETE" not in cypher
    assert "NOT" in cypher
    for label in mod._ERASURE_IDENTITY_LABELS:
        assert f"'{label}'" in cypher


def test_both_queries_pass_drainer_tenant_validation():
    from services.shared.neo4j_tenant_context import require_tenant_id_in_cypher

    require_tenant_id_in_cypher(mod._CYPHER_DELETE_IDENTITY_NODES)
    require_tenant_id_in_cypher(mod._CYPHER_ANONYMIZE_SHARED_ACTOR_REFS)


def test_erasure_removes_identity_keeps_trace_event_anonymized():
    token = mod._erased_actor_token(USER)
    result = _apply_fixed_semantics(_nodes_fixture(), TENANT, USER, token)

    # Identity nodes for the erased user are gone.
    assert not any(
        n["tenant_id"] == TENANT
        and set(n["labels"]).intersection(mod._ERASURE_IDENTITY_LABELS)
        and (n.get("user_id") == USER or n.get("id") == USER)
        for n in result
    )

    trace = next(n for n in result if n["labels"] == ["CTEEvent"] and n["tenant_id"] == TENANT and n["cte_type"] == "shipping")
    assert trace["actor_id"] == token
    assert trace["cte_type"] == "shipping"

    lot = next(n for n in result if n["labels"] == ["TLC"] and n["tenant_id"] == TENANT)
    assert lot["user_id"] == token
    assert lot["status"] == "active"


def test_delete_step_alone_never_removes_shared_records():
    """The exact reported bug: the delete step removed trace events."""
    identity = set(mod._ERASURE_IDENTITY_LABELS)
    nodes = _nodes_fixture()
    surviving = [
        node
        for node in nodes
        if not (
            node["tenant_id"] == TENANT
            and bool(identity.intersection(node["labels"]))
            and (node.get("user_id") == USER or node.get("id") == USER)
        )
    ]
    shared = [n for n in surviving if n["labels"] in (["CTEEvent"], ["TLC"]) and n["tenant_id"] == TENANT]
    assert len(shared) == 3
    user_shared = [n for n in shared if n.get("actor_id") == USER or n.get("user_id") == USER]
    assert len(user_shared) == 2


def test_other_user_and_other_tenant_records_untouched():
    token = mod._erased_actor_token(USER)
    before = _nodes_fixture()
    result = _apply_fixed_semantics([dict(n) for n in before], TENANT, USER, token)

    other_contact = next(n for n in result if n.get("user_id") == OTHER_USER)
    assert other_contact["labels"] == ["SupplierContact"]
    other_trace = next(n for n in result if n.get("actor_id") == OTHER_USER and n["tenant_id"] == TENANT)
    assert other_trace["cte_type"] == "receiving"

    foreign_contact = next(n for n in result if n["tenant_id"] == OTHER_TENANT and "user_id" in n)
    assert foreign_contact["user_id"] == USER
    foreign_trace = next(n for n in result if n["tenant_id"] == OTHER_TENANT and "actor_id" in n)
    assert foreign_trace["actor_id"] == USER


def _make_async_driver_mock():
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=None)
    session_cm = AsyncMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    mock_driver = AsyncMock()
    mock_driver.session = MagicMock(return_value=session_cm)
    mock_driver.__aenter__ = AsyncMock(return_value=mock_driver)
    mock_driver.__aexit__ = AsyncMock(return_value=False)
    mock_async_gdb = MagicMock()
    mock_async_gdb.driver = MagicMock(return_value=mock_driver)
    return mock_async_gdb, mock_session


@pytest.mark.asyncio
async def test_immediate_path_runs_delete_then_anonymize(monkeypatch):
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j-test:7687")
    monkeypatch.setenv("NEO4J_PASSWORD", "testpass")
    mock_async_gdb, mock_session = _make_async_driver_mock()
    with patch.dict("sys.modules", {"neo4j": MagicMock(AsyncGraphDatabase=mock_async_gdb)}):
        await mod._delete_neo4j_user_graph_data(TENANT, USER)

    assert mock_session.run.await_count == 2
    first_cypher = mock_session.run.await_args_list[0][0][0]
    second_cypher = mock_session.run.await_args_list[1][0][0]
    assert "DETACH DELETE" in first_cypher
    assert "actor_id" not in first_cypher
    assert "DETACH DELETE" not in second_cypher
    assert second_cypher == mod._CYPHER_ANONYMIZE_SHARED_ACTOR_REFS
    params = mock_session.run.await_args_list[1][1]
    assert params["tenant_id"] == TENANT
    assert params["user_id"] == USER
    assert params["erased_actor_id"] == mod._erased_actor_token(USER)


def _sqlite_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE graph_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT,
                    operation TEXT NOT NULL,
                    cypher TEXT NOT NULL,
                    params TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    enqueued_at TEXT NOT NULL,
                    next_attempt_at TEXT NOT NULL,
                    dedupe_key TEXT
                )
                """
            )
        )
    return Session(engine)


def test_erasure_enqueues_delete_and_anonymize_graph_rows():
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    role_id = uuid.uuid4()
    db = _sqlite_session()
    try:
        db.add_all(
            [
                TenantModel(id=tenant_id, name="Tenant A", slug=f"tenant-{tenant_id.hex}"),
                RoleModel(id=role_id, tenant_id=tenant_id, name="Owner", permissions=[]),
                UserModel(
                    id=user_id,
                    email="person@example.com",
                    global_status="active",
                    status="active",
                    is_sysadmin=False,
                    token_version=1,
                ),
                MembershipModel(user_id=user_id, tenant_id=tenant_id, role_id=role_id, is_active=True),
            ]
        )
        db.commit()

        mod._apply_account_erasure(db, user_id=user_id, tenant_id=tenant_id)
        db.commit()

        rows = db.execute(text("SELECT operation, cypher, params, dedupe_key FROM graph_outbox")).all()
        assert len(rows) == 2
        assert {row.operation for row in rows} == {"user_erasure"}
        assert len({row.dedupe_key for row in rows}) == 2

        by_kind = {}
        for row in rows:
            params = json.loads(row.params) if isinstance(row.params, str) else row.params
            assert str(user_id) in json.dumps(params)
            if "DETACH DELETE" in row.cypher:
                by_kind["delete"] = (row, params)
            else:
                by_kind["anonymize"] = (row, params)
        assert set(by_kind) == {"delete", "anonymize"}

        delete_row, _ = by_kind["delete"]
        assert "actor_id" not in delete_row.cypher

        anonymize_row, anonymize_params = by_kind["anonymize"]
        assert "$erased_actor_id" in anonymize_row.cypher
        assert anonymize_params["erased_actor_id"] == mod._erased_actor_token(str(user_id))
    finally:
        db.close()
