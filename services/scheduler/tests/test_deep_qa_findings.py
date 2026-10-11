"""Deep-QA findings for services/scheduler (no prior issue numbers).

Three real defects, each with a failing-first regression test:

A. ``compliance_integration.process_enforcement_item`` logs
   ``match["tenant_id"]`` in its per-tenant ``except`` handler, but
   ``match`` is only bound *after* ``_find_matching_tenants`` returns.
   When the matcher itself raises, the handler raises ``NameError``,
   which escapes the narrow per-item handler in
   ``SchedulerService._process_new_items`` and aborts alerts for the
   rest of the batch that tick.

B. ``CircuitBreaker`` trips on *cumulative* lifetime failures: five
   stray failures spread over weeks of successful scrapes open the
   circuit. Standard breaker semantics count *consecutive* failures;
   successes must reset the streak while lifetime totals stay intact
   for observability.

C. ``WebhookNotifier._read_outbox`` tolerates malformed JSON lines but
   not well-formed lines with explicit-null fields (``float(None)``
   raises ``TypeError``, which is not in the guarded tuple). One such
   line poisons ``retry_outbox_once`` on every pass until an operator
   hand-edits the file.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))
for _name in list(sys.modules):
    if _name == "app" or _name.startswith("app."):
        sys.modules.pop(_name, None)

from shared.paths import ensure_shared_importable  # noqa: E402

ensure_shared_importable()

import app.notifications as notifications_mod  # noqa: E402
import pytest  # noqa: E402
from app.circuit_breaker import CircuitBreaker, CircuitState  # noqa: E402
from app.models import EnforcementItem, EnforcementSeverity, SourceType  # noqa: E402

OutboxEntry = notifications_mod.OutboxEntry
WebhookNotifier = notifications_mod.WebhookNotifier


@pytest.fixture(autouse=True)
def _allow_mock_webhook_urls(monkeypatch):
    monkeypatch.setattr(notifications_mod, "validate_url", lambda _url: None)


def _make_response(status_code: int) -> MagicMock:
    r = MagicMock()
    r.status_code = status_code
    r.headers = {}
    r.content = b""
    return r


def _make_recall_item() -> EnforcementItem:
    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id="fda_recall:QA-DEEP-1",
        title="QA recall",
        summary="lettuce contamination",
        url="https://example.test/recall/qa-1",
        published_date=datetime.now(timezone.utc),
        severity=EnforcementSeverity.HIGH,
        affected_companies=["Acme Foods"],
        raw_data={"code_info": "LOT-QA1"},
    )


# ── A: unbound ``match`` in the per-tenant except handler ────────────────────


def _boom_matcher(self, session, item, **kwargs):
    raise ValueError("matcher boom")


def test_matcher_failure_before_match_binding_returns_empty(monkeypatch):
    """A matcher failure must not escape as NameError (finding A)."""
    from app import compliance_integration as ci_module

    fake_settings = MagicMock()
    fake_settings.database_url = "sqlite:///:memory:"
    monkeypatch.setattr(ci_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(ci_module, "list_maintenance_tenant_ids", lambda *a, **k: ["tid-1"])
    monkeypatch.setattr(ci_module, "set_tenant_guc", lambda *a, **k: None)
    monkeypatch.setattr(
        ci_module.ComplianceIntegration, "_find_matching_tenants", _boom_matcher
    )

    integration = ci_module.ComplianceIntegration()
    mock_session = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_session
    mock_cm.__exit__.return_value = False
    integration.Session = MagicMock(return_value=mock_cm)

    result = integration.process_enforcement_item(_make_recall_item())

    assert result == []


def test_matcher_failure_for_one_tenant_skips_only_that_tenant(monkeypatch):
    """A failing tenant must not abort alerts for later tenants (finding A)."""
    from uuid import uuid4

    from app import compliance_integration as ci_module

    fake_settings = MagicMock()
    fake_settings.database_url = "sqlite:///:memory:"
    monkeypatch.setattr(ci_module, "get_settings", lambda: fake_settings)
    monkeypatch.setattr(
        ci_module, "list_maintenance_tenant_ids", lambda *a, **k: ["tid-bad", "tid-good"]
    )
    monkeypatch.setattr(ci_module, "set_tenant_guc", lambda *a, **k: None)

    good_tenant = uuid4()

    def _selective_matcher(self, session, item, **kwargs):
        if kwargs.get("tenant_id") == "tid-bad":
            raise ValueError("bad tenant matcher boom")
        return [{"tenant_id": good_tenant, "reasons": ["supplier:Acme"]}]

    monkeypatch.setattr(
        ci_module.ComplianceIntegration, "_find_matching_tenants", _selective_matcher
    )
    monkeypatch.setattr(
        ci_module.ComplianceIntegration,
        "_create_alert",
        lambda self, session, tenant_id, item, reasons: "alert-id",
    )

    integration = ci_module.ComplianceIntegration()
    mock_session = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_session
    mock_cm.__exit__.return_value = False
    integration.Session = MagicMock(return_value=mock_cm)

    result = integration.process_enforcement_item(_make_recall_item())

    assert result == [good_tenant]


# ── B: consecutive (not cumulative) failure counting ─────────────────────────


class TestConsecutiveFailureSemantics:
    def test_success_resets_failure_streak(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_lifetime_failure_total_still_recorded(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert cb.stats.failures == 4
        assert cb.stats.successes == 1

    def test_consecutive_failures_at_threshold_still_open(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


# ── C: explicit-null outbox fields quarantine instead of poison ──────────────


def test_outbox_explicit_null_line_does_not_poison_drain(tmp_path):
    """A well-formed line with null fields is quarantined (finding C)."""
    outbox = tmp_path / "outbox.jsonl"
    corrupt = {
        "url": "https://hook.example.com",
        "payload": {"items": []},
        "attempt_count": 0,
        "first_attempted_at": None,
        "last_attempted_at": None,
        "next_retry_at": None,
        "last_error": "stale",
        "last_status_code": 500,
    }
    due = OutboxEntry(
        url="https://hook.example.com",
        payload={"items": []},
        attempt_count=0,
        next_retry_at=time.time() - 1,
    )
    outbox.write_text(json.dumps(corrupt) + "\n" + json.dumps(due.to_dict()) + "\n")

    n = WebhookNotifier(
        urls=["https://hook.example.com"],
        max_retries=1,
        max_workers=1,
        outbox_path=str(outbox),
    )
    try:
        with patch.object(n.session, "post", return_value=_make_response(200)):
            counter = n.retry_outbox_once()
    finally:
        n.close()

    assert counter["attempted"] == 1
    assert counter["delivered"] == 1
    quarantine = outbox.with_suffix(outbox.suffix + ".quarantine")
    assert quarantine.exists()
    assert "first_attempted_at" in quarantine.read_text()
