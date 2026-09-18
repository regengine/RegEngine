"""#2698: unknown-type events must be counted as UNCHECKED, never as covered.

Pre-fix, ``_build_completeness_summary`` gave events whose ``event_type``
is not a ``WebhookCTEType`` member (canonical/EPCIS-ingested types, typos)
an empty required-field list, so an export where NOTHING was checked
reported ``required_kde_coverage_ratio == 1.0``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from services.ingestion.app import fda_export_service as svc  # noqa: E402
from services.ingestion.app.webhook_models import WebhookCTEType  # noqa: E402


def _known_event(**overrides: Any) -> dict:
    event: dict[str, Any] = {
        "event_type": WebhookCTEType.SHIPPING.value,
        "id": "known-1",
        "traceability_lot_code": "T",
        "kdes": {},
    }
    event.update(overrides)
    return event


class TestUncheckedTypeAccounting:
    def test_all_unknown_types_reports_zero_ratio(self) -> None:
        """An export where nothing was checked must NOT claim 100% coverage."""
        summary = svc._build_completeness_summary(
            [{"event_type": "OBJECT_EVENT", "id": "e1"}, {"event_type": "typo_cte", "id": "e2"}]
        )
        assert summary["required_checks_total"] == 0
        assert summary["required_kde_coverage_ratio"] == 0.0
        assert summary["events_unchecked_type"] == 2
        assert summary["unchecked_event_types"] == sorted(["OBJECT_EVENT", "typo_cte"])

    def test_empty_export_stays_vacuously_full(self) -> None:
        """No events at all → nothing to check → ratio stays 1.0."""
        summary = svc._build_completeness_summary([])
        assert summary["required_kde_coverage_ratio"] == 1.0
        assert summary["events_unchecked_type"] == 0
        assert summary["unchecked_event_types"] == []

    def test_mixed_known_and_unknown_flags_unchecked(self) -> None:
        """The ratio covers checked events only; unchecked ones are surfaced."""
        summary = svc._build_completeness_summary([_known_event(), {"event_type": "OBJECT_EVENT", "id": "e2"}])
        assert summary["required_checks_total"] > 0
        assert summary["events_unchecked_type"] == 1
        assert summary["unchecked_event_types"] == ["OBJECT_EVENT"]

    def test_missing_event_type_counts_as_unchecked(self) -> None:
        summary = svc._build_completeness_summary([{"kdes": {}}])
        assert summary["events_unchecked_type"] == 1
        assert summary["required_kde_coverage_ratio"] == 0.0

    def test_known_types_unaffected(self) -> None:
        summary = svc._build_completeness_summary([_known_event()])
        assert summary["events_unchecked_type"] == 0
        # SHIPPING with empty KDEs has missing checks — ratio reflects them.
        assert summary["required_checks_total"] > 0


class TestVerificationPayloadSurfacesUnchecked:
    def test_payload_carries_unchecked_fields(self) -> None:
        from types import SimpleNamespace

        chain = SimpleNamespace(valid=True, chain_length=1, errors=[], checked_at="t")
        events = [{"event_type": "OBJECT_EVENT", "id": "e1", "sha256_hash": "x", "chain_hash": "y"}]
        summary = svc._build_completeness_summary(events)
        payload = svc._build_chain_verification_payload(
            tenant_id="t1",
            tlc=None,
            events=events,
            csv_hash="h",
            chain_verification=chain,
            completeness_summary=summary,
        )
        assert payload["completeness"]["events_unchecked_type"] == 1
        assert payload["completeness"]["unchecked_event_types"] == ["OBJECT_EVENT"]
        assert payload["completeness"]["required_kde_coverage_ratio"] == 0.0
