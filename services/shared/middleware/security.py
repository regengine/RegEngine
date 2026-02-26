from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

def add_security(app: FastAPI):
    """Add CORS and TrustedHost security middleware to the FastAPI app."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "https://*.regengine.co",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8002",
            "http://localhost:8400",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*.regengine.co", "localhost", "testserver"])
