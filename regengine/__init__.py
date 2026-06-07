"""
RegEngine Python SDK
Official client library for RegEngine FSMA 204 Compliance Platform.
"""

from .client import RegEngineClient
from .exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RegEngineError,
    ValidationError,
)
from .models import (
    CTEType,
    FTLResult,
    ReadinessScore,
    RecallDrill,
    Record,
    TimelineEvent,
    TraceResult,
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
