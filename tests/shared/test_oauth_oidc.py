"""
SEC-007: Tests for OAuth 2.0 / OpenID Connect Support.
"""

import time
from unittest.mock import patch

import pytest


class TestOAuthProvider:
    """Test OAuthProvider enum."""

    def test_supported_providers(self):
        """Should define all supported providers."""
        from shared.oauth_oidc import OAuthProvider

        assert OAuthProvider.OKTA.value == "okta"
        assert OAuthProvider.AUTH0.value == "auth0"
        assert OAuthProvider.AZURE_AD.value == "azure_ad"
        assert OAuthProvider.GOOGLE.value == "google"
        assert OAuthProvider.KEYCLOAK.value == "keycloak"
        assert OAuthProvider.CUSTOM.value == "custom"


class TestOAuthConfig:
    """Test OAuthConfig class."""

    def test_create_config(self):
        """Should create config with required fields."""
        from shared.oauth_oidc import OAuthConfig

        config = OAuthConfig(
            client_id="test-client",
            redirect_uri="http://localhost/callback",
            issuer="https://auth.example.com",
        )

        assert config.client_id == "test-client"
        assert config.redirect_uri == "http://localhost/callback"
        assert config.issuer == "https://auth.example.com"
        assert config.use_pkce is True  # Default

    def test_default_scopes(self):
        """Should have default OpenID scopes."""
        from shared.oauth_oidc import OAuthConfig

        config = OAuthConfig(
            client_id="test",
            redirect_uri="http://localhost/callback",
            issuer="https://auth.example.com",
        )

        assert "openid" in config.scopes
        assert "profile" in config.scopes
        assert "email" in config.scopes

    def test_from_env(self):
        """Should create config from environment."""
        from shared.oauth_oidc import OAuthConfig

        env = {
            "OAUTH_CLIENT_ID": "env-client",
            "OAUTH_CLIENT_SECRET": "env-secret",
            "OAUTH_REDIRECT_URI": "http://localhost/callback",
            "OAUTH_ISSUER": "https://auth.example.com",
            "OAUTH_USE_PKCE": "true",
        }

        with patch.dict("os.environ", env, clear=True):
            config = OAuthConfig.from_env()

        assert config.client_id == "env-client"
        assert config.client_secret == "env-secret"
        assert config.issuer == "https://auth.example.com"


class TestPKCEGenerator:
    """Test PKCE code generation."""

    def test_generate_verifier(self):
        """Should generate code verifier of correct length."""
        from shared.oauth_oidc import PKCEGenerator

        verifier = PKCEGenerator.generate_verifier(64)

        assert len(verifier) == 64
        # Should be URL-safe base64
        assert "+" not in verifier
        assert "/" not in verifier

    def test_verifier_uniqueness(self):
        """Each verifier should be unique."""
        from shared.oauth_oidc import PKCEGenerator

        verifiers = [PKCEGenerator.generate_verifier() for _ in range(10)]

        assert len(set(verifiers)) == 10

    def test_verifier_length_validation(self):
        """Should validate verifier length."""
        from shared.oauth_oidc import PKCEGenerator

        with pytest.raises(ValueError, match="43"):
            PKCEGenerator.generate_verifier(10)

        with pytest.raises(ValueError, match="128"):
            PKCEGenerator.generate_verifier(200)

    def test_generate_challenge_s256(self):
        """Should generate S256 challenge."""
        from shared.oauth_oidc import PKCEGenerator

        verifier = "test-verifier-string-that-is-long-enough-for-testing"
        challenge, method = PKCEGenerator.generate_challenge(verifier, "S256")

        assert method == "S256"
        assert challenge != verifier  # Should be hashed
        # Should be URL-safe base64
        assert "+" not in challenge
        assert "/" not in challenge

    def test_generate_challenge_plain(self):
        """Should support plain method (not recommended)."""
        from shared.oauth_oidc import PKCEGenerator

        verifier = "test-verifier"
        challenge, method = PKCEGenerator.generate_challenge(verifier, "plain")

        assert method == "plain"
        assert challenge == verifier

    def test_create_pkce_pair(self):
        """Should create complete PKCE pair."""
        from shared.oauth_oidc import PKCEGenerator

        verifier, challenge, method = PKCEGenerator.create_pkce_pair()

        assert len(verifier) == 64
        assert method == "S256"
        assert challenge != verifier


class TestOAuthTokenResponse:
    """Test OAuth token response model."""

    def test_create_token_response(self):
        """Should create token response."""
        from shared.oauth_oidc import OAuthTokenResponse

        response = OAuthTokenResponse(
            access_token="access-token-value",
            token_type="Bearer",
            expires_in=3600,
            refresh_token="refresh-token-value",
        )

        assert response.access_token == "access-token-value"
        assert response.token_type == "Bearer"
        assert response.expires_in == 3600
        assert not response.is_expired

    def test_expiration_check(self):
        """Should check if token is expired."""
        from shared.oauth_oidc import OAuthTokenResponse

        response = OAuthTokenResponse(
            access_token="test",
            expires_in=-1,  # Already expired
            issued_at=time.time() - 100,
        )

        assert response.is_expired is True

    def test_expires_at_calculation(self):
        """Should calculate expiration timestamp."""
        from shared.oauth_oidc import OAuthTokenResponse

        now = time.time()
        response = OAuthTokenResponse(
            access_token="test",
            expires_in=3600,
            issued_at=now,
        )

        assert response.expires_at == now + 3600


class TestIDTokenClaims:
    """Test OIDC ID token claims."""

    def test_create_claims(self):
        """Should create ID token claims."""
        from shared.oauth_oidc import IDTokenClaims

        now = int(time.time())
        claims = IDTokenClaims(
            iss="https://auth.example.com",
            sub="user-123",
            aud="client-id",
            exp=now + 3600,
            iat=now,
            email="user@example.com",
        )

        assert claims.sub == "user-123"
        assert claims.email == "user@example.com"
        assert not claims.is_expired

    def test_expired_token(self):
        """Should detect expired token."""
        from shared.oauth_oidc import IDTokenClaims

        past = int(time.time()) - 3600
        claims = IDTokenClaims(
            iss="https://auth.example.com",
            sub="user-123",
            aud="client-id",
            exp=past,  # In the past
            iat=past - 3600,
        )

        assert claims.is_expired is True

    def test_validate_audience_string(self):
        """Should validate audience string."""
        from shared.oauth_oidc import IDTokenClaims

        claims = IDTokenClaims(
            iss="https://auth.example.com",
            sub="user-123",
            aud="my-client",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
        )

        assert claims.validate_audience("my-client") is True
        assert claims.validate_audience("other-client") is False

    def test_validate_audience_list(self):
        """Should validate audience list."""
        from shared.oauth_oidc import IDTokenClaims

        claims = IDTokenClaims(
            iss="https://auth.example.com",
            sub="user-123",
            aud=["client-1", "client-2"],
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
        )

        assert claims.validate_audience("client-1") is True
        assert claims.validate_audience("client-2") is True
        assert claims.validate_audience("client-3") is False


class TestAuthorizationState:
    """Test authorization state model."""

    def test_create_state(self):
        """Should create authorization state."""
        from shared.oauth_oidc import AuthorizationState

        state = AuthorizationState(
            state="random-state-value",
            nonce="random-nonce",
            code_verifier="pkce-verifier",
            redirect_uri="http://localhost/callback",
        )

        assert state.state == "random-state-value"
        assert state.nonce == "random-nonce"
        assert not state.is_expired

    def test_state_expiration(self):
        """State should expire after 10 minutes."""
        from shared.oauth_oidc import AuthorizationState

        state = AuthorizationState(
            state="test",
            redirect_uri="http://localhost/callback",
            created_at=time.time() - 700,  # 11+ minutes ago
        )

        assert state.is_expired is True


class TestOAuthClient:
    """Test OAuth client."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        from shared.oauth_oidc import OAuthConfig

        return OAuthConfig(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost/callback",
            issuer="https://auth.example.com",
        )

    @pytest.fixture
    def client(self, config):
        """Create OAuth client."""
        from shared.oauth_oidc import OAuthClient

        return OAuthClient(config)

    def test_requires_client_id(self):
        """Should require client_id."""
        from shared.oauth_oidc import OAuthConfig, OAuthClient

        config = OAuthConfig(
            client_id="",
            redirect_uri="http://localhost/callback",
            issuer="https://auth.example.com",
        )

        with pytest.raises(ValueError, match="client_id"):
            OAuthClient(config)

    def test_requires_redirect_uri(self):
        """Should require redirect_uri."""
        from shared.oauth_oidc import OAuthConfig, OAuthClient

        config = OAuthConfig(
            client_id="test",
            redirect_uri="",
            issuer="https://auth.example.com",
        )

        with pytest.raises(ValueError, match="redirect_uri"):
            OAuthClient(config)

    def test_get_authorization_url(self, client):
        """Should generate authorization URL."""
        auth_url, state = client.get_authorization_url()

        assert "auth.example.com" in auth_url
        assert "client_id=test-client" in auth_url
        assert "response_type=code" in auth_url
        assert "state=" in auth_url

    def test_authorization_url_includes_pkce(self, client):
        """Should include PKCE parameters."""
        auth_url, state = client.get_authorization_url()

        assert "code_challenge=" in auth_url
        assert "code_challenge_method=S256" in auth_url

    def test_authorization_url_includes_nonce(self, client):
        """Should include nonce for OpenID."""
        auth_url, state = client.get_authorization_url()

        assert "nonce=" in auth_url

    def test_validates_callback_state(self, client):
        """Should validate callback state."""
        _, auth_state = client.get_authorization_url()

        # Valid state
        result = client.validate_callback_state(auth_state.state)
        assert result.state == auth_state.state

        # Invalid state
        with pytest.raises(ValueError, match="Invalid state"):
            client.validate_callback_state("unknown-state")

    def test_state_cannot_be_reused(self, client):
        """State should be deleted after validation."""
        _, auth_state = client.get_authorization_url()

        # First validation succeeds
        client.validate_callback_state(auth_state.state)

        # Second validation fails
        with pytest.raises(ValueError, match="Invalid state"):
            client.validate_callback_state(auth_state.state)

    def test_build_token_request(self, client):
        """Should build token request."""
        from shared.oauth_oidc import AuthorizationState

        auth_state = AuthorizationState(
            state="test-state",
            code_verifier="test-verifier",
            redirect_uri="http://localhost/callback",
        )

        body = client.build_token_request("auth-code", auth_state)

        assert body["grant_type"] == "authorization_code"
        assert body["code"] == "auth-code"
        assert body["code_verifier"] == "test-verifier"
        assert body["client_id"] == "test-client"
        assert body["client_secret"] == "test-secret"

    def test_build_refresh_request(self, client):
        """Should build refresh token request."""
        body = client.build_refresh_request("refresh-token")

        assert body["grant_type"] == "refresh_token"
        assert body["refresh_token"] == "refresh-token"
        assert body["client_id"] == "test-client"


class TestIDTokenValidator:
    """Test ID token validator."""

    @pytest.fixture
    def validator(self):
        """Create validator."""
        from shared.oauth_oidc import IDTokenValidator

        return IDTokenValidator(
            issuer="https://auth.example.com",
            client_id="test-client",
        )

    def test_validate_valid_claims(self, validator):
        """Should validate correct claims."""
        from shared.oauth_oidc import IDTokenClaims

        now = int(time.time())
        claims = IDTokenClaims(
            iss="https://auth.example.com",
            sub="user-123",
            aud="test-client",
            exp=now + 3600,
            iat=now,
        )

        assert validator.validate_claims(claims) is True

    def test_reject_wrong_issuer(self, validator):
        """Should reject wrong issuer."""
        from shared.oauth_oidc import IDTokenClaims

        now = int(time.time())
        claims = IDTokenClaims(
            iss="https://other.example.com",  # Wrong issuer
            sub="user-123",
            aud="test-client",
            exp=now + 3600,
            iat=now,
        )

        with pytest.raises(ValueError, match="issuer"):
            validator.validate_claims(claims)

    def test_reject_wrong_audience(self, validator):
        """Should reject wrong audience."""
        from shared.oauth_oidc import IDTokenClaims

        now = int(time.time())
        claims = IDTokenClaims(
            iss="https://auth.example.com",
            sub="user-123",
            aud="other-client",  # Wrong audience
            exp=now + 3600,
            iat=now,
        )

        with pytest.raises(ValueError, match="audience"):
            validator.validate_claims(claims)

    def test_reject_expired(self, validator):
        """Should reject expired tokens."""
        from shared.oauth_oidc import IDTokenClaims

        past = int(time.time()) - 3600
        claims = IDTokenClaims(
            iss="https://auth.example.com",
            sub="user-123",
            aud="test-client",
            exp=past,  # Expired
            iat=past - 3600,
        )

        with pytest.raises(ValueError, match="expired"):
            validator.validate_claims(claims)

    def test_validate_nonce(self, validator):
        """Should validate nonce."""
        from shared.oauth_oidc import IDTokenClaims

        now = int(time.time())
        claims = IDTokenClaims(
            iss="https://auth.example.com",
            sub="user-123",
            aud="test-client",
            exp=now + 3600,
            iat=now,
            nonce="expected-nonce",
        )

        assert validator.validate_claims(claims, nonce="expected-nonce") is True

        with pytest.raises(ValueError, match="Nonce"):
            validator.validate_claims(claims, nonce="different-nonce")


class TestInMemoryAuthStateStore:
    """Test in-memory state store."""

    @pytest.fixture
    def store(self):
        """Create store."""
        from shared.oauth_oidc import InMemoryAuthStateStore

        return InMemoryAuthStateStore()

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, store):
        """Should store and retrieve state."""
        from shared.oauth_oidc import AuthorizationState

        state = AuthorizationState(
            state="test-state",
            redirect_uri="http://localhost/callback",
        )

        await store.store("test-state", state)
        result = await store.retrieve("test-state")

        assert result is not None
        assert result.state == "test-state"

    @pytest.mark.asyncio
    async def test_retrieve_removes_state(self, store):
        """Retrieval should remove the state."""
        from shared.oauth_oidc import AuthorizationState

        state = AuthorizationState(
            state="test",
            redirect_uri="http://localhost/callback",
        )

        await store.store("test", state)
        await store.retrieve("test")
        result = await store.retrieve("test")

        assert result is None

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, store):
        """Should cleanup expired states."""
        from shared.oauth_oidc import AuthorizationState

        # Expired state
        expired = AuthorizationState(
            state="expired",
            redirect_uri="http://localhost/callback",
            created_at=time.time() - 700,
        )

        # Valid state
        valid = AuthorizationState(
            state="valid",
            redirect_uri="http://localhost/callback",
        )

        await store.store("expired", expired)
        await store.store("valid", valid)

        cleaned = await store.cleanup_expired()

        assert cleaned == 1
        assert await store.retrieve("expired") is None
        assert await store.retrieve("valid") is not None


class TestOAuthFlow:
    """Test OAuth flow helper."""

    @pytest.fixture
    def flow(self):
        """Create OAuth flow."""
        from shared.oauth_oidc import OAuthConfig, OAuthFlow

        config = OAuthConfig(
            client_id="test-client",
            client_secret="test-secret",
            redirect_uri="http://localhost/callback",
            issuer="https://auth.example.com",
        )
        return OAuthFlow(config)

    def test_start_authorization(self, flow):
        """Should start authorization flow."""
        auth_url, state = flow.start_authorization()

        assert "auth.example.com" in auth_url
        assert state is not None
        assert len(state) > 0

    def test_handle_callback(self, flow):
        """Should handle callback."""
        _, state = flow.start_authorization()

        token_request = flow.handle_callback(
            code="auth-code",
            state=state,
        )

        assert token_request["code"] == "auth-code"
        assert token_request["grant_type"] == "authorization_code"

    def test_handle_callback_error(self, flow):
        """Should raise on OAuth error."""
        _, state = flow.start_authorization()

        with pytest.raises(ValueError, match="access_denied"):
            flow.handle_callback(
                code="",
                state=state,
                error="access_denied",
                error_description="User denied access",
            )

    def test_token_endpoint(self, flow):
        """Should return token endpoint."""
        assert flow.token_endpoint == "https://auth.example.com/oauth/token"


class TestInMemoryTokenStorage:
    """Test in-memory token storage."""

    @pytest.fixture
    def storage(self):
        """Create storage."""
        from shared.oauth_oidc import InMemoryTokenStorage

        return InMemoryTokenStorage()

    @pytest.mark.asyncio
    async def test_store_and_get_tokens(self, storage):
        """Should store and retrieve tokens."""
        from shared.oauth_oidc import OAuthTokenResponse, OAuthProvider

        tokens = OAuthTokenResponse(
            access_token="test-access-token",
            refresh_token="test-refresh-token",
        )

        await storage.store_tokens("user-1", tokens, OAuthProvider.OKTA)
        result = await storage.get_tokens("user-1", OAuthProvider.OKTA)

        assert result is not None
        assert result.access_token == "test-access-token"

    @pytest.mark.asyncio
    async def test_tokens_isolated_by_provider(self, storage):
        """Tokens should be isolated by provider."""
        from shared.oauth_oidc import OAuthTokenResponse, OAuthProvider

        tokens_okta = OAuthTokenResponse(access_token="okta-token")
        tokens_auth0 = OAuthTokenResponse(access_token="auth0-token")

        await storage.store_tokens("user-1", tokens_okta, OAuthProvider.OKTA)
        await storage.store_tokens("user-1", tokens_auth0, OAuthProvider.AUTH0)

        result_okta = await storage.get_tokens("user-1", OAuthProvider.OKTA)
        result_auth0 = await storage.get_tokens("user-1", OAuthProvider.AUTH0)

        assert result_okta.access_token == "okta-token"
        assert result_auth0.access_token == "auth0-token"

    @pytest.mark.asyncio
    async def test_delete_tokens(self, storage):
        """Should delete tokens."""
        from shared.oauth_oidc import OAuthTokenResponse, OAuthProvider

        tokens = OAuthTokenResponse(access_token="test")
        await storage.store_tokens("user-1", tokens, OAuthProvider.OKTA)

        await storage.delete_tokens("user-1", OAuthProvider.OKTA)
        result = await storage.get_tokens("user-1", OAuthProvider.OKTA)

        assert result is None


class TestSecurityFeatures:
    """Test security features."""

    def test_state_uniqueness(self):
        """Each state should be unique."""
        from shared.oauth_oidc import OAuthConfig, OAuthClient

        config = OAuthConfig(
            client_id="test",
            redirect_uri="http://localhost/callback",
            issuer="https://auth.example.com",
        )
        client = OAuthClient(config)

        states = [client.get_authorization_url()[1].state for _ in range(10)]

        assert len(set(states)) == 10

    def test_pkce_verifier_entropy(self):
        """PKCE verifiers should have high entropy."""
        from shared.oauth_oidc import PKCEGenerator

        verifier = PKCEGenerator.generate_verifier()

        # Check for randomness (no repeating patterns)
        unique_chars = len(set(verifier))
        assert unique_chars > 30  # Should have many unique characters
