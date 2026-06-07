"""
Entity registration and alias management for identity resolution.

Mechanically split out of ``service.py`` — no logic changes. These
methods are mixed into :class:`shared.identity_resolution.service.
IdentityResolutionService`; they are not a standalone API.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import text

from shared.identity_resolution.constants import (
    VALID_ENTITY_TYPES,
    VALID_ALIAS_TYPES,
)
from shared.identity_resolution.normalization import _normalize_identifier
# #1233: PII masking helpers for log emission. Raw alias_value /
# canonical_name must never reach the log sinks — log retention is
# typically longer than DB retention and sinks are accessible to a
# wider personnel surface (SRE, observability vendors).
from shared.pii import mask_alias_value, mask_name

logger = logging.getLogger("identity-resolution")


class RegistrationMixin:
    """Registration / alias write methods of ``IdentityResolutionService``."""

    # ------------------------------------------------------------------
    # 1. Register Entity
    # ------------------------------------------------------------------

    def register_entity(
        self,
        tenant_id: str,
        entity_type: str,
        canonical_name: str,
        *,
        gln: Optional[str] = None,
        gtin: Optional[str] = None,
        fda_registration: Optional[str] = None,
        internal_id: Optional[str] = None,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
        contact_email: Optional[str] = None,
        confidence_score: float = 1.0,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a canonical entity record and seed its primary name alias.

        Returns the newly created entity as a dict.
        """
        # #1230: verify the tenant before any side effects
        self._verify_tenant_access(tenant_id)

        if entity_type not in VALID_ENTITY_TYPES:
            raise ValueError(f"Invalid entity_type '{entity_type}'. Must be one of {sorted(VALID_ENTITY_TYPES)}")

        # #1212: normalize structured identifiers before storing on the
        # canonical entity row.  Free-text fields (canonical_name, address,
        # contact_*) are intentionally left untouched.
        if gln is not None:
            gln = _normalize_identifier("gln", gln)
        if gtin is not None:
            gtin = _normalize_identifier("gtin", gtin)
        if fda_registration is not None:
            fda_registration = _normalize_identifier("fda_registration", fda_registration)
        if internal_id is not None:
            internal_id = _normalize_identifier("internal_code", internal_id)

        entity_id = str(uuid4())
        now = datetime.now(timezone.utc)

        self.session.execute(
            text("""
                INSERT INTO fsma.canonical_entities (
                    entity_id, tenant_id, entity_type, canonical_name,
                    gln, gtin, fda_registration, internal_id,
                    address, city, state, country,
                    contact_name, contact_phone, contact_email,
                    verification_status, confidence_score, is_active,
                    created_at, updated_at, created_by
                ) VALUES (
                    :entity_id, :tenant_id, :entity_type, :canonical_name,
                    :gln, :gtin, :fda_registration, :internal_id,
                    :address, :city, :state, :country,
                    :contact_name, :contact_phone, :contact_email,
                    'unverified', :confidence_score, TRUE,
                    :now, :now, :created_by
                )
            """),
            {
                "entity_id": entity_id,
                "tenant_id": tenant_id,
                "entity_type": entity_type,
                "canonical_name": canonical_name,
                "gln": gln,
                "gtin": gtin,
                "fda_registration": fda_registration,
                "internal_id": internal_id,
                "address": address,
                "city": city,
                "state": state,
                "country": country,
                "contact_name": contact_name,
                "contact_phone": contact_phone,
                "contact_email": contact_email,
                "confidence_score": confidence_score,
                "now": now,
                "created_by": created_by,
            },
        )

        # Seed the canonical name as the first alias
        self._insert_alias(
            tenant_id=tenant_id,
            entity_id=entity_id,
            alias_type="name",
            alias_value=canonical_name,
            source_system="identity_resolution",
            confidence=1.0,
            created_by=created_by,
        )

        # If structured identifiers were provided, register them as aliases too
        identifier_aliases: List[Tuple[str, Optional[str]]] = [
            ("gln", gln),
            ("gtin", gtin),
            ("fda_registration", fda_registration),
            ("internal_code", internal_id),
        ]
        for alias_type, alias_value in identifier_aliases:
            if alias_value:
                self._insert_alias(
                    tenant_id=tenant_id,
                    entity_id=entity_id,
                    alias_type=alias_type,
                    alias_value=alias_value,
                    source_system="identity_resolution",
                    confidence=1.0,
                    created_by=created_by,
                )

        # #1233: canonical_name is PII (GDPR) when the entity is a
        # sole proprietor / natural person. Mask before emit — the
        # hashed suffix preserves log correlation without leaking.
        logger.info(
            "entity_registered",
            extra={
                "entity_id": entity_id,
                "tenant_id": tenant_id,
                "entity_type": entity_type,
                "canonical_name_masked": mask_name(canonical_name),
            },
        )

        return {
            "entity_id": entity_id,
            "tenant_id": tenant_id,
            "entity_type": entity_type,
            "canonical_name": canonical_name,
            "gln": gln,
            "gtin": gtin,
            "fda_registration": fda_registration,
            "internal_id": internal_id,
            "confidence_score": confidence_score,
            "verification_status": "unverified",
            "is_active": True,
            "created_at": now.isoformat(),
        }

    # ------------------------------------------------------------------
    # 2. Add Alias
    # ------------------------------------------------------------------

    def add_alias(
        self,
        tenant_id: str,
        entity_id: str,
        alias_type: str,
        alias_value: str,
        source_system: str,
        *,
        source_file: Optional[str] = None,
        confidence: float = 1.0,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add an alias to an existing entity.

        The (entity_id, alias_type, alias_value) combination must be unique.
        Returns the created alias record.
        """
        # #1230: verify the tenant before any side effects
        self._verify_tenant_access(tenant_id)

        if alias_type not in VALID_ALIAS_TYPES:
            raise ValueError(f"Invalid alias_type '{alias_type}'. Must be one of {sorted(VALID_ALIAS_TYPES)}")

        # #1212: normalize structured identifiers before insert.
        alias_value = _normalize_identifier(alias_type, alias_value)

        # Verify entity exists and belongs to this tenant
        self._require_entity(tenant_id, entity_id)

        alias_id = self._insert_alias(
            tenant_id=tenant_id,
            entity_id=entity_id,
            alias_type=alias_type,
            alias_value=alias_value,
            source_system=source_system,
            source_file=source_file,
            confidence=confidence,
            created_by=created_by,
        )

        # #1233: alias_value is a regulated identifier (DUNS, EIN,
        # FDA-registration number) or a name — either way, never log
        # the raw value. ``mask_alias_value`` dispatches on alias_type
        # to pick the right masking strategy.
        logger.info(
            "alias_added",
            extra={
                "alias_id": alias_id,
                "entity_id": entity_id,
                "alias_type": alias_type,
                "alias_value_masked": mask_alias_value(alias_type, alias_value),
                "tenant_id": tenant_id,
            },
        )

        return {
            "alias_id": alias_id,
            "entity_id": entity_id,
            "alias_type": alias_type,
            "alias_value": alias_value,
            "source_system": source_system,
            "confidence": confidence,
        }

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    def _insert_alias(
        self,
        tenant_id: str,
        entity_id: str,
        alias_type: str,
        alias_value: str,
        source_system: str,
        confidence: float = 1.0,
        source_file: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> str:
        """
        Insert an alias record. Returns the alias_id.

        Idempotency: the INSERT uses ON CONFLICT DO NOTHING against the
        (entity_id, alias_type, alias_value) unique index. The
        UNIQUE(tenant_id, alias_type, alias_value) constraint added in
        migration v059 (#1179) is the authoritative tenant-wide dedup
        barrier — if a concurrent transaction registered the same alias
        under a different entity, the INSERT is a no-op and the caller
        must re-SELECT to find the winning entity (#1190).
        """
        # #1212: normalize structured identifiers before insert so that
        # whitespace variants are collapsed to a single canonical form.
        alias_value = _normalize_identifier(alias_type, alias_value)

        alias_id = str(uuid4())
        now = datetime.now(timezone.utc)

        self.session.execute(
            text("""
                INSERT INTO fsma.entity_aliases (
                    alias_id, tenant_id, entity_id, alias_type, alias_value,
                    source_system, source_file, confidence,
                    created_at, created_by
                ) VALUES (
                    :alias_id, :tenant_id, :entity_id, :alias_type, :alias_value,
                    :source_system, :source_file, :confidence,
                    :now, :created_by
                )
                ON CONFLICT (entity_id, alias_type, alias_value) DO NOTHING
            """),
            {
                "alias_id": alias_id,
                "tenant_id": tenant_id,
                "entity_id": entity_id,
                "alias_type": alias_type,
                "alias_value": alias_value,
                "source_system": source_system,
                "source_file": source_file,
                "confidence": confidence,
                "now": now,
                "created_by": created_by,
            },
        )

        return alias_id

    def _require_entity(self, tenant_id: str, entity_id: str) -> None:
        """Raise ValueError if entity doesn't exist for this tenant."""
        row = self.session.execute(
            text("""
                SELECT 1 FROM fsma.canonical_entities
                WHERE tenant_id = :tenant_id AND entity_id = :entity_id
            """),
            {"tenant_id": tenant_id, "entity_id": entity_id},
        ).fetchone()

        if not row:
            raise ValueError(
                f"Entity '{entity_id}' not found for tenant '{tenant_id}'"
            )
