"""
Energy Service - Unit Tests for Authentication

Tests JWT token validation, user extraction, and authentication dependencies.
"""
import pytest
from fastapi import HTTPException
from app.auth import get_current_user, get_optional_user, AuthenticatedUser, JWT_SECRET, JWT_ALGORITHM
import jwt
import os


class TestAuthentication:
    """Tests for JWT authentication and user extraction."""
    
    def test_valid_jwt_token_extraction(self):
        """Test successful user extraction from valid JWT."""
        # Create valid token
        payload = {
            "user_id": "user-123",
            "email": "test@example.com",
            "tenant_id": "tenant-456",
            "role": "engineer"
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        # Simulate Authorization header
        class MockHeader:
            authorization = f"Bearer {token}"
        
        # Extract user
        user = get_current_user(f"Bearer {token}")
        
        assert user.user_id == "user-123"
        assert user.email == "test@example.com"
        assert user.tenant_id == "tenant-456"
        assert user.role == "engineer"
    
    def test_missing_authorization_header(self):
        """Test that missing auth header raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(None)
        
        assert exc_info.value.status_code == 401
        assert "Missing authorization header" in exc_info.value.detail
    
    def test_invalid_header_format(self):
        """Test that invalid header format raises 401."""
        with pytest.raises(HTTPException) as exc_info:
            get_current_user("InvalidToken")
        
        assert exc_info.value.status_code == 401
        assert "Invalid authorization header format" in exc_info.value.detail
    
    def test_expired_token(self):
        """Test that expired token raises 401."""
        import time
        from datetime import datetime, timedelta
        
        # Create expired token
        payload = {
            "user_id": "user-123",
            "email": "test@example.com",
            "exp": datetime.utcnow() - timedelta(hours=1)  # Expired 1 hour ago
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(f"Bearer {token}")
        
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()
    
    def test_invalid_token_signature(self):
        """Test that token with wrong signature raises 401."""
        # Create token with different secret
        payload = {"user_id": "user-123", "email": "test@example.com"}
        token = jwt.encode(payload, "wrong-secret", algorithm=JWT_ALGORITHM)
        
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(f"Bearer {token}")
        
        assert exc_info.value.status_code == 401
    
    def test_missing_user_id_in_token(self):
        """Test that token without user_id raises 401."""
        payload = {"email": "test@example.com"}  # Missing user_id
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        with pytest.raises(HTTPException) as exc_info:
            get_current_user(f"Bearer {token}")
        
        assert exc_info.value.status_code == 401
        assert "missing user_id" in exc_info.value.detail.lower()
    
    def test_optional_user_with_no_token(self):
        """Test optional user returns None when no token provided."""
        user = get_optional_user(None)
        assert user is None
    
    def test_optional_user_with_valid_token(self):
        """Test optional user returns user when valid token provided."""
        payload = {
            "user_id": "user-123",
            "email": "test@example.com"
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        user = get_optional_user(f"Bearer {token}")
        
        assert user is not None
        assert user.user_id == "user-123"
        assert user.email == "test@example.com"
    
    def test_sub_field_as_user_id_fallback(self):
        """Test that 'sub' field can be used as user_id fallback."""
        payload = {
            "sub": "user-789",  # Using 'sub' instead of 'user_id'
            "email": "test@example.com"
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        user = get_current_user(f"Bearer {token}")
        
        assert user.user_id == "user-789"
    
    def test_default_tenant_when_missing(self):
        """Test that tenant defaults to 'default' when not in token."""
        payload = {
            "user_id": "user-123",
            "email": "test@example.com"
            # No tenant_id specified
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        user = get_current_user(f"Bearer {token}")
        
        assert user.tenant_id == "default"
    
    def test_default_role_when_missing(self):
        """Test that role defaults to 'user' when not in token."""
        payload = {
            "user_id": "user-123",
            "email": "test@example.com"
            # No role specified
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        
        user = get_current_user(f"Bearer {token}")
        
        assert user.role == "user"
