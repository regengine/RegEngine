"""Data gap time to fix.

A *gap* is a validation failure on a traceability lot: a required KDE missing
from a CTE record (``missing_kde``) or a CTE record that failed rule
validation (``cte_validation_failed``). Gaps live in ``public.data_gap_events``
(``supabase/migrations/20261024060000_data_gap_time_to_fix.sql``).

State transitions, per (tenant, lot_code, cte_type):

* a record that fails validation opens one gap per failure, idempotently
  (``ON CONFLICT DO NOTHING`` on the partial unique index over open rows), and
  never closes anything;
* a record that passes validation and is persisted closes every open gap for
  that lot and CTE, stamping the closing record id and its canonical SHA-256
  (the persisted ledger hash) as the receipt.

Gap logging is observability. It must never block or roll back ingest, so the
writer catches every error, logs it, and returns.
"""

from __future__ import annotations

import logging
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import text

logger = logging.getLogger("data-gap-tracking")

GAP_KIND_MISSING_KDE = "missing_kde"
GAP_KIND_CTE_VALIDATION_FAILED = "cte_validation_failed"
UNASSIGNED_SUPPLIER_KEY = "unassigned"

# 21 CFR 1.1455(c)(1): records must reach FDA within 24 hours of a request.
AT_RISK_THRESHOLD = timedelta(hours=24)

_MISSING_KDE_RE = re.compile(r"Missing required KDE '([^']+)'")
_HARVESTER_PHONE_ERROR = "Harvester business phone must be a non-empty string"
_RECEIPT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class Gap:
    gap_kind: str
    gap_key: str


@dataclass(frozen=True)
class ValidationOutcome:
    """One record's validation result, queued for the gap writer.

    ``order`` is the record's position in the request so a fail then pass for
    the same lot and CTE in one batch is applied in arrival order.
    """

    order: int
    lot_code: str
    cte_type: str
    gaps: tuple[Gap, ...] = field(default_factory=tuple)
    closing_record_id: Optional[str] = None
    closing_record_hash: Optional[str] = None


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def gaps_from_kde_errors(errors: Iterable[str]) -> tuple[Gap, ...]:
    """Map ``_validate_event_kdes`` messages to missing KDE gaps.

    An unrecognised message still opens a gap (keyed on the message) so a new
    validator message is never silently dropped from time to fix.
    """
    gaps: list[Gap] = []
    for error in errors:
        match = _MISSING_KDE_RE.search(error)
        if match:
            key = match.group(1)
        elif error == _HARVESTER_PHONE_ERROR:
            key = "harvester_business_phone"
        else:
            key = error.strip()
        gap = Gap(GAP_KIND_MISSING_KDE, key)
        if key and gap not in gaps:
            gaps.append(gap)
    return tuple(gaps)


def gap_from_rule_reason(reason: Optional[str]) -> Gap:
    """Map a rules pre-eval reject reason (``"<rule_id>: <why>"``) to a gap keyed on rule id."""
    rule_id = (reason or "").split(":", 1)[0].strip()
    return Gap(GAP_KIND_CTE_VALIDATION_FAILED, rule_id or "rule_violation")


def gap_identity(
    tenant_id: str,
    supplier_key: str,
    lot_code: str,
    cte_type: str,
    gap: Gap,
) -> tuple[str, str, str, str, str, str]:
    """The open gap idempotency key, column for column with ``uq_data_gap_events_open``."""
    return (
        str(tenant_id).strip().lower(),
        supplier_key.strip(),
        lot_code.strip(),
        cte_type.strip().lower(),
        gap.gap_kind,
        gap.gap_key.strip(),
    )


def decide_transition(gaps: Sequence[Gap]) -> str:
    """``"open"`` when the record failed validation, ``"close"`` only when it passed."""
    return "open" if gaps else "close"


def is_receipt_hash(value: Optional[str]) -> bool:
    """True for a lowercase SHA-256 hex digest, the only accepted closing receipt."""
    return bool(value) and _RECEIPT_HASH_RE.match(value) is not None


def median_seconds(durations: Sequence[float]) -> Optional[float]:
    """Median of fix durations in seconds; None when nothing has been fixed yet."""
    if not durations:
        return None
    return float(statistics.median(durations))


def oldest_opened_at(opened_ats: Sequence[datetime]) -> Optional[datetime]:
    return min(opened_ats) if opened_ats else None


def is_at_risk(
    open_opened_ats: Sequence[datetime],
    now: datetime,
    threshold: timedelta = AT_RISK_THRESHOLD,
) -> bool:
    """True when any open gap has been open strictly longer than ``threshold``."""
    return any(now - opened > threshold for opened in open_opened_ats)


def summarize_supplier(
    open_opened_ats: Sequence[datetime],
    fix_durations_seconds: Sequence[float],
    now: datetime,
) -> dict[str, Any]:
    oldest = oldest_opened_at(open_opened_ats)
    return {
        "open_gap_count": len(open_opened_ats),
        "median_time_to_fix_seconds": median_seconds(fix_durations_seconds),
        "oldest_open_gap_opened_at": oldest.isoformat() if oldest else None,
        "at_risk": is_at_risk(open_opened_ats, now),
        "has_data": bool(open_opened_ats) or bool(fix_durations_seconds),
    }


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_OPEN_GAP_SQL = text(
    """
    INSERT INTO public.data_gap_events
        (tenant_id, supplier_key, lot_code, cte_type, gap_kind, gap_key)
    SELECT
        CAST(:tid AS uuid),
        COALESCE(
            (SELECT l.facility_id::text
               FROM public.supplier_traceability_lots l
              WHERE l.tenant_id = CAST(:tid AS uuid)
                AND l.tlc_code = :lot
              LIMIT 1),
            :unassigned
        ),
        :lot, :cte, :kind, :key
    ON CONFLICT (tenant_id, supplier_key, lot_code, cte_type, gap_kind, gap_key)
        WHERE closed_at IS NULL
    DO NOTHING
    """
)

_CLOSE_GAPS_SQL = text(
    """
    UPDATE public.data_gap_events
       SET closed_at = GREATEST(now(), opened_at),
           closing_record_id = CAST(:rid AS uuid),
           closing_record_hash = :rhash
     WHERE tenant_id = CAST(:tid AS uuid)
       AND lot_code = :lot
       AND cte_type = :cte
       AND closed_at IS NULL
    """
)


def _apply_outcome(db_session: Any, tenant_id: str, outcome: ValidationOutcome) -> None:
    lot_code = outcome.lot_code.strip()
    cte_type = outcome.cte_type.strip().lower()
    if decide_transition(outcome.gaps) == "open":
        for gap in outcome.gaps:
            db_session.execute(
                _OPEN_GAP_SQL,
                {
                    "tid": tenant_id,
                    "lot": lot_code,
                    "cte": cte_type,
                    "kind": gap.gap_kind,
                    "key": gap.gap_key.strip(),
                    "unassigned": UNASSIGNED_SUPPLIER_KEY,
                },
            )
        return
    if not outcome.closing_record_id or not is_receipt_hash(outcome.closing_record_hash):
        # No receipt, no close: a gap must never close without proof.
        logger.warning("data_gap_close_skipped_missing_receipt tenant=%s", tenant_id)
        return
    db_session.execute(
        _CLOSE_GAPS_SQL,
        {
            "tid": tenant_id,
            "lot": lot_code,
            "cte": cte_type,
            "rid": outcome.closing_record_id,
            "rhash": outcome.closing_record_hash,
        },
    )


def record_outcomes(db_session: Any, tenant_id: str, outcomes: Sequence[ValidationOutcome]) -> None:
    """Apply queued outcomes in arrival order, then commit. Never raises.

    Call after the ingest transaction has committed: closes then reference
    durable records, and a failure here cannot roll back accepted events.
    Each outcome gets its own savepoint so one bad row does not drop the rest.
    """
    if db_session is None or not outcomes:
        return
    try:
        for outcome in sorted(outcomes, key=lambda o: o.order):
            savepoint = db_session.begin_nested()
            try:
                _apply_outcome(db_session, tenant_id, outcome)
                savepoint.commit()
            except Exception as exc:  # noqa: BLE001 -- gap logging is fail-open
                savepoint.rollback()
                logger.warning(
                    "data_gap_write_failed tenant=%s error_type=%s error=%s",
                    tenant_id,
                    type(exc).__name__,
                    exc,
                )
        db_session.commit()
    except Exception as exc:  # noqa: BLE001 -- gap logging must never block ingest
        logger.warning(
            "data_gap_record_failed tenant=%s error_type=%s error=%s",
            tenant_id,
            type(exc).__name__,
            exc,
        )
        try:
            db_session.rollback()
        except Exception:  # noqa: BLE001
            logger.warning("data_gap_rollback_failed tenant=%s", tenant_id)


_SUMMARY_ROWS_SQL = text(
    """
    SELECT supplier_key,
           opened_at,
           EXTRACT(EPOCH FROM (closed_at - opened_at)) AS fix_seconds
      FROM public.data_gap_events
     WHERE tenant_id = CAST(:tid AS uuid)
       AND supplier_key = ANY(:keys)
    """
)


def fetch_supplier_summaries(
    db_session: Any,
    tenant_id: str,
    supplier_keys: Sequence[str],
    now: datetime,
) -> dict[str, dict[str, Any]]:
    """Per supplier time to fix summary for ``supplier_keys`` (every key is present)."""
    open_by_key: dict[str, list[datetime]] = {key: [] for key in supplier_keys}
    fixed_by_key: dict[str, list[float]] = {key: [] for key in supplier_keys}
    if supplier_keys:
        rows = db_session.execute(_SUMMARY_ROWS_SQL, {"tid": tenant_id, "keys": list(supplier_keys)}).fetchall()
        for supplier_key, opened_at, fix_seconds in rows:
            if fix_seconds is None:
                open_by_key[supplier_key].append(opened_at)
            else:
                fixed_by_key[supplier_key].append(float(fix_seconds))
    return {key: summarize_supplier(open_by_key[key], fixed_by_key[key], now) for key in supplier_keys}
