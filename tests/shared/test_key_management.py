"""
Tests for SEC-021: Cryptographic Key Management.

Tests cover:
- Key generation
- Key storage and retrieval
- Key rotation
- Key lifecycle management
- Key derivation
- Convenience functions
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta

from shared.key_management import (
    # Enums
    KeyType,
    KeyPurpose,
    KeyStatus,
    KeyAlgorithm,
    # Data classes
    KeyMetadata,
    KeyMaterial,
    RotationPolicy,
    # Storage
    InMemoryKeyStorage,
    # Generator
    KeyGenerator,
    # Manager
    KeyManager,
    # Functions
    get_key_manager,
    create_encryption_key,
    create_signing_key,
    create_hmac_key,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def storage():
    """Create test storage."""
    return InMemoryKeyStorage()


@pytest.fixture
def manager(storage):
    """Create test manager."""
    return KeyManager(storage=storage)


@pytest.fixture
def generator():
    """Create key generator."""
    return KeyGenerator()


# =============================================================================
# Test: Enums
# =============================================================================

class TestEnums:
    """Test enum values."""
    
    def test_key_type(self):
        """Should have expected key types."""
        assert KeyType.SYMMETRIC == "symmetric"
        assert KeyType.ASYMMETRIC_RSA == "asymmetric_rsa"
        assert KeyType.ASYMMETRIC_EC == "asymmetric_ec"
    
    def test_key_purpose(self):
        """Should have expected purposes."""
        assert KeyPurpose.ENCRYPTION == "encryption"
        assert KeyPurpose.SIGNING == "signing"
        assert KeyPurpose.AUTHENTICATION == "authentication"
    
    def test_key_status(self):
        """Should have expected statuses."""
        assert KeyStatus.ACTIVE == "active"
        assert KeyStatus.ROTATED == "rotated"
        assert KeyStatus.COMPROMISED == "compromised"
    
    def test_key_algorithm(self):
        """Should have expected algorithms."""
        assert KeyAlgorithm.AES_256_GCM == "aes-256-gcm"
        assert KeyAlgorithm.RSA_4096 == "rsa-4096"
        assert KeyAlgorithm.ECDSA_P256 == "ecdsa-p256"


# =============================================================================
# Test: Key Metadata
# =============================================================================

class TestKeyMetadata:
    """Test KeyMetadata data class."""
    
    def test_creation(self):
        """Should create metadata with defaults."""
        metadata = KeyMetadata(
            key_id="key-123",
            version=1,
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
        )
        
        assert metadata.key_id == "key-123"
        assert metadata.status == KeyStatus.ACTIVE
        assert metadata.auto_rotate is True
    
    def test_is_expired(self):
        """Should detect expired keys."""
        # Not expired
        active = KeyMetadata(
            key_id="key-1",
            version=1,
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        assert active.is_expired() is False
        
        # Expired
        expired = KeyMetadata(
            key_id="key-2",
            version=1,
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        assert expired.is_expired() is True
    
    def test_is_usable(self):
        """Should check if key is usable."""
        # Active and not expired
        usable = KeyMetadata(
            key_id="key-1",
            version=1,
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
            status=KeyStatus.ACTIVE,
        )
        assert usable.is_usable() is True
        
        # Rotated (not usable for new operations)
        rotated = KeyMetadata(
            key_id="key-2",
            version=1,
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
            status=KeyStatus.ROTATED,
        )
        assert rotated.is_usable() is False
    
    def test_needs_rotation(self):
        """Should detect when rotation is needed."""
        # Recently created - no rotation needed
        recent = KeyMetadata(
            key_id="key-1",
            version=1,
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
            rotation_period_days=90,
        )
        assert recent.needs_rotation() is False
        
        # Old key - needs rotation
        old = KeyMetadata(
            key_id="key-2",
            version=1,
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
            created_at=datetime.now(timezone.utc) - timedelta(days=100),
            rotation_period_days=90,
        )
        assert old.needs_rotation() is True
    
    def test_to_dict(self):
        """Should convert to dictionary."""
        metadata = KeyMetadata(
            key_id="key-123",
            version=1,
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
            tenant_id="tenant-1",
        )
        
        data = metadata.to_dict()
        
        assert data["key_id"] == "key-123"
        assert data["key_type"] == "symmetric"
        assert data["algorithm"] == "aes-256-gcm"


# =============================================================================
# Test: Key Material
# =============================================================================

class TestKeyMaterial:
    """Test KeyMaterial data class."""
    
    def test_clear(self):
        """Should securely clear key material."""
        material = KeyMaterial(
            key_id="key-123",
            version=1,
            secret_key=b"secret_key_data",
            private_key=b"private_key_data",
            public_key=b"public_key_data",
        )
        
        material.clear()
        
        assert material.secret_key is None
        assert material.private_key is None
        assert material.public_key is None


# =============================================================================
# Test: Key Generator
# =============================================================================

class TestKeyGenerator:
    """Test KeyGenerator."""
    
    def test_generate_aes_256_key(self, generator):
        """Should generate 256-bit AES key."""
        key = generator.generate_symmetric_key(KeyAlgorithm.AES_256_GCM)
        assert len(key) == 32  # 256 bits
    
    def test_generate_aes_128_key(self, generator):
        """Should generate 128-bit AES key."""
        key = generator.generate_symmetric_key(KeyAlgorithm.AES_128_GCM)
        assert len(key) == 16  # 128 bits
    
    def test_generate_hmac_sha256_key(self, generator):
        """Should generate HMAC-SHA256 key."""
        key = generator.generate_symmetric_key(KeyAlgorithm.HMAC_SHA256)
        assert len(key) == 32
    
    def test_generate_hmac_sha512_key(self, generator):
        """Should generate HMAC-SHA512 key."""
        key = generator.generate_symmetric_key(KeyAlgorithm.HMAC_SHA512)
        assert len(key) == 64
    
    def test_generate_unique_keys(self, generator):
        """Should generate unique keys."""
        key1 = generator.generate_symmetric_key(KeyAlgorithm.AES_256_GCM)
        key2 = generator.generate_symmetric_key(KeyAlgorithm.AES_256_GCM)
        assert key1 != key2
    
    def test_generate_rsa_key_pair(self, generator):
        """Should generate RSA key pair."""
        private_key, public_key = generator.generate_rsa_key_pair(
            KeyAlgorithm.RSA_2048
        )
        
        assert private_key is not None
        assert public_key is not None
        assert b"BEGIN PRIVATE KEY" in private_key
        assert b"BEGIN PUBLIC KEY" in public_key
    
    def test_generate_ec_key_pair(self, generator):
        """Should generate EC key pair."""
        private_key, public_key = generator.generate_ec_key_pair(
            KeyAlgorithm.ECDSA_P256
        )
        
        assert private_key is not None
        assert public_key is not None
        assert b"BEGIN PRIVATE KEY" in private_key
        assert b"BEGIN PUBLIC KEY" in public_key
    
    def test_derive_key(self, generator):
        """Should derive key from master key."""
        master = generator.generate_symmetric_key(KeyAlgorithm.AES_256_GCM)
        salt = generator.generate_salt()
        info = b"context-info"
        
        derived = generator.derive_key(master, salt, info)
        
        assert len(derived) == 32
        assert derived != master
    
    def test_derive_key_deterministic(self, generator):
        """Should derive same key with same inputs."""
        master = generator.generate_symmetric_key(KeyAlgorithm.AES_256_GCM)
        salt = b"fixed_salt_value_32_bytes_long!!"
        info = b"context"
        
        derived1 = generator.derive_key(master, salt, info)
        derived2 = generator.derive_key(master, salt, info)
        
        assert derived1 == derived2
    
    def test_derive_key_from_password(self, generator):
        """Should derive key from password."""
        password = "secure_password_123"
        salt = generator.generate_salt()
        
        key = generator.derive_key_from_password(password, salt, iterations=10000)
        
        assert len(key) == 32
    
    def test_generate_salt(self, generator):
        """Should generate random salt."""
        salt1 = generator.generate_salt()
        salt2 = generator.generate_salt()
        
        assert len(salt1) == 32
        assert salt1 != salt2
    
    def test_generate_key_id(self, generator):
        """Should generate unique key IDs."""
        id1 = generator.generate_key_id()
        id2 = generator.generate_key_id()
        
        assert id1.startswith("key_")
        assert id1 != id2


# =============================================================================
# Test: In-Memory Storage
# =============================================================================

class TestInMemoryKeyStorage:
    """Test InMemoryKeyStorage."""
    
    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, storage):
        """Should store and retrieve keys."""
        metadata = KeyMetadata(
            key_id="key-123",
            version=1,
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
        )
        material = KeyMaterial(
            key_id="key-123",
            version=1,
            secret_key=b"test_secret_key",
        )
        
        await storage.store_key(metadata, material)
        
        result = await storage.get_key("key-123")
        assert result is not None
        retrieved_metadata, retrieved_material = result
        assert retrieved_metadata.key_id == "key-123"
        assert retrieved_material.secret_key == b"test_secret_key"
    
    @pytest.mark.asyncio
    async def test_get_specific_version(self, storage):
        """Should retrieve specific version."""
        # Store v1
        await storage.store_key(
            KeyMetadata(
                key_id="key-123", version=1,
                key_type=KeyType.SYMMETRIC,
                algorithm=KeyAlgorithm.AES_256_GCM,
                purpose=KeyPurpose.ENCRYPTION,
            ),
            KeyMaterial(key_id="key-123", version=1, secret_key=b"v1_key"),
        )
        
        # Store v2
        await storage.store_key(
            KeyMetadata(
                key_id="key-123", version=2,
                key_type=KeyType.SYMMETRIC,
                algorithm=KeyAlgorithm.AES_256_GCM,
                purpose=KeyPurpose.ENCRYPTION,
            ),
            KeyMaterial(key_id="key-123", version=2, secret_key=b"v2_key"),
        )
        
        # Get v1 specifically
        result = await storage.get_key("key-123", version=1)
        assert result is not None
        _, material = result
        assert material.secret_key == b"v1_key"
        
        # Get latest (v2)
        result = await storage.get_key("key-123")
        _, material = result
        assert material.secret_key == b"v2_key"
    
    @pytest.mark.asyncio
    async def test_list_keys(self, storage):
        """Should list keys with filters."""
        # Store various keys
        await storage.store_key(
            KeyMetadata(
                key_id="enc-1", version=1,
                key_type=KeyType.SYMMETRIC,
                algorithm=KeyAlgorithm.AES_256_GCM,
                purpose=KeyPurpose.ENCRYPTION,
                tenant_id="tenant-1",
            ),
            KeyMaterial(key_id="enc-1", version=1),
        )
        await storage.store_key(
            KeyMetadata(
                key_id="sign-1", version=1,
                key_type=KeyType.ASYMMETRIC_EC,
                algorithm=KeyAlgorithm.ECDSA_P256,
                purpose=KeyPurpose.SIGNING,
                tenant_id="tenant-1",
            ),
            KeyMaterial(key_id="sign-1", version=1),
        )
        await storage.store_key(
            KeyMetadata(
                key_id="enc-2", version=1,
                key_type=KeyType.SYMMETRIC,
                algorithm=KeyAlgorithm.AES_256_GCM,
                purpose=KeyPurpose.ENCRYPTION,
                tenant_id="tenant-2",
            ),
            KeyMaterial(key_id="enc-2", version=1),
        )
        
        # List all
        all_keys = await storage.list_keys()
        assert len(all_keys) == 3
        
        # Filter by tenant
        tenant1_keys = await storage.list_keys(tenant_id="tenant-1")
        assert len(tenant1_keys) == 2
        
        # Filter by purpose
        signing_keys = await storage.list_keys(purpose=KeyPurpose.SIGNING)
        assert len(signing_keys) == 1
    
    @pytest.mark.asyncio
    async def test_delete_key(self, storage):
        """Should delete key and clear material."""
        await storage.store_key(
            KeyMetadata(
                key_id="key-123", version=1,
                key_type=KeyType.SYMMETRIC,
                algorithm=KeyAlgorithm.AES_256_GCM,
                purpose=KeyPurpose.ENCRYPTION,
            ),
            KeyMaterial(key_id="key-123", version=1, secret_key=b"secret"),
        )
        
        await storage.delete_key("key-123")
        
        result = await storage.get_key("key-123")
        assert result is None


# =============================================================================
# Test: Key Manager
# =============================================================================

class TestKeyManager:
    """Test KeyManager."""
    
    @pytest.mark.asyncio
    async def test_create_symmetric_key(self, manager):
        """Should create symmetric encryption key."""
        metadata = await manager.create_key(
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
            tenant_id="tenant-1",
        )
        
        assert metadata.key_id is not None
        assert metadata.version == 1
        assert metadata.status == KeyStatus.ACTIVE
        assert metadata.tenant_id == "tenant-1"
    
    @pytest.mark.asyncio
    async def test_create_rsa_key(self, manager):
        """Should create RSA key pair."""
        metadata = await manager.create_key(
            key_type=KeyType.ASYMMETRIC_RSA,
            algorithm=KeyAlgorithm.RSA_2048,
            purpose=KeyPurpose.SIGNING,
        )
        
        assert metadata.key_type == KeyType.ASYMMETRIC_RSA
        
        # Verify both keys exist
        result = await manager.get_key(metadata.key_id)
        assert result is not None
        _, material = result
        assert material.private_key is not None
        assert material.public_key is not None
    
    @pytest.mark.asyncio
    async def test_create_ec_key(self, manager):
        """Should create EC key pair."""
        metadata = await manager.create_key(
            key_type=KeyType.ASYMMETRIC_EC,
            algorithm=KeyAlgorithm.ECDSA_P256,
            purpose=KeyPurpose.SIGNING,
        )
        
        assert metadata.key_type == KeyType.ASYMMETRIC_EC
    
    @pytest.mark.asyncio
    async def test_get_active_key(self, manager):
        """Should get key only if active."""
        metadata = await manager.create_key(
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
        )
        
        result = await manager.get_active_key(metadata.key_id)
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_get_public_key(self, manager):
        """Should get only public key."""
        metadata = await manager.create_key(
            key_type=KeyType.ASYMMETRIC_EC,
            algorithm=KeyAlgorithm.ECDSA_P256,
            purpose=KeyPurpose.SIGNING,
        )
        
        public_key = await manager.get_public_key(metadata.key_id)
        
        assert public_key is not None
        assert b"PUBLIC KEY" in public_key
    
    @pytest.mark.asyncio
    async def test_rotate_key(self, manager):
        """Should rotate key to new version."""
        # Create original
        original = await manager.create_key(
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
        )
        
        # Rotate
        rotated = await manager.rotate_key(original.key_id, reason="test rotation")
        
        assert rotated is not None
        assert rotated.key_id == original.key_id
        assert rotated.version == 2
        assert rotated.status == KeyStatus.ACTIVE
        
        # Old version should be marked as rotated
        old_metadata = await manager._storage.get_metadata(original.key_id, version=1)
        assert old_metadata.status == KeyStatus.ROTATED
    
    @pytest.mark.asyncio
    async def test_revoke_key(self, manager):
        """Should revoke compromised key."""
        metadata = await manager.create_key(
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
        )
        
        result = await manager.revoke_key(
            metadata.key_id,
            reason="Potential compromise detected",
        )
        
        assert result is True
        
        # Key should be marked compromised
        updated = await manager._storage.get_metadata(metadata.key_id)
        assert updated.status == KeyStatus.COMPROMISED
    
    @pytest.mark.asyncio
    async def test_destroy_key(self, manager):
        """Should destroy key."""
        metadata = await manager.create_key(
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
        )
        
        result = await manager.destroy_key(metadata.key_id)
        
        assert result is True
        
        # Key should be gone
        result = await manager.get_key(metadata.key_id)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_derive_key(self, manager):
        """Should derive key from master."""
        # Create master key
        master = await manager.create_key(
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.DERIVATION,
        )
        
        # Derive child key
        derived = await manager.derive_key(
            master_key_id=master.key_id,
            context="user-encryption",
            purpose=KeyPurpose.ENCRYPTION,
        )
        
        assert derived is not None
        assert derived.key_type == KeyType.DERIVED
        assert "Derived from" in derived.description
    
    @pytest.mark.asyncio
    async def test_check_rotation_needed(self, manager):
        """Should find keys needing rotation."""
        # Create old key
        old = await manager.create_key(
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
            rotation_period_days=1,  # Short period for testing
        )
        
        # Manually age the key
        await manager._storage.update_metadata(
            old.key_id,
            old.version,
            {"created_at": datetime.now(timezone.utc) - timedelta(days=10)},
        )
        
        # Check
        needs_rotation = await manager.check_rotation_needed()
        
        assert len(needs_rotation) >= 1
        assert any(k.key_id == old.key_id for k in needs_rotation)
    
    @pytest.mark.asyncio
    async def test_rotation_policy(self, manager):
        """Should apply rotation policies."""
        # Create key
        key = await manager.create_key(
            key_type=KeyType.SYMMETRIC,
            algorithm=KeyAlgorithm.AES_256_GCM,
            purpose=KeyPurpose.ENCRYPTION,
        )
        
        # Age the key
        await manager._storage.update_metadata(
            key.key_id,
            key.version,
            {"created_at": datetime.now(timezone.utc) - timedelta(days=100)},
        )
        
        # Add policy
        policy = RotationPolicy(
            policy_id="policy-1",
            name="90-day rotation",
            rotation_period_days=90,
        )
        manager.add_rotation_policy(policy)
        
        # Apply policies
        rotated = await manager.apply_rotation_policies()
        
        assert len(rotated) >= 1


# =============================================================================
# Test: Convenience Functions
# =============================================================================

class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_key_manager(self):
        """Should return singleton."""
        manager1 = get_key_manager()
        manager2 = get_key_manager()
        assert manager1 is manager2
    
    @pytest.mark.asyncio
    async def test_create_encryption_key(self):
        """Should create AES encryption key."""
        KeyManager.configure()
        
        metadata = await create_encryption_key(tenant_id="tenant-1")
        
        assert metadata.key_type == KeyType.SYMMETRIC
        assert metadata.algorithm == KeyAlgorithm.AES_256_GCM
        assert metadata.purpose == KeyPurpose.ENCRYPTION
    
    @pytest.mark.asyncio
    async def test_create_signing_key(self):
        """Should create signing key."""
        KeyManager.configure()
        
        metadata = await create_signing_key(algorithm=KeyAlgorithm.ECDSA_P256)
        
        assert metadata.key_type == KeyType.ASYMMETRIC_EC
        assert metadata.purpose == KeyPurpose.SIGNING
    
    @pytest.mark.asyncio
    async def test_create_hmac_key(self):
        """Should create HMAC key."""
        KeyManager.configure()
        
        metadata = await create_hmac_key()
        
        assert metadata.key_type == KeyType.HMAC
        assert metadata.algorithm == KeyAlgorithm.HMAC_SHA256
        assert metadata.purpose == KeyPurpose.AUTHENTICATION
