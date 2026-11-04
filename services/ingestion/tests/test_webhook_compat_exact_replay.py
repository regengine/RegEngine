"""An exact replay of a stored event must not write new rule evidence.

``normalize_webhook_event`` mints a fresh event id, so evaluating a replay
anchored evidence and exception cases to an id that exists in no table.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_compat as webhook_compat  # noqa: E402
from app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload  # noqa: E402
from shared.canonical_persistence import CanonicalEventStore  # noqa: E402
from shared.canonical_persistence.models import CanonicalStoreResult  # noqa: E402
from shared.cte_persistence import CTEPersistence  # noqa: E402
from shared.cte_persistence.models import StoreResult  # noqa: E402
from shared.exception_queue import ExceptionQueueService  # noqa: E402
from shared.rules_engine import RulesEngine  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"
STORED_CTE_ID = "22222222-2222-2222-2222-222222222222"
STORED_CANONICAL_ID = "33333333-3333-3333-3333-333333333333"
KDES = {
    "ship_from_location": "WH",
    "ship_to_location": "DC",
    "ship_date": "2026-10-01",
    "reference_document": "BOL1",
    "tlc_source_reference": "SRC",
    "tlc_source_gln": "0614141000012",
    "ftl_covered": True,
}


def _ingest(*, cte_idempotent: bool, canonical_idempotent: bool):
    """Run the real ingest loop for one event with storage and rules stubbed."""
    payload = WebhookPayload(
        source="edi_inbound_945",
        tenant_id=TENANT,
        events=[
            IngestEvent(
                cte_type=WebhookCTEType.SHIPPING,
                traceability_lot_code="LOT-1",
                product_description="romaine",
                quantity=100,
                unit_of_measure="lbs",
                location_name="WH",
                timestamp="2026-10-01T12:00:00+00:00",
                kdes=dict(KDES),
            )
        ],
    )
    store_result = StoreResult(
        success=True,
        event_id=STORED_CTE_ID,
        sha256_hash="hash",
        chain_hash="chain",
        idempotent=cte_idempotent,
        errors=[],
    )

    def _persist(self, event):
        return CanonicalStoreResult(
            success=True,
            event_id=STORED_CANONICAL_ID if canonical_idempotent else str(event.event_id),
            sha256_hash="hash",
            chain_hash="chain",
            idempotent=canonical_idempotent,
            errors=[],
        )

    summary = MagicMock(compliant=False, critical_failures=[])
    evaluate = MagicMock(return_value=summary)
    create_cases = MagicMock()

    def _session():
        yield MagicMock()

    async def _run():
        return await webhook_compat.ingest_events(payload, principal_tenant_id=TENANT, x_regengine_api_key="key")

    with (
        patch.object(webhook_compat, "_get_db_session", _session),
        patch.object(webhook_compat, "_verify_api_key_sync", lambda **kwargs: None),
        patch.object(webhook_compat, "_check_rate_limit", lambda tenant: None),
        patch.object(webhook_compat, "record_outcomes", lambda *args: None),
        patch.object(webhook_compat, "_publish_graph_sync", lambda *args: None),
        patch.object(CTEPersistence, "__init__", lambda self, session: None),
        patch.object(CTEPersistence, "store_event", lambda self, **kwargs: store_result),
        patch.object(CanonicalEventStore, "persist_event", _persist),
        patch.object(RulesEngine, "evaluate_event", evaluate),
        patch.object(ExceptionQueueService, "create_exceptions_from_evaluation", create_cases),
    ):
        response = asyncio.run(_run())
    return response, evaluate, create_cases


def test_exact_replay_writes_no_rule_evidence_and_stays_accepted():
    response, evaluate, create_cases = _ingest(cte_idempotent=True, canonical_idempotent=True)
    assert (response.accepted, response.rejected) == (1, 0)
    assert response.events[0].event_id == STORED_CTE_ID
    evaluate.assert_not_called()
    create_cases.assert_not_called()


def test_new_event_is_still_evaluated():
    response, evaluate, create_cases = _ingest(cte_idempotent=False, canonical_idempotent=False)
    assert response.accepted == 1
    evaluate.assert_called_once()
    create_cases.assert_called_once()


def test_replay_that_backfills_the_canonical_row_is_evaluated():
    """The canonical write is best-effort, so the first pass may never have evaluated."""
    _, evaluate, _ = _ingest(cte_idempotent=True, canonical_idempotent=False)
    evaluate.assert_called_once()


def test_evaluation_anchors_to_the_persisted_canonical_row():
    _, evaluate, _ = _ingest(cte_idempotent=False, canonical_idempotent=True)
    evaluate.assert_called_once()
    assert evaluate.call_args.args[0]["event_id"] == STORED_CANONICAL_ID
