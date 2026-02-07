"""
API key authentication for Construction service.
"""

from fastapi import HTTPException, Header, status
from typing import Optional


async def require_api_key(
    x_regengine_api_key: Optional[str] = Header(None, alias="X-RegEngine-API-Key")
) -> str:
    if not x_regengine_api_key or not x_regengine_api_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-RegEngine-API-Key header"
        )
    return x_regengine_api_key
