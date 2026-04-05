"""Pydantic models used by the ingestion API."""

from __future__ import annotations

import ipaddress
import socket
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator

# ---------------------------------------------------------------------------
# SSRF protection (#549)
# Block requests to private IP ranges and well-known metadata endpoints.
# ---------------------------------------------------------------------------

_BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "169.254.169.254",          # AWS/GCP/Azure IMDS
    "fd00:ec2::254",            # AWS IPv6 IMDS
})

_SSRF_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / IMDS
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]


def _reject_private_host(url: HttpUrl) -> None:
    """Raise ValueError if the URL resolves to a private or metadata IP address."""
    host = url.host
    if not host:
        raise ValueError("URL must include a hostname.")

    # Block known metadata endpoint hostnames directly
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Requests to '{host}' are not permitted (metadata endpoint).")

    # Resolve the hostname and check all returned addresses
    try:
        addrinfos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # If DNS resolution fails we cannot verify safety — reject
        raise ValueError(f"Unable to resolve hostname '{host}'.")

    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise ValueError(
                f"Requests to private or reserved IP addresses are not permitted "
                f"(resolved '{host}' → {ip_str})."
            )
        for network in _SSRF_BLOCKED_NETWORKS:
            if addr in network:
                raise ValueError(
                    f"Requests to private or reserved IP addresses are not permitted "
                    f"(resolved '{host}' → {ip_str})."
                )


class IngestRequest(BaseModel):
    """Request payload for URL ingestion."""

    url: HttpUrl
    source_system: str = Field(..., min_length=1, max_length=200)
    vertical: Optional[str] = Field(None, description="Regulatory vertical")

    @field_validator("url")
    @classmethod
    def url_must_not_be_private(cls, v: HttpUrl) -> HttpUrl:
        _reject_private_host(v)
        return v


class DirectIngestRequest(BaseModel):
    """Request payload for direct text or byte ingestion."""

    text: Optional[str] = None
    source_url: Optional[str] = "manual://direct"
    source_system: str = Field(..., min_length=1, max_length=200)
    vertical: Optional[str] = Field(None, description="Regulatory vertical")


class PositionMapEntry(BaseModel):
    """Mapping from normalized text offsets back to source artifacts."""

    page: int = Field(..., ge=1)
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)
    source_start: Optional[int] = Field(default=None, ge=0)
    source_end: Optional[int] = Field(default=None, ge=0)


class TextExtractionMetadata(BaseModel):
    """Metadata about the text extraction process."""

    engine: str
    confidence_mean: float = Field(..., ge=0.0, le=1.0)
    confidence_std: float = Field(..., ge=0.0, le=1.0)


class NormalizedDocument(BaseModel):
    """Schema for normalized regulatory document payloads."""

    document_id: str
    source_url: HttpUrl
    source_system: str
    retrieved_at: datetime
    text: str
    title: Optional[str] = None
    jurisdiction: Optional[str] = None
    position_map: Optional[List[PositionMapEntry]] = None
    text_extraction: Optional[TextExtractionMetadata] = None
    content_sha256: str
    content_type: Optional[str] = None

    @field_validator("source_url")
    @classmethod
    def source_url_must_not_be_private(cls, v: HttpUrl) -> HttpUrl:
        _reject_private_host(v)
        return v


class NormalizedEvent(BaseModel):
    """Kafka event emitted after normalization."""

    event_id: str
    document_id: str
    document_hash: str  # Content hash for deduplication
    tenant_id: Optional[str] = None  # Tenant UUID for multi-tenancy
    source_system: str
    source_url: HttpUrl
    raw_s3_path: str
    normalized_s3_path: str
    text_s3_uri: Optional[str] = None  # Claim Check pointer for payloads > 1MB
    timestamp: datetime
    content_sha256: str
    is_duplicate: bool = False


class FederalRegisterIngestRequest(BaseModel):
    """Request payload for Federal Register ingestion."""

    vertical: str = Field(..., description="Regulatory vertical (e.g., fsma)")
    max_documents: int = Field(default=10, ge=1, le=100)
    date_from: Optional[datetime] = None
    agencies: Optional[List[str]] = None


class ECFRIngestRequest(BaseModel):
    """Request payload for eCFR ingestion."""

    vertical: str = Field(..., description="Regulatory vertical")
    cfr_title: int = Field(..., ge=1, le=50)
    cfr_part: int = Field(..., ge=1)


class FDAIngestRequest(BaseModel):
    """Request payload for FDA ingestion."""

    vertical: str = Field(..., description="Regulatory vertical")
    max_documents: int = Field(default=10, ge=1, le=100)


class DiscoveryQueueItem(BaseModel):
    """Item in the manual discovery queue."""

    body: str
    url: str
    index: int


class BulkDiscoveryRequest(BaseModel):
    """Request payload for bulk discovery operations."""

    indices: List[int]


class ExportHistoryItem(BaseModel):
    """Individual export record in history."""

    export_id: str
    format: str
    lot_code: Optional[str] = None
    event_count: int
    generated_at: str
    file_name: str


class ExportHistoryResponse(BaseModel):
    """Response for export history endpoint."""

    tenant_id: str
    exports: List[ExportHistoryItem]
    total: int


class ExportVerifyResponse(BaseModel):
    """Response for export verification endpoint."""

    export_id: str
    original_hash: str
    regenerated_hash: str
    hashes_match: bool
    original_record_count: int
    current_record_count: int
    data_integrity: str
    original_generated_at: str
    verified_at: str


BulkDiscoveryRequest.model_rebuild()
