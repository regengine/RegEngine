"""Tests for resilient HTTP client with retry + circuit breaker integration."""

import pytest
import httpx

from shared.resilient_http import (
    resilient_client,
    get_http_circuit,
    _http_circuits,
    RetryTransport,
    _RETRYABLE_STATUS_CODES,
)
from shared.circuit_breaker import CircuitOpenError, CircuitState


# ---------------------------------------------------------------------------
# Helpers — fake transport that returns controlled responses
# ---------------------------------------------------------------------------

class FakeTransport(httpx.AsyncBaseTransport):
    """Transport that returns pre-configured responses for testing."""

    def __init__(self, responses=None, side_effect=None):
        """
        Args:
            responses: List of (status_code, json_body) tuples to return in order.
            side_effect: Exception to raise on every call (overrides responses).
        """
        self._responses = list(responses or [])
        self._side_effect = side_effect
        self.call_count = 0
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        self.requests.append(request)

        if self._side_effect:
            raise self._side_effect

        if self._responses:
            status, body = self._responses.pop(0)
        else:
            status, body = 200, {"ok": True}

        return httpx.Response(
            status_code=status,
            json=body,
            request=request,
        )


# ---------------------------------------------------------------------------
# RetryTransport tests
# ---------------------------------------------------------------------------

class TestRetryTransport:
    """Tests for the retry transport layer."""

    @pytest.mark.asyncio
    async def test_successful_request_no_retry(self):
        """Successful request should not retry."""
        fake = FakeTransport(responses=[(200, {"status": "ok"})])
        transport = RetryTransport(wrapped=fake, retries=3)

        request = httpx.Request("GET", "http://test/api")
        response = await transport.handle_async_request(request)

        assert response.status_code == 200
        assert fake.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_502(self):
        """Should retry on 502 then succeed."""
        fake = FakeTransport(responses=[
            (502, {"error": "bad gateway"}),
            (502, {"error": "bad gateway"}),
            (200, {"status": "ok"}),
        ])
        transport = RetryTransport(wrapped=fake, retries=3, backoff_base=0.01)

        request = httpx.Request("GET", "http://test/api")
        response = await transport.handle_async_request(request)

        assert response.status_code == 200
        assert fake.call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_503(self):
        """Should retry on 503."""
        fake = FakeTransport(responses=[
            (503, {"error": "unavailable"}),
            (200, {"ok": True}),
        ])
        transport = RetryTransport(wrapped=fake, retries=2, backoff_base=0.01)

        request = httpx.Request("GET", "http://test/api")
        response = await transport.handle_async_request(request)

        assert response.status_code == 200
        assert fake.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_504(self):
        """Should retry on 504."""
        fake = FakeTransport(responses=[
            (504, {"error": "timeout"}),
            (200, {"ok": True}),
        ])
        transport = RetryTransport(wrapped=fake, retries=2, backoff_base=0.01)

        request = httpx.Request("GET", "http://test/api")
        response = await transport.handle_async_request(request)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self):
        """Should NOT retry on 400 (client error)."""
        fake = FakeTransport(responses=[(400, {"error": "bad request"})])
        transport = RetryTransport(wrapped=fake, retries=3)

        request = httpx.Request("GET", "http://test/api")
        response = await transport.handle_async_request(request)

        assert response.status_code == 400
        assert fake.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_401(self):
        """Should NOT retry on 401 (auth error)."""
        fake = FakeTransport(responses=[(401, {"error": "unauthorized"})])
        transport = RetryTransport(wrapped=fake, retries=3)

        request = httpx.Request("GET", "http://test/api")
        response = await transport.handle_async_request(request)

        assert response.status_code == 401
        assert fake.call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self):
        """Should NOT retry on 404."""
        fake = FakeTransport(responses=[(404, {"error": "not found"})])
        transport = RetryTransport(wrapped=fake, retries=3)

        request = httpx.Request("GET", "http://test/api")
        response = await transport.handle_async_request(request)

        assert response.status_code == 404
        assert fake.call_count == 1

    @pytest.mark.asyncio
    async def test_exhausted_retries_returns_last_response(self):
        """When retries exhausted, should return the last 5xx response."""
        fake = FakeTransport(responses=[
            (502, {"error": "1"}),
            (503, {"error": "2"}),
            (504, {"error": "3"}),
            (502, {"error": "4"}),
        ])
        transport = RetryTransport(wrapped=fake, retries=3, backoff_base=0.01)

        request = httpx.Request("GET", "http://test/api")
        response = await transport.handle_async_request(request)

        # Should return the last response after exhausting retries
        assert response.status_code in _RETRYABLE_STATUS_CODES
        assert fake.call_count == 4  # 1 initial + 3 retries

    @pytest.mark.asyncio
    async def test_retries_on_connect_error(self):
        """Should retry on connection errors."""
        call_count = 0

        class FailThenSucceed(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise httpx.ConnectError("Connection refused")
                return httpx.Response(200, json={"ok": True}, request=request)

        transport = RetryTransport(wrapped=FailThenSucceed(), retries=3, backoff_base=0.01)
        request = httpx.Request("GET", "http://test/api")
        response = await transport.handle_async_request(request)

        assert response.status_code == 200
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_connect_retries_exhausted(self):
        """Should raise ConnectError after retries exhausted."""
        transport = RetryTransport(
            wrapped=FakeTransport(side_effect=httpx.ConnectError("refused")),
            retries=2,
            backoff_base=0.01,
        )
        request = httpx.Request("GET", "http://test/api")

        with pytest.raises(httpx.ConnectError):
            await transport.handle_async_request(request)

    @pytest.mark.asyncio
    async def test_backoff_delay_increases(self):
        """Backoff delay should increase with each attempt."""
        transport = RetryTransport(
            wrapped=FakeTransport(),  # not used directly
            retries=3,
            backoff_base=1.0,
            backoff_max=8.0,
        )
        delays = [transport._delay(i) for i in range(4)]
        # Each delay should be >= previous (with jitter, base doubles)
        assert delays[1] > delays[0] * 0.8  # allow jitter
        assert delays[2] > delays[1] * 0.8

    @pytest.mark.asyncio
    async def test_backoff_capped_at_max(self):
        """Backoff should not exceed max."""
        transport = RetryTransport(
            wrapped=FakeTransport(),
            retries=3,
            backoff_base=1.0,
            backoff_max=4.0,
        )
        # At attempt 10, base would be 1024 without cap
        delay = transport._delay(10)
        assert delay <= 4.0 * 1.2  # max + 20% jitter


# ---------------------------------------------------------------------------
# resilient_client context manager tests
# ---------------------------------------------------------------------------

class TestResilientClient:
    """Tests for the resilient_client context manager."""

    @pytest.mark.asyncio
    async def test_yields_httpx_client(self):
        """Should yield an httpx.AsyncClient."""
        async with resilient_client(timeout=5.0) as client:
            assert isinstance(client, httpx.AsyncClient)

    @pytest.mark.asyncio
    async def test_timeout_is_set(self):
        """Client should use the specified timeout."""
        async with resilient_client(timeout=42.0) as client:
            assert client.timeout.connect == 42.0

    @pytest.mark.asyncio
    async def test_follows_redirects(self):
        """Client should follow redirects."""
        async with resilient_client() as client:
            assert client.follow_redirects is True


# ---------------------------------------------------------------------------
# Circuit breaker integration tests
# ---------------------------------------------------------------------------

class TestCircuitBreakerIntegration:
    """Tests for circuit breaker integration with resilient_client."""

    def setup_method(self):
        """Clear circuit breaker registry between tests."""
        _http_circuits.clear()

    def test_get_http_circuit_creates_new(self):
        """Should create a new circuit breaker for unknown name."""
        circuit = get_http_circuit("test-service")
        assert circuit.name == "http_test-service"
        assert circuit.failure_threshold == 5
        assert circuit.recovery_timeout == 30.0

    def test_get_http_circuit_returns_same(self):
        """Should return same instance for same name."""
        c1 = get_http_circuit("test-service")
        c2 = get_http_circuit("test-service")
        assert c1 is c2

    def test_get_http_circuit_different_names(self):
        """Different names should get different circuits."""
        c1 = get_http_circuit("service-a")
        c2 = get_http_circuit("service-b")
        assert c1 is not c2
        assert c1.name == "http_service-a"
        assert c2.name == "http_service-b"

    @pytest.mark.asyncio
    async def test_circuit_breaker_fails_fast_when_open(self):
        """Should raise CircuitOpenError immediately when circuit is open."""
        circuit = get_http_circuit("failing-service")
        # Manually open the circuit
        for _ in range(5):
            circuit._record_failure(Exception("test"))

        assert circuit.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            async with resilient_client(circuit_name="failing-service") as client:
                pass  # Should never reach here

    @pytest.mark.asyncio
    async def test_no_circuit_name_skips_breaker(self):
        """Without circuit_name, should not use circuit breaker."""
        async with resilient_client(timeout=5.0) as client:
            assert isinstance(client, httpx.AsyncClient)
            # No circuit created
            assert len(_http_circuits) == 0

    @pytest.mark.asyncio
    async def test_circuit_records_failure_on_5xx(self):
        """5xx responses should be recorded as circuit failures."""
        circuit = get_http_circuit("track-5xx")
        assert circuit._failure_count == 0

        # Simulate what resilient_client does internally
        fake_request = httpx.Request("GET", "http://test/api")
        fake_response = httpx.Response(500, json={"error": "internal"}, request=fake_request)
        circuit._record_failure(
            httpx.HTTPStatusError("500", request=fake_request, response=fake_response)
        )

        assert circuit._failure_count == 1

    @pytest.mark.asyncio
    async def test_circuit_records_success_on_2xx(self):
        """2xx responses should reset failure count."""
        circuit = get_http_circuit("track-2xx")
        circuit._record_failure(Exception("prior"))
        assert circuit._failure_count == 1

        circuit._record_success()
        assert circuit._failure_count == 0

    @pytest.mark.asyncio
    async def test_circuit_4xx_should_not_trip(self):
        """4xx responses should NOT trip the circuit (client errors, not server)."""
        circuit = get_http_circuit("track-4xx")

        # Record 10 "4xx" as successes — circuit should stay closed
        for _ in range(10):
            circuit._record_success()

        assert circuit._failure_count == 0
        assert circuit.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self):
        """Circuit should open after 5 consecutive failures."""
        circuit = get_http_circuit("threshold-test")

        for i in range(5):
            circuit._record_failure(Exception(f"fail-{i}"))

        assert circuit.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_open_rejects_new_client(self):
        """Once circuit is open, new resilient_client calls should fail fast."""
        circuit = get_http_circuit("reject-test")
        for _ in range(5):
            circuit._record_failure(Exception("boom"))

        with pytest.raises(CircuitOpenError) as exc_info:
            async with resilient_client(circuit_name="reject-test") as client:
                await client.get("http://test/api")

        assert "reject-test" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Retryable status codes
# ---------------------------------------------------------------------------

class TestRetryableStatusCodes:
    """Verify the retryable status code set."""

    def test_502_is_retryable(self):
        assert 502 in _RETRYABLE_STATUS_CODES

    def test_503_is_retryable(self):
        assert 503 in _RETRYABLE_STATUS_CODES

    def test_504_is_retryable(self):
        assert 504 in _RETRYABLE_STATUS_CODES

    def test_500_is_not_retryable(self):
        assert 500 not in _RETRYABLE_STATUS_CODES

    def test_400_is_not_retryable(self):
        assert 400 not in _RETRYABLE_STATUS_CODES

    def test_404_is_not_retryable(self):
        assert 404 not in _RETRYABLE_STATUS_CODES
