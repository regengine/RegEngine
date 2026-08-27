"""Graph-tree pytest hooks.

Gates ``@pytest.mark.integration`` tests in the graph tree behind an
opt-in flag so ``pytest services/graph/tests`` stays fast for local
iteration. The single existing integration test
(``test_neo4j_integration_testcontainers.py``) needs a live Neo4j and
dominates the suite runtime.

Activation:
- ``pytest services/graph/tests --run-integration`` — runs everything,
  including the Neo4j integration test.
- ``pytest services/graph/tests -m integration`` — runs only the
  integration tests (selection via marker, no gating applied).
- Default ``pytest services/graph/tests`` — auto-skips integration tests.

CI (corrected, #2877): this gate DOES apply to the ``Test graph`` matrix
leg — an earlier version of this docstring claimed CI was unaffected,
which was wrong and was half of the double guard that made the Neo4j
test run nowhere. The matrix leg still skips it (no ``--run-integration``,
and that leg has no Neo4j). It is run for real by the dedicated
``graph-neo4j-integration`` job, which provisions Neo4j, passes
``--run-integration``, and sets ``REGENGINE_REQUIRE_NEO4J=1`` so a
missing Neo4j fails instead of skipping.
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
