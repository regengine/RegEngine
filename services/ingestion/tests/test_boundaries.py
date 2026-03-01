"""Boundary tests for the ingestion service.

Validates SSRF protection, rate limiting enforcement, payload size limits,
and URL/scheme validation — all without making real network requests.

These tests import safety functions from app.routes after setting the
required environment variables to avoid Settings initialization failures.
"""

import os
import sys
from pathlib import Path
from ipaddress import ip_network, ip_address
from unittest.mock import patch, MagicMock

# Set required env vars BEFORE any app module imports
os.environ.setdefault("ADMIN_SERVICE_URL", "http://localhost:8000")
os.environ.setdefault("NLP_SERVICE_URL", "http://localhost:8002")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "test-ingestion-bucket")
os.environ.setdefault("OBJECT_STORAGE_ACCESS_KEY_ID", "test-key")
os.environ.setdefault("OBJECT_STORAGE_SECRET_ACCESS_KEY", "test-secret")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ENABLE_DB_API_KEYS", "false")

# Add service directory to path for imports to work
service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

# Pre-mock optional dependencies that app.routes transitively imports
# These are not needed for boundary tests but are required for module load
_mock_kafka = MagicMock()
for _ck in [
    "confluent_kafka", "confluent_kafka.admin", "confluent_kafka.schema_registry",
    "confluent_kafka.schema_registry.avro", "confluent_kafka.serialization",
]:
    sys.modules.setdefault(_ck, _mock_kafka)

for _mod in [
    "feedparser",
    "kafka", "kafka.errors",
    "opentelemetry", "opentelemetry.trace",
    "opentelemetry.sdk", "opentelemetry.sdk.resources",
    "opentelemetry.sdk.trace", "opentelemetry.sdk.trace.export",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.instrumentation.fastapi",
]:
    sys.modules.setdefault(_mod, MagicMock())




import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException


# ─────────────────────────────────────────────────────────────────────────────
# Lazy import helpers — defer app.routes import to test time
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def routes():
    """Import app.routes lazily after env vars are set."""
    # Patch get_settings to avoid the api_key attribute error
    from app import config as cfg

    class _TestSettings(cfg.Settings):
        api_key: str = "test-key"

    _cached = _TestSettings()
    with patch.object(cfg, "get_settings", return_value=_cached):
        cfg.get_settings.cache_clear()
        import app.routes as r
        yield r


# ═══════════════════════════════════════════════════════════════════════════════
# URL Validation Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateUrl:
    """Tests for _validate_url: scheme, port, host, and credential blocking."""

    # --- Scheme restrictions ---

    def test_https_scheme_allowed(self, routes):
        with patch.object(routes, "_resolve_and_validate", return_value={"93.184.216.34"}):
            routes._validate_url("https://example.com/doc.pdf")

    def test_http_scheme_allowed(self, routes):
        with patch.object(routes, "_resolve_and_validate", return_value={"93.184.216.34"}):
            routes._validate_url("http://example.com/doc.pdf")

    def test_ftp_scheme_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("ftp://example.com/file.txt")
        assert exc_info.value.status_code == 400
        assert "scheme" in exc_info.value.detail.lower()

    def test_file_scheme_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("file:///etc/passwd")
        assert exc_info.value.status_code == 400

    def test_javascript_scheme_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("javascript:alert(1)")
        assert exc_info.value.status_code == 400

    def test_data_scheme_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("data:text/html,<h1>xss</h1>")
        assert exc_info.value.status_code == 400

    # --- Credential stripping ---

    def test_url_with_credentials_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("https://admin:password@example.com/doc")
        assert exc_info.value.status_code == 400
        assert "credentials" in exc_info.value.detail.lower()

    def test_url_with_username_only_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("https://admin@example.com/doc")
        assert exc_info.value.status_code == 400

    # --- Prohibited hosts ---

    def test_localhost_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("http://localhost:8080/admin")
        assert exc_info.value.status_code == 400

    def test_127_0_0_1_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("http://127.0.0.1/admin")
        assert exc_info.value.status_code == 400

    # --- Port restrictions ---

    def test_default_https_port_allowed(self, routes):
        with patch.object(routes, "_resolve_and_validate", return_value={"93.184.216.34"}):
            routes._validate_url("https://example.com/doc")

    def test_port_8080_allowed(self, routes):
        with patch.object(routes, "_resolve_and_validate", return_value={"93.184.216.34"}):
            routes._validate_url("https://example.com:8080/doc")

    def test_port_22_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("http://example.com:22/cmd")
        assert exc_info.value.status_code == 400
        assert "port" in exc_info.value.detail.lower()

    def test_port_6379_redis_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("http://example.com:6379/")
        assert exc_info.value.status_code == 400

    def test_port_5432_postgres_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("http://example.com:5432/")
        assert exc_info.value.status_code == 400

    def test_port_9092_kafka_blocked(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._validate_url("http://example.com:9092/")
        assert exc_info.value.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════════
# DNS Resolution / IP Validation Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveAndValidate:
    """Tests for _resolve_and_validate: private IP blocking."""

    def test_private_10_x_blocked(self, routes):
        with patch.object(routes.socket, "getaddrinfo",
                          return_value=[(2, 1, 6, "", ("10.0.0.1", 0))]):
            with pytest.raises(HTTPException) as exc_info:
                routes._resolve_and_validate("evil.com")
            assert exc_info.value.status_code == 400
            assert "private" in exc_info.value.detail.lower()

    def test_private_172_16_blocked(self, routes):
        with patch.object(routes.socket, "getaddrinfo",
                          return_value=[(2, 1, 6, "", ("172.16.5.1", 0))]):
            with pytest.raises(HTTPException):
                routes._resolve_and_validate("evil.com")

    def test_private_192_168_blocked(self, routes):
        with patch.object(routes.socket, "getaddrinfo",
                          return_value=[(2, 1, 6, "", ("192.168.1.1", 0))]):
            with pytest.raises(HTTPException):
                routes._resolve_and_validate("evil.com")

    def test_loopback_127_blocked(self, routes):
        with patch.object(routes.socket, "getaddrinfo",
                          return_value=[(2, 1, 6, "", ("127.0.0.1", 0))]):
            with pytest.raises(HTTPException):
                routes._resolve_and_validate("evil.com")

    def test_link_local_169_254_blocked(self, routes):
        """Metadata IP 169.254.169.254 must be blocked."""
        with patch.object(routes.socket, "getaddrinfo",
                          return_value=[(2, 1, 6, "", ("169.254.169.254", 0))]):
            with pytest.raises(HTTPException):
                routes._resolve_and_validate("metadata.evil.com")

    def test_ipv6_loopback_blocked(self, routes):
        with patch.object(routes.socket, "getaddrinfo",
                          return_value=[(10, 1, 6, "", ("::1", 0, 0, 0))]):
            with pytest.raises(HTTPException):
                routes._resolve_and_validate("evil.com")

    def test_ipv6_ula_fc00_blocked(self, routes):
        with patch.object(routes.socket, "getaddrinfo",
                          return_value=[(10, 1, 6, "", ("fd12:3456::1", 0, 0, 0))]):
            with pytest.raises(HTTPException):
                routes._resolve_and_validate("evil.com")

    def test_public_ip_allowed(self, routes):
        with patch.object(routes.socket, "getaddrinfo",
                          return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
            addresses = routes._resolve_and_validate("example.com")
            assert "93.184.216.34" in addresses

    def test_mixed_private_public_blocked(self, routes):
        """If ANY resolved IP is private, entire resolution should fail."""
        with patch.object(routes.socket, "getaddrinfo",
                          return_value=[
                              (2, 1, 6, "", ("93.184.216.34", 0)),
                              (2, 1, 6, "", ("10.0.0.1", 0)),
                          ]):
            with pytest.raises(HTTPException):
                routes._resolve_and_validate("dual-record.com")


# ═══════════════════════════════════════════════════════════════════════════════
# Size Limit Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestEnforceSizeLimit:
    """Tests for _enforce_size_limit: payload size validation."""

    def test_small_payload_allowed(self, routes):
        routes._enforce_size_limit(b"x" * 1024)

    def test_exact_limit_allowed(self, routes):
        routes._enforce_size_limit(b"x" * routes.MAX_PAYLOAD_BYTES)

    def test_over_limit_rejected(self, routes):
        with pytest.raises(HTTPException) as exc_info:
            routes._enforce_size_limit(b"x" * (routes.MAX_PAYLOAD_BYTES + 1))
        assert exc_info.value.status_code == 413
        assert "size" in exc_info.value.detail.lower()

    def test_empty_payload_allowed(self, routes):
        routes._enforce_size_limit(b"")


# ═══════════════════════════════════════════════════════════════════════════════
# Rate Limiter Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRateLimiter:
    """Tests for the RateLimiter utility used by source adapters."""

    def test_rate_limiter_enforces_minimum_interval(self):
        from regengine_ingestion.utils.rate_limiter import RateLimiter
        import time

        limiter = RateLimiter(requests_per_minute=6000)  # 10ms interval
        limiter.wait_if_needed("test.com")
        t0 = time.time()
        limiter.wait_if_needed("test.com")
        elapsed = time.time() - t0
        assert elapsed >= 0.005

    def test_exponential_backoff_on_error(self):
        from regengine_ingestion.utils.rate_limiter import RateLimiter

        limiter = RateLimiter(max_retries=5, exponential_backoff=True)
        b1 = limiter.record_error("test.com")
        b2 = limiter.record_error("test.com")
        b3 = limiter.record_error("test.com")
        assert b1 == 1.0
        assert b2 == 2.0
        assert b3 == 4.0

    def test_max_retries_exceeded_returns_none(self):
        from regengine_ingestion.utils.rate_limiter import RateLimiter

        limiter = RateLimiter(max_retries=2, exponential_backoff=True)
        limiter.record_error("test.com")
        limiter.record_error("test.com")
        result = limiter.record_error("test.com")
        assert result is None

    def test_success_resets_retry_counter(self):
        from regengine_ingestion.utils.rate_limiter import RateLimiter

        limiter = RateLimiter(max_retries=2)
        limiter.record_error("test.com")
        limiter.record_error("test.com")
        limiter.record_success("test.com")
        b1 = limiter.record_error("test.com")
        assert b1 == 1.0  # Reset, so first error again


# ═══════════════════════════════════════════════════════════════════════════════
# Security Constants Validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecurityConstants:
    """Validate the security constants themselves are correctly configured."""

    def test_prohibited_networks_include_all_rfc1918(self, routes):
        rfc1918 = [
            ip_network("10.0.0.0/8"),
            ip_network("172.16.0.0/12"),
            ip_network("192.168.0.0/16"),
        ]
        for net in rfc1918:
            assert any(n == net for n in routes.PROHIBITED_NETWORKS), \
                f"{net} missing from PROHIBITED_NETWORKS"

    def test_prohibited_networks_include_link_local(self, routes):
        assert any(n == ip_network("169.254.0.0/16") for n in routes.PROHIBITED_NETWORKS)

    def test_prohibited_networks_include_ipv6_loopback(self, routes):
        assert any(n == ip_network("::1/128") for n in routes.PROHIBITED_NETWORKS)

    def test_max_payload_is_25_mb(self, routes):
        assert routes.MAX_PAYLOAD_BYTES == 25 * 1024 * 1024

    def test_only_http_https_allowed(self, routes):
        assert routes.ALLOWED_SCHEMES == {"http", "https"}

    def test_dangerous_ports_excluded(self, routes):
        dangerous = {22, 25, 3306, 5432, 6379, 9092, 27017}
        assert not (dangerous & routes.ALLOWED_PORTS), \
            f"Dangerous ports found in ALLOWED_PORTS: {dangerous & routes.ALLOWED_PORTS}"
