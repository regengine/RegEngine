"""
SEC-028: API Authentication.

Provides comprehensive API authentication:
- API key authentication
- JWT token authentication
- OAuth2 token validation
- Multi-factor authentication support
- Token refresh handling
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class AuthenticationError(Exception):
    """Base exception for authentication errors."""
    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""
    pass


class TokenExpiredError(AuthenticationError):
    """Raised when token has expired."""
    pass


class TokenInvalidError(AuthenticationError):
    """Raised when token is invalid."""
    pass


class InsufficientScopeError(AuthenticationError):
    """Raised when token lacks required scope."""
    pass


class MFARequiredError(AuthenticationError):
    """Raised when MFA is required."""
    pass


# =============================================================================
# Enums
# =============================================================================

class AuthMethod(str, Enum):
    """Authentication methods."""
    API_KEY = "api_key"
    JWT = "jwt"
    OAUTH2 = "oauth2"
    BASIC = "basic"
    BEARER = "bearer"


class TokenType(str, Enum):
    """Token types."""
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"
    MFA = "mfa"


class KeyStatus(str, Enum):
    """API key status."""
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    SUSPENDED = "suspended"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class APIKey:
    """API key with metadata."""
    key_id: str
    key_hash: str  # Hashed key for storage
    name: str
    owner_id: str
    scopes: Set[str] = field(default_factory=set)
    status: KeyStatus = KeyStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    rate_limit: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_valid(self) -> bool:
        """Check if key is valid."""
        if self.status != KeyStatus.ACTIVE:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True


@dataclass
class Token:
    """Authentication token."""
    value: str
    token_type: TokenType
    expires_at: datetime
    issued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    subject: str = ""
    scopes: Set[str] = field(default_factory=set)
    claims: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.now(timezone.utc) > self.expires_at
    
    @property
    def ttl(self) -> int:
        """Time to live in seconds."""
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))


@dataclass
class AuthResult:
    """Result of authentication."""
    authenticated: bool
    subject: Optional[str] = None
    method: Optional[AuthMethod] = None
    scopes: Set[str] = field(default_factory=set)
    claims: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    mfa_required: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "authenticated": self.authenticated,
            "subject": self.subject,
            "method": self.method.value if self.method else None,
            "scopes": list(self.scopes),
            "error": self.error,
            "mfa_required": self.mfa_required,
        }


@dataclass
class TokenPair:
    """Access and refresh token pair."""
    access_token: Token
    refresh_token: Token
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for response."""
        return {
            "access_token": self.access_token.value,
            "token_type": "bearer",
            "expires_in": self.access_token.ttl,
            "refresh_token": self.refresh_token.value,
        }


# =============================================================================
# API Key Authenticator
# =============================================================================

class APIKeyAuthenticator:
    """
    Authenticates requests using API keys.
    
    Features:
    - Key generation
    - Key validation
    - Scope checking
    - Key revocation
    """
    
    def __init__(self):
        """Initialize authenticator."""
        self._keys: Dict[str, APIKey] = {}
        self._key_lookup: Dict[str, str] = {}  # hash -> key_id
    
    def generate_key(
        self,
        name: str,
        owner_id: str,
        scopes: Optional[Set[str]] = None,
        expires_in: Optional[int] = None,  # seconds
        prefix: str = "rk_",
    ) -> tuple[str, APIKey]:
        """
        Generate new API key.
        
        Args:
            name: Key name
            owner_id: Owner identifier
            scopes: Allowed scopes
            expires_in: Expiration time in seconds
            prefix: Key prefix
            
        Returns:
            Tuple of (raw_key, APIKey)
        """
        # Generate key
        raw_key = prefix + secrets.token_urlsafe(32)
        key_hash = self._hash_key(raw_key)
        key_id = secrets.token_hex(16)
        
        # Calculate expiration
        expires_at = None
        if expires_in:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            owner_id=owner_id,
            scopes=scopes or set(),
            expires_at=expires_at,
        )
        
        # Store key
        self._keys[key_id] = api_key
        self._key_lookup[key_hash] = key_id
        
        return raw_key, api_key
    
    def _hash_key(self, key: str) -> str:
        """Hash API key for storage."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def authenticate(
        self,
        api_key: str,
        required_scopes: Optional[Set[str]] = None,
    ) -> AuthResult:
        """
        Authenticate with API key.
        
        Args:
            api_key: Raw API key
            required_scopes: Required scopes
            
        Returns:
            AuthResult
        """
        key_hash = self._hash_key(api_key)
        
        # Look up key
        key_id = self._key_lookup.get(key_hash)
        if not key_id:
            return AuthResult(
                authenticated=False,
                error="Invalid API key",
            )
        
        key = self._keys.get(key_id)
        if not key:
            return AuthResult(
                authenticated=False,
                error="Invalid API key",
            )
        
        # Check validity
        if not key.is_valid():
            return AuthResult(
                authenticated=False,
                error=f"API key is {key.status.value}",
            )
        
        # Check scopes
        if required_scopes:
            missing = required_scopes - key.scopes
            if missing:
                return AuthResult(
                    authenticated=False,
                    error=f"Missing scopes: {missing}",
                )
        
        # Update last used
        key.last_used_at = datetime.now(timezone.utc)
        
        return AuthResult(
            authenticated=True,
            subject=key.owner_id,
            method=AuthMethod.API_KEY,
            scopes=key.scopes,
            claims={"key_id": key.key_id, "key_name": key.name},
        )
    
    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        if key_id in self._keys:
            self._keys[key_id].status = KeyStatus.REVOKED
            return True
        return False
    
    def get_key(self, key_id: str) -> Optional[APIKey]:
        """Get API key by ID."""
        return self._keys.get(key_id)
    
    def list_keys(self, owner_id: str) -> List[APIKey]:
        """List keys for owner."""
        return [k for k in self._keys.values() if k.owner_id == owner_id]


# =============================================================================
# JWT Authenticator
# =============================================================================

class JWTAuthenticator:
    """
    Authenticates requests using JWT tokens.
    
    Note: This is a simplified implementation.
    Production should use a proper JWT library like PyJWT.
    """
    
    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        access_token_ttl: int = 3600,  # 1 hour
        refresh_token_ttl: int = 86400 * 7,  # 7 days
        issuer: str = "regengine",
    ):
        """Initialize authenticator."""
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_ttl = access_token_ttl
        self.refresh_token_ttl = refresh_token_ttl
        self.issuer = issuer
        self._revoked_tokens: Set[str] = set()
    
    def _base64url_encode(self, data: bytes) -> str:
        """Base64url encode without padding."""
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")
    
    def _base64url_decode(self, data: str) -> bytes:
        """Base64url decode with padding restoration."""
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)
    
    def _sign(self, message: str) -> str:
        """Create HMAC signature."""
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256,
        ).digest()
        return self._base64url_encode(signature)
    
    def create_token(
        self,
        subject: str,
        token_type: TokenType = TokenType.ACCESS,
        scopes: Optional[Set[str]] = None,
        claims: Optional[Dict[str, Any]] = None,
        ttl: Optional[int] = None,
    ) -> Token:
        """
        Create JWT token.
        
        Args:
            subject: Token subject (user ID)
            token_type: Type of token
            scopes: Token scopes
            claims: Additional claims
            ttl: Time to live in seconds
            
        Returns:
            Token
        """
        now = datetime.now(timezone.utc)
        
        if ttl is None:
            ttl = (
                self.access_token_ttl
                if token_type == TokenType.ACCESS
                else self.refresh_token_ttl
            )
        
        expires_at = now + timedelta(seconds=ttl)
        
        # Build payload
        payload = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": self.issuer,
            "type": token_type.value,
            "scopes": list(scopes or []),
            "jti": secrets.token_hex(16),  # JWT ID
        }
        
        if claims:
            payload.update(claims)
        
        # Encode header and payload
        header = {"alg": self.algorithm, "typ": "JWT"}
        header_encoded = self._base64url_encode(json.dumps(header).encode())
        payload_encoded = self._base64url_encode(json.dumps(payload).encode())
        
        # Create signature
        message = f"{header_encoded}.{payload_encoded}"
        signature = self._sign(message)
        
        token_value = f"{message}.{signature}"
        
        return Token(
            value=token_value,
            token_type=token_type,
            expires_at=expires_at,
            issued_at=now,
            subject=subject,
            scopes=scopes or set(),
            claims=payload,
        )
    
    def create_token_pair(
        self,
        subject: str,
        scopes: Optional[Set[str]] = None,
        claims: Optional[Dict[str, Any]] = None,
    ) -> TokenPair:
        """Create access and refresh token pair."""
        access_token = self.create_token(
            subject=subject,
            token_type=TokenType.ACCESS,
            scopes=scopes,
            claims=claims,
        )
        
        refresh_token = self.create_token(
            subject=subject,
            token_type=TokenType.REFRESH,
            scopes=scopes,
            claims=claims,
        )
        
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
        )
    
    def verify_token(
        self,
        token_value: str,
        required_scopes: Optional[Set[str]] = None,
    ) -> AuthResult:
        """
        Verify JWT token.
        
        Args:
            token_value: JWT token string
            required_scopes: Required scopes
            
        Returns:
            AuthResult
        """
        try:
            # Split token
            parts = token_value.split(".")
            if len(parts) != 3:
                return AuthResult(
                    authenticated=False,
                    error="Invalid token format",
                )
            
            header_encoded, payload_encoded, signature = parts
            
            # Verify signature
            message = f"{header_encoded}.{payload_encoded}"
            expected_sig = self._sign(message)
            
            if not hmac.compare_digest(signature, expected_sig):
                return AuthResult(
                    authenticated=False,
                    error="Invalid token signature",
                )
            
            # Decode payload
            payload = json.loads(self._base64url_decode(payload_encoded))
            
            # Check expiration
            exp = payload.get("exp", 0)
            if time.time() > exp:
                return AuthResult(
                    authenticated=False,
                    error="Token expired",
                )
            
            # Check issuer
            if payload.get("iss") != self.issuer:
                return AuthResult(
                    authenticated=False,
                    error="Invalid token issuer",
                )
            
            # Check if revoked
            jti = payload.get("jti")
            if jti and jti in self._revoked_tokens:
                return AuthResult(
                    authenticated=False,
                    error="Token has been revoked",
                )
            
            # Check scopes
            token_scopes = set(payload.get("scopes", []))
            if required_scopes:
                missing = required_scopes - token_scopes
                if missing:
                    return AuthResult(
                        authenticated=False,
                        error=f"Missing scopes: {missing}",
                    )
            
            return AuthResult(
                authenticated=True,
                subject=payload.get("sub"),
                method=AuthMethod.JWT,
                scopes=token_scopes,
                claims=payload,
            )
            
        except Exception as e:
            return AuthResult(
                authenticated=False,
                error=f"Token verification failed: {e}",
            )
    
    def refresh_tokens(
        self,
        refresh_token: str,
    ) -> Optional[TokenPair]:
        """
        Refresh token pair using refresh token.
        
        Args:
            refresh_token: Refresh token value
            
        Returns:
            New TokenPair or None if invalid
        """
        result = self.verify_token(refresh_token)
        
        if not result.authenticated:
            return None
        
        # Verify it's a refresh token
        if result.claims.get("type") != TokenType.REFRESH.value:
            return None
        
        # Revoke old refresh token
        if jti := result.claims.get("jti"):
            self._revoked_tokens.add(jti)
        
        # Create new pair
        return self.create_token_pair(
            subject=result.subject,
            scopes=result.scopes,
        )
    
    def revoke_token(self, token_value: str) -> bool:
        """Revoke a token."""
        result = self.verify_token(token_value)
        if result.authenticated:
            if jti := result.claims.get("jti"):
                self._revoked_tokens.add(jti)
                return True
        return False


# =============================================================================
# Basic Auth Authenticator
# =============================================================================

class BasicAuthenticator:
    """
    Authenticates requests using HTTP Basic Authentication.
    """
    
    def __init__(
        self,
        verify_credentials: Callable[[str, str], Optional[Dict[str, Any]]],
    ):
        """
        Initialize authenticator.
        
        Args:
            verify_credentials: Callback to verify username/password
                Returns user info dict if valid, None if invalid
        """
        self.verify_credentials = verify_credentials
    
    def authenticate(self, auth_header: str) -> AuthResult:
        """
        Authenticate using Basic auth header.
        
        Args:
            auth_header: Authorization header value
            
        Returns:
            AuthResult
        """
        if not auth_header.startswith("Basic "):
            return AuthResult(
                authenticated=False,
                error="Invalid authorization header",
            )
        
        try:
            # Decode credentials
            encoded = auth_header[6:]  # Remove "Basic "
            decoded = base64.b64decode(encoded).decode("utf-8")
            username, password = decoded.split(":", 1)
            
            # Verify credentials
            user_info = self.verify_credentials(username, password)
            
            if user_info is None:
                return AuthResult(
                    authenticated=False,
                    error="Invalid credentials",
                )
            
            return AuthResult(
                authenticated=True,
                subject=user_info.get("id", username),
                method=AuthMethod.BASIC,
                scopes=set(user_info.get("scopes", [])),
                claims=user_info,
            )
            
        except Exception as e:
            return AuthResult(
                authenticated=False,
                error=f"Authentication failed: {e}",
            )


# =============================================================================
# Authentication Service
# =============================================================================

class AuthenticationService:
    """
    High-level authentication service.
    
    Provides:
    - Multiple auth method support
    - Request authentication
    - Token management
    """
    
    _instance: Optional["AuthenticationService"] = None
    
    def __init__(
        self,
        jwt_secret: Optional[str] = None,
    ):
        """Initialize service.

        Raises ``ValueError`` if *jwt_secret* is not provided **and**
        ``configure()`` has not been called first.  This prevents the
        service from silently using a placeholder secret.
        """
        if jwt_secret is None:
            raise ValueError(
                "jwt_secret is required. Call AuthenticationService.configure(jwt_secret=...) "
                "before using get_instance(), or set the JWT_SECRET environment variable."
            )
        self.api_key_auth = APIKeyAuthenticator()
        self.jwt_auth = JWTAuthenticator(jwt_secret)
        self._basic_auth: Optional[BasicAuthenticator] = None

    @classmethod
    def get_instance(cls) -> "AuthenticationService":
        """Get singleton instance.

        Raises ``ValueError`` if the service has not been configured via
        ``configure()`` first.
        """
        if cls._instance is None:
            raise ValueError(
                "AuthenticationService has not been configured. "
                "Call AuthenticationService.configure(jwt_secret=...) at startup."
            )
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        jwt_secret: str,
    ) -> "AuthenticationService":
        """Configure the service."""
        cls._instance = cls(jwt_secret=jwt_secret)
        return cls._instance
    
    def set_basic_auth_verifier(
        self,
        verifier: Callable[[str, str], Optional[Dict[str, Any]]],
    ) -> None:
        """Set basic auth credential verifier."""
        self._basic_auth = BasicAuthenticator(verifier)
    
    def authenticate_request(
        self,
        authorization: Optional[str] = None,
        api_key: Optional[str] = None,
        required_scopes: Optional[Set[str]] = None,
    ) -> AuthResult:
        """
        Authenticate a request.
        
        Args:
            authorization: Authorization header
            api_key: API key (from header or query param)
            required_scopes: Required scopes
            
        Returns:
            AuthResult
        """
        # Try API key first
        if api_key:
            return self.api_key_auth.authenticate(api_key, required_scopes)
        
        # Try Authorization header
        if authorization:
            if authorization.startswith("Bearer "):
                token = authorization[7:]
                return self.jwt_auth.verify_token(token, required_scopes)
            elif authorization.startswith("Basic ") and self._basic_auth:
                return self._basic_auth.authenticate(authorization)
        
        return AuthResult(
            authenticated=False,
            error="No authentication credentials provided",
        )
    
    def create_api_key(
        self,
        name: str,
        owner_id: str,
        scopes: Optional[Set[str]] = None,
    ) -> tuple[str, APIKey]:
        """Create new API key."""
        return self.api_key_auth.generate_key(name, owner_id, scopes)
    
    def create_tokens(
        self,
        subject: str,
        scopes: Optional[Set[str]] = None,
    ) -> TokenPair:
        """Create JWT token pair."""
        return self.jwt_auth.create_token_pair(subject, scopes)
    
    def refresh_tokens(self, refresh_token: str) -> Optional[TokenPair]:
        """Refresh tokens."""
        return self.jwt_auth.refresh_tokens(refresh_token)


# =============================================================================
# Convenience Functions
# =============================================================================

def get_auth_service() -> AuthenticationService:
    """Get the global authentication service."""
    return AuthenticationService.get_instance()


def authenticate(
    authorization: Optional[str] = None,
    api_key: Optional[str] = None,
    required_scopes: Optional[Set[str]] = None,
) -> AuthResult:
    """Authenticate a request."""
    return get_auth_service().authenticate_request(
        authorization,
        api_key,
        required_scopes,
    )
