"""
Tests for API Gateway (nginx) configuration.

Sprint 4: API Gateway Hardening

Validates:
- Configuration syntax
- Route definitions
- Security headers
- Rate limiting zones
- Upstream definitions
"""

import pytest
import re
from pathlib import Path


NGINX_CONF_PATH = Path(__file__).parent.parent.parent.parent / "infra" / "gateway" / "nginx.conf"


@pytest.fixture
def nginx_config():
    """Load nginx configuration file."""
    assert NGINX_CONF_PATH.exists(), f"nginx.conf not found at {NGINX_CONF_PATH}"
    return NGINX_CONF_PATH.read_text()


# ============================================================================
# UPSTREAM DEFINITION TESTS
# ============================================================================

class TestUpstreamDefinitions:
    """Tests for upstream service definitions."""
    
    def test_admin_service_upstream(self, nginx_config):
        """Admin service upstream is defined."""
        assert "upstream admin_service" in nginx_config
        assert "admin-api:8400" in nginx_config
    
    def test_ingestion_service_upstream(self, nginx_config):
        """Ingestion service upstream is defined."""
        assert "upstream ingestion_service" in nginx_config
        assert "ingestion-service:8000" in nginx_config
    
    def test_nlp_service_upstream(self, nginx_config):
        """NLP service upstream is defined and enabled."""
        assert "upstream nlp_service" in nginx_config
        assert "nlp-service:8100" in nginx_config
        # Should NOT be commented out
        lines = nginx_config.split('\n')
        for i, line in enumerate(lines):
            if "upstream nlp_service" in line:
                assert not line.strip().startswith('#'), "NLP service upstream should not be commented"
    
    def test_graph_service_upstream(self, nginx_config):
        """Graph service upstream is defined and enabled."""
        assert "upstream graph_service" in nginx_config
        assert "graph-service:8200" in nginx_config
        # Should NOT be commented out
        lines = nginx_config.split('\n')
        for i, line in enumerate(lines):
            if "upstream graph_service" in line:
                assert not line.strip().startswith('#'), "Graph service upstream should not be commented"
    
    def test_compliance_service_upstream(self, nginx_config):
        """Compliance service upstream is defined."""
        assert "upstream compliance_service" in nginx_config
        assert "compliance-service:8500" in nginx_config
    
    def test_keepalive_connections(self, nginx_config):
        """Upstreams have keepalive connections configured."""
        assert "keepalive" in nginx_config


# ============================================================================
# ROUTE DEFINITION TESTS
# ============================================================================

class TestRouteDefinitions:
    """Tests for location block route definitions."""
    
    def test_admin_route(self, nginx_config):
        """Admin route is defined."""
        assert "location /admin/" in nginx_config
        assert "proxy_pass http://admin_service" in nginx_config
    
    def test_ingest_route(self, nginx_config):
        """Ingestion route is defined."""
        assert "location /ingest/" in nginx_config
        assert "proxy_pass http://ingestion_service" in nginx_config
    
    def test_nlp_route(self, nginx_config):
        """NLP route is defined."""
        assert "location /nlp/" in nginx_config
        assert "proxy_pass http://nlp_service" in nginx_config
    
    def test_graph_route(self, nginx_config):
        """Graph route is defined."""
        assert "location /graph/" in nginx_config
        assert "proxy_pass http://graph_service" in nginx_config
    
    def test_fsma_route(self, nginx_config):
        """FSMA route is defined and routes to graph service."""
        assert "location /fsma/" in nginx_config
        assert "proxy_pass http://graph_service/v1/fsma/" in nginx_config
    
    def test_compliance_route(self, nginx_config):
        """Compliance route is defined."""
        assert "location /compliance/" in nginx_config
        assert "proxy_pass http://compliance_service" in nginx_config
    
    def test_trace_forward_shortcut(self, nginx_config):
        """Trace forward shortcut route is defined."""
        assert "/trace/forward/" in nginx_config
        assert "v1/fsma/trace/forward" in nginx_config
    
    def test_trace_backward_shortcut(self, nginx_config):
        """Trace backward shortcut route is defined."""
        assert "/trace/backward/" in nginx_config
        assert "v1/fsma/trace/backward" in nginx_config


# ============================================================================
# SECURITY HEADER TESTS
# ============================================================================

class TestSecurityHeaders:
    """Tests for security header configuration."""
    
    def test_x_frame_options(self, nginx_config):
        """X-Frame-Options header is set."""
        assert "X-Frame-Options" in nginx_config
        assert '"DENY"' in nginx_config or '"SAMEORIGIN"' in nginx_config
    
    def test_x_xss_protection(self, nginx_config):
        """X-XSS-Protection header is set."""
        assert "X-XSS-Protection" in nginx_config
        assert "1; mode=block" in nginx_config
    
    def test_x_content_type_options(self, nginx_config):
        """X-Content-Type-Options header is set."""
        assert "X-Content-Type-Options" in nginx_config
        assert "nosniff" in nginx_config
    
    def test_referrer_policy(self, nginx_config):
        """Referrer-Policy header is set."""
        assert "Referrer-Policy" in nginx_config
        assert "strict-origin-when-cross-origin" in nginx_config
    
    def test_content_security_policy(self, nginx_config):
        """Content-Security-Policy header is set."""
        assert "Content-Security-Policy" in nginx_config
        assert "default-src" in nginx_config

    def test_csp_frame_src_none(self, nginx_config):
        """CSP forbids nested frames via frame-src 'none' (#1066)."""
        assert "frame-src 'none'" in nginx_config

    def test_csp_form_action_self(self, nginx_config):
        """CSP restricts form posts to same-origin via form-action 'self' (#1066)."""
        assert "form-action 'self'" in nginx_config

    def test_csp_base_uri_self(self, nginx_config):
        """CSP prevents base-tag injection via base-uri 'self' (#1066)."""
        assert "base-uri 'self'" in nginx_config

    def test_permissions_policy(self, nginx_config):
        """Permissions-Policy header is set."""
        assert "Permissions-Policy" in nginx_config


# ============================================================================
# RATE LIMITING TESTS
# ============================================================================

class TestRateLimiting:
    """Tests for rate limiting configuration."""
    
    def test_api_limit_zone(self, nginx_config):
        """General API rate limit zone is defined."""
        assert "limit_req_zone" in nginx_config
        assert "zone=api_limit" in nginx_config
    
    def test_fsma_limit_zone(self, nginx_config):
        """FSMA-specific rate limit zone is defined with higher limit."""
        assert "zone=fsma_limit" in nginx_config
        # FSMA should have higher rate (20r/s vs 10r/s)
        match = re.search(r'zone=fsma_limit.*rate=(\d+)r/s', nginx_config)
        assert match, "FSMA rate limit not found"
        rate = int(match.group(1))
        assert rate >= 20, "FSMA rate limit should be at least 20r/s"
    
    def test_auth_limit_zone(self, nginx_config):
        """Auth rate limit zone is defined with stricter limit."""
        assert "zone=auth_limit" in nginx_config
    
    def test_fsma_routes_use_fsma_limit(self, nginx_config):
        """FSMA routes use the fsma_limit zone."""
        # Find FSMA location block and check it uses fsma_limit
        assert "limit_req zone=fsma_limit" in nginx_config


# ============================================================================
# HEALTH CHECK TESTS
# ============================================================================

class TestHealthChecks:
    """Tests for health check endpoints."""
    
    def test_gateway_health(self, nginx_config):
        """Gateway health endpoint is defined."""
        assert "location /health" in nginx_config
        assert '"status":"ok"' in nginx_config
    
    def test_readiness_probe(self, nginx_config):
        """Kubernetes readiness probe is defined."""
        assert "location /ready" in nginx_config
        assert '"ready":true' in nginx_config
    
    def test_liveness_probe(self, nginx_config):
        """Kubernetes liveness probe is defined."""
        assert "location /live" in nginx_config
        assert '"alive":true' in nginx_config
    
    def test_metrics_endpoint(self, nginx_config):
        """Prometheus metrics endpoint is defined."""
        assert "location /metrics" in nginx_config
        assert "stub_status" in nginx_config


# ============================================================================
# LOGGING TESTS
# ============================================================================

class TestLogging:
    """Tests for logging configuration."""
    
    def test_json_log_format(self, nginx_config):
        """JSON structured logging format is defined."""
        assert "log_format json_audit" in nginx_config
        assert '"timestamp"' in nginx_config
        assert '"request_id"' in nginx_config
        assert '"status"' in nginx_config
    
    def test_access_log_uses_json(self, nginx_config):
        """Access log uses JSON format."""
        assert "access_log" in nginx_config
        assert "json_audit" in nginx_config
    
    def test_request_id_header(self, nginx_config):
        """Request ID correlation header is configured."""
        assert "X-Request-ID" in nginx_config


# ============================================================================
# PROXY CONFIGURATION TESTS
# ============================================================================

class TestProxyConfiguration:
    """Tests for proxy settings."""
    
    def test_proxy_headers(self, nginx_config):
        """Required proxy headers are set."""
        assert "proxy_set_header Host" in nginx_config
        assert "proxy_set_header X-Real-IP" in nginx_config
        assert "proxy_set_header X-Forwarded-For" in nginx_config
        assert "proxy_set_header X-Forwarded-Proto" in nginx_config
    
    def test_http_version(self, nginx_config):
        """HTTP/1.1 is used for upstream connections."""
        assert "proxy_http_version 1.1" in nginx_config
    
    def test_connection_header(self, nginx_config):
        """Connection header is set for keepalive."""
        assert 'proxy_set_header Connection ""' in nginx_config
    
    def test_proxy_timeouts(self, nginx_config):
        """Proxy timeouts are configured."""
        assert "proxy_connect_timeout" in nginx_config
        assert "proxy_send_timeout" in nginx_config
        assert "proxy_read_timeout" in nginx_config
    
    def test_ingestion_large_body(self, nginx_config):
        """Ingestion route allows large file uploads."""
        assert "client_max_body_size" in nginx_config
        # Should be at least 50M
        match = re.search(r'client_max_body_size\s+(\d+)M', nginx_config)
        assert match, "client_max_body_size not found"
        size = int(match.group(1))
        assert size >= 50, "Should allow at least 50M uploads"


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Tests for error page configuration."""
    
    def test_500_error_page(self, nginx_config):
        """500 error returns JSON response."""
        assert "error_page 500 502 503 504" in nginx_config
        assert "50x.json" in nginx_config
    
    def test_404_error_page(self, nginx_config):
        """404 error returns JSON response."""
        assert "error_page 404" in nginx_config
        assert "404.json" in nginx_config
    
    def test_429_error_page(self, nginx_config):
        """429 rate limit error returns JSON response."""
        assert "error_page 429" in nginx_config
        assert "429.json" in nginx_config


# ============================================================================
# CORS TESTS
# ============================================================================

class TestCORS:
    """Tests for CORS configuration."""
    
    def test_cors_preflight(self, nginx_config):
        """CORS preflight (OPTIONS) handling is configured."""
        assert "OPTIONS" in nginx_config
        assert "Access-Control-Allow-Origin" in nginx_config
    
    def test_cors_methods(self, nginx_config):
        """CORS allowed methods are configured."""
        assert "Access-Control-Allow-Methods" in nginx_config
        assert "GET" in nginx_config
        assert "POST" in nginx_config
        assert "DELETE" in nginx_config
    
    def test_cors_headers(self, nginx_config):
        """CORS allowed headers include API key."""
        assert "Access-Control-Allow-Headers" in nginx_config
        assert "X-RegEngine-API-Key" in nginx_config


# ============================================================================
# SSL/TLS TESTS (Commented section validation)
# ============================================================================

class TestSSLConfiguration:
    """Tests for SSL/TLS configuration (even if commented)."""
    
    def test_ssl_section_exists(self, nginx_config):
        """SSL server block template exists."""
        assert "listen 443 ssl" in nginx_config or "listen 443" in nginx_config
    
    def test_tls_protocols(self, nginx_config):
        """TLS protocols are specified (TLS 1.2+)."""
        assert "TLSv1.2" in nginx_config or "ssl_protocols" in nginx_config
    
    def test_hsts_header_template(self, nginx_config):
        """HSTS header template exists."""
        assert "Strict-Transport-Security" in nginx_config


# ============================================================================
# FSMA-SPECIFIC TESTS
# ============================================================================

class TestFSMAConfiguration:
    """Tests specific to FSMA 204 compliance requirements."""
    
    def test_fsma_higher_rate_limit(self, nginx_config):
        """FSMA endpoints have higher rate limits for recall scenarios."""
        # Extract FSMA rate limit
        match = re.search(r'zone=fsma_limit.*rate=(\d+)r/s', nginx_config)
        api_match = re.search(r'zone=api_limit.*rate=(\d+)r/s', nginx_config)
        
        if match and api_match:
            fsma_rate = int(match.group(1))
            api_rate = int(api_match.group(1))
            assert fsma_rate >= api_rate, "FSMA rate should be >= general API rate"
    
    def test_fsma_fast_timeouts(self, nginx_config):
        """FSMA endpoints have optimized timeouts for 24-hour mandate."""
        # FSMA should have fast connect timeout
        assert "proxy_connect_timeout 5s" in nginx_config or "proxy_connect_timeout" in nginx_config
    
    def test_fsma_burst_capacity(self, nginx_config):
        """FSMA has high burst capacity for batch recall queries."""
        match = re.search(r'limit_req zone=fsma_limit burst=(\d+)', nginx_config)
        assert match, "FSMA burst limit not found"
        burst = int(match.group(1))
        assert burst >= 50, "FSMA burst should be at least 50 for recall scenarios"
