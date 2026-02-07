"""
RegEngine SDK Exceptions
"""


class RegEngineError(Exception):
    """Base exception for RegEngine SDK errors."""
    
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class AuthenticationError(RegEngineError):
    """Raised when API key is invalid or expired (HTTP 401)."""
    pass


class RateLimitError(RegEngineError):
    """Raised when rate limit is exceeded (HTTP 429)."""
    pass


class NotFoundError(RegEngineError):
    """Raised when a resource is not found (HTTP 404)."""
    pass


class ValidationError(RegEngineError):
    """Raised when request validation fails (HTTP 400)."""
    pass
