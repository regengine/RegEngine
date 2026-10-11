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

    The predicates below are read from the actual query text in the module
    under test, so a query regression flips this mirror and fails the
    outcome tests instead of leaving them green: the identity label set
    comes from ``mod._ERASURE_IDENTITY_LABELS``, the delete match fields
    from ``_CYPHER_DELETE_IDENTITY_NODES``, and the anonymize rewrite
    fields from ``_CYPHER_ANONYMIZE_SHARED_ACTOR_REFS``. Companion string
    assertions pin the exact clauses.
    """
    identity = set(mod._ERASURE_IDENTITY_LABELS)
    delete_cypher = mod._CYPHER_DELETE_IDENTITY_NODES
    anonymize_cypher = mod._CYPHER_ANONYMIZE_SHARED_ACTOR_REFS

    def is_identity(node: dict) -> bool:
        return bool(identity.intersection(node["labels"]))

    def delete_matches(node: dict) -> bool:
        matched = node.get("user_id") == user_id or node.get("id") == user_id
        if "n.actor_id = $user_id" in delete_cypher:
            matched = matched or node.get("actor_id") == user_id
        return matched

    # Step 1: _CYPHER_DELETE_IDENTITY_NODES.
    surviving = [
        node
        for node in nodes
        if not (node["tenant_id"] == tenant_id and is_identity(node) and delete_matches(node))
    ]

    def rewrite(field: str) -> bool:
        # Require the SET assignment itself, not a mere WHERE mention.
        return (
            f"m.{field} = CASE WHEN m.{field} = $user_id THEN $erased_actor_id"
            in anonymize_cypher
        )

    drop_invite_email = (
        "PendingSupplierInvite" in anonymize_cypher and "m.email = CASE" in anonymize_cypher
    )
    # Step 2: _CYPHER_ANONYMIZE_SHARED_ACTOR_REFS.
    for node in surviving:
        if node["tenant_id"] != tenant_id or is_identity(node):
            continue
        if rewrite("actor_id") and node.get("actor_id") == user_id:
            node["actor_id"] = token
        if rewrite("user_id") and node.get("user_id") == user_id:
            node["user_id"] = token
        if rewrite("created_by") and node.get("created_by") == user_id:
            node["created_by"] = token
        accepted = rewrite("accepted_by") and node.get("accepted_by") == user_id
        if accepted:
            node["accepted_by"] = token
            if drop_invite_email and "PendingSupplierInvite" in node["labels"]:
                node.pop("email", None)
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
    # step may match actor_id only inside the identity-label filter, so an
    # identity node keyed solely by actor_id is removed while shared
    # records are never matched here.
    assert "any(label IN labels(n) WHERE label IN" in cypher
    assert "n.actor_id = $user_id" in cypher
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
    # The rewrite half of the fix: the query must assign the token to the
    # actor fields, not merely mention it.
    assert "SET" in cypher
    assert "m.actor_id" in cypher
    assert "m.user_id" in cypher
    assert "m.created_by" in cypher
    assert "m.accepted_by" in cypher
    assert "THEN $erased_actor_id" in cypher
    assert "PendingSupplierInvite" in cypher


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
            and (
                node.get("user_id") == USER
                or node.get("id") == USER
                or node.get("actor_id") == USER
            )
        )
    ]
    shared = [n for n in surviving if n["labels"] in (["CTEEvent"], ["TLC"]) and n["tenant_id"] == TENANT]
    assert len(shared) == 3
    user_shared = [n for n in shared if n.get("actor_id") == USER or n.get("user_id") == USER]
    assert len(user_shared) == 2


def test_identity_node_keyed_only_by_actor_id_is_deleted():
    """An identity node that links the person only via actor_id is still
    identity: the delete step must remove it, not leave the raw id."""
    token = mod._erased_actor_token(USER)
    nodes = [
        {"labels": ["TeamMember"], "tenant_id": TENANT, "actor_id": USER},
        {"labels": ["CTEEvent"], "tenant_id": TENANT, "actor_id": USER, "cte_type": "shipping"},
    ]
    result = _apply_fixed_semantics([dict(n) for n in nodes], TENANT, USER, token)
    assert not any(set(n["labels"]).intersection(mod._ERASURE_IDENTITY_LABELS) for n in result)
    trace = next(n for n in result if n["labels"] == ["CTEEvent"])
    assert trace["actor_id"] == token


def test_invite_bookkeeping_fields_are_anonymized():
    """PendingSupplierInvite created_by/accepted_by are rewritten, and the
    email is dropped on invites the erased user accepted (their own
    address). A pending invite they created keeps its invitee email."""
    token = mod._erased_actor_token(USER)
    nodes = [
        {
            "labels": ["PendingSupplierInvite"],
            "tenant_id": TENANT,
            "email": "erased@example.com",
            "created_by": OTHER_USER,
            "accepted_by": USER,
        },
        {
            "labels": ["PendingSupplierInvite"],
            "tenant_id": TENANT,
            "email": "invitee@example.com",
            "created_by": USER,
            "status": "pending",
        },
    ]
    result = _apply_fixed_semantics([dict(n) for n in nodes], TENANT, USER, token)
    accepted = next(n for n in result if n.get("accepted_by") == token)
    assert "email" not in accepted
    created = next(n for n in result if n.get("created_by") == token)
    assert created["email"] == "invitee@example.com"


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
    # actor_id may only appear inside the identity-label filter of the
    # delete step, never as an unscoped shared-record match.
    assert "any(label IN labels(n) WHERE label IN" in first_cypher
    assert "MATCH (n {tenant_id: $tenant_id}) DETACH DELETE n" not in first_cypher
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
        assert "any(label IN labels(n) WHERE label IN" in delete_row.cypher
        assert "n.actor_id = $user_id" in delete_row.cypher

        anonymize_row, anonymize_params = by_kind["anonymize"]
        assert "$erased_actor_id" in anonymize_row.cypher
        assert "SET" in anonymize_row.cypher
        assert "m.actor_id" in anonymize_row.cypher
        assert "m.user_id" in anonymize_row.cypher
        assert "THEN $erased_actor_id" in anonymize_row.cypher
        assert anonymize_params["erased_actor_id"] == mod._erased_actor_token(str(user_id))
    finally:
        db.close()


def test_erasure_refreshes_stale_pending_delete_row():
    """A delete row enqueued before the fix (old Cypher under the same
    dedupe key) is refreshed while still pending, so the drainer cannot
    run the statement that deleted shared records by actor_id."""
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
        stale_cypher = (
            "MATCH (n {tenant_id: $tenant_id}) "
            "WHERE n.actor_id = $user_id OR n.user_id = $user_id "
            "DETACH DELETE n"
        )
        db.execute(
            text(
                """
                INSERT INTO graph_outbox (
                    tenant_id, operation, cypher, params,
                    dedupe_key, max_attempts,
                    status, attempts, enqueued_at, next_attempt_at
                ) VALUES (
                    :tenant_id, 'user_erasure', :cypher, :params,
                    :dedupe_key, 10,
                    'pending', 0, :now, :now
                )
                """
            ),
            {
                "tenant_id": str(tenant_id),
                "cypher": stale_cypher,
                "params": json.dumps({"user_id": str(user_id)}),
                "dedupe_key": f"user_erasure:{tenant_id}:{user_id}",
                "now": "2026-01-01T00:00:00+00:00",
            },
        )
        db.commit()

        mod._apply_account_erasure(db, user_id=user_id, tenant_id=tenant_id)
        db.commit()

        rows = db.execute(
            text("SELECT cypher, params, dedupe_key, status FROM graph_outbox")
        ).all()
        delete_rows = [r for r in rows if r.dedupe_key == f"user_erasure:{tenant_id}:{user_id}"]
        if db.bind.dialect.name == "sqlite":
            # The sqlite test fallback has no dedupe enforcement, so the
            # stale row plus the fresh enqueue coexist; production Postgres
            # keeps exactly one row via ON CONFLICT DO NOTHING.
            assert len(delete_rows) == 2
        else:
            assert len(delete_rows) == 1
        assert all(r.cypher == mod._CYPHER_DELETE_IDENTITY_NODES for r in delete_rows)
        anonymize_rows = [
            r for r in rows if r.dedupe_key == f"user_erasure_anonymize:{tenant_id}:{user_id}"
        ]
        assert len(anonymize_rows) == 1
        assert "$erased_actor_id" in anonymize_rows[0].cypher
    finally:
        db.close()


def test_erased_actor_token_uses_configured_secret(monkeypatch):
    """With a server secret set, the token is an HMAC a tenant-level
    outbox reader cannot recompute; without one it stays deterministic."""
    plain = mod._erased_actor_token(USER)
    monkeypatch.setenv("ERASURE_TOKEN_SECRET", "test-secret-123")
    keyed = mod._erased_actor_token(USER)
    assert keyed == mod._erased_actor_token(USER)
    assert keyed.startswith("erased-user-")
    assert USER not in keyed
    assert keyed != plain
    assert mod._erased_actor_token(OTHER_USER) != keyed
