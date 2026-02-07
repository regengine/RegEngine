"""
SEC-006: JWT Token Support for RegEngine.

This module provides JWT (JSON Web Token) authentication with:
- RS256 (RSA) and HS256 (HMAC) algorithm support
- Access and refresh token management
- Token blacklisting for logout/revocation
- Claims validation and extraction
- Configurable expiration times

Usage:
    from shared.jwt_auth import JWTManager, TokenType
    
    jwt_manager = JWTManager(secret_key="your-secret")
    
    # Create tokens
    access_token = jwt_manager.create_access_token(
        subject="user-123",
        claims={"role": "admin", "tenant_id": "tenant-456"}
    )
    
    # Verify tokens
    payload = jwt_manager.verify_token(access_token)
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, Set
from uuid import uuid4

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger("jwt_auth")

# Try to import PyJWT
try:
    import jwt
    from jwt.exceptions import (
        DecodeError,
        ExpiredSignatureError,
        InvalidAudienceError,
        InvalidIssuerError,
        InvalidSignatureError,
        InvalidTokenError,
    )
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    # Define placeholder exceptions for when jwt is not installed
    class InvalidTokenError(Exception):
        pass
    class ExpiredSignatureError(InvalidTokenError):
        pass
    class InvalidSignatureError(InvalidTokenError):
        pass
    class DecodeError(InvalidTokenError):
        pass
    class InvalidAudienceError(InvalidTokenError):
        pass
    class InvalidIssuerError(InvalidTokenError):
        pass


class TokenType(str, Enum):
    """Types of JWT tokens."""
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"  # For API key-based JWTs


class JWTAlgorithm(str, Enum):
    """Supported JWT signing algorithms."""
    HS256 = "HS256"  # HMAC with SHA-256
    HS384 = "HS384"  # HMAC with SHA-384
    HS512 = "HS512"  # HMAC with SHA-512
    RS256 = "RS256"  # RSA with SHA-256
    RS384 = "RS384"  # RSA with SHA-384
    RS512 = "RS512"  # RSA with SHA-512
    ES256 = "ES256"  # ECDSA with SHA-256
    ES384 = "ES384"  # ECDSA with SHA-384
    ES512 = "ES512"  # ECDSA with SHA-512


class TokenPayload(BaseModel):
    """Standard JWT payload claims."""
    
    # Standard claims
    sub: str  # Subject (user ID)
    iat: int  # Issued at (Unix timestamp)
    exp: int  # Expiration (Unix timestamp)
    jti: str  # JWT ID (unique identifier)
    
    # Optional standard claims
    iss: Optional[str] = None  # Issuer
    aud: Optional[str | list[str]] = None  # Audience
    nbf: Optional[int] = None  # Not before
    
    # Custom claims
    type: TokenType = TokenType.ACCESS
    tenant_id: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    
    # Additional custom claims
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        """Check if the token is expired."""
        return self.exp < int(time.time())

    @property
    def expires_at(self) -> datetime:
        """Get expiration as datetime."""
        return datetime.fromtimestamp(self.exp, tz=timezone.utc)

    @property
    def issued_at(self) -> datetime:
        """Get issued at as datetime."""
        return datetime.fromtimestamp(self.iat, tz=timezone.utc)


class TokenResponse(BaseModel):
    """Response model for token creation."""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int  # Seconds until expiration
    expires_at: datetime
    scope: Optional[str] = None


class JWTConfig(BaseModel):
    """Configuration for JWT management."""
    
    # Algorithm and keys
    algorithm: JWTAlgorithm = JWTAlgorithm.HS256
    secret_key: Optional[str] = None  # For HMAC algorithms
    private_key: Optional[str] = None  # For RSA/ECDSA algorithms
    public_key: Optional[str] = None  # For RSA/ECDSA verification
    
    # Token lifetimes
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    
    # Validation options
    issuer: Optional[str] = None
    audience: Optional[str | list[str]] = None
    
    # Security options
    verify_exp: bool = True
    verify_iat: bool = True
    verify_nbf: bool = True
    require_exp: bool = True
    require_iat: bool = True
    leeway: int = 0  # Seconds of leeway for exp/nbf validation


class JWTManager:
    """JWT token manager with support for access and refresh tokens.
    
    This class handles:
    - Token creation with configurable claims
    - Token verification with signature and claims validation
    - Token refresh flow
    - Token blacklisting for logout/revocation
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        private_key: Optional[str] = None,
        public_key: Optional[str] = None,
        algorithm: JWTAlgorithm = JWTAlgorithm.HS256,
        access_token_expire_minutes: int = 15,
        refresh_token_expire_days: int = 7,
        issuer: Optional[str] = None,
        audience: Optional[str | list[str]] = None,
    ):
        """Initialize the JWT manager.
        
        Args:
            secret_key: Secret for HMAC algorithms (HS256, HS384, HS512)
            private_key: Private key for RSA/ECDSA algorithms
            public_key: Public key for RSA/ECDSA verification
            algorithm: Signing algorithm to use
            access_token_expire_minutes: Access token lifetime
            refresh_token_expire_days: Refresh token lifetime
            issuer: Token issuer (iss claim)
            audience: Expected audience (aud claim)
        """
        if not JWT_AVAILABLE:
            raise ImportError(
                "PyJWT is required for JWT support. "
                "Install it with: pip install PyJWT"
            )

        self._algorithm = algorithm
        self._issuer = issuer or os.environ.get("JWT_ISSUER", "regengine")
        self._audience = audience or os.environ.get("JWT_AUDIENCE")
        self._access_expire_minutes = access_token_expire_minutes
        self._refresh_expire_days = refresh_token_expire_days
        
        # Set up signing keys based on algorithm
        if algorithm.value.startswith("HS"):
            # HMAC algorithms use a shared secret
            self._secret_key = secret_key or os.environ.get("JWT_SECRET")
            if not self._secret_key:
                raise ValueError(
                    "secret_key is required for HMAC algorithms. "
                    "Set JWT_SECRET environment variable or pass secret_key."
                )
            self._signing_key = self._secret_key
            self._verify_key = self._secret_key
        else:
            # RSA/ECDSA algorithms use public/private key pair
            self._private_key = private_key or os.environ.get("JWT_PRIVATE_KEY")
            self._public_key = public_key or os.environ.get("JWT_PUBLIC_KEY")
            
            if not self._private_key:
                raise ValueError(
                    f"private_key is required for {algorithm.value}. "
                    "Set JWT_PRIVATE_KEY environment variable or pass private_key."
                )
            
            self._signing_key = self._private_key
            self._verify_key = self._public_key or self._private_key
        
        # In-memory token blacklist (use Redis in production)
        self._blacklist: Set[str] = set()
        
        logger.info(
            "jwt_manager_initialized",
            algorithm=algorithm.value,
            issuer=self._issuer,
            access_expire_minutes=access_token_expire_minutes,
        )

    def create_access_token(
        self,
        subject: str,
        *,
        tenant_id: Optional[str] = None,
        roles: Optional[list[str]] = None,
        scopes: Optional[list[str]] = None,
        expires_delta: Optional[timedelta] = None,
        extra_claims: Optional[dict[str, Any]] = None,
    ) -> str:
        """Create an access token.
        
        Args:
            subject: User ID or identifier (becomes 'sub' claim)
            tenant_id: Tenant ID for multi-tenancy
            roles: User roles
            scopes: Permission scopes
            expires_delta: Custom expiration time
            extra_claims: Additional claims to include
            
        Returns:
            Encoded JWT access token
        """
        return self._create_token(
            subject=subject,
            token_type=TokenType.ACCESS,
            tenant_id=tenant_id,
            roles=roles,
            scopes=scopes,
            expires_delta=expires_delta or timedelta(minutes=self._access_expire_minutes),
            extra_claims=extra_claims,
        )

    def create_refresh_token(
        self,
        subject: str,
        *,
        tenant_id: Optional[str] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """Create a refresh token.
        
        Refresh tokens have longer lifetimes and are used to obtain
        new access tokens without re-authentication.
        
        Args:
            subject: User ID or identifier
            tenant_id: Tenant ID for multi-tenancy
            expires_delta: Custom expiration time
            
        Returns:
            Encoded JWT refresh token
        """
        return self._create_token(
            subject=subject,
            token_type=TokenType.REFRESH,
            tenant_id=tenant_id,
            expires_delta=expires_delta or timedelta(days=self._refresh_expire_days),
        )

    def create_token_pair(
        self,
        subject: str,
        *,
        tenant_id: Optional[str] = None,
        roles: Optional[list[str]] = None,
        scopes: Optional[list[str]] = None,
        extra_claims: Optional[dict[str, Any]] = None,
    ) -> TokenResponse:
        """Create both access and refresh tokens.
        
        Args:
            subject: User ID or identifier
            tenant_id: Tenant ID for multi-tenancy
            roles: User roles
            scopes: Permission scopes
            extra_claims: Additional claims for access token
            
        Returns:
            TokenResponse with both tokens
        """
        access_token = self.create_access_token(
            subject=subject,
            tenant_id=tenant_id,
            roles=roles,
            scopes=scopes,
            extra_claims=extra_claims,
        )
        
        refresh_token = self.create_refresh_token(
            subject=subject,
            tenant_id=tenant_id,
        )
        
        expires_in = self._access_expire_minutes * 60
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self._access_expire_minutes)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            expires_at=expires_at,
            scope=" ".join(scopes) if scopes else None,
        )

    def _create_token(
        self,
        subject: str,
        token_type: TokenType,
        *,
        tenant_id: Optional[str] = None,
        roles: Optional[list[str]] = None,
        scopes: Optional[list[str]] = None,
        expires_delta: timedelta,
        extra_claims: Optional[dict[str, Any]] = None,
    ) -> str:
        """Internal method to create a token."""
        now = datetime.now(timezone.utc)
        exp = now + expires_delta
        jti = str(uuid4())
        
        payload = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "jti": jti,
            "type": token_type.value,
        }
        
        # Add issuer if configured
        if self._issuer:
            payload["iss"] = self._issuer
            
        # Add audience if configured
        if self._audience:
            payload["aud"] = self._audience
        
        # Add optional claims
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if roles:
            payload["roles"] = roles
        if scopes:
            payload["scopes"] = scopes
        if extra_claims:
            payload["extra"] = extra_claims
        
        token = jwt.encode(
            payload,
            self._signing_key,
            algorithm=self._algorithm.value,
        )
        
        logger.debug(
            "token_created",
            subject=subject,
            token_type=token_type.value,
            jti=jti,
            expires_at=exp.isoformat(),
        )
        
        return token

    def verify_token(
        self,
        token: str,
        *,
        expected_type: Optional[TokenType] = None,
        verify_exp: bool = True,
    ) -> TokenPayload:
        """Verify and decode a JWT token.
        
        Args:
            token: The JWT token to verify
            expected_type: Expected token type (ACCESS, REFRESH)
            verify_exp: Whether to verify expiration
            
        Returns:
            TokenPayload with decoded claims
            
        Raises:
            InvalidTokenError: If token is invalid
            ExpiredSignatureError: If token is expired
        """
        # Check blacklist first
        token_hash = self._hash_token(token)
        if token_hash in self._blacklist:
            logger.warning("token_blacklisted", token_hash=token_hash[:16])
            raise InvalidTokenError("Token has been revoked")
        
        # Set up verification options
        options = {
            "verify_exp": verify_exp,
            "verify_iat": True,
            "verify_nbf": True,
            "require": ["exp", "iat", "sub", "jti"],
        }
        
        # Build decode kwargs
        decode_kwargs: dict[str, Any] = {
            "algorithms": [self._algorithm.value],
            "options": options,
        }
        
        if self._issuer:
            decode_kwargs["issuer"] = self._issuer
        if self._audience:
            decode_kwargs["audience"] = self._audience
        
        try:
            payload = jwt.decode(
                token,
                self._verify_key,
                **decode_kwargs,
            )
        except ExpiredSignatureError:
            logger.warning("token_expired", token_prefix=token[:20])
            raise
        except InvalidSignatureError:
            logger.warning("token_invalid_signature", token_prefix=token[:20])
            raise InvalidTokenError("Invalid token signature")
        except DecodeError as e:
            logger.warning("token_decode_error", error=str(e))
            raise InvalidTokenError(f"Token decode error: {e}")
        except InvalidAudienceError:
            logger.warning("token_invalid_audience")
            raise InvalidTokenError("Invalid token audience")
        except InvalidIssuerError:
            logger.warning("token_invalid_issuer")
            raise InvalidTokenError("Invalid token issuer")
        except InvalidTokenError as e:
            logger.warning("token_invalid", error=str(e))
            raise
        
        # Verify token type if specified
        token_type = TokenType(payload.get("type", TokenType.ACCESS.value))
        if expected_type and token_type != expected_type:
            logger.warning(
                "token_type_mismatch",
                expected=expected_type.value,
                actual=token_type.value,
            )
            raise InvalidTokenError(
                f"Expected {expected_type.value} token, got {token_type.value}"
            )
        
        return TokenPayload(
            sub=payload["sub"],
            iat=payload["iat"],
            exp=payload["exp"],
            jti=payload["jti"],
            iss=payload.get("iss"),
            aud=payload.get("aud"),
            type=token_type,
            tenant_id=payload.get("tenant_id"),
            roles=payload.get("roles", []),
            scopes=payload.get("scopes", []),
            extra=payload.get("extra", {}),
        )

    def refresh_access_token(
        self,
        refresh_token: str,
        *,
        roles: Optional[list[str]] = None,
        scopes: Optional[list[str]] = None,
    ) -> TokenResponse:
        """Use a refresh token to get a new access token.
        
        Args:
            refresh_token: The refresh token
            roles: Updated roles (optional)
            scopes: Updated scopes (optional)
            
        Returns:
            TokenResponse with new access token
        """
        # Verify the refresh token
        payload = self.verify_token(
            refresh_token,
            expected_type=TokenType.REFRESH,
        )
        
        # Create new access token
        access_token = self.create_access_token(
            subject=payload.sub,
            tenant_id=payload.tenant_id,
            roles=roles or payload.roles,
            scopes=scopes or payload.scopes,
        )
        
        expires_in = self._access_expire_minutes * 60
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self._access_expire_minutes)
        
        logger.info("access_token_refreshed", subject=payload.sub)
        
        return TokenResponse(
            access_token=access_token,
            refresh_token=None,  # Don't return a new refresh token
            expires_in=expires_in,
            expires_at=expires_at,
            scope=" ".join(scopes) if scopes else None,
        )

    def revoke_token(self, token: str) -> bool:
        """Revoke a token by adding it to the blacklist.
        
        In production, use Redis or a database for the blacklist
        to support distributed systems.
        
        Args:
            token: The token to revoke
            
        Returns:
            True if token was revoked
        """
        token_hash = self._hash_token(token)
        self._blacklist.add(token_hash)
        logger.info("token_revoked", token_hash=token_hash[:16])
        return True

    def is_revoked(self, token: str) -> bool:
        """Check if a token has been revoked.
        
        Args:
            token: The token to check
            
        Returns:
            True if token is revoked
        """
        token_hash = self._hash_token(token)
        return token_hash in self._blacklist

    @staticmethod
    def _hash_token(token: str) -> str:
        """Hash a token for blacklist storage.
        
        We store hashes instead of full tokens to limit exposure
        if the blacklist is compromised.
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def decode_token_unverified(self, token: str) -> dict[str, Any]:
        """Decode a token without verification.
        
        WARNING: Only use for debugging or introspection.
        Never trust unverified token data for authorization.
        
        Args:
            token: The token to decode
            
        Returns:
            Raw payload dict
        """
        return jwt.decode(
            token,
            options={"verify_signature": False},
        )

    def get_token_id(self, token: str) -> Optional[str]:
        """Extract the JTI (token ID) from a token without full verification.
        
        Args:
            token: The token
            
        Returns:
            The JTI claim or None
        """
        try:
            payload = self.decode_token_unverified(token)
            return payload.get("jti")
        except Exception:
            return None


# FastAPI dependency helpers
def get_jwt_manager() -> JWTManager:
    """Get the global JWT manager instance.
    
    Creates a new instance using environment variables.
    """
    return JWTManager()


# Export exceptions for convenience
__all__ = [
    "JWTManager",
    "JWTConfig",
    "JWTAlgorithm",
    "TokenType",
    "TokenPayload",
    "TokenResponse",
    "InvalidTokenError",
    "ExpiredSignatureError",
    "get_jwt_manager",
]
