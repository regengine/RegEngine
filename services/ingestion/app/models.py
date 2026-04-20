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

    # Pydantic v2's HttpUrl preserves IPv6 URL brackets on ``.host``
    # (``https://[fd00:ec2::254]/`` -> ``host == "[fd00:ec2::254]"``).
    # Strip them before any comparison/resolution so the metadata
    # blocklist and literal-IP short-circuit below are not bypassed.
    host_bare = host.strip("[]")

    # Block known metadata endpoint hostnames directly. Matching against
    # the bracket-stripped form is required for the IPv6 entries in
    # ``_BLOCKED_HOSTNAMES`` (e.g. ``fd00:ec2::254``) to fire at all.
    if host_bare.lower() in _BLOCKED_HOSTNAMES:
        raise ValueError(
            f"Requests to '{host}' are not permitted (metadata endpoint)."
        )

    # Short-circuit literal-IP URLs: if the host is already an IPv4 or
    # IPv6 address, don't bother with DNS — apply the private-range
    # check directly. This catches ``https://10.0.0.1/`` and
    # ``https://[fd00::1]/`` even in environments where the resolver
    # might fail or where ``getaddrinfo`` would silently accept the
    # literal and pass it back unchanged.
    try:
        literal_ip = ipaddress.ip_address(host_bare)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        _reject_if_private_ip(literal_ip, host)
        return

    # Resolve the hostname and check all returned addresses
    try:
        addrinfos = socket.getaddrinfo(host_bare, None)
    except socket.gaierror:
        # If DNS resolution fails we cannot verify safety — reject
        raise ValueError(f"Unable to resolve hostname '{host}'.")

    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        _reject_if_private_ip(addr, host, resolved_as=ip_str)


def _reject_if_private_ip(
    addr: "ipaddress.IPv4Address | ipaddress.IPv6Address",
    host: str,
    *,
    resolved_as: Optional[str] = None,
) -> None:
    """Raise ValueError if ``addr`` is in any blocked range.

    Shared tail of :func:`_reject_private_host` so the literal-IP
    short-circuit and the DNS-resolved path use exactly the same
    classifier. ``resolved_as`` is the DNS-observed IP literal for
    the error message; pass ``None`` when ``host`` itself was a
    literal IP.
    """
    detail = f"resolved '{host}' → {resolved_as}" if resolved_as else f"host '{host}'"
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        raise ValueError(
            f"Requests to private or reserved IP addresses are not permitted "
            f"({detail})."
        )
    for network in _SSRF_BLOCKED_NETWORKS:
        if addr in network:
            raise ValueError(
                f"Requests to private or reserved IP addresses are not permitted "
                f"({detail})."
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
    event_entry_timestamp: Optional[datetime] = None  # FDA 21 CFR 1.1455; added by migration v054
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


# Response models for ingestion routes

class IngestRegulationResponse(BaseModel):
    """Response from POST /v1/ingest/regulation."""

    job_id: str
    status: str
    message: str
    webhook: Optional[str] = None


class ManualQueueItem(BaseModel):
    """Item in the manual queue response."""

    index: int
    body: str
    url: Optional[str] = None


class ManualQueueResponse(BaseModel):
    """Response from GET /v1/ingest/manual-queue."""

    tenant_id: str
    total: int
    skip: int
    limit: int
    items: List[ManualQueueItem]


class DiscoveryApprovalResponse(BaseModel):
    """Response from POST /v1/ingest/discovery/approve."""

    status: str
    body: str
    url: str


class DiscoveryRejectionResponse(BaseModel):
    """Response from POST /v1/ingest/discovery/reject."""

    status: str
    index: int


class BulkDiscoveryApprovalItem(BaseModel):
    """Item in bulk approval response."""

    body: str
    url: str


class BulkDiscoveryApprovalResponse(BaseModel):
    """Response from POST /v1/ingest/discovery/bulk-approve."""

    status: str
    count: int
    items: List[BulkDiscoveryApprovalItem]


class BulkDiscoveryRejectionResponse(BaseModel):
    """Response from POST /v1/ingest/discovery/bulk-reject."""

    status: str
    count: int


class ScrapeResponse(BaseModel):
    """Response from POST /v1/scrape/cppa."""

    status: str
    message: str


class ScrapeRegistrySource(BaseModel):
    """Source item in registry scrape response."""

    pass  # Dynamic structure: varies by adaptor


class ScrapeRegistryResponse(BaseModel):
    """Response from POST /scrape/{adaptor}."""

    adaptor: str
    count: int
    sources: List[dict]


class IngestAllRegulationsResponse(BaseModel):
    """Response from POST /v1/ingest/all-regulations."""

    job_id: str
    status: str
    jurisdiction: str
    duration_ms: int
    sources_attempted: int
    queued_manual: int
    unchanged: int
    ingested: int
    failed: int


class SourceCapability(BaseModel):
    """Capability of a source adapter."""

    pass  # Will contain string values


class SourceItem(BaseModel):
    """Individual source in the sources list."""

    id: str
    name: str
    type: str
    jurisdiction: str
    capabilities: List[str]


class ListSourcesResponse(BaseModel):
    """Response from GET /v1/ingest/sources."""

    sources: List[SourceItem]


class FederalRegisterResponse(BaseModel):
    """Response from POST /v1/ingest/federal-register."""

    status: str
    job_id: str
    message: str


class ECFRResponse(BaseModel):
    """Response from POST /v1/ingest/ecfr."""

    status: str
    job_id: str
    message: str


class FDAResponse(BaseModel):
    """Response from POST /v1/ingest/fda."""

    status: str
    job_id: str
    message: str


class IngestionStatusResponse(BaseModel):
    """Response from GET /v1/ingest/status/{job_id}."""

    job_id: str
    status: str
    result: Optional[dict] = None


class DocumentAnalysisResponse(BaseModel):
    """Response from GET /v1/ingest/documents/{document_id}/analysis."""

    document_id: str
    status: str
    risk_score: int
    obligations_count: int
    missing_dates_count: int
    critical_risks: List[dict]


class JobStatusResponse(BaseModel):
    """Response from GET /v1/audit/jobs/{job_id}."""

    pass  # Will return raw job dict from db_manager


class AuditLogEntry(BaseModel):
    """Individual audit log entry."""

    pass  # Will contain audit log structure


class JobLogsResponse(BaseModel):
    """Response from GET /v1/audit/logs/{job_id}."""

    job_id: str
    entries: List[dict]


class DocumentMetadata(BaseModel):
    """Metadata for a document in list_documents response."""

    pass  # Dynamic structure


class ListDocumentsResponse(BaseModel):
    """Response from GET /v1/ingest/documents."""

    documents: List[dict]
    count: int


class DocumentHash(BaseModel):
    """Hash values for a document."""

    content_sha256: str
    content_sha512: str
    text_sha256: str
    text_sha512: str


class VerifyDocumentResponse(BaseModel):
    """Response from GET /v1/verify/{document_id}."""

    document_id: str
    status: str
    hashes: DocumentHash
    verified_at: str


BulkDiscoveryRequest.model_rebuild()
