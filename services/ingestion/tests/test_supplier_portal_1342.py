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


# ---------------------------------------------------------------------------
# Portal submit must reach persistence without an API key.
#
# The portal has no X-RegEngine-API-Key: the link token is the credential.
# ``ingest_events`` used to fall through to the key-presence gate for any
# caller that was not a session principal, so every portal submit raised
# 401 before a row was written.
# ---------------------------------------------------------------------------

_PORTAL_TENANT = "11111111-1111-1111-1111-111111111111"


def _portal_link() -> dict:
    return {
        "tenant_id": _PORTAL_TENANT,
        "supplier_name": "Valley Fresh Farms",
        "allowed_cte_types": ["shipping"],
        "integration_profile_id": None,
    }


def _portal_submission() -> SupplierSubmission:
    return SupplierSubmission(
        traceability_lot_code="LOT-2026-001",
        product_description="Romaine Lettuce",
        quantity=10,
        unit_of_measure="cases",
        ship_date="2026-11-01",
        ship_from_location="Valley Fresh Farms, Salinas CA",
        ship_to_location="Metro DC, Los Angeles CA",
    )


def _open_portal_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "_enforce_portal_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(sp, "_portal_subscription_active", lambda _tenant: True)
    monkeypatch.setattr(
        sp,
        "_build_supplier_preflight",
        lambda *a, **k: MagicMock(status="ready"),
    )


@pytest.mark.asyncio
async def test_portal_submit_passes_ingest_auth_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real ingest_events auth gate must admit a portal submission."""
    from app import webhook_compat as wc

    _open_portal_gates(monkeypatch)
    monkeypatch.setattr(wc, "_check_rate_limit", lambda _tenant: None)
    # No database in this unit test: getting as far as the session lookup
    # proves the call cleared authentication.
    monkeypatch.setattr(wc, "_get_db_session", lambda: iter([None]))

    with pytest.raises(RuntimeError, match="Database unavailable"):
        await sp._submit_supplier_data_inner("tok-secret-123", _portal_link(), _portal_submission())


@pytest.mark.asyncio
async def test_portal_submit_principal_is_tenant_bound_and_token_free(monkeypatch: pytest.MonkeyPatch) -> None:
    _open_portal_gates(monkeypatch)
    seen: dict = {}

    async def fake_ingest(payload, **kwargs):
        seen["payload"] = payload
        seen.update(kwargs)
        return MagicMock(accepted=0, events=[MagicMock(errors=["stop"])])

    monkeypatch.setattr(sp, "ingest_events", fake_ingest)
    await sp._submit_supplier_data_inner("tok-secret-123", _portal_link(), _portal_submission())

    principal = seen["principal"]
    assert principal.auth_mode == "portal_link"
    assert principal.tenant_id == _PORTAL_TENANT == seen["principal_tenant_id"]
    assert principal.scopes == ["webhooks.ingest"]
    # The link token is a bearer credential; it must not become the actor id.
    assert "tok-secret-123" not in principal.key_id


@pytest.mark.asyncio
async def test_ingest_events_rejects_portal_principal_without_ingest_scope() -> None:
    from app import webhook_compat as wc
    from app.authz import IngestionPrincipal
    from app.webhook_models import WebhookPayload

    principal = IngestionPrincipal(
        key_id="supplier-portal", scopes=[], tenant_id=_PORTAL_TENANT, auth_mode="portal_link"
    )
    payload = WebhookPayload.model_construct(source="supplier_portal", events=[], tenant_id=_PORTAL_TENANT)
    with pytest.raises(PermissionError, match="webhooks.ingest"):
        await wc.ingest_events(payload, principal_tenant_id=_PORTAL_TENANT, principal=principal)


@pytest.mark.asyncio
async def test_ingest_events_still_requires_key_for_other_keyless_callers() -> None:
    """Only named pre-authorized modes skip the key gate; nothing else does."""
    from app import webhook_compat as wc
    from app.authz import IngestionPrincipal
    from app.webhook_models import WebhookPayload

    payload = WebhookPayload.model_construct(source="x", events=[], tenant_id=_PORTAL_TENANT)
    with pytest.raises(HTTPException) as exc:
        await wc.ingest_events(payload, principal_tenant_id=_PORTAL_TENANT)
    assert exc.value.status_code == 401

    principal = IngestionPrincipal(
        key_id="k", scopes=["webhooks.ingest"], tenant_id=_PORTAL_TENANT, auth_mode="made_up_mode"
    )
    with pytest.raises(HTTPException) as exc:
        await wc.ingest_events(payload, principal_tenant_id=_PORTAL_TENANT, principal=principal)
    assert exc.value.status_code == 401


def test_portal_event_never_carries_the_link_token() -> None:
    """The token is a bearer credential; records get a digest (QA BE-011)."""
    token = "tok-secret-123"
    event = sp._submission_event_dict(token, _portal_link(), _portal_submission())
    assert token not in repr(event)
    ref = sp._portal_link_ref(token)
    assert ref.startswith("pl_") and token not in ref
    assert event["kdes"]["portal_link_ref"] == ref
    assert event["kdes"]["reference_document"] == f"supplier-portal:{ref}"
    # Same link, same reference: events from one link stay correlatable.
    assert sp._portal_link_ref(token) == ref != sp._portal_link_ref("other-token")


@pytest.mark.asyncio
async def test_portal_submit_tenant_rate_limit_does_not_disclose_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    _open_portal_gates(monkeypatch)

    async def tenant_bucket_full(payload, **kwargs):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for tenant '{_PORTAL_TENANT}' (120/60s)",
            headers={"Retry-After": "60", "X-RateLimit-Tenant": _PORTAL_TENANT},
        )

    monkeypatch.setattr(sp, "ingest_events", tenant_bucket_full)
    with pytest.raises(HTTPException) as exc:
        await sp._submit_supplier_data_inner("tok-secret-123", _portal_link(), _portal_submission())

    assert exc.value.status_code == 429
    assert _PORTAL_TENANT not in str(exc.value.detail)
    assert exc.value.headers == {"Retry-After": "60"}


@pytest.mark.asyncio
async def test_portal_submit_passes_through_non_rate_limit_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _open_portal_gates(monkeypatch)

    async def boom(payload, **kwargs):
        raise HTTPException(status_code=503, detail="unavailable")

    monkeypatch.setattr(sp, "ingest_events", boom)
    with pytest.raises(HTTPException) as exc:
        await sp._submit_supplier_data_inner("tok-secret-123", _portal_link(), _portal_submission())
    assert exc.value.status_code == 503


# ---------------------------------------------------------------------------
# Ship date. The store refuses events dated in the future, but preflight used
# to say "ready" for them and the supplier then got "Internal storage error".
# Preflight and submit now refuse a future ship date with a readable reason.
# The record stays stamped at midnight UTC of the ship date so the export's
# Event Date equals the Ship Date.
# ---------------------------------------------------------------------------


def _submission_with(**overrides) -> SupplierSubmission:
    return _portal_submission().model_copy(update=overrides)


def _freeze_portal_clock(monkeypatch: pytest.MonkeyPatch, iso: str) -> None:
    from datetime import datetime

    monkeypatch.setattr(sp, "_utc_now", lambda: datetime.fromisoformat(iso))


def test_ship_timestamp_is_midnight_utc_of_the_ship_date() -> None:
    event = sp._submission_event_dict("tok", _portal_link(), _submission_with(ship_date="2026-11-01"))
    assert event["timestamp"] == "2026-11-01T00:00:00Z"
    assert event["kdes"]["ship_date"] == "2026-11-01"


def test_preflight_accepts_today_and_past_ship_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze_portal_clock(monkeypatch, "2026-11-10T22:00:00+00:00")
    for ship_date in ("2026-11-10", "2026-11-09", "2025-01-15"):
        preflight = sp._build_supplier_preflight("tok", _portal_link(), _submission_with(ship_date=ship_date))
        assert preflight.status == "ready", ship_date


def test_preflight_blocks_future_ship_date_with_a_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze_portal_clock(monkeypatch, "2026-11-10T22:00:00+00:00")
    for ship_date in ("2026-11-11", "2026-12-25"):
        preflight = sp._build_supplier_preflight("tok", _portal_link(), _submission_with(ship_date=ship_date))
        assert preflight.status == "blocked", ship_date
        assert preflight.result.submission_blocked is True
        assert any("in the future" in reason for reason in preflight.result.blocking_reasons)


def test_ship_date_check_allows_the_stores_clock_skew(monkeypatch: pytest.MonkeyPatch) -> None:
    # Three minutes before midnight UTC: the store tolerates five.
    _freeze_portal_clock(monkeypatch, "2026-11-10T23:57:00+00:00")
    assert sp._ship_date_block_reason(_submission_with(ship_date="2026-11-11")) is None


@pytest.mark.asyncio
async def test_submit_future_ship_date_is_refused_before_ingest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp, "_enforce_portal_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(sp, "_portal_subscription_active", lambda _tenant: True)
    _freeze_portal_clock(monkeypatch, "2026-11-10T22:00:00+00:00")

    async def must_not_ingest(*a, **k):
        raise AssertionError("future-dated submission reached ingest_events")

    monkeypatch.setattr(sp, "ingest_events", must_not_ingest)
    result = await sp._submit_supplier_data_inner("tok", _portal_link(), _submission_with(ship_date="2026-12-25"))
    assert result.status == "error"
    assert "in the future" in result.message


@pytest.mark.parametrize("bad", ["", "11/09/2026", "2026-13-01", "2026-11-09T10:00:00Z", "tomorrow"])
def test_ship_date_must_be_a_calendar_date(bad: str) -> None:
    with pytest.raises(ValidationError):
        SupplierSubmission(**{**_portal_submission().model_dump(), "ship_date": bad})


def test_very_old_ship_date_does_not_crash_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze_portal_clock(monkeypatch, "2026-11-10T22:00:00+00:00")
    assert sp._ship_date_block_reason(_submission_with(ship_date="0001-01-01")) is None
