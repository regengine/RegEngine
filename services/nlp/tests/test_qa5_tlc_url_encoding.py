"""QA5: lot codes containing path separators must be URL-encoded.

Traceability lot codes can legally contain ``/`` and ``:`` (the NLP lot
pattern admits ``[A-Za-z0-9\\-_.:/]``). Interpolating a raw TLC into the
graph path with ``urllib.parse.quote`` defaults leaves ``/`` unencoded,
so ``LOT-1/A`` produced ``.../trace/forward/LOT-1/A`` (a wrong route,
surfaced downstream as a 404/502) instead of ``.../LOT-1%2FA``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.nlp.app.query_planner import parse_query
from services.nlp.app.routes import _execute_query_plan


def _request():
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [
            (b"x-regengine-api-key", b"rge_test.secret"),
        ],
    }
    return Request(scope)


@pytest.mark.parametrize(
    "query,intent",
    [
        ("trace forward lot LOT-1/A", "trace_forward"),
        ("trace back lot LOT-1/A", "trace_backward"),
        ("timeline for lot LOT-1/A", "lot_timeline"),
    ],
)
@pytest.mark.asyncio
async def test_tlc_with_slash_is_encoded_in_graph_endpoint(query, intent):
    plan = parse_query(query)
    assert plan.intent == intent
    assert plan.tlc == "LOT-1/A"

    seen = {}

    async def fake_graph_get(request, tenant_id, endpoint, params=None):
        seen["endpoint"] = endpoint
        return {"facilities": [], "downstream_lots": [], "source_lots": [], "events": []}

    with patch(
        "services.nlp.app.routes._graph_get",
        new=fake_graph_get,
    ):
        await _execute_query_plan(
            request=_request(),
            tenant_id="11111111-1111-1111-1111-111111111111",
            plan=plan,
        )

    assert seen["endpoint"].endswith("LOT-1%2FA"), seen["endpoint"]
    assert "/LOT-1/A" not in seen["endpoint"]
