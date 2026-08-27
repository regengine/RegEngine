"""Secret-gated trust check for the internal service-to-service tenant header.

Pre-auth middleware runs before FastAPI route dependencies, so it has no
authenticated principal to read a tenant from. The repo's established answer
(``services/shared/middleware/tenant_context.py`` Method 2) is that the *only*
header a pre-auth layer may trust for tenant identity is
``X-RegEngine-Tenant-ID``, and only when the caller also proves it is an
internal service by presenting ``X-RegEngine-Internal-Secret`` matching the
``REGENGINE_INTERNAL_SECRET`` env var.

A plain ``X-Tenant-ID`` is never trustworthy pre-auth: the gateway does not
strip it, any client can set it, and the trusted-tenant path in
``tenant_context.py`` deliberately refuses it. #2841 (idempotency cache
namespace) and #2844 (rate-limit bucket) were both instances of a pre-auth
control trusting that header; this helper is the shared gate they now use.

The secret is read from the environment on every call rather than cached at
import time so rotation takes effect without a restart, and so tests can set
it with ``monkeypatch.setenv``.
"""

from __future__ import annotations

import hmac
import os
from typing import Optional

INTERNAL_TENANT_HEADER = "X-RegEngine-Tenant-ID"
INTERNAL_SECRET_HEADER = "X-RegEngine-Internal-Secret"
INTERNAL_SECRET_ENV = "REGENGINE_INTERNAL_SECRET"


def is_internal_caller(headers) -> bool:
    """True when the request proves internal-service origin.

    Fails closed: an unset or empty ``REGENGINE_INTERNAL_SECRET`` means no
    caller is internal, so a deployment that forgets to configure the secret
    degrades to "nobody is trusted" rather than "everybody is".
    """
    configured = os.getenv(INTERNAL_SECRET_ENV)
    if not configured:
        return False
    presented = headers.get(INTERNAL_SECRET_HEADER)
    if not presented:
        return False
    return hmac.compare_digest(presented, configured)


def internal_tenant_id(headers) -> Optional[str]:
    """Return the internal-header tenant, but only for a proven internal caller.

    Returns ``None`` for every external request — including one that supplies
    ``X-RegEngine-Tenant-ID`` without a valid secret — so callers can treat
    ``None`` as "no trusted tenant available at this point in the request".
    """
    tenant = headers.get(INTERNAL_TENANT_HEADER)
    if not tenant:
        return None
    if not is_internal_caller(headers):
        return None
    stripped = tenant.strip()
    return stripped or None
