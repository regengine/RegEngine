"""Tests for WebAuthn passkey registration and login routes."""

from __future__ import annotations

import base64
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from starlette.requests import Request

from services.admin.app.auth import webauthn_router as wr
from services.admin.app.auth.session_auth import (
    ActiveSessionContext,
    get_current_active_user,
    require_high_assurance_session,
)
from services.admin.app.sqlalchemy_models import (
    SessionModel,
    WebAuthnChallengeModel,
    WebAuthnCredentialModel,
)


def _request(path: str = "/auth/webauthn/login/verify") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [],
        "client": ("203.0.113.50", 12345),
        "server": ("testserver", 443),
        "scheme": "https",
        "query_string": b"",
        "http_version": "1.1",
        "root_path": "",
        "state": {},
        "app": SimpleNamespace(state=SimpleNamespace()),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


def _client_data(challenge: str) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps({"challenge": challenge}).encode("utf-8"))
    return encoded.rstrip(b"=").decode("ascii")


def _credential_payload(challenge: str, *, credential_id: str = "credential-id") -> wr.WebAuthnCredentialPayload:
    return wr.WebAuthnCredentialPayload(
        credential={
            "id": credential_id,
            "rawId": credential_id,
            "type": "public-key",
            "response": {"clientDataJSON": _client_data(challenge)},
        }
    )


class FakeScalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return list(self.values)


class FakeResult:
    def __init__(self, *, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = [] if scalars is None else scalars

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return FakeScalars(self._scalars)


def _is_security_guc(statement) -> bool:
    return "set_config('regengine.is_sysadmin'" in str(statement)


class FakeTransaction:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.begin_count += 1
        self.db.active_transaction = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.db.rollback_count += 1
        else:
            self.db.commit_count += 1
        self.db.active_transaction = False
        return False


class FakeDb:
    def __init__(self, results=None):
        self.results = list(results or [])
        self.execute_statements = []
        self.added = []
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.active_transaction = False

    def begin(self):
        return FakeTransaction(self)

    def in_transaction(self):
        return self.active_transaction

    def execute(self, statement):
        self.execute_statements.append(statement)
        if _is_security_guc(statement):
            return FakeResult()
        if not self.results:
            raise AssertionError("unexpected execute")
        return self.results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1
        self.active_transaction = False


class FakeCrypto:
    def generate_opaque_session_token(self) -> str:
        return "raw-session-token"

    def hash_session_token(self, token: str) -> str:
        assert token == "raw-session-token"
        return "stored-session-digest"


def _user(user_id: uuid.UUID | None = None):
    return SimpleNamespace(
        id=user_id or uuid.UUID("11111111-1111-4111-8111-111111111111"),
        email="admin@example.com",
        global_status="active",
        status="active",
    )


def _stored_challenge(*, user_id: uuid.UUID, challenge: str, purpose: str) -> WebAuthnChallengeModel:
    return WebAuthnChallengeModel(
        id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        user_id=user_id,
        challenge=challenge,
        purpose=purpose,
        expires_at=wr.datetime.now(wr.timezone.utc) + wr.timedelta(seconds=60),
        consumed_at=None,
    )


def _stored_credential(*, user_id: uuid.UUID, credential_id: str = "credential-id") -> WebAuthnCredentialModel:
    return WebAuthnCredentialModel(
        id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
        user_id=user_id,
        credential_id=credential_id,
        public_key=b"stored-public-key",
        sign_count=1,
    )


def test_passkey_enrollment_routes_require_existing_high_assurance_session():
    dependencies = {
        route.path: {dependency.call for dependency in route.dependant.dependencies}
        for route in wr.router.routes
    }

    for path in (
        "/webauthn/register/generate-options",
        "/webauthn/register/verify",
    ):
        assert require_high_assurance_session in dependencies[path]
        assert get_current_active_user not in dependencies[path]


def test_email_otp_sysadmin_cannot_bootstrap_attacker_passkey():
    user = _user()
    user.is_sysadmin = True
    context = ActiveSessionContext(
        user=user,
        session=SimpleNamespace(auth_method="email_otp"),
    )

    with pytest.raises(HTTPException) as exc_info:
        require_high_assurance_session(context)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "requires_step_up"


@pytest.mark.asyncio
async def test_registration_generate_options_requires_session_and_stores_user_challenge(monkeypatch):
    user = _user()
    db = FakeDb([FakeResult(scalars=[])])

    def fake_generate(*, user, existing_credentials):
        assert existing_credentials == []
        return {"challenge": "registration-challenge"}, "registration-challenge"

    monkeypatch.setattr(wr, "_webauthn_generate_registration_options", fake_generate)

    result = await wr.generate_webauthn_registration_options(db=db, current_user=user)

    assert result == {"challenge": "registration-challenge"}
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert len(db.added) == 1
    state = db.added[0]
    assert isinstance(state, WebAuthnChallengeModel)
    assert state.user_id == user.id
    assert state.purpose == wr.WEBAUTHN_REGISTRATION_PURPOSE
    assert state.challenge == "registration-challenge"


@pytest.mark.asyncio
async def test_registration_verify_saves_new_credential_and_consumes_challenge(monkeypatch):
    user = _user()
    challenge = _stored_challenge(
        user_id=user.id,
        challenge="registration-challenge",
        purpose=wr.WEBAUTHN_REGISTRATION_PURPOSE,
    )
    db = FakeDb([FakeResult(scalar=challenge)])

    monkeypatch.setattr(
        wr,
        "_webauthn_verify_registration_response",
        lambda **kwargs: SimpleNamespace(
            credential_id=b"credential-one",
            credential_public_key=b"public-key",
            sign_count=7,
        ),
    )

    result = await wr.verify_webauthn_registration(
        payload=_credential_payload("registration-challenge"),
        request=_request("/auth/webauthn/register/verify"),
        db=db,
        current_user=user,
    )

    assert result == {"status": "verified"}
    assert db.begin_count == 1
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert challenge.consumed_at is not None
    credentials = [obj for obj in db.added if isinstance(obj, WebAuthnCredentialModel)]
    assert len(credentials) == 1
    credential = credentials[0]
    assert credential.user_id == user.id
    assert credential.credential_id == wr._bytes_to_b64url(b"credential-one")
    assert credential.public_key == b"public-key"
    assert credential.sign_count == 7


@pytest.mark.asyncio
async def test_registration_verify_resets_dependency_read_transaction_before_row_lock(monkeypatch):
    user = _user()
    challenge = _stored_challenge(
        user_id=user.id,
        challenge="registration-challenge",
        purpose=wr.WEBAUTHN_REGISTRATION_PURPOSE,
    )
    db = FakeDb([FakeResult(scalar=challenge)])
    db.active_transaction = True

    monkeypatch.setattr(
        wr,
        "_webauthn_verify_registration_response",
        lambda **kwargs: SimpleNamespace(
            credential_id=b"credential-one",
            credential_public_key=b"public-key",
            sign_count=1,
        ),
    )

    result = await wr.verify_webauthn_registration(
        payload=_credential_payload("registration-challenge"),
        request=_request("/auth/webauthn/register/verify"),
        db=db,
        current_user=user,
    )

    assert result == {"status": "verified"}
    assert db.rollback_count == 1
    assert db.begin_count == 1
    assert db.commit_count == 1
    assert challenge.consumed_at is not None


@pytest.mark.asyncio
async def test_registration_verify_returns_401_when_webauthn_library_rejects(monkeypatch):
    user = _user()
    challenge = _stored_challenge(
        user_id=user.id,
        challenge="registration-challenge",
        purpose=wr.WEBAUTHN_REGISTRATION_PURPOSE,
    )
    db = FakeDb([FakeResult(scalar=challenge)])

    def reject(**kwargs):
        raise ValueError("bad attestation")

    monkeypatch.setattr(wr, "_webauthn_verify_registration_response", reject)

    with pytest.raises(HTTPException) as exc_info:
        await wr.verify_webauthn_registration(
            payload=_credential_payload("registration-challenge"),
            request=_request("/auth/webauthn/register/verify"),
            db=db,
            current_user=user,
        )

    assert exc_info.value.status_code == 401
    assert not [obj for obj in db.added if isinstance(obj, WebAuthnCredentialModel)]
    assert challenge.consumed_at is None


@pytest.mark.asyncio
async def test_login_generate_options_returns_fake_challenge_without_user_enumeration(monkeypatch):
    db = FakeDb([FakeResult(scalar=None)])

    def fail_if_called(**kwargs):
        pytest.fail("unknown users must not reach WebAuthn option generation")

    monkeypatch.setattr(wr, "_webauthn_generate_authentication_options", fail_if_called)

    result = await wr.generate_webauthn_login_options(
        payload=wr.WebAuthnLoginOptionsRequest(email="missing@example.com"),
        db=db,
    )

    assert result["challenge"]
    assert isinstance(result["allowCredentials"], list) and len(result["allowCredentials"]) == 1
    assert result["allowCredentials"][0]["type"] == "public-key"
    assert result["allowCredentials"][0]["id"]
    assert result["userVerification"] == "required"
    assert db.added == []
    assert db.commit_count == 0


@pytest.mark.asyncio
async def test_login_generate_options_for_passkey_user_stores_authentication_challenge(monkeypatch):
    user = _user()
    credential = _stored_credential(user_id=user.id, credential_id=wr._bytes_to_b64url(b"credential-one"))
    db = FakeDb([FakeResult(scalar=user), FakeResult(scalars=[credential])])

    def fake_generate(*, credentials):
        assert credentials == [credential]
        return {"challenge": "authentication-challenge"}, "authentication-challenge"

    monkeypatch.setattr(wr, "_webauthn_generate_authentication_options", fake_generate)

    result = await wr.generate_webauthn_login_options(
        payload=wr.WebAuthnLoginOptionsRequest(email="admin@example.com"),
        db=db,
    )

    assert result == {"challenge": "authentication-challenge"}
    assert db.commit_count == 1
    assert len(db.added) == 1
    state = db.added[0]
    assert isinstance(state, WebAuthnChallengeModel)
    assert state.user_id == user.id
    assert state.purpose == wr.WEBAUTHN_AUTHENTICATION_PURPOSE
    assert state.challenge == "authentication-challenge"


@pytest.mark.asyncio
async def test_login_verify_updates_sign_count_consumes_challenge_and_sets_session_cookie(monkeypatch):
    user = _user()
    challenge = _stored_challenge(
        user_id=user.id,
        challenge="authentication-challenge",
        purpose=wr.WEBAUTHN_AUTHENTICATION_PURPOSE,
    )
    credential = _stored_credential(user_id=user.id)
    membership_id = uuid.UUID("44444444-4444-4444-8444-444444444444")
    db = FakeDb(
        [
            FakeResult(scalar=challenge),
            FakeResult(scalar=credential),
            FakeResult(scalar=user),
            FakeResult(scalar=membership_id),
        ]
    )

    monkeypatch.setattr(
        wr,
        "_webauthn_verify_authentication_response",
        lambda **kwargs: SimpleNamespace(new_sign_count=2),
    )
    response = Response()

    result = await wr.verify_webauthn_login(
        payload=_credential_payload("authentication-challenge"),
        request=_request(),
        response=response,
        db=db,
        crypto_service=FakeCrypto(),
    )

    assert result == {"status": "verified"}
    assert db.begin_count == 1
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert challenge.consumed_at is not None
    assert credential.sign_count == 2
    assert credential.last_used_at is not None
    sessions = [obj for obj in db.added if isinstance(obj, SessionModel)]
    assert len(sessions) == 1
    session = sessions[0]
    assert session.user_id == user.id
    assert session.active_membership_id == membership_id
    assert session.token_hash == "stored-session-digest"
    assert session.refresh_token_hash == "stored-session-digest"
    assert session.auth_method == "webauthn"
    assert session.authenticated_at is not None
    assert "raw-session-token" not in repr(session.__dict__)

    set_cookie = response.headers["set-cookie"]
    assert f"{wr.AUTH_SESSION_COOKIE}=raw-session-token" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie


@pytest.mark.asyncio
async def test_login_verify_returns_401_when_webauthn_library_rejects(monkeypatch):
    user = _user()
    challenge = _stored_challenge(
        user_id=user.id,
        challenge="authentication-challenge",
        purpose=wr.WEBAUTHN_AUTHENTICATION_PURPOSE,
    )
    credential = _stored_credential(user_id=user.id)
    db = FakeDb(
        [
            FakeResult(scalar=challenge),
            FakeResult(scalar=credential),
            FakeResult(scalar=user),
        ]
    )

    def reject(**kwargs):
        raise ValueError("bad assertion")

    monkeypatch.setattr(wr, "_webauthn_verify_authentication_response", reject)
    response = Response()

    with pytest.raises(HTTPException) as exc_info:
        await wr.verify_webauthn_login(
            payload=_credential_payload("authentication-challenge"),
            request=_request(),
            response=response,
            db=db,
            crypto_service=FakeCrypto(),
        )

    assert exc_info.value.status_code == 401
    assert not [obj for obj in db.added if isinstance(obj, SessionModel)]
    assert "set-cookie" not in response.headers
    assert challenge.consumed_at is None


@pytest.mark.asyncio
async def test_login_verify_rejects_non_monotonic_sign_count_without_session(monkeypatch):
    user = _user()
    challenge = _stored_challenge(
        user_id=user.id,
        challenge="authentication-challenge",
        purpose=wr.WEBAUTHN_AUTHENTICATION_PURPOSE,
    )
    credential = _stored_credential(user_id=user.id)
    credential.sign_count = 5
    db = FakeDb(
        [
            FakeResult(scalar=challenge),
            FakeResult(scalar=credential),
            FakeResult(scalar=user),
        ]
    )

    monkeypatch.setattr(
        wr,
        "_webauthn_verify_authentication_response",
        lambda **kwargs: SimpleNamespace(new_sign_count=5),
    )

    with pytest.raises(HTTPException) as exc_info:
        await wr.verify_webauthn_login(
            payload=_credential_payload("authentication-challenge"),
            request=_request(),
            response=Response(),
            db=db,
            crypto_service=FakeCrypto(),
        )

    assert exc_info.value.status_code == 401
    assert not [obj for obj in db.added if isinstance(obj, SessionModel)]
