"""
SEC-021: Cryptographic Key Management.

Secure key generation, storage, rotation, and lifecycle management including:
- Key generation with proper entropy
- Key rotation policies
- Key versioning and archival
- Secure key derivation
- Hardware security module (HSM) integration support
"""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Use cryptography library for secure operations
try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa, ec, padding
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================

class KeyType(str, Enum):
    """Types of cryptographic keys."""
    SYMMETRIC = "symmetric"  # AES keys
    ASYMMETRIC_RSA = "asymmetric_rsa"  # RSA key pairs
    ASYMMETRIC_EC = "asymmetric_ec"  # Elliptic curve key pairs
    HMAC = "hmac"  # HMAC keys
    DERIVED = "derived"  # Keys derived from master keys


class KeyPurpose(str, Enum):
    """Purpose/usage of keys."""
    ENCRYPTION = "encryption"  # Data encryption
    SIGNING = "signing"  # Digital signatures
    AUTHENTICATION = "authentication"  # API/session auth
    KEY_WRAPPING = "key_wrapping"  # Encrypting other keys
    DERIVATION = "derivation"  # Deriving other keys


class KeyStatus(str, Enum):
    """Key lifecycle status."""
    ACTIVE = "active"  # In use for encrypt/decrypt
    INACTIVE = "inactive"  # Not for new operations, can still decrypt
    PENDING_ROTATION = "pending_rotation"  # Scheduled for rotation
    ROTATED = "rotated"  # Replaced by newer version
    COMPROMISED = "compromised"  # Potentially leaked
    DESTROYED = "destroyed"  # Securely deleted


class KeyAlgorithm(str, Enum):
    """Supported cryptographic algorithms."""
    AES_256_GCM = "aes-256-gcm"
    AES_128_GCM = "aes-128-gcm"
    RSA_2048 = "rsa-2048"
    RSA_4096 = "rsa-4096"
    ECDSA_P256 = "ecdsa-p256"
    ECDSA_P384 = "ecdsa-p384"
    HMAC_SHA256 = "hmac-sha256"
    HMAC_SHA512 = "hmac-sha512"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class KeyMetadata:
    """Metadata about a cryptographic key."""
    key_id: str
    version: int
    key_type: KeyType
    algorithm: KeyAlgorithm
    purpose: KeyPurpose
    status: KeyStatus = KeyStatus.ACTIVE
    
    # Lifecycle dates
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    activated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    rotated_at: Optional[datetime] = None
    destroyed_at: Optional[datetime] = None
    
    # Rotation settings
    rotation_period_days: int = 90
    auto_rotate: bool = True
    
    # Access control
    tenant_id: Optional[str] = None
    owner: Optional[str] = None
    allowed_services: List[str] = field(default_factory=list)
    
    # Audit
    created_by: Optional[str] = None
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    
    # Additional metadata
    description: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """Check if key has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_usable(self) -> bool:
        """Check if key can be used for new operations."""
        if self.status not in {KeyStatus.ACTIVE}:
            return False
        if self.is_expired():
            return False
        return True
    
    def needs_rotation(self) -> bool:
        """Check if key should be rotated."""
        if not self.auto_rotate:
            return False
        if self.status != KeyStatus.ACTIVE:
            return False
        
        rotation_due = self.created_at + timedelta(days=self.rotation_period_days)
        return datetime.now(timezone.utc) > rotation_due
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (without sensitive data)."""
        return {
            "key_id": self.key_id,
            "version": self.version,
            "key_type": self.key_type.value,
            "algorithm": self.algorithm.value,
            "purpose": self.purpose.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "rotation_period_days": self.rotation_period_days,
            "auto_rotate": self.auto_rotate,
            "tenant_id": self.tenant_id,
            "owner": self.owner,
            "description": self.description,
            "tags": self.tags,
        }


@dataclass
class KeyMaterial:
    """Container for actual key material."""
    key_id: str
    version: int
    
    # Symmetric key (for AES, HMAC)
    secret_key: Optional[bytes] = None
    
    # Asymmetric keys (for RSA, EC)
    private_key: Optional[bytes] = None
    public_key: Optional[bytes] = None
    
    # Key derivation info
    salt: Optional[bytes] = None
    derived_from: Optional[str] = None
    
    def clear(self) -> None:
        """Securely clear key material from memory."""
        if self.secret_key:
            # Overwrite with zeros
            self.secret_key = b'\x00' * len(self.secret_key)
            self.secret_key = None
        if self.private_key:
            self.private_key = b'\x00' * len(self.private_key)
            self.private_key = None
        if self.public_key:
            self.public_key = None
        if self.salt:
            self.salt = None


@dataclass
class RotationPolicy:
    """Policy for automatic key rotation."""
    policy_id: str
    name: str
    rotation_period_days: int = 90
    overlap_period_days: int = 7  # Keep old key active during transition
    auto_destroy_after_days: int = 365  # Destroy old keys after this period
    notify_before_days: int = 14  # Notify before rotation
    enabled: bool = True
    
    # Filters
    key_types: List[KeyType] = field(default_factory=list)
    key_purposes: List[KeyPurpose] = field(default_factory=list)
    tenant_ids: List[str] = field(default_factory=list)


# =============================================================================
# Key Storage Backend
# =============================================================================

class KeyStorage(ABC):
    """Abstract base class for key storage backends."""
    
    @abstractmethod
    async def store_key(
        self,
        metadata: KeyMetadata,
        material: KeyMaterial,
    ) -> None:
        """Store key metadata and material."""
        pass
    
    @abstractmethod
    async def get_key(
        self,
        key_id: str,
        version: Optional[int] = None,
    ) -> Optional[Tuple[KeyMetadata, KeyMaterial]]:
        """Retrieve key by ID and optional version."""
        pass
    
    @abstractmethod
    async def get_metadata(
        self,
        key_id: str,
        version: Optional[int] = None,
    ) -> Optional[KeyMetadata]:
        """Retrieve only metadata (no key material)."""
        pass
    
    @abstractmethod
    async def update_metadata(
        self,
        key_id: str,
        version: int,
        updates: Dict[str, Any],
    ) -> None:
        """Update key metadata."""
        pass
    
    @abstractmethod
    async def list_keys(
        self,
        tenant_id: Optional[str] = None,
        key_type: Optional[KeyType] = None,
        purpose: Optional[KeyPurpose] = None,
        status: Optional[KeyStatus] = None,
    ) -> List[KeyMetadata]:
        """List keys matching criteria."""
        pass
    
    @abstractmethod
    async def delete_key(
        self,
        key_id: str,
        version: Optional[int] = None,
    ) -> None:
        """Delete key (mark as destroyed or remove)."""
        pass


class InMemoryKeyStorage(KeyStorage):
    """In-memory key storage for development/testing."""
    
    def __init__(self):
        self._keys: Dict[str, Dict[int, Tuple[KeyMetadata, KeyMaterial]]] = {}
        self._lock = asyncio.Lock()
    
    async def store_key(
        self,
        metadata: KeyMetadata,
        material: KeyMaterial,
    ) -> None:
        """Store key."""
        async with self._lock:
            if metadata.key_id not in self._keys:
                self._keys[metadata.key_id] = {}
            self._keys[metadata.key_id][metadata.version] = (metadata, material)
    
    async def get_key(
        self,
        key_id: str,
        version: Optional[int] = None,
    ) -> Optional[Tuple[KeyMetadata, KeyMaterial]]:
        """Get key by ID."""
        async with self._lock:
            if key_id not in self._keys:
                return None
            
            versions = self._keys[key_id]
            if version is not None:
                return versions.get(version)
            
            # Return latest version
            if not versions:
                return None
            latest_version = max(versions.keys())
            return versions[latest_version]
    
    async def get_metadata(
        self,
        key_id: str,
        version: Optional[int] = None,
    ) -> Optional[KeyMetadata]:
        """Get only metadata."""
        result = await self.get_key(key_id, version)
        if result:
            return result[0]
        return None
    
    async def update_metadata(
        self,
        key_id: str,
        version: int,
        updates: Dict[str, Any],
    ) -> None:
        """Update metadata."""
        async with self._lock:
            if key_id not in self._keys:
                return
            if version not in self._keys[key_id]:
                return
            
            metadata, material = self._keys[key_id][version]
            for key, value in updates.items():
                if hasattr(metadata, key):
                    setattr(metadata, key, value)
    
    async def list_keys(
        self,
        tenant_id: Optional[str] = None,
        key_type: Optional[KeyType] = None,
        purpose: Optional[KeyPurpose] = None,
        status: Optional[KeyStatus] = None,
    ) -> List[KeyMetadata]:
        """List keys matching criteria."""
        async with self._lock:
            results = []
            
            for key_id, versions in self._keys.items():
                # Get latest version
                if not versions:
                    continue
                latest = max(versions.keys())
                metadata, _ = versions[latest]
                
                # Apply filters
                if tenant_id and metadata.tenant_id != tenant_id:
                    continue
                if key_type and metadata.key_type != key_type:
                    continue
                if purpose and metadata.purpose != purpose:
                    continue
                if status and metadata.status != status:
                    continue
                
                results.append(metadata)
            
            return results
    
    async def delete_key(
        self,
        key_id: str,
        version: Optional[int] = None,
    ) -> None:
        """Delete key."""
        async with self._lock:
            if key_id not in self._keys:
                return
            
            if version is not None:
                if version in self._keys[key_id]:
                    # Clear key material
                    _, material = self._keys[key_id][version]
                    material.clear()
                    del self._keys[key_id][version]
            else:
                # Delete all versions
                for v in list(self._keys[key_id].keys()):
                    _, material = self._keys[key_id][v]
                    material.clear()
                del self._keys[key_id]


# =============================================================================
# Key Generator
# =============================================================================

class KeyGenerator:
    """Generate cryptographic keys with proper entropy."""
    
    @staticmethod
    def generate_symmetric_key(algorithm: KeyAlgorithm) -> bytes:
        """Generate a symmetric key."""
        if algorithm in {KeyAlgorithm.AES_256_GCM, KeyAlgorithm.HMAC_SHA256}:
            return secrets.token_bytes(32)  # 256 bits
        elif algorithm in {KeyAlgorithm.AES_128_GCM}:
            return secrets.token_bytes(16)  # 128 bits
        elif algorithm == KeyAlgorithm.HMAC_SHA512:
            return secrets.token_bytes(64)  # 512 bits
        else:
            raise ValueError(f"Unsupported algorithm for symmetric key: {algorithm}")
    
    @staticmethod
    def generate_rsa_key_pair(
        algorithm: KeyAlgorithm,
    ) -> Tuple[bytes, bytes]:
        """Generate RSA key pair. Returns (private_key, public_key) in PEM format."""
        if not CRYPTOGRAPHY_AVAILABLE:
            raise RuntimeError("cryptography library not available")
        
        if algorithm == KeyAlgorithm.RSA_2048:
            key_size = 2048
        elif algorithm == KeyAlgorithm.RSA_4096:
            key_size = 4096
        else:
            raise ValueError(f"Unsupported RSA algorithm: {algorithm}")
        
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
            backend=default_backend(),
        )
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        
        return private_pem, public_pem
    
    @staticmethod
    def generate_ec_key_pair(
        algorithm: KeyAlgorithm,
    ) -> Tuple[bytes, bytes]:
        """Generate EC key pair. Returns (private_key, public_key) in PEM format."""
        if not CRYPTOGRAPHY_AVAILABLE:
            raise RuntimeError("cryptography library not available")
        
        if algorithm == KeyAlgorithm.ECDSA_P256:
            curve = ec.SECP256R1()
        elif algorithm == KeyAlgorithm.ECDSA_P384:
            curve = ec.SECP384R1()
        else:
            raise ValueError(f"Unsupported EC algorithm: {algorithm}")
        
        private_key = ec.generate_private_key(curve, default_backend())
        
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        
        return private_pem, public_pem
    
    @staticmethod
    def derive_key(
        master_key: bytes,
        salt: bytes,
        info: bytes,
        length: int = 32,
    ) -> bytes:
        """Derive a key from master key using HKDF."""
        if not CRYPTOGRAPHY_AVAILABLE:
            raise RuntimeError("cryptography library not available")
        
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=length,
            salt=salt,
            info=info,
            backend=default_backend(),
        )
        return hkdf.derive(master_key)
    
    @staticmethod
    def derive_key_from_password(
        password: str,
        salt: bytes,
        iterations: int = 600000,
        length: int = 32,
    ) -> bytes:
        """Derive a key from password using PBKDF2."""
        if not CRYPTOGRAPHY_AVAILABLE:
            raise RuntimeError("cryptography library not available")
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=length,
            salt=salt,
            iterations=iterations,
            backend=default_backend(),
        )
        return kdf.derive(password.encode())
    
    @staticmethod
    def generate_salt(length: int = 32) -> bytes:
        """Generate random salt."""
        return secrets.token_bytes(length)
    
    @staticmethod
    def generate_key_id() -> str:
        """Generate unique key ID."""
        return f"key_{uuid.uuid4().hex}"


# =============================================================================
# Key Manager
# =============================================================================

class KeyManager:
    """
    Central manager for cryptographic key lifecycle.
    
    Handles key generation, storage, rotation, and destruction
    with proper security controls.
    """
    
    _instance: Optional["KeyManager"] = None
    
    def __init__(
        self,
        storage: Optional[KeyStorage] = None,
    ):
        self._storage = storage or InMemoryKeyStorage()
        self._generator = KeyGenerator()
        self._rotation_policies: Dict[str, RotationPolicy] = {}
        self._cache: Dict[str, Tuple[KeyMetadata, KeyMaterial]] = {}
        self._cache_ttl = timedelta(minutes=5)
        self._lock = asyncio.Lock()
    
    @classmethod
    def configure(
        cls,
        storage: Optional[KeyStorage] = None,
    ) -> "KeyManager":
        """Configure singleton instance."""
        cls._instance = cls(storage=storage)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "KeyManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def create_key(
        self,
        key_type: KeyType,
        algorithm: KeyAlgorithm,
        purpose: KeyPurpose,
        tenant_id: Optional[str] = None,
        owner: Optional[str] = None,
        rotation_period_days: int = 90,
        auto_rotate: bool = True,
        expires_at: Optional[datetime] = None,
        description: Optional[str] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> KeyMetadata:
        """
        Create a new cryptographic key.
        
        Returns metadata (key material stored securely).
        """
        key_id = self._generator.generate_key_id()
        version = 1
        
        # Generate key material based on type
        material = KeyMaterial(key_id=key_id, version=version)
        
        if key_type == KeyType.SYMMETRIC:
            material.secret_key = self._generator.generate_symmetric_key(algorithm)
        elif key_type == KeyType.HMAC:
            material.secret_key = self._generator.generate_symmetric_key(algorithm)
        elif key_type == KeyType.ASYMMETRIC_RSA:
            private_key, public_key = self._generator.generate_rsa_key_pair(algorithm)
            material.private_key = private_key
            material.public_key = public_key
        elif key_type == KeyType.ASYMMETRIC_EC:
            private_key, public_key = self._generator.generate_ec_key_pair(algorithm)
            material.private_key = private_key
            material.public_key = public_key
        else:
            raise ValueError(f"Unsupported key type: {key_type}")
        
        # Create metadata
        now = datetime.now(timezone.utc)
        metadata = KeyMetadata(
            key_id=key_id,
            version=version,
            key_type=key_type,
            algorithm=algorithm,
            purpose=purpose,
            status=KeyStatus.ACTIVE,
            created_at=now,
            activated_at=now,
            expires_at=expires_at,
            rotation_period_days=rotation_period_days,
            auto_rotate=auto_rotate,
            tenant_id=tenant_id,
            owner=owner,
            description=description,
            tags=tags or {},
        )
        
        # Store
        await self._storage.store_key(metadata, material)
        
        logger.info(
            "Created key: %s (type=%s, algorithm=%s, purpose=%s)",
            key_id, key_type.value, algorithm.value, purpose.value,
        )
        
        return metadata
    
    async def get_key(
        self,
        key_id: str,
        version: Optional[int] = None,
    ) -> Optional[Tuple[KeyMetadata, KeyMaterial]]:
        """
        Retrieve a key by ID.
        
        Returns (metadata, material) or None if not found.
        """
        result = await self._storage.get_key(key_id, version)
        
        if result:
            metadata, material = result
            # Update usage stats
            await self._storage.update_metadata(
                key_id,
                metadata.version,
                {
                    "last_used_at": datetime.now(timezone.utc),
                    "use_count": metadata.use_count + 1,
                },
            )
        
        return result
    
    async def get_active_key(
        self,
        key_id: str,
    ) -> Optional[Tuple[KeyMetadata, KeyMaterial]]:
        """Get key only if it's active and not expired."""
        result = await self.get_key(key_id)
        if result:
            metadata, material = result
            if metadata.is_usable():
                return result
        return None
    
    async def get_public_key(
        self,
        key_id: str,
        version: Optional[int] = None,
    ) -> Optional[bytes]:
        """Get only the public key (for asymmetric keys)."""
        result = await self._storage.get_key(key_id, version)
        if result:
            _, material = result
            return material.public_key
        return None
    
    async def rotate_key(
        self,
        key_id: str,
        reason: Optional[str] = None,
    ) -> Optional[KeyMetadata]:
        """
        Rotate a key by creating a new version.
        
        The old version is marked as ROTATED but kept for decryption.
        """
        # Get current key
        current = await self._storage.get_key(key_id)
        if not current:
            return None
        
        old_metadata, old_material = current
        
        # Create new version
        new_version = old_metadata.version + 1
        new_material = KeyMaterial(key_id=key_id, version=new_version)
        
        # Generate new key material
        if old_metadata.key_type == KeyType.SYMMETRIC:
            new_material.secret_key = self._generator.generate_symmetric_key(
                old_metadata.algorithm
            )
        elif old_metadata.key_type == KeyType.HMAC:
            new_material.secret_key = self._generator.generate_symmetric_key(
                old_metadata.algorithm
            )
        elif old_metadata.key_type == KeyType.ASYMMETRIC_RSA:
            private_key, public_key = self._generator.generate_rsa_key_pair(
                old_metadata.algorithm
            )
            new_material.private_key = private_key
            new_material.public_key = public_key
        elif old_metadata.key_type == KeyType.ASYMMETRIC_EC:
            private_key, public_key = self._generator.generate_ec_key_pair(
                old_metadata.algorithm
            )
            new_material.private_key = private_key
            new_material.public_key = public_key
        
        # Create new metadata
        now = datetime.now(timezone.utc)
        new_metadata = KeyMetadata(
            key_id=key_id,
            version=new_version,
            key_type=old_metadata.key_type,
            algorithm=old_metadata.algorithm,
            purpose=old_metadata.purpose,
            status=KeyStatus.ACTIVE,
            created_at=now,
            activated_at=now,
            rotation_period_days=old_metadata.rotation_period_days,
            auto_rotate=old_metadata.auto_rotate,
            tenant_id=old_metadata.tenant_id,
            owner=old_metadata.owner,
            description=old_metadata.description,
            tags=old_metadata.tags,
        )
        
        # Mark old key as rotated
        await self._storage.update_metadata(
            key_id,
            old_metadata.version,
            {
                "status": KeyStatus.ROTATED,
                "rotated_at": now,
            },
        )
        
        # Store new version
        await self._storage.store_key(new_metadata, new_material)
        
        logger.info(
            "Rotated key: %s (v%d -> v%d, reason=%s)",
            key_id, old_metadata.version, new_version, reason,
        )
        
        return new_metadata
    
    async def revoke_key(
        self,
        key_id: str,
        reason: str,
        version: Optional[int] = None,
    ) -> bool:
        """
        Revoke a key (mark as compromised).
        
        Compromised keys should not be used for any operations.
        """
        metadata = await self._storage.get_metadata(key_id, version)
        if not metadata:
            return False
        
        await self._storage.update_metadata(
            key_id,
            metadata.version,
            {"status": KeyStatus.COMPROMISED},
        )
        
        logger.warning(
            "Revoked key: %s v%d (reason=%s)",
            key_id, metadata.version, reason,
        )
        
        return True
    
    async def destroy_key(
        self,
        key_id: str,
        version: Optional[int] = None,
    ) -> bool:
        """
        Securely destroy a key.
        
        Key material is cleared and key is marked as destroyed.
        """
        await self._storage.delete_key(key_id, version)
        
        logger.info("Destroyed key: %s (version=%s)", key_id, version)
        
        return True
    
    async def list_keys(
        self,
        tenant_id: Optional[str] = None,
        key_type: Optional[KeyType] = None,
        purpose: Optional[KeyPurpose] = None,
        status: Optional[KeyStatus] = None,
    ) -> List[KeyMetadata]:
        """List keys matching criteria."""
        return await self._storage.list_keys(
            tenant_id=tenant_id,
            key_type=key_type,
            purpose=purpose,
            status=status,
        )
    
    async def check_rotation_needed(self) -> List[KeyMetadata]:
        """Find keys that need rotation."""
        all_keys = await self._storage.list_keys(status=KeyStatus.ACTIVE)
        return [k for k in all_keys if k.needs_rotation()]
    
    async def derive_key(
        self,
        master_key_id: str,
        context: str,
        purpose: KeyPurpose,
        tenant_id: Optional[str] = None,
    ) -> KeyMetadata:
        """
        Derive a new key from an existing master key.
        
        Uses HKDF for secure key derivation.
        """
        # Get master key
        master = await self.get_active_key(master_key_id)
        if not master:
            raise ValueError(f"Master key not found or not active: {master_key_id}")
        
        master_metadata, master_material = master
        if not master_material.secret_key:
            raise ValueError("Master key has no secret key material")
        
        # Generate salt and derive
        salt = self._generator.generate_salt()
        info = context.encode()
        derived_secret = self._generator.derive_key(
            master_material.secret_key,
            salt,
            info,
        )
        
        # Create new key entry
        key_id = self._generator.generate_key_id()
        now = datetime.now(timezone.utc)
        
        metadata = KeyMetadata(
            key_id=key_id,
            version=1,
            key_type=KeyType.DERIVED,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=purpose,
            status=KeyStatus.ACTIVE,
            created_at=now,
            activated_at=now,
            tenant_id=tenant_id or master_metadata.tenant_id,
            description=f"Derived from {master_key_id} for {context}",
        )
        
        material = KeyMaterial(
            key_id=key_id,
            version=1,
            secret_key=derived_secret,
            salt=salt,
            derived_from=master_key_id,
        )
        
        await self._storage.store_key(metadata, material)
        
        return metadata
    
    def add_rotation_policy(self, policy: RotationPolicy) -> None:
        """Add a key rotation policy."""
        self._rotation_policies[policy.policy_id] = policy
    
    async def apply_rotation_policies(self) -> List[KeyMetadata]:
        """Apply rotation policies and rotate keys as needed."""
        rotated = []
        
        for policy in self._rotation_policies.values():
            if not policy.enabled:
                continue
            
            # Find matching keys
            keys = await self._storage.list_keys(status=KeyStatus.ACTIVE)
            
            for key in keys:
                # Check if policy applies
                if policy.key_types and key.key_type not in policy.key_types:
                    continue
                if policy.key_purposes and key.purpose not in policy.key_purposes:
                    continue
                if policy.tenant_ids and key.tenant_id not in policy.tenant_ids:
                    continue
                
                # Check if rotation needed based on policy
                rotation_due = key.created_at + timedelta(days=policy.rotation_period_days)
                if datetime.now(timezone.utc) > rotation_due:
                    new_key = await self.rotate_key(
                        key.key_id,
                        reason=f"Policy: {policy.name}",
                    )
                    if new_key:
                        rotated.append(new_key)
        
        return rotated


# =============================================================================
# Convenience Functions
# =============================================================================

def get_key_manager() -> KeyManager:
    """Get the singleton key manager."""
    return KeyManager.get_instance()


async def create_encryption_key(
    tenant_id: Optional[str] = None,
    **kwargs,
) -> KeyMetadata:
    """Create a new AES-256 encryption key."""
    manager = get_key_manager()
    return await manager.create_key(
        key_type=KeyType.SYMMETRIC,
        algorithm=KeyAlgorithm.AES_256_GCM,
        purpose=KeyPurpose.ENCRYPTION,
        tenant_id=tenant_id,
        **kwargs,
    )


async def create_signing_key(
    algorithm: KeyAlgorithm = KeyAlgorithm.ECDSA_P256,
    tenant_id: Optional[str] = None,
    **kwargs,
) -> KeyMetadata:
    """Create a new signing key."""
    manager = get_key_manager()
    
    if algorithm in {KeyAlgorithm.RSA_2048, KeyAlgorithm.RSA_4096}:
        key_type = KeyType.ASYMMETRIC_RSA
    else:
        key_type = KeyType.ASYMMETRIC_EC
    
    return await manager.create_key(
        key_type=key_type,
        algorithm=algorithm,
        purpose=KeyPurpose.SIGNING,
        tenant_id=tenant_id,
        **kwargs,
    )


async def create_hmac_key(
    tenant_id: Optional[str] = None,
    **kwargs,
) -> KeyMetadata:
    """Create a new HMAC key for authentication."""
    manager = get_key_manager()
    return await manager.create_key(
        key_type=KeyType.HMAC,
        algorithm=KeyAlgorithm.HMAC_SHA256,
        purpose=KeyPurpose.AUTHENTICATION,
        tenant_id=tenant_id,
        **kwargs,
    )
