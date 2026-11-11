"""Transaction-scoped EDI replay protection, independent of the Redis cache.

Acquire before writing any events and record storage in that same transaction.
The advisory lock lasts until commit/rollback, even if a Redis claim expires.
Only a committed receipt may produce a duplicate response.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from shared.tenant_context import set_tenant_guc
from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class EDIInterchange:
    """Envelope identity; tenant always comes from authenticated ingest context."""

    sender_id: str
    receiver_id: str
    isa13: str

    @classmethod
    def from_envelope(cls, extracted: dict) -> EDIInterchange | None:
        """Match the cache's normalization and existing malformed-envelope fallback."""
        sender = (extracted.get("sender_id") or "").strip()
        isa13 = (extracted.get("isa13") or "").strip()
        if not sender or not isa13:
            return None
        return cls(sender, (extracted.get("receiver_id") or "").strip(), isa13)

    def _params(self, tenant_id: str) -> dict[str, str]:
        return {
            "tenant_id": str(UUID(tenant_id)),
            "sender_id": self.sender_id.strip(),
            "receiver_id": self.receiver_id.strip(),
            "isa13": self.isa13.strip(),
        }

    def reserve(self, session: Session, tenant_id: str) -> None:
        """Serialize this envelope and reject a still-valid committed receipt."""
        params = self._params(tenant_id)
        set_tenant_guc(session, params["tenant_id"])
        # Length-delimited JSON avoids colon ambiguity in partner identifiers.
        identity = json.dumps(["edi-interchange", *params.values()], separators=(",", ":"))
        lock_id = int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big", signed=True)
        locked = session.execute(text("SELECT pg_try_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id}).scalar_one()
        if not locked:
            raise HTTPException(
                status_code=503,
                detail={"message": "Interchange is still being processed. Retry after the delay.", "client_safe": True},
                headers={"Retry-After": "30"},
            )
        stored = session.execute(
            text("""
                SELECT 1 FROM fsma.edi_interchanges
                WHERE tenant_id = :tenant_id AND sender_id = :sender_id
                  AND receiver_id = :receiver_id AND isa13 = :isa13
                  AND expires_at > clock_timestamp()
            """),
            params,
        ).scalar_one_or_none()
        if stored is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate_interchange",
                    "message": "Interchange control number (ISA13) already processed. No events were ingested.",
                    "isa13": self.isa13,
                    "idempotent_replay": True,
                },
            )

    def is_stored(self, session: Session, tenant_id: str) -> bool:
        """Read-only: is there a still-valid committed receipt? Takes no lock."""
        params = self._params(tenant_id)
        set_tenant_guc(session, params["tenant_id"])
        stored = session.execute(
            text("""
                SELECT 1 FROM fsma.edi_interchanges
                WHERE tenant_id = :tenant_id AND sender_id = :sender_id
                  AND receiver_id = :receiver_id AND isa13 = :isa13
                  AND expires_at > clock_timestamp()
            """),
            params,
        ).scalar_one_or_none()
        return stored is not None

    def record_stored(self, session: Session, tenant_id: str) -> None:
        """Write the receipt before the event transaction commits; never fail open."""
        result = session.execute(
            text("""
                INSERT INTO fsma.edi_interchanges
                    (tenant_id, sender_id, receiver_id, isa13, stored_at, expires_at)
                VALUES (:tenant_id, :sender_id, :receiver_id, :isa13,
                        clock_timestamp(), clock_timestamp() + interval '7 days')
                ON CONFLICT (tenant_id, sender_id, receiver_id, isa13) DO UPDATE
                    SET stored_at = EXCLUDED.stored_at, expires_at = EXCLUDED.expires_at
                    WHERE edi_interchanges.expires_at <= clock_timestamp()
            """),
            self._params(tenant_id),
        )
        if result.rowcount != 1:
            raise RuntimeError("EDI receipt was already committed; refusing event commit")
