"""#2860: /export/all must refuse rather than deliver a truncated package.

The exporter built its bytes from ``query_events_by_tlcs`` (the
transformation-link expansion) but computed ``X-Truncated`` from
``query_all_events`` (the strictly smaller seed set). An export whose seed
count fit under the limit could therefore have its *content* cut at the limit
and still present as complete.

These tests drive ``reconstruct_full_export_events`` directly with a stub
persistence layer, so they need no database.
"""

import pytest

from services.ingestion.app.fda_export.queries import (
    ExportOverflowError,
    reconstruct_full_export_events,
)


class _StubPersistence:
    """Minimal stand-in for the CTE persistence layer.

    ``query_all_events`` mirrors the real contract: ``total`` is a true
    COUNT(*), independent of ``limit``. ``query_events_by_tlcs`` mirrors the
    real one too — it truncates at ``limit`` and returns a bare list with no
    count, which is precisely why overflow was undetectable.
    """

    def __init__(self, *, seed_total: int, expansion_size: int):
        self._seed_total = seed_total
        self._expansion_size = expansion_size
        self.expansion_limit_seen = None

    def query_all_events(self, *, tenant_id, start_date, end_date, event_type, limit):
        rows = [
            {"id": f"seed-{i}", "traceability_lot_code": f"TLC-{i}"}
            for i in range(min(self._seed_total, limit))
        ]
        return rows, self._seed_total

    def query_events_by_tlcs(self, *, tenant_id, tlcs, start_date, end_date, limit):
        self.expansion_limit_seen = limit
        return [
            {"id": f"evt-{i}", "traceability_lot_code": f"TLC-{i}"}
            for i in range(min(self._expansion_size, limit))
        ]


def _run(persistence, limit=10):
    return reconstruct_full_export_events(
        persistence,
        tenant_id="t1",
        start_date=None,
        end_date=None,
        event_type=None,
        limit=limit,
    )


def test_expansion_overflow_is_refused_even_when_seed_set_fits():
    """The regression: seed set fits, expansion does not."""
    p = _StubPersistence(seed_total=5, expansion_size=50)
    with pytest.raises(ExportOverflowError) as excinfo:
        _run(p, limit=10)
    assert excinfo.value.stage == "transformation-link expansion"
    assert excinfo.value.limit == 10


def test_expansion_is_queried_one_row_past_the_limit_as_a_sentinel():
    """Without the +1 the expansion cannot distinguish 'full' from 'overflowing'."""
    p = _StubPersistence(seed_total=5, expansion_size=5)
    _run(p, limit=10)
    assert p.expansion_limit_seen == 11


def test_seed_overflow_is_refused():
    p = _StubPersistence(seed_total=50, expansion_size=50)
    with pytest.raises(ExportOverflowError) as excinfo:
        _run(p, limit=10)
    assert excinfo.value.stage == "seed query"
    assert excinfo.value.available == 50


def test_export_that_fits_is_returned_intact():
    p = _StubPersistence(seed_total=3, expansion_size=7)
    events, total = _run(p, limit=10)
    assert len(events) == 7
    assert total == 3


def test_exactly_at_the_limit_is_not_an_overflow():
    """Boundary: an expansion of exactly ``limit`` rows is complete, not truncated."""
    p = _StubPersistence(seed_total=3, expansion_size=10)
    events, _total = _run(p, limit=10)
    assert len(events) == 10


def test_duplicate_events_across_seeds_are_deduplicated():
    class _DupPersistence(_StubPersistence):
        def query_events_by_tlcs(self, *, tenant_id, tlcs, start_date, end_date, limit):
            self.expansion_limit_seen = limit
            return [{"id": "same", "traceability_lot_code": "TLC-0"} for _ in range(3)]

    events, _total = _run(_DupPersistence(seed_total=2, expansion_size=3), limit=10)
    assert len(events) == 1
