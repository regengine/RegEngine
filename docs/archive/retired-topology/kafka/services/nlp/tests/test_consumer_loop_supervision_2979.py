"""#2979 — a poll error must not kill the consumer, and /health must not lie.

``KafkaConsumerCompat.poll()`` turns any message-level error into a raised
``KafkaError``. Neither consumer loop wrapped ``poll()`` in an ``except`` —
the inner try/except blocks only cover per-record processing — and
``run_consumer`` had a ``finally`` but no ``except``, so the exception
propagated out of the daemon thread and the thread died. Nothing supervised
or restarted it. Worse, the NLP consumer's own liveness probe returned
``200 {"status":"ok"}`` based solely on ``_shutdown_event``, so a dead
consumer kept reporting healthy and no orchestrator could tell that message
processing had stopped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


@pytest.fixture
def consumer_mod():
    from services.nlp.app import consumer as mod

    # ``reset_consumer_health`` does not exist before the fix; tolerate its
    # absence so the pre-fix run fails on BEHAVIOUR (dead loop, lying probe)
    # rather than on a missing helper.
    _reset = getattr(mod, "reset_consumer_health", lambda: None)
    mod._shutdown_event.clear()
    _reset()
    yield mod
    mod._shutdown_event.clear()
    _reset()


def _install(monkeypatch, mod, poll_side_effect):
    consumer = MagicMock(name="KafkaConsumer")
    consumer.poll.side_effect = poll_side_effect
    producer = MagicMock(name="KafkaProducer")
    producer.flush.return_value = None

    monkeypatch.setattr(mod, "KafkaConsumer", MagicMock(return_value=consumer))
    monkeypatch.setattr(mod, "KafkaProducer", MagicMock(return_value=producer))
    monkeypatch.setattr(mod, "_ensure_topic", MagicMock())
    monkeypatch.setattr(mod, "_start_health_server", MagicMock())
    return consumer, producer


def _probe():
    """Drive the real HTTP handler and return (status_code, body)."""
    from services.nlp.app.consumer.health import _HealthHandler

    handler = _HealthHandler.__new__(_HealthHandler)
    handler.path = "/health"
    captured: dict = {"headers": {}}

    class _Wfile:
        def write(self, payload):
            captured["body"] = payload

    handler.send_response = lambda code: captured.__setitem__("code", code)
    handler.send_header = lambda k, v: captured["headers"].__setitem__(k, v)
    handler.end_headers = lambda: None
    handler.wfile = _Wfile()

    handler.do_GET()
    return captured["code"], json.loads(captured["body"].decode("utf-8"))


class TestLoopSurvivesPollErrors:
    def test_transient_poll_error_does_not_kill_the_loop(self, monkeypatch, consumer_mod):
        from shared.kafka_compat import KafkaError

        calls = {"n": 0}

        def _poll(*_a, **_kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise KafkaError("UNKNOWN_TOPIC_OR_PART")
            consumer_mod._shutdown_event.set()
            return {}

        consumer, _producer = _install(monkeypatch, consumer_mod, _poll)
        monkeypatch.setattr(consumer_mod, "_wait_backoff", lambda seconds: None)

        consumer_mod.run_consumer()

        assert calls["n"] >= 2, (
            "one message-level poll error terminated the consumer loop "
            "permanently — no retry, no restart, no supervision (#2979)"
        )

    def test_repeated_poll_errors_back_off(self, monkeypatch, consumer_mod):
        from shared.kafka_compat import KafkaError

        delays: list[float] = []
        calls = {"n": 0}

        def _poll(*_a, **_kw):
            calls["n"] += 1
            if calls["n"] <= 3:
                raise KafkaError("broker down")
            consumer_mod._shutdown_event.set()
            return {}

        _install(monkeypatch, consumer_mod, _poll)
        monkeypatch.setattr(consumer_mod, "_wait_backoff", lambda seconds: delays.append(seconds))

        consumer_mod.run_consumer()

        assert len(delays) == 3, "each failed poll must back off before retrying"
        assert delays == sorted(delays) and delays[-1] > delays[0], (
            "backoff must grow so a broker outage is not a hot retry loop"
        )


class TestHealthTellsTheTruth:
    def test_probe_is_ok_while_the_loop_polls(self, monkeypatch, consumer_mod):
        """Probed from inside the loop, i.e. while it is genuinely alive."""
        seen: dict = {}
        calls = {"n": 0}

        def _poll(*_a, **_kw):
            calls["n"] += 1
            if calls["n"] == 1:
                return {}
            seen["probe"] = _probe()
            consumer_mod._shutdown_event.set()
            return {}

        _install(monkeypatch, consumer_mod, _poll)
        consumer_mod.run_consumer()

        code, body = seen["probe"]
        assert code == 200
        assert body["status"] == "ok"

    def test_probe_reports_unhealthy_when_the_loop_is_dead(self, monkeypatch, consumer_mod):
        """The headline #2979 lie: dead loop, /health still 200."""

        def _poll(*_a, **_kw):
            raise RuntimeError("fatal: consumer thread is gone")

        _install(monkeypatch, consumer_mod, _poll)

        with pytest.raises(RuntimeError):
            consumer_mod.run_consumer()

        code, body = _probe()
        assert code != 200, (
            "the liveness probe still returned 200 with the consumer loop "
            "dead — no orchestrator can detect that processing stopped "
            "(#2979)"
        )
        assert body["status"] != "ok"

    def test_probe_reports_unhealthy_while_polls_keep_failing(self, monkeypatch, consumer_mod):
        from shared.kafka_compat import KafkaError

        calls = {"n": 0}

        def _poll(*_a, **_kw):
            calls["n"] += 1
            if calls["n"] > 10:
                consumer_mod._shutdown_event.set()
                return {}
            raise KafkaError("UNKNOWN_TOPIC_OR_PART")

        _install(monkeypatch, consumer_mod, _poll)
        monkeypatch.setattr(consumer_mod, "_wait_backoff", lambda seconds: None)
        consumer_mod._shutdown_event.clear()

        # Run the loop, then probe before the shutdown flag is inspected.
        consumer_mod.run_consumer()
        consumer_mod._shutdown_event.clear()

        code, body = _probe()
        assert code != 200, (
            "a consumer that cannot poll must not report healthy (#2979)"
        )

    def test_startup_before_first_poll_is_still_healthy(self, consumer_mod):
        """The probe deliberately starts before the first poll — keep that."""
        code, body = _probe()
        assert code == 200
        assert body["status"] in {"ok", "starting"}

    def test_shutdown_still_reports_stopping(self, consumer_mod):
        consumer_mod._shutdown_event.set()
        code, body = _probe()
        assert code == 503
        assert body["status"] == "stopping"


class TestTopicCreationFailureIsSurfaced:
    def test_topic_creation_failure_appears_in_health(self, monkeypatch, consumer_mod):
        def _boom(*_a, **_kw):
            raise ConnectionError("broker unreachable")

        monkeypatch.setattr(consumer_mod, "KafkaAdminClient", _boom)
        consumer_mod._ensure_topic("nlp.needs_review")

        _code, body = _probe()
        assert "nlp.needs_review" in body.get("topic_creation_failures", []), (
            "a swallowed topic-creation failure surfaces later as the poll "
            "error that used to kill the loop — it must be visible (#2979)"
        )
