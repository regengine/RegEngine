"""Tests for security headers middleware."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.security_headers import (
    DevelopmentSecurityHeaders,
    ProductionSecurityHeaders,
    SecurityHeadersMiddleware,
)


@pytest.fixture
def app():
    """Create a simple FastAPI app for testing."""
    app = FastAPI()
    
    @app.get("/test")
    def test_endpoint():
        return {"status": "ok"}
    
    @app.get("/cached")
    def cached_endpoint():
        from starlette.responses import JSONResponse
        response = JSONResponse({"cached": True})
        response.headers["Cache-Control"] = "max-age=3600"
        return response
    
    return app


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    def test_basic_security_headers(self, app):
        """Test that basic security headers are added."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "Referrer-Policy" in response.headers
        assert "Permissions-Policy" in response.headers

    def test_hsts_disabled_by_default(self, app):
        """Test HSTS is disabled by default."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert "Strict-Transport-Security" not in response.headers

    def test_hsts_enabled(self, app):
        """Test HSTS when enabled."""
        app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=True)
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert "Strict-Transport-Security" in response.headers
        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=" in hsts

    def test_hsts_with_subdomains(self, app):
        """Test HSTS with includeSubDomains."""
        app.add_middleware(
            SecurityHeadersMiddleware,
            hsts_enabled=True,
            hsts_include_subdomains=True,
        )
        client = TestClient(app)
        
        response = client.get("/test")
        
        hsts = response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" in hsts

    def test_hsts_with_preload(self, app):
        """Test HSTS with preload directive."""
        app.add_middleware(
            SecurityHeadersMiddleware,
            hsts_enabled=True,
            hsts_preload=True,
        )
        client = TestClient(app)
        
        response = client.get("/test")
        
        hsts = response.headers["Strict-Transport-Security"]
        assert "preload" in hsts

    def test_csp_enabled_by_default(self, app):
        """Test CSP is enabled by default."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert "Content-Security-Policy" in response.headers

    def test_csp_disabled(self, app):
        """Test CSP can be disabled."""
        app.add_middleware(SecurityHeadersMiddleware, csp_enabled=False)
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert "Content-Security-Policy" not in response.headers

    def test_custom_csp_policy(self, app):
        """Test custom CSP policy."""
        custom_csp = "default-src 'none'; script-src 'self'"
        app.add_middleware(SecurityHeadersMiddleware, csp_policy=custom_csp)
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert response.headers["Content-Security-Policy"] == custom_csp

    def test_custom_frame_options(self, app):
        """Test custom X-Frame-Options."""
        app.add_middleware(SecurityHeadersMiddleware, frame_options="SAMEORIGIN")
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"

    def test_custom_referrer_policy(self, app):
        """Test custom Referrer-Policy."""
        app.add_middleware(SecurityHeadersMiddleware, referrer_policy="no-referrer")
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert response.headers["Referrer-Policy"] == "no-referrer"

    def test_default_cache_control(self, app):
        """Test default cache control for API responses."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)
        
        response = client.get("/test")
        
        cache_control = response.headers["Cache-Control"]
        assert "no-store" in cache_control
        assert "private" in cache_control

    def test_preserves_existing_cache_control(self, app):
        """Test existing Cache-Control is not overwritten."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)
        
        response = client.get("/cached")
        
        assert response.headers["Cache-Control"] == "max-age=3600"

    def test_permissions_policy(self, app):
        """Test Permissions-Policy header."""
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)
        
        response = client.get("/test")
        
        policy = response.headers["Permissions-Policy"]
        assert "camera=()" in policy
        assert "microphone=()" in policy
        assert "geolocation=()" in policy


class TestDevelopmentSecurityHeaders:
    """Tests for development security headers preset."""

    def test_hsts_disabled(self, app):
        """Test HSTS is disabled in dev."""
        app.add_middleware(DevelopmentSecurityHeaders)
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert "Strict-Transport-Security" not in response.headers

    def test_relaxed_csp(self, app):
        """Test relaxed CSP for development."""
        app.add_middleware(DevelopmentSecurityHeaders)
        client = TestClient(app)
        
        response = client.get("/test")
        
        csp = response.headers["Content-Security-Policy"]
        assert "unsafe-inline" in csp
        assert "unsafe-eval" in csp


class TestProductionSecurityHeaders:
    """Tests for production security headers preset."""

    def test_hsts_enabled(self, app):
        """Test HSTS is enabled in production."""
        app.add_middleware(ProductionSecurityHeaders)
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert "Strict-Transport-Security" in response.headers

    def test_hsts_includes_subdomains(self, app):
        """Test HSTS includes subdomains in production."""
        app.add_middleware(ProductionSecurityHeaders)
        client = TestClient(app)
        
        response = client.get("/test")
        
        hsts = response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" in hsts

    def test_strict_csp(self, app):
        """Test strict CSP in production."""
        app.add_middleware(ProductionSecurityHeaders)
        client = TestClient(app)
        
        response = client.get("/test")
        
        csp = response.headers["Content-Security-Policy"]
        assert "unsafe-eval" not in csp


class TestEnvironmentConfiguration:
    """Tests for environment variable configuration."""

    def test_hsts_from_env(self, app, monkeypatch):
        """Test HSTS configuration from environment."""
        monkeypatch.setenv("SECURITY_HSTS_ENABLED", "true")
        monkeypatch.setenv("SECURITY_HSTS_MAX_AGE", "7200")
        
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)
        
        response = client.get("/test")
        
        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=7200" in hsts

    def test_frame_options_from_env(self, app, monkeypatch):
        """Test frame options from environment."""
        monkeypatch.setenv("SECURITY_FRAME_OPTIONS", "SAMEORIGIN")
        
        app.add_middleware(SecurityHeadersMiddleware)
        client = TestClient(app)
        
        response = client.get("/test")
        
        assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
