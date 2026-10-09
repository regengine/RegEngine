"""Tests for POST /auth/challenges passwordless login start."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from pydantic import ValidationError
from starlette.requests import Request
from starlette.testclient import TestClient

from services.admin.app.auth import challenges_router as cr
from services.admin.app.auth.schemas import ChallengeCreateRequest, ChallengeVerifyRequest
from services.admin.app.e2e_safety import CriticalSecurityError
from services.admin.app.rate_limit_service import RateLimitExceededException
from services.admin.app.sqlalchemy_models import AuthChallengeModel, SessionModel


class _DummyEmails:
    last_payload = None

    @staticmethod
    def send(payload):
        _DummyEmails.last_payload = payload
        return SimpleNamespace(id="email_123")


class _DummyResend:
    api_key = None
    Emails = _DummyEmails


def _make_request(*, client_host: str = "203.0.113.50", cookie: str | None = None) -> Request:
    raw_headers = []
    if cookie is not None:
        raw_headers.append((b"cookie", f"{cr.AUTH_BROWSER_NONCE_COOKIE}={cookie}".encode("latin-1")))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/challenges",
        "headers": raw_headers,
        "client": (client_host, 12345),
        "server": ("testserver", 80),
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


class FakeCrypto:
    def __init__(self, *, verify_result: bool = True, opaque_tokens: list[str] | None = None):
        self.generated_nonces = 0
        self.hash_otp_calls = []
        self.verify_result = verify_result
        self.verify_calls = []
        self.opaque_tokens = list(opaque_tokens or ["browser-nonce"])

    def fingerprint_email(self, email: str) -> str:
        return f"fingerprint:{email}"

    def generate_opaque_session_token(self) -> str:
        self.generated_nonces += 1
        return self.opaque_tokens.pop(0) if self.opaque_tokens else "opaque-token"

    def hash_session_token(self, token: str) -> str:
        if token == "session-token":
            return "stored-session-digest"
        if token == "refresh-token":
            return "stored-refresh-digest"
        return f"browser-hash:{token}"

    def generate_secure_otp(self) -> str:
        return "012345"

    def hash_otp(self, *, challenge_id, purpose, email_fingerprint, code) -> str:
        self.hash_otp_calls.append(
            {
                "challenge_id": challenge_id,
                "purpose": purpose,
                "email_fingerprint": email_fingerprint,
                "code": code,
            }
        )
        return "hmac-digest"

    def verify_otp_hash(self, *, expected_hash, challenge_id, purpose, email_fingerprint, code) -> bool:
        self.verify_calls.append(
            {
                "expected_hash": expected_hash,
                "challenge_id": challenge_id,
                "purpose": purpose,
                "email_fingerprint": email_fingerprint,
                "code": code,
            }
        )
        return self.verify_result


class FakeRateLimit:
    def __init__(self, exc: Exception | None = None):
        self.exc = exc
        self.calls = []

    async def check_otp_generation(self, *, email_fingerprint, browser_binding_hash, ip_address):
        self.calls.append(
            {
                "email_fingerprint": email_fingerprint,
                "browser_binding_hash": browser_binding_hash,
                "ip_address": ip_address,
            }
        )
        if self.exc:
            raise self.exc


class FakeResult:
    def __init__(self, *, scalar=None, first=None):
        self._scalar = scalar
        self._first = first

    def scalar_one_or_none(self):
        return self._scalar

    def first(self):
        return self._first


def _is_security_guc(statement) -> bool:
    return "set_config('regengine.is_sysadmin'" in str(statement)


def _data_execute_statements(db):
    return [statement for statement in db.execute_statements if not _is_security_guc(statement)]


def _data_execute_calls(db):
    return [call for call in db.execute.call_args_list if not _is_security_guc(call.args[0])]


class FakeTransaction:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.begin_count += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.db.rollback_count += 1
        else:
            self.db.commit_count += 1
        return False


class FakeDb:
    def __init__(self, results):
        self.results = list(results)
        self.execute_statements = []
        self.added = []
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0

    def begin(self):
        return FakeTransaction(self)

    def execute(self, statement):
        self.execute_statements.append(statement)
        if _is_security_guc(statement):
            return FakeResult()
        if not self.results:
            raise AssertionError("unexpected execute")
        return self.results.pop(0)

    def add(self, obj):
        self.added.append(obj)


class LockedChallengeStore:
    def __init__(self):
        self.challenge = _challenge()
        self.identity = _identity()
        self.row_lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.added = []
        self.lock_acquisitions = 0


class LockedTransaction:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.begin_count += 1
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.db.rollback_count += 1
        else:
            self.db.commit_count += 1
        if self.db.owns_row_lock:
            self.db.store.row_lock.release()
            self.db.owns_row_lock = False
        return False


class LockedFakeDb:
    def __init__(self, store: LockedChallengeStore):
        self.store = store
        self.begin_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        self.owns_row_lock = False
        self.challenge_loaded = False
        self.execute_statements = []

    def begin(self):
        return LockedTransaction(self)

    def execute(self, statement):
        self.execute_statements.append(statement)
        if _is_security_guc(statement):
            return FakeResult()
        if not self.challenge_loaded:
            self.challenge_loaded = True
            if not self.store.row_lock.acquire(timeout=2):
                raise AssertionError("timed out waiting for simulated row lock")
            self.owns_row_lock = True
            with self.store.state_lock:
                self.store.lock_acquisitions += 1
            time.sleep(0.05)
            return FakeResult(scalar=self.store.challenge)
        return FakeResult(first=self.store.identity)

    def add(self, obj):
        with self.store.state_lock:
            self.store.added.append(obj)


def _challenge(
    *,
    status: str = "pending",
    failed_attempts: int = 0,
    expires_delta_seconds: int = 60,
    browser_binding_hash: str = "browser-hash:browser-nonce",
    email_fingerprint: str = "email-fp",
) -> AuthChallengeModel:
    return AuthChallengeModel(
        id=uuid.UUID("22222222-2222-4222-8222-222222222222"),
        purpose="sign_in",
        email_fingerprint=email_fingerprint,
        code_digest="stored-hmac-digest",
        browser_binding_hash=browser_binding_hash,
        status=status,
        failed_attempts=failed_attempts,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_delta_seconds),
    )


def _identity():
    user = SimpleNamespace(id=uuid.UUID("33333333-3333-4333-8333-333333333333"))
    membership = SimpleNamespace(id=uuid.UUID("44444444-4444-4444-8444-444444444444"))
    return user, membership


_DEFAULT_IDENTITY = object()


def _mock_db_for_identity(identity=_DEFAULT_IDENTITY):
    db = MagicMock()
    identity_result = MagicMock()
    identity_result.first.return_value = _identity() if identity is _DEFAULT_IDENTITY else identity
    db.execute.side_effect = lambda statement: MagicMock() if _is_security_guc(statement) else identity_result
    return db


@pytest.mark.asyncio
async def test_create_auth_challenge_persists_digest_sets_cookie_and_queues_plaintext_code(monkeypatch):
    fixed_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    monkeypatch.setattr(cr.uuid, "uuid4", lambda: fixed_id)

    db = _mock_db_for_identity()
    response = Response()
    background_tasks = BackgroundTasks()
    crypto = FakeCrypto()
    rate_limit = FakeRateLimit()

    result = await cr.create_auth_challenge(
        payload=ChallengeCreateRequest(email="USER@example.com"),
        request=_make_request(),
        response=response,
        background_tasks=background_tasks,
        db=db,
        rate_limit_service=rate_limit,
        crypto_service=crypto,
    )

    assert result.detail == cr.AUTH_CHALLENGE_DETAIL
    assert result.challenge_id == str(fixed_id)
    db.add.assert_called_once()
    db.commit.assert_called_once()
    challenge = db.add.call_args.args[0]
    assert challenge.id == fixed_id
    assert challenge.purpose == "sign_in"
    assert challenge.email_fingerprint == "fingerprint:user@example.com"
    assert challenge.code_digest == "hmac-digest"
    assert challenge.browser_binding_hash == "browser-hash:browser-nonce"
    assert challenge.status == "pending"
    assert challenge.failed_attempts == 0
    assert challenge.expires_at > datetime.now(timezone.utc)
    assert "012345" not in repr(challenge.__dict__)

    assert crypto.hash_otp_calls == [
        {
            "challenge_id": fixed_id,
            "purpose": "sign_in",
            "email_fingerprint": "fingerprint:user@example.com",
            "code": "012345",
        }
    ]
    assert rate_limit.calls == [
        {
            "email_fingerprint": "fingerprint:user@example.com",
            "browser_binding_hash": "browser-hash:browser-nonce",
            "ip_address": "203.0.113.50",
        }
    ]

    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func is cr._dispatch_sign_in_code_email
    assert task.args == ("user@example.com", "012345", fixed_id)

    set_cookie = response.headers["set-cookie"]
    assert f"{cr.AUTH_BROWSER_NONCE_COOKIE}=browser-nonce" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


@pytest.mark.asyncio
async def test_verified_sso_only_identity_gets_generic_contract_without_email(monkeypatch):
    fixed_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    db = _mock_db_for_identity(identity=None)
    response = Response()
    background_tasks = BackgroundTasks()
    crypto = FakeCrypto()
    rate_limit = FakeRateLimit()
    monkeypatch.setattr(cr.uuid, "uuid4", lambda: fixed_id)

    result = await cr.create_auth_challenge(
        payload=ChallengeCreateRequest(email="Leader@Enterprise.Example"),
        request=_make_request(),
        response=response,
        background_tasks=background_tasks,
        db=db,
        rate_limit_service=rate_limit,
        crypto_service=crypto,
    )

    assert result.model_dump(exclude_none=True) == {
        "detail": cr.AUTH_CHALLENGE_DETAIL,
        "challenge_id": str(fixed_id),
    }
    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert len(crypto.hash_otp_calls) == 1
    assert len(rate_limit.calls) == 1
    assert background_tasks.tasks == []
    assert f"{cr.AUTH_BROWSER_NONCE_COOKIE}=browser-nonce" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_unverified_sso_only_domain_uses_normal_otp_flow(monkeypatch):
    fixed_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    monkeypatch.setattr(cr.uuid, "uuid4", lambda: fixed_id)
    db = _mock_db_for_identity()
    response = Response()
    background_tasks = BackgroundTasks()
    crypto = FakeCrypto()
    rate_limit = FakeRateLimit()

    result = await cr.create_auth_challenge(
        payload=ChallengeCreateRequest(email="user@unverified.example"),
        request=_make_request(),
        response=response,
        background_tasks=background_tasks,
        db=db,
        rate_limit_service=rate_limit,
        crypto_service=crypto,
    )

    assert result.model_dump(exclude_none=True) == {
        "detail": cr.AUTH_CHALLENGE_DETAIL,
        "challenge_id": str(fixed_id),
    }
    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert crypto.hash_otp_calls[0]["challenge_id"] == fixed_id
    assert rate_limit.calls[0]["email_fingerprint"] == "fingerprint:user@unverified.example"
    assert len(background_tasks.tasks) == 1
    assert f"{cr.AUTH_BROWSER_NONCE_COOKIE}=browser-nonce" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_standard_domain_still_uses_normal_otp_flow(monkeypatch):
    fixed_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
    monkeypatch.setattr(cr.uuid, "uuid4", lambda: fixed_id)
    db = _mock_db_for_identity()
    response = Response()
    background_tasks = BackgroundTasks()
    crypto = FakeCrypto()
    rate_limit = FakeRateLimit()

    result = await cr.create_auth_challenge(
        payload=ChallengeCreateRequest(email="user@standard.example"),
        request=_make_request(),
        response=response,
        background_tasks=background_tasks,
        db=db,
        rate_limit_service=rate_limit,
        crypto_service=crypto,
    )

    assert result.model_dump(exclude_none=True) == {
        "detail": cr.AUTH_CHALLENGE_DETAIL,
        "challenge_id": str(fixed_id),
    }
    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert crypto.hash_otp_calls[0]["challenge_id"] == fixed_id
    assert rate_limit.calls[0]["email_fingerprint"] == "fingerprint:user@standard.example"
    assert len(background_tasks.tasks) == 1
    assert f"{cr.AUTH_BROWSER_NONCE_COOKIE}=browser-nonce" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_existing_browser_nonce_is_reused_for_binding_and_cookie():
    db = _mock_db_for_identity()
    response = Response()
    crypto = FakeCrypto()
    rate_limit = FakeRateLimit()

    await cr.create_auth_challenge(
        payload=ChallengeCreateRequest(email="user@example.com"),
        request=_make_request(cookie="existing-browser-nonce"),
        response=response,
        background_tasks=BackgroundTasks(),
        db=db,
        rate_limit_service=rate_limit,
        crypto_service=crypto,
    )

    assert crypto.generated_nonces == 0
    assert rate_limit.calls[0]["browser_binding_hash"] == "browser-hash:existing-browser-nonce"
    assert f"{cr.AUTH_BROWSER_NONCE_COOKIE}=existing-browser-nonce" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_rate_limit_exceeded_does_not_persist_or_enqueue_or_set_cookie():
    db = _mock_db_for_identity()
    response = Response()
    background_tasks = BackgroundTasks()
    rate_limit = FakeRateLimit(
        RateLimitExceededException(
            key="rate-key",
            limit=1,
            window_seconds=60,
            retry_after_seconds=60,
            bucket_name="email_browser",
        )
    )

    with pytest.raises(HTTPException) as exc_info:
        await cr.create_auth_challenge(
            payload=ChallengeCreateRequest(email="user@example.com"),
            request=_make_request(),
            response=response,
            background_tasks=background_tasks,
            db=db,
            rate_limit_service=rate_limit,
            crypto_service=FakeCrypto(),
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "60"
    db.add.assert_not_called()
    db.commit.assert_not_called()
    assert background_tasks.tasks == []
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_passwordless_identity_query_joins_organization_policy():
    db = MagicMock()
    db.execute.return_value.first.return_value = None

    assert cr._load_valid_identity(db=db, email_fingerprint="fingerprint:user@example.com") is None

    statement = str(db.execute.call_args.args[0]).lower()
    assert "join organizations" in statement
    assert "enforced_auth_policy" in statement
    assert "domain_verified" in statement


@pytest.mark.asyncio
async def test_known_and_unknown_email_get_same_response_but_only_known_identity_receives_code():
    async def call(email: str, identity):
        db = _mock_db_for_identity(identity=identity)
        response = Response()
        background_tasks = BackgroundTasks()
        result = await cr.create_auth_challenge(
            payload=ChallengeCreateRequest(email=email),
            request=_make_request(),
            response=response,
            background_tasks=background_tasks,
            db=db,
            rate_limit_service=FakeRateLimit(),
            crypto_service=FakeCrypto(),
        )
        return result, db, response, background_tasks

    known, known_db, known_response, known_tasks = await call("known@example.com", _identity())
    unknown, unknown_db, unknown_response, unknown_tasks = await call("unknown@example.com", None)

    assert known.detail == unknown.detail == cr.AUTH_CHALLENGE_DETAIL
    assert known.challenge_id
    assert unknown.challenge_id
    known_queries = _data_execute_calls(known_db)
    unknown_queries = _data_execute_calls(unknown_db)
    assert len(known_queries) == len(unknown_queries) == 1
    assert "organizations" in str(known_queries[0].args[0])
    assert "users" in str(known_queries[0].args[0])
    assert known_db.add.call_count == unknown_db.add.call_count == 1
    assert known_db.commit.call_count == unknown_db.commit.call_count == 1
    assert bool(known_response.headers.get("set-cookie")) == bool(unknown_response.headers.get("set-cookie"))
    assert len(known_tasks.tasks) == 1
    assert unknown_tasks.tasks == []


@pytest.mark.asyncio
async def test_identity_lookup_failure_returns_503_without_generating_otp():
    db = MagicMock()

    def _execute(statement):
        if _is_security_guc(statement):
            return MagicMock()
        raise RuntimeError("identity lookup failed")

    db.execute.side_effect = _execute
    response = Response()
    background_tasks = BackgroundTasks()
    crypto = FakeCrypto()
    rate_limit = FakeRateLimit()

    with pytest.raises(HTTPException) as exc_info:
        await cr.create_auth_challenge(
            payload=ChallengeCreateRequest(email="user@example.com"),
            request=_make_request(),
            response=response,
            background_tasks=background_tasks,
            db=db,
            rate_limit_service=rate_limit,
            crypto_service=crypto,
        )

    assert exc_info.value.status_code == 503
    db.add.assert_not_called()
    db.commit.assert_not_called()
    assert len(rate_limit.calls) == 1
    assert background_tasks.tasks == []
    assert "set-cookie" not in response.headers


def test_challenge_request_validates_email_syntax():
    with pytest.raises(ValidationError):
        ChallengeCreateRequest(email="not-an-email")


@pytest.mark.asyncio
async def test_verify_auth_challenge_consumes_challenge_creates_session_and_sets_host_cookie():
    challenge = _challenge()
    db = FakeDb(
        [
            FakeResult(scalar=challenge),
            FakeResult(first=_identity()),
        ]
    )
    response = Response()
    crypto = FakeCrypto(opaque_tokens=["session-token", "refresh-token"])

    result = await cr.verify_auth_challenge(
        challenge_id=challenge.id,
        payload=ChallengeVerifyRequest(code="012345"),
        request=_make_request(cookie="browser-nonce"),
        response=response,
        db=db,
        crypto_service=crypto,
    )

    assert result.status == "verified"
    assert challenge.status == "consumed"
    assert db.begin_count == 1
    assert db.commit_count == 1
    assert db.rollback_count == 0
    assert _data_execute_statements(db)[0]._for_update_arg is not None
    assert len(db.added) == 1
    session = db.added[0]
    assert isinstance(session, SessionModel)
    assert session.user_id == _identity()[0].id
    assert session.active_membership_id == _identity()[1].id
    assert session.token_hash == "stored-session-digest"
    assert session.refresh_token_hash == "stored-refresh-digest"
    assert session.refresh_token_hash != session.token_hash
    assert session.auth_method == "email_otp"
    assert session.authenticated_at is not None
    assert "session-token" not in repr(session.__dict__)
    assert "refresh-token" not in repr(session.__dict__)
    assert crypto.verify_calls == [
        {
            "expected_hash": "stored-hmac-digest",
            "challenge_id": challenge.id,
            "purpose": "sign_in",
            "email_fingerprint": "email-fp",
            "code": "012345",
        }
    ]

    set_cookie = response.headers["set-cookie"]
    assert f"{cr.AUTH_SESSION_COOKIE}=session-token" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie


def test_verify_concurrent_double_submit_creates_one_session_under_row_lock():
    store = LockedChallengeStore()
    barrier = threading.Barrier(2)
    result_lock = threading.Lock()
    results = []

    def submit(name: str):
        db = LockedFakeDb(store)
        response = Response()
        barrier.wait(timeout=2)
        try:
            result = asyncio.run(
                cr.verify_auth_challenge(
                    challenge_id=store.challenge.id,
                    payload=ChallengeVerifyRequest(code="012345"),
                    request=_make_request(cookie="browser-nonce"),
                    response=response,
                    db=db,
                    crypto_service=FakeCrypto(opaque_tokens=["session-token"]),
                )
            )
            outcome = {"name": name, "status_code": 200, "result": result, "response": response, "db": db}
        except HTTPException as exc:
            outcome = {"name": name, "status_code": exc.status_code, "response": response, "db": db}
        except BaseException as exc:  # pragma: no cover - makes thread failures visible
            outcome = {"name": name, "exception": exc, "response": response, "db": db}
        with result_lock:
            results.append(outcome)

    threads = [
        threading.Thread(target=submit, args=("first",)),
        threading.Thread(target=submit, args=("second",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 2
    exceptions = [result.get("exception") for result in results if "exception" in result]
    assert exceptions == []
    assert sorted(result["status_code"] for result in results) == [200, 401]
    assert store.challenge.status == "consumed"
    assert store.lock_acquisitions == 2
    assert len(store.added) == 1
    assert isinstance(store.added[0], SessionModel)

    success = next(result for result in results if result["status_code"] == 200)
    assert success["result"].status == "verified"
    assert cr.AUTH_SESSION_COOKIE in success["response"].headers["set-cookie"]


@pytest.mark.asyncio
async def test_verify_wrong_code_increments_attempts_locks_at_five_and_commits():
    challenge = _challenge(failed_attempts=4)
    db = FakeDb([FakeResult(scalar=challenge)])
    response = Response()

    with pytest.raises(HTTPException) as exc_info:
        await cr.verify_auth_challenge(
            challenge_id=challenge.id,
            payload=ChallengeVerifyRequest(code="999999"),
            request=_make_request(cookie="browser-nonce"),
            response=response,
            db=db,
            crypto_service=FakeCrypto(verify_result=False),
        )

    assert exc_info.value.status_code == 401
    assert challenge.failed_attempts == 5
    assert challenge.status == "locked"
    assert db.commit_count == 1
    assert db.added == []
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_verify_wrong_code_below_threshold_keeps_pending_and_commits():
    challenge = _challenge(failed_attempts=2)
    db = FakeDb([FakeResult(scalar=challenge)])

    with pytest.raises(HTTPException) as exc_info:
        await cr.verify_auth_challenge(
            challenge_id=challenge.id,
            payload=ChallengeVerifyRequest(code="999999"),
            request=_make_request(cookie="browser-nonce"),
            response=Response(),
            db=db,
            crypto_service=FakeCrypto(verify_result=False),
        )

    assert exc_info.value.status_code == 401
    assert challenge.failed_attempts == 3
    assert challenge.status == "pending"
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_verify_browser_binding_mismatch_does_not_increment_attempts():
    challenge = _challenge(failed_attempts=1)
    db = FakeDb([FakeResult(scalar=challenge)])

    with pytest.raises(HTTPException) as exc_info:
        await cr.verify_auth_challenge(
            challenge_id=challenge.id,
            payload=ChallengeVerifyRequest(code="012345"),
            request=_make_request(cookie="wrong-browser-nonce"),
            response=Response(),
            db=db,
            crypto_service=FakeCrypto(),
        )

    assert exc_info.value.status_code == 401
    assert challenge.failed_attempts == 1
    assert challenge.status == "pending"
    assert db.commit_count == 1
    assert db.added == []


def test_browser_binding_uses_constant_time_comparison(monkeypatch):
    calls = []

    def fake_compare_digest(left, right):
        calls.append((left, right))
        return True

    monkeypatch.setattr(cr.hmac, "compare_digest", fake_compare_digest)

    assert cr._browser_binding_matches(
        request=_make_request(cookie="browser-nonce"),
        challenge=_challenge(),
        crypto_service=FakeCrypto(),
    )
    assert calls == [("browser-hash:browser-nonce", "browser-hash:browser-nonce")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "challenge",
    [
        _challenge(status="consumed"),
        _challenge(status="locked"),
        _challenge(expires_delta_seconds=-1),
        _challenge(failed_attempts=5),
    ],
)
async def test_verify_rejects_non_pending_expired_or_exhausted_challenges(challenge):
    db = FakeDb([FakeResult(scalar=challenge)])

    with pytest.raises(HTTPException) as exc_info:
        await cr.verify_auth_challenge(
            challenge_id=challenge.id,
            payload=ChallengeVerifyRequest(code="012345"),
            request=_make_request(cookie="browser-nonce"),
            response=Response(),
            db=db,
            crypto_service=FakeCrypto(),
        )

    assert exc_info.value.status_code == 401
    assert db.added == []
    assert db.commit_count == 1


@pytest.mark.asyncio
async def test_verify_consumes_valid_code_but_returns_401_when_identity_not_valid():
    challenge = _challenge()
    db = FakeDb(
        [
            FakeResult(scalar=challenge),
            FakeResult(first=None),
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await cr.verify_auth_challenge(
            challenge_id=challenge.id,
            payload=ChallengeVerifyRequest(code="012345"),
            request=_make_request(cookie="browser-nonce"),
            response=Response(),
            db=db,
            crypto_service=FakeCrypto(),
        )

    assert exc_info.value.status_code == 401
    assert challenge.status == "consumed"
    assert db.commit_count == 1
    assert db.added == []


@pytest.mark.asyncio
async def test_verify_missing_challenge_cookie_returns_401_without_attempt_increment():
    challenge = _challenge(failed_attempts=1)
    db = FakeDb([FakeResult(scalar=challenge)])

    with pytest.raises(HTTPException) as exc_info:
        await cr.verify_auth_challenge(
            challenge_id=challenge.id,
            payload=ChallengeVerifyRequest(code="012345"),
            request=_make_request(cookie=None),
            response=Response(),
            db=db,
            crypto_service=FakeCrypto(),
        )

    assert exc_info.value.status_code == 401
    assert challenge.failed_attempts == 1
    assert db.commit_count == 1


def test_challenge_verify_request_validates_code_syntax():
    with pytest.raises(ValidationError):
        ChallengeVerifyRequest(code="abc123")
    with pytest.raises(ValidationError):
        ChallengeVerifyRequest(code="12345")


@pytest.mark.asyncio
async def test_db_failure_rolls_back_and_does_not_enqueue_or_set_cookie():
    db = _mock_db_for_identity()
    db.commit.side_effect = RuntimeError("database unavailable")
    response = Response()
    background_tasks = BackgroundTasks()

    with pytest.raises(HTTPException) as exc_info:
        await cr.create_auth_challenge(
            payload=ChallengeCreateRequest(email="user@example.com"),
            request=_make_request(),
            response=response,
            background_tasks=background_tasks,
            db=db,
            rate_limit_service=FakeRateLimit(),
            crypto_service=FakeCrypto(),
        )

    assert exc_info.value.status_code == 503
    db.rollback.assert_called_once()
    assert background_tasks.tasks == []
    assert "set-cookie" not in response.headers


def test_mock_dispatch_receives_but_does_not_log_plaintext_code(monkeypatch):
    fake_resend_token = "resend-fixture-value"
    monkeypatch.setenv("RESEND_API_KEY", fake_resend_token)
    monkeypatch.setenv("RESEND_FROM_EMAIL", "auth@regengine.test")
    monkeypatch.setitem(sys.modules, "resend", _DummyResend)
    _DummyEmails.last_payload = None
    logger = SimpleNamespace(info=MagicMock(), warning=MagicMock(), error=MagicMock())
    monkeypatch.setattr(cr, "logger", logger)

    cr._dispatch_sign_in_code_email("user@example.com", "012345", uuid.uuid4())

    for log_method in (logger.info, logger.warning, logger.error):
        for call in log_method.call_args_list:
            assert "code" not in call.kwargs
            assert "012345" not in repr(call.args)
            assert "012345" not in repr(call.kwargs)


def test_dispatch_sends_sign_in_code_with_resend_when_configured(monkeypatch):
    challenge_id = uuid.uuid4()
    fake_resend_token = "resend-fixture-value"
    monkeypatch.setenv("RESEND_API_KEY", fake_resend_token)
    monkeypatch.setenv("RESEND_FROM_EMAIL", "auth@regengine.test")
    monkeypatch.setitem(sys.modules, "resend", _DummyResend)
    _DummyEmails.last_payload = None
    logger = SimpleNamespace(info=MagicMock(), warning=MagicMock(), error=MagicMock())
    monkeypatch.setattr(cr, "logger", logger)

    cr._dispatch_sign_in_code_email("user@example.com", "012345", challenge_id)

    assert _DummyResend.api_key == fake_resend_token
    assert _DummyEmails.last_payload == {
        "from": "auth@regengine.test",
        "to": "user@example.com",
        "subject": "Your RegEngine sign-in code",
        "html": _DummyEmails.last_payload["html"],
    }
    assert "012345" in _DummyEmails.last_payload["html"]
    assert "012345" not in _DummyEmails.last_payload["subject"]
    assert logger.info.call_args.args[0] == "auth_challenge_email_sent"
    assert logger.info.call_args.kwargs["challenge_id"] == str(challenge_id)
    assert logger.info.call_args.kwargs["resend_id"] == "email_123"


def test_mock_dispatch_records_plaintext_code_only_in_e2e_outbox(monkeypatch, tmp_path):
    outbox = tmp_path / "auth-outbox.jsonl"
    challenge_id = uuid.uuid4()
    monkeypatch.setenv("REGENGINE_ENV", "test")
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setenv("REGENGINE_E2E_EMAIL_OUTBOX", str(outbox))
    monkeypatch.delenv("REGENGINE_E2E_MODE", raising=False)

    cr._dispatch_sign_in_code_email("user@example.com", "012345", challenge_id)
    assert not outbox.exists()

    monkeypatch.setenv("REGENGINE_E2E_MODE", "true")
    cr._dispatch_sign_in_code_email("user@example.com", "012345", challenge_id)

    record = json.loads(outbox.read_text(encoding="utf-8").strip())
    assert record == {
        "kind": "auth_challenge",
        "email": "user@example.com",
        "code": "012345",
        "challenge_id": str(challenge_id),
        "created_at": record["created_at"],
    }


def test_plaintext_otp_outbox_fatally_rejects_e2e_mode_in_production(monkeypatch, tmp_path):
    monkeypatch.setenv("REGENGINE_ENV", "production")
    monkeypatch.setenv("REGENGINE_E2E_MODE", "true")
    monkeypatch.setenv("REGENGINE_E2E_EMAIL_OUTBOX", str(tmp_path / "auth-outbox.jsonl"))
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(CriticalSecurityError, match="E2E mode is strictly forbidden in production"):
        cr._record_e2e_sign_in_code(
            email="user@example.com",
            code="012345",
            challenge_id=uuid.uuid4(),
        )


def test_route_returns_202_with_generic_body_and_secure_cookie(monkeypatch):
    app = FastAPI()
    app.include_router(cr.router, prefix="/auth")
    db = _mock_db_for_identity()
    crypto = FakeCrypto()
    rate_limit = FakeRateLimit()
    monkeypatch.setattr(cr, "_dispatch_sign_in_code_email", lambda *args: None)

    app.dependency_overrides[cr.get_session] = lambda: db
    app.dependency_overrides[cr.get_auth_crypto_service] = lambda: crypto
    app.dependency_overrides[cr.get_rate_limit_service] = lambda: rate_limit

    client = TestClient(app)
    response = client.post("/auth/challenges", json={"email": "user@example.com"})

    assert response.status_code == 202
    body = response.json()
    assert body["detail"] == cr.AUTH_CHALLENGE_DETAIL
    assert uuid.UUID(body["challenge_id"])
    assert response.cookies.get(cr.AUTH_BROWSER_NONCE_COOKIE) == "browser-nonce"
    set_cookie = response.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_route_sso_only_identity_returns_same_202_contract_and_cookie():
    app = FastAPI()
    app.include_router(cr.router, prefix="/auth")
    db = _mock_db_for_identity(identity=None)

    app.dependency_overrides[cr.get_session] = lambda: db
    app.dependency_overrides[cr.get_auth_crypto_service] = lambda: FakeCrypto()
    app.dependency_overrides[cr.get_rate_limit_service] = lambda: FakeRateLimit()

    client = TestClient(app)
    response = client.post("/auth/challenges", json={"email": "user@enterprise.example"})

    assert response.status_code == 202
    assert response.json()["detail"] == cr.AUTH_CHALLENGE_DETAIL
    assert uuid.UUID(response.json()["challenge_id"])
    db.add.assert_called_once()
    db.commit.assert_called_once()
    assert response.cookies.get(cr.AUTH_BROWSER_NONCE_COOKIE) == "browser-nonce"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_verify_route_returns_200_and_host_session_cookie(monkeypatch):
    app = FastAPI()
    app.include_router(cr.router, prefix="/auth")
    challenge = _challenge()
    db = FakeDb(
        [
            FakeResult(scalar=challenge),
            FakeResult(first=_identity()),
        ]
    )
    crypto = FakeCrypto(opaque_tokens=["session-token"])

    app.dependency_overrides[cr.get_session] = lambda: db
    app.dependency_overrides[cr.get_auth_crypto_service] = lambda: crypto

    client = TestClient(app)
    client.cookies.set(cr.AUTH_BROWSER_NONCE_COOKIE, "browser-nonce", path="/auth")
    response = client.post(f"/auth/challenges/{challenge.id}/verify", json={"code": "012345"})

    assert response.status_code == 200
    assert response.json() == {"status": "verified"}
    assert response.cookies.get(cr.AUTH_SESSION_COOKIE) == "session-token"
    set_cookie = response.headers["set-cookie"]
    assert f"{cr.AUTH_SESSION_COOKIE}=session-token" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "Path=/" in set_cookie
