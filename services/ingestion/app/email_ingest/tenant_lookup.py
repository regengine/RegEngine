"""Recipient-address + sender -> tenant_id resolution for the inbound-email webhook.

At webhook-receipt time there is no tenant context yet, so this goes through
the ``fsma.get_tenant_by_inbound_address`` SECURITY DEFINER bootstrap
function added in migration v121 and hardened in v122 — the same bootstrap
shape as ``get_remediation_token_by_hash`` (v095) for exactly the same "no
tenant context yet" problem.

v122: Postmark's Basic-Auth webhook credential only authenticates the
transport ("this call came from Postmark") — it says nothing about who sent
the underlying email, and Postmark will forward mail from *any* internet
sender addressed to a configured inbound address using that same shared
credential. The recipient address alone is therefore not a tenant boundary
by itself (inbound addresses are provisioned ad hoc, with no stated entropy
requirement). ``sender`` is now a required argument, checked in the database
against that tenant's ``allowed_senders`` allowlist — a row with no
configured allowlist authorizes no sender at all (fail closed).
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text


def lookup_tenant_by_inbound_address(session: Any, address: str, sender: str) -> Optional[str]:
    """Resolve a tenant_id from a recipient address AND an authorized sender.

    Returns ``None`` when the address is unmapped/inactive, or when ``sender``
    does not match that tenant's ``allowed_senders`` allowlist. The session is
    committed afterward to release the transaction-local GUCs
    (``app.inbound_lookup_address``, and ``app.tenant_id`` when the bootstrap
    pinned it) that ``fsma.get_tenant_by_inbound_address`` sets for the
    duration of the lookup.
    """
    row = session.execute(
        # nosemgrep: avoid-sqlalchemy-text — SECURITY DEFINER function, parameterized address/sender
        text("SELECT fsma.get_tenant_by_inbound_address(:addr, :sender) AS tenant_id"),
        {"addr": address.strip().lower(), "sender": (sender or "").strip().lower()},
    ).fetchone()
    session.commit()
    return str(row.tenant_id) if row and row.tenant_id else None
