"""Tests for ``DatabaseAPIKeyStore.change_scopes``.

Covers the privilege-sensitive scope-change path added to prevent silent
escalation through ``update_key()``. The key behaviors pinned here:

  1. Broadening with ``rotate=True`` (default) issues a new key, revokes
     the old, and the response carries a fresh ``raw_key``.
  2. Broadening with ``rotate=False`` raises ``ValueError`` — silent
     escalation is the bug we are guarding against.
  3. Narrowing with ``rotate=False`` updates in place (no new raw_key).
  4. Unknown ``key_id`` returns ``None`` rather than raising.
  5. Broadening requires an explicit reason.
  6. Rotation inserts the replacement and revokes the old key in one
     transaction.
  7. The ``api_key_scopes_changing`` audit event fires with an explicit
     added/removed diff so SOC2 can reconstruct who broadened what.

Mock pattern matches ``services/shared/tests/test_api_key_store_*.py``:
build a real ``DatabaseAPIKeyStore`` against a postgres URL but patch
``create_async_engine`` / ``sessionmaker`` so no real connection is
opened, then mock ``_session()``. The ``api_keys`` table is not created
because SQLite cannot render the postgres-specific ``ARRAY`` columns
used by the production model — see #1879 for that history.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.api_key_store import (
    APIKeyCreateResponse,
    APIKeyResponse,
    DatabaseAPIKeyStore,
)


def _make_store(monkeypatch) -> DatabaseAPIKeyStore:
    """Build a store without opening real DB or Redis connections.

    Mirrors the helper in test_api_key_store_rate_limit_minute_rollover.
    """
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h:6543/d")
    with patch("shared.api_key_store.create_async_engine") as _e, patch(
        "shared.api_key_store.sessionmaker"
    ) as _s:
        _e.return_value = object()
        _s.return_value = lambda: None
        return DatabaseAPIKeyStore()


def _existing_row(scopes: list[str]):
    """Stand-in for an APIKeyModel row returned by select(...)."""
    row = MagicMock()
    row.key_id = "rge_existing"
    row.name = "Existing Key"
    row.description = "desc"
    row.tenant_id = "00000000-0000-0000-0000-000000000001"
    row.partner_id = None
    row.billing_tier = "PROFESSIONAL"
    row.allowed_jurisdictions = ["US"]
    row.scopes = scopes
    row.rate_limit_per_minute = 60
    row.rate_limit_per_hour = 1000
    row.rate_limit_per_day = 10000
    row.expires_at = None
    row.extra_data = {"existing": "metadata"}
    return row


def _patch_session_returning(
    store: DatabaseAPIKeyStore,
    row,
    *,
    update_rowcount: int = 1,
) -> AsyncMock:
    """Patch store._session() so the first execute() returns ``row``.

    Returns the mock_session so callers can introspect later execute()
    calls (e.g. the in-place narrowing UPDATE).
    """
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=row)
    update_result = MagicMock()
    update_result.rowcount = update_rowcount
    context_result = MagicMock()
    side_effects = [select_result]
    if row is not None and getattr(row, "tenant_id", None):
        side_effects.append(context_result)
    side_effects.append(update_result)
    mock_session.execute = AsyncMock(side_effect=side_effects)

    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_session)
    ctx.__aexit__ = AsyncMock(return_value=None)
    store._session = MagicMock(return_value=ctx)  # type: ignore[method-assign]
    return mock_session


def _patch_key_generation(store: DatabaseAPIKeyStore) -> None:
    store._generate_key_id = MagicMock(  # type: ignore[method-assign]
        return_value="rge_new"
    )
    store._generate_secret = MagicMock(  # type: ignore[method-assign]
        return_value="secretsecret"
    )


@pytest.mark.asyncio
async def test_change_scopes_broadening_with_rotate_issues_new_key(monkeypatch):
    """Default rotate=True path: new raw_key issued, old key revoked."""
    store = _make_store(monkeypatch)
    mock_session = _patch_session_returning(store, _existing_row(["clients.read"]))
    _patch_key_generation(store)

    result = await store.change_scopes(
        "rge_existing",
        new_scopes=["clients.read", "clients.write"],
        changed_by="user_1",
        reason="grant write access",
    )

    assert isinstance(result, APIKeyCreateResponse)
    assert result.raw_key == "rge_new.secretsecret"
    assert result.key_id == "rge_new"
    # Replacement insert and old-key revoke happen in one session.
    assert mock_session.execute.await_count == 3
    mock_session.add.assert_called_once()
    new_model = mock_session.add.call_args.args[0]
    assert new_model.scopes == ["clients.read", "clients.write"]
    assert new_model.enabled is None or new_model.enabled is True
    meta = new_model.extra_data
    assert meta["scope_change_from_key_id"] == "rge_existing"
    assert meta["scope_change_added"] == ["clients.write"]
    assert meta["scope_change_removed"] == []
    assert meta["scope_change_reason"] == "grant write access"
    # Existing extra_data preserved
    assert meta["existing"] == "metadata"


@pytest.mark.asyncio
async def test_change_scopes_broadening_with_rotate_false_raises(monkeypatch):
    """Silent broadening MUST be refused — that's the whole point."""
    store = _make_store(monkeypatch)
    _patch_session_returning(store, _existing_row(["clients.read"]))
    store.create_key = AsyncMock()  # type: ignore[method-assign]
    store.revoke_key = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="rotate=False is only allowed"):
        await store.change_scopes(
            "rge_existing",
            new_scopes=["clients.read", "clients.write"],
            rotate=False,
        )

    # No state mutations should have happened
    store.create_key.assert_not_awaited()
    store.revoke_key.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_scopes_broadening_requires_reason(monkeypatch):
    """Non-narrowing changes need an explicit audit justification."""
    store = _make_store(monkeypatch)
    mock_session = _patch_session_returning(store, _existing_row(["clients.read"]))
    _patch_key_generation(store)

    with pytest.raises(ValueError, match="reason is required"):
        await store.change_scopes(
            "rge_existing",
            new_scopes=["clients.read", "clients.write"],
        )

    mock_session.add.assert_not_called()
    assert mock_session.execute.await_count == 1


@pytest.mark.asyncio
async def test_change_scopes_narrowing_in_place_updates_without_rotate(monkeypatch):
    """Narrowing-only change with rotate=False: no new raw_key, just shrink."""
    store = _make_store(monkeypatch)
    mock_session = _patch_session_returning(
        store, _existing_row(["clients.read", "clients.write", "branding.write"])
    )
    # get_key is awaited at the end of the narrowing path to return the
    # post-update row — stub it.
    store.get_key = AsyncMock(  # type: ignore[method-assign]
        return_value=APIKeyResponse(
            key_id="rge_existing",
            key_prefix="rge_existing",
            name="Existing Key",
            scopes=["clients.read"],
            created_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ),
        )
    )
    store.create_key = AsyncMock()  # type: ignore[method-assign]
    store.revoke_key = AsyncMock()  # type: ignore[method-assign]

    result = await store.change_scopes(
        "rge_existing",
        new_scopes=["clients.read"],
        rotate=False,
        reason="least privilege",
    )

    assert isinstance(result, APIKeyResponse)
    assert not isinstance(result, APIKeyCreateResponse)  # no raw_key
    assert result.scopes == ["clients.read"]
    # No rotation
    store.create_key.assert_not_awaited()
    store.revoke_key.assert_not_awaited()
    # Two execute calls: first the SELECT, then the UPDATE
    assert mock_session.execute.await_count == 2


@pytest.mark.asyncio
async def test_change_scopes_unknown_key_returns_none(monkeypatch):
    """Missing key_id should be a soft None, not an exception."""
    store = _make_store(monkeypatch)
    _patch_session_returning(store, None)

    result = await store.change_scopes(
        "rge_does_not_exist",
        new_scopes=["clients.read"],
    )
    assert result is None


@pytest.mark.asyncio
async def test_change_scopes_rotate_forwards_partner_id_to_new_key(monkeypatch):
    """Rotation must carry the existing row's ``partner_id`` onto the new key.

    ``partner_id`` is a privilege-bearing column (v076) — losing it on
    rotation would orphan a partner-issued key from its partner, which
    breaks every ``get_partner_principal`` lookup that resolves tenants
    via partner_id. Pin that ``create_key`` is invoked with exactly the
    existing row's partner_id, sourced from the column (not extra_data).
    """
    store = _make_store(monkeypatch)
    existing = _existing_row(["clients.read"])
    existing.partner_id = "partner_acme"
    mock_session = _patch_session_returning(store, existing)
    _patch_key_generation(store)

    result = await store.change_scopes(
        "rge_existing",
        new_scopes=["clients.read", "clients.write"],
        changed_by="user_1",
        reason="grant write access",
    )

    assert isinstance(result, APIKeyCreateResponse)
    assert result.partner_id == "partner_acme"
    new_model = mock_session.add.call_args.args[0]
    assert new_model.partner_id == "partner_acme"


@pytest.mark.asyncio
async def test_change_scopes_rotation_fails_if_old_key_not_revoked(monkeypatch):
    """Never hand back a new raw_key if the old key update did not land."""
    store = _make_store(monkeypatch)
    mock_session = _patch_session_returning(
        store,
        _existing_row(["clients.read"]),
        update_rowcount=0,
    )
    _patch_key_generation(store)

    with pytest.raises(RuntimeError, match="failed to revoke old key"):
        await store.change_scopes(
            "rge_existing",
            new_scopes=["clients.read", "clients.write"],
            changed_by="user_1",
            reason="grant write access",
        )

    mock_session.add.assert_called_once()
    mock_session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_change_scopes_emits_audit_event_with_diff(monkeypatch):
    """The api_key_scopes_changing event must include added/removed diffs.

    Compliance reviewers reconstruct who-broadened-what from this log
    entry; if it ever loses the diff, fail loudly. Uses
    ``structlog.testing.capture_logs`` because the module logger is a
    structlog BoundLogger that does not write to the stdlib root by
    default — caplog would see nothing.
    """
    import structlog

    store = _make_store(monkeypatch)
    _patch_session_returning(
        store, _existing_row(["clients.read", "branding.read"])
    )
    _patch_key_generation(store)

    with structlog.testing.capture_logs() as logs:
        await store.change_scopes(
            "rge_existing",
            new_scopes=["clients.read", "clients.write", "revenue.read"],
            changed_by="user_1",
            reason="onboarding new partner",
        )

    changing = next(
        (e for e in logs if e.get("event") == "api_key_scopes_changing"), None
    )
    assert changing is not None, f"missing audit event in: {logs}"
    assert changing["key_id"] == "rge_existing"
    assert changing["changed_by"] == "user_1"
    assert changing["reason"] == "onboarding new partner"
    assert changing["added_scopes"] == ["clients.write", "revenue.read"]
    assert changing["removed_scopes"] == ["branding.read"]
    assert changing["rotate"] is True
    assert changing["narrowing_only"] is False

    # The follow-up "rotated" event is what the SOC2 evidence chain
    # actually links the new key_id to the old one.
    rotated = next(
        (
            e
            for e in logs
            if e.get("event") == "api_key_scopes_changed_via_rotation"
        ),
        None,
    )
    assert rotated is not None
    assert rotated["old_key_id"] == "rge_existing"
    assert rotated["new_key_id"] == "rge_new"
