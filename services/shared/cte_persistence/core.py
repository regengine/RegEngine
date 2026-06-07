# ============================================================
# Deprecated dual-write path — do NOT add new callers.
#
# This module writes to the old schema (fsma.cte_events + fsma.cte_kdes)
# alongside the canonical writer (canonical_persistence.writer, which
# writes to fsma.traceability_events). The canonical writer is the
# forward path; this module stays only to serve the 11+ live callers
# in services/ingestion/app/ (webhook_router_v2, epcis/persistence,
# fda_export/*, etc.) that have not yet been migrated. Retirement is
# tracked as #1335 and is a multi-sprint effort — each caller's tests
# must stay green at every step.
#
# Divergence from canonical — intentional, documented:
#   - idempotency_key formula uses (location_gln, location_name) while
#     canonical_event.TraceabilityEvent.compute_idempotency_key uses
#     (from_facility, to_facility). The same real-world event dual-
#     written through both paths produces DIFFERENT keys in each
#     table. Cross-table reconciliation must therefore use sha256_hash,
#     not idempotency_key.
#
# Changes here risk breaking FDA export, hash chain integrity, and
# graph sync. Prefer fixing the canonical path when both paths have
# the same bug.
# ============================================================
"""
FSMA 204 CTE Persistence Layer — deprecated dual-write path.

Provides database-backed storage for Critical Tracking Events to the
older ``fsma.cte_events`` + ``fsma.cte_kdes`` schema. New ingestion
paths should use ``shared.canonical_persistence`` which writes to
``fsma.traceability_events``. Both paths coexist during the in-progress
migration; see the ``UNSAFE ZONE`` comment block above.

Usage:
    from services.shared.cte_persistence import CTEPersistence

    persistence = CTEPersistence(db_session)
    result = persistence.store_event(tenant_id, event, kdes, alerts)
    chain = persistence.verify_chain(tenant_id)
    events = persistence.query_for_export(tenant_id, tlc, start, end)
"""

from __future__ import annotations

# NOTE (file split): this module was split into sibling modules
# (``writes``, ``batch``, ``queries``, ``verification``, ``exports``)
# purely mechanically. ``core`` remains the compatibility surface:
# every name that used to be a module global here (helpers, constants,
# model classes, hashing functions, ``logger``) is still defined or
# imported below, and the sibling modules resolve them late through
# this module so monkeypatching ``core.X`` keeps working.

import hashlib  # noqa: F401  — kept for backward compat (was a module global)
import json
import logging
import warnings  # noqa: F401  — kept for backward compat (was a module global)
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

from sqlalchemy import text  # noqa: F401  — kept for backward compat
from sqlalchemy.exc import (  # noqa: F401  — kept for backward compat
    DatabaseError,
    OperationalError,
    ProgrammingError,
)
from sqlalchemy.orm import Session

from .models import StoreResult, ChainVerification, MerkleVerification, DuplicateEventError
from .hashing import compute_event_hash, compute_chain_hash, compute_idempotency_key

# ---------------------------------------------------------------------------
# Validation Status Constants (fix #1324)
# ---------------------------------------------------------------------------

#: Event passed all compliance validators — safe to chain and export.
VALIDATION_STATUS_VALID = "valid"

#: Event has warnings but is not outright rejected — included in chain.
VALIDATION_STATUS_WARNING = "warning"

#: Event failed one or more compliance validators at REJECT severity.
#: The event row is persisted (for audit) but is NOT written to the hash
#: chain, is excluded from FDA export queries, and is excluded from graph
#: sync.  See ``store_event`` for the short-circuit logic.
VALIDATION_STATUS_REJECTED = "rejected"

#: Validator severity strings that constitute a hard rejection.
_REJECT_SEVERITIES: frozenset[str] = frozenset({"reject", "error", "critical"})

# Machine-findable marker: this module and canonical_persistence dual-write
# the same events with divergent idempotency-key formulas. Reconciliation
# is required before canonical_persistence can be made the sole writer.
# See #1335 and grep for this constant to find all related references.
DUAL_WRITE_RECONCILIATION_NEEDED = True

logger = logging.getLogger("cte-persistence")


def _is_rejecting_validation_item(item: Dict[str, Any]) -> bool:
    """Return True when an alert or validator result should reject the event."""
    severity = str(item.get("severity", "")).strip().lower()
    if severity in _REJECT_SEVERITIES:
        return True
    return item.get("alert_type") == "missing_required_kde"


def _derive_validation_status(
    alerts: List[Dict[str, Any]],
    validator_results: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Collapse alert and validator outputs into one persisted status."""
    validator_results = validator_results or []
    if any(_is_rejecting_validation_item(item) for item in [*alerts, *validator_results]):
        return VALIDATION_STATUS_REJECTED
    if alerts or validator_results:
        return VALIDATION_STATUS_WARNING
    return VALIDATION_STATUS_VALID


# ---------------------------------------------------------------------------
# Timestamp Validation (fix #1308)
# ---------------------------------------------------------------------------

# Clock-skew tolerance for "future" events: small positive offsets can legitimately
# occur across machines whose clocks aren't perfectly in sync (NTP drift, laptop
# sleep, etc.).  Anything beyond this is rejected as a data-quality error.
_FUTURE_SKEW_TOLERANCE = timedelta(minutes=5)


def _parse_timestamp(value: Any, *, field: str) -> datetime:
    """Parse an ISO-8601 timestamp into a timezone-aware UTC datetime.

    Rejects:
        * None, empty strings, non-string inputs
        * Unparseable formats
        * Naive (no-timezone) datetimes — FSMA records must be
          timezone-unambiguous to support the 24-hour notification rule.
        * Timestamps more than _FUTURE_SKEW_TOLERANCE in the future —
          these almost always indicate caller bugs or data exfiltration
          attempts rather than legitimate forward-dated events.

    Does NOT reject very-old timestamps — legacy backfill is a legitimate
    use case and the regulatory 2-year retention lower bound is enforced
    at query time, not at ingest.

    Returns a datetime normalized to UTC.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{field} is required and must be an ISO-8601 timestamp")

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        # Accept trailing "Z" for UTC by normalizing to +00:00 first.
        candidate = value.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(candidate)
        except ValueError as exc:
            raise ValueError(
                f"{field} is not a valid ISO-8601 timestamp: {value!r}"
            ) from exc
    else:
        raise ValueError(
            f"{field} must be a string or datetime, got {type(value).__name__}"
        )

    if dt.tzinfo is None:
        raise ValueError(
            f"{field} must be timezone-aware (got naive datetime: {value!r}). "
            "FSMA records require an unambiguous UTC offset."
        )

    dt = dt.astimezone(timezone.utc)

    now_utc = datetime.now(timezone.utc)
    if dt > now_utc + _FUTURE_SKEW_TOLERANCE:
        raise ValueError(
            f"{field} is in the future beyond the allowed skew tolerance: "
            f"{dt.isoformat()} (now={now_utc.isoformat()})"
        )
    return dt


# ---------------------------------------------------------------------------
# CTE event_type Validation (fix #1312)
# ---------------------------------------------------------------------------

# The 7 FSMA 204 §1.1310 Critical Tracking Event types, in the SAME
# lowercase form the ``fsma.cte_events_event_type_check`` DB constraint
# accepts (see V037__obligation_cte_rules.sql). The schema already
# rejects bad values at INSERT time — but the app-level guard here
# fails EARLIER (before we hash and chain-lock), with a clearer
# message, and protects against the more subtle typo cases the DB
# constraint also rejects but opaquely (e.g. trailing whitespace, wrong
# case). Keeping the two in sync is load-bearing: if a new CTE type
# lands in the schema, this set must be updated in the same PR or
# valid inputs will be rejected.
#
# Note: canonical_persistence has its own, parallel ``CTEType`` enum
# (services/shared/canonical_event.py) which also includes 'growing'.
# The cte_events schema does NOT currently accept 'growing', so this
# module must not either — the two paths intentionally differ until
# #1335 retires this module.
_ALLOWED_CTE_TYPES = frozenset({
    "harvesting",
    "cooling",
    "initial_packing",
    "first_land_based_receiving",
    "shipping",
    "receiving",
    "transformation",
})


def _validate_event_type(value: Any) -> str:
    """Enforce that ``event_type`` is one of the 7 FSMA 204 CTE types.

    Rejects (with a clear message):
      * ``None``, non-strings, empty / whitespace-only strings
      * Values with leading/trailing whitespace (strict equality, not
        ``.strip()`` — a caller passing ``"HARVESTING "`` has a bug;
        silently normalizing would mask it)
      * Wrong case (``"HARVESTING"``, ``"Shipping"``)
      * Non-FSMA tokens (``"XFORM"``, ``"harvest"``, ``"[object Object]"``)

    The DB's CHECK constraint is the ultimate authority and would also
    reject these — but Postgres rejects them AFTER we've hashed, chain-
    locked, and written KDEs, surfacing as a confusing IntegrityError.
    This guard fails fast with the list of valid types so calling code
    can react meaningfully.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"event_type is required and must be a non-empty string, "
            f"got {type(value).__name__}: {value!r}"
        )
    if value not in _ALLOWED_CTE_TYPES:
        raise ValueError(
            f"event_type {value!r} is not a recognized FSMA 204 CTE type. "
            f"Allowed: {sorted(_ALLOWED_CTE_TYPES)}. "
            f"Note: values are case-sensitive and must have no surrounding "
            f"whitespace."
        )
    return value


# ---------------------------------------------------------------------------
# KDE Value Serialization (fix #1311)
# ---------------------------------------------------------------------------

def _jsonify_kde(value: Any) -> str:
    """Serialize a KDE value to JSON text suitable for ``::jsonb`` cast.

    fsma.cte_kdes.kde_value is JSONB; storing ``str(value)`` produced
    Python repr for dicts (``"{'gln': '...'}"``), which is not JSON
    and cannot be round-tripped.  We emit proper JSON:

        - dict / list / bool / None / int / float  → json.dumps
        - str (already a scalar)                   → json.dumps(str)
                                                     (so it becomes "..."
                                                     rather than a bare
                                                     token the parser
                                                     would reject)
        - anything else                            → json.dumps(str(value))
                                                     as a best-effort
                                                     fallback; the cast
                                                     will fail loudly if
                                                     the result is still
                                                     not valid JSON.
    """
    if isinstance(value, (dict, list, bool, int, float)) or value is None:
        return json.dumps(value, default=str, sort_keys=True)
    if isinstance(value, str):
        return json.dumps(value)
    # Datetime and UUID instances end up here — stringify and wrap.
    return json.dumps(str(value))


# ---------------------------------------------------------------------------
# Append-only enforcement helpers (#1334)
# ---------------------------------------------------------------------------

def _assert_not_exists(sha256_hash: str, tenant_id: str, session: Any) -> None:
    """Raise DuplicateEventError if a CTE event with this sha256_hash already exists.

    fsma.cte_events is append-only — no UPDATE or DELETE is ever valid (#1334).
    This application-level check fires before the INSERT so callers receive a
    typed ``DuplicateEventError`` rather than a DB IntegrityError.  The
    companion DB trigger ``fsma.cte_events_no_update_delete`` enforces the same
    constraint at the SQL layer for direct-DB writes that bypass Python.

    Parameterised SQL only — no user input is interpolated into the query text.
    """
    from sqlalchemy import text as _text  # local import avoids circular at module load

    row = session.execute(
        _text(
            """
            SELECT id FROM fsma.cte_events
            WHERE sha256_hash = :sha AND tenant_id = :tid
            LIMIT 1
            """
        ),
        {"sha": sha256_hash, "tid": tenant_id},
    ).fetchone()
    if row is not None:
        raise DuplicateEventError(event_id=str(row[0]), sha256_hash=sha256_hash)


# ---------------------------------------------------------------------------
# Persistence Layer
# ---------------------------------------------------------------------------

# Imported AFTER the helpers above so the sibling modules can resolve
# ``core`` attributes during their (lazy, call-time) lookups. These
# mixins contain code moved verbatim out of this file.
from .writes import WritePathMixin  # noqa: E402
from .batch import BatchWritePathMixin  # noqa: E402
from .queries import QueryPathMixin  # noqa: E402
from .verification import ChainVerificationMixin  # noqa: E402
from .exports import ExportLogMixin  # noqa: E402


class CTEPersistence(
    WritePathMixin,
    BatchWritePathMixin,
    QueryPathMixin,
    ChainVerificationMixin,
    ExportLogMixin,
):
    """
    LEGACY database-backed persistence for FSMA 204 CTE events.

    New callers should prefer
    ``shared.canonical_persistence.CanonicalEventStore`` which writes
    to ``fsma.traceability_events``. This class exists to serve the
    in-ingestion-service callers that have not yet migrated. Retirement
    is tracked by #1335.

    All methods expect a SQLAlchemy session that has already set
    the tenant context via ``SET LOCAL app.tenant_id = '<uuid>'``, or
    a caller that invokes ``set_tenant_context`` before writing. The
    RLS policies on the ``fsma.*`` tables enforce tenant isolation
    automatically — this module does not filter by ``tenant_id`` in
    read-query ``WHERE`` clauses.

    Implementation note (file split): the method bodies live in the
    sibling mixin modules — ``writes`` (store_event), ``batch``
    (store_events_batch), ``queries`` (TLC/export/graph-sync reads),
    ``verification`` (hash-chain + Merkle), and ``exports``
    (fda_export_log). The split is mechanical; behavior is unchanged.
    """

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------
    # Tenant Context
    # ------------------------------------------------------------------

    def set_tenant_context(self, tenant_id: str) -> None:
        """Set the RLS tenant context for this session.

        Uses ``app.tenant_id`` — the single namespace read by
        ``get_tenant_context()`` and all RLS policies. Previously this
        method set ``regengine.tenant_id`` which was **never** checked by
        any RLS policy, silently bypassing tenant isolation.

        Delegates to ``services.shared.tenant_context.set_tenant_guc`` —
        the canonical Phase B primitive (#1934). Behavior-preserving for
        valid UUIDs (same ``SET LOCAL app.tenant_id = :tid`` SQL with the
        same parameterized binding); the helper additionally validates
        ``tenant_id`` is a UUID up front and raises ``ValueError`` on
        bad input rather than silently setting a non-UUID GUC that would
        break every ``get_tenant_context()::UUID`` comparison in RLS.
        """
        from services.shared.tenant_context import set_tenant_guc  # noqa: PLC0415
        set_tenant_guc(self.session, tenant_id)
