"""Security headers middleware for FastAPI applications.

This module provides middleware that adds security headers to all HTTP responses,
protecting against common web vulnerabilities.

Headers Added:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Strict-Transport-Security (HSTS)
- Content-Security-Policy (CSP)
- Referrer-Policy
- Permissions-Policy

Usage:
    from shared.security_headers import SecurityHeadersMiddleware
    
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to all responses.
    
    Configuration via environment variables:
    - SECURITY_HSTS_ENABLED: Enable HSTS (default: false in dev, true recommended for prod)
    - SECURITY_HSTS_MAX_AGE: HSTS max-age in seconds (default: 31536000 = 1 year)
    - SECURITY_HSTS_INCLUDE_SUBDOMAINS: Include subdomains (default: true)
    - SECURITY_HSTS_PRELOAD: Enable preload (default: false)
    - SECURITY_CSP_ENABLED: Enable CSP header (default: true)
    - SECURITY_FRAME_OPTIONS: X-Frame-Options value (default: DENY)
    """
    
    def __init__(
        self,
        app,
        hsts_enabled: Optional[bool] = None,
        hsts_max_age: Optional[int] = None,
        hsts_include_subdomains: Optional[bool] = None,
        hsts_preload: Optional[bool] = None,
        csp_enabled: Optional[bool] = None,
        csp_policy: Optional[str] = None,
        frame_options: Optional[str] = None,
        referrer_policy: Optional[str] = None,
    ):
        """Initialize security headers middleware.
        
        Args:
            app: The ASGI application.
            hsts_enabled: Enable HSTS header.
            hsts_max_age: HSTS max-age in seconds.
            hsts_include_subdomains: Include subdomains in HSTS.
            hsts_preload: Enable HSTS preload.
            csp_enabled: Enable Content-Security-Policy.
            csp_policy: Custom CSP policy string.
            frame_options: X-Frame-Options value.
            referrer_policy: Referrer-Policy value.
        """
        super().__init__(app)
        
        # HSTS configuration
        self.hsts_enabled = hsts_enabled if hsts_enabled is not None else \
            os.getenv("SECURITY_HSTS_ENABLED", "false").lower() in ("true", "1", "yes")
        self.hsts_max_age = hsts_max_age if hsts_max_age is not None else \
            int(os.getenv("SECURITY_HSTS_MAX_AGE", "31536000"))
        self.hsts_include_subdomains = hsts_include_subdomains if hsts_include_subdomains is not None else \
            os.getenv("SECURITY_HSTS_INCLUDE_SUBDOMAINS", "true").lower() in ("true", "1", "yes")
        self.hsts_preload = hsts_preload if hsts_preload is not None else \
            os.getenv("SECURITY_HSTS_PRELOAD", "false").lower() in ("true", "1", "yes")
        
        # CSP configuration
        self.csp_enabled = csp_enabled if csp_enabled is not None else \
            os.getenv("SECURITY_CSP_ENABLED", "true").lower() in ("true", "1", "yes")
        self.csp_policy = csp_policy or os.getenv("SECURITY_CSP_POLICY") or self._default_csp()
        
        # Other headers
        self.frame_options = frame_options or os.getenv("SECURITY_FRAME_OPTIONS", "DENY")
        self.referrer_policy = referrer_policy or os.getenv("SECURITY_REFERRER_POLICY", "strict-origin-when-cross-origin")
    
    def _default_csp(self) -> str:
        """Generate default Content-Security-Policy.
        
        Returns:
            CSP policy string suitable for API services.
        """
        return "; ".join([
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",  # For Swagger UI
            "img-src 'self' data: https:",
            "font-src 'self'",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ])
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and add security headers to response."""
        response = await call_next(request)
        
        # Always add these headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = self.frame_options
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = self.referrer_policy
        
        # Permissions-Policy (formerly Feature-Policy)
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )
        
        # HSTS (only enable in production with HTTPS)
        if self.hsts_enabled:
            hsts_value = f"max-age={self.hsts_max_age}"
            if self.hsts_include_subdomains:
                hsts_value += "; includeSubDomains"
            if self.hsts_preload:
                hsts_value += "; preload"
            response.headers["Strict-Transport-Security"] = hsts_value
        
        # Content-Security-Policy
        if self.csp_enabled:
            response.headers["Content-Security-Policy"] = self.csp_policy
        
        # Cache control for API responses
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        
        return response


def get_security_headers_middleware(**kwargs) -> type:
    """Factory function to create configured middleware.
    
    This allows passing configuration when adding middleware:
    
        app.add_middleware(
            get_security_headers_middleware(hsts_enabled=True)
        )
    """
    class ConfiguredSecurityHeadersMiddleware(SecurityHeadersMiddleware):
        def __init__(self, app):
            super().__init__(app, **kwargs)
    
    return ConfiguredSecurityHeadersMiddleware


# Preset configurations for common environments

class DevelopmentSecurityHeaders(SecurityHeadersMiddleware):
    """Security headers preset for development environment.
    
    - HSTS disabled (no HTTPS in dev)
    - Relaxed CSP for hot reload
    """
    
    def __init__(self, app):
        super().__init__(
            app,
            hsts_enabled=False,
            csp_enabled=True,
            csp_policy=(
                "default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "connect-src 'self' ws: wss: http: https:; "
                "img-src 'self' data: https:; "
                "frame-ancestors 'self'"
            ),
        )


class ProductionSecurityHeaders(SecurityHeadersMiddleware):
    """Security headers preset for production environment.
    
    - HSTS enabled with 1 year max-age
    - Strict CSP
    """
    
    def __init__(self, app):
        super().__init__(
            app,
            hsts_enabled=True,
            hsts_max_age=31536000,
            hsts_include_subdomains=True,
            hsts_preload=False,  # Enable after testing
            csp_enabled=True,
        )
