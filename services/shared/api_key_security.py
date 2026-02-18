"""
SEC-041: API Key Security.

Secure API key management with generation, validation, rotation,
and secure storage patterns.
"""

import hashlib
import hmac
import secrets
import time
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class KeyStatus(str, Enum):
    """API key status."""
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING = "pending"


class KeyScope(str, Enum):
    """API key scope levels."""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    FULL = "full"


@dataclass
class APIKeyConfig:
    """Configuration for API key security."""
    
    # Key generation
    key_length: int = 32
    prefix: str = "rk"
    version: str = "1"
    
    # Validation
    min_key_length: int = 16
    max_key_length: int = 128
    allowed_chars: str = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    
    # Expiration
    default_ttl_days: int = 90
    max_ttl_days: int = 365
    
    # Rate limiting
    default_rate_limit: int = 1000
    rate_limit_window_seconds: int = 3600
    
    # Security
    hash_algorithm: str = "sha256"
    require_https: bool = True


@dataclass
class APIKey:
    """Represents an API key."""
    
    key_id: str
    key_hash: str
    prefix: str
    version: str
    status: KeyStatus = KeyStatus.ACTIVE
    scope: KeyScope = KeyScope.READ
    
    # Metadata
    name: str = ""
    description: str = ""
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    
    # Timestamps
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    last_used_at: Optional[float] = None
    revoked_at: Optional[float] = None
    
    # Limits
    rate_limit: int = 1000
    allowed_ips: set = field(default_factory=set)
    allowed_origins: set = field(default_factory=set)
    
    @property
    def is_expired(self) -> bool:
        """Check if key is expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """Check if key is valid."""
        return self.status == KeyStatus.ACTIVE and not self.is_expired
    
    def to_safe_dict(self) -> dict:
        """Convert to dict without sensitive data."""
        return {
            "key_id": self.key_id,
            "prefix": self.prefix,
            "status": self.status.value,
            "scope": self.scope.value,
            "name": self.name,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_used_at": self.last_used_at,
        }


@dataclass
class KeyValidationResult:
    """Result of key validation."""
    
    is_valid: bool
    key: Optional[APIKey] = None
    error: Optional[str] = None
    
    @property
    def key_id(self) -> Optional[str]:
        """Get key ID if valid."""
        return self.key.key_id if self.key else None


class APIKeyGenerator:
    """Generates secure API keys."""
    
    def __init__(self, config: Optional[APIKeyConfig] = None):
        self.config = config or APIKeyConfig()
    
    def generate(
        self,
        scope: KeyScope = KeyScope.READ,
        ttl_days: Optional[int] = None,
        **metadata: Any,
    ) -> tuple[str, APIKey]:
        """
        Generate a new API key.
        
        Returns tuple of (raw_key, api_key_object).
        The raw_key should only be shown once to the user.
        """
        # Generate random bytes
        key_bytes = secrets.token_bytes(self.config.key_length)
        key_b64 = secrets.token_urlsafe(self.config.key_length)
        
        # Generate key ID
        key_id = secrets.token_hex(8)
        
        # Build full key with prefix
        raw_key = f"{self.config.prefix}_{self.config.version}_{key_b64}"
        
        # Hash the key for storage
        key_hash = self._hash_key(raw_key)
        
        # Calculate expiration
        expires_at = None
        if ttl_days is not None:
            expires_at = time.time() + (ttl_days * 86400)
        elif self.config.default_ttl_days > 0:
            expires_at = time.time() + (self.config.default_ttl_days * 86400)
        
        # Create key object
        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            prefix=self.config.prefix,
            version=self.config.version,
            scope=scope,
            expires_at=expires_at,
            name=metadata.get("name", ""),
            description=metadata.get("description", ""),
            tenant_id=metadata.get("tenant_id"),
            user_id=metadata.get("user_id"),
            rate_limit=metadata.get("rate_limit", self.config.default_rate_limit),
        )
        
        return raw_key, api_key
    
    def _hash_key(self, raw_key: str) -> str:
        """Hash a raw key for storage."""
        if self.config.hash_algorithm == "sha256":
            return hashlib.sha256(raw_key.encode()).hexdigest()
        elif self.config.hash_algorithm == "sha512":
            return hashlib.sha512(raw_key.encode()).hexdigest()
        else:
            return hashlib.sha256(raw_key.encode()).hexdigest()
    
    def generate_key_pair(
        self,
        scope: KeyScope = KeyScope.READ,
        **metadata: Any,
    ) -> tuple[str, str, APIKey]:
        """
        Generate API key with separate secret.
        
        Returns tuple of (key_id, secret, api_key_object).
        """
        key_id = f"{self.config.prefix}_{secrets.token_hex(8)}"
        secret = secrets.token_urlsafe(self.config.key_length)
        
        # Hash secret for storage
        secret_hash = self._hash_key(secret)
        
        api_key = APIKey(
            key_id=key_id,
            key_hash=secret_hash,
            prefix=self.config.prefix,
            version=self.config.version,
            scope=scope,
            **{k: v for k, v in metadata.items() if k in [
                "name", "description", "tenant_id", "user_id", "rate_limit"
            ]},
        )
        
        return key_id, secret, api_key


class APIKeyValidator:
    """Validates API keys."""
    
    def __init__(self, config: Optional[APIKeyConfig] = None):
        self.config = config or APIKeyConfig()
        # Pattern for valid key format
        self._key_pattern = re.compile(
            r'^[a-zA-Z]{2,8}_[0-9]+_[a-zA-Z0-9_-]+$'
        )
    
    def validate_format(self, raw_key: str) -> tuple[bool, Optional[str]]:
        """
        Validate key format.
        
        Returns tuple of (is_valid, error_message).
        """
        if not raw_key:
            return False, "Key is empty"
        
        if len(raw_key) < self.config.min_key_length:
            return False, "Key too short"
        
        if len(raw_key) > self.config.max_key_length:
            return False, "Key too long"
        
        if not self._key_pattern.match(raw_key):
            return False, "Invalid key format"
        
        return True, None
    
    def validate_key(
        self,
        raw_key: str,
        stored_key: APIKey,
    ) -> KeyValidationResult:
        """Validate a raw key against stored key."""
        # Check format
        is_valid_format, error = self.validate_format(raw_key)
        if not is_valid_format:
            return KeyValidationResult(is_valid=False, error=error)
        
        # Check status
        if stored_key.status == KeyStatus.REVOKED:
            return KeyValidationResult(
                is_valid=False,
                key=stored_key,
                error="Key has been revoked",
            )
        
        if stored_key.status == KeyStatus.EXPIRED or stored_key.is_expired:
            return KeyValidationResult(
                is_valid=False,
                key=stored_key,
                error="Key has expired",
            )
        
        # Verify hash using constant-time comparison
        expected_hash = stored_key.key_hash
        actual_hash = self._hash_key(raw_key)
        
        if not hmac.compare_digest(expected_hash, actual_hash):
            return KeyValidationResult(
                is_valid=False,
                error="Invalid key",
            )
        
        return KeyValidationResult(is_valid=True, key=stored_key)
    
    def _hash_key(self, raw_key: str) -> str:
        """Hash a raw key."""
        if self.config.hash_algorithm == "sha256":
            return hashlib.sha256(raw_key.encode()).hexdigest()
        elif self.config.hash_algorithm == "sha512":
            return hashlib.sha512(raw_key.encode()).hexdigest()
        else:
            return hashlib.sha256(raw_key.encode()).hexdigest()
    
    def check_ip_allowed(
        self,
        key: APIKey,
        client_ip: str,
    ) -> bool:
        """Check if IP is allowed for key."""
        if not key.allowed_ips:
            return True
        return client_ip in key.allowed_ips
    
    def check_origin_allowed(
        self,
        key: APIKey,
        origin: str,
    ) -> bool:
        """Check if origin is allowed for key."""
        if not key.allowed_origins:
            return True
        return origin in key.allowed_origins


class APIKeyRotator:
    """Handles API key rotation."""
    
    def __init__(
        self,
        generator: Optional[APIKeyGenerator] = None,
        config: Optional[APIKeyConfig] = None,
    ):
        self.config = config or APIKeyConfig()
        self.generator = generator or APIKeyGenerator(self.config)
    
    def rotate(
        self,
        old_key: APIKey,
        grace_period_hours: int = 24,
    ) -> tuple[str, APIKey, APIKey]:
        """
        Rotate an API key.
        
        Returns tuple of (new_raw_key, new_key, old_key_updated).
        Old key gets a grace period before expiration.
        """
        # Generate new key with same metadata
        new_raw_key, new_key = self.generator.generate(
            scope=old_key.scope,
            name=f"{old_key.name} (rotated)",
            description=old_key.description,
            tenant_id=old_key.tenant_id,
            user_id=old_key.user_id,
            rate_limit=old_key.rate_limit,
        )
        
        # Copy allowed IPs and origins
        new_key.allowed_ips = old_key.allowed_ips.copy()
        new_key.allowed_origins = old_key.allowed_origins.copy()
        
        # Update old key with grace period
        old_key.expires_at = time.time() + (grace_period_hours * 3600)
        old_key.name = f"{old_key.name} (deprecated)"
        
        return new_raw_key, new_key, old_key
    
    def revoke(self, key: APIKey, reason: str = "") -> APIKey:
        """Revoke an API key immediately."""
        key.status = KeyStatus.REVOKED
        key.revoked_at = time.time()
        key.description = f"{key.description} [Revoked: {reason}]".strip()
        return key
    
    def should_rotate(
        self,
        key: APIKey,
        days_before_expiry: int = 30,
    ) -> bool:
        """Check if key should be rotated."""
        if key.expires_at is None:
            return False
        
        threshold = key.expires_at - (days_before_expiry * 86400)
        return time.time() > threshold


class APIKeySecurityService:
    """Comprehensive API key security service."""
    
    _instance: Optional["APIKeySecurityService"] = None
    
    def __init__(self, config: Optional[APIKeyConfig] = None):
        self.config = config or APIKeyConfig()
        self.generator = APIKeyGenerator(self.config)
        self.validator = APIKeyValidator(self.config)
        self.rotator = APIKeyRotator(self.generator, self.config)
        
        # In-memory storage (replace with persistent storage)
        self._keys: dict[str, APIKey] = {}
    
    @classmethod
    def get_instance(cls) -> "APIKeySecurityService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def configure(
        cls,
        config: APIKeyConfig,
    ) -> "APIKeySecurityService":
        """Configure and return singleton."""
        cls._instance = cls(config)
        return cls._instance
    
    def create_key(
        self,
        scope: KeyScope = KeyScope.READ,
        **metadata: Any,
    ) -> tuple[str, APIKey]:
        """Create a new API key."""
        raw_key, api_key = self.generator.generate(scope=scope, **metadata)
        self._keys[api_key.key_id] = api_key
        return raw_key, api_key
    
    def validate(
        self,
        raw_key: str,
        client_ip: Optional[str] = None,
        origin: Optional[str] = None,
    ) -> KeyValidationResult:
        """Validate an API key."""
        # Find key by hash
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        stored_key = None
        
        for key in self._keys.values():
            if key.key_hash == key_hash:
                stored_key = key
                break
        
        if not stored_key:
            return KeyValidationResult(is_valid=False, error="Key not found")
        
        # Validate key
        result = self.validator.validate_key(raw_key, stored_key)
        
        if not result.is_valid:
            return result
        
        # Check IP restriction
        if client_ip and not self.validator.check_ip_allowed(stored_key, client_ip):
            return KeyValidationResult(
                is_valid=False,
                key=stored_key,
                error="IP not allowed",
            )
        
        # Check origin restriction
        if origin and not self.validator.check_origin_allowed(stored_key, origin):
            return KeyValidationResult(
                is_valid=False,
                key=stored_key,
                error="Origin not allowed",
            )
        
        # Update last used
        stored_key.last_used_at = time.time()
        
        return KeyValidationResult(is_valid=True, key=stored_key)
    
    def rotate_key(
        self,
        key_id: str,
        grace_period_hours: int = 24,
    ) -> Optional[tuple[str, APIKey]]:
        """Rotate a key by ID."""
        if key_id not in self._keys:
            return None
        
        old_key = self._keys[key_id]
        new_raw_key, new_key, updated_old = self.rotator.rotate(
            old_key,
            grace_period_hours,
        )
        
        self._keys[new_key.key_id] = new_key
        self._keys[key_id] = updated_old
        
        return new_raw_key, new_key
    
    def revoke_key(self, key_id: str, reason: str = "") -> bool:
        """Revoke a key by ID."""
        if key_id not in self._keys:
            return False
        
        self.rotator.revoke(self._keys[key_id], reason)
        return True
    
    def get_key(self, key_id: str) -> Optional[APIKey]:
        """Get key by ID."""
        return self._keys.get(key_id)
    
    def list_keys(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[KeyStatus] = None,
    ) -> list[APIKey]:
        """List keys with optional filters."""
        keys = list(self._keys.values())
        
        if tenant_id:
            keys = [k for k in keys if k.tenant_id == tenant_id]
        
        if user_id:
            keys = [k for k in keys if k.user_id == user_id]
        
        if status:
            keys = [k for k in keys if k.status == status]
        
        return keys
    
    def cleanup_expired(self) -> int:
        """Remove expired keys. Returns count removed."""
        expired_ids = [
            key_id for key_id, key in self._keys.items()
            if key.is_expired and key.status != KeyStatus.REVOKED
        ]
        
        for key_id in expired_ids:
            del self._keys[key_id]
        
        return len(expired_ids)


# Convenience functions
def get_api_key_service() -> APIKeySecurityService:
    """Get API key service instance."""
    return APIKeySecurityService.get_instance()


def create_api_key(
    scope: KeyScope = KeyScope.READ,
    **metadata: Any,
) -> tuple[str, APIKey]:
    """Create a new API key."""
    return get_api_key_service().create_key(scope=scope, **metadata)


def validate_api_key(
    raw_key: str,
    client_ip: Optional[str] = None,
    origin: Optional[str] = None,
) -> KeyValidationResult:
    """Validate an API key."""
    return get_api_key_service().validate(raw_key, client_ip, origin)
