"""Tests for argon2-based recovery code hashing -- #1041.

Verifies that hash_recovery_code uses argon2id instead of SHA-256, that
verify_recovery_code correctly validates and rejects codes, and that legacy
SHA-256 hashes are gracefully rejected (False, not a crash).
"""

import hashlib
import inspect
import sys
import types as _types

import pytest

# Stub pyotp before importing mfa module (pyotp may not be installed in CI)
if "pyotp" not in sys.modules:

    class _FakeTOTP:
        def __init__(self, secret):
            self._secret = secret

        def verify(self, token, valid_window=1):
            return token == "999111"

        def provisioning_uri(self, name=None, issuer_name=None):
            return f"otpauth://totp/{issuer_name}:{name}?secret={self._secret}"

    _pyotp_stub = _types.ModuleType("pyotp")
    _pyotp_stub.TOTP = _FakeTOTP
    _pyotp_stub.random_base32 = lambda: "JBSWY3DPEHPK3PXP"
    sys.modules["pyotp"] = _pyotp_stub


from services.admin.app.mfa import hash_recovery_code, verify_recovery_code  # noqa: E402


# ── hash_recovery_code produces argon2 output ───────────────────────────────


def test_hash_recovery_code_returns_argon2_prefix():
    """hash_recovery_code must return an argon2id hash, not a hex digest."""
    result = hash_recovery_code("ABCD-EFGH")
    assert result.startswith("$argon2"), (
        f"Expected argon2 hash (prefix $argon2), got: {result!r}"
    )


def test_hash_recovery_code_not_sha256_length():
    """SHA-256 hex digests are exactly 64 chars. Argon2 hashes are longer."""
    result = hash_recovery_code("ABCD-EFGH")
    assert len(result) > 64, (
        f"Hash length {len(result)} looks like a SHA-256 hex digest: {result!r}"
    )


def test_hash_recovery_code_implementation_is_not_sha256():
    """Source-level guard: hash_recovery_code must not use hashlib.sha256."""
    source = inspect.getsource(hash_recovery_code)
    assert "sha256" not in source, (
        "hash_recovery_code still references sha256 — was the refactor reverted?"
    )
    assert "hashlib" not in source, (
        "hash_recovery_code still imports hashlib — was the refactor reverted?"
    )


# ── verify_recovery_code correctness ────────────────────────────────────────


def test_verify_recovery_code_correct_code_returns_true():
    """Correct code verifies successfully."""
    hashed = hash_recovery_code("ABCD-EFGH")
    assert verify_recovery_code("ABCD-EFGH", hashed) is True


def test_verify_recovery_code_wrong_code_returns_false():
    """Wrong code must return False."""
    hashed = hash_recovery_code("ABCD-EFGH")
    assert verify_recovery_code("WRONG123", hashed) is False


def test_verify_recovery_code_normalizes_case_and_dash():
    """Normalization: lower-case and dash variants of the same code must verify."""
    hashed = hash_recovery_code("ABCD-EFGH")
    assert verify_recovery_code("abcd-efgh", hashed) is True
    assert verify_recovery_code("abcdefgh", hashed) is True
    assert verify_recovery_code("ABCDEFGH", hashed) is True


# ── legacy SHA-256 hash rejection ───────────────────────────────────────────


def _sha256_hash(code: str) -> str:
    """Reproduce the old hash_recovery_code logic for test setup."""
    from services.admin.app.mfa import normalize_recovery_code
    canonical = normalize_recovery_code(code)
    return hashlib.sha256(canonical.encode()).hexdigest()


def test_verify_recovery_code_rejects_sha256_hash_gracefully():
    """Legacy SHA-256 hashes must return False, not raise an exception."""
    sha256_hash = _sha256_hash("ABCD-EFGH")
    # Must not crash
    result = verify_recovery_code("ABCD-EFGH", sha256_hash)
    assert result is False, (
        "verify_recovery_code returned True for a SHA-256 hash — "
        "legacy hashes must be rejected."
    )


def test_verify_recovery_code_rejects_arbitrary_string_gracefully():
    """Garbage hash values must return False, not raise."""
    assert verify_recovery_code("ABCD-EFGH", "not-a-hash-at-all") is False
    assert verify_recovery_code("ABCD-EFGH", "") is False


# ── each hash is unique (salted) ────────────────────────────────────────────


def test_hash_recovery_code_produces_unique_hashes_for_same_input():
    """Argon2 is salted — hashing the same code twice must yield different strings."""
    h1 = hash_recovery_code("ABCD-EFGH")
    h2 = hash_recovery_code("ABCD-EFGH")
    assert h1 != h2, "Argon2 hashes should be salted and therefore unique per call."
    # But both should verify correctly
    assert verify_recovery_code("ABCD-EFGH", h1) is True
    assert verify_recovery_code("ABCD-EFGH", h2) is True
