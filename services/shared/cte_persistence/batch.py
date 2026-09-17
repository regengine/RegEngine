"""Batch write path for the CTE persistence layer (CSV / bulk ingestion).

Mechanically extracted from ``core.py`` (file split — no logic changes).
``core.CTEPersistence`` composes this mixin. Helpers, constants, models
and hashing functions that used to be module globals of ``core.py`` are
resolved late through the ``core`` module (method-local ``from . import
core as _core``) so existing monkeypatch / ``patch("...cte_persistence.
core.X")`` targets keep affecting this code exactly as before the split.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Tuple
from uuid import uuid4

from sqlalchemy import text

if TYPE_CHECKING:  # pragma: no cover — annotation-only import
    from .models import StoreResult


class BatchWritePathMixin:
    """Batch write path — mixed into :class:`core.CTEPersistence`."""

    # ------------------------------------------------------------------
    # Batch Write Path (optimized for CSV/bulk ingestion)
    # ------------------------------------------------------------------

    def store_events_batch(
        self,
        tenant_id: str,
        events: List[Dict[str, Any]],
        source: str = "csv",
    ) -> List[StoreResult]:
        """
        Persist multiple CTE events in optimized batches.

        Instead of N round-trips per event, this method:
        1. Batch-checks idempotency with a single SELECT ... IN (...)
        2. Computes all hashes in Python (sequential chain, no DB needed)
        3. Batch-INSERTs events, KDEs, and chain entries

        The caller is responsible for committing the session.

        Returns:
            List of StoreResult, one per input event.
        """
        # Late-bind through the core module so patched attributes
        # (e.g. core._assert_not_exists) take effect (#file-split).
        from . import core as _core

        # #1335 — LEGACY write path. Migrate callers to
        # ``shared.canonical_persistence.CanonicalEventStore``.
        warnings.warn(
            "CTEPersistence.store_events_batch() is LEGACY (#1335). "
            "Use shared.canonical_persistence.CanonicalEventStore instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        if not events:
            return []

        # --- Serialize chain growth per-tenant (fix #1332) ---
        # Mirrors the single-write path above. Taken before any chain
        # read so two concurrent first-event batches serialize on the
        # same tenant rather than both producing sequence_num=1.
        self._acquire_chain_lock(tenant_id)

        # --- Step 1: Pre-compute idempotency keys (+ validate ts; fix #1308) ---
        prepared = []
        for evt in events:
            event_id = str(uuid4())
            kdes = evt.get("kdes") or {}
            # event_type guard (fix #1312) — reject free-form strings
            # before doing any hashing/insert work for this row. Runs
            # per-row so one malformed event in a batch fails loudly
            # rather than corrupting the other N-1 rows' chain or
            # polluting the idempotency cache.
            evt = dict(evt)  # don't mutate caller input
            evt["event_type"] = _core._validate_event_type(evt.get("event_type"))
            # Parse + validate timestamps, normalize to UTC ISO-8601.
            event_dt = _core._parse_timestamp(evt.get("event_timestamp"), field="event_timestamp")
            evt["event_timestamp"] = event_dt.isoformat()
            if evt.get("event_entry_timestamp") is not None:
                entry_dt = _core._parse_timestamp(evt["event_entry_timestamp"], field="event_entry_timestamp")
                evt["event_entry_timestamp"] = entry_dt.isoformat()
            idemp_key = _core.compute_idempotency_key(
                evt["event_type"],
                evt["traceability_lot_code"],
                evt["event_timestamp"],
                source,
                kdes,
                location_gln=evt.get("location_gln"),
                location_name=evt.get("location_name"),
            )
            prepared.append(
                {
                    "event_id": event_id,
                    "idemp_key": idemp_key,
                    "evt": evt,
                    "kdes": kdes,
                }
            )

        # --- Step 2: Batch idempotency check ---
        all_keys = [p["idemp_key"] for p in prepared]
        existing_map: Dict[str, Tuple[str, str, str]] = {}
        # SQLAlchemy doesn't support WHERE IN with named params for lists easily,
        # so chunk into groups of 100
        for chunk_start in range(0, len(all_keys), 100):
            chunk = all_keys[chunk_start : chunk_start + 100]
            placeholders = ", ".join(f":k{i}" for i in range(len(chunk)))
            params = {f"k{i}": k for i, k in enumerate(chunk)}
            params["tid"] = tenant_id
            rows = self.session.execute(
                text(f"""
                    SELECT idempotency_key, id, sha256_hash, chain_hash
                    FROM fsma.cte_events
                    WHERE tenant_id = :tid AND idempotency_key IN ({placeholders})
                """),
                params,
            ).fetchall()
            for row in rows:
                existing_map[row[0]] = (str(row[1]), row[2], row[3])

        # --- Step 3: Get chain head once ---
        # No FOR UPDATE — see writes.store_event: the advisory lock
        # serializes appends and the v111 grant inventory is append-only.
        chain_head = self.session.execute(
            text("""
                SELECT chain_hash, sequence_num
                FROM fsma.hash_chain
                WHERE tenant_id = :tid
                ORDER BY sequence_num DESC
                LIMIT 1
            """),
            {"tid": tenant_id},
        ).fetchone()

        previous_chain_hash = chain_head[0] if chain_head else None
        next_sequence = (chain_head[1] + 1) if chain_head else 1

        # --- Step 4: Compute all hashes in memory, prepare batch inserts ---
        event_rows = []
        kde_rows = []
        chain_rows = []
        # (event_id, alert) pairs — written after the events INSERT so we only
        # emit rows for events that actually landed (#2902).
        alert_rows: List[Tuple[str, Dict[str, Any]]] = []
        results: List[StoreResult] = []

        for p in prepared:
            # Skip idempotent
            if p["idemp_key"] in existing_map:
                eid, sha, ch = existing_map[p["idemp_key"]]
                results.append(
                    _core.StoreResult(
                        success=True,
                        event_id=eid,
                        sha256_hash=sha,
                        chain_hash=ch,
                        idempotent=True,
                        errors=[],
                        kde_completeness=1.0,
                        alerts=[],
                    )
                )
                continue

            evt = p["evt"]
            event_id = p["event_id"]
            kdes = p["kdes"]
            alerts = evt.get("alerts") or []
            validator_results = evt.get("validator_results") or []

            rejection_reasons: List[str] = []
            for item in [*validator_results, *alerts]:
                if _core._is_rejecting_validation_item(item):
                    reason = item.get("reason") or item.get("message") or str(item)
                    rejection_reasons.append(reason)
            validation_status = _core._derive_validation_status(alerts, validator_results)

            # --- Quantity validation (fix #1306) ---
            # Previous implementation silently clamped ``quantity`` to a
            # minimum of 1.0 (both in the hash input and the row value),
            # so a HARVESTING event for 0.25 kg was persisted and hashed
            # as 1.0 kg.  The single-event path does NOT clamp, so the
            # same input via two code paths produced different SHA-256
            # hashes and different row values.  FSMA audit integrity
            # depends on the persisted regulatory payload matching what
            # the caller sent, so we now reject anything non-positive
            # rather than silently rewriting it.
            raw_qty = evt.get("quantity")
            if raw_qty is None:
                raise ValueError(
                    f"quantity is required for CTE event "
                    f"(tlc={evt.get('traceability_lot_code')}, "
                    f"type={evt.get('event_type')})"
                )
            try:
                quantity = float(raw_qty)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"quantity must be numeric, got {raw_qty!r}") from exc
            if quantity <= 0:
                raise ValueError(f"quantity must be > 0, got {quantity} (tlc={evt.get('traceability_lot_code')})")

            sha256_hash = _core.compute_event_hash(
                event_id,
                evt["event_type"],
                evt["traceability_lot_code"],
                evt.get("product_description", ""),
                quantity,
                evt.get("unit_of_measure", ""),
                evt.get("location_gln"),
                evt.get("location_name"),
                evt["event_timestamp"],
                kdes,
            )
            if evt.get("_canonical_event") is not None:
                sha256_hash = _core.compute_canonical_event_hash(event_id, tenant_id, evt["_canonical_event"])

            # --- Append-only enforcement (#1334) ---
            _core._assert_not_exists(sha256_hash, tenant_id, self.session)

            chain_hash = _core.compute_chain_hash(sha256_hash, previous_chain_hash)

            event_rows.append(
                {
                    "id": event_id,
                    "tenant_id": tenant_id,
                    "event_type": evt["event_type"],
                    "tlc": evt["traceability_lot_code"],
                    "product_description": evt.get("product_description", ""),
                    "quantity": quantity,
                    "unit_of_measure": evt.get("unit_of_measure", ""),
                    "location_gln": evt.get("location_gln"),
                    "location_name": evt.get("location_name"),
                    "event_timestamp": evt["event_timestamp"],
                    "source": source,
                    "source_event_id": evt.get("source_event_id"),
                    "idempotency_key": p["idemp_key"],
                    "sha256_hash": sha256_hash,
                    "chain_hash": chain_hash,
                    "epcis_event_type": evt.get("epcis_event_type"),
                    "epcis_action": evt.get("epcis_action"),
                    "epcis_biz_step": evt.get("epcis_biz_step"),
                    "validation_status": validation_status,
                }
            )

            if validation_status != _core.VALIDATION_STATUS_REJECTED:
                for kde_key, kde_value in kdes.items():
                    if kde_value is not None:
                        kde_rows.append(
                            {
                                "tenant_id": tenant_id,
                                "cte_event_id": event_id,
                                "kde_key": kde_key,
                                # fix #1311 — JSON text, cast to jsonb in the batch INSERT
                                "kde_value": _core._jsonify_kde(kde_value),
                                "is_required": False,
                            }
                        )

                chain_rows.append(
                    {
                        "tenant_id": tenant_id,
                        "cte_event_id": event_id,
                        "sequence_num": next_sequence,
                        "event_hash": sha256_hash,
                        "previous_chain_hash": previous_chain_hash,
                        "chain_hash": chain_hash,
                    }
                )

                # #2902 — the batch path had no fsma.compliance_alerts writer
                # at all, so every alert generated upstream was discarded here
                # while the single-event path persisted it. Queue them for the
                # post-INSERT write below.
                for alert in alerts:
                    alert_rows.append((event_id, alert))

                results.append(
                    _core.StoreResult(
                        success=True,
                        event_id=event_id,
                        sha256_hash=sha256_hash,
                        chain_hash=chain_hash,
                        idempotent=False,
                        errors=[],
                        kde_completeness=1.0,
                        alerts=alerts,
                    )
                )

                # Advance chain state only for accepted events.
                previous_chain_hash = chain_hash
                next_sequence += 1
            else:
                results.append(
                    _core.StoreResult(
                        success=False,
                        event_id=event_id,
                        sha256_hash=sha256_hash,
                        chain_hash=chain_hash,
                        idempotent=False,
                        errors=rejection_reasons,
                        kde_completeness=1.0,
                        alerts=alerts,
                    )
                )

            # #2820: later rows in this same batch with the same key must
            # reuse this result. Without this, the second occurrence
            # advances previous_chain_hash for a row ON CONFLICT will drop,
            # forking the in-memory chain from what actually persisted.
            existing_map[p["idemp_key"]] = (event_id, sha256_hash, chain_hash)

        # --- Step 5: Batch INSERT (with lost-race reconciliation — #1248) ---
        # ON CONFLICT DO NOTHING silently discards rows whose idempotency
        # key collides with a concurrent writer's INSERT. Before #1248 we
        # still reported idempotent=False / event_id=<our new uuid> for
        # those, so the caller walked away with a phantom event_id that
        # never landed. RETURNING id tells us exactly which ids actually
        # inserted; the complement is the lost-race set and we re-select
        # the winner rows to patch our StoreResult list.
        inserted_ids: set[str] = set()
        if event_rows:
            # Chunk inserts to avoid parameter limits (Postgres max ~32K params)
            for chunk_start in range(0, len(event_rows), 50):
                chunk = event_rows[chunk_start : chunk_start + 50]
                values_clauses = []
                params: Dict[str, Any] = {}
                for i, row in enumerate(chunk):
                    values_clauses.append(
                        f"(:id_{i}, :tid_{i}, :et_{i}, :tlc_{i}, :pd_{i}, :qty_{i}, :uom_{i}, "
                        f":gln_{i}, :ln_{i}, :ts_{i}, :eets_{i}, :src_{i}, :seid_{i}, :ik_{i}, "
                        f":sha_{i}, :ch_{i}, :eet_{i}, :ea_{i}, :ebs_{i}, :vs_{i})"
                    )
                    params.update(
                        {
                            f"id_{i}": row["id"],
                            f"tid_{i}": row["tenant_id"],
                            f"et_{i}": row["event_type"],
                            f"tlc_{i}": row["tlc"],
                            f"pd_{i}": row["product_description"],
                            f"qty_{i}": row["quantity"],
                            f"uom_{i}": row["unit_of_measure"],
                            f"gln_{i}": row["location_gln"],
                            f"ln_{i}": row["location_name"],
                            f"ts_{i}": row["event_timestamp"],
                            f"eets_{i}": row.get("event_entry_timestamp", datetime.now(timezone.utc).isoformat()),
                            f"src_{i}": row["source"],
                            f"seid_{i}": row["source_event_id"],
                            f"ik_{i}": row["idempotency_key"],
                            f"sha_{i}": row["sha256_hash"],
                            f"ch_{i}": row["chain_hash"],
                            f"eet_{i}": row["epcis_event_type"],
                            f"ea_{i}": row["epcis_action"],
                            f"ebs_{i}": row["epcis_biz_step"],
                            f"vs_{i}": row["validation_status"],
                        }
                    )
                sql = f"""
                    INSERT INTO fsma.cte_events (
                        id, tenant_id, event_type, traceability_lot_code,
                        product_description, quantity, unit_of_measure,
                        location_gln, location_name, event_timestamp,
                        event_entry_timestamp,
                        source, source_event_id, idempotency_key,
                        sha256_hash, chain_hash,
                        epcis_event_type, epcis_action, epcis_biz_step,
                        validation_status
                    ) VALUES {", ".join(values_clauses)}
                    ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
                    RETURNING id
                """
                returned = self.session.execute(text(sql), params).fetchall()
                for r in returned:
                    inserted_ids.add(str(r[0]))

            # --- #1248 lost-race reconciliation ---
            # For every event_row that was NOT in the returned set, the
            # concurrent writer won; re-select the winner by idempotency
            # key and rewrite our StoreResult so the caller sees the
            # authoritative event_id / sha256 / chain.
            lost_idemp_keys = [row["idempotency_key"] for row in event_rows if str(row["id"]) not in inserted_ids]
            if lost_idemp_keys:
                # Map idempotency_key → position in ``results`` so we can
                # patch the entry the caller is going to see.
                key_to_result_idx: Dict[str, int] = {}
                for idx, p in enumerate(prepared):
                    key_to_result_idx[p["idemp_key"]] = idx
                winners: Dict[str, Tuple[str, str, str]] = {}
                for chunk_start in range(0, len(lost_idemp_keys), 100):
                    chunk_keys = lost_idemp_keys[chunk_start : chunk_start + 100]
                    placeholders = ", ".join(f":lk{i}" for i in range(len(chunk_keys)))
                    lr_params: Dict[str, Any] = {f"lk{i}": k for i, k in enumerate(chunk_keys)}
                    lr_params["tid"] = tenant_id
                    rows = self.session.execute(
                        text(f"""
                            SELECT idempotency_key, id, sha256_hash, chain_hash
                            FROM fsma.cte_events
                            WHERE tenant_id = :tid
                              AND idempotency_key IN ({placeholders})
                        """),
                        lr_params,
                    ).fetchall()
                    for idemp_key, winner_id, sha, ch in rows:
                        winners[idemp_key] = (str(winner_id), sha, ch)
                for idemp_key, (winner_id, sha, ch) in winners.items():
                    ridx = key_to_result_idx.get(idemp_key)
                    if ridx is None:
                        continue
                    results[ridx] = _core.StoreResult(
                        success=True,
                        event_id=winner_id,
                        sha256_hash=sha,
                        chain_hash=ch,
                        idempotent=True,
                        errors=[],
                        kde_completeness=1.0,
                        alerts=[],
                    )
                _core.logger.info(
                    "batch_events_lost_race_reconciled",
                    extra={
                        "tenant_id": tenant_id,
                        "lost_race": len(lost_idemp_keys),
                    },
                )

        if kde_rows:
            for chunk_start in range(0, len(kde_rows), 200):
                chunk = kde_rows[chunk_start : chunk_start + 200]
                values_clauses = []
                params = {}
                for i, row in enumerate(chunk):
                    # fix #1311: cast kde_value param to jsonb in the VALUES tuple
                    values_clauses.append(f"(:tid_{i}, :eid_{i}, :kk_{i}, CAST(:kv_{i} AS jsonb), :ir_{i})")
                    params.update(
                        {
                            f"tid_{i}": row["tenant_id"],
                            f"eid_{i}": row["cte_event_id"],
                            f"kk_{i}": row["kde_key"],
                            f"kv_{i}": row["kde_value"],
                            f"ir_{i}": row["is_required"],
                        }
                    )
                sql = f"""
                    INSERT INTO fsma.cte_kdes (
                        tenant_id, cte_event_id, kde_key, kde_value, is_required
                    ) VALUES {", ".join(values_clauses)}
                    ON CONFLICT (cte_event_id, kde_key) DO NOTHING
                """
                self.session.execute(text(sql), params)

        if chain_rows:
            # --- fix #1307 ---
            # Previous implementation blindly INSERTed every chain row,
            # but the companion cte_events INSERT above uses ON CONFLICT
            # DO NOTHING — when a batch lost the idempotency race for one
            # of its events, the chain still wrote and produced an orphan
            # row pointing at a non-existent cte_event_id, which breaks
            # verify_chain's expected_seq = i+1 check.
            #
            # We now mirror the single-event path: each chain row is
            # inserted via INSERT ... SELECT guarded by a WHERE EXISTS
            # check against fsma.cte_events, so orphan rows cannot occur.
            # Rows are issued one at a time to keep the guarded form
            # simple and avoid VALUES-expansion footguns.
            for row in chain_rows:
                self.session.execute(
                    text("""
                        INSERT INTO fsma.hash_chain (
                            tenant_id, cte_event_id, sequence_num,
                            event_hash, previous_chain_hash, chain_hash
                        )
                        SELECT :tenant_id, :cte_event_id, :sequence_num,
                               :event_hash, :previous_chain_hash, :chain_hash
                        WHERE EXISTS (
                            SELECT 1 FROM fsma.cte_events
                            WHERE id = :cte_event_id
                              AND tenant_id = :tenant_id
                        )
                    """),
                    row,
                )

        # --- Compliance alerts (fix #2902) ---
        # Mirrors the single-event path (writes.store_event): each alert gets
        # its own savepoint so a bad alert row can never take down the event
        # and hash-chain evidence that was already written.
        #
        # Only events whose INSERT actually landed get alerts. A row that lost
        # the ON CONFLICT race was reconciled to the *winner's* event_id above;
        # writing our alert against our own discarded uuid would orphan it
        # against a row that does not exist — the same defect #1307 fixed for
        # fsma.hash_chain — and the winning writer persists its own alerts.
        alerts_written = 0
        for event_id, alert in alert_rows:
            if str(event_id) not in inserted_ids:
                continue
            nested = self.session.begin_nested()
            try:
                self.session.execute(
                    text(_core.ALERT_INSERT_SQL),
                    _core._alert_insert_params(tenant_id, event_id, alert),
                )
                # Release the savepoint. A batch can carry many alerts, so
                # unlike the single-event path we must not leave one open per
                # alert for the outer transaction to unwind.
                nested.commit()
                alerts_written += 1
            except Exception as exc:
                nested.rollback()
                _core.logger.warning(
                    "alert_insert_failed",
                    extra={
                        "event_id": event_id,
                        "alert_type": alert.get("alert_type", "missing_kde"),
                        "error": str(exc),
                    },
                )

        _core.logger.info(
            "batch_events_persisted",
            extra={
                "tenant_id": tenant_id,
                "total": len(events),
                "new": len(event_rows),
                "idempotent": len(events) - len(event_rows),
                "kdes": len(kde_rows),
                "alerts": alerts_written,
            },
        )

        return results
