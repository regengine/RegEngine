"""Hash-chain and Merkle verification for the CTE persistence layer.

Mechanically extracted from ``core.py`` (file split — no logic changes).
``core.CTEPersistence`` composes this mixin. Names that used to be module
globals of ``core.py`` (``logger``, ``compute_chain_hash``, the model
dataclasses) are resolved late through the ``core`` module (method-local
``from . import core as _core``) so existing monkeypatch /
``patch("...cte_persistence.core.X")`` targets keep affecting this code
exactly as before the split.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import text

if TYPE_CHECKING:  # pragma: no cover — annotation-only imports
    from .models import ChainVerification, MerkleVerification


class ChainVerificationMixin:
    """Chain / Merkle verification — mixed into :class:`core.CTEPersistence`."""

    # ------------------------------------------------------------------
    # Chain Verification
    # ------------------------------------------------------------------

    def verify_chain(self, tenant_id: str) -> ChainVerification:
        """
        Verify the integrity of a tenant's entire hash chain.

        Walks the chain from genesis to head, recomputing each
        ``chain_hash`` and comparing to the stored value. Any mismatch
        means tampering.

        #1314: this method formerly only read ``fsma.hash_chain``, so an
        orphan chain row (``cte_event_id`` referencing a row that no
        longer exists or that was never inserted in the first place —
        see #1307) would pass verification silently, and a CTE event
        whose chain insert failed would likewise be undetected. The
        verification now:
          * LEFT JOINs to ``fsma.cte_events`` and flags chain rows
            whose ``cte_event_id`` has no matching event.
          * Counts non-rejected events and compares to ``count(chain)``,
            surfacing ``missing_chain_rows`` — events that should have
            a chain entry but don't.
        Both conditions make ``valid = False`` and append a structured
        entry to ``orphan_chain_rows`` / ``missing_chain_rows`` plus a
        human-readable line to ``errors``.
        """
        from . import core as _core

        # LEFT JOIN chain → cte_events: a NULL event_id means the chain
        # row is orphaned. Chain rows are ordered by sequence_num so the
        # per-row checks below still work left-to-right.
        rows = self.session.execute(
            text("""
                SELECT hc.sequence_num, hc.event_hash,
                       hc.previous_chain_hash, hc.chain_hash,
                       hc.cte_event_id, ce.id AS matched_event_id
                FROM fsma.hash_chain hc
                LEFT JOIN fsma.cte_events ce
                    ON ce.id = hc.cte_event_id
                   AND ce.tenant_id = hc.tenant_id
                WHERE hc.tenant_id = :tid
                ORDER BY hc.sequence_num ASC
            """),
            {"tid": tenant_id},
        ).fetchall()

        # Count non-rejected CTE events for the missing-chain cross-check.
        # A CTE event with validation_status='rejected' is intentionally
        # not chained (writes are short-circuited before hash_chain
        # insert); don't flag those as missing.
        event_count_row = self.session.execute(
            text("""
                SELECT COUNT(*)
                FROM fsma.cte_events
                WHERE tenant_id = :tid
                  AND validation_status != 'rejected'
            """),
            {"tid": tenant_id},
        ).fetchone()
        cte_events_count = int(event_count_row[0]) if event_count_row else 0

        checked_at = datetime.now(timezone.utc).isoformat()

        if not rows:
            # Empty chain is only valid if the event table is also empty
            # (or all events are rejected). Otherwise every event is
            # orphaned — the #1314 regression surfaces here.
            missing_ids = self._missing_chain_event_ids(tenant_id)
            if cte_events_count == 0 and not missing_ids:
                return _core.ChainVerification(
                    valid=True,
                    chain_length=0,
                    errors=[],
                    checked_at=checked_at,
                    orphan_chain_rows=[],
                    missing_chain_rows=[],
                    cte_events_count=0,
                )
            errors = [
                f"Empty chain but {cte_events_count} non-rejected events exist ({len(missing_ids)} missing chain rows)"
            ]
            return _core.ChainVerification(
                valid=False,
                chain_length=0,
                errors=errors,
                checked_at=checked_at,
                orphan_chain_rows=[],
                missing_chain_rows=missing_ids,
                cte_events_count=cte_events_count,
            )

        errors: List[str] = []
        orphan_chain_rows: List[int] = []

        for i, row in enumerate(rows):
            seq, event_hash, stored_prev, stored_chain = row[0], row[1], row[2], row[3]
            cte_event_id, matched_event_id = row[4], row[5]

            # Check sequence continuity
            expected_seq = i + 1
            if seq != expected_seq:
                errors.append(f"Sequence gap: expected {expected_seq}, got {seq}")

            # Check previous_chain_hash linkage
            if i == 0:
                if stored_prev is not None:
                    errors.append(f"Genesis entry (seq={seq}) has non-null previous_chain_hash")
                expected_prev = None
            else:
                expected_prev = rows[i - 1][3]  # chain_hash of previous row
                if stored_prev != expected_prev:
                    errors.append(
                        f"Chain break at seq={seq}: stored prev "
                        f"{stored_prev[:16]}... != expected {expected_prev[:16]}..."
                    )

            # Recompute chain_hash and compare
            recomputed = _core.compute_chain_hash(event_hash, stored_prev)
            if recomputed != stored_chain:
                errors.append(
                    f"Tamper detected at seq={seq}: recomputed chain_hash "
                    f"{recomputed[:16]}... != stored {stored_chain[:16]}..."
                )

            # #1314: orphan chain row — cte_event_id has no match in
            # cte_events. Either the event was deleted (never legal —
            # cte_events is append-only) or the chain was written with
            # a bogus id (code bug). Either way the chain no longer
            # proves what it claims to prove.
            if matched_event_id is None:
                orphan_chain_rows.append(int(seq))
                errors.append(
                    f"Orphan chain row at seq={seq}: cte_event_id={cte_event_id} has no matching fsma.cte_events row"
                )

        # #1314: cross-check the row counts. chain rows should equal
        # non-rejected event count. A mismatch means an event was
        # written without a chain row (#1307 regression class), which
        # the per-chain walk above cannot detect on its own because it
        # only iterates rows that DO exist.
        missing_chain_rows: List[str] = []
        if len(rows) != cte_events_count:
            missing_chain_rows = self._missing_chain_event_ids(tenant_id)
            if missing_chain_rows:
                errors.append(
                    f"Chain row count ({len(rows)}) != non-rejected event "
                    f"count ({cte_events_count}); {len(missing_chain_rows)} "
                    f"event(s) have no chain entry"
                )

        return _core.ChainVerification(
            valid=(len(errors) == 0 and not orphan_chain_rows and not missing_chain_rows),
            chain_length=len(rows),
            errors=errors,
            checked_at=checked_at,
            orphan_chain_rows=orphan_chain_rows,
            missing_chain_rows=missing_chain_rows,
            cte_events_count=cte_events_count,
        )

    def _missing_chain_event_ids(self, tenant_id: str) -> List[str]:
        """Return non-rejected ``cte_events.id`` values with no
        matching ``hash_chain`` row (#1314 cross-check helper).

        Capped at 1000 ids to bound memory — a chain that far off from
        the event table is already deep into incident-response
        territory; more detail than that belongs in a dedicated audit
        query, not in every verify_chain call.
        """
        rows = self.session.execute(
            text("""
                SELECT ce.id::text
                FROM fsma.cte_events ce
                LEFT JOIN fsma.hash_chain hc
                    ON hc.cte_event_id = ce.id
                   AND hc.tenant_id = ce.tenant_id
                WHERE ce.tenant_id = :tid
                  AND ce.validation_status != 'rejected'
                  AND hc.id IS NULL
                ORDER BY ce.ingested_at
                LIMIT 1000
            """),
            {"tid": tenant_id},
        ).fetchall()
        return [r[0] for r in rows] if rows else []

    # ------------------------------------------------------------------
    # Merkle Tree Verification
    # ------------------------------------------------------------------

    def verify_chain_merkle(self, tenant_id: str) -> MerkleVerification:
        """
        Build a Merkle tree from a tenant's hash chain and return verification info.

        This provides O(log n) inclusion proofs as a complement to the
        linear verify_chain() method. The Merkle tree is computed in memory
        from the ordered event_hashes stored in fsma.hash_chain.
        """
        from shared.merkle_tree import MerkleTree

        from . import core as _core

        rows = self.session.execute(
            text("""
                SELECT event_hash
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num ASC
            """),
            {"tid": tenant_id},
        ).fetchall()

        if not rows:
            # Fail closed on the degenerate case (#2698, mirroring the
            # canonical verifier's #1314 guard): ZERO chain rows while
            # non-rejected events exist. An unreadable (RLS-denied) or
            # emptied chain is indistinguishable from chain-less ingestion,
            # so a `valid=True, chain_length=0` claim — surfaced verbatim by
            # the FDA verification routes — would attest integrity after
            # walking zero rows of evidence. Not a tamper verdict.
            events_count = (
                self.session.execute(
                    text("""
                        SELECT COUNT(*) FROM fsma.cte_events
                        WHERE tenant_id = :tid
                          AND validation_status != 'rejected'
                    """),
                    {"tid": tenant_id},
                ).scalar()
                or 0
            )
            if events_count > 0:
                return _core.MerkleVerification(
                    valid=False,
                    merkle_root=None,
                    chain_length=0,
                    tree_depth=0,
                    errors=[
                        f"No chain rows exist for tenant with {events_count} non-rejected "
                        "events — chain integrity cannot be attested (nothing was walked). "
                        "Not a tamper verdict; failing closed rather than reporting valid."
                    ],
                    checked_at=datetime.now(timezone.utc).isoformat(),
                    no_chain_evidence=True,
                )
            return _core.MerkleVerification(
                valid=True,
                merkle_root=None,
                chain_length=0,
                tree_depth=0,
                errors=[],
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

        hashes = [row[0] for row in rows]
        errors = []

        try:
            tree = MerkleTree(hashes)
            merkle_root = tree.root
            tree_depth = tree.depth
        except Exception as e:
            _core.logger.error(
                "merkle_tree_build_failed",
                extra={"tenant_id": tenant_id, "error": str(e)},
            )
            return _core.MerkleVerification(
                valid=False,
                merkle_root=None,
                chain_length=len(hashes),
                tree_depth=0,
                errors=[f"Failed to build Merkle tree: {e}"],
                checked_at=datetime.now(timezone.utc).isoformat(),
            )

        # Verify every leaf can produce a valid proof back to the root
        for i, event_hash in enumerate(hashes):
            try:
                proof = tree.generate_proof(i)
                if not MerkleTree.verify_proof(event_hash, proof, merkle_root):
                    errors.append(f"Merkle proof verification failed for event at index {i}")
            except Exception as e:
                _core.logger.warning(f"Merkle proof generation failed at index {i}", exc_info=True)
                errors.append(f"Merkle proof generation failed at index {i}: {e}")

        return _core.MerkleVerification(
            valid=len(errors) == 0,
            merkle_root=merkle_root,
            chain_length=len(hashes),
            tree_depth=tree_depth,
            errors=errors,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    def get_merkle_proof(
        self,
        tenant_id: str,
        event_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Generate a Merkle inclusion proof for a specific event.

        Returns a dict with merkle_root, proof steps, event_hash, and index,
        or None if the event is not found in the chain.
        """
        from shared.merkle_tree import MerkleTree

        rows = self.session.execute(
            text("""
                SELECT cte_event_id, event_hash
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num ASC
            """),
            {"tid": tenant_id},
        ).fetchall()

        if not rows:
            return None

        # Find the target event's index in the chain
        target_index = None
        target_hash = None
        hashes = []
        for i, row in enumerate(rows):
            hashes.append(row[1])
            if str(row[0]) == str(event_id):
                target_index = i
                target_hash = row[1]

        if target_index is None:
            return None

        tree = MerkleTree(hashes)
        proof = tree.generate_proof(target_index)

        return {
            "event_id": str(event_id),
            "event_hash": target_hash,
            "index": target_index,
            "merkle_root": tree.root,
            "tree_depth": tree.depth,
            "chain_length": len(hashes),
            "proof": proof,
        }
