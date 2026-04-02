"""
RegEngine API Client
"""

import httpx
from typing import Optional, List, Any, Dict
from datetime import date

from .models import (
    Record,
    TraceResult,
    TimelineEvent,
    FTLResult,
    RecallDrill,
    ReadinessScore,
    CTEType,
)
from .exceptions import (
    RegEngineError,
    AuthenticationError,
    RateLimitError,
    NotFoundError,
    ValidationError,
)


class RegEngineClient:
    """
    Official Python client for RegEngine FSMA 204 Compliance API.
    
    Args:
        api_key: Your RegEngine API key (format: rge_xxx)
        base_url: API base URL (default: https://api.regengine.co)
        tenant_id: Optional tenant ID for multi-tenant isolation
        timeout: Request timeout in seconds (default: 30)
    
    Example:
        >>> client = RegEngineClient(api_key="rge_your_key")
        >>> record = client.get_record("LOT-2026-001")
    """
    
    DEFAULT_BASE_URL = "https://api.regengine.co"
    
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        tenant_id: Optional[str] = None,
        timeout: int = 30,
    ):
        if not api_key or not api_key.startswith("rge_"):
            raise ValidationError("API key must start with 'rge_'")
        
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.timeout = timeout
        self._session = httpx.Client()
    
    def _headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {
            "X-RegEngine-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
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
    ) -> Dict[str, Any]:
        """Make an API request."""
        url = f"{self.base_url}{path}"
        
        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
                json=json,
                timeout=self.timeout,
            )
        except httpx.HTTPError as e:
            raise RegEngineError(f"Request failed: {e}")

        # Handle error responses
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
        
        # Handle empty responses
        if response.status_code == 204:
            return {}
        
        return response.json()
    
    def _request_bytes(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> bytes:
        """Make an API request that returns raw bytes (for file downloads)."""
        url = f"{self.base_url}{path}"
        
        try:
            response = self._session.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as e:
            raise RegEngineError(f"Request failed: {e}")
    
    # =========================================================================
    # Record Management
    # =========================================================================
    
    def create_record(
        self,
        cte_type: CTEType,
        tlc: str,
        location: str,
        quantity: float,
        quantity_uom: str = "lbs",
        product_description: Optional[str] = None,
        event_date: Optional[str] = None,
        reference_document: Optional[str] = None,
        input_tlcs: Optional[List[str]] = None,
        **extra_kdes: Any,
    ) -> Record:
        """
        Create a traceability record for a Critical Tracking Event.
        
        Args:
            cte_type: Type of CTE (GROWING, RECEIVING, TRANSFORMATION, SHIPPING)
            tlc: Traceability Lot Code
            location: GLN of the facility
            quantity: Amount of product
            quantity_uom: Unit of measure (default: lbs)
            product_description: Description of the product
            event_date: Date of the event (ISO format, defaults to today)
            reference_document: Associated document reference
            input_tlcs: For TRANSFORMATION, list of input lot codes
            **extra_kdes: Additional Key Data Elements
        
        Returns:
            Record object with created record details
        """
        payload = {
            "cte_type": cte_type.value if isinstance(cte_type, CTEType) else cte_type,
            "tlc": tlc,
            "location": location,
            "quantity": quantity,
            "quantity_uom": quantity_uom,
            "event_date": event_date or date.today().isoformat(),
            **extra_kdes,
        }
        if product_description:
            payload["product_description"] = product_description
        if reference_document:
            payload["reference_document"] = reference_document
        if input_tlcs:
            payload["input_tlcs"] = input_tlcs
        
        data = self._request("POST", "/api/graph/fsma/records", json=payload)
        return Record(**data)
    
    def get_record(self, tlc: str) -> Record:
        """
        Retrieve a traceability record by Traceability Lot Code.
        
        Args:
            tlc: The Traceability Lot Code to look up
        
        Returns:
            Record object with record details
        """
        data = self._request("GET", f"/api/graph/fsma/records/{tlc}")
        return Record(**data)
    
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
            params["cte_type"] = cte_type.value if isinstance(cte_type, CTEType) else cte_type
        
        data = self._request("GET", "/api/graph/fsma/records", params=params)
        return [Record(**r) for r in data.get("records", [])]
    
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
        data = self._request("GET", f"/api/graph/fsma/trace/forward/{tlc}", params=params)
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
        data = self._request("GET", f"/api/graph/fsma/trace/backward/{tlc}", params=params)
        return TraceResult(**data)
    
    def get_timeline(self, tlc: str) -> List[TimelineEvent]:
        """
        Get chronological timeline of all events for a lot.
        
        Args:
            tlc: Traceability Lot Code
        
        Returns:
            List of TimelineEvent objects in chronological order
        """
        data = self._request("GET", f"/api/graph/fsma/timeline/{tlc}")
        return [TimelineEvent(**e) for e in data.get("events", [])]
    
    # =========================================================================
    # FTL Checker
    # =========================================================================
    
    def check_ftl(self, product_category: str) -> FTLResult:
        """
        Check if a product category is on FDA's Food Traceability List.
        
        Args:
            product_category: Category ID (e.g., 'leafy-greens', 'finfish')
        
        Returns:
            FTLResult with coverage status, CTEs, and KDEs required
        """
        data = self._request("GET", f"/api/compliance/ftl/{product_category}")
        return FTLResult(**data)
    
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
        data = self._request("POST", "/api/graph/fsma/recall/drills", json=payload)
        return RecallDrill(**data)
    
    def get_recall_drills(self, limit: int = 20) -> List[RecallDrill]:
        """
        Get history of mock recall drills.
        
        Args:
            limit: Maximum number of drills to return
        
        Returns:
            List of RecallDrill objects
        """
        data = self._request("GET", "/api/graph/fsma/recall/drills", params={"limit": limit})
        return [RecallDrill(**d) for d in data.get("drills", [])]
    
    def get_readiness_score(self) -> ReadinessScore:
        """
        Get your FSMA 204 recall readiness score.
        
        Returns:
            ReadinessScore with score and recommendations
        """
        data = self._request("GET", "/api/graph/fsma/recall/readiness")
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
        """
        params = {
            "tlc": tlc,
            "start_date": start_date,
            "end_date": end_date,
        }
        return self._request_bytes("GET", "/api/graph/fsma/export/fda-spreadsheet", params=params)
