"""Regression tests for #1216 — graph consumer inbound schema validation.

Before the fix, ``services/graph/app/consumer.py`` called
``GraphEvent.parse_obj()`` / ``extraction.dict()`` on whatever
dict the deserializer produced. Bad payloads crashed the record
processor, burned the retry budget on deterministic failures, and
eventually hit DLQ with uninformative ``AttributeError: 'NoneType'
object has no attribute ...`` entries.

The fix loads a Draft7Validator from
``data-schemas/events/graph.update.schema.json`` at module scope and
rejects malformed payloads with a structured ``schema_invalid`` DLQ
reason *before* any parser is given a chance to crash.

These tests exercise the validator in isolation so they don't need
Kafka, Schema Registry, or Neo4j.
"""

from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


class TestInboundSchemaLoaded:
    """The module-level validator must actually load — if the schema
    file is missing or malformed we fall back to fail-open (None),
    which silently reopens the bug. Pin both the happy path and the
    contract that the schema file ships with the repo."""

    def test_inbound_validator_is_loaded(self) -> None:
        from jsonschema import Draft7Validator

        from services.graph.app import consumer

        assert consumer._INBOUND_VALIDATOR is not None, (
            "Graph consumer must load its Draft7Validator at import "
            "time; if this is None a malformed payload will silently "
            "reach GraphEvent.parse_obj() and regress #1216."
        )
        assert isinstance(consumer._INBOUND_VALIDATOR, Draft7Validator)

    def test_schema_file_exists_in_repo(self) -> None:
        schema_path = (
            _repo_root / "data-schemas" / "events" / "graph.update.schema.json"
        )
        assert schema_path.exists(), (
            "graph.update schema must be checked into "
            "data-schemas/events/ — the consumer looks it up by path."
        )


class TestValidateInboundEventHappyPath:
    """A well-formed GraphEvent-shape payload must validate cleanly."""

    def test_valid_graph_event_payload_passes(self) -> None:
        from services.graph.app.consumer import _validate_inbound_event

        payload = {
            "event_id": "evt-001",
            "event_type": "approve_provision",
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "doc_hash": "abc123",
            "document_id": "doc-001",
            "text_clean": "Some cleaned provision text.",
            "extraction": {
                "subject": "food facilities",
                "action": "must maintain",
                "obligation_type": "MUST",
                "confidence_score": 0.92,
                "source_text": "Food facilities must maintain records.",
                "source_offset": 0,
            },
            "provenance": {"source_url": "https://example.com/a.pdf"},
            "status": "APPROVED",
        }

        assert _validate_inbound_event(payload) is None, (
            "A canonical GraphEvent payload must pass validation; "
            "otherwise legitimate producer traffic would be DLQ'd."
        )

    def test_valid_legacy_payload_with_entities_passes(self) -> None:
        """Legacy-format messages (doc_id + entities list, no extraction)
        must still pass — the consumer supports both formats and we do
        not want the schema fix to break existing producers."""
        from services.graph.app.consumer import _validate_inbound_event

        payload = {
            "doc_id": "legacy-doc-1",
            "source_url": "https://example.com/legacy.pdf",
            "entities": [
                {"type": "ORG", "text": "ACME Corp", "start": 0, "end": 9},
            ],
            "tenant_id": "00000000-0000-0000-0000-000000000001",
        }

        assert _validate_inbound_event(payload) is None


class TestValidateInboundEventRejectsMalformed:
    """Malformed messages must return a descriptive error string so the
    DLQ entry carries a real root cause instead of an opaque
    ``AttributeError``."""

    def test_missing_both_doc_id_fields_is_rejected(self) -> None:
        """The ``anyOf`` clause requires ``document_id`` OR ``doc_id``.
        A payload with neither is the canonical producer-bug case from
        the #1216 write-up."""
        from services.graph.app.consumer import _validate_inbound_event

        payload = {
            "event_type": "approve_provision",
            "text_clean": "some text",
        }

        err = _validate_inbound_event(payload)
        assert err is not None, (
            "A payload missing both document_id and doc_id must be "
            "rejected — otherwise the consumer crashes later on a "
            "None doc_id."
        )
        assert isinstance(err, str) and len(err) > 0

    def test_wrong_type_value_is_rejected(self) -> None:
        """A field with the wrong JSON type (here: ``entities`` passed
        as a string instead of an array) must be caught at the edge,
        not when the legacy upsert tries to iterate it."""
        from services.graph.app.consumer import _validate_inbound_event

        payload = {
            "doc_id": "doc-1",
            "entities": "not-an-array",  # should be array
        }

        err = _validate_inbound_event(payload)
        assert err is not None
        # The error should name the offending field / type so DLQ
        # consumers can diagnose without spelunking through logs.
        assert "array" in err.lower() or "entities" in err.lower() or "type" in err.lower()

    def test_invalid_event_type_enum_is_rejected(self) -> None:
        """``event_type`` is constrained to a fixed enum; an arbitrary
        string must fail so a producer can't introduce phantom event
        types that bypass the downstream ``status`` routing."""
        from services.graph.app.consumer import _validate_inbound_event

        payload = {
            "document_id": "doc-1",
            "event_type": "delete_everything",  # not in enum
            "doc_hash": "h",
            "text_clean": "t",
            "extraction": {},
        }

        err = _validate_inbound_event(payload)
        assert err is not None

    def test_non_dict_payload_is_rejected(self) -> None:
        """If the deserializer falls back to raw bytes (magic-byte
        mismatch), the payload reaches ``_validate_inbound_event`` as
        a non-dict. Must be rejected with a clear error, not a
        TypeError from ``iter_errors``."""
        from services.graph.app.consumer import _validate_inbound_event

        err = _validate_inbound_event(b"\x00\x01raw-bytes")
        assert err is not None
        assert "not a json object" in err.lower() or "bytes" in err.lower()

    def test_none_payload_is_rejected(self) -> None:
        from services.graph.app.consumer import _validate_inbound_event

        err = _validate_inbound_event(None)
        assert err is not None


class TestDlqReasonLabel:
    """The DLQ counter must carry a ``schema_invalid`` label so ops
    can alert on producer-bug spikes separately from upsert errors."""

    def test_dlq_counter_supports_schema_invalid_reason(self) -> None:
        from services.graph.app.consumer import DLQ_COUNTER

        # prometheus_client raises on unknown label values only if
        # labels are pre-declared; here ``reason`` is a free-form
        # label so any string works. The assertion is that the
        # counter object exists and is label-compatible.
        metric = DLQ_COUNTER.labels(reason="schema_invalid")
        assert metric is not None
