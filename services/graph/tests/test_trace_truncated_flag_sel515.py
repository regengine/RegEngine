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
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.graph.app.fsma import tracer  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"


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
    def __init__(self, path_records):
        self._path_records = path_records

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, **params):
        if "hop_count" in query:  # the capped traversal query
            return _Result(self._path_records)
        return _Result([])


class _Client:
    def __init__(self, n):
        records = [
            {"labels": ["TraceEvent"], "props": {"event_id": str(i), "tenant_id": TENANT}, "hop_count": 1}
            for i in range(n)
        ]
        self._records = records

    def session(self):
        return _Session(self._records)


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
