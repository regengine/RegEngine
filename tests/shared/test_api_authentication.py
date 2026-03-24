"""
Tests for SEC-028: API Authentication.

Tests cover:
- API key authentication
- JWT token authentication
- Basic authentication
- Token refresh
- Scope validation
- Authentication service
"""

import pytest
import time
import base64

from shared.api_authentication import (
    # Enums
    AuthMethod,
    TokenType,
    KeyStatus,
    # Exceptions
    AuthenticationError,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenInvalidError,
    InsufficientScopeError,
    # Data classes
    APIKey,
    Token,
    AuthResult,
    TokenPair,
    # Classes
    APIKeyAuthenticator,
    JWTAuthenticator,
    BasicAuthenticator,
    AuthenticationService,
    # Convenience functions
    get_auth_service,
    authenticate,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def api_key_auth():
    """Create API key authenticator."""
    return APIKeyAuthenticator()


@pytest.fixture
def jwt_auth():
    """Create JWT authenticator."""
    return JWTAuthenticator(
        secret_key="test-secret-key-12345",
        access_token_ttl=3600,
        refresh_token_ttl=86400,
    )


@pytest.fixture
def service():
    """Create authentication service."""
    return AuthenticationService(jwt_secret="test-secret")


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_auth_methods(self):
        """Should have expected auth methods."""
        assert AuthMethod.API_KEY == "api_key"
        assert AuthMethod.JWT == "jwt"
        assert AuthMethod.BEARER == "bearer"
    
    def test_token_types(self):
        """Should have expected token types."""
        assert TokenType.ACCESS == "access"
        assert TokenType.REFRESH == "refresh"
    
    def test_key_statuses(self):
        """Should have expected key statuses."""
        assert KeyStatus.ACTIVE == "active"
        assert KeyStatus.REVOKED == "revoked"


# =============================================================================
# Test: Data Classes
# =============================================================================

class TestDataClasses:
    """Test data class functionality."""
    
    def test_api_key_validity(self):
        """Should check key validity."""
        from datetime import datetime, timezone, timedelta
        
        key = APIKey(
            key_id="test",
            key_hash="hash",
            name="Test Key",
            owner_id="user1",
            status=KeyStatus.ACTIVE,
        )
        
        assert key.is_valid() is True
        
        # Revoked key
        key.status = KeyStatus.REVOKED
        assert key.is_valid() is False
    
    def test_token_expiration(self):
        """Should track token expiration."""
        from datetime import datetime, timezone, timedelta
        
        token = Token(
            value="test",
            token_type=TokenType.ACCESS,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        
        assert token.is_expired is True
    
    def test_token_ttl(self):
        """Should calculate TTL."""
        from datetime import datetime, timezone, timedelta
        
        token = Token(
            value="test",
            token_type=TokenType.ACCESS,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=100),
        )
        
        assert 95 <= token.ttl <= 100
    
    def test_auth_result_to_dict(self):
        """Should convert to dictionary."""
        result = AuthResult(
            authenticated=True,
            subject="user1",
            method=AuthMethod.JWT,
            scopes={"read", "write"},
        )
        
        data = result.to_dict()
        
        assert data["authenticated"] is True
        assert data["subject"] == "user1"
        assert "read" in data["scopes"]


# =============================================================================
# Test: API Key Authenticator
# =============================================================================

class TestAPIKeyAuthenticator:
    """Test APIKeyAuthenticator."""
    
    def test_generate_key(self, api_key_auth):
        """Should generate API key."""
        raw_key, key = api_key_auth.generate_key(
            name="Test Key",
            owner_id="user1",
            scopes={"read"},
        )
        
        assert raw_key.startswith("rk_")
        assert key.name == "Test Key"
        assert key.owner_id == "user1"
        assert "read" in key.scopes
    
    def test_authenticate_valid_key(self, api_key_auth):
        """Should authenticate with valid key."""
        raw_key, _ = api_key_auth.generate_key(
            name="Test",
            owner_id="user1",
        )
        
        result = api_key_auth.authenticate(raw_key)
        
        assert result.authenticated is True
        assert result.subject == "user1"
        assert result.method == AuthMethod.API_KEY
    
    def test_authenticate_invalid_key(self, api_key_auth):
        """Should reject invalid key."""
        result = api_key_auth.authenticate("invalid-key")
        
        assert result.authenticated is False
        assert "invalid" in result.error.lower()
    
    def test_authenticate_revoked_key(self, api_key_auth):
        """Should reject revoked key."""
        raw_key, key = api_key_auth.generate_key(
            name="Test",
            owner_id="user1",
        )
        
        api_key_auth.revoke_key(key.key_id)
        
        result = api_key_auth.authenticate(raw_key)
        
        assert result.authenticated is False
        assert "revoked" in result.error.lower()
    
    def test_scope_validation(self, api_key_auth):
        """Should validate required scopes."""
        raw_key, _ = api_key_auth.generate_key(
            name="Test",
            owner_id="user1",
            scopes={"read"},
        )
        
        # Should pass with matching scope
        result = api_key_auth.authenticate(raw_key, {"read"})
        assert result.authenticated is True
        
        # Should fail with missing scope
        result = api_key_auth.authenticate(raw_key, {"write"})
        assert result.authenticated is False
    
    def test_list_keys(self, api_key_auth):
        """Should list keys for owner."""
        api_key_auth.generate_key("Key1", "user1")
        api_key_auth.generate_key("Key2", "user1")
        api_key_auth.generate_key("Key3", "user2")
        
        keys = api_key_auth.list_keys("user1")
        
        assert len(keys) == 2


# =============================================================================
# Test: JWT Authenticator
# =============================================================================

class TestJWTAuthenticator:
    """Test JWTAuthenticator."""
    
    def test_create_token(self, jwt_auth):
        """Should create JWT token."""
        token = jwt_auth.create_token(
            subject="user1",
            scopes={"read", "write"},
        )
        
        assert token.value is not None
        assert token.subject == "user1"
        assert "read" in token.scopes
    
    def test_verify_valid_token(self, jwt_auth):
        """Should verify valid token."""
        token = jwt_auth.create_token(subject="user1")
        
        result = jwt_auth.verify_token(token.value)
        
        assert result.authenticated is True
        assert result.subject == "user1"
        assert result.method == AuthMethod.JWT
    
    def test_verify_invalid_token(self, jwt_auth):
        """Should reject invalid token."""
        result = jwt_auth.verify_token("invalid.token.here")
        
        assert result.authenticated is False
    
    def test_verify_tampered_token(self, jwt_auth):
        """Should reject tampered token."""
        token = jwt_auth.create_token(subject="user1")
        
        # Tamper with token
        parts = token.value.split(".")
        tampered = f"{parts[0]}.{parts[1]}.invalid_signature"
        
        result = jwt_auth.verify_token(tampered)
        
        assert result.authenticated is False
        assert "signature" in result.error.lower()
    
    def test_verify_expired_token(self, jwt_auth):
        """Should reject expired token."""
        token = jwt_auth.create_token(
            subject="user1",
            ttl=1,  # 1 second
        )
        
        time.sleep(2)
        
        result = jwt_auth.verify_token(token.value)
        
        assert result.authenticated is False
        assert "expired" in result.error.lower()
    
    def test_create_token_pair(self, jwt_auth):
        """Should create token pair."""
        pair = jwt_auth.create_token_pair(
            subject="user1",
            scopes={"read"},
        )
        
        assert pair.access_token.token_type == TokenType.ACCESS
        assert pair.refresh_token.token_type == TokenType.REFRESH
    
    def test_refresh_tokens(self, jwt_auth):
        """Should refresh tokens."""
        pair = jwt_auth.create_token_pair(subject="user1")
        
        new_pair = jwt_auth.refresh_tokens(pair.refresh_token.value)
        
        assert new_pair is not None
        assert new_pair.access_token.value != pair.access_token.value
    
    def test_refresh_with_access_token_fails(self, jwt_auth):
        """Should not refresh with access token."""
        pair = jwt_auth.create_token_pair(subject="user1")
        
        new_pair = jwt_auth.refresh_tokens(pair.access_token.value)
        
        assert new_pair is None
    
    def test_revoke_token(self, jwt_auth):
        """Should revoke token."""
        token = jwt_auth.create_token(subject="user1")
        
        # Verify works before revocation
        result = jwt_auth.verify_token(token.value)
        assert result.authenticated is True
        
        # Revoke
        jwt_auth.revoke_token(token.value)
        
        # Should fail after revocation
        result = jwt_auth.verify_token(token.value)
        assert result.authenticated is False
    
    def test_scope_validation(self, jwt_auth):
        """Should validate required scopes."""
        token = jwt_auth.create_token(
            subject="user1",
            scopes={"read"},
        )
        
        # Should pass with matching scope
        result = jwt_auth.verify_token(token.value, {"read"})
        assert result.authenticated is True
        
        # Should fail with missing scope
        result = jwt_auth.verify_token(token.value, {"write"})
        assert result.authenticated is False


# =============================================================================
# Test: Basic Authenticator
# =============================================================================

class TestBasicAuthenticator:
    """Test BasicAuthenticator."""
    
    def test_authenticate_valid(self):
        """Should authenticate with valid credentials."""
        def verify(username, password):
            if username == "admin" and password == "secret":
                return {"id": "user1", "role": "admin"}
            return None
        
        auth = BasicAuthenticator(verify)
        
        # Encode credentials
        creds = base64.b64encode(b"admin:secret").decode()
        header = f"Basic {creds}"
        
        result = auth.authenticate(header)
        
        assert result.authenticated is True
        assert result.subject == "user1"
    
    def test_authenticate_invalid(self):
        """Should reject invalid credentials."""
        def verify(username, password):
            return None
        
        auth = BasicAuthenticator(verify)
        
        creds = base64.b64encode(b"wrong:creds").decode()
        header = f"Basic {creds}"
        
        result = auth.authenticate(header)
        
        assert result.authenticated is False
    
    def test_invalid_header_format(self):
        """Should reject invalid header format."""
        auth = BasicAuthenticator(lambda u, p: None)
        
        result = auth.authenticate("Invalid header")
        
        assert result.authenticated is False


# =============================================================================
# Test: Authentication Service
# =============================================================================

class TestAuthenticationService:
    """Test AuthenticationService."""
    
    def test_authenticate_with_api_key(self, service):
        """Should authenticate with API key."""
        raw_key, _ = service.create_api_key(
            name="Test",
            owner_id="user1",
        )
        
        result = service.authenticate_request(api_key=raw_key)
        
        assert result.authenticated is True
        assert result.method == AuthMethod.API_KEY
    
    def test_authenticate_with_bearer_token(self, service):
        """Should authenticate with bearer token."""
        pair = service.create_tokens(subject="user1")
        
        result = service.authenticate_request(
            authorization=f"Bearer {pair.access_token.value}",
        )
        
        assert result.authenticated is True
        assert result.method == AuthMethod.JWT
    
    def test_authenticate_with_basic_auth(self, service):
        """Should authenticate with basic auth."""
        service.set_basic_auth_verifier(
            lambda u, p: {"id": "user1"} if u == "admin" and p == "pass" else None
        )
        
        creds = base64.b64encode(b"admin:pass").decode()
        
        result = service.authenticate_request(
            authorization=f"Basic {creds}",
        )
        
        assert result.authenticated is True
        assert result.method == AuthMethod.BASIC
    
    def test_authenticate_no_credentials(self, service):
        """Should fail without credentials."""
        result = service.authenticate_request()
        
        assert result.authenticated is False
    
    def test_refresh_tokens(self, service):
        """Should refresh tokens."""
        pair = service.create_tokens(subject="user1")
        
        new_pair = service.refresh_tokens(pair.refresh_token.value)
        
        assert new_pair is not None


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_auth_service(self, monkeypatch):
        """Should return service instance."""
        monkeypatch.setenv("JWT_SECRET", "test-secret-for-unit-tests")
        # Reset singleton so it picks up the env var
        from shared.api_authentication import AuthenticationService
        AuthenticationService._instance = None
        service = get_auth_service()
        assert service is not None
    
    def test_authenticate_function(self):
        """Should authenticate via convenience function."""
        result = authenticate()
        
        assert isinstance(result, AuthResult)
