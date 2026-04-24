"""
RegEngine Python SDK
Official client library for RegEngine FSMA 204 Compliance Platform.
"""

from .client import RegEngineClient
from .models import (
    Record,
    TraceResult, 
    TimelineEvent,
    FTLResult,
    RecallDrill,
    ReadinessScore,
    CTEType,
)
from .exceptions import (
    RegEngineError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    ValidationError,
)

__version__ = "0.1.0.dev0"
__all__ = [
    "RegEngineClient",
    "Record",
    "TraceResult",
    "TimelineEvent", 
    "FTLResult",
    "RecallDrill",
    "ReadinessScore",
    "CTEType",
    "RegEngineError",
    "AuthenticationError",
    "RateLimitError",
    "NotFoundError",
    "ValidationError",
]
