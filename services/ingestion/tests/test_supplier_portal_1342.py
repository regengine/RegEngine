"""Data-free schema and fail-closed checks for the supplier portal."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from app import supplier_portal as sp
from app.supplier_portal import (
    CreatePortalLinkRequest,
    SupplierSubmission,
    _db_get_portal_link,
    _db_store_portal_link,
    _db_update_portal_link_status,
    _enforce_portal_rate_limit,
    _get_active_portal_link,
    _portal_subscription_active,
    router,
)
from fastapi import HTTPException
from pydantic import ValidationError


def test_create_portal_link_requires_tenant_and_supplier() -> None:
    with pytest.raises(ValidationError) as exc:
        CreatePortalLinkRequest.model_validate({})
    assert {error["loc"][0] for error in exc.value.errors()} == {"tenant_id", "supplier_name"}


def test_create_portal_link_rejects_zero_expiry() -> None:
    with pytest.raises(ValidationError) as exc:
        CreatePortalLinkRequest.model_validate({"expires_days": 0})
    assert "expires_days" in {error["loc"][0] for error in exc.value.errors()}


def test_supplier_submission_rejects_missing_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        SupplierSubmission.model_validate({})
    assert "traceability_lot_code" in {error["loc"][0] for error in exc.value.errors()}
    assert "quantity" in {error["loc"][0] for error in exc.value.errors()}


def test_supplier_submission_rejects_empty_tlc() -> None:
    with pytest.raises(ValidationError) as exc:
        SupplierSubmission.model_validate({"traceability_lot_code": ""})
    assert "traceability_lot_code" in {error["loc"][0] for error in exc.value.errors()}


def test_supplier_submission_rejects_zero_quantity() -> None:
    with pytest.raises(ValidationError) as exc:
        SupplierSubmission.model_validate({"quantity": 0})
    assert "quantity" in {error["loc"][0] for error in exc.value.errors()}


def test_db_helpers_fail_closed_without_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "get_db_safe", lambda: None)
    assert _db_store_portal_link("", {}) is False
    assert _db_get_portal_link("") is None
    assert _db_update_portal_link_status("", "") is False


def test_portal_lookup_with_no_row_uses_token_function(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None
    monkeypatch.setattr(sp, "get_db_safe", lambda: db)
    assert _db_get_portal_link("") is None
    assert "fsma.get_active_portal_link_by_token(:link_token)" in str(db.execute.call_args.args[0])
    assert db.close.called


def test_portal_lookup_exception_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    db = MagicMock()
    db.execute.side_effect = RuntimeError()
    monkeypatch.setattr(sp, "get_db_safe", lambda: db)
    assert _db_get_portal_link("") is None
    assert db.close.called


def test_missing_portal_link_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "_db_get_portal_link", lambda _portal_id: None)
    monkeypatch.setattr(sp, "_allow_memory_fallback", lambda: True)
    sp._portal_links.clear()
    with pytest.raises(HTTPException) as exc:
        _get_active_portal_link("")
    assert exc.value.status_code == 404


def test_rate_limit_rejection_does_not_need_portal_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "consume_tenant_rate_limit", lambda **_kwargs: (False, 0))
    with pytest.raises(HTTPException) as exc:
        _enforce_portal_rate_limit("", "", scope="preflight", limit=1)
    assert exc.value.status_code == 429
    assert exc.value.headers["X-RateLimit-Remaining"] == "0"


def test_unset_redis_url_fails_closed_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(sp, "is_production", lambda: True)
    with pytest.raises(HTTPException) as exc:
        _portal_subscription_active("")
    assert exc.value.status_code == 503


def test_unset_redis_url_skips_gate_outside_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(sp, "is_production", lambda: False)
    assert _portal_subscription_active("") is None


def test_portal_routes_registered() -> None:
    paths = {route.path for route in router.routes}
    assert "/api/v1/portal/links" in paths
    assert "/api/v1/portal/links/list" in paths
    assert "/api/v1/portal/links/{portal_id}/revoke" in paths
    assert "/api/v1/portal/{portal_id}/preflight" in paths
    assert "/api/v1/portal/{portal_id}/submit" in paths
