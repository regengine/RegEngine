"""Data-free webhook router helper and failure-path checks."""

import sys
import types
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).resolve().parent.parent
if str(service_dir) not in sys.path:
    sys.path.insert(0, str(service_dir))

import app.webhook_router_v2 as wr  # noqa: E402
from app.webhook_models import WebhookCTEType  # noqa: E402


def _empty_event(cte_type=WebhookCTEType.SHIPPING, **kdes):
    """Only empty schema fields; no transaction or location identity."""
    return types.SimpleNamespace(
        cte_type=cte_type,
        traceability_lot_code="",
        product_description="",
        quantity=None,
        unit_of_measure="",
        location_name=None,
        location_gln=None,
        kdes=kdes,
    )


class TestSmallHelpers:
    def test_is_production_true(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_ENV", "production")
        assert wr._is_production() is True

    def test_is_production_false(self, monkeypatch):
        monkeypatch.delenv("REGENGINE_ENV", raising=False)
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert wr._is_production() is False

    def test_verify_api_key_missing_header_rejects(self):
        with pytest.raises(HTTPException) as exc:
            wr._verify_api_key(None)
        assert exc.value.status_code == 401

    def test_get_persistence_none_session_returns_none(self):
        assert wr._get_persistence(None) is None

    def test_get_persistence_happy_path(self, monkeypatch):
        session = object()
        fake_cte = types.ModuleType("shared.cte_persistence")
        fake_cte.CTEPersistence = lambda value: value
        monkeypatch.setitem(sys.modules, "shared.cte_persistence", fake_cte)
        assert wr._get_persistence(session) is session

    def test_get_persistence_importerror_returns_none(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "shared.cte_persistence", None)
        assert wr._get_persistence(object()) is None


class TestReplayWindowEnvHelpers:
    def test_max_event_age_days_default(self, monkeypatch):
        monkeypatch.delenv("WEBHOOK_MAX_EVENT_AGE_DAYS", raising=False)
        assert wr._max_event_age_days() == 90

    def test_max_event_age_days_override(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_MAX_EVENT_AGE_DAYS", "7")
        assert wr._max_event_age_days() == 7

    def test_max_event_age_days_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_MAX_EVENT_AGE_DAYS", "")
        assert wr._max_event_age_days() == 90

    def test_max_event_future_hours_default(self, monkeypatch):
        monkeypatch.delenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", raising=False)
        assert wr._max_event_future_hours() == 24

    def test_max_event_future_hours_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("WEBHOOK_MAX_EVENT_FUTURE_HOURS", "")
        assert wr._max_event_future_hours() == 24

    def test_unparseable_timestamp_window(self):
        assert "not parseable" in wr._validate_event_timestamp_window("")


class TestReplayMetricClassification:
    def test_unparseable_timestamp_classified(self):
        assert wr._classify_replay_rejection("") == ("unparseable", "na")

    def test_record_replay_rejection_no_op_when_disabled(self, monkeypatch):
        monkeypatch.setattr(wr, "_WEBHOOK_METRICS_ENABLED", False)
        wr._record_replay_rejection("")

    def test_record_replay_rejection_records_when_enabled(self, monkeypatch):
        labels = []

        class Counter:
            def labels(self, **values):
                labels.append(values)
                return self

            def inc(self):
                pass

        monkeypatch.setattr(wr, "_WEBHOOK_METRICS_ENABLED", True)
        monkeypatch.setattr(wr, "WEBHOOK_REPLAY_REJECTED", Counter())
        wr._record_replay_rejection("")
        assert labels == [{"reason": "unparseable", "age_bucket": "na"}]


class TestCheckRateLimit:
    def test_allow_records_remaining(self, monkeypatch):
        captured = {}

        def allow(**kwargs):
            captured.update(kwargs)
            return True, 0

        monkeypatch.setattr(wr, "consume_tenant_rate_limit", allow)
        wr._check_rate_limit("")
        assert captured["tenant_id"] == ""
        assert captured["bucket_suffix"] == "webhooks.ingest"

    def test_block_raises_429(self, monkeypatch):
        monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **kwargs: (False, 0))
        with pytest.raises(HTTPException) as exc:
            wr._check_rate_limit("")
        assert exc.value.status_code == 429


class TestValidateEventKdes:
    def test_missing_required_kde_reported(self):
        errors = wr._validate_event_kdes(_empty_event())
        assert any("Missing required KDE" in error for error in errors)

    def test_empty_string_counts_as_missing(self):
        errors = wr._validate_event_kdes(_empty_event(ship_date=""))
        assert any("ship_date" in error for error in errors)


class TestGenerateAlerts:
    def test_shipping_event_missing_route_emits_alert(self):
        alerts = wr._generate_alerts(_empty_event())
        assert [alert["alert_type"] for alert in alerts] == ["incomplete_route"]

    def test_non_shipping_event_returns_empty(self):
        assert wr._generate_alerts(_empty_event(WebhookCTEType.HARVESTING)) == []


class TestCheckObligations:
    def test_no_session_returns_empty(self):
        assert wr._check_obligations(None, None, "", "") == []

    def test_no_rows_returns_empty(self):
        class Session:
            def begin_nested(self):
                return types.SimpleNamespace(commit=lambda: None)

            def execute(self, statement, params):
                return types.SimpleNamespace(fetchall=lambda: [])

        assert wr._check_obligations(Session(), _empty_event(), "", "") == []

    def test_nested_query_failure_rolls_back_and_returns_empty(self):
        rolled_back = []

        class Session:
            def begin_nested(self):
                return types.SimpleNamespace(rollback=lambda: rolled_back.append(True))

            def execute(self, statement, params):
                raise ValueError

        assert wr._check_obligations(Session(), _empty_event(), "", "") == []
        assert rolled_back == [True]

    def test_outer_exception_returns_empty(self):
        class Session:
            def begin_nested(self):
                raise ValueError

        assert wr._check_obligations(Session(), _empty_event(), "", "") == []


class TestRedisHelpers:
    def test_get_redis_client_error_returns_none(self, monkeypatch):
        fake_redis = types.ModuleType("redis")

        def fail(*args, **kwargs):
            raise ConnectionError

        fake_redis.from_url = fail
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        assert wr._get_redis_client() is None

    def test_get_redis_client_success(self, monkeypatch):
        client = object()
        fake_redis = types.ModuleType("redis")
        fake_redis.from_url = lambda *args, **kwargs: client
        monkeypatch.setitem(sys.modules, "redis", fake_redis)
        assert wr._get_redis_client() is client

    def test_incr_sync_counter_uses_redis_when_available(self, monkeypatch):
        captured = []

        class Client:
            def incr(self, key):
                captured.append(key)

        monkeypatch.setattr(wr, "_get_redis_client", lambda: Client())
        wr._incr_sync_counter("successes")
        assert captured == [f"{wr._SYNC_COUNTER_PREFIX}:successes"]

    def test_incr_sync_counter_falls_back_on_failures_key(self, monkeypatch):
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        before = wr._graph_sync_failures
        wr._incr_sync_counter("failures")
        assert wr._graph_sync_failures == before + 1

    def test_incr_sync_counter_falls_back_on_successes_key(self, monkeypatch):
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        before = wr._graph_sync_successes
        wr._incr_sync_counter("successes")
        assert wr._graph_sync_successes == before + 1

    def test_incr_sync_counter_redis_raise_falls_back(self, monkeypatch):
        class Client:
            def incr(self, key):
                raise RuntimeError

        monkeypatch.setattr(wr, "_get_redis_client", lambda: Client())
        before = wr._graph_sync_successes
        wr._incr_sync_counter("successes")
        assert wr._graph_sync_successes == before + 1

    def test_get_graph_sync_stats_reads_from_redis(self, monkeypatch):
        class Client:
            def get(self, key):
                return None

        monkeypatch.setattr(wr, "_get_redis_client", lambda: Client())
        assert wr.get_graph_sync_stats() == {"successes": 0, "failures": 0}

    def test_get_graph_sync_stats_redis_none_returns_in_memory(self, monkeypatch):
        monkeypatch.setattr(wr, "_get_redis_client", lambda: None)
        assert wr.get_graph_sync_stats() == {
            "successes": wr._graph_sync_successes,
            "failures": wr._graph_sync_failures,
        }

    def test_get_graph_sync_stats_redis_raises_returns_in_memory(self, monkeypatch):
        class Client:
            def get(self, key):
                raise RuntimeError

        monkeypatch.setattr(wr, "_get_redis_client", lambda: Client())
        assert wr.get_graph_sync_stats() == {
            "successes": wr._graph_sync_successes,
            "failures": wr._graph_sync_failures,
        }

    def test_publish_graph_sync_no_redis_url_is_noop(self, monkeypatch):
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
        monkeypatch.delenv("REDIS_URL", raising=False)
        wr._publish_graph_sync("", None, "")

    def test_publish_graph_sync_disabled_by_default_is_noop(self, monkeypatch):
        monkeypatch.delenv("ENABLE_NEO4J_SYNC", raising=False)
        wr._publish_graph_sync("", None, "")

    @pytest.mark.parametrize("flag", ["", "false", "0", "no", "off"])
    def test_publish_graph_sync_falsey_env_values_are_noop(self, monkeypatch, flag):
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", flag)
        wr._publish_graph_sync("", None, "")

    def test_publish_graph_sync_max_queue_invalid_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("NEO4J_SYNC_MAX_QUEUE", "")
        assert wr._neo4j_sync_max_queue() == 100_000

    def test_publish_graph_sync_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("ENABLE_NEO4J_SYNC", raising=False)
        assert wr._neo4j_sync_enabled() is False

    def test_publish_graph_sync_disabled_with_false_flag(self, monkeypatch):
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", "false")
        assert wr._neo4j_sync_enabled() is False

    @pytest.mark.parametrize("flag", ["1", "true", "yes", "on"])
    def test_publish_graph_sync_truthy_values_enable(self, monkeypatch, flag):
        monkeypatch.setenv("ENABLE_NEO4J_SYNC", flag)
        assert wr._neo4j_sync_enabled() is True

    def test_publish_graph_sync_invalid_max_queue_falls_back(self, monkeypatch):
        monkeypatch.setenv("NEO4J_SYNC_MAX_QUEUE", "")
        assert wr._neo4j_sync_max_queue() == 100_000
