"""#2507 — the published ``regengine-verify`` SDK computed a per-record
hash that matched NONE of the production hashing algorithms, so
``verify_record_offline`` returned INVALID for every authentic record
(the ``sha256:`` prefix alone guaranteed inequality). It also had zero
test coverage.

These tests lock the SDK's ``compute_record_hash`` byte-for-byte to the
canonical production function
``shared.canonical_event.TraceabilityEvent.compute_sha256_hash`` — the
algorithm that produces the ``sha256_hash`` written to
``fsma.traceability_events`` and emitted in canonical exports — and
exercise the offline / file-parsing paths the SDK ships.

A separate guard asserts the frontend-served ``/proof`` bundle verifier
(``frontend/public/sdk/verify_chain.py``) still agrees with the
production Merkle scheme in ``services/shared/merkle_tree.py``, so a
change to one side cannot silently break the served verifier.

The repo root + ``services`` are on ``pythonpath`` (pyproject), so both
``regengine.verify_records`` and ``shared.*`` import cleanly.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

import regengine.verify_records as vc

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures: a real canonical event + its canonical-export record dict
# ---------------------------------------------------------------------------


def _build_event_and_record():
    """Return (server_hash, export_record) for one real canonical event.

    The record dict uses the same keys the canonical read path emits
    (``event_id``, ``event_type``, ``traceability_lot_code``,
    ``product_reference``, ``quantity``, ``unit_of_measure``,
    ``from_facility_reference``, ``to_facility_reference``,
    ``event_timestamp``, ``kdes``, ``sha256_hash``).
    """
    from shared.canonical_event import CTEType, IngestionSource, TraceabilityEvent

    event = TraceabilityEvent(
        event_id=UUID("11111111-1111-1111-1111-111111111111"),
        tenant_id=UUID("22222222-2222-2222-2222-222222222222"),
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.SHIPPING,
        event_timestamp=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        product_reference="Romaine Lettuce",
        traceability_lot_code="LOT-2026-001",
        quantity=5,
        unit_of_measure="CASE",
        from_facility_reference="gln-from",
        to_facility_reference="gln-to",
        kdes={"b": 2, "a": 1},
    )
    server_hash = event.compute_sha256_hash()
    record = {
        "event_id": str(event.event_id),
        "event_type": event.event_type.value,
        "traceability_lot_code": event.traceability_lot_code,
        "product_reference": event.product_reference,
        "quantity": float(event.quantity),
        "unit_of_measure": event.unit_of_measure,
        "from_facility_reference": event.from_facility_reference,
        "to_facility_reference": event.to_facility_reference,
        "event_timestamp": event.event_timestamp.isoformat(),
        "kdes": event.kdes,
        "sha256_hash": server_hash,
    }
    return server_hash, record


# ---------------------------------------------------------------------------
# Golden vector: SDK reproduces the canonical production hash byte-for-byte
# ---------------------------------------------------------------------------


class TestSdkMatchesProductionHash_Issue2507:
    def test_compute_record_hash_matches_canonical_function(self):
        server_hash, record = _build_event_and_record()
        assert vc.compute_record_hash(record) == server_hash

    def test_output_has_no_sha256_prefix(self):
        _, record = _build_event_and_record()
        out = vc.compute_record_hash(record)
        assert not out.startswith("sha256:")
        assert len(out) == 64  # bare hex SHA-256 digest

    def test_golden_vector_is_pinned(self):
        """Hard-coded digest so a silent change to the SDK canonical form
        (field order, delimiter, prefix) is caught even if the production
        function were edited in the same change."""
        _, record = _build_event_and_record()
        assert vc.compute_record_hash(record) == "50244d1adeccc16b689057c56428f082e0cb015401dc447b3b0485e28c6b6ca6"


# ---------------------------------------------------------------------------
# verify_record_offline: authentic passes, tampered fails
# ---------------------------------------------------------------------------


class TestVerifyRecordOffline_Issue2507:
    def test_authentic_record_is_valid(self):
        _, record = _build_event_and_record()
        result = vc.verify_record_offline(record)
        assert result.valid is True
        assert result.computed_hash == record["sha256_hash"]

    def test_tampered_field_is_invalid(self):
        _, record = _build_event_and_record()
        # Mutate a hashed field WITHOUT updating sha256_hash → must fail.
        record["quantity"] = 999.0
        result = vc.verify_record_offline(record)
        assert result.valid is False

    def test_tampered_stored_hash_is_invalid(self):
        _, record = _build_event_and_record()
        record["sha256_hash"] = "0" * 64
        result = vc.verify_record_offline(record)
        assert result.valid is False

    def test_accepts_bare_hash_alias(self):
        _, record = _build_event_and_record()
        record["hash"] = record.pop("sha256_hash")
        result = vc.verify_record_offline(record)
        assert result.valid is True


# ---------------------------------------------------------------------------
# verify_file: both JSON shapes (bare list and {"records": [...]})
# ---------------------------------------------------------------------------


class TestVerifyFileShapes_Issue2507:
    def test_bare_list_shape(self, tmp_path):
        _, record = _build_event_and_record()
        path = tmp_path / "records.json"
        path.write_text(json.dumps([record]))
        results = vc.verify_file(path)
        assert len(results) == 1
        assert results[0].valid is True

    def test_records_wrapper_shape(self, tmp_path):
        _, record = _build_event_and_record()
        path = tmp_path / "pack.json"
        path.write_text(json.dumps({"records": [record]}))
        results = vc.verify_file(path)
        assert len(results) == 1
        assert results[0].valid is True


# ---------------------------------------------------------------------------
# Drift guard: frontend bundle verifier vs production Merkle scheme
# ---------------------------------------------------------------------------


def _load_frontend_bundle_verifier():
    path = _REPO_ROOT / "frontend" / "public" / "sdk" / "verify_chain.py"
    spec = importlib.util.spec_from_file_location("_frontend_verify_bundle", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestFrontendMerkleNoDrift_Issue2507:
    """If the frontend-served bundle verifier's leaf/pair scheme or
    odd-node padding ever diverges from ``services/shared/merkle_tree``,
    a customer's bundle verification silently breaks. Fail loudly here."""

    def test_constants_match(self):
        fe = _load_frontend_bundle_verifier()
        # Domain-separation prefix and node separator must match production.
        from shared.merkle_tree import _hash_leaf, _hash_pair

        assert fe.LEAF_PREFIX == "leaf|"
        assert fe.NODE_SEPARATOR == "|"
        # The primitive functions must produce identical output.
        assert fe._hash_leaf("abc") == _hash_leaf("abc")
        assert fe._hash_pair("aa", "bb") == _hash_pair("aa", "bb")

    @pytest.mark.parametrize("n", [1, 2, 3, 4, 5, 8])
    def test_merkle_root_matches_production(self, n):
        fe = _load_frontend_bundle_verifier()
        from shared.merkle_tree import MerkleTree

        leaves = [f"{i:064x}" for i in range(n)]
        assert fe._merkle_root(leaves) == MerkleTree(leaves).root
