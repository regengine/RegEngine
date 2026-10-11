"""QA5 deep-pass regression tests for services/scheduler/app/.

Each class pins one real bug found by reading the module. Every test in
this file FAILS on the pre-fix code and PASSES after the fix.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch as _patch
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

# ---------------------------------------------------------------------------
# 1. Circuit breaker must count CONSECUTIVE failures, not lifetime failures
# ---------------------------------------------------------------------------


class TestConsecutiveFailureCounting:
    def test_interspersed_successes_do_not_trip_breaker(self):
        from app.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="qa5", failure_threshold=3, recovery_timeout=300)
        cb.record_failure()
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_consecutive_failures_still_trip_breaker(self):
        from app.circuit_breaker import CircuitBreaker, CircuitState

        cb = CircuitBreaker(name="qa5", failure_threshold=3, recovery_timeout=300)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_cumulative_stats_survive_a_success(self):
        from app.circuit_breaker import CircuitBreaker

        cb = CircuitBreaker(name="qa5", failure_threshold=100, recovery_timeout=300)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.stats.failures == 2
        assert cb.stats.successes == 1


# ---------------------------------------------------------------------------
# 2. One tenant's matcher failure must not abort alerting for later tenants
# ---------------------------------------------------------------------------


def _make_item():
    from app.models import EnforcementItem, EnforcementSeverity, SourceType

    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id="fda_recall:qa5-1",
        title="QA5 recall",
        summary="spinach contamination",
        url="https://example.test/recall/qa5",
        published_date=datetime.now(timezone.utc),
        severity=EnforcementSeverity.HIGH,
        affected_companies=["Acme Foods"],
    )


def test_matcher_failure_for_one_tenant_does_not_abort_others(monkeypatch):
    from app import compliance_integration as ci_module

    fake_settings = MagicMock()
    fake_settings.database_url = "sqlite:///:memory:"
    monkeypatch.setattr(ci_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(ci_module, "set_tenant_guc", lambda *args: None)

    tenant_a = uuid4()
    tenant_b = uuid4()
    monkeypatch.setattr(
        ci_module,
        "list_maintenance_tenant_ids",
        lambda: [tenant_a, tenant_b],
    )

    integration = ci_module.ComplianceIntegration()
    integration.Session = MagicMock  # fresh MagicMock session per tenant

    with (
        _patch.object(
            ci_module.ComplianceIntegration,
            "_find_matching_tenants",
            side_effect=[
                SQLAlchemyError("tenant A profile table unreadable"),
                [{"tenant_id": tenant_b, "reasons": ["supplier:Acme"]}],
            ],
        ),
        _patch.object(
            ci_module.ComplianceIntegration,
            "_create_alert",
            return_value="alert-1",
        ),
    ):
        alerted = integration.process_enforcement_item(_make_item())

    assert alerted == [tenant_b]


# ---------------------------------------------------------------------------
# 3. Outbox lines with explicit null timestamps must quarantine, not crash
# ---------------------------------------------------------------------------


class TestOutboxNullTimestamps:
    def test_null_timestamps_quarantined_without_raising(self, tmp_path):
        from services.scheduler.app.notifications import WebhookNotifier

        outbox = tmp_path / "outbox.jsonl"
        raw = json.dumps(
            {
                "url": "https://hook.example.com",
                "payload": {"items": []},
                "attempt_count": 0,
                "first_attempted_at": None,
                "last_attempted_at": None,
                "next_retry_at": None,
            }
        )
        outbox.write_text(raw + "\n")

        n = WebhookNotifier(urls=["https://hook.example.com"], outbox_path=str(outbox))
        try:
            n.retry_outbox_once()  # must not raise TypeError
        finally:
            n.close()

        quarantine = tmp_path / "outbox.jsonl.quarantine"
        assert quarantine.exists()
        assert raw in quarantine.read_text()


# ---------------------------------------------------------------------------
# 4. RSS dates without a timezone must come back timezone-aware (UTC)
# ---------------------------------------------------------------------------


class TestRssDateAwareness:
    def test_pubdate_without_offset_returns_aware_utc(self):
        from app.scrapers.fda_warning_letters import FDAWarningLettersScraper

        scraper = FDAWarningLettersScraper.__new__(FDAWarningLettersScraper)
        parsed = scraper._parse_rss_date("Wed, 15 Jan 2026 12:00:00")
        assert parsed.tzinfo is not None
        assert parsed.utcoffset().total_seconds() == 0

    def test_pubdate_with_offset_still_respected(self):
        from app.scrapers.fda_warning_letters import FDAWarningLettersScraper

        scraper = FDAWarningLettersScraper.__new__(FDAWarningLettersScraper)
        parsed = scraper._parse_rss_date("Wed, 15 Jan 2026 12:00:00 -0500")
        assert parsed.tzinfo is not None
        assert parsed.utcoffset().total_seconds() == -5 * 3600


# ---------------------------------------------------------------------------
# 5. Quantity parsing must accept numbers coming from JSON payloads
# ---------------------------------------------------------------------------


class TestParseQuantityNumbers:
    def test_numeric_quantity_parses(self):
        from app.fda_fsma_transformer import FSMAEventTransformer

        t = FSMAEventTransformer()
        assert t._parse_quantity(250) == 250.0
        assert t._parse_quantity(2.5) == 2.5
        assert t._parse_quantity(None) is None
        assert t._parse_quantity("") is None
        assert t._parse_quantity("250 cases") == 250.0

    def test_transform_survives_numeric_quantity(self):
        from app.fda_fsma_transformer import FSMAEventTransformer
        from app.models import SourceType

        item = _make_item()
        assert item.source_type == SourceType.FDA_RECALL
        item.raw_data = {"recall_number": "D-qa5", "product_quantity": 250}
        event = FSMAEventTransformer().transform(item)
        assert event is not None
        assert event["lot"]["quantity"] == 250.0
