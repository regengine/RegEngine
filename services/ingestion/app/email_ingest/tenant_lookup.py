"""Recipient-address -> tenant_id resolution for the inbound-email webhook.

At webhook-receipt time there is no tenant context yet, so this goes through
the ``fsma.get_tenant_by_inbound_address`` SECURITY DEFINER bootstrap
function added in migration v121 — the same bootstrap shape as
``get_remediation_token_by_hash`` (v095) for exactly the same "no tenant
context yet" problem.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text


def lookup_tenant_by_inbound_address(session: Any, address: str) -> Optional[str]:
    """Resolve a tenant_id from a recipient address.

    Returns ``None`` when the address is unmapped or inactive. The session is
    committed afterward to release the transaction-local GUCs
    (``app.inbound_lookup_address``, and ``app.tenant_id`` when the bootstrap
    pinned it) that ``fsma.get_tenant_by_inbound_address`` sets for the
    duration of the lookup.
    """
    row = session.execute(
        # nosemgrep: avoid-sqlalchemy-text — SECURITY DEFINER function, parameterized address
        text("SELECT fsma.get_tenant_by_inbound_address(:addr) AS tenant_id"),
        {"addr": address.strip().lower()},
    ).fetchone()
    session.commit()
    return str(row.tenant_id) if row and row.tenant_id else None
