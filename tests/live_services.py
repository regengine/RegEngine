"""Hard-fail gate for suites that target live HTTP services (#2503).

``tests/security/test_security_audit_fixes.py`` and
``tests/data_integrity/test_fsma_204_verification_phase2b.py`` exercise live
HTTP services (admin/ingestion/graph). Historically every request was wrapped
in a ``ConnectError``/``_service_available`` guard that called ``pytest.skip``
when the service was unreachable — and no CI job booted those services, so the
assertions never ran: the suites passed by skipping (#2503).

This helper makes "service unreachable" a *decision*, not a silent skip:

  * ``REGENGINE_REQUIRE_LIVE_SERVICES=1`` (or ``true``/``yes``) → ``pytest.fail``
    A CI job that boots the services and sets this flag can never go green by
    skipping — an unreachable service is a red gate.
  * unset → ``pytest.skip`` (local convenience: running the suite without the
    stack up still skips cleanly rather than erroring).

The proper long-term fix is to rebuild these suites against an in-process
``fastapi.testclient.TestClient`` so no network is involved; until then this
gate removes the false-green.
"""

from __future__ import annotations

import os

import pytest


def require_live_services() -> bool:
    """True when CI has declared the live services are up and must be tested."""
    return os.getenv("REGENGINE_REQUIRE_LIVE_SERVICES", "").strip().lower() in {"1", "true", "yes"}


def skip_or_fail_service(service: str) -> None:
    """Skip locally, but FAIL when REGENGINE_REQUIRE_LIVE_SERVICES is set.

    ``service`` is a short label for the unreachable service, e.g.
    ``"Ingestion service"``.
    """
    reason = f"{service} not running"
    if require_live_services():
        pytest.fail(
            f"{reason} but REGENGINE_REQUIRE_LIVE_SERVICES=1 — this suite must run its "
            "assertions against the live service, not skip."
        )
    pytest.skip(reason)
