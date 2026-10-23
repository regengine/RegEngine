"""Data-free FDA export round-trip and thread dispatch guards."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.fda_export import (
    queries,  # noqa: E402
    router as fda_router,  # noqa: E402
)
from shared.cte_persistence import CTEPersistence  # noqa: E402


class _NoDatabaseSession:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("empty input must not query the database")


def test_query_events_by_tlcs_empty_input_no_db() -> None:
    persistence = CTEPersistence(_NoDatabaseSession())
    assert persistence.query_events_by_tlcs("", []) == []


@pytest.mark.parametrize(
    "handler_name",
    ["export_fda_spreadsheet", "export_all_events", "export_fda_spreadsheet_v2", "trace_transformation_graph"],
)
def test_blocking_handlers_are_sync_def(handler_name: str) -> None:
    route = next(route for route in fda_router.router.routes if route.endpoint.__name__ == handler_name)
    assert not inspect.iscoroutinefunction(route.endpoint)


def test_empty_full_export_uses_one_batch_call() -> None:
    class EmptyPersistence:
        batch_calls = 0

        def query_all_events(self, **_kwargs):
            return [], 0

        def query_events_by_tlcs(self, **kwargs):
            self.batch_calls += 1
            assert kwargs["tlcs"] == []
            return []

        def query_events_by_tlc(self, **_kwargs):
            raise AssertionError("per-lot query must not run")

    persistence = EmptyPersistence()
    assert queries.reconstruct_full_export_events(
        persistence, tenant_id="", start_date=None, end_date=None, event_type=None
    ) == ([], 0)
    assert persistence.batch_calls == 1
