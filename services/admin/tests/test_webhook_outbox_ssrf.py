"""SSRF coverage for ``app.webhook_outbox.default_http_poster``.

Regression for Suite 3 of the 2026-05-12 audit: ``default_http_poster``
previously called raw ``httpx.Client`` against tenant-registered
webhook URLs, so a tenant could direct the outbox at
``http://169.254.169.254/`` (cloud metadata) or RFC 1918 hosts and exfil
internal state.

The fix routes through ``shared.safe_http.safe_httpx_post_sync``, which
runs the URL through ``shared.url_validation.validate_url`` and pins the
connection to a validated IP. These tests prove the pipeline is wired
up by pointing the poster at IPs that ``BLOCKED_NETWORKS`` covers and
asserting an ``SSRFError`` (or its ``ValueError`` cousin) propagates
before any socket is opened.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))
sys.path.insert(0, str(service_dir.parent / "shared"))

pytest.importorskip("httpx")

# Import directly from the package so we get the same module identity
# that ``shared.safe_http`` imports — avoids drift if a sibling test
# stuffed something into ``sys.modules['shared.url_validation']``.
import app.webhook_outbox as wo  # noqa: E402
from shared.url_validation import SSRFError  # noqa: E402


def test_default_http_poster_rejects_metadata_ip() -> None:
    """169.254.169.254 must NOT reach the network layer.

    ``BLOCKED_NETWORKS`` includes 169.254.0.0/16 so the safe wrapper
    refuses before a socket is opened. We accept either ``SSRFError``
    (raised by the validator itself) or a generic ``Exception`` whose
    chain contains ``SSRFError`` — implementations vary by call path.
    """
    with pytest.raises((SSRFError, ValueError)) as exc_info:
        wo.default_http_poster(
            "http://169.254.169.254/latest/meta-data/",
            b"{}",
            {"Content-Type": "application/json"},
        )
    # Sanity: the error mentions the blocked address or a validation phrase.
    msg = str(exc_info.value).lower()
    assert "169.254" in msg or "blocked" in msg or "validation" in msg or "ssrf" in msg, msg


def test_default_http_poster_rejects_rfc1918() -> None:
    """Internal RFC 1918 hosts must be rejected by the safe wrapper."""
    with pytest.raises((SSRFError, ValueError)) as exc_info:
        wo.default_http_poster(
            "http://10.0.0.1/admin",
            b"{}",
            {},
        )
    msg = str(exc_info.value).lower()
    assert "10.0.0" in msg or "blocked" in msg or "validation" in msg or "ssrf" in msg, msg
