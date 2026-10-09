"""
RegEngine API Client
"""

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger("regengine.client")

from .exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RegEngineError,
    ValidationError,
)
from .models import (
    CTEType,
    ReadinessScore,
    RecallDrill,
    Record,
    TimelineEvent,
    TraceResult,
)


class RegEngineClient:
    """
    Official Python client for RegEngine FSMA 204 Compliance API.

    Args:
        api_key: Your RegEngine API key (format: rge_xxx)
        base_url: API base URL (default: https://regengine.co)
        tenant_id: Optional tenant ID for multi-tenant isolation
        timeout: Request timeout in seconds (default: 30)

    Example:
        >>> client = RegEngineClient(api_key="rge_your_key")
        >>> record = client.get_record("LOT-2026-001")

    Experimental surface (#2952): the methods listed in
    ``EXPERIMENTAL_METHODS`` target the graph FSMA routers, which the
    production deployment does not mount (they are excluded from the
    release-approved ``ENABLED_ROUTERS`` allowlist). Against the hosted API
    they return 404; they work only against a deployment that mounts the
    experimental graph routers. ``tests/sdk/test_route_contract.py`` enforces
    that this list exactly matches the set of client methods whose routes are
    absent from the production route table.
    """

    DEFAULT_BASE_URL = "https://regengine.co"
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503}

    # Client methods whose backing routes exist only when the experimental
    # graph routers are mounted (not in production). Kept in exact sync with
    # the production route table by the SDK route-contract test: a method may
    # leave this set only when its route is promoted into the production
    # allowlist, and may not be added to the client without either a
    # production route or an entry here.
    EXPERIMENTAL_METHODS = frozenset(
        {
            "trace_forward",
            "trace_backward",
            "get_timeline",
            "start_recall_drill",
            "get_recall_drills",
            "get_readiness_score",
            "export_fda",
        }
    )

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        tenant_id: Optional[str] = None,
        timeout: int = 30,
        connect_timeout: int = 30,
        read_timeout: int = 60,
        max_retries: int = 3,
        retry_backoff_factor: float = 1.0,
    ):
        """
        Args:
            api_key: Your RegEngine API key (format: rge_xxx)
            base_url: API base URL (default: https://regengine.co)
            tenant_id: Optional tenant ID for multi-tenant isolation
            timeout: Overall request timeout in seconds (default: 30). Ignored if connect_timeout/read_timeout are set.
            connect_timeout: Connection timeout in seconds (default: 30)
            read_timeout: Read timeout in seconds (default: 60)
            max_retries: Maximum number of retry attempts on transient failures (default: 3)
            retry_backoff_factor: Base delay multiplier for exponential backoff in seconds (default: 1.0)
        """
        if not api_key or not api_key.startswith("rge_"):
            raise ValidationError("API key must start with 'rge_'")

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.timeout = httpx.Timeout(
            timeout=timeout,
            connect=connect_timeout,
            read=read_timeout,
        )
        self.max_retries = max_retries
        self.retry_backoff_factor = retry_backoff_factor
        self._session = httpx.Client()

    @staticmethod
    def _encode_segment(value: str) -> str:
        """Percent-encode one URL path segment (lot codes are caller input)."""
        return quote(value, safe="")

    def _headers(self, accept: str = "application/json") -> Dict[str, str]:
        """Build request headers.

        ``accept`` is parameterised (#2956) so a file download can ask for the
        media type it actually wants instead of advertising JSON.
        """
        headers = {
            "X-RegEngine-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": accept,
        }
        if self.tenant_id:
            headers["X-Tenant-ID"] = self.tenant_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        *,
        parse: str = "json",
        accept: str = "application/json",
        expected_content_type: Optional[str] = None,
    ) -> Any:
        """Make an API request with automatic retry on transient failures.

        Retries on 429, 500, 502, 503 with exponential backoff.
        Respects the Retry-After header when present.

        Args:
            parse: ``"json"`` (default) to decode the body as JSON, or
                ``"bytes"`` to return the raw ``response.content`` for file
                downloads. #2956: the bytes mode lives here rather than in a
                separate transport path so downloads get the same retry loop
                and the same 401/404/429 exception mapping as every other call.
            accept: value for the ``Accept`` request header.
            expected_content_type: when set (bytes mode), the response
                ``Content-Type`` must match it, or ``RegEngineError`` is raised
                rather than handing an HTML/JSON error body back as a file.
        """
        url = f"{self.base_url}{path}"
        last_exc: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.request(
                    method=method,
                    url=url,
                    headers=self._headers(accept),
                    params=params,
                    json=json,
                    timeout=self.timeout,
                )
            except httpx.HTTPError as e:
                last_exc = e
                if attempt < self.max_retries:
                    delay = self.retry_backoff_factor * (2**attempt)
                    logger.warning(
                        "Request to %s failed (attempt %d/%d), retrying in %.1fs: %s",
                        path,
                        attempt + 1,
                        self.max_retries + 1,
                        delay,
                        e,
                    )
                    time.sleep(delay)
                    continue
                raise RegEngineError(f"Request failed after {self.max_retries + 1} attempts: {e}")

            # Retryable status codes
            if response.status_code in self.RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        delay = self.retry_backoff_factor * (2**attempt)
                else:
                    delay = self.retry_backoff_factor * (2**attempt)
                logger.warning(
                    "Received %d from %s (attempt %d/%d), retrying in %.1fs",
                    response.status_code,
                    path,
                    attempt + 1,
                    self.max_retries + 1,
                    delay,
                )
                time.sleep(delay)
                continue

            # Non-retryable error responses
            if response.status_code == 401:
                raise AuthenticationError("Invalid or expired API key")
            elif response.status_code == 404:
                raise NotFoundError(f"Resource not found: {path}")
            elif response.status_code == 429:
                raise RateLimitError("Rate limit exceeded. Please slow down requests.")
            elif response.status_code >= 400:
                try:
                    error = response.json().get("detail", response.text)
                except Exception:
                    error = response.text
                raise RegEngineError(f"API error ({response.status_code}): {error}")

            # Success
            if parse == "bytes":
                if expected_content_type and response.status_code != 204:
                    content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                    if content_type != expected_content_type.lower():
                        raise RegEngineError(
                            f"Unexpected Content-Type from {path}: expected "
                            f"{expected_content_type!r}, got {content_type or '(none)'!r}. "
                            "Refusing to return the body as a file."
                        )
                return response.content
            if response.status_code == 204:
                return {}
            return response.json()

        # Exhausted retries — raise last status error
        raise RegEngineError(f"Request to {path} failed after {self.max_retries + 1} attempts")

    def _request_bytes(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        accept: str = "application/json",
        expected_content_type: Optional[str] = None,
    ) -> bytes:
        """Make an API request that returns raw bytes (for file downloads).

        #2956: this used to be a second, bare transport path — one attempt,
        ``raise_for_status()``, and a blanket ``except httpx.HTTPError`` that
        collapsed 401/404/429 into a generic ``RegEngineError``. It now
        delegates to ``_request``, so downloads share the retry loop,
        ``Retry-After`` handling and the documented status-to-exception
        mapping.
        """
        return self._request(
            method,
            path,
            params=params,
            parse="bytes",
            accept=accept,
            expected_content_type=expected_content_type,
        )

    # =========================================================================
    # Record Management
    # =========================================================================
    #
    # WS-11 note: create_record and check_ftl were removed (not deprecated) —
    # both always raised NotImplementedError because the consolidated API has
    # no public create-record endpoint (records are written by the ingestion
    # pipeline) and no per-category FTL lookup (#2531). The client exposes
    # only methods with real routes behind them.

    def get_record(self, tlc: str) -> Record:
        """
        Retrieve a single traceability record by Traceability Lot Code.

        Args:
            tlc: The Traceability Lot Code to look up

        Returns:
            Record object with record details

        Raises:
            NotFoundError: if no record exists for the given TLC.
        """
        data = self._request(
            "GET",
            "/api/v1/records",
            params={"tlc": tlc, "limit": 1},
        )
        events = data.get("events", [])
        if not events:
            raise NotFoundError(f"No record found for TLC: {tlc}")
        return Record.from_api(events[0])

    def query_records(
        self,
        start_date: str,
        end_date: str,
        cte_type: Optional[CTEType] = None,
        limit: int = 100,
    ) -> List[Record]:
        """
        Query traceability records by date range.

        Args:
            start_date: Start date (ISO format)
            end_date: End date (ISO format)
            cte_type: Optional filter by CTE type
            limit: Maximum number of records to return

        Returns:
            List of Record objects
        """
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
        }
        if cte_type:
            params["event_type"] = cte_type.value if isinstance(cte_type, CTEType) else cte_type

        data = self._request("GET", "/api/v1/records", params=params)
        return [Record.from_api(r) for r in data.get("events", [])]

    # =========================================================================
    # Supply Chain Tracing
    # =========================================================================

    def trace_forward(
        self,
        tlc: str,
        max_depth: int = 10,
        enforce_time_arrow: bool = True,
    ) -> TraceResult:
        """
        Trace a lot forward through the supply chain.

        Args:
            tlc: Traceability Lot Code to trace from
            max_depth: Maximum hops to trace (default: 10)
            enforce_time_arrow: Ensure chronological ordering (default: True)

        Returns:
            TraceResult with downstream facilities and events
        """
        params = {
            "max_depth": max_depth,
            "enforce_time_arrow": enforce_time_arrow,
        }
        data = self._request(
            "GET", f"/api/v1/fsma/traceability/trace/forward/{self._encode_segment(tlc)}", params=params
        )
        return TraceResult(**data)

    def trace_backward(
        self,
        tlc: str,
        max_depth: int = 10,
    ) -> TraceResult:
        """
        Trace a lot backward to source materials and suppliers.

        Args:
            tlc: Traceability Lot Code to trace from
            max_depth: Maximum hops to trace (default: 10)

        Returns:
            TraceResult with source lots and facilities
        """
        params = {"max_depth": max_depth}
        data = self._request(
            "GET", f"/api/v1/fsma/traceability/trace/backward/{self._encode_segment(tlc)}", params=params
        )
        return TraceResult(**data)

    def get_timeline(self, tlc: str) -> List[TimelineEvent]:
        """
        Get chronological timeline of all events for a lot.

        Args:
            tlc: Traceability Lot Code

        Returns:
            List of TimelineEvent objects in chronological order
        """
        data = self._request("GET", f"/api/v1/fsma/traceability/timeline/{self._encode_segment(tlc)}")
        return [TimelineEvent.from_api(e) for e in data.get("events", [])]

    # =========================================================================
    # FTL Checker
    # =========================================================================

    # =========================================================================
    # Recall Management
    # =========================================================================

    def start_recall_drill(
        self,
        target_tlc: str,
        drill_type: str = "forward_trace",
        severity: str = "class_ii",
    ) -> RecallDrill:
        """
        Initiate a mock recall drill for FDA compliance testing.

        Args:
            target_tlc: Lot code to trace during drill
            drill_type: Type of drill ('forward_trace' or 'backward_trace')
            severity: Recall severity class ('class_i', 'class_ii', 'class_iii')

        Returns:
            RecallDrill object with drill status
        """
        payload = {
            "target_tlc": target_tlc,
            "type": drill_type,
            "severity": severity,
        }
        data = self._request("POST", "/api/v1/fsma/recall/drill", json=payload)
        return RecallDrill(**data)

    def get_recall_drills(self, limit: int = 20) -> List[RecallDrill]:
        """
        Get history of mock recall drills.

        Args:
            limit: Maximum number of drills to return

        Returns:
            List of RecallDrill objects
        """
        data = self._request("GET", "/api/v1/fsma/recall/history", params={"limit": limit})
        return [RecallDrill(**d) for d in data.get("drills", [])]

    def get_readiness_score(self) -> ReadinessScore:
        """
        Get your FSMA 204 recall readiness score.

        Returns:
            ReadinessScore with score and recommendations
        """
        data = self._request("GET", "/api/v1/fsma/recall/readiness")
        return ReadinessScore(**data)

    # =========================================================================
    # FDA Export
    # =========================================================================

    def export_fda(
        self,
        tlc: str,
        start_date: str,
        end_date: str,
    ) -> bytes:
        """
        Generate FDA-compliant sortable spreadsheet (CSV).

        Per 21 CFR 1.1455(b)(3), produces a spreadsheet within 24 hours
        containing all traceability records for the specified lot.

        Args:
            tlc: Traceability Lot Code
            start_date: Start date (ISO format)
            end_date: End date (ISO format)

        Returns:
            CSV file content as bytes

        Raises:
            AuthenticationError: on HTTP 401 (expired or invalid key).
            NotFoundError: on HTTP 404 (endpoint not mounted / no such lot).
            RateLimitError: on HTTP 429 after retries are exhausted.
            RegEngineError: on other errors, or if the 200 response is not
                ``text/csv``.
        """
        params = {
            "tlc": tlc,
            "start_date": start_date,
            "end_date": end_date,
        }
        return self._request_bytes(
            "GET",
            "/api/v1/fsma/compliance/export/fda-request",
            params=params,
            # The server streams this as media_type="text/csv"
            # (services/graph/app/routers/fsma/compliance.py:169-173).
            accept="text/csv",
            expected_content_type="text/csv",
        )
