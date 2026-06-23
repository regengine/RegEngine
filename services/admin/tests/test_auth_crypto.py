"""Unit tests for passwordless auth cryptographic helpers."""

from __future__ import annotations

import hashlib
import inspect
import re
import uuid

import pytest

from services.admin.app import auth_crypto
from services.admin.app.auth_crypto import AuthCryptoService


TEST_SECRET = "test-auth-otp-hmac-secret-32-bytes-minimum"
OTHER_SECRET = "other-auth-otp-hmac-secret-32-bytes-minimum"


def _service(secret: str = TEST_SECRET) -> AuthCryptoService:
    return AuthCryptoService(hmac_secret=secret)


def test_generate_secure_otp_returns_six_digit_string(monkeypatch):
    monkeypatch.setattr(auth_crypto.secrets, "randbelow", lambda upper: 42)

    code = AuthCryptoService.generate_secure_otp()

    assert code == "000042"
    assert len(code) == 6
    assert code.isdigit()


def test_generate_secure_otp_uses_full_million_code_space(monkeypatch):
    seen_upper_bound = []

    def fake_randbelow(upper: int) -> int:
        seen_upper_bound.append(upper)
        return 999999

    monkeypatch.setattr(auth_crypto.secrets, "randbelow", fake_randbelow)

    assert AuthCryptoService.generate_secure_otp() == "999999"
    assert seen_upper_bound == [1_000_000]


def test_hash_otp_is_hmac_sha256_and_deterministic():
    service = _service()
    challenge_id = uuid.uuid4()

    digest_a = service.hash_otp(challenge_id, "sign_in", "email-fp", "012345")
    digest_b = service.hash_otp(challenge_id, "sign_in", "email-fp", "012345")

    assert digest_a == digest_b
    assert re.fullmatch(r"[0-9a-f]{64}", digest_a)


@pytest.mark.parametrize(
    "field_name,replacement",
    [
        ("challenge_id", uuid.uuid4()),
        ("purpose", "step_up"),
        ("email_fingerprint", "other-email-fp"),
        ("code", "654321"),
    ],
)
def test_hash_otp_is_bound_to_all_context_fields(field_name, replacement):
    service = _service()
    values = {
        "challenge_id": uuid.uuid4(),
        "purpose": "sign_in",
        "email_fingerprint": "email-fp",
        "code": "012345",
    }
    original = service.hash_otp(**values)
    values[field_name] = replacement

    assert service.hash_otp(**values) != original


def test_hash_otp_changes_when_hmac_secret_changes():
    challenge_id = uuid.uuid4()

    digest_a = _service(TEST_SECRET).hash_otp(challenge_id, "sign_in", "email-fp", "012345")
    digest_b = _service(OTHER_SECRET).hash_otp(challenge_id, "sign_in", "email-fp", "012345")

    assert digest_a != digest_b


@pytest.mark.parametrize("bad_code", ["12345", "1234567", "abcdef", "", 123456])
def test_hash_otp_rejects_non_six_digit_codes(bad_code):
    with pytest.raises(ValueError, match="exactly 6 digits"):
        _service().hash_otp(uuid.uuid4(), "sign_in", "email-fp", bad_code)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"challenge_id": "", "purpose": "sign_in", "email_fingerprint": "email-fp", "code": "012345"},
        {"challenge_id": uuid.uuid4(), "purpose": "", "email_fingerprint": "email-fp", "code": "012345"},
        {"challenge_id": uuid.uuid4(), "purpose": "sign_in", "email_fingerprint": " ", "code": "012345"},
    ],
)
def test_hash_otp_rejects_missing_context(kwargs):
    with pytest.raises(ValueError):
        _service().hash_otp(**kwargs)


def test_verify_otp_hash_accepts_matching_hmac():
    service = _service()
    challenge_id = uuid.uuid4()
    expected = service.hash_otp(challenge_id, "sign_in", "email-fp", "012345")

    assert service.verify_otp_hash(expected, challenge_id, "sign_in", "email-fp", "012345") is True


def test_verify_otp_hash_rejects_wrong_code():
    service = _service()
    challenge_id = uuid.uuid4()
    expected = service.hash_otp(challenge_id, "sign_in", "email-fp", "012345")

    assert service.verify_otp_hash(expected, challenge_id, "sign_in", "email-fp", "111111") is False


def test_verify_otp_hash_strictly_uses_constant_time_compare(monkeypatch):
    service = _service()
    challenge_id = uuid.uuid4()
    expected = service.hash_otp(challenge_id, "sign_in", "email-fp", "012345")
    calls = []

    def fake_compare_digest(left: str, right: str) -> bool:
        calls.append((left, right))
        return False

    monkeypatch.setattr(auth_crypto.hmac, "compare_digest", fake_compare_digest)

    assert service.verify_otp_hash(expected, challenge_id, "sign_in", "email-fp", "012345") is False
    assert calls == [(expected, expected)]


def test_verify_otp_hash_source_guard_uses_compare_digest_not_equality():
    source = inspect.getsource(AuthCryptoService.verify_otp_hash)

    assert "compare_digest" in source
    assert "==" not in source


def test_otp_hashing_does_not_use_password_hashers():
    source = inspect.getsource(auth_crypto).lower()

    assert "bcrypt" not in source
    assert "argon" not in source
    assert "pwd_context" not in source


def test_generate_opaque_session_token_uses_256_bits(monkeypatch):
    calls = []

    def fake_token_urlsafe(nbytes: int) -> str:
        calls.append(nbytes)
        return "opaque-token"

    monkeypatch.setattr(auth_crypto.secrets, "token_urlsafe", fake_token_urlsafe)

    assert AuthCryptoService.generate_opaque_session_token() == "opaque-token"
    assert calls == [32]


def test_hash_session_token_uses_sha256_hex_digest():
    token = "browser-session-token"

    assert AuthCryptoService.hash_session_token(token) == hashlib.sha256(token.encode("utf-8")).hexdigest()


@pytest.mark.parametrize("bad_token", ["", None])
def test_hash_session_token_rejects_missing_token(bad_token):
    with pytest.raises(ValueError, match="session token is required"):
        AuthCryptoService.hash_session_token(bad_token)


def test_service_loads_hmac_secret_from_environment(monkeypatch):
    monkeypatch.setenv(auth_crypto._HMAC_SECRET_ENV, TEST_SECRET)

    service = AuthCryptoService()

    assert service.hash_otp(uuid.uuid4(), "sign_in", "email-fp", "012345")


def test_service_requires_hmac_secret_in_production(monkeypatch):
    monkeypatch.delenv(auth_crypto._HMAC_SECRET_ENV, raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "production")

    with pytest.raises(RuntimeError, match=auth_crypto._HMAC_SECRET_ENV):
        AuthCryptoService()


def test_hmac_secret_must_be_at_least_32_bytes():
    with pytest.raises(ValueError, match="at least 32 bytes"):
        AuthCryptoService(hmac_secret="too-short")
