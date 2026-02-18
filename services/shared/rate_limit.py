from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from fastapi import FastAPI

limiter = Limiter(key_func=get_remote_address)

def add_rate_limiting(app: FastAPI):
    """Add standardized rate limiting middleware to the FastAPI app."""
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)
