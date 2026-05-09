"""Graph-tree pytest hooks.

Gates ``@pytest.mark.integration`` tests in the graph tree behind an
opt-in flag so ``pytest services/graph/tests`` stays fast for local
iteration. The single existing integration test
(``test_neo4j_integration_testcontainers.py``) spins up a Neo4j
testcontainer and dominates the suite runtime.

Activation:
- ``pytest services/graph/tests --run-integration`` — runs everything,
  including the testcontainers test.
- ``pytest services/graph/tests -m integration`` — runs only the
  integration tests (selection via marker, no gating applied).
- Default ``pytest services/graph/tests`` — auto-skips integration tests.

CI is unaffected: backend-ci.yml runs ``pytest tests/`` without
``-m "not integration"``, and the testcontainers test has its own
``_IN_CI`` skip guard inside the fixture, so CI behaviour is identical
to before this change.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _stub_audit_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    """No-op ``fsma_audit._persist_audit_entry`` for the graph test suite.

    The test conftest sets ``DATABASE_URL=sqlite:///:memory:`` so a SQLAlchemy
    engine is created, but no test creates the ``fsma.fsma_audit_trail``
    schema. Each ``log()`` call therefore hits the persist retry loop
    (1s + 2s = 3s per call) before failing silently. Across the graph tree
    that adds ~90s to test_fsma_audit.py alone and ~30s elsewhere.

    Persistence is covered by integration tests against a real DB; here we
    test the in-memory log mechanics, so stubbing persistence is correct.
    """
    # Patch every loaded module path that exposes ``_persist_audit_entry``
    # (fsma_audit can be imported as ``app.fsma_audit`` or
    # ``services.graph.app.fsma_audit`` depending on test).
    import sys
    for mod_name in (
        "app.fsma_audit",
        "services.graph.app.fsma_audit",
    ):
        if mod_name not in sys.modules:
            try:
                __import__(mod_name)
            except ImportError:
                continue
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "_persist_audit_entry"):
            monkeypatch.setattr(mod, "_persist_audit_entry", lambda entry: None)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help=(
            "Run @pytest.mark.integration tests in services/graph/tests "
            "(default: skipped to keep local runs fast)."
        ),
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-integration"):
        return
    # If the user explicitly selected integration tests via -m, respect that.
    markexpr = config.getoption("-m", default="") or ""
    if "integration" in markexpr:
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "integration test (heavy testcontainers/docker dependency); "
            "pass --run-integration or -m integration to run"
        )
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)
