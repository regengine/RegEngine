"""FDA export-log support for the CTE persistence layer.

Mechanically extracted from ``core.py`` (file split — no logic changes).
``core.CTEPersistence`` composes this mixin.
"""

from __future__ import annotations

import hashlib
from typing import Optional
from uuid import uuid4

from sqlalchemy import text


class ExportLogMixin:
    """Export audit-log methods — mixed into :class:`core.CTEPersistence`."""

    # ------------------------------------------------------------------
    # Export Support
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_export_fingerprint(
        *,
        tenant_id: str,
        export_type: str,
        query_tlc: Optional[str],
        query_start_date: Optional[str],
        query_end_date: Optional[str],
        record_count: int,
        export_hash: str,
    ) -> str:
        """Return a stable fingerprint for an FDA export.

        EPIC-L (#1655): the fingerprint feeds the partial UNIQUE index on
        ``fsma.fda_export_log (tenant_id, export_fingerprint)`` so that a
        retried export — same tenant, same window, same filters, same
        content hash — resolves to a single audit row. The content hash
        dominates the fingerprint: if the underlying CSV changes (a
        corrected event, a new record), the fingerprint changes and the
        second attempt lands a fresh row rather than masking the change.
        """
        parts = "\x1f".join(
            [
                str(tenant_id or ""),
                export_type or "",
                query_tlc or "",
                query_start_date or "",
                query_end_date or "",
                str(record_count),
                export_hash or "",
            ]
        )
        return hashlib.sha256(parts.encode("utf-8")).hexdigest()

    def log_export(
        self,
        tenant_id: str,
        export_hash: str,
        record_count: int,
        query_tlc: Optional[str] = None,
        query_start_date: Optional[str] = None,
        query_end_date: Optional[str] = None,
        generated_by: Optional[str] = None,
        export_type: str = "fda_spreadsheet",
    ) -> str:
        """Log an FDA export event and return the export log ID.

        The insert is idempotent on ``(tenant_id, export_fingerprint)``:
        a second call for the same (tenant, window, filters, content
        hash) returns the pre-existing row's id rather than writing a
        duplicate audit entry (EPIC-L / #1655). Schemas that haven't
        migrated to add the ``export_fingerprint`` column still work —
        the ``INSERT ... ON CONFLICT`` clause degrades to a plain
        insert and the idempotency is simply not enforced.
        """
        export_id = str(uuid4())
        fingerprint = self._compute_export_fingerprint(
            tenant_id=tenant_id,
            export_type=export_type,
            query_tlc=query_tlc,
            query_start_date=query_start_date,
            query_end_date=query_end_date,
            record_count=record_count,
            export_hash=export_hash,
        )
        try:
            row = self.session.execute(
                text(
                    """
                    INSERT INTO fsma.fda_export_log (
                        id, tenant_id, export_type, query_tlc,
                        query_start_date, query_end_date, record_count,
                        export_hash, generated_by, export_fingerprint
                    ) VALUES (
                        :id, :tid, :etype, :tlc, :start, :end, :count,
                        :hash, :by, :fp
                    )
                    ON CONFLICT (tenant_id, export_fingerprint)
                        WHERE export_fingerprint IS NOT NULL
                        DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "id": export_id,
                    "tid": tenant_id,
                    "etype": export_type,
                    "tlc": query_tlc,
                    "start": query_start_date,
                    "end": query_end_date,
                    "count": record_count,
                    "hash": export_hash,
                    "by": generated_by,
                    "fp": fingerprint,
                },
            ).fetchone()
        except Exception:
            # Legacy schema fallback: the ``export_fingerprint`` column
            # isn't in ``fsma.fda_export_log`` yet, so the ON CONFLICT
            # clause has nowhere to land. Fall back to the pre-EPIC-L
            # insert shape — idempotency is lost until the v071
            # migration lands, but the audit row still gets written.
            self.session.execute(
                text(
                    """
                    INSERT INTO fsma.fda_export_log (
                        id, tenant_id, export_type, query_tlc,
                        query_start_date, query_end_date, record_count,
                        export_hash, generated_by
                    ) VALUES (
                        :id, :tid, :etype, :tlc, :start, :end, :count,
                        :hash, :by
                    )
                    """
                ),
                {
                    "id": export_id,
                    "tid": tenant_id,
                    "etype": export_type,
                    "tlc": query_tlc,
                    "start": query_start_date,
                    "end": query_end_date,
                    "count": record_count,
                    "hash": export_hash,
                    "by": generated_by,
                },
            )
            return export_id

        if row is not None:
            # Fresh insert — returned the newly minted id.
            return str(row[0])

        # ON CONFLICT DO NOTHING fired; look up the winning row's id so
        # callers always get a real export log id back rather than the
        # locally generated UUID that never landed.
        existing = self.session.execute(
            text(
                """
                SELECT id FROM fsma.fda_export_log
                WHERE tenant_id = :tid AND export_fingerprint = :fp
                LIMIT 1
                """
            ),
            {"tid": tenant_id, "fp": fingerprint},
        ).fetchone()
        if existing is None:
            # Extremely unlikely: conflict fired but the winning row
            # disappeared between statements. Fall through to a second
            # attempt rather than lying about success.
            raise RuntimeError(
                "log_export: ON CONFLICT fired but no matching row found "
                "for (tenant_id, export_fingerprint)"
            )
        return str(existing[0])
