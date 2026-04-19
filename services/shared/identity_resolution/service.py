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
# #1233: PII masking helpers for log emission. Raw alias_value /
# canonical_name must never reach the log sinks — log retention is
# typically longer than DB retention and sinks are accessible to a
# wider personnel surface (SRE, observability vendors).
from shared.pii import mask_alias_value, mask_name

logger = logging.getLogger("identity-resolution")


# ---------------------------------------------------------------------------
# Identity Resolution Service
# ---------------------------------------------------------------------------

class IdentityResolutionService:
    """
    Cross-record identity resolution for FSMA supply-chain entities.

    All methods are tenant-scoped. The caller must supply ``tenant_id``
    explicitly; this service never infers it.

    #1230 tenant lock: when constructed with ``principal_tenant_id``,
    every write method verifies that the caller-supplied ``tenant_id``
    matches the principal's tenant. This blocks cross-tenant writes
    even if a router bug — e.g. the pattern seen in #1106 where an
    ``X-Tenant-ID`` header is forwarded without cross-check — lets
    a mismatched tenant_id reach the service. Callers that legitimately
    need cross-tenant access (admin tooling, platform jobs) construct
    the service without ``principal_tenant_id`` OR set
    ``allow_cross_tenant=True`` on construction.
    """

    def __init__(
        self,
        session: Session,
        *,
        principal_tenant_id: Optional[str] = None,
        allow_cross_tenant: bool = False,
    ):
        self.session = session
        # Keyword-only to prevent positional-arg drift from accidentally
        # disabling the lock in a new call site.
        self._principal_tenant_id = principal_tenant_id
        self._allow_cross_tenant = allow_cross_tenant

    # ------------------------------------------------------------------
    # Tenant-access guard (#1230)
    # ------------------------------------------------------------------

    def _verify_tenant_access(self, tenant_id: str) -> None:
        """Raise PermissionError if the caller-supplied ``tenant_id``
        doesn't match the principal the service was constructed with.

        No-op when:
        - ``principal_tenant_id`` is None (backwards-compatible path
          for background jobs / ingestion consumers that run with a
          service account not bound to a tenant).
        - ``allow_cross_tenant=True`` (admin tooling explicitly
          opting out of the lock).

        The service cannot enforce the "is this user entitled to this
        tenant" question by itself — that's the router's job. But it
        CAN enforce that whatever tenant the router handed in matches
        the principal's tenant. That's defense-in-depth against
        router-level bugs like #1106.
        """
        if self._allow_cross_tenant:
            return
        if self._principal_tenant_id is None:
            return
        if not tenant_id:
            raise PermissionError(
                "identity_resolution: tenant_id is required"
            )
        if tenant_id != self._principal_tenant_id:
            logger.warning(
                "identity_tenant_mismatch principal=%s requested=%s",
                self._principal_tenant_id, tenant_id,
            )
            raise PermissionError(
                "identity_resolution: tenant_id does not match the "
                "authenticated principal's tenant. Cross-tenant writes "
                "require an explicit platform-admin grant; see #1230."
            )

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
        case_sensitive: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Confidence-scored fuzzy matching by name similarity.

        Uses SequenceMatcher (Ratcliff/Obershelp) from difflib on all
        name-type aliases for the tenant. Results are sorted by
        descending confidence.

        Fix #1177: fuzzy matching defaults to case-insensitive because
        names are frequently formatted inconsistently ("Acme Foods" vs
        "ACME FOODS"). But case-insensitive matching MUST NEVER be the
        authoritative path for lot codes or other identifiers — those
        must use :meth:`find_entity_by_alias` (exact, case-sensitive).
        For callers that do want strict comparison (e.g., an alternate
        lot-code suggestion path), pass ``case_sensitive=True``.
        """
        # #1191: keep the SQL string 100% static — no f-string
        # interpolation, even for whitelisted values. A future edit that
        # inlines an unvetted string would turn a static query into a
        # SQL-injection vector. The type filter is expressed as a
        # nullable parameter (`:entity_type IS NULL OR ...`) so the
        # planner can optimise it away when the filter is unused.
        if entity_type is not None and entity_type not in VALID_ENTITY_TYPES:
            raise ValueError(f"Invalid entity_type '{entity_type}'")

        params: Dict[str, Any] = {
            "tenant_id": tenant_id,
            "entity_type": entity_type,  # None is bound explicitly to NULL
        }

        # Pre-normalize the search term — we need it for both the
        # Python re-score and the SQL-side trigram filter (lowered).
        if case_sensitive:
            search_norm = search_name
        else:
            search_norm = search_name.lower().strip()

        # #1208 — SQL-side pg_trgm pre-filter.
        #
        # Before: this method pulled every tenant alias into Python
        # (``O(N)`` wire + ``O(N)`` SequenceMatcher) — multi-second at
        # 100K aliases and directly on the ingestion hot path.
        #
        # After: a ``similarity(lower(alias_value), :q) >= :sim_floor``
        # predicate (backed by the GIN/pg_trgm index added in v070
        # migration) shrinks the candidate set to ``candidate_pool``
        # rows before Python re-scores them with the authoritative
        # Ratcliff/Obershelp ratio that callers depend on.
        #
        # Fallback: when pg_trgm isn't present (stripped-down test PG,
        # or the migration hasn't run), the SQL raises ``UndefinedFunction``
        # which we catch and re-issue the pre-#1208 full-scan query.
        # Correctness stays identical — only the perf win is lost.
        #
        # The trigram path only runs when we have a normalized search
        # term and we're not in case-sensitive mode; case_sensitive
        # paths are non-fuzzy comparisons typically used for
        # authoritative lookups where a full-scan match matters more
        # than speed.
        candidate_pool = max(limit * 20, 100)
        rows = None
        if not case_sensitive and search_norm:
            try:
                rows = self.session.execute(
                    text(
                        """
                        SELECT ce.entity_id, ce.entity_type, ce.canonical_name,
                               ce.gln, ce.gtin, ce.verification_status,
                               ce.confidence_score, ea.alias_value
                        FROM fsma.entity_aliases ea
                        JOIN fsma.canonical_entities ce
                            ON ce.entity_id = ea.entity_id
                           AND ce.tenant_id = ea.tenant_id
                        WHERE ea.tenant_id = :tenant_id
                          AND ea.alias_type IN ('name', 'trade_name', 'abbreviation')
                          AND ce.is_active = TRUE
                          AND (:entity_type IS NULL OR ce.entity_type = :entity_type)
                          AND similarity(lower(ea.alias_value), :q) >= :sim_floor
                        ORDER BY similarity(lower(ea.alias_value), :q) DESC
                        LIMIT :cand_limit
                        """
                    ),
                    {
                        **params,
                        "q": search_norm,
                        # Lenient floor — the authoritative cutoff is
                        # the Python-side ``threshold``. Use ``0.2`` as
                        # the absolute minimum (roughly "shares at
                        # least one meaningful trigram") and raise it
                        # toward the caller's threshold up to 0.8 so
                        # the caller's stricter threshold translates
                        # into a smaller candidate pool.
                        "sim_floor": max(0.2, min(threshold * 0.7, 0.8)),
                        "cand_limit": candidate_pool,
                    },
                ).fetchall()
            except Exception as exc:
                logger.debug(
                    "find_potential_matches_trgm_unavailable",
                    exc_info=True,
                    error=str(exc)[:200],
                )
                rows = None

        if rows is None:
            # Fallback path — pre-#1208 behavior, preserved for
            # environments without pg_trgm and for ``case_sensitive=True``
            # callers.
            rows = self.session.execute(
                text(
                    """
                    SELECT ce.entity_id, ce.entity_type, ce.canonical_name,
                           ce.gln, ce.gtin, ce.verification_status,
                           ce.confidence_score, ea.alias_value
                    FROM fsma.entity_aliases ea
                    JOIN fsma.canonical_entities ce
                        ON ce.entity_id = ea.entity_id AND ce.tenant_id = ea.tenant_id
                    WHERE ea.tenant_id = :tenant_id
                      AND ea.alias_type IN ('name', 'trade_name', 'abbreviation')
                      AND ce.is_active = TRUE
                      AND (:entity_type IS NULL OR ce.entity_type = :entity_type)
                    """
                ),
                params,
            ).fetchall()

        # ``search_norm`` is already computed above (pre-#1208 it was
        # computed here). The raw alias_value is still returned verbatim
        # so callers never see a mutated identifier.

        scored: List[Dict[str, Any]] = []
        seen_entities: set = set()

        for r in rows:
            entity_id = str(r[0])
            alias_value = r[7] or ""
            if case_sensitive:
                comparand = alias_value
            else:
                comparand = alias_value.lower().strip()
            ratio = SequenceMatcher(None, search_norm, comparand).ratio()

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
        # #1230: verify the tenant before any side effects
        self._verify_tenant_access(tenant_id)

        if source_entity_id == target_entity_id:
            raise ValueError("Cannot merge an entity with itself")

        self._require_entity(tenant_id, source_entity_id)
        self._require_entity(tenant_id, target_entity_id)

        merge_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # #1207 — snapshot the source entity's aliases BEFORE re-pointing
        # them to the target. Without this, split_entity can only restore
        # the canonical-name alias by string match; GLN/GTIN/FDA registration
        # aliases are irrecoverable, giving a false sense of rollback.
        #
        # Shape: {"<source_entity_uuid>": [
        #     {"alias_type": "gln", "alias_value": "..."},
        #     {"alias_type": "gtin", "alias_value": "..."},
        #     ...
        # ]}
        source_aliases_rows = self.session.execute(
            text("""
                SELECT alias_type, alias_value
                FROM fsma.entity_aliases
                WHERE tenant_id = :tenant_id
                  AND entity_id = :source_entity_id
                ORDER BY alias_type, alias_value
            """),
            {"tenant_id": tenant_id, "source_entity_id": source_entity_id},
        ).fetchall()
        alias_snapshot = {
            source_entity_id: [
                {"alias_type": r[0], "alias_value": r[1]}
                for r in source_aliases_rows
            ]
        }

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

        # Record merge history WITH alias snapshot (#1207)
        self.session.execute(
            text("""
                INSERT INTO fsma.entity_merge_history (
                    merge_id, tenant_id, action, source_entity_ids,
                    target_entity_id, reason, performed_by, performed_at,
                    is_reversed, alias_snapshot
                ) VALUES (
                    :merge_id, :tenant_id, 'merge', ARRAY[:source_entity_id]::uuid[],
                    :target_entity_id, :reason, :performed_by, :now,
                    FALSE, CAST(:alias_snapshot AS jsonb)
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
                "alias_snapshot": json.dumps(alias_snapshot),
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
        - Restores aliases from ``entity_merge_history.alias_snapshot``
          (#1207) — every alias that was on the source at merge time
          is moved back to the source. Aliases added to the target
          AFTER the merge stay with the target.
        - Records the reversal in merge_history.

        #1207 — pre-v069 merges lack an ``alias_snapshot``. Those
        merges cannot be safely reversed: the canonical-name alias
        alone came back, and every GLN/GTIN/FDA identifier silently
        stayed on the target. Rather than perpetuate the lossy
        behavior, this method now RAISES when the snapshot is NULL.
        Operators can either manually reconstruct aliases and flip
        ``is_reversed`` themselves, or accept that pre-v069 merges
        are non-reversible through this API.
        """
        # #1230: verify the tenant before any side effects
        self._verify_tenant_access(tenant_id)

        merge_row = self.session.execute(
            text("""
                SELECT merge_id, source_entity_ids, target_entity_id,
                       action, is_reversed, alias_snapshot
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
        alias_snapshot_raw = merge_row[5]  # JSONB -> dict or None

        # #1207 — refuse to reverse a pre-v069 merge. Silent alias loss
        # is a false-audit surface we no longer tolerate.
        if alias_snapshot_raw is None:
            raise ValueError(
                f"Merge '{merge_id}' was recorded before v069 and has no "
                "alias_snapshot. Split is refused to prevent silent loss "
                "of GLN/GTIN/FDA aliases that would otherwise stay on the "
                "target entity. Reconstruct aliases manually if reversal "
                "is required (#1207)."
            )

        # JSONB may arrive as a dict (SQLAlchemy + psycopg2) or as a
        # string (SQLite or some driver configs). Normalize.
        if isinstance(alias_snapshot_raw, str):
            alias_snapshot = json.loads(alias_snapshot_raw)
        else:
            alias_snapshot = alias_snapshot_raw

        now = datetime.now(timezone.utc)

        # Re-activate source entities and replay each one's alias snapshot.
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

            # Move the snapshot aliases back from target to source. Each
            # (alias_type, alias_value) is a unique key within a tenant,
            # so UPDATE suffices — there will be at most one row to flip.
            snapshot_aliases = alias_snapshot.get(src_id_str, [])
            for alias in snapshot_aliases:
                alias_type = alias.get("alias_type")
                alias_value = alias.get("alias_value")
                if not alias_type or not alias_value:
                    continue
                self.session.execute(
                    text("""
                        UPDATE fsma.entity_aliases
                        SET entity_id = :source_entity_id
                        WHERE tenant_id = :tenant_id
                          AND entity_id = :target_entity_id
                          AND alias_type = :alias_type
                          AND alias_value = :alias_value
                    """),
                    {
                        "tenant_id": tenant_id,
                        "source_entity_id": src_id_str,
                        "target_entity_id": target_entity_id,
                        "alias_type": alias_type,
                        "alias_value": alias_value,
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

        Idempotency (#1211) is STATUS-AWARE: the check only treats rows
        in ``('pending', 'deferred')`` — the active review states — as
        duplicates. A prior ``confirmed_distinct`` or
        ``confirmed_match`` resolution does NOT block a fresh review
        when new evidence comes in; a new row is inserted instead, with
        ``previous_review_id`` pointing at the most-recent closed row
        so the reopen cycle is auditable.

        The schema backs this semantic: v068 replaces the full-table
        ``UNIQUE(entity_a_id, entity_b_id)`` with a partial unique
        index scoped to ``status IN ('pending', 'deferred')``.

        Before #1211 the existing-row check returned any existing row,
        including closed ``confirmed_distinct`` rows, which silently
        no-op'd the re-queue and denied operators the chance to
        re-examine stale distinct verdicts.
        """
        # #1230: verify the tenant before any side effects
        self._verify_tenant_access(tenant_id)

        valid_match_types = {"exact", "likely", "ambiguous", "unresolved"}
        if match_type not in valid_match_types:
            raise ValueError(f"Invalid match_type '{match_type}'. Must be one of {sorted(valid_match_types)}")

        # Normalize ordering so (A,B) == (B,A).
        a_id, b_id = sorted([entity_a_id, entity_b_id])

        # #1211 — status-aware idempotency. An OPEN review (pending or
        # deferred) short-circuits. A CLOSED review (confirmed_match /
        # confirmed_distinct) does NOT; the closed row's id is captured
        # for previous_review_id linkage below.
        open_existing = self.session.execute(
            text("""
                SELECT review_id, status, match_confidence
                FROM fsma.identity_review_queue
                WHERE tenant_id = :tenant_id
                  AND entity_a_id = :a_id
                  AND entity_b_id = :b_id
                  AND status IN ('pending', 'deferred')
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {"tenant_id": tenant_id, "a_id": a_id, "b_id": b_id},
        ).fetchone()

        if open_existing:
            return {
                "review_id": str(open_existing[0]),
                "status": open_existing[1],
                "match_confidence": (
                    float(open_existing[2]) if open_existing[2] is not None else None
                ),
                "idempotent": True,
            }

        # No open row. Look for the most-recent CLOSED row so we can
        # thread previous_review_id and preserve the audit trail
        # across a reopen cycle. ORDER BY resolved_at (NULLS LAST so a
        # row that was closed without resolved_at still lands in a
        # deterministic position).
        prior_closed = self.session.execute(
            text("""
                SELECT review_id
                FROM fsma.identity_review_queue
                WHERE tenant_id = :tenant_id
                  AND entity_a_id = :a_id
                  AND entity_b_id = :b_id
                  AND status IN ('confirmed_match', 'confirmed_distinct')
                ORDER BY resolved_at DESC NULLS LAST, created_at DESC
                LIMIT 1
            """),
            {"tenant_id": tenant_id, "a_id": a_id, "b_id": b_id},
        ).fetchone()
        previous_review_id = str(prior_closed[0]) if prior_closed else None

        review_id = str(uuid4())
        now = datetime.now(timezone.utc)

        self.session.execute(
            text("""
                INSERT INTO fsma.identity_review_queue (
                    review_id, tenant_id, entity_a_id, entity_b_id,
                    match_type, match_confidence, matching_fields,
                    status, created_at, previous_review_id
                ) VALUES (
                    :review_id, :tenant_id, :a_id, :b_id,
                    :match_type, :match_confidence, :matching_fields,
                    'pending', :now, :previous_review_id
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
                "previous_review_id": previous_review_id,
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
                # Present when this is a reopen after a prior closed
                # verdict. None on a first-time queueing.
                "previous_review_id": previous_review_id,
                "is_reopen": previous_review_id is not None,
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
            # Surface reopen semantics to callers so dashboards and
            # alerting can flag "this pair has been reviewed before".
            "previous_review_id": previous_review_id,
            "is_reopen": previous_review_id is not None,
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
        # #1230: verify the tenant before any side effects
        self._verify_tenant_access(tenant_id)

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
        # #1230: verify the tenant before any side effects. This is the
        # hot path — every ingested canonical event goes through here —
        # so the guard has to stay O(1).
        self._verify_tenant_access(tenant_id)

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

    def _acquire_resolve_lock(
        self,
        tenant_id: str,
        alias_type: str,
        alias_value: str,
    ) -> None:
        """
        Acquire a PostgreSQL advisory lock scoped to the current
        transaction, keyed deterministically on (tenant_id, alias_type,
        alias_value). Prevents the TOCTOU race between "lookup existing"
        and "insert new" in :meth:`_resolve_or_register` (#1190).

        pg_advisory_xact_lock(bigint) takes a signed 64-bit key; we hash
        the triple with blake2b and fold to 63 bits so it always fits a
        postgres BIGINT.

        On non-PostgreSQL backends (sqlite in tests) the call is a
        best-effort no-op — correctness still depends on the UNIQUE
        constraint added in migration v059 (#1179), which is the
        authoritative dedup barrier.
        """
        import hashlib
        payload = f"{tenant_id}|{alias_type}|{alias_value}".encode("utf-8")
        # Fold to signed bigint range (Postgres bigint = int8, 63 bits
        # usable once we account for sign).
        digest = hashlib.blake2b(payload, digest_size=8).digest()
        lock_key = int.from_bytes(digest, byteorder="big", signed=False) & (
            (1 << 63) - 1
        )
        try:
            self.session.execute(
                text("SELECT pg_advisory_xact_lock(:key)"),
                {"key": lock_key},
            )
        except Exception as exc:  # pragma: no cover — non-Postgres or no tx
            # Advisory locks only work against Postgres. If it fails,
            # the UNIQUE constraint from migration v059 still prevents
            # duplicate aliases; we log once and continue.
            logger.debug(
                "advisory_lock_unavailable",
                extra={
                    "tenant_id": tenant_id,
                    "alias_type": alias_type,
                    "error": str(exc),
                },
            )

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

        Fix #1190: the critical section — "check existing then create" —
        is now serialized per (tenant_id, alias_type, alias_value) using
        a PostgreSQL advisory lock, and the _insert_alias call itself
        relies on the UNIQUE(tenant_id, alias_type, alias_value) constraint
        added in migration v059 (#1179) to provide ON CONFLICT DO NOTHING
        semantics. Together these make duplicate entity creation impossible
        across concurrent transactions.
        """
        # 0. Acquire advisory lock keyed on the (tenant, alias_type,
        # alias_value) triple. pg_advisory_xact_lock takes a signed int8;
        # we hash the triple deterministically. The lock is released at
        # transaction end. On non-PostgreSQL backends the call degrades
        # to a no-op — the UNIQUE constraint from v059 remains the
        # authoritative dedup barrier.
        self._acquire_resolve_lock(tenant_id, alias_type, reference)

        # 1. Exact alias lookup — ALWAYS case-sensitive verbatim match.
        # Fix #1177: Identifiers (lot codes, GLNs, GTINs, TLCs) must never be
        # normalized or case-folded on the authoritative path.
        # find_entity_by_alias compares alias_value verbatim in SQL.
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

        # 2. Fuzzy matching for potential duplicates — ONLY for name-type
        # references. For identifier aliases (tlc, tlc_prefix, gln, gtin,
        # fda_registration, internal_code, duns), fuzzy name matching would
        # silently collide unrelated lot codes (issue #1177). Identifiers
        # are resolved strictly by exact alias match above; if no exact
        # match, we register a new entity with no review queue.
        _NAME_LIKE_ALIAS_TYPES = {"name", "trade_name", "abbreviation"}
        if alias_type in _NAME_LIKE_ALIAS_TYPES:
            fuzzy_matches = self.find_potential_matches(
                tenant_id, reference, entity_type=entity_type,
                threshold=AMBIGUOUS_THRESHOLD_LOW,
            )
        else:
            fuzzy_matches = []

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

        # Fix #1175/#1177: when the caller passed a non-'name' alias_type
        # (e.g. 'tlc', 'gln'), register_entity only seeded the 'name' alias.
        # We must also persist the alias under its caller-supplied alias_type
        # so subsequent exact lookups succeed.
        if alias_type != "name":
            try:
                self._insert_alias(
                    tenant_id=tenant_id,
                    entity_id=new_entity["entity_id"],
                    alias_type=alias_type,
                    alias_value=reference,
                    source_system=source_system,
                    confidence=1.0,
                    created_by=created_by,
                )
            except (ValueError, RuntimeError) as exc:
                # #1233: reference is a regulated identifier or name;
                # mask before emission.
                logger.warning(
                    "resolve_or_register_alias_insert_failed",
                    extra={
                        "entity_id": new_entity["entity_id"],
                        "alias_type": alias_type,
                        "alias_value_masked": mask_alias_value(alias_type, reference),
                        "error": str(exc),
                    },
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
