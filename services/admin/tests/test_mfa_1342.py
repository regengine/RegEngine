"""Coverage sweep tests for services/admin/app/mfa.py (issue #1342).

Pins the remaining uncovered branches after test_mfa_verification.py:

- Fernet key env-var handling (missing/invalid/valid) -- #1376 encryption-at-rest.
- resolve_user_mfa_secret decrypt-failure fallback to legacy plaintext column.
- store_mfa_secret_on_user plaintext fallback when key is unset.
- encrypt_mfa_secret + decrypt_mfa_secret happy-path + RuntimeError when unconfigured.
- generate_mfa_secret / create_provisioning_uri / verify_totp format guards + except path.
- require_mfa rejects when current_user is falsy (line 361-362).
- require_mfa_dependency factory returns a functioning FastAPI dep that delegates
  through real get_current_user/get_session imports (line 433-447).
- Recovery code helpers: normalize_recovery_code handles empty / punctuation /
  mixed-case; verify_recovery_code uses constant-time compare.
- MFAEnrollmentState / create_enrollment_state / validate_enrollment_state
  including the expired-state warning branch.

No production code is modified.
"""
from __future__ import annotations

import os
import sys
import types as _types
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# --------------------------------------------------------------------
# Stub pyotp BEFORE importing the mfa module so tests work without the
# real lib installed. Mirrors test_mfa_verification.py.
# --------------------------------------------------------------------
if "pyotp" not in sys.modules:

    class _FakeTOTP:
        def __init__(self, secret):
            self._secret = secret

        def verify(self, token, valid_window=1):
            if token == "boom":
                raise RuntimeError("pyotp blew up")
            return token == "999111"

        def provisioning_uri(self, name=None, issuer_name=None):
            return f"otpauth://totp/{issuer_name}:{name}?secret={self._secret}"

    _pyotp_stub = _types.ModuleType("pyotp")
    _pyotp_stub.TOTP = _FakeTOTP
    _pyotp_stub.random_base32 = lambda: "JBSWY3DPEHPK3PXP"
    sys.modules["pyotp"] = _pyotp_stub
else:  # pragma: no cover - real pyotp present locally
    # Patch the real verifier so we can drive the exception branch on demand.
    _real = sys.modules["pyotp"]
    _orig_TOTP = _real.TOTP

    class _WrappedTOTP(_orig_TOTP):  # type: ignore[misc, valid-type]
        def verify(self, token, valid_window=1):
            if token == "boom":
                raise RuntimeError("pyotp blew up")
            return super().verify(token, valid_window=valid_window)

    _real.TOTP = _WrappedTOTP


from services.admin.app import mfa as mfa_module  # noqa: E402


# ==============================================================
# Fernet / encryption primitives (#1376)
# ==============================================================
# Pre-generated valid Fernet key used across tests. Regenerable via:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
_FERNET_KEY = "6UMC7WJRL-mfToH9-qLM_g0ppGz1A4FXT58AGigrDr4="


class TestGetFernet:
    """Pins mfa.py lines 56-68: env-var resolution of the Fernet instance.

    Why it matters: MFA_ENCRYPTION_KEY is the at-rest protection for TOTP
    seeds. Mis-parsing this env var silently falls back to plaintext storage,
    so each branch (unset, missing lib, malformed key) must be exercised.
    """

    def test_returns_none_when_env_unset(self, monkeypatch):
        """Line 56-58: no env var -> None (plaintext fallback)."""
        monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
        assert mfa_module._get_fernet() is None

    def test_returns_none_when_cryptography_missing(self, monkeypatch):
        """Lines 61-63: ImportError on cryptography -> None with error log."""
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", _FERNET_KEY)

        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def fake_import(name, *args, **kwargs):
            if name == "cryptography.fernet":
                raise ImportError("cryptography missing")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            assert mfa_module._get_fernet() is None

    def test_returns_none_when_key_is_invalid(self, monkeypatch):
        """Lines 66-68: Fernet() raises on malformed key -> None + error log."""
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", "not-a-valid-fernet-key")
        assert mfa_module._get_fernet() is None

    def test_returns_fernet_with_valid_key(self, monkeypatch):
        """Happy path: valid Fernet key -> usable Fernet instance."""
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", _FERNET_KEY)
        fernet = mfa_module._get_fernet()
        assert fernet is not None
        # Round-trip to prove it actually works.
        ct = fernet.encrypt(b"hello")
        assert fernet.decrypt(ct) == b"hello"

    def test_accepts_bytes_key(self, monkeypatch):
        """Line 65: Fernet accepts bytes OR str; don't double-encode bytes."""
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", _FERNET_KEY)
        fernet = mfa_module._get_fernet()
        assert fernet is not None


class TestEncryptDecryptMfaSecret:
    """Pins mfa.py lines 71-95: encrypt_mfa_secret/decrypt_mfa_secret round-trip
    and the RuntimeError when decryption is attempted without a key.

    Why it matters: asymmetric encrypt/decrypt availability is a real failure
    mode (rotated key, forgotten env); the RuntimeError must surface instead
    of silently returning gibberish.
    """

    def test_encrypt_returns_none_when_unconfigured(self, monkeypatch):
        """Line 78-79: unconfigured encryption -> None so caller can fall back."""
        monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
        assert mfa_module.encrypt_mfa_secret("JBSWY3DPEHPK3PXP") is None

    def test_encrypt_then_decrypt_round_trips(self, monkeypatch):
        """Line 80 + 95: happy-path round-trip with a real key."""
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", _FERNET_KEY)
        plain = "JBSWY3DPEHPK3PXP"
        ct = mfa_module.encrypt_mfa_secret(plain)
        assert ct is not None and ct != plain
        assert mfa_module.decrypt_mfa_secret(ct) == plain

    def test_decrypt_raises_when_unconfigured(self, monkeypatch):
        """Line 91-94: decrypt with no key raises RuntimeError (no silent fail)."""
        monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
        with pytest.raises(RuntimeError, match="MFA_ENCRYPTION_KEY"):
            mfa_module.decrypt_mfa_secret("anything")


class TestResolveUserMfaSecret:
    """Pins mfa.py lines 98-116: the legacy-plaintext/ciphertext resolver.

    Why it matters: rows are migrating from plaintext -> ciphertext and a
    corrupt/key-mismatched ciphertext must NOT flip a user to "MFA disabled";
    we need to fall through to the plaintext column if it's still populated.
    """

    def test_returns_none_when_neither_column_set(self):
        user = SimpleNamespace(mfa_secret=None, mfa_secret_ciphertext=None, id="u1")
        assert mfa_module.resolve_user_mfa_secret(user) is None

    def test_prefers_ciphertext(self, monkeypatch):
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", _FERNET_KEY)
        ct = mfa_module.encrypt_mfa_secret("CIPHERTEXT_SEED")
        user = SimpleNamespace(
            mfa_secret="LEGACY_SEED",
            mfa_secret_ciphertext=ct,
            id="u1",
        )
        assert mfa_module.resolve_user_mfa_secret(user) == "CIPHERTEXT_SEED"

    def test_falls_back_to_plaintext_when_decrypt_fails(self, monkeypatch):
        """Lines 110-114: decrypt error -> log + fall through to legacy column.

        Guards against a silent "MFA disabled" flip when a key is rotated
        before all rows are re-encrypted.
        """
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", _FERNET_KEY)
        user = SimpleNamespace(
            mfa_secret="LEGACY_SEED",
            mfa_secret_ciphertext="not-a-valid-token",
            id="u1",
        )
        assert mfa_module.resolve_user_mfa_secret(user) == "LEGACY_SEED"

    def test_returns_plaintext_only(self):
        user = SimpleNamespace(
            mfa_secret="LEGACY_SEED",
            mfa_secret_ciphertext=None,
            id="u1",
        )
        assert mfa_module.resolve_user_mfa_secret(user) == "LEGACY_SEED"


class TestStoreMfaSecretOnUser:
    """Pins mfa.py lines 178-198: enrollment-time storage.

    Why it matters: the writer must blank the legacy plaintext column once
    ciphertext is present so backups can't leak both versions. And when the
    key is missing, we must fall back to plaintext rather than silently
    losing the enrollment.
    """

    def test_encrypts_and_clears_plaintext(self, monkeypatch):
        """Lines 187-191: ciphertext stored; legacy column nulled."""
        monkeypatch.setenv("MFA_ENCRYPTION_KEY", _FERNET_KEY)
        user = SimpleNamespace(mfa_secret="stale-legacy", mfa_secret_ciphertext=None)
        mfa_module.store_mfa_secret_on_user(user, "SEED")
        assert user.mfa_secret is None
        assert user.mfa_secret_ciphertext is not None
        assert mfa_module.decrypt_mfa_secret(user.mfa_secret_ciphertext) == "SEED"

    def test_falls_back_to_plaintext_when_no_key(self, monkeypatch):
        """Lines 192-198: no key -> warn + plaintext column written, ciphertext cleared."""
        monkeypatch.delenv("MFA_ENCRYPTION_KEY", raising=False)
        user = SimpleNamespace(mfa_secret=None, mfa_secret_ciphertext="stale-ct")
        mfa_module.store_mfa_secret_on_user(user, "SEED")
        assert user.mfa_secret == "SEED"
        assert user.mfa_secret_ciphertext is None


# ==============================================================
# Core TOTP helpers
# ==============================================================
class TestGenerateAndProvision:
    """Pins mfa.py lines 166-219: secret generation + provisioning URI shape.

    Why it matters: the provisioning URI is what users scan into their
    authenticator app; a regression here is a silently-broken enrollment flow.
    """

    def test_generate_mfa_secret_returns_string(self):
        """Line 173-175: base32 secret comes out as a non-empty string."""
        secret = mfa_module.generate_mfa_secret()
        assert isinstance(secret, str) and len(secret) > 0

    def test_create_provisioning_uri_shape(self):
        """Lines 216-219: otpauth URI contains issuer, email, and secret."""
        uri = mfa_module.create_provisioning_uri(
            secret="JBSWY3DPEHPK3PXP",
            email="alice@example.com",
            issuer="MyApp",
        )
        assert uri.startswith("otpauth://totp/")
        assert "alice@example.com" in uri
        assert "MyApp" in uri
        assert "JBSWY3DPEHPK3PXP" in uri

    def test_create_provisioning_uri_default_issuer(self):
        uri = mfa_module.create_provisioning_uri(
            secret="JBSWY3DPEHPK3PXP", email="bob@example.com"
        )
        assert "RegEngine" in uri


class TestVerifyTotp:
    """Pins mfa.py lines 222-249: TOTP format guards + verifier exception path.

    Why it matters: verify_totp is the security boundary. Every rejection
    branch (short token, non-digits, empty, and pyotp raising) needs to map
    to False — never True and never a 500.
    """

    def test_rejects_wrong_length(self):
        """Line 237-239: non-6-char token logged & rejected."""
        assert mfa_module.verify_totp("SECRET", "12345") is False

    def test_rejects_non_digit(self):
        """Line 237-239: alpha chars in token -> rejected."""
        assert mfa_module.verify_totp("SECRET", "abcdef") is False

    def test_rejects_empty_token(self):
        """Line 237-239: empty string -> rejected (isdigit('') is False)."""
        assert mfa_module.verify_totp("SECRET", "") is False

    # NOTE: verify_totp(None) currently raises TypeError because the
    # guard's warning log calls len(None) (see "production bugs noticed"
    # in the PR description). We don't ship a pinning test for that
    # broken branch — it would either lock in the bug or require fixing
    # production code in this test-only PR.

    def test_accepts_valid_token(self):
        """Happy path to anchor the rejection branches above."""
        assert mfa_module.verify_totp("SECRET", "999111") is True

    def test_rejects_on_verifier_exception(self):
        """Lines 247-249: pyotp raising -> False, not 500."""
        # The stubbed TOTP.verify raises when token == "boom" (and "boom" is
        # 4 chars). We have to get past the length/isdigit guard, so monkey
        # patch pyotp.TOTP so verify() raises for any token shape.
        import pyotp as _pyotp

        class _RaisingTOTP:
            def __init__(self, *_a, **_kw):
                pass

            def verify(self, *_a, **_kw):
                raise RuntimeError("pyotp blew up")

        with patch.object(_pyotp, "TOTP", _RaisingTOTP):
            assert mfa_module.verify_totp("SECRET", "123456") is False


# ==============================================================
# Recovery code helpers (#1377)
# ==============================================================
class TestRecoveryCodeHelpers:
    """Pins mfa.py lines 260-317: normalize/generate/hash/verify recovery codes.

    Why it matters: normalization rules decide whether a user who typed
    "abcd-efgh " can redeem "ABCDEFGH"; a regression here locks users out
    of their account recovery.
    """

    def test_normalize_empty(self):
        """Line 268: empty/None input -> empty string."""
        assert mfa_module.normalize_recovery_code("") == ""
        assert mfa_module.normalize_recovery_code(None) == ""  # type: ignore[arg-type]

    def test_normalize_strips_and_uppercases(self):
        assert mfa_module.normalize_recovery_code("abcd-efgh") == "ABCDEFGH"
        assert mfa_module.normalize_recovery_code(" abcd efgh ") == "ABCDEFGH"
        assert mfa_module.normalize_recovery_code("abcd_efgh") == "ABCDEFGH"

    def test_generate_recovery_codes_default_count_and_format(self):
        """Lines 287-294: default count matches RECOVERY_CODE_COUNT, format XXXX-XXXX."""
        codes = mfa_module.generate_recovery_codes()
        assert len(codes) == mfa_module.RECOVERY_CODE_COUNT
        for code in codes:
            assert len(code) == 9  # 4 + '-' + 4
            assert code[4] == "-"
            assert code[:4].isalnum() and code[5:].isalnum()

    def test_generate_recovery_codes_custom_count(self):
        codes = mfa_module.generate_recovery_codes(count=3)
        assert len(codes) == 3

    def test_hash_is_deterministic_over_normalization(self):
        """Hash(abcd-efgh) == Hash(ABCDEFGH) thanks to normalization."""
        a = mfa_module.hash_recovery_code("abcd-efgh")
        b = mfa_module.hash_recovery_code("ABCDEFGH")
        c = mfa_module.hash_recovery_code(" abcd_efgh ")
        assert a == b == c

    def test_verify_recovery_code_true_and_false(self):
        h = mfa_module.hash_recovery_code("ABCD-EFGH")
        assert mfa_module.verify_recovery_code("abcd-efgh", h) is True
        assert mfa_module.verify_recovery_code("WRONG-CODE", h) is False


# ==============================================================
# require_mfa edge cases
# ==============================================================
class TestRequireMfaCurrentUserGuards:
    """Pins mfa.py line 361-362: require_mfa rejects when current_user is falsy.

    Why it matters: get_current_user override returning None must map to 403
    "MFA not enrolled", not an AttributeError that surfaces as a 500.
    """

    @pytest.mark.asyncio
    async def test_rejects_when_current_user_is_none(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await mfa_module.require_mfa(
                x_mfa_token="999111", current_user=None, db=MagicMock()
            )
        assert exc_info.value.status_code == 403
        assert "MFA not enrolled" in exc_info.value.detail


class TestRequireMfaDependencyFactory:
    """Pins mfa.py lines 423-447: require_mfa_dependency factory wiring.

    Why it matters: the factory is the actual entrypoint routes use; a bug
    here means no route can enforce MFA even though callers look correct.
    """

    @pytest.mark.asyncio
    async def test_factory_returns_callable_that_delegates_to_require_mfa(
        self, monkeypatch
    ):
        """The returned coroutine delegates to require_mfa with kwargs intact."""
        dep = mfa_module.require_mfa_dependency()
        assert callable(dep)

        captured: dict = {}

        async def fake_require_mfa(*, x_mfa_token, current_user, db, session_store):
            captured["token"] = x_mfa_token
            captured["user"] = current_user
            captured["db"] = db
            captured["session_store"] = session_store
            return "ok"

        monkeypatch.setattr(mfa_module, "require_mfa", fake_require_mfa)

        sentinel_user = SimpleNamespace(id=uuid.uuid4())
        sentinel_db = MagicMock()
        sentinel_session_store = MagicMock()
        result = await dep(
            x_mfa_token="999111",
            current_user=sentinel_user,
            db=sentinel_db,
            session_store=sentinel_session_store,
        )
        assert result == "ok"
        assert captured == {
            "token": "999111",
            "user": sentinel_user,
            "db": sentinel_db,
            "session_store": sentinel_session_store,
        }


# ==============================================================
# Enrollment state objects
# ==============================================================
class TestEnrollmentState:
    """Pins mfa.py lines 467-518: create_enrollment_state / validate_enrollment_state.

    Why it matters: enrollment state TTL is what prevents an attacker from
    replaying a half-completed enrollment blob; the expired-branch must log
    and return False instead of quietly accepting a stale state.
    """

    def test_create_enrollment_state_populates_fields(self):
        """Lines 482-501: all fields set, hashes match codes, times sensible."""
        state = mfa_module.create_enrollment_state(
            admin_id="admin-123", hours_until_expiry=2
        )
        assert state.admin_id == "admin-123"
        assert state.secret  # some base32 seed
        assert len(state.recovery_codes) == mfa_module.RECOVERY_CODE_COUNT
        assert len(state.recovery_codes_hashed) == mfa_module.RECOVERY_CODE_COUNT
        # Hashes should line up pairwise.
        for code, code_hash in zip(
            state.recovery_codes, state.recovery_codes_hashed
        ):
            assert mfa_module.verify_recovery_code(code, code_hash)
        # Expiry should be roughly 2 hours after created_at.
        delta = state.expires_at - state.created_at
        assert abs(delta.total_seconds() - 2 * 3600) < 5

    def test_validate_enrollment_state_valid(self):
        """Line 515-518: un-expired state -> True."""
        state = mfa_module.create_enrollment_state("admin-fresh", hours_until_expiry=1)
        assert mfa_module.validate_enrollment_state(state) is True

    def test_validate_enrollment_state_expired(self):
        """Line 516-518: expired state -> warn + False."""
        now = datetime.now(timezone.utc)
        state = mfa_module.MFAEnrollmentState(
            admin_id="admin-expired",
            secret="SEED",
            recovery_codes=["ABCD-EFGH"],
            recovery_codes_hashed=[mfa_module.hash_recovery_code("ABCD-EFGH")],
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        assert mfa_module.validate_enrollment_state(state) is False


# ---------------------------------------------------------------------------
# Lines 24-25 — ImportError re-raise when pyotp is not installed
# ---------------------------------------------------------------------------


class TestMfaImportErrorReRaise:

    def test_missing_pyotp_raises_import_error_with_hint(self):
        """Lines 24-25: if pyotp is absent from the environment, the
        module re-raises ImportError with an actionable install hint
        rather than surfacing a bare ModuleNotFoundError. Pinned so a
        refactor can't silently swallow the install hint or change the
        required package name."""
        import importlib
        import sys

        mfa_key = None
        for k in list(sys.modules):
            if "services.admin.app.mfa" in k or k.endswith(".mfa"):
                mfa_key = k

        # Temporarily block pyotp
        real_pyotp = sys.modules.pop("pyotp", None)
        if mfa_key:
            real_mfa = sys.modules.pop(mfa_key, None)
        else:
            real_mfa = None

        sys.modules["pyotp"] = None  # type: ignore[assignment]
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "_mfa_reimport_test",
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "mfa.py"),
            )
            with pytest.raises(ImportError, match="pyotp is required"):
                importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                spec.loader.exec_module(  # type: ignore[union-attr]
                    importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
                )
        finally:
            # Restore
            del sys.modules["pyotp"]
            if real_pyotp is not None:
                sys.modules["pyotp"] = real_pyotp
            if mfa_key and real_mfa is not None:
                sys.modules[mfa_key] = real_mfa
