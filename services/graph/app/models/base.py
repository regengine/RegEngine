from datetime import datetime, timezone
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    """Standard metadata for all Graph API responses."""

    request_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = "1.0.0"


class ResponseEnvelope(BaseModel, Generic[T]):
    """Standard envelope for all Graph API responses."""

    data: T
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
