"""
Custom exceptions for RegEngine Energy SDK.
"""


class RegEngineError(Exception):
    """Base exception for all RegEngine errors."""
    
    def __init__(self, message: str, status_code: int = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(RegEngineError):
    """Raised when API key is invalid or missing."""
    pass


class ValidationError(RegEngineError):
    """Raised when request data fails validation."""
    pass


class SnapshotCreationError(RegEngineError):
    """Raised when snapshot creation fails."""
    pass


class VerificationError(RegEngineError):
    """Raised when chain integrity verification fails."""
    pass


class NetworkError(RegEngineError):
    """Raised when network request fails."""
    pass


class RateLimitError(RegEngineError):
    """Raised when API rate limit is exceeded."""
    pass
