"""
Entity merge / split operations for identity resolution.

Mechanically split out of ``service.py`` — no logic changes. These
methods are mixed into :class:`shared.identity_resolution.service.
IdentityResolutionService`; they are not a standalone API.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import text

logger = logging.getLogger("identity-resolution")


class MergeMixin:
    """Merge/split write methods of ``IdentityResolutionService``."""

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
        Merge a single source entity into a target entity.

        Thin wrapper over :meth:`merge_entities_bulk` that preserves the
        original 1:1 API. Existing callers continue to work unchanged.
        For N-way merges (the resolver's "three duplicate 'Organic Apples'
        SKUs — merge all into the canonical one" case) use
        :meth:`merge_entities_bulk` directly — it writes a single audit
        row with all source IDs, which :meth:`split_entity` can then
        reverse atomically.
        """
        # #1230: verify the tenant before any side effects. The call is
        # redundant with the one in ``merge_entities_bulk``, but keeping
        # it here preserves the source-level static guard that every
        # public write method carries its own tenant check.
        self._verify_tenant_access(tenant_id)
        return self.merge_entities_bulk(
            tenant_id=tenant_id,
            source_entity_ids=[source_entity_id],
            target_entity_id=target_entity_id,
            reason=reason,
            performed_by=performed_by,
        )

    def merge_entities_bulk(
        self,
        tenant_id: str,
        source_entity_ids: List[str],
        target_entity_id: str,
        *,
        reason: Optional[str] = None,
        performed_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Merge N source entities into a single target entity atomically.

        - Every alias on any source is re-pointed to the target (duplicates
          silently dropped).
        - All source entities are deactivated (is_active = FALSE).
        - **Exactly one** ``entity_merge_history`` row is written with
          ``source_entity_ids = ARRAY[source_1, source_2, ...]::uuid[]``,
          which :meth:`split_entity` can reverse in one call.
        - Pending review-queue items touching any source are auto-resolved.

        Issue #1195: the underlying schema (V047) stored
        ``source_entity_ids`` as ``UUID[]``, but the public API forced
        one-at-a-time merges. A 3-way merge therefore wrote 3 history
        rows, 2 of which referenced entities that were already inactive
        by the time they ran — making ``split_entity`` unable to cleanly
        reverse the merge. This method fixes that by writing one history
        row per logical merge operation.

        Validation (all raise ``ValueError``):
        - ``source_entity_ids`` must be non-empty.
        - No duplicates within ``source_entity_ids``.
        - ``target_entity_id`` must not appear in ``source_entity_ids``.
        - Every source and the target must exist for this tenant.
        """
        # #1230: verify the tenant before any side effects
        self._verify_tenant_access(tenant_id)

        if not source_entity_ids:
            raise ValueError("source_entity_ids must not be empty")

        if len(set(source_entity_ids)) != len(source_entity_ids):
            raise ValueError("source_entity_ids must not contain duplicates")

        if target_entity_id in source_entity_ids:
            raise ValueError("Cannot merge an entity with itself")

        # Validate every participant before any side effects — partial
        # failures here would leave the DB in a half-merged state that
        # split_entity can't cleanly reverse.
        for source_entity_id in source_entity_ids:
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
        alias_snapshot = {source_entity_id: [{"alias_type": r[0], "alias_value": r[1]} for r in source_aliases_rows]}

        # Re-point aliases from source to target (skip duplicates)
        self.session.execute(
            text("""
                UPDATE fsma.entity_aliases
                SET entity_id = :target_entity_id
                WHERE tenant_id = :tenant_id
                  AND entity_id = ANY(CAST(:source_entity_ids AS uuid[]))
                  AND (alias_type, alias_value) NOT IN (
                      SELECT alias_type, alias_value
                      FROM fsma.entity_aliases
                      WHERE tenant_id = :tenant_id
                        AND entity_id = :target_entity_id
                  )
            """),
            {
                "tenant_id": tenant_id,
                "source_entity_ids": source_entity_ids,
                "target_entity_id": target_entity_id,
            },
        )

        # Remove any remaining aliases on the sources (duplicates that
        # couldn't move because the target already has that alias).
        self.session.execute(
            text("""
                DELETE FROM fsma.entity_aliases
                WHERE tenant_id = :tenant_id
                  AND entity_id = ANY(CAST(:source_entity_ids AS uuid[]))
            """),
            {"tenant_id": tenant_id, "source_entity_ids": source_entity_ids},
        )

        # Deactivate all source entities in one statement.
        self.session.execute(
            text("""
                UPDATE fsma.canonical_entities
                SET is_active = FALSE, updated_at = :now
                WHERE tenant_id = :tenant_id
                  AND entity_id = ANY(CAST(:source_entity_ids AS uuid[]))
            """),
            {
                "tenant_id": tenant_id,
                "source_entity_ids": source_entity_ids,
                "now": now,
            },
        )

        # Record merge history WITH alias snapshot (#1207)
        self.session.execute(
            text("""
                INSERT INTO fsma.entity_merge_history (
                    merge_id, tenant_id, action, source_entity_ids,
                    target_entity_id, reason, performed_by, performed_at,
                    is_reversed, alias_snapshot
                ) VALUES (
                    :merge_id, :tenant_id, 'merge',
                    CAST(:source_entity_ids AS uuid[]),
                    :target_entity_id, :reason, :performed_by, :now,
                    FALSE, CAST(:alias_snapshot AS jsonb)
                )
            """),
            {
                "merge_id": merge_id,
                "tenant_id": tenant_id,
                "source_entity_ids": source_entity_ids,
                "target_entity_id": target_entity_id,
                "reason": reason,
                "performed_by": performed_by,
                "now": now,
                "alias_snapshot": json.dumps(alias_snapshot),
            },
        )

        # Close any pending review-queue items touching any merged source.
        self.session.execute(
            text("""
                UPDATE fsma.identity_review_queue
                SET status = 'confirmed_match',
                    resolved_by = :performed_by,
                    resolved_at = :now,
                    resolution_notes = 'Auto-resolved by merge operation'
                WHERE tenant_id = :tenant_id
                  AND status = 'pending'
                  AND (
                      entity_a_id = ANY(CAST(:source_entity_ids AS uuid[]))
                      OR entity_b_id = ANY(CAST(:source_entity_ids AS uuid[]))
                  )
            """),
            {
                "tenant_id": tenant_id,
                "source_entity_ids": source_entity_ids,
                "performed_by": performed_by,
                "now": now,
            },
        )

        logger.info(
            "entities_merged",
            extra={
                "merge_id": merge_id,
                "source_entity_ids": source_entity_ids,
                "source_count": len(source_entity_ids),
                "target_entity_id": target_entity_id,
                "tenant_id": tenant_id,
            },
        )

        return {
            "merge_id": merge_id,
            "action": "merge",
            "source_entity_ids": list(source_entity_ids),
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
