"""Export-window validation.

FSMA 204 responses are always bounded: an auditor issues a traceback
for a specific date range, not "every event we have ever recorded".
Before EPIC-L, the ingestion service accepted ``end_date``-only
exports and the compliance service accepted ranges up to the entire
retention window. Neither is appropriate for a response to a 24-hour
FDA request — both represent full-tenant dumps in a human-readable
format.

This module centralizes the window validation:

* Both ``start`` and ``end`` are required.
* Span is capped at :data:`MAX_EXPORT_WINDOW_DAYS` (90 days).
* Both values are normalized to UTC.
* ``end < start`` is rejected.

Service routers translate :class:`ExportWindowError` into an HTTP 400
with the exception message; the exception itself has no HTTP coupling
so it's safe to use in non-request code paths (cron exports, etc.).

Related issue: EPIC-L (#1655) — "end_date-only exports permitting
full-tenant dumps".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

# 90 days covers the overwhelming majority of FSMA-204 traceback
# windows without letting a caller dump the whole retention window in
# one export. Callers that genuinely need more get an async batched
# job — not a wider synchronous window.
MAX_EXPORT_WINDOW_DAYS = 90


class ExportWindowError(ValueError):
    """Raised when an export date window is missing, malformed, or too wide.

    This is a plain ``ValueError`` so non-HTTP callers can catch it
    generically; the HTTP routers map it to a 400 in one place.
    """


@dataclass(frozen=True)
class ExportWindow:
    """Validated, UTC-normalized export window."""

    start: date
    end: date

    @property
    def span_days(self) -> int:
        return (self.end - self.start).days

    def to_iso(self) -> tuple[str, str]:
        return self.start.isoformat(), self.end.isoformat()


def _coerce(name: str, value: object) -> date:
    """Coerce ``value`` to a ``date`` or raise :class:`ExportWindowError`."""
    if value is None or value == "":
        raise ExportWindowError(f"{name} is required")
    if isinstance(value, datetime):
        # UTC-normalize a datetime by dropping below-day precision after
        # coercing to UTC. This tolerates callers that pass aware or
        # naive datetimes (naive is treated as UTC — the FSMA-204 audit
        # trail records UTC timestamps by construction, so this is the
        # safe assumption here).
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        # Accept both ``YYYY-MM-DD`` and full ISO-8601 timestamps with
        # trailing ``Z`` — the common shapes in our query params.
        try:
            return date.fromisoformat(raw)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ExportWindowError(
                    f"{name} must be ISO-8601 YYYY-MM-DD"
                ) from exc
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).date()
    raise ExportWindowError(f"{name} has an unsupported type: {type(value).__name__}")


def validate_export_window(
    start: Optional[object],
    end: Optional[object],
    *,
    max_days: int = MAX_EXPORT_WINDOW_DAYS,
) -> ExportWindow:
    """Return a validated :class:`ExportWindow` or raise.

    Contract:
      * ``start`` and ``end`` must both be present.
      * ``end`` must be on or after ``start``.
      * Span in days must not exceed ``max_days``.
    """
    start_d = _coerce("start_date", start)
    end_d = _coerce("end_date", end)
    if end_d < start_d:
        raise ExportWindowError("end_date must be on or after start_date")
    span = (end_d - start_d).days
    if span > max_days:
        raise ExportWindowError(
            f"export window of {span} days exceeds the {max_days}-day "
            "FSMA-204 cap — narrow the range or request an async batched job"
        )
    return ExportWindow(start=start_d, end=end_d)


__all__ = [
    "ExportWindow",
    "ExportWindowError",
    "MAX_EXPORT_WINDOW_DAYS",
    "validate_export_window",
]
