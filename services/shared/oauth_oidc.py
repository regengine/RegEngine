"""
SEC-007: OAuth 2.0 / OpenID Connect Support for RegEngine.

This module provides OAuth 2.0 and OIDC integration for:
- External identity provider authentication (Okta, Auth0, Azure AD, etc.)
- Token exchange and validation
- PKCE (Proof Key for Code Exchange) support
- ID token validation

Usage:
    from shared.oauth_oidc import OAuthConfig, OAuthFlow
    
    # Load from environment variables (recommended):
    config = OAuthConfig.from_env()  # Reads OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, etc.
    
    # Or configure explicitly (never hardcode secrets):
    config = OAuthConfig(
        issuer="https://auth.example.com",
        client_id="regengine-app",
        client_secret=os.environ["OAUTH_CLIENT_SECRET"],
        redirect_uri="https://regengine.co/callback",
    )
    
    flow = OAuthFlow(config)
    
    # Get authorization URL
    auth_url, state = client.get_authorization_url()
    
    # Exchange code for tokens
    tokens = await client.exchange_code(code, code_verifier)
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlencode

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("oauth_oidc")


# =============================================================================
# Configuration
# =============================================================================

class OAuthProvider(str, Enum):
    """Supported OAuth/OIDC providers."""
    OKTA = "okta"
    AUTH0 = "auth0"
    AZURE_AD = "azure_ad"
    GOOGLE = "google"
    KEYCLOAK = "keycloak"
    CUSTOM = "custom"


@dataclass
class OAuthConfig:
    """OAuth 2.0 / OIDC configuration."""
    
    # Required settings
    client_id: str
    redirect_uri: str
    
    # Provider settings (choose one approach)
    issuer: Optional[str] = None  # For OIDC discovery
    authorization_endpoint: Optional[str] = None  # Manual config
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    
    # Optional settings
    client_secret: Optional[str] = None  # Not required for public clients with PKCE
    provider: OAuthProvider = OAuthProvider.CUSTOM
    
    # Scopes
    scopes: list[str] = field(default_factory=lambda: ["openid", "profile", "email"])
    
    # Timeouts
    token_timeout: int = 30  # seconds
    
    # PKCE settings
    use_pkce: bool = True  # Always use PKCE when possible
    
    @classmethod
    def from_env(cls, prefix: str = "OAUTH") -> "OAuthConfig":
        """Create config from environment variables."""
        return cls(
            client_id=os.environ.get(f"{prefix}_CLIENT_ID", ""),
            client_secret=os.environ.get(f"{prefix}_CLIENT_SECRET"),
            redirect_uri=os.environ.get(f"{prefix}_REDIRECT_URI", ""),
            issuer=os.environ.get(f"{prefix}_ISSUER"),
            authorization_endpoint=os.environ.get(f"{prefix}_AUTH_ENDPOINT"),
            token_endpoint=os.environ.get(f"{prefix}_TOKEN_ENDPOINT"),
            use_pkce=os.environ.get(f"{prefix}_USE_PKCE", "true").lower() == "true",
        )


# =============================================================================
# PKCE Support
# =============================================================================

class PKCEGenerator:
    """Generate PKCE code verifier and challenge.
    
    PKCE (Proof Key for Code Exchange) prevents authorization code
    interception attacks. Required for public clients, recommended for all.
    """
    
    @staticmethod
    def generate_verifier(length: int = 64) -> str:
        """Generate a cryptographically random code verifier.
        
        Args:
            length: Length of verifier (43-128 characters)
            
        Returns:
            Base64-URL encoded random string
        """
        if not 43 <= length <= 128:
            raise ValueError("Verifier length must be between 43 and 128")
        
        random_bytes = secrets.token_bytes(length)
        # Use URL-safe base64 without padding
        return base64.urlsafe_b64encode(random_bytes).decode().rstrip("=")[:length]
    
    @staticmethod
    def generate_challenge(verifier: str, method: str = "S256") -> tuple[str, str]:
        """Generate code challenge from verifier.
        
        Args:
            verifier: The code verifier
            method: Challenge method (S256 recommended, plain as fallback)
            
        Returns:
            Tuple of (challenge, method)
        """
        if method == "S256":
            # SHA-256 hash, base64-URL encoded
            digest = hashlib.sha256(verifier.encode()).digest()
            challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
            return challenge, "S256"
        elif method == "plain":
            # Not recommended but supported
            return verifier, "plain"
        else:
            raise ValueError(f"Unsupported PKCE method: {method}")
    
    @classmethod
    def create_pkce_pair(cls, length: int = 64) -> tuple[str, str, str]:
        """Create a complete PKCE pair.
        
        Returns:
            Tuple of (verifier, challenge, method)
        """
        verifier = cls.generate_verifier(length)
        challenge, method = cls.generate_challenge(verifier)
        return verifier, challenge, method


# =============================================================================
# Token Models
# =============================================================================

class OAuthTokenResponse(BaseModel):
    """OAuth 2.0 token response."""
    
    access_token: str
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None  # OIDC only
    
    # Computed fields
    issued_at: float = Field(default_factory=time.time)
    
    @property
    def is_expired(self) -> bool:
        """Check if access token is expired."""
        if self.expires_in is None:
            return False
        return time.time() > (self.issued_at + self.expires_in)
    
    @property
    def expires_at(self) -> Optional[float]:
        """Get expiration timestamp."""
        if self.expires_in is None:
            return None
        return self.issued_at + self.expires_in


class IDTokenClaims(BaseModel):
    """OIDC ID Token standard claims."""
    
    # Required claims
    iss: str  # Issuer
    sub: str  # Subject (user ID)
    aud: str | list[str]  # Audience
    exp: int  # Expiration
    iat: int  # Issued at
    
    # Optional standard claims
    auth_time: Optional[int] = None
    nonce: Optional[str] = None
    acr: Optional[str] = None  # Authentication context class
    amr: Optional[list[str]] = None  # Authentication methods
    azp: Optional[str] = None  # Authorized party
    
    # Profile claims
    name: Optional[str] = None
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    preferred_username: Optional[str] = None
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return time.time() > self.exp
    
    def validate_audience(self, expected_client_id: str) -> bool:
        """Validate the audience claim."""
        if isinstance(self.aud, list):
            return expected_client_id in self.aud
        return self.aud == expected_client_id


class AuthorizationState(BaseModel):
    """State for authorization flow."""
    
    state: str  # Random state value
    nonce: Optional[str] = None  # For ID token validation
    code_verifier: Optional[str] = None  # PKCE verifier
    redirect_uri: str
    created_at: float = Field(default_factory=time.time)
    
    # Optional: store requested scopes
    scopes: list[str] = Field(default_factory=list)
    
    @property
    def is_expired(self) -> bool:
        """State expires after 10 minutes."""
        return time.time() > (self.created_at + 600)


# =============================================================================
# OAuth Client
# =============================================================================

class OAuthClient:
    """OAuth 2.0 Client for authorization code flow."""
    
    def __init__(self, config: OAuthConfig):
        """Initialize OAuth client.
        
        Args:
            config: OAuth configuration
        """
        self._config = config
        self._pending_states: dict[str, AuthorizationState] = {}
        
        if not config.client_id:
            raise ValueError("client_id is required")
        if not config.redirect_uri:
            raise ValueError("redirect_uri is required")
        if not config.authorization_endpoint and not config.issuer:
            raise ValueError("authorization_endpoint or issuer is required")
    
    def get_authorization_url(
        self,
        scopes: Optional[list[str]] = None,
        extra_params: Optional[dict[str, str]] = None,
    ) -> tuple[str, AuthorizationState]:
        """Generate authorization URL.
        
        Args:
            scopes: Override default scopes
            extra_params: Additional query parameters
            
        Returns:
            Tuple of (authorization_url, state_object)
        """
        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)
        
        # Generate nonce for ID token validation
        nonce = secrets.token_urlsafe(32) if "openid" in (scopes or self._config.scopes) else None
        
        # Generate PKCE if enabled
        code_verifier = None
        code_challenge = None
        code_challenge_method = None
        
        if self._config.use_pkce:
            code_verifier, code_challenge, code_challenge_method = PKCEGenerator.create_pkce_pair()
        
        # Build authorization URL parameters
        params: dict[str, str] = {
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes or self._config.scopes),
            "state": state,
        }
        
        if nonce:
            params["nonce"] = nonce
        
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = code_challenge_method
        
        if extra_params:
            params.update(extra_params)
        
        # Build URL
        auth_endpoint = self._config.authorization_endpoint or f"{self._config.issuer}/authorize"
        auth_url = f"{auth_endpoint}?{urlencode(params)}"
        
        # Store state
        auth_state = AuthorizationState(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_uri=self._config.redirect_uri,
            scopes=scopes or self._config.scopes,
        )
        self._pending_states[state] = auth_state
        
        logger.debug("oauth_auth_url_generated", state=state)
        return auth_url, auth_state
    
    def validate_callback_state(self, state: str) -> AuthorizationState:
        """Validate callback state parameter.
        
        Args:
            state: State from callback
            
        Returns:
            The stored authorization state
            
        Raises:
            ValueError: If state is invalid or expired
        """
        auth_state = self._pending_states.pop(state, None)
        
        if auth_state is None:
            logger.warning("oauth_invalid_state", state=state[:10] + "...")
            raise ValueError("Invalid state parameter")
        
        if auth_state.is_expired:
            logger.warning("oauth_state_expired", state=state[:10] + "...")
            raise ValueError("Authorization state expired")
        
        return auth_state
    
    def build_token_request(
        self,
        code: str,
        auth_state: AuthorizationState,
    ) -> dict[str, str]:
        """Build token exchange request body.
        
        Args:
            code: Authorization code from callback
            auth_state: Stored authorization state
            
        Returns:
            Request body for token endpoint
        """
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": auth_state.redirect_uri,
            "client_id": self._config.client_id,
        }
        
        if self._config.client_secret:
            body["client_secret"] = self._config.client_secret
        
        if auth_state.code_verifier:
            body["code_verifier"] = auth_state.code_verifier
        
        return body
    
    def build_refresh_request(self, refresh_token: str) -> dict[str, str]:
        """Build refresh token request body.
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            Request body for token endpoint
        """
        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self._config.client_id,
        }
        
        if self._config.client_secret:
            body["client_secret"] = self._config.client_secret
        
        return body
    
    @property
    def token_endpoint(self) -> str:
        """Get token endpoint URL."""
        return self._config.token_endpoint or f"{self._config.issuer}/oauth/token"


# =============================================================================
# ID Token Validation
# =============================================================================

class IDTokenValidator:
    """Validate OIDC ID tokens.
    
    Note: In production, you should use a proper JWT library with
    JWKS key fetching. This provides the validation logic structure.
    """
    
    def __init__(
        self,
        issuer: str,
        client_id: str,
        jwks_uri: Optional[str] = None,
    ):
        """Initialize validator.
        
        Args:
            issuer: Expected token issuer
            client_id: Expected audience
            jwks_uri: JWKS endpoint for key fetching
        """
        self._issuer = issuer
        self._client_id = client_id
        self._jwks_uri = jwks_uri
        self._jwks_cache: dict[str, Any] = {}
    
    def validate_claims(
        self,
        claims: IDTokenClaims,
        nonce: Optional[str] = None,
    ) -> bool:
        """Validate ID token claims.
        
        Args:
            claims: Parsed ID token claims
            nonce: Expected nonce (from authorization request)
            
        Returns:
            True if claims are valid
            
        Raises:
            ValueError: If claims are invalid
        """
        # Check issuer
        if claims.iss != self._issuer:
            raise ValueError(f"Invalid issuer: {claims.iss}")
        
        # Check audience
        if not claims.validate_audience(self._client_id):
            raise ValueError(f"Invalid audience: {claims.aud}")
        
        # Check expiration
        if claims.is_expired:
            raise ValueError("ID token expired")
        
        # Check issued at (should not be in future)
        if claims.iat > time.time() + 300:  # 5 min clock skew tolerance
            raise ValueError("ID token issued in the future")
        
        # Check nonce (if provided)
        if nonce and claims.nonce != nonce:
            raise ValueError("Nonce mismatch")
        
        # Check azp (if aud is array)
        if isinstance(claims.aud, list) and len(claims.aud) > 1:
            if not claims.azp:
                raise ValueError("azp required for multiple audiences")
            if claims.azp != self._client_id:
                raise ValueError(f"Invalid azp: {claims.azp}")
        
        logger.debug("id_token_claims_validated", sub=claims.sub)
        return True


# =============================================================================
# State Store Interface
# =============================================================================

class AuthStateStore:
    """Interface for storing authorization state.
    
    Subclass this for production use with Redis or database storage.
    """
    
    async def store(self, state: str, auth_state: AuthorizationState) -> None:
        """Store authorization state."""
        raise NotImplementedError
    
    async def retrieve(self, state: str) -> Optional[AuthorizationState]:
        """Retrieve and delete authorization state."""
        raise NotImplementedError
    
    async def cleanup_expired(self) -> int:
        """Remove expired states."""
        raise NotImplementedError


class InMemoryAuthStateStore(AuthStateStore):
    """In-memory state store for development/testing."""
    
    def __init__(self):
        self._states: dict[str, AuthorizationState] = {}
    
    async def store(self, state: str, auth_state: AuthorizationState) -> None:
        """Store authorization state."""
        self._states[state] = auth_state
    
    async def retrieve(self, state: str) -> Optional[AuthorizationState]:
        """Retrieve and delete authorization state."""
        return self._states.pop(state, None)
    
    async def cleanup_expired(self) -> int:
        """Remove expired states."""
        expired = [
            state for state, auth_state in self._states.items()
            if auth_state.is_expired
        ]
        for state in expired:
            del self._states[state]
        return len(expired)


# =============================================================================
# OAuth Flow Helper
# =============================================================================

class OAuthFlow:
    """High-level OAuth flow management.
    
    Example usage:
        flow = OAuthFlow(config)
        
        # Step 1: Get auth URL
        auth_url, state = flow.start_authorization()
        # Redirect user to auth_url
        
        # Step 2: Handle callback (in callback handler)
        code = request.query_params['code']
        state = request.query_params['state']
        token_request = flow.handle_callback(code, state)
        
        # Step 3: Exchange code for tokens (make HTTP request)
        # tokens = await http_client.post(flow.token_endpoint, data=token_request)
    """
    
    def __init__(
        self,
        config: OAuthConfig,
        state_store: Optional[AuthStateStore] = None,
    ):
        """Initialize OAuth flow.
        
        Args:
            config: OAuth configuration
            state_store: Optional state store (defaults to in-memory)
        """
        self._client = OAuthClient(config)
        self._state_store = state_store or InMemoryAuthStateStore()
        self._config = config
    
    def start_authorization(
        self,
        scopes: Optional[list[str]] = None,
        extra_params: Optional[dict[str, str]] = None,
    ) -> tuple[str, str]:
        """Start authorization flow.
        
        Args:
            scopes: Override default scopes
            extra_params: Additional parameters
            
        Returns:
            Tuple of (authorization_url, state_value)
        """
        auth_url, auth_state = self._client.get_authorization_url(scopes, extra_params)
        return auth_url, auth_state.state
    
    def handle_callback(
        self,
        code: str,
        state: str,
        error: Optional[str] = None,
        error_description: Optional[str] = None,
    ) -> dict[str, str]:
        """Handle OAuth callback.
        
        Args:
            code: Authorization code
            state: State parameter
            error: Error code (if any)
            error_description: Error description (if any)
            
        Returns:
            Token request body
            
        Raises:
            ValueError: If there's an error or invalid state
        """
        # Check for OAuth error
        if error:
            logger.warning(
                "oauth_callback_error",
                error=error,
                description=error_description,
            )
            raise ValueError(f"OAuth error: {error} - {error_description}")
        
        # Validate state
        auth_state = self._client.validate_callback_state(state)
        
        # Build token request
        return self._client.build_token_request(code, auth_state)
    
    @property
    def token_endpoint(self) -> str:
        """Get token endpoint URL."""
        return self._client.token_endpoint


# =============================================================================
# Token Storage
# =============================================================================

class SecureTokenStorage:
    """Secure storage for OAuth tokens.
    
    In production, tokens should be encrypted at rest.
    This provides the interface - implement with your storage backend.
    """
    
    async def store_tokens(
        self,
        user_id: str,
        tokens: OAuthTokenResponse,
        provider: OAuthProvider,
    ) -> None:
        """Store tokens for a user."""
        raise NotImplementedError
    
    async def get_tokens(
        self,
        user_id: str,
        provider: OAuthProvider,
    ) -> Optional[OAuthTokenResponse]:
        """Get stored tokens for a user."""
        raise NotImplementedError
    
    async def delete_tokens(
        self,
        user_id: str,
        provider: OAuthProvider,
    ) -> None:
        """Delete stored tokens for a user."""
        raise NotImplementedError


class InMemoryTokenStorage(SecureTokenStorage):
    """In-memory token storage for development/testing."""
    
    def __init__(self):
        self._tokens: dict[tuple[str, str], OAuthTokenResponse] = {}
    
    async def store_tokens(
        self,
        user_id: str,
        tokens: OAuthTokenResponse,
        provider: OAuthProvider,
    ) -> None:
        """Store tokens for a user."""
        key = (user_id, provider.value)
        self._tokens[key] = tokens
    
    async def get_tokens(
        self,
        user_id: str,
        provider: OAuthProvider,
    ) -> Optional[OAuthTokenResponse]:
        """Get stored tokens for a user."""
        key = (user_id, provider.value)
        return self._tokens.get(key)
    
    async def delete_tokens(
        self,
        user_id: str,
        provider: OAuthProvider,
    ) -> None:
        """Delete stored tokens for a user."""
        key = (user_id, provider.value)
        self._tokens.pop(key, None)
