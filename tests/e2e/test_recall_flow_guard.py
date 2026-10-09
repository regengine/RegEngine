"""Guard: the recall E2E fixture must skip, never pass via mock, when services are down.

Audit re-platform-2-tests (medium 4): the old ``http_client`` fixture in
``test_recall_flow.py`` yielded a ``MockClient`` returning canned 200s when
services were unreachable, so every trace assertion passed with nothing
running. This test drives the fixture with unreachable service URLs and
requires an explicit skip.
"""

import importlib.util
import inspect
from pathlib import Path

import pytest
from _pytest.outcomes import Skipped


def _load_recall_flow_module():
    """Load test_recall_flow.py by path so this guard survives renames of imports."""
    path = Path(__file__).with_name("test_recall_flow.py")
    spec = importlib.util.spec_from_file_location("test_recall_flow_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_http_client_skips_when_services_unreachable(monkeypatch):
    module = _load_recall_flow_module()
    # Point at a closed loopback port: connection refused, fast, no external I/O.
    monkeypatch.setattr(module, "INGESTION_URL", "http://127.0.0.1:9")
    monkeypatch.setattr(module, "GRAPH_URL", "http://127.0.0.1:9")
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.delenv(var, raising=False)

    fixture_fn = getattr(module.http_client, "__wrapped__", module.http_client)
    # The pre-fix fixture took an unused ``request`` arg; pass a dummy for
    # each declared parameter so the old code runs far enough to yield its mock.
    dummies = [object()] * len(inspect.signature(fixture_fn).parameters)
    try:
        result = next(fixture_fn(*dummies))
    except Skipped:
        return
    except Exception as exc:  # noqa: BLE001 - any other error is also wrong
        pytest.fail(f"fixture raised {exc!r} instead of skipping explicitly")
    if isinstance(result, module.MockClient):
        pytest.fail("fixture yielded MockClient with services down: assertions would pass vacuously")
    pytest.fail(f"fixture yielded {result!r} with services down instead of skipping")
