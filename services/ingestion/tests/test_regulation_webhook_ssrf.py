"""SSRF coverage for the regulation-ingestion webhook callback.

Suite 3 of the 2026-05-12 audit found that ``routes_ingest.py`` and
``task_handlers_regulation.py`` both accepted a tenant-supplied
``webhook`` URL and called it via raw ``httpx.AsyncClient``. A tenant
could direct the post-ingest notification at internal targets
(``169.254.169.254``, RFC 1918) and use the response as an oracle.

The fix routes both call sites through
``shared.safe_http.safe_httpx_post_async``. These tests verify the
wiring: pointing the safe wrapper at the cloud metadata IP / an RFC
1918 host raises before any network call is made.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))
sys.path.insert(0, str(service_dir.parent / "shared"))

pytest.importorskip("httpx")

from shared.url_validation import SSRFError  # noqa: E402


def test_safe_httpx_post_async_rejects_metadata_ip() -> None:
    """The safe wrapper used by both regulation-ingestion paths must reject
    the cloud metadata IP without issuing a network request."""
    from shared.safe_http import safe_httpx_post_async

    with pytest.raises((SSRFError, ValueError)):
        asyncio.run(
            safe_httpx_post_async(
                "http://169.254.169.254/latest/meta-data/",
                json={"job_id": "x", "status": "completed"},
            )
        )


def test_safe_httpx_post_async_rejects_rfc1918() -> None:
    from shared.safe_http import safe_httpx_post_async

    with pytest.raises((SSRFError, ValueError)):
        asyncio.run(
            safe_httpx_post_async(
                "http://10.0.0.5/internal",
                json={"job_id": "x", "status": "failed"},
            )
        )
