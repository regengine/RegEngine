"""SEL-515: a trace that hits the query cap must say it is partial.

The capped queries fetch ``TRACE_ROW_LIMIT + 1`` rows. A result over the cap
returns the first ``TRACE_ROW_LIMIT`` with ``truncated=True`` (partial result,
not a 413), so a recall trace never looks complete when it is not. Exactly the
cap is complete and is not flagged.

Data-free: records carry only positional ids, no lot codes or sample records.
"""

from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma import tracer  # noqa: E402

# Generated per run: no hardcoded tenant id.
TENANT = str(uuid.uuid4())


class _Result:
    def __init__(self, records):
        self._records = records

    def __aiter__(self):
        self._it = iter(self._records)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Session:
    def __init__(self, path_records, association_rows=()):
        self._path_records = path_records
        self._association_rows = list(association_rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, **params):
        if "hop_count" in query:  # the capped traversal query
            return _Result(self._path_records)
        if "AS lot" in query:  # the capped association query
            return _Result(self._association_rows)
        return _Result([])


class _Client:
    def __init__(self, n):
        records = [
            {"labels": ["TraceEvent"], "props": {"event_id": str(i), "tenant_id": TENANT}, "hop_count": 1}
            for i in range(n)
        ]
        self._records = records
        self._association_rows = []

    def session(self):
        return _Session(self._records, self._association_rows)


def test_limit_constant_matches_every_capped_query():
    src = Path(tracer.__file__).read_text()
    assert set(re.findall(r"^\s*LIMIT (\d+)", src, re.M)) == {str(tracer.TRACE_ROW_LIMIT + 1)}


@pytest.mark.asyncio
@pytest.mark.parametrize("fn", ["trace_forward", "trace_backward"])
async def test_trace_over_cap_is_flagged_truncated(fn):
    result = await getattr(tracer, fn)(_Client(tracer.TRACE_ROW_LIMIT + 1), "0", tenant_id=TENANT)
    assert result.truncated is True
    assert result.truncation_limit == tracer.TRACE_ROW_LIMIT
    assert len(result.events) == tracer.TRACE_ROW_LIMIT  # partial data is still returned


@pytest.mark.asyncio
@pytest.mark.parametrize("fn", ["trace_forward", "trace_backward"])
async def test_trace_exactly_at_cap_is_complete(fn):
    result = await getattr(tracer, fn)(_Client(tracer.TRACE_ROW_LIMIT), "0", tenant_id=TENANT)
    assert result.truncated is False
    assert result.truncation_limit is None
    assert len(result.events) == tracer.TRACE_ROW_LIMIT


@pytest.mark.asyncio
@pytest.mark.parametrize("fn", ["trace_forward", "trace_backward"])
async def test_trace_under_cap_is_not_truncated(fn):
    result = await getattr(tracer, fn)(_Client(3), "0", tenant_id=TENANT)
    assert result.truncated is False
    assert result.truncation_limit is None


@pytest.mark.asyncio
@pytest.mark.parametrize("fn", ["trace_forward", "trace_backward"])
async def test_association_query_over_cap_alone_is_flagged_truncated(fn):
    """CodeRabbit r4370185652: the association cap must flag on its own."""
    client = _Client(3)
    # One lot so the association query runs; position numbers only.
    client._records.append({"labels": ["Lot"], "props": {"tlc": "0", "tenant_id": TENANT}, "hop_count": 1})
    client._association_rows = [
        {
            "lot": {"tlc": "0", "tenant_id": TENANT},
            "event": {"event_id": str(i % 3), "tenant_id": TENANT},
            "facility": None,
        }
        for i in range(tracer.TRACE_ROW_LIMIT + 1)
    ]
    result = await getattr(tracer, fn)(client, "0", tenant_id=TENANT)
    assert len(result.events) < tracer.TRACE_ROW_LIMIT
    assert result.truncated is True
    assert result.truncation_limit == tracer.TRACE_ROW_LIMIT
    assert len(result.trace_rows) == tracer.TRACE_ROW_LIMIT
