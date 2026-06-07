"""
Human review queue management for identity resolution.

Mechanically split out of ``service.py`` — no logic changes. These
methods are mixed into :class:`shared.identity_resolution.service.
IdentityResolutionService`; they are not a standalone API.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy import text

from shared.identity_resolution.constants import VALID_REVIEW_STATUSES

logger = logging.getLogger("identity-resolution")


class ReviewMixin:
    """Review-queue methods of ``IdentityResolutionService``."""

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

    # Ranking for deterministic merge target (#1193). Higher is better.
    # queue_for_review normalizes entity_a_id < entity_b_id lexicographically
    # for idempotency, which meant resolve_review silently picked the lex-
    # lower UUID as "source" (the deactivated side) regardless of which
    # entity was authoritative. The reviewer can now opt to specify
    # ``target_entity_id`` explicitly, or we fall back to a deterministic
    # rank: verified > pending_review > unverified, then higher
    # confidence_score, then earlier created_at, then lex-lower entity_id
    # as a last-resort tiebreaker so the outcome is fully reproducible.
    _VERIFICATION_RANK = {
        "verified": 2,
        "pending_review": 1,
        "unverified": 0,
    }

    def _pick_merge_target(
        self,
        tenant_id: str,
        entity_a_id: str,
        entity_b_id: str,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """Return (source_entity_id, target_entity_id, rationale) for a
        merge pair.  The target is the entity with the higher rank.

        Rationale is logged so auditors can reconstruct why a given
        entity was deactivated rather than the other.
        """
        rows = self.session.execute(
            text("""
                SELECT entity_id, verification_status, confidence_score,
                       created_at
                FROM fsma.canonical_entities
                WHERE tenant_id = :tenant_id
                  AND entity_id IN (:a_id, :b_id)
            """),
            {"tenant_id": tenant_id, "a_id": entity_a_id, "b_id": entity_b_id},
        ).fetchall()

        by_id = {str(r[0]): r for r in rows}
        a_row = by_id.get(entity_a_id)
        b_row = by_id.get(entity_b_id)

        def _rank(row):
            if row is None:
                # Missing entity sorts last so the surviving one wins.
                return (-1, -1.0, datetime.max.replace(tzinfo=timezone.utc))
            v_rank = self._VERIFICATION_RANK.get(row[1], 0)
            conf = float(row[2]) if row[2] is not None else 0.0
            created = row[3] or datetime.max.replace(tzinfo=timezone.utc)
            # Higher rank + higher confidence + earlier created_at wins,
            # so we negate created_at's sort direction by using a wrapper.
            return (v_rank, conf, created)

        a_key = _rank(a_row)
        b_key = _rank(b_row)

        # Compare: higher verification, higher confidence, EARLIER created_at.
        # Tuple sort is natural on verification + confidence (higher wins),
        # but created_at should be earlier-wins — so flip the comparison
        # piece-by-piece.
        if a_key[0] != b_key[0]:
            a_wins = a_key[0] > b_key[0]
            tiebreaker = "verification_status"
        elif a_key[1] != b_key[1]:
            a_wins = a_key[1] > b_key[1]
            tiebreaker = "confidence_score"
        elif a_key[2] != b_key[2]:
            # Earlier created_at wins — more established record.
            a_wins = a_key[2] < b_key[2]
            tiebreaker = "created_at"
        else:
            # Fully tied — fall back to lex order so the outcome is
            # reproducible rather than depending on row insertion order.
            a_wins = entity_a_id < entity_b_id
            tiebreaker = "entity_id_lex"

        if a_wins:
            target, source = entity_a_id, entity_b_id
        else:
            target, source = entity_b_id, entity_a_id

        rationale = {
            "tiebreaker": tiebreaker,
            "target_entity_id": target,
            "source_entity_id": source,
            "a_verification_status": a_row[1] if a_row else None,
            "b_verification_status": b_row[1] if b_row else None,
            "a_confidence_score": float(a_row[2]) if a_row and a_row[2] is not None else None,
            "b_confidence_score": float(b_row[2]) if b_row and b_row[2] is not None else None,
        }
        return source, target, rationale

    def resolve_review(
        self,
        tenant_id: str,
        review_id: str,
        resolution: str,
        *,
        resolved_by: Optional[str] = None,
        resolution_notes: Optional[str] = None,
        auto_merge: bool = True,
        target_entity_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Resolve a pending identity review item.

        resolution must be one of:
            - confirmed_match: the two entities are the same; optionally
              auto-merge them (if auto_merge=True).
            - confirmed_distinct: the two entities are different; no action.
            - deferred: postpone the decision.

        ``target_entity_id`` (#1193): if provided, must equal the review's
        ``entity_a_id`` or ``entity_b_id`` and becomes the merge target
        (the entity that SURVIVES; the other is deactivated). When not
        provided, the target is chosen deterministically from the pair
        based on ``verification_status`` → ``confidence_score`` →
        ``created_at`` (earliest) — NOT on the lexicographic ordering
        that ``queue_for_review`` uses for its idempotency key.

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

        entity_a_id = str(review[1])
        entity_b_id = str(review[2])

        # Validate caller-supplied target up front — reject before any
        # side effect if it's not one of the two entities on this review.
        if (
            target_entity_id is not None
            and target_entity_id not in (entity_a_id, entity_b_id)
        ):
            raise ValueError(
                f"target_entity_id '{target_entity_id}' is not part of review "
                f"'{review_id}' (expected one of '{entity_a_id}' or "
                f"'{entity_b_id}')"
            )

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
            "entity_a_id": entity_a_id,
            "entity_b_id": entity_b_id,
            "resolution": resolution,
            "resolved_by": resolved_by,
            "resolved_at": now.isoformat(),
        }

        # Auto-merge if confirmed match
        if resolution == "confirmed_match" and auto_merge:
            # #1193: pick the merge direction explicitly rather than
            # silently deactivating the lex-lower entity.
            if target_entity_id is not None:
                target = target_entity_id
                source = entity_b_id if target == entity_a_id else entity_a_id
                rationale: Dict[str, Any] = {
                    "tiebreaker": "explicit_override",
                    "target_entity_id": target,
                    "source_entity_id": source,
                }
            else:
                source, target, rationale = self._pick_merge_target(
                    tenant_id, entity_a_id, entity_b_id,
                )
            logger.info(
                "review_merge_target_selected",
                extra={
                    "review_id": review_id,
                    "tenant_id": tenant_id,
                    **rationale,
                },
            )
            merge_result = self.merge_entities(
                tenant_id=tenant_id,
                source_entity_id=source,
                target_entity_id=target,
                reason=(
                    f"Confirmed match via review {review_id} "
                    f"(target selected by {rationale['tiebreaker']})"
                ),
                performed_by=resolved_by,
            )
            result["merge"] = merge_result
            result["merge_target_rationale"] = rationale

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
