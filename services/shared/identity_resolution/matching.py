"""
Exact and fuzzy entity lookup for identity resolution.

Mechanically split out of ``service.py`` — no logic changes. These
methods are mixed into :class:`shared.identity_resolution.service.
IdentityResolutionService`; they are not a standalone API.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

import structlog
from shared.identity_resolution.constants import VALID_ENTITY_TYPES
from shared.identity_resolution.normalization import _normalize_identifier
from sqlalchemy import text

logger = structlog.get_logger("identity-resolution")


class MatchingMixin:
    """Read/lookup methods of ``IdentityResolutionService``."""

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
        # #1212: normalize structured identifiers before lookup so that
        # whitespace variants and URN-prefix case differences resolve to the
        # same stored record.
        lookup_value = _normalize_identifier(alias_type, alias_value)

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
                -- Stable order: oldest entity wins over newer aliases
                -- #1234: confidence_score DESC (higher quality first), then created_at ASC
                -- (oldest canonical wins on ties), entity_id ASC as UUID tiebreak.
                ORDER BY ce.confidence_score DESC, ce.created_at ASC, ce.entity_id ASC
            """),
            {
                "tenant_id": tenant_id,
                "alias_type": alias_type,
                "alias_value": lookup_value,
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
        # planner can optimise it away when the filter is unused. The CAST
        # is required: psycopg 3 binds server-side, and Postgres cannot type
        # a parameter whose first use is ``IS NULL`` (same form as
        # canonical_persistence.writer's nullable date filters).
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
                # SAVEPOINT so a failed trgm probe (e.g. pg_trgm missing,
                # or installed in a schema off the search_path) rolls back
                # to here instead of aborting the caller's transaction —
                # otherwise the fallback query below dies with
                # InFailedSqlTransaction and takes the caller's
                # uncommitted work with it.
                with self.session.begin_nested():
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
                              AND (CAST(:entity_type AS text) IS NULL OR ce.entity_type = CAST(:entity_type AS text))
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
                      AND (CAST(:entity_type AS text) IS NULL OR ce.entity_type = CAST(:entity_type AS text))
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
            scored.append(
                {
                    "entity_id": entity_id,
                    "entity_type": r[1],
                    "canonical_name": r[2],
                    "gln": r[3],
                    "gtin": r[4],
                    "verification_status": r[5],
                    "entity_confidence": float(r[6]) if r[6] is not None else None,
                    "confidence": round(ratio, 4),
                    "matched_alias": alias_value,
                }
            )

        scored.sort(key=lambda x: x["confidence"], reverse=True)
        return scored[:limit]

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
