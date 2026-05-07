"""EPIC-I (#1316) regression: CorrelationIdMiddleware is wired into the
ingestion service and round-trips ``X-Correlation-ID`` correctly.

Before this PR, the middleware was imported (line 81 of services/ingestion/main.py)
but never registered via ``app.add_middleware(CorrelationIdMiddleware)``. The
import was effectively dead and ingestion routes silently lost trace context
emitted by upstream services / the gateway.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Set required env vars BEFORE any app module imports — mirrors test_boundaries.py
os.environ.setdefault("ADMIN_SERVICE_URL", "http://localhost:8000")
os.environ.setdefault("NLP_SERVICE_URL", "http://localhost:8002")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("S3_BUCKET", "test-ingestion-bucket")
os.environ.setdefault("OBJECT_STORAGE_ACCESS_KEY_ID", "test-key")
os.environ.setdefault("OBJECT_STORAGE_SECRET_ACCESS_KEY", "test-secret")
# These tests import ``services/ingestion/main.py`` directly. Force the auth
# env they expect instead of inheriting a root-suite production setting.
os.environ["AUTH_TEST_BYPASS_TOKEN"] = "test-bypass-token"
os.environ["REGENGINE_ENV"] = "test"
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ENABLE_DB_API_KEYS", "false")

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

_mock_kafka = MagicMock()
for _ck in [
    "confluent_kafka",
    "confluent_kafka.admin",
    "confluent_kafka.schema_registry",
    "confluent_kafka.schema_registry.avro",
    "confluent_kafka.serialization",
]:
    sys.modules.setdefault(_ck, _mock_kafka)


def _client():
    """Build a TestClient against the real ingestion FastAPI app.

    Imported lazily inside the helper so the env-var setup above is in place
    before settings are loaded.
    """
    from fastapi.testclient import TestClient
    return TestClient(_load_ingestion_app())


def _load_ingestion_app():
    """Import ``main.app`` under the deterministic test auth env.

    Root-suite order can mutate process env after this module is imported, so
    we restamp the auth/test variables immediately before importing
    ``services/ingestion/main.py`` and evict any cached ``main`` module.
    """
    os.environ["AUTH_TEST_BYPASS_TOKEN"] = "test-bypass-token"
    os.environ["REGENGINE_ENV"] = "test"
    sys.modules.pop("main", None)
    from main import app  # type: ignore[import-not-found]

    return app


def test_correlation_id_middleware_is_registered_in_app():
    """CorrelationIdMiddleware must appear in the app's middleware stack.

    Guards against the regression where the import existed but the
    ``app.add_middleware(CorrelationIdMiddleware)`` call was missing.
    """
    from shared.observability.correlation import CorrelationIdMiddleware
    app = _load_ingestion_app()

    middleware_classes = [m.cls for m in app.user_middleware]
    assert CorrelationIdMiddleware in middleware_classes, (
        f"CorrelationIdMiddleware must be wired into the ingestion app. "
        f"Found: {[c.__name__ for c in middleware_classes]}"
    )


def test_correlation_id_round_trips_supplied_header():
    """When the request carries X-Correlation-ID, the response echoes it back."""
    client = _client()
    supplied = "test-correlation-id-2151"
    response = client.get("/healthz", headers={"X-Correlation-ID": supplied})
    # /healthz exists on the ingestion app; even if it returns non-200,
    # middleware still echoes the header on the way out.
    assert response.headers.get("X-Correlation-ID") == supplied, (
        f"Expected echoed X-Correlation-ID={supplied!r}, got "
        f"{response.headers.get('X-Correlation-ID')!r} (status {response.status_code})"
    )


def test_correlation_id_minted_when_absent():
    """When the request omits X-Correlation-ID, the middleware mints one."""
    client = _client()
    response = client.get("/healthz")
    minted = response.headers.get("X-Correlation-ID")
    assert minted is not None and len(minted) > 0, (
        "Middleware must mint a fresh correlation id when the request omits one"
    )
    # 36-char UUID4 is the canonical shape from generate_correlation_id().
    assert len(minted) == 36, f"Expected UUID4-length correlation id, got len={len(minted)}"
