"""
API key authentication for Automotive service.
"""

from fastapi import HTTPException, Header, status
from typing import Optional

from .config import settings


async def require_api_key(
    x_regengine_api_key: Optional[str] = Header(None, alias="X-RegEngine-API-Key")
) -> str:
    """
    Verify API key from X-RegEngine-API-Key header.
    
    Raises:
        HTTPException: 401 if key is missing or invalid.
    
    Returns:
        str: The validated API key.
    """
    if not x_regengine_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-RegEngine-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    # TODO: Validate against database or secrets manager
    if not x_regengine_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"}
        )
    
    return x_regengine_api_key
