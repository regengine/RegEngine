"""Tests for agent operator review endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared.agent_operator_view import (
    AgentArtifactTimelineResponse,
    AgentReviewDecisionResponse,
    AgentReviewItem,
    AgentReviewListResponse,
)


def _make_user(*, is_sysadmin: bool) -> MagicMock:
    user = MagicMock()
    user.id = uuid.uuid4()
    user.is_sysadmin = is_sysadmin
    return user


def _build_app(user: MagicMock, db: MagicMock, tenant_id: uuid.UUID | None) -> FastAPI:
    from services.admin.app.agent_review_routes import router
    from services.admin.app.dependencies import get_session
    from services.admin.app.privileged_auth import PrivilegedActor, require_review_decide, require_review_read

    app = FastAPI()
    app.include_router(router, prefix="/v1")
    actor = PrivilegedActor(
        actor_type="tenant_user",
        actor_id=str(user.id),
        auth_method="webauthn",
        tenant_id=str(tenant_id) if tenant_id else None,
        permissions=("review.read", "review.decide"),
        user=user,
    )
    app.dependency_overrides[require_review_read] = lambda: actor
    app.dependency_overrides[require_review_decide] = lambda: actor
    app.dependency_overrides[get_session] = lambda: db
    return app


def test_agent_review_items_use_authenticated_tenant(monkeypatch) -> None:
    tenant_id = uuid.uuid4()
    db = MagicMock()
    helper = MagicMock(return_value=AgentReviewListResponse(items=[], total=0, limit=50, offset=0))
    from services.admin.app import agent_review_routes as routes

    monkeypatch.setattr(routes, "fetch_agent_review_items", helper)
    audit = MagicMock()
    monkeypatch.setattr(routes, "audit_privileged_action", audit)

    client = TestClient(_build_app(_make_user(is_sysadmin=False), db, tenant_id))
    resp = client.get("/v1/agent-reviews/items")

    assert resp.status_code == 200
    assert resp.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}
    helper.assert_called_once()
    assert helper.call_args.kwargs["tenant_id"] == str(tenant_id)
    assert helper.call_args.kwargs["limit"] == 50
    assert helper.call_args.kwargs["offset"] == 0
    assert [call.kwargs["outcome"] for call in audit.call_args_list] == [
        "attempted",
        "succeeded",
    ]
    assert audit.call_args_list[-1].kwargs["selected_tenant"] == str(tenant_id)


def test_agent_review_items_reject_cross_tenant_filter_for_non_sysadmin(monkeypatch) -> None:
    auth_tenant = uuid.uuid4()
    other_tenant = uuid.uuid4()
    from services.admin.app import agent_review_routes as routes

    audit = MagicMock()
    monkeypatch.setattr(routes, "audit_privileged_action", audit)

    client = TestClient(
        _build_app(_make_user(is_sysadmin=False), MagicMock(), auth_tenant),
        raise_server_exceptions=False,
    )
    resp = client.get(f"/v1/agent-reviews/items?tenant_id={other_tenant}")

    assert resp.status_code == 403
    assert [call.kwargs["outcome"] for call in audit.call_args_list] == [
        "attempted",
        "denied",
    ]
    assert audit.call_args_list[-1].kwargs["reason"] == "tenant_assertion_mismatch"


def test_agent_review_items_sysadmin_cannot_select_request_tenant(monkeypatch) -> None:
    requested_tenant = uuid.uuid4()
    active_tenant = uuid.uuid4()
    db = MagicMock()
    helper = MagicMock(return_value=AgentReviewListResponse(items=[], total=0, limit=25, offset=5))
    from services.admin.app import agent_review_routes as routes

    monkeypatch.setattr(routes, "fetch_agent_review_items", helper)

    client = TestClient(_build_app(_make_user(is_sysadmin=True), db, active_tenant))
    resp = client.get(f"/v1/agent-reviews/items?tenant_id={requested_tenant}&limit=25&offset=5")

    assert resp.status_code == 403
    helper.assert_not_called()


def test_agent_review_items_require_tenant_context(monkeypatch) -> None:
    from services.admin.app import agent_review_routes as routes

    client = TestClient(
        _build_app(_make_user(is_sysadmin=False), MagicMock(), None),
        raise_server_exceptions=False,
    )
    resp = client.get("/v1/agent-reviews/items")

    assert resp.status_code == 403


def test_agent_review_decision_persists_for_authenticated_tenant(monkeypatch) -> None:
    tenant_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    reviewer = _make_user(is_sysadmin=False)
    db = MagicMock()
    reviewed_at = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    helper = MagicMock(
        return_value=AgentReviewDecisionResponse(
            review_id=str(uuid.uuid4()),
            artifact_id=str(artifact_id),
            tenant_id=str(tenant_id),
            status="accepted",
            reviewed_by=str(reviewer.id),
            reviewed_at=reviewed_at,
            ingestion_run_id=str(uuid.uuid4()),
            advisory_receipt_id=str(uuid.uuid4()),
        )
    )
    from services.admin.app import agent_review_routes as routes

    monkeypatch.setattr(routes, "upsert_agent_artifact_review", helper)
    audit = MagicMock()
    monkeypatch.setattr(routes, "audit_privileged_action", audit)

    client = TestClient(_build_app(reviewer, db, tenant_id))
    resp = client.post(
        f"/v1/agent-reviews/items/{artifact_id}/review",
        json={
            "status": "accepted",
            "review_reason": "Evidence chain verified",
            "operator_notes": "Looks good",
            "decision_metadata": {"source": "route-test"},
        },
    )

    assert resp.status_code == 200
    db.commit.assert_called_once()
    db.rollback.assert_not_called()
    helper.assert_called_once()
    assert helper.call_args.kwargs["tenant_id"] == str(tenant_id)
    assert helper.call_args.kwargs["artifact_id"] == str(artifact_id)
    assert helper.call_args.kwargs["status"] == "accepted"
    assert helper.call_args.kwargs["reviewed_by"] == str(reviewer.id)
    assert helper.call_args.kwargs["review_reason"] == "Evidence chain verified"
    assert helper.call_args.kwargs["operator_notes"] == "Looks good"
    assert [call.kwargs["outcome"] for call in audit.call_args_list] == [
        "attempted",
        "succeeded",
    ]
    assert audit.call_args_list[-1].kwargs["target"] == str(artifact_id)
    assert audit.call_args_list[-1].kwargs["reason"] == "decision:accepted"


def test_agent_review_decision_returns_404_for_missing_artifact(monkeypatch) -> None:
    tenant_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    db = MagicMock()
    from services.admin.app import agent_review_routes as routes

    monkeypatch.setattr(
        routes,
        "upsert_agent_artifact_review",
        MagicMock(side_effect=LookupError("agent artifact not found for tenant")),
    )
    audit = MagicMock()
    monkeypatch.setattr(routes, "audit_privileged_action", audit)

    client = TestClient(
        _build_app(_make_user(is_sysadmin=False), db, tenant_id),
        raise_server_exceptions=False,
    )
    resp = client.post(
        f"/v1/agent-reviews/items/{artifact_id}/review",
        json={"status": "rejected"},
    )

    assert resp.status_code == 404
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    assert [call.kwargs["outcome"] for call in audit.call_args_list] == [
        "attempted",
        "denied",
    ]
    assert audit.call_args_list[-1].kwargs["reason"] == "artifact_not_found"


def test_agent_review_timeline_uses_authenticated_tenant(monkeypatch) -> None:
    tenant_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    created_at = datetime(2026, 5, 19, 12, 0, tzinfo=timezone.utc)
    db = MagicMock()
    helper = MagicMock(
        return_value=AgentArtifactTimelineResponse(
            item=AgentReviewItem(
                artifact_id=str(artifact_id),
                tenant_id=str(tenant_id),
                artifact_type="validation_explanation",
                created_at=created_at,
                agent_name="fsma-risk-agent",
                suggestion="Review failed event-time rule.",
                confidence=0.78,
                requires_human_review=True,
                review_status="pending",
                risk_score=88.0,
                risk_breakdown={
                    "score": 88.0,
                    "uncapped_score": 88.0,
                    "confidence_risk": 8.8,
                    "review_risk": 25.0,
                    "artifact_type_risk": 15.0,
                    "evidence_gap_risk": 15.0,
                    "rule_gap_risk": 10.0,
                },
                compliance_gap_count=1,
                compliance_gaps=[{"code": "human_review_required", "message": "Review required."}],
            ),
            timeline=None,
            chain_valid=None,
        )
    )
    from services.admin.app import agent_review_routes as routes

    monkeypatch.setattr(routes, "fetch_agent_artifact_timeline", helper)
    audit = MagicMock()
    monkeypatch.setattr(routes, "audit_privileged_action", audit)

    client = TestClient(_build_app(_make_user(is_sysadmin=False), db, tenant_id))
    resp = client.get(f"/v1/agent-reviews/items/{artifact_id}/timeline")

    assert resp.status_code == 200
    helper.assert_called_once_with(
        db,
        tenant_id=str(tenant_id),
        artifact_id=str(artifact_id),
    )
    assert [call.kwargs["outcome"] for call in audit.call_args_list] == [
        "attempted",
        "succeeded",
    ]
