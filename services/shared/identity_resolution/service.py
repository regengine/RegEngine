"""
Identity Resolution Service.

Provides a durable cross-record identity layer for entities, facilities,
products, and lots within the FSMA traceability system. Supports canonical
entity registration, alias management, fuzzy matching, merge/split
operations, and human review queues for ambiguous matches.

Database tables (V047):
    - fsma.canonical_entities
    - fsma.entity_aliases
    - fsma.entity_merge_history
    - fsma.identity_review_queue
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.identity_resolution.constants import (
    VALID_ENTITY_TYPES,
    VALID_ALIAS_TYPES,
    VALID_REVIEW_STATUSES,
    AMBIGUOUS_THRESHOLD_LOW,
    AMBIGUOUS_THRESHOLD_HIGH,
)

logger = logging.getLogger("identity-resolution")


# ---------------------------------------------------------------------------
# Identity Resolution Service
# ---------------------------------------------------------------------------

class IdentityResolutionService:
    """
    Cross-record identity resolution for FSMA supply-chain entities.

    All methods are tenant-scoped. The caller must supply ``tenant_id``
    explicitly; this service never infers it.
    """

    def __init__(self, session: Session):
        self.session = session

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
        if entity_type not in VALID_ENTITY_TYPES:
            raise ValueError(f"Invalid entity_type '{entity_type}'. Must be one of {sorted(VALID_ENTITY_TYPES)}")

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

        logger.info(
            "entity_registered",
            extra={
                "entity_id": entity_id,
                "tenant_id": tenant_id,
                "entity_type": entity_type,
                "canonical_name": canonical_name,
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
        if alias_type not in VALID_ALIAS_TYPES:
            raise ValueError(f"Invalid alias_type '{alias_type}'. Must be one of {sorted(VALID_ALIAS_TYPES)}")

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

        logger.info(
            "alias_added",
            extra={
                "alias_id": alias_id,
                "entity_id": entity_id,
                "alias_type": alias_type,
                "alias_value": alias_value,
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
    # 3. Find Entity by Alias (exact lookup)
    # ------------------------------------------------------------------

    def find_entity_by_alias(
        self,
        tenant_id: str,
        alias_type: str,
        alias_value: str,
    ) -> List[Dict[str, Any]]:
        """
        Exact-match lookup by alias type and value.

        Returns a list of matching entities (there may be more than one
        if the alias hasn't been resolved/merged yet).
        """
        rows = self.session.execute(
            text("""
                SELECT ce.entity_id, ce.entity_type, ce.canonical_name,
                       ce.gln, ce.gtin, ce.fda_registration, ce.internal_id,
                       ce.verification_status, ce.confidence_score, ce.is_active,
                       ea.alias_id, ea.alias_type, ea.alias_value,
                       ea.source_system, ea.confidence AS alias_confidence
                FROM fsma.entity_aliases ea
                JOIN fsma.canonical_entities ce
                    ON ce.entity_id = ea.entity_id AND ce.tenant_id = ea.tenant_id
                WHERE ea.tenant_id = :tenant_id
                  AND ea.alias_type = :alias_type
                  AND ea.alias_value = :alias_value
                  AND ce.is_active = TRUE
            """),
            {
                "tenant_id": tenant_id,
                "alias_type": alias_type,
                "alias_value": alias_value,
            },
        ).fetchall()

        return [
            {
                "entity_id": str(r[0]),
                "entity_type": r[1],
                "canonical_name": r[2],
                "gln": r[3],
                "gtin": r[4],
                "fda_registration": r[5],
                "internal_id": r[6],
                "verification_status": r[7],
                "confidence_score": float(r[8]) if r[8] is not None else None,
                "is_active": r[9],
                "matched_alias": {
                    "alias_id": str(r[10]),
                    "alias_type": r[11],
                    "alias_value": r[12],
                    "source_system": r[13],
                    "confidence": float(r[14]) if r[14] is not None else None,
                },
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 4. Find Potential Matches (fuzzy)
    # ------------------------------------------------------------------

    def find_potential_matches(
        self,
        tenant_id: str,
        search_name: str,
        *,
        entity_type: Optional[str] = None,
        threshold: float = 0.6,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Confidence-scored fuzzy matching by name similarity.

        Uses SequenceMatcher (Ratcliff/Obershelp) from difflib on all
        name-type aliases for the tenant. Results are sorted by
        descending confidence.
        """
        params: Dict[str, Any] = {"tenant_id": tenant_id}
        type_filter = ""
        if entity_type:
            if entity_type not in VALID_ENTITY_TYPES:
                raise ValueError(f"Invalid entity_type '{entity_type}'")
            type_filter = "AND ce.entity_type = :entity_type"
            params["entity_type"] = entity_type

        rows = self.session.execute(
            text(f"""
                SELECT ce.entity_id, ce.entity_type, ce.canonical_name,
                       ce.gln, ce.gtin, ce.verification_status,
                       ce.confidence_score, ea.alias_value
                FROM fsma.entity_aliases ea
                JOIN fsma.canonical_entities ce
                    ON ce.entity_id = ea.entity_id AND ce.tenant_id = ea.tenant_id
                WHERE ea.tenant_id = :tenant_id
                  AND ea.alias_type IN ('name', 'trade_name', 'abbreviation')
                  AND ce.is_active = TRUE
                  {type_filter}
            """),
            params,
        ).fetchall()

        search_lower = search_name.lower().strip()
        scored: List[Dict[str, Any]] = []
        seen_entities: set = set()

        for r in rows:
            entity_id = str(r[0])
            alias_value = r[7] or ""
            ratio = SequenceMatcher(
                None, search_lower, alias_value.lower().strip()
            ).ratio()

            if ratio < threshold:
                continue

            # Keep only the best-scoring alias per entity
            if entity_id in seen_entities:
                # Update if this alias scores higher
                for item in scored:
                    if item["entity_id"] == entity_id and ratio > item["confidence"]:
                        item["confidence"] = round(ratio, 4)
                        item["matched_alias"] = alias_value
                        break
                continue

            seen_entities.add(entity_id)
            scored.append({
                "entity_id": entity_id,
                "entity_type": r[1],
                "canonical_name": r[2],
                "gln": r[3],
                "gtin": r[4],
                "verification_status": r[5],
                "entity_confidence": float(r[6]) if r[6] is not None else None,
                "confidence": round(ratio, 4),
                "matched_alias": alias_value,
            })

        scored.sort(key=lambda x: x["confidence"], reverse=True)
        return scored[:limit]

    # ------------------------------------------------------------------
    # 5. Merge Entities
    # ------------------------------------------------------------------

    def merge_entities(
        self,
        tenant_id: str,
        source_entity_id: str,
        target_entity_id: str,
        *,
        reason: Optional[str] = None,
        performed_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Merge source entity into target entity.

        - All aliases from the source are re-pointed to the target.
        - The source entity is deactivated (is_active = FALSE).
        - A merge_history record is created for auditability.
        - Any pending review-queue items involving the source are closed.

        Returns the merge history record.
        """
        if source_entity_id == target_entity_id:
            raise ValueError("Cannot merge an entity with itself")

        self._require_entity(tenant_id, source_entity_id)
        self._require_entity(tenant_id, target_entity_id)

        merge_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Re-point aliases from source to target (skip duplicates)
        self.session.execute(
            text("""
                UPDATE fsma.entity_aliases
                SET entity_id = :target_entity_id
                WHERE tenant_id = :tenant_id
                  AND entity_id = :source_entity_id
                  AND (entity_id, alias_type, alias_value) NOT IN (
                      SELECT entity_id, alias_type, alias_value
                      FROM fsma.entity_aliases
                      WHERE tenant_id = :tenant_id
                        AND entity_id = :target_entity_id
                  )
            """),
            {
                "tenant_id": tenant_id,
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
            },
        )

        # Remove any remaining aliases on the source (duplicates that couldn't move)
        self.session.execute(
            text("""
                DELETE FROM fsma.entity_aliases
                WHERE tenant_id = :tenant_id AND entity_id = :source_entity_id
            """),
            {"tenant_id": tenant_id, "source_entity_id": source_entity_id},
        )

        # Deactivate source entity
        self.session.execute(
            text("""
                UPDATE fsma.canonical_entities
                SET is_active = FALSE, updated_at = :now
                WHERE tenant_id = :tenant_id AND entity_id = :source_entity_id
            """),
            {"tenant_id": tenant_id, "source_entity_id": source_entity_id, "now": now},
        )

        # Record merge history
        self.session.execute(
            text("""
                INSERT INTO fsma.entity_merge_history (
                    merge_id, tenant_id, action, source_entity_ids,
                    target_entity_id, reason, performed_by, performed_at,
                    is_reversed
                ) VALUES (
                    :merge_id, :tenant_id, 'merge', ARRAY[:source_entity_id]::uuid[],
                    :target_entity_id, :reason, :performed_by, :now,
                    FALSE
                )
            """),
            {
                "merge_id": merge_id,
                "tenant_id": tenant_id,
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "reason": reason,
                "performed_by": performed_by,
                "now": now,
            },
        )

        # Close any pending review-queue items involving the merged source
        self.session.execute(
            text("""
                UPDATE fsma.identity_review_queue
                SET status = 'confirmed_match',
                    resolved_by = :performed_by,
                    resolved_at = :now,
                    resolution_notes = 'Auto-resolved by merge operation'
                WHERE tenant_id = :tenant_id
                  AND status = 'pending'
                  AND (entity_a_id = :source_entity_id OR entity_b_id = :source_entity_id)
            """),
            {
                "tenant_id": tenant_id,
                "source_entity_id": source_entity_id,
                "performed_by": performed_by,
                "now": now,
            },
        )

        logger.info(
            "entities_merged",
            extra={
                "merge_id": merge_id,
                "source_entity_id": source_entity_id,
                "target_entity_id": target_entity_id,
                "tenant_id": tenant_id,
            },
        )

        return {
            "merge_id": merge_id,
            "action": "merge",
            "source_entity_ids": [source_entity_id],
            "target_entity_id": target_entity_id,
            "reason": reason,
            "performed_by": performed_by,
            "performed_at": now.isoformat(),
        }

    # ------------------------------------------------------------------
    # 6. Split Entity (reverse a merge)
    # ------------------------------------------------------------------

    def split_entity(
        self,
        tenant_id: str,
        merge_id: str,
        *,
        performed_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Reverse a previous merge operation.

        - Looks up the original merge record.
        - Re-activates the source entity.
        - Restores aliases that originally belonged to the source entity
          (aliases added *after* the merge stay with the target).
        - Records the reversal in merge_history.

        Note: only the alias snapshot at merge time can be inferred from
        the source_system='identity_resolution' seed alias. Additional
        aliases that were on the source before merge cannot be perfectly
        reconstructed; those remain on the target. A full undo would
        require an alias snapshot table (future enhancement).
        """
        merge_row = self.session.execute(
            text("""
                SELECT merge_id, source_entity_ids, target_entity_id,
                       action, is_reversed
                FROM fsma.entity_merge_history
                WHERE tenant_id = :tenant_id AND merge_id = :merge_id
            """),
            {"tenant_id": tenant_id, "merge_id": merge_id},
        ).fetchone()

        if not merge_row:
            raise ValueError(f"Merge record '{merge_id}' not found for tenant '{tenant_id}'")
        if merge_row[3] != "merge":
            raise ValueError(f"Record '{merge_id}' is not a merge action")
        if merge_row[4]:
            raise ValueError(f"Merge '{merge_id}' has already been reversed")

        source_entity_ids = merge_row[1]  # UUID[]
        target_entity_id = str(merge_row[2])
        now = datetime.now(timezone.utc)

        # Re-activate source entities
        for src_id in source_entity_ids:
            src_id_str = str(src_id)
            self.session.execute(
                text("""
                    UPDATE fsma.canonical_entities
                    SET is_active = TRUE, updated_at = :now
                    WHERE tenant_id = :tenant_id AND entity_id = :entity_id
                """),
                {"tenant_id": tenant_id, "entity_id": src_id_str, "now": now},
            )

            # Restore the canonical-name alias back to the source entity
            source_entity = self.session.execute(
                text("""
                    SELECT canonical_name
                    FROM fsma.canonical_entities
                    WHERE tenant_id = :tenant_id AND entity_id = :entity_id
                """),
                {"tenant_id": tenant_id, "entity_id": src_id_str},
            ).fetchone()

            if source_entity and source_entity[0]:
                # Move the canonical name alias back if it's on the target
                self.session.execute(
                    text("""
                        UPDATE fsma.entity_aliases
                        SET entity_id = :source_entity_id
                        WHERE tenant_id = :tenant_id
                          AND entity_id = :target_entity_id
                          AND alias_type = 'name'
                          AND alias_value = :canonical_name
                    """),
                    {
                        "tenant_id": tenant_id,
                        "source_entity_id": src_id_str,
                        "target_entity_id": target_entity_id,
                        "canonical_name": source_entity[0],
                    },
                )

        # Mark original merge as reversed
        self.session.execute(
            text("""
                UPDATE fsma.entity_merge_history
                SET is_reversed = TRUE, reversed_by = :performed_by, reversed_at = :now
                WHERE tenant_id = :tenant_id AND merge_id = :merge_id
            """),
            {
                "tenant_id": tenant_id,
                "merge_id": merge_id,
                "performed_by": performed_by,
                "now": now,
            },
        )

        # Record the split action
        split_id = str(uuid4())
        self.session.execute(
            text("""
                INSERT INTO fsma.entity_merge_history (
                    merge_id, tenant_id, action, source_entity_ids,
                    target_entity_id, reason, performed_by, performed_at,
                    is_reversed
                ) VALUES (
                    :split_id, :tenant_id, 'split', :source_entity_ids,
                    :target_entity_id,
                    :reason, :performed_by, :now,
                    FALSE
                )
            """),
            {
                "split_id": split_id,
                "tenant_id": tenant_id,
                "source_entity_ids": source_entity_ids,
                "target_entity_id": target_entity_id,
                "reason": f"Reversal of merge {merge_id}",
                "performed_by": performed_by,
                "now": now,
            },
        )

        logger.info(
            "entity_split",
            extra={
                "split_id": split_id,
                "original_merge_id": merge_id,
                "source_entity_ids": [str(s) for s in source_entity_ids],
                "target_entity_id": target_entity_id,
                "tenant_id": tenant_id,
            },
        )

        return {
            "split_id": split_id,
            "original_merge_id": merge_id,
            "source_entity_ids": [str(s) for s in source_entity_ids],
            "target_entity_id": target_entity_id,
            "performed_by": performed_by,
            "performed_at": now.isoformat(),
        }

    # ------------------------------------------------------------------
    # 7. Queue Ambiguous Match for Human Review
    # ------------------------------------------------------------------

    def queue_for_review(
        self,
        tenant_id: str,
        entity_a_id: str,
        entity_b_id: str,
        match_type: str,
        match_confidence: float,
        *,
        matching_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add an ambiguous entity pair to the identity review queue.

        Idempotent: if the pair already exists (in either direction) and
        is still pending, the existing record is returned unchanged.
        """
        valid_match_types = {"exact", "likely", "ambiguous", "unresolved"}
        if match_type not in valid_match_types:
            raise ValueError(f"Invalid match_type '{match_type}'. Must be one of {sorted(valid_match_types)}")

        # Normalize ordering so (A,B) == (B,A)
        a_id, b_id = sorted([entity_a_id, entity_b_id])

        # Idempotency check
        existing = self.session.execute(
            text("""
                SELECT review_id, status, match_confidence
                FROM fsma.identity_review_queue
                WHERE tenant_id = :tenant_id
                  AND entity_a_id = :a_id
                  AND entity_b_id = :b_id
            """),
            {"tenant_id": tenant_id, "a_id": a_id, "b_id": b_id},
        ).fetchone()

        if existing:
            return {
                "review_id": str(existing[0]),
                "status": existing[1],
                "match_confidence": float(existing[2]) if existing[2] is not None else None,
                "idempotent": True,
            }

        review_id = str(uuid4())
        now = datetime.now(timezone.utc)

        self.session.execute(
            text("""
                INSERT INTO fsma.identity_review_queue (
                    review_id, tenant_id, entity_a_id, entity_b_id,
                    match_type, match_confidence, matching_fields,
                    status, created_at
                ) VALUES (
                    :review_id, :tenant_id, :a_id, :b_id,
                    :match_type, :match_confidence, :matching_fields,
                    'pending', :now
                )
            """),
            {
                "review_id": review_id,
                "tenant_id": tenant_id,
                "a_id": a_id,
                "b_id": b_id,
                "match_type": match_type,
                "match_confidence": match_confidence,
                "matching_fields": json.dumps(matching_fields or {}),
                "now": now,
            },
        )

        logger.info(
            "review_queued",
            extra={
                "review_id": review_id,
                "entity_a_id": a_id,
                "entity_b_id": b_id,
                "match_type": match_type,
                "match_confidence": match_confidence,
                "tenant_id": tenant_id,
            },
        )

        return {
            "review_id": review_id,
            "entity_a_id": a_id,
            "entity_b_id": b_id,
            "match_type": match_type,
            "match_confidence": match_confidence,
            "status": "pending",
            "idempotent": False,
        }

    # ------------------------------------------------------------------
    # 8. Resolve Review
    # ------------------------------------------------------------------

    def resolve_review(
        self,
        tenant_id: str,
        review_id: str,
        resolution: str,
        *,
        resolved_by: Optional[str] = None,
        resolution_notes: Optional[str] = None,
        auto_merge: bool = True,
    ) -> Dict[str, Any]:
        """
        Resolve a pending identity review item.

        resolution must be one of:
            - confirmed_match: the two entities are the same; optionally
              auto-merge them (if auto_merge=True).
            - confirmed_distinct: the two entities are different; no action.
            - deferred: postpone the decision.

        Returns the updated review record (and merge result if applicable).
        """
        if resolution not in VALID_REVIEW_STATUSES:
            raise ValueError(
                f"Invalid resolution '{resolution}'. Must be one of {sorted(VALID_REVIEW_STATUSES)}"
            )

        review = self.session.execute(
            text("""
                SELECT review_id, entity_a_id, entity_b_id, status
                FROM fsma.identity_review_queue
                WHERE tenant_id = :tenant_id AND review_id = :review_id
            """),
            {"tenant_id": tenant_id, "review_id": review_id},
        ).fetchone()

        if not review:
            raise ValueError(f"Review '{review_id}' not found for tenant '{tenant_id}'")
        if review[3] != "pending" and review[3] != "deferred":
            raise ValueError(f"Review '{review_id}' is already resolved with status '{review[3]}'")

        now = datetime.now(timezone.utc)

        self.session.execute(
            text("""
                UPDATE fsma.identity_review_queue
                SET status = :resolution,
                    resolved_by = :resolved_by,
                    resolved_at = :now,
                    resolution_notes = :resolution_notes
                WHERE tenant_id = :tenant_id AND review_id = :review_id
            """),
            {
                "tenant_id": tenant_id,
                "review_id": review_id,
                "resolution": resolution,
                "resolved_by": resolved_by,
                "now": now,
                "resolution_notes": resolution_notes,
            },
        )

        result: Dict[str, Any] = {
            "review_id": review_id,
            "entity_a_id": str(review[1]),
            "entity_b_id": str(review[2]),
            "resolution": resolution,
            "resolved_by": resolved_by,
            "resolved_at": now.isoformat(),
        }

        # Auto-merge if confirmed match
        if resolution == "confirmed_match" and auto_merge:
            merge_result = self.merge_entities(
                tenant_id=tenant_id,
                source_entity_id=str(review[1]),
                target_entity_id=str(review[2]),
                reason=f"Confirmed match via review {review_id}",
                performed_by=resolved_by,
            )
            result["merge"] = merge_result

        logger.info(
            "review_resolved",
            extra={
                "review_id": review_id,
                "resolution": resolution,
                "tenant_id": tenant_id,
            },
        )

        return result

    # ------------------------------------------------------------------
    # 9. Get Entity with All Aliases
    # ------------------------------------------------------------------

    def get_entity(
        self,
        tenant_id: str,
        entity_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a canonical entity with all its aliases.

        Returns None if the entity doesn't exist or belongs to a
        different tenant.
        """
        entity_row = self.session.execute(
            text("""
                SELECT entity_id, tenant_id, entity_type, canonical_name,
                       gln, gtin, fda_registration, internal_id,
                       address, city, state, country,
                       contact_name, contact_phone, contact_email,
                       verification_status, confidence_score, is_active,
                       created_at, updated_at, created_by,
                       verified_by, verified_at
                FROM fsma.canonical_entities
                WHERE tenant_id = :tenant_id AND entity_id = :entity_id
            """),
            {"tenant_id": tenant_id, "entity_id": entity_id},
        ).fetchone()

        if not entity_row:
            return None

        alias_rows = self.session.execute(
            text("""
                SELECT alias_id, alias_type, alias_value,
                       source_system, source_file, confidence,
                       created_at, created_by
                FROM fsma.entity_aliases
                WHERE tenant_id = :tenant_id AND entity_id = :entity_id
                ORDER BY alias_type, alias_value
            """),
            {"tenant_id": tenant_id, "entity_id": entity_id},
        ).fetchall()

        aliases = [
            {
                "alias_id": str(a[0]),
                "alias_type": a[1],
                "alias_value": a[2],
                "source_system": a[3],
                "source_file": a[4],
                "confidence": float(a[5]) if a[5] is not None else None,
                "created_at": a[6].isoformat() if a[6] else None,
                "created_by": a[7],
            }
            for a in alias_rows
        ]

        return {
            "entity_id": str(entity_row[0]),
            "tenant_id": str(entity_row[1]),
            "entity_type": entity_row[2],
            "canonical_name": entity_row[3],
            "gln": entity_row[4],
            "gtin": entity_row[5],
            "fda_registration": entity_row[6],
            "internal_id": entity_row[7],
            "address": entity_row[8],
            "city": entity_row[9],
            "state": entity_row[10],
            "country": entity_row[11],
            "contact_name": entity_row[12],
            "contact_phone": entity_row[13],
            "contact_email": entity_row[14],
            "verification_status": entity_row[15],
            "confidence_score": float(entity_row[16]) if entity_row[16] is not None else None,
            "is_active": entity_row[17],
            "created_at": entity_row[18].isoformat() if entity_row[18] else None,
            "updated_at": entity_row[19].isoformat() if entity_row[19] else None,
            "created_by": entity_row[20],
            "verified_by": entity_row[21],
            "verified_at": entity_row[22].isoformat() if entity_row[22] else None,
            "aliases": aliases,
        }

    # ------------------------------------------------------------------
    # 10. Auto-Register Entities from Canonical Events
    # ------------------------------------------------------------------

    def auto_register_from_event(
        self,
        tenant_id: str,
        event: Dict[str, Any],
        *,
        source_system: str = "canonical_event",
        created_by: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract entities (facilities, products, firms) from a canonical
        traceability event and register them if not already known.

        For each reference found in the event, this method:
        1. Checks whether an alias already resolves to a known entity.
        2. If not, registers a new canonical entity.
        3. If a fuzzy match exists in the ambiguous range, queues it
           for human review.

        Returns a dict of entity lists keyed by role:
            {
                "facilities": [...],
                "products": [...],
                "firms": [...],
            }
        """
        results: Dict[str, List[Dict[str, Any]]] = {
            "facilities": [],
            "products": [],
            "firms": [],
        }

        # --- Facilities ---
        facility_refs: List[Tuple[str, str]] = []
        if event.get("from_facility_reference"):
            facility_refs.append(("from_facility", event["from_facility_reference"]))
        if event.get("to_facility_reference"):
            facility_refs.append(("to_facility", event["to_facility_reference"]))

        for role, ref in facility_refs:
            entity = self._resolve_or_register(
                tenant_id=tenant_id,
                reference=ref,
                entity_type="facility",
                source_system=source_system,
                created_by=created_by,
            )
            results["facilities"].append({**entity, "role": role})

        # --- Products ---
        product_ref = event.get("product_reference")
        if product_ref:
            entity = self._resolve_or_register(
                tenant_id=tenant_id,
                reference=product_ref,
                entity_type="product",
                source_system=source_system,
                created_by=created_by,
            )
            results["products"].append(entity)

        # --- Firms (from_entity / to_entity) ---
        entity_refs: List[Tuple[str, str]] = []
        if event.get("from_entity_reference"):
            entity_refs.append(("from_entity", event["from_entity_reference"]))
        if event.get("to_entity_reference"):
            entity_refs.append(("to_entity", event["to_entity_reference"]))

        for role, ref in entity_refs:
            entity = self._resolve_or_register(
                tenant_id=tenant_id,
                reference=ref,
                entity_type="firm",
                source_system=source_system,
                created_by=created_by,
            )
            results["firms"].append({**entity, "role": role})

        # --- Lots (traceability_lot_code) ---
        # Fix #1175: TLC must be stored VERBATIM as alias_type='tlc' — the canonical
        # form required by FSMA 204 traceability. The GTIN-14 prefix is registered
        # as a SECONDARY `tlc_prefix` alias for fuzzy lookup only. Previously the
        # code stored `tlc_prefix` as the primary alias, which dropped the
        # variable lot-suffix and broke supplier trace-back.
        tlc = event.get("traceability_lot_code")
        if tlc:
            lot_entity = self._resolve_or_register(
                tenant_id=tenant_id,
                reference=tlc,
                entity_type="lot",
                alias_type="tlc",
                source_system=source_system,
                created_by=created_by,
            )
            # If the TLC is a GTIN-14 + lot-suffix, register the 14-digit
            # prefix as a secondary alias so prefix-based lookup still works
            # (used by product-family queries). This is NOT the canonical
            # identifier — it is a lossy fingerprint for fuzzy lookup.
            if len(tlc) > 14 and tlc[:14].isdigit():
                try:
                    self._insert_alias(
                        tenant_id=tenant_id,
                        entity_id=lot_entity["entity_id"],
                        alias_type="tlc_prefix",
                        alias_value=tlc[:14],
                        source_system=source_system,
                        confidence=0.8,
                        created_by=created_by,
                    )
                except (ValueError, RuntimeError) as exc:
                    # Non-fatal — the canonical TLC alias is already persisted.
                    logger.warning(
                        "tlc_prefix_secondary_alias_failed",
                        extra={
                            "entity_id": lot_entity["entity_id"],
                            "tlc": tlc,
                            "error": str(exc),
                        },
                    )
            # Lots are associated with products but tracked separately
            results.setdefault("lots", []).append(lot_entity)

        logger.info(
            "auto_register_from_event",
            extra={
                "tenant_id": tenant_id,
                "facilities": len(results["facilities"]),
                "products": len(results["products"]),
                "firms": len(results["firms"]),
                "lots": len(results.get("lots", [])),
            },
        )

        return results

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
        """Insert an alias record. Returns the alias_id. Idempotent on conflict."""
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

    def _resolve_or_register(
        self,
        tenant_id: str,
        reference: str,
        entity_type: str,
        source_system: str,
        alias_type: str = "name",
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Try to resolve a reference to an existing entity. If no exact
        match is found, check for fuzzy matches and potentially queue
        for review, then register a new entity.

        Returns a dict with entity info and a 'resolution' key indicating
        what happened: 'existing', 'new', or 'new_with_review'.
        """
        # 1. Exact alias lookup
        # Check across common alias types for exact match
        search_types = [alias_type]
        if alias_type == "name":
            search_types.extend(["trade_name", "abbreviation"])
        # Also check if it looks like a GLN (13 digits)
        if reference.isdigit() and len(reference) == 13:
            search_types.append("gln")
        # Or a GTIN (14 digits)
        if reference.isdigit() and len(reference) == 14:
            search_types.append("gtin")

        for st in search_types:
            matches = self.find_entity_by_alias(tenant_id, st, reference)
            active_matches = [m for m in matches if m.get("is_active")]
            if active_matches:
                return {**active_matches[0], "resolution": "existing"}

        # 2. Fuzzy matching for potential duplicates
        fuzzy_matches = self.find_potential_matches(
            tenant_id, reference, entity_type=entity_type, threshold=AMBIGUOUS_THRESHOLD_LOW,
        )

        # 3. Register new entity
        new_entity = self.register_entity(
            tenant_id=tenant_id,
            entity_type=entity_type,
            canonical_name=reference,
            gln=reference if reference.isdigit() and len(reference) == 13 else None,
            gtin=reference if reference.isdigit() and len(reference) == 14 else None,
            confidence_score=0.8,
            created_by=created_by,
        )

        resolution = "new"

        # 4. Queue ambiguous matches for review
        for match in fuzzy_matches:
            if AMBIGUOUS_THRESHOLD_LOW <= match["confidence"] < AMBIGUOUS_THRESHOLD_HIGH:
                self.queue_for_review(
                    tenant_id=tenant_id,
                    entity_a_id=new_entity["entity_id"],
                    entity_b_id=match["entity_id"],
                    match_type="ambiguous",
                    match_confidence=match["confidence"],
                    matching_fields={
                        "search_reference": reference,
                        "matched_alias": match.get("matched_alias"),
                        "entity_type": entity_type,
                        "source_system": source_system,
                    },
                )
                resolution = "new_with_review"
            elif match["confidence"] >= AMBIGUOUS_THRESHOLD_HIGH:
                # High-confidence match — still register new but flag as likely
                self.queue_for_review(
                    tenant_id=tenant_id,
                    entity_a_id=new_entity["entity_id"],
                    entity_b_id=match["entity_id"],
                    match_type="likely",
                    match_confidence=match["confidence"],
                    matching_fields={
                        "search_reference": reference,
                        "matched_alias": match.get("matched_alias"),
                        "entity_type": entity_type,
                        "source_system": source_system,
                    },
                )
                resolution = "new_with_review"

        return {**new_entity, "resolution": resolution}

    # ------------------------------------------------------------------
    # Convenience: List pending reviews
    # ------------------------------------------------------------------

    def list_pending_reviews(
        self,
        tenant_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List pending identity review items for a tenant."""
        rows = self.session.execute(
            text("""
                SELECT irq.review_id, irq.entity_a_id, irq.entity_b_id,
                       irq.match_type, irq.match_confidence, irq.matching_fields,
                       irq.status, irq.created_at,
                       cea.canonical_name AS entity_a_name,
                       cea.entity_type AS entity_a_type,
                       ceb.canonical_name AS entity_b_name,
                       ceb.entity_type AS entity_b_type
                FROM fsma.identity_review_queue irq
                JOIN fsma.canonical_entities cea
                    ON cea.entity_id = irq.entity_a_id AND cea.tenant_id = irq.tenant_id
                JOIN fsma.canonical_entities ceb
                    ON ceb.entity_id = irq.entity_b_id AND ceb.tenant_id = irq.tenant_id
                WHERE irq.tenant_id = :tenant_id
                  AND irq.status IN ('pending', 'deferred')
                ORDER BY irq.match_confidence DESC, irq.created_at ASC
                LIMIT :limit OFFSET :offset
            """),
            {"tenant_id": tenant_id, "limit": limit, "offset": offset},
        ).fetchall()

        return [
            {
                "review_id": str(r[0]),
                "entity_a_id": str(r[1]),
                "entity_b_id": str(r[2]),
                "match_type": r[3],
                "match_confidence": float(r[4]) if r[4] is not None else None,
                "matching_fields": r[5] if isinstance(r[5], dict) else json.loads(r[5] or "{}"),
                "status": r[6],
                "created_at": r[7].isoformat() if r[7] else None,
                "entity_a_name": r[8],
                "entity_a_type": r[9],
                "entity_b_name": r[10],
                "entity_b_type": r[11],
            }
            for r in rows
        ]
