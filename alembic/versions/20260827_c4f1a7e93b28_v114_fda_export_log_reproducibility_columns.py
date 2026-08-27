"""v114 — record the FDA export inputs that determine the exported bytes.

``POST /api/v1/fda/export/verify`` regenerates a previous export from its
``fsma.fda_export_log`` row and compares SHA-256 digests; a mismatch is
surfaced to the caller as ``data_integrity: "MISMATCH_DETECTED"``. Two
inputs that materially change those bytes were never stored on the row
(#2898)::

    fsma.fda_export_log
      id, tenant_id, export_type, query_tlc, query_start_date,
      query_end_date, record_count, export_hash, generated_by,
      generated_at, export_fingerprint          -- V002 + v078

1. ``include_pii`` — the permission-gated flag (``fda.export.pii``) that
   decides whether Location Name / Ship From Name / Ship To Name /
   Immediate Previous Source / Receiving Location carry real values or
   ``[REDACTED]``, and whether PII keys survive in the Additional-KDEs
   JSON blob. Without it the verifier always regenerated the *redacted*
   CSV, so every PII-bearing export verified as tampered.

2. ``query_event_type`` — the ``/export/all`` CTE-type filter. It narrows
   the seed set of the full-tenant export and therefore the row set of the
   generated CSV.

Both are nullable with no default, deliberately: NULL means "this row
predates byte-level reproducibility capture", and the verifier reads that
as *not reproducible* and returns HTTP 409 instead of a tamper verdict. A
``DEFAULT false`` backfill would instead assert that historical exports
were redacted — a false statement about FSMA 204 audit evidence.

``include_pii`` is also audit evidence in its own right: it is the record
of whether a regulator-facing export disclosed customer facility names.

Revision ID: c4f1a7e93b28
Revises: d8b2056471a7
Create Date: 2026-08-27

Downgrade guard (#2827 convention, as in v108): dropping these columns
destroys the recorded PII-disclosure posture of every export logged since
this revision — FSMA 204 §1.1455(c) chain-of-custody evidence that cannot
be reconstructed from the CSV itself. The downgrade therefore requires the
same explicit two-variable acknowledgement the baseline downgrade uses.
"""

import os

from alembic import op

# revision identifiers, used by Alembic.
revision = "c4f1a7e93b28"  # pragma: allowlist secret
down_revision = "4e9c1f7a02b6"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE fsma.fda_export_log
            ADD COLUMN IF NOT EXISTS include_pii BOOLEAN,
            ADD COLUMN IF NOT EXISTS query_event_type TEXT
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN fsma.fda_export_log.include_pii IS
        'Whether the export disclosed unredacted facility/location PII. '
        'NULL = row predates capture; /export/verify treats it as not '
        'reproducible and returns 409 rather than a tamper verdict.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN fsma.fda_export_log.query_event_type IS
        'CTE-type filter applied to the export query, if any. Needed to '
        'reproduce the exported byte stream.'
        """
    )


def _require_destructive_downgrade_ack() -> None:
    """Refuse to run the destructive downgrade without an explicit opt-in.

    Same shape and same two variables as the baseline downgrade guard
    (``20260324_97588ba8edf3_baseline...py``) and v108: ``REGENGINE_ENV``
    must name a non-production environment AND
    ``REGENGINE_ALLOW_BASELINE_DOWNGRADE`` must be ``1``.

    To override (dev only)::

        REGENGINE_ENV=development \\
        REGENGINE_ALLOW_BASELINE_DOWNGRADE=1 \\
        alembic downgrade d8b2056471a7
    """
    env = os.environ.get("REGENGINE_ENV", "unset").lower()
    ack = os.environ.get("REGENGINE_ALLOW_BASELINE_DOWNGRADE", "0")
    if env in {"development", "dev", "test", "ci"} and ack == "1":
        return
    raise RuntimeError(
        "v114 downgrade blocked (#2898). Dropping "
        "fsma.fda_export_log.include_pii destroys the record of whether each "
        "regulator-facing export disclosed customer facility names — FSMA 204 "
        "§1.1455(c) audit evidence that cannot be reconstructed from the "
        "export file.\n\n"
        "To proceed in a development environment, set BOTH:\n"
        "  REGENGINE_ENV=development\n"
        "  REGENGINE_ALLOW_BASELINE_DOWNGRADE=1\n\n"
        "For production rollback, restore from a database snapshot rather than "
        "running this downgrade.\n\n"
        f"Current: REGENGINE_ENV={env!r}, "
        f"REGENGINE_ALLOW_BASELINE_DOWNGRADE={ack!r}"
    )


def downgrade() -> None:
    _require_destructive_downgrade_ack()
    op.execute(
        """
        ALTER TABLE fsma.fda_export_log
            DROP COLUMN IF EXISTS include_pii,
            DROP COLUMN IF EXISTS query_event_type
        """
    )
