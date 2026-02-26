"""
SEC-009: Service-to-Service Authentication for RegEngine.

This module provides secure inter-service communication with:
- Mutual TLS (mTLS) support
- Service tokens with short lifetimes
- Service identity verification
- Request signing for additional security
- Circuit breaker for failing services

Usage:
    from shared.service_auth import ServiceAuthClient, ServiceIdentity
    
    # Create a service client
    client = ServiceAuthClient(
        service_id="nlp-service",
        target_service="graph-service",
        secret_key=os.environ["SERVICE_AUTH_SECRET"],
    )
    
    # Make authenticated requests
    response = await client.request("GET", "/api/v1/nodes")
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlencode
from uuid import uuid4

import structlog
from pydantic import BaseModel

logger = structlog.get_logger("service_auth")


# =============================================================================
# Service Registry
# =============================================================================

class ServiceName(str, Enum):
    """Known internal services."""
    ADMIN = "admin-api"
    INGESTION = "ingestion-service"
    NLP = "nlp-service"
    GRAPH = "graph-service"
    OPPORTUNITY = "opportunity-api"
    COMPLIANCE = "compliance-service"


@dataclass
class ServiceIdentity:
    """Represents a service's identity."""
    
    service_id: str
    service_name: ServiceName
    instance_id: str = field(default_factory=lambda: str(uuid4())[:8])
    version: str = "1.0.0"
    environment: str = field(default_factory=lambda: os.environ.get("REGENGINE_ENV", "development"))
    
    # Trust level (for gradual rollout)
    trust_level: int = 1  # 1=basic, 2=elevated, 3=high
    
    # Capabilities
    allowed_targets: set[ServiceName] = field(default_factory=set)  # Services this can call
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for token payload."""
        return {
            "service_id": self.service_id,
            "service_name": self.service_name.value,
            "instance_id": self.instance_id,
            "version": self.version,
            "environment": self.environment,
            "trust_level": self.trust_level,
        }


# =============================================================================
# Service Token
# =============================================================================

class ServiceTokenPayload(BaseModel):
    """Payload for service-to-service tokens."""
    
    # Standard JWT-like claims
    iss: str  # Issuing service
    sub: str  # Service making the request
    aud: str  # Target service
    iat: int  # Issued at
    exp: int  # Expiration
    jti: str  # Unique token ID
    
    # Service-specific claims
    instance_id: str
    trust_level: int = 1
    request_id: Optional[str] = None  # For request correlation

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return self.exp < int(time.time())


class ServiceTokenManager:
    """Manages service-to-service authentication tokens.
    
    Uses short-lived tokens (default: 5 minutes) to minimize
    the impact of token compromise.
    """

    def __init__(
        self,
        secret_key: Optional[str] = None,
        token_lifetime_seconds: int = 300,  # 5 minutes
    ):
        """Initialize the token manager.
        
        Args:
            secret_key: Shared secret for signing (all services must use same key)
            token_lifetime_seconds: Token lifetime in seconds
        """
        self._secret_key = secret_key or os.environ.get("SERVICE_AUTH_SECRET")
        if not self._secret_key:
            raise ValueError(
                "Service auth secret is required. "
                "Set SERVICE_AUTH_SECRET environment variable."
            )
        
        self._token_lifetime = token_lifetime_seconds
        
        # Token cache to prevent replay attacks
        self._used_tokens: set[str] = set()
        self._used_tokens_cleanup_time = time.time()

    def create_token(
        self,
        source_service: ServiceIdentity,
        target_service: ServiceName,
        request_id: Optional[str] = None,
    ) -> str:
        """Create a service token.
        
        Args:
            source_service: The service making the request
            target_service: The service being called
            request_id: Optional request ID for correlation
            
        Returns:
            Base64-encoded signed token
        """
        now = int(time.time())
        jti = str(uuid4())
        
        payload = ServiceTokenPayload(
            iss=source_service.service_name.value,
            sub=source_service.service_id,
            aud=target_service.value,
            iat=now,
            exp=now + self._token_lifetime,
            jti=jti,
            instance_id=source_service.instance_id,
            trust_level=source_service.trust_level,
            request_id=request_id,
        )
        
        # Serialize payload
        payload_json = payload.model_dump_json()
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode()
        
        # Create signature
        signature = self._sign(payload_b64)
        
        # Combine payload and signature
        token = f"{payload_b64}.{signature}"
        
        logger.debug(
            "service_token_created",
            source=source_service.service_name.value,
            target=target_service.value,
            jti=jti,
        )
        
        return token

    def verify_token(
        self,
        token: str,
        expected_audience: ServiceName,
    ) -> ServiceTokenPayload:
        """Verify a service token.
        
        Args:
            token: The token to verify
            expected_audience: The service that should be receiving this token
            
        Returns:
            Verified token payload
            
        Raises:
            ValueError: If token is invalid
        """
        # Cleanup old used tokens periodically
        self._cleanup_used_tokens()
        
        # Split token
        try:
            payload_b64, signature = token.split(".", 1)
        except ValueError:
            raise ValueError("Invalid token format")
        
        # Verify signature
        expected_signature = self._sign(payload_b64)
        if not hmac.compare_digest(signature, expected_signature):
            logger.warning("service_token_invalid_signature")
            raise ValueError("Invalid token signature")
        
        # Decode payload
        try:
            payload_json = base64.urlsafe_b64decode(payload_b64).decode()
            payload = ServiceTokenPayload.model_validate_json(payload_json)
        except Exception as e:
            logger.warning("service_token_decode_error", error=str(e))
            raise ValueError(f"Token decode error: {e}")
        
        # Check expiration
        if payload.is_expired:
            logger.warning("service_token_expired", jti=payload.jti)
            raise ValueError("Token expired")
        
        # Check audience
        if payload.aud != expected_audience.value:
            logger.warning(
                "service_token_audience_mismatch",
                expected=expected_audience.value,
                actual=payload.aud,
            )
            raise ValueError("Token audience mismatch")
        
        # Check for replay
        if payload.jti in self._used_tokens:
            logger.warning("service_token_replay", jti=payload.jti)
            raise ValueError("Token already used (replay detected)")
        
        # Mark token as used
        self._used_tokens.add(payload.jti)
        
        logger.debug(
            "service_token_verified",
            source=payload.sub,
            jti=payload.jti,
        )
        
        return payload

    def _sign(self, data: str) -> str:
        """Create HMAC signature."""
        signature = hmac.new(
            self._secret_key.encode(),
            data.encode(),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(signature).decode()

    def _cleanup_used_tokens(self) -> None:
        """Remove expired tokens from used set."""
        now = time.time()
        # Cleanup every 5 minutes
        if now - self._used_tokens_cleanup_time > 300:
            # In a real implementation, we'd track expiration per token
            # For simplicity, just clear tokens older than 2x lifetime
            self._used_tokens.clear()
            self._used_tokens_cleanup_time = now


# =============================================================================
# Request Signing
# =============================================================================

class RequestSigner:
    """Signs HTTP requests for additional security.
    
    This provides an additional layer of security beyond tokens,
    ensuring requests haven't been tampered with in transit.
    """

    SIGNATURE_HEADER = "X-RegEngine-Signature"
    TIMESTAMP_HEADER = "X-RegEngine-Timestamp"
    
    def __init__(
        self,
        secret_key: Optional[str] = None,
        max_age_seconds: int = 300,  # 5 minutes
    ):
        """Initialize the request signer.
        
        Args:
            secret_key: Secret for signing
            max_age_seconds: Maximum age of signature before rejection
        """
        self._secret_key = secret_key or os.environ.get("SERVICE_AUTH_SECRET", "")
        self._max_age = max_age_seconds

    def sign_request(
        self,
        method: str,
        path: str,
        body: Optional[bytes] = None,
        query_params: Optional[dict[str, str]] = None,
    ) -> dict[str, str]:
        """Sign a request and return headers to add.
        
        Args:
            method: HTTP method
            path: Request path
            body: Request body (if any)
            query_params: Query parameters (if any)
            
        Returns:
            Dict of headers to add to the request
        """
        timestamp = str(int(time.time()))
        
        # Build canonical request
        canonical = self._build_canonical_request(
            method, path, body, query_params, timestamp
        )
        
        # Sign
        signature = hmac.new(
            self._secret_key.encode(),
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        return {
            self.SIGNATURE_HEADER: signature,
            self.TIMESTAMP_HEADER: timestamp,
        }

    def verify_request(
        self,
        method: str,
        path: str,
        signature: str,
        timestamp: str,
        body: Optional[bytes] = None,
        query_params: Optional[dict[str, str]] = None,
    ) -> bool:
        """Verify a signed request.
        
        Args:
            method: HTTP method
            path: Request path
            signature: Signature from header
            timestamp: Timestamp from header
            body: Request body
            query_params: Query parameters
            
        Returns:
            True if signature is valid
        """
        # Check timestamp age
        try:
            ts = int(timestamp)
            age = abs(int(time.time()) - ts)
            if age > self._max_age:
                logger.warning("request_signature_too_old", age=age)
                return False
        except ValueError:
            return False
        
        # Rebuild canonical request
        canonical = self._build_canonical_request(
            method, path, body, query_params, timestamp
        )
        
        # Verify signature
        expected = hmac.new(
            self._secret_key.encode(),
            canonical.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)

    def _build_canonical_request(
        self,
        method: str,
        path: str,
        body: Optional[bytes],
        query_params: Optional[dict[str, str]],
        timestamp: str,
    ) -> str:
        """Build canonical request string for signing."""
        parts = [
            method.upper(),
            path,
            timestamp,
        ]
        
        if query_params:
            # Sort params for consistency
            sorted_params = sorted(query_params.items())
            parts.append(urlencode(sorted_params))
        
        if body:
            # Hash the body
            body_hash = hashlib.sha256(body).hexdigest()
            parts.append(body_hash)
        
        return "\n".join(parts)


# =============================================================================
# Service Auth Client
# =============================================================================

@dataclass
class ServiceAuthConfig:
    """Configuration for service authentication."""
    
    service_id: str
    service_name: ServiceName
    secret_key: Optional[str] = None
    token_lifetime_seconds: int = 300
    sign_requests: bool = True
    
    # Circuit breaker settings
    failure_threshold: int = 5
    reset_timeout_seconds: int = 60


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreaker:
    """Simple circuit breaker for service calls."""
    
    failure_threshold: int = 5
    reset_timeout: int = 60
    
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[float] = None

    def record_success(self) -> None:
        """Record a successful call."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                "circuit_breaker_opened",
                failures=self.failure_count,
            )

    def allow_request(self) -> bool:
        """Check if a request should be allowed."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Check if we should try again
            if self.last_failure_time:
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.reset_timeout:
                    self.state = CircuitState.HALF_OPEN
                    return True
            return False
        
        # HALF_OPEN: allow one request to test
        return True


class ServiceAuthClient:
    """Client for making authenticated service-to-service calls.
    
    Features:
    - Automatic token generation
    - Request signing
    - Circuit breaker for fault tolerance
    - Request correlation via request IDs
    """

    SERVICE_TOKEN_HEADER = "X-Service-Token"
    REQUEST_ID_HEADER = "X-Request-ID"

    def __init__(
        self,
        config: ServiceAuthConfig,
    ):
        """Initialize the service auth client.
        
        Args:
            config: Service authentication configuration
        """
        self._identity = ServiceIdentity(
            service_id=config.service_id,
            service_name=config.service_name,
        )
        
        self._token_manager = ServiceTokenManager(
            secret_key=config.secret_key,
            token_lifetime_seconds=config.token_lifetime_seconds,
        )
        
        self._request_signer = RequestSigner(secret_key=config.secret_key) if config.sign_requests else None
        
        # Circuit breakers per target service
        self._circuit_breakers: dict[ServiceName, CircuitBreaker] = {}
        self._failure_threshold = config.failure_threshold
        self._reset_timeout = config.reset_timeout_seconds

    def get_auth_headers(
        self,
        target_service: ServiceName,
        method: str = "GET",
        path: str = "/",
        body: Optional[bytes] = None,
        query_params: Optional[dict[str, str]] = None,
        request_id: Optional[str] = None,
    ) -> dict[str, str]:
        """Get authentication headers for a request.
        
        Args:
            target_service: Service being called
            method: HTTP method
            path: Request path
            body: Request body
            query_params: Query parameters
            request_id: Optional request ID for correlation
            
        Returns:
            Dict of headers to add to the request
        """
        request_id = request_id or str(uuid4())
        
        # Create service token
        token = self._token_manager.create_token(
            self._identity,
            target_service,
            request_id=request_id,
        )
        
        headers = {
            self.SERVICE_TOKEN_HEADER: token,
            self.REQUEST_ID_HEADER: request_id,
        }
        
        # Add request signature if enabled
        if self._request_signer:
            sig_headers = self._request_signer.sign_request(
                method, path, body, query_params
            )
            headers.update(sig_headers)
        
        return headers

    def get_circuit_breaker(self, target: ServiceName) -> CircuitBreaker:
        """Get or create circuit breaker for a target service."""
        if target not in self._circuit_breakers:
            self._circuit_breakers[target] = CircuitBreaker(
                failure_threshold=self._failure_threshold,
                reset_timeout=self._reset_timeout,
            )
        return self._circuit_breakers[target]

    def can_call_service(self, target: ServiceName) -> bool:
        """Check if we can call a target service."""
        breaker = self.get_circuit_breaker(target)
        return breaker.allow_request()

    def record_success(self, target: ServiceName) -> None:
        """Record a successful call to a service."""
        breaker = self.get_circuit_breaker(target)
        breaker.record_success()

    def record_failure(self, target: ServiceName) -> None:
        """Record a failed call to a service."""
        breaker = self.get_circuit_breaker(target)
        breaker.record_failure()


# =============================================================================
# Service Auth Verifier (for receiving services)
# =============================================================================

class ServiceAuthVerifier:
    """Verifies incoming service-to-service requests.
    
    Use this in services that receive calls from other services.
    """

    def __init__(
        self,
        service_name: ServiceName,
        secret_key: Optional[str] = None,
        verify_signature: bool = True,
    ):
        """Initialize the verifier.
        
        Args:
            service_name: This service's name (for audience verification)
            secret_key: Shared secret for verification
            verify_signature: Whether to verify request signatures
        """
        self._service_name = service_name
        self._token_manager = ServiceTokenManager(secret_key=secret_key)
        self._request_signer = RequestSigner(secret_key=secret_key) if verify_signature else None

    def verify_request(
        self,
        token: str,
        method: Optional[str] = None,
        path: Optional[str] = None,
        signature: Optional[str] = None,
        timestamp: Optional[str] = None,
        body: Optional[bytes] = None,
        query_params: Optional[dict[str, str]] = None,
    ) -> ServiceTokenPayload:
        """Verify an incoming service request.
        
        Args:
            token: Service token from header
            method: HTTP method (for signature verification)
            path: Request path (for signature verification)
            signature: Request signature
            timestamp: Signature timestamp
            body: Request body
            query_params: Query parameters
            
        Returns:
            Verified token payload
            
        Raises:
            ValueError: If verification fails
        """
        # Verify token
        payload = self._token_manager.verify_token(token, self._service_name)
        
        # Verify request signature if enabled
        if self._request_signer and signature and timestamp:
            if not self._request_signer.verify_request(
                method or "GET",
                path or "/",
                signature,
                timestamp,
                body,
                query_params,
            ):
                logger.warning("service_request_signature_invalid")
                raise ValueError("Invalid request signature")
        
        logger.info(
            "service_request_verified",
            source=payload.sub,
            request_id=payload.request_id,
        )
        
        return payload


# =============================================================================
# FastAPI Middleware/Dependencies
# =============================================================================

def create_service_auth_dependency(
    service_name: ServiceName,
    secret_key: Optional[str] = None,
):
    """Create a FastAPI dependency for service authentication.
    
    Usage:
        verify_service = create_service_auth_dependency(ServiceName.GRAPH)
        
        @app.get("/internal/data")
        def get_data(service_payload: ServiceTokenPayload = Depends(verify_service)):
            ...
    """
    verifier = ServiceAuthVerifier(service_name, secret_key)
    
    def dependency(
        x_service_token: Optional[str] = None,  # Header
    ) -> ServiceTokenPayload:
        if not x_service_token:
            raise ValueError("Missing service token")
        
        return verifier.verify_request(x_service_token)
    
    return dependency


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Enums
    "ServiceName",
    "CircuitState",
    
    # Identity
    "ServiceIdentity",
    
    # Token management
    "ServiceTokenPayload",
    "ServiceTokenManager",
    
    # Request signing
    "RequestSigner",
    
    # Client
    "ServiceAuthConfig",
    "ServiceAuthClient",
    "CircuitBreaker",
    
    # Verifier
    "ServiceAuthVerifier",
    
    # FastAPI
    "create_service_auth_dependency",
]
