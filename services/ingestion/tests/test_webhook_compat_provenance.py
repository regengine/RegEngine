"""Receipt annotations preserve canonical identity; no database or network."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from copy import deepcopy
from types import SimpleNamespace

import pytest
from shared.canonical_event import normalize_webhook_event
from shared.canonical_persistence import CanonicalEventStore

from services.ingestion.tests import test_webhook_compat_replay_identity as replay

wc = replay.harness.wc
RUN_ID = "55555555-5555-4555-8555-555555555555"


def _receipt(original_format=None):
    receipt = wc.SourceFileReceipt(
        filename="misleading.json", raw_bytes=b"original source\x00\xff", content_type="application/json"
    )
    if original_format is not None:
        # Set the internal signal separately so RED exercises the adapter,
        # not a constructor error before the new dataclass field exists.
        receipt.original_format = original_format
    return receipt


def _ingest(monkeypatch, *, receipt=None, kdes=None, replay_existing=False):
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    session, _, captured = replay._install(
        monkeypatch, summary=replay.harness._compliant_summary(), replay=replay_existing
    )
    # Only the receipt's external database writes are substituted. The real
    # normalizer, writer serialization, and idempotent lookup remain in use.
    monkeypatch.setattr(wc, "_open_ingestion_run", lambda *args: RUN_ID)
    monkeypatch.setattr(wc, "_close_ingestion_run", lambda *args, **kwargs: None)
    captured["before"] = []
    captured["params"] = []

    def normalize(*args, **kwargs):
        canonical = normalize_webhook_event(*args, **kwargs)
        captured["before"].append(canonical.model_copy(deep=True))
        return canonical

    monkeypatch.setattr(sys.modules["shared.canonical_event"], "normalize_webhook_event", normalize)
    store_class = sys.modules["shared.canonical_persistence"].CanonicalEventStore
    original_persist = store_class.persist_event

    def persist(store, canonical):
        captured["params"].append(CanonicalEventStore(session, dual_write=False)._event_to_params(canonical))
        return original_persist(store, canonical)

    monkeypatch.setattr(store_class, "persist_event", persist)
    event = replay.harness._make_event()
    event.kdes = kdes or {}
    payload = replay.harness._make_payload([event], tenant_id=replay.TENANT_A)
    payload.source = "supplier_acme"
    captured["stored_before"] = deepcopy(captured["stored"][replay.TENANT_A].model_dump())
    response = asyncio.run(
        wc.ingest_events(
            payload=payload,
            principal_tenant_id=replay.TENANT_A,
            x_regengine_api_key="test-key",  # pragma: allowlist secret - synthetic test credential
            source_file=receipt,
        )
    )
    assert response.accepted == 1 and response.rejected == 0
    return session, captured


@pytest.mark.parametrize("original_format", ["csv", "edi", None], ids=["csv", "edi", "unknown"])
@pytest.mark.parametrize("kdes", [{}, {"ingest_source": "caller-kde-source"}], ids=["default-kde", "caller-kde"])
def test_receipt_metadata_preserves_historical_identity_inputs(monkeypatch, original_format, kdes):
    receipt = _receipt(original_format)
    _, captured = _ingest(monkeypatch, receipt=receipt, kdes=kdes)
    canonical = captured["canonicals"][0]
    before = captured["before"][0]
    provenance = json.loads(captured["params"][0]["provenance_metadata"])

    assert provenance == {
        **before.provenance_metadata.to_dict(),
        "original_format": original_format or "unknown",
        "source_file_name": "misleading.json",
        "source_file_hash": hashlib.sha256(b"original source\x00\xff").hexdigest(),
    }
    assert canonical.model_dump(exclude={"provenance_metadata"}) == before.model_dump(exclude={"provenance_metadata"})
    assert canonical.source_system.value == "webhook_api"
    assert canonical.raw_payload["source"] == "webhook_api"
    assert canonical.kdes["ingest_source"] == kdes.get("ingest_source", "webhook_api")
    assert (
        canonical.sha256_hash == before.sha256_hash == canonical.compute_sha256_hash() == before.compute_sha256_hash()
    )
    assert (
        canonical.idempotency_key
        == before.idempotency_key
        == canonical.compute_idempotency_key()
        == before.compute_idempotency_key()
    )


def test_no_receipt_leaves_json_provenance_unchanged(monkeypatch):
    _, captured = _ingest(monkeypatch)
    canonical = captured["canonicals"][0]
    assert canonical.model_dump() == captured["before"][0].model_dump()
    provenance = json.loads(captured["params"][0]["provenance_metadata"])
    assert provenance["original_format"] == "json"
    assert "source_file_name" not in provenance and "source_file_hash" not in provenance


def test_replay_keeps_stored_provenance_and_identity_unchanged(monkeypatch):
    receipt = _receipt("edi")
    _, captured = _ingest(monkeypatch, receipt=receipt, replay_existing=True)
    stored = captured["stored"][replay.TENANT_A]
    assert stored.model_dump() == captured["stored_before"]
    assert stored.provenance_metadata.original_format == "json"
    assert stored.provenance_metadata.source_file_hash is None
    assert stored.provenance_metadata.source_file_name is None
    assert captured["canonicals"][0].provenance_metadata.original_format == "edi"
    assert captured["canonicals"][0].idempotency_key == stored.idempotency_key
    # The real writer takes its existing-key branch without updating evidence;
    # existing rules reevaluation still uses the original persisted identity.
    assert not any("UPDATE" in sql or "INSERT" in sql for sql, _ in captured["sql"])
    assert captured["evaluations"][0][0]["event_id"] == str(stored.event_id)
    assert captured["reads"] == [(replay.TENANT_A, str(stored.event_id))]


@pytest.mark.parametrize("decoded_jsonb", [False, True], ids=["json-text", "decoded-jsonb"])
def test_provenance_readback_remains_tenant_qualified(monkeypatch, decoded_jsonb):
    receipt = _receipt("csv")
    _, captured = _ingest(monkeypatch, receipt=receipt)
    canonical = captured["canonicals"][0]
    params = {
        **captured["params"][0],
        "event_timestamp": canonical.event_timestamp,
        "created_at": canonical.created_at,
        "amended_at": None,
    }
    fields = (
        "event_id tenant_id source_system source_record_id event_type event_timestamp event_timezone "
        "product_reference lot_reference traceability_lot_code quantity unit_of_measure "
        "from_entity_reference to_entity_reference from_facility_reference to_facility_reference "
        "transport_reference kdes raw_payload normalized_payload provenance_metadata confidence_score "
        "status supersedes_event_id schema_version sha256_hash chain_hash created_at amended_at"
    ).split()
    if decoded_jsonb:
        for field in ("kdes", "raw_payload", "normalized_payload", "provenance_metadata"):
            params[field] = json.loads(params[field])

    def execute(statement, bindings):
        assert "WHERE tenant_id = :tid AND event_id = :eid" in str(statement)
        match = bindings == {"tid": replay.TENANT_A, "eid": str(canonical.event_id)}
        return SimpleNamespace(fetchone=lambda: tuple(params[field] for field in fields) if match else None)

    store = CanonicalEventStore(SimpleNamespace(execute=execute), dual_write=False)
    saved = store.get_event(replay.TENANT_A, str(canonical.event_id), include_raw_payload=True)
    assert saved["provenance_metadata"]["original_format"] == "csv"
    assert saved["provenance_metadata"]["source_file_name"] == receipt.filename
    assert saved["provenance_metadata"]["source_file_hash"] == hashlib.sha256(receipt.raw_bytes).hexdigest()
    assert saved["raw_payload"] == json.loads(json.dumps(canonical.raw_payload, default=str))
    assert saved["sha256_hash"] == canonical.sha256_hash
    assert store.get_event(replay.TENANT_B, str(canonical.event_id), include_raw_payload=True) is None
