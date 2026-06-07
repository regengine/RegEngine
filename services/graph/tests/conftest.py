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


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help=("Run @pytest.mark.integration tests in services/graph/tests (default: skipped to keep local runs fast)."),
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-integration"):
        return
    # If the user explicitly selected integration tests via -m, respect that.
    markexpr = config.getoption("-m", default="") or ""
    if "integration" in markexpr:
        return
    skip_marker = pytest.mark.skip(
        reason=(
            "integration test (heavy testcontainers/docker dependency); pass --run-integration or -m integration to run"
        )
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)
