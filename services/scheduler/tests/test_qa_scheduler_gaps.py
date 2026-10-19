"""QA gap coverage for services/scheduler.

Focused regression tests for scheduler behaviors the existing suite does
not pin down: per-tenant isolation in the compliance alert loop, alert
countdown mapping and insert idempotency, the strict role-cutover gate,
emit-then-ack stop-on-error, outbox drain crash safety, and tenant
matching outcomes. All tests are deterministic with no network, no
sleeps, and no live database.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError


def _make_item(severity=None, **kw):
    from app.models import EnforcementItem, EnforcementSeverity, SourceType

    return EnforcementItem(
        source_type=SourceType.FDA_RECALL,
        source_id=kw.pop("source_id", "fda_recall:QA-1"),
        title=kw.pop("title", "Acme juice recall"),
        summary=kw.pop("summary", "foreign material found"),
        url=kw.pop("url", "https://example.test/recalls/qa-1"),
        published_date=datetime(2026, 5, 1, tzinfo=timezone.utc),
        severity=severity or EnforcementSeverity.HIGH,
        affected_companies=kw.pop("affected_companies", ["Acme Foods Inc"]),
        raw_data=kw.pop("raw_data", {}),
        **kw,
    )


def _bare_integration():
    """Build ComplianceIntegration without touching the database engine."""
    from app import compliance_integration as ci_module

    integration = ci_module.ComplianceIntegration.__new__(ci_module.ComplianceIntegration)
    return ci_module, integration


def _sessions_for(integration, sessions):
    managers = []
    for session in sessions:
        manager = MagicMock()
        manager.__enter__.return_value = session
        manager.__exit__.return_value = False
        managers.append(manager)
    integration.Session = MagicMock(side_effect=managers)


class TestPerTenantAlertIsolation:
    """One tenant's database failure must not drop other tenants' alerts."""

    def test_matcher_failure_on_first_tenant_does_not_abort_rest(self):
        ci_module, integration = _bare_integration()
        t1, t2 = str(uuid4()), str(uuid4())
        _sessions_for(integration, [MagicMock(), MagicMock()])
        with (
            patch.object(ci_module, "list_maintenance_tenant_ids", return_value=[t1, t2]),
            patch.object(ci_module, "set_tenant_guc", return_value=None),
            patch.object(
                integration,
                "_find_matching_tenants",
                side_effect=[
                    SQLAlchemyError("connection gone"),
                    [{"tenant_id": t2, "reasons": ["supplier:acme"]}],
                ],
            ),
            patch.object(integration, "_create_alert", return_value="alert-1"),
        ):
            result = integration.process_enforcement_item(_make_item())

        assert result == [t2]

    def test_commit_failure_skips_only_that_tenant(self):
        ci_module, integration = _bare_integration()
        t1, t2 = str(uuid4()), str(uuid4())
        failing, succeeding = MagicMock(), MagicMock()
        failing.commit.side_effect = SQLAlchemyError("commit gone")
        _sessions_for(integration, [failing, succeeding])
        with (
            patch.object(ci_module, "list_maintenance_tenant_ids", return_value=[t1, t2]),
            patch.object(ci_module, "set_tenant_guc", return_value=None),
            patch.object(
                integration,
                "_find_matching_tenants",
                side_effect=[
                    [{"tenant_id": t1, "reasons": ["supplier:acme"]}],
                    [{"tenant_id": t2, "reasons": ["supplier:acme"]}],
                ],
            ),
            patch.object(integration, "_create_alert", return_value="alert-1"),
        ):
            result = integration.process_enforcement_item(_make_item())

        assert result == [t2]
        failing.rollback.assert_called()

    def test_non_alert_source_types_are_skipped_without_db(self):
        from app.models import SourceType

        ci_module, integration = _bare_integration()
        integration.Session = MagicMock()
        item = _make_item()
        item.source_type = SourceType.FDA_IMPORT_ALERT

        assert integration.process_enforcement_item(item) == []
        integration.Session.assert_not_called()


class TestCreateAlertContract:
    """Countdown windows and insert idempotency are compliance evidence."""

    @staticmethod
    def _session_for_create():
        session = MagicMock()
        count_result = MagicMock()
        count_result.fetchone.return_value = (0, 0, 0)
        deadline_result = MagicMock()
        deadline_result.fetchone.return_value = None
        session.execute.side_effect = [MagicMock(), count_result, deadline_result, MagicMock()]
        return session

    @pytest.mark.parametrize(
        ("severity_name", "expected_hours"),
        [("CRITICAL", 24), ("HIGH", 24), ("MEDIUM", 48), ("LOW", 48)],
    )
    def test_countdown_hours_by_severity(self, severity_name, expected_hours):
        from app.models import EnforcementSeverity

        _, integration = _bare_integration()
        session = self._session_for_create()
        item = _make_item(severity=EnforcementSeverity[severity_name])

        integration._create_alert(session, uuid4(), item, ["supplier:acme"])

        params = session.execute.call_args_list[0].args[1]
        assert params["countdown_hours"] == expected_hours
        assert params["countdown_end"] - params["countdown_start"] == timedelta(hours=expected_hours)
        assert params["severity"] == severity_name
        assert params["source_type"] == "FDA_RECALL"

    def test_alert_insert_is_idempotent_on_conflict(self):
        _, integration = _bare_integration()
        session = self._session_for_create()

        integration._create_alert(session, uuid4(), _make_item(), ["supplier:acme"])

        statement = str(session.execute.call_args_list[0].args[0])
        assert "ON CONFLICT (tenant_id, source_type, source_id) DO NOTHING" in statement


class TestStrictDatabaseRoleCutover:
    """The cutover gate decides whether identity mutation jobs may run."""

    @staticmethod
    def _clear_env(monkeypatch):
        for var in ("REGENGINE_ENV", "ENVIRONMENT", "ENV", "REGENGINE_REQUIRE_RLS_ENFORCEMENT"):
            monkeypatch.delenv(var, raising=False)

    def test_defaults_to_off(self, monkeypatch):
        from services.scheduler.service import _strict_database_role_cutover_enabled

        self._clear_env(monkeypatch)
        assert _strict_database_role_cutover_enabled() is False

    @pytest.mark.parametrize("var", ["REGENGINE_ENV", "ENVIRONMENT", "ENV"])
    @pytest.mark.parametrize("value", ["production", "staging", " Production "])
    def test_prod_like_environments_enable_cutover(self, monkeypatch, var, value):
        from services.scheduler.service import _strict_database_role_cutover_enabled

        self._clear_env(monkeypatch)
        monkeypatch.setenv(var, value)
        assert _strict_database_role_cutover_enabled() is True

    @pytest.mark.parametrize("value", ["1", "true", "yes", "on", " True "])
    def test_flag_values_enable_cutover(self, monkeypatch, value):
        from services.scheduler.service import _strict_database_role_cutover_enabled

        self._clear_env(monkeypatch)
        monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", value)
        assert _strict_database_role_cutover_enabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", ""])
    def test_negative_flag_values_keep_cutover_off(self, monkeypatch, value):
        from services.scheduler.service import _strict_database_role_cutover_enabled

        self._clear_env(monkeypatch)
        monkeypatch.setenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", value)
        assert _strict_database_role_cutover_enabled() is False

    def test_development_environment_keeps_cutover_off(self, monkeypatch):
        from services.scheduler.service import _strict_database_role_cutover_enabled

        self._clear_env(monkeypatch)
        monkeypatch.setenv("REGENGINE_ENV", "development")
        assert _strict_database_role_cutover_enabled() is False


class TestMarkItemsSeenContract:
    """Stop at the first mark_seen failure so the rest retry next tick."""

    def test_stops_at_first_failure(self):
        from app.models import SourceType

        from services.scheduler.service import SchedulerService

        service = SchedulerService.__new__(SchedulerService)
        service.state_manager = MagicMock()
        service.state_manager.mark_seen.side_effect = [None, RuntimeError("db gone")]
        items = [
            _make_item(source_id="fda_recall:0"),
            _make_item(source_id="fda_recall:1"),
            _make_item(source_id="fda_recall:2"),
        ]

        service._mark_items_seen(items, SourceType.FDA_RECALL)

        assert service.state_manager.mark_seen.call_count == 2
        attempted = {call.kwargs["source_id"] for call in service.state_manager.mark_seen.call_args_list}
        assert attempted == {"fda_recall:0", "fda_recall:1"}


class TestDrainWebhookOutboxContract:
    """The drain tick is telemetry: it must never crash the scheduler."""

    def test_notifier_exception_does_not_propagate(self):
        from services.scheduler.service import SchedulerService

        service = SchedulerService.__new__(SchedulerService)
        service.notifier = MagicMock()
        service.notifier.retry_outbox_once.side_effect = RuntimeError("disk gone")

        assert service.drain_webhook_outbox() is None

    def test_quiet_drain_stays_quiet(self):
        from services.scheduler.service import SchedulerService

        service = SchedulerService.__new__(SchedulerService)
        service.notifier = MagicMock()
        service.notifier.retry_outbox_once.return_value = {
            "attempted": 0,
            "delivered": 0,
            "rescheduled": 0,
            "exhausted": 0,
        }

        assert service.drain_webhook_outbox() is None
        service.notifier.retry_outbox_once.assert_called_once()


class TestNearBootFirstRun:
    def test_returns_near_future_datetime(self):
        from services.scheduler.service import SchedulerService

        before = datetime.now(timezone.utc)
        first_run = SchedulerService._near_boot_first_run(4)

        assert first_run.tzinfo is not None
        assert timedelta(minutes=3) < first_run - before < timedelta(minutes=5)


class TestDisableInactiveAccountsCutover:
    def test_cutover_returns_early_without_touching_db(self, monkeypatch):
        import shared.database

        from services.scheduler.service import SchedulerService

        monkeypatch.setenv("REGENGINE_ENV", "staging")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT", raising=False)
        touched = MagicMock(side_effect=AssertionError("database must not be touched"))
        monkeypatch.setattr(shared.database, "SessionLocal", touched)

        service = SchedulerService.__new__(SchedulerService)
        assert service.disable_inactive_accounts() is None
        touched.assert_not_called()


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    """Route canned rows by query text so matching logic runs for real."""

    def __init__(self, tier1_rows, profile_rows):
        self.tier1_rows = tier1_rows
        self.profile_rows = profile_rows
        self.calls = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, dict(params or {})))
        if "traceability_events" in sql:
            return _FakeResult(self.tier1_rows)
        if "tenant_product_profile" in sql:
            return _FakeResult(self.profile_rows)
        raise AssertionError(f"unexpected query: {sql[:80]}")


class TestFindMatchingTenantsOutcomes:
    """Only tenants whose profile matches the recall should be alerted."""

    @pytest.mark.parametrize(
        ("suppliers", "companies"),
        [
            (["acme"], ["Acme Foods Inc"]),
            (["Acme Foods Incorporated"], ["acme"]),
        ],
    )
    def test_supplier_containment_matches_either_direction(self, suppliers, companies):
        _, integration = _bare_integration()
        tenant_id = uuid4()
        session = _FakeSession(
            tier1_rows=[],
            profile_rows=[(tenant_id, ["Beverages"], ["Midwest"], suppliers)],
        )
        item = _make_item(
            title="Acme juice recall",
            summary="foreign material found",
            affected_companies=companies,
            raw_data={},
        )

        assert integration._find_matching_tenants(session, item, tenant_id=str(tenant_id)) == [
            {"tenant_id": tenant_id, "reasons": [f"supplier:{suppliers[0]}"]}
        ]

    def test_unrelated_tenant_does_not_match(self):
        _, integration = _bare_integration()
        session = _FakeSession(
            tier1_rows=[],
            profile_rows=[(uuid4(), ["Dairy Products"], ["Midwest"], ["DairyCo"])],
        )
        item = _make_item(
            title="Acme canned beans recall",
            summary="possible foreign material contamination",
            affected_companies=["Acme Foods"],
            raw_data={},
        )

        assert integration._find_matching_tenants(session, item, tenant_id=str(uuid4())) == []

    def test_tier1_lot_code_match_alerts_tenant_without_profile(self):
        _, integration = _bare_integration()
        tenant_id = str(uuid4())
        session = _FakeSession(tier1_rows=[(tenant_id,)], profile_rows=[])
        item = _make_item(raw_data={"code_info": "LOT-9"})

        assert integration._find_matching_tenants(session, item, tenant_id=tenant_id) == [
            {"tenant_id": tenant_id, "reasons": ["match_tier:lot_code"]}
        ]

    def test_every_matching_query_is_bound_to_one_tenant(self):
        # No lot-code or profile read may span tenants: each carries the
        # caller's tenant as a bound predicate.
        _, integration = _bare_integration()
        tenant_id = str(uuid4())
        session = _FakeSession(tier1_rows=[], profile_rows=[])
        item = _make_item(raw_data={"code_info": "LOT-9"})

        integration._find_matching_tenants(session, item, tenant_id=tenant_id)

        assert len(session.calls) == 2
        for sql, params in session.calls:
            assert "tenant_id = CAST(:tenant_id AS uuid)" in sql
            assert params["tenant_id"] == tenant_id
