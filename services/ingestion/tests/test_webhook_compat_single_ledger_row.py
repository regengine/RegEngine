"""One accepted event writes one hash-chain row, shared by both stores.

``ingest_events`` (CSV, EDI, supplier portal, Sensitech) stores each event
twice: a legacy ``fsma.cte_events`` row and a canonical
``fsma.traceability_events`` row. The canonical write used to append its own
``fsma.hash_chain`` row under a second id, so ``/api/v1/webhooks/chain/verify``
reported one orphan per accepted event.

The real-database proof is
``tests/shared/test_chain_verify_dual_write_live.py``. These tests pin the
three things that make it hold, without a database.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_compat as webhook_compat  # noqa: E402
from app.webhook_models import IngestEvent, WebhookCTEType, WebhookPayload  # noqa: E402
from shared.canonical_persistence import CanonicalEventStore  # noqa: E402
from shared.canonical_persistence.models import CanonicalStoreResult  # noqa: E402
from shared.cte_persistence import CTEPersistence  # noqa: E402
from shared.cte_persistence.hashing import compute_canonical_event_hash  # noqa: E402
from shared.cte_persistence.models import StoreResult  # noqa: E402
from shared.exception_queue import ExceptionQueueService  # noqa: E402
from shared.rules_engine import RulesEngine  # noqa: E402

TENANT = "11111111-1111-1111-1111-111111111111"
STORED_CTE_ID = "22222222-2222-2222-2222-222222222222"
KDES = {
    "ship_from_location": "WH",
    "ship_to_location": "DC",
    "ship_date": "2026-10-01",
    "reference_document": "BOL1",
    "tlc_source_reference": "SRC",
    "tlc_source_gln": "0614141000012",
    "ftl_covered": True,
}


def _ingest(*, normalize_error: Exception | None = None):
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
    seen = {"store_kwargs": [], "canonical_stores": [], "persisted": []}

    def _store_event(self, **kwargs):
        seen["store_kwargs"].append(kwargs)
        return StoreResult(
            success=True,
            event_id=STORED_CTE_ID,
            sha256_hash="hash",
            chain_hash="chain",
            idempotent=False,
            errors=[],
        )

    def _canonical_store_init(self, session, dual_write=True, skip_chain_write=False, meter_usage=True):
        seen["canonical_stores"].append({"dual_write": dual_write, "skip_chain_write": skip_chain_write})

    def _persist(self, event):
        seen["persisted"].append(event)
        return CanonicalStoreResult(
            success=True,
            event_id=str(event.event_id),
            sha256_hash=event.sha256_hash,
            chain_hash="chain",
            idempotent=False,
            errors=[],
        )

    evaluate = MagicMock(return_value=MagicMock(compliant=True, critical_failures=[]))

    def _session():
        yield MagicMock()

    async def _run():
        return await webhook_compat.ingest_events(payload, principal_tenant_id=TENANT, x_regengine_api_key="key")

    patches = [
        patch.object(webhook_compat, "_get_db_session", _session),
        patch.object(webhook_compat, "_verify_api_key_sync", lambda **kwargs: None),
        patch.object(webhook_compat, "_check_rate_limit", lambda tenant: None),
        patch.object(webhook_compat, "record_outcomes", lambda *args: None),
        patch.object(webhook_compat, "_publish_graph_sync", lambda *args: None),
        patch.object(CTEPersistence, "__init__", lambda self, session: None),
        patch.object(CTEPersistence, "store_event", _store_event),
        patch.object(CanonicalEventStore, "__init__", _canonical_store_init),
        patch.object(CanonicalEventStore, "persist_event", _persist),
        patch.object(RulesEngine, "evaluate_event", evaluate),
        patch.object(ExceptionQueueService, "create_exceptions_from_evaluation", MagicMock()),
    ]
    if normalize_error is not None:
        patches.append(patch("shared.canonical_event.normalize_webhook_event", MagicMock(side_effect=normalize_error)))
    for item in patches:
        item.start()
    try:
        response = asyncio.run(_run())
    finally:
        for item in reversed(patches):
            item.stop()
    return response, seen, evaluate


def test_canonical_write_appends_no_second_chain_row():
    """The legacy write owns the ledger row; a second one is an orphan to chain verify."""
    response, seen, _ = _ingest()
    assert response.accepted == 1
    assert seen["canonical_stores"] == [{"dual_write": False, "skip_chain_write": True}]


def test_canonical_row_takes_the_legacy_event_id():
    """Chain verify joins the ledger row to both stores by this one id."""
    response, seen, evaluate = _ingest()
    (persisted,) = seen["persisted"]
    assert response.events[0].event_id == STORED_CTE_ID
    assert persisted.event_id == UUID(STORED_CTE_ID)
    assert persisted.normalized_payload["event_id"] == STORED_CTE_ID
    # Rule evidence is anchored on the same stored id.
    assert evaluate.call_args.args[0]["event_id"] == STORED_CTE_ID


def test_ledger_row_hashes_the_canonical_content():
    """Without this the canonical write refuses the row: its hash would not match.

    ``CanonicalEventStore(skip_chain_write=True)`` compares the ledger row's
    event hash to the canonical event's own hash and raises on a difference.
    """
    _, seen, _ = _ingest()
    projection = seen["store_kwargs"][0]["canonical_event"]
    (persisted,) = seen["persisted"]
    # What CTEPersistence.store_event writes to the ledger row for this
    # projection. It raises TypeError for anything but a canonical event.
    ledger_hash = compute_canonical_event_hash(STORED_CTE_ID, TENANT, projection)
    assert persisted.sha256_hash == ledger_hash
    assert persisted.sha256_hash == persisted.compute_sha256_hash()


def test_event_without_a_canonical_projection_is_stored_in_the_legacy_store_only():
    """Rules enforcement is off here, so a failed projection must not lose the event."""
    response, seen, evaluate = _ingest(normalize_error=ValueError("cannot normalize"))
    assert (response.accepted, response.rejected) == (1, 0)
    assert seen["store_kwargs"][0].get("canonical_event") is None
    assert seen["canonical_stores"] == []
    assert seen["persisted"] == []
    evaluate.assert_not_called()
