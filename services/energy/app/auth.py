"""
Energy Service - Authentication Dependencies

JWT token validation and user extraction for authenticated endpoints.
Created as part of Platform Audit remediation (P1 priority).
"""
from fastapi import Header, HTTPException, status
from typing import Optional
import jwt
import os
import logging

logger = logging.getLogger(__name__)

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"


class AuthenticatedUser:
    """Authenticated user context from JWT token."""
    
    def __init__(self, user_id: str, email: str, tenant_id: str, role: str):
        self.user_id = user_id
        self.email = email
        self.tenant_id = tenant_id
        self.role = role
    
    def __repr__(self):
        return f"<AuthenticatedUser {self.email} ({self.role})>"


def get_current_user(
    authorization: Optional[str] = Header(None)
) -> AuthenticatedUser:
    """
    Extract and validate user from JWT token.
    
    Args:
        authorization: Bearer token from Authorization header
        
    Returns:
        AuthenticatedUser instance with user context
        
    Raises:
        HTTPException: If token is missing, invalid, or expired
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = parts[1]
    
    try:
        # Decode and validate JWT
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM]
        )
        
        # Extract user information
        user_id = payload.get("user_id") or payload.get("sub")
        email = payload.get("email")
        tenant_id = payload.get("tenant_id")
        role = payload.get("role", "user")
        
        if not user_id or not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload: missing user_id or email"
            )
        
        return AuthenticatedUser(
            user_id=user_id,
            email=email,
            tenant_id=tenant_id or "default",
            role=role
        )
        
    except jwt.ExpiredSignatureError:
        logger.warning(f"Expired JWT token: {token[:20]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


def get_optional_user(
    authorization: Optional[str] = Header(None)
) -> Optional[AuthenticatedUser]:
    """
    Extract user from JWT token if provided, otherwise return None.
    
    Used for endpoints that support both authenticated and unauthenticated access.
    """
    if not authorization:
        return None
    
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None
