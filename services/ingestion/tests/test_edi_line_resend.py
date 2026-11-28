"""A resent EDI document must not store a line twice or lose a correction (ADR-007).

The three cases PR 3811 reproduced, driven through the real ``/document``
route and the real ``ingest_events``:

A. a line is removed and the document is sent again,
B. a quantity is corrected,
C. the same document arrives under a new ISA13.

What is real: the parser, extractors, FSMA validation, the KDE gate, event
normalization, line identity, and the idempotency key formulas of both stores.
What is faked: the two stores keep rows in memory and deduplicate on those real
keys, and the registry is a dict with the same contract as the table. The live
table is covered by ``test_edi_line_identity_pg.py``. The ingestion run that
retains each uploaded document is a list entry, undone by the same rollback.

The ISA13 gates are off here. Under the same ISA13 that is the state after the
seven-day receipt has expired or for an envelope with no ISA13; under a new
ISA13 they never apply. The last test is the control: a document that cannot
name its lines keeps the old behaviour, and shows all three faults.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
from uuid import uuid4

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir.parent))

from shared.paths import ensure_shared_importable  # noqa: E402

ensure_shared_importable()
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.edi_ingestion.routes as edi_routes  # noqa: E402
import app.webhook_compat as webhook_compat  # noqa: E402
import shared.canonical_persistence as canonical_persistence  # noqa: E402
import shared.cte_persistence as cte_persistence  # noqa: E402
import shared.rules_engine as rules_engine  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.edi_ingestion import (  # noqa: E402
    dedup as dedup_mod,
    rejection_log,
    router as edi_router,
)
from app.edi_interchange import EDIInterchange  # noqa: E402
from app.edi_line_identity import EDILineRegistry, StoredLine  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from shared.cte_persistence import core as cte_core  # noqa: E402
from shared.cte_persistence.models import StoreResult  # noqa: E402
from tests.edi_documents import GTIN, TENANT, shipping_advice, two_shipping_advices  # noqa: E402

LINES = [("40", "LOT-A"), ("25", "LOT-B"), ("80", "LOT-C")]
NEW_ENVELOPE = {"isa13": "000000202", "gs06": "2", "st02": "0002"}
# No shipment id and no order number: the document cannot name its lines.
UNNAMED = {"header": "W06*N**20260310~", "references": "N9*BM*BOL-7001~"}


class _Stores:
    """Both event stores and the registry, with rollback."""

    def __init__(self) -> None:
        self.legacy: dict[str, dict[str, Any]] = {}
        self.canonical: dict[str, str] = {}
        self.registry: dict[str, tuple[str, str]] = {}
        # SHA-256 of each retained source document, one per ingestion run.
        self.runs: list[str] = []
        self.published: list[str] = []
        self.redis: dict[str, str] = {}

    def snapshot(self) -> tuple:
        return copy.deepcopy((self.legacy, self.canonical, self.registry, self.runs))

    def restore(self, saved: tuple) -> None:
        self.legacy, self.canonical, self.registry, self.runs = copy.deepcopy(saved)

    def quantities(self) -> list[tuple[str, float]]:
        return sorted((row["lot"], row["quantity"]) for row in self.legacy.values())

    def event_ids(self) -> dict[str, str]:
        return {row["lot"]: row["id"] for row in self.legacy.values()}


class _Savepoint:
    def __init__(self, stores: _Stores) -> None:
        self.stores = stores
        self.saved = stores.snapshot()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        self.stores.restore(self.saved)


class _Session:
    def __init__(self, stores: _Stores) -> None:
        self.stores = stores
        self.saved = stores.snapshot()

    def begin_nested(self) -> _Savepoint:
        return _Savepoint(self.stores)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        self.stores.restore(self.saved)


class _Redis:
    """SET NX and the two owner-checked scripts, as dedup uses them."""

    def __init__(self, keys: dict[str, str]) -> None:
        self.keys = keys

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.keys:
            return None
        self.keys[key] = value
        return True

    def get(self, key):
        return self.keys.get(key)

    def eval(self, script, numkeys, key, *args):
        if self.keys.get(key) != args[0]:
            return 0
        if script == dedup_mod._RELEASE_IF_OWNER_LUA:
            del self.keys[key]
        else:
            self.keys[key] = args[1]
        return 1


@pytest.fixture()
def stores(monkeypatch: pytest.MonkeyPatch) -> _Stores:
    state = _Stores()

    class _Legacy:
        """``fsma.cte_events``: one row per legacy idempotency key."""

        def __init__(self, session: Any) -> None:
            self.session = session

        def store_event(self, **kwargs: Any) -> StoreResult:
            timestamp = cte_core._parse_timestamp(kwargs["event_timestamp"], field="event_timestamp").isoformat()
            key = cte_core.compute_idempotency_key(
                kwargs["event_type"],
                kwargs["traceability_lot_code"],
                timestamp,
                kwargs["source"],
                kwargs["kdes"],
                location_gln=kwargs["location_gln"],
                location_name=kwargs["location_name"],
            )
            row = state.legacy.get(key)
            if row is None:
                row = {"id": str(uuid4()), "lot": kwargs["traceability_lot_code"], "quantity": kwargs["quantity"]}
                state.legacy[key] = row
                idempotent = False
            else:
                idempotent = True
            return StoreResult(
                success=True, event_id=row["id"], sha256_hash="h" * 64, chain_hash="c" * 64, idempotent=idempotent
            )

    class _Canonical:
        """``fsma.traceability_events``: one row per canonical idempotency key."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def persist_event(self, event: Any) -> SimpleNamespace:
            idempotent = event.idempotency_key in state.canonical
            state.canonical.setdefault(event.idempotency_key, str(event.event_id))
            return SimpleNamespace(idempotent=idempotent)

    class _Registry(EDILineRegistry):
        """``fsma.edi_line_identities``, joined to the events that still exist."""

        def lookup(self, session, tenant_id, lines):
            live = {row["id"] for row in state.legacy.values()}
            return {
                line.identity_key: StoredLine(*state.registry[line.identity_key], "h" * 64, "c" * 64)
                for line in lines
                if line is not None
                and line.identity_key in state.registry
                and state.registry[line.identity_key][1] in live
            }

        def record(self, session, tenant_id, line, event_id):
            state.registry[line.identity_key] = (line.content_digest, event_id)

    class _NoRules:
        def __init__(self, session: Any) -> None:
            return None

        def evaluate_event(self, *args: Any, **kwargs: Any) -> None:
            return None

    def _sessions() -> Iterator[_Session]:
        yield _Session(state)

    def _open_run(session: Any, tenant_id: str, source: str, receipt: Any) -> str:
        """``fsma.ingestion_runs`` and ``fsma.manifest_blobs``: the document as uploaded."""
        state.runs.append(receipt.sha256)
        return str(uuid4())

    monkeypatch.setattr(webhook_compat, "_open_ingestion_run", _open_run)
    monkeypatch.setattr(webhook_compat, "_close_ingestion_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(webhook_compat, "_check_rate_limit", lambda tenant_id: None)
    monkeypatch.setattr(webhook_compat, "_verify_api_key_sync", lambda **kwargs: None)
    monkeypatch.setattr(webhook_compat, "_get_db_session", _sessions)
    monkeypatch.setattr(webhook_compat, "record_outcomes", lambda *args: None)
    monkeypatch.setattr(webhook_compat, "_publish_graph_sync", lambda event_id, *args: state.published.append(event_id))
    monkeypatch.setattr(cte_persistence, "CTEPersistence", _Legacy)
    monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _Canonical)
    monkeypatch.setattr(rules_engine, "RulesEngine", _NoRules)
    monkeypatch.setattr(edi_routes, "EDILineRegistry", _Registry)
    # The Postgres receipt is off: expired, or the envelope has no ISA13.
    monkeypatch.setattr(EDIInterchange, "reserve", lambda self, session, tenant_id: None)
    monkeypatch.setattr(EDIInterchange, "record_stored", lambda self, session, tenant_id: None)
    monkeypatch.setattr(dedup_mod, "_redis_client", lambda: None)
    monkeypatch.setenv("RULES_ENGINE_ENFORCE", "off")
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    rejection_log._edi_rejection_store.pop(TENANT, None)
    return state


@pytest.fixture()
def post(stores: _Stores):
    app = FastAPI()
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", tenant_id=TENANT, scopes=["*"], auth_mode="test"
    )

    def _post(raw: bytes):
        with TestClient(app) as client:
            return client.post(
                "/api/v1/ingest/edi/document",
                data={
                    "traceability_lot_code": f"{GTIN}-LOT001",
                    "tenant_id": TENANT,
                    "tlc_source_reference": "0061414100001",
                },
                files={"file": ("advice.edi", raw, "application/edi-x12")},
            )

    return _post


def _stored(post, stores: _Stores, **document) -> dict[str, str]:
    """Store the three-line document and return its event id per lot."""
    first = post(shipping_advice(LINES, **document))
    assert first.status_code == 201, first.text
    assert first.json()["ingestion_result"]["accepted"] == 3
    assert stores.quantities() == [(f"{GTIN}-LOT-A", 40.0), (f"{GTIN}-LOT-B", 25.0), (f"{GTIN}-LOT-C", 80.0)]
    return stores.event_ids()


ENVELOPES = pytest.mark.parametrize("envelope", [{}, NEW_ENVELOPE], ids=["same-isa13", "new-isa13"])


@ENVELOPES
def test_case_a_removing_a_line_does_not_store_the_others_again(post, stores: _Stores, envelope) -> None:
    ids = _stored(post, stores)

    resend = post(shipping_advice([LINES[0], LINES[2]], **envelope))

    assert resend.status_code == 201, resend.text
    result = resend.json()["ingestion_result"]
    assert (result["accepted"], result["rejected"]) == (2, 0)
    # LOT-C moved from line 3 to line 2. It is reported as the stored event.
    assert [event["event_id"] for event in result["events"]] == [ids[f"{GTIN}-LOT-A"], ids[f"{GTIN}-LOT-C"]]
    assert len(stores.legacy) == 3
    assert len(stores.canonical) == 3
    # The removed line is not retracted.
    assert (f"{GTIN}-LOT-B", 25.0) in stores.quantities()


@ENVELOPES
def test_case_b_a_corrected_quantity_is_refused_not_dropped(post, stores: _Stores, envelope) -> None:
    ids = _stored(post, stores)
    before = stores.snapshot()

    corrected = post(shipping_advice([LINES[0], ("30", "LOT-B"), LINES[2]], **envelope))

    assert corrected.status_code == 409, corrected.text
    detail = corrected.json()["detail"]
    assert detail["error"] == "edi_line_content_conflict"
    assert detail["needs_review"] is True
    assert detail["conflicts"] == [
        {"line": 2, "traceability_lot_code": f"{GTIN}-LOT-B", "stored_event_id": ids[f"{GTIN}-LOT-B"]}
    ]
    # The stored value stands and nothing else was written.
    assert stores.snapshot() == before
    assert (f"{GTIN}-LOT-B", 25.0) in stores.quantities()
    # The rejection log holds the correction, with the value it proposed.
    record = rejection_log._edi_rejection_store[TENANT][detail["rejection_id"]]
    assert record["reason"] == "edi_line_content_conflict"
    assert record["needs_review"] is True
    (error,) = record["errors"]
    assert error["loc"] == ["line", 2]
    assert error["input"]["traceability_lot_code"] == f"{GTIN}-LOT-B"
    assert error["input"]["quantity"] == 30.0
    # The response names the stored event and carries none of its values.
    assert set(detail) == {"error", "message", "needs_review", "conflicts", "rejection_id"}


def test_a_conflict_in_a_later_transaction_set_records_that_line(post, stores: _Stores) -> None:
    """The rejection's ``extracted`` snapshot is the first set only.

    A refused line in the second set is recorded itself, with its own set's
    control number, shipment and proposed quantity.
    """
    first = post(two_shipping_advices([("40", "LOT-A")], [("25", "LOT-B")]))
    assert first.status_code == 201, first.text
    assert first.json()["ingestion_result"]["accepted"] == 2

    corrected = post(two_shipping_advices([("40", "LOT-A")], [("30", "LOT-B")], isa13="000000202", gs06="2"))

    assert corrected.status_code == 409, corrected.text
    detail = corrected.json()["detail"]
    assert [conflict["line"] for conflict in detail["conflicts"]] == [2]
    record = rejection_log._edi_rejection_store[TENANT][detail["rejection_id"]]
    assert record["extracted"]["shipment_id"] == "SHIP-9001"
    (error,) = record["errors"]
    proposed = error["input"]
    assert (proposed["traceability_lot_code"], proposed["quantity"]) == (f"{GTIN}-LOT-B", 30.0)
    assert proposed["kdes"]["shipment_id"] == "SHIP-9002"
    assert proposed["kdes"]["edi_control_number"] == "0002"
    assert proposed["kdes"]["edi_isa13"] == "000000202"
    assert (f"{GTIN}-LOT-B", 25.0) in stores.quantities()


@ENVELOPES
def test_case_c_the_same_document_again_stores_nothing(post, stores: _Stores, envelope) -> None:
    ids = _stored(post, stores)
    published = list(stores.published)

    resend = post(shipping_advice(LINES, **envelope))

    assert resend.status_code == 201, resend.text
    result = resend.json()["ingestion_result"]
    assert (result["accepted"], result["rejected"]) == (3, 0)
    assert [event["event_id"] for event in result["events"]] == [ids[f"{GTIN}-{lot}"] for _, lot in LINES]
    assert len(stores.legacy) == 3
    assert len(stores.canonical) == 3
    # A registered line is not sent to graph sync again.
    assert stores.published == published


def test_a_new_line_in_a_resend_is_stored_beside_the_known_ones(post, stores: _Stores) -> None:
    _stored(post, stores)

    resend = post(shipping_advice([*LINES, ("12", "LOT-D")], **NEW_ENVELOPE))

    assert resend.status_code == 201, resend.text
    assert resend.json()["ingestion_result"]["accepted"] == 4
    assert len(stores.legacy) == 4
    assert (f"{GTIN}-LOT-D", 12.0) in stores.quantities()


def test_two_identical_lines_both_persist_and_both_replay(post, stores: _Stores) -> None:
    twins = [("40", "LOT-A"), ("40", "LOT-A")]

    first = post(shipping_advice(twins))
    assert first.status_code == 201, first.text
    assert first.json()["ingestion_result"]["accepted"] == 2
    assert len(stores.legacy) == 2

    resend = post(shipping_advice(twins, **NEW_ENVELOPE))
    assert resend.status_code == 201, resend.text
    assert len(stores.legacy) == 2
    first_ids = [event["event_id"] for event in first.json()["ingestion_result"]["events"]]
    assert [event["event_id"] for event in resend.json()["ingestion_result"]["events"]] == first_ids
    assert first_ids[0] != first_ids[1]


def test_a_refused_correction_stores_none_of_the_interchange(post, stores: _Stores) -> None:
    _stored(post, stores)

    mixed = post(shipping_advice([("30", "LOT-B"), ("12", "LOT-D")], **NEW_ENVELOPE))

    assert mixed.status_code == 409, mixed.text
    assert len(stores.legacy) == 3
    assert not any(lot.endswith("LOT-D") for lot, _ in stores.quantities())
    # The refused document is not retained either: only the first upload has a run.
    assert len(stores.runs) == 1


def test_a_refused_correction_frees_its_isa13(post, stores: _Stores, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dedup_mod, "_redis_client", lambda: _Redis(stores.redis))
    _stored(post, stores)
    assert [value.split(":")[0] for value in stores.redis.values()] == ["stored"]

    refused = post(shipping_advice([LINES[0], ("30", "LOT-B"), LINES[2]], **NEW_ENVELOPE))

    assert refused.status_code == 409, refused.text
    # Only the first interchange holds a claim, so the partner can use this ISA13 again.
    assert len(stores.redis) == 1


def test_a_refusal_the_log_cannot_record_sends_no_rejection_id(
    post, stores: _Stores, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``rejection_id`` is returned only once the rejection log took the record.

    If the recorder fails, its error replaces the 409. Nothing is stored and
    the ISA13 is free, so the same document sent again is refused with a record.
    """
    monkeypatch.setattr(dedup_mod, "_redis_client", lambda: _Redis(stores.redis))
    _stored(post, stores)
    before = stores.snapshot()
    corrected = shipping_advice([LINES[0], ("30", "LOT-B"), LINES[2]], **NEW_ENVELOPE)

    def _unavailable(**kwargs: Any) -> None:
        raise HTTPException(status_code=503, detail="EDI rejection could not be recorded.")

    with monkeypatch.context() as patch:
        patch.setattr(edi_routes, "_record_edi_rejection", _unavailable)
        unrecorded = post(corrected)

    assert unrecorded.status_code == 503, unrecorded.text
    # The recorder's own error: no conflicts and no id for a record that does not exist.
    assert unrecorded.json() == {"detail": "EDI rejection could not be recorded."}
    assert stores.snapshot() == before
    assert len(stores.redis) == 1

    retried = post(corrected)

    assert retried.status_code == 409, retried.text
    assert retried.json()["detail"]["rejection_id"] in rejection_log._edi_rejection_store[TENANT]
    assert len(stores.redis) == 1


def test_a_purged_event_is_stored_again(post, stores: _Stores) -> None:
    _stored(post, stores)
    purged = next(key for key, row in stores.legacy.items() if row["lot"].endswith("LOT-B"))
    del stores.legacy[purged]

    resend = post(shipping_advice(LINES, **NEW_ENVELOPE))

    assert resend.status_code == 201, resend.text
    assert stores.quantities() == [(f"{GTIN}-LOT-A", 40.0), (f"{GTIN}-LOT-B", 25.0), (f"{GTIN}-LOT-C", 80.0)]


def test_control_a_document_that_cannot_name_its_lines_keeps_all_three_faults(post, stores: _Stores) -> None:
    """Without a shipment or order number there is no identity (ADR-007).

    These lines fall back to the event keys alone. This pins that limit, and
    shows the stores here deduplicate on the real keys: with identity off, the
    faults the tests above rule out all come back.
    """
    first = post(shipping_advice(LINES, **UNNAMED))
    assert first.status_code == 201, first.text
    assert len(stores.legacy) == 3
    assert stores.registry == {}

    # B: the keys leave out quantity, so the corrected value is dropped with a clean 201.
    corrected = post(shipping_advice([LINES[0], ("30", "LOT-B"), LINES[2]], **UNNAMED))
    assert corrected.status_code == 201, corrected.text
    assert corrected.json()["ingestion_result"]["accepted"] == 3
    assert (f"{GTIN}-LOT-B", 25.0) in stores.quantities()
    assert len(stores.legacy) == 3

    # A: LOT-C becomes line 2, gets a new key, and is stored a second time.
    shorter = post(shipping_advice([LINES[0], LINES[2]], **UNNAMED))
    assert shorter.status_code == 201, shorter.text
    assert stores.quantities().count((f"{GTIN}-LOT-C", 80.0)) == 2

    # C: a new ISA13 changes every key, so every line is stored again.
    again = post(shipping_advice(LINES, **UNNAMED, **NEW_ENVELOPE))
    assert again.status_code == 201, again.text
    assert len(stores.legacy) == 4 + 3
