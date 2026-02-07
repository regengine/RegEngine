"""URL and path validation utilities for SSRF and path traversal protection."""

from __future__ import annotations

import re
import socket
from ipaddress import ip_address, ip_network
from typing import Optional
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger("url-validation")

# Allowed URL schemes
ALLOWED_SCHEMES = frozenset({"http", "https"})

# Blocked hostnames (case-insensitive)
BLOCKED_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
    "metadata.google.internal",
    "metadata.google",
    "169.254.169.254",
})

# Blocked IP networks (private/internal ranges)
BLOCKED_NETWORKS = [
    ip_network("10.0.0.0/8"),
    ip_network("172.16.0.0/12"),
    ip_network("192.168.0.0/16"),
    ip_network("127.0.0.0/8"),
    ip_network("169.254.0.0/16"),  # Link-local / AWS metadata
    ip_network("::1/128"),
    ip_network("fc00::/7"),  # IPv6 private
    ip_network("fe80::/10"),  # IPv6 link-local
]

# S3 key pattern validation
S3_KEY_PATTERN = re.compile(r"^[a-zA-Z0-9!_.*'()/-]+$")


class SSRFError(ValueError):
    """Raised when a URL fails SSRF validation."""
    pass


class PathTraversalError(ValueError):
    """Raised when a path contains traversal sequences."""
    pass


def validate_url(
    url: str,
    allowed_schemes: frozenset[str] | None = None,
    allowed_domains: list[str] | None = None,
    resolve_dns: bool = True,
) -> str:
    """Validate URL against SSRF attacks.
    
    Args:
        url: The URL to validate
        allowed_schemes: Set of allowed schemes (default: http, https)
        allowed_domains: Optional allowlist of domain suffixes
        resolve_dns: Whether to resolve DNS and check IP (default: True)
    
    Returns:
        The validated URL (unchanged)
    
    Raises:
        SSRFError: If URL fails validation
    """
    schemes = allowed_schemes or ALLOWED_SCHEMES
    
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SSRFError(f"Invalid URL format: {url}") from exc
    
    # Check scheme
    if parsed.scheme.lower() not in schemes:
        raise SSRFError(f"Invalid URL scheme '{parsed.scheme}'. Allowed: {schemes}")
    
    # Check for empty host
    if not parsed.netloc:
        raise SSRFError("URL must include a host")
    
    # Extract hostname (handle IPv6 brackets)
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("Could not extract hostname from URL")
    
    hostname_lower = hostname.lower()
    
    # Check blocked hostnames
    if hostname_lower in BLOCKED_HOSTS:
        raise SSRFError(f"Blocked host: {hostname}")
    
    # Check domain allowlist if provided
    if allowed_domains:
        if not any(hostname_lower.endswith(domain.lower()) for domain in allowed_domains):
            raise SSRFError(f"Host '{hostname}' not in allowed domains: {allowed_domains}")
    
    # Resolve DNS and check IP if enabled
    if resolve_dns:
        _check_resolved_ip(hostname)
    
    logger.debug("url_validated", url=url, hostname=hostname)
    return url


def _check_resolved_ip(hostname: str) -> None:
    """Resolve hostname and verify IP is not in blocked ranges."""
    try:
        # Try to parse as IP directly first
        try:
            ip = ip_address(hostname)
        except ValueError:
            # Not an IP, resolve via DNS
            resolved = socket.gethostbyname(hostname)
            ip = ip_address(resolved)
        
        # Check against blocked networks
        for network in BLOCKED_NETWORKS:
            if ip in network:
                raise SSRFError(f"Resolved IP {ip} is in blocked network {network}")
                
    except socket.gaierror as exc:
        # DNS resolution failed - could be legit or could be attack
        logger.warning("dns_resolution_failed", hostname=hostname, error=str(exc))
        raise SSRFError(f"Could not resolve hostname: {hostname}") from exc


def validate_s3_key(key: str) -> str:
    """Validate S3 object key against path traversal attacks.
    
    Args:
        key: The S3 object key to validate
    
    Returns:
        The validated key (unchanged)
    
    Raises:
        PathTraversalError: If key contains traversal patterns
    """
    if not key:
        raise PathTraversalError("S3 key cannot be empty")
    
    # Check for path traversal sequences
    if ".." in key:
        raise PathTraversalError("S3 key cannot contain '..' sequences")
    
    # Check for absolute paths
    if key.startswith("/"):
        raise PathTraversalError("S3 key cannot start with '/'")
    
    # Check for null bytes
    if "\x00" in key:
        raise PathTraversalError("S3 key cannot contain null bytes")
    
    # Validate characters (AWS S3 safe characters)
    if not S3_KEY_PATTERN.match(key):
        raise PathTraversalError(f"S3 key contains invalid characters: {key}")
    
    logger.debug("s3_key_validated", key=key)
    return key


def validate_s3_uri(uri: str) -> tuple[str, str]:
    """Validate and parse an S3 URI.
    
    Args:
        uri: S3 URI in format s3://bucket/key
    
    Returns:
        Tuple of (bucket, key)
    
    Raises:
        ValueError: If URI format is invalid
        PathTraversalError: If key contains traversal patterns
    """
    if not uri.startswith("s3://"):
        raise ValueError(f"Invalid S3 URI scheme: {uri}")
    
    # Remove scheme
    path = uri[5:]
    
    # Split bucket and key
    if "/" not in path:
        raise ValueError(f"S3 URI must include bucket and key: {uri}")
    
    bucket, key = path.split("/", 1)
    
    if not bucket:
        raise ValueError("S3 bucket name cannot be empty")
    
    if not key:
        raise ValueError("S3 key cannot be empty")
    
    # Validate bucket name (simplified AWS rules)
    if not re.match(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", bucket):
        raise ValueError(f"Invalid S3 bucket name: {bucket}")
    
    # Validate key
    validate_s3_key(key)
    
    return bucket, key
