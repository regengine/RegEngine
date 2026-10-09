"""Regression tests for the init-db-constraints script.

Audit finding (low): ``services/graph/scripts/init_db_constraints.py`` used
``neo4j_client.driver.session()``, but ``Neo4jClient`` exposes no ``driver``
attribute (only the private ``_driver`` plus a ``session()`` helper), so the
script crashed with ``AttributeError`` before applying anything. It was also
written against the synchronous driver API while ``Neo4jClient`` is async.

These tests load the script and drive ``apply_constraints`` with a fake client
that mirrors the real ``Neo4jClient`` surface (``session()`` only, async), so
they fail on the old code (``AttributeError`` / not a coroutine function) and
pass on the fixed code.
"""

from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

SCRIPT_PATH = Path(__file__).parent.parent / "scripts" / "init_db_constraints.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("init_db_constraints_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeResult:
    """Minimal async result supporting ``async for`` over fake records."""

    def __init__(self, records):
        self._records = list(records)

    def __aiter__(self):
        async def _gen():
            for record in self._records:
                yield record

        return _gen()


class _FakeSession:
    """Async stand-in for a Neo4j session; records every query run."""

    def __init__(self):
        self.queries: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def run(self, query, **kwargs):
        self.queries.append(query)
        return _FakeResult([])


class _FakeClient:
    """Mirrors the real Neo4jClient surface: ``session()`` only, no driver."""

    def __init__(self):
        self.session_obj = _FakeSession()

    def session(self, **kwargs):
        return self.session_obj


async def test_apply_constraints_is_async_and_uses_client_session():
    module = _load_script()
    assert inspect.iscoroutinefunction(module.apply_constraints), (
        "apply_constraints must be async to match Neo4jClient's async API"
    )

    client = _FakeClient()
    assert not hasattr(client, "driver"), "fake must mirror Neo4jClient (no .driver)"
    await module.apply_constraints(client)

    ran = client.session_obj.queries
    assert any("CREATE CONSTRAINT" in q for q in ran), ran
    assert any("CREATE INDEX" in q for q in ran), ran
    assert any("SHOW CONSTRAINTS" in q for q in ran), ran
    assert any("SHOW INDEXES" in q for q in ran), ran


async def test_apply_constraints_runs_every_defined_statement():
    module = _load_script()
    client = _FakeClient()
    await module.apply_constraints(client)

    ran = client.session_obj.queries
    creates = [q for q in ran if "CREATE CONSTRAINT" in q or "CREATE INDEX" in q]
    # 9 constraints + 11 indexes defined in the script; each must be attempted.
    assert len(creates) == 20, [q.splitlines()[0] for q in creates]
