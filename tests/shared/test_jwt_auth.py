"""
SEC-006: Tests for JWT authentication.
"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


class TestJWTAlgorithmEnum:
    """Test JWT algorithm enumeration."""

    def test_hmac_algorithms_available(self):
        """HMAC algorithms should be available."""
        from shared.jwt_auth import JWTAlgorithm

        assert JWTAlgorithm.HS256.value == "HS256"
        assert JWTAlgorithm.HS384.value == "HS384"
        assert JWTAlgorithm.HS512.value == "HS512"

    def test_rsa_algorithms_available(self):
        """RSA algorithms should be available."""
        from shared.jwt_auth import JWTAlgorithm

        assert JWTAlgorithm.RS256.value == "RS256"
        assert JWTAlgorithm.RS384.value == "RS384"
        assert JWTAlgorithm.RS512.value == "RS512"

    def test_ecdsa_algorithms_available(self):
        """ECDSA algorithms should be available."""
        from shared.jwt_auth import JWTAlgorithm

        assert JWTAlgorithm.ES256.value == "ES256"
        assert JWTAlgorithm.ES384.value == "ES384"
        assert JWTAlgorithm.ES512.value == "ES512"


class TestTokenTypeEnum:
    """Test token type enumeration."""

    def test_access_token_type(self):
        """ACCESS token type should exist."""
        from shared.jwt_auth import TokenType

        assert TokenType.ACCESS.value == "access"

    def test_refresh_token_type(self):
        """REFRESH token type should exist."""
        from shared.jwt_auth import TokenType

        assert TokenType.REFRESH.value == "refresh"

    def test_api_key_token_type(self):
        """API_KEY token type should exist."""
        from shared.jwt_auth import TokenType

        assert TokenType.API_KEY.value == "api_key"


class TestTokenPayload:
    """Test TokenPayload model."""

    def test_required_fields(self):
        """TokenPayload should require standard claims."""
        from shared.jwt_auth import TokenPayload, TokenType

        now = int(time.time())
        payload = TokenPayload(
            sub="user-123",
            iat=now,
            exp=now + 3600,
            jti="unique-id",
        )

        assert payload.sub == "user-123"
        assert payload.iat == now
        assert payload.exp == now + 3600
        assert payload.jti == "unique-id"

    def test_default_token_type_is_access(self):
        """Default token type should be ACCESS."""
        from shared.jwt_auth import TokenPayload, TokenType

        now = int(time.time())
        payload = TokenPayload(
            sub="user-123",
            iat=now,
            exp=now + 3600,
            jti="unique-id",
        )

        assert payload.type == TokenType.ACCESS

    def test_is_expired_property(self):
        """is_expired should return True for expired tokens."""
        from shared.jwt_auth import TokenPayload

        past = int(time.time()) - 3600
        payload = TokenPayload(
            sub="user-123",
            iat=past - 3600,
            exp=past,  # Expired
            jti="unique-id",
        )

        assert payload.is_expired is True

    def test_is_not_expired_property(self):
        """is_expired should return False for valid tokens."""
        from shared.jwt_auth import TokenPayload

        now = int(time.time())
        payload = TokenPayload(
            sub="user-123",
            iat=now,
            exp=now + 3600,  # Future
            jti="unique-id",
        )

        assert payload.is_expired is False

    def test_expires_at_property(self):
        """expires_at should return datetime."""
        from shared.jwt_auth import TokenPayload

        now = int(time.time())
        exp = now + 3600
        payload = TokenPayload(
            sub="user-123",
            iat=now,
            exp=exp,
            jti="unique-id",
        )

        assert isinstance(payload.expires_at, datetime)
        assert payload.expires_at.timestamp() == exp

    def test_custom_claims(self):
        """Should support custom claims."""
        from shared.jwt_auth import TokenPayload

        now = int(time.time())
        payload = TokenPayload(
            sub="user-123",
            iat=now,
            exp=now + 3600,
            jti="unique-id",
            tenant_id="tenant-456",
            roles=["admin", "user"],
            scopes=["read:all", "write:all"],
            extra={"custom_field": "custom_value"},
        )

        assert payload.tenant_id == "tenant-456"
        assert "admin" in payload.roles
        assert "read:all" in payload.scopes
        assert payload.extra["custom_field"] == "custom_value"


class TestTokenResponse:
    """Test TokenResponse model."""

    def test_required_fields(self):
        """TokenResponse should have required fields."""
        from shared.jwt_auth import TokenResponse

        response = TokenResponse(
            access_token="eyJ...",
            expires_in=900,
            expires_at=datetime.now(timezone.utc),
        )

        assert response.access_token == "eyJ..."
        assert response.expires_in == 900
        assert response.token_type == "Bearer"

    def test_optional_refresh_token(self):
        """refresh_token should be optional."""
        from shared.jwt_auth import TokenResponse

        response = TokenResponse(
            access_token="eyJ...",
            refresh_token="eyJ.refresh...",
            expires_in=900,
            expires_at=datetime.now(timezone.utc),
        )

        assert response.refresh_token == "eyJ.refresh..."


class TestJWTManagerInit:
    """Test JWTManager initialization."""

    def test_requires_secret_for_hmac(self):
        """Should require secret_key for HMAC algorithms."""
        from shared.jwt_auth import JWTManager, JWTAlgorithm

        # Clear env var
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="secret_key is required"):
                JWTManager(algorithm=JWTAlgorithm.HS256)

    def test_accepts_secret_key(self):
        """Should accept secret_key parameter."""
        from shared.jwt_auth import JWTManager

        manager = JWTManager(secret_key="test-secret-key-for-testing")
        assert manager is not None

    def test_uses_env_var_secret(self):
        """Should use JWT_SECRET env var."""
        from shared.jwt_auth import JWTManager

        with patch.dict("os.environ", {"JWT_SECRET": "env-secret-key"}):
            manager = JWTManager()
            assert manager._secret_key == "env-secret-key"

    def test_default_issuer(self):
        """Should use regengine as default issuer."""
        from shared.jwt_auth import JWTManager

        manager = JWTManager(secret_key="test-secret")
        assert manager._issuer == "regengine"

    def test_custom_issuer(self):
        """Should accept custom issuer."""
        from shared.jwt_auth import JWTManager

        manager = JWTManager(secret_key="test-secret", issuer="custom-issuer")
        assert manager._issuer == "custom-issuer"


class TestJWTManagerCreateToken:
    """Test token creation."""

    @pytest.fixture
    def jwt_manager(self):
        """Create a JWT manager for testing."""
        from shared.jwt_auth import JWTManager

        return JWTManager(
            secret_key="test-secret-key-minimum-length-32-chars",
            issuer="test-issuer",
        )

    def test_create_access_token(self, jwt_manager):
        """Should create a valid access token."""
        token = jwt_manager.create_access_token(subject="user-123")

        assert token is not None
        assert isinstance(token, str)
        assert token.count(".") == 2  # JWT format: header.payload.signature

    def test_create_refresh_token(self, jwt_manager):
        """Should create a valid refresh token."""
        token = jwt_manager.create_refresh_token(subject="user-123")

        assert token is not None
        assert isinstance(token, str)

    def test_create_token_pair(self, jwt_manager):
        """Should create both access and refresh tokens."""
        from shared.jwt_auth import TokenResponse

        response = jwt_manager.create_token_pair(
            subject="user-123",
            roles=["admin"],
            scopes=["read:all"],
        )

        assert isinstance(response, TokenResponse)
        assert response.access_token is not None
        assert response.refresh_token is not None
        assert response.token_type == "Bearer"
        assert response.expires_in > 0

    def test_access_token_includes_claims(self, jwt_manager):
        """Access token should include custom claims."""
        token = jwt_manager.create_access_token(
            subject="user-123",
            tenant_id="tenant-456",
            roles=["admin"],
            scopes=["read:all"],
        )

        # Verify by decoding
        payload = jwt_manager.verify_token(token)
        assert payload.sub == "user-123"
        assert payload.tenant_id == "tenant-456"
        assert "admin" in payload.roles
        assert "read:all" in payload.scopes

    def test_token_has_unique_jti(self, jwt_manager):
        """Each token should have a unique JTI."""
        token1 = jwt_manager.create_access_token(subject="user-123")
        token2 = jwt_manager.create_access_token(subject="user-123")

        payload1 = jwt_manager.verify_token(token1)
        payload2 = jwt_manager.verify_token(token2)

        assert payload1.jti != payload2.jti


class TestJWTManagerVerifyToken:
    """Test token verification."""

    @pytest.fixture
    def jwt_manager(self):
        """Create a JWT manager for testing."""
        from shared.jwt_auth import JWTManager

        return JWTManager(
            secret_key="test-secret-key-minimum-length-32-chars",
        )

    def test_verify_valid_token(self, jwt_manager):
        """Should verify a valid token."""
        from shared.jwt_auth import TokenPayload

        token = jwt_manager.create_access_token(subject="user-123")
        payload = jwt_manager.verify_token(token)

        assert isinstance(payload, TokenPayload)
        assert payload.sub == "user-123"

    def test_verify_expired_token_raises(self, jwt_manager):
        """Should raise for expired tokens."""
        from shared.jwt_auth import ExpiredSignatureError

        # Create a token that's already expired
        token = jwt_manager.create_access_token(
            subject="user-123",
            expires_delta=timedelta(seconds=-10),
        )

        with pytest.raises(ExpiredSignatureError):
            jwt_manager.verify_token(token)

    def test_verify_invalid_signature_raises(self, jwt_manager):
        """Should raise for tokens with invalid signature."""
        from shared.jwt_auth import JWTManager, InvalidTokenError

        # Create token with different secret
        other_manager = JWTManager(secret_key="different-secret-key-for-test")
        token = other_manager.create_access_token(subject="user-123")

        with pytest.raises(InvalidTokenError):
            jwt_manager.verify_token(token)

    def test_verify_wrong_token_type_raises(self, jwt_manager):
        """Should raise when token type doesn't match expected."""
        from shared.jwt_auth import TokenType, InvalidTokenError

        refresh_token = jwt_manager.create_refresh_token(subject="user-123")

        with pytest.raises(InvalidTokenError, match="Expected access"):
            jwt_manager.verify_token(refresh_token, expected_type=TokenType.ACCESS)

    def test_verify_revoked_token_raises(self, jwt_manager):
        """Should raise for revoked tokens."""
        from shared.jwt_auth import InvalidTokenError

        token = jwt_manager.create_access_token(subject="user-123")
        jwt_manager.revoke_token(token)

        with pytest.raises(InvalidTokenError, match="revoked"):
            jwt_manager.verify_token(token)


class TestJWTManagerRefresh:
    """Test token refresh flow."""

    @pytest.fixture
    def jwt_manager(self):
        """Create a JWT manager for testing."""
        from shared.jwt_auth import JWTManager

        return JWTManager(
            secret_key="test-secret-key-minimum-length-32-chars",
        )

    def test_refresh_access_token(self, jwt_manager):
        """Should create new access token from refresh token."""
        from shared.jwt_auth import TokenResponse

        # Create initial tokens
        pair = jwt_manager.create_token_pair(subject="user-123")

        # Refresh
        response = jwt_manager.refresh_access_token(pair.refresh_token)

        assert isinstance(response, TokenResponse)
        assert response.access_token is not None
        assert response.access_token != pair.access_token  # New token

    def test_refresh_preserves_subject(self, jwt_manager):
        """Refreshed token should have same subject."""
        pair = jwt_manager.create_token_pair(subject="user-123")
        response = jwt_manager.refresh_access_token(pair.refresh_token)

        new_payload = jwt_manager.verify_token(response.access_token)
        assert new_payload.sub == "user-123"

    def test_refresh_with_access_token_fails(self, jwt_manager):
        """Should not accept access token for refresh."""
        from shared.jwt_auth import InvalidTokenError

        pair = jwt_manager.create_token_pair(subject="user-123")

        with pytest.raises(InvalidTokenError, match="Expected refresh"):
            jwt_manager.refresh_access_token(pair.access_token)


class TestJWTManagerRevocation:
    """Test token revocation."""

    @pytest.fixture
    def jwt_manager(self):
        """Create a JWT manager for testing."""
        from shared.jwt_auth import JWTManager

        return JWTManager(
            secret_key="test-secret-key-minimum-length-32-chars",
        )

    def test_revoke_token(self, jwt_manager):
        """Should add token to blacklist."""
        token = jwt_manager.create_access_token(subject="user-123")

        result = jwt_manager.revoke_token(token)

        assert result is True
        assert jwt_manager.is_revoked(token) is True

    def test_is_revoked_for_non_revoked_token(self, jwt_manager):
        """Should return False for non-revoked tokens."""
        token = jwt_manager.create_access_token(subject="user-123")

        assert jwt_manager.is_revoked(token) is False

    def test_token_hash_stored_not_raw(self, jwt_manager):
        """Should store hash, not raw token."""
        token = jwt_manager.create_access_token(subject="user-123")
        jwt_manager.revoke_token(token)

        # Raw token should not be in blacklist
        assert token not in jwt_manager._blacklist
        # Hash should be in blacklist
        token_hash = jwt_manager._hash_token(token)
        assert token_hash in jwt_manager._blacklist


class TestJWTManagerUtilities:
    """Test utility methods."""

    @pytest.fixture
    def jwt_manager(self):
        """Create a JWT manager for testing."""
        from shared.jwt_auth import JWTManager

        return JWTManager(
            secret_key="test-secret-key-minimum-length-32-chars",
        )

    def test_decode_unverified(self, jwt_manager):
        """Should decode without verification."""
        token = jwt_manager.create_access_token(subject="user-123")

        payload = jwt_manager.decode_token_unverified(token)

        assert payload["sub"] == "user-123"

    def test_get_token_id(self, jwt_manager):
        """Should extract JTI from token."""
        token = jwt_manager.create_access_token(subject="user-123")

        jti = jwt_manager.get_token_id(token)

        assert jti is not None
        assert isinstance(jti, str)

    def test_get_token_id_invalid_token(self, jwt_manager):
        """Should return None for invalid tokens."""
        jti = jwt_manager.get_token_id("invalid-token")

        assert jti is None


class TestSecurityFeatures:
    """Test security-related features."""

    def test_tokens_different_each_call(self):
        """Tokens should be unique even with same params."""
        from shared.jwt_auth import JWTManager

        manager = JWTManager(secret_key="test-secret-key-for-security")
        
        tokens = [
            manager.create_access_token(subject="user-123")
            for _ in range(10)
        ]

        assert len(set(tokens)) == 10  # All unique

    def test_hash_is_consistent(self):
        """Token hash should be deterministic."""
        from shared.jwt_auth import JWTManager

        token = "test-token-value"
        hash1 = JWTManager._hash_token(token)
        hash2 = JWTManager._hash_token(token)

        assert hash1 == hash2

    def test_different_tokens_different_hashes(self):
        """Different tokens should have different hashes."""
        from shared.jwt_auth import JWTManager

        hash1 = JWTManager._hash_token("token1")
        hash2 = JWTManager._hash_token("token2")

        assert hash1 != hash2
