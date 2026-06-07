"""
Auto-registration / resolve-or-register flow for identity resolution.

Mechanically split out of ``service.py`` — no logic changes. These
methods are mixed into :class:`shared.identity_resolution.service.
IdentityResolutionService`; they are not a standalone API.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from shared.identity_resolution.constants import (
    AMBIGUOUS_THRESHOLD_LOW,
    AMBIGUOUS_THRESHOLD_HIGH,
)
# #1233: PII masking helpers for log emission. Raw alias_value /
# canonical_name must never reach the log sinks.
from shared.pii import mask_alias_value

logger = logging.getLogger("identity-resolution")


class ResolverMixin:
    """Event-driven resolution methods of ``IdentityResolutionService``."""

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
