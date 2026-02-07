"""
Main client for RegEngine Energy API.
"""

import os
import time
from typing import Optional, Dict, Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import (
    SnapshotCreateRequest,
    SnapshotResponse,
    SnapshotListResponse,
    VerificationResult,
)
from .exceptions import (
    AuthenticationError,
    ValidationError,
    SnapshotCreationError,
    VerificationError,
    NetworkError,
    RateLimitError,
    RegEngineError,
)


class EnergyCompliance:
    """
    RegEngine Energy compliance client.
    
    Provides type-safe access to NERC CIP-013 compliance snapshot APIs.
    
    Example:
        >>> from regengine_energy import EnergyCompliance
        >>> client = EnergyCompliance(api_key="rge_...")
        >>> snapshot = client.snapshots.create(
        ...     substation_id="ALPHA-001",
        ...     facility_name="Alpha Substation",
        ...     system_status="NOMINAL",
        ...     assets=[...],
        ...     esp_config={...}
        ... )
        >>> print(snapshot.snapshot_id)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        """
        Initialize Energy compliance client.
        
        Args:
            api_key: RegEngine API key (or set REGENGINE_API_KEY env var)
            base_url: API base URL (default: production API)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            
        Raises:
            AuthenticationError: If API key is not provided
        """
        self.api_key = api_key or os.getenv("REGENGINE_API_KEY")
        if not self.api_key:
            raise AuthenticationError(
                "API key required. Provide via api_key parameter or REGENGINE_API_KEY environment variable."
            )
        
        self.base_url = base_url or "https://api.regengine.co/v1/energy"
        self.timeout = timeout
        
        # Create session with retry logic
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,  # 1s, 2s, 4s delays
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "regengine-energy-sdk/0.1.0",
        })
        
        # Initialize sub-clients
        self.snapshots = SnapshotClient(self)
        self.verification = VerificationClient(self)
    
    def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request with error handling.
        
        Args:
            method: HTTP method
            endpoint: API endpoint path
            **kwargs: Additional request parameters
            
        Returns:
            Parsed JSON response
            
        Raises:
            AuthenticationError: On 401 response
            ValidationError: On 400/422 response
            RateLimitError: On 429 response
            NetworkError: On connection errors
            RegEngineError: On other errors
        """
        url = urljoin(self.base_url, endpoint.lstrip("/"))
        
        try:
            response = self.session.request(
                method,
                url,
                timeout=self.timeout,
                **kwargs
            )
            
            # Handle specific error codes
            if response.status_code == 401:
                raise AuthenticationError(
                    "Invalid API key",
                    status_code=401,
                )
            elif response.status_code in (400, 422):
                error_data = response.json() if response.content else {}
                raise ValidationError(
                    error_data.get("detail", "Request validation failed"),
                    status_code=response.status_code,
                    details=error_data,
                )
            elif response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "60")
                raise RateLimitError(
                    f"Rate limit exceeded. Retry after {retry_after} seconds",
                    status_code=429,
                    details={"retry_after": retry_after},
                )
            elif response.status_code >= 500:
                raise RegEngineError(
                    f"Server error: {response.status_code}",
                    status_code=response.status_code,
                )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            raise NetworkError(f"Request timeout after {self.timeout}s")
        except requests.exceptions.ConnectionError as e:
            raise NetworkError(f"Connection failed: {str(e)}")
        except requests.exceptions.RequestException as e:
            if not isinstance(e, (AuthenticationError, ValidationError, RateLimitError, RegEngineError)):
                raise NetworkError(f"Request failed: {str(e)}")
            raise


class SnapshotClient:
    """Client for snapshot operations."""
    
    def __init__(self, client: EnergyCompliance):
        self._client = client
    
    def create(
        self,
        substation_id: str,
        facility_name: str,
        system_status: str,
        assets: list,
        esp_config: dict,
        patch_metrics: Optional[dict] = None,
        regulatory: Optional[dict] = None,
        trigger_reason: Optional[str] = None,
    ) -> SnapshotResponse:
        """
        Create a compliance snapshot.
        
        Args:
            substation_id: Substation identifier
            facility_name: Facility name
            system_status: System status (NOMINAL, DEGRADED, NON_COMPLIANT)
            assets: List of asset dictionaries
            esp_config: ESP configuration dictionary
            patch_metrics: Optional patch management metrics
            regulatory: Optional regulatory info
            trigger_reason: Optional human-readable trigger reason
            
        Returns:
            SnapshotResponse with snapshot details
            
        Raises:
            ValidationError: If request data is invalid
            SnapshotCreationError: If snapshot creation fails
        """
        # Validate request with Pydantic
        request = SnapshotCreateRequest(
            substation_id=substation_id,
            facility_name=facility_name,
            system_status=system_status,
            assets=assets,
            esp_config=esp_config,
            patch_metrics=patch_metrics or {},
            regulatory=regulatory,
            trigger_reason=trigger_reason or f"SDK snapshot for {substation_id}",
        )
        
        try:
            response_data = self._client._request(
                "POST",
                "/energy/snapshots",
                json=request.model_dump(),
            )
            
            return SnapshotResponse(**response_data)
            
        except (ValidationError, AuthenticationError, RateLimitError):
            raise
        except Exception as e:
            raise SnapshotCreationError(f"Snapshot creation failed: {str(e)}")
    
    def get(self, snapshot_id: str) -> SnapshotResponse:
        """
        Retrieve a specific snapshot.
        
        Args:
            snapshot_id: Snapshot UUID
            
        Returns:
            SnapshotResponse with snapshot details
        """
        response_data = self._client._request(
            "GET",
            f"/energy/snapshots/{snapshot_id}",
        )
        return SnapshotResponse(**response_data)
    
    def list(
        self,
        substation_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SnapshotListResponse:
        """
        List snapshots with pagination.
        
        Args:
            substation_id: Optional filter by substation
            limit: Maximum results per page
            offset: Pagination offset
            
        Returns:
            SnapshotListResponse with paginated results
        """
        params = {"limit": limit, "offset": offset}
        if substation_id:
            params["substation_id"] = substation_id
        
        response_data = self._client._request(
            "GET",
            "/energy/snapshots",
            params=params,
        )
        return SnapshotListResponse(**response_data)


class VerificationClient:
    """Client for chain integrity verification."""
    
    def __init__(self, client: EnergyCompliance):
        self._client = client
    
    def verify_chain(
        self,
        substation_id: str,
        snapshot_id: Optional[str] = None,
    ) -> VerificationResult:
        """
        Verify chain integrity for a substation.
        
        Args:
            substation_id: Substation to verify
            snapshot_id: Optional specific snapshot to verify
            
        Returns:
            VerificationResult with verification status
            
        Raises:
            VerificationError: If verification fails
        """
        endpoint = f"/energy/verify/latest/{substation_id}"
        if snapshot_id:
            endpoint += f"?snapshot_id={snapshot_id}"
        
        try:
            response_data = self._client._request("GET", endpoint)
            return VerificationResult(**response_data)
        except Exception as e:
            raise VerificationError(f"Verification failed: {str(e)}")
    
    def verify_latest(self, substation_id: str) -> VerificationResult:
        """
        Verify the latest snapshot for a substation.
        
        Args:
            substation_id: Substation identifier
            
        Returns:
            VerificationResult with verification status
        """
        try:
            response_data = self._client._request(
                "GET",
                f"/substations/{substation_id}/snapshots/latest/verify",
            )
            return VerificationResult(**response_data)
        except Exception as e:
            raise VerificationError(f"Latest snapshot verification failed: {str(e)}")
