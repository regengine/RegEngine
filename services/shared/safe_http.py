"""Safe HTTP client utilities with SSRF defenses.

Provides httpx-based clients that:

1. Resolve hostnames to all IPs (v4+v6) and validate every address against the
   blocklist before connecting.
2. Pin one validated IP for the connection so the OS cannot re-resolve to a
   different (rebound) address between validate and connect (TOCTOU defense).
3. Re-validate every redirect hop. ``follow_redirects`` is disabled at the
   client layer; callers wanting redirect-following must use
   :func:`follow_redirects_safely` so each hop is checked.

Closes RE-SEC-001 (redirect SSRF), RE-SEC-002 (TOCTOU/DNS rebinding), and
hardens the IPv6 path (RE-SEC-006) when used with the upgraded
``shared.url_validation``.
"""

from __future__ import annotations

import socket
import ssl
from ipaddress import ip_address
from typing import Any, Callable, Dict, Iterable, Mapping, Optional
from urllib.parse import urlparse, urlunparse

import httpx
import structlog
from shared.url_validation import SSRFError, validate_url

logger = structlog.get_logger("safe-http")


DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_REDIRECTS = 5

# Upper bound on response bodies accepted through the safe helpers. Callers
# fetching regulatory pages, feeds, or vendor JSON get a bounded buffer so a
# malicious or misconfigured server cannot force unbounded memory use.
# Callers with a legitimately smaller budget pass ``max_bytes`` explicitly.
DEFAULT_MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class ResponseTooLargeError(ValueError):
    """Raised when a response body exceeds the caller's ``max_bytes`` cap."""

    pass


# Standard browser-like headers used by upstream fetchers. Kept here so callers
# that want a single SSRF-safe entry point don't have to redefine them.
STANDARD_BROWSER_HEADERS: Dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


def _build_ssl_context() -> ssl.SSLContext:
    """Default SSL context for outbound HTTPS calls."""
    ctx = ssl.create_default_context()
    return ctx


class _IPPinnedAsyncTransport(httpx.AsyncHTTPTransport):
    """Async transport that pins the destination IP after validation.

    The transport replaces the request URL host with a validated IP literal
    while preserving the original Host header (for correct virtual-host
    routing) and using the original hostname as the TLS SNI/server_hostname.
    """

    def __init__(self, *, pinned_ip: str, original_host: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pinned_ip = pinned_ip
        self._original_host = original_host

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        # Rewrite URL host -> pinned IP literal so the OS does not re-resolve.
        original_url = request.url
        # Bracket IPv6 literals
        ip_literal = f"[{self._pinned_ip}]" if ":" in self._pinned_ip else self._pinned_ip
        new_netloc = ip_literal
        if original_url.port is not None:
            new_netloc = f"{ip_literal}:{original_url.port}"
        rewritten = original_url.copy_with(host=ip_literal)
        request.url = rewritten
        # Preserve Host header so the remote server routes correctly.
        request.headers["Host"] = (
            f"{self._original_host}:{original_url.port}"
            if original_url.port is not None and original_url.port not in (80, 443)
            else self._original_host
        )
        # httpcore otherwise derives TLS SNI and certificate verification from
        # the rewritten IP literal.  Preserve the validated hostname while the
        # TCP connection remains pinned to the selected address.
        request.extensions["sni_hostname"] = self._original_host
        return await super().handle_async_request(request)


class _IPPinnedSyncTransport(httpx.HTTPTransport):
    """Sync counterpart to :class:`_IPPinnedAsyncTransport`."""

    def __init__(self, *, pinned_ip: str, original_host: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._pinned_ip = pinned_ip
        self._original_host = original_host

    def handle_request(self, request: httpx.Request) -> httpx.Response:  # type: ignore[override]
        original_url = request.url
        ip_literal = f"[{self._pinned_ip}]" if ":" in self._pinned_ip else self._pinned_ip
        rewritten = original_url.copy_with(host=ip_literal)
        request.url = rewritten
        request.headers["Host"] = (
            f"{self._original_host}:{original_url.port}"
            if original_url.port is not None and original_url.port not in (80, 443)
            else self._original_host
        )
        request.extensions["sni_hostname"] = self._original_host
        return super().handle_request(request)


def _validate_and_pin(url: str) -> tuple[str, str]:
    """Validate ``url`` and return ``(pinned_ip, original_host)``.

    Raises :class:`SSRFError` if validation fails or no usable address.
    """
    validate_url(url)  # blocklist + scheme + DNS check (per-IP)
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise SSRFError("URL missing hostname")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise SSRFError(f"Could not resolve hostname: {host}") from exc
    # Re-validate the exact address we are about to pin. validate_url checked
    # the addresses from an earlier resolution, but DNS can rebind between the
    # two lookups; pinning an unvalidated addr would reopen the SSRF window.
    for info in infos:
        addr = info[4][0]
        if not addr:
            continue
        try:
            resolved = ip_address(addr)
        except ValueError:
            continue
        mapped = getattr(resolved, "ipv4_mapped", None)
        if not (mapped or resolved).is_global:
            raise SSRFError(f"Resolved IP {resolved} is not a public global address")
        return addr, host
    raise SSRFError(f"No addresses for host: {host}")


def safe_httpx_client(
    *,
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    http2: bool = False,
    headers: Optional[dict] = None,
) -> httpx.AsyncClient:
    """Build an async client whose transport is pinned to a validated IP.

    The client is bound to the ``url``'s host. ``follow_redirects`` is forced
    off; use :func:`follow_redirects_safely` for redirect handling.
    """
    pinned_ip, host = _validate_and_pin(url)
    ssl_ctx = _build_ssl_context()
    transport = _IPPinnedAsyncTransport(
        pinned_ip=pinned_ip,
        original_host=host,
        verify=ssl_ctx,
        http2=http2,
    )
    return httpx.AsyncClient(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        headers=headers or {},
    )


def _check_declared_length(headers, *, max_bytes: int) -> None:
    """Refuse before reading when ``Content-Length`` already exceeds the cap."""
    declared = headers.get("content-length")
    if declared is None:
        return
    try:
        if int(declared) > max_bytes:
            raise ResponseTooLargeError(f"Response body exceeds {max_bytes} bytes (declared {declared})")
    except ResponseTooLargeError:
        raise
    except (TypeError, ValueError):
        pass


def _effective_origin(url: str) -> tuple[str, str, int]:
    """Effective origin as ``(scheme, normalized host, effective port)``."""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "http":
            port = 80
        else:
            port = -1
    return (scheme, host, port)


def _is_same_origin(first_url: str, second_url: str) -> bool:
    return _effective_origin(first_url) == _effective_origin(second_url)


# Benign request headers that are safe to resend on a cross-origin redirect.
# Covers ``STANDARD_BROWSER_HEADERS`` (the ``safe_fetch_content`` default) plus
# common cache/negotiation validators. Anything else (Authorization, Cookie,
# X-Api-Key, custom headers, ...) fails closed: the redirect is rejected
# before the second origin is requested. Compared case-insensitively.
_SAFE_CROSS_ORIGIN_HEADERS: frozenset[str] = frozenset(
    {
        "user-agent",
        "accept",
        "accept-language",
        "accept-encoding",
        "dnt",
        "connection",
        "upgrade-insecure-requests",
        "cache-control",
        "pragma",
        "if-none-match",
        "if-modified-since",
        "te",
    }
)


def _has_only_safe_redirect_headers(headers: Optional[dict]) -> bool:
    if not headers:
        return True
    return all(str(name).lower() in _SAFE_CROSS_ORIGIN_HEADERS for name in headers.keys())


def _check_redirect_allowed(*, from_url: str, to_url: str, headers: Optional[dict]) -> None:
    """Reject header-leaking or downgrading redirects before the next hop.

    Policy: HTTPS->HTTP downgrades are always rejected. Same-origin
    redirects keep working with any headers. Cross-origin redirects are
    allowed only when caller headers are absent or limited to benign
    content-negotiation/cache headers (``_SAFE_CROSS_ORIGIN_HEADERS``);
    any other header (``Authorization``/``X-Api-Key``/``Cookie``/custom)
    rejects before the second origin is requested, so credentials never
    leak. Header names compare case-insensitively.
    """
    if urlparse(from_url).scheme.lower() == "https" and urlparse(to_url).scheme.lower() == "http":
        raise SSRFError(f"Refusing HTTPS->HTTP downgrade redirect: {from_url} -> {to_url}")
    if _is_same_origin(from_url, to_url):
        return
    if _has_only_safe_redirect_headers(headers):
        return
    raise SSRFError(f"Refusing cross-origin redirect with headers: {from_url} -> {to_url}")


def _read_capped_sync(response: httpx.Response, *, max_bytes: int) -> bytes:
    """Read decoded body bytes, stopping immediately once ``max_bytes`` is exceeded."""
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ResponseTooLargeError(f"Response body exceeds {max_bytes} bytes (received >{max_bytes})")
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_capped_async(response, *, max_bytes: int) -> bytes:
    """Async counterpart to :func:`_read_capped_sync` (decoded bytes)."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise ResponseTooLargeError(f"Response body exceeds {max_bytes} bytes (received >{max_bytes})")
        chunks.append(chunk)
    return b"".join(chunks)


def _finalize_response(response, body: bytes) -> httpx.Response:
    """Rebuild a buffered response preserving status/headers/request semantics.

    ``body`` holds decoded bytes, so content-encoding/length from the wire
    are dropped and httpx sets the decoded length.
    """
    headers = httpx.Headers(response.headers)
    for name in ("content-encoding", "content-length"):
        if name in headers:
            del headers[name]
    return httpx.Response(
        status_code=response.status_code,
        headers=headers,
        content=body,
        request=response.request,
    )


def safe_httpx_get_sync(
    url: str,
    *,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    validator: Callable[[str], str] = validate_url,
) -> httpx.Response:
    """Sync GET that validates every hop (initial + redirects).

    Returns the final :class:`httpx.Response`. Each hop uses a transport
    pinned to the freshly validated IP for that hop's hostname. Responses
    larger than ``max_bytes`` are refused with :class:`ResponseTooLargeError`.
    """
    current_url = validator(url)
    for hop in range(max_redirects + 1):
        pinned_ip, host = _validate_and_pin(current_url)
        ssl_ctx = _build_ssl_context()
        transport = _IPPinnedSyncTransport(
            pinned_ip=pinned_ip,
            original_host=host,
            verify=ssl_ctx,
        )
        with httpx.Client(
            transport=transport,
            timeout=timeout,
            follow_redirects=False,
            headers=headers or {},
        ) as client:
            with client.stream("GET", current_url) as response:
                _check_declared_length(response.headers, max_bytes=max_bytes)
                if response.is_redirect:
                    next_url = response.headers.get("location")
                    if not next_url:
                        body = _read_capped_sync(response, max_bytes=max_bytes)
                        return _finalize_response(response, body)
                    # Resolve relative redirects against current URL
                    from urllib.parse import urljoin

                    next_url = urljoin(current_url, next_url)
                    _check_redirect_allowed(from_url=current_url, to_url=next_url, headers=headers)
                    logger.info(
                        "safe_http_redirect",
                        from_url=current_url,
                        to_url=next_url,
                        hop=hop,
                    )
                    current_url = validator(next_url)
                    continue
                body = _read_capped_sync(response, max_bytes=max_bytes)
                return _finalize_response(response, body)
    raise SSRFError(f"Too many redirects (>{max_redirects}); last hop: {current_url}")


def safe_httpx_post_sync(
    url: str,
    *,
    headers: Optional[dict] = None,
    json: Optional[Any] = None,
    data: Optional[Any] = None,
    timeout: float = DEFAULT_TIMEOUT,
    validator: Callable[[str], str] = validate_url,
) -> httpx.Response:
    """Sync POST that validates the destination and pins to a validated IP.

    Unlike :func:`safe_httpx_get_sync` this does NOT follow redirects: POST
    redirects are unusual and unsafe to chase blindly (the body would be
    re-sent to the redirected host). Callers needing redirect handling for
    POST should validate explicitly and re-issue.
    """
    current_url = validator(url)
    pinned_ip, host = _validate_and_pin(current_url)
    ssl_ctx = _build_ssl_context()
    transport = _IPPinnedSyncTransport(
        pinned_ip=pinned_ip,
        original_host=host,
        verify=ssl_ctx,
    )
    with httpx.Client(
        transport=transport,
        timeout=timeout,
        follow_redirects=False,
        headers=headers or {},
    ) as client:
        return client.post(current_url, json=json, data=data)


async def safe_httpx_post_async(
    url: str,
    *,
    headers: Optional[dict] = None,
    json: Optional[Any] = None,
    data: Optional[Any] = None,
    timeout: float = DEFAULT_TIMEOUT,
    http2: bool = False,
    validator: Callable[[str], str] = validate_url,
) -> httpx.Response:
    """Async counterpart to :func:`safe_httpx_post_sync`.

    Does NOT follow redirects (see :func:`safe_httpx_post_sync` rationale).
    """
    current_url = validator(url)
    async with safe_httpx_client(url=current_url, timeout=timeout, http2=http2, headers=headers) as client:
        return await client.post(current_url, json=json, data=data)


class PinnedHTTPSession:
    """Small sync session facade whose every request uses a pinned client.

    This deliberately offers only the ``get``/``post`` surface needed by the
    embedded scheduler.  It preserves the familiar mutable ``headers`` and
    ``close`` seams used by existing tests without retaining a raw
    ``httpx.Client`` that could bypass per-request DNS validation.
    """

    def __init__(self, *, headers: Optional[dict] = None) -> None:
        self.headers: dict = dict(headers or {})
        self.closed = False

    def get(
        self,
        url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> httpx.Response:
        if self.closed:
            raise RuntimeError("HTTP session is closed")
        request_url = str(httpx.URL(url).copy_merge_params(params)) if params else url
        return safe_httpx_get_sync(request_url, headers=self.headers, timeout=timeout, max_bytes=max_bytes)

    def post(
        self,
        url: str,
        *,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> httpx.Response:
        if self.closed:
            raise RuntimeError("HTTP session is closed")
        return safe_httpx_post_sync(
            url,
            headers=self.headers,
            json=json,
            data=data,
            timeout=timeout,
        )

    def close(self) -> None:
        self.closed = True


async def follow_redirects_safely(
    url: str,
    *,
    headers: Optional[dict] = None,
    timeout: float = DEFAULT_TIMEOUT,
    http2: bool = False,
    max_hops: int = DEFAULT_MAX_REDIRECTS,
    validator: Callable[[str], str] = validate_url,
):
    """Async generator-style helper: yields the final streaming response.

    Returns a tuple ``(client, response_ctx)`` where ``response_ctx`` is the
    streaming context manager from ``client.stream("GET", final_url)`` after
    all redirects have been followed and validated. Caller is responsible
    for closing the client.
    """
    current_url = validator(url)
    for hop in range(max_hops + 1):
        client = safe_httpx_client(url=current_url, timeout=timeout, http2=http2, headers=headers)
        # First do a HEAD-equivalent: issue GET but don't stream body if redirect
        response = await client.get(current_url)
        if response.is_redirect:
            next_url = response.headers.get("location")
            await client.aclose()
            if not next_url:
                raise SSRFError("Redirect without Location header")
            from urllib.parse import urljoin

            next_url = urljoin(current_url, next_url)
            logger.info(
                "safe_http_async_redirect",
                from_url=current_url,
                to_url=next_url,
                hop=hop,
            )
            current_url = validator(next_url)
            continue
        # Not a redirect: return client + response
        return client, response
    raise SSRFError(f"Too many redirects (>{max_hops}); last hop: {current_url}")


async def safe_httpx_get_async(
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[Mapping[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    http2: bool = False,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    validator: Callable[[str], str] = validate_url,
) -> httpx.Response:
    """Async GET that validates every hop and pins each hop's IP.

    Mirrors :func:`safe_httpx_get_sync` for ``httpx.AsyncClient`` callers such
    as vendor connectors whose ``base_url`` is tenant-configurable. Query
    ``params`` are merged into the first-hop URL only. Responses larger than
    ``max_bytes`` are refused with :class:`ResponseTooLargeError`.
    """
    current_url = validator(url)
    if params:
        current_url = str(httpx.URL(current_url).copy_merge_params(params))
    for hop in range(max_redirects + 1):
        client = safe_httpx_client(url=current_url, timeout=timeout, http2=http2, headers=headers)
        try:
            async with client.stream("GET", current_url) as response:
                _check_declared_length(response.headers, max_bytes=max_bytes)
                if response.is_redirect:
                    next_url = response.headers.get("location")
                    if not next_url:
                        body = await _read_capped_async(response, max_bytes=max_bytes)
                        return _finalize_response(response, body)
                    from urllib.parse import urljoin

                    next_url = urljoin(current_url, next_url)
                    _check_redirect_allowed(from_url=current_url, to_url=next_url, headers=headers)
                    logger.info(
                        "safe_http_async_redirect",
                        from_url=current_url,
                        to_url=next_url,
                        hop=hop,
                    )
                    current_url = validator(next_url)
                    continue
                body = await _read_capped_async(response, max_bytes=max_bytes)
                return _finalize_response(response, body)
        finally:
            await client.aclose()
    raise SSRFError(f"Too many redirects (>{max_redirects}); last hop: {current_url}")


def safe_fetch_content(
    url: str,
    *,
    timeout: int = 30,
    headers: Optional[dict] = None,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
) -> Dict[str, Any]:
    """SSRF-safe sync fetch returning a normalized response dict.

    This is the canonical "give me bytes for a URL" helper for ingestion-style
    callers. It runs the URL through :func:`validate_url`, then through
    :func:`safe_httpx_get_sync` so every redirect hop is re-validated with a
    pinned IP (RE-SEC-001/002).

    SSRF errors are NEVER swallowed: callers receive a ``ValueError`` whose
    message starts with ``"URL validation failed:"`` and must not promote that
    to a stronger fetcher (RE-SEC-004).

    Returns ``{"content", "status_code", "headers", "content_type"}``.
    """
    try:
        url = validate_url(url)
    except SSRFError as e:
        logger.warning("ssrf_validation_failed", url=url, error=str(e))
        raise ValueError(f"URL validation failed: {str(e)}") from e

    try:
        response = safe_httpx_get_sync(
            url, headers=headers or STANDARD_BROWSER_HEADERS, timeout=timeout, max_bytes=max_bytes
        )
    except SSRFError as e:
        logger.warning("ssrf_error_during_fetch", url=url, error=str(e))
        raise ValueError(f"URL validation failed: {str(e)}") from e

    response.raise_for_status()
    return {
        "content": response.content,
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "content_type": response.headers.get("Content-Type", "application/octet-stream"),
    }


__all__ = [
    "DEFAULT_MAX_RESPONSE_BYTES",
    "PinnedHTTPSession",
    "ResponseTooLargeError",
    "STANDARD_BROWSER_HEADERS",
    "safe_httpx_client",
    "safe_httpx_get_async",
    "safe_httpx_get_sync",
    "safe_httpx_post_sync",
    "safe_httpx_post_async",
    "safe_fetch_content",
    "follow_redirects_safely",
]
